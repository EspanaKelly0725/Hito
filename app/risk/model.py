"""Payment-default risk model (SI4006-style).

A logistic regression fitted in pure Python - no numpy, no scikit-learn - so that
`pip install -r requirements.txt && uvicorn` is genuinely all a judge needs.

It answers one question: given everything we know about this client and this
invoice, how likely is it that this money never arrives? The answer drives two
business decisions in Hito:

  1. the tone of the collection message (TONE_POLICY below), and
  2. the expected loss shown on the dashboard, so Laura sees risk in dollars.

The model is trained on data/historial_pagos.csv at startup (~900 rows, ~25 ms)
and reports its own out-of-sample AUC / Brier score / log loss through
GET /api/risk/model, because a risk score nobody can audit is just a vibe.
"""
from __future__ import annotations

import csv
import math
import random
from dataclasses import dataclass, field
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent.parent / "data" / "historial_pagos.csv"

FEATURES = [
    "log_amount",
    "prior_late_ratio",
    "prior_avg_days_late",
    "relationship",
    "cross_border",
    "days_overdue",
]

LABELS = {
    "log_amount": "Invoice size (log of USD / 1,000)",
    "prior_late_ratio": "Share of past invoices this client paid late",
    "prior_avg_days_late": "Average days late in the past",
    "relationship": "Invoices already settled with this client",
    "cross_border": "Cross-border payment",
    "days_overdue": "Days past due right now",
}

# Tone policy: probability of default -> how Hito asks for the money.
#
# The cut-offs between bands are NOT hand-picked. A fixed 0.18 / 0.45 split would
# mean something different for every portfolio: in a book where three invoices in
# ten go bad, 0.30 is an ordinary client, not a worrying one. So the thresholds
# are the 50th and 85th percentile of the fitted model's own predictions
# (`RiskModel.cutoffs`, computed in fit()). The bottom half of the book gets a
# nudge, the top 15% gets a payment plan, and the policy travels with the data.
TONE_POLICY = [
    {
        "band": "low",
        "tone": "friendly",
        "intent": "A short, warm nudge. Assume it slipped through the cracks.",
        "offer": None,
    },
    {
        "band": "medium",
        "tone": "firm",
        "intent": "Clear and professional. Name a specific date and the contract clause.",
        "offer": None,
    },
    {
        "band": "high",
        "tone": "payment_plan",
        "intent": "Protect the relationship and the cash: offer to split the balance in two.",
        "offer": "split_in_two",
    },
]

# Used only when the model could not be fitted (missing dataset).
DEFAULT_CUTOFFS = (0.25, 0.55)


