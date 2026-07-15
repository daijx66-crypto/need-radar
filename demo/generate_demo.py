#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generate_demo.py — 需求雷达 Phase 2：把一条需求 → 一个苹果极简风落地页 demo。

读 data/needs.json，取 needs[0]（或 CLI 传入的 need id），映射进 demo/template.html
的占位符，输出自包含单文件到 demo/out/<need-id>/index.html。

  python3 demo/generate_demo.py            # 默认生成 needs[0]
  python3 demo/generate_demo.py need-003   # 指定某条需求
  python3 demo/generate_demo.py --all      # 全部需求各生成一页

文案策略：默认走「确定性」分支（无网络、可复现）；若设置 ANTHROPIC_API_KEY，
则调用 Anthropic Messages API 把 hero/特性/why-now 写得更地道（失败自动回落确定性）。
纯标准库，零依赖。
"""
import os, sys, json, re, html, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO_DIR = os.path.join(ROOT, "demo")
NEEDS = os.path.join(ROOT, "data", "needs.json")
TEMPLATE = os.path.join(DEMO_DIR, "template.html")
OUT_DIR = os.path.join(DEMO_DIR, "out")

KEY = os.environ.get("ANTHROPIC_API_KEY")
MODEL = os.environ.get("NEED_RADAR_MODEL", "claude-sonnet-4-6")
API = "https://api.anthropic.com/v1/messages"

# 维度中文名（来自 SCHEMA：八维）
DIM_LABEL = {
    "pain": "痛点强度", "narrow": "人群精准", "wtp": "付费意愿", "freq": "重复频次",
    "gap": "供给缺口", "alpha": "趋势窗口", "fit": "能力匹配", "feasible": "实现可行",
}
# 变现方式 → 一句话定价说明
MONET_NOTE = {
    "订阅": "按月订阅，随时取消。先用免费额度验证价值，再决定是否升级。",
    "按量计费": "按调用量计费，用多少付多少，没有起步门槛。",
    "广告 + 低价会员": "基础功能免费，去广告 + 解锁高级特性走低价会员。",
    "私域转化": "内容免费，深度陪跑与定制方案单独报价。",
    "高客单": "面向结果交付定价，一次投入换一套可复用的资产。",
    "高客单陪跑": "陪跑制：按结果与里程碑收费，做不出来不收尾款。",
}


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------
def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def clean_title(raw):
    """把原帖标题压成一个干净的产品名（≤14 字 / 词）。"""
    t = (raw or "").strip()
    t = re.sub(r"^\s*[\[【(（].*?[\]】)）]\s*", "", t)      # 去前缀标签
    t = re.sub(r"[?？.!！。…]+$", "", t).strip()
    return t


def pct(x10):
    """0-10 维度分 → 百分比整数。"""
    try:
        return max(4, min(100, round(float(x10) * 10)))
    except Exception:
        return 0


def top_dims(dims, n=4):
    return sorted(dims.items(), key=lambda kv: -kv[1])[:n]


# 主题关键词 → 一个干净、好读的产品名（用于过长/英文标题的兜底）
THEME_BRAND = [
    (("saas", "indie", "profitable", "one-person", "side"), "MicroSaaS"),
    (("automation", "automate", "workflow", "zapier", "n8n"), "FlowKit"),
    (("claude", "llm", "gpt", "ai 助手", "agent", "prompt", "vibe coding"), "AgentDesk"),
    (("email", "邮件", "mail"), "InboxOne"),
    (("svg", "drawing", "封面", "屏保", "animation", "设计"), "Canvas"),
    (("vps", "线路", "chromium", "browser", "claudevm"), "DevBox"),
    (("laravel", "controller", "架构", "self-taught", "tools"), "DevStack"),
]


def derive_product(title, summary, top_form):
    """从需求里提炼一个 ≤24 字的干净产品名。短中文标题直接用；长/英文标题走主题词兜底。"""
    t = clean_title(title)
    # 短且可读（不是一长串英文从句）直接用作产品名
    if 0 < len(t) <= 22 and not re.search(r"\bis\b|\bwhat\b|\bhow\b|\bshould\b", t, re.I):
        return t
    blob = (title + " " + (summary or "")).lower()
    for keys, brand in THEME_BRAND:
        if any(k.lower() in blob for k in keys):
            return brand
    return (top_form.get("form", "Web App") or "Web App")


# ---------------------------------------------------------------------------
# 确定性文案：把一条 Need 映射成「产品落地页」语言
# ---------------------------------------------------------------------------
def build_copy(need):
    title = clean_title(need.get("title", ""))
    summary = (need.get("summary", "") or "").strip()
    region = need.get("region", "通用")
    dims = need.get("demand_score", {}).get("dims", {})
    total = need.get("demand_score", {}).get("total", 0)
    forms = need.get("product_forms", []) or []
    top_form = forms[0] if forms else {"form": "Web App", "monetization": "订阅", "note": ""}
    sources = "、".join(need.get("sources", []) or []) or "公开社区"
    sig = need.get("signal_count", 0)
    evid = need.get("evidence", []) or []
    pop = sum(max(0, e.get("popularity", 0) or 0) for e in evid)
    reasons = need.get("demand_score", {}).get("reasons", []) or []

    # 产品名：从需求提炼出一个干净的品牌名
    product = derive_product(need.get("title", ""), summary, top_form)
    # hero 价值主张：从痛点翻成「不再为 X 发愁」式的承诺
    hero, subhead = _hero(product, title, summary, region, dims, top_form)

    # 三个特性：top product_forms + 高分维度，翻成卖点
    feats = _features(forms, dims, region, evid)

    # 如何运作 3 步：从「发现需求 → 验证 → 上线」叙事
    steps = _steps(top_form, region)

    # why now：alpha / gap / 痛点信号
    why_title, why_now, why_points = _why_now(dims, reasons, region, pop, sig, sources)

    # 定价：从 monetization
    price, price_per, plan_name, plan_feats, price_note = _pricing(top_form, region)

    money_count = sum(1 for k in ("pain", "wtp", "gap", "narrow") if dims.get(k, 0) >= 6)

    return {
        # 顶栏 / hero
        "PRODUCT": product,
        "HERO_TAG": f"来自真实信号 · 需求强度 {total:.0f}/100",
        "HERO": hero,
        "SUBHEAD": subhead,
        "CTA": "免费开始" if region != "国内" else "免费试用",
        "CTA_SECONDARY": "看看怎么用",
        "PROOF_1_NUM": f"{total:.0f}", "PROOF_1_LABEL": "需求强度分",
        "PROOF_2_NUM": (f"{pop:,}" if pop else str(sig)), "PROOF_2_LABEL": "条真实信号热度" if pop else "条社区信号",
        "PROOF_3_NUM": f"{pct(dims.get('wtp',0))}%", "PROOF_3_LABEL": "付费意愿指数",
        # 特性
        "FEATURES_EYEBROW": "为什么是它",
        "FEATURES_TITLE": "把一个真实痛点，做成一件趁手的工具",
        "FEATURES_SUB": "不是又一个大而全的平台。只解决一件被反复抱怨、且有人愿意为之付费的事。",
        "FEATURE_1_TITLE": feats[0][0], "FEATURE_1_DESC": feats[0][1], "FEATURE_1_META": feats[0][2],
        "FEATURE_2_TITLE": feats[1][0], "FEATURE_2_DESC": feats[1][1], "FEATURE_2_META": feats[1][2],
        "FEATURE_3_TITLE": feats[2][0], "FEATURE_3_DESC": feats[2][1], "FEATURE_3_META": feats[2][2],
        # 如何运作
        "HOW_EYEBROW": "如何运作",
        "HOW_TITLE": "三步，从注册到拿到结果",
        "HOW_SUB": "没有冗长的引导，没有学习曲线。打开就能用。",
        "STEP_1_TITLE": steps[0][0], "STEP_1_DESC": steps[0][1],
        "STEP_2_TITLE": steps[1][0], "STEP_2_DESC": steps[1][1],
        "STEP_3_TITLE": steps[2][0], "STEP_3_DESC": steps[2][1],
        # why now
        "WHY_EYEBROW": "为什么是现在",
        "WHY_TITLE": why_title,
        "WHY_NOW": why_now,
        "WHY_POINT_1": why_points[0], "WHY_POINT_2": why_points[1], "WHY_POINT_3": why_points[2],
        "GAUGE_TITLE": "需求强度 · 八维拆解",
        # gauge 用 top4 维度
        **_gauge_fields(dims),
        # 定价
        "PRICE_EYEBROW": "定价",
        "PRICE_TITLE": "先用起来，值了再付费",
        "PRICE_SUB": "海外靠真金白银验证需求，国内靠流量跑通模型——先把第一个愿意掏钱的人找到。" if region == "海外"
                     else "先把模型跑通、把人留住，再谈变现。",
        "PLAN_NAME": plan_name, "PRICE": price, "PRICE_PER": price_per,
        "PRICE_NOTE": price_note,
        "PLAN_FEAT_1": plan_feats[0], "PLAN_FEAT_2": plan_feats[1], "PLAN_FEAT_3": plan_feats[2],
        "PRICE_FOOTNOTE": "无需绑卡 · 随时取消 · 这是一个用于验证需求的早期 demo",
        # 页脚
        "FOOTER_NOTE": f"本页由「需求雷达」依据 {sources} 的 {sig} 条真实信号自动生成，"
                       f"用于验证「{title}」这个方向是否值得做。",
        "EVIDENCE_LINE": _evidence_line(evid),
        "FOOTER_META": f"NEED · {esc(need.get('id',''))} · {region} · 强度 {total:.0f}",
    }


def _hero(product, title, summary, region, dims, top_form):
    """把痛点翻成价值主张：大标题给承诺，副标给语境。"""
    blob = (title + " " + (summary or "")).lower()
    # 主题命中 → 量身定制的承诺式大标题（HTML，含一个 grad 高亮短语）
    themed = [
        (("saas", "profitable", "indie", "one-person", "side hustle", "$500", "500$"),
         ('一个人，<span class="grad">也能做出赚钱的小产品</span>',
          "别再为「做什么」发愁。从真实的社区抱怨里，找到第一个愿意付费的小而美需求。")),
        (("automation", "automate", "workflow", "zapier", "n8n"),
         ('把重复的活，<span class="grad">交给会自己跑的流程</span>',
          "那些每天手动重复的琐事，连成一条自动运转的流水线。设一次，之后忘了它。")),
        (("claude", "llm", "gpt", "agent", "prompt", "vibe coding", "ai 助手"),
         ('让 AI 真正<span class="grad">听懂你想要什么</span>',
          "不是又一个聊天框。把你的真实工作流接进来，让它替你把事做完，而不只是给建议。")),
        (("email", "邮件", "mail"),
         ('所有邮箱，<span class="grad">收进同一个清爽的窗口</span>',
          "不用再在好几个网页之间反复横跳。一个干净、好看、顺手的客户端，收发都在这里。")),
    ]
    for keys, (h, s) in themed:
        if any(k in blob for k in keys):
            return h, s
    # 通用承诺式兜底（仍然像产品页，不像占位符）
    hero = f'{product}，<span class="grad">把一件事做到位</span>'
    sub = summary if summary and len(summary) <= 64 else \
        f"围绕这个被反复提起的需求，我们只做一件事——把它做对。先用起来，值了再说。"
    if len(sub) > 88:
        sub = sub[:84].rstrip() + "…"
    return hero, sub


def _features(forms, dims, region, evid):
    """3 个卖点：优先用 product_forms 的形态/变现/note，配合高分维度。"""
    base = []
    for f in forms[:3]:
        form = f.get("form", "Web App")
        note = f.get("note", "")
        monet = f.get("monetization", "")
        title_map = {
            "Web App": "打开网页就能用",
            "Chrome 扩展": "嵌进你的浏览器",
            "API/服务": "一行调用接入",
            "微信小程序": "扫一扫即用，用完即走",
            "微信公众号/社群": "在你已有的场里转化",
            "服务产品化": "结果交付，不止给工具",
            "移动 App": "随手就能打开",
        }
        desc_map = {
            "Web App": "跨平台、零安装。注册即用，迭代飞快，获客成本最低。",
            "Chrome 扩展": "在你日常浏览的页面上直接起效，不打断现有工作流。",
            "API/服务": "把能力嵌进你自己的产品或工作流，按需调用。",
            "微信小程序": "微信生态内分享裂变，不用下载、不占内存。",
            "微信公众号/社群": "先用内容验证需求，再把工具递到真正需要的人手里。",
            "服务产品化": "痛点强、低频的事，交付结果比交付工具更值钱。",
            "移动 App": "把它放进口袋，随时随地解决问题。",
        }
        base.append((
            title_map.get(form, form),
            note or desc_map.get(form, "围绕这个需求做到位的一种产品形态。"),
            f"{form} · {monet}".strip(" ·"),
        ))
    # 不足 3 个用高分维度补
    dim_feat = {
        "narrow": ("人群窄而精准", "不讨好所有人。只服务那一小群把它当真问题、愿意为之买单的人。", "精准触达"),
        "wtp": ("有人愿意掏钱", "这不是叶公好龙的伪需求——信号里能看到真实的付费意愿。", "付费意愿强"),
        "pain": ("痛点足够尖锐", "被反复抱怨、反复求助的真痛点，不是问卷里编出来的需要。", "高痛点"),
        "feasible": ("一个人就能做", "实现门槛低、风险可控，独立开发者用 AI 编程就能跑通。", "低门槛"),
        "gap": ("现有方案不够好", "市面上要么没人做对，要么都在找替代——供给缺口就是机会。", "供给缺口"),
        "alpha": ("踩在趋势窗口上", "新技术 / 新平台刚打开的红利期，早一步就是优势。", "趋势窗口"),
    }
    for k, _v in top_dims(dims, 6):
        if len(base) >= 3:
            break
        if k in dim_feat:
            base.append(dim_feat[k])
    while len(base) < 3:
        base.append(("做到位的一件事", "只留一个核心动作，把别的全部砍掉。", "克制"))
    return base[:3]


def _steps(top_form, region):
    form = top_form.get("form", "Web App")
    enter = {
        "微信小程序": "微信扫码", "Chrome 扩展": "一键安装扩展",
        "API/服务": "拿到 API Key",
    }.get(form, "打开网页注册")
    return [
        (f"{enter}", "30 秒内开始，不用配置、不用看教程。第一次用就知道它解决什么。"),
        ("说出你的问题", "用最自然的方式描述你卡在哪。它替你把模糊的需求收拢成清晰的下一步。"),
        ("拿到能用的结果", "不是一堆建议，而是可以直接落地的产出。值了，再决定要不要长期用。"),
    ]


def _why_now(dims, reasons, region, pop, sig, sources):
    alpha = dims.get("alpha", 0)
    gap = dims.get("gap", 0)
    pain = dims.get("pain", 0)
    if alpha >= 6:
        title = "窗口正开着，但不会一直开"
        body = ("AI 编程把「一个人做出一个可付费产品」的成本压到了历史最低。"
                "同样的需求，三年前要一个团队、半年时间，现在一个人、一个周末就能验证。"
                "早进场的人，吃的是工具红利。")
    elif gap >= 5:
        title = "需求一直在，好用的供给却没跟上"
        body = ("这不是一个新冒出来的需求——它被反复提起，说明痛是真的、持续的。"
                "缺的从来不是需求，是有人愿意把它认真做对。现在轮到你。")
    else:
        title = "真实的抱怨，就是最好的需求来源"
        body = (f"这条方向不是拍脑袋想出来的，而是从 {sources} 的 {sig} 条真实抱怨里"
                "收拢出来的。需求倒做：先看人怎么抱怨，再去做产品。")
    points = []
    if pain >= 6:
        points.append("痛点被反复提起，不是一次性的情绪")
    if dims.get("wtp", 0) >= 6:
        points.append("信号里能看到真实的付费意愿")
    if dims.get("narrow", 0) >= 6:
        points.append("人群窄而具体，第一批用户好找")
    if alpha >= 6:
        points.append("踩在新技术 / 新平台的红利窗口上")
    if gap >= 5:
        points.append("现有方案不够好，替代空间明显")
    generic = ["边际成本近零，做一个和做一万个力气差不多",
               "无需许可即可开始，今天就能验证", "越窄越好，先服务好一小群人"]
    for g in generic:
        if len(points) >= 3:
            break
        if g not in points:
            points.append(g)
    return title, body, points[:3]


def _gauge_fields(dims):
    rows = top_dims(dims, 4)
    out = {}
    for i, (k, v) in enumerate(rows, 1):
        out[f"GAUGE_{i}_LBL"] = DIM_LABEL.get(k, k)
        out[f"GAUGE_{i}_PCT"] = str(pct(v))
        out[f"GAUGE_{i}_VAL"] = f"{v:.1f}"
    # 不足 4 行兜底
    for i in range(len(rows) + 1, 5):
        out[f"GAUGE_{i}_LBL"] = "—"
        out[f"GAUGE_{i}_PCT"] = "0"
        out[f"GAUGE_{i}_VAL"] = "0.0"
    return out


def _pricing(top_form, region):
    monet = top_form.get("monetization", "订阅")
    note = MONET_NOTE.get(monet, "先免费用起来，值了再升级。")
    if region == "海外":
        price, per, plan = "$9", "/月", "Starter"
        feats = ["核心功能全部解锁", "无限次使用，不限量", "首批用户锁定早鸟价"]
    elif "按量" in monet:
        price, per, plan = "¥0.1", "/次", "按量"
        feats = ["用多少付多少，无起步费", "前 100 次免费", "可嵌入你自己的产品"]
    elif "广告" in monet or "私域" in monet:
        price, per, plan = "免费", "起", "免费版"
        feats = ["基础功能永久免费", "去广告 + 高级特性走会员", "微信内一键分享"]
    else:
        price, per, plan = "¥19", "/月", "会员"
        feats = ["核心功能全部解锁", "不限次数使用", "首批用户半价"]
    return price, per, plan, feats, note


def _evidence_line(evid):
    if not evid:
        return "证据来源：公开社区信号。"
    e = evid[0]
    t = esc(clean_title(e.get("title", ""))[:48])
    url = e.get("url", "#")
    lab = esc(e.get("source_label", ""))
    return f"代表证据：<a href=\"{esc(url)}\" target=\"_blank\" rel=\"noopener\">{t}</a> · {lab}"


# ---------------------------------------------------------------------------
# 可选 LLM 增强（填 key 即开，失败回落确定性）
# ---------------------------------------------------------------------------
LLM_SYS = """你是资深产品文案与落地页操盘手，服务一位用 AI 编程找可付费需求的独立开发者。
请把一条来自真实社区抱怨的需求，改写成一个苹果极简风产品落地页的核心文案。
风格：克制、自信、说人话、不堆形容词、不喊口号、价值主张一句话说清。
只输出 JSON，不要任何多余文字。"""


def llm_polish(need, copy):
    if not KEY:
        return copy
    prompt = f"""需求标题：{need.get('title','')}
