"""Anchor index dates, apply eligibility, and build baseline features."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .tuva import CONDITION_FLAGS


def month_diff(a: pd.Series, b: pd.Series) -> pd.Series:
    """Whole months from b to a (both first-of-month dates)."""
    return (a.dt.year - b.dt.year) * 12 + (a.dt.month - b.dt.month)


def draw_candidate_index(person_ids: pd.Series, spec: dict, rng: np.random.Generator) -> pd.DataFrame:
    """Give every person one candidate index month inside the enrollment window.

    Enrollees keep it as their enrollment (index) month; the comparison pool keeps
    it as a pseudo-index, so both groups share the same calendar distribution.
    """
    w = spec["intervention"]["enrollment_window"]
    months = pd.date_range(pd.Timestamp(w["start"]), pd.Timestamp(w["end"]), freq="MS")
    picks = rng.integers(0, len(months), size=len(person_ids))
    return pd.DataFrame({"person_id": person_ids.values, "index_date": months[picks]})


def apply_eligibility(cand: pd.DataFrame, data: dict, spec: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (eligible, attrition) where attrition counts each rule's drop."""
    elig = spec["eligibility"]
    win = spec["windows"]
    df = cand.merge(data["patients"], on="person_id", how="left")
    steps = [("candidates", len(df))]

    # Condition onset before index
    cond = data["conditions"]
    onset = cond.loc[cond["condition"] == elig["condition"]["cms_chronic_condition"], ["person_id", "onset_date"]]
    df = df.merge(onset, on="person_id", how="inner")
    df = df[pd.to_datetime(df["onset_date"]) < df["index_date"]]
    steps.append((f"{elig['condition']['name']} before index", len(df)))

    # Age at index
    df["age"] = ((df["index_date"] - pd.to_datetime(df["birth_date"])).dt.days / 365.25).astype(int)
    df = df[df["age"] >= elig["age_at_index"]["min"]]
    steps.append((f"age >= {elig['age_at_index']['min']} at index", len(df)))

    # Continuous enrollment across baseline and follow-up
    ce = elig["continuous_enrollment"]
    first, last = -ce["months_before_index"], ce["months_after_index"] - 1
    panel = data["panel"][["person_id", "month"]].merge(df[["person_id", "index_date"]], on="person_id")
    panel["rel_month"] = month_diff(pd.to_datetime(panel["month"]), panel["index_date"])
    covered = panel[panel["rel_month"].between(first, last)].groupby("person_id")["rel_month"].nunique()
    needed = last - first + 1 - ce.get("allowed_gap_months", 0)
    df = df[df["person_id"].map(covered).fillna(0) >= needed]
    steps.append((f"enrolled months {first} to +{last}", len(df)))

    # Alive through follow-up
    if "died_before_end_of_follow_up" in elig.get("exclusions", []):
        fu_end = df["index_date"] + pd.DateOffset(months=win["follow_up"]["end_month"] + 1)
        death = pd.to_datetime(df["death_date"])
        df = df[death.isna() | (death >= fu_end)]
        steps.append(("alive through follow-up", len(df)))

    attrition = pd.DataFrame(steps, columns=["step", "members"])
    return df.drop(columns=["onset_date"]).reset_index(drop=True), attrition


def relative_panel(eligible: pd.DataFrame, data: dict, spec: dict) -> pd.DataFrame:
    """Member-month panel indexed by months relative to the index date."""
    win = spec["windows"]
    p = data["panel"].merge(eligible[["person_id", "index_date"]], on="person_id")
    p["month"] = pd.to_datetime(p["month"])
    p["rel_month"] = month_diff(p["month"], p["index_date"])
    lo, hi = win["baseline"]["start_month"], win["follow_up"]["end_month"]
    p = p[p["rel_month"].between(lo, hi)].copy()
    p["period"] = np.where(p["rel_month"] < 0, "baseline", "follow_up")
    return p.sort_values(["person_id", "rel_month"]).reset_index(drop=True)


def baseline_features(eligible: pd.DataFrame, panel: pd.DataFrame, data: dict) -> pd.DataFrame:
    base = panel[panel["period"] == "baseline"]
    agg = base.groupby("person_id").agg(
        baseline_total_paid=("total_paid", "sum"),
        baseline_medical_paid=("medical_paid", "sum"),
        baseline_pharmacy_paid=("pharmacy_paid", "sum"),
        baseline_ip_admits=("ip_admits", "sum"),
        baseline_ed_visits=("ed_visits", "sum"),
        baseline_office_visits=("office_visits", "sum"),
    )

    # Cost trend: slope of monthly paid over the last 6 baseline months
    last6 = base[base["rel_month"] >= -6]
    x = last6["rel_month"] - last6.groupby("person_id")["rel_month"].transform("mean")
    y = last6["total_paid"] - last6.groupby("person_id")["total_paid"].transform("mean")
    slope = (x * y).groupby(last6["person_id"]).sum() / (x * x).groupby(last6["person_id"]).sum()
    agg["paid_slope_last_6_months"] = slope

    feats = eligible[["person_id", "index_date", "age", "sex", "race"]].set_index("person_id").join(agg)

    # Chronic conditions with onset before index
    cond = data["conditions"].merge(eligible[["person_id", "index_date"]], on="person_id")
    cond = cond[pd.to_datetime(cond["onset_date"]) < cond["index_date"]]
    feats["chronic_condition_count"] = cond.groupby("person_id").size()
    for flag, name in CONDITION_FLAGS.items():
        feats[flag] = feats.index.isin(cond.loc[cond["condition"] == name, "person_id"]).astype(int)

    # Prospective HCC score for the index year (prior calendar year's diagnoses)
    risk = data["risk"].set_index(["person_id", "payment_year"])["hcc_risk_score"]
    keys = list(zip(feats.index, feats["index_date"].dt.year))
    feats["hcc_risk_score"] = risk.reindex(keys).to_numpy()
    feats["hcc_missing"] = feats["hcc_risk_score"].isna().astype(int)
    feats["hcc_risk_score"] = feats["hcc_risk_score"].fillna(feats["hcc_risk_score"].median())

    num = feats.select_dtypes("number").columns
    feats[num] = feats[num].fillna(0)
    feats["female"] = (feats["sex"].str.lower() == "female").astype(int)
    return feats.reset_index()
