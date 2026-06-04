# Nested Subfigure JSON

Use this workflow for complex paper-figure recreation when the master figure
must stay complete, but dense local regions need their own editable specs.

## Model

- `subfigure_crop`: semantic region with internal structure. It can start as a
  crop placeholder, then graduate to a nested JSON subfigure.
- `image_crop`: leaf visual asset with no planned internal structure. Use it
  for single icons, logos, tiny pictograms, and hard-to-vectorize symbols.
- Master output should be one complete `.drawio`; subfigures are JSON modules
  expanded by `render.py`, not PNGs pasted into the master.

## Preferred Workflow

1. In the master flat spec, mark dense regions as `subfigure_crop`.
2. For a region you want to decompose, create:

```text
subfigures/<id>/<id>_spec.json
```

3. In the master element, add `spec` and `expand`:

```json
{
  "type": "subfigure_crop",
  "id": "value_symmetry",
  "crop": [1549, 356, 578, 172],
  "x": 1549,
  "y": 356,
  "w": 578,
  "h": 172,
  "spec": "subfigures/value_symmetry/value_symmetry_spec.json",
  "expand": true
}
```

4. Put local coordinates in the subfigure JSON, starting near `(0, 0)`:

```json
{
  "canvas": {"width": 578, "height": 172, "background": "#ffffff"},
  "assets": {
    "source": "../../../pic_20260604151434_2141_257.png",
    "crop_dir": "assets/crops"
  },
  "elements": [
    {"type": "rect", "id": "panel", "x": 1, "y": 2, "w": 576, "h": 167},
    {"type": "text", "id": "title", "x": 151, "y": 12, "w": 276, "h": 34,
     "text": "<b>Value Symmetry (<i>C<sub>sym</sub></i>)</b>"},
    {"type": "image_crop", "id": "scale_icon", "crop": [1765, 440, 102, 48],
     "x": 216, "y": 84, "w": 102, "h": 48}
  ]
}
```

5. Render the master:

```bash
python3 references/render.py trace_guard_spec.json
```

## Render Semantics

When a `subfigure_crop` has `"expand": true` and `"spec": ...`, `render.py`:

- Loads the referenced subfigure JSON.
- Temporarily resolves assets relative to the subfigure spec directory.
- Inlines each subfigure element into the master drawio.
- Prefixes every inserted ID with `<parent-id>__`.
- Adds parent `x/y` to vertex coordinates.
- Adds parent `x/y` to edge `sourcePoint`, `targetPoint`, and `points`.
- Prefixes edge `source` and `target` IDs when present.
- Avoids resaving crop assets while expanding nested specs.

If `expand` or `spec` is absent, `subfigure_crop` falls back to an image crop
placeholder for source-faithful scaffolding.

## Recreating Dense Regions

- Recreate containers, labels, formulas, arrows, and simple shapes as editable
  drawio primitives in the subfigure JSON.
- Keep true leaf icons as single `image_crop` or `image` cells. Example: a
  balance/scale symbol inside a value-symmetry panel should be one
  `scale_icon` image cell, while the surrounding panel, labels, formula, and
  arrows remain editable.
- Use local coordinates in subfigure specs. Do not pre-add the parent offset.
- Keep subfigure IDs short and semantic; render will add the parent prefix.

## Validation

After rendering:

```bash
python3 -c "import xml.etree.ElementTree as ET; ET.parse('trace_guard_spec.drawio')"
drawio-export/scripts/drawio-export.sh trace_guard_spec.drawio trace_guard_spec.png --scale 1 --timeout 60000
```

Inspect the PNG. Check for misplaced text, clipped icons, bad z-order, and
that expanded cells use IDs such as `value_symmetry__panel`.

## Legacy XML Cell Sync

`references/sync_subfigures.py` can still extract and sync editable cells from
older `.drawio`-only workflows. Use it only as a migration helper when there is
no subfigure JSON yet. Prefer creating nested JSON specs for new work.
