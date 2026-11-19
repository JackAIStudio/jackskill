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


# ---------------------------------------------------------------------------
# bsk saveFull 外壳与 VOM StaticText 折行：直接喂给脚本不能得到 0 条
# ---------------------------------------------------------------------------

def test_savefull_and_vom_fold() -> None:
    import json

    xhs_savefull = json.dumps({"observation": {"text": XHS_PAGE}}, ensure_ascii=False)
    check(len(rs.parse_xhs(xhs_savefull)) == 2, "小红书解析应直接认 bsk saveFull JSON 外壳")

    wx_savefull = json.dumps({"observation": {"text": WX_PAGE}}, ensure_ascii=False)
    check(len(rs.parse_wx(wx_savefull)) == 2, "视频号解析应直接认 bsk saveFull JSON 外壳")

    # VOM 会先写一行截断的 RootWebArea，再把 JSON 折成多行 StaticText，
    # 折行点甚至可能正好切进 desc 或 statistics 内部。
    folded_vom = (
        '@vom 1\n'
        'L1 page\n'
        '  RootWebArea "{\\"aweme_list\\":[{\\"desc\\":\\"被截断的预"\n'
        '    StaticText "{\\"aweme_list\\":[{\\"create_time\\":1794736179,\\"desc\\":\\"谷歌模型"\n'
        '    StaticText "做的不错但harness做得是一坨\\",\\"duration\\":37500,\\"stat"\n'
        '    StaticText "istics\\":{\\"aweme_id\\":\\"7708333154834091300\\",\\"collect_count\\":1,\\"comment_count\\":4,\\"digg_count\\":8,\\"play_count\\":555,\\"share_count\\":0},\\"status\\":{\\"is_delete\\":false,\\"self_see\\":false}}],\\"total\\":145}"\n'
        '    form "美观输出"\n'
    )
    dy_savefull = json.dumps({"observation": {"text": folded_vom}}, ensure_ascii=False)
    items = rs.parse_dy_json(dy_savefull)
    check(len(items) == 1, f"折在 statistics 里的 bsk saveFull 也应解析出 1 条，实际 {len(items)}")
    if items:
        check(items[0]["aweme_id"] == "7708333154834091300", "折行后 aweme_id 应完整")
        check(items[0]["title"] == "谷歌模型做的不错但harness做得是一坨", f"折在 desc 中间应还原完整标题：{items[0]['title']!r}")
        check(items[0]["raw"] == ["555", "8", "4", "0", "1"], f"折在 statistics 中间应还原五元组：{items[0]['raw']}")
    check(rs.extract_dy_total(dy_savefull) == 145, "应能从 saveFull 里读出 total=145")


def test_suspected_new_unmatched() -> None:
    rows = [{"date": "2026-11-14", "topic": "旧视频", "platforms": {}}]
    leftovers = [
        {"date": "2026-11-15", "title": "刚发的新视频", "aweme_id": "123"},
        {"date": "2026-11-14", "title": "昨晚发的另一期"},
        {"date": "2026-07-25", "title": "删除"},
        {"date": "2026-03-02", "title": "很久以前未收录的私密稿"},
    ]
    got = rs.find_suspected_new_unmatched(rows, leftovers)
    titles = [x["title"] for x in got]
    check(titles == ["刚发的新视频", "昨晚发的另一期"], f"疑似漏收录筛得不对：{titles}")


def test_rolling_scope_days_and_limit() -> None:
    import datetime
    import tempfile

    check(rs.resolve_since_date(14, today=datetime.date(2026, 11, 17)) == "2026-11-03",
          "--days 14 应计算 14 天前的起始日期")
    check(rs.resolve_since_date(None) is None, "未传 --days 时返回 None")

    rows = [
        {"id": "2026-11-16_新1", "date": "2026-11-16", "topic": "新片一",
         "platforms": {"bilibili": {"url": "https://www.bilibili.com/video/BV1111111111/", "views": 1},
                       "xiaohongshu": {"views": 10, "likes": 0, "collects": 0, "shares": 0, "comments": 0}}},
        {"id": "2026-11-10_近2", "date": "2026-11-10", "topic": "近期二",
         "platforms": {"bilibili": {"url": "https://www.bilibili.com/video/BV2222222222/", "views": 1},
                       "xiaohongshu": {"views": 20, "likes": 0, "collects": 0, "shares": 0, "comments": 0}}},
        {"id": "2026-10-01_置顶老3", "date": "2026-10-01", "topic": "置顶老视频",
         "platforms": {"bilibili": {"url": "https://www.bilibili.com/video/BV3333333333/", "views": 1},
                       "xiaohongshu": {"views": 30, "likes": 0, "collects": 0, "shares": 0, "comments": 0}}},
    ]

    targets_days, total_bili = rs.select_bili_targets(rows, since_date="2026-11-03")
    check(total_bili == 3, f"库内 B 站总数应为 3，实际 {total_bili}")
    check([t[2] for t in targets_days] == ["BV1111111111", "BV2222222222"],
          "--days 过滤后应只选近期 2 期 B 站视频")

    targets_lim, _ = rs.select_bili_targets(rows, limit=1)
    check([t[2] for t in targets_lim] == ["BV1111111111"],
          "--limit 1 应只选最新 1 期 B 站视频")

    xhs_dump = '''
      StaticText "置顶"
      StaticText "置顶老视频"
      StaticText "2026-10-01 10:00"
      StaticText "999"
      StaticText "0"
      StaticText "0"
      StaticText "0"
      StaticText "0"
      StaticText "新片一"
      StaticText "2026-11-16 11:00"
      StaticText "111"
      StaticText "0"
      StaticText "0"
      StaticText "0"
      StaticText "0"
      StaticText "近期二"
      StaticText "2026-11-10 11:00"
      StaticText "222"
      StaticText "0"
      StaticText "0"
      StaticText "0"
      StaticText "0"
    '''
    with tempfile.NamedTemporaryFile("w", suffix=".txt", encoding="utf-8", delete=True) as tf:
        tf.write(xhs_dump)
        tf.flush()
        rows_copy = copy.deepcopy(rows)
        log = rs.refresh_from_pages(rows_copy, "xiaohongshu", [tf.name], dry_run=False, since_date="2026-11-03")
        check(len(log) == 2, f"滚动范围内应更新 2 条，实际 {len(log)}：{log}")
        check(rows_copy[0]["platforms"]["xiaohongshu"]["views"] == 111, "新片一应更新为 111")
        check(rows_copy[1]["platforms"]["xiaohongshu"]["views"] == 222, "近期二应更新为 222")
        check(rows_copy[2]["platforms"]["xiaohongshu"]["views"] == 30, "置顶老视频超出滚动范围，应保持原值 30")

        rows_lim = copy.deepcopy(rows)
        log_lim = rs.refresh_from_pages(rows_lim, "xiaohongshu", [tf.name], dry_run=False, limit=1)
        check(len(log_lim) == 1 and rows_lim[0]["platforms"]["xiaohongshu"]["views"] == 111,
              "--limit 1 应只更新最新 1 条")
        check(rows_lim[1]["platforms"]["xiaohongshu"]["views"] == 20, "--limit 1 不应改动第二条")


