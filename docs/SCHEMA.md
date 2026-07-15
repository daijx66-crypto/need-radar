# 需求雷达 · 数据契约（SCHEMA）

三层解耦：`采集层 collectors/` → `data/raw/<source>.json` → `打分层 scorer/` → `data/needs.json` → `呈现层 web/`。
所有 JSON 用 UTF-8、`ensure_ascii=false`。

## 1. Signal（采集器输出，`data/raw/<source>.json`）

```
{ "source": str, "generated_at": ISO, "count": int, "signals": [ Signal ] }
```

每个 Signal：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | `"{source}-{native_id}"`，全局唯一 |
| source | str | 机读源名，如 `hackernews` |
| source_label | str | 展示名，如 `Hacker News` |
| region | str | `海外` / `国内` / `通用` |
| lang | str | `en` / `zh` |
| title | str | 标题 |
| text | str | 正文/摘要，可为 "" |
| url | str | 原帖链接 |
| popularity | int | 源生热度（点赞/回复/榜位反推） |
| comments | int | 评论数 |
| created_at | str | ISO 或 "" |
| signal_type | str | `complaint`/`question`/`trend`/`launch`/`ranking`/`review`/`discussion` |
| keywords | [str] | 抽取的关键词 |

## 2. Need（打分器输出，`data/needs.json`）

```
{ "generated_at": ISO, "source_stats": {source_label:int}, "meta": Meta, "needs": [ Need ], "watchlist": [ WatchItem ], "attention": Attention, "history": History }
```

每个 Need：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | 需求簇 id |
| stable_id | str | 基于证据 URL 的跨日稳定 id，不随当天名次变化 |
| title | str | 需求陈述（不是原帖标题，是提炼后的需求）|
| summary | str | 一句话痛点 |
| region | str | `海外`/`国内`/`通用` |
| sources | [str] | 命中的来源展示名（去重）|
| source_tiers | [str] | 来源层级，`A`/`B`/`C`/`D` |
| source_tier_labels | [str] | 来源层级展示名 |
| signal_count | int | 该簇聚合的信号数 |
| evidence | [{title,url,source_label,popularity,created_at,source_tier,source_tier_label}] | 代表证据（最多 5）|
| demand_score | DemandScore | 见下 |
| opportunity | Opportunity | 购买理由卡片，见下 |
| personas | { [persona_key]: str } | 多视角一句话，key 来自 `scorer/persona_rubric.json` |
| product_forms | [ProductForm] | 2–4 个产品形态及打分 |
| recommendation | str | 一句话结论 |
| verdict_label | str | `强烈推荐`/`值得一试`/`谨慎`/`过滤` |

**DemandScore**：`{ total: 0-100, dims: {...0-10}, reasons: [str] }`，dims 八维：
`pain`(痛点强度) `narrow`(人群窄度) `wtp`(付费意愿) `freq`(重复频次) `gap`(供给缺口) `alpha`(Alpha窗口) `fit`(能力匹配) `feasible`(实现可行/低风险)。
权重（课程：痛点与需求强度最高、人数权重低）：pain .22, wtp .18, gap .15, freq .12, narrow .10, alpha .08, feasible .08, fit .07。

**ProductForm**：`{ form: str, score: 0-100, monetization: str, build_cost: str, note: str }`，
form ∈ `Web App`/`微信小程序`/`Chrome 扩展`/`API/服务`/`移动 App`/`服务产品化`。

**Opportunity**：
`{ status, who, scenario, purchase_reason, current_workaround, mvp, validation, intent_type, semantic_label, source_tier, source_tier_label }`。
核心用途是把榜单从“热度/打分”改成“购买理由卡片”：谁在什么场景下，为什么可能付费，现在怎么凑合，第一版该怎么验证。

**WatchItem**：
`{ id, stable_id, title, summary, source, source_label, region, url, popularity, comments, signal_type, gate, intent_type, noise_type, source_tier, source_tier_label, reason }`。
观察池只放未进入主榜但值得继续追踪的信号：过闸但分数/聚类不足的候选、社交源显式需求、以及 D 类泛热榜背景。它不是高置信机会，不参与主榜排名。

