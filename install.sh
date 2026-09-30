#!/usr/bin/env bash
# ==============================================================================
# JackSkill 一键安装与配置脚本 (支持本地运行与远程 curl | bash)
# 支持环境：豆包 Mac、WorkBuddy、Claude Code、Codex、Trae 以及通用 Agents
# ==============================================================================

set -euo pipefail

TARGET_DIR="${HOME}/.jackskill"
REPO_URL="https://github.com/JackAIStudio/jackskill.git"

# 1. 确定源文件所在位置
if [ -t 0 ] && [ -f "$(dirname "${BASH_SOURCE[0]:-$0}")/skills/jack/SKILL.md" ]; then
  # 本地仓库直接运行
  INSTALL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
else
  # 远程 curl | bash 运行，静默安装到 ~/.jackskill
  echo "📦 正在获取 JackSkill 最新代码..."
  if [ -d "${TARGET_DIR}/.git" ]; then
    git -C "${TARGET_DIR}" pull --quiet || true
  else
    mkdir -p "${TARGET_DIR}"
    git clone --quiet --depth=1 "${REPO_URL}" "${TARGET_DIR}"
  fi
  INSTALL_DIR="${TARGET_DIR}"
fi

SOURCE_JACK="${INSTALL_DIR}/skills/jack"

if [ ! -d "${SOURCE_JACK}" ]; then
  echo "❌ 错误：未找到 jack 技能目录：${SOURCE_JACK}"
  exit 1
fi

echo "🚀 开始配置 JackSkill 到本机各 Agent 环境..."

# 2. 通用 Agent 公共入口（豆包 Mac App, Trae, Codex, Cursor, Windsurf 等）
AGENTS_DIR="${HOME}/.agents/skills"
mkdir -p "${AGENTS_DIR}"
ln -sfn "${SOURCE_JACK}" "${AGENTS_DIR}/jack"
echo "  ✓ 已配置通用 Agents 入口: ${AGENTS_DIR}/jack"

# 3. 腾讯 WorkBuddy 专属入口 (若存在 ~/.workbuddy)
if [ -d "${HOME}/.workbuddy" ]; then
  WB_DIR="${HOME}/.workbuddy/skills"
  mkdir -p "${WB_DIR}"
  ln -sfn "${SOURCE_JACK}" "${WB_DIR}/jack"
  echo "  ✓ 已配置 WorkBuddy 专属入口: ${WB_DIR}/jack"
fi

# 4. Claude Code 专属入口 (若存在 ~/.claude)
if [ -d "${HOME}/.claude" ]; then
  CLAUDE_DIR="${HOME}/.claude/skills"
  mkdir -p "${CLAUDE_DIR}"
  ln -sfn "${SOURCE_JACK}" "${CLAUDE_DIR}/jack"
  echo "  ✓ 已配置 Claude Code 专属入口: ${CLAUDE_DIR}/jack"
fi

echo ""
echo "🎉 安装完成！现在可以在 豆包、WorkBuddy、Claude Code 或任何支持的 Agent 中直接使用："
echo "   - 输入「/jack」开始使用或获取推荐"
echo "   - 输入「/jack <编号>」直接执行对应技能（如 /jack 101）"
echo "   - 输入「/jack list」查看当前技能清单"
