import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest import mock

from scripts.refresh import classify_collector, overall_status, run_process


class RefreshStatusTest(unittest.TestCase):
    @mock.patch("scripts.refresh.time.monotonic", side_effect=[100.0, 104.2])
    @mock.patch("scripts.refresh.subprocess.run", return_value=CompletedProcess([], 0, "ok", ""))
    def test_process_duration_uses_monotonic_clock(self, _run, _clock):
        result = run_process("source", Path("collector.py"), print_status=False)

        self.assertEqual(result["secs"], 4.2)

    def test_zero_exit_with_empty_payload_is_not_success(self):
        result = classify_collector(
            {"label": "source", "status": "success", "ok": True},
            {"count": 0, "generated_at": "2026-07-15T08:00:00+08:00"},
        )

        self.assertEqual(result["status"], "empty")
        self.assertFalse(result["ok"])

    def test_score_failure_makes_whole_run_fail(self):
        status = overall_status(
            {"status": "failed"},
            "2026-07-15T08:00:00+08:00",
            {"aihot"},
            [],
            [],
        )

        self.assertEqual(status, "failed")

    def test_stale_raw_file_does_not_turn_zero_exit_green(self):
        result = classify_collector(
            {"label": "source", "status": "success", "ok": True},
            {"count": 5, "generated_at": "2026-07-10T08:00:00+08:00"},
            produced=False,
        )

        self.assertEqual(result["status"], "failed")
        self.assertIn("fresh raw file", result["err"])

    def test_missing_required_source_is_degraded_not_green(self):
        status = overall_status(
            {"status": "success"},
            "2026-07-15T08:00:00+08:00",
            {"aihot"},
            [],
            ["hackernews"],
        )

        self.assertEqual(status, "degraded")


if __name__ == "__main__":
    unittest.main()
