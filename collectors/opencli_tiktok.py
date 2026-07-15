#!/usr/bin/env python3
# TikTok 公开搜索（OpenCLI Browser Bridge），作为海外短视频需求/趋势补充源。
import os
import re

try:
    from . import _opencli
    from ._common import write_raw, mk_signal, detect_signal_type, extract_keywords
except ImportError:
    import _opencli
    from _common import write_raw, mk_signal, detect_signal_type, extract_keywords


SOURCE = "opencli_tiktok"
QUERIES = os.environ.get(
    "NEED_RADAR_TIKTOK_QUERIES",
    "looking for app,looking for a tool,need a tool,need an app,too expensive app,overpriced app",
).split(",")
NEEDISH_RE = re.compile(
    r"(looking for (?:a |an |the )?(?:tool|app|service|software|alternative)|"
    r"need (?:a |an )?(?:tool|app|service|software|alternative)|"
    r"is there (?:a |an )?(?:tool|app|service|software)|"
    r"wish there (?:was|were)|too expensive|overpriced|tired of|can't find|cant find)"
)
ADISH = ("last day", "limited", "% off", "download", "shop now", "sale", "tool set", "multi-tool",
         "gift", "we've got you covered", "we’ve got you covered", "make a tool", "make it yourself",
         "appbuilder", "#fyp", "#foryou")
ENTERTAINMENT = ("pokemon", "pokémon", "game", "gaming", "gameplay", "legend za", "legends za", "movie", "anime")
PRODUCT_OBJECT_RE = re.compile(r"\b(tool|app|service|software|alternative|extension|plugin|workflow|automation)\b")


def _slug(s):
    return re.sub(r"[^0-9A-Za-z]+", "-", s or "").strip("-")[:48] or "row"


def keep_row(row):
    title = (row.get("desc") or row.get("title") or "").lower()
    if any(k in title for k in ADISH) or any(k in title for k in ENTERTAINMENT):
        return False
    if ("can't find" in title or "cant find" in title) and not PRODUCT_OBJECT_RE.search(title):
        return False
    if ("overpriced" in title or "too expensive" in title) and not PRODUCT_OBJECT_RE.search(title):
        return False
    return bool(NEEDISH_RE.search(title))


def row_to_signal(row, query):
    title = (row.get("desc") or row.get("title") or "").strip() or "(no description)"
    text = f"query={query} author={row.get('author', '')} shares={row.get('shares', 0)}"
    st = detect_signal_type(title, text, default="discussion")
    if any(p in f"{query} {title}".lower() for p in ("looking for", "need a tool", "need an app", "is there")):
        st = "question"
    return mk_signal(
        id=f"{SOURCE}-{_slug(row.get('url') or title)}",
        source=SOURCE,
        source_label="TikTok",
        region="海外",
        lang="en",
        title=title[:120],
        text=text,
        url=row.get("url", ""),
        popularity=(_opencli.parse_human_count(row.get("likes"))
                    + _opencli.parse_human_count(row.get("comments")) * 5
                    + _opencli.parse_human_count(row.get("shares")) * 3),
        comments=_opencli.parse_human_count(row.get("comments")),
        created_at="",
        signal_type=st,
        keywords=extract_keywords(f"{query} {title} {text}", "en"),
    )


def main():
    if not _opencli.browser_connected():
        print("[opencli_tiktok] skip: Browser Bridge extension not connected")
        write_raw(SOURCE, [])
        return
    signals = []
    for q in [q.strip() for q in QUERIES if q.strip()]:
        try:
            rows = _opencli.run_json([
                "tiktok", "search", q, "--limit", "12", "-f", "json",
                "--window", "background", "--site-session", "persistent",
            ], timeout=70)
        except _opencli.OpenCliError as e:
            print(f"[opencli_tiktok] {q}: {e}")
            continue
        signals.extend(row_to_signal(row, q) for row in rows if isinstance(row, dict) and keep_row(row))
    write_raw(SOURCE, _opencli.dedupe(signals))


if __name__ == "__main__":
    main()
