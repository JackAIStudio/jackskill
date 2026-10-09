#!/usr/bin/env node
/**
 * 把本仓库的两套事实资产打包成静态页面可直接读取的 JSON。
 *
 *   输入：data/videos.jsonl        （跨平台自媒体数据，唯一真源）
 *         transcripts/md/*.md      （口播逐字稿，唯一真源）
 *         skills/jack/numbered-prompts/catalog.json （编号工具清单，唯一真源）
 *   输出：docs/data/videos.json    （GitHub Pages 站点数据，构建产物）
 *         docs/llms.txt            （给 AI 爬虫的机器可读索引，构建产物）
 *
 * 全程只读本地文件，不连任何外部服务。
 * 数据更新后重跑本脚本即可，页面不需要任何后端。
 *
 * llms.txt 由本脚本生成而不是手写：它的正文里带期数、逐字稿篇数、
 * 时间跨度这些数字，手写就一定会过期——索引文件说着旧数字，
 * 和页面说着旧数字一样糟。
 *
 * 构建前先跑一遍 check-data.mjs：数据有硬伤就不生成页面，
 * 免得把坏数据发到网上。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { checkData } from "./check-data.mjs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const DATA_FILE = path.join(REPO_ROOT, "data/videos.jsonl");
const OUT_FILE = path.join(REPO_ROOT, "docs/data/videos.json");
const LLMS_FILE = path.join(REPO_ROOT, "docs/llms.txt");
const CATALOG_FILE = path.join(REPO_ROOT, "skills/jack/numbered-prompts/catalog.json");

const SITE_URL = "https://jackaistudio.github.io/jackskill";
const RAW_URL = "https://raw.githubusercontent.com/JackAIStudio/jackskill/main";

const PLATFORM_ORDER = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];
const METRICS = ["views", "likes", "collects", "shares", "comments"];
// 平台中文名和 docs/assets/app.js 里的 PLAT.label 是同一套，改一处要改两处。
// 之所以不共用一份：那份定义在浏览器脚本里，Node 这边拿不到。
const PLATFORM_LABEL = {
  bilibili: "B 站",
  douyin: "抖音",
  xiaohongshu: "小红书",
  wechat_channels: "微信视频号",
};

const check = checkData({ quiet: true });
if (check.errors.length) {
  console.error(`数据校验没过（${check.errors.length} 个错误），已中止构建：`);
  for (const e of check.errors) console.error(`  - ${e}`);
  console.error(`\n先跑 node scripts/check-data.mjs 看全貌。`);
  process.exit(1);
}
// 提醒不拦构建，但必须打出来。以前这些是脚本静默处理掉的，
// 现在没人兜底了，构建的人得看见。
if (check.warnings.length) {
  console.warn(`数据校验有 ${check.warnings.length} 条提醒（不阻止构建）：`);
  for (const w of check.warnings) console.warn(`  - ${w}`);
  console.warn("");
}

/** 从逐字稿 Markdown 里取出「## 逐字稿」之后的正文，保留段落结构。 */
function extractTranscriptBody(markdown) {
  const marker = markdown.match(/^##\s*逐字稿\s*$/m);
  const body = marker ? markdown.slice(marker.index + marker[0].length) : markdown;
  return body
    .replace(/^\s*---\s*$/gm, "")
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean);
}

function readTranscript(relPath) {
  if (!relPath) return null;
  const abs = path.join(REPO_ROOT, relPath);
  if (!fs.existsSync(abs)) return null;
  const paragraphs = extractTranscriptBody(fs.readFileSync(abs, "utf8"));
  const text = paragraphs.join("");
  return { path: relPath, chars: text.length, paragraphs };
}

function readRecords() {
  if (!fs.existsSync(DATA_FILE)) {
    throw new Error(`找不到唯一真源：${DATA_FILE}`);
  }
  return fs
    .readFileSync(DATA_FILE, "utf8")
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, i) => {
      try {
        return JSON.parse(line);
      } catch (err) {
        throw new Error(`data/videos.jsonl 第 ${i + 1} 行不是合法 JSON：${err.message}`);
      }
    });
}

