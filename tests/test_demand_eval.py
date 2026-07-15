import json
import unittest
from pathlib import Path

from scripts.evaluate_demand_gate import evaluate


ROOT = Path(__file__).resolve().parents[1]


class DemandEvalTest(unittest.TestCase):
    def test_versioned_gate_cases_meet_quality_floor(self):
        payload = json.loads((ROOT / "tests" / "fixtures" / "demand_gate_cases.json").read_text(encoding="utf-8"))
        result = evaluate(payload)

        self.assertGreaterEqual(result["precision"], 0.8)
        self.assertGreaterEqual(result["recall"], 0.5)


if __name__ == "__main__":
    unittest.main()
