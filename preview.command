#!/usr/bin/env bash
# macOS 上双击这个文件就能预览数据站，等价于在仓库根目录跑：
#   node scripts/preview.mjs
#
# 会先构建页面数据，再起一个只绑 127.0.0.1 的静态服务器并打开浏览器。
# 弹出的终端窗口就是服务器本体，关掉窗口或在里面按 Ctrl+C 才停。
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
exec node scripts/preview.mjs "$@"
