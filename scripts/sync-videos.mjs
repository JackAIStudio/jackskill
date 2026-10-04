#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "..");
const TRANSCRIPTS_DIR = path.join(REPO_ROOT, "transcripts/md");
const DATA_DIR = path.join(REPO_ROOT, "data");
const OUTPUT_JSONL = path.join(DATA_DIR, "videos.jsonl");

// 清理 data 目录下旧的临时和多余 json 文件
if (fs.existsSync(DATA_DIR)) {
  for (const f of fs.readdirSync(DATA_DIR)) {
    if (f.endsWith(".json") || f.endsWith(".jsonl")) {
      fs.unlinkSync(path.join(DATA_DIR, f));
    }
  }
} else {
  fs.mkdirSync(DATA_DIR, { recursive: true });
}

// 统一字符清洗函数，杜绝 Ambiguous Unicode Characters (如全角竖线、零宽字符、全角空格等)
function cleanUnicode(str) {
  if (!str) return "";
  return str
    .replace(/[\u200B-\u200D\uFEFF]/g, "") // 零宽字符
    .replace(/[\u00A0\u3000]/g, " ")       // 不换行空格与全角空格
    .replace(/[｜]/g, "|")                  // 全角竖线转为标准 ASCII 半角竖线
    .replace(/[“”]/g, '"')                  // 引号规范
    .replace(/[‘’]/g, "'")
    .replace(/\s+/g, " ")                   // 连续空格压缩为单个空格
    .trim();
}

// 1. 读取本地 transcripts
const transcriptFiles = fs.existsSync(TRANSCRIPTS_DIR)
  ? fs.readdirSync(TRANSCRIPTS_DIR).filter(f => f.endsWith(".md"))
  : [];

const transcripts = transcriptFiles.map(file => {
  const match = file.match(/^(\d{4}-\d{2}-\d{2})_(.+)\.md$/);
  if (!match) return null;
  return {
    file,
    relPath: `transcripts/md/${file}`,
    date: match[1],
    topic: cleanUnicode(match[2])
  };
}).filter(Boolean);

console.log(`[1/4] 本地逐字稿已加载: ${transcripts.length} 篇`);

// 2. 从云端 FollowJack Hub 拉取 own-account 的全部作品与最新快照
console.log(`[2/4] 正在从 FollowJack Hub 提取全量自有作品指标...`);
const sql = `
SELECT json_agg(t) FROM (
  SELECT 
    ci.id,
    ci.platform,
    ci.platform_item_id,
    ci.title,
    ci.content_url,
    substring(ci.published_at::text from 1 for 10) as pub_date,
    ci.published_at,
    ci.duration_text,
    ci.duration_seconds,
    coalesce(ms.views, 0) as views,
    coalesce(ms.likes, 0) as likes,
    coalesce(ms.collects, 0) as collects,
    coalesce(ms.shares, 0) as shares,
    coalesce(ms.comments, 0) as comments,
    ms.captured_at
  FROM content_items ci
  LEFT JOIN LATERAL (
    SELECT views, likes, collects, shares, comments, captured_at
    FROM metric_snapshots 
    WHERE content_item_id = ci.id 
    ORDER BY captured_at DESC LIMIT 1
  ) ms ON true
  WHERE ci.creator_id IN (SELECT id FROM creators WHERE platform_creator_id = 'own-account')
  ORDER BY coalesce(ci.published_at, ci.first_seen_at) DESC
) t;
`;

const res = spawnSync("ssh", ["aliyun-ecs-new", "docker exec -i content-radar-postgres-1 psql -U content_radar -d content_radar -t -A"], {
  input: sql,
  encoding: "utf8",
  maxBuffer: 50 * 1024 * 1024
});

if (res.error || !res.stdout) {
  console.error("SSH/SQL 提取失败:", res.error || res.stderr);
  process.exit(1);
}

const items = JSON.parse(res.stdout.trim());
console.log(`[2/4] 成功获取 ${items.length} 条多平台作品原始数据`);

// 3. 相似度与聚类
console.log(`[3/4] 正在执行母体归集与数据清洗...`);

