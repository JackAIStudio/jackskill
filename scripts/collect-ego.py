#!/usr/bin/env python3
"""
用 Ego Lite（ego-browser）从本机已登录浏览器采集抖音 / 小红书 / 微信视频号 / X 的后台页面文本与数据 JSON。

设计原则：
  - 只读平台自己的页面，复用本机 Ego Lite 登录态，不读取也不写入任何 Cookie / 凭证；
  - 产出纯 JSON 或纯文本落到输出目录（默认 /tmp/jackskill-ego），再交给
    scripts/refresh-stats.py 与 scripts/refresh-followers.py 解析入库；
  - 某个平台未登录（常见的是微信视频号或 X 过期）时，不停掉其他平台：先采完已登录的平台，
    最后停在未登录页面调用 task.handOff() 交给人扫码/登录，并打印续跑命令（--space <id>）；
  - 全部采完后单独调用一次 task.finish({ keep: [] }) 关闭临时空间，不留多余标签页。

用法：
    # 默认滚动采集四个登录态平台（作品指标第 1 页/首屏 + 粉丝数）
    python3 scripts/collect-ego.py

    # 只采指定平台
    python3 scripts/collect-ego.py --platforms douyin xiaohongshu x

    # 只采作品指标或只采粉丝数
    python3 scripts/collect-ego.py --target stats
    python3 scripts/collect-ego.py --target followers

    # 全量模式（抖音循环翻完全部页、小红书滚到底、视频号翻完所有页、X 媒体页滚到底）
    python3 scripts/collect-ego.py --mode full

    # 用户在 Ego Lite 扫完登录后，接着刚才那个空间补采
    python3 scripts/collect-ego.py --space 28 --platforms wechat_channels
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

ALL_PLATFORMS = ["douyin", "xiaohongshu", "wechat_channels", "x"]
REPO_ROOT = Path(__file__).resolve().parent.parent

# 注入到 x.com 新文档的只读 XHR 旁路脚本：独立成 raw string 并经 json.dumps 传入，
# 避免 Python f-string + JS 模板字符串双重反转义破坏正则里的 \/。
X_HOOK_JS = r"""
(() => {
  if (!/(^|\.)x\.com$/i.test(location.hostname)) return;
  window.__jackXGql = [];
  const origOpen = XMLHttpRequest.prototype.open;
  const origSend = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__jackXUrl = String(url || "");
    return origOpen.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function() {
    this.addEventListener("load", function() {
      const u = this.__jackXUrl || "";
      const idx = u.indexOf("/i/api/graphql/");
      if (idx < 0) return;
      const tail = u.slice(idx + "/i/api/graphql/".length).split("?")[0];
      const parts = tail.split("/");
      const op = parts[1] || "";
      if (
        op === "UserByScreenName" ||
        op === "UserVideoTimeline" ||
        op === "UserMedia" ||
        op === "UserTweets"
      ) {
        window.__jackXGql.push({ op, text: this.responseText || "" });
      }
    });
    return origSend.apply(this, arguments);
  };
})();
""".strip()


def build_collect_js(cfg: dict) -> str:
    """生成交给 `ego-browser nodejs` 执行的 ESM 采集脚本。"""
    cfg_json = json.dumps(cfg, ensure_ascii=False)
    x_hook_json = json.dumps(X_HOOK_JS, ensure_ascii=False)
    return f"""
const fs = await import("node:fs/promises");
const path = await import("node:path");

const CFG = {cfg_json};
await fs.mkdir(CFG.outDir, {{ recursive: true }});

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// 递归提取页面可见文本（兼容普通 DOM 与 open shadowRoot，不依赖页面特定类名）
const EXTRACT_DEEP_TEXT_FN = () => {{
  const lines = [];
  const skipTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "PATH"]);
  const walk = (root) => {{
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {{
      const t = (root.nodeValue || "").replace(/\\s+/g, " ").trim();
      if (t) lines.push(t);
      return;
    }}
    if (root.nodeType !== Node.ELEMENT_NODE && root.nodeType !== Node.DOCUMENT_FRAGMENT_NODE) {{
      return;
    }}
    if (root.nodeType === Node.ELEMENT_NODE) {{
      if (skipTags.has(root.tagName)) return;
      const style = window.getComputedStyle ? window.getComputedStyle(root) : null;
      if (style && (style.display === "none" || style.visibility === "hidden")) return;
      if (root.shadowRoot) {{
        walk(root.shadowRoot);
      }}
    }}
    for (const child of root.childNodes) {{
      walk(child);
    }}
  }};
  walk(document.body);
  return lines.join("\\n");
}};

