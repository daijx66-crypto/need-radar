"""注意力分层、稳定 ID 与每日快照。只改变展示优先级，不改变原始评分。"""
import copy
import datetime
import hashlib
import json
import math
import os
import re
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


DEFAULT_ATTENTION = {
    "focus_keywords": [],
    "deprioritize_keywords": [],
    "preferred_sources": [],
    "now_limit": 5,
    "later_limit": 8,
    "now_thresholds": {"need": 60, "shift": 68, "builder": 68},
    "later_thresholds": {"need": 50, "shift": 55, "builder": 55},
    "max_age_hours": {"need": 336, "shift": 96, "builder": 168},
    "now_kind_limits": {"need": 3, "shift": 3, "builder": 1},
    "later_kind_limits": {"need": 3, "shift": 4, "builder": 3},
}


def _now():
    return datetime.datetime.now(datetime.timezone.utc).astimezone()


def _as_datetime(value=None):
    if value is None:
        return _now()
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime.combine(value, datetime.time(), tzinfo=datetime.timezone.utc)
    return datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def _parse_datetime(value):
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def _age_hours(published_at, current_time):
    parsed = _parse_datetime(published_at)
    if not parsed:
        return None
    current = current_time
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    delta = current.astimezone(datetime.timezone.utc) - parsed.astimezone(datetime.timezone.utc)
    return max(0, round(delta.total_seconds() / 3600, 1))


def canonical_url(url):
    value = (url or "").strip()
    if not value:
        return ""
    parts = urlsplit(value)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def stable_id(kind, url, title, source):
    canonical = canonical_url(url)
    fallback = re.sub(r"\s+", " ", f"{source} {title}".lower()).strip()
    digest = hashlib.sha1(f"{kind}|{canonical or fallback}".encode("utf-8")).hexdigest()[:16]
    return f"{kind}-{digest}"


def _profile_attention(profile):
    merged = copy.deepcopy(DEFAULT_ATTENTION)
    merged.update((profile or {}).get("attention") or {})
    merged["now_limit"] = max(0, int(merged.get("now_limit") or 0))
    merged["later_limit"] = max(0, int(merged.get("later_limit") or 0))
    for key in ("now_thresholds", "later_thresholds", "max_age_hours"):
        base = copy.deepcopy(DEFAULT_ATTENTION[key])
        base.update(merged.get(key) or {})
        merged[key] = {kind: max(0, float(value)) for kind, value in base.items()}
    for key in ("now_kind_limits", "later_kind_limits"):
        base = copy.deepcopy(DEFAULT_ATTENTION[key])
        base.update(merged.get(key) or {})
        merged[key] = {kind: max(0, int(value)) for kind, value in base.items()}
    return merged


def _need_item(need, as_of):
    evidence = need.get("evidence") or []
    url = next((row.get("url") for row in evidence if row.get("url")), "")
    source = (need.get("sources") or [""])[0]
    title = need.get("title") or "(无标题需求)"
    score = float((need.get("demand_score") or {}).get("total") or 0)
    dated_evidence = [row.get("created_at") for row in evidence if _parse_datetime(row.get("created_at"))]
    published_at = max(dated_evidence, key=lambda value: _parse_datetime(value)) if dated_evidence else ""
    return {
        "stable_id": stable_id("need", url, title, source),
        "need_id": need.get("id") or "",
        "kind": "need",
        "title": title,
        "summary": (need.get("opportunity") or {}).get("purchase_reason") or need.get("summary") or "",
        "source": source,
        "url": url,
        "permalink": "",
        "published_at": published_at,
        "category": "product-opportunity",
        "source_score": round(score, 1),
        "evidence_count": max(len(evidence), int(need.get("signal_count") or 0)),
        "region": need.get("region") or "通用",
        "verdict_label": need.get("verdict_label") or "",
    }


def _signal_kind(signal):
    explicit = signal.get("content_kind")
    if explicit in ("shift", "builder"):
        return explicit
    gate = signal.get("_gate") or {}
    if gate.get("source_tier") == "C" and signal.get("signal_type") in ("trend", "launch", "ranking"):
        return "shift"
    return ""


