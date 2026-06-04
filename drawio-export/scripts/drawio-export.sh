#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLI_JS="$SCRIPT_DIR/../cli.mjs"

show_help() {
	cat <<'EOF'
draw.io CLI Export Tool

从命令行将 .drawio 文件导出为 PNG / SVG，无需图形界面。
基于 draw.io 核心渲染引擎 (app.min.js)，使用与 vscode-drawio 相同的消息通信机制。

用法:
  drawio-export input.drawio output.png             导出 PNG
  drawio-export input.drawio output.svg --format svg 导出 SVG

选项:
  --format png|svg    导出格式 (默认: png)
  --scale NUMBER      缩放比例 (默认: 1)
  --border NUMBER     边距像素 (默认: 0)
  --background COLOR  背景颜色 (例如 #FFFFFF 白底)
  --timeout MS        超时毫秒数 (默认: 30000)
  --no-headless       显示浏览器窗口 (调试用)
  -h, --help          显示此帮助

示例:
  drawio-export diagram.drawio output.png
  drawio-export diagram.drawio output.png --scale 2
  drawio-export diagram.drawio output.svg --format svg

依赖:
  Node.js, Playwright (npm install playwright)
EOF
}

if [ $# -eq 0 ] || [ "$1" = "-h" ] || [ "$1" = "--help" ]; then
	show_help
	exit 0
fi

if [ ! -f "$CLI_JS" ]; then
	echo "Error: cli.mjs not found at $CLI_JS" >&2
	exit 1
fi

exec node "$CLI_JS" "$@"
