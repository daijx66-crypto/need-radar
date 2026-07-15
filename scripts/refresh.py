#!/usr/bin/env python3
"""Run collectors, score signals, and record an honest machine-readable status.

`NEED_RADAR_MODE=github` skips collectors that need a local browser session or
use a fragile browser-facing endpoint. A collector that exits zero but writes an
empty feed is recorded as `empty`, never as a successful source.
"""
import datetime
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
LAST_RUN = ROOT / "data" / "last_run.json"
NEEDS = ROOT / "data" / "needs.json"
MODE = os.environ.get("NEED_RADAR_MODE", "local").strip().lower()
LOCAL_ONLY = {
    "opencli_douyin",
    "opencli_tiktok",
    "opencli_twitter",
    "opencli_xiaohongshu",
}
# This endpoint currently relies on browser-like anti-risk workarounds and is
# intentionally not part of the reproducible public runner.
GITHUB_DISABLED = LOCAL_ONLY | {"bilibili"}
DEFAULT_REQUIRED = {
    "github": {"aihot", "hackernews", "stackexchange"},
    "local": {"aihot", "hackernews", "stackexchange"},
}


def iso_now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")


def clock():
    return datetime.datetime.now().strftime("%H:%M:%S")


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def collector_paths():
    paths = [Path(p) for p in sorted(glob.glob(str(ROOT / "collectors" / "*.py")))
             if not Path(p).name.startswith("_")]
    if MODE == "github":
        paths = [p for p in paths if p.stem not in GITHUB_DISABLED]
    return paths


def required_sources():
    raw = os.environ.get("NEED_RADAR_REQUIRED_SOURCES", "").strip()
    return {item.strip() for item in raw.split(",") if item.strip()} if raw else DEFAULT_REQUIRED.get(MODE, set())


def tail_text(value, limit=400):
    clean = (value or "").strip()
    return clean[-limit:]


def run_process(label, relpath, timeout=200, print_status=True):
    # Wall-clock time can jump when the OS synchronizes its clock. Duration and
    # timeout reporting must use a monotonic clock.
    started = time.monotonic()
    try:
        result = subprocess.run(
            [sys.executable, str(relpath)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        seconds = round(time.monotonic() - started, 1)
        status = "success" if result.returncode == 0 else "failed"
        record = {
            "label": label,
            "status": status,
            "ok": status == "success",
            "returncode": result.returncode,
            "secs": seconds,
            "tail": tail_text(result.stdout, 240),
            "err": tail_text(result.stderr),
        }
    except subprocess.TimeoutExpired as exc:
        record = {
            "label": label,
            "status": "failed",
            "ok": False,
            "returncode": None,
            "secs": timeout,
            "tail": tail_text(exc.stdout, 240),
            "err": "timeout",
        }
    if print_status:
        print(f"  [{clock()}] {label:<18} {record['status']:<7} {record['secs']:5.0f}s  {record['tail'][-78:]}")
    return record


def run_collector(path):
    raw_path = RAW_DIR / f"{path.stem}.json"
    before_mtime = raw_path.stat().st_mtime_ns if raw_path.exists() else None
    record = run_process(path.stem, path.relative_to(ROOT), print_status=False)
    after_mtime = raw_path.stat().st_mtime_ns if raw_path.exists() else None
    raw = read_json(raw_path)
    record = classify_collector(record, raw, produced=after_mtime is not None and after_mtime != before_mtime)
    print(f"  [{clock()}] {path.stem:<18} {record['status']:<7} {record['secs']:5.0f}s  {record['tail'][-78:]}")
    return record


def classify_collector(record, raw, produced=True):
    record = dict(record)
    count = int((raw or {}).get("count") or 0)
    record["count"] = count
    record["generated_at"] = (raw or {}).get("generated_at") or ""
    if record["status"] == "success" and not produced:
        record["status"] = "failed"
        record["ok"] = False
        record["err"] = "collector exited zero without producing a fresh raw file"
    elif record["status"] == "success" and count == 0:
        record["status"] = "empty"
        record["ok"] = False
    return record


def overall_status(score, generated_at, nonempty, failed, missing_required):
    if score.get("status") != "success" or not generated_at:
        return "failed"
    if not nonempty:
        return "failed"
    if failed or missing_required:
        return "degraded"
    return "success"


def skipped_collectors():
    if MODE != "github":
        return []
    return [{
        "label": name,
        "status": "skipped",
        "ok": False,
        "count": 0,
        "secs": 0,
        "tail": "",
        "err": "requires local browser/session or is not suitable for the public runner",
    } for name in sorted(GITHUB_DISABLED)]


def main():
    started_at = iso_now()
    paths = collector_paths()
    print(f"=== 需求雷达刷新 {started_at} · mode={MODE} ===")
    print(f"采集 {len(paths)} 个可运行源…")
    collectors = [run_collector(path) for path in paths] + skipped_collectors()

    print("打分…")
    score = run_process("score", Path("scorer") / "score.py", timeout=180)
    llm = {"label": "enrich_llm", "status": "skipped", "ok": False, "reason": "no API key"}
    if os.environ.get("ANTHROPIC_API_KEY") and (ROOT / "scorer" / "enrich_llm.py").exists():
        print("LLM 增强（显式检测到本地 ANTHROPIC_API_KEY）…")
        llm = run_process("enrich_llm", Path("scorer") / "enrich_llm.py", timeout=600)

    payload = read_json(NEEDS) or {}
    generated_at = payload.get("generated_at") or ""
    needs_count = len(payload.get("needs") or [])
    nonempty = {row["label"] for row in collectors if row["status"] == "success" and row.get("count", 0) > 0}
    required = required_sources()
    missing_required = sorted(required - nonempty)
    failed = [row["label"] for row in collectors if row["status"] == "failed"]
    empty = [row["label"] for row in collectors if row["status"] == "empty"]

    overall = overall_status(score, generated_at, nonempty, failed, missing_required)

    log = {
        "schema_version": 2,
        "mode": MODE,
        "status": overall,
        "started_at": started_at,
        "finished_at": iso_now(),
        "generated_at": generated_at,
        "collectors": collectors,
        "score": score,
        "llm": llm,
        "needs": needs_count,
        "required_sources": sorted(required),
        "missing_required_sources": missing_required,
        "failed_sources": failed,
        "empty_sources": empty,
        "successful_sources": sorted(nonempty),
    }
    atomic_json(LAST_RUN, log)
    print(
        f"=== {overall.upper()}：{len(nonempty)}/{len(paths)} 源有数据 · "
        f"{needs_count} 条需求 -> data/needs.json ==="
    )
    if overall == "failed":
        raise SystemExit(1)
    if overall == "degraded" and os.environ.get("NEED_RADAR_FAIL_ON_DEGRADED") == "1":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