摘要：{need.get('summary','')}
地区：{need.get('region','')}  主形态：{(need.get('product_forms') or [{{}}])[0].get('form','')}
当前确定性文案（请在此基础上润色，使其更地道、更像真实苹果产品页）：
HERO（含一个 <span class="grad"> 高亮短语，HTML 片段）：{copy['HERO']}
SUBHEAD：{copy['SUBHEAD']}
特性1标题/描述：{copy['FEATURE_1_TITLE']} / {copy['FEATURE_1_DESC']}
特性2标题/描述：{copy['FEATURE_2_TITLE']} / {copy['FEATURE_2_DESC']}
特性3标题/描述：{copy['FEATURE_3_TITLE']} / {copy['FEATURE_3_DESC']}
WHY_NOW：{copy['WHY_NOW']}

只输出 JSON：
{{"HERO":"...","SUBHEAD":"≤40字","FEATURE_1_TITLE":"≤10字","FEATURE_1_DESC":"≤40字",
  "FEATURE_2_TITLE":"≤10字","FEATURE_2_DESC":"≤40字","FEATURE_3_TITLE":"≤10字",
  "FEATURE_3_DESC":"≤40字","WHY_NOW":"≤90字"}}"""
    try:
        body = json.dumps({"model": MODEL, "max_tokens": 900, "system": LLM_SYS,
                           "messages": [{"role": "user", "content": prompt}]}).encode("utf-8")
        req = urllib.request.Request(API, data=body, headers={
            "x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read())
        txt = "".join(b.get("text", "") for b in d.get("content", []) if b.get("type") == "text")
        patch = json.loads(txt[txt.find("{"): txt.rfind("}") + 1])
        for k, v in patch.items():
            if k in copy and isinstance(v, str) and v.strip():
                copy[k] = v.strip()
        print("  · LLM 文案增强成功")
    except Exception as e:
        print("  · LLM 增强失败，回落确定性文案：", e)
    return copy


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------
# 允许保留 HTML 的字段（hero 含 <span class=grad>、页脚含 <a>）
RAW_FIELDS = {"HERO", "FOOTER_NOTE", "EVIDENCE_LINE"}


def render(template, copy):
    out = template
    for k, v in copy.items():
        token = "{{" + k + "}}"
        val = v if k in RAW_FIELDS else esc(v)
        out = out.replace(token, str(val))
    # 兜底：任何残留占位符替换为空，避免页面出现 {{...}}
    leftovers = re.findall(r"\{\{[A-Z0-9_]+\}\}", out)
    if leftovers:
        print("  ! 警告：仍有未替换占位符：", sorted(set(leftovers)))
        out = re.sub(r"\{\{[A-Z0-9_]+\}\}", "", out)
    return out


def generate(need, template):
    nid = need.get("id", "need")
    print(f"→ 生成 {nid}：{clean_title(need.get('title',''))[:36]}")
    copy = build_copy(need)
    copy = llm_polish(need, copy)
    html_out = render(template, copy)
    outdir = os.path.join(OUT_DIR, nid)
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "index.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html_out)
    print(f"  ✓ {os.path.relpath(path, ROOT)}")
    return path


def main():
    if not os.path.exists(NEEDS):
        sys.exit(f"找不到数据文件：{NEEDS}")
    if not os.path.exists(TEMPLATE):
        sys.exit(f"找不到模板：{TEMPLATE}")
    data = json.load(open(NEEDS, encoding="utf-8"))
    needs = data.get("needs", [])
    if not needs:
        sys.exit("needs.json 里没有需求。")
    template = open(TEMPLATE, encoding="utf-8").read()

    args = sys.argv[1:]
    if "--all" in args:
        targets = needs
    elif args and not args[0].startswith("-"):
        targets = [n for n in needs if n.get("id") == args[0]]
        if not targets:
            sys.exit(f"找不到 need id：{args[0]}")
    else:
        targets = [needs[0]]  # 默认排名第一的需求

    print(f"模板：{os.path.relpath(TEMPLATE, ROOT)}  ·  LLM：{'开' if KEY else '关（确定性）'}")
    for n in targets:
        generate(n, template)
    print(f"完成：{len(targets)} 页 → demo/out/")


if __name__ == "__main__":
    main()
