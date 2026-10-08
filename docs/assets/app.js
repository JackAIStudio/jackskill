/* 吴杰克 Jack · 自媒体数据站
 * 纯静态：数据来自同目录 data/videos.json（由 scripts/build-site.mjs 生成）。
 * 零第三方依赖，图表全部手写 SVG。
 */

// 用各平台官方 logo 的色，不要按「微信=绿」这种印象配。
// 抖音最麻烦：它的品牌红 #FE2C55 和小红书的 #FF2442 几乎一样，
// 但抖音 logo 本体是黑的（青 #25F4EE 和红只是故障风描边），所以用黑——
// 既对得上 logo，又能和小红书分开。
// short 是列头用的短名：表头里挤不下「微信视频号」五个字
const PLAT = {
  bilibili:        { label: "B 站",      short: "B 站",   color: "#00AEEC" },
  douyin:          { label: "抖音",       short: "抖音",   color: "#161823" },
  xiaohongshu:     { label: "小红书",     short: "小红书", color: "#FF2442" },
  wechat_channels: { label: "微信视频号", short: "视频号", color: "#FA9D3B" },
};
const ORDER = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];
const METRICS = ["views", "likes", "collects", "shares", "comments"];

/* ---------------- 小工具 ---------------- */

const $ = (id) => document.getElementById(id);
const esc = (s) =>
  String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function fmtInt(n) {
  return (n || 0).toLocaleString("zh-CN");
}
function fmtCompact(n) {
  n = n || 0;
  if (n >= 100000000) return (n / 100000000).toFixed(2) + " 亿";
  if (n >= 10000) return (n / 10000).toFixed(1) + " 万";
  return fmtInt(n);
}
function fmtDuration(sec) {
  if (!sec) return "—";
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return `${m}:${String(s).padStart(2, "0")}`;
}
function sum(arr) {
  return arr.reduce((a, b) => a + b, 0);
}
function median(arr) {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}
/** 互动率 = （点赞 + 收藏 + 分享 + 评论）/ 播放 */
function engagement(p) {
  if (!p || !p.views) return 0;
  return (p.likes + p.collects + p.shares + p.comments) / p.views;
}
function collectRate(p) {
  if (!p || !p.views) return 0;
  return p.collects / p.views;
}
function platKeys(v) {
  return ORDER.filter((k) => v.platforms[k]);
}
/** 这条平台记录有没有真实数据。五个指标全 0 的是待补录的占位记录，不算。 */
function hasData(p) {
  return Boolean(p) && !p.empty;
}
/** 只有真采到数的平台。统计和中位数一律用这个，不用 platKeys。 */
function dataKeys(v) {
  return ORDER.filter((k) => hasData(v.platforms[k]));
}

// 链接分三类，标签必须跟着变：
//   video  作品页    → 「看原片」
//   home   平台主页   → 「平台主页」（小红书和视频号在数据里存的就是主页）
//   none   其余一切   → 不给链接。观众点进去只有登录墙，给了他也没用。
//
// 判据是白名单，不是黑名单。这已经是第二次栽在黑名单上了：
//   第一版只排除 xiaohongshu.com 和 channels.weixin.qq.com 两个精确的主页域名，
//   于是 92 条 creator.douyin.com 被当成作品直链；
//   改成「排除 creator.* + 空路径的主页」之后，
//   channels.weixin.qq.com/platform/post/list 又漏了进来——那是视频号创作者后台。
// 白名单的失效方向是「本来能打开却说不确定」，比反过来安全。漏掉的形态由
// check-data.mjs 报出来，再补进下面两个数组。
const VIDEO_URL = [
  /^https?:\/\/(www\.)?bilibili\.com\/video\/BV[0-9A-Za-z]+/i,
  /^https?:\/\/(www\.)?douyin\.com\/video\/\d+/i,
  /^https?:\/\/(www\.)?xiaohongshu\.com\/explore\/[0-9a-z]+/i,
];
const HOME_URL = [
  /^https?:\/\/(www\.)?xiaohongshu\.com\/?$/i,
  /^https?:\/\/channels\.weixin\.qq\.com\/?$/i,
];

function urlKind(url) {
  const u = (url || "").trim();
  if (!u) return "none";
  if (VIDEO_URL.some((re) => re.test(u))) return "video";
  if (HOME_URL.some((re) => re.test(u))) return "home";
  return "none";
}

function highlight(text, q) {
  const safe = esc(text);
  if (!q) return safe;
  const needle = esc(q).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  if (!needle) return safe;
  return safe.replace(new RegExp(needle, "gi"), (m) => `<mark>${m}</mark>`);
}

