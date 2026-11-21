#!/usr/bin/env python3
"""
刷新 data/followers.jsonl 里五个平台的粉丝数。

粉丝数和作品指标是两套东西，别混：
  - 作品指标（data/videos.jsonl）一行一期，五平台各自一条，可以相加
  - 粉丝数（data/followers.jsonl）是账号级的，一天一条快照，**不能相加**
所以刷新脚本、校验脚本、页面呈现都是分开的一套。

五个平台的取数方式：

    bilibili         公开接口，免登录。先取任一条作品的 owner.mid，再查粉丝数
    douyin           Ego Lite 采创作者后台「数据中心」页里的「总粉丝量」
    xiaohongshu      Ego Lite 采创作者服务平台首页的「粉丝数」
    wechat_channels  Ego Lite 采视频号助手首页的「关注者」
    x                Ego Lite 采个人页 GraphQL（UserByScreenName 精确整数），页面「关注者 / Followers」兜底

**只有 B 站能自动跑。** 另外四个平台需要登录态，统一通过 `scripts/collect-ego.py`
在已登录的 Ego Lite 浏览器里采集，再把输出文件交给 `--in`。脚本按写死的规则去认，
认不出就如实报「没读到」，绝不拿别的数字顶上。

「粉丝指数」不是粉丝数。抖音创作者中心首页那个 301 是账号权重分，
不是粉丝量；真正的总数在数据中心页的「总粉丝量」，实测同一个号是 299。
读错了不会报错，只会一直错下去——所以判据写死在下面的正则里。

用法：
    # B 站：自动，不开浏览器
    python3 scripts/refresh-followers.py --platform bilibili

    # 另外四个：先用 Ego Lite 一次性采集到 /tmp/jackskill-ego/
    python3 scripts/collect-ego.py --target followers
    python3 scripts/refresh-followers.py --platform douyin --in /tmp/jackskill-ego/dy-followers.txt
    python3 scripts/refresh-followers.py --platform xiaohongshu --in /tmp/jackskill-ego/xhs-home.txt
    python3 scripts/refresh-followers.py --platform wechat_channels --in /tmp/jackskill-ego/wx-home.txt
    python3 scripts/refresh-followers.py --platform x --in /tmp/jackskill-ego/x-followers.json

    # 光看不写
    python3 scripts/refresh-followers.py --platform x --in /tmp/jackskill-ego/x-followers.json --dry-run

写完记得跑 node scripts/check-followers.mjs && node scripts/build-site.mjs。

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
PLATFORMS = ["bilibili", "douyin", "xiaohongshu", "wechat_channels", "x"]

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
# 另外四个平台：读 Ego Lite 采集的页面文本与 JSON
# --------------------------------------------------------------------------
#
# 各处页面结构不同，标点、空格、同义写法都要容纳，但**认的是同一个东西**：
# 平台上写着的那个总数。认不出就返回 None，让人去核对，不退回到「大概是这个数」。
#
# 抖音的坑最多，写在这里免得下次踩：
#   - 「粉丝指数 301」是账号权重分，不是粉丝数；页面首页根本没写粉丝总数
#   - 真正的总粉丝量在数据中心页：`总粉丝量` 后面跟一个数字节点
#   - 粉丝净增、吸粉量、脱粉量都在旁边，顺序不同，只认「总粉丝量」这个标签

# 兼容 Ego Lite 的两种文本形态：
#   1. Ego Lite page.snapshot()：`  text "总粉丝量"` / `  button "299"`
#   2. 纯文本（`document.body.innerText` 按行输出）：`总粉丝量\n299`

_EGO_NODE_RE = re.compile(
    r'(?P<line>(?:^|\n)\s*(?:text|button|heading|paragraph|link)\s+"(?P<text>(?:[^"\\]|\\.)*)"(?P<ctx>[^\n]*))'
)


def _nodes(raw: str) -> list[tuple[str, str]]:
    """把页面文本拆成 (文本, 整行) 列表，兼容 Ego Lite snapshot 与纯文本。"""
    out = []
    for m in _EGO_NODE_RE.finditer(raw):
        text = m.group("text").replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")
        out.append((text, m.group("line")))
    if out:
        return out
    return [(line.strip(), line) for line in raw.splitlines() if line.strip()]


def _parse_followers_number(text: str) -> int | None:
    """把「6441」「1.9万」「2,299」「1.2K」「1.5M」都转成整数。"""
    t = (text or "").strip().replace(",", "").replace("，", "")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(万|w|W|亿|k|K|m|M)?", t)
    if not m:
        return None
    n = float(m.group(1))
    unit = m.group(2) or ""
    if unit in ("k", "K"):
        n *= 1000
    elif unit in ("万", "w", "W"):
        n *= 10000
    elif unit in ("m", "M"):
        n *= 1000000
    elif unit == "亿":
        n *= 100000000
    return int(round(n))


def parse_douyin(raw: str) -> tuple[int | None, str]:
    """抖音：数据中心页的「总粉丝量」。

    两种形态都认：
      1. 同一行/同一节点连写：`总粉丝量 299` / `总粉丝量：299`
      2. 值节点和标签是前后两个节点：`总粉丝量` 之后跟 `299`
    认不出时明确说「没读到」，不要拿首页的粉丝指数糊弄——那是个账号权重分，
    不是粉丝量。
    """
    nodes = _nodes(raw)
    # 形态 1：同节点/同行内「总粉丝量 + 数字」
    for text, _ in nodes:
        m = re.search(r"总粉丝量\s*[:：]?\s*(\d[\d,]*(?:\.\d+)?\s*(?:万|w|W|亿)?)", text)
        if m:
            n = _parse_followers_number(m.group(1))
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
    # 骨架屏保护：小红书首页数据接口尚未返回时，账号卡片会短暂渲染出
    # 「0 关注数 / 0 粉丝数 / 0 获赞与收藏 / 小红书账号:（空）」。
    # 绝不能把这个占位 0 当成粉丝清零写进库。
    is_skeleton = bool(re.search(r"小红书账号\s*[:：]\s*(?:\n|$)", raw))
    # 形态 0：同一段文本里「数字 + 粉丝数」连写
    for text, _ in nodes:
        m = re.search(r"(\d[\d,]*(?:\.\d+)?\s*(?:万|w|W|亿)?)\s*粉丝数", text)
        if m:
            n = _parse_followers_number(m.group(1))
            if n is not None:
                if n == 0 and is_skeleton:
                    return None, "页面仍在加载（小红书账号数据尚未返回，读到占位 0）"
                return n, "粉丝数"
    # 形态 1：值在前、标签在后（账号卡片，innerText / snapshot 里就是这个顺序）
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "粉丝数":
            continue
        for j in range(i - 1, max(i - 4, -1), -1):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                if n == 0 and is_skeleton:
                    return None, "页面仍在加载（小红书账号数据尚未返回，读到占位 0）"
                return n, "粉丝数"
    # 形态 2：标签在前、值在后
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "粉丝数":
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                if n == 0 and is_skeleton:
                    return None, "页面仍在加载（小红书账号数据尚未返回，读到占位 0）"
                return n, "粉丝数"
    return None, "没找到「粉丝数」"


def parse_wechat_channels(raw: str) -> tuple[int | None, str]:
    """视频号：助手首页的「关注者」。

    页面上是 `视频` / `92` / `关注者` / `446` 这一串，标签在值前面。
    「昨日数据」里的「净增关注」是另一个量，别认错。
    """
    nodes = _nodes(raw)
    for text, _ in nodes:
        m = re.search(r"(?:^|\s)关注者\s*[:：]?\s*(\d[\d,]*(?:\.\d+)?\s*(?:万|w|W|亿)?)", text)
        if m:
            n = _parse_followers_number(m.group(1))
            if n is not None:
                return n, "关注者"
    for i, (text, _) in enumerate(nodes):
        if text.strip() != "关注者":
            continue
        for j in range(i + 1, min(i + 4, len(nodes))):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "关注者"
    return None, "没找到「关注者」"


def _parse_x_text(raw: str) -> tuple[int | None, str]:
    """从 X 个人主页文本或 Ego snapshot 提取粉丝数（中英文均认，排除「正在关注 / Following」）。"""
    nodes = _nodes(raw)
    # 形态 1：同行/同节点「462 关注者」或「462 Followers」
    for text, _ in nodes:
        m = re.search(
            r"(\d[\d,]*(?:\.\d+)?\s*(?:万|w|W|亿|k|K|m|M)?)\s*(?:位)?(?:关注者|Followers)\b",
            text,
            re.I,
        )
        if m:
            n = _parse_followers_number(m.group(1))
            if n is not None:
                return n, "X 个人页关注者"
    # 形态 2：值在前、标签在后（例如两行 `462` / `关注者` 或 `462` / `Followers`）
    for i, (text, _) in enumerate(nodes):
        if text.strip().lower() not in ("关注者", "followers"):
            continue
        for j in range(i - 1, max(i - 3, -1), -1):
            n = _parse_followers_number(nodes[j][0])
            if n is not None:
                return n, "X 个人页关注者"
    return None, "没找到 X 的「关注者 / Followers」"


def parse_x(raw: str) -> tuple[int | None, str]:
    """X：优先读 Ego Lite 采集的精确 JSON（UserByScreenName），缺失时退回页面文本兜底。"""
    s = (raw or "").strip()
    if s.startswith("{"):
        try:
            obj = json.loads(s)
        except json.JSONDecodeError:
            obj = None
        if isinstance(obj, dict):
            # 1) collect-ego.py 产出的 x-followers.json
            if isinstance(obj.get("followers"), int):
                src = obj.get("source") or "x-followers.json"
                return obj["followers"], str(src)
            # 2) 原始 UserByScreenName GraphQL 响应
            u = (((obj.get("data") or {}).get("user") or {}).get("result")) or {}
            if isinstance(u, dict):
                rc = u.get("relationship_counts") or {}
                if isinstance(rc.get("followers"), int):
                    return rc["followers"], "UserByScreenName.relationship_counts"
                leg = u.get("legacy") or {}
                if isinstance(leg.get("followers_count"), int):
                    return leg["followers_count"], "UserByScreenName.legacy"
            # 3) JSON 里带的 DOM 文本兜底
            if isinstance(obj.get("domText"), str) and obj["domText"].strip():
                return _parse_x_text(obj["domText"])
    return _parse_x_text(raw)


PARSERS = {
    "douyin": parse_douyin,
    "xiaohongshu": parse_xiaohongshu,
    "wechat_channels": parse_wechat_channels,
    "x": parse_x,
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
    ap = argparse.ArgumentParser(description="刷新 data/followers.jsonl 的五平台粉丝数")
    ap.add_argument("--platform", required=True, choices=PLATFORMS)
    ap.add_argument("--in", dest="inputs", nargs="+", help="Ego Lite 采集脚本产出的页面文本或 JSON（B 站不需要）")
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
            ap.error(f"{args.platform} 需要 --in 指定页面文本或 JSON 文件")
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
