# collectors/hackernews.py — Hacker News（Algolia API，无需 key）
# 信号类型：front_page / Ask HN(问题) / 含抱怨语言(complaint) / Show HN(launch)
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, write_raw, mk_signal, detect_signal_type, extract_keywords

QUERIES = ["ai", "saas", "tool", "api", "indie hacker", "automation"]

def run():
    seen = {}
    feeds = ["https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=50"]
    feeds += [f"https://hn.algolia.com/api/v1/search?tags=story&query={urlq(q)}&hitsPerPage=30" for q in QUERIES]
    feeds += ["https://hn.algolia.com/api/v1/search_by_date?tags=ask_hn&hitsPerPage=30",
              "https://hn.algolia.com/api/v1/search_by_date?tags=show_hn&hitsPerPage=20"]
    for url in feeds:
        try:
            data = get_json(url)
        except Exception as e:
            print("  hn feed fail:", e); continue
        for h in data.get("hits", []):
            oid = h.get("objectID")
            title = h.get("title") or h.get("story_title") or ""
            if not oid or oid in seen or not title:
                continue
            text = (h.get("story_text") or h.get("comment_text") or "")[:600]
            stype = detect_signal_type(title, text, "discussion")
            tl = title.lower()
            if tl.startswith("ask hn"):
                stype = "question"
            elif tl.startswith("show hn"):
                stype = "launch"
            seen[oid] = mk_signal(
                id=f"hackernews-{oid}", source="hackernews", source_label="Hacker News",
                region="海外", lang="en", title=title, text=text,
                url=h.get("url") or f"https://news.ycombinator.com/item?id={oid}",
                popularity=int(h.get("points") or 0), comments=int(h.get("num_comments") or 0),
                created_at=h.get("created_at") or "", signal_type=stype,
                keywords=extract_keywords(title + " " + text, "en"))
    write_raw("hackernews", list(seen.values()))

def urlq(s):
    import urllib.parse
    return urllib.parse.quote(s)

if __name__ == "__main__":
    run()
