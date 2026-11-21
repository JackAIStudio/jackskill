#!/usr/bin/env python3
"""
refresh-followers.py 的解析与写入规则测试。

这里测的是「不依赖网络、不依赖浏览器」的那部分：Ego Lite 采集输出 → 粉丝数，
以及拿到数之后怎么写进快照文件。这部分最容易静默出错——
认错了标签不会报错，只会把「粉丝指数」或「正在关注」当成粉丝数一直错下去。

跑法：
    python3 tests/test-refresh-followers.py
    ./tests/run.sh 10          # 也可以挂进统一入口
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location(
    "refresh_followers", REPO_ROOT / "scripts/refresh-followers.py"
)
rf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rf)

failures: list[str] = []
checks = 0


def check(cond: bool, label: str) -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(label)


# ---------------------------------------------------------------------------
# 数字格式：精确值、约数、千分位、英文 K / M
# ---------------------------------------------------------------------------

def test_number_formats() -> None:
    check(rf._parse_followers_number("6441") == 6441, "精确整数 6441")
    check(rf._parse_followers_number("6,441") == 6441, "千分位 6,441")
    check(rf._parse_followers_number("1.9万") == 19000, "「1.9万」按档位还原")
    check(rf._parse_followers_number("1.2K") == 1200, "「1.2K」按档位还原")
    check(rf._parse_followers_number("1.5M") == 1500000, "「1.5M」按档位还原")
    check(rf._parse_followers_number("299") == 299, "三位数 299")
    check(rf._parse_followers_number("1.2亿") == 120000000, "「1.2亿」")
    check(rf._parse_followers_number("—") is None, "破折号不是数字")
    check(rf._parse_followers_number("") is None, "空串不是数字")
    check(rf._parse_followers_number("粉丝数") is None, "标签不是数字")


# ---------------------------------------------------------------------------
# 小红书：值和标签的先后顺序、合并节点与骨架屏拦截
# ---------------------------------------------------------------------------

XHS_HOME = '''
root
  container
    text "吴杰克 Jack"
    text "0"
    text "关注数"
    text "6441"
    text "粉丝数"
    text "1.9万"
    text "获赞与收藏"
'''

XHS_MERGED = '''
吴杰克 Jack 0 关注数 6446 粉丝数 1.9万 获赞与收藏 小红书账号: 9552197136
'''

XHS_NO_FANS = '''
吴杰克 Jack 0 关注数 6446 获赞与收藏
'''


def test_xiaohongshu() -> None:
    n, src = rf.parse_xiaohongshu(XHS_HOME)
    check(n == 6441, f"小红书应读成 6441，实际 {n}")
    check(src == "粉丝数", f"小红书的来源标签应是「粉丝数」，实际 {src}")

    n2, _ = rf.parse_xiaohongshu(XHS_MERGED)
    check(n2 == 6446, f"小红书合并节点应读成 6446，实际 {n2}")
    n3, _ = rf.parse_xiaohongshu(XHS_NO_FANS)
    check(n3 is None, f"没有「粉丝数」标签时应报没读到，实际 {n3}")


# ---------------------------------------------------------------------------
# 抖音：粉丝指数不是粉丝数、只认「总粉丝量」
# ---------------------------------------------------------------------------

DY_INLINE = "总粉丝量 299\n粉丝净增 7\n"
DY_SEQ = '''
root
  container
    text "总粉丝量"
    button "299"
    text "粉丝净增"
    text "7"
'''
DY_INDEX_ONLY = "首页\n粉丝指数 301\n关注 0\n"


def test_douyin() -> None:
    n, src = rf.parse_douyin(DY_INLINE)
    check(n == 299, f"抖音（同行形态）应读成 299，实际 {n}")
    check(src == "总粉丝量", f"抖音的来源标签应是「总粉丝量」，实际 {src}")

    n, _ = rf.parse_douyin(DY_SEQ)
    check(n == 299, f"抖音（Ego snapshot 顺序形态）应读成 299，实际 {n}")

    n, src = rf.parse_douyin(DY_INDEX_ONLY)
    check(n is None, f"只有粉丝指数时不能读成粉丝数，实际读成 {n}")
    check("粉丝指数" in src, f"报错要说清页面里只有粉丝指数，实际 {src}")

    n, _ = rf.parse_douyin(DY_SEQ)
    check(n != 7, "不能把「粉丝净增」的 7 当成粉丝总数")


# ---------------------------------------------------------------------------
# 视频号：标签在前、值在后，旁边还有「净增关注」
# ---------------------------------------------------------------------------

WX_HOME = '''
root
  container
    text "视频"
    text "92"
    text "关注者"
    text "446"
    text "昨日数据"
    text "净增关注"
    text "0"
'''


def test_wechat_channels() -> None:
    n, src = rf.parse_wechat_channels(WX_HOME)
    check(n == 446, f"视频号应读成 446，实际 {n}")
    check(src == "关注者", f"视频号的来源标签应是「关注者」，实际 {src}")
    check(n != 92, "不能把「视频」的数量当成关注者")

    n2, _ = rf.parse_wechat_channels("关注者\n1.2万\n")
    check(n2 == 12000, f"视频号的约数应按档位还原，实际 {n2}")


# ---------------------------------------------------------------------------
# X：JSON 精确整数（UserByScreenName）+ 中英文页面文本兜底，不误读正在关注
# ---------------------------------------------------------------------------

def test_x() -> None:
    # 1) collect-ego.py 产出的 x-followers.json
    x_json = json.dumps({
        "platform": "x",
        "handle": "WuJieKe1999",
        "followers": 462,
        "following": 578,
        "source": "UserByScreenName.relationship_counts",
        "domText": "462 关注者",
    }, ensure_ascii=False)
    n, src = rf.parse_x(x_json)
    check(n == 462, f"X x-followers.json 应读成 462，实际 {n}")
    check("UserByScreenName" in src, f"X 来源不对：{src}")

    # 2) 原始 UserByScreenName GraphQL 响应
    raw_gql = json.dumps({
        "data": {
            "user": {
                "result": {
                    "core": {"screen_name": "WuJieKe1999"},
                    "relationship_counts": {"followers": 465, "following": 578},
                }
            }
        }
    })
    n2, _ = rf.parse_x(raw_gql)
    check(n2 == 465, f"X 原始 GraphQL 应读成 465，实际 {n2}")

    # 3) JSON 里 followers 为 null 时退回 domText 兜底
    fallback_json = json.dumps({
        "platform": "x",
        "handle": "WuJieKe1999",
        "followers": None,
        "domText": "1.2K Followers",
    })
    n3, _ = rf.parse_x(fallback_json)
    check(n3 == 1200, f"X domText 英文 1.2K 兜底应读成 1200，实际 {n3}")

    # 4) 纯文本页面：578 正在关注 / 462 关注者（不能误读 578）
    x_plain_zh = "吴杰克Jack\n@WuJieKe1999\n578 正在关注\n462 关注者\n"
    n4, _ = rf.parse_x(x_plain_zh)
    check(n4 == 462, f"X 中文页面应读成 462 而非 578，实际 {n4}")

    x_plain_en = "Jack\n@WuJieKe1999\n578 Following\n1,234 Followers\n"
    n5, _ = rf.parse_x(x_plain_en)
    check(n5 == 1234, f"X 英文页面应读成 1234，实际 {n5}")

    # 5) 只有「正在关注 / Following」没有「关注者 / Followers」必须返回 None
    n6, _ = rf.parse_x("578 正在关注\n578 Following\n")
    check(n6 is None, f"只有正在关注时必须返回 None，实际 {n6}")


# ---------------------------------------------------------------------------
# 认不出就返回 None，不瞎猜
# ---------------------------------------------------------------------------

def test_missing() -> None:
    for name, fn in (
        ("douyin", rf.parse_douyin),
        ("xiaohongshu", rf.parse_xiaohongshu),
        ("wechat_channels", rf.parse_wechat_channels),
        ("x", rf.parse_x),
    ):
        n, src = fn("今天天气不错\n")
        check(n is None, f"{name} 在无关页面上必须返回 None，实际 {n}")
        check(bool(src), f"{name} 认不出时要给一句原因")


# ---------------------------------------------------------------------------
# 写入：同一天重刷替换，不同天追加
# ---------------------------------------------------------------------------

def test_upsert() -> None:
    snaps: list[dict] = []
    rf.upsert(snaps, "2026-10-30", "bilibili", 479, dry_run=False)
    check(len(snaps) == 1, "第一次写应生成一条快照")
    check(snaps[0]["platforms"]["bilibili"]["followers"] == 479, "应写入 479")

    rf.upsert(snaps, "2026-10-30", "bilibili", 481, dry_run=False)
    check(len(snaps) == 1, "同一天重刷不能多出一条快照")
    check(snaps[0]["platforms"]["bilibili"]["followers"] == 481, "同一天重刷应替换为最新读数")

    rf.upsert(snaps, "2026-10-31", "bilibili", 483, dry_run=False)
    check(len(snaps) == 2, "换一天应追加一条快照")

    rf.upsert(snaps, "2026-11-21", "x", 462, dry_run=False)
    check(rf.latest(snaps, "x") == (462, "2026-11-21"), "latest 应正确返回 X 的最新快照")

    check(rf.latest(snaps, "bilibili") == (483, "2026-10-31"), "latest 应返回最新那条")

    before = len(snaps)
    rf.upsert(snaps, "2026-11-01", "douyin", 300, dry_run=True)
    check(len(snaps) == before, "dry-run 不能写进列表")


def test_upsert_delta() -> None:
    snaps = [{"date": "2026-10-29", "platforms": {"bilibili": {"followers": 470}}}]
    diffs, why = rf.upsert(snaps, "2026-10-30", "bilibili", 479, dry_run=True)
    check(why is None, f"正常写入不该报错，实际 {why}")
    check(any("+9" in d for d in diffs), f"应报出 +9 的增量，实际 {diffs}")


# ---------------------------------------------------------------------------
# 排序：写回时按日期倒序
# ---------------------------------------------------------------------------

def test_save_order(tmp: Path) -> None:
    snaps = [
        {"date": "2026-10-29", "platforms": {"bilibili": {"followers": 470}}},
        {"date": "2026-10-31", "platforms": {"bilibili": {"followers": 483}}},
        {"date": "2026-10-30", "platforms": {"bilibili": {"followers": 479}}},
    ]
    rf.FOLLOWERS_FILE = tmp
    rf.save_snapshots(snaps)
    lines = [l for l in tmp.read_text(encoding="utf-8").splitlines() if l.strip()]
    dates = [json.loads(line)["date"] for line in lines]
    check(dates == ["2026-10-31", "2026-10-30", "2026-10-29"], f"应按日期倒序写回，实际 {dates}")


def test_plain_text_and_ego_snapshot() -> None:
    """兼容 Ego Lite snapshot 与纯文本 innerText，且仍挡掉抖音「粉丝指数」与小红书骨架屏。"""
    dy_plain = "11.13-11.19\n导出数据\n总粉丝量\n327\n粉丝净增\n5\n"
    n, src = rf.parse_douyin(dy_plain)
    check(n == 327 and src == "总粉丝量", f"抖音纯文本应读成 327，实际 {n}（{src}）")

    dy_ego = 'root\n  container\n    text "总粉丝量"\n    button "327" [ref=12]\n    text "粉丝净增"\n    text "5"\n'
    n, _ = rf.parse_douyin(dy_ego)
    check(n == 327, f"抖音 Ego snapshot 应读成 327，实际 {n}")

    dy_home_plain = "首页\n粉丝指数\n301\n关注\n0\n"
    n, src = rf.parse_douyin(dy_home_plain)
    check(n is None and "粉丝指数" in src, f"抖音首页纯文本不能误读粉丝指数：{n} / {src}")

    xhs_plain = "吴杰克 Jack\n0\n关注数\n6455\n粉丝数\n1.9万\n获赞与收藏\n小红书账号: 9552197136\n"
    n, src = rf.parse_xiaohongshu(xhs_plain)
    check(n == 6455 and src == "粉丝数", f"小红书纯文本应读成 6455，实际 {n}（{src}）")

    # 骨架屏保护：账号尚未返回时的占位 0 不能当成粉丝归零
    xhs_skeleton = "吴杰克 Jack\n0\n关注数\n0\n粉丝数\n0\n获赞与收藏\n小红书账号:\n"
    n, src = rf.parse_xiaohongshu(xhs_skeleton)
    check(n is None and "加载" in src, f"小红书骨架屏占位 0 必须拦截：{n} / {src}")

    xhs_ego = 'root\n  container\n    text "0"\n    text "关注数"\n    text "6455"\n    text "粉丝数"\n'
    n, _ = rf.parse_xiaohongshu(xhs_ego)
    check(n == 6455, f"小红书 Ego snapshot 应读成 6455，实际 {n}")

    wx_plain = "视频\n92\n关注者\n446\n昨日数据\n净增关注\n2\n"
    n, src = rf.parse_wechat_channels(wx_plain)
    check(n == 446 and src == "关注者", f"视频号纯文本应读成 446，实际 {n}（{src}）")

    wx_ego = 'root\n  container\n    text "关注者"\n    text "446"\n    text "净增关注"\n    text "2"\n'
    n, _ = rf.parse_wechat_channels(wx_ego)
    check(n == 446, f"视频号 Ego snapshot 应读成 446，实际 {n}")

    x_ego = 'root\n  container\n    link "578 正在关注"\n    link "462 关注者"\n'
    n, _ = rf.parse_x(x_ego)
    check(n == 462, f"X Ego snapshot 应读成 462，实际 {n}")


def main() -> int:
    import tempfile

    test_number_formats()
    test_xiaohongshu()
    test_douyin()
    test_wechat_channels()
    test_x()
    test_plain_text_and_ego_snapshot()
    test_missing()
    test_upsert()
    test_upsert_delta()
    with tempfile.TemporaryDirectory() as d:
        test_save_order(Path(d) / "followers.jsonl")

    if failures:
        print(f"\n{len(failures)} / {checks} 项失败：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"PASS: 粉丝数解析与快照写入共 {checks} 项检查全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