// 搜索命中的平台标题。主题里本来就含 q 的那些不算——那已经在标题上高亮了，
// 再重复一遍只是把行撑高。跨平台重复的同一条标题也去掉。
function matchedPlatTitles(v, q) {
  if (!q) return [];
  const needle = q.toLowerCase();
  if ((v.topic || "").toLowerCase().includes(needle)) return [];
  const seen = new Set();
  const out = [];
  for (const k of ORDER) {
    const t = v.platforms[k] && v.platforms[k].title;
    if (!t || !t.toLowerCase().includes(needle) || seen.has(t)) continue;
    seen.add(t);
    out.push(t);
  }
  return out;
}

/* ---------------- tooltip ---------------- */

const tip = document.createElement("div");
tip.className = "tip";
tip.hidden = true;
document.body.appendChild(tip);

function showTip(html, evt) {
  tip.innerHTML = html;
  tip.hidden = false;
  const pad = 14;
  const r = tip.getBoundingClientRect();
  let x = evt.clientX + pad, y = evt.clientY + pad;
  if (x + r.width > innerWidth - 8) x = evt.clientX - r.width - pad;
  if (y + r.height > innerHeight - 8) y = evt.clientY - r.height - pad;
  tip.style.left = Math.max(8, x) + "px";
  tip.style.top = Math.max(8, y) + "px";
}
function hideTip() { tip.hidden = true; }

/* ---------------- SVG 帮手 ---------------- */

const NS = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs = {}, parent) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}

/* ---------------- 启动 ---------------- */

let DATA = null;

