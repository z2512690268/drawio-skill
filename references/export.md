# Drawio Export Reference

Use the bundled drawio exporter for PNG/SVG visual verification after generating
or modifying `.drawio` files.

## Preferred Command

From the installed skill directory or this repository root:

```bash
drawio-export/scripts/drawio-export.sh input.drawio output.png --scale 1 --timeout 30000
```

If Chromium fails under sandboxing with `Operation not permitted`, rerun the
same command with escalated permissions.

## Formats

```bash
# PNG
drawio-export/scripts/drawio-export.sh input.drawio output.png --scale 1 --timeout 30000

# SVG
drawio-export/scripts/drawio-export.sh input.drawio output.svg --format svg --timeout 30000
```

## Background Option Caveat

Do not pass `--background` if the `.drawio` file already has an
`<mxGraphModel background="...">` attribute.

The current exporter injects background by string replacement:

```js
xml = xmlRaw.replace('<mxGraphModel', '<mxGraphModel background="' + opts.background + '"');
```

If the input already has `background=...`, this creates a duplicate XML
attribute and can export a tiny blank image.

## Bundled Layout

The standalone skill repository contains:

```text
drawio-skill/
  SKILL.md
  references/
  drawio-export/
  drawio/                 # git submodule with diagrams.net webapp
```

The exporter loads `drawio-export/export-cli.html`, which in turn loads the
drawio webapp assets from the sibling `drawio/` submodule.

Install JS dependencies after cloning or installing the skill:

```bash
npm --prefix drawio-export install
npx --prefix drawio-export playwright install chromium
```

If the layout differs, set an environment variable in local docs or a wrapper:

```bash
export DRAWIO_EXPORT=/path/to/drawio-skill/drawio-export/scripts/drawio-export.sh
$DRAWIO_EXPORT diagram.drawio diagram.png --scale 1 --timeout 30000
```

## Quick Health Check

After migration, verify the exporter with any known-good `.drawio` file:

```bash
$DRAWIO_EXPORT example.drawio /tmp/example.png --scale 1 --timeout 30000
test -s /tmp/example.png
```

Also inspect the output image. A non-empty file can still be blank if the input
XML was malformed or if duplicate background attributes were introduced.
