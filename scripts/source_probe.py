#!/usr/bin/env python3
# Probe high-signal source access paths and write a reproducible report.
import datetime
import os
import urllib.error
import urllib.request


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "reports", "source-access-matrix.md")
UA = "need-radar/0.1 (+local source access probe)"


SOURCES = [
    {
        "name": "Product Hunt",
        "state_hint": "integrated",
        "attempts": [
            {"method": "official_feed", "url": "https://www.producthunt.com/feed",
             "note": "官方 Atom feed，可免费读；已接入 collectors/producthunt.py。"},
            {"method": "official_api_docs", "url": "https://api.producthunt.com/v2/docs",
             "note": "官方 API 文档可访问，但生产查询需要 OAuth token。"},
            {"method": "graphql_without_token", "url": "https://api.producthunt.com/v2/api/graphql",
             "note": "无 token 不作为默认路径；保留给未来付费/授权模式。"},
        ],
    },
    {
        "name": "GitHub Trending",
        "state_hint": "integrated",
        "attempts": [
            {"method": "public_html", "url": "https://github.com/trending?since=daily",
             "note": "公开 HTML 页面，可免费读；已接入 collectors/github_trending.py。"},
            {"method": "official_api_search", "url": "https://api.github.com/search/repositories?q=stars:%3E1000&sort=stars&order=desc&per_page=5",
             "note": "官方 Search API 免费但有速率限制；更像总星趋势，不等价 daily trending。"},
            {"method": "rss_guess", "url": "https://github.com/trending.atom",
             "note": "GitHub 没有官方 Trending RSS；仅探测常见猜测路径。"},
        ],
    },
    {
        "name": "Chrome Web Store",
        "state_hint": "not_integrated",
        "attempts": [
            {"method": "search_page", "url": "https://chromewebstore.google.com/search/ai%20summarizer",
             "note": "搜索页可访问，但主要是前端数据，不提供稳定评论契约。"},
            {"method": "official_api_docs", "url": "https://developer.chrome.com/docs/webstore/api",
             "note": "官方 API 主要面向扩展发布/管理，不是公开评论抓取 API。"},
            {"method": "reviews_contract", "url": "https://chromewebstore.google.com/detail/nonexistent/reviews",
             "note": "评论页不是稳定 JSON/RSS 接口；不放入每日自动采集。"},
        ],
    },
    {
        "name": "Toolify",
        "state_hint": "not_integrated",
        "attempts": [
            {"method": "direct_revenue_page", "url": "https://www.toolify.ai/Best-AI-Tools-revenue",
             "note": "本机直连返回 403，不能作为稳定免费源。"},
            {"method": "rss_guess", "url": "https://www.toolify.ai/rss",
             "note": "探测常见 RSS 路径。"},
            {"method": "api_guess", "url": "https://www.toolify.ai/api",
             "note": "探测是否存在公开 API 入口。"},
        ],
    },
    {
        "name": "There Is An AI For That",
        "state_hint": "not_integrated",
        "attempts": [
            {"method": "front_page", "url": "https://theresanaiforthat.com/",
             "note": "页面可访问但体积很大，结构偏前端页面；本轮不把脆弱解析放进主链路。"},
            {"method": "sitemap", "url": "https://theresanaiforthat.com/sitemap.xml",
             "note": "探测 sitemap 是否可作为低噪声入口。"},
            {"method": "rss_guess", "url": "https://theresanaiforthat.com/rss",
             "note": "探测常见 RSS 路径。"},
        ],
    },
]


def classify_probe(ok, status, body):
    text = (body or "")[:2000].lower()
    if ok:
        if "captcha" in text or "unusual traffic" in text:
            return {"status": "captcha", "reason": "页面要求人机验证"}
        return {"status": "reachable", "reason": "可访问"}
    if status in (401, 407):
        return {"status": "needs_auth", "reason": f"HTTP {status}，需要授权"}
    if status == 403:
        return {"status": "blocked", "reason": "HTTP 403，被拒绝或反爬"}
    if status == 404:
        return {"status": "not_found", "reason": "HTTP 404，路径不存在"}
    if status:
        return {"status": "unavailable", "reason": f"HTTP {status}"}
    return {"status": "unavailable", "reason": "请求失败"}


def probe_url(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json,application/xml,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read(240000)
            body = raw.decode("utf-8", "ignore")
            info = classify_probe(True, r.status, body)
            info.update({"http_status": r.status, "bytes_sampled": len(raw)})
            return info
    except urllib.error.HTTPError as e:
        try:
            body = e.read(4000).decode("utf-8", "ignore")
        except Exception:
            body = ""
        info = classify_probe(False, e.code, body)
        info.update({"http_status": e.code, "bytes_sampled": len(body)})
        return info
    except Exception as e:
        info = classify_probe(False, 0, "")
        info.update({"http_status": 0, "bytes_sampled": 0, "error": str(e)[:180]})
        return info


def summarize_attempts(name, attempts):
    working = any(a.get("status") == "reachable" for a in attempts)
    state = "integrated" if working and len(attempts) < 3 else "not_integrated"
    if name in {"Product Hunt", "GitHub Trending"} and working:
        state = "integrated"
    return {"name": name, "state": state, "attempt_count": len(attempts)}


def run_probe():
    rows = []
    for source in SOURCES:
        attempts = []
        for attempt in source["attempts"]:
            result = probe_url(attempt["url"])
            attempts.append({**attempt, **result})
        summary = summarize_attempts(source["name"], attempts)
        if source.get("state_hint") == "not_integrated":
            summary["state"] = "not_integrated"
        rows.append({"source": source["name"], "summary": summary, "attempts": attempts})
    return rows


def render_report(rows):
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# Source Access Matrix · A/C 类高信号源打通记录",
        "",
        f"生成时间：{now}",
        "",
        "## 总览",
        "",
        "| 源 | 状态 | 尝试数 | 当前处理 |",
        "|---|---|---:|---|",
    ]
    treatment = {
        "Product Hunt": "已接入 official feed，作为 A 类商业上下文进入观察池。",
        "GitHub Trending": "已接入公开 trending HTML，作为 C 类技术趋势进入观察池。",
        "Chrome Web Store": "搜索页可达，但评论/评分无稳定公开契约；暂不自动采集。",
        "Toolify": "本机直连核心页 403；未接入。",
        "There Is An AI For That": "页面可达但结构重且易漂移；待后续做专门解析与抽样评估。",
    }
    for row in rows:
        s = row["summary"]
        lines.append(f"| {row['source']} | {s['state']} | {s['attempt_count']} | {treatment.get(row['source'], '')} |")
    lines += ["", "## 明细", ""]
    for row in rows:
        lines.append(f"### {row['source']}")
        lines.append("")
        lines.append("| 方法 | HTTP | 状态 | 原因 | 备注 |")
        lines.append("|---|---:|---|---|---|")
        for a in row["attempts"]:
            lines.append(f"| `{a['method']}` | {a.get('http_status', 0)} | {a['status']} | {a['reason']} | {a['note']} |")
        lines.append("")
    return "\n".join(lines)


def main():
    rows = run_probe()
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w", encoding="utf-8") as f:
        f.write(render_report(rows))
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
