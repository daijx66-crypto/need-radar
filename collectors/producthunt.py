#!/usr/bin/env python3
# Product Hunt official Atom feed（无需 key）。作为 A 类商业/发布上下文，不直接等价于购买理由。
import html
import os
import re
import sys
from xml.etree import ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import http_get, write_raw, mk_signal, extract_keywords  # noqa


SOURCE = "producthunt"
FEED_URL = os.environ.get("NEED_RADAR_PRODUCTHUNT_FEED", "https://www.producthunt.com/feed")
LIMIT = int(os.environ.get("NEED_RADAR_PRODUCTHUNT_LIMIT", "40"))
ATOM = {"a": "http://www.w3.org/2005/Atom"}


def clean_html(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r'\s*"?\s*Discussion\s*\|\s*Link\s*$', "", value, flags=re.I)
    value = re.sub(r"\s*View on Product Hunt\s*$", "", value, flags=re.I)
    return value.strip().strip('"').strip()


def entry_text(entry):
    content = entry.findtext("a:content", default="", namespaces=ATOM)
    return clean_html(content)


def entry_link(entry):
    for link in entry.findall("a:link", ATOM):
        if link.attrib.get("rel") in ("alternate", None, ""):
            return link.attrib.get("href", "")
    return ""


def entry_id(entry, url, title):
    raw = entry.findtext("a:id", default="", namespaces=ATOM) or url or title
    m = re.search(r"Post/(\d+)", raw)
    return m.group(1) if m else re.sub(r"[^0-9A-Za-z]+", "-", raw).strip("-")[:80]


def parse_feed(raw, limit=LIMIT):
    root = ET.fromstring(raw)
    signals = []
    for idx, entry in enumerate(root.findall("a:entry", ATOM)[:limit], start=1):
        title = clean_html(entry.findtext("a:title", default="", namespaces=ATOM))
        if not title:
            continue
        url = entry_link(entry)
        text = entry_text(entry)
        native_id = entry_id(entry, url, title)
        popularity = max(1, 120 - idx * 3)
        signals.append(mk_signal(
            id=f"{SOURCE}-{native_id}",
            source=SOURCE,
            source_label="Product Hunt",
            region="海外",
            lang="en",
            title=title,
            text=text[:600],
            url=url,
            popularity=popularity,
            comments=0,
            created_at=entry.findtext("a:updated", default="", namespaces=ATOM)
            or entry.findtext("a:published", default="", namespaces=ATOM),
            signal_type="launch",
            keywords=extract_keywords(f"{title} {text}", "en"),
        ))
    return signals


def run():
    try:
        raw = http_get(FEED_URL, timeout=15, retries=1, headers={"Accept": "application/atom+xml, application/xml, text/xml"})
        signals = parse_feed(raw)
    except Exception as e:
        print(f"[producthunt] feed fail: {e}")
        signals = []
    write_raw(SOURCE, signals)


if __name__ == "__main__":
    run()
