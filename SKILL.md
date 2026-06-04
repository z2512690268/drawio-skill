---
name: drawio
description: Read, analyze, modify, create, and split .drawio diagrams programmatically. Understands the drawio XML format, can parse diagram structure, cluster sub-diagrams, and adjust styles and positions. Improves over time by learning from user-provided before/after examples.
---

# Drawio Diagram Skill

This skill equips Claude to work with draw.io / diagrams.net `.drawio` files programmatically. It covers format understanding, XML parsing, spatial analysis, sub-diagram splitting, style modification, and element manipulation.

## Capabilities

1. **Parse** .drawio files into structured data (cells, positions, styles, connections)
2. **Analyze** diagram structure (spatial clusters, connected components, hierarchy)
3. **Split** large diagrams into sub-diagrams by spatial proximity
4. **Modify** existing elements (reposition, restyle, relabel)
5. **Create** new diagrams from scratch or add elements to existing ones
6. **Learn** from user-provided before/after examples to handle new patterns

## Format Reference

Detailed format reference is in `references/format.md`. Key points:

- XML structure with `<mxfile>` → `<diagram>` → `<mxGraphModel>` → `<root>` → `<mxCell>`
- Vertex cells (`vertex="1"`) are shapes/nodes; Edge cells (`edge="1"`) are connectors
- Position via `<mxGeometry>` — self-closing for vertices, multi-line with children for edges
- Group cells (`style="group"`) contain child cells with relative coordinates
- Text content in `value` is HTML-encoded; supports `$$...$$` for LaTeX with `math="1"`
- Style is semicolon-delimited `key=value;key=value;...` string

## Core Algorithm: Sub-diagram Splitting

When asked to split a .drawio file into sub-diagrams:

1. **Parse** all cells, separate vertices (with x,y,w,h) from edges (with source,target,sourcePoint/targetPoint,waypoints)
2. **Spatial clustering** using DBSCAN-like algorithm with rectangle distance:
   - Default epsilon: 200px (tunable: 100 for finer, 300 for coarser splits)
   - `rect_distance(a,b)` = minimum Euclidean distance between two rectangles
3. **Edge assignment**: edges go to the cluster containing their source/target vertices
4. **Child cell inclusion**: recursively include any cell whose `parent` is in the cluster
5. **Coordinate adjustment**: shift all coordinates to origin with padding, update page dimensions
6. **Output**: generate separate `.drawio` files, each with valid standalone structure

The splitting script is bundled at `references/split_drawio.py`.

## Architecture Diagram Workflow (Spec-Driven)

For architecture/flow diagrams, use a three-layer pipeline instead of writing raw XML:

```
fmrl_spec.json  ──references/render.py──→  *.drawio
       │
       └──references/analyze_layout.py──→ 布局质量报告
```

- **spec.json**: 层次化的中间描述语言，reader-writer friendly。完整示例见 `references/fmrl_spec_example.json`
- **render.py**: 递归渲染器，把 spec 转成 drawio XML
- **analyze_layout.py**: 从渲染结果读取实际位置，做对齐/留白/箭头检查

For exact figure recreation, `render.py` also supports a top-level flat
`elements` list with absolute-position primitives. Use this mode for plots,
screenshots, and paper figures that need pixel-level placement. It supports
`rect`, `text`, `ellipse`, `rhombus`, `edge`, `image`, `image_crop`,
`subfigure_crop`, `gpu_icon`, `hourglass`, and `lightbulb`.

Use `subfigure_crop` for dense regions that have internal structure but are too
large to decompose in one pass. Use `image_crop` only for leaf-level visual
assets such as individual icons. Details are in `references/image_assets.md`.

For complex figures, keep the master JSON complete while moving dense local
regions into nested subfigure JSON specs. A master `subfigure_crop` can set
`"spec": "subfigures/<id>/<id>_spec.json"` and `"expand": true`; `render.py`
then inlines that subfigure's editable elements into the master `.drawio`,
offsets coordinates by the parent `x/y`, and prefixes IDs with `<id>__`.
See `references/subfigure_sync.md`. Use `references/sync_subfigures.py` only
as a legacy migration helper for older `.drawio`-only subfigures.

### Spec 节点类型

所有节点共享递归结构，`type` 决定渲染行为：

