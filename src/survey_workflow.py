"""Auditable sample construction for pooled YRBS microdata.

Python/SQLite portfolio companion prepared in October 2026.
The original research analysis was written in Stata. No row-level exports.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
YEARS = (2015, 2017, 2019)
KEYS = ["sitecode", "year", "record"]
REQUIRED = ["age", "sex", "grade", "race7", "q34", "q35", "bmi"]
POLICY_VARS = ["fips", "ecigtax", "ecigtax_c", "yearly_unemployrate", "banned"]
COMMON = KEYS + ["sitetypenum", "weight", "age", "sex", "grade", "race7", "bmi"]
DOMAINS = {"age": range(1, 8), "sex": [1, 2], "grade": range(1, 5),
           "race7": range(1, 8), "q34": [1, 2], "q35": range(1, 8)}


def read_inputs(root: Path, manifest: Path):
    config = json.loads(manifest.read_text())
    frames, provenance = [], []
    for spec in config["survey_sources"]:
        path = root / spec["path"]
        columns = list(dict.fromkeys(COMMON + [spec["q34"], spec["q35"]]))
        frame = pd.read_csv(path, usecols=columns).rename(
            columns={spec["q34"]: "q34", spec["q35"]: "q35"})
        frame["source_file"] = path.name
        frames.append(frame)
        provenance.append({"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                           "rows": len(frame), "q34_source": spec["q34"], "q35_source": spec["q35"]})
    policy_path = root / config["policy"]
    policy = (pd.read_excel(policy_path) if policy_path.suffix == ".xlsx"
              else pd.read_csv(policy_path))
    policy = policy.rename(columns=config.get("policy_rename", {}))
    provenance.append({"file": policy_path.name,
                       "sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
                       "rows": len(policy)})
    return pd.concat(frames, ignore_index=True), policy, provenance


def validate_survey(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    missing = set(COMMON + ["q34", "q35"]) - set(df.columns)
    if missing:
        raise ValueError(f"Missing survey columns: {sorted(missing)}")
    df["sitecode"] = df.sitecode.astype("string").str.strip().str.upper()
    if df[KEYS].isna().any().any() or df.sitecode.eq("").any():
        raise ValueError("Survey keys must be nonmissing.")
    if df.duplicated(KEYS).any():
        raise ValueError("Duplicate site/year/record keys; survey rows would be counted twice.")
    if not df.year.isin(YEARS).all() or not df.sitetypenum.eq(2).all():
        raise ValueError("This workflow expects state-site surveys from 2015, 2017, and 2019.")
    df["year"] = df.year.astype("int64")
    for col, domain in DOMAINS.items():
        if not df[col].dropna().isin(domain).all():
            raise ValueError(f"Invalid response codes in {col}.")
    # A binary current-use indicator (1=yes, 2=no) must not be interpreted as
    # raw Q35 (1=zero days, 2=one or two days, ..., 7=all 30 days).
    if (df.q34.eq(2) & df.q35.gt(1)).any():
        raise ValueError("Q35 conflicts with never-use responses. Check raw vs binary coding.")
    return df


def construct_sample(df: pd.DataFrame):
    current = df.copy()
    rows = [{"step": "All survey responses", "removed": 0, "remaining": len(current)}]
    for col in REQUIRED:
        previous = len(current)
        current = current.loc[current[col].notna()].copy()
        rows.append({"step": f"Observed {col}", "removed": previous - len(current),
                     "remaining": len(current)})
    if current.empty:
        raise ValueError("No complete survey responses remain.")
    if not current.bmi.gt(0).all():
        raise ValueError("The complete-case sample contains nonpositive BMI; review these records.")
    # End categories are open: age code 1 means <=12; code 7 means >=18.
    # Preserve the codes rather than treating the endpoints as exact ages.
    current["female"] = current.sex.eq(1).astype(int)
    current["ever_vaped"] = current.q34.eq(1).astype(int)
    current["current_vaped"] = current.q35.gt(1).astype(int)
    current["vaping_days_midpoint"] = current.q35.map(
        {1: 0, 2: 1.5, 3: 4, 4: 7.5, 5: 14.5, 6: 24.5, 7: 30})
    return current, pd.DataFrame(rows)


def attach_policy(sample: pd.DataFrame, policy: pd.DataFrame):
    needed = ["sitecode", "year"] + POLICY_VARS
    missing = set(needed) - set(policy.columns)
    if missing:
        raise ValueError(f"Missing policy columns: {sorted(missing)}")
    policy = policy[needed].copy()
    policy["sitecode"] = policy.sitecode.astype("string").str.strip().str.upper()
    if policy[["sitecode", "year"]].isna().any().any() or policy.sitecode.eq("").any():
        raise ValueError("Policy keys must be nonmissing.")
    if policy.duplicated(["sitecode", "year"]).any():
        raise ValueError("Policy keys are not unique; a join would multiply respondents.")
    joined = sample.merge(policy, on=["sitecode", "year"], how="left",
                          validate="many_to_one", indicator=True)
    unmatched = int(joined._merge.eq("left_only").sum())
    missing_covariates = int(joined[POLICY_VARS].isna().any(axis=1).sum())
    audit = {"survey_rows": len(sample), "joined_rows": len(joined),
             "matched_rows": len(joined) - unmatched, "unmatched_rows": unmatched,
             "rows_missing_policy_covariates": missing_covariates}
    if unmatched or missing_covariates:
        raise ValueError(f"Incomplete policy join: {audit}")
    return joined.drop(columns="_merge"), audit


def query_summaries(sample: pd.DataFrame, survey: pd.DataFrame):
    """Run actual SQL over local microdata and verify against pandas."""
    with sqlite3.connect(":memory:") as connection:
        survey.to_sql("survey", connection, index=False)
        sample.to_sql("analysis_sample", connection, index=False)
        by_year = pd.read_sql_query((REPO / "sql/sample_by_year.sql").read_text(), connection)
        grouped = pd.read_sql_query((REPO / "sql/site_year.sql").read_text(), connection)
    expected = sample.groupby("year").agg(
        complete_responses=("record", "size"), included_sites=("sitecode", "nunique"))
    expected = expected.reindex(sorted(survey.year.unique()), fill_value=0).reset_index()
    pd.testing.assert_frame_equal(by_year[["year", "complete_responses", "included_sites"]],
                                  expected, check_dtype=False)
    if (grouped.responses < 30).any():
        raise ValueError("At least one site/year summary has fewer than 30 responses.")
    return by_year, grouped


def flow_svg(flow: pd.DataFrame, demo: bool):
    title = "From survey records to an analysis-ready sample"
    subtitle = "SYNTHETIC DEMO" if demo else "YRBS pooled state-site responses | 2015, 2017, 2019"
    labels = {"All survey responses": "Starting sample", "Observed age": "Age observed",
              "Observed sex": "Sex observed", "Observed grade": "Grade observed",
              "Observed race7": "Race/ethnicity observed", "Observed q34": "Lifetime use observed",
              "Observed q35": "Frequency observed", "Observed bmi": "BMI observed"}
    start, end = int(flow.iloc[0].remaining), int(flow.iloc[-1].remaining)
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="750" viewBox="0 0 1200 750">',
             '<rect width="1200" height="750" fill="#f7f8fa"/>',
             '<rect x="30" y="30" width="1140" height="690" rx="22" fill="white"/>',
             '<g font-family="Arial, sans-serif" fill="#172b3a">',
             f'<text x="66" y="82" font-size="18" fill="#167c80">{subtitle}</text>',
             f'<text x="66" y="128" font-size="32" font-weight="700">{title}</text>',
             f'<text x="66" y="172" font-size="21">{end:,} complete responses | {end/start:.1%} retained</text>']
    for i, row in flow.iterrows():
        y = 214 + i * 53
        width = 570 * row.remaining / start
        color = "#16858a" if i == len(flow) - 1 else "#a9ced0"
        parts += [f'<text x="66" y="{y+22}" font-size="19">{labels[row.step]}</text>',
                  f'<rect x="340" y="{y}" width="570" height="31" rx="5" fill="#edf2f4"/>',
                  f'<rect x="340" y="{y}" width="{width:.2f}" height="31" rx="5" fill="{color}"/>',
                  f'<text x="1085" y="{y+23}" font-size="21" text-anchor="end">{int(row.remaining):,}</text>']
    parts += ['<text x="66" y="675" font-size="16" fill="#556675">Sequential complete-case filters. Counts describe the available sample; they are unweighted.</text>',
              '</g></svg>']
    return "\n".join(parts)


def write_outputs(out: Path, survey, sample, flow, audit, provenance, demo=False):
    by_year, site_year = query_summaries(sample, survey)
    out.mkdir(parents=True, exist_ok=True)
    flow.to_csv(out / "sample_flow.csv", index=False)
    by_year.to_csv(out / "sample_by_year.csv", index=False)
    # Release aggregate counts only. No respondent rows, BMI means, or health effects.
    site_year.to_csv(out / "site_year_counts.csv", index=False)
    (out / "sample_flow.svg").write_text(flow_svg(flow, demo))
    metadata = {"data_mode": "synthetic" if demo else "local_research_data", "years": list(YEARS),
                "raw_responses": len(survey), "complete_responses": len(sample),
                "raw_sites": int(survey.sitecode.nunique()),
                "included_sites": int(sample.sitecode.nunique()),
                "retention_pct": round(100 * len(sample) / len(survey), 2),
                "join_audit": audit, "sources": provenance,
                "q35_coding": "raw seven-category frequency; 1=0 days, 7=30 days",
                "original_analysis_language": "Stata", "companion_languages": ["Python", "SQL"],
                "population_estimates": False, "causal_effects_estimated": False}
    (out / "run_summary.json").write_text(json.dumps(metadata, indent=2) + "\n")
    table = "| Year | Source responses | Complete responses | Sites retained | Retained |\n|---|---:|---:|---:|---:|\n"
    for r in by_year.itertuples():
        table += f"| {r.year} | {r.source_responses:,} | {r.complete_responses:,} | {r.included_sites} | {r.retention_pct:.1f}% |\n"
    report = f"""# Building a reliable sample from {len(survey):,} survey responses

