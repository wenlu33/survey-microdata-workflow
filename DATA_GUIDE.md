# Data and reproduction guide

## Sources

- CDC, [YRBS data and documentation](https://www.cdc.gov/yrbs/data/), **2019 combined high-school state files A-M and N-Z**. These combined files contain multiple survey years. The local project exports retain 2015, 2017, and 2019.
- CDC, [2019 combined datasets user's guide](https://www.cdc.gov/yrbs/files/2019/pdf/2019_YRBS_SADC_Documentation.pdf), especially variable definitions and analytic considerations.
- CDC, [combining YRBS data across years and sites](https://www.cdc.gov/yrbs/media/pdf/2023/2023_YRBS_combining_data.pdf), for design and weighting requirements when moving beyond sample counts.
- The original project policy workbook, `E-cig_tax.xlsx`, combines state/year e-cigarette tax measures, an indoor-ban indicator, and annual unemployment. This companion treats it as an existing local input. It does not recreate its source collection or infer undocumented tax units.

The survey project is about adolescent health. Unemployment is a contextual control. The existence of that variable does not make the dataset a workforce study.

## Survey input schema

| Field | Meaning / handling |
|---|---|
| `sitecode`, `year`, `record` | Composite unique respondent key within the combined exports |
| `sitetypenum` | 2 for state-site surveys; district and national rows rejected |
| `weight` | Read for provenance; not applied to the sample counts in this companion |
| `age` | 1-7 categories; endpoints mean 12 or younger and 18 or older |
| `sex` | 1=female, 2=male, as coded in these historical surveys |
| `grade` | 1-4, corresponding to grades 9-12 |
| `race7` | Seven-category race/ethnicity field |
| `q34` | Ever electronic-vapor-product use: 1=yes, 2=no |
| `q35` | Raw frequency categories listed below |
| `bmi` | Existing CDC BMI variable, not an obesity classification |

The input manifest names the actual raw question columns. Local legacy column names alone are insufficient to identify whether a field contains raw categories or a binary indicator. The A-M input used here carries the raw response in the `qn35`-named column of its legacy export; the N-Z input uses `q35`. The mappings were checked by joining each raw export to its paired indicator export on site/year/record. Use the official codebook, not the spelling of the filename, to interpret a column.

### Raw Q35 frequency

| Code | Days in past 30 | Optional midpoint |
|---|---|---:|
| 1 | 0 | 0 |
| 2 | 1-2 | 1.5 |
| 3 | 3-5 | 4 |
| 4 | 6-9 | 7.5 |
| 5 | 10-19 | 14.5 |
| 6 | 20-29 | 24.5 |
| 7 | 30 | 30 |

Midpoints are an approximation to category intervals, not exact observed days. They are generated for transparency and not used to estimate a model here. The companion checks that someone coded as never having vaped is not simultaneously coded as a current user. This is one diagnostic, not proof of every field's correctness.

## Policy schema

One row per `sitecode` and `year`, with `fips`, `ecigtax`, `ecigtax_c`, `yearly_unemployrate`, and `banned`. The legacy workbook's `FIPS Code` is renamed `fips`. Keep year numeric and site codes consistent with the survey. Blank keys, duplicate keys, unmatched survey rows, and missing linked covariates stop the run.

## Reproduction boundary

The code, SQL, synthetic example, and aggregate reports are public. The actual respondent records and policy workbook remain local. File checksums in `reports/run_summary.json` identify the inputs used for the real run without distributing them. Consequently, the public repository supports a complete synthetic run and code review; reproducing the exact research-data aggregates requires the corresponding local inputs.

Reports show unweighted response counts. The source surveys' weighting and design requirements would need to be addressed separately for population inference. Individual respondents are not followed across survey years.
