#!/usr/bin/env python3
"""
把浏览器里读到的抖音 work_list JSON 转成封面清单。

为什么需要这个中转：抖音创作者后台的 work_list 接口要登录态，curl 直接打
返回空；只能在已登录的浏览器里打开那个 URL，再从页面文本里把 JSON 抠出来。
抠出来的文本会被工具折行，所以这里负责清洗、解析、落盘。

抖音这一步的价值：**一个作品对象里同时带两张封面**——
    Cover           竖版 540x721   → 3:4
    horizontal_cover 横版 720x539  → 4:3
所以抖音一期能同时补齐横竖两张，不用再分别找平台。

用法：
    python3 scripts/parse-dy-dump.py --in /tmp/dy-page.txt --out /tmp/dy-covers.json
    # --in 支持多份，按作品 id 去重合并
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 工具把长文本折行时插进来的标记：引号 + 换行 + 缩进 + StaticText + 引号
FOLD = re.compile(r'"\s*\n\s*StaticText "')


def extract_json(raw: str) -> dict | None:
    """从页面文本里抠出那段 work_list JSON。"""
    m = re.search(r'StaticText "(.*?)"\n\s*form', raw, re.S)
    if not m:
        m = re.search(r'"(.*aweme_list.*)"', raw, re.S)
    if not m:
        return None
    txt = m.group(1).replace('\\"', '"')
    txt = FOLD.sub("", txt)
    txt = txt.replace("\\\\", "\\")
    try:
        return json.loads(txt)
    except json.JSONDecodeError:
        # 退一步：只抓 aweme_list 那一段，逐个对象解析
        return None


def norm_title(s: str) -> str:
    import unicodedata
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"#[^\s#]+", "", s)
    return re.sub(r"[\s\W_]+", "", s).lower()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", nargs="+", required=True, help="页面文本文件，可多份")
    ap.add_argument("--out", default="/tmp/dy-covers.json")
    args = ap.parse_args()

    items: dict[str, dict] = {}
    for path in args.inputs:
        raw = Path(path).read_text(encoding="utf-8", errors="replace")
        data = extract_json(raw)
        if not data:
            print(f"  ! {path} 解析失败，跳过", file=sys.stderr)
            continue
        aw = data.get("aweme_list") or []
        print(f"  {Path(path).name}: {len(aw)} 条")
        for a in aw:
            aid = str(a.get("aweme_id") or a.get("item_id") or "")
            if not aid:
                continue
            items[aid] = a

    print(f"\n累计 {len(items)} 个作品（按 id 去重）")

    # 用作品 id 当 key，不用标题。
    #
    # 标题在抖音上经常被改短：仓库主题写「DeepSeek出了个新东西，这回是真能
    # 帮你干活|deepseek harness上手体验」，抖音只写前半句。按标题匹配时，
    # 只要改过一个字整条就对不上，那期的横竖两张封面全漏掉。作品 id 与视频
    # 一一对应，标题怎么改都不影响。标题仍然留着，只是不再当索引用。
    out = {}
    for a in items.values():
        aid = str(a.get("aweme_id") or a.get("item_id") or "")
        if not aid:
            continue
        title = a.get("item_title") or a.get("desc") or ""
        clean = re.sub(r"\s*#[^\s#]+", "", title).strip()
        vert = (a.get("Cover") or {}).get("url_list") or []
        horiz = (a.get("horizontal_cover") or {}).get("url_list") or []
        covers = {}
        if horiz:
            covers["4x3"] = {"url": horiz[0], "source": "douyin"}
        if vert:
            covers["3x4"] = {"url": vert[0], "source": "douyin"}
        if covers:
            out[aid] = {"title": clean, "covers": covers}

    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"写出 {len(out)} 个作品（按 aweme_id 索引）→ {args.out}")

    both = sum(1 for v in out.values() if len(v.get("covers") or {}) == 2)
    print(f"横竖齐全: {both}/{len(out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
