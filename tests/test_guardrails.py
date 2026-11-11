"""The parts that are allowed to move money need to be the parts under test.

Two guardrails matter most:
  * the reviewer must stop an invoice the contract does not support
  * the splitter must never pay out more than came in
"""
from __future__ import annotations

from app.agents import reviewer, splitter
from app.agents.reviewer import _deterministic_checks

CONTRACT = """
Total fee US$9,000 in three parts.
Milestone 1 - Logo: US$3,000 due October 10, 2026.
Milestone 2 - Website: US$3,000 due October 28, 2026.
Milestone 3 - Manual: US$3,000 due November 25, 2026.
"""

PROJECT = {
    "id": "prj_test",
    "client_name": "Bluebonnet Coffee Roasters",
    "client_email": "ap@bluebonnetroasters.example",
    "currency": "USD",
    "total_amount": 9000.0,
}

MILESTONE = {
    "id": "ms_1",
    "title": "Logo",
    "description": "Primary logotype",
    "amount": 3000.0,
    "due_date": "2026-10-10",
    "status": "delivered",
    "invoice_id": None,
    "evidence": "Delivered as SVG",
}


def checks_for(**overrides):
    kwargs = {
        "contract_text": CONTRACT,
        "project": PROJECT,
        "milestone": MILESTONE,
        "already_invoiced": 0.0,
        "invoice_items": [{"name": "Logo", "amount": 3000.0}],
        "recipient_email": PROJECT["client_email"],
        "currency": "USD",
    }
    kwargs.update(overrides)
    return {c["name"]: c for c in _deterministic_checks(**kwargs)}


def test_a_clean_invoice_passes_every_check():
    results = checks_for()
    assert all(c["pass"] for c in results.values()), \
        [n for n, c in results.items() if not c["pass"]]


def test_amount_that_does_not_match_the_plan_is_blocking():
    results = checks_for(invoice_items=[{"name": "Logo", "amount": 4500.0}])
    assert results["matches_approved_plan"]["pass"] is False
    assert results["matches_approved_plan"]["blocking"] is True
    # 4,500 is not in the contract either, so the soft check fires too
    assert results["amount_appears_in_contract"]["pass"] is False


def test_invoicing_the_same_milestone_twice_is_blocked():
    results = checks_for(milestone={**MILESTONE, "invoice_id": "INV2-ALREADY"})
    assert results["not_already_invoiced"]["pass"] is False
    assert results["not_already_invoiced"]["blocking"] is True


def test_cannot_bill_past_the_contract_total():
    results = checks_for(already_invoiced=7000.0)
    assert results["within_contract_total"]["pass"] is False
    assert results["within_contract_total"]["blocking"] is True


def test_recipient_must_be_the_client_on_record():
    results = checks_for(recipient_email="someone.else@example.com")
    assert results["recipient_matches_contract"]["pass"] is False
    assert results["recipient_matches_contract"]["blocking"] is True


def test_contract_amounts_are_recognised_in_several_notations():
    for text, amount in (
        ("fee of US$3,000 per milestone", 3000.0),
        ("fee of USD 3000 per milestone", 3000.0),
        ("honorario de US$3.000 por entrega", 3000.0),
        ("fee of $3,000.00 per milestone", 3000.0),
    ):
        assert reviewer._amount_in_text(amount, text), text
    assert not reviewer._amount_in_text(4500.0, "fee of US$3,000 per milestone")


def test_blocking_failure_beats_a_model_approval():
    results = list(checks_for(already_invoiced=8000.0).values())
    decision = reviewer.decide(
        results, {"verdict": "approve", "confidence": 0.99, "summary": "looks fine"},
        amount=3000.0,
    )
    assert decision["verdict"] == "block"
    assert "within_contract_total" in decision["hard_failures"]


def test_model_objection_becomes_a_hold_not_a_block():
    results = list(checks_for().values())
    decision = reviewer.decide(
        results,
        {"verdict": "object", "confidence": 0.8,
         "summary": "The contract makes this payable on written acceptance."},
        amount=3000.0,
    )
    assert decision["verdict"] == "hold"
    assert decision["hard_failures"] == []


