import datetime
import unittest

from scripts.quality_gate import evaluate


class QualityGateTest(unittest.TestCase):
    def payload(self, item):
        generated = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return ({
            "generated_at": generated,
            "needs": [],
            "watchlist": [],
            "attention": {"limits": {"now": 5}, "items": [item]},
        }, {"status": "success", "generated_at": generated})

    def test_rejects_stale_now_item(self):
        payload, status = self.payload({
            "stable_id": "shift-a",
            "kind": "shift",
            "priority": "now",
            "attention_score": 90,
            "is_stale": True,
            "url": "https://example.com/item",
            "title": "Old item",
        })

        result = evaluate(payload, status)
        self.assertFalse(result["passed"])
        self.assertTrue(any("stale item" in error for error in result["errors"]))

    def test_accepts_empty_honest_day(self):
        payload, status = self.payload({
            "stable_id": "shift-a",
            "kind": "shift",
            "priority": "ignore",
            "attention_score": 40,
            "is_stale": False,
            "url": "https://example.com/item",
            "title": "Below threshold",
        })

        self.assertTrue(evaluate(payload, status)["passed"])


if __name__ == "__main__":
    unittest.main()
