# 需求雷达 · Need Radar

每天从海内外社区采集**抱怨 / 求助 / 差评 / 重要变化 / 建设者动态**，先经过购买理由语义闸和来源分层，再按你的关注方向压缩成「现在看 / 稍后看 / 已下沉」。目标不是制造更多信息，而是保护注意力，同时持续发现值得验证的新需求。

> 方法论来自「深海圈 AI 编程」课程：**产品 = 购买理由；真需求 = 有人愿意付出代价，代价越大越真；收集抱怨；需求倒做；人群越窄越好、痛点强度＞人数。**

## ⚠️ 已知局限（务必先读 · 见 `reports/` 第 1 轮审计）

- **首页已改为注意力优先**：默认只展示 5 条「现在看」和 8 条「稍后看」，并区分新需求、重要变化、建设者动态；完整统计和观察池仍可展开查看。
- **三类内容只设上限、不设保底名额**：需求、重要变化、建设者分别经过独立新鲜度和质量阈值；某一类今天没有合格内容时不会凑数，同一类也不能垄断全部注意力。
- **跨日变化已具备，但当前只有首份快照**：`data/history/` 会保存每天的稳定 ID、排名和证据变化。至少刷新两天后，页面才会出现「新出现 / 排名上升 / 证据增强」等真实日差。
- **建设者动态当前可能为 0 条**：Follow Builders 的 X、博客、播客公开 feed 没有合格新内容时保持空状态，不拿旧内容凑数；原始链接是进入页面的硬条件。
- **当前已切到严格购买理由闸**：会主动下沉 how-to、市场调研、讨论、产品链接投放、泛热榜等噪声。旧 raw 数据在严格闸下可能输出 0 条高置信机会，这是诚实结果；主榜之外的候选会进入“观察池”，不再直接消失。
- **语义闸已有本地缓存**：`data/cache/semantic_gate.json` 记录每条信号的确定性闸判断，便于后续接 LLM 复核或人工抽检；默认不调用外部模型。
- **已新增 OpenCLI 本地浏览器源**：小红书、X/Twitter、TikTok、抖音热点。它们依赖本机 `opencli` + Browser Bridge extension；不通时自动写 0 条，不阻断刷新。小红书/X/TikTok 只保留显式需求语言，抖音热点只作泛趋势背景。
- **已补 A/C 类免费上下文源**：Product Hunt official feed、GitHub Trending public HTML。它们进入观察池作为商业/技术趋势上下文，不单独证明购买理由。
- **已三路探测但未进主链路**：Chrome Web Store、Toolify、TAAFT。原因见 `reports/source-access-matrix.md`：不是需要授权/付费，就是页面可达但没有稳定公开评论/结构契约。
- **名人点评是模板生成的"参考语气"**，非核心判断；决策以八维分 + 证据原帖为准。
- **Apple 差评源产出不稳**（受节流，单次 47～424 条波动），导致每日需求条数波动。
- **demo 生成器（`demo/`）暂停扩展**：需求识别达标前不批量出 demo。
- **个性化偏好与反馈完全留在浏览器本地**：可以导入私有偏好，并用「有价值 / 噪声 / 稍后」持续校准；两者都不会上传，也不会自动修改公共评分规则。

---

## 30 秒上手

```bash
cd ~/Desktop/需求雷达

# 1) 采集 + 打分（跑一次，约 1-2 分钟）
python3 scripts/refresh.py        # 或 bash scripts/refresh.sh

# 2) 起站看结果（必须用 http，不能 file://）
python3 -m http.server 8910 --directory ~/Desktop/需求雷达
# 浏览器打开： http://localhost:8910/web/index.html
```

打开首页先看「今日」：5 条现在看、8 条稍后看。需要专门找机会时切到「新需求」；想理解最近发生了什么时切到「重要变化」；想追踪一线建设者时切到「建设者」。点需求条目仍可查看购买理由、当前替代方案、MVP 切口、验证动作、八维打分和证据原帖。

