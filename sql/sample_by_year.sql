-- Counts describe the available sample. No survey-weighted prevalence estimates.
WITH source AS (
    SELECT year, COUNT(*) AS source_responses
    FROM survey
    GROUP BY year
), complete AS (
    SELECT year, COUNT(*) AS complete_responses,
           COUNT(DISTINCT sitecode) AS included_sites
    FROM analysis_sample
    GROUP BY year
)
SELECT source.year, source.source_responses,
       COALESCE(complete.complete_responses, 0) AS complete_responses,
       COALESCE(complete.included_sites, 0) AS included_sites,
       ROUND(100.0 * COALESCE(complete.complete_responses, 0)
             / source.source_responses, 2) AS retention_pct
FROM source
LEFT JOIN complete ON source.year = complete.year
ORDER BY source.year;
