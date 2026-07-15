# collectors/_common.py — 需求雷达采集器共享工具（仅标准库，零依赖）
import json, os, re, time, urllib.request, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "data", "raw")
UA = "need-radar/0.1 (+local research tool; contact: user)"

def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).astimezone().isoformat(timespec="seconds")

def http_get(url, timeout=15, headers=None, retries=2):
    h = {"User-Agent": UA, "Accept": "application/json, text/plain, */*",
         "Accept-Language": "en,zh-CN;q=0.8"}
    if headers:
        h.update(headers)
    last = None
    for i in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=h)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(1.2 * (i + 1))
    raise last

def get_json(url, **kw):
    return json.loads(http_get(url, **kw).decode("utf-8", "ignore"))

# —— 抱怨/需求语言标记（中英）——
PAIN_EN = ["annoying", "frustrat", "i hate", "i wish", "wish there", "is there a", "how do i",
           "how can i", "alternative to", "too expensive", "overpriced", "painful", "struggle",
           "tired of", "sucks", "doesn't work", "can't find", "looking for a", "need a tool",
           "any tool", "workaround", "no good", "hard to"]
PAIN_ZH = ["求推荐", "有没有", "好烦", "难用", "吐槽", "踩坑", "替代", "太贵", "不会用", "求一个",
           "怎么办", "求助", "有没有人", "崩溃", "退款", "没法", "用不了", "求大佬", "求方案",
           "痛点", "好用的", "求", "坑爹", "麻烦"]
WTP_MARK = ["$", "美元", "付费", "订阅", "subscri", "pricing", "per month", "/mo", "会员",
            "plan", "license", "充值", "买单", "愿意付"]
RECUR_EN = ["every day", "daily", "every time", "each time", "weekly", "constantly",
            "always have to", "repeat", "over and over"]
RECUR_ZH = ["每天", "每次", "天天", "反复", "总是", "经常", "老是"]
GAP_MARK = ["alternative to", "替代", "没有好用", "wish there", "there's no", "还没有",
            "缺一个", "find a better", "no decent"]
STOP_EN = set(("the a an and or to of in for on is are be this that with you your i we it as at by "
               "from has have new use using just like get can will not what how why so do does my "
               "me but if then than into out up about more most some any all one two no yes vs via "
               "they them their our he she his her who whom which when where").split())

def _has(s, words):
    return any(w in s for w in words)

def detect_signal_type(title, text, default="discussion"):
    low = (title + " " + text).lower()
    raw = title + " " + text
    if _has(low, PAIN_EN) or _has(raw, PAIN_ZH):
        if any(q in low for q in ["how do i", "how can i", "is there"]) or any(q in raw for q in ["怎么", "有没有", "求"]):
            return "question"
        return "complaint"
    return default

def extract_keywords(text, lang="en", k=8):
    text = re.sub(r"https?://\S+", " ", text or "")
    if lang == "zh":
        toks = re.findall(r"[一-龥]{2,6}", text)
    else:
        toks = [t for t in re.findall(r"[a-zA-Z][a-zA-Z0-9+\-]{2,}", text.lower()) if t not in STOP_EN]
    freq = {}
    for t in toks:
        freq[t] = freq.get(t, 0) + 1
    return [w for w, _ in sorted(freq.items(), key=lambda x: -x[1])[:k]]

def write_raw(source, signals):
    os.makedirs(RAW_DIR, exist_ok=True)
    path = os.path.join(RAW_DIR, f"{source}.json")
    out = {"source": source, "generated_at": now_iso(), "count": len(signals), "signals": signals}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"[{source}] wrote {len(signals)} signals -> {path}")
    return path

def mk_signal(**kw):
    base = {"id": "", "source": "", "source_label": "", "region": "通用", "lang": "en",
            "title": "", "text": "", "url": "", "popularity": 0, "comments": 0,
            "created_at": "", "signal_type": "discussion", "keywords": []}
    base.update(kw)
    return base
