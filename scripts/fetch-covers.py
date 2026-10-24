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

**槽位是「你设计的那张」，不是「像素必须是这个比例」。** 4:3 / 3:4 /
16:9 是制作封面时的规格；上传之后平台会按自己的展示框做处理，B 站早年
那批就存成过 3:2（864x540）、16:10，甚至竖版视频的封面本来就是竖的。
所以判断标准是：

    - 槽位（slot）由来源决定：B 站 → 16:9 槽，抖音竖封 → 3:4 槽
    - 实测宽高如实记进索引（size / ratio），不篡改、不裁切、不重命名
    - 只做方向性校验：横屏槽收竖图、竖屏槽收横图才算错位，要标出来
    - 比例偏离不否决这张图——那就是平台当时展示的那张封面

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


def aweme_id_of(rec: dict) -> str | None:
    """抖音作品 id。这是跟一期视频一一对应的稳定键。

    标题不能用：各平台标题是分别填的，同一个视频在抖音常被改短、
    加后缀或换说法。用规范化标题当 key 时，只要标题改过一个字就整条
    匹配不上——实测 129 期抖音作品里有 36 期主题与抖音标题不一致，
    那批的封面就全漏了。作品 id 不受标题改写影响。
    """
    url = (rec.get("platforms", {}).get("douyin") or {}).get("url", "")
    m = re.search(r"/video/(\d{8,})", url)
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


# 槽位期望的方向。只查方向，不查比例——平台会按自己的展示框裁切，
# 3:2、16:10 都出现过，那是平台当时展示的那张图，不是抓错了。
SLOT_ORIENTATION = {"4x3": "landscape", "3x4": "portrait", "16x9": "landscape"}


def shape_of(w: int, h: int) -> dict:
    """量出这张图的真实形态，用来记账，不用来否决它。

    比例是制作封面时的规格，不是平台一定会照搬的像素尺寸。所以这里
    只回答三件事：横的还是竖的、最接近哪个规格、偏了多少。
    偏离不构成丢弃理由，方向反了才是真的错位。
    """
    r = w / h
    specs = {"4x3": 4 / 3, "3x4": 3 / 4, "16x9": 16 / 9}
    nearest = min(specs, key=lambda k: abs(r - specs[k]))
    if r > 1.02:
        orientation = "landscape"
    elif r < 0.98:
        orientation = "portrait"
    else:
        orientation = "square"
    return {
        "ratio": round(r, 4),
        "nearest": nearest,
        "deviation": round(abs(r - specs[nearest]) / specs[nearest], 4),
        "orientation": orientation,
    }


def check_slot(slot: str, size: tuple[int, int]) -> str | None:
    """槽位和图片方向对不上时返回一句提示，对得上返回 None。"""
    want = SLOT_ORIENTATION.get(slot)
    got = shape_of(*size)["orientation"]
    if want and got != want:
        return f"{slot} 槽收进了 {got} 图（{size[0]}x{size[1]}），方向和槽位不符"
    return None


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

    抖音一条作品同时带两个封面。清单支持两种结构：

        新（推荐）：{"<aweme_id>": {"title": "...", "covers": {...}}}
        旧：       {"<标题>": {"4x3": {...}, "3x4": {...}}}

    新结构用作品 id 当 key，标题改成同一个视频在别的平台被改写过也照样
    对得上。旧结构仍然认，但按标题匹配会漏，读到旧格式时提示一次。

    地址带签名和有效期（x-expires），过期就下不动，所以清单要现抓现用。
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        print(f"  ! 找不到 {path}，跳过", file=sys.stderr)
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    by_id: dict[str, dict] = {}
    by_title: dict[str, dict] = {}
    legacy = 0
    for key, val in raw.items():
        if not isinstance(val, dict):
            continue
        if "covers" in val:                      # 新结构
            covers = val.get("covers") or {}
            if any(k in covers for k in ("4x3", "3x4")):
                by_id[str(key)] = {"title": val.get("title") or "", "covers": covers}
        elif any(k in val for k in ("4x3", "3x4")):   # 旧结构
            legacy += 1
            by_title[normalize_title(key)] = val
    if legacy:
        print(
            f"  ! {p.name} 是旧格式（按标题当 key，{legacy} 条）。"
            "标题被改写过的那批会匹配不上，建议用新版的 parse-dy-dump.py 重导。",
            file=sys.stderr,
        )
    return {"by_id": by_id, "by_title": by_title}


