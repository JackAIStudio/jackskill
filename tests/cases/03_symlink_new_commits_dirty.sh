#!/usr/bin/env bash
# 用例 3：软链接安装，远端有新提交，已跟踪文件有未提交改动（不冲突）→
#          autostash 暂存再放回，改动仍是未提交状态，软链接保持，退出码 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "symlink_new_dirty"
trap teardown_case EXIT

make_source_repo "$CASE_TMP/repo"
setup_origin "$CASE_TMP/repo"
make_remote_ahead "$CASE_TMP/repo" "$CASE_ORIGIN"
make_symlink_install "$CASE_TMP/repo"

# 改一个已跟踪、且远端这次没动的文件。未跟踪新文件不经 autostash 也会留下，证明不了暂存再放回。
marker="LOCAL_DIRTY_MARKER_$(date +%s%N)"
tracked="$CASE_TMP/repo/skills/jack/scripts/upgrade.sh"
echo "# $marker" >> "$tracked"
head_before="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"

output="$(bash "$tracked" 2>&1)"
code=$?
head_after="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"

assert_exit_code 0 "$code" || exit 1
assert_output_contains "$output" "已从源码仓库同步最新版本" || exit 1
assert_symlink_intact "$SYMLINK_PATH" "$CASE_TMP/repo/skills/jack" || exit 1
if [ "$head_before" = "$head_after" ]; then
  echo "FAIL: 远端有新提交但本地 HEAD 未前进，升级未生效"
  echo "  输出: $output"
  exit 1
fi
if ! grep -qF "$marker" "$tracked"; then
  echo "FAIL: 已跟踪文件的本地改动在升级后丢失"
  echo "  输出: $output"
  exit 1
fi
if git -C "$CASE_TMP/repo" show "HEAD:skills/jack/scripts/upgrade.sh" | grep -qF "$marker"; then
  echo "FAIL: 本地未提交改动被写进了提交"
  exit 1
fi
if git -C "$CASE_TMP/repo" diff HEAD --quiet -- skills/jack/scripts/upgrade.sh; then
  echo "FAIL: 本地改动不再是未提交状态，autostash 没有把改动放回来"
  echo "  输出: $output"
  exit 1
fi
echo "PASS: 软链接安装且远端有新提交（已跟踪文件有未提交改动）时，改动仍在工作区，软链接保持。"
exit 0
