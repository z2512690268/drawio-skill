#!/usr/bin/env python3
"""Recursive renderer: walks tree, computes positions, emits drawio XML.

Three-phase rendering for correct z-order (edges behind text):
  Phase 1 — boxes (containers, cells) via _render_node
  Phase 2 — edges
  Phase 3 — all text (titles, labels, cell text)
"""
import base64, io, json, sys, os
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

try:
    from PIL import Image, ImageChops
except ImportError:
    Image = None
    ImageChops = None

def style(parts):
    chunks = []
    for k, v in parts.items():
        if v is None:
            continue
        if v == '__bare__':
            chunks.append(k)
        else:
            chunks.append(f'{k}={v}')
    return ';'.join(chunks) + ';'

class FlatRenderer:
    """Absolute-position renderer for figure recreation specs.

    This complements the recursive architecture renderer below. Use it when the
    spec has a top-level `elements` list and the source figure needs precise,
    editable recreation with absolute coordinates, plot lines, and composite
    icon primitives.
    """
    def __init__(self, spec):
        self.spec = spec
        self._spec_dir = spec.get('__spec_dir', os.getcwd())
        self._source_images = {}
        self._skip_crop_save = False
        c = spec.get('canvas', {})
        self.mxfile = Element('mxfile', host='drawio', modified='2025-05-22T00:00:00Z', version='21.1.2')
        diag = SubElement(self.mxfile, 'diagram', id=spec.get('id', 'drawio-flat'), name=spec.get('name', 'Diagram'))
        model_attrs = {
            'dx':'0','dy':'0','grid':'0','gridSize':'10','guides':'1','tooltips':'1','connect':'1',
            'arrows':'1','fold':'1','page':'1','pageScale':'1',
            'pageWidth':str(c.get('width', 1000)),'pageHeight':str(c.get('height', 460)),
            'math':'0','shadow':'0'
        }
        if c.get('background'):
            model_attrs['background'] = c['background']
        model = SubElement(diag, 'mxGraphModel', **model_attrs)
        self.base = SubElement(model, 'root')
        SubElement(self.base, 'mxCell', id='0')
        SubElement(self.base, 'mxCell', id='1', parent='0')

    def _geom(self, cell, x, y, w, h):
        SubElement(cell, 'mxGeometry', x=str(x), y=str(y), width=str(w), height=str(h), **{'as':'geometry'})

    def _vertex(self, item, shape_style):
        el = SubElement(self.base, 'mxCell', id=item['id'], value=item.get('text', ''),
                        style=shape_style, parent='1', vertex='1')
        self._geom(el, item.get('x', 0), item.get('y', 0), item.get('w', 10), item.get('h', 10))

    def _resolve_path(self, path):
        if os.path.isabs(path):
            return path
        return os.path.join(self._spec_dir, path)

    def _image_to_data_uri(self, img, fmt='png'):
        buf = io.BytesIO()
        fmt = fmt.lower()
        save_fmt = 'JPEG' if fmt in ('jpg', 'jpeg') else 'PNG'
        if save_fmt == 'JPEG' and img.mode in ('RGBA', 'LA'):
            bg = Image.new('RGB', img.size, '#ffffff')
            bg.paste(img, mask=img.getchannel('A'))
            img = bg
        img.save(buf, format=save_fmt)
        mime = 'jpeg' if save_fmt == 'JPEG' else 'png'
        data = base64.b64encode(buf.getvalue()).decode('ascii')
        return f'data:image/{mime}%3Bbase64,{data}'

    def _asset_path(self, item, fmt='png'):
        explicit = item.get('asset') or item.get('asset_path')
        if explicit:
            return self._resolve_path(explicit)
        crop_dir = item.get('crop_dir') or self.spec.get('assets', {}).get('crop_dir')
        if not crop_dir:
            return None
        ext = 'jpg' if fmt.lower() in ('jpg', 'jpeg') else 'png'
        return self._resolve_path(os.path.join(crop_dir, f'{item["id"]}.{ext}'))

    def _save_asset_image(self, item, img, fmt='png'):
        path = self._asset_path(item, fmt)
        if not path:
            return
        os.makedirs(os.path.dirname(path), exist_ok=True)
        save_fmt = 'JPEG' if fmt.lower() in ('jpg', 'jpeg') else 'PNG'
        out = img
        if save_fmt == 'JPEG' and out.mode in ('RGBA', 'LA'):
            bg = Image.new('RGB', out.size, '#ffffff')
            bg.paste(out, mask=out.getchannel('A'))
            out = bg
        out.save(path, format=save_fmt)

    def _load_source_image(self, source=None):
        if Image is None:
            raise RuntimeError('Pillow is required for image/image_crop elements')
        source = source or self.spec.get('assets', {}).get('source')
        if not source:
            raise ValueError('image_crop requires item.source or top-level assets.source')
        path = self._resolve_path(source)
        if path not in self._source_images:
            self._source_images[path] = Image.open(path).convert('RGBA')
        return self._source_images[path]

    def _trim_image(self, img, trim):
        if not trim:
            return img
        if ImageChops is None:
            return img
        if isinstance(trim, dict):
            bg_color = trim.get('background')
            tolerance = int(trim.get('tolerance', 0))
        else:
            bg_color = None
            tolerance = 0
        if bg_color:
            bg = Image.new(img.mode, img.size, bg_color)
        else:
            bg = Image.new(img.mode, img.size, img.getpixel((0, 0)))
        diff = ImageChops.difference(img, bg)
        if tolerance:
            diff = diff.point(lambda p: 0 if p <= tolerance else 255)
        bbox = diff.getbbox()
        return img.crop(bbox) if bbox else img

    def _image(self, item):
        if item.get('data'):
            data_uri = item['data']
        elif item.get('path'):
            if Image is None:
                raise RuntimeError('Pillow is required for image path elements')
            with Image.open(self._resolve_path(item['path'])) as img:
                data_uri = self._image_to_data_uri(img.convert('RGBA'), item.get('format', 'png'))
        else:
            raise ValueError(f'image element {item["id"]} requires data or path')
        self._vertex(item, style({
            'shape':'image','html':1,'image':data_uri,'aspect':'fixed' if item.get('fixed', False) else None,
            'verticalLabelPosition':'bottom','verticalAlign':'top','labelBackgroundColor':'#ffffff'
        }))

    def _image_crop(self, item):
        fmt = item.get('format', 'png')
        asset_path = self._asset_path(item, fmt)
        if item.get('reuse') and asset_path and os.path.exists(asset_path):
            with Image.open(asset_path) as cached:
                data_uri = self._image_to_data_uri(cached.convert('RGBA'), fmt)
            self._vertex(item, style({
                'shape':'image','html':1,'image':data_uri,'aspect':'fixed' if item.get('fixed', False) else None,
                'verticalLabelPosition':'bottom','verticalAlign':'top','labelBackgroundColor':'#ffffff'
            }))
            return

        src = self._load_source_image(item.get('source'))
        crop = item.get('crop') or item.get('bbox')
        if not crop or len(crop) != 4:
            raise ValueError(f'image_crop element {item["id"]} requires crop/bbox [x,y,w,h] or [x1,y1,x2,y2]')
        if item.get('bbox_mode') == 'corners':
            x1, y1, x2, y2 = crop
        else:
            x1, y1, cw, ch = crop
            x2, y2 = x1 + cw, y1 + ch
        pad = int(item.get('pad', 0))
        x1 = max(0, int(x1) - pad)
        y1 = max(0, int(y1) - pad)
        x2 = min(src.width, int(x2) + pad)
        y2 = min(src.height, int(y2) + pad)
        img = src.crop((x1, y1, x2, y2))
        img = self._trim_image(img, item.get('trim'))
        if item.get('background'):
            bg = Image.new('RGBA', img.size, item['background'])
            bg.alpha_composite(img)
            img = bg
        self._save_asset_image(item, img, fmt) if not self._skip_crop_save else None
        data_uri = self._image_to_data_uri(img, fmt)
        self._vertex(item, style({
            'shape':'image','html':1,'image':data_uri,'aspect':'fixed' if item.get('fixed', False) else None,
            'verticalLabelPosition':'bottom','verticalAlign':'top','labelBackgroundColor':'#ffffff'
        }))

    def _subfigure_crop(self, item):
        """Render a complex subfigure from a referenced JSON spec (expand) or as a crop placeholder.

        When expand=true and spec is given, load the subfigure JSON, offset all
        coordinates, prefix all IDs, and inline its elements into the master.
        Otherwise fall back to image_crop for raster placeholder.
        """
        if item.get('expand') and item.get('spec'):
            self._render_included_spec(item)
        else:
            self._image_crop(item)

    def _render_included_spec(self, item):
        spec_path = self._resolve_path(item['spec'])
        prefix = f"{item['id']}__"
        dx = item.get('x', 0)
        dy = item.get('y', 0)

        with open(spec_path) as f:
            sub_spec = json.load(f)

        old_spec = self.spec
        old_spec_dir = self._spec_dir
        old_skip_crop = self._skip_crop_save
        self.spec = sub_spec
        self._spec_dir = os.path.dirname(os.path.abspath(spec_path))
        self._skip_crop_save = True

        try:
            for sub_item in sub_spec.get('elements', []):
                new_item = dict(sub_item)
                new_item['id'] = prefix + sub_item.get('id', '')
                if 'x' in new_item:
                    new_item['x'] = new_item['x'] + dx
                if 'y' in new_item:
                    new_item['y'] = new_item['y'] + dy
                if new_item.get('type') == 'edge':
                    if new_item.get('source'):
                        new_item['source'] = prefix + new_item['source']
                    if new_item.get('target'):
                        new_item['target'] = prefix + new_item['target']
                    if 'sourcePoint' in new_item:
                        new_item['sourcePoint'] = [new_item['sourcePoint'][0] + dx, new_item['sourcePoint'][1] + dy]
                    if 'targetPoint' in new_item:
                        new_item['targetPoint'] = [new_item['targetPoint'][0] + dx, new_item['targetPoint'][1] + dy]
                    if 'points' in new_item:
                        new_item['points'] = [[px + dx, py + dy] for px, py in new_item['points']]
                self._render_element(new_item)
        finally:
            self.spec = old_spec
            self._spec_dir = old_spec_dir
            self._skip_crop_save = old_skip_crop

    def _text(self, item):
        fs = item.get('fs', 14)
        font_style = 0
        if item.get('bold'): font_style |= 1
        if item.get('italic'): font_style |= 2
        self._vertex(item, style({
            'text':'__bare__','html':1,'strokeColor':'none','fillColor':'none',
            'align':item.get('align','center'),'verticalAlign':item.get('valign','middle'),
            'whiteSpace':'wrap','rounded':0,'fontSize':fs,'fontColor':item.get('color','#111111'),
            'fontStyle':font_style if font_style else None,'fontFamily':item.get('font','Helvetica'),
            'spacing':item.get('spacing'),'rotation':item.get('rotation')
        }))

    def _rect(self, item):
        self._vertex(item, style({
            'rounded':1 if item.get('round', 1) else 0,'arcSize':item.get('arc', 8),
            'whiteSpace':'wrap','html':1,'fillColor':item.get('fill','#ffffff'),
            'strokeColor':item.get('stroke','#999999'),'strokeWidth':item.get('sw',1),
            'dashed':1 if item.get('dashed') else None,'fontSize':item.get('fs',14),
            'fontColor':item.get('color','#111111'),'fontStyle':1 if item.get('bold') else None,
            'align':item.get('align','center'),'verticalAlign':item.get('valign','middle')
        }))

    def _ellipse(self, item):
        self._vertex(item, style({
            'ellipse':'__bare__','whiteSpace':'wrap','html':1,'aspect':'fixed' if item.get('fixed', True) else None,
            'fillColor':item.get('fill','#ffffff'),'strokeColor':item.get('stroke','#999999'),
            'strokeWidth':item.get('sw',1),'fontSize':item.get('fs',14),'fontColor':item.get('color','#111111')
        }))

    def _edge(self, item):
        kwargs = {'id':item['id'], 'value':item.get('text',''), 'parent':'1', 'edge':'1',
                  'style':style({
                      'endArrow':item.get('end','classic'),'startArrow':item.get('start'),
                      'endFill':1 if item.get('end','classic') != 'none' else 0,'html':1,'rounded':0,
                      'edgeStyle':item.get('edgeStyle','orthogonalEdgeStyle'),'strokeColor':item.get('stroke','#111111'),
                      'strokeWidth':item.get('sw',1.5),'dashed':1 if item.get('dashed') else None,
                      'curved':1 if item.get('curved') else None,'exitX':item.get('exitX'),'exitY':item.get('exitY'),
                      'entryX':item.get('entryX'),'entryY':item.get('entryY')
                  })}
        if item.get('source'): kwargs['source'] = item['source']
        if item.get('target'): kwargs['target'] = item['target']
        el = SubElement(self.base, 'mxCell', **kwargs)
        gg = SubElement(el, 'mxGeometry', relative='1', **{'as':'geometry'})
        if 'sourcePoint' in item:
            SubElement(gg, 'mxPoint', x=str(item['sourcePoint'][0]), y=str(item['sourcePoint'][1]), **{'as':'sourcePoint'})
        if 'targetPoint' in item:
            SubElement(gg, 'mxPoint', x=str(item['targetPoint'][0]), y=str(item['targetPoint'][1]), **{'as':'targetPoint'})
        if item.get('points'):
            arr = SubElement(gg, 'Array', **{'as':'points'})
            for x, y in item['points']:
                SubElement(arr, 'mxPoint', x=str(x), y=str(y))

    def _rhombus(self, item):
        self._vertex(item, style({
            'rhombus':'__bare__','whiteSpace':'wrap','html':1,
            'fillColor':item.get('fill','#ffffff'),'strokeColor':item.get('stroke','#999999'),
            'strokeWidth':item.get('sw',1),'fontSize':item.get('fs',14),'fontColor':item.get('color','#111111')
        }))

    def _gpu_icon(self, item):
        x, y = item['x'], item['y']
        w, h = item.get('w', 34), item.get('h', 30)
        stroke = item.get('stroke', '#6d7d85')
        self._rect({**item, 'id':item['id'] + '_body', 'x':x, 'y':y, 'w':w, 'h':h,
                    'fill':item.get('fill','#d9e3e8'), 'stroke':stroke, 'sw':1.4, 'text':''})
        self._ellipse({'id':item['id'] + '_fan', 'x':x+w*0.27, 'y':y+h*0.22, 'w':w*0.46, 'h':h*0.46,
                       'fill':'#c2d0d6', 'stroke':stroke, 'sw':1})
        cx, cy = x + w/2, y + h/2
        for i, (dx, dy) in enumerate([(0,-10),(8,-5),(8,5),(0,10),(-8,5),(-8,-5)]):
            self._edge({'id':f"{item['id']}_spoke_{i}", 'end':'none', 'stroke':stroke, 'sw':1,
                        'sourcePoint':[cx, cy], 'targetPoint':[cx+dx*0.55, cy+dy*0.55], 'edgeStyle':None})
        for i in range(3):
            yy = y + 7 + i * 7
            self._edge({'id':f"{item['id']}_pin_l_{i}", 'end':'none', 'stroke':stroke, 'sw':1,
                        'sourcePoint':[x-3, yy], 'targetPoint':[x, yy], 'edgeStyle':None})
            self._edge({'id':f"{item['id']}_pin_r_{i}", 'end':'none', 'stroke':stroke, 'sw':1,
                        'sourcePoint':[x+w, yy], 'targetPoint':[x+w+3, yy], 'edgeStyle':None})

    def _hourglass(self, item):
        x, y, w, h = item['x'], item['y'], item['w'], item['h']
        paths = [
            [[x, y], [x+w, y], [x+w/2, y+h/2], [x, y]],
            [[x, y+h], [x+w, y+h], [x+w/2, y+h/2], [x, y+h]],
        ]
        for i, pts in enumerate(paths):
            for j in range(len(pts)-1):
                self._edge({'id':f"{item['id']}_{i}_{j}", 'end':'none', 'stroke':item.get('stroke','#d93030'),
                            'sw':item.get('sw',2), 'sourcePoint':pts[j], 'targetPoint':pts[j+1], 'edgeStyle':None})

    def _lightbulb(self, item):
        x, y = item['x'], item['y']
        self._ellipse({'id':item['id']+'_bulb', 'x':x+10, 'y':y, 'w':28, 'h':32,
                       'fill':'#fff2cc', 'stroke':'#666666', 'sw':2})
        self._rect({'id':item['id']+'_base', 'x':x+18, 'y':y+29, 'w':12, 'h':8,
                    'fill':'#e6e6e6', 'stroke':'#666666', 'sw':1, 'round':0})
        for i, (sx, sy, tx, ty) in enumerate([(24,-9,24,-2),(6,1,12,7),(42,1,36,7),(2,18,9,18),(48,18,41,18)]):
            self._edge({'id':f"{item['id']}_ray_{i}", 'end':'none', 'stroke':'#666666', 'sw':1.4,
                        'sourcePoint':[x+sx, y+sy], 'targetPoint':[x+tx, y+ty], 'edgeStyle':None})

    def _render_element(self, item):
        typ = item.get('type')
        if typ == 'rect': self._rect(item)
        elif typ == 'text': self._text(item)
        elif typ == 'ellipse': self._ellipse(item)
        elif typ == 'rhombus': self._rhombus(item)
        elif typ == 'edge': self._edge(item)
        elif typ == 'image': self._image(item)
        elif typ == 'image_crop': self._image_crop(item)
        elif typ == 'subfigure_crop': self._subfigure_crop(item)
        elif typ == 'gpu_icon': self._gpu_icon(item)
        elif typ == 'hourglass': self._hourglass(item)
        elif typ == 'lightbulb': self._lightbulb(item)
        else:
            raise ValueError(f'Unsupported flat element type: {typ}')

    def render(self):
        for item in self.spec.get('elements', []):
            self._render_element(item)

