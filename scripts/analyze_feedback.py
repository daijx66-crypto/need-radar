#!/usr/bin/env python3
"""Turn exported browser feedback into bounded, review-only suggestions.

This script never edits scoring code or profiles. It produces an explainable
report that a person can review before changing a private local profile.
"""
import argparse
import collections
import json
from pathlib import Path


VALUE = {"useful": 1, "noise": -1, "later": 0}


def summarize(payload):
    rows = payload.get("feedback") or []
    source = collections.defaultdict(list)
    kind = collections.defaultdict(list)
    for row in rows:
        value = row.get("value")
        if value not in VALUE:
            continue
        source[str(row.get("source") or "未知来源")].append(VALUE[value])
        kind[str(row.get("kind") or "unknown")].append(VALUE[value])

    def suggestions(groups, multiplier, limit):
        result = []
        for name, votes in sorted(groups.items()):
            net = sum(votes)
            result.append({
                "name": name,
                "votes": len(votes),
                "useful_minus_noise": net,
                "suggested_delta": max(-limit, min(limit, net * multiplier)),
                "confidence": "review" if len(votes) < 3 else "usable",
            })
        return result

    return {
        "schema_version": 1,
        "mode": "review_only",
        "feedback_count": len(rows),
        "source_suggestions": suggestions(source, 2, 6),
        "kind_suggestions": suggestions(kind, 1, 3),
        "guardrail": "Suggestions are bounded and are never applied automatically.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", help="JSON exported by the web interface")
    parser.add_argument("--output", help="optional report path")
    args = parser.parse_args()
    payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
    report = summarize(payload)
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
