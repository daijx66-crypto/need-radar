# collectors/v2ex.py — V2EX（热门 + 最新，免登录纯 JSON）
# 信号类型：detect_signal_type（V2EX 大量"求推荐/吐槽/有没有"→ question/complaint）
import sys, os, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

FEEDS = [
    "https://www.v2ex.com/api/topics/hot.json",
    "https://www.v2ex.com/api/topics/latest.json",
]

def unix_to_iso(ts):
    try:
        ts = int(ts)
        if ts <= 0:
            return ""
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    except Exception:
        return ""

def run():
    seen = {}
    for url in FEEDS:
        try:
            topics = get_json(url)
        except Exception as e:
            print("  v2ex feed fail:", url, e)
            time.sleep(0.5)
            continue
        for t in topics or []:
            tid = t.get("id")
            title = (t.get("title") or "").strip()
            if not tid or tid in seen or not title:
                continue
            text = (t.get("content") or "").strip()[:500]
            replies = int(t.get("replies") or 0)
            created_at = unix_to_iso(t.get("last_touched") or t.get("created") or 0)
            stype = detect_signal_type(title, text, "discussion")
            seen[tid] = mk_signal(
                id=f"v2ex-{tid}", source="v2ex", source_label="V2EX",
                region="国内", lang="zh", title=title, text=text,
                url=t.get("url") or f"https://www.v2ex.com/t/{tid}",
                popularity=replies, comments=replies,
                created_at=created_at, signal_type=stype,
                keywords=extract_keywords(title + " " + text, "zh"))
        time.sleep(0.5)
    write_raw("v2ex", list(seen.values()))

if __name__ == "__main__":
    run()