(async function main() {
  try {
    const res = await fetch("data/videos.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    DATA = await res.json();
  } catch (err) {
    document.querySelector("main").innerHTML =
      `<section class="section"><h2>数据没能加载</h2>
       <p class="note">读取 <code>docs/data/videos.json</code> 失败（${esc(err.message)}）。
       先跑一次 <code>node scripts/build-site.mjs</code>；本地预览请用
       <code>python3 -m http.server</code> 起个静态服务，直接双击 html 会被浏览器的
       file:// 策略挡住。</p></section>`;
    return;
  }
  renderStamp();
  renderPlatforms();
  renderTrend("median");
  initTable();
})();

function renderStamp() {
  const [from, to] = DATA.dateRange;
  const totalViews = sum(DATA.videos.map((v) => v.summary.views));
  const withTr = DATA.videos.filter((v) => v.transcript).length;
  $("stamp").textContent =
    `${DATA.count} 期 · ${from} ~ ${to} · 全平台 ${fmtCompact(totalViews)} 播放 · ${withTr} 篇口播逐字稿` +
    ` · 构建于 ${new Date(DATA.generatedAt).toLocaleString("zh-CN")}`;
}

/* ---------------- 平台表现 ---------------- */

function renderPlatforms() {
  // 只统计采到数的记录。待补录的占位记录（五个指标全 0）如果混进来，
  // 会把中位播放整个拉下来——抖音那 21 条就把它从 623 拉到了 480。
  const rows = ORDER.map((key) => {
    const all = DATA.videos.map((v) => v.platforms[key]).filter(Boolean);
    const list = all.filter(hasData);
    const views = list.map((p) => p.views);
    const totalViews = sum(views);
    const totalEng = sum(list.map((p) => p.likes + p.collects + p.shares + p.comments));
    return {
      key,
      label: PLAT[key].label,
      color: PLAT[key].color,
      n: list.length,
      blanks: all.length - list.length,
      totalViews,
      medianViews: median(views),
      eng: totalViews ? totalEng / totalViews : 0,
      collectRate: totalViews ? sum(list.map((p) => p.collects)) / totalViews : 0,
    };
  });

  $("platTable").innerHTML = `
    <thead>
      <tr>
        <th>平台</th><th>收录期数</th><th>总播放</th><th>中位播放</th><th>互动率</th><th>收藏率</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map((r) => `
        <tr>
          <td><span class="plat-name"><i class="pdot" style="background:${r.color}"></i>${r.label}</span></td>
          <td title="${r.blanks ? `另有 ${r.blanks} 期待补录的占位记录，不计入` : "每一期都采到了数"}">${fmtInt(r.n)}</td>
          <td>${fmtCompact(r.totalViews)}</td>
          <td>${fmtCompact(r.medianViews)}</td>
          <td>${(r.eng * 100).toFixed(2)}%</td>
          <td>${(r.collectRate * 100).toFixed(2)}%</td>
        </tr>`).join("")}
      <tr class="dim">
        <td>全部作品</td>
        <td title="全站收录的总期数。不是上面四行相加——同一期可能发在多个平台">${fmtInt(DATA.count)}</td>
        <td title="四平台播放量之和">${fmtCompact(sum(rows.map((r) => r.totalViews)))}</td>
        <td class="dim">—</td>
        <td class="dim">—</td>
        <td class="dim">—</td>
      </tr>
    </tbody>`;

  const blanks = sum(rows.map((r) => r.blanks));
  $("platNote").textContent =
    `收录期数只算采到数据的期。数据源里另有 ${fmtInt(blanks)} 条待补录的占位记录（五个指标全 0），` +
    `它们不进这一张表的任何一列。「全部作品」那行的 ${fmtInt(DATA.count)} 是全站总期数，不是上面四行相加——` +
    `同一期可能发在多个平台。`;
}

/* ---------------- 时间线 ---------------- */

const MONTH_NAMES = ["1月","2月","3月","4月","5月","6月","7月","8月","9月","10月","11月","12月"];

function monthList() {
  const [from, to] = DATA.dateRange;
  const out = [];
  let [y, m] = from.slice(0, 7).split("-").map(Number);
  const [ty, tm] = to.slice(0, 7).split("-").map(Number);
  while (y < ty || (y === ty && m <= tm)) {
    out.push(`${y}-${String(m).padStart(2, "0")}`);
    m++;
    if (m > 12) { m = 1; y++; }
  }
  return out;
}

const TREND_MODES = [
  { id: "median", label: "月度中位播放" },
  { id: "total",  label: "月度总播放" },
  // 叫「收录」不叫「发布」：只数采到数的期，待补录的占位记录不算，
  // 三个模式用的是同一批记录，不然三条线各说各的人口。
  { id: "count",  label: "月度收录期数" },
];

function renderTrend(mode) {
  const months = monthList();
  const buckets = new Map(months.map((m) => [m, { bilibili: [], douyin: [], xiaohongshu: [], wechat_channels: [] }]));

  for (const v of DATA.videos) {
    const mk = (v.date || "").slice(0, 7);
    const b = buckets.get(mk);
    if (!b) continue;
    // 只放采到数的记录。占位记录（全 0）会把这个月的中位数拉到 0，
    // 而对数轴上的 0 画在最低网格线上，看着像「有一点播放」。
    for (const k of dataKeys(v)) b[k].push(v.platforms[k]);
  }

  const series = ORDER.map((key) => ({
    key,
    label: PLAT[key].label,
    color: PLAT[key].color,
    values: months.map((m) => {
      const list = buckets.get(m)[key];
      if (!list.length) return null;
      if (mode === "count") return list.length;
      if (mode === "total") return sum(list.map((p) => p.views));
      return median(list.map((p) => p.views));
    }),
  }));

  const allVals = series.flatMap((s) => s.values).filter((x) => x !== null);
  const rawMax = Math.max(1, ...allVals);

  // 月度播放量能跨几十倍（几百到几千），线性纵轴会把绝大多数月份压成一条平线，
  // 所以播放量走对数刻度；期数本身范围小，保持线性。
  const useLog = mode !== "count";
  let yMin = 0, yMax = niceMax(rawMax), gridVals;
  if (useLog) {
    const pos = allVals.filter((v) => v > 0);
    const eLo = Math.floor(Math.log10(Math.min(...pos)));
    const eHi = Math.ceil(Math.log10(Math.max(...pos)));
    yMin = Math.pow(10, eLo);
    yMax = Math.pow(10, Math.max(eHi, eLo + 1));
    gridVals = [];
    for (let e = eLo; e <= Math.log10(yMax) + 1e-9; e++) {
      for (const m of [1, 2, 5]) {
        const v = m * Math.pow(10, e);
        if (v >= yMin - 1e-9 && v <= yMax + 1e-9) gridVals.push(Math.round(v));
      }
    }
    gridVals = [...new Set(gridVals)].sort((a, b) => a - b);
  } else {
    gridVals = [0, 1, 2, 3, 4].map((i) => (yMax / 4) * i);
  }

  const W = 900, H = 340;
  const pad = { l: 58, r: 18, t: 14, b: 36 };
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const x = (i) => pad.l + (months.length === 1 ? iw / 2 : (i / (months.length - 1)) * iw);
  const y = useLog
    ? (v) => {
        const lo = Math.log10(yMin), hi = Math.log10(yMax);
        return pad.t + ih - ((Math.log10(Math.max(v, yMin)) - lo) / (hi - lo)) * ih;
      }
    : (v) => pad.t + ih - (v / yMax) * ih;

  const svg = $("trendChart");
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);

  // 横向网格
  for (const v of gridVals) {
    svgEl("line", { class: "grid-line", x1: pad.l, x2: W - pad.r, y1: y(v), y2: y(v) }, svg);
    const t = svgEl("text", { class: "axis-text", x: pad.l - 9, y: y(v) + 4, "text-anchor": "end" }, svg);
    t.textContent = mode === "count" ? String(Math.round(v)) : fmtCompact(Math.round(v));
  }

  // x 轴：每年 1 月打一个刻度
  months.forEach((m, i) => {
    if (m.endsWith("-01") || i === 0) {
      const t = svgEl("text", { class: "axis-text", x: x(i), y: H - 12, "text-anchor": "middle" }, svg);
      t.textContent = m.slice(0, 4);
    }
  });

  // 折线（缺口即断线）
  for (const s of series) {
    let d = "", pen = false;
    s.values.forEach((v, i) => {
      if (v === null) { pen = false; return; }
      d += `${pen ? "L" : "M"}${x(i).toFixed(1)},${y(v).toFixed(1)}`;
      pen = true;
    });
    if (d) svgEl("path", { class: "series-line", d, stroke: s.color }, svg);
    s.values.forEach((v, i) => {
      if (v === null) return;
      svgEl("circle", { class: "series-dot", cx: x(i), cy: y(v), r: 2.6, fill: s.color }, svg);
    });
  }

  // 悬停竖带
  const bw = iw / Math.max(1, months.length);
  months.forEach((m, i) => {
    const band = svgEl("rect", {
      class: "hover-band", x: x(i) - bw / 2, y: pad.t, width: bw, height: ih,
    }, svg);
    band.addEventListener("mousemove", (evt) => {
      const lines = series.map((s) => {
        const v = s.values[i];
        const shown = v === null ? "—" : mode === "count" ? `${v} 期` : fmtCompact(v);
        return `<span style="color:${s.color}">■</span> ${s.label} <b>${shown}</b>`;
      });
      showTip(`<b>${m.slice(0, 4)} 年 ${MONTH_NAMES[Number(m.slice(5, 7)) - 1]}</b><br>${lines.join("<br>")}`, evt);
    });
    band.addEventListener("mouseleave", hideTip);
  });

  // 工具条
  const tb = $("trendToolbar");
  tb.innerHTML = "";
  for (const m of TREND_MODES) {
    const b = document.createElement("button");
    b.textContent = m.label;
    b.setAttribute("aria-pressed", String(m.id === mode));
    b.onclick = () => renderTrend(m.id);
    tb.appendChild(b);
  }

  const note = mode === "count"
    ? "只数采到数的期，待补录的占位记录不算。断线的地方就是那个月该平台没有数据——早期平台没接入，不是没发。"
    : mode === "total"
    ? "总播放会被爆款和期数同时影响，看趋势建议切回中位播放。（纵轴为对数刻度）"
    : "中位数：把那个月该平台所有视频的播放量排序取中间值，单条爆款拉不动它。待补录的占位记录不算。（纵轴为对数刻度）";
  $("trendLegend").innerHTML =
    ORDER.map((k) => `<span><i class="plat-dot" style="background:${PLAT[k].color};display:inline-block"></i>${PLAT[k].label}</span>`).join("") +
    `<span class="legend-note">${note}</span>`;
}

