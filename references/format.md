---
name: drawio-format
description: Detailed reference documentation for the .drawio XML file format, covering all cell types, geometry patterns, style properties, and common structures.
---

# Drawio XML Format Reference

## Overall File Structure

```xml
<mxfile host="Electron" agent="..." version="29.0.3">
  <diagram name="Page Name" id="page_id">
    <mxGraphModel dx="0" dy="0" grid="1" gridSize="10"
                  guides="1" tooltips="1" connect="1" arrows="1"
                  page="1" pageScale="1"
                  pageWidth="827" pageHeight="1169"
                  background="none" math="0" shadow="0">
      <root>
        <mxCell id="0" />            <!-- root sentinel — ALWAYS required -->
        <mxCell id="1" parent="0" />  <!-- default parent cell — ALWAYS required -->
        <!-- ... diagram content cells ... -->
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

### mxGraphModel Attributes

| Attribute | Description |
|-----------|-------------|
| `dx`, `dy` | Viewport scroll offset in px |
| `pageWidth`, `pageHeight` | Canvas dimensions in px |
| `grid` | 0=off, 1=on |
| `gridSize` | Grid spacing in px |
| `guides` | Alignment guides on/off |
| `background` | Canvas background color or "none" |
| `math` | 0=off, 1=on — enables LaTeX `$$...$$` rendering |
| `shadow` | Global shadow on/off |

## Cell Reference

Every visible or structural element is an `<mxCell>`.

### Cell Attributes

| Attribute | Applies To | Description |
|-----------|-----------|-------------|
| `id` | All | Unique identifier within the file |
| `parent` | All | Parent cell id. Top-level cells have `parent="1"`. Root cells have `parent="0"`. Group children have `parent="<group_id>"` |
| `vertex="1"` | Shapes | Marks this cell as a shape/node |
| `edge="1"` | Connectors | Marks this cell as an edge/connector |
| `source` | Edges | Id of the source vertex |
| `target` | Edges | Id of the target vertex |
| `value` | All | Text content (HTML-encoded; see Text Encoding below) |
| `style` | All | Semicolon-delimited style properties |
| `connectable="0"` | Groups | Prevents drawing edges to/from this cell |

### Root Cells

Every file must have exactly these two root cells:
```xml
<mxCell id="0" />
<mxCell id="1" parent="0" />
```

### Vertex Cells

A shape or node:
```xml
<mxCell id="PA9tXJAimPVp9acHOORb-2" value="F1"
        style="rounded=0;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;"
        parent="1" vertex="1">
  <mxGeometry x="200" y="80" width="50" height="40" as="geometry" />
</mxCell>
```

The `<mxGeometry>` is **self-closing** for vertices. It has `x`, `y`, `width`, `height`.

### Edge Cells

A connector between vertices. Two forms:

**With source/target vertices** (auto-routes using entry/exit points):
```xml
<mxCell id="e1" value="" style="endArrow=classic;html=1;rounded=0;
       exitX=1;exitY=0.5;entryX=0;entryY=0.5;"
       parent="1" source="v1" target="v2" edge="1">
  <mxGeometry relative="1" as="geometry" />
</mxCell>
```

**With absolute coordinates** (no source/target, explicit path):
```xml
<mxCell id="e2" value="" style="endArrow=none;dashed=1;html=1;rounded=0;"
       parent="1" edge="1">
  <mxGeometry width="50" height="50" relative="1" as="geometry">
    <mxPoint x="607.5" y="3756.96" as="sourcePoint" />
    <mxPoint x="607.5" y="3569.96" as="targetPoint" />
  </mxGeometry>
</mxCell>
```

**With waypoints** (intermediate bend points):
```xml
<mxCell id="e3" value="" style="endArrow=classic;html=1;rounded=0;"
       parent="1" edge="1">
  <mxGeometry relative="1" as="geometry">
    <mxPoint x="350" y="150" as="sourcePoint" />
    <mxPoint x="440" y="250" as="targetPoint" />
    <Array as="points">
      <mxPoint x="350" y="140" />
      <mxPoint x="400" y="200" />
    </Array>
  </mxGeometry>
