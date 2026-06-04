# Extracting Image Assets Into Drawio

Use this when a source figure contains leaf-level icons, logos, textured glyphs,
or other small components that are not worth recreating as editable vector
shapes.

Do not use `image_crop` as the long-term representation for a dense panel that
has internal structure. Mark that region as `subfigure_crop`, create a nested
subfigure JSON spec for it, set `"expand": true` in the master, and let
`render.py` inline the editable elements. See `subfigure_sync.md`.

The shared renderer supports two flat-spec element types:

- `image`: embed an existing local PNG/JPEG file or data URI
- `image_crop`: crop a region from the original source image and embed it as a
  PNG/JPEG data URI in the generated `.drawio`
- `subfigure_crop`: same initial crop behavior as `image_crop`, but semantically
  means "complex local region to later replace or expand from a nested JSON spec"

Embedded assets are stored inside the drawio XML, so the final `.drawio` does
not need the original image file when moved elsewhere. The renderer uses a
drawio-style-safe data URI form such as `data:image/png%3Bbase64,...` because
raw semicolons inside style values conflict with drawio's style separator.

## Basic Leaf Crop Workflow

Add a source image path at the top level:

```json
{
  "canvas": {"width": 1400, "height": 1120, "background": "#ffffff"},
  "assets": {
    "source": "original.png",
    "crop_dir": "assets/crops"
  },
  "elements": [
    {
      "type": "image_crop",
      "id": "original_lightbulb",
      "crop": [1150, 145, 62, 62],
      "x": 1150,
      "y": 145,
      "w": 62,
      "h": 62,
      "trim": {"tolerance": 8},
      "pad": 2
    }
  ]
}
```

Then render normally:

```bash
python3 references/render.py spec.json
```

When `assets.crop_dir` is set, every `image_crop` without an explicit `asset`
path is also saved as an intermediate PNG:

```text
assets/crops/<element-id>.png
```

This is useful for inspection and later reuse.

## Coordinate Fields

Default `crop` format is `[x, y, width, height]` in source-image pixels.

For corner coordinates, use:

```json
{
  "type": "image_crop",
  "id": "logo",
  "bbox_mode": "corners",
  "crop": [100, 120, 180, 190],
  "x": 300,
  "y": 40,
  "w": 80,
  "h": 70
}
```

Drawio placement uses `x`, `y`, `w`, `h` in diagram coordinates. For one-to-one
recreation from a screenshot, keep the drawio canvas the same size as the source
image and use the same coordinates.

## Trimming and Padding

`pad` expands the crop before embedding.

`trim` removes solid border pixels from the crop. It compares against the
top-left crop pixel by default:

```json
"trim": true
```

For a known background color:

```json
"trim": {"background": "#ffffff", "tolerance": 10}
```

Use trim for isolated icons on a plain background. Do not use trim for icons
where the surrounding whitespace is intentional for alignment.

## Direct Image Embedding

Embed a local image file:

```json
{
  "type": "image",
  "id": "gpu_bitmap",
  "path": "assets/gpu.png",
  "x": 60,
  "y": 276,
  "w": 40,
  "h": 34
}
```

Embed an existing data URI:

```json
{
  "type": "image",
  "id": "icon",
  "data": "data:image/png;base64,...",
  "x": 10,
  "y": 10,
  "w": 32,
  "h": 32
}
```

## Reusable Crop Assets

For repeated icons, crop once into a named asset and reuse that file with
`type: "image"`:

```json
[
  {
    "type": "image_crop",
    "id": "worker_gpu_seed",
    "crop": [972, 635, 33, 30],
    "asset": "assets/icons/gpu_worker.png",
    "x": 972,
    "y": 635,
    "w": 33,
    "h": 30
  },
  {
    "type": "image",
    "id": "worker_gpu_copy",
    "path": "assets/icons/gpu_worker.png",
    "x": 1019,
    "y": 635,
    "w": 33,
    "h": 30
  }
]
```

This keeps repeated icons visually identical and leaves a stable intermediate
asset file for future diagrams.

`image_crop` also supports `reuse: true` with `asset`/`asset_path`; if the asset
file already exists, the renderer embeds it instead of cropping again.

## Leaf Icon Rule

When a symbol appears inside a larger editable panel and the symbol itself has
no meaningful internal structure for the diagram, keep that symbol as one image
cell. Example: in a value-symmetry panel, recreate the panel, labels, formulas,
arrows, and asset boxes as editable cells, but keep a detailed balance/scale
symbol as one cropped `scale_icon` image cell rather than redrawing its internal
strokes.

## Tradeoff

Bitmap crops improve visual fidelity but are not internally editable. Use them
only for leaf components where exact appearance matters more than editability.
Keep boxes, arrows, labels, formulas, axes, and layout scaffolding as drawio
shapes whenever possible.
