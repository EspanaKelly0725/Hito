"""Hito - FastAPI application.

The five moments of the product, as HTTP:

  1. POST /api/contracts/parse        read the contract, propose the plan
     POST /api/projects               Laura approves it
  2. POST /api/milestones/{id}/deliver   she delivered -> reviewer -> PayPal invoice
  3. POST /api/webhooks/paypal        the money landed
  4. POST /api/milestones/{id}/dunning   risk model picks the tone, Claude writes it
  5. POST /api/milestones/{id}/payout/propose  split it, with an approval ceiling

Everything an agent decides is written to `events` with actor='agent'; everything
Laura decides is written with actor='human'. The dashboard reads that table, so
the audit trail is the product, not an afterthought.
"""
from __future__ import annotations

import io
import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import db
from .agents import collector, contract_parser, llm, reviewer, splitter
from .config import settings
from .paypal import PayPalError, gateway
from .risk import risk_model

@asynccontextmanager
async def lifespan(_: FastAPI):
    db.connect()
    _ensure_column("projects", "client_language", "TEXT")
    db.log_event(
        "app.start",
        f"Hito up. PayPal={settings.modes()['paypal']}, AI={settings.modes()['ai']}, "
        f"risk model AUC={risk_model.metrics.get('auc')}",
        actor="system",
    )
    yield


app = FastAPI(
    title="Hito API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Contract-to-cash for freelancers. Reads the contract, invoices each "
        "milestone through PayPal, scores the risk of not being paid, asks for the "
        "money in the register that risk deserves, and splits what arrives."
    ),
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def today() -> date:
    return datetime.now(timezone.utc).date()


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def days_overdue(milestone: dict) -> int:
    due = parse_date(milestone.get("due_date"))
    if not due or milestone.get("paid_at"):
        return 0
    return max((today() - due).days, 0)


def effective_status(milestone: dict) -> str:
    status = milestone.get("status") or "pending"
    if status == "invoiced" and days_overdue(milestone) > 0:
        return "overdue"
    return status


def client_history(client_email: str, *, exclude_project: str | None = None) -> dict:
    """What Hito knows about this client from its own ledger.

    Feeds the risk model: how many invoices this client has settled, how often
    late, and how late. No external bureau, no credit file - just behaviour
    observed inside Hito.
    """
    rows = db.query(
        """
        SELECT m.due_date, m.paid_at, m.amount
        FROM milestones m JOIN projects p ON p.id = m.project_id
        WHERE lower(p.client_email) = lower(?) AND m.paid_at IS NOT NULL
          AND (? IS NULL OR m.project_id <> ?)
        """,
        (client_email, exclude_project, exclude_project),
    )
    settled, late, total_days = 0, 0, 0
    for row in rows:
        due = parse_date(row["due_date"])
        paid = parse_date(row["paid_at"])
        if not due or not paid:
            continue
        settled += 1
        delta = (paid - due).days
        if delta > 0:
            late += 1
            total_days += delta
    return {
        "invoices_settled": settled,
        "late_ratio": round(late / settled, 4) if settled else 0.0,
        "avg_days_late": round(total_days / late, 1) if late else 0.0,
    }


def score_milestone(project: dict, milestone: dict) -> dict:
    history = client_history(project["client_email"], exclude_project=project["id"])
    return risk_model.score(
        amount=float(milestone.get("amount") or 0),
        prior_late_ratio=history["late_ratio"],
        prior_avg_days_late=history["avg_days_late"],
        relationship_invoices=history["invoices_settled"],
        cross_border=(project.get("client_country") or "").upper() not in ("", "CO"),
        days_overdue=days_overdue(milestone),
    )


def get_project(project_id: str) -> dict:
    row = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not row:
        raise HTTPException(404, "project not found")
    return row


