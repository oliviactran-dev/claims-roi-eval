import numpy as np
import pandas as pd

from claims_roi_eval.cohort import month_diff
from claims_roi_eval.simulate import _logit_rate, plant_effect

SPEC = {
    "intervention": {"simulation": {"planted_effect": {
        "outcome": "total_paid_pmpm",
        "by_engagement_tier": {"none": 0.0, "low": -0.1, "high": -0.2},
        "ramp_months": 1,
    }}},
    "engagement": {"populations": {"as_treated": ["low", "high"], "per_protocol": ["high"]}},
}


def test_month_diff():
    a = pd.Series(pd.to_datetime(["2017-03-01", "2016-12-01"]))
    b = pd.Series(pd.to_datetime(["2017-01-01", "2017-01-01"]))
    assert month_diff(a, b).tolist() == [2, -1]


def test_logit_rate_hits_target():
    z = np.random.default_rng(0).normal(size=5000)
    assert abs(_logit_rate(z, 0.2).mean() - 0.2) < 1e-3


def test_plant_effect_only_touches_treated_follow_up():
    panel = pd.DataFrame({
        "person_id": ["a", "a", "b", "b"],
        "rel_month": [-1, 0, -1, 0],
        "period": ["baseline", "follow_up", "baseline", "follow_up"],
        "medical_paid": [100.0] * 4,
        "pharmacy_paid": [0.0] * 4,
        "total_paid": [100.0] * 4,
    })
    cohort = pd.DataFrame({"person_id": ["a", "b"], "engagement_tier": ["high", None]})
    observed, truth = plant_effect(panel, cohort, SPEC)
    assert observed["total_paid"].tolist() == [100.0, 80.0, 100.0, 100.0]
    assert truth["as_treated"]["savings_pmpm"] == 20.0
