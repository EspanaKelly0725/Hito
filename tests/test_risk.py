"""The risk model has to behave like a risk model, not like a random number."""
from __future__ import annotations

from app.risk import TONE_POLICY, risk_model
from app.risk.model import quantile


def test_model_is_fitted_and_beats_chance():
    assert risk_model.trained
    assert risk_model.n_train > 500
    assert risk_model.metrics["auc"] > 0.62, "model should rank better than a coin flip"
    # A Brier score below the base-rate variance means it beats predicting the mean.
    base = risk_model.metrics["base_rate"]
    assert risk_model.metrics["brier"] < base * (1 - base)


def test_pd_rises_monotonically_with_days_overdue():
    pds = [
        risk_model.score(amount=3000, days_overdue=d)["pd"]
        for d in (0, 5, 15, 30, 60)
    ]
    assert pds == sorted(pds)
    assert pds[-1] > pds[0]


def test_a_longer_clean_relationship_lowers_risk():
    stranger = risk_model.score(amount=3000, relationship_invoices=0)["pd"]
    regular = risk_model.score(amount=3000, relationship_invoices=9)["pd"]
    assert regular < stranger


def test_late_history_raises_risk():
    clean = risk_model.score(amount=3000, prior_late_ratio=0.0)["pd"]
    messy = risk_model.score(amount=3000, prior_late_ratio=0.8,
                             prior_avg_days_late=30)["pd"]
    assert messy > clean


def test_expected_loss_is_pd_times_exposure():
    score = risk_model.score(amount=4200, days_overdue=10)
    # pd is reported rounded to 4 decimals, so allow for that rounding only
    assert abs(score["expected_loss"] - score["pd"] * 4200) < 4200 * 1e-4


def test_tone_bands_escalate_and_cover_the_range():
    bands = [p["band"] for p in TONE_POLICY]
    assert bands == ["low", "medium", "high"]
    low, high = risk_model.cutoffs
    assert 0 < low < high < 1
    assert risk_model.band_for(low - 0.01)["tone"] == "friendly"
    assert risk_model.band_for((low + high) / 2)["tone"] == "firm"
    assert risk_model.band_for(high + 0.01)["tone"] == "payment_plan"
    # only the top band offers a payment plan
    assert risk_model.band_for(high + 0.01)["offer"] == "split_in_two"
    assert risk_model.band_for(low - 0.01)["offer"] is None


def test_explanation_names_the_factors_that_moved_the_score():
    score = risk_model.score(amount=9000, prior_late_ratio=0.9,
                             prior_avg_days_late=40, days_overdue=45)
    assert len(score["factors"]) == 6
    # sorted by absolute contribution, largest first
    sizes = [abs(f["logit_contribution"]) for f in score["factors"]]
    assert sizes == sorted(sizes, reverse=True)
    assert len(score["top_factors"]) == 3
    assert all(f["direction"] in ("raises", "lowers") for f in score["factors"])


def test_quantile_interpolates():
    assert quantile([0.0, 1.0], 0.5) == 0.5
    assert quantile([1.0, 2.0, 3.0, 4.0], 0.0) == 1.0
    assert quantile([1.0, 2.0, 3.0, 4.0], 1.0) == 4.0
    assert quantile([], 0.5) == 0.0
