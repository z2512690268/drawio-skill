---
name: drawio
description: Read, analyze, modify, create, split, recreate, and visually verify .drawio diagrams. Use for diagrams.net/draw.io XML editing, JSON-spec-to-drawio rendering, nested editable subfigures, crop/icon handling, drawio export, and learning new drawio XML patterns from before/after examples.
---

# Drawio Diagram Skill

Use this skill to produce editable diagrams.net / draw.io artifacts. Prefer
editable drawio cells over pasted bitmaps; use raster crops only for leaf icons
or temporary scaffolding.

## Choose the Workflow

- **Inspect or edit an existing `.drawio`**: read `references/format.md`, parse
  XML cells, modify only the necessary cells, then visually export if possible.
- **Create or recreate a paper figure**: use the JSON spec renderer in
  `references/render.py`. Read `references/spec_workflow.md` for element types,
  layout conventions, and commands.
- **Handle dense local regions**: model them as nested JSON subfigures. Read
  `references/subfigure_sync.md`.
- **Handle icons or image fragments**: read `references/image_assets.md`. Use
  `image_crop` for leaf icons only; use `subfigure_crop` for regions with
  internal structure.
- **Split a large `.drawio` into parts**: use
  `references/split_drawio.py`; read the splitting notes below first.
- **Export PNG/SVG for visual checking**: use the bundled exporter and read
  `references/export.md` for setup and failure modes.
- **Use built-in drawio icon libraries**: read `references/stencils.md`.

## Core Commands

Render a JSON spec:

```bash
python3 references/render.py spec.json
```

Analyze a rendered spec layout:

```bash
python3 references/analyze_layout.py spec.json
```

Export a drawio file from this repository or an installed skill directory:

```bash
drawio-export/scripts/drawio-export.sh input.drawio output.png --scale 1 --timeout 30000
```

If Chromium fails under sandboxing with `Operation not permitted`, rerun the
same export command with escalated permissions.

## JSON Spec Rules

The renderer supports two modes:

- **Structured architecture specs**: hierarchical containers, hbox/vbox layout,
  cells, text, titles, groups, and constraints.
- **Flat recreation specs**: a top-level `elements` list with absolute-position
  primitives for pixel-level figure recreation.

Flat specs support `rect`, `text`, `ellipse`, `rhombus`, `edge`, `image`,
`image_crop`, `subfigure_crop`, `gpu_icon`, `hourglass`, and `lightbulb`.
Read `references/spec_workflow.md` before changing renderer behavior or authoring
a nontrivial spec.

## Nested Subfigures

For complex figures, the master JSON should remain the complete figure. Dense
regions can live in separate editable subfigure JSON files and be expanded into
the master at render time:

```json
{
  "type": "subfigure_crop",
  "id": "value_symmetry",
  "x": 1549,
  "y": 356,
  "w": 578,
  "h": 172,
  "spec": "subfigures/value_symmetry/value_symmetry_spec.json",
  "expand": true
}
```

`render.py` loads the nested spec, resolves its assets relative to that spec,
prefixes inserted IDs with `<parent-id>__`, offsets geometry by parent `x/y`,
and writes one complete editable master `.drawio`.

Do not sync a subfigure back as a PNG. Use PNG crops only as temporary
scaffolding or leaf-level icons. `references/sync_subfigures.py` is a legacy
migration helper for older `.drawio`-only subfigure workflows.

## Splitting Existing Drawio Files

When asked to split a `.drawio` file:

1. Parse cells into vertices, edges, and parent-child groups.
2. Cluster vertices by rectangle distance; default epsilon is about 200 px.
3. Assign edges to the cluster containing their source/target vertices.
4. Recursively include child cells whose parent is in the cluster.
5. Shift each cluster to an origin with padding and preserve valid root cells.

Use:

```bash
python3 references/split_drawio.py input.drawio output_dir
```

Tune clustering manually when the visual result is wrong; spatial proximity is a
heuristic, not semantic understanding.

## Visual Verification

After creating or modifying `.drawio`:

1. Render or edit the `.drawio`.
2. Export to PNG/SVG with `drawio-export/scripts/drawio-export.sh`.
3. Inspect the image for blank output, clipping, overlap, bad routing, bad
   z-order, or obvious mismatch.
4. Iterate on the spec/XML.
5. Give the user both `.drawio` and exported image paths.

Avoid passing `--background` if the drawio XML already has a background
attribute; see `references/export.md`.

## Learning New Patterns

When a requested operation depends on an unknown drawio XML pattern, ask the user
for before/after `.drawio` examples. Diff cells by id, geometry, style, value,
parent, source/target, and child structure. Generalize the pattern and append the
result to `references/learned_patterns.md`.

## Pitfalls

- Every `.drawio` needs root cells `id="0"` and `id="1" parent="0"`.
- Vertex geometry is normally self-closing; edge geometry may contain points.
- Group child coordinates are relative to the group.
- IDs must be unique; prefix IDs when merging or expanding diagrams.
- Edge entry/exit coordinates are normalized values in `[0, 1]`.
- Text content is HTML-encoded; LaTeX uses `$$...$$` with math enabled.
