#!/usr/bin/env bash
# ==============================================================================
# JKSKILL 一键多端安装脚本
# 支持：豆包 Mac App、WorkBuddy、Claude Code、Codex、Trae 以及通用 Agents
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_JKS="${SCRIPT_DIR}/skills/jks"

if [ ! -d "${SOURCE_JKS}" ]; then
  echo "❌ 错误：未找到 jks 核心技能目录：${SOURCE_JKS}"
  exit 1
fi

echo "🚀 开始安装 JKSKILL（吴杰克 Jack 生产力武器库）..."

# 1. 核心公共入口：~/.agents/skills/jks (覆盖豆包 Mac App, Trae, Codex, DSH 等)
AGENTS_DIR="${HOME}/.agents/skills"
mkdir -p "${AGENTS_DIR}"
ln -sfn "${SOURCE_JKS}" "${AGENTS_DIR}/jks"
echo "  ✓ 已链接通用 Agents 公共入口: ${AGENTS_DIR}/jks"

# 2. 腾讯 WorkBuddy 专属入口 (若存在 ~/.workbuddy)
if [ -d "${HOME}/.workbuddy" ]; then
  WB_DIR="${HOME}/.workbuddy/skills"
  mkdir -p "${WB_DIR}"
  ln -sfn "${SOURCE_JKS}" "${WB_DIR}/jks"
  echo "  ✓ 已链接 WorkBuddy 专属入口: ${WB_DIR}/jks"
fi

# 3. Claude Code 专属入口 (若存在 ~/.claude)
if [ -d "${HOME}/.claude" ]; then
  CLAUDE_DIR="${HOME}/.claude/skills"
  mkdir -p "${CLAUDE_DIR}"
  ln -sfn "${SOURCE_JKS}" "${CLAUDE_DIR}/jks"
  echo "  ✓ 已链接 Claude Code 专属入口: ${CLAUDE_DIR}/jks"
fi

echo ""
echo "🎉 安装完成！你可以在 豆包、WorkBuddy、Claude Code 或任何 Agent 中使用："
echo "   - 输入「/jks」开始使用或获取推荐"
echo "   - 输入「/jks 001」直接执行第 001 号视频技能"
echo "   - 输入「/jks list」查看当前所有发布的编号与隐藏款"
