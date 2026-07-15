#!/usr/bin/env python3
"""Fail closed when a daily result is stale, malformed, or below attention rules."""
import argparse
import datetime
import json
import os
from pathlib import Path
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_THRESHOLDS = {"need": 60, "shift": 68, "builder": 68}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def parse_time(value):
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def valid_url(value):
    parts = urlsplit(value or "")
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def evaluate(payload, status, max_age_hours=36):
    errors = []
    warnings = []
    generated = parse_time(payload.get("generated_at"))
    now = datetime.datetime.now(datetime.timezone.utc)
    if not generated:
        errors.append("missing or invalid generated_at")
    elif (now - generated.astimezone(datetime.timezone.utc)).total_seconds() > max_age_hours * 3600:
        errors.append(f"data older than {max_age_hours} hours")
    if status.get("status") == "failed":
        errors.append("refresh status is failed")
    elif status.get("status") == "degraded":
        warnings.append("refresh status is degraded")
    if status.get("generated_at") != payload.get("generated_at"):
        errors.append("last_run.generated_at does not match needs.generated_at")

    attention = payload.get("attention") or {}
    items = attention.get("items") or []
    now_rows = [row for row in items if row.get("priority") == "now"]
    now_limit = int((attention.get("limits") or {}).get("now") or 0)
    if len(now_rows) > now_limit:
        errors.append("now attention budget exceeded")
    seen = set()
    for row in items:
        stable_id = row.get("stable_id")
        if not stable_id:
            errors.append("attention item missing stable_id")
        elif stable_id in seen:
            errors.append(f"duplicate stable_id: {stable_id}")
        seen.add(stable_id)
    for row in now_rows:
        kind = row.get("kind")
        if not valid_url(row.get("url")):
            errors.append(f"now item missing verifiable URL: {row.get('title')}")
        if row.get("is_stale"):
            errors.append(f"stale item promoted to now: {row.get('title')}")
        threshold = DEFAULT_THRESHOLDS.get(kind, 100)
        if float(row.get("attention_score") or 0) < threshold:
            errors.append(f"{kind} item below now threshold: {row.get('title')}")
    metrics = {
        "attention_items": len(items),
        "now": len(now_rows),
        "later": sum(row.get("priority") == "later" for row in items),
        "ignored": sum(row.get("priority") == "ignore" for row in items),
        "needs": len(payload.get("needs") or []),
        "watchlist": len(payload.get("watchlist") or []),
    }
    return {"passed": not errors, "errors": errors, "warnings": warnings, "metrics": metrics}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "data" / "needs.json"))
    parser.add_argument("--status", default=str(ROOT / "data" / "last_run.json"))
    parser.add_argument("--report", default=str(ROOT / "reports" / "quality-gate.json"))
    parser.add_argument("--max-age-hours", type=int, default=36)
    args = parser.parse_args()
    result = evaluate(read_json(args.data), read_json(args.status), args.max_age_hours)
    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
