"""Agent 2 - the reviewer that has to agree before any invoice leaves.

Hito's invoicing agent is allowed to move money toward Laura's client. So it
does not get to act alone. Before a PayPal invoice is created, a second,
independent reviewer checks the request against the contract:

  * seven deterministic checks in Python - arithmetic, duplicates, totals,
    recipient, currency, state machine. These can hard-block.
  * one Claude pass that reads the contract text and the proposed invoice and
    answers a different question: *does this invoice actually match what the
    client agreed to pay for?*

Policy, implemented in `decide()`:
  deterministic failure -> BLOCK      (nothing is created)
  Claude objects        -> HOLD       (Laura sees the objection and can override)
  both agree            -> APPROVE    (the invoice is created and sent)

This is the guardrail that makes an autonomous billing agent defensible: the
thing that writes the invoice is never the only thing that approves it.
"""
from __future__ import annotations

import re

from . import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["approve", "object"],
            "description": "approve when the invoice matches the contract; object when "
                           "anything about it contradicts or is not supported by the "
                           "contract.",
        },
        "confidence": {"type": "number", "description": "0 to 1"},
        "contract_evidence": {
            "type": "string",
            "description": "Verbatim sentence from the contract that supports (or "
                           "contradicts) this invoice amount.",
        },
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "enum": ["info", "warning", "critical"]},
                    "check": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["severity", "check", "detail"],
                "additionalProperties": False,
            },
        },
        "summary": {"type": "string", "description": "One sentence for Laura."},
    },
    "required": ["verdict", "confidence", "contract_evidence", "findings", "summary"],
    "additionalProperties": False,
}

SYSTEM = """You are the invoice reviewer in an automated billing system. Another agent
has prepared an invoice to send to a client. Your job is to stop anything the contract
does not support.

Object when:
- the amount does not match what the contract sets for this deliverable
- the deliverable is not one the contract lists, or is not billable yet
- the currency, the client, or the recipient does not match the contract
- the invoice would bill the same deliverable twice
- the contract makes payment conditional on something that has not happened

Approve when the amount and the deliverable match the contract. A missing nicety
(no PO number, a terse description) is a finding with severity "info", not an objection.

Quote the contract verbatim in contract_evidence. Never restate the invoice as if it
were the contract. You are the check, not the author."""


def review(*, contract_text: str, project: dict, milestone: dict,
           already_invoiced: float, invoice_items: list[dict],
           recipient_email: str, currency: str) -> dict:
    """Run both reviewers and return the combined decision."""
    checks = _deterministic_checks(
        contract_text=contract_text,
        project=project,
        milestone=milestone,
        already_invoiced=already_invoiced,
        invoice_items=invoice_items,
        recipient_email=recipient_email,
        currency=currency,
    )

    amount = round(sum(float(i["amount"]) for i in invoice_items), 2)
    user = (
        f"CONTRACT TOTAL ON RECORD: {currency} {llm.money(project.get('total_amount', 0))}\n"
        f"CLIENT ON RECORD: {project.get('client_name')} <{project.get('client_email')}>\n"
        f"ALREADY INVOICED ON THIS CONTRACT: {currency} {llm.money(already_invoiced)}\n\n"
        "PROPOSED INVOICE\n"
        f"  deliverable: {milestone.get('title')}\n"
        f"  description: {milestone.get('description')}\n"
        f"  amount: {currency} {llm.money(amount)}\n"
        f"  recipient: {recipient_email}\n"
        f"  due date: {milestone.get('due_date')}\n"
        f"  milestone state: {milestone.get('status')}\n"
        f"  delivery evidence from Laura: {milestone.get('evidence') or '(none given)'}\n\n"
        "--- CONTRACT TEXT ---\n"
        f"{contract_text[:50000]}\n"
        "--- END CONTRACT TEXT ---\n\n"
        "Review this invoice."
    )

    opinion = llm.call_json(
        "reviewer",
        system=SYSTEM,
        user=user,
        schema=SCHEMA,
        fallback=lambda: _fallback(checks, amount),
        effort="high",
        max_tokens=4000,
    )
    return decide(checks, opinion, amount=amount, currency=currency)


