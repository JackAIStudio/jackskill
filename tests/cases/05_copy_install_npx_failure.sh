#!/usr/bin/env bash
# 用例 5：副本安装，npx 可用但拉取失败 → 如实报告失败原因，退出码非 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "copy_npx_fail"
trap teardown_case EXIT

make_copy_install
make_fake_npx "fail"

output="$(bash "$COPY_SKILL_DIR/scripts/upgrade.sh" 2>&1)"
code=$?

if [ "$code" -eq 0 ]; then
  echo "FAIL: npx 失败时退出码应为非 0，实际为 0"
  echo "  输出: $output"
  exit 1
fi
assert_output_contains "$output" "升级失败" || exit 1
echo "PASS: 副本安装且 npx 失败时，如实报告失败，退出码非 0。"
exit 0
