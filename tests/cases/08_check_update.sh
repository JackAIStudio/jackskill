#!/usr/bin/env bash
# 用例 8：check-update.sh —— 旧版本收到提醒，同版本静默
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "check_update"
trap teardown_case EXIT

# 造一个假 UPDATE.json，模拟远端最新版是 9.9.9
fake_update="$CASE_TMP/UPDATE.json"
cat > "$fake_update" <<'EOF'
{
  "version": "9.9.9",
  "notice": "测试提醒：这是一条不该出现在真实环境里的 notice。",
  "updated_at": "2026-01-01"
}
EOF

# check-update.sh 有 24 小时缓存，直接把 JACK_DIR 指向临时目录绕开真实缓存
export JACK_UPDATE_URL="file://$fake_update"

# 8a：本地版本落后 → 应输出提醒
out_old="$(bash "$CHECK_UPDATE_SH" "1.0.0" 2>&1)"
code_old=$?
assert_exit_code 0 "$code_old" || exit 1
assert_output_contains "$out_old" "9.9.9" || exit 1
assert_output_contains "$out_old" "测试提醒" || exit 1

# 8b：本地版本已经是最新 → 应静默（换个干净的 HOME 避免命中 8a 的缓存）
HOME="$CASE_TMP/home-same"
mkdir -p "$HOME"
out_same="$(bash "$CHECK_UPDATE_SH" "9.9.9" 2>&1)"
code_same=$?
assert_exit_code 0 "$code_same" || exit 1
if [ -n "$out_same" ]; then
  echo "FAIL: 本地版本与远端一致时不应输出提醒，实际输出：$out_same"
  exit 1
fi

echo "PASS: check-update.sh 在旧版本时输出提醒，同版本时静默。"
exit 0
