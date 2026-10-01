#!/usr/bin/env bash
# 用例 7：--dry-run 经软链接调用时应认出软链接安装；直接调用仓库内脚本应认出实体目录。
#          两种调用都只读，不改 HEAD。
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "dry_run_symlink"
trap teardown_case EXIT

make_source_repo "$CASE_TMP/repo"
setup_origin "$CASE_TMP/repo"
make_remote_ahead "$CASE_TMP/repo" "$CASE_ORIGIN"
make_symlink_install "$CASE_TMP/repo"

head_before="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"
# macOS 上 mktemp 返回 /var/...，pwd -P 解析后是 /private/var/...，断言前规范化
expected_repo="$(cd "$CASE_TMP/repo" && pwd -P)"

output="$(bash "$SYMLINK_PATH/scripts/upgrade.sh" --dry-run 2>&1)"
code=$?
assert_exit_code 0 "$code" || exit 1
assert_output_contains "$output" "dry-run" || exit 1
assert_output_contains "$output" "未执行任何写操作" || exit 1
assert_output_contains "$output" "形态：软链接安装" || exit 1
assert_output_contains "$output" "仓库根：$expected_repo" || exit 1

output_rel="$(cd "$SYMLINK_PATH/scripts" && bash ./upgrade.sh --dry-run 2>&1)"
code_rel=$?
assert_exit_code 0 "$code_rel" || exit 1
assert_output_contains "$output_rel" "形态：软链接安装" || exit 1

# 直接跑真实路径。/var -> /private/var 不能把这里判成软链接。
output_real="$(bash "$CASE_TMP/repo/skills/jack/scripts/upgrade.sh" --dry-run 2>&1)"
code_real=$?
assert_exit_code 0 "$code_real" || exit 1
assert_output_contains "$output_real" "形态：实体目录" || exit 1
if printf '%s\n' "$output_real" | grep -qF "形态：软链接安装"; then
  echo "FAIL: 直接调用仓库内脚本被判成了软链接安装"
  echo "  输出: $output_real"
  exit 1
fi

head_after="$(git -C "$CASE_TMP/repo" rev-parse HEAD)"
if [ "$head_before" != "$head_after" ]; then
  echo "FAIL: dry-run 修改了仓库状态（HEAD 发生变化）"
  exit 1
fi
assert_symlink_intact "$SYMLINK_PATH" "$CASE_TMP/repo/skills/jack" || exit 1
echo "PASS: --dry-run 经软链接认出软链接安装，直接调用认出实体目录，且未写盘。"
exit 0
