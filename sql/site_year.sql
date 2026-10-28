-- Publish aggregate counts, with a minimum cell size enforced in Python.
SELECT sitecode, year, COUNT(*) AS responses
FROM analysis_sample
GROUP BY sitecode, year
ORDER BY sitecode, year;
