#!/usr/bin/env python3
"""Measure deterministic demand-gate precision/recall on versioned cases."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from collectors._common import mk_signal
from scorer import score


def evaluate(payload):
    confusion = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    failures = []
    for case in payload.get("cases") or []:
        raw = {
            "id": case["id"],
            "source": "eval",
            "region": "通用",
            "url": f"https://example.com/eval/{case['id']}",
            "popularity": 0,
            "comments": 0,
            "created_at": "2026-07-15T00:00:00Z",
            **case["signal"],
        }
        signal = score.featurize(mk_signal(**raw))
        gate = score.semantic_gate(signal)
        predicted = "need" if gate["should_rank"] and score.need_candidate(signal, gate) else "noise"
        expected = case["expected"]
        key = "tp" if expected == predicted == "need" else "tn" if expected == predicted == "noise" else "fp" if predicted == "need" else "fn"
        confusion[key] += 1
        if predicted != expected:
            failures.append({"id": case["id"], "expected": expected, "predicted": predicted, "gate": gate})
    tp, fp, tn, fn = (confusion[key] for key in ("tp", "fp", "tn", "fn"))
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    accuracy = (tp + tn) / max(1, tp + fp + tn + fn)
    return {
        "policy_version": payload.get("policy_version"),
        "cases": tp + fp + tn + fn,
        "confusion": confusion,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "accuracy": round(accuracy, 3),
        "failures": failures,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(ROOT / "tests" / "fixtures" / "demand_gate_cases.json"))
    parser.add_argument("--min-precision", type=float, default=0.8)
    parser.add_argument("--min-recall", type=float, default=0.5)
    args = parser.parse_args()
    result = evaluate(json.loads(Path(args.cases).read_text(encoding="utf-8")))
    print(json.dumps(result, ensure_ascii=False))
    if result["precision"] < args.min_precision or result["recall"] < args.min_recall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
