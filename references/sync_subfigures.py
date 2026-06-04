#!/usr/bin/env python3
"""Extract editable drawio subfigures and sync them back into a master drawio.

This script treats subfigures as editable mxCell fragments, not raster images.
Use `extract` to create local drawio files from the master figure, edit those
files in diagrams.net/draw.io, then use `sync` to replace the corresponding
region in the master with the edited cells.
"""
import argparse
import copy
import json
import os
from xml.dom import minidom
from xml.etree import ElementTree as ET


BASE_IDS = {'0', '1'}
DEFAULT_MAIN = 'trace_guard_spec.drawio'
DEFAULT_SPEC = 'trace_guard_spec.json'
DEFAULT_SUBFIG_DIR = 'subfigures'


def load_json(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def read_drawio(path):
    return ET.parse(path)


def write_drawio(tree, path):
    rough = ET.tostring(tree.getroot(), encoding='unicode')
    dom = minidom.parseString(rough.encode())
    pretty = dom.toprettyxml(indent='  ')
    lines = pretty.split('\n')[1:]
    result = '<?xml version="1.0" encoding="UTF-8"?>\n' + '\n'.join(lines)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(result)


def graph_root(tree):
    root = tree.getroot().find('.//mxGraphModel/root')
    if root is None:
        raise ValueError('drawio file does not contain mxGraphModel/root')
    return root


def first_model(tree):
    model = tree.getroot().find('.//mxGraphModel')
    if model is None:
        raise ValueError('drawio file does not contain mxGraphModel')
    return model


def subfigures(spec):
    for item in spec.get('elements', []):
        if item.get('type') != 'subfigure_crop':
            continue
        yield {
            'id': item['id'],
            'x': float(item['x']),
            'y': float(item['y']),
            'w': float(item['w']),
            'h': float(item['h']),
            'path': item.get('drawio') or item.get('subfigure') or os.path.join(DEFAULT_SUBFIG_DIR, f'{item["id"]}.drawio'),
        }


def wanted_subfigures(spec, wanted_id):
    items = list(subfigures(spec))
    if wanted_id:
        items = [item for item in items if item['id'] == wanted_id]
        if not items:
            raise ValueError(f'No subfigure_crop with id {wanted_id!r}')
    return items


def geom(cell):
    return cell.find('mxGeometry')


def cell_bbox(cell):
    g = geom(cell)
    if g is None:
        return None
    try:
        x = float(g.get('x', '0'))
        y = float(g.get('y', '0'))
        w = float(g.get('width', '0'))
        h = float(g.get('height', '0'))
    except ValueError:
        return None
    if not w and not h and cell.get('edge') == '1':
        pts = edge_points(cell)
        if not pts:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)
    return x, y, w, h


def edge_points(cell):
    g = geom(cell)
    if g is None:
        return []
    points = []
    for tag in ('sourcePoint', 'targetPoint'):
        p = g.find(f"mxPoint[@as='{tag}']")
        if p is not None and p.get('x') is not None and p.get('y') is not None:
            points.append((float(p.get('x')), float(p.get('y'))))
    arr = g.find("Array[@as='points']")
    if arr is not None:
        for p in arr.findall('mxPoint'):
            if p.get('x') is not None and p.get('y') is not None:
                points.append((float(p.get('x')), float(p.get('y'))))
    return points


def contained(bbox, region, pad=1.0):
    if bbox is None:
        return False
    x, y, w, h = bbox
    rx, ry, rw, rh = region
    return (
        x >= rx - pad and
        y >= ry - pad and
        x + w <= rx + rw + pad and
        y + h <= ry + rh + pad
    )


def point_contained(point, region, pad=1.0):
    x, y = point
    rx, ry, rw, rh = region
    return rx - pad <= x <= rx + rw + pad and ry - pad <= y <= ry + rh + pad


def region_tuple(info):
    return info['x'], info['y'], info['w'], info['h']


def is_in_region(cell, region):
    if cell.get('id') in BASE_IDS:
        return False
    bbox = cell_bbox(cell)
    if contained(bbox, region):
        return True
    pts = edge_points(cell)
    return bool(pts) and all(point_contained(p, region) for p in pts)


def selected_cells(root, region):
    cells = {cell.get('id'): cell for cell in root.findall('mxCell') if cell.get('id')}
    selected = {cid for cid, cell in cells.items() if is_in_region(cell, region)}

    changed = True
    while changed:
        changed = False
        for cid, cell in cells.items():
            if cid in selected or cid in BASE_IDS:
                continue
            if cell.get('source') in selected and cell.get('target') in selected:
                selected.add(cid)
                changed = True

        for cid in list(selected):
            parent = cells[cid].get('parent') if cid in cells else None
            if parent and parent not in BASE_IDS and parent not in selected:
                selected.add(parent)
                changed = True

    return [cell for cell in root.findall('mxCell') if cell.get('id') in selected]


def shift_geometry(cell, dx, dy):
    g = geom(cell)
    if g is None:
        return
    if g.get('x') is not None:
        g.set('x', clean_num(float(g.get('x')) + dx))
    if g.get('y') is not None:
        g.set('y', clean_num(float(g.get('y')) + dy))
    for p in g.findall('.//mxPoint'):
        if p.get('x') is not None:
            p.set('x', clean_num(float(p.get('x')) + dx))
        if p.get('y') is not None:
            p.set('y', clean_num(float(p.get('y')) + dy))


def clean_num(value):
    if abs(value - round(value)) < 0.001:
        return str(int(round(value)))
    return f'{value:.3f}'.rstrip('0').rstrip('.')


