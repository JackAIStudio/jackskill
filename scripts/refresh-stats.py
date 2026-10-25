#!/usr/bin/env python3
"""
刷新 data/videos.jsonl 里各平台的播放 / 点赞 / 收藏 / 分享 / 评论。

四平台的数据来源不一样，可靠性也不一样，这个脚本按平台分开处理：

    bilibili         公开接口，免登录、返回精确值、字段有名字
    douyin           创作者后台列表页，页面文本 → 按列序解析
    xiaohongshu      创作者后台列表页，同上
    wechat_channels  创作者后台列表页，同上（列表要滚动才渲染）

**为什么 B 站不用浏览器。** B 站的
`api.bilibili.com/x/web-interface/view?bvid=` 免登录就能拿到
view / like / favorite / share / reply 五个精确值，和创作者后台完全一致，
而且返回的是字段名不是位置，不存在看错列的问题。220 期跑一遍只有一条会
被限流（62012），退避重试即可。这条路径比读后台列表页省事得多，别绕回去。

**为什么另外三个平台必须靠页面文本。** 它们的后台接口都要登录态和签名，
curl 直接打拿不到；只能在已登录的浏览器里读。读回来的是一段纯文本，
数字没有表头，靠位置判断——所以列序写死在下面 PLATFORM_SPEC 里，不让
模型每次现猜。四个平台的列序各不相同，而且都不直观：

    bilibili         （走接口，无列序问题）
    douyin           播放 点赞 评论 分享 收藏
    xiaohongshu      观看 评论 点赞 收藏 分享     ← 收藏在分享前面，最反直觉
    wechat_channels  播放 点赞 评论 分享 收藏

小红书那一条是拿五期旧数据反推验证出来的：只有「观看/评论/点赞/收藏/分享」
这一种排法能同时对上。按直觉写成「观看/点赞/评论/收藏/分享」会每一条都错位。

用法：
    # B 站：全部重刷（默认就是全部）
    python3 scripts/refresh-stats.py --platform bilibili

    # 另外三个平台：先在浏览器里 observe 列表页，把输出存成文件
    python3 scripts/refresh-stats.py --platform douyin --in /tmp/dy-page.txt
    python3 scripts/refresh-stats.py --platform xiaohongshu --in /tmp/xhs-1.txt /tmp/xhs-2.txt
    python3 scripts/refresh-stats.py --platform wechat_channels --in /tmp/wx-page.txt

    # 只看看会改什么，不落盘
    python3 scripts/refresh-stats.py --platform douyin --in /tmp/dy-page.txt --dry-run

写完记得跑 node scripts/check-data.mjs 和 node scripts/build-site.mjs。

**近似值不覆盖精确值。** 抖音后台播放量上万会显示成「1.3万」。这个值是
四舍五入过的，1.3 万覆盖 [12500, 13500)。如果库里已经有一条精确值落在
这个区间里，那条精确值比「1.3万」更可信，不覆盖。硬写 13000 是降精度。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = REPO_ROOT / "data/videos.jsonl"

METRICS = ["views", "likes", "collects", "shares", "comments"]

# 页面上的列序，按「从左到右」写死。改这里之前先拿旧数据反推验证一遍，
# 四个平台的顺序真的不一样，凭直觉改会静默错位。
PLATFORM_SPEC = {
    "douyin": ["views", "likes", "comments", "shares", "collects"],
    "xiaohongshu": ["views", "comments", "likes", "collects", "shares"],
    "wechat_channels": ["views", "likes", "comments", "shares", "collects"],
}

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)


# --------------------------------------------------------------------------
# 通用
# --------------------------------------------------------------------------

def norm(s: str) -> str:
    """标题归一化：去掉标点、空格、话题标签，用于模糊匹配。"""
    s = re.sub(r"\s*#[^\s#]+", "", s or "")
    return re.sub(r"[｜|:：，。！？!?,.~～_\-/\s#]", "", s).lower()


def load_rows() -> list[dict]:
    return [json.loads(line) for line in DATA_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]


def save_rows(rows: list[dict]) -> None:
    with DATA_FILE.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n")


def recompute_summary(row: dict) -> None:
    row["summary"] = {
        m: sum(p.get(m, 0) for p in row["platforms"].values()) for m in METRICS
    }


def parse_count(text: str) -> tuple[int, bool] | None:
    """把页面上的数字转成整数。第二个返回值表示它是不是近似值。

    「1.3万」这种是四舍五入过的，1.3 万覆盖 [12500, 13500)。返回近似标记，
    让调用方决定要不要覆盖已有的精确值。
    """
    t = (text or "").strip()
    if not re.fullmatch(r"[\d.]+[万亿]?", t):
        return None
    if t.endswith("万"):
        try:
            v = float(t[:-1])
        except ValueError:
            return None
        return int(round(v * 10000)), True
    if t.endswith("亿"):
        try:
            v = float(t[:-1])
        except ValueError:
            return None
        return int(round(v * 100000000)), True
    try:
        return int(t), False
    except ValueError:
        return None


def rounded_interval(approx_value: int, raw: str) -> tuple[int, int]:
    """「1.3万」这种写法对应的真实取值区间，用来判断旧值是否更精确。"""
    if "万" in raw:
        # 一位小数：1.3 万 = [12500, 13500)
        return approx_value - 500, approx_value + 500
    if "亿" in raw:
        return approx_value - 5000000, approx_value + 5000000
    return approx_value, approx_value


# --------------------------------------------------------------------------
# B 站：公开接口
# --------------------------------------------------------------------------

def bili_fetch(bvid: str, retries: int = 3) -> tuple[dict | None, str | None]:
    url = f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.load(r)
        except Exception as exc:  # noqa: BLE001 - 网络问题一律当可重试
            if i == retries - 1:
                return None, f"网络错误 {exc}"
            time.sleep(1.5 * (i + 1))
            continue
        code = data.get("code")
        if code == 0:
            stat = data["data"]["stat"]
            return {
                "views": stat["view"],
                "likes": stat["like"],
                "collects": stat["favorite"],
                "shares": stat["share"],
                "comments": stat["reply"],
            }, None
        # 62012 是频率限制，退避后重试；62002「稿件不可见」是平台侧事实，重试没用
        if code == 62012 and i < retries - 1:
            time.sleep(2.0 * (i + 1))
            continue
        return None, f"code={code} {data.get('message', '')}".strip()
    return None, "重试耗尽"


def refresh_bilibili(rows: list[dict], *, delay: float, dry_run: bool) -> list[str]:
    log: list[str] = []
    targets = []
    for r in rows:
        b = r["platforms"].get("bilibili")
        if not b:
            continue
        m = re.search(r"/video/(BV[0-9A-Za-z]+)", b.get("url", ""))
        if m:
            targets.append((r, b, m.group(1)))

    print(f"B 站待刷 {len(targets)} 期", file=sys.stderr)
    changed = 0
    failed = []
    for i, (row, plat, bvid) in enumerate(targets):
        stat, err = bili_fetch(bvid)
        if err:
            failed.append((row["date"], bvid, err))
            print(f"  ! {row['date']} {bvid}: {err}", file=sys.stderr)
        else:
            diffs = []
            for k, v in stat.items():
                old = plat.get(k)
                if old != v:
                    diffs.append(f"{k} {old}→{v}")
                    if not dry_run:
                        plat[k] = v
            if diffs:
                changed += 1
                log.append(f"{row['date']} {row['topic'][:24]}: " + ", ".join(diffs))
        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{len(targets)}", file=sys.stderr)
        time.sleep(delay)

    print(f"\nB 站：{changed} 期有变化，{len(failed)} 期失败", file=sys.stderr)
    for date, bvid, err in failed:
        print(f"  失败 {date} {bvid}: {err}", file=sys.stderr)
    return log


# --------------------------------------------------------------------------
# 全局配对：后台列表页 302 条，仓库 302 条，逐条按「当天」找会漏掉一大片
# --------------------------------------------------------------------------

# 平台侧发布日期和仓库 topic 的日期经常差一天（早上录、晚上发，或者跨时区），
# 标题还会被改写（「我做了一个」→「我开发了个」）。所以配对不能只认当天。
MATCH_MAX_GAP_DAYS = 40      # 超出这个天数的两期不可能是同一条
MATCH_MIN_SIMILARITY = 0.55  # 标题相似度下限
MATCH_MARGIN = 0.06          # 最佳候选要甩开第二名多少才认


def _similar(a: str, b: str) -> float:
    import difflib

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


def pair_items_to_rows(
    rows: list[dict], platform: str, items: list[dict]
) -> tuple[list[tuple[dict, dict]], list[dict]]:
    """把读回来的作品和仓库记录做**一对一**配对，返回 (配好的对, 没配上的作品)。

    为什么要全局配对，而不是像以前那样只看同一天：列表页读回来的标题经常和
    仓库 topic 差一天（2026-09-10 对 09-09、08-30 对 08-29），外加平台会改写
    标题（「我做了一个达芬奇插件」→「我开发了个达芬奇插件」）。只按当天匹配时
    这些会全部落到「未匹配」，数字一直停在旧快照上，而页面上早就变了。

    两条约束防止张冠李戴：
      - **日期必须接近**：超过 40 天的两期不可能是同一条；
      - **一对一**：一条作品只能配一条记录，按分数从高到低贪心分配，
        必须同时甩开「同一条作品的第二名」和「同一记录的竞争者」一定余量。
    """
    target_rows = [r for r in rows if platform in r.get("platforms", {})]
    if not target_rows or not items:
        return [], list(items)

    scored: list[tuple[float, dict, dict]] = []
    for it in items:
        try:
            item_date = date.fromisoformat(it["date"])
        except (KeyError, ValueError):
            continue
        for r in target_rows:
            try:
                row_date = date.fromisoformat(r["date"])
            except (KeyError, ValueError):
                continue
            gap = abs((row_date - item_date).days)
            if gap > MATCH_MAX_GAP_DAYS:
                continue
            t, rt = norm(it["title"]), norm(r["topic"])
            score = _similar(it["title"], r["topic"])
            if t and rt:
                if t == rt:
                    score = 1.0
                elif (t in rt or rt in t) and min(len(t), len(rt)) >= 6:
                    score = max(score, 0.9)
            # 同一天、差一天，比「标题也一样但差了 20 天」更可信
            score += 0.04 if gap == 0 else (0.02 if gap == 1 else 0.0)
            scored.append((score, it, r))

    scored.sort(key=lambda x: -x[0])

    used_items: set[int] = set()
    used_rows: set[str] = set()
    pairs: list[tuple[dict, dict]] = []
    for score, it, r in scored:
        key = id(it)
        if key in used_items or r["id"] in used_rows:
            continue
        if score < MATCH_MIN_SIMILARITY:
            continue
        # 同一条作品的更强候选还没被占走 → 让给它。
        # 比的是「基础分」，不含 0/1 天那点加分；否则标题完全一样的两条
        # （只差一天）会永远互相让位，谁都配不上。基础分打平时按分数排序
        # 已保证日期更近的在前，直接认它。
        base = score - (0.04 if it["date"] == r["date"] else 0.02)
        rivals = [
            s - (0.04 if it2["date"] == r2["date"] else 0.02)
            for s, it2, r2 in scored
            if it2 is it and r2["id"] != r["id"] and r2["id"] not in used_rows
        ]
        if rivals:
            top = max(rivals)
            tied = abs(top - base) < 1e-9
            if not tied and base < top + MATCH_MARGIN:
                continue
        used_items.add(key)
        used_rows.add(r["id"])
        pairs.append((r, it))

    unmatched = [it for it in items if id(it) not in used_items]
    return pairs, unmatched


# --------------------------------------------------------------------------
# 三个后台：解析 observe 出来的页面文本
# --------------------------------------------------------------------------

STATIC = re.compile(r'StaticText\s+"((?:[^"\\]|\\.)*)"')
BUTTON = re.compile(r'button\s+"((?:[^"\\]|\\.)*)"')


def _unescape(s: str) -> str:
    return s.replace('\\"', '"').replace("\\n", "\n").replace("\\\\", "\\")


def parse_xhs(raw: str) -> list[dict]:
    """小红书：标题 / 日期 / 五个裸数字，没有表头。

    日期形如 `2026-10-22 17:39`，紧跟其后五个纯数字就是
    观看 评论 点赞 收藏 分享。中间的 img / button 行直接跳过。
    """
    items = []
    lines = [_unescape(x).strip() for x in STATIC.findall(raw)]
    i = 0
    while i < len(lines):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", lines[i]):
            # 往前找标题：最近一个既不是日期也不是纯数字的行
            title = ""
            for j in range(i - 1, max(-1, i - 4), -1):
                cand = lines[j]
                if cand and not re.fullmatch(r"[\d.]+[万亿]?", cand) and not re.fullmatch(
                    r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", cand
                ):
                    title = cand
                    break
            nums = []
            k = i + 1
            while k < len(lines) and len(nums) < 5:
                if re.fullmatch(r"[\d.]+[万亿]?", lines[k]):
                    nums.append(lines[k])
                    k += 1
                else:
                    break
            if title and len(nums) == 5:
                items.append({"title": title, "date": lines[i][:10], "raw": nums})
            i = k
        else:
            i += 1
    return items


def parse_wx(raw: str) -> list[dict]:
    """视频号：标题 / 日期 / 「已声明原创」/ 五个裸数字。

    列表不滚动的话只有导航栏，滚一下才渲染出数据；所以空结果是常态，
    让调用方重新滚一次，不要当成「这期没数据」。

    标题里带「年」是常事（「都2026年了，还在用传统方式剪口播？」），所以
    排除上一层候选时只能按「这一行是不是日期」判断，不能按「含不含年」——
    按含年判断会把这类标题整条丢掉。
    """
    items = []
    lines = [_unescape(x).strip() for x in STATIC.findall(raw)]
    date_re = re.compile(r"\d{4}年\d{1,2}月\d{1,2}日")
    i = 0
    while i < len(lines):
        if re.fullmatch(r"\d{4}年\d{2}月\d{2}日 \d{2}:\d{2}", lines[i]):
            title = ""
            for j in range(i - 1, max(-1, i - 4), -1):
                cand = lines[j]
                if not cand:
                    continue
                if re.fullmatch(r"[\d.]+[万亿]?", cand) or date_re.search(cand):
                    continue
                title = cand
                break
            nums = []
            k = i + 1
            while k < len(lines) and len(nums) < 5:
                if re.fullmatch(r"[\d.]+[万亿]?", lines[k]):
                    nums.append(lines[k])
                    k += 1
                elif lines[k] in ("已声明原创", "作者修改过视频信息"):
                    k += 1
                else:
                    break
            if len(nums) == 5:
                d = re.match(r"(\d{4})年(\d{2})月(\d{2})日", lines[i])
                items.append(
                    {"title": title, "date": f"{d.group(1)}-{d.group(2)}-{d.group(3)}", "raw": nums}
                )
            i = k
        else:
            i += 1
    return items


DY_LABELS = {"播放": "views", "点赞": "likes", "评论": "comments", "分享": "shares", "收藏": "collects"}


DY_DATE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日 \d{2}:\d{2}")
DY_NOISE = ("已发布", "减少作品推荐", "查看详情", "已智能生成章节要点", "当前字幕")


def parse_dy(raw: str) -> list[dict]:
    """抖音：卡片是「标题 / 日期 / 状态 / 五组『标签 数值』」。

    和另外两个平台一样以日期为锚：往前找标题，往后找五组指标。往后找的时候
    认标签（播放/点赞/评论/分享/收藏），不认位置——标签是稳定的，位置不是。

    状态为「减少作品推荐」的作品，五个指标在页面上是「-」不是数字。这类
    仍然返回一条记录，带 blocked 标记和原因，交给上层打 limited：保留最后
    读数，说明这个数停在什么时候。**不清零——限流前那些播放真实发生过。**
    """
    # 按文档顺序取所有 StaticText / button 的文本，顺序不能丢——
    # 标题在日期前、指标在日期后，全靠相对位置判断。
    tokens = [
        _unescape(m.group(1)).strip()
        for m in re.finditer(r'(?:StaticText|button)\s+"((?:[^"\\]|\\.)*)"', raw)
    ]

    items = []
    for idx, tok in enumerate(tokens):
        m = DY_DATE.fullmatch(tok)
        if not m:
            continue
        date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

        # 往前找标题：跳过状态、纯数字、纯标签这些
        title = ""
        for j in range(idx - 1, max(-1, idx - 5), -1):
            cand = tokens[j]
            if not cand or parse_count(cand) is not None:
                continue
            if DY_DATE.fullmatch(cand) or cand in DY_LABELS or cand.startswith(DY_NOISE):
                continue
            title = cand
            break

        # 往后找五组指标
        found: dict[str, str] = {}
        j = idx + 1
        while j < len(tokens) and len(found) < 5:
            label = DY_LABELS.get(tokens[j])
            if label and j + 1 < len(tokens):
                nxt = tokens[j + 1]
                if parse_count(nxt) is not None:
                    found[label] = nxt
                    j += 2
                    continue
            j += 1

        # 状态行（「减少作品推荐」等）在日期前，用来判断这期为什么没有数字
        status = ""
        for j in range(idx, min(len(tokens), idx + 4)):
            if tokens[j] in ("减少作品推荐", "不适宜公开", "限制自己可见", "已删除"):
                status = tokens[j]
                break

        if title and len(found) == 5:
            items.append(
                {"title": title, "date": date, "raw": [found[k] for k in PLATFORM_SPEC["douyin"]]}
            )
        elif title and not found:
            # 一个数都没读到：平台不给。仍然交出去，让上层打 limited 标记，
            # 保留最后读数——不是清零（那会丢掉限流前真实跑过的量）。
            items.append(
                {"title": title, "date": date, "raw": None, "blocked": True,
                 "reason": status or "平台不给数据"}
            )
    return items


DY_STAT_KEYS = {
    "play_count": "views",
    "digg_count": "likes",
    "comment_count": "comments",
    "share_count": "shares",
    "collect_count": "collects",
}

# 记录本身的状态。紧跟在 statistics 后面，和它属于同一条作品。
#   is_delete / is_prohibited / self_see / is_private 为 true 时，平台不会给真实播放
DY_HIDDEN_FLAGS = {
    "is_delete": "已删除",
    "is_prohibited": "已下架",
    "self_see": "仅自己可见",
    "is_private": "已设为私密",
}


def parse_dy_json(raw: str) -> list[dict]:
    """抖音：从 work_list 接口的原始 JSON 里取 statistics，精确值，不靠列序。

    比列表页可靠得多，原因有三：
      - statistics 里字段有名字（play_count 等），不存在看错列；
      - 全是精确整数，没有「1.3万」这类四舍五入；
      - 同一条记录里还带着 status，能区分「真的 0」和「平台不给看」。

    **别用同一个 JSON 里别处的 view_count** —— 那是话题标签的计数，
    不是播放量，按它抓会把每条读成 0 或者乱数。

    锚点是 `"statistics":{"aweme_id":"<id>"`：它同时给出作品 id 和五个指标，
    紧跟着的 `"status":{...}` 给出可见性。两段都在同一条记录里，位置稳定。

    返回值和 parse_dy 一致，所以上层逻辑不用改：`raw` 是五个精确数字的字符串，
    或者 `blocked=True` 表示平台不给数（这时保留最后读数，打 limited）。
    """
    items = []
    pattern = re.compile(
        r'\\"statistics\\":\{\\"aweme_id\\":\\"(\d+)\\"(.*?)\},\\"status\\":\{(.*?)\}'
    )
    for m in pattern.finditer(raw):
        aid, stat_body, status_body = m.group(1), m.group(2), m.group(3)

        values: dict[str, str] = {}
        for field, key in DY_STAT_KEYS.items():
            vm = re.search(r'\\"' + field + r'\\":(\d+)', stat_body)
            if vm:
                values[key] = vm.group(1)

        # 标题和日期：从这条记录往前找最近的一份。desc 里带话题标签，
        # 和仓库里的 topic 不一定完全一致，靠上层的归一化匹配兜底。
        pre = raw[max(0, m.start() - 30000):m.start()]
        dm = list(re.finditer(r'\\"desc\\":\\"(.*?)\\"', pre))
        title = _unescape(dm[-1].group(1)) if dm else ""
        cm = list(re.finditer(r'\\"create_time\\":(\d{9,10})', pre))
        when = ""
        if cm:
            when = time.strftime("%Y-%m-%d", time.localtime(int(cm[-1].group(1))))

        hidden = next(
            (why for flag, why in DY_HIDDEN_FLAGS.items()
             if re.search(r'\\"' + flag + r'\\":true', status_body)),
            None,
        )

        if len(values) == 5 and not hidden:
            items.append({
                "title": title,
                "date": when,
                "raw": [values[k] for k in PLATFORM_SPEC["douyin"]],
                "aweme_id": aid,
            })
        else:
            # 平台不给数：被删/下架/仅自己可见，或者字段不全。
            items.append({
                "title": title,
                "date": when,
                "raw": None,
                "blocked": True,
                "reason": hidden or "平台不给数据",
                "aweme_id": aid,
            })
    return items


PARSERS = {"xiaohongshu": parse_xhs, "wechat_channels": parse_wx, "douyin": parse_dy}


# --------------------------------------------------------------------------
# 匹配与写入
# --------------------------------------------------------------------------

def _work_id(row: dict, platform: str) -> str:
    """记录里存的这条作品 id（抖音的 aweme_id）。取不到就返回空串。"""
    url = (row.get("platforms", {}).get(platform, {}) or {}).get("url") or ""
    tail = url.rstrip("/").split("/")[-1]
    return tail if tail.isdigit() else ""


def match_row(
    rows: list[dict], platform: str, date: str, title: str, work_id: str = ""
) -> dict | None:
    """先按作品 id 精确匹配，对不上再按日期 + 归一化标题。

    **作品 id 优先，因为它没有歧义。** 同一天发两条是常事，标题还会被平台
    改写（加话题标签、截短），而 id 永远指向同一条作品。抖音走 work_list
    接口时能拿到 aweme_id，就用它。

    日期 + 标题是给小红书、视频号那两条路的：它们读的是列表页，拿不到 id。
    同一日期可能有多期，所以必须再比标题；标题对不上时退一步做包含匹配。
    """
    if work_id:
        for r in rows:
            if _work_id(r, platform) == work_id:
                return r
        return None  # 给了 id 却没找到，说明这条不在库里，别退化成猜
    same_day = [r for r in rows if r["date"] == date]
    if not same_day:
        return None
    t = norm(title)
    for r in same_day:
        if norm(r["topic"]) == t:
            return r
    for r in same_day:
        rt = norm(r["topic"])
        if t and (t in rt or rt in t):
            return r
    # 只有一期时，标题差异再大也认它
    if len(same_day) == 1:
        return same_day[0]
    return None


def apply_values(row: dict, platform: str, raw_values: list[str], *, dry_run: bool) -> tuple[list[str], str | None]:
    """把页面上读到的五个数写进记录，返回 (变更说明, 跳过原因)。"""
    order = PLATFORM_SPEC[platform]
    plat = row["platforms"].get(platform)
    if plat is None:
        return [], "该期没有这个平台的键"

    diffs = []
    for key, raw in zip(order, raw_values):
        parsed = parse_count(raw)
        if parsed is None:
            return [], f"无法解析的数字 {raw!r}"
        value, approximate = parsed
        old = plat.get(key, 0)

        if approximate:
            lo, hi = rounded_interval(value, raw)
            # 旧值落在四舍五入区间里 → 旧值更精确，不动
            if lo <= old < hi:
                continue
            # 旧值比近似值大：那是同一个数在涨，只是这次只读到近似值。
            # 保留旧值，别用一个粗值把细值盖掉。
            if old > value:
                continue
        if old == value:
            continue

        # 指标下降是可能的：观众会取消点赞、平台会清理播放。但播放量掉了
        # 一大截几乎只有两种解释——读错了行，或者平台侧改了可见性。前者要
        # 拦住，后者要人来判断，所以这里只对「明显异常」的跌幅报出来。
        if value < old and key == "views" and old > 0 and value < old * 0.8:
            return [], f"{key} 从 {old} 掉到 {value}（跌超 20%），疑似读错行或平台改可见性"

        diffs.append(f"{key} {old}→{value}")
        if not dry_run:
            plat[key] = value
    return diffs, None


def mark_limited(row: dict, platform: str, reason: str, *, dry_run: bool) -> tuple[list[str], str | None]:
    """平台不给数据（页面上是 `-`）时，保留最后读数并打上 limited 标记。

    **区分两件事：**
      - 平台返回 0   → 就是 0，不加标记
      - 平台返回 `-` → 这期被限流/退回，数字不再更新

    第二种如果直接清零，就把「限流前真实跑过的量」丢了。10-15 那期在限流
    前确实有 164 次播放，那是真的发生过的事实。所以保留原值，另记
    `limited: {reason, lastRead}`，说明这个数停在什么时候。

    读的时候，带 limited 的期次不能和正常期次比转化率——它的分母是冻住的。
    """
    plat = row["platforms"].get(platform)
    if plat is None:
        return [], "该期没有这个平台的键"

    old = plat.get("limited")
    last_read = old.get("lastRead") if old else None
    if not last_read:
        # 没有历史标记时，用这次跑批的日期当最后读数日
        last_read = date.today().isoformat()

    new = {"reason": reason, "lastRead": last_read}
    if old == new:
        return [], None

    diffs = [f"limited: {old} → {new}"] if old else [f"标记 limited（{reason}，最后读数 {last_read}）"]
    if not dry_run:
        plat["limited"] = new
    return diffs, None


def clear_limited(row: dict, platform: str, *, dry_run: bool) -> list[str]:
    """平台重新给数据了，把 limited 标记摘掉。"""
    plat = row["platforms"].get(platform)
    if plat is None or "limited" not in plat:
        return []
    if not dry_run:
        plat.pop("limited", None)
    return ["解除 limited（平台重新给数了）"]


def refresh_from_pages(rows: list[dict], platform: str, paths: list[str], *, dry_run: bool) -> list[str]:
    parser = PARSERS[platform]
    log: list[str] = []
    items: list[dict] = []
    for p in paths:
        raw = Path(p).read_text(encoding="utf-8", errors="replace")
        got = parser(raw)
        # 抖音优先走 work_list 接口的原始 JSON：字段有名字、全是精确值。
        # 解析不出来（给的是列表页文本）再退回按列序读。
        if platform == "douyin":
            precise = parse_dy_json(raw)
            if precise:
                print(f"  {Path(p).name}: 按 statistics 精确解析出 {len(precise)} 条", file=sys.stderr)
                got = precise
        print(f"  {Path(p).name}: 解析出 {len(got)} 条", file=sys.stderr)
        items.extend(got)

    if not items:
        hint = "（列表页要先滚动才会渲染出数据）" if platform == "wechat_channels" else ""
        print(f"  ! 没解析出任何记录{hint}", file=sys.stderr)
        return log

    matched = skipped = 0
    # 抖音的 work_list 带 aweme_id，id 是唯一可靠的判据，保持逐条精确匹配；
    # 小红书、视频号的列表页拿不到 id，只能按标题配，必须全局一对一配对，
    # 否则标题被平台改写、或者晚一天发的那一批会全部落到「未匹配」。
    if platform == "douyin":
        pairs = []
        leftovers = []
        for it in items:
            row = match_row(rows, platform, it["date"], it["title"], it.get("aweme_id", ""))
            if row is None:
                leftovers.append(it)
            else:
                pairs.append((row, it))
    else:
        pairs, leftovers = pair_items_to_rows(rows, platform, items)

    for it in leftovers:
        print(f"  ? 未匹配到仓库记录：{it['date']} {it['title'][:30]}", file=sys.stderr)
        skipped += 1

    for row, it in pairs:
        if it.get("blocked"):
            # 平台不给数据 → 保留最后读数并打 limited 标记，不清零
            diffs, why = mark_limited(
                row, platform, it.get("reason", "平台不给数据"), dry_run=dry_run
            )
            if why:
                print(f"  ! 跳过 {it['date']} {it['title'][:20]}：{why}", file=sys.stderr)
                skipped += 1
                continue
            matched += 1
            if diffs:
                log.append(f"{it['date']} {row['topic'][:24]}: " + ", ".join(diffs))
            continue
        diffs, why = apply_values(row, platform, it["raw"], dry_run=dry_run)
        if why:
            print(f"  ! 跳过 {it['date']} {it['title'][:20]}：{why}", file=sys.stderr)
            skipped += 1
            continue
        matched += 1
        # 这次读到真数了，如果之前标过 limited 就摘掉
        cleared = clear_limited(row, platform, dry_run=dry_run)
        diffs = cleared + diffs
        if diffs:
            log.append(f"{it['date']} {row['topic'][:24]}: " + ", ".join(diffs))

    print(f"\n{platform}：匹配 {matched} 条，跳过 {skipped} 条", file=sys.stderr)
    return log


# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="刷新 data/videos.jsonl 的平台指标")
    ap.add_argument(
        "--platform",
        required=True,
        choices=["bilibili", "douyin", "xiaohongshu", "wechat_channels"],
    )
    ap.add_argument("--in", dest="inputs", nargs="+", help="observe 出来的页面文本（B 站不需要）")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不写盘")
    ap.add_argument("--delay", type=float, default=0.45, help="B 站请求间隔秒数")
    args = ap.parse_args()

    rows = load_rows()
    print(f"读入 {len(rows)} 期", file=sys.stderr)

    if args.platform == "bilibili":
        log = refresh_bilibili(rows, delay=args.delay, dry_run=args.dry_run)
    else:
        if not args.inputs:
            ap.error(f"{args.platform} 需要 --in 指定页面文本文件")
        log = refresh_from_pages(rows, args.platform, args.inputs, dry_run=args.dry_run)

    if log:
        print(f"\n=== {args.platform} 有变化的记录（{len(log)} 条）===")
        for line in log:
            print("  " + line)
    else:
        print(f"\n{args.platform}：没有变化")

    if args.dry_run:
        print("\n（--dry-run，未写盘）")
        return 0

    for r in rows:
        recompute_summary(r)
    save_rows(rows)
    print(f"\n已写回 {DATA_FILE}")
    print("接着跑：node scripts/check-data.mjs && node scripts/build-site.mjs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