// 向下滚动页面或内部最大的可滚动主容器（适配 SPA 局部滚动布局）
const SCROLL_MAIN_DOWN_FN = (delta) => {{
  let target = document.scrollingElement || document.documentElement;
  let bestArea = 0;
  for (const el of document.querySelectorAll("div, main, section")) {{
    const st = window.getComputedStyle(el);
    if (!/(auto|scroll)/.test(st.overflowY)) continue;
    if (el.scrollHeight <= el.clientHeight + 40) continue;
    const rect = el.getBoundingClientRect();
    const area = rect.width * rect.height;
    if (rect.width > 300 && area > bestArea) {{
      bestArea = area;
      target = el;
    }}
  }}
  const before = target.scrollTop;
  target.scrollTop = before + delta;
  window.scrollBy(0, delta);
  return {{ before, after: target.scrollTop, scrollHeight: target.scrollHeight }};
}};

// 打开或接管 TaskSpace
const entry =
  CFG.spaceId === null
    ? undefined
    : (await listTaskSpaces()).find((s) => s.id === CFG.spaceId);
const task = !entry
  ? await taskSpace("jackskill collect")
  : entry.ownership === "user"
    ? await claimTaskSpace(CFG.spaceId)
    : entry.ownership === "agentDelegatedToUser"
      ? await takeOverTaskSpace(CFG.spaceId)
      : await taskSpace(CFG.spaceId);

const existingPages = await task.pages();
const page = existingPages[0] ?? (await task.adopt((await task.tabs())[0].page));

const result = {{
  taskSpaceId: task.spaceId,
  mode: CFG.mode,
  target: CFG.target,
  outDir: CFG.outDir,
  platforms: {{}},
  needsLogin: [],
  handedOff: false,
}};

const wantStats = CFG.target === "all" || CFG.target === "stats";
const wantFollowers = CFG.target === "all" || CFG.target === "followers";

// ---------------------------------------------------------------------------
// 抖音：work_list 接口拿精确作品指标 + 点侧栏「数据中心」拿总粉丝量
// ---------------------------------------------------------------------------
if (CFG.platforms.includes("douyin")) {{
  const t0 = Date.now();
  const info = {{ status: "ok", statsFiles: [], followersFile: null }};
  try {{
    await page.goto("https://creator.douyin.com/creator-micro/home", {{
      waitUntil: "domcontentloaded",
      timeout: 25000,
    }});
    await page
      .waitForFunction(
        () => {{
          const t = document.body?.innerText || "";
          return t.includes("数据中心") || /login/i.test(location.href);
        }},
        undefined,
        {{ timeout: 15000 }}
      )
      .catch(() => {{}});
    const curUrl = await page.url();

    if (/login/i.test(curUrl)) {{
      info.status = "needs_login";
      info.loginUrl = curUrl;
      result.needsLogin.push({{ platform: "douyin", url: curUrl }});
    }} else {{
      if (wantStats) {{
        let cursor = 0;
        let pageIdx = 0;
        let total = null;
        let totalItems = 0;
        const maxPages = CFG.mode === "full" ? 30 : 1;
        while (pageIdx < maxPages) {{
          const apiUrl =
            `https://creator.douyin.com/janus/douyin/creator/pc/work_list` +
            `?status=0&count=100&max_cursor=${{cursor}}&scene=star_atlas&device_platform=android`;
          const resp = await page.fetch(apiUrl, {{ timeout: 20000 }});
          if (!resp.ok || !resp.body) {{
            throw new Error(`work_list HTTP ${{resp.status}}`);
          }}
          const parsed = JSON.parse(resp.body);
          if (!Array.isArray(parsed.aweme_list)) {{
            info.status = "needs_login";
            info.loginUrl = "https://creator.douyin.com/creator-micro/home";
            result.needsLogin.push({{ platform: "douyin", url: info.loginUrl }});
            break;
          }}
          pageIdx += 1;
          const outPath = path.join(CFG.outDir, `dy-p${{pageIdx}}.json`);
          await fs.writeFile(outPath, resp.body, "utf8");
          info.statsFiles.push(outPath);
          totalItems += parsed.aweme_list.length;
          if (typeof parsed.total === "number") total = parsed.total;
          if (!parsed.has_more || !parsed.max_cursor || parsed.max_cursor === cursor) {{
            break;
          }}
          cursor = parsed.max_cursor;
          if (CFG.mode === "full") await sleep(400);
        }}
        info.workCount = totalItems;
        info.total = total;
      }}

      if (wantFollowers && info.status === "ok") {{
        // 必须从首页点侧栏「数据中心」，不能直接敲 URL（直接敲会显示「数据暂未产出」）。
        // 首页右侧卡片也包含「数据中心」，所以精准点左侧菜单里的 span:text-is("数据中心")。
        await page.waitForSelector('span:text-is("数据中心") >> nth=0', {{
          state: "visible",
          timeout: 15000,
        }});
        await page.click('span:text-is("数据中心") >> nth=0', {{
          label: "open douyin data center",
        }});
        await page.waitForFunction(
          () => {{
            const t = document.body?.innerText || "";
            return /总粉丝量\\s*[\\r\\n]+\\s*\\d/.test(t);
          }},
          undefined,
          {{ timeout: 15000 }}
        );
        const dyText = await page.evaluate(() => document.body?.innerText || "");
        const outPath = path.join(CFG.outDir, "dy-followers.txt");
        await fs.writeFile(outPath, dyText, "utf8");
        info.followersFile = outPath;
      }}
    }}
  }} catch (err) {{
    info.status = "error";
    info.error = String(err?.message || err);
  }}
  info.elapsedMs = Date.now() - t0;
  result.platforms.douyin = info;
}}

