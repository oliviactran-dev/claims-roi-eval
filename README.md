# claims-roi-eval

A transparent, spec-driven workflow for evaluating health programs from claims data: from raw claims to a weighted cohort, assumption checks, and an ROI estimate with confidence intervals.

Most program evaluations rebuild the same claims analytic dataset and rerun the same causal checks by hand. This project packages that workflow so that a new evaluation means editing a short study spec, not rewriting code.

## How it works

1. **Study spec.** One YAML file per evaluation defines the intervention, index date rule, eligibility, baseline and follow-up windows, comparison pool, engagement tiers, outcomes, and covariates. See [`specs/diabetes_care_mgmt.yaml`](specs/diabetes_care_mgmt.yaml).
2. **Analytic data layer.** Raw claims are mapped once into a canonical member-month and event schema. Every later stage reads from it.
3. **Cohort and anchoring.** Index dates for enrollees, pseudo-index dates for the comparison pool, and a baseline feature table.
4. **Propensity weighting and balance.** IPTW and overlap weights, or matching, with standardized mean differences, love plots, and overlap checks.
5. **Engagement.** Intent-to-treat vs. as-treated vs. per-protocol populations, and how results shift between them.
6. **Difference-in-differences checks.** Parallel trends, event-study leads, no anticipation, stable composition, and pre-period sensitivity.
7. **Modeling and ROI.** Two-part or GLM cost models and count models with cluster-robust errors, translated into PMPM savings and ROI with confidence intervals.
8. **Report.** An auto-generated report showing every check, so the result is auditable.

## Data model: Tuva

The pipeline reads the [Tuva Project](https://thetuvaproject.com/) data model rather than raw claims. Tuva turns claims into standard core tables and data marts (member months, encounters, CMS chronic conditions, CMS-HCC risk scores, PMPM), so any claims source mapped into Tuva's input layer works here without code changes. The `dbt/` folder is adapted from [tuva-health/demo](https://github.com/tuva-health/demo) and builds Tuva on its 1,000-member synthetic Medicare dataset (2016 to 2018) in a local DuckDB file.

## Validation by design

The first example runs a **simulated** care management program for members with diabetes. Enrollment is deliberately confounded by baseline risk (sicker, costlier members are more likely to enroll), and a known treatment effect is planted in enrollees' follow-up costs. The pipeline passes only if it recovers the planted effect while a naive comparison does not. The planted truth is written to a separate file that the analysis never reads.

The 1,000-member demo is enough to build and demo every stage. The final validation run will use a larger synthetic dataset mapped into Tuva.

## Quickstart

```bash
pip install -e ".[dbt,dev]"

# 1. Build the Tuva data model on the demo data (writes data/tuva.duckdb)
cd dbt
export DBT_PROFILES_DIR=.
dbt deps
dbt build            # add --vars '{tuva_seed_mirror: ../data/tuva_seeds}' if you mirrored seeds (below)
cd ..

# 2. Build the study cohort from the spec
claims-roi build-cohort specs/diabetes_care_mgmt.yaml
```

This writes to `data/analytic/`:

| File | Contents |
|---|---|
| `cohort.parquet` | One row per member: index date, enrolled or comparison, engagement tier |
| `member_month.parquet` | Costs and utilization by month relative to index (-12 to +11) |
| `baseline.parquet` | Baseline features: demographics, HCC score, chronic conditions, prior utilization and cost, cost trend |
| `truth.json` | The planted effect, for validation only |

**No internet access to S3 from DuckDB?** Tuva normally streams its seed files from S3 using DuckDB's `httpfs` extension. If that extension can't be installed, mirror the files once (about 1 GB) with `python scripts/mirror_tuva_seeds.py data/tuva_seeds` and pass the `tuva_seed_mirror` var shown above.

## Status

Early development. Roadmap:

- [x] Study spec format and first example spec
- [x] Tuva data model as the analytic layer (demo data in DuckDB)
- [x] Intervention anchoring, comparison pool, and baseline features
- [ ] Propensity weighting and balance diagnostics
- [ ] Engagement populations and DiD assumption checks
- [ ] DiD models, ROI with CIs, and the HTML report
- [ ] Claude Code skills that run and explain each stage

## Stack

Python (pandas, DuckDB, statsmodels to come), dbt for the Tuva data model. No real patient data is used or included.
