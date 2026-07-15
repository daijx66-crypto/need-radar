#!/usr/bin/env python3
# GitHub Trending public page（无需 key）。作为 C 类技术趋势注释，不单独证明购买理由。
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import http_get, write_raw, mk_signal, extract_keywords  # noqa


SOURCE = "github_trending"
URL = os.environ.get("NEED_RADAR_GITHUB_TRENDING_URL", "https://github.com/trending?since=daily")
LIMIT = int(os.environ.get("NEED_RADAR_GITHUB_TRENDING_LIMIT", "30"))


def clean(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def parse_int(value):
    m = re.search(r"[\d,]+", value or "")
    return int(m.group(0).replace(",", "")) if m else 0


def article_blocks(raw):
    text = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    return re.findall(r'<article class="Box-row">(.*?)</article>', text, flags=re.S)


def parse_article(block):
    link = re.search(r'<h2.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, flags=re.S)
    if not link:
        return None
    href = html.unescape(link.group(1))
    title = clean(link.group(2)).replace(" / ", "/").replace(" /", "/").replace("/ ", "/")
    if not title or title.startswith("Sponsor"):
        return None
    desc_match = re.search(r'<p[^>]+class="[^"]*color-fg-muted[^"]*"[^>]*>(.*?)</p>', block, flags=re.S)
    desc = clean(desc_match.group(1)) if desc_match else ""
    lang_match = re.search(r'<span[^>]+itemprop="programmingLanguage"[^>]*>(.*?)</span>', block, flags=re.S)
    lang = clean(lang_match.group(1)) if lang_match else ""
    today_match = re.search(r'([\d,]+)\s+stars?\s+today', clean(block), flags=re.I)
    today = parse_int(today_match.group(1)) if today_match else 0
    total_match = re.search(r'/stargazers"[^>]*>\s*([\d,]+)', block, flags=re.S)
    total = parse_int(total_match.group(1)) if total_match else 0
    repo_path = href.strip("/")
    text = desc
    if lang:
        text = f"{desc} · language={lang}".strip(" ·")
    return mk_signal(
        id=f"{SOURCE}-{repo_path.replace('/', '-')}",
        source=SOURCE,
        source_label="GitHub Trending",
        region="海外",
        lang="en",
        title=title,
        text=text[:600],
        url=f"https://github.com{href}",
        popularity=today or total,
        comments=0,
        created_at="",
        signal_type="trend",
        keywords=([lang] if lang else []) + extract_keywords(f"{title} {desc}", "en"),
    )


def parse_trending_html(raw, limit=LIMIT):
    signals = []
    seen = set()
    for block in article_blocks(raw)[:limit]:
        sig = parse_article(block)
        if not sig or sig["id"] in seen:
            continue
        seen.add(sig["id"])
        signals.append(sig)
    return signals


def run():
    try:
        raw = http_get(URL, timeout=15, retries=1, headers={"Accept": "text/html,application/xhtml+xml"})
        signals = parse_trending_html(raw)
    except Exception as e:
        print(f"[github_trending] page fail: {e}")
        signals = []
    write_raw(SOURCE, signals)


if __name__ == "__main__":
    run()