// ---------------------------------------------------------------------------
// 小红书：首页读粉丝数 + 笔记管理页读近期/全量作品
// ---------------------------------------------------------------------------
if (CFG.platforms.includes("xiaohongshu")) {{
  const t0 = Date.now();
  const info = {{ status: "ok", statsFiles: [], followersFile: null }};
  try {{
    if (wantFollowers) {{
      await page.goto("https://creator.xiaohongshu.com/new/home", {{
        waitUntil: "domcontentloaded",
        timeout: 25000,
      }});
      // 必须等账号 ID（同行内至少 3 位字母/数字）渲染出来，避免在接口未返回前读到骨架屏占位 0
      await page
        .waitForFunction(
          () => {{
            const t = document.body?.innerText || "";
            return /小红书账号[:：][ \\t]*[0-9A-Za-z_]{{3,}}/.test(t) || /login/i.test(location.href);
          }},
          undefined,
          {{ timeout: 15000 }}
        )
        .catch(() => {{}});
      const curUrl = await page.url();
      if (/login/i.test(curUrl)) {{
        info.status = "needs_login";
        info.loginUrl = curUrl;
        result.needsLogin.push({{ platform: "xiaohongshu", url: curUrl }});
      }} else {{
        const homeText = await page.evaluate(() => document.body?.innerText || "");
        const outPath = path.join(CFG.outDir, "xhs-home.txt");
        await fs.writeFile(outPath, homeText, "utf8");
        info.followersFile = outPath;
      }}
    }}

    if (wantStats && info.status === "ok") {{
      await page.goto("https://creator.xiaohongshu.com/new/note-manager", {{
        waitUntil: "domcontentloaded",
        timeout: 25000,
      }});
      await page
        .waitForFunction(
          () => {{
            const t = document.body?.innerText || "";
            return /\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}}/.test(t) || /login/i.test(location.href);
          }},
          undefined,
          {{ timeout: 15000 }}
        )
        .catch(() => {{}});
      const curUrl = await page.url();
      if (/login/i.test(curUrl)) {{
        info.status = "needs_login";
        info.loginUrl = curUrl;
        result.needsLogin.push({{ platform: "xiaohongshu", url: curUrl }});
      }} else {{
        // 小红书首屏一般渲染 10 条左右；滚动模式轻滚 2 次覆盖近 14 天，全量模式滚到底
        const maxScrolls = CFG.mode === "full" ? 80 : 2;
        let lastDates = 0;
        let stagnant = 0;
        for (let s = 0; s < maxScrolls; s++) {{
          const count = await page.evaluate(() => {{
            const t = document.body?.innerText || "";
            return (t.match(/\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}}/g) || []).length;
          }});
          if (CFG.mode === "full") {{
            const reachedEnd = await page.evaluate(() =>
              (document.body?.innerText || "").includes("没有更多")
            );
            if (reachedEnd) break;
            if (count === lastDates) {{
              stagnant += 1;
              if (stagnant >= 3) break;
            }} else {{
              stagnant = 0;
              lastDates = count;
            }}
          }}
          await page.evaluate(SCROLL_MAIN_DOWN_FN, 1800);
          await sleep(1000);
        }}
        const notesText = await page.evaluate(() => document.body?.innerText || "");
        const outPath = path.join(CFG.outDir, "xhs-notes.txt");
        await fs.writeFile(outPath, notesText, "utf8");
        info.statsFiles.push(outPath);
        info.dateAnchors = (notesText.match(/\\d{{4}}-\\d{{2}}-\\d{{2}} \\d{{2}}:\\d{{2}}/g) || []).length;
      }}
    }}
  }} catch (err) {{
    info.status = "error";
    info.error = String(err?.message || err);
  }}
  info.elapsedMs = Date.now() - t0;
  result.platforms.xiaohongshu = info;
}}

