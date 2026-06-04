# Drawio Codex Skill

Standalone repository for the `drawio` Codex skill.

## Contents

- `SKILL.md` and `references/`: the skill instructions and deterministic helper scripts.
- `drawio/`: diagrams.net/drawio webapp as a git submodule.
- `drawio-export/`: bundled CLI exporter code for PNG/SVG verification.

## Install

Clone with submodules:

```bash
git clone --recurse-submodules <repo-url> drawio-skill
cd drawio-skill
./install.sh
```

If the repository was cloned without submodules:

```bash
git submodule update --init --recursive
./install.sh
```

Install exporter dependencies too:

```bash
./install.sh --with-deps
```

The installer copies the repository into:

```text
$CODEX_HOME/skills/drawio
```

`CODEX_HOME` defaults to `~/.codex`.

## Exporter

After installing npm dependencies, verify a `.drawio` file with:

```bash
drawio-export/scripts/drawio-export.sh input.drawio output.png --scale 1 --timeout 30000
```

The exporter loads `drawio-export/export-cli.html`, which uses the sibling
`drawio/` submodule's webapp assets.
