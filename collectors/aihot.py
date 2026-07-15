#!/usr/bin/env python3
"""AI HOT public selected feed + current hot topics.

This collector follows AI HOT's public read-only contract: recognizable
non-browser UA, no credentials, permalink-first display, retained attribution,
and a lightweight fingerprint check before downloading full content.
"""
import datetime
import json
import os
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import extract_keywords, get_json, mk_signal, write_raw  # noqa: E402


SOURCE = "aihot"
API_ROOT = os.environ.get("NEED_RADAR_AIHOT_ROOT", "https://aihot.virxact.com/api/public").rstrip("/")
LIMIT = max(1, min(100, int(os.environ.get("NEED_RADAR_AIHOT_LIMIT", "50"))))
UA = "aihot-skill/0.3.6 (+https://aihot.virxact.com/aihot-skill/) need-radar/0.3"
STATE_PATH = Path(__file__).resolve().parents[1] / "data" / "cache" / "aihot_state.json"


def _text(value):
    return str(value or "").strip()


def parse_items(payload):
    signals = []
    canonical = _text(payload.get("canonical"))
    for rank, item in enumerate(payload.get("items") or [], start=1):
        if not item.get("selected", True):
            continue
        title = _text(item.get("title") or item.get("title_en"))
        permalink = _text(item.get("permalink"))
        original_url = _text(item.get("url"))
        display_url = permalink or original_url
        if not title or not display_url:
            continue
        summary = _text(item.get("summary"))
        external_source = _text(item.get("source")) or "AI HOT"
        score = item.get("score")
        signals.append(mk_signal(
            id=f"{SOURCE}-{item.get('id') or display_url}",
            source=SOURCE,
            source_label="AI HOT",
            region="通用",
            lang="zh",
            title=title,
            text=summary[:1000],
            url=display_url,
            original_url=original_url,
            popularity=int(score or 0),
            comments=0,
            created_at=_text(item.get("publishedAt")),
            signal_type="trend",
            keywords=extract_keywords(f"{title} {summary}", "zh"),
            content_kind="shift",
            category=_text(item.get("category")) or "industry",
            external_score=float(score) if score is not None else max(55, 78 - rank),
            source_rank=rank,
            permalink=permalink,
            external_source=external_source,
            attribution="AI HOT",
            canonical=canonical,
            feed_kind="selected",
        ))
    return signals


def parse_hot_topics(payload):
    signals = []
    canonical = _text(payload.get("canonical"))
    for rank, item in enumerate(payload.get("items") or [], start=1):
        title = _text(item.get("title"))
        permalink = _text(item.get("permalink"))
        original_url = _text(item.get("url"))
        display_url = permalink or original_url
        if not title or not display_url:
            continue
        source_count = int(item.get("sourceCount") or 0)
        signal_count = int(item.get("signalCount") or 0)
        summary = f"{source_count} 个独立信源正在集中讨论"
        if signal_count:
            summary += f"，合并 {signal_count} 条信号"
        summary += "。"
        signals.append(mk_signal(
            id=f"{SOURCE}-hot-{item.get('id') or display_url}",
            source=SOURCE,
            source_label="AI HOT",
            region="通用",
            lang="zh",
            title=title,
            text=summary,
            url=display_url,
            original_url=original_url,
            popularity=source_count,
            comments=0,
            created_at=_text(item.get("latestAt")),
            signal_type="trend",
            keywords=extract_keywords(title, "zh"),
            content_kind="shift",
            category="hot-topic",
            external_score=max(68, 91 - (rank - 1) * 4),
            source_rank=rank,
            source_count=source_count,
            signal_count=signal_count,
            permalink=permalink,
            external_source=_text(item.get("source")) or "AI HOT",
            attribution="AI HOT",
            canonical=canonical,
            feed_kind="hot-topics",
        ))
    return signals


def _load_state():
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_state(payload):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = STATE_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, STATE_PATH)


def run():
    state = _load_state()
    fingerprint = {}
    try:
        # A version failure must not block a content refresh.
        version = get_json(f"{API_ROOT}/version", timeout=10, retries=0, headers={"User-Agent": UA})
        state["api_version"] = version.get("apiVersion")
        state["skill_version"] = version.get("skillVersion")
    except Exception:
        pass
    try:
        fingerprint = get_json(f"{API_ROOT}/fingerprint", timeout=12, retries=1, headers={"User-Agent": UA})
    except Exception:
        pass

    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=48)).isoformat(timespec="seconds")
    query = urllib.parse.urlencode({"mode": "selected", "since": since, "take": LIMIT})
    signals = []
    errors = []
    try:
        signals.extend(parse_items(get_json(
            f"{API_ROOT}/items?{query}", timeout=20, retries=1, headers={"User-Agent": UA}
        )))
    except Exception as exc:
        errors.append(f"selected: {exc}")
    try:
        signals.extend(parse_hot_topics(get_json(
            f"{API_ROOT}/hot-topics", timeout=20, retries=1, headers={"User-Agent": UA}
        )))
    except Exception as exc:
        errors.append(f"hot-topics: {exc}")

    # A hot topic can also be selected; the AI HOT item permalink is the stable
    # dedupe key, so keep the richer/hotter representation only once.
    deduped = {}
    for signal in signals:
        key = signal.get("permalink") or signal.get("url") or signal.get("id")
        old = deduped.get(key)
        if old is None or float(signal.get("external_score") or 0) > float(old.get("external_score") or 0):
            deduped[key] = signal
    output = list(deduped.values())
    if not output and errors:
        print("[aihot] " + " | ".join(errors))
    if fingerprint:
        state["fingerprint"] = fingerprint
    state["errors"] = errors
    _save_state(state)
    write_raw(SOURCE, output)


if __name__ == "__main__":
    run()
