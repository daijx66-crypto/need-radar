import unittest

from scripts.analyze_feedback import summarize


class FeedbackAnalysisTest(unittest.TestCase):
    def test_feedback_suggestions_are_bounded_and_review_only(self):
        payload = {"feedback": [
            {"source": "AI HOT", "kind": "shift", "value": "noise"}
            for _ in range(10)
        ] + [
            {"source": "V2EX", "kind": "need", "value": "useful"}
            for _ in range(10)
        ]}

        report = summarize(payload)
        source = {row["name"]: row for row in report["source_suggestions"]}

        self.assertEqual(report["mode"], "review_only")
        self.assertEqual(source["AI HOT"]["suggested_delta"], -6)
        self.assertEqual(source["V2EX"]["suggested_delta"], 6)


if __name__ == "__main__":
    unittest.main()
