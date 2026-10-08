#!/usr/bin/env node
/**
 * 把本仓库的两套事实资产打包成静态页面可直接读取的 JSON。
 *
 *   输入：data/videos.jsonl        （跨平台自媒体数据，唯一真源）
 *         transcripts/md/*.md      （口播逐字稿，唯一真源）
 *   输出：docs/data/videos.json    （GitHub Pages 站点数据，构建产物）
 *
 * 全程只读本地文件，不联网、不查任何云端。
 * 数据更新后重跑本脚本即可，页面不需要任何后端。
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

const PLATFORM_ORDER = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];
const METRICS = ["views", "likes", "collects", "shares", "comments"];

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
      // 五个指标全是 0 = 这一期在这个平台没采到数据（待补录的占位记录）。
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
const perPlatform = Object.fromEntries(
  PLATFORM_ORDER.map((k) => [k, videos.filter((v) => v.platforms[k]).length]),
);
const livePlatform = Object.fromEntries(
  PLATFORM_ORDER.map((k) => [k, videos.filter((v) => v.platforms[k] && !v.platforms[k].empty).length]),
);

console.log(`已生成 ${path.relative(REPO_ROOT, OUT_FILE)}`);
console.log(`- 期数: ${payload.count}（${payload.dateRange[0]} ~ ${payload.dateRange[1]}）`);
console.log(`- 含逐字稿: ${withTranscript} 期`);
// 两个数都给：页面上的「收录期数」用的是后者，差出来的就是待补录的占位记录。
console.log(`- 各平台覆盖: ${PLATFORM_ORDER.map((k) => `${k} ${perPlatform[k]}`).join(" · ")}`);
console.log(`- 各平台有数据: ${PLATFORM_ORDER.map((k) => `${k} ${livePlatform[k]}`).join(" · ")}`);
console.log(`- 文件大小: ${(size / 1024).toFixed(1)} KB`);
if (warnings.length) {
  console.log(`\n提醒 ${warnings.length} 条：`);
  for (const w of warnings) console.log(`  - ${w}`);
}
