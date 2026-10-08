#!/usr/bin/env node
/**
 * 校验 data/videos.jsonl（跨平台自媒体数据唯一真源）。
 *
 * 以前这些不变量由 sync-videos.mjs 在生成时保证。数据改成纯本地维护之后，
 * 没有生成器兜底了，所以校验单独拆出来，随时可跑：
 *
 *   node scripts/check-data.mjs
 *
 * 出错（exit 1）：结构坏了，必须修 —— 比如 summary 和各平台对不上、
 *                 transcript 指向不存在的文件、id 重复。
 * 警告（exit 0）：数据本身合法，但看着可疑 —— 比如同一条视频出现两次、
 *                 某期一个平台的数据都没有。
 *
 * build-site.mjs 会先调这里的 checkData()，出错就不生成页面，
 * 避免把坏数据发到网上。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const DATA_FILE = path.join(REPO_ROOT, "data/videos.jsonl");

export const PLATFORMS = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];
const METRICS = ["views", "likes", "collects", "shares", "comments"];

const cleanForMatching = (s) =>
  (s || "").replace(/[｜|:：，。！？!?,.~～_\-/\s]/g, "").toLowerCase();

// 数据里允许出现的两种链接形态：某条作品的直链，和平台主页。
// 和 docs/assets/app.js 里的 VIDEO_URL / HOME_URL 是同一套判据，改一处要改两处——
// 那边决定页面标「看原片」还是「平台主页」，这边负责在数据攒下第三种形态之前报出来。
const VIDEO_URL = [
  /^https?:\/\/(www\.)?bilibili\.com\/video\/BV[0-9A-Za-z]+/i,
  /^https?:\/\/(www\.)?douyin\.com\/video\/\d+/i,
  /^https?:\/\/(www\.)?xiaohongshu\.com\/explore\/[0-9a-z]+/i,
];
const HOME_URL = [
  /^https?:\/\/(www\.)?xiaohongshu\.com\/?$/i,
  /^https?:\/\/channels\.weixin\.qq\.com\/?$/i,
];

/** 给汇总提醒用：一批链接里都有哪些 host。 */
const hostsIn = (xs) => [...new Set(xs.map((x) => {
  try { return new URL(x.url).hostname; } catch { return x.url; }
}))].join("、");

const MIN_TITLE_CHARS = 6;
const MERGE_WINDOW_DAYS = 30;

