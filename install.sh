#!/usr/bin/env bash
# ==============================================================================
# JackSkill 一键安装脚本
# 统一安装至 Agent 通用标准目录：~/.agents/skills/jack
# 兼容环境：豆包、WorkBuddy、Codex、Claude Code、Trae 以及各类 AI Agents
# ==============================================================================

set -euo pipefail

SKILLS_ROOT="${HOME}/.agents/skills"
TARGET_JACK="${SKILLS_ROOT}/jack"
REPO_URL="https://github.com/JackAIStudio/jackskill.git"

mkdir -p "${SKILLS_ROOT}"

echo "开始安装 JackSkill 到 Agent 通用目录..."

# 1. 判断是本地源码运行，还是远程终端运行
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd || echo "")"
if [ -n "${SCRIPT_DIR}" ] && [ -f "${SCRIPT_DIR}/skills/jack/SKILL.md" ]; then
  # 本地仓库运行：直接软链接到通用目录，开发修改实时生效
  SRC_JACK="${SCRIPT_DIR}/skills/jack"
  ln -sfn "${SRC_JACK}" "${TARGET_JACK}"
  echo "  已通过源码链接至: ${TARGET_JACK}"
else
  # 远程 curl | bash 运行：直接将 jack skill 部署到通用目录
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "${TMP_DIR}"' EXIT
  echo "  正在获取最新技能文件..."
  git clone --quiet --depth=1 "${REPO_URL}" "${TMP_DIR}/jackskill"
  rm -rf "${TARGET_JACK}"
  cp -R "${TMP_DIR}/jackskill/skills/jack" "${TARGET_JACK}"
  echo "  已部署至通用 Agent 目录: ${TARGET_JACK}"
fi

# 2. 腾讯 WorkBuddy 专属入口兼容（若存在 ~/.workbuddy/skills）
if [ -d "${HOME}/.workbuddy" ]; then
  WB_DIR="${HOME}/.workbuddy/skills"
  mkdir -p "${WB_DIR}"
  ln -sfn "${TARGET_JACK}" "${WB_DIR}/jack"
  echo "  已同步 WorkBuddy 入口: ${WB_DIR}/jack"
fi

# 3. Claude Code 专属入口兼容（若存在 ~/.claude/skills）
if [ -d "${HOME}/.claude" ]; then
  CLAUDE_DIR="${HOME}/.claude/skills"
  mkdir -p "${CLAUDE_DIR}"
  ln -sfn "${TARGET_JACK}" "${CLAUDE_DIR}/jack"
  echo "  已同步 Claude Code 入口: ${CLAUDE_DIR}/jack"
fi

echo ""
echo "安装完成。核心目录已就绪: ${TARGET_JACK}"
echo "   现在可在 豆包、WorkBuddy、Claude Code、Codex 等任意支持的 Agent 中直接使用："
echo "   - 输入「/jack」开始使用"
echo "   - 输入「/jack <编号>」直接执行对应技能（如 /jack 101）"
echo "   - 输入「/jack list」查看当前技能清单"
