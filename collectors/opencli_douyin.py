#!/usr/bin/env python3
# 抖音 OpenCLI 补充源。当前可稳定读取热点词；关键词 hashtag search 在本机返回空 JSON，先只作为泛趋势背景。
try:
    from . import _opencli
    from ._common import write_raw, mk_signal, extract_keywords
except ImportError:
    import _opencli
    from _common import write_raw, mk_signal, extract_keywords


SOURCE = "opencli_douyin"


def row_to_signal(row):
    name = row.get("name") or ""
    return mk_signal(
        id=f"{SOURCE}-{row.get('id') or name}",
        source=SOURCE,
        source_label="抖音热点",
        region="国内",
        lang="zh",
        title=name,
        text="OpenCLI douyin hashtag hot；关键词搜索当前不可用，仅作泛趋势背景。",
        url="https://www.douyin.com/hot",
        popularity=_opencli.parse_human_count(row.get("view_count")),
        comments=0,
        created_at="",
        signal_type="trend",
        keywords=extract_keywords(name, "zh"),
    )


def main():
    if not _opencli.browser_connected():
        print("[opencli_douyin] skip: Browser Bridge extension not connected")
        write_raw(SOURCE, [])
        return
    try:
        rows = _opencli.run_json([
            "douyin", "hashtag", "hot", "--keyword", "AI工具", "--limit", "20", "-f", "json",
            "--window", "background", "--site-session", "persistent",
        ], timeout=45)
    except _opencli.OpenCliError as e:
        print(f"[opencli_douyin] hot: {e}")
        rows = []
    write_raw(SOURCE, _opencli.dedupe(row_to_signal(row) for row in rows if isinstance(row, dict)))


if __name__ == "__main__":
    main()
