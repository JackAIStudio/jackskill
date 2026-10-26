#!/usr/bin/env python3
"""
refresh-stats.py 的解析与写入规则测试。

这里测的是「不依赖网络、不依赖浏览器」的那部分：页面文本 → 五元组，
以及拿到五元组之后怎么决定写不写。这部分是最容易静默出错的地方——
列序错了不会报错，只会把点赞写成评论，然后一直错下去。

跑法：
    python3 tests/test-refresh-stats.py
    ./tests/run.sh 09          # 也可以挂进统一入口
"""
from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("refresh_stats", REPO_ROOT / "scripts/refresh-stats.py")
rs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rs)

failures: list[str] = []
checks = 0


def check(cond: bool, label: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(label)


# ---------------------------------------------------------------------------
# 列序：这是整套东西的地基，写错不会报错，只会一直错
# ---------------------------------------------------------------------------

def test_column_order() -> None:
    check(rs.PLATFORM_SPEC["douyin"] == ["views", "likes", "comments", "shares", "collects"],
          "抖音列序应为 播放 点赞 评论 分享 收藏")
    check(rs.PLATFORM_SPEC["xiaohongshu"] == ["views", "comments", "likes", "collects", "shares"],
          "小红书列序应为 观看 评论 点赞 收藏 分享（收藏在分享前）")
    check(rs.PLATFORM_SPEC["wechat_channels"] == ["views", "likes", "comments", "shares", "collects"],
          "视频号列序应为 播放 点赞 评论 分享 收藏")


# ---------------------------------------------------------------------------
# 小红书：裸数字，最依赖列序
# ---------------------------------------------------------------------------

XHS_PAGE = '''
  StaticText "置顶"
  StaticText "我能为你提供价值，请你雇佣我为你工作"
  StaticText "2026-10-18 13:06"
  StaticText "38"
  StaticText "0"
  StaticText "1"
  StaticText "0"
  StaticText "0"
  img
  StaticText "在达芬奇中剪辑长视频的思路和方法"
  StaticText "2026-10-22 17:39"
  StaticText "355"
  StaticText "0"
  StaticText "23"
  StaticText "20"
  StaticText "1"
'''


def test_xhs_parse() -> None:
    items = rs.parse_xhs(XHS_PAGE)
    check(len(items) == 2, f"小红书应解析出 2 条，实际 {len(items)}")
    by_date = {it["date"]: it for it in items}
    it = by_date.get("2026-10-22")
    check(it is not None, "小红书应解析出 2026-10-22 那条")
    if it:
        # 355 观看 / 0 评论 / 23 点赞 / 20 收藏 / 1 分享
        check(it["raw"] == ["355", "0", "23", "20", "1"], f"小红书数字顺序不对：{it['raw']}")
        check("达芬奇" in it["title"], f"小红书标题取错：{it['title']!r}")


# ---------------------------------------------------------------------------
# 视频号：日期格式带「年月日」，中间夹「已声明原创」
# ---------------------------------------------------------------------------

WX_PAGE = '''
  StaticText "在达芬奇中剪辑长视频的思路和方法 #达芬奇剪辑"
  StaticText "2026年10月22日 17:39"
  StaticText "已声明原创"
  StaticText "397"
  StaticText "0"
  StaticText "1"
  StaticText "3"
  StaticText "6"
  StaticText "实测用AI开发安卓APP会比苹果更方便一些 #吴杰克"
  StaticText "2026年10月18日 18:25"
  StaticText "已声明原创"
  StaticText "856"
  StaticText "1"
  StaticText "0"
  StaticText "2"
  StaticText "6"
'''


def test_wx_parse() -> None:
    items = rs.parse_wx(WX_PAGE)
    check(len(items) == 2, f"视频号应解析出 2 条，实际 {len(items)}")
    by_date = {it["date"]: it for it in items}
    it = by_date.get("2026-10-22")
    check(it is not None, "视频号应解析出 2026-10-22 那条")
    if it:
        check(it["raw"] == ["397", "0", "1", "3", "6"], f"视频号数字顺序不对：{it['raw']}")


# ---------------------------------------------------------------------------
# 抖音：标签 + 数值成对，还有近似值和「减少作品推荐」
# ---------------------------------------------------------------------------

DY_PAGE = '''
    StaticText "在达芬奇中剪辑长视频的思路和方法 #达芬奇剪辑"
    StaticText "2026年10月22日 17:40"
    StaticText "已发布"
    @e55 button "播放"
    @e56 button "718"
    @e57 button "点赞"
    @e58 button "6"
    @e59 button "评论"
    @e60 button "0"
    @e61 button "分享"
    @e62 button "0"
    @e63 button "收藏"
    @e64 button "5"
    StaticText "实测用AI开发安卓APP会比苹果更方便一些 #吴杰克"
    StaticText "2026年10月18日 18:25"
    StaticText "已发布"
    @e126 button "播放"
    @e127 button "1.3万"
    @e128 button "点赞"
    @e129 button "75"
    @e130 button "评论"
    @e131 button "36"
    @e132 button "分享"
    @e133 button "4"
    @e134 button "收藏"
    @e135 button "23"
'''

DY_BLOCKED = '''
    StaticText "DeepSeek送了我100多赠金，看看你有没有 #吴杰克"
    StaticText "2026年10月15日 17:01"
    StaticText "减少作品推荐"
    StaticText "播放"
    StaticText "-"
    StaticText "点赞"
    StaticText "-"
    StaticText "评论"
    StaticText "-"
    StaticText "分享"
    StaticText "-"
    StaticText "收藏"
    StaticText "-"
'''


def test_dy_parse() -> None:
    items = rs.parse_dy(DY_PAGE)
    check(len(items) == 2, f"抖音应解析出 2 条，实际 {len(items)}")
    by_date = {it["date"]: it for it in items}
    it = by_date.get("2026-10-22")
    check(it is not None, "抖音应解析出 2026-10-22 那条")
    if it:
        check(it["raw"] == ["718", "6", "0", "0", "5"], f"抖音数字顺序不对：{it['raw']}")
        check("达芬奇" in it["title"], f"抖音标题取错：{it['title']!r}")
    it2 = by_date.get("2026-10-18")
    check(it2 is not None and it2["raw"][0] == "1.3万", "抖音应保留「1.3万」原样交给上层判断")

    blocked = rs.parse_dy(DY_BLOCKED)
    check(len(blocked) == 1, "「减少作品推荐」的作品应仍被识别出来，只是没有数字")
    check(blocked and blocked[0].get("blocked") is True, "被限流的作品应带 blocked 标记")
    check(blocked and blocked[0]["raw"] is None, "被限流的作品不应有数字")


# ---------------------------------------------------------------------------
# 近似值：抖音上万是四舍五入，不能拿它盖掉更精确的旧值
# ---------------------------------------------------------------------------

def test_parse_count() -> None:
    check(rs.parse_count("718") == (718, False), "718 应是精确值")
    check(rs.parse_count("1.3万") == (13000, True), "1.3万 应是近似值 13000")
    check(rs.parse_count("1.1万") == (11000, True), "1.1万 应是近似值 11000")
    check(rs.parse_count("-") is None, "- 不应解析成数字")
    check(rs.parse_count("0%") is None, "百分比不应解析成数字")


def _row(**over):
    r = {
        "id": "t",
        "date": "2026-10-18",
        "topic": "测试",
        "platforms": {
            "douyin": {"title": "t", "url": "u", "views": 1000, "likes": 75, "collects": 23,
                       "shares": 4, "comments": 36}
        },
    }
    r["platforms"]["douyin"].update(over)
    return r


def test_apply_values() -> None:
    # 旧值落在「1.3万」的区间里 → 旧值更精确，不动
    r = _row(views=12584)
    diffs, why = rs.apply_values(r, "douyin", ["1.3万", "75", "36", "4", "23"], dry_run=False)
    check(why is None and diffs == [] and r["platforms"]["douyin"]["views"] == 12584,
          "旧值 12584 在 [12500,13500) 内，不应被「1.3万」覆盖")

    # 旧值明显小于区间 → 覆盖
    r = _row(views=11000)
    diffs, why = rs.apply_values(r, "douyin", ["1.3万", "75", "36", "4", "23"], dry_run=False)
    check(why is None and r["platforms"]["douyin"]["views"] == 13000,
          "旧值 11000 明显落后，应被「1.3万」更新")

    # 旧值比近似值大 → 同一期在涨，别用粗值盖掉
    r = _row(views=14000)
    diffs, why = rs.apply_values(r, "douyin", ["1.3万", "75", "36", "4", "23"], dry_run=False)
    check(r["platforms"]["douyin"]["views"] == 14000, "旧值 14000 比近似值大，不应被降精度")

    # 点赞小幅回落是正常的
    r = _row(likes=3)
    diffs, why = rs.apply_values(r, "douyin", ["1000", "2", "36", "4", "23"], dry_run=False)
    check(why is None and r["platforms"]["douyin"]["likes"] == 2, "点赞 3→2 应正常写入")

    # 播放量暴跌要拦住
    r = _row(views=1000)
    diffs, why = rs.apply_values(r, "douyin", ["700", "75", "36", "4", "23"], dry_run=False)
    check(why is not None and r["platforms"]["douyin"]["views"] == 1000,
          "播放量跌超 20% 应拦下且不写入")


# ---------------------------------------------------------------------------
# 匹配：一天发两条时不能串行
# ---------------------------------------------------------------------------

def test_match_row() -> None:
    rows = [
        {"date": "2026-10-22", "topic": "在达芬奇中剪辑长视频的思路和方法", "platforms": {}},
        {"date": "2026-10-22", "topic": "创业失败送外卖还债，雨天摔了一跤，餐撒了", "platforms": {}},
        {"date": "2026-10-18", "topic": "实测用AI开发安卓APP会比苹果更方便一些", "platforms": {}},
    ]
    hit = rs.match_row(rows, "douyin", "2026-10-22", "在达芬奇中剪辑长视频的思路和方法 #达芬奇剪辑")
    check(hit is not None and "达芬奇" in hit["topic"], "同一天两条时，应匹配到标题正确的那条")

    hit = rs.match_row(rows, "douyin", "2026-10-22", "创业失败送外卖还债，雨天摔了一跤，餐撒了")
    check(hit is not None and "创业失败" in hit["topic"], "应匹配到创业失败那条")

    hit = rs.match_row(rows, "douyin", "2026-10-24", "用一个skill完成产品宣传片的制作")
    check(hit is None, "库里没有的日期应返回 None，不能硬塞给别的期")

    # 只有一期时，标题差异再大也认它（各平台标题会被改短）
    hit = rs.match_row(rows, "douyin", "2026-10-18", "完全不一样的标题")
    check(hit is not None and hit["date"] == "2026-10-18", "当天只有一期时，应认下这一期")


# ---------------------------------------------------------------------------
# 拿不到数据 → 清零，不保留旧快照
# ---------------------------------------------------------------------------

def test_mark_limited() -> None:
    # 平台显示 "-"：保留最后读数，打 limited 标记，不清零
    r = _row(views=164, likes=0, collects=1, shares=0, comments=0)
    diffs, why = rs.mark_limited(r, "douyin", "减少作品推荐", dry_run=False)
    d = r["platforms"]["douyin"]
    check(why is None, f"打标记不应报错：{why}")
    check(d["views"] == 164, "限流时不能清零——164 是限流前真实跑过的量")
    check(d.get("limited", {}).get("reason") == "减少作品推荐", "应记下限流原因")
    check(bool(d.get("limited", {}).get("lastRead")), "应记下最后读数日期")
    check(len(diffs) == 1, f"首次打标记应产生一条变更，实际 {diffs}")

    # 重复跑不应重复报
    diffs2, _ = rs.mark_limited(r, "douyin", "减少作品推荐", dry_run=False)
    check(diffs2 == [], "同样的标记重复打不应产生变更")

    # dry-run 不能真写
    r3 = _row(views=164)
    rs.mark_limited(r3, "douyin", "减少作品推荐", dry_run=True)
    check("limited" not in r3["platforms"]["douyin"], "dry-run 不应写入")

    # 平台重新给数了，标记要摘掉
    r4 = _row(views=164)
    r4["platforms"]["douyin"]["limited"] = {"reason": "减少作品推荐", "lastRead": "2026-10-19"}
    cleared = rs.clear_limited(r4, "douyin", dry_run=False)
    check(cleared, "解除标记应产生变更记录")
    check("limited" not in r4["platforms"]["douyin"], "平台重新给数后应摘掉 limited")


def test_zero_stays_zero() -> None:
    # 平台明确返回 0（不是 "-"）：就是 0，不加任何标记
    r = _row(views=0, likes=0, collects=0, shares=0, comments=0)
    diffs, why = rs.apply_values(r, "douyin", ["0", "0", "0", "0", "0"], dry_run=False)
    check(why is None and diffs == [], "全 0 且与库内一致时不应产生变更")
    check("limited" not in r["platforms"]["douyin"], "平台返回 0 不应加 limited 标记")


# ---------------------------------------------------------------------------
# 抖音走 work_list 的 statistics：精确值，且能认出「平台不给看」
# ---------------------------------------------------------------------------

# 抖音的 JSON 在不同环节会被存成不同形态，解析器必须都认：
#   转义（列表页 StaticText）／未转义（spill 文件、<pre> 内层）；
#   紧凑（`"a":1`）／带空格（`"a": 1`）。
# 以前只认「转义 + 紧凑」，照文档拿 spill 文件来解析会得到 0 条。
# 下面两份 fixture 内容相同，只是序列化形态不同，用来钉住这个容错。
DY_JSON = (
    r'\"desc\":\"用Codex来获取、整理和分析浏览器网页数据\",'
    r'\"duration\":172100,'
    r'\"create_time\":1785148780,'
    r'\"statistics\":{\"aweme_id\":\"7667155598017957160\",\"collect_count\":18,'
    r'\"comment_count\":2,\"digg_count\":33,\"forward_count\":0,'
    r'\"live_watch_count\":0,\"play_count\":2124,\"share_count\":1},'
    r'\"status\":{\"allow_comment\":true,\"is_delete\":false,\"is_private\":false,'
    r'\"is_prohibited\":false,\"self_see\":false,\"with_goods\":false},'
    r'\"desc\":\"解决CodeX每次会话都要经过5次reconnecting\",'
    r'\"duration\":79400,'
    r'\"create_time\":1784700000,'
    r'\"statistics\":{\"aweme_id\":\"7663119071394712872\",\"collect_count\":0,'
    r'\"comment_count\":0,\"digg_count\":0,\"play_count\":0,\"share_count\":0},'
    r'\"status\":{\"is_delete\":false,\"is_private\":false,'
    r'\"is_prohibited\":false,\"self_see\":true}'
)

# 同一份内容，未转义 + 带空格（`json.dumps` 的默认输出形态）。
DY_JSON_PLAIN = (
    '{"desc":"用Codex来获取、整理和分析浏览器网页数据",'
    '"duration":172100,'
    '"create_time":1785148780,'
    '"statistics":{"aweme_id":"7667155598017957160","collect_count":18,'
    '"comment_count":2,"digg_count":33,"forward_count":0,'
    '"live_watch_count":0,"play_count":2124,"share_count":1},'
    '"status":{"allow_comment":true,"is_delete":false,"is_private":false,'
    '"is_prohibited":false,"self_see":false,"with_goods":false}}'
)

# 章节 desc 紧挨在 statistics 前面：标题不能读成「结语」。
DY_JSON_WITH_CHAPTERS = (
    '{"desc":"真实标题 #话题","duration":158467,"create_time":1793007816,'
    '"recommend_chapter_info":{"recommend_chapter_list":['
    '{"desc":"引言","detail":"","timestamp":1500},'
    '{"desc":"结语","detail":"","timestamp":133000}]},'
    '"statistics":{"aweme_id":"7700909905561144626","collect_count":0,'
    '"comment_count":0,"digg_count":0,"play_count":15,"share_count":0},'
    '"status":{"is_delete":false,"self_see":false}}'
)


def test_dy_json_parse() -> None:
    items = rs.parse_dy_json(DY_JSON)
    check(len(items) == 2, f"statistics 应解析出 2 条，实际 {len(items)}")

    normal = next((i for i in items if i.get("aweme_id") == "7667155598017957160"), None)
    check(normal is not None, "应解析出正常那条")
    if normal:
        check(normal.get("blocked") is not True, "self_see=false 的不该被标 blocked")
        # 顺序必须是 播放 点赞 评论 分享 收藏
        check(normal["raw"] == ["2124", "33", "2", "1", "18"],
              f"statistics 取值或顺序不对：{normal['raw']}")
        check(normal.get("title") == "用Codex来获取、整理和分析浏览器网页数据",
              f"标题不对：{normal.get('title')!r}")

    hidden = next((i for i in items if i.get("aweme_id") == "7663119071394712872"), None)
    check(hidden is not None, "应解析出仅自己可见那条")
    if hidden:
        check(hidden.get("blocked") is True, "self_see=true 应标 blocked（平台不给数）")
        check(hidden.get("raw") is None, "仅自己可见不应给数字")
        check(hidden.get("reason") == "仅自己可见", f"原因不对：{hidden.get('reason')!r}")

    # 空输入不能崩，也不能瞎编
    check(rs.parse_dy_json("") == [], "空文本应解析出 0 条")
    check(rs.parse_dy_json("StaticText \"播放\"") == [], "列表页文本应解析出 0 条（交给 parse_dy）")


def test_dy_json_serialization_tolerance() -> None:
    """未转义 / 带空格 / <pre> 包裹的形态都要认。

    照 SKILL.md 的指引拿 spill 文件（未转义）来解析，以前会静默得到 0 条，
    操作者只能手工再转义一遍。四种形态必须解出同样的结果。
    """
    plain = rs.parse_dy_json(DY_JSON_PLAIN)
    check(len(plain) == 1, f"未转义形态应解析出 1 条，实际 {len(plain)}")
    if plain:
        check(plain[0]["aweme_id"] == "7667155598017957160", "未转义形态的作品 id 不对")
        check(plain[0]["raw"] == ["2124", "33", "2", "1", "18"],
              f"未转义形态的取值不对：{plain[0]['raw']}")
        check(plain[0]["date"] == "2026-07-27",
              f"未转义形态的日期不对：{plain[0]['date']!r}")

    # <pre> 包裹（spill 文件 / 接口页面）也要认
    wrapped = "<html><body><pre>" + DY_JSON_PLAIN + "</pre></body></html>"
    check(len(rs.parse_dy_json(wrapped)) == 1, "包在 <pre> 里的应照样解析")

    # 带空格 + 转义
    spaced = DY_JSON.replace('":"', '": "').replace('",\\"', '", \\"')
    check(len(rs.parse_dy_json(spaced)) == 2, "带空格又转义的形态也要认")


def test_dy_title_not_from_chapters() -> None:
    """标题要取 item 自己的 desc，不能取 statistics 前最近的 desc。

    `recommend_chapter_info.recommend_chapter_list` 里每个章节都有一个 desc
    （引言 / 结语 / 取餐与送餐…），它就排在 statistics 前面。按「最近的
    desc」会把这期的标题读成「结语」，然后拿它去匹配仓库记录必然对不上。
    """
    items = rs.parse_dy_json(DY_JSON_WITH_CHAPTERS)
    check(len(items) == 1, f"应解析出 1 条，实际 {len(items)}")
    if items:
        check(items[0]["title"] == "真实标题 #话题",
              f"标题被章节 desc 抢走了：{items[0]['title']!r}")
        check(items[0]["raw"] == ["15", "0", "0", "0", "0"],
              f"取值不对：{items[0]['raw']}")


def test_dy_date_not_from_neighbour_item() -> None:
    """日期不能取到隔壁 item 的 create_time。

    真实数据里踩过：某条窗口尾部混进了另一条作品（desc 为空）的碎片，
    那个 create_time 排在后面，按「窗口里最后一个」取就把 2026-03-02
    读成了 2026-06-22，于是整条对不上仓库、被报成「未匹配」。

    这里拼两条 item：第一条（20260401）在前，第二条（20260101）的窗口里
    塞了一个属于第三条的靠后时间戳。第二条的日期必须仍是 2026-01-01。
    """
    item_a = (
        '{"desc":"第一条作品","duration":100,"create_time":1775000000,'
        '"statistics":{"aweme_id":"1000000000000000001","play_count":10,'
        '"digg_count":0,"comment_count":0,"share_count":0,"collect_count":0},'
        '"status":{"is_delete":false,"self_see":false}}'
    )
    # 第二条：desc 前面有自己的 create_time；desc 之后又混了一个更晚的
    item_b = (
        '{"desc":"第二条作品","duration":200,"create_time":1767000000,'
        '"recommend_chapter_info":{"recommend_chapter_list":['
        '{"desc":"结语","detail":"","timestamp":1000}]},'
        '"statistics":{"aweme_id":"1000000000000000002","play_count":20,'
        '"digg_count":1,"comment_count":0,"share_count":0,"collect_count":0},'
        '"status":{"is_delete":false,"self_see":false}},'
        '{"desc":"","create_time":1782000000,"deleted_index":[]}'
    )
    items = rs.parse_dy_json("[" + item_a + "," + item_b + "]")
    check(len(items) == 2, f"应解析出 2 条，实际 {len(items)}")
    by_id = {i["aweme_id"]: i for i in items}
    a = by_id.get("1000000000000000001")
    b = by_id.get("1000000000000000002")
    if a:
        check(a["date"] == "2026-04-01", f"第一条日期被带偏：{a['date']!r}")
        check(a["title"] == "第一条作品", f"第一条标题不对：{a['title']!r}")
    if b:
        check(b["date"] == "2025-12-29", f"第二条日期被隔壁 item 顶掉了：{b['date']!r}")
        check(b["title"] == "第二条作品", f"第二条标题不对：{b['title']!r}")
        check(b["raw"] == ["20", "1", "0", "0", "0"], f"第二条取值不对：{b['raw']}")



def test_match_by_work_id() -> None:
    rows = [
        {"id": "a", "date": "2026-09-10", "topic": "WorkBuddy 接入 GPT",
         "platforms": {"douyin": {"url": "https://www.douyin.com/video/7683968316486028559"}}},
        {"id": "b", "date": "2026-09-10", "topic": "把 Agent 接入达芬奇",
         "platforms": {"douyin": {"url": "https://www.douyin.com/video/7683611440728542490"}}},
    ]
    # 同一天两条，标题还都对不上时，id 是唯一可靠的判据
    hit = rs.match_row(rows, "douyin", "2026-09-10", "完全不一样的标题",
                       work_id="7683611440728542490")
    check(hit is not None and hit["id"] == "b", "应优先按作品 id 匹配")
    # 给了 id 但库里没有：不能退化成猜日期
    miss = rs.match_row(rows, "douyin", "2026-09-10", "WorkBuddy 接入 GPT",
                        work_id="9999999999999999999")
    check(miss is None, "id 对不上时不该退回标题匹配（那会张冠李戴）")
    # 不给 id 时，老路照常工作
    by_title = rs.match_row(rows, "douyin", "2026-09-10", "WorkBuddy 接入 GPT")
    check(by_title is not None and by_title["id"] == "a", "没有 id 时应退回标题匹配")


# ---------------------------------------------------------------------------
# 全局一对一配对：平台日期差一天、标题被改写时也要配上
# ---------------------------------------------------------------------------

def test_pair_items_to_rows() -> None:
    rows = [
        {"id": "2017-09-09_把Agent接入达芬奇", "date": "2026-09-09",
         "topic": "把 Agent 接入达芬奇|用一个skill实现自动剪辑",
         "platforms": {"xiaohongshu": {"views": 1}}},
        {"id": "2017-09-10_WorkBuddy", "date": "2026-09-10",
         "topic": "WorkBuddy 接入 GPT、Gemini、Grok",
         "platforms": {"xiaohongshu": {"views": 1}}},
        {"id": "2017-08-29_避免宕机", "date": "2026-08-29",
         "topic": "如何避免dsh宕机？让AI工作台稳定运行的方法",
         "platforms": {"xiaohongshu": {"views": 1}}},
        {"id": "2017-08-30_掌上Agent", "date": "2026-08-30",
         "topic": "掌上Agent|自制dsh远程控制插件（已开源）",
         "platforms": {"xiaohongshu": {"views": 1}}},
    ]
    items = [
        # 日期差一天、标题被改写，只看当天会漏
        {"title": "把Agent接入达芬奇,用skill实现自动剪辑", "date": "2026-09-10", "raw": ["1"]},
        {"title": "如何避免dsh宕机？AI工作台稳定运行的诀窍", "date": "2026-08-30", "raw": ["1"]},
        # 标题完全不同：宁可报未匹配，也不能硬塞给同一天的另一条
        {"title": "完全不存在的主题", "date": "2026-09-10", "raw": ["1"]},
    ]
    pairs, unmatched = rs.pair_items_to_rows(rows, "xiaohongshu", items)
    got = {r["id"] for r, _ in pairs}
    check("2017-09-09_把Agent接入达芬奇" in got, "差一天 + 标题改写时应配上正确的记录")
    check("2017-08-29_避免宕机" in got, "差一天的「dsh宕机」应配对到 08-29 那期")
    check("2017-09-10_WorkBuddy" not in got, "标题不同不能张冠李戴")
    check(len(unmatched) == 1, f"配不上的应如实留在未匹配里，实际 {len(unmatched)}")

    # 一条作品只能配一条记录：同标题的两条不会被同一条作品重复占用
    dup_rows = [
        {"id": "d1", "date": "2026-04-12", "topic": "用达芬奇5秒钟剪完一个片子是种什么体验？",
         "platforms": {"xiaohongshu": {"views": 1}}},
        {"id": "d2", "date": "2026-04-13", "topic": "用达芬奇5秒钟剪完一个片子是种什么体验？",
         "platforms": {"xiaohongshu": {"views": 1}}},
    ]
    dup_items = [{"title": "用达芬奇5秒钟剪完一个片子是种什么体验？", "date": "2026-04-12", "raw": ["1"]}]
    pairs2, _ = rs.pair_items_to_rows(dup_rows, "xiaohongshu", dup_items)
    check(len(pairs2) == 1 and pairs2[0][0]["id"] == "d1", "一条作品只配一条记录，且优先当天")

    # 日期太远的根本不参与打分
    far_rows = [{"id": "f1", "date": "2026-01-01", "topic": "同一个标题",
                 "platforms": {"xiaohongshu": {"views": 1}}}]
    pairs3, unmatched3 = rs.pair_items_to_rows(
        far_rows, "xiaohongshu",
        [{"title": "同一个标题", "date": "2026-09-01", "raw": ["1"]}],
    )
    check(not pairs3 and len(unmatched3) == 1, "差 40 天以上的不配对")


# ---------------------------------------------------------------------------
# 视频号：标题里带「年」不能被当成日期行丢掉
# ---------------------------------------------------------------------------

def test_wx_title_with_year() -> None:
    raw = (
        'StaticText "都2026年了，还在用传统方式剪口播？"\n'
        'StaticText "2026年04月19日 23:23"\n'
        'StaticText "已声明原创"\n'
        'StaticText "作者修改过视频信息"\n'
        'StaticText "1395"\n'
        'StaticText "10"\n'
        'StaticText "5"\n'
        'StaticText "18"\n'
        'StaticText "22"\n'
    )
    got = rs.parse_wx(raw)
    check(len(got) == 1, f"标题含「年」的视频号作品应能解析出来，实际 {len(got)} 条")
    if got:
        check(got[0]["title"].startswith("都2026年了"), "标题应完整保留，不能被吞掉")
        check(got[0]["raw"] == ["1395", "10", "5", "18", "22"], "五个数字应按列序读全")


def main() -> int:
    for fn in [
        test_column_order,
        test_xhs_parse,
        test_wx_parse,
        test_dy_parse,
        test_dy_json_parse,
        test_dy_json_serialization_tolerance,
        test_dy_title_not_from_chapters,
        test_dy_date_not_from_neighbour_item,
        test_parse_count,
        test_apply_values,
        test_match_row,
        test_match_by_work_id,
        test_pair_items_to_rows,
        test_wx_title_with_year,
        test_mark_limited,
        test_zero_stays_zero,
    ]:
        fn()

    if failures:
        print(f"FAIL: {len(failures)}/{checks} 项未通过")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS: {checks} 项检查全部通过（列序、四平台解析、近似值、id 匹配、全局一对一配对）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