</mxCell>
```

**Important format notes:**
- `sourcePoint`/`targetPoint` use `as="sourcePoint" />` (space before `/>`) — the regex must account for this
- Edges with `source`/`target` attributes may omit explicit sourcePoint/targetPoint (drawio computes from entry/exit)
- `relative="1"` is standard for edges; the mxGeometry x/y/width/height are NOT used for positioning when relative=1

### Group Cells

A container that groups child elements:
```xml
<mxCell id="group1" value="" style="group"
       parent="1" vertex="1" connectable="0">
  <mxGeometry x="100" y="100" width="300" height="200" as="geometry" />
</mxCell>
```

Child cells reference the group as their parent:
```xml
<mxCell id="child1" value="Label" style="text;html=1;"
       parent="group1" vertex="1">
  <mxGeometry x="50" y="30" width="80" height="30" as="geometry" />
</mxCell>
```

**Children use coordinates relative to the group parent.** When extracting/cloning grouped cells, you must either:
- Keep the group structure (preferred), or
- Convert to absolute coordinates by adding the group's x,y

### Text Cells (Labels)

```xml
<mxCell id="label1" value="GPU"
        style="text;html=1;strokeColor=none;fillColor=none;
               align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;"
        parent="1" vertex="1">
  <mxGeometry x="70" y="85" width="60" height="30" as="geometry" />
</mxCell>
```

## mxGeometry Details

### For Vertices

Self-closing tag with position and size:
```xml
<mxGeometry x="200" y="80" width="150" height="40" as="geometry" />
```
- `x`, `y`: Position relative to parent (px)
- `width`, `height`: Size (px)
- `as="geometry"`: Required literal value

### For Edges

Multi-line tag with child coordinates. Key attributes:
- `relative="1"`: Marks this as relative geometry (standard for edges)
- `width`, `height`: Usually 50x50 (ignored when relative=1)
- `as="geometry"`: Required literal value

Child elements:
- `<mxPoint x="..." y="..." as="sourcePoint" />`: Absolute start position
- `<mxPoint x="..." y="..." as="targetPoint" />`: Absolute end position
- `<Array as="points">`: Array of `<mxPoint>` waypoints

## Style Reference

The `style` attribute is `key=value;key=value;...`

### Color & Fill

| Property | Example | Description |
|----------|---------|-------------|
| `fillColor` | `#dae8fc` | Background fill color |
| `strokeColor` | `#6c8ebf` | Border/line color |
| `gradientColor` | `#ffffff` | Gradient end color |
| `fontColor` | `#000000` | Text color |
| `opacity` | `50` | Transparency (0-100) |
| `fillOpacity` | `80` | Fill transparency |

### Shape & Layout

| Property | Values | Description |
|----------|--------|-------------|
| `rounded` | 0, 1 | Rounded corners |
| `arcSize` | number | Corner radius px |
| `whiteSpace` | wrap, nowrap | Text overflow |
| `html` | 0, 1 | HTML label rendering |
| `container` | 0, 1 | Is a container element |
| `collapsible` | 0, 1 | Can be collapsed |
| `expand` | 0, 1 | Expand/collapse state |
| `recursiveResize` | 0, 1 | Resize children with parent |
| `shadow` | 0, 1 | Drop shadow |
| `sketch` | 0, 1 | Hand-drawn effect |
| `curved` | 0, 1 | Curved edges |
| `pointerEvents` | 0, 1 | Enable pointer events |
| `points` | `[]` | Custom connection points |

### Text Formatting

| Property | Values | Description |
|----------|--------|-------------|
| `fontSize` | number | Font size in pt |
| `fontFamily` | name | Font family |
| `fontColor` | hex | Font color |
| `fontStyle` | 0,1,2,4 | 1=bold, 2=italic, 4=underline |
| `align` | left, center, right | Horizontal alignment |
| `verticalAlign` | top, middle, bottom | Vertical alignment |
| `spacing` | number | Padding in px |
| `spacingLeft` | number | Left padding |
| `spacingRight` | number | Right padding |
| `spacingTop` | number | Top padding |
| `spacingBottom` | number | Bottom padding |
| `whiteSpace` | wrap, nowrap | Text wrapping |
| `overflow` | hidden, visible, fill | Overflow behavior |