# --- splitter ---------------------------------------------------------------

COLLABORATORS = [
    {"id": "c1", "name": "Andres Villa", "email": "a@example.dev",
     "role": "developer", "pct": 30},
    {"id": "c2", "name": "Mariana Soto", "email": "m@example.art",
     "role": "illustrator", "pct": 20},
]


def test_split_is_exact_and_never_overpays():
    items = splitter.compute_split(3000.0, COLLABORATORS)
    assert [i["amount"] for i in items] == [900.0, 600.0]
    assert sum(i["amount"] for i in items) <= 3000.0


def test_split_handles_amounts_that_do_not_divide_cleanly():
    items = splitter.compute_split(1000.01, [
        {"id": "a", "name": "A", "email": "a@x.dev", "role": "dev", "pct": 33.333},
        {"id": "b", "name": "B", "email": "b@x.dev", "role": "art", "pct": 33.333},
        {"id": "c", "name": "C", "email": "c@x.dev", "role": "qa", "pct": 33.334},
    ])
    total = sum(i["amount"] for i in items)
    assert total <= 1000.01, f"paid out {total} from 1000.01"
    assert abs(total - 1000.01) < 0.03


def test_full_payout_cannot_exceed_the_payment():
    items = splitter.compute_split(500.0, [
        {"id": "a", "name": "A", "email": "a@x.dev", "role": "dev", "pct": 60},
        {"id": "b", "name": "B", "email": "b@x.dev", "role": "art", "pct": 40},
    ])
    assert sum(i["amount"] for i in items) <= 500.0


def test_items_above_the_ceiling_are_flagged_for_approval():
    from app.config import settings

    items = splitter.compute_split(3000.0, COLLABORATORS)
    flagged = {i["name"]: i["needs_approval"] for i in items}
    assert flagged["Andres Villa"] is (900.0 > settings.payout_threshold)
    assert flagged["Mariana Soto"] is (600.0 > settings.payout_threshold)


# --- the quoted contract clause has to be real -----------------------------

CONTRACT_WITH_CLAUSE = (
    "2. DELIVERABLES AND FEES\n"
    "Milestone 1 - Logo and primary marks: US$3,000, due on October 10, 2026.\n"
    "Each invoice is issued through PayPal upon delivery of the corresponding\n"
    "milestone and is payable within fifteen (15) days of issue.\n"
)


def test_a_real_quote_is_kept():
    quote = "Milestone 1 - Logo and primary marks: US$3,000, due on October 10, 2026."
    assert reviewer.verify_evidence(quote, CONTRACT_WITH_CLAUSE) == quote


def test_a_quote_that_wraps_in_the_source_is_still_found():
    # the contract wraps this across two lines; the model returns it as one
    quote = ("Each invoice is issued through PayPal upon delivery of the "
             "corresponding milestone and is payable within fifteen (15) days of issue.")
    assert reviewer.verify_evidence(quote, CONTRACT_WITH_CLAUSE) == quote


def test_a_paraphrase_is_dropped():
    """The dangerous case: it reads exactly like evidence and is not."""
    paraphrase = "The contract states that each milestone is worth three thousand dollars."
    assert reviewer.verify_evidence(paraphrase, CONTRACT_WITH_CLAUSE) == ""


def test_the_prompt_markers_are_never_quoted():
    # qwen2.5:3b returned exactly this on the first run
    assert reviewer.verify_evidence("CONTRACT TEXT", CONTRACT_WITH_CLAUSE) == ""
    assert reviewer.verify_evidence(
        "=== contract begins on the next line ===", CONTRACT_WITH_CLAUSE) == ""


def test_a_scrap_is_not_evidence():
    assert reviewer.verify_evidence("US$3,000", CONTRACT_WITH_CLAUSE) == ""
    assert reviewer.verify_evidence("", CONTRACT_WITH_CLAUSE) == ""


def test_curly_quotes_around_a_real_clause_are_stripped():
    quote = "Milestone 1 - Logo and primary marks: US$3,000, due on October 10, 2026."
    assert reviewer.verify_evidence(f"\u201c{quote}\u201d",
                                    CONTRACT_WITH_CLAUSE) == quote
