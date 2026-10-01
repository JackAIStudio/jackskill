#!/usr/bin/env bash
# JackSkill 升级：先认安装形态，再决定升级路径。
#   源码 / 软链接安装：git pull --rebase。这是仓库开发者的装法，软链接直连源码，
#                     重新拉取会把软链接替换成一份副本，本地改动随之丢失，因此必须走 git。
#   复制 / 市场安装  ：交给 skills CLI 重新拉取。
# 标准输出一行结果，退出码非 0 表示未完成升级。
set -uo pipefail

# 逐级解析软链接，拿到脚本自身的真实路径
resolve_self() {
  local target="$1" link
  while [ -L "$target" ]; do
    link="$(readlink "$target")" || return 1
    case "$link" in
      /*) target="$link" ;;
      *) target="$(dirname "$target")/$link" ;;
    esac
  done
  printf '%s\n' "$target"
}

SELF="$(resolve_self "${BASH_SOURCE[0]}")" || {
  echo "升级失败：无法解析脚本路径。"
  exit 1
}
SKILL_DIR="$(cd "$(dirname "$SELF")/.." && pwd -P)" || {
  echo "升级失败：无法定位 skill 目录。"
  exit 1
}

# 向上找源码仓库根：既要是 git 仓库，又要包含本 skill，避免误判
REPO_ROOT=""
dir="$SKILL_DIR"
while [ -n "$dir" ] && [ "$dir" != "/" ]; do
  if [ -e "$dir/.git" ] && [ -f "$dir/skills/jack/SKILL.md" ]; then
    REPO_ROOT="$dir"
    break
  fi
  dir="$(dirname "$dir")"
done

if [ -n "$REPO_ROOT" ]; then
  # 先取远端引用再比对：没有新提交时就不必动工作区，脏工作区也能正常结束
  if ! git -C "$REPO_ROOT" fetch --quiet 2>/dev/null; then
    echo "源码仓库同步未完成：连不上远端，已保留当前版本：${REPO_ROOT}"
    exit 1
  fi
  UPSTREAM="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null || true)"
  if [ -z "$UPSTREAM" ]; then
    echo "源码仓库没有配置上游分支，未自动同步，已保留当前版本：${REPO_ROOT}"
    exit 1
  fi
  if [ "$(git -C "$REPO_ROOT" rev-parse HEAD)" = "$(git -C "$REPO_ROOT" rev-parse "$UPSTREAM")" ]; then
    echo "已是最新版本（${UPSTREAM} 无新提交）：${REPO_ROOT}"
    exit 0
  fi
  # --autostash：本地未提交的改动先自动暂存，同步完再放回来，不会丢
  if git -C "$REPO_ROOT" pull --rebase --autostash --quiet 2>/dev/null; then
    if [ -n "$(git -C "$REPO_ROOT" diff --name-only --diff-filter=U 2>/dev/null)" ]; then
      echo "已同步最新版本，但你本地未提交的改动与新版有重叠，工作区留有冲突标记，需要手动处理：${REPO_ROOT}"
      exit 0
    fi
    echo "已从源码仓库同步最新版本，软链接安装方式保持不变：${REPO_ROOT}"
    exit 0
  fi
  if [ -d "$REPO_ROOT/.git/rebase-merge" ] || [ -d "$REPO_ROOT/.git/rebase-apply" ]; then
    echo "源码仓库同步中断在合并中，需要手动处理（git rebase --continue 或 --abort）：${REPO_ROOT}"
    exit 1
  fi
  echo "源码仓库同步未完成，已保留当前版本，可在该仓库手动 git pull：${REPO_ROOT}"
  exit 1
fi

if command -v npx >/dev/null 2>&1; then
  if npx -y skills add JackAIStudio/jackskill -g --all >/dev/null 2>&1; then
    echo "已重新拉取最新版本。"
    exit 0
  fi
  echo "升级失败：skills CLI 未能完成拉取，可稍后重试。"
  exit 1
fi

echo "升级失败：本机没有 npx，当前也不是源码安装，无法自动升级。"
exit 1
