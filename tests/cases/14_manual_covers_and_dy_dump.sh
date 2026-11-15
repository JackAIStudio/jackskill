#!/usr/bin/env bash
# 用例 14：parse-dy-dump 对 saveFull + 折行的解析，以及 fetch-covers --manual 的压图与方向校验
set -uo pipefail
. "$(dirname "$0")/../lib.sh"
setup_case "manual_covers_and_dy_dump"
trap teardown_case EXIT

# --- 1. parse-dy-dump.py 应直接认 bsk saveFull + 折行 StaticText ------------
dy_in="$CASE_TMP/dy_savefull.json"
dy_out="$CASE_TMP/dy_covers.json"

python3 - "$dy_in" <<'PY'
import json, sys
folded_vom = (
    '@vom 1\n'
    'L1 page\n'
    '  RootWebArea "{\\"aweme_list\\":[{\\"aweme_id\\":\\"123"\n'
    '    StaticText "{\\"aweme_list\\":[{\\"aweme_id\\":\\"7708333154834091300\\",\\"item_title\\":\\"测试\\\\\\"标题\\",\\""\n'
    '    StaticText "Cover\\":{\\"url_list\\":[\\"https://example.com/3x4.jpg\\"]},\\"horizontal_cover\\":{\\"url_list\\":[\\"https://example.com/4x3.jpg\\"]}}]}"\n'
    '    form "美观输出"\n'
)
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump({"observation": {"text": folded_vom}}, f, ensure_ascii=False)
PY

parse_out="$(python3 "$REPO_ROOT/scripts/parse-dy-dump.py" --in "$dy_in" --out "$dy_out" 2>&1)"
assert_exit_code 0 "$?" || {
  printf '%s\n' "$parse_out"
  exit 1
}

python3 - "$dy_out" <<'PY'
import json, sys
d = json.load(open(sys.argv[1], encoding="utf-8"))
assert "7708333154834091300" in d, f"missing aweme_id: {d}"
rec = d["7708333154834091300"]
assert rec["title"] == '测试"标题', f"bad title: {rec['title']!r}"
assert rec["covers"]["4x3"]["url"] == "https://example.com/4x3.jpg"
assert rec["covers"]["3x4"]["url"] == "https://example.com/3x4.jpg"
PY
assert_exit_code 0 "$?" || exit 1

# --- 2. fetch-covers.py --manual 在沙盒中压图、写索引并拦住方向错误 --------
sandbox="$CASE_TMP/repo"
mkdir -p "$sandbox/scripts" "$sandbox/data" "$sandbox/docs/covers"
cp "$REPO_ROOT/scripts/fetch-covers.py" "$sandbox/scripts/"
touch "$sandbox/data/videos.jsonl"

img_dir="$CASE_TMP/imgs"
mkdir -p "$img_dir"
python3 - "$img_dir" <<'PY'
import struct, zlib, sys
from pathlib import Path

def write_png(path: Path, w: int, h: int, rgb=(220, 180, 90)):
    def chunk(tag, data):
        return struct.pack("!I", len(data)) + tag + data + struct.pack("!I", zlib.crc32(tag + data) & 0xffffffff)
    row = b"\x00" + bytes(rgb) * w
    raw = row * h
    ihdr = struct.pack("!IIBBBBB", w, h, 8, 2, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    path.write_bytes(png)

d = Path(sys.argv[1])
write_png(d / "c43.png", 1600, 1200)
write_png(d / "c34.png", 1200, 1600)
write_png(d / "c169.png", 1920, 1080)
PY

# 2a. 传反方向（把 3x4 竖图塞进 --cover-4x3）必须报错退出，且不能写盘
bad_out="$(cd "$sandbox" && python3 scripts/fetch-covers.py --manual \
  --date 2026-11-15 \
  --topic "手动 封面 测试" \
  --cover-4x3 "$img_dir/c34.png" 2>&1)"
bad_code=$?
if [ "$bad_code" -eq 0 ]; then
  echo "FAIL: 把竖图塞进 4x3 槽位时 --manual 应当拒绝"
  exit 1
fi
assert_output_contains "$bad_out" "方向和槽位不符" || exit 1
if [ -f "$sandbox/docs/covers/index.json" ]; then
  echo "FAIL: 校验失败时不该生成 index.json"
  exit 1
fi

# 2b. 正确方向应压成 <=800 的 JPEG、记为 manual，并顺利通过 --verify
ok_out="$(cd "$sandbox" && python3 scripts/fetch-covers.py --manual \
  --date 2026-11-15 \
  --topic "手动 封面 测试" \
  --cover-4x3 "$img_dir/c43.png" \
  --cover-3x4 "$img_dir/c34.png" \
  --cover-16x9 "$img_dir/c169.png" 2>&1)"
assert_exit_code 0 "$?" || {
  printf '%s\n' "$ok_out"
  exit 1
}

verify_out="$(cd "$sandbox" && python3 scripts/fetch-covers.py --verify 2>&1)"
assert_exit_code 0 "$?" || {
  printf '%s\n' "$verify_out"
  exit 1
}

python3 - "$sandbox/docs/covers/index.json" <<'PY'
import json, sys
idx = json.load(open(sys.argv[1], encoding="utf-8"))
assert idx["count"] == 1
it = idx["items"][0]
assert it["id"] == "2026-11-15_手动_封面_测试", f"bad id: {it['id']}"
assert it["dir"] == "covers/2026-11-15_手动 封面 测试", f"bad dir: {it['dir']}"
assert it["covers"]["4x3"]["size"] == [800, 600]
assert it["covers"]["3x4"]["size"] == [600, 800]
assert it["covers"]["16x9"]["size"] == [800, 450]
for slot in ("4x3", "3x4", "16x9"):
    assert it["covers"][slot]["source"] == "manual"
    assert it["covers"][slot]["slot"] == slot
PY
assert_exit_code 0 "$?" || exit 1

echo "PASS: parse-dy-dump 支持 saveFull/折行，fetch-covers --manual 压图、建索引与方向拦截均正确。"
exit 0