function niceMax(v) {
  if (v <= 0) return 1;
  const exp = Math.floor(Math.log10(v));
  const base = Math.pow(10, exp);
  const n = v / base;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * base;
}

/* ---------------- 作品表 ---------------- */

// 列的唯一定义处：表头和数据行都从这里生成，加一列只改这里。
// 分平台播放量各占一列——竖着扫才能比较，塞进主题下面那行小字是比不出来的。
//
// 最后两列跟着上面的指标走，值在 renderHead / renderTable 里现算：
//   合计 = 当前指标的四平台之和（以前这里写死 views，所以切到点赞时它还在显示播放）
//   效率 = 当前指标 ÷ 播放（播放视图下退回收藏率，见 effMetricKey）
const COLS = [
  { key: "date",        label: "日期",   cls: "col-date" },
  { key: "topic",       label: "主题",   cls: "col-topic" },
  { key: "duration",    label: "时长",   cls: "col-num" },
  ...ORDER.map((k) => ({ key: k, label: PLAT[k].short, cls: "col-num col-platnum", plat: k })),
  { key: "total",       label: "合计",   cls: "col-num col-total" },
  { key: "rate",        label: "效率",   cls: "col-num col-rate" },
];

let state = { q: "", filter: "all", platMetric: "views", sort: { key: "date", dir: "desc" }, filtered: [] };