const records = readRecords();
const warnings = [];

const videos = records
  .map((rec) => {
    const platforms = {};
    for (const key of PLATFORM_ORDER) {
      const p = rec.platforms?.[key];
      if (!p) continue;
      const entry = { title: p.title || rec.topic, url: p.url || "" };
      for (const m of METRICS) entry[m] = Number(p[m]) || 0;
      // 五个指标全是 0 = 这一期在这个平台没采到数据（平台没给数据的记录）。
      // 这里显式标出来，页面才不会把它当成「真的 0 播放」算进中位数——
      // 早先没有这个标记，抖音的中位播放被 21 条空记录从 623 拉到 480。
      entry.empty = METRICS.every((m) => !entry[m]);
      platforms[key] = entry;
    }

    const summary = {};
    for (const m of METRICS) summary[m] = Number(rec.summary?.[m]) || 0;

    const transcript = readTranscript(rec.transcript);
    if (rec.transcript && !transcript) {
      warnings.push(`${rec.date} 声明的逐字稿不存在：${rec.transcript}`);
    }
    if (!Object.keys(platforms).length) {
      warnings.push(`${rec.date} ${rec.topic} 没有任何平台数据`);
    }

    return {
      id: rec.id,
      date: rec.date,
      topic: rec.topic,
      duration: Number(rec.duration) || 0,
      summary,
      platforms,
      transcript,
    };
  })
  .sort((a, b) => (a.date < b.date ? 1 : a.date > b.date ? -1 : 0));

const dates = videos.map((v) => v.date).filter(Boolean).sort();
const payload = {
  generatedAt: new Date().toISOString(),
  source: "data/videos.jsonl",
  transcriptSource: "transcripts/md/*.md",
  platformOrder: PLATFORM_ORDER,
  metrics: METRICS,
  count: videos.length,
  dateRange: [dates[0] ?? null, dates[dates.length - 1] ?? null],
  videos,
};

fs.mkdirSync(path.dirname(OUT_FILE), { recursive: true });
fs.writeFileSync(OUT_FILE, JSON.stringify(payload), "utf8");

const size = fs.statSync(OUT_FILE).size;
const withTranscript = videos.filter((v) => v.transcript).length;
const transcriptChars = videos.reduce((n, v) => n + (v.transcript?.chars || 0), 0);
const perPlatform = Object.fromEntries(
  PLATFORM_ORDER.map((k) => [k, videos.filter((v) => v.platforms[k]).length]),
);
const livePlatform = Object.fromEntries(
  PLATFORM_ORDER.map((k) => [k, videos.filter((v) => v.platforms[k] && !v.platforms[k].empty).length]),
);

/* ---------------- docs/llms.txt ---------------- */

/** 编号工具的标题与用途来自 catalog.json，索引里不另写一份。 */
function readCatalog() {
  const rel = path.relative(REPO_ROOT, CATALOG_FILE);
  if (!fs.existsSync(CATALOG_FILE)) {
    warnings.push(`找不到编号工具清单：${rel}`);
    return [];
  }
  try {
    return JSON.parse(fs.readFileSync(CATALOG_FILE, "utf8")).items || [];
  } catch (err) {
    warnings.push(`${rel} 不是合法 JSON：${err.message}`);
    return [];
  }
}

const catalog = readCatalog();
const [from, to] = payload.dateRange;
const platformNames = PLATFORM_ORDER.map((k) => PLATFORM_LABEL[k]).join("、");
const toolLines = catalog.length
  ? catalog.map((it) => `- ${it.id} — ${it.title}：${it.purpose}`).join("\n")
  : "- （编号清单未读到，见 skills/jack/numbered-prompts/catalog.json）";

