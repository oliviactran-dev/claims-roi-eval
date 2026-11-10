"""Read the Tuva data model into the tables the pipeline needs.

Everything downstream works from three frames:
  * patients: one row per person (demographics, death date)
  * panel: one row per person per enrolled month (costs and utilization)
  * conditions: one row per person per CMS chronic condition (onset date)
  * risk: one row per person per payment year (CMS-HCC score from the prior year)
"""
from __future__ import annotations

import duckdb
import pandas as pd

# Short names for the CMS chronic conditions used as covariates
CONDITION_FLAGS = {
    "chf": "Heart Failure and Non-Ischemic Heart Disease",
    "copd": "Chronic Obstructive Pulmonary Disease",
    "ckd": "Chronic Kidney Disease",
    "ischemic_heart_disease": "Ischemic Heart Disease",
    "depression": "Depression, Bipolar, or Other Depressive Mood Disorders",
}


def connect(spec: dict, root=".") -> duckdb.DuckDBPyConnection:
    from pathlib import Path

    return duckdb.connect(str(Path(root) / spec["data"]["database"]), read_only=True)


def load_patients(con, t: dict) -> pd.DataFrame:
    return con.sql(f"""
        select person_id, sex, race, birth_date, death_date
        from {t['patient']}
    """).df()


def load_panel(con, t: dict) -> pd.DataFrame:
    """Member-month panel: enrolled months with paid amounts and encounter counts."""
    return con.sql(f"""
        with mm as (
            select distinct person_id, year_month from {t['member_months']}
        ),
        cost as (
            select person_id, year_month,
                   sum(total_paid) as total_paid,
                   sum(medical_paid) as medical_paid,
                   sum(pharmacy_paid) as pharmacy_paid
            from {t['costs']}
            group by all
        ),
        enc as (
            select person_id,
                   strftime(encounter_start_date, '%Y%m') as year_month,
                   count(*) filter (where encounter_type = 'acute inpatient') as ip_admits,
                   count(*) filter (where encounter_type = 'emergency department') as ed_visits,
                   count(*) filter (where encounter_type = 'office visit') as office_visits
            from {t['encounters']}
            group by all
        )
        select mm.person_id,
               strptime(mm.year_month || '01', '%Y%m%d')::date as month,
               coalesce(cost.total_paid, 0)::double as total_paid,
               coalesce(cost.medical_paid, 0)::double as medical_paid,
               coalesce(cost.pharmacy_paid, 0)::double as pharmacy_paid,
               coalesce(enc.ip_admits, 0) as ip_admits,
               coalesce(enc.ed_visits, 0) as ed_visits,
               coalesce(enc.office_visits, 0) as office_visits
        from mm
        left join cost using (person_id, year_month)
        left join enc using (person_id, year_month)
    """).df()


def load_conditions(con, t: dict) -> pd.DataFrame:
    return con.sql(f"""
        select person_id, condition, min(start_date) as onset_date
        from {t['chronic_conditions']}
        group by all
    """).df()


def load_risk(con, t: dict) -> pd.DataFrame:
    """Prospective CMS-HCC score: the full prior calendar year's diagnoses,
    keyed by payment_year (= the year the score applies to)."""
    return con.sql(f"""
        select person_id, payment_year, blended_risk_score::double as hcc_risk_score
        from {t['risk_scores']}
        where month(collection_end_date) = 12
    """).df()


def load_all(spec: dict, root=".") -> dict[str, pd.DataFrame]:
    t = spec["data"]["tables"]
    with connect(spec, root) as con:
        return {
            "patients": load_patients(con, t),
            "panel": load_panel(con, t),
            "conditions": load_conditions(con, t),
            "risk": load_risk(con, t),
        }