**Meta**：
`{ signals, candidates, clusters, needs, watchlist, weights, mode, stage, gate_counts, noise_counts, source_tier_counts, source_tier_labels, semantic_gate_cache, persona_profiles, personas_note }`。
其中 `gate_counts` 统计 `real_need`/`possible_need`/`noise`，`noise_counts` 用于解释空榜或低产出，`source_tier_counts` 用于判断源池是否过度依赖低信号源。
`semantic_gate_cache` 记录本地确定性语义闸缓存状态：`{path, entries, mode, llm_enabled}`。默认 `llm_enabled=false`，不调用外部模型。
`persona_profiles` 是 `{ [persona_key]: {name, tag, avatar, source_skill} }`，供前端动态渲染人格卡片。

**Attention**：

```json
{
  "generated_at": "ISO",
  "limits": {"now": 5, "later": 8},
  "summary": {"now": 5, "later": 8, "ignore": 20, "new": 3, "need": 2, "shift": 20, "builder": 4},
  "items": [AttentionItem]
}
```

**AttentionItem** 统一三类内容：`kind=need`（高置信需求）、`kind=shift`（重要变化）、`kind=builder`（建造者信号）。

| 字段 | 类型 | 说明 |
|---|---|---|
| stable_id | str | 以内容类型 + 原始 URL 为主生成的稳定 id |
| need_id | str | `kind=need` 时指向当天 Need id，其余为空 |
| kind | str | `need` / `shift` / `builder` |
| priority | str | `now` / `later` / `ignore`，受每日注意力预算限制 |
| attention_score | number | 个性化后的展示优先级，不覆盖原始分 |
| source_score | number | 需求总分或外部源原始评分 |
| title / summary | str | 人类可扫读的标题与摘要 |
| source / url / permalink | str | 来源、原始链接、可选聚合页链接 |
| published_at / category | str | 原始发布时间与内容分类 |
| why_now / why_ignore | str | 为什么值得看或可放心忽略 |
| rank / rank_delta | int / null | 当日注意力名次、相对上一快照的升降 |
| is_new | bool | 相对上一日是否首次出现；首份快照恒为 false |
| score_delta / evidence_delta | number / null | 原始分和证据数变化 |
| streak_days | int | 连续出现在快照中的天数 |
| change_label | str | `首份快照` / `今日新增` / `上升 N` / `连续 N 天` / `持续关注` |
| age_hours / is_stale | number/null / bool | 基于来源原始时间计算的新鲜度；未知时间按陈旧处理 |

个性化来自 `scorer/profile.json.attention`，只能改变 `attention_score` 和展示数量，不能修改 `source_score`、语义闸标签或证据。
公共默认值来自 `scorer/profile.default.json`。`now_thresholds` / `later_thresholds` 控制各类质量下限，`max_age_hours` 控制新鲜度，`now_kind_limits` / `later_kind_limits` 只设各类上限、不保证任何类别必须入榜。

浏览器反馈不写回本契约。它只在 `localStorage` 中计算 `local_score` 和 `effective_priority`；公开 JSON、原始 `attention_score` 与需求证据不变。

**History**：`{ current_date, previous_date, has_previous, snapshot_path }`。每日快照保存到 `data/history/YYYY-MM-DD.json`，索引在 `data/history/index.json`。同日重跑覆盖同日快照；跨日对比只读取严格早于当天的最新快照。

来源层级：

| 层级 | 含义 | 用途 |
|---|---|---|
| A 商业证据 | TrustMRR / Toolify / Product Hunt / App Store 等收入、榜单、差评源 | 优先作为购买理由或竞品证据 |
| B 抱怨求助 | Reddit / HN / V2EX / Stack Exchange / 小红书 / X 等社区求助、吐槽 | 主要需求发现源 |
| C 趋势注释 | AI HOT / Follow Builders / Google Trends / GitHub Trending / Hugging Face / TikTok 等趋势源 | 只注释起势或建造者实践，不单独决定入榜 |
| D 泛热榜 | 微博 / B站 / 抖音热点 / 今日热榜等泛热度源 | 默认下沉为背景，避免噪声进榜 |

## 3. 前端读取约定
- 前端只读 `data/needs.json`（+ 可选 `data/needs.sample.json` 兜底）。
- `needs` 是高置信机会主榜；`watchlist` 是观察池，前端必须视觉降权显示。
- `attention.items` 是首页注意力流；`kind` 与 `priority` 分别控制导航分类和阅读预算。
- 必须零依赖（无 CDN/Google Fonts）、深浅双主题、tabular-nums、系统字体、clamp() 响应式。
- 起站：`python3 -m http.server 8910 --directory <repo根>`，访问 `/web/index.html`（fetch 走相对路径 `../data/needs.json`）。