{'**Synthetic demonstration. These are invented test records, not research results.**' if demo else '**Data preparation case study | Wen Lu | October 2026**'}

Before estimating a policy effect, I need to know which observations are usable and whether state-level data attach correctly to each survey response. This companion makes those steps visible.

![Sequential sample construction](sample_flow.svg)

## What the workflow establishes

The starting files contain **{len(survey):,} responses** across **{survey.sitecode.nunique()} sites** in 2015, 2017, and 2019. Requiring observed age, sex, grade, race/ethnicity, lifetime vaping, vaping frequency, and BMI leaves **{len(sample):,} complete responses across {sample.sitecode.nunique()} sites**. That retains **{len(sample)/len(survey):.1%}** of the input rows.

{table}
The filters remove rows with missing fields. A blank can reflect an omitted question as well as individual nonresponse; the workflow does not label all missingness as refusal. The separate sample-flow table records the observations removed at each step, in the order used in the original Stata preparation.

## Linking the policy context

The site/year join matches **{audit['matched_rows']:,} of {audit['survey_rows']:,} complete survey responses**, with **{audit['unmatched_rows']:,} unmatched rows** and no increase in row count. Each policy key occurs once. The linked table provides e-cigarette tax measures, an indoor-ban indicator, and annual unemployment. Unemployment supplies state economic context; this is a health-policy dataset.

