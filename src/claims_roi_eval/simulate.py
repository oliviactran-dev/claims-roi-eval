"""Simulate a program on data that has none: confounded enrollment,
engagement tiers, and a planted treatment effect with a known answer."""
from __future__ import annotations

import numpy as np
import pandas as pd

TIER_TOUCHES = {"none": (0, 0), "low": (1, 3), "high": (4, 12)}


def _logit_rate(z: np.ndarray, target: float) -> np.ndarray:
    """Find an intercept so the mean enrollment probability hits the target."""
    lo, hi = -20.0, 20.0
    for _ in range(100):
        mid = (lo + hi) / 2
        p = 1 / (1 + np.exp(-(mid + z)))
        lo, hi = (mid, hi) if p.mean() < target else (lo, mid)
    return 1 / (1 + np.exp(-(mid + z)))


def assign_enrollment(feats: pd.DataFrame, spec: dict, rng: np.random.Generator) -> pd.DataFrame:
    sel = spec["intervention"]["simulation"]["selection_model"]
    z = np.zeros(len(feats))
    for col, w in sel["drivers"].items():
        x = feats[col].astype(float)
        sd = x.std(ddof=0)
        if sd > 0:
            z += w * (x - x.mean()) / sd
    p = _logit_rate(z, sel["target_enrollment_rate"])
    out = feats[["person_id", "index_date"]].copy()
    out["true_enroll_prob"] = p
    out["treated"] = (rng.random(len(feats)) < p).astype(int)
    out["group"] = np.where(out["treated"] == 1, "enrolled", "comparison")
    return out


def assign_engagement(cohort: pd.DataFrame, spec: dict, rng: np.random.Generator) -> pd.DataFrame:
    shares = spec["intervention"]["simulation"]["engagement_simulation"]["tiers_share"]
    tiers = list(shares)
    treated = cohort["treated"] == 1
    draw = rng.choice(tiers, size=treated.sum(), p=[shares[t] for t in tiers])
    cohort = cohort.copy()
    cohort["engagement_tier"] = None
    cohort.loc[treated, "engagement_tier"] = draw
    touches = [rng.integers(TIER_TOUCHES[t][0], TIER_TOUCHES[t][1] + 1) for t in draw]
    cohort["touches_first_90_days"] = np.nan
    cohort.loc[treated, "touches_first_90_days"] = touches
    return cohort


def plant_effect(panel: pd.DataFrame, cohort: pd.DataFrame, spec: dict) -> tuple[pd.DataFrame, dict]:
    """Scale enrollees' follow-up costs by the planted effect.

    Returns the observed panel (what the analysis sees) and a truth dict holding
    the realized effect in dollars PMPM, which the analysis never reads.
    """
    eff = spec["intervention"]["simulation"]["planted_effect"]
    ramp = max(eff.get("ramp_months", 1), 1)
    p = panel.merge(cohort[["person_id", "engagement_tier"]], on="person_id", how="left")
    rel = p["rel_month"].to_numpy()
    tier_eff = p["engagement_tier"].map(eff["by_engagement_tier"]).fillna(0.0).to_numpy()
    phase = np.clip((rel + 1) / ramp, 0, 1) * (rel >= 0)
    factor = 1 + tier_eff * phase

    untreated_total = p["total_paid"].to_numpy().copy()
    for col in ["medical_paid", "pharmacy_paid"]:
        p[col] = p[col] * factor
    p["total_paid"] = p["medical_paid"] + p["pharmacy_paid"]

    fu = (p["period"] == "follow_up").to_numpy()
    p["_saving"] = untreated_total - p["total_paid"].to_numpy()

    def realized(tiers):
        m = fu & p["engagement_tier"].isin(tiers).to_numpy()
        return {
            "members": int(p.loc[m, "person_id"].nunique()),
            "savings_pmpm": round(float(p.loc[m, "_saving"].mean()), 2) if m.any() else None,
            "untreated_pmpm": round(float(untreated_total[m].mean()), 2) if m.any() else None,
        }

    pops = spec.get("engagement", {}).get("populations", {})
    truth = {
        "planted_effect": eff,
        "outcome": eff["outcome"],
        "note": "Realized savings among enrollees in follow-up months (untreated minus observed). "
                "Positive = savings. The analysis must never read this file.",
        "itt": realized(["none", "low", "high"]),
        "as_treated": realized(pops.get("as_treated", ["low", "high"])),
        "per_protocol": realized(pops.get("per_protocol", ["high"])),
    }
    return p.drop(columns=["_saving", "engagement_tier"]), truth
