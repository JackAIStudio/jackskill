#!/usr/bin/env bash
# 用例 11：版本号与页面产物的一致性
#
# 这两件事都不会自己报错，只会悄悄错下去：
#   1. VERSION / UPDATE.json / SKILL.md 里的版本号对不上 —— 用户要么收不到更新提醒，
#      要么收到一条说错版本的提醒；
#   2. 改了 data/ 下的真源却没重跑 build-site.mjs —— 线上页面还是旧数字，
#      而且没有任何人会看见这个错误。
#
# 所以在这里各挡一道。
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "version_sync"
trap teardown_case EXIT

# --- 1. 三处版本号必须一致 ---------------------------------------------------
version_file="$(tr -d '[:space:]' < "$REPO_ROOT/VERSION")"
update_version="$(python3 -c "import json;print(json.load(open('$REPO_ROOT/UPDATE.json'))['version'])")"
skill_version="$(grep -o 'check-update\.sh"[[:space:]]*"[0-9][0-9.]*"' "$REPO_ROOT/skills/jack/SKILL.md" \
  | grep -o '[0-9][0-9.]*' | head -1)"

for pair in "VERSION:$version_file" "UPDATE.json:$update_version" "SKILL.md:$skill_version"; do
  name="${pair%%:*}"
  value="${pair#*:}"
  if [ -z "$value" ]; then
    echo "FAIL: 读不到 ${name} 里的版本号"
    exit 1
  fi
done

if [ "$version_file" != "$update_version" ] || [ "$version_file" != "$skill_version" ]; then
  echo "FAIL: 三处版本号不一致 —— VERSION=${version_file}、UPDATE.json=${update_version}、SKILL.md=${skill_version}"
  echo "      改版本时要三处一起改，否则 check-update.sh 会一直不提醒、或者报一个错的版本。"
  exit 1
fi

# --- 2. 页面产物不能比真源旧 -------------------------------------------------
# build-site.mjs 会先跑 check-data / check-followers，产物存在就说明校验也过了。
for artifact in "$REPO_ROOT/docs/data/videos.json" "$REPO_ROOT/docs/data/followers.json"; do
  if [ ! -f "$artifact" ]; then
    artifact_rel="${artifact#"$REPO_ROOT"/}"
    echo "FAIL: 缺页面产物 ${artifact_rel}，先跑 node scripts/build-site.mjs"
    exit 1
  fi
done

newer="$(find "$REPO_ROOT/data" -name '*.jsonl' -newer "$REPO_ROOT/docs/data/videos.json" -print -quit 2>/dev/null)"
if [ -n "$newer" ]; then
  newer_rel="${newer#"$REPO_ROOT"/}"
  echo "FAIL: ${newer_rel} 比页面产物新，说明改了数据却没重建页面。"
  echo "      跑：node scripts/build-site.mjs"
  exit 1
fi

echo "PASS: 版本号三处一致（${version_file}），页面产物不旧于真源。"
exit 0
