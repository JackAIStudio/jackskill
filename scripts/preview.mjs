#!/usr/bin/env node
/**
 * 本地预览数据站：按需构建，再起一个只绑本机的静态服务器，然后打开浏览器。
 *
 *   node scripts/preview.mjs              按需构建 + 起服务 + 开浏览器
 *   node scripts/preview.mjs --build      不管有没有改动，强制重建一次
 *   node scripts/preview.mjs --no-build   跳过构建，直接看 docs/ 里现有的产物
 *   node scripts/preview.mjs -p 9000      换端口（默认 8000，被占用就往后找）
 *   node scripts/preview.mjs --no-open    只起服务，不自动开浏览器
 *
 * 默认按需构建：真源（data/videos.jsonl、transcripts/md/、编号工具清单）没有比
 * 产物更新的改动就跳过。这样平时打开就能看，不会每次白构建一遍，也不会平白把
 * 产物里的构建时间戳刷新一遍——那种只为时间戳的 diff 没有意义。
 *
 * 为什么需要它：站点本身是纯静态的，但页面用 fetch 读同目录的 data/videos.json，
 * 而 file:// 下的 fetch 会被浏览器拦掉——所以双击 docs/index.html 只会看到一段报错，
 * 跟数据坏没坏无关。把同一批文件从 http://127.0.0.1 发出去，就没有这回事了。
 *
 * 只用 Node 内置模块：不装依赖、不连外部服务，Ctrl+C 就停。
 */
import http from "node:http";
import fsp from "node:fs/promises";
import path from "node:path";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = path.resolve(__dirname, "..");
const SITE_DIR = path.join(REPO_ROOT, "docs");
const BUILD_SCRIPT = path.join(__dirname, "build-site.mjs");
const SITE_ARTIFACT = path.join(SITE_DIR, "data/videos.json");
// build-site.mjs 的全部输入，用来判断产物过没过期；那边加输入这里也要加。
const SOURCE_FILES = [
  path.join(REPO_ROOT, "data/videos.jsonl"),
  // 粉丝数是另一份真源、另一份产物。忘了加这一行，改完粉丝数打开预览会看到旧页面，
  // 还会以为是写错了。
  path.join(REPO_ROOT, "data/followers.jsonl"),
  path.join(REPO_ROOT, "skills/jack/numbered-prompts/catalog.json"),
];
const TRANSCRIPT_DIR = path.join(REPO_ROOT, "transcripts/md");

const DEFAULT_PORT = 8000;
const MAX_PORT_TRIES = 20;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".jsonl": "application/x-ndjson; charset=utf-8",
  ".txt": "text/plain; charset=utf-8",
  ".md": "text/plain; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".gif": "image/gif",
  ".ico": "image/x-icon",
  ".woff2": "font/woff2",
};

function usage() {
  console.log(`用法：node scripts/preview.mjs [选项]

  -p, --port <端口>   起服务的端口，默认 ${DEFAULT_PORT}；被占用就自动往后找
      --build         强制重建一次，不看有没有改动
      --no-build      跳过构建，直接看 docs/ 里现有的产物
      --no-open       只起服务，不自动开浏览器
  -h, --help          显示这段说明

默认按需构建：真源比产物新才重建，否则直接用现有产物。`);
}

function parseArgs(argv) {
  const opts = { port: DEFAULT_PORT, build: "auto", open: true };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg === "--build") opts.build = "force";
    else if (arg === "--no-build") opts.build = "skip";
    else if (arg === "--no-open") opts.open = false;
    else if (arg === "-p" || arg === "--port") opts.port = Number(argv[++i]);
    else if (arg.startsWith("--port=")) opts.port = Number(arg.slice("--port=".length));
    else if (arg === "-h" || arg === "--help") {
      usage();
      process.exit(0);
    } else {
      console.error(`未知参数：${arg}\n`);
      usage();
      process.exit(1);
    }
  }
  if (!Number.isInteger(opts.port) || opts.port < 1 || opts.port > 65535) {
    console.error(`端口不合法：${opts.port}`);
    process.exit(1);
  }
  return opts;
}

const opts = parseArgs(process.argv.slice(2));

/* 产物比全部真源都新就不用重建：省几秒，也不会平白多出一份只为时间戳的 diff。
   只看 mtime，宁可多构建一次，不会漏掉改动。 */
async function staleReason() {
  const artifact = await fsp.stat(SITE_ARTIFACT).catch(() => null);
  if (!artifact) return "页面产物还不存在";

  const files = [...SOURCE_FILES];
  const entries = await fsp.readdir(TRANSCRIPT_DIR, { withFileTypes: true }).catch(() => []);
  for (const entry of entries) {
    if (entry.isFile()) files.push(path.join(TRANSCRIPT_DIR, entry.name));
  }

  let newest = 0;
  for (const file of files) {
    const stat = await fsp.stat(file).catch(() => null);
    if (stat && stat.mtimeMs > newest) newest = stat.mtimeMs;
  }
  return newest > artifact.mtimeMs ? "真源有比产物更新的改动" : null;
}

