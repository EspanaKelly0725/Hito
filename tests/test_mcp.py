"""The MCP server has to speak the protocol and keep the same guardrails."""
from __future__ import annotations

import asyncio
import json

from app import mcp_server


def call(method: str, params: dict | None = None, request_id: int = 1):
    return asyncio.run(
        mcp_server.dispatch(
            {"jsonrpc": "2.0", "id": request_id, "method": method,
             "params": params or {}}
        )
    )


def tool_result(name: str, arguments: dict | None = None) -> dict:
    response = call("tools/call", {"name": name, "arguments": arguments or {}})
    payload = json.loads(response["result"]["content"][0]["text"])
    payload["_isError"] = response["result"]["isError"]
    return payload


def test_initialize_announces_the_protocol_and_the_rules():
    result = call("initialize")["result"]
    assert result["protocolVersion"] == mcp_server.PROTOCOL_VERSION
    assert result["serverInfo"]["name"] == "hito"
    assert "tools" in result["capabilities"]
    # the guardrails are stated to the agent, not just enforced in code
    assert "override" in result["instructions"]
    assert "needs_approval" in result["instructions"]


def test_notifications_get_no_response():
    assert call("notifications/initialized") is None


def test_unknown_method_is_a_jsonrpc_error():
    assert call("nope/nope")["error"]["code"] == -32601


def test_every_tool_has_a_schema_and_a_handler():
    tools = call("tools/list")["result"]["tools"]
    assert len(tools) >= 10
    for entry in tools:
        assert entry["description"].strip()
        assert entry["inputSchema"]["type"] == "object"
        assert entry["name"] in mcp_server.HANDLERS


def test_read_contract_returns_a_plan_without_creating_anything():
    plan = tool_result("read_contract", {
        "text": (
            "Total fee US$6,000.\n"
            "Milestone 1 - Logo: US$3,000 due October 10, 2026.\n"
            "Milestone 2 - Website: US$3,000 due October 28, 2026.\n"
            "Ana Ruiz - developer - ana@example.dev - 25% of each payment\n"
        ),
        "filename": "mcp.txt",
    })
    assert len(plan["milestones"]) == 2
    assert tool_result("list_milestones")["milestones"] == []


def test_the_full_loop_over_mcp_keeps_the_payout_ceiling():
    plan = tool_result("read_contract", {
        "text": (
            "Total fee US$6,000.\n"
            "Milestone 1 - Logo: US$3,000 due October 10, 2026.\n"
            "Milestone 2 - Website: US$3,000 due October 28, 2026.\n"
            "Ana Ruiz - developer - ana@example.dev - 40% of each payment\n"
        ),
    })
    created = tool_result("approve_plan", {
        "project_name": "MCP project",
        "client_name": "Client",
        "client_email": "client@example.com",
        "client_country": "US",
        "currency": "USD",
        "contract_text": "Milestone 1 - Logo: US$3,000.",
        "milestones": [
            {k: m[k] for k in ("title", "description", "amount", "due_date",
                               "contract_quote")}
            for m in plan["milestones"]
        ],
        "collaborators": plan["collaborators"],
    })
    assert created["ok"]

    milestones = tool_result("list_milestones")["milestones"]
    first = milestones[0]

    invoiced = tool_result("invoice_milestone", {
        "milestone_id": first["id"], "evidence": "delivered over MCP"
    })
    assert invoiced["stage"] == "invoiced"
    assert invoiced["review"]["verdict"] == "approve"

    # risk is scoreable the moment there is an invoice
    risk = tool_result("score_risk", {"milestone_id": first["id"]})
    assert 0 < risk["pd"] < 1
    assert risk["band"] in ("low", "medium", "high")

    # pay it, then split it
    from app.main import _apply_payment

    _apply_payment(invoiced["invoice"]["id"], 3000.0, source="test")

    proposal = tool_result("propose_split", {"milestone_id": first["id"]})
    flagged = [i for i in proposal["items"] if i["needs_approval"]]
    assert flagged, "40% of 3,000 is above the 800 ceiling"

    # without approving the flagged id, nothing can be sent
    refused = tool_result("send_payout", {"payout_id": proposal["payout_id"]})
    assert refused["_isError"] is True

    sent = tool_result("send_payout", {
        "payout_id": proposal["payout_id"],
        "approved_item_ids": [i["id"] for i in flagged],
    })
    assert sent["ok"] is True
    assert len(sent["sent"]) == len(proposal["items"])


def test_model_card_and_audit_trail_are_reachable():
    card = tool_result("explain_risk_model")
    assert card["trained"] is True
    assert card["coefficients"]
    assert "events" in tool_result("audit_trail", {"limit": 5})