若要模拟公开仓库的无登录运行环境：

```bash
NEED_RADAR_MODE=github python3 scripts/refresh.py
python3 scripts/quality_gate.py
python3 scripts/build_public.py --write-public-data
python3 -m http.server 8910 --directory dist
```

---

## 它怎么工作（三层解耦）

```
collectors/*.py   每个信息源一个采集器（零依赖，标准库）
      ↓  data/raw/<source>.json        ← 标准化「信号」
scorer/score.py   购买理由闸 → 来源分层 → 聚类成「机会」→ 八维打分
scorer/attention.py  稳定 ID → 个性化注意力分 → now/later/ignore → 跨日变化
      ↓  data/needs.json               ← attention + needs + watchlist
      ↓  data/history/YYYY-MM-DD.json  ← 每日快照与变化基线
      ↓  data/cache/semantic_gate.json ← 本地语义闸缓存
web/index.html    注意力工作台，默认先呈现少量行动信息
```

数据契约见 `docs/SCHEMA.md`。

### 信息源（v1 · 零门槛免费、可每日自动跑）

| 源 | 区域 | 信号 | 备注 |
|---|---|---|---|
| Hacker News (Algolia) | 海外 | 抱怨/Ask/Show HN | 开发者需求金矿 |
| Stack Exchange | 海外 | 找工具/技术痛点 | softwarerecs/webapps 站最佳 |
| App Store 榜+差评 (us/cn) | 海外+国内 | ≤3 星差评挖痛点 | 官方 RSS |
| V2EX | 国内 | 求推荐/吐槽 | 免登录 JSON |
| 微博热搜 | 国内 | 即时情绪/趋势 | 娱乐噪声会被打分器过滤 |
| Hugging Face | 海外 | 新模型/Spaces（alpha 窗口） | trending |
| Reddit | 海外 | SaaS/IndieHackers 抱怨 | 数据中心 IP 常被挡，**你的住宅 IP 一般可用** |
| Product Hunt | 海外 | 新产品发布 | 官方 Atom feed；A 类商业上下文，进观察池 |
| GitHub Trending | 海外 | 技术趋势 | 公开 HTML；C 类趋势注释，进观察池 |
| 小红书 (OpenCLI) | 国内 | 搜索结果里的显式痛点 | 需 Browser Bridge；当前严格过滤普通教程/盘点 |
| X/Twitter (OpenCLI) | 海外 | 短查询搜索 + 趋势 | 复杂布尔查询易超时；官方 API 另需付费/额度 |
| TikTok (OpenCLI) | 海外 | 搜索结果里的显式痛点 | 过滤工具盘点/广告后再入 raw |
| 抖音热点 (OpenCLI) | 国内 | 热点词 | 仅 D 类背景；关键词搜索接口本机不可用 |
| AI HOT | 海外+国内 | 多源精选的重要变化 | 只进入趋势流；保留原始来源，不伪装成需求 |
| Follow Builders | 海外 | X / 博客 / 播客的一线建设者动态 | 过滤短回复和促销；公开 feed 无新内容时返回 0 |

> 2025-26 现实：`pytrends 已归档`、`GummySearch 已关停`、`X 免费层取消`、`Amazon 评论正文被砍`。公开版刻意只用稳定、无需登录的免费源做骨架；旧版 Bilibili 采集器依赖浏览器伪装与占位 cookie，已从公开清单和 GitHub 模式排除。微博等泛热榜只作背景，不直接入榜。

### 来源层级（v2 · 购买理由优先）

| 层级 | 代表来源 | 用途 |
|---|---|---|
| A 商业证据 | TrustMRR / Toolify / TAAFT / Product Hunt / App Store / Chrome Web Store | 优先证明有人用、有人付费、有人差评 |
| B 抱怨求助 | Reddit / HN / V2EX / Stack Exchange / Indie Hackers / 小红书 / X | 发现具体痛点和替代品搜索 |
| C 趋势注释 | AI HOT / Follow Builders / Google Trends / GitHub Trending / Hugging Face / TikTok | 只判断是否起势，不单独决定需求入榜 |
| D 泛热榜 | 微博 / B站 / 今日热榜 / 即刻 / 抖音热点 | 默认下沉，避免把热闹当需求 |