function metricLabel(key) {
  const m = PLAT_METRICS.find((x) => x.key === key);
  return m ? m.label : "播放";
}

// 效率列算的是哪个指标。播放视图下没有「播放的效率」，所以退回收藏率：
// 播放量只说明多少人刷到，收藏才说明多少人觉得以后还要用。
function effMetricKey() {
  return state.platMetric === "views" ? "collects" : state.platMetric;
}
function effLabel() {
  return metricLabel(effMetricKey()) + "率";
}
/** 效率 = 当前指标 ÷ 播放。分母是 0 就给 0，不给 NaN 或 Infinity。 */
function effRate(summary) {
  if (!summary || !summary.views) return 0;
  return (summary[effMetricKey()] || 0) / summary.views;
}

/** 已升序排好的数组里取第 p 分位（p = 0.9 就是「前 10%」的门槛）。 */
function quantile(sortedAsc, p) {
  if (!sortedAsc.length) return Infinity;
  return sortedAsc[Math.min(sortedAsc.length - 1, Math.floor((sortedAsc.length - 1) * p))];
}

// 橙色高亮 = 该指标的效率排进全站前 10%。
// 阈值必须按当前指标现算：点赞率全站 1.96%、收藏率 1.02%、评论率 0.40%，
// 根本不是一个量级。写死一个数就会出现「列上标着点赞率，亮的是收藏率的标准」。
function effThreshold() {
  const rates = DATA.videos
    .filter((v) => v.summary.views > 0)
    .map((v) => effRate(v.summary))
    .sort((a, b) => a - b);
  return quantile(rates, 0.9);
}

// 抽屉那一列永远是「分平台收藏率」，样本是每一期 × 每个平台，
// 和表格里按整期算的口径不是一回事，所以门槛单独算一次。
function platCollectThreshold() {
  const rates = DATA.videos
    .flatMap((v) => ORDER.map((k) => v.platforms[k]).filter(Boolean))
    .filter((p) => p.views > 0)
    .map((p) => p.collects / p.views)
    .sort((a, b) => a - b);
  return quantile(rates, 0.9);
}

// 平台列换成别的指标时，排序、表头、单元格必须一起跟着换，否则会出现
// 「列上写着收藏、排的是播放」这种对不上的情况。
function platValue(v, k) {
  const p = v.platforms[k];
  // -1 = 没有可比的值（这一期没发到这个平台，或者只有待补录的占位记录），
  // 排序时沉到最后，而不是被当成 0 混在真实数据里。
  return hasData(p) ? p[state.platMetric] || 0 : -1;
}

function sortValue(v, key) {
  if (ORDER.includes(key)) return platValue(v, key);
  if (key === "total") return v.summary[state.platMetric] || 0;
  if (key === "rate") return effRate(v.summary);
  if (key === "duration") return v.duration;
  return v.date;
}

// 排序只留「点列头」这一套。再放一个排序下拉就是两套机制抢同一件事，
// 迟早出现下拉写着「最新在前」而实际按播放量排的情况。
function renderHead() {
  const metric = metricLabel(state.platMetric);

  $("worksHead").innerHTML = `<tr>${COLS.map((c) => {
    const active = state.sort.key === c.key;
    const arrow = active ? (state.sort.dir === "asc" ? " ▲" : " ▼") : "";
    const cls = `${c.cls}${active ? " sorted" : ""}`;
    // 平台列、合计列、效率列都跟着指标走，所以表头一律两行：
    // 上行写这一列是谁，下行写它装的是哪个量、怎么算出来的。
    // 表头是 sticky 的，指标必须跟着一起滚动，不然滚下去就忘了这几列是什么。
    if (c.plat) {
      return `<th class="${cls}" data-key="${c.key}">`
        + `<span class="th-plat"><i class="pdot" style="background:${PLAT[c.plat].color}"></i>${c.label}</span>`
        + `<span class="th-metric">${metric}${arrow}</span></th>`;
    }
    if (c.key === "total") {
      return `<th class="${cls}" data-key="${c.key}">`
        + `<span class="th-plat">${c.label}</span>`
        + `<span class="th-metric">${metric}${arrow}</span></th>`;
    }
    // 效率列的名字随指标现算，COLS 里那个 label 只是占位
    if (c.key === "rate") {
      return `<th class="${cls}" data-key="${c.key}">`
        + `<span class="th-plat">${effLabel()}${arrow}</span>`
        + `<span class="th-metric">${metricLabel(effMetricKey())} ÷ 播放</span></th>`;
    }
    return `<th class="${cls}" data-key="${c.key}">${c.label}${arrow}</th>`;
  }).join("")}</tr>`;

  $("worksHead").querySelectorAll("th").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.key;
      state.sort = state.sort.key === key
        ? { key, dir: state.sort.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "desc" };
      renderHead();
      renderTable();
    });
  });
}

