#!/usr/bin/env bash
# 用例 13：封面索引的 id 必须和数据记录对得上
#
# 这类错误是静默的：文件都在、索引也写了，页面却整块不显示封面，构建一声不响。
# 实际踩过一次——手工往索引里加 10-26 那条时，id 保留了空格，而记录 id
# 里空格已换成下划线，coversById.get() 永远落空。
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "cover_ids"
trap teardown_case EXIT

# 沙盒：脚本和封面索引复制一份（要改），真源与图片用软链接指回真实仓库
# （只读，不动它）。这样构建能跑通，又不会污染仓库。
sandbox="$CASE_TMP/repo"
mkdir -p "$sandbox/scripts" "$sandbox/docs/covers" "$sandbox/transcripts" "$sandbox/skills/jack/numbered-prompts"
cp "$REPO_ROOT/scripts/build-site.mjs" "$REPO_ROOT/scripts/check-data.mjs" \
   "$REPO_ROOT/scripts/check-followers.mjs" "$sandbox/scripts/"
cp "$REPO_ROOT/docs/covers/index.json" "$sandbox/docs/covers/"
cp "$REPO_ROOT/skills/jack/numbered-prompts/catalog.json" "$sandbox/skills/jack/numbered-prompts/"
ln -s "$REPO_ROOT/data" "$sandbox/data"
ln -s "$REPO_ROOT/transcripts/md" "$sandbox/transcripts/md"

# 封面目录整体软链过来（index.json 已在上面单独复制）
for dir in "$REPO_ROOT"/docs/covers/*/; do
  [ -d "$dir" ] || continue
  ln -s "$dir" "$sandbox/docs/covers/$(basename "$dir")" 2>/dev/null || true
done

# 13a：当前索引应当干净
out="$(cd "$sandbox" && node scripts/build-site.mjs 2>&1)"
if printf '%s' "$out" | grep -q '封面索引'; then
  echo "FAIL: 当前封面索引应当没有对不上的 id，实际报了警："
  printf '%s\n' "$out" | grep '封面索引'
  exit 1
fi

# 13b：把 10-26 那条 id 退回「空格未换下划线」，构建要报警并给出正确写法
python3 - "$sandbox/docs/covers/index.json" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8"))
for it in d["items"]:
    if it.get("date") == "2026-10-26":
        it["id"] = "2026-10-26_AI博主不上班 送外卖 逃避工作"
json.dump(d, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PY
out2="$(cd "$sandbox" && node scripts/build-site.mjs 2>&1)"
assert_output_contains "$out2" "封面索引的 id 与记录对不上" || {
  echo "FAIL: 空格未换成下划线时，构建应当报警"
  printf '%s\n' "$out2" | tail -5
  exit 1
}
assert_output_contains "$out2" "2026-10-26_AI博主不上班_送外卖_逃避工作" || {
  echo "FAIL: 报警里应当直接给出正确的 id 写法"
  exit 1
}

echo "PASS: 封面索引 id 对不上时会报警，并给出正确的 id 写法。"
exit 0
