#!/usr/bin/env bash
# 用例 10：refresh-followers.py 的解析与快照写入规则
# 同样不碰网络和浏览器，只测「页面文本 → 粉丝数」和「一样本怎么并进快照」。
# 认错标签不会报错，只会把「粉丝指数」当成粉丝数然后一直错下去，所以单独看住。
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "refresh_followers"
trap teardown_case EXIT

output="$(python3 "$REPO_ROOT/tests/test-refresh-followers.py" 2>&1)"
code=$?

assert_exit_code 0 "$code" || {
  printf '%s\n' "$output"
  exit 1
}
assert_output_contains "$output" "PASS:" || exit 1

# 校验脚本本身也要能跑：真源是仓库里的 data/followers.jsonl
check_output="$(node "$REPO_ROOT/scripts/check-followers.mjs" 2>&1)"
check_code=$?
assert_exit_code 0 "$check_code" || {
  printf '%s\n' "$check_output"
  exit 1
}

echo "PASS: 粉丝数解析、快照写入与 check-followers 校验均正确。"
exit 0
