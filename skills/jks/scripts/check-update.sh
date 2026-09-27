#!/usr/bin/env bash
# jkskill 版本检查：24 小时内最多联网一次，有新版时输出一行用户提醒。
set -uo pipefail

LOCAL_VERSION="${1:-1.0.0}"
JKS_DIR="$HOME/.jks"
CACHE_FILE="$JKS_DIR/update_check_at"
REMOTE_URL="${JKS_UPDATE_URL:-https://raw.githubusercontent.com/JackAIStudio/jkskill/main/UPDATE.json}"
CACHE_TTL=86400

if [[ ! "$LOCAL_VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]; then
  exit 0
fi

NOW="$(date +%s)"
if [ -f "$CACHE_FILE" ]; then
  LAST_CHECK="$(tr -d '[:space:]' < "$CACHE_FILE" 2>/dev/null || true)"
  if [[ "$LAST_CHECK" =~ ^[0-9]+$ ]] && [ "$NOW" -ge "$LAST_CHECK" ] && [ $((NOW - LAST_CHECK)) -lt "$CACHE_TTL" ]; then
    exit 0
  fi
fi

mkdir -p "$JKS_DIR" 2>/dev/null || exit 0
printf '%s\n' "$NOW" > "$CACHE_FILE" 2>/dev/null || exit 0

# 超时时间设为 3 秒，防止阻塞对话
PAYLOAD="$(curl -fsS --max-time 3 "$REMOTE_URL" 2>/dev/null || true)"
[ -n "$PAYLOAD" ] || exit 0

parse_with_python() {
  python3 -c '
import json, re, sys
try:
    data = json.load(sys.stdin)
    version = data.get("version", "")
    notice = data.get("notice", "")
    if not isinstance(version, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        raise ValueError
    if not isinstance(notice, str) or not 1 <= len(notice.strip()) <= 100:
        raise ValueError
    print(f"{version}\t{notice.strip()}", end="")
except Exception:
    sys.exit(1)
'
}

if command -v python3 >/dev/null 2>&1; then
  PARSED="$(printf '%s' "$PAYLOAD" | parse_with_python 2>/dev/null || true)"
else
  exit 0
fi

[[ "$PARSED" == *$'\t'* ]] || exit 0
REMOTE_VERSION="${PARSED%%$'\t'*}"
NOTICE="${PARSED#*$'\t'}"

version_is_higher() {
  local remote_major remote_minor remote_patch local_major local_minor local_patch
  IFS=. read -r remote_major remote_minor remote_patch <<< "$1"
  IFS=. read -r local_major local_minor local_patch <<< "$2"
  if ((10#$remote_major != 10#$local_major)); then
    ((10#$remote_major > 10#$local_major))
  elif ((10#$remote_minor != 10#$local_minor)); then
    ((10#$remote_minor > 10#$local_minor))
  else
    ((10#$remote_patch > 10#$local_patch))
  fi
}

if version_is_higher "$REMOTE_VERSION" "$LOCAL_VERSION"; then
  printf 'jkskill v%s：%s 回复 1，我现在帮你更新。\n' "$REMOTE_VERSION" "$NOTICE"
fi