def pick_douyin(dy_dump: dict, rec: dict) -> dict | None:
    """按作品 id 取抖音封面，取不到再退回标题匹配。"""
    if not dy_dump:
        return None
    aid = aweme_id_of(rec)
    if aid:
        hit = (dy_dump.get("by_id") or {}).get(aid)
        if hit:
            return hit.get("covers")
    return (dy_dump.get("by_title") or {}).get(normalize_title(rec["topic"]))


def reindex() -> int:
    """按磁盘上的实际图片重写索引里的记账字段。

    只动「这张图是什么」这类客观字段（size / slot / shape），
    不动 source——来源是抓取当时的事实，事后猜不出来。有些尺寸两个
    平台都会产出（540x721 抖音和小红书都有），凭尺寸反推来源就是编。

    历史遗留：早先索引里有个 `ratio` 字段，写的是槽位名，于是 800x500
    的图被记成 ratio=16x9，看起来像「16:9 的图实际是 3:2」，其实只是
    字段名用错了。这里把它换成 slot（槽位）+ shape（真实形态）。
    """
    idx_path = COVERS_DIR / "index.json"
    if not idx_path.exists():
        print("没有 index.json，先跑一次抓取。", file=sys.stderr)
        return 1
    payload = json.loads(idx_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []

    changed = 0
    dropped = 0
    fixed_dir = 0
    for it in items:
        # dir 丢了就按目录名规则补回来：covers/<id>。
        # id 就是「日期_主题」，和落盘目录名同源，能原样还原。
        if not it.get("dir") and it.get("id"):
            it["dir"] = f"covers/{it['id']}"
            fixed_dir += 1
        cov = it.get("covers") or {}
        for slot, meta in list(cov.items()):
            p = COVERS_DIR.parent / (it.get("dir") or "") / (meta.get("file") or f"{slot}.jpg")
            size = image_size(p) if p.exists() else None
            if not size:
                # 文件没了就别在索引里留个假条目
                cov.pop(slot, None)
                dropped += 1
                continue
            before = (meta.get("size"), meta.get("slot"), meta.get("shape"), meta.get("ratio"))
            meta.pop("ratio", None)
            meta["size"] = list(size)
            meta["slot"] = slot
            meta["shape"] = shape_of(*size)
            after = (meta.get("size"), meta.get("slot"), meta.get("shape"), None)
            if before != after:
                changed += 1
        it["covers"] = cov

    payload["generatedAt"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    payload["source"] = "covers/<日期>_<主题>/"
    payload["slots"] = list(RATIOS)
    payload.pop("ratios", None)
    payload["count"] = len(items)
    payload["items"] = sorted(items, key=lambda x: x["date"], reverse=True)
    idx_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"索引已重写：{len(items)} 期，改动 {changed} 张，补回 dir {fixed_dir} 条，清掉失效条目 {dropped} 张")
    return 0


def verify() -> int:
    """体检：逐张量真实宽高，核对索引和磁盘对不对得上。

    查四件事：
      1. 索引里写了、磁盘上没有（页面会挂破图）
      2. 磁盘上有、索引里没写（白占体积，页面看不见）
      3. 索引记的尺寸和实测尺寸不一致（记错了）
      4. 槽位方向和图片方向相反（这才是真的错位：横槽收了竖图）

    比例偏离槽位**不算问题**。槽位是你制作封面时的规格，平台会按自己的
    展示框裁切，B 站早年那批就是 3:2。只记录，不判错。
    """
    idx_path = COVERS_DIR / "index.json"
    if not idx_path.exists():
        print("没有 index.json，先跑一次抓取。", file=sys.stderr)
        return 1
    payload = json.loads(idx_path.read_text(encoding="utf-8"))
    items = payload.get("items") or []

    missing_file, unindexed, size_mismatch, flipped = [], [], [], []
    seen = set()
    shapes = {k: {} for k in RATIOS}
    sources = {}
    per_episode = {}

    for it in items:
        cov = it.get("covers") or {}
        per_episode[len(cov)] = per_episode.get(len(cov), 0) + 1
        for slot, meta in cov.items():
            p = COVERS_DIR.parent / (it.get("dir") or "") / (meta.get("file") or f"{slot}.jpg")
            seen.add(p.resolve())
            if not p.exists():
                missing_file.append((it["date"], slot, str(p)))
                continue
            size = image_size(p)
            if not size:
                missing_file.append((it["date"], slot, f"{p}（读不出宽高）"))
                continue
            shape = shape_of(*size)
            shapes.setdefault(slot, {})
            key = f"{size[0]}x{size[1]}"
            shapes[slot][key] = shapes[slot].get(key, 0) + 1
            sources[meta.get("source") or "unknown"] = sources.get(meta.get("source") or "unknown", 0) + 1
            rec_size = meta.get("size")
            if rec_size and list(rec_size) != list(size):
                size_mismatch.append((it["date"], slot, rec_size, size))
            want = SLOT_ORIENTATION.get(slot)
            if want and shape["orientation"] != want:
                flipped.append((it["date"], slot, size, meta.get("source")))

    for root, _dirs, files in os.walk(COVERS_DIR):
        for f in files:
            if f.endswith(".jpg"):
                p = Path(root) / f
                if p.resolve() not in seen:
                    unindexed.append(str(p.relative_to(COVERS_DIR.parent)))

    # per_episode 的 key 是「这期有几张」，value 是有多少期；张数要把 key 乘回去。
    total = sum(k * v for k, v in per_episode.items())
    print(f"索引 {len(items)} 期 · 封面 {total} 张 · 磁盘多出 {len(unindexed)} 张\n")
    print("每期张数分布：")
    for k in sorted(per_episode, reverse=True):
        print(f"   {k} 张：{per_episode[k]} 期")
    print("\n各槽位的真实尺寸分布（比例偏离不判错，只记账）：")
    for slot in RATIOS:
        dist = shapes.get(slot) or {}
        print(f"   {slot}：", end="")
        if not dist:
            print("（没有）")
            continue
        print(" · ".join(f"{k} ×{v}" for k, v in sorted(dist.items(), key=lambda x: -x[1])))
    print("\n来源分布：")
    for k, v in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"   {k}：{v} 张")

    problems = 0
    if missing_file:
        problems += len(missing_file)
        print(f"\n[错] 索引有、磁盘没有：{len(missing_file)} 张")
        for d, s, p in missing_file[:10]:
            print(f"   {d} {s} → {p}")
    if unindexed:
        problems += len(unindexed)
        print(f"\n[错] 磁盘有、索引没记：{len(unindexed)} 张")
        for p in unindexed[:10]:
            print(f"   {p}")
    if size_mismatch:
        problems += len(size_mismatch)
        print(f"\n[错] 索引记的尺寸和实测不符：{len(size_mismatch)} 张")
        for d, s, old, new in size_mismatch[:10]:
            print(f"   {d} {s}：记 {old} 实测 {list(new)}")
    if flipped:
        print(f"\n[提示] 槽位方向和图片方向不同：{len(flipped)} 张")
        print("   这不是抓错。平台按自己的展示框放封面，竖版视频在 B 站的封面")
        print("   本来就是竖的；槽位仍按当初的设计规格记，真实比例照实标出。")
        for d, s, size, src in flipped[:10]:
            print(f"   {d} {s}：{size[0]}x{size[1]}（来源 {src}）")

    if problems:
        print(f"\n共 {problems} 处要处理。")
        return 1
    print("\n全部对得上：索引与磁盘一致，尺寸记录属实，没有方向错位的槽位。")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="抓取每期视频的多比例封面")
    ap.add_argument("--limit", type=int, default=20, help="抓最近多少期，默认 20")
    ap.add_argument("--date", help="只抓指定日期的一期")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不下载")
    ap.add_argument("--verify", action="store_true", help="只体检：核对索引、磁盘和真实宽高")
    ap.add_argument("--reindex", action="store_true", help="按磁盘实际图片重写索引的记账字段")
    ap.add_argument("--only-missing", action="store_true", help="只补缺的槽位，已有的图不重下")
    ap.add_argument("--xhs-json", help="小红书封面清单 JSON（登录态导出）")
    ap.add_argument("--wxch-json", help="视频号封面清单 JSON（登录态导出）")
    ap.add_argument("--dy-json", help="抖音封面清单 JSON（创作者后台 work_list 导出）")
    args = ap.parse_args()

    if args.verify:
        return verify()
    if args.reindex:
        return reindex()

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

    # --only-missing：已经有图的槽位不再重下。
    # 存量那 434 张当初是别的脚本抓的，来源记不全；重下一遍既浪费请求，
    # 也可能把已有的好图换成平台现在返回的另一张。补缺就只补缺。
    existing_covers: dict[str, set] = {}
    idx_path = COVERS_DIR / "index.json"
    if args.only_missing and idx_path.exists():
        try:
            for it in json.loads(idx_path.read_text(encoding="utf-8")).get("items", []):
                existing_covers[it["id"]] = set((it.get("covers") or {}).keys())
        except Exception:
            pass

    print(f"准备抓取 {len(records)} 期封面 → {COVERS_DIR.relative_to(REPO_ROOT)}/")
    print(f"{'日期':<12}{'主题':<34}{'4x3':>6}{'3x4':>6}{'16x9':>6}")
    print("-" * 72)

    stat = {"full": 0, "partial": 0, "none": 0, "skipped": 0}
    manifest = []

    for rec in records:
        key = normalize_title(rec["topic"])
        target = COVERS_DIR / dirname_for(rec)
        got: dict[str, dict] = {}
        # 原图先落到暂存目录，压成 800px 再进 covers/。
        # 直接下到目标位置会把原图留在仓库里，也容易忘了压缩这一步。
        staging = target / ".raw"
        warnings: list[str] = []

        have = existing_covers.get(rec["id"], set()) if args.only_missing else set()

        def take(slot: str, url: str, raw: Path, referer: str, source: str) -> None:
            """下载 → 压到 800px → 记进 got。槽位是固定的，形态只记录。"""
            if slot in have:
                return
            if args.dry_run:
                got[slot] = {"url": url, "size": None, "source": source}
                return
            if not download(url, raw, referer):
                return
            size = press(raw, target / f"{slot}.jpg")
            if not size:
                return
            got[slot] = {"url": url, "size": size, "source": source}
            note = check_slot(slot, size)
            if note:
                warnings.append(note)

        # --- 16:9：B 站公开 API ---
        #
        # B 站这个位置就叫「16:9 封面」，但拿到的图不一定是 16:9：
        # 早年那批上传的是 864x540（3:2）、720x450，竖版视频的封面本身
        # 就是竖的。那是 B 站当时展示的那张封面，照收，把真实宽高记下来。
        bvid = bvid_of(rec)
        if bvid:
            url = fetch_bili_169(bvid)
            if url:
                take("16x9", url, staging / "16x9.jpg", "https://www.bilibili.com/", "bilibili")
            time.sleep(0.25)

        # --- 小红书：单张封面，比例跟着视频方向走 ---
        #
        # 竖屏视频发到小红书，封面就是 3:4；横屏发的就是 4:3。
        # 早先脚本硬把小红书当 4:3 存，结果 8 期竖屏视频的封面被存进
        # 了 4x3.jpg。现在按图片真实方向归槽，不按平台硬编码。
        hit = xhs.get(key)
        if hit:
            url = hit.get("cover") or hit.get("url")
            raw = staging / "_xhs_raw"
            if args.dry_run:
                got["4x3"] = {"url": url, "size": None, "source": "xiaohongshu"}
            elif download(url, raw, "https://creator.xiaohongshu.com/"):
                size = image_size(raw)
                if size:
                    slot = "3x4" if shape_of(*size)["orientation"] == "portrait" else "4x3"
                    pressed = press(raw, target / f"{slot}.jpg")
                    if pressed:
                        got[slot] = {"url": url, "size": pressed, "source": "xiaohongshu"}
                        note = check_slot(slot, pressed)
                        if note:
                            warnings.append(note)

        # --- 视频号：3:4 个人主页卡片 ---
        hit = wxch.get(key)
        if hit:
            url = hit.get("cover") or hit.get("url")
            take("3x4", url, staging / "3x4.jpg", "https://channels.weixin.qq.com/", "wechat_channels")

        # --- 抖音兜底 ---
        #
        # 抖音创作者后台的 work_list 里，一条作品同时带着两个封面：
        # Cover（3:4 竖封）和 horizontal_cover（4:3 横封）。这是唯一
        # 能一次拿齐「横竖两张」的来源，所以放在最后补缺。
        #
        # 按作品 id 查，不按标题：抖音标题经常被改短（仓库主题写了
        # 「…|deepseek harness上手体验」，抖音只写前半句），按标题匹配
        # 会整条漏掉。id 不受标题改写影响。
        dy = pick_douyin(dy_dump, rec)
        if dy:
            for ratio, meta in dy.items():
                if ratio not in ("4x3", "3x4") or ratio in got:
                    continue
                url = (meta or {}).get("url")
                if not url:
                    continue
                take(ratio, url, staging / f"dy_{ratio}.jpg", "https://creator.douyin.com/", "douyin")

        # 暂存的原图不留在仓库里。
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

        for note in warnings:
            print(f"    ! {note}")

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
                    # slot 是这张图占的槽位（也是文件名），shape 是它的真实形态。
                    # 两者分开记：平台会裁切，槽位不变，形态会变。
                    "slot": k,
                    "shape": shape_of(*got[k]["size"]) if got[k].get("size") else None,
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
        # 按封面增量合并，不整条覆盖。
        #
        # 整条替换有个坑：某次只带一个来源重跑（比如只跑 --date 抓 B 站），
        # 这一期之前抓到的 4:3 / 3:4 会被整条冲掉——图片还在磁盘上，索引里
        # 却没了，页面就只剩一张。索引只增不减：新抓到的覆盖旧的，没抓到的
        # 原样保留。
        for it in manifest:
            old = existing.get(it["id"]) or {}
            merged = dict(old)
            # dir 不能拿空值去覆盖。
            #
            # 只补缺时，如果这期原本一张都没抓到、这次也没补到，manifest 里
            # 的 dir 是 None；直接 merged.update() 会把旧条目的 dir 抹成空，
            # 索引里所有封面就都指向 docs/ 根目录下的裸文件名，页面全挂。
            # 只在这次真的有值时才覆盖。
            for k, v in it.items():
                if k == "covers":
                    continue
                if v in (None, ""):
                    continue
                merged[k] = v
            covers = dict(old.get("covers") or {})
            covers.update(it.get("covers") or {})
            merged["covers"] = covers
            if not merged.get("dir") and it.get("dir"):
                merged["dir"] = it["dir"]
            existing[it["id"]] = merged
        payload = {
            "generatedAt": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "source": "covers/<日期>_<主题>/",
            "slots": list(RATIOS),
            "count": len(existing),
            "items": sorted(existing.values(), key=lambda x: x["date"], reverse=True),
        }
        idx.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"清单已写入 {idx.relative_to(REPO_ROOT)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
