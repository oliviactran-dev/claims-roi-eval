"""Command line entry point.

    claims-roi build-cohort specs/diabetes_care_mgmt.yaml
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import cohort as C
from . import simulate as S
from .spec import load_spec
from .tuva import load_all

SUMMARY_COLS = [
    "age", "female", "hcc_risk_score", "chronic_condition_count",
    "baseline_ip_admits", "baseline_ed_visits", "baseline_total_paid",
]


def smd(a: pd.Series, b: pd.Series) -> float:
    pooled = np.sqrt((a.var() + b.var()) / 2)
    return float((a.mean() - b.mean()) / pooled) if pooled > 0 else 0.0


def build_cohort(spec_path: str, root: str = ".") -> dict:
    spec = load_spec(spec_path)
    rng = np.random.default_rng(spec["intervention"]["simulation"]["seed"])
    data = load_all(spec, root)

    cand = C.draw_candidate_index(data["patients"]["person_id"], spec, rng)
    eligible, attrition = C.apply_eligibility(cand, data, spec)
    panel = C.relative_panel(eligible, data, spec)
    feats = C.baseline_features(eligible, panel, data)

    cohort = S.assign_enrollment(feats, spec, rng)
    cohort = S.assign_engagement(cohort, spec, rng)
    panel, truth = S.plant_effect(panel, cohort, spec)

    out = Path(root) / spec["outputs"]["dir"]
    out.mkdir(parents=True, exist_ok=True)
    cohort.drop(columns=["true_enroll_prob"]).to_parquet(out / spec["outputs"]["cohort"], index=False)
    panel.to_parquet(out / spec["outputs"]["member_month"], index=False)
    feats.to_parquet(out / spec["outputs"]["baseline_features"], index=False)
    (out / spec["outputs"]["truth"]).write_text(json.dumps(truth, indent=2, default=str))

    # Summary: who enrolled, and why a naive comparison is biased
    f = feats.merge(cohort[["person_id", "group"]], on="person_id")
    t, c = f[f["group"] == "enrolled"], f[f["group"] == "comparison"]
    balance = pd.DataFrame({
        "enrolled_mean": t[SUMMARY_COLS].mean(),
        "comparison_mean": c[SUMMARY_COLS].mean(),
        "smd": [smd(t[k], c[k]) for k in SUMMARY_COLS],
    }).round(3)

    pm = panel.merge(cohort[["person_id", "group", "engagement_tier"]], on="person_id")
    fu, base = pm[pm["period"] == "follow_up"], pm[pm["period"] == "baseline"]
    naive_post = fu[fu["group"] == "comparison"]["total_paid"].mean() - fu[fu["group"] == "enrolled"]["total_paid"].mean()
    naive_did = naive_post - (
        base[base["group"] == "comparison"]["total_paid"].mean() - base[base["group"] == "enrolled"]["total_paid"].mean()
    )

    summary = {
        "attrition": attrition,
        "groups": cohort["group"].value_counts().to_dict(),
        "engagement": cohort["engagement_tier"].value_counts().to_dict(),
        "balance": balance,
        "naive_post_only_savings_pmpm": round(float(naive_post), 2),
        "naive_unadjusted_did_savings_pmpm": round(float(naive_did), 2),
        "truth": truth,
        "out": out,
    }
    return summary


def print_summary(s: dict) -> None:
    print("\nAttrition")
    print(s["attrition"].to_string(index=False))
    print(f"\nGroups: {s['groups']}")
    print(f"Engagement tiers (enrolled): {s['engagement']}")
    print("\nBaseline balance before any adjustment (|SMD| > 0.1 = imbalanced)")
    print(s["balance"].to_string())
    tr = s["truth"]
    print(f"\nPlanted truth, ITT savings PMPM:        {tr['itt']['savings_pmpm']}")
    print(f"Planted truth, as-treated savings PMPM: {tr['as_treated']['savings_pmpm']}")
    print(f"Naive post-only comparison, PMPM:       {s['naive_post_only_savings_pmpm']}")
    print(f"Naive unadjusted DiD, PMPM:             {s['naive_unadjusted_did_savings_pmpm']}")
    print(f"\nWrote analytic files to {s['out']}/")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(prog="claims-roi")
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build-cohort", help="anchor index dates, apply eligibility, build baseline features")
    b.add_argument("spec")
    b.add_argument("--root", default=".", help="project root (paths in the spec are relative to it)")
    args = parser.parse_args(argv)
    if args.cmd == "build-cohort":
        print_summary(build_cohort(args.spec, args.root))


if __name__ == "__main__":
    main()
