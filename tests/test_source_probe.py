import unittest

from scripts.source_probe import classify_probe, summarize_attempts


class SourceProbeTest(unittest.TestCase):
    def test_classify_probe_marks_auth_and_blocked_cases(self):
        self.assertEqual(classify_probe(ok=False, status=401, body="Unauthorized")["status"], "needs_auth")
        self.assertEqual(classify_probe(ok=False, status=403, body="Forbidden")["status"], "blocked")
        self.assertEqual(classify_probe(ok=True, status=200, body="<html></html>")["status"], "reachable")

    def test_summarize_attempts_requires_one_working_or_three_failures(self):
        blocked = summarize_attempts("Toolify", [
            {"method": "direct_page", "status": "blocked"},
            {"method": "rss", "status": "not_found"},
            {"method": "official_api", "status": "needs_auth"},
        ])
        working = summarize_attempts("Product Hunt", [
            {"method": "official_feed", "status": "reachable"},
        ])

        self.assertEqual(blocked["state"], "not_integrated")
        self.assertEqual(blocked["attempt_count"], 3)
        self.assertEqual(working["state"], "integrated")


if __name__ == "__main__":
    unittest.main()