function initTable() {
  // 平台和逐字稿合成一个筛选器：两项都是「把列表收窄」，分两个下拉只是多占地方
  $("platFilter").innerHTML = `
    <option value="all">全部作品</option>
    <optgroup label="按平台">
      ${ORDER.map((k) => `<option value="plat:${k}">有${PLAT[k].label}数据</option>`).join("")}
    </optgroup>
    <optgroup label="按逐字稿">
      <option value="tr:yes">有逐字稿</option>
      <option value="tr:no">没有逐字稿</option>
    </optgroup>`;

  $("q").addEventListener("input", (e) => { state.q = e.target.value.trim(); renderTable(); });
  $("platFilter").addEventListener("change", (e) => { state.filter = e.target.value; renderTable(); });
  $("drawerClose").addEventListener("click", closeDrawer);
  $("drawerMask").addEventListener("click", closeDrawer);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeDrawer(); });

  renderLegend();
  renderHead();
  renderTable();
}

// 平台那四列显示哪个指标。只换指标、不换列数——表格的形制始终不变，
// 这是它和「展开行」的关键区别：扫读的节奏不会被破坏。
const PLAT_METRICS = [
  { key: "views",    label: "播放" },
  { key: "likes",    label: "点赞" },
  { key: "collects", label: "收藏" },
  { key: "shares",   label: "分享" },
  { key: "comments", label: "评论" },
];

function renderLegend() {
  // 页面上凡是「用颜色/形状编码但没写字」的地方都在这里交代清楚。
  // 图例必须待在表格上方：表格限高，放在下面会被推到屏幕外。
  const bar = PLAT_METRICS.map((m) =>
    `<button type="button" data-metric="${m.key}" aria-pressed="${state.platMetric === m.key}">${m.label}</button>`
  ).join("");

  // 末列的算式和橙色阈值都写在图例里。以前这两个数在页面上都没交代：
  // 收藏率没说除以什么，3% 也没说是怎么定的，看完只能猜。
  const effKey = effMetricKey();
  const th = effThreshold();

  $("platLegend").innerHTML =
    `<span class="lg-label">平台列</span><span class="metric-bar">${bar}</span>` +
    `<span class="lg-sep"></span>` +
    `<span class="lg-note">末列 <b>${effLabel()}</b> = ${metricLabel(effKey)} ÷ 播放</span>` +
    `<span class="lg-sep"></span>` +
    `<span class="lg-note"><b class="rate-hot">橙色</b> = 排进全站前 10%（≥ ${(th * 100).toFixed(1)}%）</span>` +
    `<span class="lg-sep"></span>` +
    `<span class="lg-note">「—」= 该平台没有数据（没发，或者还没补数）</span>`;

  $("platLegend").querySelectorAll("button[data-metric]").forEach((b) => {
    b.addEventListener("click", () => {
      state.platMetric = b.dataset.metric;
      renderLegend();
      renderHead();
      renderTable();
    });
  });
}

function applyFilters() {
  const q = state.q.toLowerCase();
  const [kind, value] = state.filter.split(":");
  let list = DATA.videos.filter((v) => {
    // 「有抖音数据」要的是有数据，不是有那条占位记录
    if (kind === "plat" && !hasData(v.platforms[value])) return false;
    if (kind === "tr" && (value === "yes") !== Boolean(v.transcript)) return false;
    if (!q) return true;
    if (v.topic.toLowerCase().includes(q)) return true;
    if (v.transcript && v.transcript.paragraphs.join("").toLowerCase().includes(q)) return true;
    // 各平台标题也要搜。抖音和视频号那条标题是「主题 + #话题标签」，
    // 搜「#jackskill」这类标签以前是搜不到的。
    if (Object.values(v.platforms).some((p) => (p.title || "").toLowerCase().includes(q))) return true;
    return false;
  });

  const mul = state.sort.dir === "asc" ? 1 : -1;
  list.sort((a, b) => {
    if (state.sort.key === "topic") return a.topic.localeCompare(b.topic) * mul;
    const x = sortValue(a, state.sort.key);
    const y = sortValue(b, state.sort.key);
    if (x < y) return -1 * mul;
    if (x > y) return 1 * mul;
    return 0;
  });
  return list;
}

