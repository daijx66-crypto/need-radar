# collectors/apple_appstore.py — App Store（官方榜单 RSS + 用户评论 RSS，无需 key）
# 信号类型：ranking（榜单趋势）/ complaint·review（差评挖痛点）
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

# 每个区：cc -> (展示信息)
REGIONS = {
    "us": {"region": "海外", "lang": "en"},
    "cn": {"region": "国内", "lang": "zh"},
}
TOP_N = 25          # 榜单条数
REVIEW_APPS = 8     # 每个区取榜单 Top ~8 拉差评
SLEEP = 0.4         # 礼貌限速（秒/请求）


def chart_url(cc):
    return f"https://rss.marketingtools.apple.com/api/v2/{cc}/apps/top-free/{TOP_N}/apps.json"


def reviews_url(cc, app_id):
    return (f"https://itunes.apple.com/{cc}/rss/customerreviews/"
            f"page=1/sortby=mostrecent/id={app_id}/json")


def _label(node):
    """安全取 iTunes RSS 里 {'label': ...} 结构的值。"""
    if isinstance(node, dict):
        return node.get("label", "") or ""
    return node or ""


def collect_chart(cc, meta, seen):
    """拉一个区的榜单 -> ranking 信号；返回 (chart_title, [(rank, app)...]) 供差评用。"""
    data = get_json(chart_url(cc))
    feed = data.get("feed", {})
    chart_title = feed.get("title") or "Top Free Apps"
    results = feed.get("results", []) or []
    ranked = []
    for i, app in enumerate(results):
        rank = i + 1
        app_id = app.get("id")
        name = app.get("name") or ""
        if not app_id or not name:
            continue
        ranked.append((rank, app))
        genres = [g.get("name", "") for g in (app.get("genres") or []) if g.get("name")]
        genre_str = "、".join(genres) if genres else ""
        text = f"{chart_title} 第{rank}" + (f"（{genre_str}）" if genre_str else "")
        # 榜位反推热度：靠前更高；25 名内 (26-rank)*4 -> 100..4
        popularity = max(0, (26 - rank) * 4)
        sid = f"apple_appstore-rank-{cc}-{app_id}"
        if sid in seen:
            continue
        keywords = genres + [name]
        seen[sid] = mk_signal(
            id=sid, source="apple_appstore", source_label="App Store",
            region=meta["region"], lang=meta["lang"],
            title=name, text=text,
            url=app.get("url") or "",
            popularity=popularity, comments=0,
            created_at=app.get("releaseDate") or "",
            signal_type="ranking", keywords=keywords)
    return chart_title, ranked


def collect_reviews(cc, meta, ranked, seen):
    """对榜单 Top REVIEW_APPS 的 app 拉评论，取 <=3 星 -> complaint/review 信号。"""
    got = 0
    for rank, app in ranked[:REVIEW_APPS]:
        app_id = app.get("id")
        app_url = app.get("url") or ""
        try:
            time.sleep(SLEEP)
            data = get_json(reviews_url(cc, app_id))
        except Exception as e:
            print(f"  review feed fail ({cc}/{app_id}):", e)
            continue
        entries = data.get("feed", {}).get("entry", []) or []
        if isinstance(entries, dict):  # 仅 1 条评论时 RSS 可能给 dict
            entries = [entries]
        for ent in entries:
            try:
                rating = int(_label(ent.get("im:rating")) or 0)
            except (TypeError, ValueError):
                continue
            if rating <= 0 or rating > 3:
                continue
            title = _label(ent.get("title"))
            body = _label(ent.get("content"))
            if not title and not body:
                continue
            rid = _label(ent.get("id"))
            sid = f"apple_appstore-review-{cc}-{rid}"
            if not rid or sid in seen:
                continue
            try:
                votes = int(_label(ent.get("im:voteCount")) or 0)
            except (TypeError, ValueError):
                votes = 0
            text = body[:500]
            # 差评热度：评分越低越高 (6-rating)*20 + 点赞
            popularity = (6 - rating) * 20 + votes
            stype = detect_signal_type(title, text, "review")
            if stype not in ("complaint", "question"):
                stype = "complaint"  # <=3 星本质是抱怨
            seen[sid] = mk_signal(
                id=sid, source="apple_appstore", source_label="App Store",
                region=meta["region"], lang=meta["lang"],
                title=title or "(无标题)", text=text,
                url=app_url,
                popularity=popularity, comments=0,
                created_at=_label(ent.get("updated")),
                signal_type=stype,
                keywords=extract_keywords(title + " " + text, meta["lang"]))
            got += 1
    return got


def run():
    seen = {}
    n_rank, n_review = 0, 0
    for cc, meta in REGIONS.items():
        try:
            time.sleep(SLEEP)
            chart_title, ranked = collect_chart(cc, meta, seen)
        except Exception as e:
            print(f"  chart fail ({cc}):", e)
            continue
        added_rank = sum(1 for s in seen.values()
                         if s["signal_type"] == "ranking" and s["region"] == meta["region"])
        print(f"  [{cc}] 榜单「{chart_title}」拿到 {len(ranked)} 个 app")
        got = collect_reviews(cc, meta, ranked, seen)
        print(f"  [{cc}] 差评信号 {got} 条")
        n_review += got
    signals = list(seen.values())
    n_rank = sum(1 for s in signals if s["signal_type"] == "ranking")
    n_review = sum(1 for s in signals if s["signal_type"] in ("complaint", "review", "question"))
    write_raw("apple_appstore", signals)
    print(f"  合计 ranking={n_rank}  complaint/review={n_review}")


if __name__ == "__main__":
    run()
