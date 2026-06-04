# JSON Spec Workflow

Use the JSON renderer for architecture diagrams, exact paper-figure recreation,
and editable nested subfigures.

## Pipeline

```text
spec.json  --references/render.py-->  spec.drawio
    |
    '--references/analyze_layout.py--> layout report
```

Commands:

```bash
python3 references/render.py spec.json
python3 references/analyze_layout.py spec.json
```

The complete example is `references/fmrl_spec_example.json`.

## Renderer Modes

### Structured Architecture Specs

Use recursive layout nodes when the diagram has semantic sections, rows, columns,
and aligned components.

Common node types:

| type | Meaning | Key fields | Behavior |
|---|---|---|---|
| `container` | Background block | `id`, `w`, `h`, `fill`, `stroke`, `children` | Draws a rounded frame and offsets children into it |
| `hbox` | Horizontal layout | `gap`, `x0`, `y0`, `children` | Lays children left to right |
| `vbox` | Vertical layout | `gap`, `x0`, `y0`, `children` | Lays children top to bottom |
| `cell` | Box plus text | `w`, `h`, `text`, `fill`, `tc` | Draws a rounded box with centered text |
| `cell` with `rx:true` | Absolute leaf | `x`, `y`, `rx:true` | Uses local absolute coordinates |
| `text` | Label | `cx` or `x`, `y`, `fs` | Draws text only |
| `title` | Container title | `y0`, `fs` | Draws a title inside a container |
| `group` | Semantic grouping | `children` | Pass-through; produces no cell |

Coordinate rules:

- Container positions come from `box.x` / `box.y`.
- Cell and text positions inside containers use local `x0` / `y0`.
- Use `rx:true` when a child should not be auto-arranged by hbox/vbox.
- Text with `cx` is centered by computing its left edge.

Arrow definition:

```json
{
  "id": "arrow_name",
  "from": "src_id",
  "to": "tgt_id",
  "exit": "E",
  "enter": "W",
  "exit_y": 1.0,
  "stroke": "#315f9f",
  "width": 2.5,
  "dashed": true
}
```

`exit` / `enter` use `E`, `W`, `S`, `N`. Override `exit_x`, `exit_y`,
`enter_x`, or `enter_y` when auto anchors route through components.

### Flat Recreation Specs

Use a top-level `elements` list with absolute coordinates when reproducing a
screenshot, plot, or paper figure with pixel-level placement.

Supported element families include:

- Shapes: `rect`, `ellipse`, `rhombus`
- Text and formulas: `text`
- Connectors: `edge`
- Images and crops: `image`, `image_crop`, `subfigure_crop`
- Small built-ins: `gpu_icon`, `hourglass`, `lightbulb`

For one-to-one recreation from a screenshot, set the canvas size to the source
image dimensions and place elements in the same coordinate system.

## Dense Regions

Use `subfigure_crop` for any region that has meaningful internal structure but
is too complex to decompose immediately. It may start as a crop placeholder and
later become an expanded nested JSON spec. Read `subfigure_sync.md` before
creating or syncing subfigures.

Use `image_crop` only for leaf-level visual assets such as one icon, logo, tiny
pictogram, or hard-to-vectorize symbol. Read `image_assets.md`.

## Layout Principles

1. Define section backgrounds first.
2. Put same-row components in `hbox`.
3. Stack rows with `vbox` and explicit `gap`.
4. Use consistent widths/heights for visual rhythm.
5. Use constraints such as `align_top` / `align_bot` when available.
6. Keep text boxes tall enough for the font size; too-short text cells clip.
7. Run `analyze_layout.py` after substantial layout changes.

## Common Issues

- `d.setId is not a function`: an element id conflicts with a JS method or
  reserved name. Rename the id.
- Arrows pass through components: fix `exit` / `enter` directions or override
  anchor coordinates.
- Text overflows: increase width/height or reduce font size.
- hbox/vbox ignores a desired position: mark the child with `rx:true`.
- Container heights differ unintentionally: set matching `h` values manually.