function isSameTitle(a, b) {
  const norm = (s) => cleanForMatching(s).replace(/\//g, "");
  const contained = (x, y) => {
    const [short, long] = x.length <= y.length ? [x, y] : [y, x];
    return short.length >= MIN_TITLE_CHARS && long.includes(short);
  };
  const c1 = norm(a), c2 = norm(b);
  if (!c1 || !c2) return false;
  if (c1 === c2 || contained(c1, c2)) return true;
  // 各平台会把同一期写成「钩子|副标题」，副标题各写各的，所以再比竖线之前那截
  const head = (s) => norm(String(s).split(/[|｜]/)[0]);
  const h1 = head(a), h2 = head(b);
  return h1.length >= MIN_TITLE_CHARS && h1 === h2;
}

export function checkData({ quiet = false } = {}) {
  const errors = [];
  const warnings = [];
  const log = (...a) => { if (!quiet) console.log(...a); };

  if (!fs.existsSync(DATA_FILE)) {
    errors.push(`找不到唯一真源：${path.relative(REPO_ROOT, DATA_FILE)}`);
    return { errors, warnings, count: 0 };
  }

  const lines = fs.readFileSync(DATA_FILE, "utf8").split("\n").map((l) => l.trim()).filter(Boolean);
  const records = [];
  // 这几类问题逐条收集，最后按平台汇总成一条提醒。逐条报出来有九十多条，
  // 会把真正要看的错误淹掉；汇总里带日期，照样能定位。
  const unusableLinks = [];
  const emptyPlats = [];
  const workLinks = new Map();

  lines.forEach((line, i) => {
    const at = `第 ${i + 1} 行`;
    let r;
    try {
      r = JSON.parse(line);
    } catch (err) {
      errors.push(`${at} 不是合法 JSON：${err.message}`);
      return;
    }
    records.push(r);

    if (!r.id) errors.push(`${at} 缺 id`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(r.date || "")) errors.push(`${at} date 格式不对：${r.date}`);
    if (!r.topic) errors.push(`${at} 缺 topic`);
    if (!Number.isInteger(r.duration) || r.duration < 0) errors.push(`${at} duration 必须是非负整数：${r.duration}`);

    // id 是推导出来的，不是随便起的：同一期的身份必须能由「日期 + 标题」复现
    const expectId = `${r.date}_${String(r.topic).replace(/\s+/g, "_")}`;
    if (r.id !== expectId) errors.push(`${at} id 与「日期_标题」不符，应为 ${expectId}`);

    const platforms = r.platforms || {};
    for (const [k, p] of Object.entries(platforms)) {
      if (!PLATFORMS.includes(k)) errors.push(`${at} 平台名不认识：${k}`);
      for (const m of METRICS) {
        if (!Number.isInteger(p[m]) || p[m] < 0) errors.push(`${at} ${k}.${m} 必须是非负整数：${p[m]}`);
      }
      if (!p.url) warnings.push(`${at} ${k} 没有链接`);

      // 链接要么指向某条作品，要么指向平台主页。两边都不是的（创作者后台、
      // 后台管理页……）观众点进去只有登录墙，而页面只能把它标成「未收录原片链接」。
      // 判据是白名单，和 docs/assets/app.js 里的 VIDEO_URL / HOME_URL 是同一套：
      // 那边决定页面写「看原片」还是「平台主页」，这边保证数据里不会悄悄攒下
      // 一批两边都不认的链接。改判据记得两处一起改。
      const u = (p.url || "").trim();
      if (u && !VIDEO_URL.some((re) => re.test(u)) && !HOME_URL.some((re) => re.test(u))) {
        unusableLinks.push({ date: r.date, k, url: u });
      }
      // 一条作品链接只该属于一期。两条记录指向同一个作品，多半是同一条视频
      // 记了两遍——按标题相似度查不出来（各平台标题本来就不一样），按链接能查到。
      if (u && VIDEO_URL.some((re) => re.test(u))) {
        if (!workLinks.has(u)) workLinks.set(u, []);
        workLinks.get(u).push(`${r.date}「${r.topic}」`);
      }

      // 五个指标全是 0 = 这一期在这个平台没采到数据（平台没给数据的记录）。
      // 页面已经不把它算进收录期数和任何中位数，但它确实还占着一行。
      if (METRICS.every((m) => !p[m])) emptyPlats.push({ date: r.date, k });
    }

    // summary 必须等于各平台之和——这是全站所有数字的口径
    for (const m of METRICS) {
      const sum = Object.values(platforms).reduce((a, p) => a + (p[m] || 0), 0);
      if ((r.summary?.[m] || 0) !== sum) {
        errors.push(`${at} summary.${m}=${r.summary?.[m]} 与各平台之和 ${sum} 对不上`);
      }
    }

    if (r.transcript) {
      const abs = path.join(REPO_ROOT, r.transcript);
      if (!fs.existsSync(abs)) {
        errors.push(`${at} transcript 指向不存在的文件：${r.transcript}`);
      } else {
        // 文件名日期就是这一期的身份，记录里的 date 必须和它一致，
        // 否则页面显示的日期和逐字稿文件对不上。
        const fd = path.basename(r.transcript).match(/^(\d{4}-\d{2}-\d{2})_/);
        if (!fd) {
          errors.push(`${at} 逐字稿文件名缺 YYYY-MM-DD_ 前缀：${r.transcript}`);
        } else if (fd[1] !== r.date) {
          errors.push(`${at} date=${r.date} 与逐字稿文件名日期 ${fd[1]} 不一致：${path.basename(r.transcript)}`);
        }

        // md 头部还写着一条独立的发布日期。两处对不上说明有一处没跟上，
        // 这正是批量整理逐字稿时最容易出的错。
        const head = fs.readFileSync(abs, "utf8").slice(0, 800);
        const h = head.match(/\*\*发布日期\*\*：\s*(\d{4}-\d{2}-\d{2})/);
        if (h && fd && h[1] !== fd[1]) {
          warnings.push(`${at} md 头部发布日期 ${h[1]} 与文件名日期 ${fd[1]} 不一致：${path.basename(r.transcript)}`);
        }
      }
    }
    if (!r.transcript && !Object.keys(platforms).length) {
      warnings.push(`${at} 既没有逐字稿也没有平台数据：${r.topic}`);
    }
  });

  // 按平台汇总这两类问题。带上前几个日期，够定位到具体是哪几期。
  const summarise = (list, describe) => {
    const byPlat = new Map();
    for (const x of list) {
      if (!byPlat.has(x.k)) byPlat.set(x.k, []);
      byPlat.get(x.k).push(x);
    }
    for (const [k, xs] of byPlat) {
      const dates = xs.map((x) => x.date).sort();
      const shown = dates.slice(0, 8).join("、") + (dates.length > 8 ? ` 等 ${dates.length} 期` : "");
      warnings.push(`${k} ${describe(xs)}：${shown}`);
    }
  };

  summarise(unusableLinks, (xs) =>
    `有 ${xs.length} 条链接既不是作品直链也不是平台主页（${hostsIn(xs)}），`
    + `观众点进去多半只有登录墙；页面已按「未收录原片链接」处理，建议换成作品直链或平台主页`);

  summarise(emptyPlats, (xs) =>
    `有 ${xs.length} 条记录五个指标全是 0。这些不是「还没补录」——`
    + `从抖音创作者后台逐条核过，这批作品的状态是「不适宜公开 / 减少作品推荐 / 限制自己可见 / 已删除」，`
    + `平台侧根本不提供数据，补不出来。页面已把它们排除出收录期数和各种中位数；`
    + `记录留着是因为「这一期发过、但被平台限流了」本身也是真实状态。删不删由人定`);

  // 同一个作品链接被两条记录引用。按标题相似度查不出这类重复——各平台标题
  // 本来就不一样（同一条视频在 B 站叫「A」、在小红书叫「B」是常态），
  // 但作品链接骗不了人：一条链接只属于一期。
  for (const [url, owners] of workLinks) {
    if (owners.length > 1) {
      warnings.push(`同一条作品链接被 ${owners.length} 条记录引用，多半是同一条视频记了两遍：`
        + `${owners.join(" 与 ")}（${url}）`);
    }
  }

  // id 唯一
  const idCount = new Map();
  for (const r of records) idCount.set(r.id, (idCount.get(r.id) || 0) + 1);
  for (const [id, n] of idCount) if (n > 1) errors.push(`id 重复 ${n} 次：${id}`);

  // 同一条视频被记了两次（以前 sync 会自动合并，现在只报给人看）
  const daysApart = (a, b) => Math.abs((new Date(a) - new Date(b)) / 86400000);
  const sorted = [...records].sort((a, b) => a.date.localeCompare(b.date));
  for (let i = 0; i < sorted.length; i++) {
    for (let j = i + 1; j < sorted.length; j++) {
      if (daysApart(sorted[i].date, sorted[j].date) > MERGE_WINDOW_DAYS) break;
      if (isSameTitle(sorted[i].topic, sorted[j].topic)) {
        warnings.push(`疑似同一条视频出现两次：${sorted[i].date} 与 ${sorted[j].date}「${sorted[i].topic}」`);
      }
    }
  }

  const dates = records.map((r) => r.date).filter(Boolean).sort();
  log(`检查 ${records.length} 期（${dates[0] || "?"} ~ ${dates[dates.length - 1] || "?"}）`);
  if (errors.length) {
    log(`\n✗ ${errors.length} 个错误：`);
    for (const e of errors) log(`  - ${e}`);
  }
  if (warnings.length) {
    log(`\n! ${warnings.length} 条提醒：`);
    for (const w of warnings) log(`  - ${w}`);
  }
  if (!errors.length && !warnings.length) log("✓ 全部通过");

  return { errors, warnings, count: records.length };
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const { errors } = checkData();
  process.exit(errors.length ? 1 : 0);
}