def get_milestone(milestone_id: str) -> tuple[dict, dict]:
    row = db.one("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
    if not row:
        raise HTTPException(404, "milestone not found")
    return row, get_project(row["project_id"])


def project_for_agent(project: dict) -> dict:
    """Project row plus the fields the agents expect."""
    return {
        **project,
        "name": project.get("name"),
        "invoicer_name": f"{settings.invoicer_given_name} "
                         f"{settings.invoicer_surname}".strip(),
        "client_language": project.get("client_language") or "en",
        "team_language": "es",
    }


def extract_text(filename: str, raw: bytes) -> str:
    lower = (filename or "").lower()
    if lower.endswith(".pdf") or raw[:4] == b"%PDF":
        try:
            from pypdf import PdfReader

            reader = PdfReader(io.BytesIO(raw))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n".join(pages).strip()
            if text:
                return text
            raise HTTPException(
                422,
                "That PDF has no extractable text layer (it looks scanned). "
                "Upload a text PDF, or paste the contract text instead.",
            )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(422, f"Could not read the PDF: {exc}")
    for encoding in ("utf-8", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(422, "Unsupported file type. Use PDF, TXT or MD.")


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

@app.get("/api/status")
async def status() -> dict:
    gw = gateway()
    counts = db.one(
        """
        SELECT
          (SELECT COUNT(*) FROM projects)   AS projects,
          (SELECT COUNT(*) FROM milestones) AS milestones,
          (SELECT COUNT(*) FROM events)     AS events
        """
    ) or {}
    spend = db.one(
        "SELECT COUNT(*) AS runs, COALESCE(SUM(cost_usd), 0) AS cost FROM agent_runs"
    ) or {}
    return {
        "app": "Hito",
        "version": "1.0.0",
        "modes": settings.modes(),
        "paypal": await gw.health(),
        "ai": llm.status(),
        "risk_model": {
            "trained": risk_model.trained,
            "metrics": risk_model.metrics,
            "n_train": risk_model.n_train,
        },
        "counts": counts,
        "agent_spend": {
            "runs": spend.get("runs", 0),
            "cost_usd": round(float(spend.get("cost", 0) or 0), 6),
        },
    }


@app.get("/api/risk/model")
async def risk_model_card() -> dict:
    return risk_model.describe()


class RiskWhatIf(BaseModel):
    amount: float = 3000
    prior_late_ratio: float = 0.0
    prior_avg_days_late: float = 0.0
    relationship_invoices: int = 0
    cross_border: bool = True
    days_overdue: float = 0


@app.post("/api/risk/score")
async def risk_score(payload: RiskWhatIf) -> dict:
    """What-if endpoint: move the inputs, watch the tone decision change."""
    return risk_model.score(**payload.model_dump())


# ---------------------------------------------------------------------------
# 1. read the contract
# ---------------------------------------------------------------------------

@app.post("/api/contracts/parse")
async def parse_contract(file: UploadFile | None = File(default=None),
                         text: str | None = Form(default=None)) -> dict:
    if file is not None:
        raw = await file.read()
        if len(raw) > 8 * 1024 * 1024:
            raise HTTPException(413, "Contract files are limited to 8 MB.")
        contract_text = extract_text(file.filename or "contract.pdf", raw)
        filename = file.filename or "contract.pdf"
    elif text:
        contract_text, filename = text, "pasted-contract.txt"
    else:
        raise HTTPException(400, "Send a contract file or the contract text.")

    plan = contract_parser.parse(contract_text, filename=filename)
    db.log_agent_run("contract_parser", plan,
                     verdict=f"{len(plan['milestones'])} milestones")
    db.log_event(
        "contract.parsed",
        f"Read {filename}: {len(plan['milestones'])} milestones, "
        f"{plan['currency']} {llm.money(plan['total_amount'])} total",
        payload={"warnings": plan["warnings"], "engine": plan["_meta"].get("engine")},
    )
    plan["contract_text"] = contract_text
    plan["contract_filename"] = filename
    return plan


class Milestone(BaseModel):
    title: str
    description: str = ""
    amount: float
    due_date: str = ""
    contract_quote: str = ""


class Collaborator(BaseModel):
    name: str
    email: str
    role: str = "collaborator"
    pct: float


class PlanApproval(BaseModel):
    project_name: str
    client_name: str
    client_email: str
    client_country: str = ""
    client_language: str = "en"
    currency: str = "USD"
    total_amount: float = 0
    payment_terms: str = ""
    contract_text: str = ""
    contract_filename: str = ""
    contract_summary: str = ""
    milestones: list[Milestone] = Field(default_factory=list)
    collaborators: list[Collaborator] = Field(default_factory=list)


@app.post("/api/projects")
async def approve_plan(payload: PlanApproval) -> dict:
    """Laura approves the plan. This is the only way a project comes into being."""
    if not payload.milestones:
        raise HTTPException(400, "A plan needs at least one milestone.")
    if not payload.client_email:
        raise HTTPException(400, "The client needs an email to be invoiced.")

    project_id = db.new_id("prj")
    db.insert("projects", {
        "id": project_id,
        "name": payload.project_name,
        "client_name": payload.client_name,
        "client_email": payload.client_email,
        "client_country": payload.client_country.upper(),
        "currency": payload.currency.upper(),
        "total_amount": payload.total_amount
        or round(sum(m.amount for m in payload.milestones), 2),
        "contract_filename": payload.contract_filename,
        "contract_text": payload.contract_text,
        "contract_summary": payload.payment_terms,
        "status": "active",
        "created_at": db.now(),
    })
    db.execute("UPDATE projects SET client_country = ? WHERE id = ?",
               (payload.client_country.upper(), project_id))
    # client_language lives on the project row; add it without a migration dance
    _ensure_column("projects", "client_language", "TEXT")
    db.execute("UPDATE projects SET client_language = ? WHERE id = ?",
               (payload.client_language, project_id))

    for idx, milestone in enumerate(payload.milestones, start=1):
        db.insert("milestones", {
            "id": db.new_id("ms"),
            "project_id": project_id,
            "idx": idx,
            "title": milestone.title,
            "description": milestone.description,
            "amount": round(milestone.amount, 2),
            "currency": payload.currency.upper(),
            "due_date": milestone.due_date or "",
            "status": "pending",
            "contract_quote": milestone.contract_quote,
        })
    for collaborator in payload.collaborators:
        db.insert("collaborators", {
            "id": db.new_id("col"),
            "project_id": project_id,
            "name": collaborator.name,
            "email": collaborator.email,
            "role": collaborator.role,
            "pct": collaborator.pct,
        })

    db.log_event(
        "plan.approved",
        f"Laura approved the plan for {payload.project_name}: "
        f"{len(payload.milestones)} milestones, "
        f"{payload.currency} {llm.money(payload.total_amount)}",
        actor="human", project_id=project_id,
    )
    return {"project_id": project_id, "ok": True}


def _ensure_column(table: str, column: str, decl: str) -> None:
    cols = {r["name"] for r in db.query(f"PRAGMA table_info({table})")}
    if column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


# ---------------------------------------------------------------------------
# 2. deliver -> review -> invoice
# ---------------------------------------------------------------------------

class Delivery(BaseModel):
    evidence: str = ""
    override: bool = False


@app.post("/api/milestones/{milestone_id}/deliver")
async def deliver_milestone(milestone_id: str, payload: Delivery) -> dict:
    """Laura says she delivered. The reviewer decides whether PayPal gets called."""
    milestone, project = get_milestone(milestone_id)
    if milestone.get("invoice_id"):
        raise HTTPException(409, "This milestone has already been invoiced.")

    db.update("milestones", milestone_id, {
        "status": "delivered",
        "delivered_at": db.now(),
        "evidence": payload.evidence,
    })
    milestone = db.one("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
    db.log_event("milestone.delivered",
                 f"Laura marked \"{milestone['title']}\" as delivered",
                 actor="human", project_id=project["id"])

    invoiced = db.one(
        """
        SELECT COALESCE(SUM(amount), 0) AS total FROM milestones
        WHERE project_id = ? AND invoice_id IS NOT NULL
        """,
        (project["id"],),
    )["total"]

    verdict = reviewer.review(
        contract_text=project.get("contract_text") or "",
        project=project_for_agent(project),
        milestone=milestone,
        already_invoiced=float(invoiced or 0),
        invoice_items=[{"name": milestone["title"], "amount": milestone["amount"]}],
        recipient_email=project["client_email"],
        currency=project["currency"],
    )
    db.log_agent_run("reviewer", verdict, project_id=project["id"],
                     verdict=verdict["verdict"])
    db.log_event(
        f"review.{verdict['verdict']}",
        f"Reviewer {verdict['verdict'].upper()}: {verdict['headline']}",
        project_id=project["id"],
        payload={"checks": verdict["checks"], "findings": verdict["findings"]},
    )

    if verdict["verdict"] == "block":
        db.update("milestones", milestone_id, {"status": "blocked"})
        return {"stage": "blocked", "review": verdict, "invoice": None}

    if verdict["verdict"] == "hold" and not payload.override:
        db.update("milestones", milestone_id, {"status": "delivered"})
        return {"stage": "hold", "review": verdict, "invoice": None}

    if payload.override and verdict["verdict"] == "hold":
        db.log_event("review.overridden",
                     f"Laura overrode the reviewer hold on \"{milestone['title']}\"",
                     actor="human", project_id=project["id"])

    invoice = await _create_and_send_invoice(project, milestone)
    return {"stage": "invoiced", "review": verdict, "invoice": invoice}


async def _create_and_send_invoice(project: dict, milestone: dict) -> dict:
    gw = gateway()
    try:
        number = await gw.next_invoice_number()
        due = milestone.get("due_date") or (today() + timedelta(days=14)).isoformat()
        invoice = await gw.create_invoice(
            number=number,
            currency=project["currency"],
            note=(
                f"{milestone['title']} - {project['name']}. "
                f"Thank you for working with "
                f"{settings.invoicer_business or 'us'}."
            ),
            terms=project.get("contract_summary")
            or "Payable on delivery of this milestone, per our agreement.",
            invoice_date=today().isoformat(),
            due_date=due,
            recipient_name=project["client_name"],
            recipient_email=project["client_email"],
            items=[{
                "name": milestone["title"],
                "description": milestone.get("description") or "",
                "amount": milestone["amount"],
            }],
            reference=f"{project['id']}-{milestone['id']}",
        )
        sent = await gw.send_invoice(
            invoice["id"],
            subject=f"Invoice {number} - {milestone['title']}",
            note=f"Invoice for {milestone['title']} on {project['name']}.",
        )
    except PayPalError as exc:
        db.log_event("invoice.failed",
                     f"PayPal refused the invoice: {exc}",
                     actor="paypal", project_id=project["id"],
                     payload=exc.as_dict())
        raise HTTPException(502, detail=exc.as_dict())

    db.update("milestones", milestone["id"], {
        "status": "invoiced",
        "invoice_id": sent["id"],
        "invoice_number": sent.get("number") or number,
        "invoice_url": sent.get("view_url") or "",
        "invoiced_at": db.now(),
        "due_date": milestone.get("due_date") or due,
    })
    db.log_event(
        "invoice.sent",
        f"Invoice {sent.get('number') or number} for "
        f"{project['currency']} {llm.money(milestone['amount'])} sent to "
        f"{project['client_email']}",
        payload={"invoice_id": sent["id"], "gateway": gw.mode},
        project_id=project["id"],
    )
    return {
        "id": sent["id"],
        "number": sent.get("number") or number,
        "status": sent.get("status"),
        "view_url": sent.get("view_url"),
        "amount": milestone["amount"],
        "gateway": gw.mode,
    }


# ---------------------------------------------------------------------------
# 3. the money lands
# ---------------------------------------------------------------------------

def _apply_payment(invoice_id: str, amount: float | None, source: str) -> dict | None:
    milestone = db.one("SELECT * FROM milestones WHERE invoice_id = ?", (invoice_id,))
    if not milestone:
        return None
    if milestone.get("paid_at"):
        return milestone
    paid = float(amount if amount is not None else milestone["amount"])
    db.update("milestones", milestone["id"], {
        "status": "paid",
        "paid_at": db.now(),
        "paid_amount": paid,
    })
    project = get_project(milestone["project_id"])
    db.log_event(
        "payment.received",
        f"{project['currency']} {llm.money(paid)} received for "
        f"\"{milestone['title']}\" (invoice {milestone.get('invoice_number')})",
        actor="paypal", project_id=project["id"],
        payload={"source": source, "invoice_id": invoice_id},
    )
    return db.one("SELECT * FROM milestones WHERE id = ?", (milestone["id"],))


@app.post("/api/webhooks/paypal")
async def paypal_webhook(request: Request) -> JSONResponse:
    """PayPal webhook. Verified against the webhook id when one is configured."""
    raw = await request.body()
    try:
        body = json.loads(raw or b"{}")
    except json.JSONDecodeError:
        raise HTTPException(400, "webhook body was not JSON")

    verification = await gateway().verify_webhook(
        headers=dict(request.headers), body=body
    )
    event_type = body.get("event_type", "")
    resource = body.get("resource", {}) or {}
    invoice_id = resource.get("id") or resource.get("invoice", {}).get("id", "")

    db.insert("webhook_log", {
        "id": db.new_id("wh"),
        "ts": db.now(),
        "event_type": event_type,
        "verified": verification,
        "resource_id": invoice_id,
        "raw": json.dumps(body)[:20000],
    })

    if verification == "FAILURE":
        db.log_event("webhook.rejected",
                     f"Rejected an unverified {event_type} webhook",
                     actor="system", payload={"resource_id": invoice_id})
        raise HTTPException(401, "webhook signature verification failed")

    handled = False
    if event_type in ("INVOICING.INVOICE.PAID", "INVOICING.INVOICE.PARTIALLY_PAID"):
        amount = None
        for key in ("payments", "due_amount", "amount"):
            node = resource.get(key)
            if isinstance(node, dict) and node.get("value"):
                amount = float(node["value"])
                break
        milestone = _apply_payment(invoice_id, amount, source=f"webhook:{event_type}")
        handled = milestone is not None

    return JSONResponse({"ok": True, "verified": verification, "handled": handled})


@app.post("/api/milestones/{milestone_id}/simulate-payment")
async def simulate_payment(milestone_id: str) -> dict:
    """Demo shortcut: pretend the client paid, through the same code path.

    In mock mode this is the equivalent of clicking Pay on the invoice. With real
    PayPal credentials it marks the milestone paid locally so a demo can continue
    without waiting for a sandbox buyer to log in - the event log records that the
    payment was simulated, not received.
    """
    milestone, project = get_milestone(milestone_id)
    if not milestone.get("invoice_id"):
        raise HTTPException(409, "Invoice this milestone first.")
    gw = gateway()
    if gw.mode == "mock":
        gw.mark_paid(milestone["invoice_id"])
    updated = _apply_payment(milestone["invoice_id"], milestone["amount"],
                             source="simulated")
    return {"ok": True, "milestone": updated}


# ---------------------------------------------------------------------------
# 4. collect, with tact
# ---------------------------------------------------------------------------

@app.get("/api/milestones/{milestone_id}/risk")
async def milestone_risk(milestone_id: str) -> dict:
    milestone, project = get_milestone(milestone_id)
    return {
        "milestone_id": milestone_id,
        "days_overdue": days_overdue(milestone),
        "history": client_history(project["client_email"],
                                  exclude_project=project["id"]),
        **score_milestone(project, milestone),
    }


@app.post("/api/milestones/{milestone_id}/dunning")
async def draft_dunning(milestone_id: str) -> dict:
    """Score the risk, let the band pick the tone, have Claude write the draft."""
    milestone, project = get_milestone(milestone_id)
    if milestone.get("paid_at"):
        raise HTTPException(409, "This milestone is already paid.")
    if not milestone.get("invoice_id"):
        raise HTTPException(409, "Nothing to chase: this milestone is not invoiced.")

    risk = score_milestone(project, milestone)
    risk["days_overdue"] = days_overdue(milestone)
    history = client_history(project["client_email"], exclude_project=project["id"])
    history["reminder_count"] = db.one(
        "SELECT COUNT(*) AS n FROM dunning WHERE milestone_id = ? AND status = 'sent'",
        (milestone_id,),
    )["n"]

    message = collector.draft(
        project=project_for_agent(project),
        milestone=milestone,
        risk=risk,
        days_overdue=days_overdue(milestone),
        history=history,
        invoice_url=milestone.get("invoice_url") or "",
    )
    db.log_agent_run("collector", message, project_id=project["id"],
                     verdict=risk["tone"])

    dunning_id = db.new_id("dun")
    db.insert("dunning", {
        "id": dunning_id,
        "milestone_id": milestone_id,
        "created_at": db.now(),
        "days_overdue": days_overdue(milestone),
        "pd": risk["pd"],
        "band": risk["band"],
        "tone": risk["tone"],
        "expected_loss": risk["expected_loss"],
        "subject": message.get("subject", ""),
        "body": message.get("body", ""),
        "offer": json.dumps(message.get("offer_terms") or {}),
        "factors": json.dumps(risk["factors"]),
        "status": "draft",
    })
    db.log_event(
        "dunning.drafted",
        f"Drafted a {risk['tone']} reminder for \"{milestone['title']}\" "
        f"(PD {risk['pd']:.0%}, {days_overdue(milestone)} days overdue)",
        project_id=project["id"],
        payload={"top_factors": risk["top_factors"]},
    )
    return {
        "dunning_id": dunning_id,
        "risk": risk,
        "history": history,
        "message": message,
        "engine": message.get("_meta", {}).get("engine"),
    }


class DunningEdit(BaseModel):
    subject: str | None = None
    body: str | None = None


@app.post("/api/dunning/{dunning_id}/send")
async def send_dunning(dunning_id: str, payload: DunningEdit) -> dict:
    """Laura presses send. Delivered as a PayPal invoice reminder."""
    row = db.one("SELECT * FROM dunning WHERE id = ?", (dunning_id,))
    if not row:
        raise HTTPException(404, "draft not found")
    if row["status"] == "sent":
        raise HTTPException(409, "This reminder was already sent.")
    milestone, project = get_milestone(row["milestone_id"])

    subject = payload.subject or row["subject"]
    body = payload.body or row["body"]
    try:
        result = await gateway().send_reminder(
            milestone["invoice_id"], subject=subject, note=body
        )
    except PayPalError as exc:
        raise HTTPException(502, detail=exc.as_dict())

    db.update("dunning", dunning_id, {
        "status": "sent", "sent_at": db.now(),
        "subject": subject, "body": body,
    })
    db.log_event(
        "dunning.sent",
        f"Laura sent the {row['tone']} reminder for \"{milestone['title']}\"",
        actor="human", project_id=project["id"],
        payload={"channel": result.get("channel"), "subject": subject},
    )
    return {"ok": True, "channel": result.get("channel"), "dunning_id": dunning_id}


@app.get("/api/dunning")
async def list_dunning() -> list[dict]:
    return db.query(
        """
        SELECT d.*, m.title AS milestone_title, m.invoice_number, p.client_name
        FROM dunning d
        JOIN milestones m ON m.id = d.milestone_id
        JOIN projects p ON p.id = m.project_id
        ORDER BY d.created_at DESC
        """
    )


# ---------------------------------------------------------------------------
# 5. split it
# ---------------------------------------------------------------------------

@app.post("/api/milestones/{milestone_id}/payout/propose")
async def propose_payout(milestone_id: str) -> dict:
    milestone, project = get_milestone(milestone_id)
    if not milestone.get("paid_at"):
        raise HTTPException(409, "Nothing to split yet: this milestone is not paid.")
    existing = db.one(
        "SELECT * FROM payouts WHERE milestone_id = ? AND status <> 'failed'",
        (milestone_id,),
    )
    if existing:
        return {
            "payout_id": existing["id"],
            "already_exists": True,
            "status": existing["status"],
            "items": db.query(
                "SELECT * FROM payout_items WHERE payout_id = ?", (existing["id"],)
            ),
        }

    collaborators = db.query(
        "SELECT * FROM collaborators WHERE project_id = ?", (project["id"],)
    )
    if not collaborators:
        raise HTTPException(409, "This project has no collaborators to pay.")

    proposal = splitter.propose(
        project=project_for_agent(project),
        milestone=milestone,
        collaborators=collaborators,
        paid_amount=float(milestone.get("paid_amount") or milestone["amount"]),
    )
    db.log_agent_run("splitter", proposal, project_id=project["id"],
                     verdict=f"{len(proposal['items'])} items")

    payout_id = db.new_id("pay")
    db.insert("payouts", {
        "id": payout_id,
        "project_id": project["id"],
        "milestone_id": milestone_id,
        "created_at": db.now(),
        "status": "proposed",
        "total": round(sum(i["amount"] for i in proposal["items"]), 2),
        "currency": proposal["currency"],
        "rationale": proposal["rationale"],
    })
    for item in proposal["items"]:
        db.insert("payout_items", {
            "id": db.new_id("pit"),
            "payout_id": payout_id,
            "collaborator_id": item.get("collaborator_id"),
            "name": item["name"],
            "email": item["email"],
            "role": item["role"],
            "pct": item["pct"],
            "amount": item["amount"],
            "needs_approval": 1 if item["needs_approval"] else 0,
            "approved": 0,
            "status": "proposed",
            "note": item.get("note", ""),
        })

    db.log_event(
        "payout.proposed",
        f"Proposed splitting {proposal['currency']} "
        f"{llm.money(proposal['paid_amount'])}: "
        + ", ".join(f"{i['pct']}% to {i['name']}" for i in proposal["items"]),
        project_id=project["id"],
        payload={"retained": proposal["retained"],
                 "needs_approval": proposal["needs_approval"],
                 "threshold": proposal["threshold"]},
    )
    return {
        "payout_id": payout_id,
        **proposal,
        "items": db.query(
            "SELECT * FROM payout_items WHERE payout_id = ?", (payout_id,)
        ),
    }


class PayoutApproval(BaseModel):
    approved_item_ids: list[str] = Field(default_factory=list)


@app.post("/api/payouts/{payout_id}/approve")
async def approve_payout(payout_id: str, payload: PayoutApproval) -> dict:
    """Send the payout. Items above the ceiling only go if Laura ticked them."""
    payout = db.one("SELECT * FROM payouts WHERE id = ?", (payout_id,))
    if not payout:
        raise HTTPException(404, "payout not found")
    if payout["status"] == "sent":
        raise HTTPException(409, "This payout was already sent.")

    items = db.query("SELECT * FROM payout_items WHERE payout_id = ?", (payout_id,))
    approved = set(payload.approved_item_ids)
    to_send, held = [], []
    for item in items:
        if item["needs_approval"] and item["id"] not in approved:
            held.append(item)
            continue
        to_send.append(item)

    if not to_send:
        raise HTTPException(
            400,
            "Every item in this payout is above the approval ceiling and none "
            "was approved.",
        )

    project = get_project(payout["project_id"])
    gw = gateway()
    batch_id = f"hito-{payout_id}"
    try:
        result = await gw.create_payout(
            batch_id=batch_id,
            subject=f"Payout - {project['name']}"[:60],
            message=payout.get("rationale") or "Your share of the milestone payment.",
            items=[
                {"id": i["id"], "email": i["email"], "amount": i["amount"],
                 "note": i.get("note") or ""}
                for i in to_send
            ],
            currency=payout["currency"],
        )
    except PayPalError as exc:
        db.update("payouts", payout_id, {"status": "failed"})
        db.log_event("payout.failed", f"PayPal refused the payout: {exc}",
                     actor="paypal", project_id=project["id"], payload=exc.as_dict())
        raise HTTPException(502, detail=exc.as_dict())

    for item in to_send:
        db.update("payout_items", item["id"], {"status": "sent", "approved": 1})
    for item in held:
        db.update("payout_items", item["id"], {"status": "held"})

    db.update("payouts", payout_id, {
        "status": "sent",
        "batch_id": result["batch_id"],
        "approved_at": db.now(),
        "sent_at": db.now(),
        "total": round(sum(i["amount"] for i in to_send), 2),
    })
    db.log_event(
        "payout.sent",
        f"Laura approved and sent {payout['currency']} "
        f"{llm.money(sum(i['amount'] for i in to_send))} to "
        f"{len(to_send)} collaborator(s) via PayPal Payouts"
        + (f"; {len(held)} item(s) held" if held else ""),
        actor="human", project_id=project["id"],
        payload={"batch_id": result["batch_id"], "gateway": gw.mode},
    )
    return {
        "ok": True,
        "batch_id": result["batch_id"],
        "batch_status": result["status"],
        "sent": [i["id"] for i in to_send],
        "held": [i["id"] for i in held],
        "gateway": gw.mode,
    }


@app.post("/api/payouts/{payout_id}/refresh")
async def refresh_payout(payout_id: str) -> dict:
    """Ask PayPal where the batch got to.

    A real Payouts batch comes back PENDING and settles over the next minute or
    two, item by item - unlike the mock, which is instant. Without this the
    dashboard would show the status at the moment of sending, forever.
    """
    payout = db.one("SELECT * FROM payouts WHERE id = ?", (payout_id,))
    if not payout:
        raise HTTPException(404, "payout not found")
    if not payout.get("batch_id"):
        raise HTTPException(409, "This payout has not been sent yet.")

    try:
        status = await gateway().get_payout(payout["batch_id"])
    except PayPalError as exc:
        raise HTTPException(502, detail=exc.as_dict())

    by_item = {
        item.get("sender_item_id"): item.get("status")
        for item in status.get("items", [])
    }
    for item_id, item_status in by_item.items():
        if item_id:
            db.update("payout_items", item_id,
                      {"status": (item_status or "").lower() or "sent"})

    db.log_event(
        "payout.refreshed",
        f"PayPal reports batch {payout['batch_id']} as {status['status']}",
        actor="paypal", project_id=payout["project_id"],
        payload={"items": by_item},
    )
    return {
        "ok": True,
        "batch_status": status["status"],
        "items": status.get("items", []),
    }


@app.get("/api/payouts")
async def list_payouts() -> list[dict]:
    payouts = db.query(
        """
        SELECT po.*, m.title AS milestone_title, p.name AS project_name
        FROM payouts po
        LEFT JOIN milestones m ON m.id = po.milestone_id
        LEFT JOIN projects p ON p.id = po.project_id
        ORDER BY po.created_at DESC
        """
    )
    for payout in payouts:
        payout["items"] = db.query(
            "SELECT * FROM payout_items WHERE payout_id = ?", (payout["id"],)
        )
    return payouts


# ---------------------------------------------------------------------------
# dashboard
# ---------------------------------------------------------------------------

@app.get("/api/dashboard")
async def dashboard() -> dict:
    projects = db.query("SELECT * FROM projects ORDER BY created_at DESC")
    milestones, invoices = [], []
    totals = {"contracted": 0.0, "invoiced": 0.0, "collected": 0.0,
              "outstanding": 0.0, "at_risk": 0.0, "overdue": 0.0}

    for project in projects:
        # Closed projects stay in the ledger (they are the client's payment
        # history, which the risk model reads) but they are not current money.
        if project.get("status") != "closed":
            totals["contracted"] += float(project.get("total_amount") or 0)
        rows = db.query(
            "SELECT * FROM milestones WHERE project_id = ? ORDER BY idx", (project["id"],)
        )
        for row in rows:
            status = effective_status(row)
            overdue = days_overdue(row)
            amount = float(row.get("amount") or 0)
            historical = project.get("status") == "closed"
            record = {
                **row,
                "status": status,
                "days_overdue": overdue,
                "project_name": project["name"],
                "client_name": project["client_name"],
                "client_email": project["client_email"],
                "currency": project["currency"],
                "historical": historical,
            }
            if historical:
                milestones.append(record)
                continue
            if status in ("invoiced", "overdue"):
                risk = score_milestone(project, row)
                record.update({
                    "pd": risk["pd"],
                    "risk_band": risk["band"],
                    "suggested_tone": risk["tone"],
                    "expected_loss": risk["expected_loss"],
                    "top_factors": risk["top_factors"],
                })
                totals["at_risk"] += risk["expected_loss"]
                totals["outstanding"] += amount
                totals["invoiced"] += amount
                if status == "overdue":
                    totals["overdue"] += amount
            elif status == "paid":
                totals["invoiced"] += amount
                totals["collected"] += float(row.get("paid_amount") or amount)

            milestones.append(record)
            if row.get("invoice_id"):
                invoices.append({
                    "invoice_id": row["invoice_id"],
                    "number": row.get("invoice_number"),
                    "milestone_id": row["id"],
                    "milestone_title": row["title"],
                    "project_name": project["name"],
                    "client_name": project["client_name"],
                    "amount": amount,
                    "currency": project["currency"],
                    "status": status,
                    "due_date": row.get("due_date"),
                    "days_overdue": overdue,
                    "paid_at": row.get("paid_at"),
                    "view_url": row.get("invoice_url"),
                    "pd": record.get("pd"),
                    "risk_band": record.get("risk_band"),
                    "expected_loss": record.get("expected_loss"),
                    "suggested_tone": record.get("suggested_tone"),
                })

    return {
        "modes": settings.modes(),
        "totals": {k: round(v, 2) for k, v in totals.items()},
        "projects": [
            {**p, "collaborators": db.query(
                "SELECT * FROM collaborators WHERE project_id = ?", (p["id"],))}
            for p in projects
        ],
        "milestones": milestones,
        "invoices": invoices,
        "payouts": await list_payouts(),
        "dunning": await list_dunning(),
        "events": db.query("SELECT * FROM events ORDER BY ts DESC, rowid DESC LIMIT 60"),
        "agent_runs": db.query(
            "SELECT * FROM agent_runs ORDER BY ts DESC, rowid DESC LIMIT 40"
        ),
        "agent_spend": db.one(
            """
            SELECT COUNT(*) AS runs,
                   COALESCE(SUM(cost_usd), 0) AS cost_usd,
                   COALESCE(SUM(input_tokens), 0) AS input_tokens,
                   COALESCE(SUM(output_tokens), 0) AS output_tokens
            FROM agent_runs
            """
        ),
        "risk_model": risk_model.describe(),
    }


@app.get("/api/events")
async def events(limit: int = 100) -> list[dict]:
    return db.query(
        "SELECT * FROM events ORDER BY ts DESC, rowid DESC LIMIT ?", (min(limit, 500),)
    )


# ---------------------------------------------------------------------------
# demo data
# ---------------------------------------------------------------------------

@app.post("/api/demo/reset")
async def demo_reset() -> dict:
    db.reset()
    db.log_event("demo.reset", "Database cleared", actor="human")
    return {"ok": True}


@app.get("/api/demo/contract")
async def demo_contract():
    pdf = settings.data_dir / "contract_laura_bluebonnet.pdf"
    if pdf.exists():
        return FileResponse(pdf, media_type="application/pdf",
                            filename=pdf.name)
    raise HTTPException(404, "Sample contract not generated. "
                             "Run: python scripts/make_demo_pdf.py")


class SeedRequest(BaseModel):
    client_email: str = "ap@bluebonnetroasters.example"


@app.post("/api/demo/seed")
async def demo_seed(payload: SeedRequest | None = None) -> dict:
    """Seed the client's past behaviour, so the risk model has something to read.

    Creates one closed project for this client, paid on time twice and 14 days
    late once. That history is what turns the reminder from "friendly" into
    "firm" - the risk score comes from Hito's own ledger, not from a constant.

    `client_email` matters: history is looked up by the client's address, so
    when you are billing a PayPal sandbox buyer, seed the history against *that*
    address or the model will correctly report it has never seen them before.
    """
    payload = payload or SeedRequest()

    # Replace only previously seeded history, never live work. Seeding has to be
    # safe to run at any point in the demo, including after a project exists -
    # wiping the database here once cost us the project we had just approved.
    for closed in db.query("SELECT id FROM projects WHERE status = 'closed'"):
        db.execute("DELETE FROM milestones WHERE project_id = ?", (closed["id"],))
        db.execute("DELETE FROM projects WHERE id = ?", (closed["id"],))

    project_id = db.new_id("prj")
    db.insert("projects", {
        "id": project_id,
        "name": "Bluebonnet Coffee - packaging refresh (2025)",
        "client_name": "Bluebonnet Coffee Roasters",
        "client_email": payload.client_email,
        "client_country": "US",
        "currency": "USD",
        "total_amount": 3600.0,
        "contract_filename": "closed-2025.pdf",
        "contract_text": "Closed engagement from 2025, kept for payment history.",
        "contract_summary": "Net 15 on each deliverable.",
        "status": "closed",
        "created_at": db.now(),
    })
    history = [
        ("Packaging concepts", 1200.0, "2025-09-15", "2025-09-15"),   # on time
        ("Label illustrations", 1200.0, "2025-10-15", "2025-10-14"),  # on time
        ("Print-ready files", 1200.0, "2025-11-15", "2025-11-29"),    # 14 days late
    ]
    for idx, (title, amount, due, paid) in enumerate(history, start=1):
        db.insert("milestones", {
            "id": db.new_id("ms"),
            "project_id": project_id,
            "idx": idx,
            "title": title,
            "description": "Historical milestone (seeded payment history)",
            "amount": amount,
            "currency": "USD",
            "due_date": due,
            "status": "paid",
            "invoice_id": f"INV2-HIST-{idx}",
            "invoice_number": f"HITO-0{idx}",
            "invoiced_at": due,
            "paid_at": paid,
            "paid_amount": amount,
        })
    db.log_event(
        "demo.seeded",
        f"Seeded 3 historical invoices for {payload.client_email} "
        "(two on time, one 14 days late)",
        actor="system", project_id=project_id,
    )
    return {
        "ok": True,
        "client_email": payload.client_email,
        "history": client_history(payload.client_email),
    }


# ---------------------------------------------------------------------------
# mock payer page (only reachable in mock mode)
# ---------------------------------------------------------------------------

MOCK_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice {number}</title>
<style>
 :root {{ color-scheme: light dark; }}
 body {{ font-family: ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
        margin: 0; background: #f3f4f6; color: #111827;
        display: flex; align-items: center; justify-content: center; min-height: 100vh; }}
 .card {{ background: #fff; border-radius: 14px; padding: 32px; width: min(560px, 92vw);
         box-shadow: 0 10px 40px rgba(0,0,0,.12); }}
 .tag {{ display: inline-block; font-size: 11px; letter-spacing: .08em;
        text-transform: uppercase; background: #fef3c7; color: #92400e;
        padding: 4px 8px; border-radius: 999px; }}
 h1 {{ font-size: 20px; margin: 16px 0 4px; }}
 .amount {{ font-size: 40px; font-weight: 650; margin: 18px 0 4px; }}
 .muted {{ color: #6b7280; font-size: 14px; }}
 table {{ width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; }}
 td {{ padding: 8px 0; border-bottom: 1px solid #e5e7eb; }}
 button {{ width: 100%; padding: 14px; border: 0; border-radius: 10px; font-size: 16px;
          font-weight: 600; background: #0070ba; color: #fff; cursor: pointer; }}
 button:hover {{ background: #005c99; }}
 .paid {{ background: #d1fae5; color: #065f46; padding: 14px; border-radius: 10px;
         text-align: center; font-weight: 600; }}
</style></head>
<body><div class="card">
 <span class="tag">Simulated PayPal invoice - no real money</span>
 <h1>{business}</h1>
 <div class="muted">Invoice {number} &middot; due {due}</div>
 <div class="amount">{currency} {amount}</div>
 <div class="muted">Billed to {recipient}</div>
 <table>{rows}</table>
 {action}
 <p class="muted" style="margin-top:18px">This page stands in for PayPal's payer view
 so the whole flow can be demonstrated without a sandbox buyer account. With
 PAYPAL_CLIENT_ID set, Hito sends a real invoice and this page is never used.</p>
</div></body></html>"""


@app.get("/mock/invoice/{invoice_id}", response_class=HTMLResponse)
async def mock_invoice(invoice_id: str) -> HTMLResponse:
    gw = gateway()
    if gw.mode != "mock":
        raise HTTPException(404, "Mock invoices only exist in mock mode.")
    invoice = await gw.get_invoice(invoice_id)
    if invoice.get("status") == "NOT_FOUND":
        raise HTTPException(404, "invoice not found")
    rows = "".join(
        f"<tr><td>{item['name']}</td>"
        f"<td style='text-align:right'>{invoice['currency']} "
        f"{llm.money(item['amount'])}</td></tr>"
        for item in invoice.get("items", [])
    )
    if invoice.get("status") == "PAID":
        action = '<div class="paid">Paid. Thank you!</div>'
    else:
        action = (
            f'<form method="post" action="/mock/invoice/{invoice_id}/pay">'
            f'<button type="submit">Pay {invoice["currency"]} '
            f'{llm.money(invoice.get("amount") or 0)}</button></form>'
        )
    return HTMLResponse(MOCK_PAGE.format(
        number=invoice.get("number", ""),
        business=settings.invoicer_business or "Freelance studio",
        due=invoice.get("due_date", ""),
        currency=invoice.get("currency", "USD"),
        amount=llm.money(invoice.get("amount") or 0),
        recipient=invoice.get("recipient_email", ""),
        rows=rows,
        action=action,
    ))


@app.post("/mock/invoice/{invoice_id}/pay", response_class=HTMLResponse)
async def mock_invoice_pay(invoice_id: str) -> HTMLResponse:
    gw = gateway()
    if gw.mode != "mock":
        raise HTTPException(404, "Mock invoices only exist in mock mode.")
    record = gw.mark_paid(invoice_id)
    if record is None:
        raise HTTPException(404, "invoice not found")
    _apply_payment(invoice_id, record.get("amount"), source="mock_payer_page")
    return await mock_invoice(invoice_id)


# ---------------------------------------------------------------------------
# static UI (built from web/ - see CLAUDE.md)
# ---------------------------------------------------------------------------

app.mount("/", StaticFiles(directory=str(settings.static_dir), html=True), name="ui")
