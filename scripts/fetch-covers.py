#!/usr/bin/env python3
"""
抓取每期视频的多比例封面。

一期视频会同时发到 B 站 / 抖音 / 小红书 / 微信视频号，每个平台对封面的
要求不一样，所以同一期在后台其实是三张不同的图：

    横屏 4:3   （小红书、抖音横封、B 站首页推荐、视频号分享卡片）
    竖屏 3:4   （抖音竖封、视频号个人主页卡片）
    横屏 16:9  （B 站个人空间）

三张图的内容是同一个主题，但比例不同、构图也不同——不是裁出来的，
是分别上传的。这个脚本负责把三张都找回来，各比例挑「好拿且清楚」的
平台取，落到 covers/<日期>_<主题>/ 下面。

取图优先级（哪个平台方便、清楚就用哪个）：

    4:3   → 小红书（1080 宽，一次翻页拿一批）
    3:4   → 视频号（540x720）→ 抖音兜底（330x441，很糊）
    16:9  → B 站公开 API（1920x1080 起，免登录可并发）

用法：
    python3 scripts/fetch-covers.py --limit 20          # 最近 20 期
    python3 scripts/fetch-covers.py --date 2026-10-20   # 指定一期
    python3 scripts/fetch-covers.py --dry-run           # 只报告不下载

需要登录态的平台（小红书 / 视频号 / 抖音）走 --xhs-json / --wxch-json /
--dy-json 传入的导出文件；没有就跳过那个比例，不会编造。

抖音的 work_list 一条作品同时带 3:4 竖封和 4:3 横封，是唯一能一次拿齐
横竖两张的来源，所以它在最后兜底。视频号的两个槽位（个人主页卡片 3:4、
分享卡片 4:3）图片地址与登录态绑定，curl 直接拉会 400，得在浏览器里存。

所有图都压到长边 800px 再入库——Agent 读图本来就会缩到 1024 左右，
存更大只是撑大仓库。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data" / "videos.jsonl"
# 封面直接落在 docs/ 下面：站点是纯静态的，预览服务器只发 docs/ 这一个目录，
# 放别处页面就读不到。这也意味着封面只有一份，不额外占仓库体积。
COVERS_DIR = REPO_ROOT / "docs" / "covers"

# 三种比例的落盘名。目录里用 4x3 / 3x4 / 16x9，冒号不能进文件名。
RATIOS = ("4x3", "3x4", "16x9")

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


def normalize_title(s: str) -> str:
    """把平台标题洗成可以互相比较的形态。

    各平台标题长得不一样：抖音/视频号常带 #话题，B 站带全角括号，
    小红书偶尔改标点。只留中英文数字，其余全部丢掉再比。
    """
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"#[^\s#]+", "", s)          # 去掉 #话题
    s = re.sub(r"[\s\W_]+", "", s)          # 只留字母数字
    return s.lower()


def load_records() -> list[dict]:
    rows = []
    for line in DATA_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return rows


def bvid_of(rec: dict) -> str | None:
    url = (rec.get("platforms", {}).get("bilibili") or {}).get("url", "")
    m = re.search(r"/video/(BV[0-9A-Za-z]{10})", url)
    return m.group(1) if m else None


def fetch_bili_169(bvid: str) -> str | None:
    """B 站 16:9 封面。公开接口，不需要登录。"""
    try:
        out = subprocess.run(
            [
                "curl", "-s", "-m", "15",
                "-H", f"User-Agent: {UA}",
                "-H", "Referer: https://www.bilibili.com/",
                f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            ],
            capture_output=True, text=True, check=False,
        ).stdout
        data = json.loads(out)
        if data.get("code") != 0:
            return None
        return (data.get("data") or {}).get("pic")
    except Exception:
        return None


def download(url: str, dest: Path, referer: str) -> bool:
    """下载到 dest。返回是否成功。"""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    r = subprocess.run(
        [
            "curl", "-s", "-m", "30", "-o", str(tmp), "-w", "%{http_code}",
            "-H", f"User-Agent: {UA}",
            "-H", f"Referer: {referer}",
            url,
        ],
        capture_output=True, text=True, check=False,
    )
    if r.stdout.strip() != "200" or not tmp.exists() or tmp.stat().st_size < 1024:
        tmp.unlink(missing_ok=True)
        return False
    tmp.replace(dest)
    return True


def image_size(path: Path) -> tuple[int, int] | None:
    """读图片宽高。只依赖 macOS 自带 sips，不装第三方库。"""
    try:
        out = subprocess.run(
            ["sips", "-g", "pixelWidth", "-g", "pixelHeight", str(path)],
            capture_output=True, text=True, check=False,
        ).stdout
        w = re.search(r"pixelWidth:\s*(\d+)", out)
        h = re.search(r"pixelHeight:\s*(\d+)", out)
        if w and h:
            return int(w.group(1)), int(h.group(1))
    except Exception:
        pass
    return None


# 封面统一压到长边 800px。Agent 读图时本来就会把长边缩到 1024 左右，
# 存更大的尺寸对「让 Agent 看清封面」没有增益，只是把仓库撑大。
# 800 在手机上放大看也够清楚，所以 800 是 Agent 可用性与仓库体积的折中。
COVER_LONG_EDGE = 800
COVER_QUALITY = 78


def press(src: Path, dst: Path) -> tuple[int, int] | None:
    """把 src 压成「长边 800 + JPEG」写到 dst，返回落盘后的宽高。

    只缩不放：原图比 800 小就保留原尺寸，只重编码——从已经压小的图上
    再放大，画质不会回来。

    优先用 Pillow（同样画质下比 sips 小将近一半）；没装 Pillow 就退回
    macOS 自带的 sips，功能不减，只是文件大一些，不为了几张封面硬加依赖。
    """
    size = image_size(src)
    if not size:
        return None
    w, h = size
    dst.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image  # 可选依赖：缺了就走 sips
    except ImportError:
        Image = None

    if Image is not None:
        try:
            im = Image.open(src).convert("RGB")
            if max(w, h) > COVER_LONG_EDGE:
                scale = COVER_LONG_EDGE / max(w, h)
                im = im.resize(
                    (max(1, round(w * scale)), max(1, round(h * scale))),
                    Image.LANCZOS,
                )
            im.save(dst, "JPEG", quality=COVER_QUALITY, optimize=True, progressive=True)
            return image_size(dst)
        except Exception:
            pass  # 落到下面的 sips 分支

    args = ["sips", "-s", "format", "jpeg", "-s", "formatOptions", str(COVER_QUALITY)]
    if max(w, h) > COVER_LONG_EDGE:
        args += ["-Z", str(COVER_LONG_EDGE)]
    args += [str(src), "--out", str(dst)]
    r = subprocess.run(args, capture_output=True, text=True, check=False)
    if r.returncode != 0 or not dst.exists():
        return None
    return image_size(dst)


def ratio_of(w: int, h: int) -> str:
    """把宽高判成我们认识的三种比例之一。"""
    r = w / h
    if abs(r - 4 / 3) < 0.06:
        return "4x3"
    if abs(r - 3 / 4) < 0.06:
        return "3x4"
    if abs(r - 16 / 9) < 0.06:
        return "16x9"
    return f"other({w}x{h})"


def dirname_for(rec: dict) -> str:
    safe = re.sub(r"[/\\:*?\"<>|]", "_", rec["topic"]).strip()
    safe = safe[:80]
    return f"{rec['date']}_{safe}"


def load_platform_dump(path: str | None) -> dict[str, dict]:
    """读一份平台后台导出的封面清单。

    形如 {"notes": [{"title": "...", "cover": "https://..."}]}，
    标题会洗过再当 key，方便和主题对齐。
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"  ! 找不到 {path}，跳过", file=sys.stderr)
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    items = raw.get("notes") or raw.get("items") or []
    out = {}
    for it in items:
        title = it.get("title") or it.get("display_title") or ""
        cover = it.get("cover") or it.get("url") or ""
        if title and cover:
            out[normalize_title(title)] = it
    return out


