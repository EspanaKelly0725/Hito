"""The whole contract-to-cash loop, over HTTP, in mock mode."""
from __future__ import annotations

from app.agents import contract_parser


def test_fallback_parser_reads_the_sample_contract(contract_pdf, client):
    response = client.post(
        "/api/contracts/parse",
        files={"file": ("contract.pdf", contract_pdf, "application/pdf")},
    )
    assert response.status_code == 200
    plan = response.json()
    assert plan["total_amount"] == 9000.0
    assert plan["currency"] == "USD"
    assert len(plan["milestones"]) == 3
    assert [m["amount"] for m in plan["milestones"]] == [3000.0, 3000.0, 3000.0]
    assert [m["due_date"] for m in plan["milestones"]] == [
        "2026-10-10", "2026-10-28", "2026-11-25"
    ]
    assert plan["client_email"] == "ap@bluebonnetroasters.example"
    assert plan["client_country"] == "US"
    shares = {c["role"]: c["pct"] for c in plan["collaborators"]}
    assert shares == {"developer": 30.0, "illustrator": 20.0}
    # the fallback has to admit what it is
    assert plan["_meta"]["engine"] == "rules"
    assert any("fallback" in w for w in plan["warnings"])


def test_date_parsing_handles_the_notations_contracts_use():
    assert contract_parser.find_date("due on October 10, 2026") == "2026-10-10"
    assert contract_parser.find_date("due 10 October 2026") == "2026-10-10"
    assert contract_parser.find_date("vence el 10 de octubre de 2026") == "2026-10-10"
    assert contract_parser.find_date("due 2026-10-10") == "2026-10-10"
    assert contract_parser.find_date("due next Tuesday") == ""


def approve_sample_plan(client, contract_pdf) -> list[dict]:
    plan = client.post(
        "/api/contracts/parse",
        files={"file": ("contract.pdf", contract_pdf, "application/pdf")},
    ).json()
    payload = {
        "project_name": plan["project_name"],
        "client_name": plan["client_name"],
        "client_email": plan["client_email"],
        "client_country": plan["client_country"],
        "client_language": plan["client_language"],
        "currency": plan["currency"],
        "total_amount": plan["total_amount"],
        "payment_terms": plan["payment_terms"],
        "contract_text": plan["contract_text"],
        "contract_filename": plan["contract_filename"],
        "milestones": [
            {k: m[k] for k in
             ("title", "description", "amount", "due_date", "contract_quote")}
            for m in plan["milestones"]
        ],
        "collaborators": plan["collaborators"],
    }
    created = client.post("/api/projects", json=payload)
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    dashboard = client.get("/api/dashboard").json()
    return [m for m in dashboard["milestones"] if m["project_id"] == project_id]


def test_a_plan_needs_milestones_and_a_client_email(client):
    assert client.post("/api/projects", json={
        "project_name": "x", "client_name": "y", "client_email": "a@b.co",
        "milestones": [],
    }).status_code == 400
    assert client.post("/api/projects", json={
        "project_name": "x", "client_name": "y", "client_email": "",
        "milestones": [{"title": "t", "amount": 10}],
    }).status_code == 400


def test_full_loop_invoice_payment_split(client, contract_pdf):
    milestones = approve_sample_plan(client, contract_pdf)
    assert len(milestones) == 3
    first = milestones[0]

    delivered = client.post(f"/api/milestones/{first['id']}/deliver",
                            json={"evidence": "Logo delivered"}).json()
    assert delivered["stage"] == "invoiced"
    assert delivered["review"]["verdict"] == "approve"
    assert all(c["pass"] for c in delivered["review"]["checks"])
    invoice_id = delivered["invoice"]["id"]
    assert delivered["invoice"]["amount"] == 3000.0

    # delivering twice must not produce a second invoice
    assert client.post(f"/api/milestones/{first['id']}/deliver",
                       json={}).status_code == 409

    # pay it through the mock payer page
    assert client.get(f"/mock/invoice/{invoice_id}").status_code == 200
    assert client.post(f"/mock/invoice/{invoice_id}/pay").status_code == 200

    dashboard = client.get("/api/dashboard").json()
    assert dashboard["totals"]["collected"] == 3000.0
    paid = [m for m in dashboard["milestones"] if m["id"] == first["id"]][0]
    assert paid["status"] == "paid"

    # split it
    payout = client.post(f"/api/milestones/{first['id']}/payout/propose").json()
    amounts = {i["name"]: i["amount"] for i in payout["items"]}
    assert amounts == {"Andres Villa": 900.0, "Mariana Soto": 600.0}
    assert payout["retained"] == 1500.0

    # an item above the ceiling is not sent unless it is approved by id
    over_ceiling = [i for i in payout["items"] if i["needs_approval"]]
    assert over_ceiling, "the 900.00 item should need approval at a 800 ceiling"
    partial = client.post(f"/api/payouts/{payout['payout_id']}/approve",
                          json={"approved_item_ids": []}).json()
    assert len(partial["held"]) == len(over_ceiling)
    assert len(partial["sent"]) == len(payout["items"]) - len(over_ceiling)


