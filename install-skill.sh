#!/usr/bin/env bash
# ==============================================================================
# JackSkill 一键多端安装脚本
# 支持：豆包 Mac App、WorkBuddy、Claude Code、Codex、Trae 以及通用 Agents
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_JACK="${SCRIPT_DIR}/skills/jack"

if [ ! -d "${SOURCE_JACK}" ]; then
  echo "❌ 错误：未找到 jack 核心技能目录：${SOURCE_JACK}"
  exit 1
fi

echo "🚀 开始安装 JackSkill（吴杰克 Jack 生产力武器库）..."

# 1. 核心公共入口：~/.agents/skills/jack (覆盖豆包 Mac App, Trae, Codex, DSH 等)
AGENTS_DIR="${HOME}/.agents/skills"
mkdir -p "${AGENTS_DIR}"
ln -sfn "${SOURCE_JACK}" "${AGENTS_DIR}/jack"
echo "  ✓ 已链接通用 Agents 公共入口: ${AGENTS_DIR}/jack"

# 2. 腾讯 WorkBuddy 专属入口 (若存在 ~/.workbuddy)
if [ -d "${HOME}/.workbuddy" ]; then
  WB_DIR="${HOME}/.workbuddy/skills"
  mkdir -p "${WB_DIR}"
  ln -sfn "${SOURCE_JACK}" "${WB_DIR}/jack"
  echo "  ✓ 已链接 WorkBuddy 专属入口: ${WB_DIR}/jack"
fi

# 3. Claude Code 专属入口 (若存在 ~/.claude)
if [ -d "${HOME}/.claude" ]; then
  CLAUDE_DIR="${HOME}/.claude/skills"
  mkdir -p "${CLAUDE_DIR}"
  ln -sfn "${SOURCE_JACK}" "${CLAUDE_DIR}/jack"
  echo "  ✓ 已链接 Claude Code 专属入口: ${CLAUDE_DIR}/jack"
fi

echo ""
echo "🎉 安装完成！你可以在 豆包、WorkBuddy、Claude Code 或任何 Agent 中使用："
echo "   - 输入「/jack」开始使用或获取推荐"
echo "   - 输入「/jack <编号>」直接执行对应视频技能"
echo "   - 输入「/jack list」查看当前所有发布的编号与隐藏款"
