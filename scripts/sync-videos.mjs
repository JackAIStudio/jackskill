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

let episodes = [];
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

// 3.3 全局去重
// 同一条视频会在库里留下多条记录，来源有三种：
//   a. 云端对同一条视频有多个 content_item（重复抓取），其中一条有完整快照、一条是残的；
//   b. 各平台分批入库，跨了好几天，第 3.2 步按精确日期分组，永远合不到一起；
//   c. 一条被逐字稿锚定（3.1）、另一条由日期聚类产生（3.2），两步之间撞车。
// 只修 3.2 的分组只解决 b，所以这里统一收一次，三种一起合掉。
const MERGE_WINDOW_DAYS = 30;   // 超出一个月的同名作品视为两条不同的视频
const MERGE_MIN_TITLE_CHARS = 6; // 太短的标题不做包含判断，避免「AI」并进「AI 工作台」

function daysApart(a, b) {
  return Math.abs((new Date(a) - new Date(b)) / 86400000);
}

// 判「同一条视频」用清洗后完全相同、或一个完整包含另一个。
// 不用相似度阈值：2025 年那批英文标题的小红书内容互相能撞到 0.90~0.92
// （「I am Chinese, like to teach you Chinese」对「Chinese Teaching : Learn To Say Hello」），
// 而真正该合并的「好用的DeepSeek Harness插件分享|AI工作台地基搭建」对
// 「DeepSeek Harness插件分享|AI工作台地基搭建」只有包含关系。阈值切不开这两类。
function isSameTitle(a, b) {
  // 比 cleanForMatching 多剥一个斜杠：同一个标题各平台会写成「codex_chatgpt」和「codex/chatgpt」。
  // 只在这里多剥一层，不动共享的 cleanForMatching，免得改变第 3.1 步既有的匹配行为。
  const norm = s => cleanForMatching(s).replace(/\//g, "");
  const isContained = (x, y) => {
    const [short, long] = x.length <= y.length ? [x, y] : [y, x];
    return short.length >= MERGE_MIN_TITLE_CHARS && long.includes(short);
  };

  const c1 = norm(a);
  const c2 = norm(b);
  if (!c1 || !c2) return false;
  if (c1 === c2 || isContained(c1, c2)) return true;

  // 各平台爱把同一期写成「钩子|副标题」，副标题各写各的：
  // 「图书馆也能口喷不打扰别人|我开发了一个支持超低声语音输入的识别工具」
  // 对「图书馆也能口喷不打扰别人|自制超低声语音输入工具」。全串比不出来，就比竖线之前那截。
  // 只认完全相等，不做包含：否则「把Agent接入达芬奇，根据文字和画面剪辑」会把
  // 「把 Agent 接入达芬奇|用一个skill实现自动剪辑」并进来，那是两期不同的视频。
  // 也要求够长：三期不同的 vlog 前截都只是「vlog」，一合就并成一条。
  const head = s => norm(String(s).split(/[|｜]/)[0]);
  const h1 = head(a);
  const h2 = head(b);
  return h1.length >= MERGE_MIN_TITLE_CHARS && h1 === h2;
}

function mergeEpisodes(list) {
  const byDate = [...list].sort((a, b) => a.date.localeCompare(b.date));
  const groups = [];

  for (const ep of byDate) {
    const host = groups.find(
      g => daysApart(g.date, ep.date) <= MERGE_WINDOW_DAYS
        && isSameTitle(g.topic, ep.topic)
    );
    if (!host) {
      groups.push({ ...ep, platforms: { ...ep.platforms }, members: [ep] });
      continue;
    }
    // 同一平台留播放量更高的那次快照——播放量只增不减，高的就是抓得更晚的
    for (const [plat, data] of Object.entries(ep.platforms)) {
      const cur = host.platforms[plat];
      if (!cur || (data.views || 0) > (cur.views || 0)) host.platforms[plat] = data;
    }
    host.members.push(ep);
  }

  return groups.map(g => {
    // 有逐字稿的那条说了算：文件名日期是人维护的，比云端首次抓到的日期更可信
    const withTranscript = g.members.find(m => m.transcript);
    const keeper = withTranscript || g;
    const { members, ...rest } = g;
    return {
      ...rest,
      topic: keeper.topic,
      date: keeper.date,
      duration_seconds: Math.max(...members.map(m => m.duration_seconds || 0)),
      transcript: withTranscript ? withTranscript.transcript : null,
      id: `${keeper.date}_${keeper.topic.replace(/\s+/g, "_")}`
    };
  });
}

const beforeDedup = episodes.length;
episodes = mergeEpisodes(episodes);
const mergedCount = beforeDedup - episodes.length;
if (mergedCount > 0) {
  console.log(`[3/4] 去重合并了 ${mergedCount} 条重复记录（同一视频被建了多期）`);
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

// 体检：一期视频匹配不到任何平台数据，几乎总是「逐字稿文件名日期 ≠ 真实发布日期」——
// 第 3.1 步的 ±2 天窗口会因此把所有候选挡掉，然后一路静默到底。
// 所以这里必须吵一声，否则错误只会以「页面上一排 0」的形式出现，没人知道是数据错了。
const empty = episodes.filter(ep => Object.keys(ep.platforms).length === 0);
if (empty.length) {
  console.warn(`\n⚠️  ${empty.length} 期没有匹配到任何平台数据：`);
  for (const ep of empty) console.warn(`   - ${ep.date}  ${ep.topic}`);
  console.warn(`   逐字稿文件名里的日期如果与真实发布日期相差超过 2 天，`);
  console.warn(`   云端记录会被匹配窗口直接挡掉（见本脚本第 3.1 步）。`);
  console.warn(`   先核对文件名与 md 头部里的「发布日期」再重跑。`);
}

// 顺带重建静态站点的数据。
// 页面数据必须跟唯一真源同一次生成，否则会出现「页面在说旧数据」——
// 但它是次要产物，失败了不能拖垮数据同步本身。
console.log(`\n重建站点数据…`);
const build = spawnSync(process.execPath, [path.join(__dirname, "build-site.mjs")], {
  stdio: "inherit",
});
if (build.status !== 0) {
  console.warn(`⚠️  站点数据重建失败（退出码 ${build.status}）。videos.jsonl 已正常落盘，`);
  console.warn(`   手动重跑 node scripts/build-site.mjs 即可。`);
}
