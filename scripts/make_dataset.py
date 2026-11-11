"""Generate data/historial_pagos.csv - the payment history the risk model learns from.

Seeded, so the dataset (and therefore the fitted coefficients, the AUC and
everything a judge sees) is reproducible from a clean clone.

Each row is one invoice that was sent to a client and then observed for 60 days
past its due date. `defaulted = 1` means it was still unpaid at day 60, which is
the event the SI4006-style logistic model estimates.
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "historial_pagos.csv"

# "True" data-generating coefficients. The fitted model has to recover these
# from noisy observations - it never sees them.
TRUE = {
    "bias": -2.55,
    "log_amount": 0.55,
    "prior_late_ratio": 2.30,
    "prior_avg_days_late": 1.10,   # per 30 days
    "relationship": -0.14,          # per prior invoice, capped at 10
    "cross_border": 0.45,
    "days_overdue": 0.90,           # per 30 days
}

COUNTRIES = [
    ("US", 0.42), ("CO", 0.18), ("ES", 0.10), ("MX", 0.09),
    ("CA", 0.07), ("GB", 0.06), ("DE", 0.04), ("AR", 0.04),
]


def pick_country(rng: random.Random) -> str:
    r = rng.random()
    acc = 0.0
    for code, weight in COUNTRIES:
        acc += weight
        if r <= acc:
            return code
    return "US"


def main(n: int = 900, seed: int = 4006) -> None:
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        country = pick_country(rng)
        cross_border = 0 if country == "CO" else 1
        relationship = min(int(rng.expovariate(1 / 3.0)), 14)
        amount = round(math.exp(rng.gauss(math.log(1400), 0.95)), 2)
        amount = min(max(amount, 120.0), 22000.0)

        if relationship == 0:
            late_ratio = 0.0
            avg_days_late = 0.0
        else:
            late_ratio = min(max(rng.betavariate(1.4, 3.2), 0.0), 1.0)
            avg_days_late = round(late_ratio * rng.uniform(3, 46), 1)

        days_overdue = rng.choice([1, 3, 5, 7, 10, 14, 21, 30, 45, 60])

        logit = (
            TRUE["bias"]
            + TRUE["log_amount"] * math.log(amount / 1000.0)
            + TRUE["prior_late_ratio"] * late_ratio
            + TRUE["prior_avg_days_late"] * (avg_days_late / 30.0)
            + TRUE["relationship"] * min(relationship, 10)
            + TRUE["cross_border"] * cross_border
            + TRUE["days_overdue"] * (days_overdue / 30.0)
        )
        p = 1.0 / (1.0 + math.exp(-logit))
        defaulted = 1 if rng.random() < p else 0

        rows.append({
            "invoice_id": f"H-{2024 + i % 3}-{i:04d}",
            "client_country": country,
            "cross_border": cross_border,
            "amount_usd": f"{amount:.2f}",
            "relationship_invoices": relationship,
            "prior_late_ratio": f"{late_ratio:.4f}",
            "prior_avg_days_late": f"{avg_days_late:.1f}",
            "days_overdue": days_overdue,
            "defaulted": defaulted,
        })

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    base = sum(int(r["defaulted"]) for r in rows) / len(rows)
    print(f"wrote {len(rows)} rows to {OUT}  (default rate {base:.1%})")


if __name__ == "__main__":
    main()
