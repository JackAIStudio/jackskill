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


def main() -> int:
    parser = argparse.ArgumentParser(description="JackSkill Numbered Prompts Dispatcher")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    get = sub.add_parser("get")
    get.add_argument("code")
    args = parser.parse_args()
    try:
        if args.command == "list":
            items, online = catalog()
            source = "远程最新" if online else "本地已安装"
            if not items:
                print("JackSkill 当前还没有上架已发布的编号。敬请期待！")
            else:
                print(f"JackSkill 当前共有 {len(items)} 个可用编号（{source}）：\n")
                for item in items:
                    print(f"- /jack {item['id']} ｜ {item['title']}：{item['purpose']}")
        else:
            if CODE.fullmatch(args.code) is None:
                raise CatalogError("编号必须是三位数字（如 001, 002）")
            print(get_prompt(args.code), end="")
    except CatalogError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