def quantile(sorted_values: list, q: float) -> float:
    """Linear-interpolation quantile over a pre-sorted list."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    position = q * (len(sorted_values) - 1)
    low = int(position)
    high = min(low + 1, len(sorted_values) - 1)
    weight = position - low
    return float(sorted_values[low] * (1 - weight) + sorted_values[high] * weight)


def sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


def build_features(*, amount: float, prior_late_ratio: float, prior_avg_days_late: float,
                   relationship_invoices: int, cross_border: bool,
                   days_overdue: float) -> dict:
    """Map raw facts to the feature space. One place, used by fit and by score."""
    return {
        "log_amount": math.log(max(amount, 1.0) / 1000.0),
        "prior_late_ratio": float(prior_late_ratio),
        "prior_avg_days_late": float(prior_avg_days_late) / 30.0,
        "relationship": float(min(int(relationship_invoices), 10)),
        "cross_border": 1.0 if cross_border else 0.0,
        "days_overdue": float(max(days_overdue, 0.0)) / 30.0,
    }


@dataclass
class RiskModel:
    coef: dict = field(default_factory=dict)
    bias: float = 0.0
    mean: dict = field(default_factory=dict)
    std: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    cutoffs: tuple = DEFAULT_CUTOFFS
    n_train: int = 0
    n_test: int = 0
    trained: bool = False

    # -- training ----------------------------------------------------------
    def fit(self, rows: list, *, epochs: int = 400, lr: float = 0.8,
            l2: float = 1e-3, seed: int = 7) -> "RiskModel":
        rng = random.Random(seed)
        data = [(build_features(**r["x"]), r["y"]) for r in rows]
        rng.shuffle(data)
        cut = int(len(data) * 0.7)
        train, test = data[:cut], data[cut:]

        self.mean = {f: sum(x[f] for x, _ in train) / len(train) for f in FEATURES}
        self.std = {}
        for f in FEATURES:
            var = sum((x[f] - self.mean[f]) ** 2 for x, _ in train) / len(train)
            self.std[f] = math.sqrt(var) or 1.0

        w = {f: 0.0 for f in FEATURES}
        b = 0.0
        n = len(train)
        for _ in range(epochs):
            gw = {f: 0.0 for f in FEATURES}
            gb = 0.0
            for x, y in train:
                z = b + sum(w[f] * self._z(f, x[f]) for f in FEATURES)
                err = sigmoid(z) - y
                gb += err
                for f in FEATURES:
                    gw[f] += err * self._z(f, x[f])
            b -= lr * gb / n
            for f in FEATURES:
                w[f] -= lr * (gw[f] / n + l2 * w[f])

        self.coef, self.bias = w, b
        self.n_train, self.n_test = len(train), len(test)
        self.metrics = self._evaluate(test)

        # Band cut-offs from the model's own predicted distribution.
        scores = sorted(self._p(x) for x, _ in data)
        self.cutoffs = (round(quantile(scores, 0.50), 4),
                        round(quantile(scores, 0.85), 4))
        self.trained = True
        return self

    def band_for(self, pd: float) -> dict:
        low, high = self.cutoffs
        index = 0 if pd < low else (1 if pd < high else 2)
        return TONE_POLICY[index]

    def _z(self, feature: str, value: float) -> float:
        return (value - self.mean.get(feature, 0.0)) / (self.std.get(feature) or 1.0)

    def _evaluate(self, test: list) -> dict:
        if not test:
            return {}
        preds = [(self._p(x), y) for x, y in test]
        brier = sum((p - y) ** 2 for p, y in preds) / len(preds)
        ll = -sum(
            y * math.log(max(p, 1e-9)) + (1 - y) * math.log(max(1 - p, 1e-9))
            for p, y in preds
        ) / len(preds)
        pos = [p for p, y in preds if y == 1]
        neg = [p for p, y in preds if y == 0]
        if pos and neg:
            wins = sum(
                1.0 if a > b else 0.5 if a == b else 0.0
                for a in pos for b in neg
            )
            auc = wins / (len(pos) * len(neg))
        else:
            auc = float("nan")
        base = sum(y for _, y in preds) / len(preds)
        return {
            "auc": round(auc, 4),
            "brier": round(brier, 4),
            "log_loss": round(ll, 4),
            "base_rate": round(base, 4),
            "n_test": len(preds),
        }

    def _p(self, x: dict) -> float:
        z = self.bias + sum(self.coef[f] * self._z(f, x[f]) for f in FEATURES)
        return sigmoid(z)

    # -- scoring -----------------------------------------------------------
    def score(self, *, amount: float, prior_late_ratio: float = 0.0,
              prior_avg_days_late: float = 0.0, relationship_invoices: int = 0,
              cross_border: bool = True, days_overdue: float = 0.0) -> dict:
        """Probability of default plus a human-readable explanation."""
        x = build_features(
            amount=amount,
            prior_late_ratio=prior_late_ratio,
            prior_avg_days_late=prior_avg_days_late,
            relationship_invoices=relationship_invoices,
            cross_border=cross_border,
            days_overdue=days_overdue,
        )
        contributions = []
        for f in FEATURES:
            delta = self.coef[f] * self._z(f, x[f])
            contributions.append({
                "feature": f,
                "label": LABELS[f],
                "value": round(x[f], 4),
                "weight": round(self.coef[f], 4),
                "logit_contribution": round(delta, 4),
                "direction": "raises" if delta > 0 else "lowers",
            })
        contributions.sort(key=lambda c: abs(c["logit_contribution"]), reverse=True)

        pd = self._p(x)
        policy = self.band_for(pd)
        return {
            "pd": round(pd, 4),
            "band": policy["band"],
            "tone": policy["tone"],
            "intent": policy["intent"],
            "offer": policy["offer"],
            "cutoffs": {"low_below": self.cutoffs[0], "high_above": self.cutoffs[1]},
            "expected_loss": round(pd * amount, 2),
            "factors": contributions,
            "top_factors": [c["label"] for c in contributions[:3]],
            "model": {
                "kind": "logistic regression (pure python, fitted on boot)",
                "trained": self.trained,
                **self.metrics,
            },
        }

    def describe(self) -> dict:
        return {
            "kind": "logistic regression",
            "target": "invoice still unpaid 60 days past due",
            "trained": self.trained,
            "n_train": self.n_train,
            "n_test": self.n_test,
            "dataset": DATA.name,
            "bias": round(self.bias, 4),
            "metrics": self.metrics,
            "cutoffs": {
                "low_below": self.cutoffs[0],
                "high_above": self.cutoffs[1],
                "derived_from": "50th and 85th percentile of fitted predictions",
            },
            "coefficients": [
                {
                    "feature": f,
                    "label": LABELS[f],
                    "standardized_weight": round(self.coef.get(f, 0.0), 4),
                    "mean": round(self.mean.get(f, 0.0), 4),
                    "std": round(self.std.get(f, 0.0), 4),
                }
                for f in sorted(FEATURES, key=lambda k: -abs(self.coef.get(k, 0.0)))
            ],
            "tone_policy": TONE_POLICY,
        }


def load_rows(path: Path = DATA) -> list:
    rows = []
    with path.open(encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append({
                "x": {
                    "amount": float(r["amount_usd"]),
                    "prior_late_ratio": float(r["prior_late_ratio"]),
                    "prior_avg_days_late": float(r["prior_avg_days_late"]),
                    "relationship_invoices": int(r["relationship_invoices"]),
                    "cross_border": bool(int(r["cross_border"])),
                    "days_overdue": float(r["days_overdue"]),
                },
                "y": int(r["defaulted"]),
            })
    return rows


def _bootstrap() -> RiskModel:
    model = RiskModel()
    try:
        model.fit(load_rows())
    except Exception as exc:  # pragma: no cover - keep the app up no matter what
        model.coef = {
            "log_amount": 0.55, "prior_late_ratio": 0.80, "prior_avg_days_late": 0.42,
            "relationship": -0.45, "cross_border": 0.18, "days_overdue": 0.52,
        }
        model.bias = -1.05
        model.mean = {f: 0.0 for f in FEATURES}
        model.std = {f: 1.0 for f in FEATURES}
        model.metrics = {"note": "fallback coefficients: " + str(exc)}
    return model


risk_model = _bootstrap()