// ---------------------------------------------------------------------------
// 微信视频号：首页读关注者 + 内容列表页（先滚动触发渲染，支持 shadowRoot）
// ---------------------------------------------------------------------------
if (CFG.platforms.includes("wechat_channels")) {{
  const t0 = Date.now();
  const info = {{ status: "ok", statsFiles: [], followersFile: null }};
  try {{
    await page.goto("https://channels.weixin.qq.com/platform", {{
      waitUntil: "domcontentloaded",
      timeout: 25000,
    }});
    await page
      .waitForFunction(
        () => {{
          const t = document.body?.innerText || "";
          return (
            t.includes("关注者") ||
            t.includes("登录视频号助手") ||
            /login/i.test(location.href)
          );
        }},
        undefined,
        {{ timeout: 12000 }}
      )
      .catch(() => {{}});
    await sleep(800);
    const curUrl = await page.url();
    const homeDeepText = await page.evaluate(EXTRACT_DEEP_TEXT_FN);
    const looksLoggedOut =
      /login/i.test(curUrl) ||
      homeDeepText.includes("登录视频号助手") ||
      (!homeDeepText.includes("关注者") && !homeDeepText.includes("发表视频") && !homeDeepText.includes("内容管理"));

    if (looksLoggedOut) {{
      info.status = "needs_login";
      info.loginUrl = curUrl;
      result.needsLogin.push({{ platform: "wechat_channels", url: curUrl }});
    }} else {{
      if (wantFollowers) {{
        let content = homeDeepText;
        if (!content.includes("关注者")) {{
          content = await page.snapshot({{ scope: "full_page" }});
        }}
        const outPath = path.join(CFG.outDir, "wx-home.txt");
        await fs.writeFile(outPath, content, "utf8");
        info.followersFile = outPath;
      }}

      if (wantStats) {{
        await page.goto("https://channels.weixin.qq.com/platform/post/list", {{
          waitUntil: "domcontentloaded",
          timeout: 25000,
        }});
        await sleep(1500);
        // 视频号列表必须先滚一下才会渲染出数据
        await page.evaluate(SCROLL_MAIN_DOWN_FN, 600);
        await page.mouse.wheel(0, 600, {{ label: "scroll wechat post list" }});
        await page
          .waitForFunction(
            () => {{
              const walk = (root) => {{
                let txt = "";
                if (!root) return txt;
                if (root.nodeType === Node.TEXT_NODE) return root.nodeValue || "";
                if (root.shadowRoot) txt += walk(root.shadowRoot);
                for (const c of root.childNodes || []) txt += " " + walk(c);
                return txt;
              }};
              return /\\d{{4}}年\\d{{2}}月\\d{{2}}日 \\d{{2}}:\\d{{2}}/.test(walk(document.body));
            }},
            undefined,
            {{ timeout: 12000 }}
          )
          .catch(() => {{}});

        const maxPages = CFG.mode === "full" ? 40 : 1;
        for (let p = 1; p <= maxPages; p++) {{
          let listContent = await page.evaluate(EXTRACT_DEEP_TEXT_FN);
          if (!/\\d{{4}}年\\d{{2}}月\\d{{2}}日 \\d{{2}}:\\d{{2}}/.test(listContent)) {{
            listContent = await page.snapshot({{ scope: "full_page" }});
          }}
          const outPath = path.join(CFG.outDir, `wx-p${{p}}.txt`);
          await fs.writeFile(outPath, listContent, "utf8");
          info.statsFiles.push(outPath);

          if (p >= maxPages) break;

          // 全量翻页：递归穿透 shadowRoot 点击可用的「下一页」
          const clickedNext = await page.evaluate(() => {{
            const findNext = (root) => {{
              if (!root) return null;
              const els = root.querySelectorAll ? root.querySelectorAll("button, a, span, div") : [];
              for (const el of els) {{
                if (el.shadowRoot) {{
                  const hit = findNext(el.shadowRoot);
                  if (hit) return hit;
                }}
                if (el.childElementCount === 0 && (el.textContent || "").trim() === "下一页") {{
                  const btn = el.closest("button, a") || el;
                  const disabled =
                    btn.disabled ||
                    btn.getAttribute("disabled") !== null ||
                    btn.getAttribute("aria-disabled") === "true" ||
                    /disabled/i.test(btn.className || "");
                  if (!disabled) return btn;
                }}
              }}
              return null;
            }};
            const nextBtn = findNext(document);
            if (!nextBtn) return false;
            nextBtn.click();
            return true;
          }});
          if (!clickedNext) break;
          await sleep(1800);
          await page.evaluate(SCROLL_MAIN_DOWN_FN, 300);
          await sleep(600);
        }}
      }}
    }}
  }} catch (err) {{
    info.status = "error";
    info.error = String(err?.message || err);
  }}
  info.elapsedMs = Date.now() - t0;
  result.platforms.wechat_channels = info;
}}

