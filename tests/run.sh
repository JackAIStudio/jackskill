#!/usr/bin/env bash
# JackSkill 测试入口：依次跑 tests/cases/ 下所有用例，任一失败即整体失败。
# 用法：
#   ./tests/run.sh           跑全部用例
#   ./tests/run.sh 01 03     只跑指定编号的用例
set -uo pipefail

TESTS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASES_DIR="$TESTS_ROOT/cases"

pass=0
fail=0
declare -a failed_cases

run_case() {
  local script="$1"
  local name
  name="$(basename "$script")"
  printf '▸ %s ... ' "$name"
  local out
  out="$(bash "$script" 2>&1)"
  local code=$?
  if [ "$code" -eq 0 ]; then
    # 用例自己 echo 了 PASS: ... 摘要
    local summary
    summary="$(printf '%s\n' "$out" | grep '^PASS:' | head -1 | sed 's/^PASS: //')"
    if [ -n "$summary" ]; then
      printf 'OK  %s\n' "$summary"
    else
      printf 'OK\n'
    fi
    pass=$((pass + 1))
  else
    printf 'FAIL\n'
    printf '%s\n' "$out" | sed 's/^/    /'
    fail=$((fail + 1))
    failed_cases+=("$name")
  fi
}

if [ "$#" -gt 0 ]; then
  # 只跑指定编号
  for n in "$@"; do
    for script in "$CASES_DIR/${n}"_*.sh; do
      [ -f "$script" ] && run_case "$script"
    done
  done
else
  for script in "$CASES_DIR"/*.sh; do
    [ -f "$script" ] && run_case "$script"
  done
fi

echo
echo "通过 $pass 个，失败 $fail 个"
if [ "$fail" -gt 0 ]; then
  printf '失败用例：%s\n' "${failed_cases[*]}"
  exit 1
fi
exit 0
