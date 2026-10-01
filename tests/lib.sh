#!/usr/bin/env bash
# 测试公共函数：每个用例在独立临时目录里搭环境，结束自动清理。
# 用法：在用例开头 . "$(dirname "$0")/lib.sh"，然后使用 make_* / assert_* 系列函数。

set -uo pipefail

TESTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_ROOT/.." && pwd)"
UPGRADE_SH="$REPO_ROOT/skills/jack/scripts/upgrade.sh"
CHECK_UPDATE_SH="$REPO_ROOT/skills/jack/scripts/check-update.sh"

# 每个用例一个临时 HOME 与一个临时工作区，避免污染真实环境
setup_case() {
  CASE_NAME="$1"
  CASE_TMP="$(mktemp -d -t "jackskill-test-${CASE_NAME}-XXXXXX")"
  CASE_HOME="$CASE_TMP/home"
  mkdir -p "$CASE_HOME"
  # 让 upgrade.sh 的 $HOME 指向临时目录，防止 npx / git 读到真实 ~/.agents
  export HOME="$CASE_HOME"
  # 隔离 git 配置，防止读到用户全局配置
  export GIT_CONFIG_GLOBAL=/dev/null
  export GIT_CONFIG_SYSTEM=/dev/null
  # 默认使用仓库内真实的 upgrade.sh / check-update.sh
  PATH_ORIG="$PATH"
}

teardown_case() {
  if [ -n "${CASE_TMP:-}" ] && [ -d "$CASE_TMP" ]; then
    rm -rf "$CASE_TMP"
  fi
}

# 在 $CASE_TMP 下造一个源码仓库（含 skills/jack/SKILL.md），并初始化 git
# 用法：make_source_repo <目录>
make_source_repo() {
  local repo="$1"
  mkdir -p "$repo/skills/jack/scripts"
  echo "---" > "$repo/skills/jack/SKILL.md"
  echo "name: jack" >> "$repo/skills/jack/SKILL.md"
  cp "$UPGRADE_SH" "$repo/skills/jack/scripts/upgrade.sh"
  chmod +x "$repo/skills/jack/scripts/upgrade.sh"
  git -C "$repo" init -q
  git -C "$repo" config user.email "test@example.com"
  git -C "$repo" config user.name "test"
  git -C "$repo" add -A
  git -C "$repo" commit -q -m "init"
}

# 在远端 origin 上新增一个提交，使本地仓库落后于远端
# 用法：make_remote_ahead <本地仓库> <origin 仓库>
make_remote_ahead() {
  local repo="$1" origin="$2"
  local clone="$CASE_TMP/remote-work"
  git clone -q "$origin" "$clone"
  git -C "$clone" config user.email "test@example.com"
  git -C "$clone" config user.name "test"
  echo "new content $(date +%s%N)" >> "$clone/skills/jack/SKILL.md"
  git -C "$clone" add -A
  git -C "$clone" commit -q -m "remote update"
  git -C "$clone" push -q origin HEAD
}

# 给源码仓库配置一个本地 bare origin 并设为上游
# 用法：setup_origin <本地仓库>；origin 路径写入 $CASE_ORIGIN
setup_origin() {
  local repo="$1"
  CASE_ORIGIN="$CASE_TMP/origin.git"
  git init -q --bare "$CASE_ORIGIN"
  git -C "$repo" remote add origin "$CASE_ORIGIN"
  git -C "$repo" push -q -u origin HEAD 2>/dev/null || git -C "$repo" push -q -u origin main 2>/dev/null || git -C "$repo" push -q -u origin master
}

# 造一个假 npx：把它放在 $CASE_TMP/fake-bin 下，PATH 前置后优先生效
# 用法：make_fake_npx <行为>；行为 = success | fail
make_fake_npx() {
  local behavior="${1:-success}"
  local bin="$CASE_TMP/fake-bin"
  mkdir -p "$bin"
  cat > "$bin/npx" <<EOF
#!/usr/bin/env bash
echo "fake-npx 被调用：\$*" >> "$CASE_TMP/npx.log"
case "$behavior" in
  success) exit 0 ;;
  fail)    echo "fake npx 拉取失败" >&2; exit 1 ;;
esac
EOF
  chmod +x "$bin/npx"
  export PATH="$bin:$PATH_ORIG"
}

# 在 $HOME 下造一份「副本安装」形态：~/.agents/skills/jack 是实体目录，不是软链接
# 用法：make_copy_install
make_copy_install() {
  local skill_dir="$HOME/.agents/skills/jack"
  mkdir -p "$skill_dir/scripts"
  echo "---" > "$skill_dir/SKILL.md"
  echo "name: jack" >> "$skill_dir/SKILL.md"
  cp "$UPGRADE_SH" "$skill_dir/scripts/upgrade.sh"
  chmod +x "$skill_dir/scripts/upgrade.sh"
  COPY_SKILL_DIR="$skill_dir"
}

# 在 $HOME 下造一份「软链接安装」形态：~/.agents/skills/jack -> 源码仓库里的 skills/jack
# 用法：make_symlink_install <源码仓库>
make_symlink_install() {
  local repo="$1"
  local link="$HOME/.agents/skills/jack"
  mkdir -p "$(dirname "$link")"
  ln -s "$repo/skills/jack" "$link"
  SYMLINK_PATH="$link"
}

# 断言：软链接仍然指向预期目标
assert_symlink_intact() {
  local link="$1" expected_target="$2"
  if [ ! -L "$link" ]; then
    echo "FAIL: $link 不再是软链接（可能已被替换成副本）"
    return 1
  fi
  local actual
  actual="$(readlink -f "$link")"
  if [ "$actual" != "$(readlink -f "$expected_target")" ]; then
    echo "FAIL: 软链接目标已改变，期望 $expected_target，实际 $actual"
    return 1
  fi
  return 0
}

# 断言：stdout 包含某段文本
assert_output_contains() {
  local output="$1" needle="$2"
  if ! printf '%s' "$output" | grep -qF -- "$needle"; then
    echo "FAIL: 输出未包含期望文本"
    echo "  期望包含: $needle"
    echo "  实际输出: $output"
    return 1
  fi
  return 0
}

# 断言：命令退出码
assert_exit_code() {
  local expected="$1" actual="$2"
  if [ "$expected" -ne "$actual" ]; then
    echo "FAIL: 退出码期望 $expected，实际 $actual"
    return 1
  fi
  return 0
}