const llms = `# JackSkill — 吴杰克 Jack 的开源自媒体上下文库

> 一个 Agent Skill。安装后在 Agent 中输入 /jack 调用。内含跨平台自媒体数据 ${payload.count} 条、视频口播逐字稿 ${withTranscript} 篇（约 ${Math.round(transcriptChars / 10000)} 万字），以及 ${catalog.length} 个自研工具的编号规范。

数据和逐字稿全部随仓库分发：读取不需要登录、不需要凭证、不连任何外部服务。
时间跨度 ${from} 至 ${to}，覆盖 ${platformNames}四个平台。

本文件由 \`scripts/build-site.mjs\` 从仓库真源生成，构建于 ${payload.generatedAt}。

## 安装与调用

- 安装命令：\`npx -y skills add JackAIStudio/jackskill -g --all\`
- 入口：在 Agent 中输入 \`/jack\`
- 清单：\`/jack list\`
- 执行工具规范：\`/jack <三位编号>\`

## 数据

- [作品数据（单文件全集）](${SITE_URL}/data/videos.json)：${payload.count} 条记录的 JSON。单条含 id、date、topic、duration、summary（四平台播放/点赞/收藏/分享/评论）、platforms（各平台标题与链接）、transcript（逐字稿正文，按段落）。其中 ${withTranscript} 条带逐字稿。
- [作品数据真源（JSONL）](${RAW_URL}/data/videos.jsonl)：每行一条，字段与上同。这是唯一真源，上面那份是它的构建产物。
- [逐字稿真源（Markdown）](${RAW_URL}/transcripts/README.md)：${withTranscript} 个文件，文件名格式 \`YYYY-MM-DD_标题.md\`，\`## 逐字稿\` 之后是口播正文。
- [数据文件说明](${RAW_URL}/data/README.md)：字段定义与口径。

注意：数据站页面 ${SITE_URL}/ 的表格由 JavaScript 渲染，直接抓页面拿不到数据行。要数据请取上面第一或第二个链接。

## 调用规范

- [SKILL.md](${RAW_URL}/skills/jack/SKILL.md)：skill 主文件，定义三部分内容、六项职责、触发条件与执行流程。
- [VOICE.md](${RAW_URL}/skills/jack/VOICE.md)：检索逐字稿回应时的语气与表达规范。
- [编号规范目录](${RAW_URL}/skills/jack/numbered-prompts/catalog.json)：各编号的标题、用途与 SHA-256。
- 编号正文路径：\`skills/jack/numbered-prompts/<编号>/PROMPT.md\`

## 编号工具

${toolLines}

## 可选

- [仓库主页](https://github.com/JackAIStudio/jackskill)
- [README](${RAW_URL}/README.md)
- [AGENTS.md](${RAW_URL}/AGENTS.md)：本仓库的维护规范
- 许可证：MIT
`;

fs.mkdirSync(path.dirname(LLMS_FILE), { recursive: true });
fs.writeFileSync(LLMS_FILE, llms, "utf8");

console.log(`已生成 ${path.relative(REPO_ROOT, OUT_FILE)}`);
console.log(`- 期数: ${payload.count}（${payload.dateRange[0]} ~ ${payload.dateRange[1]}）`);
console.log(`- 含逐字稿: ${withTranscript} 期`);
// 两个数都给：页面上的「收录期数」用的是后者，差出来的就是平台没给数据的记录。
console.log(`- 各平台覆盖: ${PLATFORM_ORDER.map((k) => `${k} ${perPlatform[k]}`).join(" · ")}`);
console.log(`- 各平台有数据: ${PLATFORM_ORDER.map((k) => `${k} ${livePlatform[k]}`).join(" · ")}`);
console.log(`- 文件大小: ${(size / 1024).toFixed(1)} KB`);
console.log(`已生成 ${path.relative(REPO_ROOT, LLMS_FILE)}（编号工具 ${catalog.length} 个）`);
if (warnings.length) {
  console.log(`\n提醒 ${warnings.length} 条：`);
  for (const w of warnings) console.log(`  - ${w}`);
}