### 八维打分（课程 + 名人框架）

`痛点强度 pain` · `人群窄度 narrow` · `付费意愿 wtp` · `重复频次 freq` · `供给缺口 gap` · `Alpha窗口 alpha` · `能力匹配 fit` · `实现可行 feasible`
权重：pain .22 / wtp .18 / gap .15 / freq .12 / narrow .10 / alpha .08 / feasible .08 / fit .07（课程：痛点与需求强度最高，人数权重低）。
`能力匹配 fit` 和本地生成的注意力排序都读不入 Git 的 `scorer/profile.json`。其中 `attention.focus_keywords`、`deprioritize_keywords`、`source_weights`、`kind_weights`、阈值和每日上限可直接调整个性化；默认配置仍可供其他用户开箱使用。公开 Pages 还支持把同一份 `attention` 配置导入当前浏览器，详情见 [`docs/PERSONALIZATION.md`](docs/PERSONALIZATION.md)。
公共默认审查视角在 `scorer/persona_rubric.default.json`。你可以在本地创建不入 Git 的 `scorer/persona_rubric.json`；公开数据构建器不会发布本地视角或对应点评。

---

## 每日自动更新（GitHub Actions + Pages）

`.github/workflows/daily-radar.yml` 每天北京时间 `08:37` 自动执行，也支持手动运行：

1. 恢复前一天脱敏历史并运行测试；
2. 以 `NEED_RADAR_MODE=github` 采集无需登录的公共源；
3. 执行质量门禁和公开数据脱敏；
4. 只提交 `public-data/`，并在同一次任务里发布 GitHub Pages。

依赖本机 Browser Bridge 的来源会明确记为 `skipped`，历史 raw 不会混入 GitHub 榜单。采集状态分为 `success / empty / failed / skipped`；打分失败或没有任何有效公共源时任务直接失败，上一版 Pages 保持不变。

启用步骤见 [`docs/GITHUB_PUBLISHING.md`](docs/GITHUB_PUBLISHING.md)。真正创建远程仓库和首次推送前，应再次核对公开清单。

---

## 零密钥默认

公开项目和每日工作流不配置也不需要模型 key、付费 API 或用户账号。确定性评分、版本化评测和质量门禁是唯一默认真源；需要登录态或付费服务的个人扩展不进入公开数据链路。

---

## 加一个新信息源

1. 照 `collectors/hackernews.py` 写 `collectors/<name>.py`，输出符合 `docs/SCHEMA.md` 的 Signal，用 `write_raw("<name>", signals)`。
2. 失败要 `try/except` 优雅降级（写 0 条，别崩）。
3. 在 `scorer/score.py` 的 `SOURCE_TIER_PATTERNS` 里给新源分层；默认别让泛热榜进主榜。
4. `python3 collectors/<name>.py` 自测通过即可，`refresh.py` 会自动发现并纳入。

---

## 路线图

- **一期（已交付）**：采集 → 严格购买理由闸 → 机会卡片 + 观察池 → 本地站内呈现。
- **二期（已交付）**：注意力首页、AI HOT 重要变化、Follow Builders 可选动态、个性化排序、稳定 ID 和每日快照。
- **三期（进行中）**：连续运行两天以上验证跨日排序质量，继续收紧低质量需求；再评估 Chrome Web Store / Product Hunt 评论层等更强购买证据。
- **四期（后置）**：接入 LLM 语义闸复核、飞书/邮件/Telegram Top5 推送。外部账号、API key、launchd 启用和推送必须单独确认。

设计基准：编辑台式暗色界面、少卡片、强分流、零外部字体依赖、克制动效；默认首页要让用户几分钟内看完，而不是继续刷。
