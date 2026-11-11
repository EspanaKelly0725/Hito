"""Hito as an MCP server: the same contract-to-cash tools, for any AI agent.

The web app is one client of Hito's API. This is the other: a Model Context
Protocol server over stdio that exposes the whole flow as tools, so Claude
Desktop, Claude Code, or any MCP-speaking agent can read a contract, invoice a
milestone through PayPal, score the risk, draft a reminder and propose a split,
with the same guardrails the UI has:

  * the reviewer still has to clear every invoice
  * payout items above the ceiling still come back as "needs a human", and the
    tool refuses to send them without an explicit approval argument

That is the point. The guardrails live in the service, not in the UI, so they
hold no matter who is driving.

Run it directly:            python -m app.mcp_server
Point Claude Desktop at it: see docs/MCP.md

No dependencies: the protocol here is JSON-RPC 2.0 over stdin/stdout, which is
all MCP stdio transport is.
"""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Any, Callable

from . import db
from .agents import contract_parser, splitter
from .config import settings

PROTOCOL_VERSION = "2025-06-18"
SERVER_INFO = {"name": "hito", "version": "1.0.0"}

TOOLS: list[dict] = []
HANDLERS: dict[str, Callable[..., Any]] = {}


def tool(name: str, description: str, schema: dict):
    def decorator(fn):
        TOOLS.append({
            "name": name,
            "description": description,
            "inputSchema": schema,
        })
        HANDLERS[name] = fn
        return fn

    return decorator


def obj(properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }


STR = {"type": "string"}
NUM = {"type": "number"}


# ---------------------------------------------------------------------------
# tools
# ---------------------------------------------------------------------------

@tool(
    "read_contract",
    "Read a freelance contract and return the proposed payment plan: client, "
    "milestones with amounts and due dates, collaborator revenue shares, and "
    "anything about the contract worth flagging. Creates nothing.",
    obj({"text": dict(STR, description="The full contract text."),
         "filename": STR}, ["text"]),
)
async def read_contract(text: str, filename: str = "contract.txt") -> dict:
    plan = contract_parser.parse(text, filename=filename)
    db.log_agent_run("contract_parser", plan, verdict="mcp")
    db.log_event("contract.parsed",
                 f"[MCP] Read {filename}: {len(plan['milestones'])} milestones",
                 payload={"via": "mcp"})
    return plan


@tool(
    "approve_plan",
    "Record an approved payment plan as a project. This is the only way a "
    "project is created; call it after a human has agreed to the plan.",
    obj({
        "project_name": STR,
        "client_name": STR,
        "client_email": STR,
        "client_country": STR,
        "currency": STR,
        "contract_text": STR,
        "milestones": {
            "type": "array",
            "items": obj({"title": STR, "description": STR, "amount": NUM,
                          "due_date": STR, "contract_quote": STR},
                         ["title", "amount"]),
        },
        "collaborators": {
            "type": "array",
            "items": obj({"name": STR, "email": STR, "role": STR, "pct": NUM},
                         ["name", "email", "pct"]),
        },
    }, ["project_name", "client_name", "client_email", "milestones"]),
)
async def approve_plan(**kwargs) -> dict:
    from .main import PlanApproval, approve_plan as handler

    payload = PlanApproval(
        project_name=kwargs["project_name"],
        client_name=kwargs["client_name"],
        client_email=kwargs["client_email"],
        client_country=kwargs.get("client_country", ""),
        currency=kwargs.get("currency", "USD"),
        contract_text=kwargs.get("contract_text", ""),
        milestones=kwargs["milestones"],
        collaborators=kwargs.get("collaborators", []),
    )
    return await handler(payload)


@tool(
    "list_milestones",
    "List every milestone Hito knows about, with its state, amount, due date, "
    "invoice and - for anything invoiced - the current risk of not being paid.",
    obj({}),
)
async def list_milestones() -> dict:
    from .main import dashboard

    data = await dashboard()
    return {
        "milestones": [
            {k: m.get(k) for k in (
                "id", "title", "amount", "currency", "due_date", "status",
                "days_overdue", "invoice_number", "pd", "risk_band",
                "expected_loss", "project_name", "client_name")}
            for m in data["milestones"] if not m.get("historical")
        ],
        "totals": data["totals"],
    }


@tool(
    "invoice_milestone",
    "Mark a milestone delivered and invoice it through PayPal. An independent "
    "reviewer checks the invoice against the contract first; it can BLOCK "
    "(nothing is created) or HOLD (needs override=true to proceed). Always "
    "show the verdict to the human before overriding.",
    obj({"milestone_id": STR,
         "evidence": dict(STR, description="What was delivered, in one line."),
         "override": {"type": "boolean",
                      "description": "Proceed despite a HOLD. Only with explicit "
                                     "human approval."}},
        ["milestone_id"]),
)
async def invoice_milestone(milestone_id: str, evidence: str = "",
                            override: bool = False) -> dict:
    from .main import Delivery, deliver_milestone

    return await deliver_milestone(milestone_id, Delivery(evidence=evidence,
                                                          override=override))


