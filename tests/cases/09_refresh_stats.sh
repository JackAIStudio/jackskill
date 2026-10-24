#!/usr/bin/env bash
# 用例 9：refresh-stats.py 的解析与写入规则
# 这里不碰网络和浏览器，只测「页面文本 → 五元组」和「拿到的数该不该写」。
# 列序错了不会报错，只会把点赞写成评论然后一直错下去，所以单独看住。
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "refresh_stats"
trap teardown_case EXIT

output="$(python3 "$REPO_ROOT/tests/test-refresh-stats.py" 2>&1)"
code=$?

assert_exit_code 0 "$code" || {
  printf '%s\n' "$output"
  exit 1
}
assert_output_contains "$output" "PASS:" || exit 1
echo "PASS: refresh-stats 的列序、三平台解析、近似值判定与匹配规则均正确。"
exit 0
