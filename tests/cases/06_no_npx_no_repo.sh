#!/usr/bin/env bash
# 用例 6：副本安装，本机无 npx → 如实报告无法升级，退出码非 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "no_npx_no_repo"
trap teardown_case EXIT

make_copy_install

# 构造一个完全没有 npx 的 PATH（保留基础命令所在目录）
clean_bin="$CASE_TMP/clean-bin"
mkdir -p "$clean_bin"
for cmd in bash sh cat sed awk grep mkdir cp chmod dirname readlink printf echo date git python3 curl tr uname; do
  src="$(command -v "$cmd" 2>/dev/null || true)"
  if [ -n "$src" ]; then
    ln -sf "$src" "$clean_bin/$cmd"
  fi
done
export PATH="$clean_bin"

if command -v npx >/dev/null 2>&1; then
  echo "SKIP: 无法构造无 npx 环境"
  exit 0
fi

output="$(bash "$COPY_SKILL_DIR/scripts/upgrade.sh" 2>&1)"
code=$?

if [ "$code" -eq 0 ]; then
  echo "FAIL: 无 npx 且非源码安装时退出码应为非 0，实际为 0"
  echo "  输出: $output"
  exit 1
fi
assert_output_contains "$output" "本机没有 npx" || exit 1
echo "PASS: 副本安装且无 npx 时，如实报告无法升级，退出码非 0。"
exit 0
