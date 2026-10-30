#!/usr/bin/env python3
"""
刷新 data/followers.jsonl 里四个平台的粉丝数。

粉丝数和作品指标是两套东西，别混：
  - 作品指标（data/videos.jsonl）一行一期，四平台各自一条，可以相加
  - 粉丝数（data/followers.jsonl）是账号级的，一天一条快照，**不能相加**
所以刷新脚本、校验脚本、页面呈现都是分开的一套。

四个平台的取数方式：

    bilibili         公开接口，免登录。先取任一条作品的 owner.mid，再查粉丝数
    douyin           创作者后台「数据中心」页里的「总粉丝量」
    xiaohongshu      创作者服务平台首页的「粉丝数」
    wechat_channels  视频号助手的「关注者」

**只有 B 站能自动跑。** 另外三个后台接口要登录态和签名，curl 打不通，只能在
已登录的浏览器里读。读回来的页面文本交给 --in，脚本按写死的位置去认，
不靠模型每次现猜——认不出就如实报「没读到」，绝不拿别的数字顶上。

「粉丝指数」不是粉丝数。抖音创作者中心首页那个 301 是账号权重分，
不是粉丝量；真正的总数在数据中心页的「总粉丝量」，实测同一个号是 299。
读错了不会报错，只会一直错下去——所以判据写死在下面的正则里。

用法：
    # B 站：自动，不开浏览器
    python3 scripts/refresh-followers.py --platform bilibili

    # 另外三个：在已登录的浏览器里 observe 页面，把输出存成文件
    python3 scripts/refresh-followers.py --platform douyin --in /tmp/dy-data.txt
    python3 scripts/refresh-followers.py --platform xiaohongshu --in /tmp/xhs-home.txt
    python3 scripts/refresh-followers.py --platform wechat_channels --in /tmp/wx-home.txt

    # 光看不写
    python3 scripts/refresh-followers.py --platform douyin --in /tmp/dy-data.txt --dry-run

写完记得跑 node scripts/check-followers.mjs 和 node scripts/build-site.mjs。

**写进去的是当天的快照，不是覆盖昨天的。** 涨粉看的是两条快照的差：
一天一条，页面上才画得出曲线。同一天重刷会替换掉当天那条，不会多出一条。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VIDEOS_FILE = REPO_ROOT / "data/videos.jsonl"
FOLLOWERS_FILE = REPO_ROOT / "data/followers.jsonl"
PLATFORMS = ["bilibili", "douyin", "xiaohongshu", "wechat_channels"]

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


# --------------------------------------------------------------------------
# 读写
# --------------------------------------------------------------------------

def load_snapshots() -> list[dict]:
    if not FOLLOWERS_FILE.exists():
        return []
    return [
        json.loads(line)
        for line in FOLLOWERS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def save_snapshots(snapshots: list[dict]) -> None:
    """按日期倒序写回，最新在最上面，跟 videos.jsonl 一个习惯。"""
    rows = sorted(snapshots, key=lambda s: s["date"], reverse=True)
    with FOLLOWERS_FILE.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def latest(snapshots: list[dict], platform: str) -> tuple[int, str] | None:
    """该平台最近一次读到的粉丝数和日期。"""
    for s in sorted(snapshots, key=lambda s: s["date"], reverse=True):
        p = s.get("platforms", {}).get(platform)
        if p is not None and isinstance(p.get("followers"), int):
            return p["followers"], s["date"]
    return None


# --------------------------------------------------------------------------
# B 站：公开接口
# --------------------------------------------------------------------------

def _bili_json(url: str, retries: int = 3) -> tuple[dict | None, str | None]:
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.bilibili.com/"})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
        except urllib.error.HTTPError as exc:
            if i == retries - 1:
                return None, f"HTTP {exc.code}"
            continue
        except Exception as exc:  # noqa: BLE001 - 网络问题一律当可重试
            if i == retries - 1:
                return None, f"网络错误 {exc}"
            continue
        if data.get("code") == 0:
            return data["data"], None
        return None, f"code={data.get('code')} {data.get('message', '')}".strip()
    return None, "重试失败"


def bili_owner_mid() -> tuple[int | None, str | None]:
    """从任意一条作品的公开接口里取 UP 主 mid。

    没有单独的「我是谁」接口可免登录调用，但每一条作品都带着 owner.mid，
    取第一条能通的就够了。取不到就让人手动给 --mid。
    """
    if not VIDEOS_FILE.exists():
        return None, f"找不到 {VIDEOS_FILE}"
    for line in VIDEOS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        url = (row.get("platforms", {}).get("bilibili", {}) or {}).get("url", "")
        m = re.search(r"/video/(BV[0-9A-Za-z]+)", url)
        if not m:
            continue
        data, err = _bili_json(f"https://api.bilibili.com/x/web-interface/view?bvid={m.group(1)}")
        if data and data.get("owner", {}).get("mid"):
            return int(data["owner"]["mid"]), None
        if err and "code=62004" not in err and "稿件" not in err:
            # 这条作品的接口不可用是常事（62002 稿件退回、62012 单条限流），换下一条
            continue
    return None, "从作品接口里取不到 owner.mid，用 --mid 手动指定"


def bili_followers(mid: int) -> tuple[int | None, str | None]:
    """粉丝数走 relation/stat。返回的 follower 是精确整数，不是「1.9万」这种近似值。"""
    data, err = _bili_json(f"https://api.bilibili.com/x/relation/stat?vmid={mid}")
    if err:
        return None, err
    n = data.get("follower")
    if not isinstance(n, int):
        return None, f"接口里没有 follower 字段：{data}"
    return n, None


# --------------------------------------------------------------------------
# 另外三个平台：读页面文本
# --------------------------------------------------------------------------
#
# 三处的页面结构完全不同，标点、空格、同义写法都要容纳，但**认的是同一个东西**：
# 平台上写着的那个总数。认不出就返回 None，让人去核对，不退回到「大概是这个数」。
#
# 抖音的坑最多，写在这里免得下次踩：
#   - 「粉丝指数 301」是账号权重分，不是粉丝数；页面首页根本没写粉丝总数
#   - 真正的总粉丝量在数据中心页：`总粉丝量` 后面跟一个按钮，值在下一个节点
#   - 粉丝净增、吸粉量、脱粉量都在旁边，顺序不同，只认「总粉丝量」这个标签

# observe 出来的文本长这样（每行一个节点）：
#     @e69 button "299" [ctx: 总粉丝量]
# 也可能是不带 ref 的纯文本：
#     StaticText "299"
#     StaticText "总粉丝量"
# 所以两套都要认。

_NODE_RE = re.compile(r'(?P<line>(?:^|\n)\s*(?:@e\d+\s+\w+|StaticText|paragraph|heading)\s+"(?P<text>[^"]*)"(?P<ctx>[^\n]*))')


def _nodes(raw: str) -> list[tuple[str, str]]:
    """把页面文本拆成 (文本, 整行) 列表，文本里带引号的已反转义。"""
    out = []
    for m in _NODE_RE.finditer(raw):
        text = m.group("text").replace('\\"', '"')
        out.append((text, m.group("line")))
    return out


def _parse_followers_number(text: str) -> int | None:
    """把「6441」「1.9万」「2,299」都转成整数。近似值按四舍五入的上界取最小值。"""
    t = (text or "").strip().replace(",", "").replace("，", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(万|w|W|亿)?", t)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("万", "w", "W"):
        n *= 10000
    elif unit == "亿":
        n *= 100000000
    return int(round(n))


def parse_douyin(raw: str) -> tuple[int | None, str]:
    """抖音：数据中心页的「总粉丝量」。

    两种形态都认：
      1. 值节点在同一条的 ctx 里：`@e69 button "299" [ctx: 总粉丝量]`
      2. 值节点和标签是前后两个节点：`StaticText "总粉丝量"` 之后跟 `StaticText "299"`
    认不出时明确说「没读到」，不要拿首页的粉丝指数糊弄——那是个位数的分，
    不是粉丝量。
    """
    nodes = _nodes(raw)
    # 形态 1：同一行的 ctx 里带着标签
    for text, line in nodes:
        if "总粉丝量" in line and "ctx" in line:
            n = _parse_followers_number(text)
            if n is not None:
                return n, "总粉丝量"
    # 形态 2：标签在前，值是紧接着的纯数字节点
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "总粉丝量":
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "总粉丝量"
    if "粉丝指数" in raw:
        return None, "页面里只有「粉丝指数」（账号权重分），没有总粉丝量；要打开数据中心页"
    return None, "没找到「总粉丝量」"


def parse_xiaohongshu(raw: str) -> tuple[int | None, str]:
    """小红书：创作平台首页的「粉丝数」。

    页面上一共出现两次：
      `6441` / `粉丝数`            ← 账号卡片
      `粉丝` / `6441` / `/10000`    ← 成就进度条
    两处是同一个数，取第一个就够。注意别认成「关注数」（0）。
    """
    nodes = _nodes(raw)
    # 形态 1：值在前、标签在后（账号卡片，observe 里就是这个顺序）
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "粉丝数":
            continue
        for j in range(i - 1, max(i - 4, -1), -1):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "粉丝数"
    # 形态 2：标签在前、值在后
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "粉丝数":
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "粉丝数"
    return None, "没找到「粉丝数」"


def parse_wechat_channels(raw: str) -> tuple[int | None, str]:
    """视频号：助手首页的「关注者」。

    页面上是 `视频` / `92` / `关注者` / `446` 这一串，标签在值前面。
    「昨日数据」里的「净增关注」是另一个量，别认错。
    """
    nodes = _nodes(raw)
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "关注者":
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "关注者"
    return None, "没找到「关注者」"


PARSERS = {
    "douyin": parse_douyin,
    "xiaohongshu": parse_xiaohongshu,
    "wechat_channels": parse_wechat_channels,
}


# --------------------------------------------------------------------------
# 写入
# --------------------------------------------------------------------------

def upsert(snapshots: list[dict], day: str, platform: str, followers: int, *, dry_run: bool) -> tuple[list[str], str | None]:
    """把今天的读数写进当天那条快照。同一天已有就替换，不加第二条。"""
    old = latest(snapshots, platform)
    if old and old == (followers, day):
        return [], None

    if followers < 0:
        return [], "粉丝数不能是负数"

    snap = next((s for s in snapshots if s.get("date") == day), None)
    if snap is None:
        snap = {"date": day, "platforms": {}}
        if not dry_run:
            snapshots.append(snap)
    if not dry_run:
        snap.setdefault("platforms", {})[platform] = {"followers": followers}

    if old is None:
        return [f"首次记录：{followers}"], None
    prev, prev_day = old
    delta = followers - prev
    sign = "+" if delta >= 0 else ""
    if delta == 0:
        return [f"{prev}（{prev_day}）→ {followers}，没变"], None
    return [f"{prev}（{prev_day}）→ {followers}（{sign}{delta}）"], None


def main() -> int:
    ap = argparse.ArgumentParser(description="刷新 data/followers.jsonl 的四平台粉丝数")
    ap.add_argument("--platform", required=True, choices=PLATFORMS)
    ap.add_argument("--in", dest="inputs", nargs="+", help="observe 出来的页面文本（B 站不需要）")
    ap.add_argument("--mid", type=int, help="B 站的 mid；不给就从作品接口里取")
    ap.add_argument("--date", help="快照日期，默认今天")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    args = ap.parse_args()

    day = args.date or date.today().isoformat()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day):
        ap.error(f"--date 必须是 YYYY-MM-DD：{day}")

    snapshots = load_snapshots()
    print(f"读入 {len(snapshots)} 条快照", file=sys.stderr)

    if args.platform == "bilibili":
        mid = args.mid
        if mid is None:
            mid, err = bili_owner_mid()
            if mid is None:
                print(f"  ! {err}", file=sys.stderr)
                return 1
            print(f"  UP 主 mid：{mid}", file=sys.stderr)
        followers, err = bili_followers(mid)
        source = "relation/stat 接口"
    else:
        if not args.inputs:
            ap.error(f"{args.platform} 需要 --in 指定页面文本文件")
        source = ""
        followers, err = None, None
        missed = ""
        for p in args.inputs:
            raw = Path(p).read_text(encoding="utf-8", errors="replace")
            n, src = PARSERS[args.platform](raw)
            print(f"  {Path(p).name}: {src}{f' → {n}' if n is not None else ''}", file=sys.stderr)
            if n is None:
                missed = src
                continue
            if followers is not None and n != followers:
                # 两个文件读出不同的数：不猜哪个对，报出来让人核对
                print(f"  ! 两次读数不一致（{followers} vs {n}），不写入", file=sys.stderr)
                return 1
            followers, source = n, src
        if followers is None:
            err = missed or "没读到粉丝数"

    if err:
        print(f"\n{args.platform}：{err}", file=sys.stderr)
        print("没读到就不写——不要用别的数字顶上。", file=sys.stderr)
        return 1

    diffs, why = upsert(snapshots, day, args.platform, followers, dry_run=args.dry_run)
    if why:
        print(f"\n{args.platform}：{why}", file=sys.stderr)
        return 1

    print(f"\n{args.platform}：{followers}（来源：{source}）")
    for d in diffs:
        print(f"  {d}")

    if args.dry_run:
        print("\n（--dry-run，未写盘）")
        return 0

    save_snapshots(snapshots)
    print(f"\n已写回 {FOLLOWERS_FILE.relative_to(REPO_ROOT)}")
    print("接着跑：node scripts/check-followers.mjs && node scripts/build-site.mjs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
