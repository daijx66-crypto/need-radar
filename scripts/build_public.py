#!/usr/bin/env python3
"""Build an allowlisted, sanitized GitHub Pages artifact and public data set."""
import argparse
import copy
import datetime
import json
import os
import re
import shutil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parents[1]
EMAIL = re.compile(r"(?<![\w.-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])", re.I)
SECRET = re.compile(r"(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
LOCAL_PATH = re.compile(r"(?:/Users/[^\s]+|/home/[^\s]+|[A-Za-z]:\\Users\\[^\s]+)")
TRACKING = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "fbclid", "gclid"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def clean_url(value):
    if not value:
        return ""
    parts = urlsplit(str(value).strip())
    if parts.scheme not in ("http", "https"):
        return ""
    query = [(key, val) for key, val in parse_qsl(parts.query, keep_blank_values=True) if key.lower() not in TRACKING]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def clean_text(value, limit=500):
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    text = EMAIL.sub("[redacted-email]", text)
    text = SECRET.sub("[redacted-secret]", text)
    text = LOCAL_PATH.sub("[redacted-local-path]", text)
    return text[:limit]


def take(source, keys):
    return {key: copy.deepcopy(source[key]) for key in keys if key in source}


def sanitize_evidence(row):
    return {
        "title": clean_text(row.get("title"), 180),
        "url": clean_url(row.get("url")),
        "source_label": clean_text(row.get("source_label"), 80),
        "popularity": int(row.get("popularity") or 0),
        "created_at": clean_text(row.get("created_at"), 64),
        "source_tier": clean_text(row.get("source_tier"), 8),
        "source_tier_label": clean_text(row.get("source_tier_label"), 40),
    }


def sanitize_need(row):
    result = take(row, (
        "id", "stable_id", "region", "sources", "source_tiers", "source_tier_labels",
        "signal_count", "demand_score", "opportunity", "product_forms", "verdict_label",
    ))
    result["title"] = clean_text(row.get("title"), 180)
    result["summary"] = clean_text(row.get("summary"), 360)
    result["recommendation"] = clean_text(row.get("recommendation"), 360)
    result["evidence"] = [sanitize_evidence(item) for item in (row.get("evidence") or [])[:5]]
    if result.get("opportunity"):
        result["opportunity"] = {key: clean_text(value, 360) for key, value in result["opportunity"].items()}
    if result.get("product_forms"):
        result["product_forms"] = [
            {key: clean_text(value, 240) if isinstance(value, str) else value for key, value in item.items()}
            for item in result["product_forms"][:4]
        ]
    return result


def sanitize_watch(row):
    result = take(row, (
        "id", "stable_id", "region", "popularity", "comments", "signal_type", "gate",
        "intent_type", "noise_type", "source_tier", "source_tier_label",
    ))
    for key, limit in (("title", 180), ("summary", 360), ("source", 60), ("source_label", 80), ("reason", 240)):
        result[key] = clean_text(row.get(key), limit)
    result["url"] = clean_url(row.get("url"))
    return result


def sanitize_attention_item(row):
    result = take(row, (
        "stable_id", "need_id", "kind", "priority", "published_at", "category",
        "source_score", "evidence_count", "region", "author", "attribution", "is_new",
        "streak_days", "score_delta", "evidence_delta", "attention_score", "rank",
        "rank_delta", "change_label", "age_hours", "is_stale",
    ))
    for key, limit in (("title", 180), ("summary", 420), ("source", 80), ("why_now", 240), ("why_ignore", 240)):
        result[key] = clean_text(row.get(key), limit)
    result["url"] = clean_url(row.get("url"))
    result["permalink"] = clean_url(row.get("permalink"))
    return result


def sanitize_payload(payload):
    meta = payload.get("meta") or {}
    safe_meta = take(meta, (
        "signals", "candidates", "clusters", "needs", "watchlist", "weights", "mode", "stage",
        "gate_counts", "noise_counts", "source_tier_counts", "source_tier_labels",
    ))
    attention = payload.get("attention") or {}
    return {
        "schema_version": 2,
        "generated_at": clean_text(payload.get("generated_at"), 64),
        "source_stats": {clean_text(key, 80): int(value or 0) for key, value in (payload.get("source_stats") or {}).items()},
        "meta": safe_meta,
        "needs": [sanitize_need(row) for row in (payload.get("needs") or [])],
        "watchlist": [sanitize_watch(row) for row in (payload.get("watchlist") or [])],
        "attention": {
            "generated_at": clean_text(attention.get("generated_at"), 64),
            "limits": attention.get("limits") or {},
            "summary": attention.get("summary") or {},
            "items": [sanitize_attention_item(row) for row in (attention.get("items") or [])],
        },
        "history": take(payload.get("history") or {}, ("current_date", "previous_date", "has_previous", "snapshot_path")),
        "public_notice": "Sanitized derived data. Third-party material belongs to its original publishers.",
    }


def sanitize_status(status):
    collectors = [{
        "label": clean_text(row.get("label"), 60),
        "status": clean_text(row.get("status"), 20),
        "count": int(row.get("count") or 0),
        "secs": float(row.get("secs") or 0),
    } for row in (status.get("collectors") or [])]
    return {
        "schema_version": 2,
        "mode": clean_text(status.get("mode"), 20),
        "status": clean_text(status.get("status"), 20),
        "started_at": clean_text(status.get("started_at"), 64),
        "finished_at": clean_text(status.get("finished_at"), 64),
        "generated_at": clean_text(status.get("generated_at"), 64),
        "needs": int(status.get("needs") or 0),
        "collectors": collectors,
        "missing_required_sources": [clean_text(item, 60) for item in status.get("missing_required_sources") or []],
        "failed_sources": [clean_text(item, 60) for item in status.get("failed_sources") or []],
    }


def sanitize_history(source_dir, target_dir, keep_days=30):
    target_dir.mkdir(parents=True, exist_ok=True)
    files = sorted(source_dir.glob("????-??-??.json"))[-keep_days:]
    dates = []
    for path in files:
        payload = read_json(path)
        date = clean_text(payload.get("date") or path.stem, 10)
        atomic_json(target_dir / f"{date}.json", {
            "date": date,
            "generated_at": clean_text(payload.get("generated_at"), 64),
            "items": [sanitize_attention_item(row) for row in (payload.get("items") or [])],
        })
        dates.append(date)
    atomic_json(target_dir / "index.json", {"latest": dates[-1] if dates else None, "dates": dates})


def assert_public_safe(root):
    forbidden = []
    for path in root.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        if SECRET.search(text) or LOCAL_PATH.search(text) or EMAIL.search(text):
            forbidden.append(str(path.relative_to(root)))
    if forbidden:
        raise SystemExit("public sanitizer rejected forbidden values in: " + ", ".join(forbidden))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(ROOT / "dist"))
    parser.add_argument("--public-data", default=str(ROOT / "public-data"))
    parser.add_argument("--keep-days", type=int, default=30)
    parser.add_argument(
        "--write-public-data",
        action="store_true",
        help="persist sanitized data to --public-data; intended for the GitHub runner",
    )
    args = parser.parse_args()
    output = Path(args.output)
    public_data = Path(args.public_data)

    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(ROOT / "web", output)
    build_data = public_data if args.write_public_data else output / ".public-data-build"

    payload = sanitize_payload(read_json(ROOT / "data" / "needs.json"))
    status = sanitize_status(read_json(ROOT / "data" / "last_run.json"))
    atomic_json(build_data / "needs.json", payload)
    atomic_json(build_data / "status.json", status)
    sanitize_history(ROOT / "data" / "history", build_data / "history", max(1, args.keep_days))
    assert_public_safe(build_data)

    (output / "data").mkdir(parents=True, exist_ok=True)
    shutil.copy2(build_data / "needs.json", output / "data" / "needs.json")
    shutil.copy2(build_data / "status.json", output / "data" / "status.json")
    shutil.copytree(build_data / "history", output / "data" / "history")
    if not args.write_public_data:
        shutil.rmtree(build_data)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    assert_public_safe(output)
    print(f"public build: {output} · {len(payload['attention']['items'])} attention items")


if __name__ == "__main__":
    main()