// ---------------------------------------------------------------------------
// X：打开个人媒体页，旁路捕获 UserByScreenName（精确粉丝数）与 UserVideoTimeline（视频指标）
// ---------------------------------------------------------------------------
if (CFG.platforms.includes("x")) {{
  const t0 = Date.now();
  const info = {{ status: "ok", statsFiles: [], followersFile: null }};
  try {{
    // 在跳转到 x.com 之前挂只读 XHR 旁路，只记录公开的 GraphQL 响应体，不接触凭证或请求头
    await page.cdp("Page.addScriptToEvaluateOnNewDocument", {{
      source: {x_hook_json},
    }});

    // 第一步：确认登录态并自动探测当前登录账号的 handle（若命令行未显式传 --x-handle）
    let handle = (CFG.xHandle || "").replace(/^@/, "").trim();
    if (!handle) {{
      await page.goto("https://x.com/home", {{
        waitUntil: "domcontentloaded",
        timeout: 25000,
      }});
      await page
        .waitForFunction(
          () => {{
            const a = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
            const u = location.href;
            const t = document.body?.innerText || "";
            return (
              Boolean(a?.getAttribute("href")) ||
              /\\/(?:i\\/flow\\/)?login/i.test(u) ||
              t.includes("登录 X") ||
              t.includes("Sign in to X")
            );
          }},
          undefined,
          {{ timeout: 18000 }}
        )
        .catch(() => {{}});
      const homeCheck = await page.evaluate(() => {{
        const a = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
        const href = a?.getAttribute("href") || "";
        const t = document.body?.innerText || "";
        return {{
          url: location.href,
          handle: href.replace(/^\\//, "").split("/")[0] || "",
          looksLoggedOut:
            /\\/(?:i\\/flow\\/)?login/i.test(location.href) ||
            t.includes("登录 X") ||
            t.includes("Sign in to X"),
        }};
      }});
      if (homeCheck.looksLoggedOut || !homeCheck.handle) {{
        info.status = "needs_login";
        info.loginUrl = "https://x.com/i/flow/login";
        result.needsLogin.push({{ platform: "x", url: info.loginUrl }});
      }} else {{
        handle = homeCheck.handle;
      }}
    }}

    if (info.status === "ok" && handle) {{
      info.handle = handle;
      const targetUrl = wantStats
        ? `https://x.com/${{handle}}/media`
        : `https://x.com/${{handle}}`;
      await page.goto(targetUrl, {{
        waitUntil: "domcontentloaded",
        timeout: 30000,
      }});
      await page
        .waitForFunction(
          (needStats) => {{
            const gql = window.__jackXGql || [];
            const hasUser = gql.some((x) => x.op === "UserByScreenName");
            const hasVideos = gql.some((x) => x.op === "UserVideoTimeline" || x.op === "UserMedia");
            const hasDomFollowers = Boolean(
              document.querySelector('a[href$="/verified_followers"], a[href$="/followers"]')
            );
            const loggedOut = /\\/(?:i\\/flow\\/)?login/i.test(location.href);
            if (loggedOut) return true;
            if (needStats) return hasVideos && (hasUser || hasDomFollowers);
            return hasUser || hasDomFollowers;
          }},
          wantStats,
          {{ timeout: 20000 }}
        )
        .catch(() => {{}});

      const curUrl = await page.url();
      const hasProfileAnchor = await page.evaluate(() =>
        Boolean(document.querySelector('a[data-testid="AppTabBar_Profile_Link"]'))
      );
      if (/\\/(?:i\\/flow\\/)?login/i.test(curUrl) || !hasProfileAnchor) {{
        info.status = "needs_login";
        info.loginUrl = "https://x.com/i/flow/login";
        result.needsLogin.push({{ platform: "x", url: info.loginUrl }});
      }} else {{
        // 统计模式下向下滚动触发更多 UserVideoTimeline 分页
        if (wantStats) {{
          const maxScrolls = CFG.mode === "full" ? 40 : 2;
          let lastCount = await page.evaluate(() =>
            (window.__jackXGql || []).filter(
              (x) => x.op === "UserVideoTimeline" || x.op === "UserMedia"
            ).length
          );
          let stagnant = 0;
          for (let s = 0; s < maxScrolls; s++) {{
            await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
            await sleep(2000);
            const curCount = await page.evaluate(() =>
              (window.__jackXGql || []).filter(
                (x) => x.op === "UserVideoTimeline" || x.op === "UserMedia"
              ).length
            );
            if (CFG.mode === "full") {{
              if (curCount === lastCount) {{
                stagnant += 1;
                if (stagnant >= 3) break;
              }} else {{
                stagnant = 0;
                lastCount = curCount;
              }}
            }}
          }}
        }}

        // 在页面内直接提纯结构化数据（不含任何无关账号或敏感字段）
        const extracted = await page.evaluate((expectedHandle) => {{
          const gql = window.__jackXGql || [];
          let followers = null;
          let following = null;
          let followerSource = null;
          const handleLower = expectedHandle.toLowerCase();

          // 1. 精确粉丝数：优先从 UserByScreenName 提取
          for (const entry of gql) {{
            if (entry.op !== "UserByScreenName") continue;
            try {{
              const j = JSON.parse(entry.text);
              const u = j?.data?.user?.result;
              if (!u) continue;
              const sn = (u.core?.screen_name || u.legacy?.screen_name || "").toLowerCase();
              if (sn && sn !== handleLower) continue;
              if (typeof u.relationship_counts?.followers === "number") {{
                followers = u.relationship_counts.followers;
                following = typeof u.relationship_counts?.following === "number" ? u.relationship_counts.following : null;
                followerSource = "UserByScreenName.relationship_counts";
                break;
              }}
              if (typeof u.legacy?.followers_count === "number") {{
                followers = u.legacy.followers_count;
                following = typeof u.legacy?.friends_count === "number" ? u.legacy.friends_count : null;
                followerSource = "UserByScreenName.legacy";
                break;
              }}
            }} catch {{}}
          }}

          const domFollowersEl = document.querySelector(
            'a[href$="/verified_followers"], a[href$="/followers"]'
          );
          const domText = (domFollowersEl?.innerText || "").trim();

          // 2. 本账号全部视频推文精确指标：从 UserVideoTimeline / UserMedia 提取
          const seen = new Set();
          const items = [];
          const walk = (o) => {{
            if (!o || typeof o !== "object") return;
            if (o.__typename === "Tweet" && o.rest_id && o.legacy && !seen.has(o.rest_id)) {{
              const userRes = o.core?.user_results?.result;
              const sn = userRes?.core?.screen_name || userRes?.legacy?.screen_name || "";
              if (sn.toLowerCase() === handleLower) {{
                const leg = o.legacy;
                const mediaList = leg.extended_entities?.media || leg.entities?.media || [];
                const vid = mediaList.find((m) => m.type === "video");
                if (vid) {{
                  seen.add(o.rest_id);
                  const rawText = leg.full_text || "";
                  const cleanText = rawText.replace(/\\s*https:\\/\\/t\\.co\\/[A-Za-z0-9]+\\s*$/g, "").trim();
                  const viewsRaw = o.views?.count;
                  const viewsNum =
                    viewsRaw !== undefined && viewsRaw !== null && /^\\d+$/.test(String(viewsRaw))
                      ? Number(viewsRaw)
                      : 0;
                  items.push({{
                    tweet_id: String(o.rest_id),
                    url: `https://x.com/${{sn}}/status/${{o.rest_id}}`,
                    created_at: leg.created_at || "",
                    title: (vid.additional_media_info?.title || "").trim(),
                    text: cleanText,
                    media_key: vid.media_key || "",
                    duration_ms: vid.video_info?.duration_millis ?? null,
                    views: viewsNum,
                    likes: Number(leg.favorite_count) || 0,
                    bookmarks: Number(leg.bookmark_count) || 0,
                    retweets: Number(leg.retweet_count) || 0,
                    quotes: Number(leg.quote_count) || 0,
                    replies: Number(leg.reply_count) || 0,
                  }});
                }}
              }}
            }}
            if (Array.isArray(o)) {{
              for (const x of o) walk(x);
            }} else {{
              for (const k of Object.keys(o)) walk(o[k]);
            }}
          }};

          for (const entry of gql) {{
            if (entry.op !== "UserVideoTimeline" && entry.op !== "UserMedia" && entry.op !== "UserTweets") {{
              continue;
            }}
            try {{
              walk(JSON.parse(entry.text));
            }} catch {{}}
          }}

          return {{
            followers,
            following,
            followerSource,
            domText,
            items,
          }};
        }}, handle);

        if (wantFollowers) {{
          const outPath = path.join(CFG.outDir, "x-followers.json");
          const payload = {{
            platform: "x",
            handle,
            collectedAt: new Date().toISOString(),
            followers: extracted.followers,
            following: extracted.following,
            source: extracted.followerSource || (extracted.domText ? "dom" : null),
            domText: extracted.domText,
          }};
          await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\\n", "utf8");
          info.followersFile = outPath;
        }}

        if (wantStats) {{
          const outPath = path.join(CFG.outDir, "x-videos.json");
          const payload = {{
            platform: "x",
            handle,
            collectedAt: new Date().toISOString(),
            count: extracted.items.length,
            items: extracted.items,
          }};
          await fs.writeFile(outPath, JSON.stringify(payload, null, 2) + "\\n", "utf8");
          info.statsFiles.push(outPath);
          info.workCount = extracted.items.length;
        }}
      }}
    }}
  }} catch (err) {{
    info.status = "error";
    info.error = String(err?.message || err);
  }}
  info.elapsedMs = Date.now() - t0;
  result.platforms.x = info;
}}

// 若有平台需要登录且允许交接：停在第一个需要登录的页面，把控制权交给人
if (result.needsLogin.length > 0 && CFG.keepOnLogin) {{
  const first = result.needsLogin[0];
  const curUrl = await page.url();
  if (first.url && curUrl !== first.url) {{
    await page.goto(first.url, {{ waitUntil: "domcontentloaded", timeout: 20000 }}).catch(() => {{}});
  }}
  await task.handOff();
  result.handedOff = true;
}}

console.log("__COLLECT_RESULT__" + JSON.stringify(result));
"""


def run_ego_js(script: str, timeout: int = 180) -> tuple[int, str, str]:
    proc = subprocess.run(
        ["ego-browser", "nodejs"],
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def finish_space(space_id: int) -> None:
    js = f"""
const task = await taskSpace({space_id});
await task.finish({{ keep: [] }});
"""
    code, _, err = run_ego_js(js, timeout=30)
    if code != 0 and err.strip():
        print(f"  ! 关闭 Ego Lite 空间 {space_id} 时提示：{err.strip()}", file=sys.stderr)


def parse_result(stdout: str) -> dict | None:
    marker = "__COLLECT_RESULT__"
    for line in reversed(stdout.splitlines()):
        idx = line.find(marker)
        if idx >= 0:
            try:
                return json.loads(line[idx + len(marker):])
            except json.JSONDecodeError:
                return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="用 Ego Lite 采集抖音 / 小红书 / 视频号 / X 平台数据到临时文件")
    ap.add_argument(
        "--platforms",
        nargs="+",
        choices=ALL_PLATFORMS,
        default=ALL_PLATFORMS,
        help="要采集的平台（默认全部四个：douyin xiaohongshu wechat_channels x）",
    )
    ap.add_argument(
        "--target",
        choices=["all", "stats", "followers"],
        default="all",
        help="采集内容：all（默认，作品+粉丝）/ stats / followers",
    )
    ap.add_argument(
        "--mode",
        choices=["rolling", "full"],
        default="rolling",
        help="rolling（默认，近期第 1 页/首屏）或 full（全量翻页）",
    )
    ap.add_argument(
        "--out-dir",
        default="/tmp/jackskill-ego",
        help="原始页面文本与 JSON 的输出目录（默认 /tmp/jackskill-ego）",
    )
    ap.add_argument(
        "--space",
        type=int,
        default=None,
        help="复用已有的 Ego Lite taskSpaceId（例如刚扫完码后续跑）",
    )
    ap.add_argument(
        "--x-handle",
        default="",
        help="可选：显式指定 X 用户名（不带 @）；省略时自动从已登录的 X 会话识别",
    )
    ap.add_argument(
        "--days",
        type=int,
        default=14,
        help="仅用于生成建议命令中的 --days 参数（rolling 模式下默认 14）",
    )
    ap.add_argument(
        "--no-finish",
        action="store_true",
        help="采集完不关闭 Ego Lite 临时空间",
    )
    ap.add_argument(
        "--json",
        action="store_true",
        help="以 JSON 格式输出结果摘要，便于脚本调用",
    )
    args = ap.parse_args()

    if not shutil.which("ego-browser"):
        print("找不到 ego-browser 命令，请先安装或启动 Ego Lite。", file=sys.stderr)
        return 2

    out_dir = str(Path(args.out_dir).expanduser().resolve())
    cfg = {
        "platforms": args.platforms,
        "target": args.target,
        "mode": args.mode,
        "outDir": out_dir,
        "spaceId": args.space,
        "xHandle": args.x_handle,
        "keepOnLogin": True,
    }

    code, stdout, stderr = run_ego_js(build_collect_js(cfg), timeout=300 if args.mode == "full" else 180)
    # ego-browser nodejs 的 console.log 可能输出在 stderr，两边一起检索结果标记
    data = parse_result(stdout + "\n" + stderr)
    if data is None:
        print(f"Ego Lite 采集脚本执行失败（exit={code}）：", file=sys.stderr)
        if stderr.strip():
            print(stderr.strip(), file=sys.stderr)
        if stdout.strip():
            print(stdout.strip(), file=sys.stderr)
        return 1

    space_id = data.get("taskSpaceId")
    needs_login = data.get("needsLogin") or []
    has_error = any(p.get("status") == "error" for p in (data.get("platforms") or {}).values())

    # 遵循 Ego Lite 规范：仅当全部正常且无需人工介入时，在独立调用中 finish 关闭空间
    if space_id is not None and not needs_login and not has_error and not args.no_finish:
        finish_space(int(space_id))
        data["finished"] = True
    else:
        data["finished"] = False

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if not has_error else 1

    print(f"Ego Lite 采集完成（mode={args.mode}, target={args.target}, out={out_dir}）")
    for plat in args.platforms:
        p = (data.get("platforms") or {}).get(plat) or {}
        st = p.get("status", "unknown")
        sec = (p.get("elapsedMs") or 0) / 1000
        if st == "ok":
            parts = []
            if p.get("statsFiles"):
                if p.get("total") is not None:
                    extra = f", total={p['total']}"
                elif p.get("workCount") is not None:
                    extra = f", {p['workCount']} 条"
                else:
                    extra = ""
                parts.append(f"作品 {len(p['statsFiles'])} 份{extra}")
            if p.get("followersFile"):
                parts.append("粉丝 1 份")
            print(f"  - {plat}: 成功（{', '.join(parts)}，{sec:.1f}s）")
        elif st == "needs_login":
            print(f"  - {plat}: 未登录 / 登录态已过期（{sec:.1f}s）")
        else:
            print(f"  - {plat}: 失败 — {p.get('error', '未知错误')}（{sec:.1f}s）")

    if needs_login:
        plat_names = " ".join(x["platform"] for x in needs_login)
        print(f"\n以下平台需要在 Ego Lite 中登录（空间已移交给你，taskSpaceId={space_id}）：{plat_names}")
        print("完成登录后运行以下命令续采：")
        print(f"  python3 scripts/collect-ego.py --space {space_id} --platforms {plat_names} --mode {args.mode} --target {args.target} --out-dir {out_dir}")

    # 打印可直接复制执行的入库命令
    days_flag = f" --days {args.days}" if args.mode == "rolling" else ""
    cmds: list[str] = []
    for plat in args.platforms:
        p = (data.get("platforms") or {}).get(plat) or {}
        if p.get("statsFiles"):
            files = " ".join(p["statsFiles"])
            cmds.append(f"python3 scripts/refresh-stats.py --platform {plat} --in {files}{days_flag}")
        if p.get("followersFile"):
            cmds.append(f"python3 scripts/refresh-followers.py --platform {plat} --in {p['followersFile']}")
    if cmds:
        print("\n接下来可运行（建议先加 --dry-run 核对）：")
        for c in cmds:
            print(f"  {c}")

    return 0 if not has_error else 1


if __name__ == "__main__":
    sys.exit(main())
