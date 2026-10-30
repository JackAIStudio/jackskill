#!/usr/bin/env python3
"""
refresh-followers.py 的解析与写入规则测试。

这里测的是「不依赖网络、不依赖浏览器」的那部分：页面文本 → 粉丝数，
以及拿到数之后怎么写进快照文件。这部分最容易静默出错——
认错了标签不会报错，只会把「粉丝指数」当成粉丝数一直错下去。

跑法：
    python3 tests/test-refresh-followers.py
    ./tests/run.sh 10          # 也可以挂进统一入口
"""
from __future__ import annotations

import importlib.util
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
# 数字格式：精确值、约数、带千分位
# ---------------------------------------------------------------------------

def test_number_formats() -> None:
    check(rf._parse_followers_number("6441") == 6441, "精确整数 6441")
    check(rf._parse_followers_number("6,441") == 6441, "千分位 6,441")
    check(rf._parse_followers_number("1.9万") == 19000, "「1.9万」按档位还原")
    check(rf._parse_followers_number("299") == 299, "三位数 299")
    check(rf._parse_followers_number("1.2亿") == 120000000, "「1.2亿」")
    check(rf._parse_followers_number("—") is None, "破折号不是数字")
    check(rf._parse_followers_number("") is None, "空串不是数字")
    check(rf._parse_followers_number("粉丝数") is None, "标签不是数字")


# ---------------------------------------------------------------------------
# 小红书：值和标签的先后顺序与 observe 里一致
# ---------------------------------------------------------------------------

XHS_HOME = '''
  StaticText "吴杰克 Jack"
  StaticText "0"
  StaticText "关注数"
  StaticText "6441"
  StaticText "粉丝数"
  StaticText "1.9万"
  StaticText "获赞与收藏"
'''


def test_xiaohongshu() -> None:
    n, src = rf.parse_xiaohongshu(XHS_HOME)
    check(n == 6441, f"小红书应读成 6441，实际 {n}")
    check(src == "粉丝数", f"小红书的来源标签应是「粉丝数」，实际 {src}")


# ---------------------------------------------------------------------------
# 抖音：三个坑——粉丝指数不是粉丝数、值在 ctx 里、值在下一个节点
# ---------------------------------------------------------------------------

DY_CTX = '''
      @e68 button "总粉丝量" [ctx: 粉丝数据]
      @e69 button "299" [ctx: 总粉丝量]
      @e70 button "粉丝净增"
      @e71 button "7" [ctx: 粉丝净增]
'''

DY_SEQ = '''
      StaticText "总粉丝量"
      StaticText "299"
      StaticText "粉丝净增"
      StaticText "7"
'''

# 首页只有「粉丝指数 301」，那个是账号权重分，不是粉丝数
DY_INDEX_ONLY = '''
      @e17 button "粉丝指数 301"
      @e16 button "关注 0"
'''


def test_douyin() -> None:
    n, src = rf.parse_douyin(DY_CTX)
    check(n == 299, f"抖音（ctx 形态）应读成 299，实际 {n}")
    check(src == "总粉丝量", f"抖音的来源标签应是「总粉丝量」，实际 {src}")

    n, _ = rf.parse_douyin(DY_SEQ)
    check(n == 299, f"抖音（顺序形态）应读成 299，实际 {n}")

    n, src = rf.parse_douyin(DY_INDEX_ONLY)
    check(n is None, f"只有粉丝指数时不能读成粉丝数，实际读成 {n}")
    check("粉丝指数" in src, f"报错要说清页面里只有粉丝指数，实际 {src}")

    # 关键回归：数据中心页上「粉丝净增 7」就在「总粉丝量 299」旁边，
    # 认错标签就会把 7 当成粉丝数。
    n, _ = rf.parse_douyin(DY_CTX)
    check(n != 7, "不能把「粉丝净增」的 7 当成粉丝总数")


# ---------------------------------------------------------------------------
# 视频号：标签在前、值在后，旁边还有「净增关注」
# ---------------------------------------------------------------------------

WX_HOME = '''
  StaticText "视频"
  StaticText "92"
  StaticText "关注者"
  StaticText "446"
  StaticText "昨日数据"
  StaticText "净增关注"
  StaticText "0"
'''


def test_wechat_channels() -> None:
    n, src = rf.parse_wechat_channels(WX_HOME)
    check(n == 446, f"视频号应读成 446，实际 {n}")
    check(src == "关注者", f"视频号的来源标签应是「关注者」，实际 {src}")

    # 「视频 92」就在「关注者 446」前面一格，认错标签会读成 92
    check(n != 92, "不能把「视频」的数量当成关注者")

    n2, _ = rf.parse_wechat_channels('StaticText "关注者"\nStaticText "1.2万"')
    check(n2 == 12000, f"视频号的约数应按档位还原，实际 {n2}")


# ---------------------------------------------------------------------------
# 认不出就返回 None，不瞎猜
# ---------------------------------------------------------------------------

def test_missing() -> None:
    for name, fn in (("douyin", rf.parse_douyin), ("xiaohongshu", rf.parse_xiaohongshu),
                     ("wechat_channels", rf.parse_wechat_channels)):
        n, src = fn("StaticText \"今天天气不错\"")
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

    check(rf.latest(snaps, "bilibili") == (483, "2026-10-31"), "latest 应返回最新那条")

    # dry-run 不写盘
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
    dates = []
    import json
    for line in lines:
        dates.append(json.loads(line)["date"])
    check(dates == ["2026-10-31", "2026-10-30", "2026-10-29"], f"应按日期倒序写回，实际 {dates}")


def main() -> int:
    import tempfile

    test_number_formats()
    test_xiaohongshu()
    test_douyin()
    test_wechat_channels()
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