def load_douyin_dump(path: str | None) -> dict[str, dict]:
    """读抖音 work_list 导出的封面清单。

    抖音一条作品同时带两个封面，导出的结构是：

        {"<标题>": {"4x3": {"url": "..."}, "3x4": {"url": "..."}}}

    标题同样洗过再当 key。地址带签名和有效期，过期就下不动，
    所以这份清单要现抓现用。
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"  ! 找不到 {path}，跳过", file=sys.stderr)
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    out = {}
    for title, covers in raw.items():
        if isinstance(covers, dict) and any(k in covers for k in ("4x3", "3x4")):
            out[normalize_title(title)] = covers
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取每期视频的多比例封面")
    ap.add_argument("--limit", type=int, default=20, help="抓最近多少期，默认 20")
    ap.add_argument("--date", help="只抓指定日期的一期")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不下载")
    ap.add_argument("--xhs-json", help="小红书封面清单 JSON（登录态导出）")
    ap.add_argument("--wxch-json", help="视频号封面清单 JSON（登录态导出）")
    ap.add_argument("--dy-json", help="抖音封面清单 JSON（创作者后台 work_list 导出）")
    args = ap.parse_args()

    records = load_records()
    if args.date:
        records = [r for r in records if r["date"] == args.date]
    else:
        records = records[: args.limit]

    if not records:
        print("没有匹配的期数。", file=sys.stderr)
        return 1

    xhs = load_platform_dump(args.xhs_json)
    wxch = load_platform_dump(args.wxch_json)
    dy_dump = load_douyin_dump(args.dy_json)

    print(f"准备抓取 {len(records)} 期封面 → {COVERS_DIR.relative_to(REPO_ROOT)}/")
    print(f"{'日期':<12}{'主题':<34}{'4x3':>6}{'3x4':>6}{'16x9':>6}")
    print("-" * 72)

    stat = {"full": 0, "partial": 0, "none": 0}
    manifest = []

    for rec in records:
        key = normalize_title(rec["topic"])
        target = COVERS_DIR / dirname_for(rec)
        got: dict[str, dict] = {}
        # 原图先落到暂存目录，压成 800px 再进 covers/。
        # 直接下到目标位置会把原图留在仓库里，也容易忘了压缩这一步。
        staging = target / ".raw"

        # --- 16:9：B 站公开 API ---
        bvid = bvid_of(rec)
        if bvid:
            url = fetch_bili_169(bvid)
            if url:
                if args.dry_run:
                    got["16x9"] = {"url": url, "size": None}
                else:
                    raw = staging / "16x9.jpg"
                    if download(url, raw, "https://www.bilibili.com/"):
                        size = press(raw, target / "16x9.jpg")
                        if size:
                            got["16x9"] = {"url": url, "size": size, "source": "bilibili"}
            time.sleep(0.25)

        # --- 横竖屏封面：小红书 ---
        #
        # 这里不按「来源」定比例，按图片的真实宽高定。
        # 同一套上传流程下，竖屏视频发到小红书，封面就是 3:4；横屏视频
        # 发的就是 4:3。早先脚本硬把小红书当 4:3 存，结果 8 期竖屏视频
        # 的封面被存成了 4x3.jpg，比例是错的。
        hit = xhs.get(key)
        if hit:
            url = hit.get("cover") or hit.get("url")
            raw = staging / "_xhs_raw"
            if args.dry_run:
                got["4x3"] = {"url": url, "size": None}
            elif download(url, raw, "https://creator.xiaohongshu.com/"):
                size = image_size(raw)
                if size:
                    kind = ratio_of(*size)
                    if kind in ("4x3", "3x4"):
                        pressed = press(raw, target / f"{kind}.jpg")
                        if pressed:
                            got[kind] = {"url": url, "size": pressed, "source": "xiaohongshu"}
                    else:
                        print(f"    ! 小红书封面比例不认识：{size}，已丢弃")

        # --- 3:4：视频号，抖音兜底 ---
        hit = wxch.get(key)
        if hit:
            url = hit.get("cover") or hit.get("url")
            if args.dry_run:
                got["3x4"] = {"url": url, "size": None}
            else:
                raw = staging / "3x4.jpg"
                if download(url, raw, "https://channels.weixin.qq.com/"):
                    size = press(raw, target / "3x4.jpg")
                    if size:
                        got["3x4"] = {"url": url, "size": size, "source": "wechat_channels"}

        # 暂存的原图不留在仓库里。
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

        # --- 抖音兜底 ---
        #
        # 抖音创作者后台的 work_list 里，一条作品同时带着两个封面：
        # Cover（3:4 竖封）和 horizontal_cover（4:3 横封）。这是唯一
        # 能一次拿齐「横竖两张」的来源，所以放在最后补缺。
        #
        # 抖音的图片地址带签名与有效期（x-expires），过期就 403，
        # 所以导出清单要及时用，别存着当长期地址。
        dy = dy_dump.get(key)
        if dy:
            for ratio, meta in dy.items():
                if ratio not in ("4x3", "3x4") or ratio in got:
                    continue
                url = meta.get("url")
                if not url:
                    continue
                if args.dry_run:
                    got[ratio] = {"url": url, "size": None}
                    continue
                raw = staging / f"dy_{ratio}.jpg"
                if download(url, raw, "https://creator.douyin.com/"):
                    size = press(raw, target / f"{ratio}.jpg")
                    if size:
                        got[ratio] = {"url": url, "size": size, "source": "douyin"}
                staging.mkdir(parents=True, exist_ok=True)
                if staging.exists():
                    shutil.rmtree(staging, ignore_errors=True)

        n = len(got)
        if n == 3:
            stat["full"] += 1
        elif n:
            stat["partial"] += 1
        else:
            stat["none"] += 1

        marks = "".join("  ✓   " if k in got else "  -   " for k in RATIOS)
        print(f"{rec['date']:<12}{rec['topic'][:32]:<34}{marks}")

        manifest.append({
            "id": rec["id"],
            "date": rec["date"],
            "topic": rec["topic"],
            # 相对 docs/ 写，站点直接拿它当 src 用；换到别的目录也不用改。
            "dir": str(target.relative_to(COVERS_DIR.parent)) if n else None,
            "covers": {
                k: {
                    "file": f"{k}.jpg",
                    "size": got[k].get("size"),
                    "ratio": k,
                    "source": got[k].get("source") or "unknown",
                }
                for k in RATIOS if k in got
            },
        })

    print("-" * 72)
    print(f"三张齐全 {stat['full']} 期 · 部分 {stat['partial']} 期 · 一张没拿到 {stat['none']} 期")

    if not args.dry_run:
        idx = COVERS_DIR / "index.json"
        idx.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if idx.exists():
            try:
                for it in json.loads(idx.read_text(encoding="utf-8")).get("items", []):
                    existing[it["id"]] = it
            except Exception:
                pass
        for it in manifest:
            existing[it["id"]] = it
        payload = {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": "covers/<日期>_<主题>/",
            "ratios": list(RATIOS),
            "count": len(existing),
            "items": sorted(existing.values(), key=lambda x: x["date"], reverse=True),
        }
        idx.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"清单已写入 {idx.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