def decide(checks: list[dict], opinion: dict, *, amount: float,
           currency: str = "USD") -> dict:
    hard_failures = [c for c in checks if not c["pass"] and c["blocking"]]
    soft_failures = [c for c in checks if not c["pass"] and not c["blocking"]]
    model_objects = opinion.get("verdict") == "object"

    if hard_failures:
        verdict = "block"
        headline = hard_failures[0]["detail"]
    elif model_objects:
        verdict = "hold"
        headline = opinion.get("summary") or "The reviewer objected to this invoice."
    else:
        verdict = "approve"
        headline = opinion.get("summary") or "Invoice matches the contract."

    return {
        "verdict": verdict,
        "headline": headline,
        "amount": amount,
        "currency": currency,
        "checks": checks,
        "hard_failures": [c["name"] for c in hard_failures],
        "soft_failures": [c["name"] for c in soft_failures],
        "model_verdict": opinion.get("verdict", "approve"),
        "model_confidence": round(float(opinion.get("confidence") or 0), 2),
        "contract_evidence": opinion.get("contract_evidence", ""),
        "findings": opinion.get("findings", []),
        "_meta": opinion.get("_meta", {}),
    }


# ---------------------------------------------------------------------------


def _deterministic_checks(*, contract_text: str, project: dict, milestone: dict,
                          already_invoiced: float, invoice_items: list[dict],
                          recipient_email: str, currency: str) -> list[dict]:
    amount = round(sum(float(i["amount"]) for i in invoice_items), 2)
    total = round(float(project.get("total_amount") or 0), 2)
    plan_amount = round(float(milestone.get("amount") or 0), 2)
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, *, blocking: bool = True) -> None:
        checks.append({"name": name, "pass": bool(ok), "detail": detail,
                       "blocking": blocking})

    add("positive_amount", amount > 0,
        f"Invoice amount is {currency} {llm.money(amount)}.")

    add("matches_approved_plan", abs(amount - plan_amount) < 0.01,
        f"Invoice {llm.money(amount)} vs approved milestone {llm.money(plan_amount)}."
        if abs(amount - plan_amount) >= 0.01 else
        f"Matches the approved milestone amount ({llm.money(plan_amount)}).")

    add("not_already_invoiced", not milestone.get("invoice_id"),
        f"Milestone already carries invoice {milestone.get('invoice_id')}."
        if milestone.get("invoice_id") else "No invoice exists for this milestone yet.")

    add("milestone_delivered", milestone.get("status") in ("delivered", "pending"),
        f"Milestone state is {milestone.get('status')}.",
        blocking=milestone.get("status") in ("paid", "invoiced"))

    projected = round(already_invoiced + amount, 2)
    add("within_contract_total", not total or projected <= total + 0.01,
        f"This invoice would take total billed to {llm.money(projected)} "
        f"against a contract of {llm.money(total)}.")

    add("recipient_matches_contract",
        bool(recipient_email) and recipient_email.lower() ==
        str(project.get("client_email", "")).lower(),
        f"Invoice recipient {recipient_email} vs client of record "
        f"{project.get('client_email')}.")

    add("currency_matches", currency == (project.get("currency") or currency),
        f"Invoice currency {currency} vs contract currency {project.get('currency')}.")

    add("amount_appears_in_contract", _amount_in_text(amount, contract_text),
        f"{llm.money(amount)} appears in the contract text."
        if _amount_in_text(amount, contract_text)
        else f"{llm.money(amount)} was not found literally in the contract text.",
        blocking=False)

    return checks


def _amount_in_text(amount: float, text: str) -> bool:
    """Does this amount literally appear in the contract, in any usual notation?"""
    whole = int(round(amount))
    candidates = {
        f"{whole:,}", f"{whole}", f"{whole:,}".replace(",", "."),
        f"{whole:,}".replace(",", " "), f"{amount:,.2f}", f"{amount:.2f}",
    }
    if whole % 1000 == 0:
        candidates.add(f"{whole // 1000}k")
        candidates.add(f"{whole // 1000},000")
    haystack = re.sub(r"\s+", " ", text or "").lower()
    return any(c.lower() in haystack for c in candidates if c)


def _fallback(checks: list[dict], amount: float) -> dict:
    """Rule-engine stand-in: trust the deterministic checks, flag the soft ones."""
    failed = [c for c in checks if not c["pass"]]
    findings = [
        {
            "severity": "critical" if c["blocking"] else "warning",
            "check": c["name"],
            "detail": c["detail"],
        }
        for c in failed
    ]
    return {
        "verdict": "object" if any(c["blocking"] for c in failed) else "approve",
        "confidence": 0.4,
        "contract_evidence": "",
        "findings": findings or [{
            "severity": "info",
            "check": "rule_engine",
            "detail": "Reviewed by the deterministic checks only "
                      "(no ANTHROPIC_API_KEY set).",
        }],
        "summary": (
            f"Deterministic review of {llm.money(amount)}: "
            f"{len(checks) - len(failed)}/{len(checks)} checks passed."
        ),
    }