def _signal_item(signal):
    kind = _signal_kind(signal)
    if not kind:
        return None
    title = signal.get("title") or "(无标题动态)"
    source = signal.get("source_label") or signal.get("source") or ""
    url = signal.get("url") or ""
    popularity = float(signal.get("popularity") or 0)
    external_score = signal.get("external_score")
    if external_score is None:
        if kind == "builder":
            external_score = 55 + min(25, popularity / 4)
        else:
            external_score = 45 + min(18, math.log10(popularity + 1) * 5)
    return {
        "stable_id": stable_id(kind, url, title, source),
        "need_id": "",
        "kind": kind,
        "title": title,
        "summary": signal.get("text") or "",
        "source": source,
        "url": url,
        "permalink": signal.get("permalink") or "",
        "published_at": signal.get("created_at") or "",
        "category": signal.get("category") or ("builder" if kind == "builder" else "industry"),
        "source_score": round(float(external_score or 0), 1),
        "evidence_count": 1 if url else 0,
        "region": signal.get("region") or "通用",
        "author": signal.get("author") or "",
        "attribution": signal.get("attribution") or source,
    }


def _personalization(item, settings):
    text = f"{item['title']} {item['summary']} {item['category']}".lower()
    focus = sum(1 for word in settings["focus_keywords"] if str(word).lower() in text)
    down = sum(1 for word in settings["deprioritize_keywords"] if str(word).lower() in text)
    source_bonus = 5 if item["source"] in settings["preferred_sources"] else 0
    return min(12, focus * 4) - min(30, down * 15) + source_bonus


def _why(item):
    if item["kind"] == "need":
        return "出现了有购买理由和原始证据的需求，值得优先判断是否验证。"
    if item["kind"] == "builder":
        return "来自精选建造者或官方来源，可能包含可复用的实践和判断。"
    return "这是可能改变产品判断的重要变化，但它本身不等于真实需求。"


