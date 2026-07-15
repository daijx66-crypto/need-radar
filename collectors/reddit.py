# collectors/reddit.py — Reddit（top/week，best-effort）
# 数据中心 IP 常被 403/429；用户住宅 IP 多半可用。所以写好但优雅降级：
# 失败重试 1 次，单 sub 仍失败则跳过；全失败 graceful 写 0 条并打印提示，绝不崩。
# 信号类型：detect_signal_type（SaaS / IndieHackers 板大量抱怨 / 找工具 → complaint / question）。
import sys, os, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

SUBS = ["SaaS", "Entrepreneur", "indiehackers", "SideProject", "webdev"]
REDDIT_UA = {"User-Agent": "need-radar/0.1 by u/researcher"}


def unix_to_iso(ts):
    try:
        ts = int(float(ts))
        if ts <= 0:
            return ""
        return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).astimezone().isoformat(timespec="seconds")
    except Exception:
        return ""


def fetch_sub(sub):
    """取单个 sub 的 top/week；内部已重试，失败抛异常交给上层处理。"""
    url = f"https://www.reddit.com/r/{sub}/top.json?t=week&limit=25"
    # http_get 默认 retries=2（共 3 次）；这里显式再保证"重试 1 次"语义，仍带像样 UA。
    return get_json(url, headers=REDDIT_UA, retries=1)


def run():
    seen = {}
    ok_subs, blocked_subs = [], []

    for sub in SUBS:
        try:
            data = fetch_sub(sub)
        except Exception as e:
            print(f"  reddit sub fail: r/{sub} -> {e}")
            blocked_subs.append(sub)
            time.sleep(0.8)
            continue

        children = (data or {}).get("data", {}).get("children", []) if isinstance(data, dict) else []
        got = 0
        for c in children:
            d = (c or {}).get("data", {})
            pid = d.get("id")
            title = (d.get("title") or "").strip()
            if not pid or pid in seen or not title:
                continue
            text = (d.get("selftext") or "")[:500]
            permalink = d.get("permalink") or ""
            url = f"https://reddit.com{permalink}" if permalink else (d.get("url") or "")
            stype = detect_signal_type(title, text, "discussion")
            seen[pid] = mk_signal(
                id=f"reddit-{pid}", source="reddit", source_label="Reddit",
                region="海外", lang="en", title=title, text=text, url=url,
                popularity=int(d.get("ups") or 0), comments=int(d.get("num_comments") or 0),
                created_at=unix_to_iso(d.get("created_utc") or d.get("created") or 0),
                signal_type=stype,
                keywords=extract_keywords(title + " " + text, "en"))
            got += 1
        ok_subs.append(sub)
        print(f"  reddit r/{sub}: {got} posts")
        time.sleep(0.8)

    signals = list(seen.values())
    if not ok_subs and not signals:
        # 全部被挡：graceful，写 0 条，绝不崩
        print("reddit blocked from this IP, will work on user's machine")
    write_raw("reddit", signals)


if __name__ == "__main__":
    run()
