# Building a reliable sample from 576,452 survey responses

**Data preparation case study | Wen Lu | October 2026**

Before estimating a policy effect, I need to know which observations are usable and whether state-level data attach correctly to each survey response. This companion makes those steps visible.

![Sequential sample construction](sample_flow.svg)

## What the workflow establishes

The starting files contain **576,452 responses** across **44 sites** in 2015, 2017, and 2019. Requiring observed age, sex, grade, race/ethnicity, lifetime vaping, vaping frequency, and BMI leaves **400,742 complete responses across 43 sites**. That retains **69.5%** of the input rows.

| Year | Source responses | Complete responses | Sites retained | Retained |
|---|---:|---:|---:|---:|
| 2015 | 204,238 | 136,523 | 29 | 66.8% |
| 2017 | 189,723 | 128,259 | 32 | 67.6% |
| 2019 | 182,491 | 135,960 | 40 | 74.5% |

The filters remove rows with missing fields. A blank can reflect an omitted question as well as individual nonresponse; the workflow does not label all missingness as refusal. The separate sample-flow table records the observations removed at each step, in the order used in the original Stata preparation.

## Linking the policy context

The site/year join matches **400,742 of 400,742 complete survey responses**, with **0 unmatched rows** and no increase in row count. Each policy key occurs once. The linked table provides e-cigarette tax measures, an indoor-ban indicator, and annual unemployment. Unemployment supplies state economic context; this is a health-policy dataset.

## Decisions that matter

- Raw vaping frequency has seven categories. A yes/no current-use indicator cannot be substituted for it. Source-column mappings are explicit, and logically contradictory codes stop the run.
- Age endpoints are categories, not exact ages. The workflow retains the original codes.
- A duplicate policy key can multiply respondents during a merge. The join validates its many-to-one relationship and rejects missing covariates.
- SQL and pandas independently calculate annual sample counts and site coverage, then compare the results.

## How to read these outputs

These are **unweighted sample counts** from pooled cross sections, not estimates of U.S. prevalence or repeated observations on the same students. The original research uses Stata regression and instrumental-variable models. This Python/SQL companion documents preparation and linkage; it estimates no health effect. Population inference would require the appropriate survey design and weighting.

**Source:** CDC, [2019 combined YRBS guide](https://www.cdc.gov/yrbs/files/2019/pdf/2019_YRBS_SADC_Documentation.pdf), questionnaire definitions on printed pages 39-40 and analytic considerations on page 18. [CDC combining guidance](https://www.cdc.gov/yrbs/media/pdf/2023/2023_YRBS_combining_data.pdf).
