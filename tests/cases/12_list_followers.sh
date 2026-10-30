#!/usr/bin/env bash
# 用例 12：/jack list 里的粉丝数展示
#
# 三种状态都要对，而且「读不到」绝对不能显示成 0：
#   1. 有两条以上快照 → 显示各平台读数 + 较上次的变化
#   2. 只有一条快照   → 显示读数，并明说「还看不出涨粉」，不编增长率
#   3. 读不到粉丝数据 → 整段不出现（不是显示 0，也不是显示「—」）
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "list_followers"
trap teardown_case EXIT

SCRIPT="$REPO_ROOT/skills/jack/scripts/numbered-prompts.py"

# 在临时目录里搭一个最小仓库根：data/ + transcripts/，再把 skill 复制进去。
make_repo() {
  local root="$1"
  mkdir -p "$root/data" "$root/transcripts/md"
  cp -R "$REPO_ROOT/skills" "$root/"
  # 至少放一篇逐字稿，避免概览因空库报错干扰判断
  local first
  first="$(find "$REPO_ROOT/transcripts/md" -name '*.md' -print -quit)"
  [ -n "$first" ] && cp "$first" "$root/transcripts/md/"
}

# --- 1. 两条快照：应带涨粉 -----------------------------------------------
repo1="$CASE_TMP/repo1"
make_repo "$repo1"
cat > "$repo1/data/followers.jsonl" <<'EOF'
{"date":"2026-10-29","platforms":{"bilibili":{"followers":470},"douyin":{"followers":299}}}
{"date":"2026-10-30","platforms":{"bilibili":{"followers":479},"douyin":{"followers":299}}}
EOF
out1="$(python3 "$repo1/skills/jack/scripts/numbered-prompts.py" list 2>&1)"
assert_output_contains "$out1" "粉丝（2026-10-30）" || exit 1
assert_output_contains "$out1" "B站 479" || exit 1
assert_output_contains "$out1" "+9" || exit 1
assert_output_contains "$out1" "持平" || exit 1

# --- 2. 一条快照：不编趋势 -------------------------------------------------
repo2="$CASE_TMP/repo2"
make_repo "$repo2"
cat > "$repo2/data/followers.jsonl" <<'EOF'
{"date":"2026-10-30","platforms":{"bilibili":{"followers":479}}}
EOF
out2="$(python3 "$repo2/skills/jack/scripts/numbered-prompts.py" list 2>&1)"
assert_output_contains "$out2" "B站 479" || exit 1
assert_output_contains "$out2" "还看不出涨粉" || exit 1
if printf '%s' "$out2" | grep -q '（+'; then
  echo "FAIL: 只有一条快照时不该出现任何涨粉数字"
  exit 1
fi

# --- 3. 没有粉丝数据：整段不出现 -------------------------------------------
repo3="$CASE_TMP/repo3"
make_repo "$repo3"
out3="$(python3 "$repo3/skills/jack/scripts/numbered-prompts.py" list 2>&1)"
if printf '%s' "$out3" | grep -q '^粉丝'; then
  echo "FAIL: 读不到粉丝数据时不该打印粉丝那一行"
  printf '%s\n' "$out3" | head -20
  exit 1
fi

# --- 4. 副本环境（没有 data/）：不能误报，也不能崩 --------------------------
repo4="$CASE_TMP/repo4"
mkdir -p "$repo4"
cp -R "$REPO_ROOT/skills" "$repo4/"
out4="$(python3 "$repo4/skills/jack/scripts/numbered-prompts.py" list 2>&1)"
code4=$?
assert_exit_code 0 "$code4" || {
  echo "FAIL: 只有 skill 副本、没有仓库数据时不该报错退出"
  printf '%s\n' "$out4"
  exit 1
}

echo "PASS: /jack list 的粉丝展示三种状态（有涨粉 / 只有一条 / 读不到）均正确。"
exit 0
