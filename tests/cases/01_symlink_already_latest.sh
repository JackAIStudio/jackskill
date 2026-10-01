#!/usr/bin/env bash
# 用例 1：软链接安装，且远端无新提交 → 应直接返回「已是最新」，软链接保持，退出码 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "symlink_already_latest"
trap teardown_case EXIT

# 搭一个源码仓库 + origin，让用户仓库已最新
make_source_repo "$CASE_TMP/repo"
setup_origin "$CASE_TMP/repo"
make_symlink_install "$CASE_TMP/repo"

# 调假仓库里那份 upgrade.sh，让 resolve_self 落在假仓库里
output="$(bash "$CASE_TMP/repo/skills/jack/scripts/upgrade.sh" 2>&1)"
code=$?

assert_exit_code 0 "$code" || exit 1
assert_output_contains "$output" "已是最新版本" || exit 1
assert_symlink_intact "$SYMLINK_PATH" "$CASE_TMP/repo/skills/jack" || exit 1
echo "PASS: 软链接安装且无新提交时，正确识别为已最新，软链接保持。"
exit 0