| type | 含义 | 关键属性 | 渲染行为 |
|------|------|---------|---------|
| `container` | 有背景框的块 | `id`,`w`,`h`,`fill`,`stroke`,`children` | 画圆角框，内容偏移到框内 |
| `hbox` | 水平排列子元素 | `gap`,`x0`,`y0`,`children` | 子元素从左到右自动排列 |
| `vbox` | 垂直排列子元素 | `gap`,`x0`,`y0`,`children` | 子元素从上到下自动排列 |
| `cell` | 叶子节点（框+文字） | `w`,`h`,`text`,`fill`,`tc` | 画圆角框+居中文字 |
| `cell`(rx) | 绝对定位的叶子节点 | `x`,`y`,`rx:true` | 不参与 hbox/vbox 自动排列 |
| `text` | 纯文字 | `cx` 或 `x`, `y`, `fs` | 画文字标签 |
| `title` | 容器内标题 | `y0`, `fs` | 容器自动 offset 3px 绘制 |
| `group` | 语义分组（不渲染） | `children` | 直接穿透，不产生图形 |

### 坐标系统

- **相对坐标**：cell/text 在容器内用 `x0`/`y0` 偏移；`rx:true` 做绝对定位
- **绝对坐标**：容器用 `box.x`/`box.y`，hbox/vbox 用 `x0`/`y0` 做绝对起始
- **居中**：text 节点用 `cx` 指定中心 x，自动计算左边界

### 箭头定义

```json
{"id": "arrow_name", "from": "src_id", "to": "tgt_id",
 "exit": "E", "enter": "W",          // E/W/S/N → 东西南北
 "exit_y": 1.0,                      // 可选，覆盖默认 0.5
 "stroke": "#color", "width": 2.5,   // 可选
 "dashed": true}                     // 可选
```

### 常见问题

1. **`d.setId is not a function`** — cell ID 与 JS 内置方法冲突（如 `at`）。避免使用 JS 保留字。
2. **箭头穿过组件** — exit/enter 方向错误。用 `analyze_layout.py` 检查。必要时用 `exit_y`/`exit_x` 覆盖默认值。
3. **文字超出框** — 框高至少 ≥ 字号+4px。
4. **hbox/vbox 内绝对定位** — 需用 `rx: true` 标记，否则位置被自动排列覆盖。
5. **容器高度不对齐** — hbox 内容器高度不同时手动设 `h` 一致。

### 布局原则

1. **先画背景框**：定义 section 的 `box`，居中且宽度一致
2. **内容从 hbox 开始**：同行的组件包在 hbox 中
3. **行间堆叠用 vbox**：行与行之间用 vbox + `gap` 控制间距
4. **列内对齐用 vbox**：同一列的多行用 vbox
5. **等高等对齐**：用 `constraints` 中的 `align_top`/`align_bot` 约束

### 工作流

1. 修改 `fmrl_spec.json`
2. 运行 `python3 references/render.py fmrl_spec.json`
3. 运行 `python3 references/analyze_layout.py fmrl_spec.json`
4. 看分析报告，确认容器对齐、箭头合理性、留白、画布范围
5. 在 drawio 中打开 `.drawio` 文件验证视觉效果
6. 回到步骤 1 迭代

## Visual Verification

This repo has a local drawio export tool. Detailed usage, caveats, and migration
requirements are documented in `references/export.md`.

Use it after creating or modifying a `.drawio` file whenever visual verification
is needed:

```bash
drawio-export/scripts/drawio-export.sh input.drawio output.png --scale 1 --timeout 30000
```

Then inspect the PNG with the local image viewer. If Chromium fails under the
sandbox with `Operation not permitted`, rerun the same export command with
escalated permissions.

**Important:** avoid passing `--background` when the `.drawio` already has a
background attribute. See `references/export.md` for the duplicate-background
blank-PNG failure mode.

**After creating or modifying a .drawio file:**
1. Export it to PNG with `drawio-export.sh`
2. Inspect the PNG for blank output, clipping, routing issues, text overlap, and obvious visual mismatch
3. Iterate on the spec/XML until the exported image is reasonable
4. Tell the user the `.drawio` and exported PNG paths
5. Ask the user to open the `.drawio` in VS Code drawio extension, app.diagrams.net, or drawio desktop for final manual verification

The exported PNG is a useful automated check, but the user remains the authority
on whether the editable drawio result matches the intended figure closely enough.

## Self-Improvement Protocol

This skill improves over time by learning from experience. Core principle: **document every new drawio XML pattern encountered**.

### When unsure about an operation:

1. Tell the user specifically what you're trying to do and what you're uncertain about (e.g., "I need to add a curved edge with a label, but I'm not sure how drawio encodes curved edge waypoints")
2. Ask the user to manually make the change in drawio, then provide **both the before and after `.drawio` files**
3. **Diff the XML** at the cell level to identify exactly what changed:
   - Which cells were added/modified/removed?
   - What attribute values changed?
   - What new style properties appeared?
   - What geometry patterns are new?
4. **Generalize** the pattern: create a reusable description or Python helper
5. **Append** the new pattern to the "Learned Patterns" section of `references/learned_patterns.md`

### Learning from before/after examples:

When a user provides paired files for learning:

```python
def diff_drawio_files(before_path, after_path):
    """Compare two .drawio files and report structural differences."""
    # Parse both files
    # Compare cell by cell (match by id if same, otherwise by position/style)
    # Report: added cells, removed cells, modified cells
    # Within modified cells: changed attributes (value, style, position, geometry)
    return diff_report
```

The goal is to build up a comprehensive library of drawio XML patterns so that over time, this skill can handle any drawio operation without user guidance.

## Common Pitfalls to Remember

- `sourcePoint`/`targetPoint` in edge geometry use `as="sourcePoint" />` (note the space before `/>`)
- Group children use the group's id as `parent`, and their positions are relative to the group
- Empty `value=""` vs non-empty: even a space in value changes rendering
- IDs must be unique per file; when merging diagrams, prefix or regenerate IDs
- Edge `entryX`/`entryY`/`exitX`/`exitY` are values in [0,1] relative to vertex bounds
- Arrow direction: `endArrow=classic` for forward, `startArrow=classic` for backward

## Stencil Shapes (Built-in Icons)

drawio includes hundreds of built-in icons from cloud providers, networks, and hardware vendors. Use `"shape":"stencil:mxgraph.<provider>.<icon>"` in spec cells to render them.

### Available stencil libraries
- **GCP** (`gcp2`): Compute Engine, GPU, CPU, VM instances, ML APIs, storage, networking
- **AWS4** (`aws4`): EC2 instances (g5, p4de GPU, inf2), Lambda, S3, etc.
- **Azure** (`azure`): Server, Computer, Server Rack, cloud services
- **Alibaba** (`alibaba_cloud`): ECS, Compute, GPU, serverless
- **Networks** (`networks`): Server, Mail Server, Proxy Server, Virtual Server, Supercomputer
- **IBM** (`ibm` / `ibm_cloud`): Cloud services, AI, analytics
- **Kubernetes** (`kubernetes` / `kubernetes2`): Pod, Node, Cluster, Deployment, etc.
- **Cisco** (`cisco19`): Routers, switches, firewalls, servers

### Usage
```json
// GPU chip icon (GCP)
{"type":"cell","id":"gpu0","x":10,"y":60,"w":50,"h":42,"shape":"stencil:mxgraph.gcp2.gpu","fill":"#388E3C","tc":"#FFFFFF","text":"GPU0","fs":9"}

// Server icon (Networks)
{"type":"cell","id":"server","x":10,"y":60,"w":50,"h":50,"shape":"stencil:mxgraph.networks.server","fill":"#1976D2","tc":"#FFFFFF"}

// EC2 instance (AWS4)
{"type":"cell","id":"ec2","x":10,"y":60,"w":50,"h":50,"shape":"stencil:mxgraph.aws4.ec2Instance","fill":"#FF9900","tc":"#FFFFFF"}
```

### Finding available icons
Check the stencil XML files in the bundled drawio submodule:
- `drawio/src/main/webapp/stencils/` — contains `*.xml` with shape definitions
- `drawio/src/main/webapp/shapes/` — contains `*.js` with shape registration

The shape name in `"shape":"stencil:mxgraph.xxx.yyy"` is not always obvious from the XML display name; check the JS registration in `mx<Provider>.js` for the correct stencil ID.

### Best practices
- Use `round` parameter is ignored for stencil shapes (the stencil defines its own shape)
- Fill color (`fill`) works with most stencils — they use it as background
- Text (`text` + `tc`) renders inside/on top of the stencil shape
- Keep icons small (40-60px) for labels; larger sizes (80-120px) for standalone icons
- Not all stencils work well with arbitrary fill colors — test before finalizing

## When to Ask the User

Ask the user for confirmation or guidance when:
- You're unsure about a drawio XML pattern you haven't seen before
- Visual verification is needed but no rendering tools are available
- The clustering/splitting result doesn't look right and needs manual adjustment
- Before/after examples are needed to learn a new pattern
- A diagram has features (custom shapes, embedded images, plots) that require special handling