def build_attention(needs, signals, profile, previous=None, as_of=None):
    current_time = _as_datetime(as_of)
    settings = _profile_attention(profile)
    candidates = [_need_item(need, current_time) for need in (needs or [])]
    candidates.extend(item for item in (_signal_item(sig) for sig in (signals or [])) if item)

    deduped = {}
    for item in candidates:
        old = deduped.get(item["stable_id"])
        if old is None or item["source_score"] > old["source_score"]:
            deduped[item["stable_id"]] = item
    items = list(deduped.values())

    previous_map = {row.get("stable_id"): row for row in (previous or {}).get("items", [])}
    has_previous = previous is not None
    previous_date = None
    if previous and previous.get("date"):
        try:
            previous_date = datetime.date.fromisoformat(previous["date"])
        except ValueError:
            previous_date = None
    is_consecutive_snapshot = previous_date == current_time.date() - datetime.timedelta(days=1)
    for item in items:
        old = previous_map.get(item["stable_id"])
        item["is_new"] = bool(has_previous and old is None)
        item["streak_days"] = int(old.get("streak_days") or 1) + 1 if old and is_consecutive_snapshot else 1
        item["score_delta"] = round(item["source_score"] - float(old.get("source_score") or 0), 1) if old else None
        item["evidence_delta"] = item["evidence_count"] - int(old.get("evidence_count") or 0) if old else None
        item["attention_score"] = round(max(0, min(100, item["source_score"] + _personalization(item, settings) + (2 if item["is_new"] else 0))), 1)
        item["age_hours"] = _age_hours(item.get("published_at"), current_time)
        max_age = settings["max_age_hours"].get(item["kind"], 0)
        item["is_stale"] = item["age_hours"] is None or item["age_hours"] > max_age
        item["why_now"] = _why(item)
        item["why_ignore"] = ""

    items.sort(key=lambda row: (0 if row["url"] else 1, -row["attention_score"], row["stable_id"]))
    for rank, item in enumerate(items, start=1):
        item["rank"] = rank
        old = previous_map.get(item["stable_id"])
        item["rank_delta"] = int(old.get("rank") or 0) - rank if old else None
        if not has_previous:
            item["change_label"] = "首份快照"
        elif item["is_new"]:
            item["change_label"] = "今日新增"
        elif item["rank_delta"] and item["rank_delta"] > 0:
            item["change_label"] = f"上升 {item['rank_delta']}"
        elif item["streak_days"] >= 3:
            item["change_label"] = f"连续 {item['streak_days']} 天"
        elif item["score_delta"] and item["score_delta"] > 0:
            item["change_label"] = f"分数 +{item['score_delta']:g}"
        else:
            item["change_label"] = "持续关注"

    eligible_now = [item for item in items if (
        item["url"]
        and not item["is_stale"]
        and item["attention_score"] >= settings["now_thresholds"].get(item["kind"], 100)
    )]
    now_ids = []
    now_kind_counts = {kind: 0 for kind in settings["now_kind_limits"]}
    for item in eligible_now:
        if len(now_ids) >= settings["now_limit"]:
            break
        kind = item["kind"]
        if now_kind_counts.get(kind, 0) >= settings["now_kind_limits"].get(kind, 0):
            continue
        now_ids.append(item["stable_id"])
        now_kind_counts[kind] = now_kind_counts.get(kind, 0) + 1

    later_used = 0
    later_kind_counts = {kind: 0 for kind in settings["later_kind_limits"]}
    for item in items:
        later_threshold = settings["later_thresholds"].get(item["kind"], 100)
        if not item["url"]:
            item["priority"] = "ignore"
            item["why_ignore"] = "缺少原始链接，无法验证，已从注意力清单下沉。"
        elif item["is_stale"]:
            item["priority"] = "ignore"
            item["why_ignore"] = "信号已超出该类型的新鲜度窗口，不再占用今日注意力。"
        elif item["stable_id"] in now_ids:
            item["priority"] = "now"
        elif (
            item["attention_score"] >= later_threshold
            and later_used < settings["later_limit"]
            and later_kind_counts.get(item["kind"], 0) < settings["later_kind_limits"].get(item["kind"], 0)
        ):
            item["priority"] = "later"
            later_used += 1
            later_kind_counts[item["kind"]] = later_kind_counts.get(item["kind"], 0) + 1
        else:
            item["priority"] = "ignore"
            item["why_ignore"] = "未达到今日质量阈值或注意力预算，可在需要时再展开。"

    priority_order = {"now": 0, "later": 1, "ignore": 2}
    items.sort(key=lambda row: (priority_order[row["priority"]], row["rank"]))
    summary = {
        "now": sum(row["priority"] == "now" for row in items),
        "later": sum(row["priority"] == "later" for row in items),
        "ignore": sum(row["priority"] == "ignore" for row in items),
        "new": sum(row["is_new"] for row in items),
        "need": sum(row["kind"] == "need" for row in items),
        "shift": sum(row["kind"] == "shift" for row in items),
        "builder": sum(row["kind"] == "builder" for row in items),
    }
    return {
        "generated_at": current_time.isoformat(timespec="seconds"),
        "limits": {"now": settings["now_limit"], "later": settings["later_limit"]},
        "summary": summary,
        "items": items,
    }


def load_previous_snapshot(history_dir, as_of=None):
    current_date = _as_datetime(as_of).date().isoformat()
    root = Path(history_dir)
    if not root.exists():
        return None
    for path in sorted(root.glob("????-??-??.json"), reverse=True):
        if path.stem >= current_date:
            continue
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _atomic_json(path, payload):
    path = Path(path)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(temp, path)


def save_snapshot(attention, history_dir, as_of=None):
    current_time = _as_datetime(as_of or attention.get("generated_at"))
    date = current_time.date().isoformat()
    root = Path(history_dir)
    root.mkdir(parents=True, exist_ok=True)
    previous = load_previous_snapshot(root, current_time)
    snapshot = {"date": date, "generated_at": attention.get("generated_at") or current_time.isoformat(), "items": attention.get("items", [])}
    _atomic_json(root / f"{date}.json", snapshot)

    dates = sorted(path.stem for path in root.glob("????-??-??.json"))
    _atomic_json(root / "index.json", {"latest": date, "dates": dates})
    return {
        "current_date": date,
        "previous_date": previous.get("date") if previous else None,
        "has_previous": previous is not None,
        "snapshot_path": f"data/history/{date}.json",
    }