def test_plain_text_and_ego_snapshot() -> None:
    """除 bsk VOM 外，也要直接认 Ego Lite snapshot 与纯文本（document.body.innerText）。"""
    # 1) 小红书纯文本（含视频时长行，不能把时长当成标题）
    xhs_plain = (
        "全部 322\n"
        "01:36\n"
        "Gemini 4 Neon 和 Gpt-6.2 Astra谁更能打？\n"
        "2026-11-19 20:12\n"
        "1\n0\n0\n0\n0\n"
        "00:56\n"
        "让 Gemini 4 Neon 给自己做一个宣传片\n"
        "2026-11-19 10:04\n"
        "320\n4\n15\n2\n4\n"
    )
    xhs_items = rs.parse_xhs(xhs_plain)
    check(len(xhs_items) == 2, f"小红书纯文本应解析出 2 条，实际 {len(xhs_items)}")
    if len(xhs_items) == 2:
        check(xhs_items[0]["title"].startswith("Gemini 4 Neon"), f"小红书纯文本标题不对：{xhs_items[0]['title']!r}")
        check(xhs_items[1]["raw"] == ["320", "4", "15", "2", "4"], f"小红书纯文本数字不对：{xhs_items[1]['raw']}")

    # 2) 小红书 Ego Lite snapshot
    xhs_ego = (
        '[p1 "小红书创作服务平台" | space "jackskill"(1): 1 managed]\n'
        'root\n'
        '  container\n'
        '    text "00:25"\n'
        '    text "A处你完蛋了，Gpt和Gemini要把你打趴下来"\n'
        '    text "2026-11-19 12:47"\n'
        '    text "174"\n'
        '    text "4"\n'
        '    text "14"\n'
        '    text "1"\n'
        '    text "0"\n'
    )
    xhs_ego_items = rs.parse_xhs(xhs_ego)
    check(len(xhs_ego_items) == 1, f"小红书 Ego snapshot 应解析出 1 条，实际 {len(xhs_ego_items)}")
    if xhs_ego_items:
        check(xhs_ego_items[0]["raw"] == ["174", "4", "14", "1", "0"], f"小红书 Ego snapshot 数字不对：{xhs_ego_items[0]['raw']}")

    # 3) 视频号纯文本 & Ego snapshot
    wx_plain = (
        "都2026年了，还在用传统方式剪口播？\n"
        "2026年04月19日 23:23\n"
        "已声明原创\n"
        "1395\n10\n5\n18\n22\n"
    )
    wx_items = rs.parse_wx(wx_plain)
    check(len(wx_items) == 1 and wx_items[0]["raw"] == ["1395", "10", "5", "18", "22"],
          f"视频号纯文本解析不对：{wx_items}")

    wx_ego = (
        'root\n'
        '  container\n'
        '    text "在达芬奇中剪辑长视频的思路和方法 #达芬奇剪辑"\n'
        '    text "2026年10月22日 17:39"\n'
        '    text "已声明原创"\n'
        '    text "397"\n'
        '    text "0"\n'
        '    text "1"\n'
        '    text "3"\n'
        '    text "6"\n'
    )
    wx_ego_items = rs.parse_wx(wx_ego)
    check(len(wx_ego_items) == 1 and wx_ego_items[0]["raw"] == ["397", "0", "1", "3", "6"],
          f"视频号 Ego snapshot 解析不对：{wx_ego_items}")

    # 4) 抖音列表页纯文本兜底
    dy_plain = (
        "在达芬奇中剪辑长视频的思路和方法 #达芬奇剪辑\n"
        "2026年10月22日 17:40\n"
        "已发布\n"
        "播放\n718\n点赞\n6\n评论\n0\n分享\n0\n收藏\n5\n"
    )
    dy_items = rs.parse_dy(dy_plain)
    check(len(dy_items) == 1 and dy_items[0]["raw"] == ["718", "6", "0", "0", "5"],
          f"抖音列表纯文本解析不对：{dy_items}")


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
        test_savefull_and_vom_fold,
        test_suspected_new_unmatched,
        test_rolling_scope_days_and_limit,
        test_plain_text_and_ego_snapshot,
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