def make_empty_drawio(name, width, height):
    mxfile = ET.Element('mxfile', host='drawio', modified='2025-05-22T00:00:00Z', version='21.1.2')
    diagram = ET.SubElement(mxfile, 'diagram', id=f'{name}-subfigure', name=name)
    model = ET.SubElement(
        diagram,
        'mxGraphModel',
        dx='0',
        dy='0',
        grid='0',
        gridSize='10',
        guides='1',
        tooltips='1',
        connect='1',
        arrows='1',
        fold='1',
        page='1',
        pageScale='1',
        pageWidth=clean_num(width),
        pageHeight=clean_num(height),
        math='0',
        shadow='0',
    )
    root = ET.SubElement(model, 'root')
    ET.SubElement(root, 'mxCell', id='0')
    ET.SubElement(root, 'mxCell', id='1', parent='0')
    return ET.ElementTree(mxfile)


def local_id(master_id, prefix):
    return master_id[len(prefix):] if master_id.startswith(prefix) else master_id


def prefixed_id(local, prefix):
    return local if local in BASE_IDS or local.startswith(prefix) else prefix + local


def extract_one(main_tree, info, base_dir):
    region = region_tuple(info)
    prefix = f'{info["id"]}__'
    out_path = os.path.join(base_dir, info['path'])
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    out_tree = make_empty_drawio(info['id'], info['w'], info['h'])
    out_root = graph_root(out_tree)
    cells = selected_cells(graph_root(main_tree), region)
    id_map = {cell.get('id'): local_id(cell.get('id'), prefix) for cell in cells}

    for cell in cells:
        new_cell = copy.deepcopy(cell)
        cid = cell.get('id')
        new_cell.set('id', id_map[cid])
        for attr in ('source', 'target', 'parent'):
            ref = new_cell.get(attr)
            if ref in id_map:
                new_cell.set(attr, id_map[ref])
            elif attr == 'parent':
                new_cell.set(attr, '1')
        shift_geometry(new_cell, -info['x'], -info['y'])
        out_root.append(new_cell)

    write_drawio(out_tree, out_path)
    print(f'extracted {info["id"]}: {len(cells)} cells -> {out_path}')


def removable_main_cell(cell, info):
    cid = cell.get('id', '')
    if cid in BASE_IDS:
        return False
    if cid == info['id'] or cid.startswith(f'{info["id"]}__'):
        return True
    return is_in_region(cell, region_tuple(info))


def sync_one(main_tree, info, base_dir):
    sub_path = os.path.join(base_dir, info['path'])
    if not os.path.exists(sub_path):
        raise FileNotFoundError(f'Missing subfigure drawio: {sub_path}')

    main_root = graph_root(main_tree)
    removed = 0
    for cell in list(main_root.findall('mxCell')):
        if removable_main_cell(cell, info):
            main_root.remove(cell)
            removed += 1

    sub_tree = read_drawio(sub_path)
    sub_root = graph_root(sub_tree)
    prefix = f'{info["id"]}__'
    cells = [cell for cell in sub_root.findall('mxCell') if cell.get('id') not in BASE_IDS]
    id_map = {cell.get('id'): prefixed_id(cell.get('id'), prefix) for cell in cells}

    for cell in cells:
        new_cell = copy.deepcopy(cell)
        cid = cell.get('id')
        new_cell.set('id', id_map[cid])
        for attr in ('source', 'target', 'parent'):
            ref = new_cell.get(attr)
            if ref in id_map:
                new_cell.set(attr, id_map[ref])
            elif attr == 'parent':
                new_cell.set(attr, '1')
        shift_geometry(new_cell, info['x'], info['y'])
        main_root.append(new_cell)

    print(f'synced {info["id"]}: removed {removed}, inserted {len(cells)} cells')


def set_page_size_from_spec(tree, spec):
    canvas = spec.get('canvas', {})
    model = first_model(tree)
    if canvas.get('width'):
        model.set('pageWidth', clean_num(float(canvas['width'])))
    if canvas.get('height'):
        model.set('pageHeight', clean_num(float(canvas['height'])))


def main():
    parser = argparse.ArgumentParser(description='Extract/sync editable drawio subfigures.')
    parser.add_argument('command', choices=['list', 'extract', 'sync'])
    parser.add_argument('--spec', default=DEFAULT_SPEC)
    parser.add_argument('--main', default=DEFAULT_MAIN)
    parser.add_argument('--id', help='Only process one subfigure id')
    parser.add_argument('--out', help='Output master drawio for sync; defaults to overwriting --main')
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(args.spec))
    spec = load_json(args.spec)
    infos = wanted_subfigures(spec, args.id)

    if args.command == 'list':
        for info in infos:
            print(f'{info["id"]}: ({clean_num(info["x"])}, {clean_num(info["y"])}) {clean_num(info["w"])}x{clean_num(info["h"])} -> {info["path"]}')
        return

    main_path = args.main if os.path.isabs(args.main) else os.path.join(base_dir, args.main)
    main_tree = read_drawio(main_path)

    if args.command == 'extract':
        for info in infos:
            extract_one(main_tree, info, base_dir)
        return

    if args.command == 'sync':
        for info in infos:
            sync_one(main_tree, info, base_dir)
        set_page_size_from_spec(main_tree, spec)
        out_arg = args.out or args.main
        out_path = out_arg if os.path.isabs(out_arg) else os.path.join(base_dir, out_arg)
        write_drawio(main_tree, out_path)
        print(f'wrote master: {out_path}')


if __name__ == '__main__':
    main()
