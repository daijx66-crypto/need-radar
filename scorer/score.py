#!/usr/bin/env python3
# scorer/score.py — 把 data/raw/*.json 的信号聚类成「需求」，按 8 维打分 + 多人格视角 + 产品形态，
# 输出 data/needs.json。纯标准库、确定性（无 LLM）。可选 LLM 增强见 scorer/enrich_llm.py。
import datetime, json, os, glob, math, re, sys, html as _html, hashlib
from email.utils import parsedate_to_datetime
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "collectors"))
from _common import PAIN_EN, PAIN_ZH, WTP_MARK, RECUR_EN, RECUR_ZH, GAP_MARK, now_iso  # noqa
try:
    from .attention import build_attention, load_previous_snapshot, save_snapshot, stable_id
except ImportError:
    from attention import build_attention, load_previous_snapshot, save_snapshot, stable_id

RAW = os.path.join(ROOT, "data", "raw")
OUT = os.path.join(ROOT, "data", "needs.json")
HISTORY = os.path.join(ROOT, "data", "history")
CACHE_DIR = os.path.join(ROOT, "data", "cache")
SEMANTIC_GATE_CACHE = os.path.join(CACHE_DIR, "semantic_gate.json")
SEMANTIC_GATE_VERSION = "phase2-strict-v5-consumer-advice"
RUN_MODE = os.environ.get("NEED_RADAR_MODE", "local").strip().lower()
GITHUB_EXCLUDED_RAW = {
    "bilibili",
    "opencli_douyin",
    "opencli_tiktok",
    "opencli_twitter",
    "opencli_xiaohongshu",
}


def filter_raw_files(paths, mode=RUN_MODE):
    if mode != "github":
        return list(paths)
    return [path for path in paths if os.path.splitext(os.path.basename(path))[0] not in GITHUB_EXCLUDED_RAW]


