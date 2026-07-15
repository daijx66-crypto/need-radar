#!/usr/bin/env python3
# X/Twitter 搜索与趋势（OpenCLI Browser Bridge）。复杂查询易超时，拆成短查询。
import os
import re

try:
    from . import _opencli
    from ._common import write_raw, mk_signal, detect_signal_type, extract_keywords
except ImportError:
    import _opencli
    from _common import write_raw, mk_signal, detect_signal_type, extract_keywords


SOURCE = "opencli_twitter"
QUERIES = os.environ.get(
    "NEED_RADAR_X_QUERIES",
    "need a tool lang:en,need an app lang:en,looking for app lang:en,looking for a tool lang:en,too expensive app lang:en",
).split(",")
NEEDISH_RE = re.compile(
    r"(looking for (?:a |an |the )?(?:tool|app|service|software|alternative)|"
    r"need (?:a |an )?(?:tool|app|service|software|alternative)|"
    r"is there (?:a |an )?(?:tool|app|service|software)|"
    r"wish there (?:was|were)|too expensive|overpriced|tired of|can't find|cant find)"
)
ADISH = ("introducing ", "idea:", "reselling ", "launching ", "i built", "we built",
         "chrome extension", "easiest way", "check out ")


def _slug(s):
    return re.sub(r"[^0-9A-Za-z]+", "-", s or "").strip("-")[:48] or "row"


def keep_row(row):
    text = (row.get("text") or row.get("topic") or "").lower()
    return bool(NEEDISH_RE.search(text)) and not any(k in text for k in ADISH)


def row_to_signal(row, query):
    text = row.get("text") or row.get("topic") or ""
    title = text[:110] or row.get("topic") or "(no text)"
    likes = _opencli.parse_human_count(row.get("likes"))
    retweets = _opencli.parse_human_count(row.get("retweets"))
    replies = _opencli.parse_human_count(row.get("replies"))
    popularity = likes + retweets * 3 + replies * 2
    st = detect_signal_type(title, text, default="discussion")
    if any(p in f"{query} {title}".lower() for p in ("looking for", "need a tool", "need an app", "is there")):
        st = "question"
    return mk_signal(
        id=f"{SOURCE}-{row.get('id') or _slug(row.get('url') or title)}",
        source=SOURCE,
        source_label="X/Twitter",
        region="海外",
        lang="en",
        title=title,
        text=f"query={query} author={row.get('author', '')} {text}",
        url=row.get("url", ""),
        popularity=popularity,
        comments=replies,
        created_at=row.get("created_at", ""),
        signal_type=st,
        keywords=extract_keywords(f"{query} {title} {text}", "en"),
    )


def trend_to_signal(row):
    topic = row.get("topic") or ""
    return mk_signal(
        id=f"{SOURCE}-trend-{_slug(topic)}",
        source=SOURCE,
        source_label="X/Twitter",
        region="海外",
        lang="en",
        title=topic,
        text=f"category={row.get('category', '')}",
        url="https://x.com/explore/tabs/trending",
        popularity=max(1, 100 - _opencli.parse_human_count(row.get("rank"))),
        comments=0,
        created_at="",
        signal_type="trend",
        keywords=extract_keywords(topic, "en"),
    )


def main():
    if not _opencli.browser_connected():
        print("[opencli_twitter] skip: Browser Bridge extension not connected")
        write_raw(SOURCE, [])
        return
    signals = []
    for q in [q.strip() for q in QUERIES if q.strip()]:
        try:
            rows = _opencli.run_json([
                "twitter", "search", q, "--limit", "10", "-f", "json",
                "--window", "background", "--site-session", "persistent",
            ], timeout=90)
        except _opencli.OpenCliError as e:
            print(f"[opencli_twitter] search {q}: {e}")
            continue
        signals.extend(row_to_signal(row, q) for row in rows if isinstance(row, dict) and keep_row(row))
    try:
        trends = _opencli.run_json([
            "twitter", "trending", "--limit", "12", "-f", "json",
            "--window", "background", "--site-session", "persistent",
        ], timeout=45)
        signals.extend(trend_to_signal(row) for row in trends if isinstance(row, dict))
    except _opencli.OpenCliError as e:
        print(f"[opencli_twitter] trending: {e}")
    write_raw(SOURCE, _opencli.dedupe(signals))


if __name__ == "__main__":
    main()
