# collectors/weibo_hot.py — 微博热搜（best-effort，国内即时情绪）
# 依次尝试多个免登录接口，任一成功即用，全失败 graceful 写 0 条
# 信号类型：trend
import sys, os, urllib.parse
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import get_json, http_get, write_raw, mk_signal, detect_signal_type, extract_keywords

WEIBO_HEADERS = {
    "Referer": "https://weibo.com",
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
}

def search_url(word):
    return "https://s.weibo.com/weibo?q=" + urllib.parse.quote("#" + word + "#")

def _mk(native_id, word, text, popularity):
    word = (word or "").strip()
    if not word:
        return None
    return mk_signal(
        id=f"weibo_hot-{native_id}", source="weibo_hot", source_label="微博热搜",
        region="国内", lang="zh", title=word, text=(text or "").strip(),
        url=search_url(word), popularity=int(popularity or 0), comments=0,
        created_at="", signal_type="trend",
        keywords=extract_keywords(word + " " + (text or ""), "zh"))

def try_weibo_official():
    # https://weibo.com/ajax/side/hotSearch -> data.realtime[{word,num,note,category}]
    data = get_json("https://weibo.com/ajax/side/hotSearch", headers=WEIBO_HEADERS)
    realtime = ((data or {}).get("data") or {}).get("realtime") or []
    signals, seen = [], set()
    for i, it in enumerate(realtime):
        word = it.get("word") or it.get("note")
        if not word or word in seen:
            continue
        seen.add(word)
        num = it.get("num") or 0
        cat = it.get("category") or it.get("note") or ""
        s = _mk(it.get("word") or f"rt{i}", word, cat, int(num) // 1000)
        if s:
            signals.append(s)
    return signals

def try_vvhan():
    # 备选第三方：https://api.vvhan.com/api/hotlist/wbHot -> data[{title,hot,url}]
    data = get_json("https://api.vvhan.com/api/hotlist/wbHot")
    rows = (data or {}).get("data") or []
    signals, seen = [], set()
    n = len(rows)
    for i, it in enumerate(rows):
        word = it.get("title") or it.get("word")
        if not word or word in seen:
            continue
        seen.add(word)
        # hot 可能是 "1234.5万" 字符串；取不到就用排名反推
        pop = 0
        raw_hot = it.get("hot")
        if isinstance(raw_hot, (int, float)):
            pop = int(raw_hot) // 1000
        if pop <= 0:
            pop = max(1, n - i)  # 排名反推
        s = _mk(f"vvhan{i}", word, it.get("type") or "", pop)
        if s:
            signals.append(s)
    return signals

PROVIDERS = [("weibo_official", try_weibo_official), ("vvhan", try_vvhan)]

def run():
    for name, fn in PROVIDERS:
        try:
            signals = fn()
        except Exception as e:
            print(f"  weibo_hot provider {name} fail: {e}")
            continue
        if signals:
            print(f"  weibo_hot provider {name} ok: {len(signals)} signals")
            write_raw("weibo_hot", signals)
            return
        print(f"  weibo_hot provider {name} returned 0 signals, try next")
    print("  weibo_hot graceful degrade: 所有免登录接口均不可用，写 0 条")
    write_raw("weibo_hot", [])

if __name__ == "__main__":
    run()
