#!/usr/bin/env python3
# 小红书公开搜索结果（OpenCLI Browser Bridge）。读不到浏览器桥接时优雅写 0 条。
import os
import re

try:
    from . import _opencli
    from ._common import write_raw, mk_signal, detect_signal_type, extract_keywords
except ImportError:
    import _opencli
    from _common import write_raw, mk_signal, detect_signal_type, extract_keywords


SOURCE = "opencli_xiaohongshu"
QUERIES = os.environ.get(
    "NEED_RADAR_XHS_QUERIES",
    "AI工具 太贵,AI自动化 太麻烦,Claude Code 太贵,有没有好用的AI工具,求推荐 AI工具,小红书运营 工具 求推荐",
).split(",")
NEEDISH = ("有没有", "求推荐", "求一个", "好用", "平替", "替代", "太麻烦", "太贵", "难用", "用不了", "怎么办", "不会用", "好累")
ROUNDUP = ("哪款更好", "到底哪款", "排行榜", "盘点", "合集", "测评", "必看", "收藏", "教程",
           "零基础", "整理", "清单", "分享", "免费方案", "方案来了")


def _slug(s):
    return re.sub(r"[^0-9A-Za-z一-龥]+", "-", s or "").strip("-")[:60] or "row"


def row_id(row):
    url = row.get("url") or ""
    m = re.search(r"/(?:search_result|explore)/([^?/#]+)", url)
    if m:
        return m.group(1)
    return _slug(url or row.get("title") or "")


def keep_row(row):
    title = row.get("title") or row.get("desc") or ""
    author = row.get("author") or ""
    if any(k in title for k in ROUNDUP):
        return False
    if "实战派" in author and "求推荐" not in title and "有没有" not in title:
        return False
    return any(k in title for k in NEEDISH)


def row_to_signal(row, query):
    title = row.get("title") or row.get("desc") or "(无标题)"
    url = row.get("url") or ""
    text = f"query={query} author={row.get('author', '')} published_at={row.get('published_at', '')}".strip()
    popularity = _opencli.parse_human_count(row.get("likes"))
    return mk_signal(
        id=f"{SOURCE}-{row_id(row)}",
        source=SOURCE,
        source_label="小红书",
        region="国内",
        lang="zh",
        title=title,
        text=text,
        url=url,
        popularity=popularity,
        comments=0,
        created_at=row.get("published_at", ""),
        signal_type=detect_signal_type(title, text, default="discussion"),
        keywords=extract_keywords(f"{query} {title} {text}", "zh"),
    )


def main():
    if not _opencli.browser_connected():
        print("[opencli_xiaohongshu] skip: Browser Bridge extension not connected")
        write_raw(SOURCE, [])
        return
    signals = []
    for q in [q.strip() for q in QUERIES if q.strip()]:
        try:
            rows = _opencli.run_json([
                "xiaohongshu", "search", q, "--limit", "12", "-f", "json",
                "--window", "background", "--site-session", "persistent",
            ], timeout=70)
        except _opencli.OpenCliError as e:
            print(f"[opencli_xiaohongshu] {q}: {e}")
            continue
        signals.extend(row_to_signal(row, q) for row in rows if isinstance(row, dict) and keep_row(row))
    write_raw(SOURCE, _opencli.dedupe(signals))


if __name__ == "__main__":
    main()