@tool(
    "score_risk",
    "Score the probability that an invoiced milestone is never paid, with the "
    "factors that moved the score and the tone band the policy assigns.",
    obj({"milestone_id": STR}, ["milestone_id"]),
)
async def score_risk(milestone_id: str) -> dict:
    from .main import milestone_risk

    return await milestone_risk(milestone_id)


@tool(
    "draft_reminder",
    "Draft a payment reminder for an overdue milestone. The risk score picks "
    "the register (friendly / firm / offer a payment plan); the draft is not "
    "sent until send_reminder is called.",
    obj({"milestone_id": STR}, ["milestone_id"]),
)
async def draft_reminder(milestone_id: str) -> dict:
    from .main import draft_dunning

    return await draft_dunning(milestone_id)


@tool(
    "send_reminder",
    "Send a drafted reminder to the client as a PayPal invoice reminder. This "
    "contacts the client - get human approval first.",
    obj({"dunning_id": STR, "subject": STR, "body": STR}, ["dunning_id"]),
)
async def send_reminder(dunning_id: str, subject: str = "", body: str = "") -> dict:
    from .main import DunningEdit, send_dunning

    return await send_dunning(dunning_id,
                              DunningEdit(subject=subject or None,
                                          body=body or None))


@tool(
    "propose_split",
    "Propose how a paid milestone is split among collaborators. Amounts are "
    "computed exactly in Python, never by a model. Items above the approval "
    "ceiling come back flagged.",
    obj({"milestone_id": STR}, ["milestone_id"]),
)
async def propose_split(milestone_id: str) -> dict:
    from .main import propose_payout

    return await propose_payout(milestone_id)


@tool(
    "send_payout",
    "Send a proposed payout through PayPal Payouts. Items flagged as needing "
    "approval are only sent when their id is listed in approved_item_ids, and "
    "that list must come from a human, never from your own judgment.",
    obj({"payout_id": STR,
         "approved_item_ids": {"type": "array", "items": STR}},
        ["payout_id"]),
)
async def send_payout(payout_id: str, approved_item_ids: list[str] | None = None) -> dict:
    from .main import PayoutApproval, approve_payout

    return await approve_payout(
        payout_id, PayoutApproval(approved_item_ids=approved_item_ids or [])
    )


@tool(
    "explain_risk_model",
    "Return the risk model card: fitted weights, out-of-sample metrics, the "
    "band cut-offs and the tone policy they drive.",
    obj({}),
)
async def explain_risk_model() -> dict:
    from .risk import risk_model

    return risk_model.describe()


@tool(
    "audit_trail",
    "Return the ledger of what happened and who decided it - which actions were "
    "taken by an agent and which by the human.",
    obj({"limit": {"type": "integer"}}),
)
async def audit_trail(limit: int = 40) -> dict:
    from .main import events

    return {"events": await events(limit=limit)}


# ---------------------------------------------------------------------------
# JSON-RPC plumbing
# ---------------------------------------------------------------------------

async def dispatch(message: dict) -> dict | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return reply(request_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": SERVER_INFO,
            "instructions": (
                "Hito turns a freelance contract into invoices, risk-weighted "
                "collection messages and collaborator payouts through PayPal. "
                "Two rules you must not work around: an invoice the reviewer "
                "HOLDs needs explicit human approval before override=true, and a "
                "payout item flagged needs_approval is only sent when the human "
                "names its id. Never approve on the human's behalf."
            ),
        })

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "tools/list":
        return reply(request_id, {"tools": TOOLS})

    if method == "tools/call":
        name = params.get("name", "")
        arguments = params.get("arguments") or {}
        handler = HANDLERS.get(name)
        if handler is None:
            return error(request_id, -32601, f"unknown tool: {name}")
        try:
            result = await handler(**arguments)
            return reply(request_id, {
                "content": [{
                    "type": "text",
                    "text": json.dumps(result, ensure_ascii=False, indent=2,
                                       default=str),
                }],
                "isError": False,
            })
        except Exception as exc:  # surfaced to the agent, not swallowed
            detail = getattr(exc, "detail", None) or str(exc)
            return reply(request_id, {
                "content": [{"type": "text",
                             "text": json.dumps({"error": str(detail)},
                                                default=str)}],
                "isError": True,
            })

    if method == "ping":
        return reply(request_id, {})

    return error(request_id, -32601, f"unknown method: {method}")


def reply(request_id: Any, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error(request_id: Any, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": request_id,
            "error": {"code": code, "message": message}}


def serve() -> None:
    """Read newline-delimited JSON-RPC from stdin, write responses to stdout.

    Deliberately a plain blocking loop over sys.stdin rather than an asyncio
    pipe: `loop.connect_read_pipe` on stdin is not supported on Windows, and
    the server has to run wherever the person's Claude Desktop runs.
    """
    db.connect()
    print(
        f"hito mcp server ready | paypal={settings.modes()['paypal']} "
        f"| ai={settings.modes()['ai']} | {len(TOOLS)} tools",
        file=sys.stderr, flush=True,
    )

    for line in sys.stdin:
        text = line.strip()
        if not text:
            continue
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            continue
        try:
            response = asyncio.run(dispatch(message))
        except Exception as exc:  # never let one bad call kill the server
            response = error(message.get("id"), -32603, str(exc))
        if response is not None:
            sys.stdout.write(json.dumps(response, default=str) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        pass