let buildReason = null;
if (opts.build === "force") buildReason = "按 --build 强制重建";
else if (opts.build === "auto") buildReason = await staleReason();

// 构建失败就不起服务：页面读的是构建产物，产物没更新，看到的就不是刚改完的数据。
if (buildReason) {
  console.log(`构建页面数据（${buildReason}）…\n`);
  const built = spawnSync(process.execPath, [BUILD_SCRIPT], { cwd: REPO_ROOT, stdio: "inherit" });
  if (built.status !== 0) {
    console.error("\n构建失败，站点没有更新。修好数据再跑一次；只想看现有产物可以加 --no-build。");
    process.exit(built.status ?? 1);
  }
  console.log("");
} else if (opts.build === "skip") {
  console.log("按 --no-build 跳过构建，直接用 docs/ 里现有的产物。\n");
} else {
  console.log("真源没有新改动，跳过构建（要强制重建加 --build）。\n");
}

const indexPath = path.join(SITE_DIR, "index.html");
try {
  await fsp.access(indexPath);
} catch {
  console.error(`找不到 ${path.relative(REPO_ROOT, indexPath)}。先跑一次 node scripts/build-site.mjs。`);
  process.exit(1);
}

function send(res, status, contentType, body) {
  res.writeHead(status, {
    "content-type": contentType,
    "content-length": Buffer.byteLength(body),
    "cache-control": "no-store",
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  try {
    const urlPath = decodeURIComponent(new URL(req.url, "http://127.0.0.1").pathname);
    // 目录穿越：拼出来之后必须还在 docs/ 里面，否则一律拒掉。
    let target = path.resolve(SITE_DIR, "." + urlPath);
    if (target !== SITE_DIR && !target.startsWith(SITE_DIR + path.sep)) {
      return send(res, 403, "text/plain; charset=utf-8", "403 路径越界");
    }
    const stat = await fsp.stat(target).catch(() => null);
    if (stat?.isDirectory()) target = path.join(target, "index.html");

    const body = await fsp.readFile(target).catch(() => null);
    if (!body) {
      return send(res, 404, "text/plain; charset=utf-8", `404 没有这个文件：${urlPath}`);
    }
    res.writeHead(200, {
      "content-type": MIME[path.extname(target).toLowerCase()] ?? "application/octet-stream",
      "content-length": body.length,
      "cache-control": "no-store",
    });
    res.end(req.method === "HEAD" ? undefined : body);
  } catch (err) {
    send(res, 500, "text/plain; charset=utf-8", `500 ${err.message}`);
  }
});

// 端口被占用就往后找一个，最多试 MAX_PORT_TRIES 个。
function listen(port, triesLeft) {
  return new Promise((resolve, reject) => {
    const onError = (err) => {
      server.removeListener("listening", onListening);
      if (err.code === "EADDRINUSE" && triesLeft > 0) {
        console.log(`端口 ${port} 被占用，换 ${port + 1} 试试…`);
        resolve(listen(port + 1, triesLeft - 1));
      } else {
        reject(err);
      }
    };
    const onListening = () => {
      server.removeListener("error", onError);
      resolve(port);
    };
    server.once("error", onError);
    server.once("listening", onListening);
    server.listen(port, "127.0.0.1");
  });
}

/* 默认浏览器打开一个地址；打不开也不影响服务本身，所以失败了只当没发生。 */
function openBrowser(url) {
  const [cmd, args] =
    process.platform === "darwin"
      ? ["open", [url]]
      : process.platform === "win32"
        ? ["cmd", ["/c", "start", "", url]]
        : ["xdg-open", [url]];
  try {
    const child = spawn(cmd, args, { stdio: "ignore", detached: true, windowsHide: true });
    child.on("error", () => {});
    child.unref();
  } catch {
    /* 忽略：下面已经把地址打出来了，手动点也一样。 */
  }
}

const port = await listen(opts.port, MAX_PORT_TRIES);
const url = `http://127.0.0.1:${port}/`;

console.log(`本地预览：${url}`);
console.log(`服务目录：${path.relative(REPO_ROOT, SITE_DIR)}/（只绑 127.0.0.1，同一局域网的别的设备访问不到）`);
console.log("改完文件刷新页面即可（响应带 no-store，不会缓存旧数据）；Ctrl+C 停止。");

if (opts.open) openBrowser(url);

process.on("SIGINT", () => {
  console.log("\n已停止。");
  server.close(() => process.exit(0));
  // 还有 keep-alive 连接挂着时 close 会等，给它一点时间就撤。
  setTimeout(() => process.exit(0), 300).unref();
});
