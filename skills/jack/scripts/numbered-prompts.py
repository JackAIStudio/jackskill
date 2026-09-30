#!/usr/bin/env python3
"""Read the public numbered catalog and prompts from the jkskill GitHub repository."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


BASE_URL = (
    "https://raw.githubusercontent.com/JackAIStudio/jackskill/"
    "main/skills/jack/numbered-prompts"
)
ROOT = Path(__file__).resolve().parents[1] / "numbered-prompts"
CODE = re.compile(r"[0-9]{3}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
TITLE = re.compile(r"^# ([0-9]{3})｜(.+)$", re.MULTILINE)

# 思想库（全量视频口播逐字稿）主题归类规则：具体主题在前、宽泛主题在后兜底。
# 分类分两阶段：先用标题匹配全部规则；标题无命中时，再用正文前 400 字走一遍同样顺序。
TOPICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("剪辑与达芬奇实战", ("达芬奇", "剪辑", "字幕", "成片", "多机位", "录屏", "JackAICut", "Screen Studio", "ScreenStudio")),
    ("桌面工作台与远程互联", ("dsh", "DSH", "Harness", "harness", "工作台", "远程", "互联互通", "桌面端", "宕机", "浏览器插件", "手机端", "掌上")),
    ("数码与开箱评测", ("iPhone", "iphone", "AirPods", "Vision Pro", "vision pro", "MacBook", "大疆", "DJI", "开箱", "自拍杆", "麦克风", "Neo", "neo2", "耳机", "高科技")),
    ("读书与写作", ("书籍", "读书", "汪曾祺", "围城", "小王子", "生死疲劳", "罪与罚", "张爱玲", "写作", "小作文", "文学", "阅读", "战争与和平", "听书", "面具之后", "倾城之恋")),
    ("音乐与唱歌", ("清唱", "李健", "演唱会", "ktv", "KTV", "风吹麦浪", "传奇", "嗨唱")),
    ("美食与烟火气", ("美食", "排骨", "包子", "羊肉", "藏面", "酥油茶", "胡辣汤", "肉夹馍", "海鲜", "KFC", "可乐", "炒饭", "甜茶", "厨师", "芹菜", "钵钵鸡", "兔头", "晚餐", "早餐", "鬼包子", "吃饭")),
    ("旅行与远方", ("旅行", "拉萨", "西藏", "大理", "洱海", "西安", "成都", "重庆", "杭州", "温州", "涠洲岛", "贵阳", "昆明", "citywalk", "city walk", "布达拉宫", "羊湖", "冰川", "古街", "回家", "海岛", "海边", "日出", "深圳")),
    ("自研工具与开源", ("开源", "开发", "神器", "APP", "app", "工具", "插件", "JackVoice", "语音输入", "语音识别", "下载", "域名", "LivePhoto")),
    ("AI 与 Agent 实战", ("AI", "Agent", "Codex", "CodeX", "codex", "DeepSeek", "Deepseek", "GPT", "Claude", "Gemini", "Grok", "grok", "大模型", "提示词", "上下文", "Vibe Coding", "vibe", "编程", "WorkBuddy", "workbuddy", "skill", "Skill", "OpenClaw", "Qwen", "qwen", "智能体")),
    ("自媒体运营与创作心法", ("自媒体", "选题", "封面", "流量", "博主", "视频号", "小红书", "抖音", "B站", "发布", "口播", "镜头", "真人出镜", "涨粉", "创作", "up主", "UP主", "主播")),
    ("生活感悟与成长", ("感悟", "迷茫", "焦虑", "鸡血", "社交", "孤独", "负债", "恐惧", "羞耻", "人生", "选择", "理想", "现实", "意义", "碎碎念", "成长", "上班", "病痛", "玩游戏", "微笑", "规划", "祝福", "生活")),
    ("Vlog 与生活记录", ("vlog", "Vlog", "VLOG", "日常", "一天", "天空", "晚霞", "落日", "游泳", "摄影", "照片", "街拍", "表白", "情书", "模特", "聚会", "爷爷", "堂弟", "同学")),
)
SECTIONS = (
    "## 用户要完成的事",
    "## 需要的输入",
    "## 执行步骤",
    "## 交付结果",
)


class CatalogError(Exception):
    pass


def read_remote(path: str, limit: int) -> bytes:
    # A unique query prevents a recently published file from being obscured by a stale CDN response.
    url = f"{BASE_URL}/{path}?v={time.time_ns()}"
    request = Request(
        url,
        headers={"User-Agent": "jkskill-numbered-prompts", "Cache-Control": "no-cache"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            if response.geturl().split("/", 3)[2] != "raw.githubusercontent.com":
                raise CatalogError("GitHub 原始文件发生意外跳转")
            content = response.read(limit + 1)
    except (HTTPError, URLError, TimeoutError, OSError) as error:
        raise CatalogError(f"无法从 GitHub 读取编号内容：{error}") from error
    if len(content) > limit:
        raise CatalogError("GitHub 编号文件超过大小限制")
    return content


def validate_catalog(raw: bytes) -> list[dict[str, str]]:
    try:
        document = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CatalogError("编号目录不是有效的 UTF-8 JSON") from error
    if not isinstance(document, dict) or document.get("schema_version") != 1:
        raise CatalogError("编号目录格式版本不正确")
    items = document.get("items")
    if not isinstance(items, list) or len(items) > 1000:
        raise CatalogError("编号目录条目数量无效")
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise CatalogError("编号目录条目格式错误")
        code = item.get("id")
        if not isinstance(code, str) or CODE.fullmatch(code) is None or code in seen:
            raise CatalogError("编号目录包含无效或重复编号")
        seen.add(code)
        if any(not isinstance(item.get(key), str) or not item[key].strip() for key in ("title", "purpose")):
            raise CatalogError(f"编号 {code} 缺少标题或用途")
        if any(len(item[key]) > 500 or "\n" in item[key] or "\r" in item[key] for key in ("title", "purpose")):
            raise CatalogError(f"编号 {code} 的标题或用途格式错误")
        if not isinstance(item.get("sha256"), str) or DIGEST.fullmatch(item["sha256"]) is None:
            raise CatalogError(f"编号 {code} 缺少有效的内容校验值")
    if [item["id"] for item in items] != sorted(seen):
        raise CatalogError("编号目录没有按编号排序")
    return items


def catalog() -> tuple[list[dict[str, str]], bool]:
    # 优先尝试从本地读取（如果本地存在且有效），网络回退
    local = ROOT / "catalog.json"
    if local.is_file():
        try:
            return validate_catalog(local.read_bytes()), False
        except (OSError, CatalogError):
            pass

    try:
        return validate_catalog(read_remote("catalog.json", 1024 * 1024)), True
    except CatalogError as remote_error:
        if local.is_file():
            try:
                return validate_catalog(local.read_bytes()), False
            except (OSError, CatalogError):
                raise remote_error
        raise remote_error


def get_prompt(code: str) -> str:
    items, online = catalog()
    entry = next((item for item in items if item["id"] == code), None)
    if entry is None:
        raise CatalogError(f"编号 {code} 尚未在目录中发布")

    # 优先读本地文件，本地没有再读远程
    path = ROOT / code / "PROMPT.md"
    if path.is_file():
        raw = path.read_bytes()
    elif online:
        raw = read_remote(f"{code}/PROMPT.md", 256 * 1024)
    else:
        raise CatalogError(f"本地及网络均未找到编号 {code} 的正文")

    if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
        # 如果哈希不匹配且在线，尝试重新从远程拉取
        try:
            raw = read_remote(f"{code}/PROMPT.md", 256 * 1024)
        except Exception:
            pass
        if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
            raise CatalogError(f"编号 {code} 的内容校验值不一致")

    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise CatalogError(f"编号 {code} 的正文不是 UTF-8") from error

    title = TITLE.search(content)
    if title is None or title.group(1) != code or any(section not in content for section in SECTIONS):
        raise CatalogError(f"编号 {code} 的正文结构不完整（缺少必要章节）")
    return content


def find_transcripts_dir() -> Path | None:
    """从脚本所在位置向上探测仓库根下的 transcripts/md 目录（兼容 symlink 安装）。"""
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "transcripts" / "md"
        if candidate.is_dir():
            return parent / "transcripts"
    return None


BODY_MARKER = re.compile(r"^##\s.*逐字稿.*$", re.MULTILINE)


def extract_body(text: str) -> str:
    """去掉 md 文件头部的标题与元信息，只留口播正文，供检索与片段提取使用。"""
    marker = BODY_MARKER.search(text)
    if marker is not None:
        return text[marker.end():]
    divider = text.find("\n---\n")
    if divider >= 0:
        return text[divider + 5:]
    return text


def load_transcripts() -> list[dict[str, str]]:
    """加载全量逐字稿：返回 [{'date': ..., 'title': ..., 'file': ..., 'text': ..., 'body': ...}]，按日期倒序。"""
    transcripts_dir = find_transcripts_dir()
    if transcripts_dir is None:
        raise CatalogError("未找到逐字稿库（transcripts/md 目录不存在，请确认仓库完整克隆）")
    entries: list[dict[str, str]] = []
    for path in (transcripts_dir / "md").glob("*.md"):
        # 文件名格式：YYYY-MM-DD_标题.md（标题中可能再含下划线，只切第一段日期）
        stem = path.stem
        date, _, title = stem.partition("_")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        entries.append({"date": date, "title": title, "file": str(path), "text": text, "body": extract_body(text)})
    entries.sort(key=lambda item: item["date"], reverse=True)
    if not entries:
        raise CatalogError("逐字稿库为空（transcripts/md 下没有任何 .md 文件）")
    return entries


def classify(entry: dict[str, str]) -> str:
    """两阶段分类：先用标题按 TOPICS 顺序匹配；标题无命中时再用口播正文前 400 字走一遍。"""
    for topic, keywords in TOPICS:
        if any(keyword in entry["title"] for keyword in keywords):
            return topic
    head = entry["body"][:400]
    for topic, keywords in TOPICS:
        if any(keyword in head for keyword in keywords):
            return topic
    return "其他"


def transcripts_overview(entries: list[dict[str, str]]) -> str:
    total_chars = sum(len(item["text"]) for item in entries)
    lines = [
        f"📚 Jack 思想库：共 {len(entries)} 篇全量视频口播逐字稿，约 {total_chars / 10000:.0f} 万字，"
        f"时间跨度 {entries[-1]['date']} 至 {entries[0]['date']}。",
        "",
        "主题分布：",
    ]
    buckets: dict[str, int] = {}
    for item in entries:
        buckets[classify(item)] = buckets.get(classify(item), 0) + 1
    for topic, count in sorted(buckets.items(), key=lambda pair: pair[1], reverse=True):
        lines.append(f"- {topic}：{count} 篇")
    lines += ["", "最近更新："]
    for item in entries[:5]:
        lines.append(f"- {item['date']}｜{item['title']}")
    return "\n".join(lines)


def transcripts_recent(entries: list[dict[str, str]], limit: int) -> str:
    lines = [f"最近 {min(limit, len(entries))} 篇逐字稿（新→旧）：", ""]
    for item in entries[:limit]:
        lines.append(f"- {item['date']}｜{item['title']}")
    return "\n".join(lines)


def _squeeze(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def transcripts_search(entries: list[dict[str, str]], keywords: list[str], limit: int = 10) -> str:
    """全文检索：在口播正文（剔除头部元信息）中计分，标题命中权重 ×5，返回带上下文片段的候选篇目。"""
    scored: list[tuple[int, dict[str, str], str]] = []
    for item in entries:
        score = 0
        first_pos = -1
        for keyword in keywords:
            body_hits = item["body"].count(keyword)
            title_hits = item["title"].count(keyword)
            score += body_hits + title_hits * 5
            pos = item["body"].find(keyword)
            if pos >= 0 and (first_pos < 0 or pos < first_pos):
                first_pos = pos
        if score <= 0:
            continue
        start = max(0, first_pos - 100)
        snippet = _squeeze(item["body"][start:first_pos + 160])
        scored.append((score, item, snippet))
    scored.sort(key=lambda triple: triple[0], reverse=True)
    if not scored:
        return f"没有找到与「{' / '.join(keywords)}」相关的逐字稿。可换用近义词或更口语化的关键词重试。"
    lines = [
        f"共 {len(scored)} 篇逐字稿命中「{' / '.join(keywords)}」，按相关度取前 {min(limit, len(scored))} 篇：",
        "（以下为候选与片段，正式回答前请先精读其中最相关 1-3 篇的完整正文）",
        "",
    ]
    for rank, (score, item, snippet) in enumerate(scored[:limit], 1):
        lines.append(f"{rank}. {item['date']}｜{item['title']}（相关度 {score}）")
        lines.append(f"   文件：{item['file']}")
        lines.append(f"   片段：…{snippet}…")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="JackSkill Numbered Prompts Dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    get = sub.add_parser("get")
    get.add_argument("code")
    transcripts = sub.add_parser("transcripts")
    transcripts_sub = transcripts.add_subparsers(dest="transcripts_command", required=True)
    transcripts_sub.add_parser("overview")
    recent = transcripts_sub.add_parser("recent")
    recent.add_argument("limit", nargs="?", type=int, default=10)
    search = transcripts_sub.add_parser("search")
    search.add_argument("keywords", nargs="+")
    args = parser.parse_args()
    try:
        if args.command == "list":
            items, online = catalog()
            source = "远程最新" if online else "本地已安装"
            if not items:
                print("JackSkill 当前还没有上架已发布的编号。敬请期待！")
            else:
                print(f"【工具编号】JackSkill 当前共有 {len(items)} 个可用编号（{source}）：\n")
                for item in items:
                    print(f"- /jack {item['id']} ｜ {item['title']}：{item['purpose']}")
            print()
            try:
                print(transcripts_overview(load_transcripts()))
            except CatalogError:
                print("【思想库】当前环境未检出逐字稿库（仅完整克隆仓库时可用）。")
        elif args.command == "get":
            if CODE.fullmatch(args.code) is None:
                raise CatalogError("编号必须是三位数字（如 001, 002）")
            print(get_prompt(args.code), end="")
        else:
            entries = load_transcripts()
            if args.transcripts_command == "overview":
                print(transcripts_overview(entries))
            elif args.transcripts_command == "recent":
                print(transcripts_recent(entries, max(1, min(args.limit, 100))))
            else:
                keywords = [keyword.strip() for keyword in args.keywords if keyword.strip()]
                if not keywords:
                    raise CatalogError("请至少提供一个检索关键词")
                print(transcripts_search(entries, keywords))
    except CatalogError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