class Renderer:
    def __init__(self, root, edges=None, labels=None):
        self.root = root
        self._parent_w = None  # track parent container width for cx_rel
        self._parent_h = None  # track parent container height for cy_rel
        self._cell_ids = set()  # track all cell IDs for edge validation
        self._cell_positions = {}  # {id: (x, y, w, h)} for edge direction checks
        self._container_ids = set()  # container IDs for cross-check filtering
        self.mxfile = Element('mxfile', host='drawio', modified='2025-05-22T00:00:00Z', version='21.1.2')
        diag = SubElement(self.mxfile, 'diagram', id='fmrl-rec', name='FMRL')
        c = root.get('canvas', {})
        model = SubElement(diag, 'mxGraphModel')
        model_attrs = {'dx':'0','dy':'0','grid':'0','gridSize':'10','guides':'1','tooltips':'1','connect':'1','arrows':'1','fold':'1','page':'1','pageScale':'1','pageWidth':str(c.get('width',1000)),'pageHeight':str(c.get('height',460)),'math':'0','shadow':'0'}
        if 'background' in c:
            model_attrs['background'] = c['background']
        for k,v in model_attrs.items():
            model.set(k,v)
        self.base = SubElement(model, 'root')
        SubElement(self.base, 'mxCell', id='0')
        SubElement(self.base, 'mxCell', id='1', parent='0')
        self._parent_stack = ['1']  # track container hierarchy for parent='id'
        self._origin_stack = [(0, 0)]  # (px, py) for translating to container-relative coords
        self.labels_root = root
        # Text queue: defer text rendering to Phase 3
        self._text_queue = []

        # Phase 1: ALL boxes (containers, cells, shapes)
        self._render_node(root['root'], 0, 0)

        # Phase 2: Edges (after boxes so source/target IDs exist in XML)
        self._render_edges(edges or [])

        # Phase 3: ALL text on top (titles, cell labels, standalone text)
        self._flush_text_queue()

        # Labels on top too
        self._render_labels(labels or [])

    # ── text queue ──────────────────────────────────────────────

    def _text(self, cid, x, y, w, h, val, fs=9, color='#333', bold=False, font_family=None):
        """Queue text for Phase 3 rendering."""
        ox, oy = self._origin_stack[-1]
        self._text_queue.append((cid, x, y, w, h, val, fs, color, bold, font_family, self._parent_stack[-1], ox, oy))

    def _flush_text_queue(self):
        for cid, x, y, w, h, val, fs, color, bold, font_family, parent, ox, oy in self._text_queue:
            style = f'text;html=1;align=center;verticalAlign=middle;fontSize={fs};fontColor={color}'
            if bold: style += ';fontStyle=1'
            if font_family: style += f';fontFamily={font_family}'
            el = SubElement(self.base, 'mxCell', id=cid, style=style, vertex='1', parent=parent, value=val)
            g = SubElement(el, 'mxGeometry'); g.set('as','geometry')
            for k,v in [('x',str(x-ox)),('y',str(y-oy)),('width',str(w)),('height',str(h))]: g.set(k,v)

    # ── edges ───────────────────────────────────────────────────

    def _render_edges(self, edges):
        for e in edges:
            exit_xy = {'E':(1,e.get('exit_y',0.5)),'W':(0,e.get('exit_y',0.5)),
                       'S':(e.get('exit_x',0.5),1),'N':(e.get('exit_x',0.5),0)}
            enter_xy = {'E':(1,e.get('entry_y',0.5)),'W':(0,e.get('entry_y',0.5)),
                        'S':(e.get('entry_x',0.5),1),'N':(e.get('entry_x',0.5),0)}
            ex,ey = exit_xy.get(e.get('exit','E'), (1,0.5))
            enx,eny = enter_xy.get(e.get('enter','W'), (0,0.5))
            extra = f'exitX={ex};exitY={ey};entryX={enx};entryY={eny}'
            if e.get('dashed'): extra += ';dashed=1'
            target_id = e.get('to')
            kwargs = {'edge':'1', 'parent':'1'}
            if 'from' in e: kwargs['source'] = e['from']
            if target_id: kwargs['target'] = target_id
            el = SubElement(self.base, 'mxCell', id=e['id'],
                           style=f'endArrow=classic;endFill=1;edgeStyle=orthogonalEdgeStyle;strokeWidth={e.get("width",1.5)};strokeColor={e.get("stroke","#78909C")};{extra}',
                           **kwargs)
            gg = SubElement(el, 'mxGeometry'); gg.set('relative','1'); gg.set('as','geometry')
            wpts = e.get('waypoints', [])
            if wpts:
                arr = SubElement(gg, 'Array', **{'as': 'points'})
                for wx, wy in wpts:
                    SubElement(arr, 'mxPoint', x=str(wx), y=str(wy))
            sp = e.get('sourcePoint')
            if sp: SubElement(gg, 'mxPoint', x=str(sp[0]), y=str(sp[1]), **{'as':'sourcePoint'})
            tp = e.get('targetPoint')
            if tp: SubElement(gg, 'mxPoint', x=str(tp[0]), y=str(tp[1]), **{'as':'targetPoint'})

    # ── labels ──────────────────────────────────────────────────

    def _render_labels(self, labels):
        for lbl in labels:
            self._make_text(lbl['id'], lbl['x'], lbl['y'], lbl['w'], lbl['h'],
                            lbl['text'], fs=lbl.get('fs',9), color=lbl.get('color','#333'),
                            bold=lbl.get('bold', False), font_family=lbl.get('font_family'))

    def _make_text(self, cid, x, y, w, h, val, fs=9, color='#333', bold=False, font_family=None):
        """Immediate text element — bypasses the text queue."""
        style = f'text;html=1;align=center;verticalAlign=middle;fontSize={fs};fontColor={color}'
        if bold: style += ';fontStyle=1'
        if font_family: style += f';fontFamily={font_family}'
        el = SubElement(self.base, 'mxCell', id=cid, style=style, vertex='1', parent='1', value=val)
        g = SubElement(el, 'mxGeometry'); g.set('as','geometry')
        for k,v in [('x',str(x)),('y',str(y)),('width',str(w)),('height',str(h))]: g.set(k,v)

    # ── boxes (shapes / cells) — immediate rendering ────────────

    def _box(self, cid, x, y, w, h, fill='#fff', stroke=None, sw=None, dashed=False, shape=None, rnd=1, image=None):
        if shape == 'diamond':
            style = f'rhombus;whiteSpace=wrap;html=1;fillColor={fill}'
        elif shape == 'circle':
            style = f'ellipse;whiteSpace=wrap;html=1;fillColor={fill}'
        elif shape and shape.startswith('stencil:'):
            stencil_name = shape.split(':', 1)[1]
            style = f'shape={stencil_name};whiteSpace=wrap;html=1;fillColor={fill}'
        elif shape == 'image' and image:
            style = f'shape=image;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;image=data:image/svg+xml,{image}'
        else:
            style = f'rounded={rnd};whiteSpace=wrap;html=1;fillColor={fill}'
        if stroke: style += f';strokeColor={stroke}'
        if sw: style += f';strokeWidth={sw}'
        if dashed: style += ';dashed=1'
        ox, oy = self._origin_stack[-1]
        el = SubElement(self.base, 'mxCell', id=cid, style=style, vertex='1', parent=self._parent_stack[-1])
        g = SubElement(el, 'mxGeometry'); g.set('as','geometry')
        for k,v in [('x',str(x-ox)),('y',str(y-oy)),('width',str(w)),('height',str(h))]: g.set(k,v)

    # ── recursive renderer ──────────────────────────────────────

    def _render_node(self, node, px, py):
        """Recursively render a node's box(es). Text is deferred to Phase 3."""
        typ = node.get('type','cell')

        if typ == 'vbox':
            gap = node.get('gap', 6)
            x = node.get('x', px)
            y = node.get('y', py)
            if 'x0' in node: x = node['x0']
            if 'y0' in node: y = node['y0']
            cur_y = y
            for child in node.get('children', []):
                self._render_node(child, x, cur_y)
                ch = child
                ch_h = ch.get('h', 30)
                if ch.get('type') == 'cell' and ch.get('rx'):  # absolute pos
                    continue
                cur_y += ch_h + gap

        elif typ == 'hbox':
            gap = node.get('gap', 12)
            x0 = node.get('x0', px + 40)
            y = node.get('y', py)
            if 'y0' in node: y = node['y0']
            fill = node.get('fill', False)
            children = node.get('children', [])
            if fill and self._parent_w:
                # Distribute children evenly across parent width
                n = len(children)
                total_gaps = gap * (n - 1)
                ch_w = (self._parent_w - total_gaps) // n
                cur_x = x0
                for child in children:
                    ch_h = child.get('h', 30)
                    # Store fill width on child so downstream code uses it
                    child['__fill_w'] = ch_w
                    self._render_node(child, cur_x, y)
                    cur_x += ch_w + gap
            else:
                cur_x = x0
                for child in children:
                    self._render_node(child, cur_x, y)
                    ch = child
                    ch_w = ch.get('w', 80)
                    if ch.get('type') == 'container':
                        ch_w = ch['box']['w'] if 'box' in ch else ch.get('w', ch_w)
                    elif ch.get('type') == 'cell' and ch.get('rx'):
                        continue
                cur_x += ch_w + gap

        elif typ == 'container':
            box_info = node.get('box', {})
            x = box_info.get('x', px)
            y = box_info.get('y', py)
            w = node.get('w', box_info.get('w', 200))
            h = node.get('h', box_info.get('h', 100))
            if 'id' in node:
                self._cell_ids.add(node['id'])
                self._cell_positions[node['id']] = (x, y, w, h)
                self._container_ids.add(node['id'])
            old_parent_w = self._parent_w
            old_parent_h = self._parent_h
            self._parent_w = w
            self._parent_h = h
            if 'x0' in node: x = node['x0']
            if 'y0' in node: y = node['y0']
            fill = node.get('fill', box_info.get('fill', '#FAFAFA'))
            stroke = node.get('stroke', box_info.get('stroke'))
            sw = node.get('sw', box_info.get('sw', 2))
            dashed = node.get('dashed', box_info.get('dashed', False))
            # Draw container background box
            rnd = node.get('round', 1)
            if fill != 'none' or stroke:
                if fill == 'none':
                    self._box(node['id'], x, y, w, h, fill='none', stroke=stroke, sw=sw, dashed=dashed, rnd=rnd)
                else:
                    self._box(node['id'], x, y, w, h, fill=fill, stroke=stroke, sw=sw, rnd=rnd)
            # Render children inside container
            for child in node.get('children', []):
                if child.get('type') == 'title':
                    yo = child.get('y0', 3)
                    self._text(child['id'], x+5, y+yo, w-10, 18,
                               f'<b>{child["text"]}</b>',
                               fs=child.get('fs', 14), color=child.get('color','#1565C0'))
            if 'id' in node:
                self._parent_stack.append(node['id'])
                self._origin_stack.append((x, y))
            for child in node.get('children', []):
                if child.get('type') == 'title': continue
                self._render_node(child, x, y)
            if 'id' in node and self._parent_stack[-1] == node['id']:
                self._parent_stack.pop()
                self._origin_stack.pop()
            self._parent_w = old_parent_w
            self._parent_h = old_parent_h

        elif typ == 'group':
            for child in node.get('children', []):
                self._render_node(child, px, py)
        elif typ == 'title':
            pass  # Handled inside container

        elif typ == 'cell':
            is_abs = node.get('rx', False)
            if is_abs:
                x = node.get('x', px)
                y = node.get('y', py)
            else:
                w = node.get('__fill_w', node.get('w', 130))
                if node.get('cx_rel') and self._parent_w:
                    x = px + (self._parent_w - w) / 2
                else:
                    x = px + node.get('x', 0)
                h = node.get('h', 30)
                if node.get('cy_rel') and self._parent_h:
                    y = py + (self._parent_h - h) / 2
                else:
                    y = py + node.get('y', 0)
                    if 'y' not in node and 'y0' in node:
                        y = py + node['y0']
            if 'id' in node:
                self._cell_ids.add(node['id'])
            w = node.get('__fill_w', node.get('w', 130))
            h = node.get('h', 30)
            if 'id' in node:
                self._cell_positions[node['id']] = (x, y, w, h)
            # Bounds check: warn if cell extends outside parent container
            if self._parent_w is not None and self._parent_h is not None:
                rel_x = x - px  # x relative to parent
                rel_y = y - py  # y relative to parent
                if rel_x + w > self._parent_w:
                    print(f'  ⚠ OVERFLOW: {node.get("id","?")} right edge ({rel_x+w:.0f}) > parent width ({self._parent_w:.0f})')
                elif rel_x + w > self._parent_w - 3:
                    print(f'  ⚠ TIGHT: {node.get("id","?")} right ({rel_x+w:.0f}) too close to parent edge ({self._parent_w:.0f})')
                if rel_y + h > self._parent_h:
                    print(f'  ⚠ OVERFLOW: {node.get("id","?")} bottom edge ({rel_y+h:.0f}) > parent height ({self._parent_h:.0f})')
                elif rel_y + h > self._parent_h - 5:
                    print(f'  ⚠ TIGHT: {node.get("id","?")} bottom ({rel_y+h:.0f}) too close to parent bottom ({self._parent_h:.0f}), <5px margin')
            fill = node.get('fill', '#BBDEFB')
            shape = node.get('shape')
            image = node.get('image')
            has_stroke = 'stroke' in node
            stroke = node.get('stroke', '#1565C0')
            rnd = node.get('round', 1)
            if has_stroke:
                self._box(node['id'], x, y, w, h, fill=fill, stroke=stroke, sw=node.get('sw',2), shape=shape, rnd=rnd, image=image)
            else:
                self._box(node['id'], x, y, w, h, fill=fill, shape=shape, rnd=rnd, image=image)
            if 'text' in node:
                tc = node.get('tc', '#1565C0')
                txt = f'<b>{node["text"]}</b>'
                if node.get('sub'):
                    sub_fs = node.get('sub_fs', 7)
                    txt += f'<br><span style="font-size:{sub_fs}px">{node["sub"]}</span>'
                self._text(node['id']+'_t', x+2, y+2, w-4, h-4, txt, fs=node.get('fs', 12), color=tc,
                           font_family=node.get('font_family'))

        elif typ == 'text':
            if 'cx' in node:
                w = node.get('w', 280)
                x = node['cx'] - w/2
            else:
                x = node.get('x', px)
                if 'x' not in node and 'x0' in node:
                    x = px + node['x0']
            y = node.get('y', py)
            if 'y' not in node and 'y0' in node:
                y = py + node['y0']
            w = node.get('w', 200)
            h = node.get('h', 18)
            self._text(node['id'], x, y, w, h, node['text'],
                       fs=node.get('fs', 10), color=node.get('color','#333'),
                       bold=node.get('bold', False),
                       font_family=node.get('font_family'))


