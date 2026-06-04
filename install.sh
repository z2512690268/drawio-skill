#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-$HOME/.codex}"
TARGET_DIR="${DRAWIO_SKILL_TARGET:-$CODEX_HOME_DIR/skills/drawio}"
WITH_DEPS=0

for arg in "$@"; do
	case "$arg" in
		--with-deps) WITH_DEPS=1 ;;
		-h|--help)
			cat <<'EOF'
Install the drawio Codex skill.

Usage:
  ./install.sh              Copy the skill into $CODEX_HOME/skills/drawio
  ./install.sh --with-deps  Also install drawio-export npm deps and Chromium

Environment:
  CODEX_HOME             Defaults to ~/.codex
  DRAWIO_SKILL_TARGET    Overrides install target
EOF
			exit 0
			;;
		*)
			echo "Unknown option: $arg" >&2
			exit 2
			;;
	esac
done

if [ ! -f "$ROOT_DIR/drawio/src/main/webapp/js/app.min.js" ]; then
	echo "drawio submodule is missing." >&2
	echo "Run: git submodule update --init --recursive" >&2
	exit 1
fi

mkdir -p "$(dirname "$TARGET_DIR")"

rsync -a --delete \
	--exclude '.git' \
	--exclude '.gitmodules' \
	--exclude 'node_modules' \
	--exclude '__pycache__' \
	"$ROOT_DIR/" "$TARGET_DIR/"

chmod +x "$TARGET_DIR/drawio-export/scripts/drawio-export.sh"

echo "Installed drawio skill to: $TARGET_DIR"

if [ "$WITH_DEPS" -eq 1 ]; then
	npm --prefix "$TARGET_DIR/drawio-export" install
	npx --prefix "$TARGET_DIR/drawio-export" playwright install chromium
else
	cat <<EOF

Optional exporter dependencies were not installed.
To enable PNG/SVG export, run:
  npm --prefix "$TARGET_DIR/drawio-export" install
  npx --prefix "$TARGET_DIR/drawio-export" playwright install chromium
EOF
fi
