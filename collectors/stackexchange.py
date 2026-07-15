# collectors/stackexchange.py — Stack Exchange（2.3 API，无需 key）
# 站点：stackoverflow / superuser / webapps / softwarerecommendations
# 关键坑：SE API 响应始终 gzip 压缩，_common.http_get 不解 gzip，本地自行解压。
import sys, os, gzip, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

import re, html

API = "https://api.stackexchange.com/2.3/questions"
# 注意：site 用的是 SE 的 api_site_parameter（机读 slug），不是域名。
# softwarerecommendations 的 slug 是 softwarerecs（用错会 HTTP 400）。
SITES = ["stackoverflow", "superuser", "webapps", "softwarerecs"]
# 这两个站的问题天然是「找工具 / 找替代」类需求，默认 question
TOOL_FINDER_SITES = {"webapps", "softwarerecs"}
KEY = os.environ.get("STACKEXCHANGE_KEY", "").strip()

SITE_LABEL = {
    "stackoverflow": "Stack Overflow",
    "superuser": "Super User",
    "webapps": "Web Applications",
    "softwarerecs": "Software Recommendations",
}


def se_get_json(url):
    """SE 响应始终 gzip。先用 http_get 拿 bytes，尝试 gzip.decompress，失败再 fallback 原始 bytes。"""
    raw = http_get(url, headers={"Accept-Encoding": "gzip"})
    try:
        raw = gzip.decompress(raw)
    except (OSError, EOFError):
        pass  # 万一服务端真的返回了 identity，直接用原始 bytes
    return json.loads(raw.decode("utf-8", "ignore"))


def strip_html(s):
    if not s:
        return ""
    s = re.sub(r"(?is)<(script|style).*?</\1>", " ", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fetch_site(site, sort="week"):
    """拉单个站的问题。返回 (items, data)；失败抛异常。"""
    url = (f"{API}?order=desc&sort={sort}&site={site}"
           f"&pagesize=40&filter=withbody")
    if KEY:
        url += f"&key={KEY}"
    data = se_get_json(url)
    err = data.get("error_id") or data.get("error_name")
    if err:
        # backoff/throttle 仍要尊重
        if data.get("backoff"):
            time.sleep(float(data["backoff"]))
        raise RuntimeError(data.get("error_message") or str(err))
    return data.get("items", []), data


def run():
    seen = {}
    for site in SITES:
        try:
            items, data = fetch_site(site, "week")
            # 低流量站（webapps/softwarerecs）sort=week 可能为空，回退到 activity
            if not items:
                time.sleep(0.5)
                items, data = fetch_site(site, "activity")
            label = SITE_LABEL.get(site, site)
            for q in items:
                qid = q.get("question_id")
                title = strip_html(q.get("title") or "")
                if not qid or qid in seen or not title:
                    continue
                text = strip_html(q.get("body") or "")[:500]
                if site in TOOL_FINDER_SITES:
                    stype = "question"
                else:
                    stype = detect_signal_type(title, text, "question")
                created = q.get("creation_date")
                created_iso = ""
                if created:
                    import datetime
                    created_iso = datetime.datetime.fromtimestamp(
                        int(created), datetime.timezone.utc).isoformat(timespec="seconds")
                seen[qid] = mk_signal(
                    id=f"stackexchange-{qid}", source="stackexchange",
                    source_label=f"Stack Exchange · {label}",
                    region="海外", lang="en", title=title, text=text,
                    url=q.get("link") or f"https://{site}.stackexchange.com/q/{qid}",
                    popularity=int(q.get("score") or 0),
                    comments=int(q.get("answer_count") or 0),
                    created_at=created_iso, signal_type=stype,
                    keywords=extract_keywords(title + " " + text, "en"))
            print(f"  se {site}: +{len(items)} items (total seen {len(seen)})")
            # 礼貌限速；若返回带 backoff 字段按其秒数等待
            bo = data.get("backoff")
            time.sleep(float(bo) if bo else 0.5)
        except Exception as e:
            print(f"  se {site} fail:", e)
            continue
    write_raw("stackexchange", list(seen.values()))


if __name__ == "__main__":
    run()
