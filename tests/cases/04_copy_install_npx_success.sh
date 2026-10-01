#!/usr/bin/env bash
# 用例 4：副本安装（~/.agents/skills/jack 是实体目录），npx 可用且成功 → 走 CLI，退出码 0
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "copy_npx_ok"
trap teardown_case EXIT

make_copy_install
make_fake_npx "success"

dry="$(bash "$COPY_SKILL_DIR/scripts/upgrade.sh" --dry-run 2>&1)"
dry_code=$?
assert_exit_code 0 "$dry_code" || exit 1
assert_output_contains "$dry" "形态：实体目录" || exit 1
assert_output_contains "$dry" "npx skills add JackAIStudio/jackskill" || exit 1
if [ -f "$CASE_TMP/npx.log" ]; then
  echo "FAIL: dry-run 不应调用 npx"
  echo "  输出: $dry"
  exit 1
fi

output="$(bash "$COPY_SKILL_DIR/scripts/upgrade.sh" 2>&1)"
code=$?

assert_exit_code 0 "$code" || exit 1
assert_output_contains "$output" "已重新拉取最新版本" || exit 1
if [ ! -f "$CASE_TMP/npx.log" ]; then
  echo "FAIL: 副本安装但 fake npx 未被调用，升级走了非预期路径"
  echo "  输出: $output"
  exit 1
fi
if ! grep -q "skills add JackAIStudio/jackskill" "$CASE_TMP/npx.log"; then
  echo "FAIL: fake npx 被调用但参数不对"
  cat "$CASE_TMP/npx.log"
  exit 1
fi
echo "PASS: 副本安装且 npx 成功时，走 CLI 路径并完成升级。"
exit 0
