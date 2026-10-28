"""Tests exercise failure modes that can change a survey analysis sample."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from survey_workflow import (read_inputs, validate_survey, construct_sample,
                             attach_policy, query_summaries)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.raw, self.policy, _ = read_inputs(ROOT / "fixtures", ROOT / "config/demo.json")
        self.survey = validate_survey(self.raw)
        self.sample, self.flow = construct_sample(self.survey)

    def test_sequential_filters_count_each_row_once(self):
        self.assertEqual(len(self.raw), 288)
        self.assertEqual(len(self.sample), 246)
        self.assertEqual(self.flow.removed.tolist(), [0, 6, 6, 6, 6, 6, 6, 6])

    def test_duplicate_respondent_key_fails(self):
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            validate_survey(pd.concat([self.raw, self.raw.iloc[[0]]], ignore_index=True))

    def test_missing_respondent_key_fails(self):
        bad = self.raw.copy()
        bad.loc[0, "record"] = None
        with self.assertRaisesRegex(ValueError, "keys"):
            validate_survey(bad)

    def test_binary_current_use_cannot_be_treated_as_raw_frequency(self):
        bad = self.raw.copy()
        # A binary no (2) would otherwise become "one or two days".
        bad.loc[bad.q34.eq(2), "q35"] = 2
        with self.assertRaisesRegex(ValueError, "raw vs binary"):
            validate_survey(bad)

    def test_invalid_response_code_fails(self):
        bad = self.raw.copy()
        bad.loc[0, "q35"] = 8
        with self.assertRaisesRegex(ValueError, "response codes"):
            validate_survey(bad)

    def test_district_data_are_not_silently_pooled_with_states(self):
        bad = self.raw.copy()
        bad.loc[0, "sitetypenum"] = 1
        with self.assertRaisesRegex(ValueError, "state-site"):
            validate_survey(bad)

    def test_frequency_midpoints_keep_zero_and_thirty(self):
        pairs = self.sample[["q35", "vaping_days_midpoint"]].drop_duplicates()
        self.assertEqual(dict(pairs.itertuples(index=False, name=None)),
                         {1: 0, 2: 1.5, 3: 4, 4: 7.5, 5: 14.5, 6: 24.5, 7: 30})

    def test_nonpositive_bmi_in_complete_sample_is_flagged(self):
        bad = self.survey.copy()
        bad.loc[10, "bmi"] = 0
        with self.assertRaisesRegex(ValueError, "nonpositive BMI"):
            construct_sample(bad)

    def test_policy_duplicates_do_not_multiply_respondents(self):
        bad = pd.concat([self.policy, self.policy.iloc[[0]]], ignore_index=True)
        with self.assertRaisesRegex(ValueError, "not unique"):
            attach_policy(self.sample, bad)

    def test_missing_policy_key_fails(self):
        bad = self.policy.copy()
        bad.loc[0, "sitecode"] = None
        with self.assertRaisesRegex(ValueError, "keys"):
            attach_policy(self.sample, bad)

    def test_unmatched_policy_rows_are_not_silently_dropped(self):
        with self.assertRaisesRegex(ValueError, "Incomplete policy join"):
            attach_policy(self.sample, self.policy.iloc[1:])

    def test_matched_key_with_missing_covariate_fails(self):
        bad = self.policy.copy()
        bad.loc[0, "yearly_unemployrate"] = None
        with self.assertRaisesRegex(ValueError, "Incomplete policy join"):
            attach_policy(self.sample, bad)

    def test_many_respondents_share_one_policy_record(self):
        joined, audit = attach_policy(self.sample, self.policy)
        self.assertEqual(len(joined), 246)
        self.assertEqual(audit["matched_rows"], 246)
        self.assertEqual(audit["unmatched_rows"], 0)

    def test_sql_and_pandas_agree(self):
        joined, _ = attach_policy(self.sample, self.policy)
        by_year, site_year = query_summaries(joined, self.survey)
        self.assertEqual(by_year.complete_responses.tolist(), [82, 82, 82])
        self.assertEqual(by_year.included_sites.tolist(), [2, 2, 2])
        self.assertEqual(site_year.responses.tolist(), [41] * 6)

    def test_small_cells_cannot_be_exported(self):
        joined, _ = attach_policy(self.sample, self.policy)
        with self.assertRaisesRegex(ValueError, "fewer than 30"):
            query_summaries(joined.iloc[:2], self.survey)

    def test_cli_runs_without_private_data_or_row_level_exports(self):
        with tempfile.TemporaryDirectory() as folder:
            subprocess.run([sys.executable, str(ROOT / "src/survey_workflow.py"),
                            "--demo", "--output", folder], check=True, capture_output=True)
            report = json.loads((Path(folder) / "run_summary.json").read_text())
            self.assertEqual(report["data_mode"], "synthetic")
            self.assertEqual(report["complete_responses"], 246)
            for file in Path(folder).glob("*.csv"):
                self.assertNotIn("record", pd.read_csv(file).columns)


if __name__ == "__main__":
    unittest.main()