def render(spec_path):
    with open(spec_path) as f: spec = json.load(f)
    spec['__spec_dir'] = os.path.dirname(os.path.abspath(spec_path))
    if 'elements' in spec:
        r = FlatRenderer(spec)
        r.render()
        rough = tostring(r.mxfile, encoding='unicode')
        dom = minidom.parseString(rough.encode())
        pretty = dom.toprettyxml(indent='  ')
        lines = pretty.split('\n')[1:]
        result = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)
        out = os.path.join(os.path.dirname(spec_path), os.path.basename(spec_path).replace('.json', '.drawio'))
        with open(out, 'w') as f: f.write(result)
        print(f'Rendered: {out}')
        return

    r = Renderer(spec,
                 edges=spec.get('edges', []),
                 labels=spec.get('labels', []))

    # Edge validation: check all sources/targets exist and direction sanity
    # Edge validation: check all sources/targets exist and direction sanity
    for e in spec.get('edges', []):
        src = e.get('from')
        tgt = e.get('to')
        wpts = e.get('waypoints', [])
        if not wpts and src in r._cell_positions and tgt in r._cell_positions:
            sx,sy,sw,sh = r._cell_positions[src]
            tx,ty,tw,th = r._cell_positions[tgt]
            ex = e.get('exit','E'); ey = e.get('exit_y',0.5); ex2 = e.get('exit_x',0.5)
            en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
            ep = {'W':(sx,sy+sh*ey),'E':(sx+sw,sy+sh*ey),'N':(sx+sw*ex2,sy),'S':(sx+sw*ex2,sy+sh)}[ex]
            enp = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
            if ep[0] != enp[0] and ep[1] != enp[1]:
                print(f'  ⚠ NOWAY: {e["id"]} exit→entry needs corner ({ep[0]:.0f},{ep[1]:.0f})→({enp[0]:.0f},{enp[1]:.0f})')

        # Check for unnecessary short segments
        for i in range(len(wpts) - 1):
            x1, y1 = wpts[i]; x2, y2 = wpts[i+1]
            if 0 < abs(x1-x2)+abs(y1-y2) < 10:
                print(f'  ⚠ NUDGE: {e["id"]} waypoint {i}→{i+1} dist={abs(x1-x2)+abs(y1-y2)}px')
        # Redundant colinear waypoints
        for i in range(len(wpts) - 2):
            if (wpts[i][0]==wpts[i+1][0]==wpts[i+2][0]) or (wpts[i][1]==wpts[i+1][1]==wpts[i+2][1]):
                print(f'  ⚠ REDUNDANT: {e["id"]} waypoint {i+1} ({wpts[i+1][0]},{wpts[i+1][1]}) colinear')
        # Orthogonal check between consecutive waypoints
        for i in range(len(wpts) - 1):
            if wpts[i][0] != wpts[i+1][0] and wpts[i][1] != wpts[i+1][1]:
                print(f'  ⚠ DIAGONAL: {e["id"]} seg {i}→{i+1} {wpts[i]}→{wpts[i+1]} not orthogonal')
        # 180° reversal between waypoints
        for i in range(len(wpts) - 2):
            x1,y1=wpts[i]; x2,y2=wpts[i+1]; x3,y3=wpts[i+2]
            if y1==y2==y3 and (x2-x1)*(x3-x2)<0:
                print(f'  ⚠ REVERSE: {e["id"]} seg {i}→{i+1}→{i+2} horizontal U-turn at x={x2}')
            if x1==x2==x3 and (y2-y1)*(y3-y2)<0:
                print(f'  ⚠ REVERSE: {e["id"]} seg {i}→{i+1}→{i+2} vertical U-turn at y={y2}')

        # SKEW: exit→first waypoint not orthogonal
        if wpts and src in r._cell_positions:
            sx,sy,sw,sh = r._cell_positions[src]
            ex = e.get('exit','E'); ey = e.get('exit_y',0.5); ex2 = e.get('exit_x',0.5)
            ex_pt = {'W':(sx,sy+sh*ey),'E':(sx+sw,sy+sh*ey),'N':(sx+sw*ex2,sy),'S':(sx+sw*ex2,sy+sh)}[ex]
            if abs(wpts[0][0] - ex_pt[0]) > 5 and abs(wpts[0][1] - ex_pt[1]) > 5:
                print(f'  ⚠ SKEW: {e["id"]} exit→wp0 ({ex_pt[0]:.0f},{ex_pt[1]:.0f})→({wpts[0][0]},{wpts[0][1]})')
        # SKEW: last waypoint→entry not orthogonal
        if wpts and tgt in r._cell_positions:
            tx,ty,tw,th = r._cell_positions[tgt]
            en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
            en_pt = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
            if abs(wpts[-1][0] - en_pt[0]) > 5 and abs(wpts[-1][1] - en_pt[1]) > 5:
                print(f'  ⚠ SKEW: {e["id"]} last wp ({wpts[-1][0]},{wpts[-1][1]})→entry ({en_pt[0]:.0f},{en_pt[1]:.0f})')
            # Check last waypoint not on target edge (parallel overlap)
            if en == 'W' and wpts[-1][0] == tx:
                print(f'  ⚠ EDGE: {e["id"]} last wp x={wpts[-1][0]} on target left edge (enter=W), move left of {tx}')
            elif en == 'E' and wpts[-1][0] == tx + tw:
                print(f'  ⚠ EDGE: {e["id"]} last wp x={wpts[-1][0]} on target right edge (enter=E), move right of {tx+tw}')
            elif en == 'N' and wpts[-1][1] == ty:
                print(f'  ⚠ EDGE: {e["id"]} last wp y={wpts[-1][1]} on target top edge (enter=N), move above {ty}')
            elif en == 'S' and wpts[-1][1] == ty + th:
                print(f'  ⚠ EDGE: {e["id"]} last wp y={wpts[-1][1]} on target bottom edge (enter=S), move below {ty+th}')
        # Check last segment direction matches enter direction
        if wpts and tgt in r._cell_positions:
            tx,ty,tw,th = r._cell_positions[tgt]
            en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
            en_pt = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
            lwx, lwy = wpts[-1]
            # For enter=W/E, last segment should be horizontal (same y). For enter=N/S, vertical (same x).
            if en in ('W', 'E') and lwy != en_pt[1]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment vertical but enter={en} expects horizontal')
            elif en in ('N', 'S') and lwx != en_pt[0]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment horizontal but enter={en} expects vertical')
            # Check direction: entering W→arrow right, last segment should move right (lwx < en_pt[0])
            if en == 'W' and lwx > en_pt[0]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment moves LEFT but enter=W expects approach from LEFT')
            elif en == 'E' and lwx < en_pt[0]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment moves RIGHT but enter=E expects approach from RIGHT')
            elif en == 'N' and lwy > en_pt[1]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment moves UP but enter=N expects approach from TOP')
            elif en == 'S' and lwy < en_pt[1]:
                print(f'  ⚠ MISDIRECT: {e["id"]} last segment moves DOWN but enter=S expects approach from BOTTOM')
        # Check if last segment is too short for arrowhead
        if wpts and tgt in r._cell_positions:
            tx,ty,tw,th = r._cell_positions[tgt]
            en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
            en_pt = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
            seg_len = abs(wpts[-1][0] - en_pt[0]) + abs(wpts[-1][1] - en_pt[1])
            if seg_len < 12 and seg_len > 0:
                print(f'  ⚠ ARROW: {e["id"]} last segment only {seg_len}px (arrowhead ≈12px), extend to ≥12px')
        if src and src not in r._cell_ids:
            print(f'  ⚠ DANGLING EDGE: {e["id"]} source "{src}" not found')
        if tgt and tgt not in r._cell_ids:
            print(f'  ⚠ DANGLING EDGE: {e["id"]} target "{tgt}" not found')
        # Check exit direction vs first waypoint
        wpts = e.get('waypoints', [])
        if wpts and src in r._cell_positions:
            sx, sy, sw, sh = r._cell_positions[src]
            ex = e.get('exit', 'E')
            exit_y = e.get('exit_y', 0.5)
            exit_x = e.get('exit_x', 0.5)
            fwx, fwy = wpts[0]
            # Check first segment aligns with exit direction
            if ex == 'W' and abs(fwy - (sy + sh * exit_y)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} exit=W but first waypoint y={fwy} ≠ exit_y={sy+sh*exit_y:.0f}')
            elif ex == 'E' and abs(fwy - (sy + sh * exit_y)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} exit=E but first waypoint y={fwy} ≠ exit_y={sy+sh*exit_y:.0f}')
            elif ex == 'N' and abs(fwx - (sx + sw * exit_x)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} exit=N but first waypoint x={fwx} ≠ exit_x={sx+sw*exit_x:.0f}')
            elif ex == 'S' and abs(fwx - (sx + sw * exit_x)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} exit=S but first waypoint x={fwx} ≠ exit_x={sx+sw*exit_x:.0f}')
            if ex == 'W' and fwx > sx:
                print(f'  ⚠ PATH: {e["id"]} exit=W (left) but first waypoint x={fwx} > source x={sx}')
            elif ex == 'E' and fwx < sx + sw:
                print(f'  ⚠ PATH: {e["id"]} exit=E (right) but first waypoint x={fwx} < source right ({sx+sw})')
            elif ex == 'N' and fwy > sy:
                print(f'  ⚠ PATH: {e["id"]} exit=N (top) but first waypoint y={fwy} > source y={sy}')
            elif ex == 'S' and fwy < sy + sh:
                print(f'  ⚠ PATH: {e["id"]} exit=S (bottom) but first waypoint y={fwy} < source bottom ({sy+sh})')
        # Check enter direction vs last waypoint
        if wpts and tgt in r._cell_positions:
            tx, ty, tw, th = r._cell_positions[tgt]
            en = e.get('enter', 'W')
            en_x = e.get('entry_x', 0.5)
            en_y = e.get('entry_y', 0.5)
            lwx, lwy = wpts[-1]
            # Check last segment aligns with enter direction
            if en == 'W' and abs(lwy - (ty + th * en_y)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} enter=W but last waypoint y={lwy} ≠ entry_y={ty+th*en_y:.0f}')
            elif en == 'E' and abs(lwy - (ty + th * en_y)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} enter=E but last waypoint y={lwy} ≠ entry_y={ty+th*en_y:.0f}')
            elif en == 'N' and abs(lwx - (tx + tw * en_x)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} enter=N but last waypoint x={lwx} ≠ entry_x={tx+tw*en_x:.0f}')
            elif en == 'S' and abs(lwx - (tx + tw * en_x)) > 2:
                print(f'  ⚠ APPROACH: {e["id"]} enter=S but last waypoint x={lwx} ≠ entry_x={tx+tw*en_x:.0f}')
            if en == 'W' and lwx > tx:
                print(f'  ⚠ PATH: {e["id"]} enter=W (left) but last waypoint x={lwx} > target x={tx}')
            elif en == 'E' and lwx < tx + tw:
                print(f'  ⚠ PATH: {e["id"]} enter=E (right) but last waypoint x={lwx} < target right ({tx+tw})')
            elif en == 'N' and lwy > ty:
                print(f'  ⚠ PATH: {e["id"]} enter=N (top) but last waypoint y={lwy} > target y={ty}')
            elif en == 'S' and lwy < ty + th:
                print(f'  ⚠ PATH: {e["id"]} enter=S (bottom) but last waypoint y={lwy} < target bottom ({ty+th})')

    # Overlap check: edge segments crossing non-source/target cells
    for e in spec.get('edges', []):
        wpts = e.get('waypoints', [])
        src = e.get('from')
        tgt = e.get('to')
        # Don't skip the target — an edge must not cross its target before entry.
        # The final entry segment is excluded by checking distance to entry point.
        skip = {src}
        # Build full path: exit_pt + waypoints + entry_pt for complete coverage
        ep, enp = None, None
        if src in r._cell_positions:
            sx,sy,sw,sh = r._cell_positions[src]
            ex = e.get('exit','E'); ey = e.get('exit_y',0.5); ex2 = e.get('exit_x',0.5)
            ep = {'W':(sx,sy+sh*ey),'E':(sx+sw,sy+sh*ey),'N':(sx+sw*ex2,sy),'S':(sx+sw*ex2,sy+sh)}[ex]
        if tgt in r._cell_positions:
            tx,ty,tw,th = r._cell_positions[tgt]
            en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
            enp = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
        if not wpts and ep and enp:
            pts = [(ep[0], ep[1]), (ep[0], enp[1]), (enp[0], enp[1])]
        elif wpts:
            pts = list(wpts)
            if ep: pts.insert(0, (ep[0], ep[1]))
            if enp: pts.append((enp[0], enp[1]))
        else:
            pts = []
        if len(pts) < 2:
            continue
        # Check each segment between consecutive points
        for i in range(len(pts) - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i+1]
            # Split non-orthogonal segments into BOTH possible orthogonal paths
            segs = []
            if x1 != x2 and y1 != y2:
                segs = [(x1, y1, x2, y1), (x2, y1, x2, y2),  # horiz first
                        (x1, y1, x1, y2), (x1, y2, x2, y2)]  # vert first
            else:
                segs = [(x1, y1, x2, y2)]
            for sx1, sy1, sx2, sy2 in segs:
                for cid, (cx, cy, cw, ch) in r._cell_positions.items():
                    if cid in skip or cid in r._container_ids:
                        continue
                    # Skip the final entry segment into the target cell itself
                    if cid == tgt and enp and abs(sx2 - enp[0]) < 2 and abs(sy2 - enp[1]) < 2:
                        continue
                    if sy1 == sy2:
                        if cy <= sy1 <= cy + ch and min(sx1, sx2) < cx + cw and max(sx1, sx2) > cx:
                            print(f'  ⚠ CROSS: {e["id"]} segment ({sx1},{sy1})→({sx2},{sy2}) crosses "{cid}" ({cx},{cy},{cw}x{ch})')
                    elif sx1 == sx2:
                        if cx <= sx1 <= cx + cw and min(sy1, sy2) < cy + ch and max(sy1, sy2) > cy:
                            print(f'  ⚠ CROSS: {e["id"]} segment ({sx1},{sy1})→({sx2},{sy2}) crosses "{cid}" ({cx},{cy},{cw}x{ch})')

    # Label-edge overlap check: labels crossing edge segments
    for lbl in spec.get('labels', []):
        lx, ly, lw, lh = lbl.get('x',0), lbl.get('y',0), lbl.get('w',100), lbl.get('h',14)
        lbl_id = lbl.get('id','?')
        for e in spec.get('edges', []):
            wpts = e.get('waypoints', [])
            # Build segment list: explicit waypoints or compute exit→entry orthogonal path
            src, tgt = e.get('from'), e.get('to')
            if not wpts and src in r._cell_positions and tgt in r._cell_positions:
                sx,sy,sw,sh = r._cell_positions[src]
                tx,ty,tw,th = r._cell_positions[tgt]
                ex = e.get('exit','E'); ey = e.get('exit_y',0.5); ex2 = e.get('exit_x',0.5)
                en = e.get('enter','W'); eny = e.get('entry_y',0.5); enx = e.get('entry_x',0.5)
                ep = {'W':(sx,sy+sh*ey),'E':(sx+sw,sy+sh*ey),'N':(sx+sw*ex2,sy),'S':(sx+sw*ex2,sy+sh)}[ex]
                enp = {'W':(tx,ty+th*eny),'E':(tx+tw,ty+th*eny),'N':(tx+tw*enx,ty),'S':(tx+tw*enx,ty+th)}[en]
                # Orthogonal path from ep to enp: corner at intermediate point
                pts = [(ep[0], ep[1]), (ep[0], enp[1]), (enp[0], enp[1])]
            else:
                pts = list(wpts)
            for i in range(len(pts) - 1):
                x1, y1 = pts[i]; x2, y2 = pts[i+1]
                if y1 == y2 and ly <= y1 <= ly + lh:
                    if min(x1, x2) < lx + lw and max(x1, x2) > lx:
                        print(f'  ⚠ ONARROW: "{lbl_id}" on {e["id"]} at y={y1} x={min(x1,x2)}-{max(x1,x2)}')
                elif x1 == x2 and lx <= x1 <= lx + lw:
                    if min(y1, y2) < ly + lh and max(y1, y2) > ly:
                        print(f'  ⚠ ONARROW: "{lbl_id}" on {e["id"]} at x={x1} y={min(y1,y2)}-{max(y1,y2)}')

    # Text overlap check: cell text vs other cells, labels vs cells
    for cid, (cx, cy, cw, ch) in r._cell_positions.items():
        if cid in r._container_ids:
            continue  # skip containers (title text naturally overlaps children)
        # Cell text area is at (cx+2, cy+2, cw-4, ch-4)
        tx, ty, tw, th = cx + 2, cy + 2, cw - 4, ch - 4
        for oid, (ox, oy, ow, oh) in r._cell_positions.items():
            if oid == cid or oid in r._container_ids:
                continue
            # Check text bbox vs other cell bbox
            if tx < ox + ow and tx + tw > ox and ty < oy + oh and ty + th > oy:
                # Only warn if overlap is significant (>20px²)
                ox1, oy1 = max(tx, ox), max(ty, oy)
                ox2, oy2 = min(tx+tw, ox+ow), min(ty+th, oy+oh)
                area = max(0, ox2-ox1) * max(0, oy2-oy1)
                if area > 20:
                    print(f'  ⚠ TEXT: "{cid}" text overlaps "{oid}" ({ox},{oy},{ow}x{oh}) area={area}px²')

    # Label overlap check: standalone labels vs cells
    for lbl in spec.get('labels', []):
        lx, ly, lw, lh = lbl.get('x',0), lbl.get('y',0), lbl.get('w',100), lbl.get('h',14)
        for cid, (cx, cy, cw, ch) in r._cell_positions.items():
            if cid in r._container_ids:
                continue
            if lx < cx + cw and lx + lw > cx and ly < cy + ch and ly + lh > cy:
                ox1, oy1 = max(lx, cx), max(ly, cy)
                ox2, oy2 = min(lx+lw, cx+cw), min(ly+lh, cy+ch)
                area = max(0, ox2-ox1) * max(0, oy2-oy1)
                if area > 20:
                    print(f'  ⚠ LABEL: "{lbl.get("id","?")}" ({lx},{ly},{lw}x{lh}) overlaps "{cid}" ({cx},{cy},{cw}x{ch})')

    # Label-label overlap check
    all_labels = spec.get('labels', [])
    for i in range(len(all_labels)):
        for j in range(i + 1, len(all_labels)):
            a, b = all_labels[i], all_labels[j]
            ax, ay, aw, ah = a.get('x',0), a.get('y',0), a.get('w',100), a.get('h',14)
            bx, by, bw, bh = b.get('x',0), b.get('y',0), b.get('w',100), b.get('h',14)
            if ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by:
                print(f'  ⚠ LABELS: "{a.get("id","?")}" and "{b.get("id","?")}" overlap')

    # ── Spacing & alignment checks ─────────────────────────────
    # Check cell gaps within each container row
    from collections import defaultdict
    cont_cells = defaultdict(list)
    for cid, (cx, cy, cw, ch) in r._cell_positions.items():
        if cid in r._container_ids: continue
        for cont_id in r._container_ids:
            cx_, cy_, cw_, ch_ = r._cell_positions[cont_id]
            if cx_ <= cx <= cx_ + cw_ and cx_ <= cx + cw <= cx_ + cw_ and cy_ <= cy <= cy_ + ch_:
                cont_cells[cont_id].append((cid, cx, cy, cw, ch))
                break
    for cont_id, cells in cont_cells.items():
        if len(cells) < 2: continue
        rows = defaultdict(list)
        for cid, cx, cy, cw, ch in cells:
            rows[round((cy + ch/2)/5)*5].append((cid, cx, cw))
        for cy_row, row_cells in rows.items():
            if len(row_cells) < 2: continue
            row_cells.sort(key=lambda x: x[1])
            gaps = [row_cells[i+1][1] - (row_cells[i][1] + row_cells[i][2]) for i in range(len(row_cells)-1)]
            if len(gaps) >= 2 and max(gaps) - min(gaps) > 3:
                print(f'  ⚠ GAP: {cont_id} y≈{cy_row} gaps: {gaps} (uneven)')
            for i in range(len(row_cells)-1):
                gap = row_cells[i+1][1] - (row_cells[i][1] + row_cells[i][2])
                if gap < 6:
                    print(f'  ⚠ TIGHT: {row_cells[i][0]}→{row_cells[i+1][0]} only {gap}px gap')

    # Check for cell overlap (same row, y-overlapping cells)
    all_pos = sorted([(cid, cx, cy, cw, ch) for cid, (cx, cy, cw, ch) in r._cell_positions.items() if cid not in r._container_ids], key=lambda x: (x[2], x[1]))
    for i, (cid_a, ax, ay, aw, ah) in enumerate(all_pos):
        for cid_b, bx, by, bw, bh in all_pos[i+1:]:
            if by > ay + ah: break  # past this row, move to next
            if not (ay < by + bh and ay + ah > by): continue  # no y overlap
            overlap = (ax + aw) - bx
            if overlap > 2 and ax < bx:
                print(f'  ⚠ OVERLAP: "{cid_a}" right={ax+aw} > "{cid_b}" left={bx} by {overlap:.0f}px')

    rough = tostring(r.mxfile, encoding='unicode')
    dom = minidom.parseString(rough.encode())
    pretty = dom.toprettyxml(indent='  ')
    lines = pretty.split('\n')[1:]
    result = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)
    out = os.path.join(os.path.dirname(spec_path), os.path.basename(spec_path).replace('.json', '.drawio'))
    with open(out, 'w') as f: f.write(result)
    print(f'Rendered: {out}')

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: render.py spec.json', file=sys.stderr)
        sys.exit(2)
    render(sys.argv[1])
