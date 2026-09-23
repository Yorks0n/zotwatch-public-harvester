from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from src.jobs import cleanup


NAMES = ("WORK_RETENTION_DAYS", "FETCH_RUN_RETENTION_DAYS", "RAW_PAYLOAD_RETENTION_DAYS")


class RetentionDefaultsTests(unittest.TestCase):
    def cleanup_days(self, env: dict[str, str], **kwargs) -> tuple[int, int, int]:
        observed = []

        def capture(_client, *, retention_days):
            observed.append(retention_days)
            return 0

        with patch.dict(os.environ, env, clear=True), patch.object(
            cleanup, "_delete_old_works", side_effect=capture
        ), patch.object(cleanup, "_delete_old_fetch_runs", side_effect=capture), patch.object(
            cleanup, "_delete_old_raw_payloads", side_effect=capture
        ):
            cleanup.run_cleanup(client=object(), **kwargs)
        return tuple(observed)

    def test_python_constants_are_canonical_90_30_7(self):
        self.assertEqual((cleanup.DEFAULT_WORK_RETENTION_DAYS,
                          cleanup.DEFAULT_FETCH_RUN_RETENTION_DAYS,
                          cleanup.DEFAULT_RAW_PAYLOAD_RETENTION_DAYS), (90, 30, 7))

    def test_unset_or_empty_workflow_variables_use_python_defaults(self):
        workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/harvest.yml").read_text()
        for name in NAMES:
            self.assertIn(f"{name}: ${'{{'} vars.{name} {'}}'}", workflow)
        self.assertNotIn("|| '90'", workflow)
        self.assertNotIn("|| '30'", workflow)
        self.assertNotIn("|| '7'", workflow)
        self.assertEqual(self.cleanup_days({}), (90, 30, 7))
        self.assertEqual(self.cleanup_days(dict.fromkeys(NAMES, "")), (90, 30, 7))

    def test_environment_and_explicit_overrides_win(self):
        env = dict(zip(NAMES, ("80", "20", "5")))
        self.assertEqual(self.cleanup_days(env), (80, 20, 5))
        self.assertEqual(self.cleanup_days(env, work_retention_days=70,
                                          fetch_run_retention_days=15,
                                          raw_payload_retention_days=4), (70, 15, 4))

    def test_invalid_or_nonpositive_environment_values_fall_back_safely(self):
        for invalid in ("bad", "0", "-2", "1.5", " "):
            with self.subTest(value=invalid):
                self.assertEqual(self.cleanup_days(dict.fromkeys(NAMES, invalid)), (90, 30, 7))


if __name__ == "__main__":
    unittest.main()