### Line / Border

| Property | Values | Description |
|----------|--------|-------------|
| `dashed` | 0, 1 | Dashed line |
| `dashPattern` | string | Custom dash pattern |
| `strokeWidth` | number | Line width in px |
| `endArrow` | none, classic, block, open, oval, diamond, ... | Arrow at target |
| `startArrow` | same as endArrow | Arrow at source |
| `endFill` | 0, 1 | Fill the target arrowhead |
| `startFill` | 0, 1 | Fill the source arrowhead |
| `endSize` | number | Target arrow size |
| `startSize` | number | Source arrow size |
| `perimeterSpacing` | number | Gap from vertex perimeter |

### Edge Routing

| Property | Values | Description |
|----------|--------|-------------|
| `edgeStyle` | orthogonalEdgeStyle, curved, isometric, ... | Edge routing algorithm |
| `orthogonalLoop` | 0, 1 | Loop edge routing |
| `jettySize` | number, auto | Perpendicular segment length |
| `jumpStyle` | none, arc, gap, line | Line jump style for crossings |
| `jumpSize` | number | Jump size in px |
| `rounded` | 0, 1 | Rounded edge corners |
| `curved` | 0, 1 | Curved edge |

### Connection Points (Edges with source/target)

| Property | Values | Description |
|----------|--------|-------------|
| `exitX`, `exitY` | 0-1 | Connection point on source vertex |
| `entryX`, `entryY` | 0-1 | Connection point on target vertex |
| `exitDx`, `exitDy` | number | Offset from exit point (px) |
| `entryDx`, `entryDy` | number | Offset from entry point (px) |
| `exitPerimeter` | 0, 1 | Snap exit to vertex perimeter |
| `entryPerimeter` | 0, 1 | Snap entry to vertex perimeter |

Exit/entry values: 0=left/top, 1=right/bottom, 0.5=center.

## Text Encoding

Text values are XML-encoded HTML:

| Raw | Encoded |
|-----|---------|
| `<br>` | `&lt;br&gt;` |
| `<div>` | `&lt;div&gt;` |
| `</div>` | `&lt;/div&gt;` |
| `&` | `&amp;` |
| `"` | `&quot;` |

Drawio supports multi-line text via `<br>` and `<div>` tags. For example:
```
value="将模型和优化器参数&lt;br&gt;传到CPU内存"
```
Renders as:
```
将模型和优化器参数
传到CPU内存
```

For HTML labels (`html=1` in style), more complex HTML is supported:
```
value="&lt;div style=&quot;line-height: 20%;&quot;&gt;&lt;span&gt;text&lt;/span&gt;&lt;/div&gt;"
```

LaTeX math is rendered inline with `$$...$$`:
```
value="$$M^2_B+O^2_B+G^2_{AB}$$"
```

## Page-level Elements

### Background Grid Pattern

(Not stored as XML — controlled by `grid`/`gridSize` attributes on mxGraphModel.)

### Multiple Pages

A single .drawio file can contain multiple `<diagram>` elements:
```xml
<mxfile ...>
  <diagram name="Page 1" id="page1">...</diagram>
  <diagram name="Page 2" id="page2">...</diagram>
</mxfile>
```

## Practical Parsing Notes

1. **Line-by-line parsing** works well because drawio outputs one element per block with consistent indentation
2. **Regex patterns to use:**
   - `r'<mxPoint x="([^"]+)" y="([^"]+)" as="sourcePoint"\s*/>'` — note `\s*` before `/>`
   - `r'<mxGeometry[^>]*/>'` — matches self-closing geometry (vertices)
   - `r'<mxGeometry[^>]*>.*?</mxGeometry>'` with `re.DOTALL` — matches multi-line geometry (edges)
3. **Always track parent= attributes** — they determine the cell hierarchy
4. **Edge cells** may have `source`/`target` attributes OR explicit `sourcePoint`/`targetPoint` coordinates, OR both
5. **Waypoints** in `<Array as="points">` are intermediate bend points (not start/end)