def load_json(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


RUBRIC_PATH = os.environ.get("NEED_RADAR_RUBRIC", "")
if not RUBRIC_PATH:
    RUBRIC_PATH = os.path.join(HERE, "persona_rubric.default.json" if RUN_MODE == "github" else "persona_rubric.json")
if not os.path.exists(RUBRIC_PATH):
    RUBRIC_PATH = os.path.join(HERE, "persona_rubric.default.json")
RUBRIC = load_json(RUBRIC_PATH)
PROFILE_PATH = os.environ.get("NEED_RADAR_PROFILE", "")
if not PROFILE_PATH:
    PROFILE_PATH = os.path.join(HERE, "profile.default.json" if RUN_MODE == "github" else "profile.json")
if not os.path.exists(PROFILE_PATH):
    PROFILE_PATH = os.path.join(HERE, "profile.default.json")
PROFILE = load_json(PROFILE_PATH)

WEIGHTS = {"pain": .22, "wtp": .18, "gap": .15, "freq": .12, "narrow": .10, "alpha": .08, "feasible": .08, "fit": .07}

AUDIENCE = ["developer", "dev", "engineer", "designer", "founder", "indie", "seller", "marketer", "student",
            "teacher", "writer", "creator", "freelanc", "startup", "saas", "ecommerce", "trader", "analyst",
            "nurse", "lawyer", "recruiter", "manager", "开发", "程序员", "设计师", "卖家", "跨境", "学生",
            "老师", "教师", "创作者", "自媒体", "运营", "商家", "主播", "考研", "考公", "求职", "应届",
            "博主", "站长", "独立开发", "外贸", "电商", "宝妈", "新手"]
TECH = ["ai", "llm", "gpt", "claude", "model", "agent", "api", "automation", "prompt", "rag", "diffusion",
        "mcp", "模型", "智能体", "自动化", "大模型", "生成", "ml", "neural", "chatbot"]
COMPLEX = ["realtime", "real-time", "video", "training", "fine-tune", "finetune", "hardware", "blockchain",
           "payment", "regulat", "compliance", "kyc", "driver", "kernel", "3d", "render", "streaming",
           "实时", "训练", "硬件", "区块链", "支付", "风控", "合规", "驱动", "渲染", "流式", "底层"]
GENERIC = ["everyone", "anyone", "people", "all users", "users", "所有人", "大家", "人人", "通用", "全部"]
# 纯娱乐/新闻噪声（这类内容吐槽不算产品需求，剔除）
ENTERTAIN = ["电影", "明星", "演唱会", "比赛", "球", "原神", "游戏cg", "动漫", "番剧", "综艺", "八卦",
             "热搜", "celebrity", "movie", "trailer", "anime", "song", "mv"]
ENTERTAIN_EXT = ENTERTAIN + ["game", "games", "gaming", "gameplay", "sport", "soccer", "football", "nba",
                             "world cup", "league", "season", "episode", " show", "series", "team ", "match",
                             "player", "manga", "casino", "gacha", "lottery", "betting",
                             "剧", "赛季", "赛事", "球队", "球员", "彩票", "博彩", "抽卡", "卡牌", "公会"]
# 功能/工具缺口语言（差评要表达这种缺口才算需求，而非单纯情绪发泄）
FEATURE_GAP = ["no way to", "can't", "cant ", "cannot", "unable", "needs a", "need a", "should add",
               "please add", "wish it", "wish there", "missing", "lacks", "no option", "alternative",
               "export", "offline", "sync", "import", "too many ads", "ads everywhere", "so many ads",
               "paywall", "overpriced", "too expensive", "subscription", "doesn't let", "won't let",
               "无法", "不能", "没有", "希望", "应该加", "建议加", "太多广告", "广告太多", "满屏广告",
               "闪退", "卡顿", "收费", "付费墙", "太贵", "导出", "离线", "同步", "求推荐", "有没有",
               "替代", "难用", "用不了", "不支持"]
# 太空洞的差评标题（命中则不能直接当需求标题）
GENERIC_TITLES = {"frustrated", "good but", "great but", "ok", "okay", "meh", "disappointed",
                  "disappointing", "love it", "hate it", "fun", "boring", "good", "bad", "nice", "cool",
                  "wow", "update", "bug", "bugs", "crash", "trash", "scam", "broken", "terrible", "amazing"}
# 正向好评（差评源里命中且压过负面=不是需求，剔除）
POSITIVE = ["really good", "love it", "love this", "best app", "amazing", "perfect", "excellent",
            "worth paying", "works great", "great app", "awesome", "fantastic", "好用", "很棒",
            "非常好", "好评", "神器", "真香", "强烈推荐", "五星"]
BUILDER_SRC = {"Hacker News", "Stack Exchange", "V2EX", "Reddit"}
# 新闻/争议/公告类（不是产品需求，命中且非在找方案则重罚）
NEWS_MARK = ["leak", "leaked", "hacked", "outage", "acquired", "acquisition", "raises $", "raised $",
             "shuts down", "shut down", "banned", "controversy", "drama", "lawsuit", "sues", "layoff",
             "泄露", "爆料", "封禁", "下架", "停服", "收购", "融资", "裁员", "起诉"]
ALPHA_KW = set()  # 由 main 从带技术属性的新发布/趋势信号填充

# —— Stage-0 真需求闸词表（先判"是不是可做的真需求"，再打分）——
# 讨论/观点/经验/八卦（不是需求）
DISCUSS = ["感想", "聊聊", "谈谈", "分享一下", "个人观点", "暴论", "随便聊", "唠唠", "怎么看",
           "如何看待", "讨论一下", "请教大家", "求经验", "有感而发", "复盘", "感悟", "求安利",
           "见过哪些",
           "thoughts on", "my take", "aha", "lesson", "lessons", "what happened", "retrospective",
           "year in review", "estimate", "estimates", "parameter count", "benchmark", "benchmarks",
           "what is your", "what are your", "what's your", "what overlooked", "anyone else",
           "how do you feel", "opinion", "rant", "story of", "my journey", "i think", "am i the only"]
# 自我推广/产品发布/广告（不是需求）
PROMO = ["[开源]", "开源]", "我做了", "我开发", "我带队", "带领 ai", "上线了", "已上线", "重磅发布",
         "推荐我的", "我的项目", "我写了个", "我搞了个", "做了个", "打磨了", "想听听大家的反馈",
         "欢迎试用", "欢迎大家试用", "免费试用", "我的这个", "我这个", "自己做", "自己开发",
         "满足自己的使用需求", "低价", "超低", "0.1x",
         "0.2x", "倍率", "优惠", "折扣", "纯血", "主打", "首发", "限时", "薅羊毛",
         "show hn", "i built", "i made", "i created", "we built", "we made", "we launched",
         "introducing ", "launching ", "my new ", "check out my", "just launched", "just shipped",
         "– a free", "- a free", "– alternative to", "- alternative to"]
# 买物咨询/硬件/政策灰（不是软件产品需求 / 不适合做）
BUYADVICE = ["二手", "回收", "求购", "选购", "配置单", "价格表", "vps", "机场", "梯子", "节点",
             "科学上网", "翻墙", "airport 求", "买什么电脑", "求推荐.*笔记本"]
# 在找一个不存在/不够好的工具或方案（=真需求的正向证据）
SEEK_TOOL = ["looking for a", "is there a tool", "is there an app", "is there a service",
             "is there any", "is there a way to", "any tool", "any app", "any service",
             "alternative to", "alternatives to", "recommend a tool", "recommend an app",
             "need a tool", "need an app", "wish there was", "wish there were", "no good",
             "there's no", "tool to", "tool that", "app to ", "app that", "service that",
             "find a tool", "find an app", "best tool for", "best app for", "how can i automate",
             "求推荐", "有没有好用", "有没有什么", "求一个", "求个", "平替", "替代品", "有没有类似",
             "找个工具", "求工具", "有什么工具", "有什么软件", "有什么好用", "怎么自动化", "能不能自动"]

SOURCE_REGION_BONUS_WTP = {"Hacker News": 1.0, "Stack Exchange": .6, "App Store": 1.0, "V2EX": .4,
                           "Bilibili": .2, "微博热搜": .2, "Hugging Face": .5, "Reddit": .8,
                           "小红书": .4, "X/Twitter": .8, "TikTok": .5, "抖音热点": .2}

SOURCE_TIER_LABELS = {
    "A": "A 商业证据",
    "B": "B 抱怨求助",
    "C": "C 趋势注释",
    "D": "D 泛热榜",
}
SOURCE_TIER_PATTERNS = [
    ("A", ["TrustMRR", "Toolify", "TAAFT", "There’s An AI For That", "Theres An AI For That",
           "Product Hunt", "App Store", "Chrome Web Store", "Google Play"]),
    ("B", ["Reddit", "Hacker News", "Stack Exchange", "V2EX", "Indie Hackers", "Lobsters", "DEV Community",
           "小红书", "X/Twitter"]),
    ("C", ["Google Trends", "GitHub Trending", "Hugging Face", "Exploding Topics", "Semrush", "Ahrefs", "TikTok",
           "AI HOT", "Follow Builders"]),
    ("D", ["Bilibili", "哔哩哔哩", "微博热搜", "微博", "今日热榜", "即刻", "知乎热榜", "抖音热榜", "抖音热点"]),
]
SOURCE_TIER_RANK = {"A": 0, "B": 1, "C": 2, "D": 3}

HOWTO_TOOL_NAMES = ["google sheets", "spreadsheet", "excel", "powerpoint", "libreoffice", "google docs",
                    "microsoft word", "word ", "gmail", "linkedin", "facebook", "notion", "airtable",
                    "docs", "sheets", "slack", "trello", "jira", "figma", "photoshop"]
HOWTO_MARKERS = ["how to", "how can i", "how do i", "is there a way", "formula", "row", "column", "cell",
                 "disable", "enable", "setting", "settings", "macro", "pull a value",
                 "extracting", "occurrence", "based on the values", "ranking in google sheets"]
WORKAROUND_MARKERS = ["manually", "manual", "spreadsheet", "csv", "google sheet", "va ", "virtual assistant",
                      "intern", "copy paste", "copy-paste", "zapier", "notion table", "airtable",
                      "手动", "表格", "人工", "复制粘贴", "外包", "助理", "客服"]
PRODUCTIZABLE_MARKERS = ["tool", "app", "service", "api", "extension", "dashboard", "alert", "monitor",
                         "automation", "workflow", "saas", "software", "平台", "工具", "软件", "应用",
                         "插件", "监控", "提醒", "自动化", "系统"]
MARKET_RESEARCH = ["profitable saas", "simple saas", "make money", "make 500", "500 usd", "500$",
                   "examples of", "looking for inspiration", "product ideas", "创业点子", "赚钱项目",
                   "有什么项目", "哪些项目"]
CONSUMER_PRODUCTS = ["手机", "大电池", "mah", "mAh", "笔记本", "电脑", "平板", "耳机", "相机", "显示器",
                     "phone", "laptop", "tablet", "headphone", "camera", "monitor"]
CONSUMER_ADVICE = ["求推荐", "买什么", "求推荐个型号", "求推荐型号", "哪家的好", "哪家好", "哪家好点", "想换个", "买哪款",
                   "选哪款", "推荐个型号", "which phone", "which laptop", "recommend a phone",
                   "recommend a laptop"]
CREATOR_ROUNDUP = ["top 10", "you should use", "i rec", "i recommend", "my favorite", "tools you need",
                   "apps you need", "best apps", "best tools", "必备工具", "工具盘点", "推荐几个",
                   "值得收藏", "建议收藏", "合集"]
SOCIAL_SPECIFIC_NEED = ["alert", "monitor", "automate", "automation", "api", "saas", "review", "export",
                        "sync", "dashboard", "extension", "billing", "invoice", "scrape", "competitor",
                        "app store", "chrome web store", "提醒", "监控", "自动化", "导出", "同步", "账单",
                        "竞品", "差评"]


def source_tier(source_label):
    label = source_label or ""
    low_label = low(label)
    for tier, pats in SOURCE_TIER_PATTERNS:
        for p in pats:
            if p.lower() in low_label:
                return tier
    return "B"


def source_tier_label(tier):
    return SOURCE_TIER_LABELS.get(tier, "B 抱怨求助")


def deh(s):
    # 去 HTML 标签 + 反转义实体，避免 <i>&#x27; 之类漏进标题/摘要
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = _html.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def low(s):
    return (s or "").lower()


def _hit(blob_low, raw, words):
    for w in words:
        if (w in blob_low) if w.isascii() else (w in raw):
            return True
    return False


def count_markers(text, markers):
    t = low(text)
    raw = text or ""
    n = 0
    for m in markers:
        if m.isascii():
            n += t.count(m)
        else:
            n += raw.count(m)
    return n


def featurize(sig):
    blob = (sig.get("title", "") + " " + sig.get("text", ""))
    f = {}
    f["pain"] = count_markers(blob, PAIN_EN) + count_markers(blob, PAIN_ZH)
    f["wtp"] = count_markers(blob, WTP_MARK)
    f["recur"] = count_markers(blob, RECUR_EN) + count_markers(blob, RECUR_ZH)
    f["gap"] = count_markers(blob, GAP_MARK)
    f["aud"] = sum(1 for a in AUDIENCE if a in low(blob))
    f["generic"] = sum(1 for g in GENERIC if g in low(blob))
    f["tech"] = sum(1 for t in TECH if t in low(blob))
    f["complex"] = sum(1 for c in COMPLEX if c in low(blob))
    f["ent"] = sum(1 for e in ENTERTAIN if e in low(blob))
    sig["_f"] = f
    return sig


def looks_entertainment(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    return any(e in blob for e in ENTERTAIN_EXT)


def expresses_gap(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    f = sig["_f"]
    if f["gap"] > 0 or f["pain"] >= 2:
        return True
    for g in FEATURE_GAP:
        if (g in blob) if g.isascii() else (g in raw):
            return True
    return False


def _has_product_marker(blob, raw):
    for k in PRODUCTIZABLE_MARKERS:
        if k.isascii():
            if re.search(rf"\b{re.escape(k)}s?\b", blob):
                return True
        elif k in raw:
            return True
    return False


def _seeks_tool(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    seeking_phrases = ["looking for", "need a", "need an", "wish there", "recommend a tool", "recommend an app", "alternative",
                       "alert", "monitor", "automate", "求推荐", "有没有", "替代", "自动化", "监控", "提醒"]
    return _hit(blob, raw, SEEK_TOOL) or (_has_product_marker(blob, raw) and _hit(blob, raw, seeking_phrases))


def _has_workaround(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    return any((m in blob) if m.isascii() else (m in raw) for m in WORKAROUND_MARKERS)


def _has_paid_cost(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    money = bool(re.search(r"(\$\s?\d+|usd\s?\d+|rmb\s?\d+|¥\s?\d+|\d+\s?(dollars|usd|元|块|人民币))", blob))
    paid_markers = [m for m in WTP_MARK if m != "$"]
    return money or any((m in blob) if m.isascii() else (m in raw) for m in paid_markers)


def is_consumer_buy_advice(sig):
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    has_product = any((p.lower() in blob) if p.isascii() else (p in raw) for p in CONSUMER_PRODUCTS)
    has_advice = any((a in blob) if a.isascii() else (a in raw) for a in CONSUMER_ADVICE)
    return has_product and has_advice


def is_creator_roundup(sig):
    label = sig.get("source_label", "")
    if label not in {"TikTok", "小红书", "Bilibili", "哔哩哔哩"}:
        return False
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    if _has_workaround(sig) or _has_paid_cost(sig):
        return False
    return any((m in blob) if m.isascii() else (m in raw) for m in CREATOR_ROUNDUP)


def is_low_context_social_reply(sig):
    if sig.get("source_label") != "X/Twitter":
        return False
    title = deh(sig.get("title", ""))
    if not title.startswith("@"):
        return False
    if _has_workaround(sig) or _has_paid_cost(sig):
        return False
    blob = low(title + " " + sig.get("text", ""))
    raw = title + " " + sig.get("text", "")
    return not any((m in blob) if m.isascii() else (m in raw) for m in SOCIAL_SPECIFIC_NEED)


def is_existing_tool_howto(sig):
    src = sig.get("source_label", "")
    if not src.startswith("Stack Exchange"):
        return False
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    has_howto = any(m in blob for m in HOWTO_MARKERS)
    has_existing_tool = any(m in blob for m in HOWTO_TOOL_NAMES)
    return has_howto and has_existing_tool


def is_product_link_drop(sig):
    src = sig.get("source_label", "")
    title = sig.get("title", "")
    blob = low(title + " " + sig.get("text", ""))
    text_empty = not (sig.get("text") or "").strip()
    if src != "Hacker News" or not text_empty:
        return False
    link_to_home = bool(sig.get("url")) and "news.ycombinator.com" not in low(sig.get("url", ""))
    product_title = bool(re.search(r"\b[\w.-]+\.(io|ai|app|com|dev)\b", blob))
    return link_to_home and product_title and ("alternative to" in blob or "–" in title or "-" in title)


def is_developer_howto(sig):
    src = sig.get("source_label", "")
    if "Stack Overflow" not in src:
        return False
    title = low(sig.get("title", ""))
    starts_like_howto = title.startswith(("how ", "how can", "how do", "why ", "error ", "cannot ", "can't "))
    code_terms = ["angular", "react", "vue", "python", "javascript", "typescript", "browser", "form",
                  "state", "api", "class", "function", "exception", "stack trace"]
    return starts_like_howto and any(t in title for t in code_terms)


def semantic_gate(sig):
    st = sig.get("signal_type")
    src = sig.get("source_label", "")
    tier = source_tier(src)
    blob = low(sig.get("title", "") + " " + sig.get("text", ""))
    raw = sig.get("title", "") + " " + sig.get("text", "")
    f = sig["_f"]
    seeks_tool = _seeks_tool(sig)
    has_cost = _has_paid_cost(sig)
    has_workaround = _has_workaround(sig)
    gap = expresses_gap(sig)

    base = {
        "label": "noise",
        "should_rank": False,
        "intent_type": "none",
        "noise_type": "",
        "purchase_reason": "",
        "current_workaround": "",
        "source_tier": tier,
        "source_tier_label": source_tier_label(tier),
    }

    if tier == "D":
        return {**base, "noise_type": "broad_heat"}
    if looks_entertainment(sig) and not gap:
        return {**base, "noise_type": "entertainment"}
    if _hit(blob, raw, PROMO):
        return {**base, "noise_type": "promotion"}
    if is_consumer_buy_advice(sig):
        return {**base, "noise_type": "consumer_buy_advice"}
    if _hit(blob, raw, BUYADVICE):
        return {**base, "noise_type": "buy_advice_or_policy_gray"}
    if is_creator_roundup(sig):
        return {**base, "noise_type": "creator_roundup"}
    if is_low_context_social_reply(sig):
        return {**base, "noise_type": "low_context_social_reply"}
    if _hit(low(sig.get("title", "")), sig.get("title", ""), NEWS_MARK):
        return {**base, "noise_type": "news_or_drama"}
    if _hit(blob, raw, MARKET_RESEARCH):
        return {**base, "noise_type": "market_research"}
    if _hit(low(sig.get("title", "")), sig.get("title", ""), DISCUSS) and not seeks_tool:
        return {**base, "noise_type": "discussion"}
    if is_product_link_drop(sig):
        return {**base, "noise_type": "product_link_drop"}
    if is_existing_tool_howto(sig):
        return {**base, "noise_type": "how_to_existing_tool"}
    if is_developer_howto(sig):
        return {**base, "noise_type": "developer_how_to"}
    if st not in ("complaint", "question", "review", "launch", "ranking"):
        return {**base, "noise_type": "unsupported_signal_type"}
    if tier == "C" and not (seeks_tool or gap or has_cost):
        return {**base, "noise_type": "trend_context_only"}

    if has_cost and (seeks_tool or gap or has_workaround):
        reason = "用户已经付出代价，且在寻找更好的工具或流程。"
        workaround = "已有人工/表格/外包/替代工具等凑合方案。" if has_workaround else "已有付费或时间成本。"
        return {**base, "label": "real_need", "should_rank": True, "intent_type": "paid_workaround",
                "purchase_reason": reason, "current_workaround": workaround, "noise_type": ""}
    if seeks_tool and (gap or f["pain"] >= 1):
        return {**base, "label": "possible_need", "should_rank": True, "intent_type": "seeking_tool",
                "purchase_reason": "用户明确在找工具、替代品或自动化方案。",
                "current_workaround": "当前方案不清晰，需要从原帖继续验证。", "noise_type": ""}
    if st == "review" and gap:
        return {**base, "label": "possible_need", "should_rank": True, "intent_type": "negative_review_gap",
                "purchase_reason": "差评指向明确功能缺口或体验成本。",
                "current_workaround": "用户仍在忍受现有产品限制。", "noise_type": ""}
    if tier == "A" and st in ("launch", "ranking") and (has_cost or "mrr" in blob or "revenue" in blob):
        return {**base, "label": "possible_need", "should_rank": True, "intent_type": "commercial_proof",
                "purchase_reason": "已有收入、榜单或增长信号，可作为竞品/需求证据。",
                "current_workaround": "需继续回看用户评论和差评确认痛点。", "noise_type": ""}
    return {**base, "noise_type": "weak_or_discussion"}


def signal_key(sig):
    key = (sig.get("url") or sig.get("id") or "").strip()
    if key:
        return key
    return f"{sig.get('source', '')}:{sig.get('source_label', '')}:{deh(best_title(sig))}"


def semantic_cache_key(sig):
    payload = {
        "version": SEMANTIC_GATE_VERSION,
        "source": sig.get("source", ""),
        "source_label": sig.get("source_label", ""),
        "title": deh(sig.get("title", "")),
        "text": deh(sig.get("text", ""))[:1200],
        "url": sig.get("url", ""),
        "signal_type": sig.get("signal_type", ""),
        "keywords": sorted(str(k).lower() for k in sig.get("keywords", []) if k),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def load_semantic_cache(path=SEMANTIC_GATE_CACHE):
    try:
        if not os.path.exists(path):
            return {}
        data = json.load(open(path, encoding="utf-8"))
        if isinstance(data, dict) and data.get("version") == SEMANTIC_GATE_VERSION:
            entries = data.get("entries", {})
            return entries if isinstance(entries, dict) else {}
        return data if isinstance(data, dict) and "entries" not in data else {}
    except Exception:
        return {}


def save_semantic_cache(cache, path=SEMANTIC_GATE_CACHE):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "version": SEMANTIC_GATE_VERSION,
        "generated_at": now_iso(),
        "count": len(cache),
        "entries": dict(sorted(cache.items(), key=lambda x: x[0])),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=1)


def semantic_gate_cached(sig, cache):
    key = semantic_cache_key(sig)
    rec = cache.get(key)
    if isinstance(rec, dict) and rec.get("version") == SEMANTIC_GATE_VERSION and isinstance(rec.get("gate"), dict):
        return rec["gate"]
    gate = semantic_gate(sig)
    cache[key] = {
        "version": SEMANTIC_GATE_VERSION,
        "input_hash": key,
        "updated_at": now_iso(),
        "source": sig.get("source", ""),
        "source_label": sig.get("source_label", ""),
        "title": deh(best_title(sig))[:160],
        "url": sig.get("url", ""),
        "label": gate["label"],
        "intent_type": gate["intent_type"],
        "noise_type": gate["noise_type"],
        "source_tier": gate["source_tier"],
        "gate": gate,
    }
    return gate


def need_candidate(sig, gate=None):
    # Stage-0 真需求闸：先判"是不是一个可做的真需求"，过闸才进入打分。
    st = sig.get("signal_type")
    src = sig.get("source_label", "")
    gate = gate or sig.get("_gate") or semantic_gate(sig)
    if not gate["should_rank"]:
        return False
    if st not in ("complaint", "question", "review") and not (source_tier(src) == "A" and st in ("launch", "ranking")):
        return False
    title = sig.get("title", "")
    title_low = low(title)
    blob = low(title + " " + sig.get("text", ""))
    raw = title + " " + sig.get("text", "")
    f = sig["_f"]
    seeks_tool = _hit(blob, raw, SEEK_TOOL)

    # 硬剔除：娱乐 / 自我推广广告 / 买物政策灰 / 新闻争议标题 / 讨论观点(且非在找工具)
    if looks_entertainment(sig) and not expresses_gap(sig):
        return False
    if _hit(blob, raw, PROMO):
        return False
    if _hit(blob, raw, BUYADVICE):
        return False
    if _hit(title_low, title, NEWS_MARK):
        return False
    if _hit(title_low, title, DISCUSS) and not seeks_tool:
        return False

    # App 差评：真功能缺口、非娱乐、非正向好评
    if st == "review" or src == "App Store":
        if looks_entertainment(sig) or not expresses_gap(sig):
            return False
        pos = sum(1 for p in POSITIVE if ((p in blob) if p.isascii() else (p in raw)))
        neg = f["pain"] + f["gap"]
        return not (pos > 0 and pos >= neg)

    # Stack Overflow = 纯代码求助，必须明确在找工具/产品才算需求
    if "Stack Overflow" in src:
        return seeks_tool
    if src.startswith("Stack Exchange"):
        return seeks_tool or f["gap"] >= 1 or _hit(blob, raw, FEATURE_GAP)

    # 建设者社区（HN/V2EX/Reddit）：必须在找工具/方案，或有明确功能缺口（不接受纯情绪/讨论）
    if src in BUILDER_SRC:
        return seeks_tool or f["gap"] >= 1 or _hit(blob, raw, FEATURE_GAP)
    return f["pain"] >= 1 or f["gap"] >= 1


def signal_datetime(sig):
    value = sig.get("created_at")
    if not value:
        return None
    try:
        parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = parsedate_to_datetime(str(value))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.timezone.utc)
    return parsed


def is_recent_signal(sig, as_of=None, max_days=30):
    parsed = signal_datetime(sig)
    if not parsed:
        return False
    current = as_of or datetime.datetime.now(datetime.timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=datetime.timezone.utc)
    age = current.astimezone(datetime.timezone.utc) - parsed.astimezone(datetime.timezone.utc)
    return datetime.timedelta(0) <= age <= datetime.timedelta(days=max_days)


def best_title(sig):
    t = clean_title(sig)
    if low(t).strip(" .。!！?？") in GENERIC_TITLES or len(t) < 12:
        text = (sig.get("text") or "").strip().replace("\n", " ")
        for s in re.split(r"[.。!！?？\n]", text):
            sl, raw = low(s), s
            if len(s.strip()) > 12 and any((g in sl) if g.isascii() else (g in raw) for g in FEATURE_GAP):
                return re.sub(r"\s+", " ", s.strip())[:80]
        if len(text) > 12:
            return re.sub(r"\s+", " ", text)[:72]
    return t


def clean_title(sig):
    t = (sig.get("title") or "").strip()
    t = re.sub(r"^(Ask|Show|Tell)\s+HN:\s*", "", t, flags=re.I)
    t = re.sub(r"\s+", " ", t)
    if len(t) < 6:
        body = (sig.get("text") or "").strip()
        if body:
            t = re.split(r"[.。!！?？\n]", body)[0][:70]
    return t or "(无标题)"


def kwset(sig):
    ks = set(k.lower() for k in sig.get("keywords", []) if len(k) >= 2)
    return ks


def cluster(cands):
    # 给每个候选先算一个个体强度分用于排序
    def indiv(sig):
        f = sig["_f"]
        st = sig.get("signal_type")
        base = {"complaint": 3, "question": 2.2, "review": 2.5, "launch": 1.5, "trend": 1.2, "ranking": 1.0}.get(st, 1.0)
        return base + 1.4 * f["pain"] + 0.8 * f["gap"] + 0.6 * f["wtp"] + 0.3 * math.log10(max(0, sig.get("popularity", 0)) + 1) * 3
    cands = sorted(cands, key=indiv, reverse=True)
    clusters = []
    used = [False] * len(cands)
    for i, seed in enumerate(cands):
        if used[i]:
            continue
        sk = kwset(seed)
        members = [seed]
        used[i] = True
        if sk:
            for j in range(i + 1, len(cands)):
                if used[j]:
                    continue
                ok = kwset(cands[j])
                if not ok:
                    continue
                shared = sk & ok
                inter = len(shared)
                jac = inter / max(1, len(sk | ok))
                seed_intent = (seed.get("_gate") or {}).get("intent_type")
                other_intent = (cands[j].get("_gate") or {}).get("intent_type")
                same_intent = bool(seed_intent and seed_intent == other_intent)
                same_source = seed.get("source_label") == cands[j].get("source_label")
                # Conservative by design: generic two-keyword overlap previously
                # merged unrelated image posts into fake multi-source demand.
                # Cross-source corroboration now needs stronger topic identity.
                merge = same_intent and jac >= 0.5 and inter >= (3 if same_source else 4)
                if merge:
                    members.append(cands[j])
                    used[j] = True
                    if len(members) >= 12:
                        break
        clusters.append({"seed": seed, "members": members, "_indiv": indiv(seed)})
    return clusters


def clamp(x, lo=0.0, hi=10.0):
    return max(lo, min(hi, x))


def agg(members, key, how="mean"):
    vals = [m["_f"][key] for m in members]
    if how == "max":
        return max(vals)
    return sum(vals) / len(vals)


def score_cluster(cl):
    ms = cl["members"]
    seed = cl["seed"]
    size = len(ms)
    total_pop = sum(m.get("popularity", 0) for m in ms)
    regions = [m.get("region") for m in ms]
    region = max(set(regions), key=regions.count)
    sources = sorted(set(m.get("source_label") for m in ms))
    types = [m.get("signal_type") for m in ms]

    type_pain = {"complaint": 6.0, "question": 4.2, "review": 5.0, "launch": 3.0, "trend": 2.6, "ranking": 2.4}
    base_pain = max(type_pain.get(t, 3.0) for t in types)
    pain = clamp(base_pain + 1.1 * agg(ms, "pain", "max") + 0.5 * math.log10(max(0, total_pop) + 1) + 0.35 * min(size, 5) - 1.0)

    aud = agg(ms, "aud", "max")
    generic = agg(ms, "generic", "max")
    builder = 1 if any(s in BUILDER_SRC for s in sources) else 0
    narrow = clamp(3.4 + 1.6 * aud - 1.2 * generic + (0.8 if region != "通用" else 0) + 1.3 * builder)

    wtp_mark = agg(ms, "wtp", "max")
    src_bonus = max(SOURCE_REGION_BONUS_WTP.get(s, 0.3) for s in sources)
    region_wtp = {"海外": 2.2, "国内": 0.6, "通用": 1.2}.get(region, 1.0)
    wtp = clamp(2.0 + region_wtp + 1.3 * wtp_mark + 1.2 * src_bonus)

    recur = agg(ms, "recur", "max")
    freq = clamp(3.0 + 1.6 * recur + 0.7 * min(size, 6))

    gap_mark = agg(ms, "gap", "max")
    finder_src = 1 if "Stack Exchange" in sources else 0
    has_q = 1 if "question" in types else 0
    has_c = 1 if "complaint" in types else 0
    gap = clamp(2.9 + 1.8 * gap_mark + 1.0 * finder_src + 0.9 * has_q + 0.4 * has_c)

    tech = agg(ms, "tech", "max")
    cl_kw = set(k.lower() for m in ms for k in m.get("keywords", []))
    alpha_hit = 1 if (cl_kw & ALPHA_KW) else 0
    alpha = clamp(3.4 + 0.9 * tech + 1.8 * alpha_hit)

    # fit：命中用户领域
    blob = low(" ".join((m.get("title", "") + " " + m.get("text", "") + " " + " ".join(m.get("keywords", []))) for m in ms))
    domain_hits = {}
    for dom, words in PROFILE["domains"].items():
        h = sum(1 for w in words if w.lower() in blob)
        if h:
            domain_hits[dom] = h
    fit = clamp(2.0 + 2.6 * (max(domain_hits.values()) if domain_hits else 0) ** 0.6)

    cplx = agg(ms, "complex", "max")
    feasible = clamp(8.0 - 1.6 * cplx + 0.4 * tech)  # 越复杂越低分（feasible 高=低风险）

    dims = {"pain": round(pain, 1), "narrow": round(narrow, 1), "wtp": round(wtp, 1), "freq": round(freq, 1),
            "gap": round(gap, 1), "alpha": round(alpha, 1), "fit": round(fit, 1), "feasible": round(feasible, 1)}
    corro = (2 if size >= 3 else 0) + (3 if size >= 6 else 0) + (2 if len(sources) >= 2 else 0)
    # 可行动性：在找解决方案的信号（提问/找替代/求推荐）更像真需求；纯情绪发泄/争议降权
    seek_kw = ["looking for", "recommend", "alternative", "any tool", "best tool",
               "求推荐", "有没有", "怎么", "如何", "求一个", "求大佬"]
    blob_all = low(" ".join(m.get("title", "") + " " + m.get("text", "") for m in ms))
    solution_seeking = bool(has_q or gap_mark > 0 or finder_src or any(k in blob_all for k in seek_kw))
    total = round(min(99.0, sum(WEIGHTS[k] * dims[k] for k in WEIGHTS) * 10 + corro), 1)
    if not solution_seeking and set(types) <= {"complaint", "review", "discussion"}:
        total = round(max(0.0, total - 6.0), 1)
    if any(m in low(seed.get("title", "")) for m in NEWS_MARK):
        total = round(max(0.0, total - 12.0), 1)

    reasons = []
    if pain >= 6.5: reasons.append("抱怨/痛点信号密集" + (f"（{int(total_pop)} 热度）" if total_pop > 50 else ""))
    if size >= 3: reasons.append(f"{size} 条信号共同指向（{('/'.join(sources))[:40]}）")
    if wtp >= 6.5: reasons.append("付费意愿强" + ("（海外市场）" if region == "海外" else ""))
    if gap >= 6: reasons.append("有明显供给缺口/在找替代")
    if narrow >= 6.5: reasons.append("人群窄而具体，易精准触达")
    if alpha >= 6.5: reasons.append("踩到新技术/趋势窗口")
    if fit >= 6: reasons.append("和你擅长的领域匹配（" + "、".join(domain_hits.keys()) + "）")
    if feasible <= 4: reasons.append("实现偏复杂，周期/风险较高")
    if not reasons: reasons.append("信号偏弱，作为观察项")

    return {"region": region, "sources": sources, "size": size, "total_pop": total_pop,
            "dims": dims, "total": total, "reasons": reasons, "domain_hits": domain_hits}


def verdict(total):
    if total >= 72: return "强烈推荐"
    if total >= 60: return "值得一试"
    if total >= 50: return "谨慎"
    return "过滤"


def infer_audience(cl):
    blob = low(cl["seed"].get("title", "") + " " + cl["seed"].get("text", ""))
    for a in AUDIENCE:
        if a in blob:
            zh = {"developer": "开发者", "dev": "开发者", "engineer": "工程师", "seller": "卖家",
                  "student": "学生", "teacher": "老师", "creator": "创作者", "founder": "创业者",
                  "designer": "设计师", "trader": "交易者", "marketer": "营销人", "freelanc": "自由职业者"}.get(a, a)
            return zh
    return {"海外": "这群海外用户", "国内": "这群国内用户", "通用": "这群用户"}.get(cl["score"]["region"], "这群用户")


def persona_keys():
    return [k for k, v in RUBRIC.items()
            if not k.startswith("_") and isinstance(v, dict) and v.get("weights") and v.get("lenses")]


def persona_profiles():
    profiles = {}
    for key in persona_keys():
        r = RUBRIC[key]
        profiles[key] = {
            "name": r.get("display_name") or key,
            "tag": r.get("tag") or "",
            "avatar": r.get("avatar") or (r.get("display_name") or key)[:1].upper(),
            "source_skill": r.get("source_skill") or "",
        }
    return profiles


def persona_take(persona, sc, audience, pain_phrase, crowded):
    r = RUBRIC[persona]
    weights = r.get("weights", {})
    lenses = r.get("lenses", {})
    pscore = sum(weights.get(k, 0.5) * sc["dims"][k] for k in sc["dims"]) / sum(weights.get(k, 0.5) for k in sc["dims"])
    if crowded and sc["dims"]["gap"] < 5.0:
        lens = lenses.get("crowded") or lenses.get("weak") or lenses.get("strong", "")
    elif pscore >= 6.3 and sc["dims"]["pain"] >= 5.5:
        lens = lenses.get("strong") or lenses.get("weak") or ""
    elif pscore < 4.8:
        lens = lenses.get("weak") or lenses.get("strong") or ""
    else:
        lens = (lenses.get("strong") if pscore >= 5.6 else lenses.get("weak")) or lenses.get("strong") or lenses.get("weak") or ""
    赛道 = "、".join(sc["sources"][:2]) + " 上的这类" if sc["sources"] else "这条"
    return (lens.replace("{人群}", audience).replace("{痛点}", pain_phrase)
            .replace("{赛道}", 赛道).replace("{供给缺口}", "现有方案不够好")
            .replace("{城市}", "").replace("{价格}", ""))


def product_forms(sc, kws_blob):
    region, d = sc["region"], sc["dims"]
    forms = []

    def add(form, score, mon, cost, note):
        forms.append({"form": form, "score": round(clamp(score, 0, 100), 0), "monetization": mon,
                      "build_cost": cost, "note": note})
    feas = d["feasible"]
    base = sc["total"]
    if region == "国内":
        if d["freq"] >= 6:
            add("微信小程序", base + 6, "广告 + 低价会员", "低", "微信生态分享裂变，用完即走")
        add("Web App", base, "订阅", "中" if feas < 6 else "低", "迭代快、获客成本低")
        if d["pain"] >= 7 and d["freq"] < 6:
            add("服务产品化", base + 4, "高客单陪跑", "中", "痛点强但低频，用服务+结果交付变现")
        add("微信公众号/社群", base - 8, "私域转化", "低", "先做内容验证需求再上工具")
    else:
        add("Web App", base + 2, "订阅", "中" if feas < 6 else "低", "跨平台、获客成本最低、迭代最快")
        if "extension" in kws_blob or "browser" in kws_blob or d["narrow"] >= 6:
            add("Chrome 扩展", base, "订阅", "低", "嵌入用户工作流，分发靠商店、审核快")
        add("API/服务", base - 4, "按量计费", "低" if feas >= 6 else "中", "嵌入别人的产品/工作流")
        if d["pain"] >= 7 and d["freq"] < 5:
            add("服务产品化", base + 2, "高客单", "中", "高痛低频，结果交付比纯工具更值钱")
    # 去重 + 按分排序 + 取前 4
    seen = set()
    uniq = []
    for f in sorted(forms, key=lambda x: -x["score"]):
        if f["form"] in seen:
            continue
        seen.add(f["form"])
        uniq.append(f)
    return uniq[:4]


def build_opportunity(cl, sc, title, summary, audience, forms):
    seed = cl["seed"]
    gate = seed.get("_gate") or semantic_gate(seed)
    best_form = forms[0]["form"] if forms else "Web App"
    tier = gate["source_tier"]
    if gate["purchase_reason"]:
        purchase_reason = gate["purchase_reason"]
    elif sc["dims"]["gap"] >= 6:
        purchase_reason = "现有方案缺口明显，用户正在寻找替代或更省事的流程。"
    elif sc["dims"]["pain"] >= 6:
        purchase_reason = "痛点强度较高，用户为减少麻烦存在付费可能。"
    else:
        purchase_reason = "购买理由仍偏弱，需要继续验证是否愿意付出代价。"

    current_workaround = gate["current_workaround"] or "暂未从证据中确认当前替代方案，需要继续追问。"
    scenario = summary.rstrip("。.") or f"{audience}遇到这个问题。"
    mvp = f"先做一个{best_form}，只解决「{title[:34]}」这一条工作流。"
    validation = "找 5 个同类用户，用假界面或人工服务验证是否愿意付费/留邮箱/预约试用。"
    if tier == "A":
        validation = "先拆竞品评论和收入来源，再验证用户为什么愿意从现有方案切换。"
    elif tier == "C":
        validation = "先用搜索量/讨论量斜率确认起势，再找抱怨源补足购买理由。"

    return {
        "status": "new",
        "who": audience,
        "scenario": scenario,
        "purchase_reason": purchase_reason,
        "current_workaround": current_workaround,
        "mvp": mvp,
        "validation": validation,
        "intent_type": gate["intent_type"],
        "semantic_label": gate["label"],
        "source_tier": tier,
        "source_tier_label": source_tier_label(tier),
    }


def build_need(cl, idx):
    sc = score_cluster(cl)
    cl["score"] = sc
    seed = cl["seed"]
    title = deh(best_title(seed))
    audience = infer_audience(cl)
    body = deh(seed.get("text") or "")
    summary = (body[:90] + "…") if len(body) > 90 else (body or f"{audience}在{('/'.join(sc['sources'])[:24])}上反复反映这个问题。")
    has_cjk = bool(re.search(r"[一-鿿]", title))
    pain_phrase = (title[:20] if has_cjk else "这个痛点")
    crowded = sc["dims"]["gap"] < 4.5 and sc["dims"]["alpha"] < 5
    kws_blob = low(" ".join(seed.get("keywords", [])) + " " + title)
    forms = product_forms(sc, kws_blob)
    source_tiers = sorted(set(source_tier(m.get("source_label", "")) for m in cl["members"]),
                          key=lambda x: SOURCE_TIER_RANK.get(x, 9))
    evidence = []
    for m in sorted(cl["members"], key=lambda x: -x.get("popularity", 0))[:5]:
        evidence.append({"title": deh(best_title(m)), "url": m.get("url", ""),
                         "source_label": m.get("source_label", ""), "popularity": m.get("popularity", 0),
                         "created_at": m.get("created_at", ""),
                         "source_tier": source_tier(m.get("source_label", "")),
                         "source_tier_label": source_tier_label(source_tier(m.get("source_label", "")))})
    return {
        "id": f"need-{idx:03d}",
        "title": title,
        "summary": summary,
        "region": sc["region"],
        "sources": sc["sources"],
        "source_tiers": source_tiers,
        "source_tier_labels": [source_tier_label(t) for t in source_tiers],
        "signal_count": sc["size"],
        "evidence": evidence,
        "demand_score": {"total": sc["total"], "dims": sc["dims"], "reasons": sc["reasons"]},
        "personas": {key: persona_take(key, sc, audience, pain_phrase, crowded) for key in persona_keys()},
        "opportunity": build_opportunity(cl, sc, title, summary, audience, forms),
        "product_forms": forms,
        "recommendation": make_reco(sc),
        "verdict_label": verdict(sc["total"]),
    }


def make_reco(sc):
    d = sc["total"]
    top_dim = max(sc["dims"], key=lambda k: sc["dims"][k])
    dim_zh = {"pain": "痛点强", "narrow": "人群精准", "wtp": "付费意愿强", "freq": "高频", "gap": "供给缺口大",
              "alpha": "踩中趋势窗口", "fit": "和你能力匹配", "feasible": "实现门槛低"}[top_dim]
    if d >= 72:
        return f"强信号：{dim_zh}，建议优先验证（先口喷个假界面问真实用户是否买单）。"
    if d >= 60:
        return f"值得一试：{dim_zh}，但先做最小验证确认有人愿付代价再投入。"
    if d >= 50:
        return f"谨慎：{dim_zh}，但整体信号一般，先观察或找更窄切入点。"
    return "信号偏弱，列为观察项，暂不投入。"


WATCH_SOURCES = {"小红书", "X/Twitter", "TikTok", "抖音热点", "抖音热榜", "Bilibili", "哔哩哔哩", "微博热搜"}
HARD_WATCH_NOISE = {"promotion", "product_link_drop", "entertainment", "market_research", "developer_how_to",
                    "how_to_existing_tool", "buy_advice_or_policy_gray", "consumer_buy_advice",
                    "creator_roundup", "low_context_social_reply", "news_or_drama"}


def is_watch_source(sig):
    src = sig.get("source", "")
    label = sig.get("source_label", "")
    return src.startswith("opencli_") or label in WATCH_SOURCES


def watch_reason(sig, gate, is_candidate):
    if is_candidate:
        return "候选信号：有需求语言，但分数、聚类或去重后未进入主榜，先观察。"
    if gate["source_tier"] == "A" and sig.get("signal_type") in ("launch", "ranking"):
        return "商业上下文：已有发布、榜单或分发证据，但还缺具体抱怨、差评或付费理由。"
    if gate["source_tier"] == "C" and sig.get("signal_type") in ("trend", "launch", "ranking"):
        return "趋势上下文：技术或工具热度在上升，需要补用户抱怨、搜索或购买证据。"
    if gate["source_tier"] == "D":
        return "趋势背景：泛热榜源，只提示热度方向，需要补抱怨、求助或付费证据。"
    if gate["noise_type"]:
        return f"下沉原因：{gate['noise_type']}，目前缺少明确购买理由。"
    return "观察项：信号不够强，需要继续补证据。"


def watch_summary(sig):
    body = deh(sig.get("text") or "")
    title = deh(best_title(sig))
    text = body or title
    if len(text) > 130:
        return text[:127].rstrip() + "..."
    return text


def build_watchlist(signals, used_keys, limit=24):
    rows = []
    seen = set()
    for sig in signals:
        key = signal_key(sig)
        if key in used_keys or key in seen:
            continue
        seen.add(key)
        gate = sig.get("_gate") or semantic_gate(sig)
        candidate = gate["should_rank"] and need_candidate(sig, gate)
        commercial_context = gate["source_tier"] == "A" and sig.get("signal_type") in ("launch", "ranking")
        trend_context = gate["source_tier"] == "C" and sig.get("signal_type") in ("trend", "launch", "ranking")
        background = gate["source_tier"] == "D" and sig.get("signal_type") == "trend" and sig.get("popularity", 0) >= 20
        if not (candidate or commercial_context or trend_context or background or (is_watch_source(sig) and gate["label"] != "noise")):
            continue
        if not (commercial_context or trend_context or background) and gate["noise_type"] in HARD_WATCH_NOISE:
            continue
        rows.append({
            "id": sig.get("id") or key,
            "title": deh(best_title(sig)),
            "summary": watch_summary(sig),
            "source": sig.get("source", ""),
            "source_label": sig.get("source_label", ""),
            "region": sig.get("region", ""),
            "url": sig.get("url", ""),
            "popularity": sig.get("popularity", 0),
            "comments": sig.get("comments", 0),
            "signal_type": sig.get("signal_type", ""),
            "gate": gate["label"],
            "intent_type": gate["intent_type"],
            "noise_type": gate["noise_type"],
            "source_tier": gate["source_tier"],
            "source_tier_label": gate["source_tier_label"],
            "reason": watch_reason(sig, gate, candidate),
        })

    gate_order = {"real_need": 0, "possible_need": 1, "noise": 2}
    rows.sort(key=lambda x: (
        gate_order.get(x["gate"], 3),
        SOURCE_TIER_RANK.get(x["source_tier"], 9),
        -float(x.get("popularity") or 0),
        x["title"],
    ))
    for i, row in enumerate(rows[:limit], start=1):
        row["id"] = f"watch-{i:03d}"
    return rows[:limit]


def attach_attention(payload, signals, profile=None, history_dir=HISTORY, as_of=None):
    previous = load_previous_snapshot(history_dir, as_of=as_of)
    attention = build_attention(
        payload.get("needs", []),
        signals,
        profile or PROFILE,
        previous=previous,
        as_of=as_of,
    )
    need_ids = {row.get("need_id"): row["stable_id"] for row in attention["items"] if row.get("need_id")}
    for need in payload.get("needs", []):
        need["stable_id"] = need_ids.get(need.get("id")) or stable_id(
            "need",
            next((row.get("url") for row in need.get("evidence", []) if row.get("url")), ""),
            need.get("title", ""),
            (need.get("sources") or [""])[0],
        )
    for row in payload.get("watchlist", []):
        row["stable_id"] = stable_id(
            "watch",
            row.get("url", ""),
            row.get("title", ""),
            row.get("source_label") or row.get("source", ""),
        )
    payload["attention"] = attention
    payload["history"] = save_snapshot(attention, history_dir, as_of=as_of)
    return payload


def main():
    files = filter_raw_files(glob.glob(os.path.join(RAW, "*.json")), RUN_MODE)
    signals = []
    stats = {}
    gate_counts = {}
    noise_counts = {}
    tier_counts = {}
    gate_cache = load_semantic_cache()
    for fp in files:
        d = json.load(open(fp, encoding="utf-8"))
        for s in d.get("signals", []):
            sig = featurize(s)
            signals.append(sig)
            gate = semantic_gate_cached(sig, gate_cache)
            sig["_gate"] = gate
            gate_counts[gate["label"]] = gate_counts.get(gate["label"], 0) + 1
            if gate["noise_type"]:
                noise_counts[gate["noise_type"]] = noise_counts.get(gate["noise_type"], 0) + 1
            tier_counts[gate["source_tier_label"]] = tier_counts.get(gate["source_tier_label"], 0) + 1
        if d.get("signals"):
            lbl = d["signals"][0].get("source_label", d.get("source"))
            stats[lbl] = d.get("count", len(d["signals"]))
    global ALPHA_KW
    for s in signals:
        if s.get("signal_type") in ("launch", "trend") and s["_f"]["tech"] >= 1 and s["_f"]["ent"] == 0:
            for k in s.get("keywords", []):
                if len(k) >= 3:
                    ALPHA_KW.add(k.lower())
    cands = [s for s in signals if need_candidate(s, s.get("_gate")) and is_recent_signal(s)]
    stale_candidates = sum(1 for s in signals if need_candidate(s, s.get("_gate")) and not is_recent_signal(s))
    print(f"signals={len(signals)} demand_candidates={len(cands)} alpha_kw={len(ALPHA_KW)}")
    clusters = cluster(cands)
    scored = []
    for cl in clusters:
        sc = score_cluster(cl)
        if sc["total"] < 50:
            continue
        scored.append((sc["total"], cl))
    scored.sort(key=lambda x: -x[0])
    built, seen_titles = [], []
    used_keys = set()
    for _, cl in scored:
        n = build_need(cl, len(built) + 1)
        tl = low(n["title"]).strip(" .。!！?？")
        if len(n["title"]) < 10 or tl in GENERIC_TITLES:
            continue
        tw = set(re.findall(r"[a-z0-9]{2,}|[一-龥]{2,}", tl))
        if tw and any(len(tw & sw) / max(1, len(tw | sw)) > 0.6 for sw in seen_titles):
            continue
        seen_titles.append(tw)
        built.append(n)
        for member in cl["members"]:
            used_keys.add(signal_key(member))
        if len(built) >= 40:
            break
    for i, n in enumerate(built):
        n["id"] = f"need-{i + 1:03d}"
    watchlist = build_watchlist(signals, used_keys, limit=24)
    out = {"generated_at": now_iso(), "source_stats": stats,
           "meta": {"signals": len(signals), "candidates": len(cands), "clusters": len(clusters), "needs": len(built),
                    "watchlist": len(watchlist),
                    "stale_candidates_excluded": stale_candidates,
                    "weights": WEIGHTS, "mode": "deterministic", "run_mode": RUN_MODE,
                    "stage": "phase2_strict_purchase_reason_gate",
                    "gate_counts": dict(sorted(gate_counts.items(), key=lambda x: x[0])),
                    "noise_counts": dict(sorted(noise_counts.items(), key=lambda x: (-x[1], x[0]))),
                    "source_tier_counts": dict(sorted(tier_counts.items(), key=lambda x: x[0])),
                    "source_tier_labels": SOURCE_TIER_LABELS,
                    "semantic_gate_cache": {"path": "data/cache/semantic_gate.json",
                                            "entries": len(gate_cache),
                                            "mode": "deterministic_cache",
                                            "llm_enabled": False},
                    "persona_profiles": persona_profiles(),
                    "personas_note": "名人点评为模板生成的「参考语气」，非核心判断；决策请以八维分与证据原帖为准。"},
           "needs": built, "watchlist": watchlist}
    out = attach_attention(out, signals, PROFILE, HISTORY)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    save_semantic_cache(gate_cache)
    print(f"wrote {len(built)} needs -> {OUT}")
    print(f"watchlist={len(watchlist)} cache_entries={len(gate_cache)}")
    for n in built[:12]:
        print(f"  {n['demand_score']['total']:5.1f} {n['verdict_label']:>4} [{n['region']}] {n['title'][:56]}")


if __name__ == "__main__":
    main()
