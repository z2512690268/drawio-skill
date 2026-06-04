#!/usr/bin/env python3
"""Analyze recursive-hierarchy fmrl spec."""
import json, sys
from collections import defaultdict

def box(node):
    if 'box' in node: return node['box']
    if all(k in node for k in ('x','y','w','h')): return node
    return None

def collect(node, cells=None, depth=0):
    if cells is None: cells = {}
    b = box(node)
    if b and node.get('id'):
        cells[node['id']] = {'box': b, 'type': node.get('type',''), 'text': node.get('text','')[:30]}
    for child in node.get('children', []): collect(child, cells, depth+1)
    return cells

def report(path):
    # Read from rendered drawio file for actual positions
    import xml.etree.ElementTree as ET
    drawio_path = path.replace('fmrl_spec.json', 'fmrl_architecture.drawio')
    with open(drawio_path) as f: xml_content = f.read()
    # Also read spec for hierarchy
    with open(path) as f: spec = json.load(f)
    C = spec['canvas']

    # Build cells from drawio XML (has all computed positions)
    cells = {}
    t = ET.fromstring(xml_content)
    for c in t.iter():
        if c.tag != 'mxCell': continue
        cid = c.get('id','')
        if cid in ('0','1'): continue
        g = c.find('mxGeometry')
        if g is None: continue
        x = g.get('x', None)
        if x is None: continue
        x, y = float(x), float(g.get('y', 0))
        w, h = float(g.get('width', 0)), float(g.get('height', 0))
        val = c.get('value','').replace('<b>','').replace('</b>','').replace('<br>',' ')[:40]
        cells[cid] = {'box':{'x':x,'y':y,'w':w,'h':h}, 'type': '', 'text': val}
    print("="*72)
    print("  层次化布局分析")
    print("="*72)

    def walk(node, d=0):
        cid = node.get('id','')
        b = box(node)
        pos = f'({b["x"]:.0f},{b["y"]:.0f})→({b["x"]+b["w"]:.0f},{b["y"]+b["h"]:.0f})' if b else ''
        txt = f' "{node.get("text","")[:30]}"' if node.get('text') else ''
        if cid: print(f'{"  "*d}{cid:12s} [{node.get("type","?"):6s}] {pos}{txt}')
        for c in node.get('children',[]): walk(c, d+1)

    print("\n树形结构:"); walk(spec['root'])

    print(f"\n{'─'*72}")
    print("箭头分析")
    emap = {'E':(1,0.5),'W':(0,0.5),'S':(0.5,1),'N':(0.5,0)}
    for e in spec.get('edges',[]):
        s, t = cells.get(e['from']), cells.get(e['to'])
        if not s or not t: print(f"  ⚠ {e['id']}: 找不到{e['from']}或{e['to']}"); continue
        sb, tb = s['box'], t['box']
        ex,ey = emap.get(e.get('exit','E'),(1,0.5))
        nx,ny = emap.get(e.get('enter','W'),(0,0.5))
        sp = (sb['x']+sb['w']*ex, sb['y']+sb['h']*ey)
        ep = (tb['x']+tb['w']*nx, tb['y']+tb['h']*ny)
        d = ((ep[0]-sp[0])**2+(ep[1]-sp[1])**2)**0.5
        w = ''; d = int(d)
        if d < 12: w = ' ⚠太短'
        if e.get('exit')=='E' and tb['x']<sb['x']: w+=' ⚠出口右目标左'
        if e.get('exit')=='S' and tb['y']<sb['y']: w+=' ⚠出口下目标上'
        dw = ' (虚线)' if e.get('dashed') else ''
        print(f"  {e['id']}{dw}: ({sp[0]:.0f},{sp[1]:.0f})→({ep[0]:.0f},{ep[1]:.0f}) d={d}{w}")

    # Container alignment
    cons = []
    def find_cons(node):
        if node.get('type')=='container' and node.get('id'):
            b = box(node)
            if b and b['w']>80: cons.append((node['id'],b))
        for c in node.get('children',[]): find_cons(c)
    find_cons(spec['root'])
    if len(cons)>=2:
        print(f"\n容器对齐:")
        for i,(cid,b) in enumerate(cons):
            aligns=[]
            if i>0:
                pb=cons[0][1]
                if abs(b['y']-pb['y'])<=3: aligns.append('顶✓')
                if abs(b['y']+b['h']-pb['y']-pb['h'])<=3: aligns.append('底✓')
                if abs(b['x']-pb['x'])<=3: aligns.append('左✓')
            print(f"  {cid:12s}: y={b['y']:.0f} h={b['h']:.0f} bot={b['y']+b['h']:.0f} x={b['x']:.0f} w={b['w']:.0f}  {','.join(aligns)}")

    print(f"\n{'─'*72}")
    print(f"摘要: {len(cells)} 组件, {len(spec.get('edges',[]))} 箭头")
    bs = [v['box'] for v in cells.values()]
    if bs:
        mx = min(b['x'] for b in bs); x2 = max(b['x']+b.get('w',0) for b in bs)
        my = min(b['y'] for b in bs); y2 = max(b['y']+b.get('h',0) for b in bs)
        print(f"范围: x=[{mx:.0f},{x2:.0f}] y=[{my:.0f},{y2:.0f}]")
        print(f"画布: {C['width']}×{C['height']} → 下余 {C['height']-y2:.0f} 右余 {C['width']-x2:.0f}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: analyze_layout.py spec.json', file=sys.stderr)
        sys.exit(2)
    report(sys.argv[1])