def test_payout_needs_a_paid_milestone(client, contract_pdf):
    milestones = approve_sample_plan(client, contract_pdf)
    assert client.post(
        f"/api/milestones/{milestones[0]['id']}/payout/propose"
    ).status_code == 409


def test_overdue_milestone_gets_a_risk_score_and_a_draft(client, contract_pdf):
    client.post("/api/demo/seed")
    milestones = approve_sample_plan(client, contract_pdf)
    second = milestones[1]
    client.post(f"/api/milestones/{second['id']}/deliver", json={"evidence": "live"})

    risk = client.get(f"/api/milestones/{second['id']}/risk").json()
    assert risk["days_overdue"] > 0
    assert 0 < risk["pd"] < 1
    assert risk["history"]["invoices_settled"] == 3
    assert risk["band"] in ("low", "medium", "high")

    drafted = client.post(f"/api/milestones/{second['id']}/dunning").json()
    assert drafted["message"]["subject"]
    assert drafted["message"]["body"]
    assert drafted["risk"]["tone"] == risk["tone"]
    # the draft is a draft until Laura sends it
    rows = client.get("/api/dunning").json()
    assert rows[0]["status"] == "draft"
    sent = client.post(f"/api/dunning/{drafted['dunning_id']}/send", json={})
    assert sent.status_code == 200
    assert client.get("/api/dunning").json()[0]["status"] == "sent"
    # and cannot be sent twice
    assert client.post(f"/api/dunning/{drafted['dunning_id']}/send",
                       json={}).status_code == 409


def test_dunning_requires_an_invoice(client, contract_pdf):
    milestones = approve_sample_plan(client, contract_pdf)
    assert client.post(
        f"/api/milestones/{milestones[0]['id']}/dunning"
    ).status_code == 409


def test_webhook_marks_the_milestone_paid(client, contract_pdf):
    milestones = approve_sample_plan(client, contract_pdf)
    delivered = client.post(f"/api/milestones/{milestones[0]['id']}/deliver",
                            json={}).json()
    invoice_id = delivered["invoice"]["id"]

    response = client.post("/api/webhooks/paypal", json={
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"id": invoice_id, "amount": {"currency_code": "USD",
                                                  "value": "3000.00"}},
    })
    assert response.status_code == 200
    assert response.json()["handled"] is True

    dashboard = client.get("/api/dashboard").json()
    paid = [m for m in dashboard["milestones"] if m["id"] == milestones[0]["id"]][0]
    assert paid["status"] == "paid"
    assert paid["paid_amount"] == 3000.0

    # a second delivery of the same event must not double-count
    client.post("/api/webhooks/paypal", json={
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"id": invoice_id},
    })
    assert client.get("/api/dashboard").json()["totals"]["collected"] == 3000.0


def test_webhook_for_an_unknown_invoice_is_acknowledged_but_not_applied(client):
    response = client.post("/api/webhooks/paypal", json={
        "event_type": "INVOICING.INVOICE.PAID",
        "resource": {"id": "INV2-DOES-NOT-EXIST"},
    })
    assert response.status_code == 200
    assert response.json()["handled"] is False


def test_audit_trail_separates_agent_decisions_from_human_ones(client, contract_pdf):
    milestones = approve_sample_plan(client, contract_pdf)
    client.post(f"/api/milestones/{milestones[0]['id']}/deliver", json={})
    events = client.get("/api/events").json()
    kinds = {e["kind"]: e["actor"] for e in events}
    assert kinds["contract.parsed"] == "agent"
    assert kinds["plan.approved"] == "human"
    assert kinds["milestone.delivered"] == "human"
    assert kinds["review.approve"] == "agent"
    assert kinds["invoice.sent"] == "agent"


def test_status_reports_which_engines_are_live(client):
    status = client.get("/api/status").json()
    assert status["modes"]["paypal"] == "mock"
    assert status["modes"]["ai_live"] is False
    assert status["risk_model"]["trained"] is True
    assert status["paypal"]["ok"] is True


def test_risk_what_if_endpoint(client):
    low = client.post("/api/risk/score", json={
        "amount": 500, "relationship_invoices": 9, "days_overdue": 1}).json()
    high = client.post("/api/risk/score", json={
        "amount": 9000, "prior_late_ratio": 0.9, "prior_avg_days_late": 40,
        "days_overdue": 50}).json()
    assert low["pd"] < high["pd"]
    assert low["tone"] == "friendly"
    assert high["tone"] == "payment_plan"
