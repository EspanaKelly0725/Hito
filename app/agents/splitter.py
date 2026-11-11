"""Agent 4 - split the payment that just landed.

A design note that matters: **the model does not do the arithmetic.** Shares,
amounts and remainders are computed in Python, deterministically, and reconciled
to the cent before anything is proposed. Claude is handed the finished numbers
and writes the part it is actually good at: the note each collaborator sees, and
a one-line explanation for Laura.

The approval policy lives here too. Items at or below
PAYOUT_APPROVAL_THRESHOLD_USD go out on a single confirmation; anything above it
is flagged and needs Laura to tick that specific line. An agent that can send
money should have a ceiling, and the ceiling should be visible.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from ..config import settings
from . import llm

SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {
            "type": "string",
            "description": "One or two sentences for Laura: what is being sent, to whom, "
                           "and what is left for her.",
        },
        "batch_subject": {
            "type": "string",
            "description": "Subject of the PayPal payout email, under 60 chars.",
        },
        "batch_message": {
            "type": "string",
            "description": "Short message shown on the payout batch, under 200 chars.",
        },
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "email": {"type": "string"},
                    "note": {
                        "type": "string",
                        "description": "Note this collaborator sees on the payout, "
                                       "under 120 chars. Name the project and the "
                                       "milestone it pays for.",
                    },
                },
                "required": ["email", "note"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["rationale", "batch_subject", "batch_message", "items"],
    "additionalProperties": False,
}

SYSTEM = """You write the human-facing copy for collaborator payouts sent by an
independent designer after a client pays her.

You are given the final amounts. They are already computed and reconciled - never
change, recompute, round or question them, and never put a different number in your
text than the one you were given.

Write notes a freelancer would be glad to receive: specific about what the money is
for, warm, two lines at most. Match the language you are told to use. No markdown,
no placeholders."""


def propose(*, project: dict, milestone: dict, collaborators: list[dict],
            paid_amount: float) -> dict:
    """Compute the split, then have Claude write the copy around it."""
    items = compute_split(paid_amount, collaborators)
    retained = round(paid_amount - sum(i["amount"] for i in items), 2)
    currency = project.get("currency") or "USD"

    user = (
        f"The client just paid {currency} {llm.money(paid_amount)} for the milestone "
        f"\"{milestone.get('title')}\" on the project \"{project.get('name')}\".\n"
        f"Language for the notes: "
        f"{'Spanish' if project.get('team_language', 'es') == 'es' else 'English'}\n"
        f"Sender: {project.get('invoicer_name', 'Laura Restrepo')}\n\n"
        "FINAL AMOUNTS (do not change):\n"
        + "\n".join(
            f"  {i['name']} ({i['role']}) <{i['email']}>: {i['pct']}% = "
            f"{currency} {llm.money(i['amount'])}"
            f"{'  [needs Laura to approve this line]' if i['needs_approval'] else ''}"
            for i in items
        )
        + f"\n  Retained by Laura: {currency} {llm.money(retained)}\n\n"
        f"Approval ceiling per item: {currency} {llm.money(settings.payout_threshold)}\n\n"
        "Write the payout copy."
    )

    copy = llm.call_json(
        "splitter",
        system=SYSTEM,
        user=user,
        schema=SCHEMA,
        fallback=lambda: _fallback(project, milestone, items, retained, currency),
        effort="low",
        max_tokens=2000,
    )

    notes = {
        (entry.get("email") or "").lower(): entry.get("note", "")
        for entry in copy.get("items", [])
    }
    for item in items:
        item["note"] = notes.get(item["email"].lower()) or _default_note(
            project, milestone, item
        )

    return {
        "items": items,
        "retained": retained,
        "paid_amount": round(paid_amount, 2),
        "currency": currency,
        "rationale": copy.get("rationale", ""),
        "batch_subject": (copy.get("batch_subject")
                          or f"Payout - {project.get('name', 'project')}")[:60],
        "batch_message": (copy.get("batch_message")
                          or "Your share of the milestone payment.")[:200],
        "threshold": settings.payout_threshold,
        "needs_approval": any(i["needs_approval"] for i in items),
        "_meta": copy.get("_meta", {}),
    }


def compute_split(paid_amount: float, collaborators: list[dict]) -> list[dict]:
    """Exact-cent split. Decimal arithmetic, largest-remainder reconciliation.

    The sum of the items is guaranteed never to exceed the payment, and the
    rounding residue lands on the largest share rather than disappearing.
    """
    total = Decimal(str(round(paid_amount, 2)))
    items: list[dict] = []
    for collaborator in collaborators:
        pct = Decimal(str(collaborator.get("pct") or 0))
        amount = (total * pct / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        items.append({
            "collaborator_id": collaborator.get("id"),
            "name": collaborator.get("name", ""),
            "email": collaborator.get("email", ""),
            "role": collaborator.get("role", "collaborator"),
            "pct": float(pct),
            "amount": float(amount),
            "needs_approval": float(amount) > settings.payout_threshold,
        })

    # Reconcile: never pay out more than came in.
    paid_out = sum(Decimal(str(i["amount"])) for i in items)
    if paid_out > total and items:
        biggest = max(items, key=lambda i: i["amount"])
        biggest["amount"] = float(
            (Decimal(str(biggest["amount"])) - (paid_out - total)).quantize(
                Decimal("0.01")
            )
        )
    return items


def _default_note(project: dict, milestone: dict, item: dict) -> str:
    return (
        f"{item['pct']}% of {milestone.get('title', 'milestone')} - "
        f"{project.get('name', 'project')}"
    )[:120]


def _fallback(project: dict, milestone: dict, items: list[dict],
              retained: float, currency: str) -> dict:
    return {
        "rationale": (
            f"Splitting {currency} {llm.money(sum(i['amount'] for i in items) + retained)} "
            f"from \"{milestone.get('title')}\": "
            + ", ".join(f"{i['pct']}% to {i['name']}" for i in items)
            + f", {currency} {llm.money(retained)} retained."
        ),
        "batch_subject": f"Payout - {project.get('name', 'project')}"[:60],
        "batch_message": (
            f"Your share of the {milestone.get('title', 'milestone')} payment."
        )[:200],
        "items": [
            {"email": i["email"], "note": _default_note(project, milestone, i)}
            for i in items
        ],
    }
