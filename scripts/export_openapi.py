"""Export docs/openapi.json straight from the running FastAPI app.

Generated, never hand-written, so the spec cannot drift from the code. The
output is what gets imported into APIMatic to produce the SDKs and the docs
portal (see docs/APIMATIC.md).

    python scripts/export_openapi.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

TAGS = [
    {"name": "Contracts",
     "description": "Read a contract and turn it into an approved payment plan."},
    {"name": "Invoicing",
     "description": "Deliver a milestone, clear the reviewer, invoice through "
                    "PayPal Invoicing v2."},
    {"name": "Payments",
     "description": "PayPal webhooks and the payment state of each milestone."},
    {"name": "Collections",
     "description": "Score the risk of not being paid and draft the message that "
                    "risk deserves."},
    {"name": "Payouts",
     "description": "Split a payment among collaborators through PayPal Payouts, "
                    "under an approval ceiling."},
    {"name": "Risk",
     "description": "The risk model: its card, and a what-if endpoint."},
    {"name": "Dashboard", "description": "Everything the UI reads."},
    {"name": "Demo", "description": "Seed and reset the demo data."},
]

# path prefix -> tag
ROUTES = [
    ("/api/contracts", "Contracts"),
    ("/api/projects", "Contracts"),
    ("/api/milestones/{milestone_id}/deliver", "Invoicing"),
    ("/api/milestones/{milestone_id}/simulate-payment", "Payments"),
    ("/api/milestones/{milestone_id}/risk", "Risk"),
    ("/api/milestones/{milestone_id}/dunning", "Collections"),
    ("/api/milestones/{milestone_id}/payout", "Payouts"),
    ("/api/webhooks", "Payments"),
    ("/api/dunning", "Collections"),
    ("/api/payouts", "Payouts"),
    ("/api/risk", "Risk"),
    ("/api/dashboard", "Dashboard"),
    ("/api/events", "Dashboard"),
    ("/api/status", "Dashboard"),
    ("/api/demo", "Demo"),
]


def tag_for(path: str) -> str:
    best = ""
    tag = "Dashboard"
    for prefix, candidate in ROUTES:
        if path.startswith(prefix) and len(prefix) > len(best):
            best, tag = prefix, candidate
    return tag


def main() -> None:
    spec = app.openapi()
    spec["info"] = {
        "title": "Hito API",
        "version": "1.0.0",
        "summary": "Contract-to-cash for freelancers, on PayPal.",
        "description": (
            "Hito reads a freelance contract, invoices each milestone through "
            "PayPal, estimates the probability that an invoice is never paid, "
            "asks for the money in the register that probability deserves, and "
            "splits what arrives among collaborators.\n\n"
            "Two guardrails are part of the API contract rather than the UI:\n\n"
            "* `POST /api/milestones/{milestone_id}/deliver` runs an independent "
            "reviewer before PayPal is called. It can return `stage: \"blocked\"` "
            "(nothing is created) or `stage: \"hold\"` (a human must pass "
            "`override: true`).\n"
            "* `POST /api/payouts/{payout_id}/approve` only sends items above "
            "`PAYOUT_APPROVAL_THRESHOLD_USD` when their ids appear in "
            "`approved_item_ids`.\n\n"
            "With no credentials configured the API is fully functional against "
            "an in-process PayPal gateway and a deterministic agent engine; "
            "`GET /api/status` always says which mode is live."
        ),
        "license": {"name": "MIT",
                    "url": "https://opensource.org/licenses/MIT"},
    }
    spec["servers"] = [
        {"url": "http://localhost:8000", "description": "Local"},
        {"url": "https://hito.onrender.com", "description": "Render deployment"},
    ]
    spec["tags"] = TAGS

    for path, operations in spec.get("paths", {}).items():
        if not path.startswith("/api"):
            continue
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["tags"] = [tag_for(path)]

    # the static mount and the mock payer pages are not part of the API
    spec["paths"] = {
        path: operations
        for path, operations in spec.get("paths", {}).items()
        if path.startswith("/api")
    }

    out = ROOT / "docs" / "openapi.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    operations = sum(
        len([k for k in ops if k in ("get", "post", "put", "patch", "delete")])
        for ops in spec["paths"].values()
    )
    print(f"wrote {out} ({len(spec['paths'])} paths, {operations} operations)")


if __name__ == "__main__":
    main()