function cleanForMatching(str) {
  if (!str) return "";
  return str
    .replace(/#\S+/g, "")
    .replace(/【.*?】/g, "")
    .replace(/\[.*?\]/g, "")
    .replace(/[｜|:：，。！？!?,.~～_\-\s]/g, "")
    .toLowerCase();
}

function similarity(s1, s2) {
  const c1 = cleanForMatching(s1);
  const c2 = cleanForMatching(s2);
  if (!c1 || !c2) return 0;
  if (c1 === c2) return 1.0;
  if (c1.includes(c2) || c2.includes(c1)) {
    return Math.min(c1.length, c2.length) / Math.max(c1.length, c2.length) + 0.3;
  }
  let match = 0;
  for (const ch of c1) {
    if (c2.includes(ch)) match++;
  }
  return match / Math.max(c1.length, c2.length);
}

const episodes = [];
const usedItemIds = new Set();

// 3.1 逐字稿锚定
for (const tr of transcripts) {
  const ep = {
    id: `${tr.date}_${tr.topic.replace(/\s+/g, "_")}`,
    topic: tr.topic,
    date: tr.date,
    duration_seconds: 0,
    transcript: tr.relPath,
    platforms: {}
  };

  const candidates = items.filter(it => {
    if (usedItemIds.has(it.id)) return false;
    if (!it.pub_date) return false;
    const diffDays = Math.abs((new Date(it.pub_date) - new Date(tr.date)) / (1000 * 3600 * 24));
    return diffDays <= 2;
  });

  for (const it of candidates) {
    const sim = similarity(it.title, tr.topic);
    if (sim >= 0.5) {
      if (!ep.platforms[it.platform] || ep.platforms[it.platform]._sim < sim) {
        ep.platforms[it.platform] = {
          _id: it.id,
          _sim: sim,
          title: cleanUnicode(it.title),
          url: it.content_url,
          views: it.views,
          likes: it.likes,
          collects: it.collects,
          shares: it.shares,
          comments: it.comments
        };
        if (it.duration_seconds && !ep.duration_seconds) {
          ep.duration_seconds = it.duration_seconds;
        }
      }
    }
  }

  for (const p of Object.keys(ep.platforms)) {
    usedItemIds.add(ep.platforms[p]._id);
    delete ep.platforms[p]._id;
    delete ep.platforms[p]._sim;
  }

  episodes.push(ep);
}

// 3.2 聚类未锚定作品
const remainingItems = items.filter(it => !usedItemIds.has(it.id));
const remDateGroups = new Map();
for (const it of remainingItems) {
  const d = it.pub_date || "unknown";
  if (!remDateGroups.has(d)) remDateGroups.set(d, []);
  remDateGroups.get(d).push(it);
}

for (const [date, group] of remDateGroups.entries()) {
  const subClusters = [];
  for (const it of group) {
    let matchedCluster = null;
    for (const c of subClusters) {
      if (similarity(it.title, c.representativeTitle) >= 0.55 && !c.platforms[it.platform]) {
        matchedCluster = c;
        break;
      }
    }
    if (matchedCluster) {
      matchedCluster.platforms[it.platform] = {
        title: cleanUnicode(it.title),
        url: it.content_url,
        views: it.views,
        likes: it.likes,
        collects: it.collects,
        shares: it.shares,
        comments: it.comments
      };
      if (it.duration_seconds && !matchedCluster.duration_seconds) {
        matchedCluster.duration_seconds = it.duration_seconds;
      }
    } else {
      subClusters.push({
        representativeTitle: it.title,
        duration_seconds: it.duration_seconds || 0,
        platforms: {
          [it.platform]: {
            title: cleanUnicode(it.title),
            url: it.content_url,
            views: it.views,
            likes: it.likes,
            collects: it.collects,
            shares: it.shares,
            comments: it.comments
          }
        }
      });
    }
  }

  for (const sc of subClusters) {
    const rawTopic = cleanUnicode(
      sc.representativeTitle
        .replace(/#\S+/g, "")
        .replace(/【.*?】/g, "")
        .replace(/[｜]/g, "|")
    );
    episodes.push({
      id: `${date}_${rawTopic.replace(/\s+/g, "_")}`,
      topic: rawTopic,
      date: date,
      duration_seconds: sc.duration_seconds,
      transcript: null,
      platforms: sc.platforms
    });
  }
}

// 排序规则：按 date 降序，同 date 按 topic 升序
episodes.sort((a, b) => {
  if (a.date !== b.date) return b.date.localeCompare(a.date);
  return a.topic.localeCompare(b.topic);
});

// 固定平台顺序
const PLATFORM_ORDER = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"];

// 生成标准的 JSON Lines 数据
console.log(`[4/4] 正在生成单一真源文件: ${OUTPUT_JSONL}...`);

const jsonlRows = episodes.map(ep => {
  const platforms = {};
  let totalViews = 0;
  let totalLikes = 0;
  let totalCollects = 0;
  let totalShares = 0;
  let totalComments = 0;

  for (const p of PLATFORM_ORDER) {
    if (ep.platforms[p]) {
      const pl = ep.platforms[p];
      totalViews += pl.views || 0;
      totalLikes += pl.likes || 0;
      totalCollects += pl.collects || 0;
      totalShares += pl.shares || 0;
      totalComments += pl.comments || 0;

      platforms[p] = {
        title: pl.title,
        url: pl.url,
        views: pl.views,
        likes: pl.likes,
        collects: pl.collects,
        shares: pl.shares,
        comments: pl.comments
      };
    }
  }

  const record = {
    id: cleanUnicode(ep.id),
    date: ep.date,
    topic: cleanUnicode(ep.topic),
    duration: ep.duration_seconds || 0,
    transcript: ep.transcript,
    summary: {
      views: totalViews,
      likes: totalLikes,
      collects: totalCollects,
      shares: totalShares,
      comments: totalComments
    },
    platforms
  };

  return JSON.stringify(record);
});

// 写入 videos.jsonl
fs.writeFileSync(OUTPUT_JSONL, jsonlRows.join("\n") + "\n", "utf8");

const stats = fs.statSync(OUTPUT_JSONL);
const lines = fs.readFileSync(OUTPUT_JSONL, "utf8").trim().split("\n").length;

console.log(`\n🎉 唯一真源落盘成功！`);
console.log(`- 目标文件: ${OUTPUT_JSONL}`);
console.log(`- 总视频数: ${lines} 期 (对应物理行数恰好 ${lines} 行)`);
console.log(`- 文件大小: ${(stats.size / 1024).toFixed(1)} KB`);