function renderTable() {
  // 全部命中项一次渲染完：表格自己限高滚动，不再分页。
  // 几百行的量级浏览器毫无压力，翻页反倒让「找那一期」变麻烦。
  state.filtered = applyFilters();
  const list = state.filtered;
  const body = $("worksBody");

  if (!state.filtered.length) {
    body.innerHTML = `<tr><td colspan="${COLS.length}" class="empty">没有符合条件的作品。</td></tr>`;
    $("resultCount").textContent = "";
    return;
  }

  // 末两列的动态量在这里算一次，别在几百行的循环里反复算阈值。
  const effKey = effMetricKey();
  const effName = effLabel();
  const th = effThreshold();

  body.innerHTML = list
    .map((v) => {
      const keys = platKeys(v);
      const er = effRate(v.summary);
      const hot = er >= th ? " rate-hot" : "";
      const erTip = `${effName} = ${metricLabel(effKey)} ${fmtInt(v.summary[effKey])} ÷ 播放 ${fmtInt(v.summary.views)}`;

      // 平台格显示当前选中的指标；悬浮提示始终给那一格的完整明细，
      // 所以换了指标也不用担心看不到别的数
      const cells = ORDER.map((k) => {
        const p = v.platforms[k];
        if (!p) return `<td class="col-num col-platnum none">—</td>`;
        // 占位记录（五个指标全 0）不显示成 0——那会读成「这期在抖音真的 0 播放」。
        // 显示成「—」，和「没发到这个平台」同一格，靠悬浮提示区分。
        if (!hasData(p)) {
          const t = `${PLAT[k].label} · ${v.date}\n这一期有记录，但五个指标全是 0（待补录的占位记录），不是真的 0 播放`;
          return `<td class="col-num col-platnum none" title="${esc(t)}">—</td>`;
        }
        const rate = p.views ? (collectRate(p) * 100).toFixed(1) + "%" : "—";
        const tip = `${PLAT[k].label} · ${v.date}
播放 ${fmtInt(p.views)}
点赞 ${fmtInt(p.likes)} · 收藏 ${fmtInt(p.collects)}
分享 ${fmtInt(p.shares)} · 评论 ${fmtInt(p.comments)}
收藏率 ${rate}`;
        return `<td class="col-num col-platnum" title="${esc(tip)}">${fmtCompact(p[state.platMetric])}</td>`;
      }).join("");

      // 这一行的小字说的是「这一期真实采到了什么」，所以看的是有数据的平台，
      // 不是有记录的平台。只有占位记录的期（全站 2 期）不能写成「赞 0 · 藏 0」——
      // 那是「没采到数」，不是「互动是 0」。
      const live = dataKeys(v);
      const eng = live.length
        ? `赞 ${fmtInt(v.summary.likes)} · 藏 ${fmtInt(v.summary.collects)} · 转 ${fmtInt(v.summary.shares)} · 评 ${fmtInt(v.summary.comments)}`
        : keys.length
        ? "这一期还没有采到数据，只有待补录的占位记录"
        : "无平台数据";

      // 平台标题（抖音那串 #话题）和主题常常不一样，搜索也扫它们。
      // 命中了就得在行里露出来，不然搜索结果看着像凭空多出来的。
      const hits = matchedPlatTitles(v, state.q);
      const hitLine = hits.length
        ? `<div class="sub sub-hit">平台标题命中：${hits.map((t) => highlight(t, state.q)).join("　／　")}</div>`
        : "";

      return `<tr data-id="${esc(v.id)}"${live.length ? "" : ' class="is-empty"'}>
        <td class="col-date">${v.date}</td>
        <td class="col-topic"><div class="t">${highlight(v.topic, state.q)}</div><div class="sub">${esc(eng)}</div>${hitLine}</td>
        <td class="col-num col-dim">${fmtDuration(v.duration)}</td>
        ${cells}
        <td class="col-num col-total" title="四平台${metricLabel(state.platMetric)}之和">${fmtCompact(v.summary[state.platMetric] || 0)}</td>
        <td class="col-num${hot}" title="${esc(erTip)}">${v.summary.views ? (er * 100).toFixed(1) + "%" : "—"}</td>
      </tr>`;
    })
    .join("");

  body.querySelectorAll("tr[data-id]").forEach((tr) => {
    tr.addEventListener("click", () => {
      const v = DATA.videos.find((x) => x.id === tr.dataset.id);
      if (v) openDrawer(v);
    });
  });

  $("resultCount").textContent = `${fmtInt(state.filtered.length)} 期`;
}


