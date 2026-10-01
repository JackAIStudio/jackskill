#!/usr/bin/env bash
# 用例 2：软链接安装，远端有新提交，工作区干净 → 走 git pull --rebase，软链接保持，退出码 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "symlink_new_clean"
trap teardown_case EXIT

make_source_repo "$CASE_TMP/repo"
setup_origin "$CASE_TMP/repo"
make_remote_ahead "$CASE_TMP/repo" "$CASE_ORIGIN"
make_symlink_install "$CASE_TMP/repo"

# 同步前先记录本地 HEAD，验证升级后 HEAD 确实前进
head_before="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"

output="$(bash "$CASE_TMP/repo/skills/jack/scripts/upgrade.sh" 2>&1)"
code=$?

head_after="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"

assert_exit_code 0 "$code" || exit 1
assert_output_contains "$output" "已从源码仓库同步最新版本" || exit 1
assert_symlink_intact "$SYMLINK_PATH" "$CASE_TMP/repo/skills/jack" || exit 1
if [ "$head_before" = "$head_after" ]; then
  echo "FAIL: 远端有新提交但本地 HEAD 未前进，升级未生效"
  exit 1
fi
echo "PASS: 软链接安装且远端有新提交（干净工作区）时，git 同步成功，软链接保持。"
exit 0
