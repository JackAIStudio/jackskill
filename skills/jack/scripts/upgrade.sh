#!/usr/bin/env bash
# JackSkill 升级：先认安装形态，再决定升级路径。
#   源码 / 软链接安装：git pull --rebase。这是仓库开发者的装法，软链接直连源码，
#                     重新拉取会把软链接替换成一份副本，本地改动随之丢失，因此必须走 git。
#   复制 / 市场安装  ：交给 skills CLI 重新拉取。
# 标准输出一行结果，退出码非 0 表示未完成升级。
#
# 用法：
#   upgrade.sh            执行升级（有写操作）
#   upgrade.sh --dry-run  只读诊断，不做任何写操作，用于日常自检与测试前置
set -uo pipefail

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '1,11p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *)
      echo "未知参数：$arg（支持 --dry-run / --help）"
      exit 2
      ;;
  esac
done

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

# 判断调用路径上的 skill 目录（scripts 的上一级）是不是软链接。
# 必须看调用路径本身：pwd -P 会把软链接解掉；比较 pwd 与 pwd -P 又会把
# macOS 的 /var -> /private/var 误判成软链接安装。
classify_install_form() {
  local invoke="${BASH_SOURCE[0]}" part rest stack="" skill_link
  case "$invoke" in
    /*) ;;
    *) invoke="$(pwd -L)/$invoke" ;;
  esac
  rest="${invoke#/}"
  while [ -n "$rest" ]; do
    part="${rest%%/*}"
    case "$rest" in
      */*) rest="${rest#*/}" ;;
      *) rest="" ;;
    esac
    case "$part" in
      ""|".") ;;
      "..")
        case "$stack" in
          */*) stack="${stack%/*}" ;;
          *) stack="" ;;
        esac
        ;;
      *)
        if [ -n "$stack" ]; then
          stack="$stack/$part"
        else
          stack="$part"
        fi
        ;;
    esac
  done
  skill_link="$(dirname "$(dirname "/$stack")")"
  if [ -L "$skill_link" ]; then
    printf 'symlink\n'
  else
    printf 'directory\n'
  fi
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

if [ "$DRY_RUN" -eq 1 ]; then
  echo "安装形态诊断（dry-run，未执行任何写操作）"
  echo "  skill 目录：$SKILL_DIR"
  if [ "$(classify_install_form)" = "symlink" ]; then
    echo "  形态：软链接安装（symlink 直连源码）"
  else
    echo "  形态：实体目录"
  fi
  if [ -n "$REPO_ROOT" ]; then
    echo "  仓库根：$REPO_ROOT"
    echo "  升级将走路径：git pull --rebase --autostash（软链接与本地改动保留）"
  else
    echo "  仓库根：未找到（向上未遇到同时含 .git 与 skills/jack/SKILL.md 的目录）"
    if command -v npx >/dev/null 2>&1; then
      echo "  升级将走路径：npx skills add JackAIStudio/jackskill -g --all"
    else
      echo "  升级将走路径：本机无 npx，无法自动升级"
    fi
  fi
  exit 0
fi

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