/* ---------------- 详情抽屉 ---------------- */

// 表格负责「比」，抽屉负责「看」。展开行试过，一行 44px 一行 400px
// 会把扫读的节奏打乱，所以明细还是回到独立的一层面板上来。
function openDrawer(v) {
  const keys = platKeys(v);
  // 这张小表里播放和收藏同屏，收藏率当场就能验算——所以它是全站少数几个
  // 不用额外解释也站得住的比率。橙色门槛按「每一期 × 每个平台」的分布算。
  const pcThreshold = platCollectThreshold();

  const rows = keys.map((k) => {
    const p = v.platforms[k];
    const cr = collectRate(p);
    // 占位记录照常占一行——读者该看见「这期在抖音有记录但没采到数」，
    // 只是数值一律给「—」，不假装成 0。
    if (!hasData(p)) {
      const t = "这一期有记录，但五个指标全是 0（待补录的占位记录），不是真的 0 播放";
      return `<tr class="dim">
      <td><span class="plat-name"><i class="pdot" style="background:${PLAT[k].color}"></i>${PLAT[k].label}</span></td>
      <td colspan="6" title="${esc(t)}">待补录，没有数据</td>
    </tr>`;
    }
    const tip = `收藏率 = 收藏 ${fmtInt(p.collects)} ÷ 播放 ${fmtInt(p.views)}`;
    return `<tr>
      <td><span class="plat-name"><i class="pdot" style="background:${PLAT[k].color}"></i>${PLAT[k].label}</span></td>
      <td>${fmtInt(p.views)}</td>
      <td>${fmtInt(p.likes)}</td>
      <td>${fmtInt(p.collects)}</td>
      <td>${fmtInt(p.shares)}</td>
      <td>${fmtInt(p.comments)}</td>
      <td${cr >= pcThreshold ? ' class="rate-hot"' : ""} title="${esc(tip)}">${p.views ? (cr * 100).toFixed(1) + "%" : "—"}</td>
    </tr>`;
  }).join("");

  // 三分类：作品页给链接，平台主页给链接，创作者后台不给——
  // 那是自己的后台，观众点进去只有登录墙，挂着它比不挂更糟。
  const links = keys.map((k) => {
    const p = v.platforms[k];
    const kind = urlKind(p.url);
    if (kind === "none") {
      return `<span class="src-none" title="${esc(p.url || "数据源里没有这一期的链接")}">未收录原片链接 · ${PLAT[k].label}</span>`;
    }
    return `<a href="${esc(p.url)}" target="_blank" rel="noopener">${kind === "video" ? "看原片" : "平台主页"} · ${PLAT[k].label}</a>`;
  }).join("");

  const transcript = v.transcript
    ? `<h4>口播逐字稿（${fmtInt(v.transcript.chars)} 字）</h4>
       <div class="script">${v.transcript.paragraphs.map((p) => `<p>${highlight(p, state.q)}</p>`).join("")}</div>`
    : `<h4>口播逐字稿</h4><p class="empty">这一期没有收录逐字稿。</p>`;

  // 「几个平台」要说清是「有记录的」还是「有数据的」，这两件事在这份数据里不一样。
  const liveN = dataKeys(v).length;
  const platMeta = liveN === keys.length
    ? `${keys.length} 个平台`
    : liveN
    ? `${liveN} 个平台有数据（另有 ${keys.length - liveN} 个只有待补录的记录）`
    : `${keys.length} 个平台记录，都待补录，还没有数据`;

  $("drawerBody").innerHTML = `
    <h3>${esc(v.topic)}</h3>
    <div class="d-meta">${v.date} · ${fmtDuration(v.duration)} · ${platMeta}</div>
    ${keys.length ? `
      <h4>分平台明细</h4>
      <table class="mini">
        <thead><tr><th>平台</th><th>播放</th><th>点赞</th><th>收藏</th><th>分享</th><th>评论</th><th>收藏率<br><span class="th-metric">收藏 ÷ 播放</span></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>
      <h4>原片</h4>
      <div class="src-links">${links}</div>`
    : `<p class="empty">这一期在数据源里没有任何平台数据，大概率是待补录的占位记录。</p>`}
    ${transcript}`;

  $("drawer").hidden = false;
  $("drawerMask").hidden = false;
  $("drawer").scrollTop = 0;
}

function closeDrawer() {
  $("drawer").hidden = true;
  $("drawerMask").hidden = true;
}
