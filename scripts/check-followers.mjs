#!/usr/bin/env node
/**
 * 校验 data/followers.jsonl（四平台粉丝数唯一真源）。
 *
 *   node scripts/check-followers.mjs
 *
 * 粉丝数和作品指标是两份数据：作品一行一期、逐条累加；粉丝是账号级的，
 * 一天一条快照，只有当下的数、不能相加。所以单独一个文件、单独一道校验。
 *
 * 出错（exit 1）：结构坏了 —— 日期格式不对、平台名不认识、粉丝数不是非负整数、
 *                 同一天记了两条、日期不是倒序。
 * 警告（exit 0）：数据本身合法，但看着可疑 —— 四个平台漏了某个、两条快照间隔太久。
 *
 * build-site.mjs 会先调这里的 checkFollowers()，出错就不生成页面。
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const FOLLOWERS_FILE = path.join(REPO_ROOT, "data/followers.jsonl");

export const PLATFORMS = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];
// 快照隔太久就没法说「这是此刻的粉丝数」。两周没记一次，提醒一声。
const STALE_DAYS = 14;

export function checkFollowers({ quiet = false } = {}) {
  const errors = [];
  const warnings = [];
  const log = (...a) => { if (!quiet) console.log(...a); };

  if (!fs.existsSync(FOLLOWERS_FILE)) {
    errors.push(`找不到粉丝数真源：${path.relative(REPO_ROOT, FOLLOWERS_FILE)}`);
    return { errors, warnings, snapshots: [] };
  }

  const lines = fs
    .readFileSync(FOLLOWERS_FILE, "utf8")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
  const snapshots = [];

  lines.forEach((line, i) => {
    const at = `第 ${i + 1} 行`;
    let s;
    try {
      s = JSON.parse(line);
    } catch (err) {
      errors.push(`${at} 不是合法 JSON：${err.message}`);
      return;
    }
    snapshots.push(s);

    if (!/^\d{4}-\d{2}-\d{2}$/.test(s.date || "")) {
      errors.push(`${at} date 格式不对：${s.date}`);
    }
    if (!s.platforms || typeof s.platforms !== "object" || Array.isArray(s.platforms)) {
      errors.push(`${at} platforms 必须是对象`);
      return;
    }
    const keys = Object.keys(s.platforms);
    if (!keys.length) errors.push(`${at} platforms 是空的`);

    for (const [k, p] of Object.entries(s.platforms)) {
      if (!PLATFORMS.includes(k)) errors.push(`${at} 平台名不认识：${k}`);
      if (!p || typeof p !== "object" || Array.isArray(p)) {
        errors.push(`${at} ${k} 必须是对象`);
        continue;
      }
      if (!Number.isInteger(p.followers) || p.followers < 0) {
        errors.push(`${at} ${k}.followers 必须是非负整数：${p.followers}`);
      }
      // 一个平台一条快照只该有一个数。多写的键没人读，却会让人以为它在生效。
      for (const key of Object.keys(p)) {
        if (key !== "followers") errors.push(`${at} ${k} 有不认识的字段：${key}`);
      }
    }

    // 四个平台一次记齐。缺一个不是错——某个平台确实可能还没开通——
    // 但多半是漏抄了，提醒一声。
    const missing = PLATFORMS.filter((k) => !(k in s.platforms));
    if (missing.length && missing.length < PLATFORMS.length) {
      warnings.push(`${at}（${s.date}）缺 ${missing.join("、")} 的粉丝数`);
    }
  });

  // 同一天只能有一条。两条同一天的快照说明有人在补记，先别猜哪条对。
  const byDate = new Map();
  for (const s of snapshots) byDate.set(s.date, (byDate.get(s.date) || 0) + 1);
  for (const [d, n] of byDate) if (n > 1) errors.push(`同一天记了 ${n} 条粉丝快照：${d}`);

  // 文件按日期倒序，最新在最上面——和 videos.jsonl 一个习惯。
  // 顺序乱了不会算错数（页面会自己排），但会让人找不到最新那条。
  const dates = snapshots.map((s) => s.date).filter(Boolean);
  for (let i = 1; i < dates.length; i++) {
    if (dates[i] >= dates[i - 1]) {
      errors.push(`日期没有按倒序排列：第 ${i + 1} 行 ${dates[i]} 排在第 ${i} 行 ${dates[i - 1]} 之后`);
      break;
    }
  }

  const sorted = [...dates].sort();
  if (sorted.length >= 2) {
    const gap = (new Date(sorted[sorted.length - 1]) - new Date(sorted[sorted.length - 2])) / 86400000;
    if (gap > STALE_DAYS) {
      warnings.push(`最近两条快照相隔 ${Math.round(gap)} 天（${sorted[sorted.length - 2]} → ${sorted[sorted.length - 1]}），粉丝数已经偏旧`);
    }
  }

  log(`检查 ${snapshots.length} 条粉丝快照（${sorted[0] || "?"} ~ ${sorted[sorted.length - 1] || "?"}）`);
  if (errors.length) {
    log(`\n✗ ${errors.length} 个错误：`);
    for (const e of errors) log(`  - ${e}`);
  }
  if (warnings.length) {
    log(`\n! ${warnings.length} 条提醒：`);
    for (const w of warnings) log(`  - ${w}`);
  }
  if (!errors.length && !warnings.length) log("✓ 全部通过");

  return { errors, warnings, snapshots };
}

if (import.meta.url === pathToFileURL(process.argv[1] || "").href) {
  const { errors } = checkFollowers();
  process.exit(errors.length ? 1 : 0);
}
