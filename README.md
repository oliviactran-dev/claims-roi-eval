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

## Validation by design

The first example uses [CMS DE-SynPUF](https://www.cms.gov/data-research/statistics-trends-and-reports/medicare-claims-synthetic-public-use-files) (synthetic Medicare FFS claims, 2008 to 2010) with a **simulated** care management program for members with diabetes. Enrollment is deliberately confounded by baseline risk, and a known treatment effect is planted in follow-up costs. The pipeline passes only if it recovers the planted effect while a naive comparison does not.

## Status

Early development. Roadmap:

- [ ] Study spec format and first example spec
- [ ] SynPUF ingest into the member-month and event schema
- [ ] Intervention anchoring, comparison pool, and baseline features
- [ ] Propensity weighting and balance diagnostics
- [ ] Engagement populations and DiD assumption checks
- [ ] DiD models, ROI with CIs, and the HTML report
- [ ] Claude Code skills that run and explain each stage

## Stack

Python (pandas or polars, statsmodels, linearmodels). No real patient data is used or included.
