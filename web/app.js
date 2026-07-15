/* 需求雷达 · Demand Radar — zero-dependency front-end controller.
   读取 ../data/needs.json，失败/空回退 ../data/needs.sample.json（标注样例数据）。 */
(() => {
  "use strict";

  /* ---------- constants ---------- */
  const DIM_LABELS = {
    pain: "痛点强度",
    narrow: "人群窄度",
    wtp: "付费意愿",
    freq: "重复频次",
    gap: "供给缺口",
    alpha: "Alpha窗口",
    fit: "能力匹配",
    feasible: "实现可行",
  };
  const DIM_ORDER = ["pain", "narrow", "wtp", "freq", "gap", "alpha", "fit", "feasible"];

  const VERDICTS = {
    "强烈推荐": { cls: "v-strong", scls: "s-strong" },
    "值得一试": { cls: "v-good", scls: "s-good" },
    "谨慎":     { cls: "v-caution", scls: "s-caution" },
    "过滤":     { cls: "v-filter", scls: "s-filter" },
  };
  const VERDICT_ORDER = ["强烈推荐", "值得一试", "谨慎", "过滤"];
  const REGION_ORDER = ["海外", "国内", "通用"];
  const TYPE_META = {
    need: { label: "新需求", mark: "N" },
    shift: { label: "重要变化", mark: "S" },
    builder: { label: "建造者", mark: "B" },
  };
  const FEEDBACK_KEY = "need-radar-feedback-v1";
  const PROFILE_KEY = "need-radar-profile-v1";
  const FEEDBACK_META = {
    useful: { label: "有价值", delta: 8 },
    later: { label: "稍后", delta: -4 },
    noise: { label: "噪声", delta: -30 },
  };

  const DEFAULT_PERSONA_PROFILES = {
    jobs: { name: "史蒂夫·乔布斯", tag: "产品 / 聚焦", avatar: "J" },
    naval: { name: "纳瓦尔·拉维坎特", tag: "杠杆 / 财富", avatar: "N" },
    zhangxuefeng: { name: "张雪峰", tag: "落地 / 付费", avatar: "张" },
  };

  /* ---------- state ---------- */
  const state = {
    needs: [],
    watchlist: [],
    attention: { items: [], summary: {}, limits: {} },
    history: {},
    view: "today",
    isSample: false,
    generatedAt: "",
    sourceStats: {},
    runStatus: {},
    meta: {},
    personaProfiles: DEFAULT_PERSONA_PROFILES,
    filters: { region: "全部", verdict: "全部", q: "" },
    sort: "total",
    lastFocus: null,
    feedback: {},
    localProfile: null,
    profileOrigin: "",
  };

  /* ---------- dom helpers ---------- */
  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, cls, html) => {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html != null) n.innerHTML = html;
    return n;
  };
  const esc = (s) =>
    String(s == null ? "" : s).replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );

  const fmtTime = (iso) => {
    if (!iso) return "未知时间";
    const d = new Date(iso);
    if (isNaN(d)) return String(iso);
    const p = (n) => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  const fmtSignalTime = (iso) => {
    if (!iso) return "时间未知";
    const d = new Date(iso);
    if (isNaN(d)) return "时间未知";
    const now = new Date();
    const sameDay = d.toDateString() === now.toDateString();
    const p = (n) => String(n).padStart(2, "0");
    return sameDay ? `今天 ${p(d.getHours())}:${p(d.getMinutes())}` : `${p(d.getMonth() + 1)}/${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  };

  function loadFeedback() {
    try {
      const saved = JSON.parse(localStorage.getItem(FEEDBACK_KEY) || "{}");
      return saved && typeof saved === "object" && !Array.isArray(saved) ? saved : {};
    } catch {
      return {};
    }
  }

  function saveFeedback() {
    try { localStorage.setItem(FEEDBACK_KEY, JSON.stringify(state.feedback)); } catch {}
  }

  const clamp = (value, min, max) => Math.max(min, Math.min(max, Number(value) || 0));

  function cleanList(value) {
    return Array.isArray(value)
      ? value.filter((row) => typeof row === "string" && row.trim()).slice(0, 60).map((row) => row.trim().slice(0, 80))
      : [];
  }

  function cleanMap(value, allowedKeys = null, min = -15, max = 15) {
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    return Object.fromEntries(Object.entries(value).filter(([key]) => !allowedKeys || allowedKeys.includes(key)).slice(0, 60)
      .map(([key, weight]) => [String(key).slice(0, 80), clamp(weight, min, max)]));
  }

  function normalizeLocalProfile(payload) {
    const source = payload && typeof payload === "object" ? payload : {};
    const raw = source.attention && typeof source.attention === "object" ? source.attention : source;
    const kinds = ["need", "shift", "builder"];
    const thresholds = (key, defaults) => ({ ...defaults, ...cleanMap(raw[key], kinds, 0, 100) });
    const limits = (key, defaults) => ({ ...defaults, ...cleanMap(raw[key], kinds, 0, 20) });
    return {
      schema_version: 1,
      name: typeof source.name === "string" ? source.name.slice(0, 80) : "本地偏好",
      attention: {
        focus_keywords: cleanList(raw.focus_keywords),
        deprioritize_keywords: cleanList(raw.deprioritize_keywords),
        source_weights: cleanMap(raw.source_weights),
        kind_weights: cleanMap(raw.kind_weights, kinds),
        now_limit: Math.round(clamp(raw.now_limit ?? 5, 0, 12)),
        later_limit: Math.round(clamp(raw.later_limit ?? 8, 0, 20)),
        now_thresholds: thresholds("now_thresholds", { need: 60, shift: 68, builder: 68 }),
        later_thresholds: thresholds("later_thresholds", { need: 50, shift: 55, builder: 55 }),
        now_kind_limits: limits("now_kind_limits", { need: 3, shift: 3, builder: 1 }),
        later_kind_limits: limits("later_kind_limits", { need: 3, shift: 4, builder: 3 }),
      },
    };
  }

  function loadLocalProfile() {
    try {
      const saved = localStorage.getItem(PROFILE_KEY);
      return saved ? normalizeLocalProfile(JSON.parse(saved)) : null;
    } catch {
      return null;
    }
  }

  function saveLocalProfile(profile, origin = "browser") {
    state.localProfile = normalizeLocalProfile(profile);
    state.profileOrigin = origin;
    try { localStorage.setItem(PROFILE_KEY, JSON.stringify(state.localProfile)); } catch {}
  }

  function importProfileFromHash() {
    const encoded = new URLSearchParams(location.hash.slice(1)).get("profile");
    if (!encoded) return;
    try {
      const base64 = encoded.replace(/-/g, "+").replace(/_/g, "/").padEnd(Math.ceil(encoded.length / 4) * 4, "=");
      const bytes = Uint8Array.from(atob(base64), (char) => char.charCodeAt(0));
      saveLocalProfile(JSON.parse(new TextDecoder().decode(bytes)), "install-link");
    } catch {
      state.localProfile = loadLocalProfile();
    }
    history.replaceState(null, "", `${location.pathname}${location.search}`);
  }

  function profileSignals(item) {
    const settings = state.localProfile?.attention;
    if (!settings) return { delta: 0, reasons: [] };
    const text = `${item.title || ""} ${item.summary || ""} ${item.category || ""}`.toLowerCase();
    const focus = settings.focus_keywords.filter((word) => text.includes(word.toLowerCase()));
    const down = settings.deprioritize_keywords.filter((word) => text.includes(word.toLowerCase()));
    const sourceName = String(item.source || "").toLowerCase();
    const sourceMatch = Object.entries(settings.source_weights)
      .filter(([name]) => sourceName.includes(name.toLowerCase()))
      .sort((a, b) => b[0].length - a[0].length)[0];
    const source = sourceMatch?.[1] || 0;
    const kind = settings.kind_weights[item.kind] || 0;
    const delta = clamp(Math.min(15, focus.length * 3) - Math.min(30, down.length * 8) + source + kind, -35, 25);
    const reasons = [];
    if (focus.length) reasons.push(`命中 ${focus.slice(0, 2).join(" / ")}`);
    if (down.length) reasons.push(`下沉 ${down.slice(0, 2).join(" / ")}`);
    if (source) reasons.push(`来源 ${source > 0 ? "+" : ""}${source}`);
    if (kind) reasons.push(`${TYPE_META[item.kind]?.label || item.kind} ${kind > 0 ? "+" : ""}${kind}`);
    return { delta, reasons };
  }

  function profileAdjustment(item) {
    return profileSignals(item).delta;
  }

  function feedbackAdjustment(item) {
    const direct = state.feedback[item.stable_id]?.value;
    let delta = (FEEDBACK_META[direct]?.delta || 0) + profileAdjustment(item);
    const related = Object.values(state.feedback).filter((row) => row.stable_id !== item.stable_id);
    const sourceNet = related.reduce((sum, row) => {
      if (row.source !== item.source) return sum;
      return sum + (row.value === "useful" ? 1 : row.value === "noise" ? -1 : 0);
    }, 0);
    const kindNet = related.reduce((sum, row) => {
      if (row.kind !== item.kind) return sum;
      return sum + (row.value === "useful" ? 1 : row.value === "noise" ? -1 : 0);
    }, 0);
    delta += Math.max(-6, Math.min(6, sourceNet * 2));
    delta += Math.max(-3, Math.min(3, kindNet));
    return delta;
  }

  function effectivePriority(item) {
    const value = state.feedback[item.stable_id]?.value;
    if (value === "noise") return "ignore";
    if (value === "later" && item.priority === "now") return "later";
    return item.priority;
  }

  function personalizedItems() {
    const order = { now: 0, later: 1, ignore: 2 };
    const rows = (state.attention.items || []).map((item) => ({
      ...item,
      local_score: Math.max(0, Math.min(100, (item.attention_score || 0) + feedbackAdjustment(item))),
      effective_priority: effectivePriority(item),
    }));
    const settings = state.localProfile?.attention;
    if (settings) {
      const nowCounts = { need: 0, shift: 0, builder: 0 };
      const laterCounts = { need: 0, shift: 0, builder: 0 };
      let nowUsed = 0;
      let laterUsed = 0;
      rows.sort((a, b) => b.local_score - a.local_score || (a.rank || 999) - (b.rank || 999));
      rows.forEach((item) => {
        const feedback = state.feedback[item.stable_id]?.value;
        if (!item.url || item.is_stale || feedback === "noise") {
          item.effective_priority = "ignore";
          return;
        }
        const kind = item.kind;
        let desired = item.local_score >= settings.now_thresholds[kind] ? "now"
          : item.local_score >= settings.later_thresholds[kind] ? "later" : "ignore";
        if (feedback === "later" && desired === "now") desired = "later";
        if (desired === "now" && nowUsed < settings.now_limit && nowCounts[kind] < settings.now_kind_limits[kind]) {
          item.effective_priority = "now";
          nowUsed += 1;
          nowCounts[kind] += 1;
        } else if (desired !== "ignore" && laterUsed < settings.later_limit && laterCounts[kind] < settings.later_kind_limits[kind]) {
          item.effective_priority = "later";
          laterUsed += 1;
          laterCounts[kind] += 1;
        } else {
          item.effective_priority = "ignore";
        }
      });
    }
    return rows.sort((a, b) =>
      order[a.effective_priority] - order[b.effective_priority]
      || b.local_score - a.local_score
      || (a.rank || 999) - (b.rank || 999)
    );
  }

  function setFeedback(item, value) {
    const previous = state.feedback[item.stable_id]?.value;
    if (previous === value) {
      delete state.feedback[item.stable_id];
    } else {
      state.feedback[item.stable_id] = {
        stable_id: item.stable_id,
        value,
        source: item.source || "",
        kind: item.kind || "",
        title: item.title || "",
        updated_at: new Date().toISOString(),
      };
    }
    saveFeedback();
    renderProfileStatus();
    renderAttentionSummary();
    renderAttention();
  }

  function exportFeedback() {
    const payload = {
      schema_version: 1,
      exported_at: new Date().toISOString(),
      storage: "browser-local-only",
      feedback: Object.values(state.feedback),
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `need-radar-feedback-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    setTimeout(() => URL.revokeObjectURL(link.href), 0);
  }

  function renderProfileStatus(message = "") {
    const status = $("#profileStatus");
    const button = $("#profileImport");
    if (!status || !button) return;
    const active = Boolean(state.localProfile);
    const feedbackCount = Object.keys(state.feedback).length;
    const origin = state.profileOrigin === "local-file" ? "本机自动" : "浏览器私有";
    status.textContent = message || (active
      ? `${state.localProfile.name} · ${origin} · ${feedbackCount} 条反馈`
      : "本地偏好未启用");
    status.classList.toggle("is-active", active);
    button.textContent = active ? "更新本地偏好" : "导入本地偏好";
  }

  async function importProfileFile(file) {
    try {
      saveLocalProfile(JSON.parse(await file.text()), "file");
      renderProfileStatus("本地偏好已启用，仅保存在当前浏览器");
      renderAttentionSummary();
      renderAttention();
    } catch {
      renderProfileStatus("偏好文件无效，未修改当前设置");
    }
  }

  function fallbackAttention() {
    const items = state.needs.map((need, index) => ({
      stable_id: need.stable_id || need.id,
      need_id: need.id,
      kind: "need",
      priority: index < 5 ? "now" : "later",
      title: need.title,
      summary: need.opportunity?.purchase_reason || need.summary,
      source: (need.sources || [""])[0],
      source_score: need.demand_score?.total || 0,
      attention_score: need.demand_score?.total || 0,
      change_label: "尚未建立快照",
      why_now: "来自现有高置信需求榜。",
      why_ignore: "",
      published_at: state.generatedAt,
      url: need.evidence?.[0]?.url || "",
    }));
    return {
      items,
      limits: { now: 5, later: 8 },
      summary: {
        now: items.filter((row) => row.priority === "now").length,
        later: items.filter((row) => row.priority === "later").length,
        ignore: 0,
        new: 0,
        need: items.length,
        shift: 0,
        builder: 0,
      },
    };
  }

  /* ============================================================
     DATA LOADING
     ============================================================ */
  async function tryFetch(url) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      if (!res.ok) return null;
      const data = await res.json();
      const hasNeeds = Array.isArray(data?.needs) && data.needs.length > 0;
      const hasWatchlist = Array.isArray(data?.watchlist) && data.watchlist.length > 0;
      const hasAttention = Array.isArray(data?.attention?.items) && data.attention.items.length > 0;
      if (!data || !Array.isArray(data.needs) || (!hasNeeds && !hasWatchlist && !hasAttention)) return null;
      return data;
    } catch {
      return null;
    }
  }

  async function tryFetchJson(url) {
    try {
      const res = await fetch(url, { cache: "no-store" });
      return res.ok ? await res.json() : null;
    } catch {
      return null;
    }
  }

  async function loadPrivateLocalProfile() {
    if (!["localhost", "127.0.0.1", "::1"].includes(location.hostname)) return;
    const profile = await tryFetchJson("../local/profile.json") || await tryFetchJson("local/profile.json");
    if (profile) saveLocalProfile(profile, "local-file");
  }

  async function loadData() {
    let data = await tryFetch("data/needs.json") || await tryFetch("../data/needs.json");
    if (data) {
      state.isSample = false;
    } else {
      data = await tryFetch("../data/needs.sample.json");
      state.isSample = true;
    }
    if (!data) {
      $("#genStatus").textContent = "数据加载失败：未找到 needs.json 或 needs.sample.json";
      $("#board").appendChild(
        el("div", "empty", "<b>无法加载数据。</b><br>请确认从仓库根目录起服务：<br><code>python3 -m http.server 8910 --bind 127.0.0.1 --directory &lt;repo根&gt;</code>")
      );
      return;
    }
    state.needs = data.needs.slice();
    state.watchlist = Array.isArray(data.watchlist) ? data.watchlist.slice() : [];
    state.generatedAt = data.generated_at || "";
    state.sourceStats = data.source_stats || {};
    state.runStatus = await tryFetchJson("data/status.json") || await tryFetchJson("../data/last_run.json") || {};
    state.meta = data.meta || {};
    state.personaProfiles = state.meta.persona_profiles || DEFAULT_PERSONA_PROFILES;
    state.attention = data.attention?.items ? data.attention : fallbackAttention();
    state.history = data.history || {};
    state.feedback = loadFeedback();
    bootRender();
  }

  /* ============================================================
     MASTHEAD: status / stats / sources
     ============================================================ */
  function renderMasthead() {
    const genline = $(".genline");
    const generated = new Date(state.generatedAt);
    const ageHours = isNaN(generated) ? Infinity : (Date.now() - generated.getTime()) / 36e5;
    const runState = state.runStatus.status || "";
    if (runState === "failed" || runState === "degraded") {
      genline.classList.add("is-stale");
      const issues = [...(state.runStatus.failed_sources || []), ...(state.runStatus.missing_required_sources || [])];
      const label = runState === "failed" ? "本次更新失败" : "本次更新部分降级";
      $("#genStatus").textContent = `${label}${issues.length ? ` · ${issues.join("、")}` : ""} · 数据 ${fmtTime(state.generatedAt)}`;
    } else if (ageHours > 36) {
      genline.classList.add("is-stale");
      $("#genStatus").textContent = `数据已过期 · 最后更新 ${fmtTime(state.generatedAt)}`;
    } else {
      genline.classList.remove("is-stale");
      $("#genStatus").textContent = `更新于 ${fmtTime(state.generatedAt)}`;
    }
    if (state.isSample) {
      genline.classList.add("is-sample");
      $("#sampleFlag").hidden = false;
    }

    // stats
    const n = state.needs;
    const meta = state.meta || {};
    const gate = meta.gate_counts || {};
    const tiers = meta.source_tier_counts || {};
    const cnt = (fn) => n.filter(fn).length;
    const avg = n.length ? Math.round(n.reduce((s, x) => s + (x.demand_score?.total || 0), 0) / n.length) : 0;
    const topScore = n.length ? Math.max(...n.map((x) => x.demand_score?.total || 0)) : 0;

    const stats = [
      { dt: "高置信机会", dd: n.length },
      { dt: "观察池", dd: meta.watchlist ?? state.watchlist.length },
      { dt: "过闸候选", dd: meta.candidates ?? n.length },
      { dt: "原始信号", dd: meta.signals ?? 0 },
      { dt: "噪声拦截", dd: gate.noise ?? 0 },
      { dt: "商业证据", dd: tiers["A 商业证据"] ?? 0 },
      { dt: "抱怨求助", dd: tiers["B 抱怨求助"] ?? 0 },
      { dt: "趋势注释", dd: tiers["C 趋势注释"] ?? 0 },
      { dt: "最高分", dd: topScore || avg, sub: "/100" },
    ];

    const dl = $("#stats");
    dl.innerHTML = "";
    stats.forEach((s, i) => {
      const wrap = el("div", "stat");
      wrap.style.animationDelay = `${i * 35}ms`;
      wrap.appendChild(el("dt", "micro", esc(s.dt)));
      wrap.appendChild(el("dd", "num", `${s.dd}${s.sub ? `<small>${esc(s.sub)}</small>` : ""}`));
      dl.appendChild(wrap);
    });

    // sources
    const src = $("#sources");
    src.innerHTML = "";
    const entries = Object.entries(state.sourceStats).sort((a, b) => b[1] - a[1]);
    if (!entries.length) { src.hidden = true; }
    entries.forEach(([label, count]) => {
      const chip = el("div", "src");
      chip.appendChild(el("span", "src-label", esc(label)));
      chip.appendChild(el("span", "src-n num", String(count)));
      src.appendChild(chip);
    });
    const a = state.attention.summary || {};
    $("#metricsSummary").textContent = `${meta.signals ?? 0} 条信号 · ${n.length} 个需求 · ${a.now ?? 0} 条现在看`;
  }

  /* ============================================================
     ATTENTION DESK
     ============================================================ */
  function renderAttentionSummary() {
    const items = personalizedItems();
    const summary = {
      ...(state.attention.summary || {}),
      now: items.filter((row) => row.effective_priority === "now").length,
      later: items.filter((row) => row.effective_priority === "later").length,
      ignore: items.filter((row) => row.effective_priority === "ignore").length,
    };
    const box = $("#attentionSummary");
    box.innerHTML = "";
    [
      ["现在看", summary.now || 0, "now"],
      ["稍后看", summary.later || 0, "later"],
      ["已下沉", summary.ignore || 0, "ignore"],
    ].forEach(([label, value, cls]) => {
      const cell = el("div", `attention-count ${cls}`);
      cell.appendChild(el("span", "num", String(value)));
      cell.appendChild(el("small", null, label));
      box.appendChild(cell);
    });
    $("#dailyTitle").textContent = `今天 ${summary.now || 0} 条现在看，${summary.later || 0} 条稍后看`;
    $("#dailySummary").textContent = state.history.has_previous
      ? `相较 ${state.history.previous_date}：${summary.new || 0} 条新增。原始证据和来源保持可追溯。`
      : "首份每日快照已建立。今天先建立基线，明天开始显示新增、上升和连续出现。";
  }

  function attentionCard(item) {
    const isNeed = item.kind === "need";
    const card = el("article", `intel-card kind-${item.kind}`);
    const node = isNeed ? el("button", "intel-row") : el("a", "intel-row");
    if (isNeed) {
      node.type = "button";
      const need = state.needs.find((row) => row.stable_id === item.stable_id || row.id === item.need_id);
      node.addEventListener("click", () => need && openDetail(need, item.rank || 1));
    } else {
      node.href = item.url || "#";
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    }
    const type = TYPE_META[item.kind] || TYPE_META.shift;
    const mark = el("div", `intel-mark mark-${item.kind}`);
    mark.appendChild(el("span", null, type.mark));
    mark.appendChild(el("small", null, type.label));
    node.appendChild(mark);

    const body = el("div", "intel-body");
    const meta = el("div", "intel-meta micro");
    meta.appendChild(el("span", "intel-change", esc(item.change_label || "持续关注")));
    meta.appendChild(el("span", null, esc(item.source || "未知来源")));
    meta.appendChild(el("span", null, esc(fmtSignalTime(item.published_at))));
    const personal = profileSignals(item);
    if (personal.delta) {
      const marker = el("span", "intel-personal", `为你 ${personal.delta > 0 ? "+" : ""}${personal.delta}`);
      marker.title = personal.reasons.join(" · ");
      meta.appendChild(marker);
    }
    body.appendChild(meta);
    body.appendChild(el("h3", null, esc(item.title || "(无标题)")));
    if (item.summary) body.appendChild(el("p", "intel-summary", esc(item.summary)));
    body.appendChild(el("p", "intel-reason", esc(item.effective_priority === "ignore" ? item.why_ignore : item.why_now)));
    node.appendChild(body);

    const score = el("div", "intel-score");
    score.appendChild(el("span", "num", String(Math.round(item.local_score ?? item.attention_score ?? item.source_score ?? 0))));
    score.appendChild(el("small", null, feedbackAdjustment(item) ? "本地排序" : "注意力"));
    score.appendChild(el("i", null, isNeed ? "打开判断" : "查看原文 ↗"));
    node.appendChild(score);
    card.appendChild(node);

    const controls = el("div", "intel-feedback");
    controls.appendChild(el("span", "micro", "这条对你："));
    Object.entries(FEEDBACK_META).forEach(([value, feedback]) => {
      const button = el("button", "feedback-choice", esc(feedback.label));
      button.type = "button";
      const active = state.feedback[item.stable_id]?.value === value;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", active ? "true" : "false");
      button.addEventListener("click", () => setFeedback(item, value));
      controls.appendChild(button);
    });
    card.appendChild(controls);
    return card;
  }

  function appendAttentionSection(root, label, note, rows) {
    if (!rows.length) return;
    const section = el("section", "intel-section");
    const head = el("div", "intel-section-head");
    const copy = el("div");
    copy.appendChild(el("p", "micro", esc(note)));
    copy.appendChild(el("h2", null, esc(label)));
    head.appendChild(copy);
    head.appendChild(el("span", "micro", `${rows.length} 条`));
    section.appendChild(head);
    const list = el("div", "intel-list");
    rows.forEach((item, index) => {
      const card = attentionCard(item);
      card.style.animationDelay = `${Math.min(index, 8) * 35}ms`;
      list.appendChild(card);
    });
    section.appendChild(list);
    root.appendChild(section);
  }

  function renderAttention() {
    const root = $("#attentionBoard");
    root.innerHTML = "";
    const all = personalizedItems();
    if (state.view === "today") {
      appendAttentionSection(root, "现在值得看", "只保留达到质量阈值的内容", all.filter((row) => row.effective_priority === "now"));
      appendAttentionSection(root, "可以稍后看", "不打断当前工作", all.filter((row) => row.effective_priority === "later"));
      if (!all.some((row) => row.effective_priority === "now" || row.effective_priority === "later")) {
        root.appendChild(el("div", "intel-empty", "<b>今天没有达到阈值的新内容。</b><p>不凑数也是注意力保护的一部分。</p>"));
      }
      return;
    }

    const rows = all.filter((row) => row.kind === state.view);
    const active = rows.filter((row) => row.effective_priority !== "ignore");
    const ignored = rows.filter((row) => row.effective_priority === "ignore");
    if (!rows.length) {
      const type = TYPE_META[state.view] || { label: "内容" };
      root.appendChild(el("div", "intel-empty", `<b>今天没有新的${esc(type.label)}信号。</b><p>没有新内容也是结果，注意力无需分配。</p>`));
      return;
    }
    appendAttentionSection(root, TYPE_META[state.view].label, "按今日注意力优先级排列", active);
    if (ignored.length) {
      const details = el("details", "ignored-list");
      details.appendChild(el("summary", null, `查看已下沉的 ${ignored.length} 条`));
      const list = el("div", "intel-list ignored");
      ignored.forEach((item) => list.appendChild(attentionCard(item)));
      details.appendChild(list);
      root.appendChild(details);
    }
  }

  function renderRoute() {
    const isWatch = state.view === "watch";
    $("#attentionBoard").hidden = isWatch;
    $("#legacyControls").hidden = !isWatch;
    $("#board").hidden = true;
    if (isWatch) {
      renderWatchlist();
    } else {
      $("#watchSection").hidden = true;
      renderAttention();
    }
  }

  function setView(view) {
    state.view = view;
    $("#streamTabs").querySelectorAll(".stream-tab").forEach((tab) => {
      const active = tab.dataset.view === view;
      tab.classList.toggle("is-active", active);
      tab.setAttribute("aria-pressed", active ? "true" : "false");
    });
    renderRoute();
  }

  /* ============================================================
     CONTROLS: facet chips
     ============================================================ */
  function buildFacets() {
    // region chips
    const regions = ["全部", ...REGION_ORDER.filter((r) => state.needs.some((n) => n.region === r))];
    const regionBox = $("#regionChips");
    regions.forEach((r) => {
      const count = r === "全部" ? state.needs.length : state.needs.filter((n) => n.region === r).length;
      const b = el("button", "chip", `${esc(r)}<span class="chip-n num">${count}</span>`);
      b.type = "button";
      b.dataset.region = r;
      b.setAttribute("aria-pressed", r === "全部" ? "true" : "false");
      if (r === "全部") b.classList.add("is-active");
      b.addEventListener("click", () => {
        state.filters.region = r;
        setActive(regionBox, b);
        render();
      });
      regionBox.appendChild(b);
    });

    // verdict chips
    const verdicts = ["全部", ...VERDICT_ORDER.filter((v) => state.needs.some((n) => n.verdict_label === v))];
    const verdictBox = $("#verdictChips");
    verdicts.forEach((v) => {
      const count = v === "全部" ? state.needs.length : state.needs.filter((n) => n.verdict_label === v).length;
      const b = el("button", "chip", `${esc(v)}<span class="chip-n num">${count}</span>`);
      b.type = "button";
      b.dataset.verdict = v;
      b.setAttribute("aria-pressed", v === "全部" ? "true" : "false");
      if (v === "全部") b.classList.add("is-active");
      b.addEventListener("click", () => {
        state.filters.verdict = v;
        setActive(verdictBox, b);
        render();
      });
      verdictBox.appendChild(b);
    });
  }

  function setActive(box, btn) {
    box.querySelectorAll(".chip").forEach((c) => {
      const on = c === btn;
      c.classList.toggle("is-active", on);
      c.setAttribute("aria-pressed", on ? "true" : "false");
    });
  }

  /* ============================================================
     FILTER + SORT + RENDER BOARD
     ============================================================ */
  function computeView() {
    const { region, verdict, q } = state.filters;
    const query = q.trim().toLowerCase();
    let rows = state.needs.filter((n) => {
      if (region !== "全部" && n.region !== region) return false;
      if (verdict !== "全部" && n.verdict_label !== verdict) return false;
      if (query) {
        const opp = n.opportunity || {};
        const hay = `${n.title} ${n.summary} ${opp.purchase_reason || ""} ${opp.current_workaround || ""} ${opp.mvp || ""}`.toLowerCase();
        if (!hay.includes(query)) return false;
      }
      return true;
    });

    const key = state.sort;
    rows.sort((a, b) => {
      let va, vb;
      if (key === "total") { va = a.demand_score?.total || 0; vb = b.demand_score?.total || 0; }
      else if (key === "signal_count") { va = a.signal_count || 0; vb = b.signal_count || 0; }
      else { va = a.demand_score?.dims?.[key] || 0; vb = b.demand_score?.dims?.[key] || 0; }
      if (vb !== va) return vb - va;
      return (b.demand_score?.total || 0) - (a.demand_score?.total || 0);
    });
    return rows;
  }

  function computeWatchlist() {
    const { region, q } = state.filters;
    const query = q.trim().toLowerCase();
    return state.watchlist.filter((item) => {
      if (region !== "全部" && item.region !== region) return false;
      if (!query) return true;
      const hay = `${item.title || ""} ${item.summary || ""} ${item.reason || ""} ${item.source_label || ""} ${item.intent_type || ""}`.toLowerCase();
      return hay.includes(query);
    });
  }

  function watchCard(item) {
    const node = item.url ? el("a", "watch-card") : el("div", "watch-card");
    if (item.url) {
      node.href = item.url;
      node.target = "_blank";
      node.rel = "noopener noreferrer";
    }

    const head = el("div", "watch-head");
    head.appendChild(el("span", "tag tier", esc(item.source_tier_label || item.source_tier || "观察")));
    if (item.source_label) head.appendChild(el("span", "tag src", esc(item.source_label)));
    if (item.region) head.appendChild(el("span", "tag region", esc(item.region)));
    if (item.popularity != null) head.appendChild(el("span", "tag more", `${esc(item.popularity)} 热度`));
    node.appendChild(head);

    node.appendChild(el("h3", null, esc(item.title || "(无标题)")));
    if (item.summary) node.appendChild(el("p", "watch-summary", esc(item.summary)));

    const foot = el("div", "watch-foot");
    foot.appendChild(el("span", "watch-reason", esc(item.reason || "观察项")));
    const gate = item.gate === "noise" ? (item.noise_type || "noise") : (item.intent_type || item.gate || "candidate");
    foot.appendChild(el("span", "watch-gate micro", esc(gate)));
    node.appendChild(foot);
    return node;
  }

  function renderWatchlist() {
    const section = $("#watchSection");
    const box = $("#watchlist");
    if (!section || !box) return;
    if (!state.watchlist.length) {
      section.hidden = true;
      return;
    }
    section.hidden = false;
    const rows = computeWatchlist();
    $("#watchCount").innerHTML = `显示 <b>${rows.length}</b> / ${state.watchlist.length} 条观察信号`;
    box.innerHTML = "";
    if (!rows.length) {
      box.appendChild(el("div", "watch-empty", "当前筛选下没有观察信号。"));
      return;
    }
    rows.forEach((item) => box.appendChild(watchCard(item)));
  }

  function miniBars(dims) {
    const wrap = el("div", "minibars");
    wrap.setAttribute("aria-hidden", "true");
    DIM_ORDER.forEach((k) => {
      const v = Math.max(0, Math.min(10, dims?.[k] ?? 0));
      const mb = el("div", "mb");
      mb.dataset.k = k;
      mb.title = `${DIM_LABELS[k]} ${v}/10`;
      mb.appendChild(el("span", "mb-track"));
      const fill = el("span", "mb-fill");
      fill.style.height = `${(v / 10) * 100}%`;
      mb.appendChild(fill);
      wrap.appendChild(mb);
    });
    return wrap;
  }

  function rowEl(need, rank) {
    const ds = need.demand_score || {};
    const v = VERDICTS[need.verdict_label] || VERDICTS["谨慎"];
    const opp = need.opportunity || {};

    const row = el("button", "row");
    row.type = "button";
    row.dataset.id = need.id;
    row.setAttribute("aria-label", `第 ${rank} 名：${need.title}，总分 ${ds.total || 0}，${need.verdict_label}`);
    row.style.animationDelay = `${Math.min(rank - 1, 12) * 30}ms`;

    // rank
    const rk = el("div", "rank");
    rk.appendChild(el("span", "rk num", String(rank)));
    rk.appendChild(el("span", "rk-sub", "RANK"));
    row.appendChild(rk);

    // main
    const main = el("div", "cell-main");
    const top = el("div", "row-top");
    top.appendChild(el("h2", null, esc(need.title)));
    top.appendChild(el("span", `verdict ${v.cls}`, esc(need.verdict_label)));
    main.appendChild(top);
    main.appendChild(el("p", "sum", esc(opp.purchase_reason || need.summary)));

    const tags = el("div", "meta-tags");
    tags.appendChild(el("span", "tag region", esc(need.region)));
    (need.source_tier_labels || []).slice(0, 2).forEach((s) => tags.appendChild(el("span", "tag tier", esc(s))));
    const srcs = (need.sources || []).slice(0, 3);
    srcs.forEach((s) => tags.appendChild(el("span", "tag src", esc(s))));
    const extra = (need.sources || []).length - srcs.length;
    if (extra > 0) tags.appendChild(el("span", "tag more", `+${extra}`));
    tags.appendChild(el("span", "tag more", `${need.signal_count || 0} 信号`));
    main.appendChild(tags);
    row.appendChild(main);

    // bars
    const bars = el("div", "cell-bars");
    bars.appendChild(miniBars(ds.dims));
    row.appendChild(bars);

    // score
    const score = el("div", `score ${v.scls}`);
    score.appendChild(el("span", "val num", String(ds.total ?? 0)));
    score.appendChild(el("span", "lab", "总分"));
    row.appendChild(score);

    row.addEventListener("click", () => openDetail(need, rank));
    return row;
  }

  function render() {
    const rows = computeView();
    const board = $("#board");
    board.innerHTML = "";

    const total = state.needs.length;
    const cEl = $("#count");
    cEl.innerHTML = `显示 <b>${rows.length}</b> / ${total} 个高置信机会 · 按${sortLabel()}降序`;
    renderWatchlist();

    if (!rows.length) {
      board.appendChild(emptyState());
      return;
    }
    rows.forEach((need, i) => board.appendChild(rowEl(need, i + 1)));
  }

  function emptyState() {
    const meta = state.meta || {};
    const noise = meta.noise_counts || {};
    const topNoise = Object.entries(noise).slice(0, 4)
      .map(([k, v]) => `<span class="tag">${esc(k)} ${esc(v)}</span>`).join("");
    const candidates = meta.candidates ?? 0;
    const signals = meta.signals ?? 0;
    return el("div", "empty empty-strong",
      `<b>今天没有高置信购买理由。</b>
       <p>严格闸从 ${esc(signals)} 条公开信号里只保留 ${esc(candidates)} 条候选，但没有一条达到入榜分数。当前结果不是采集失败，而是源池缺少 TrustMRR / Toolify / Product Hunt / 差评等高购买理由证据。</p>
       <div class="empty-tags">${topNoise}</div>`);
  }

  function sortLabel() {
    if (state.sort === "total") return "总分";
    if (state.sort === "signal_count") return "信号数";
    return DIM_LABELS[state.sort] || "总分";
  }

  function personaList(need) {
    const quotes = need.personas || {};
    const profiles = state.personaProfiles || DEFAULT_PERSONA_PROFILES;
    return Object.keys(quotes).map((key) => ({
      key,
      quote: quotes[key],
      name: profiles[key]?.name || key,
      tag: profiles[key]?.tag || "",
      avatar: profiles[key]?.avatar || key.slice(0, 1).toUpperCase(),
    }));
  }

  /* ============================================================
     DETAIL OVERLAY
     ============================================================ */
  function buildDetail(need, rank) {
    const ds = need.demand_score || {};
    const v = VERDICTS[need.verdict_label] || VERDICTS["谨慎"];
    const dims = ds.dims || {};
    const maxDim = Math.max(...DIM_ORDER.map((k) => dims[k] ?? 0), 0);

    const panel = el("div", "ov-panel");
    panel.setAttribute("role", "document");

    /* --- bar --- */
    const bar = el("div", "ov-bar");
    const head = el("div", "ov-head");
    const eyebrow = el("div", "ov-eyebrow");
    eyebrow.appendChild(el("span", "ov-rank num", `#${rank}`));
    eyebrow.appendChild(el("span", `verdict ${v.cls}`, esc(need.verdict_label)));
    eyebrow.appendChild(el("span", "tag region", esc(need.region)));
    head.appendChild(eyebrow);
    const h2 = el("h2", null, esc(need.title));
    h2.id = "ovTitle";
    head.appendChild(h2);
    head.appendChild(el("p", "ov-sum", esc(need.summary)));
    bar.appendChild(head);
    const x = el("button", "x", "&times;");
    x.type = "button";
    x.setAttribute("aria-label", "关闭详情");
    x.addEventListener("click", closeDetail);
    bar.appendChild(x);
    panel.appendChild(bar);

    /* --- body --- */
    const body = el("div", "ov-body");

    // score hero
    const hero = el("div", "ov-scorehero");
    const big = el("div", "ov-bigscore");
    const bigVal = el("span", `b num ${v.scls.replace("s-", "ink-")}`, String(ds.total ?? 0));
    bigVal.style.color = scoreColor(v.scls);
    big.appendChild(bigVal);
    big.appendChild(el("span", "l", "总分 / 100"));
    hero.appendChild(big);
    const vWrap = el("div", "ov-verdict-wrap");
    vWrap.appendChild(el("span", `verdict ${v.cls}`, esc(need.verdict_label)));
    if (need.recommendation) vWrap.appendChild(el("p", "ov-rec", esc(need.recommendation)));
    hero.appendChild(vWrap);
    body.appendChild(hero);

    // opportunity card
    if (need.opportunity) {
      const o = need.opportunity;
      const oSec = el("div", "ov-section");
      oSec.appendChild(el("h3", null, "购买理由卡片"));
      const grid = el("div", "opp-grid");
      [
        ["人群", o.who],
        ["场景", o.scenario],
        ["购买理由", o.purchase_reason],
        ["当前替代", o.current_workaround],
        ["MVP 切口", o.mvp],
        ["验证动作", o.validation],
      ].forEach(([k, val]) => {
        const card = el("div", "opp-card");
        card.appendChild(el("span", "opp-k micro", esc(k)));
        card.appendChild(el("p", "opp-v", esc(val || "待验证")));
        grid.appendChild(card);
      });
      oSec.appendChild(grid);
      body.appendChild(oSec);
    }

    // dimensions
    const dimSec = el("div", "ov-section");
    dimSec.appendChild(el("h3", null, "八维打分"));
    const dimsBox = el("div", "dims");
    DIM_ORDER.forEach((k) => {
      const val = dims[k] ?? 0;
      const row = el("div", "dim" + (val === maxDim && maxDim > 0 ? " peak" : ""));
      row.appendChild(el("span", "dk", esc(DIM_LABELS[k])));
      const bar2 = el("div", "dbar");
      const fill = el("i");
      fill.style.width = `${(val / 10) * 100}%`;
      bar2.appendChild(fill);
      row.appendChild(bar2);
      row.appendChild(el("span", "dv num", `${val}`));
      dimsBox.appendChild(row);
    });
    dimSec.appendChild(dimsBox);

    // reasons
    if (Array.isArray(ds.reasons) && ds.reasons.length) {
      const rl = el("ul", "reasons");
      ds.reasons.forEach((r) => rl.appendChild(el("li", null, esc(r))));
      dimSec.appendChild(rl);
    }
    body.appendChild(dimSec);

    // personas
    const pSec = el("div", "ov-section");
    pSec.appendChild(el("h3", null, "多视角判断 · 参考语气（模板生成，非核心判断）"));
    const pBox = el("div", "personas");
    personaList(need).forEach((p) => {
      if (!p.quote) return;
      const card = el("div", "persona");
      const nameRow = el("div", "pn");
      nameRow.appendChild(el("span", "pavatar", esc(p.avatar)));
      nameRow.appendChild(el("span", "pname", esc(p.name)));
      nameRow.appendChild(el("span", "ptag", esc(p.tag)));
      card.appendChild(nameRow);
      card.appendChild(el("p", "pquote", esc(p.quote)));
      pBox.appendChild(card);
    });
    pSec.appendChild(pBox);
    body.appendChild(pSec);

    // product forms
    if (Array.isArray(need.product_forms) && need.product_forms.length) {
      const fSec = el("div", "ov-section");
      fSec.appendChild(el("h3", null, "产品形态"));
      const scroll = el("div", "forms-scroll");
      const table = el("table", "formtab");
      table.innerHTML =
        "<thead><tr><th>形态</th><th>分数</th><th>变现</th><th>成本</th><th>备注</th></tr></thead>";
      const tb = el("tbody");
      need.product_forms.slice().sort((a, b) => (b.score || 0) - (a.score || 0)).forEach((f) => {
        const tr = el("tr");
        tr.appendChild(el("td", "f-form", esc(f.form)));
        const sc = el("td", "f-score num",
          `${esc(f.score)}<span class="f-score-bar"><i style="width:${Math.max(0, Math.min(100, f.score || 0))}%"></i></span>`);
        tr.appendChild(sc);
        tr.appendChild(el("td", null, esc(f.monetization)));
        tr.appendChild(el("td", null, esc(f.build_cost)));
        tr.appendChild(el("td", "f-note", esc(f.note)));
        tb.appendChild(tr);
      });
      table.appendChild(tb);
      scroll.appendChild(table);
      fSec.appendChild(scroll);
      body.appendChild(fSec);
    }

    // evidence
    if (Array.isArray(need.evidence) && need.evidence.length) {
      const eSec = el("div", "ov-section");
      eSec.appendChild(el("h3", null, "证据链接"));
      const evBox = el("div", "evidence");
      need.evidence.forEach((e) => {
        const a = el("a", "ev");
        a.href = e.url || "#";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.appendChild(el("span", "ev-src", esc(e.source_label)));
        if (e.source_tier_label) a.appendChild(el("span", "ev-tier", esc(e.source_tier_label)));
        a.appendChild(el("span", "ev-title", esc(e.title)));
        if (e.popularity != null) a.appendChild(el("span", "ev-pop num", String(e.popularity)));
        a.appendChild(el("span", "ev-arrow", "↗"));
        evBox.appendChild(a);
      });
      eSec.appendChild(evBox);
      body.appendChild(eSec);
    }

    panel.appendChild(body);
    return panel;
  }

  function scoreColor(scls) {
    return ({ "s-strong": "var(--ok)", "s-good": "var(--good)", "s-caution": "var(--warn)", "s-filter": "var(--mute)" }[scls]) || "var(--ink)";
  }

  function openDetail(need, rank) {
    const overlay = $("#overlay");
    const panel = buildDetail(need, rank);
    overlay.innerHTML = "";
    overlay.appendChild(panel);
    state.lastFocus = document.activeElement;

    overlay.hidden = false;
    // force reflow so transition runs
    void overlay.offsetWidth;
    overlay.classList.add("is-open");
    document.body.style.overflow = "hidden";
    overlay.scrollTop = 0;

    const closeBtn = $(".x", overlay);
    if (closeBtn) closeBtn.focus();
  }

  function closeDetail() {
    const overlay = $("#overlay");
    overlay.classList.remove("is-open");
    document.body.style.overflow = "";
    const finish = () => {
      overlay.hidden = true;          // 关闭态 display:none，避免遮罩吃掉点击
      overlay.innerHTML = "";
      overlay.removeEventListener("transitionend", finish);
      if (state.lastFocus && document.contains(state.lastFocus)) state.lastFocus.focus();
    };
    // transitionend may not fire if reduced-motion; guard with timeout
    overlay.addEventListener("transitionend", finish);
    setTimeout(() => { if (!overlay.hidden) finish(); }, 320);
  }

  /* focus trap + esc */
  function onKeydown(e) {
    const overlay = $("#overlay");
    if (overlay.hidden) return;
    if (e.key === "Escape") { e.preventDefault(); closeDetail(); return; }
    if (e.key !== "Tab") return;
    const focusables = overlay.querySelectorAll('a[href], button, select, input, [tabindex]:not([tabindex="-1"])');
    if (!focusables.length) return;
    const first = focusables[0];
    const last = focusables[focusables.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  /* ============================================================
     WIRING
     ============================================================ */
  function wireControls() {
    $("#streamTabs").addEventListener("click", (event) => {
      const tab = event.target.closest("[data-view]");
      if (tab) setView(tab.dataset.view);
    });

    // search
    const search = $("#search");
    const clear = $("#searchClear");
    let t;
    search.addEventListener("input", () => {
      clear.hidden = !search.value;
      clearTimeout(t);
      t = setTimeout(() => { state.filters.q = search.value; render(); }, 120);
    });
    clear.addEventListener("click", () => {
      search.value = ""; state.filters.q = ""; clear.hidden = true; render(); search.focus();
    });

    // sort
    $("#sortSelect").addEventListener("change", (e) => { state.sort = e.target.value; render(); });

    // overlay: click backdrop to close
    const overlay = $("#overlay");
    overlay.addEventListener("click", (e) => { if (e.target === overlay) closeDetail(); });
    document.addEventListener("keydown", onKeydown);

    // theme toggle
    const root = document.documentElement;
    const toggle = $("#themeToggle");
    const apply = (theme) => {
      root.setAttribute("data-theme", theme);
      toggle.setAttribute("aria-label", theme === "dark" ? "切换到浅色主题" : "切换到深色主题");
      try { localStorage.setItem("dr-theme", theme); } catch {}
    };
    try {
      const saved = localStorage.getItem("dr-theme");
      if (saved === "dark" || saved === "light") apply(saved);
      else if (window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) apply("light");
    } catch {}
    toggle.addEventListener("click", () => {
      apply(root.getAttribute("data-theme") === "dark" ? "light" : "dark");
    });
    $("#feedbackExport").addEventListener("click", exportFeedback);
    const profileFile = $("#profileFile");
    $("#profileImport").addEventListener("click", () => profileFile.click());
    profileFile.addEventListener("change", () => {
      if (profileFile.files?.[0]) importProfileFile(profileFile.files[0]);
      profileFile.value = "";
    });
  }

  function bootRender() {
    renderMasthead();
    renderAttentionSummary();
    buildFacets();
    render();
    renderRoute();
    renderProfileStatus();
  }

  /* ---------- init ---------- */
  state.localProfile = loadLocalProfile();
  state.profileOrigin = state.localProfile ? "browser" : "";
  importProfileFromHash();
  wireControls();
  loadPrivateLocalProfile().then(loadData);
})();