## Decisions that matter

- Raw vaping frequency has seven categories. A yes/no current-use indicator cannot be substituted for it. Source-column mappings are explicit, and logically contradictory codes stop the run.
- Age endpoints are categories, not exact ages. The workflow retains the original codes.
- A duplicate policy key can multiply respondents during a merge. The join validates its many-to-one relationship and rejects missing covariates.
- SQL and pandas independently calculate annual sample counts and site coverage, then compare the results.

## How to read these outputs

These are **unweighted sample counts** from pooled cross sections, not estimates of U.S. prevalence or repeated observations on the same students. The original research uses Stata regression and instrumental-variable models. This Python/SQL companion documents preparation and linkage; it estimates no health effect. Population inference would require the appropriate survey design and weighting.

**Source:** CDC, [2019 combined YRBS guide](https://www.cdc.gov/yrbs/files/2019/pdf/2019_YRBS_SADC_Documentation.pdf), questionnaire definitions on printed pages 39-40 and analytic considerations on page 18. [CDC combining guidance](https://www.cdc.gov/yrbs/media/pdf/2023/2023_YRBS_combining_data.pdf).
"""
    (out / "case_study.md").write_text(report)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="Run on the included synthetic fixture.")
    parser.add_argument("--input-root", type=Path)
    parser.add_argument("--manifest", type=Path, default=REPO / "config/legacy_exports.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.demo:
        root, manifest = REPO / "fixtures", REPO / "config/demo.json"
    else:
        if args.input_root is None:
            parser.error("Supply --input-root for local data, or use --demo.")
        root, manifest = args.input_root, args.manifest
    raw, policy, provenance = read_inputs(root, manifest)
    survey = validate_survey(raw)
    sample, flow = construct_sample(survey)
    joined, audit = attach_policy(sample, policy)
    result = write_outputs(args.output, survey, joined, flow, audit, provenance, args.demo)
    print(json.dumps({k: result[k] for k in ["data_mode", "raw_responses", "complete_responses", "included_sites"]}))


if __name__ == "__main__":
    main()
