# Drawio Codex Skill

Turn draw.io diagrams into something an AI coding agent can read, edit,
recreate, split, and visually verify.

This skill gives Codex a practical workflow for working with
diagrams.net / draw.io files as code: parse the XML, generate editable diagrams
from JSON specs, decompose dense paper figures into nested subfigures, reuse
leaf icons as image assets, and export PNG/SVG previews for visual checks.

## Why This Exists

Draw.io files are editable, portable, and paper-friendly, but they are awkward to
modify programmatically. This repository packages the conventions and tooling
needed to let Codex do useful diagram work without turning the final result into
a flattened PNG.

Use it when you want to:

- recreate a complex figure as an editable `.drawio`
- keep a master figure editable while developing local subfigures separately
- split a large `.drawio` into smaller diagrams
- crop only true leaf icons while rebuilding panels, arrows, labels, and formulas
- export deterministic PNG/SVG previews from generated `.drawio` files
- teach Codex new drawio XML patterns from before/after examples

## Quick Install

```bash
git clone --recurse-submodules https://github.com/z2512690268/drawio-skill.git
cd drawio-skill
./install.sh
```

Install PNG/SVG export dependencies too:

```bash
./install.sh --with-deps
```

The installer copies the skill into:

```text
${CODEX_HOME:-$HOME/.codex}/skills/drawio
```

If you cloned without submodules:

```bash
git submodule update --init --recursive
./install.sh
```

## Minimal Workflow

Render a JSON spec into an editable drawio file:

```bash
python3 references/render.py figure_spec.json
```

Export a visual preview:

```bash
drawio-export/scripts/drawio-export.sh figure_spec.drawio figure_spec.png --scale 1 --timeout 30000
```

For complex paper figures, the preferred model is:

```text
master JSON
  ├─ editable drawio primitives
  ├─ leaf image crops for single icons
  └─ nested JSON subfigures for dense local panels

render.py
  ↓
one complete editable master .drawio
```

Subfigures are expanded into the master drawio as editable cells. They are not
synced back as PNG screenshots.

## What Is Included

```text
drawio-skill/
  SKILL.md                 # agent entrypoint and workflow guide
  references/              # renderer, analyzers, XML/spec docs
  drawio-export/           # bundled PNG/SVG exporter
  drawio/                  # diagrams.net webapp as a git submodule
  install.sh               # local skill installer
```

`drawio-export` is repository code. `drawio/` is a submodule that provides the
diagrams.net webapp assets used by the exporter.

## Notes

- Final artifacts should remain editable `.drawio` files whenever possible.
- Use `image_crop` for leaf icons only.
- Use nested JSON subfigures for complex regions with internal structure.
- If Chromium fails under sandboxing during export, rerun the export command with
  elevated permissions in Codex.
