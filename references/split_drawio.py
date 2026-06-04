#!/usr/bin/env python3
"""
Split a .drawio file into sub-diagrams based on spatial clustering.
Each cluster of spatially close cells becomes a separate .drawio file.
"""

import re
import math
import os
import sys
import copy

# ============================================================
# 1. Parse the .drawio file
# ============================================================

def parse_drawio(filepath):
    """Parse a .drawio file and return structured cell data."""
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Extract header components
    mxfile_match = re.search(r'(<mxfile[^>]*>)', content)
    diagram_match = re.search(r'(<diagram[^>]*>)', content)
    graphmodel_match = re.search(r'(<mxGraphModel[^>]*>)', content)

    header = {
        'mxfile': mxfile_match.group(1) if mxfile_match else '<mxfile>',
        'diagram': diagram_match.group(1) if diagram_match else '<diagram>',
        'graphmodel': graphmodel_match.group(1) if graphmodel_match else '<mxGraphModel>',
    }

    # Line-by-line parsing (drawio outputs one cell per block)
    lines = content.split('\n')

    class Cell:
        def __init__(self):
            self.id = None
            self.is_vertex = False
            self.is_edge = False
            self.x = None
            self.y = None
            self.w = 1
            self.h = 1
            self.value = ''
            self.parent = '1'
            self.source = None
            self.target = None
            self.xml_lines = []
            self.has_source_point = False
            self.has_target_point = False
            self.source_point_x = None
            self.source_point_y = None
            self.target_point_x = None
            self.target_point_y = None
            self.waypoints = []  # list of (x, y) tuples

    cells = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Detect start of a cell block
        if '<mxCell' in stripped and ('</mxCell>' not in stripped) and ('/>' not in stripped):
            cell = Cell()
            cell.xml_lines = [line]
            i += 1
            while i < len(lines) and '</mxCell>' not in lines[i]:
                cell.xml_lines.append(lines[i])
                i += 1
            if i < len(lines):
                cell.xml_lines.append(lines[i])

            full = '\n'.join(cell.xml_lines)

            # Parse id
            m = re.search(r'id="([^"]+)"', full)
            cell.id = m.group(1) if m else None

            cell.is_vertex = 'vertex="1"' in full
            cell.is_edge = 'edge="1"' in full

            # Parse value (text label)
            m = re.search(r'value="([^"]*)"', full)
            cell.value = m.group(1) if m else ''

            # Parse parent
            m = re.search(r'parent="([^"]+)"', full)
            cell.parent = m.group(1) if m else '1'

            # Parse source/target
            m = re.search(r'source="([^"]+)"', full)
            cell.source = m.group(1) if m else None
            m = re.search(r'target="([^"]+)"', full)
            cell.target = m.group(1) if m else None

            # Parse mxGeometry
            geo_match = re.search(r'<mxGeometry[^>]*/>', full)
            if geo_match:
                geo_str = geo_match.group()
                m = re.search(r' x="([^"]+)"', geo_str)
                cell.x = float(m.group(1)) if m else None
                m = re.search(r' y="([^"]+)"', geo_str)
                cell.y = float(m.group(1)) if m else None
                m = re.search(r' width="([^"]+)"', geo_str)
                cell.w = float(m.group(1)) if m else 1
                m = re.search(r' height="([^"]+)"', geo_str)
                cell.h = float(m.group(1)) if m else 1

            # Parse sourcePoint, targetPoint, waypoints (for edges)
            sp = re.search(r'<mxPoint x="([^"]+)" y="([^"]+)" as="sourcePoint"\s*/>', full)
            if sp:
                cell.has_source_point = True
                cell.source_point_x = float(sp.group(1))
                cell.source_point_y = float(sp.group(2))

            tp = re.search(r'<mxPoint x="([^"]+)" y="([^"]+)" as="targetPoint"\s*/>', full)
            if tp:
                cell.has_target_point = True
                cell.target_point_x = float(tp.group(1))
                cell.target_point_y = float(tp.group(2))

            # Waypoints: <mxPoint x="..." y=""/> inside <Array as="points">
            # Use a more precise regex to match waypoints within Array
            array_match = re.search(r'<Array as="points">(.*?)</Array>', full, re.DOTALL)
            if array_match:
                array_content = array_match.group(1)
                for wp in re.finditer(r'<mxPoint x="([^"]+)" y="([^"]+)"\s*/>', array_content):
                    cell.waypoints.append((float(wp.group(1)), float(wp.group(2))))

            cells.append(cell)

        elif '<mxCell' in stripped and ('/>' in stripped or '</mxCell>' in stripped):
            cell = Cell()
            cell.xml_lines = [line]

            m = re.search(r'id="([^"]+)"', line)
            cell.id = m.group(1) if m else None
            cell.is_vertex = 'vertex="1"' in line
            cell.is_edge = 'edge="1"' in line

            m = re.search(r'parent="([^"]+)"', line)
            cell.parent = m.group(1) if m else '1'

            m = re.search(r'source="([^"]+)"', line)
            cell.source = m.group(1) if m else None
            m = re.search(r'target="([^"]+)"', line)
            cell.target = m.group(1) if m else None

            cells.append(cell)

        i += 1

    return cells, header, content


# ============================================================
# 2. Spatial clustering
# ============================================================

def rect_distance(a, b):
    """Minimum Euclidean distance between two rectangles."""
    # Use sourcePoint coordinates for edges if x is not set
    ax = a.source_point_x if (a.x is None and a.has_source_point) else a.x
    ay = a.source_point_y if (a.y is None and a.has_source_point) else a.y
    bx = b.source_point_x if (b.x is None and b.has_source_point) else b.x
    by = b.source_point_y if (b.y is None and b.has_source_point) else b.y

    if ax is None or bx is None or ay is None or by is None:
        return float('inf')

    a_right = ax + a.w
    b_right = bx + b.w
    hd = 0
    if bx > a_right:
        hd = bx - a_right
    elif ax > b_right:
        hd = ax - b_right

    a_bottom = ay + a.h
    b_bottom = by + b.h
    vd = 0
    if by > a_bottom:
        vd = by - a_bottom
    elif ay > b_bottom:
        vd = ay - b_bottom

    return math.sqrt(hd * hd + vd * vd)


def cluster_vertices(vertices, epsilon=150):
    """DBSCAN-like clustering of vertices by spatial proximity."""
    remaining = list(vertices)
    clusters = []

    while remaining:
        seed = remaining.pop(0)
        cluster = [seed]
        queue = [seed]
        while queue:
            cur = queue.pop(0)
            still = []
            for v in remaining:
                if rect_distance(cur, v) <= epsilon:
                    cluster.append(v)
                    queue.append(v)
                else:
                    still.append(v)
            remaining = still
        clusters.append(cluster)

    return clusters


# ============================================================
# 3. Refine clusters using edge connectivity & parent relationships
# ============================================================

def refine_clusters(clusters, cells_by_id, all_vertices, all_edges, epsilon_merge=300):
    """
    Merge clusters that are connected by edges or shared parent containers,
    or are close enough to be considered part of the same sub-diagram.
    """
    # Build cluster_id -> set of cell ids
    cluster_cell_ids = []
    for cl in clusters:
        cluster_cell_ids.append(set(c.id for c in cl))

    changed = True
    while changed:
        changed = False
        n = len(cluster_cell_ids)
        merged = [False] * n

        for i in range(n):
            if merged[i]:
                continue
            for j in range(i + 1, n):
                if merged[j]:
                    continue

                should_merge = False

                # NOTE: Do NOT merge by edge connectivity — edges can cross
                # sub-diagram boundaries. Only merge by spatial proximity,
                # parent relationships, or shared parent containers.

                if not should_merge:
                    # Check parent relationships
                    # If any cell in cluster i has a parent in cluster j (or vice versa)
                    for cid in cluster_cell_ids[i]:
                        cell = cells_by_id.get(cid)
                        if cell and cell.parent in cluster_cell_ids[j]:
                            should_merge = True
                            break

                if not should_merge:
                    # Check if bounding boxes are very close (epsilon_merge threshold)
                    # Compute bounding boxes
                    def cluster_bbox(cid_set):
                        pts = [cells_by_id[cid] for cid in cid_set if cells_by_id[cid].x is not None and cells_by_id[cid].y is not None]
                        if not pts:
                            return None
                        min_x = min(c.x for c in pts)
                        max_x = max(c.x + c.w for c in pts)
                        min_y = min(c.y for c in pts)
                        max_y = max(c.y + c.h for c in pts)
                        return (min_x, min_y, max_x, max_y)

                    bbox_i = cluster_bbox(cluster_cell_ids[i])
                    bbox_j = cluster_bbox(cluster_cell_ids[j])
                    if bbox_i and bbox_j:
                        # Distance between bounding boxes
                        hd = 0
                        if bbox_j[0] > bbox_i[2]:
                            hd = bbox_j[0] - bbox_i[2]
                        elif bbox_i[0] > bbox_j[2]:
                            hd = bbox_i[0] - bbox_j[2]

                        vd = 0
                        if bbox_j[1] > bbox_i[3]:
                            vd = bbox_j[1] - bbox_i[3]
                        elif bbox_i[1] > bbox_j[3]:
                            vd = bbox_i[1] - bbox_j[3]

                        bbox_dist = math.sqrt(hd * hd + vd * vd)
                        if bbox_dist <= epsilon_merge:
                            should_merge = True

                if should_merge:
                    cluster_cell_ids[i] |= cluster_cell_ids[j]
                    cluster_cell_ids[j] = set()
                    merged[j] = True
                    changed = True

    # Remove empty clusters
    cluster_cell_ids = [c for c in cluster_cell_ids if c]

    # Rebuild cluster objects
    rebuilt = []
    for cid_set in cluster_cell_ids:
        rebuilt.append([cells_by_id[cid] for cid in cid_set if cells_by_id[cid].x is not None])

    return rebuilt


# ============================================================
# 4. Assign edges to clusters
# ============================================================

def assign_edges_to_clusters(clusters, all_edges):
    """Assign each edge to the cluster(s) containing its source and target vertices."""
    # Build vertex id -> cluster index
    vertex_to_cluster = {}
    for i, cl in enumerate(clusters):
        for v in cl:
            vertex_to_cluster[v.id] = i

    cluster_edges = [[] for _ in clusters]
    unassigned_edges = []

    for edge in all_edges:
        if edge.source and edge.target:
            src_idx = vertex_to_cluster.get(edge.source)
            tgt_idx = vertex_to_cluster.get(edge.target)
            if src_idx is not None and tgt_idx is not None and src_idx == tgt_idx:
                cluster_edges[src_idx].append(edge)
            elif src_idx is not None and tgt_idx is not None:
                # Cross-cluster edge - put it in both or the first one
                cluster_edges[src_idx].append(edge)
                print(f"  Warning: cross-cluster edge {edge.id}: src={edge.source}(cluster{src_idx}) tgt={edge.target}(cluster{tgt_idx})")
            elif src_idx is not None:
                cluster_edges[src_idx].append(edge)
                print(f"  Warning: edge {edge.id}: only source {edge.source} found in cluster {src_idx}")
            elif tgt_idx is not None:
                cluster_edges[tgt_idx].append(edge)
            else:
                unassigned_edges.append(edge)
        else:
            # Edge without source/target - might be a standalone line
            # Try to assign by spatial proximity using sourcePoint/targetPoint
            edge_x = edge.source_point_x if edge.has_source_point else edge.x
            edge_y = edge.source_point_y if edge.has_source_point else edge.y
            if edge_x is not None:
                best_dist = float('inf')
                best_idx = 0
                for i, cl in enumerate(clusters):
                    for v in cl:
                        d = rect_distance(edge, v)
                        if d < best_dist:
                            best_dist = d
                            best_idx = i
                if best_dist < 500:
                    cluster_edges[best_idx].append(edge)
                else:
                    unassigned_edges.append(edge)
            else:
                unassigned_edges.append(edge)

    return cluster_edges, unassigned_edges


# ============================================================
# 5. Generate output files
# ============================================================

def generate_sub_diagram(cluster, edges, header, idx, original_content, all_cells_by_id, output_dir, padding=50):
    """Generate a .drawio file for one sub-diagram cluster."""
    # Collect all cell IDs in this cluster
    cluster_ids = set(c.id for c in cluster)
    for e in edges:
        cluster_ids.add(e.id)

    # Also include parent cells that are referenced but might not be vertices
    extra_ids = set()
    for c in cluster:
        if c.parent not in ('0', '1'):
            extra_ids.add(c.parent)
    for e in edges:
        if e.parent not in ('0', '1'):
            extra_ids.add(e.parent)

    # Include CHILD cells: any cell whose parent is in this cluster
    # These are children of group containers
    for c in all_cells_by_id.values():
        if c.parent in cluster_ids and c.id not in cluster_ids:
            extra_ids.add(c.id)
            # Also include their children recursively
            for c2 in all_cells_by_id.values():
                if c2.parent == c.id:
                    extra_ids.add(c2.id)

    # Add edges' source/target vertices if they're not already in the cluster
    for e in edges:
        if e.source and e.source not in cluster_ids:
            parent_cell = all_cells_by_id.get(e.source)
            if parent_cell and parent_cell.x is not None:
                # This source is a vertex with position - include it
                extra_ids.add(e.source)
                print(f"  Adding external source vertex {e.source} to cluster {idx}")
        if e.target and e.target not in cluster_ids:
            parent_cell = all_cells_by_id.get(e.target)
            if parent_cell and parent_cell.x is not None:
                extra_ids.add(e.target)
                print(f"  Adding external target vertex {e.target} to cluster {idx}")

    cluster_ids |= extra_ids

    # Recurse: also include children of any newly added cell
    more_added = True
    while more_added:
        more_added = False
        new_children = set()
        for c in all_cells_by_id.values():
            if c.parent in cluster_ids and c.id not in cluster_ids:
                new_children.add(c.id)
                more_added = True
        if new_children:
            cluster_ids |= new_children
            extra_ids |= new_children

    # Also include the parent cells that define group boundaries
    # These group cells have position and size
    parent_group_cells = [all_cells_by_id[cid] for cid in extra_ids if cid in all_cells_by_id and all_cells_by_id[cid].x is not None]
    for pg in parent_group_cells:
        if pg.x is not None and pg not in cluster:
            cluster.append(pg)

    # Compute bounding box for coordinate shifting
    all_with_pos = [c for c in cluster if c.x is not None and c.y is not None]
    if not all_with_pos:
        return None

    min_x = min(c.x for c in all_with_pos)
    min_y = min(c.y for c in all_with_pos)
    max_x = max(c.x + c.w for c in all_with_pos)
    max_y = max(c.y + c.h for c in all_with_pos)

    # Also include edges with sourcePoint for bounding box calculation
    for e in edges:
        if e.has_source_point:
            min_x = min(min_x, e.source_point_x)
            min_y = min(min_y, e.source_point_y)
            max_x = max(max_x, e.source_point_x)
            max_y = max(max_y, e.source_point_y)
        if e.has_target_point:
            min_x = min(min_x, e.target_point_x)
            min_y = min(min_y, e.target_point_y)
            max_x = max(max_x, e.target_point_x)
            max_y = max(max_y, e.target_point_y)
        for wp in e.waypoints:
            min_x = min(min_x, wp[0])
            min_y = min(min_y, wp[1])
            max_x = max(max_x, wp[0])
            max_y = max(max_y, wp[1])

    # Add padding
    page_width = max_x - min_x + 2 * padding
    page_height = max_y - min_y + 2 * padding

    # Build the output XML
    lines = []
    lines.append(f'<mxfile host="Electron" agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) draw.io/29.0.3 Chrome/140.0.7339.249 Electron/38.7.0 Safari/537.36" version="29.0.3">')
    lines.append(f'  <diagram name="子图 {idx + 1}" id="subgraph_{idx}">')
    lines.append(f'    <mxGraphModel dx="0" dy="0" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="{page_width}" pageHeight="{page_height}" background="none" math="0" shadow="0">')
    lines.append(f'      <root>')
    lines.append(f'        <mxCell id="0" />')
    lines.append(f'        <mxCell id="1" parent="0" />')

    # Collect all cells to output: cluster vertices, edges, and parent cells
    output_cells = list(cluster) + list(edges)

    # Deduplicate by id
    seen_ids = set()
    deduped = []
    for c in output_cells:
        if c.id not in seen_ids:
            seen_ids.add(c.id)
            deduped.append(c)

    # Add extra parent cells that are not yet included
    for cid in extra_ids:
        if cid not in seen_ids and cid in all_cells_by_id:
            c = all_cells_by_id[cid]
            if c not in deduped:
                deduped.append(c)
                seen_ids.add(cid)

    # Sort cells: id="0" and id="1" first, then rest (preserve original order gives stable output)
    # Actually just output in the order we have; 0 and 1 are already handled above

    # Output each cell with adjusted coordinates
    for cell in deduped:
        if cell.id == '0' or cell.id == '1':
            continue  # Already handled above

        xml_str = '\n'.join(cell.xml_lines)

        # Adjust coordinates for vertices
        if cell.x is not None and cell.y is not None and cell.is_vertex:
            new_x = cell.x - min_x + padding
            new_y = cell.y - min_y + padding
            xml_str = re.sub(r' x="([^"]+)"', f' x="{new_x}"', xml_str)
            xml_str = re.sub(r' y="([^"]+)"', f' y="{new_y}"', xml_str)

        # Adjust sourcePoint/targetPoint for edges
        if cell.has_source_point:
            new_spx = cell.source_point_x - min_x + padding
            new_spy = cell.source_point_y - min_y + padding
            old_sp = f'as="sourcePoint" />'
            new_sp = f'as="sourcePoint" />'
            xml_str = re.sub(
                r'<mxPoint x="[^"]+" y="[^"]+" as="sourcePoint"\s*/>',
                f'<mxPoint x="{new_spx}" y="{new_spy}" as="sourcePoint" />',
                xml_str
            )

        if cell.has_target_point:
            new_tpx = cell.target_point_x - min_x + padding
            new_tpy = cell.target_point_y - min_y + padding
            old_tp = f'as="targetPoint" />'
            new_tp = f'as="targetPoint" />'
            xml_str = re.sub(
                r'<mxPoint x="[^"]+" y="[^"]+" as="targetPoint"\s*/>',
                f'<mxPoint x="{new_tpx}" y="{new_tpy}" as="targetPoint" />',
                xml_str
            )
            xml_str = xml_str.replace(old_tp, new_tp)

        # Adjust waypoints
        for old_wp, new_wp in zip(cell.waypoints, [
            (wp[0] - min_x + padding, wp[1] - min_y + padding) for wp in cell.waypoints
        ]):
            xml_str = re.sub(
                r'<mxPoint x="' + str(old_wp[0]) + r'" y="' + str(old_wp[1]) + r'"\s*/>',
                f'<mxPoint x="{new_wp[0]}" y="{new_wp[1]}" />',
                xml_str
            )

        # Adjust parent references: if parent cell is also in the output, keep as-is
        # If parent is not in output and is not 0/1, change to "1"
        if cell.parent not in ('0', '1') and cell.parent not in seen_ids:
            xml_str = re.sub(r' parent="[^"]+"', ' parent="1"', xml_str)

        lines.append(f'        {xml_str.strip()}')

    lines.append(f'      </root>')
    lines.append(f'    </mxGraphModel>')
    lines.append(f'  </diagram>')
    lines.append(f'</mxfile>')

    return '\n'.join(lines)


# ============================================================
# Main
# ============================================================

def main():
    input_file = os.path.join(os.path.dirname(__file__), '数据传输全异步.drawio')
    output_dir = os.path.dirname(__file__)

    print(f'Parsing {input_file}...')
    cells, header, original_content = parse_drawio(input_file)
    print(f'  Total cells: {len(cells)}')

    # Separate vertices and edges
    vertices = [c for c in cells if c.is_vertex and c.x is not None and c.y is not None]
    all_edges = [c for c in cells if c.is_edge]
    standalone = [c for c in cells if not c.is_vertex and not c.is_edge and c.x is not None and c.y is not None]

    print(f'  Vertices: {len(vertices)}')
    print(f'  Edges: {len(all_edges)}')
    print(f'  Standalone shapes: {len(standalone)}')

    # Build id -> cell map
    cells_by_id = {}
    for c in cells:
        cells_by_id[c.id] = c

    # Spatial clustering with epsilon=200
    print('\nClustering by spatial proximity (epsilon=200)...')
    clusters = cluster_vertices(vertices, epsilon=200)
    print(f'  Initial clusters: {len(clusters)}')
    for i, cl in enumerate(clusters):
        min_x = min(c.x for c in cl)
        max_x = max(c.x + c.w for c in cl)
        min_y = min(c.y for c in cl)
        max_y = max(c.y + c.h for c in cl)
        print(f'  Cluster {i}: {len(cl):3d} cells  X=[{min_x:5.0f}, {max_x:5.0f}]  Y=[{min_y:5.0f}, {max_y:5.0f}]')

    # Skip refinement — the spatial clustering already gives clean sub-diagrams.
    # Parent-based refinement tends to over-merge because container groups can
    # span multiple sub-diagrams.
    print(f'\nUsing {len(clusters)} spatial clusters directly (no refinement).')
    for i, cl in enumerate(clusters):
        min_x = min(c.x for c in cl)
        max_x = max(c.x + c.w for c in cl)
        min_y = min(c.y for c in cl)
        max_y = max(c.y + c.h for c in cl)
        print(f'  Cluster {i}: {len(cl):3d} cells  X=[{min_x:5.0f}, {max_x:5.0f}]  Y=[{min_y:5.0f}, {max_y:5.0f}]')

    # Assign edges to clusters
    print('\nAssigning edges to clusters...')
    cluster_edges_list, unassigned = assign_edges_to_clusters(clusters, all_edges)
    print(f'  Unassigned edges: {len(unassigned)}')

    # Handle standalone shapes (non-vertex, non-edge cells with positions)
    # Try to assign each to nearest cluster
    for sa in standalone:
        best_dist = float('inf')
        best_idx = 0
        for i, cl in enumerate(clusters):
            for v in cl:
                d = rect_distance(sa, v)
                if d < best_dist:
                    best_dist = d
                    best_idx = i
        if best_dist < 500:
            clusters[best_idx].append(sa)
        else:
            # Create a new cluster for this standalone cell
            clusters.append([sa])
            cluster_edges_list.append([])

    # Merge very small clusters (<= 4 cells) into the nearest neighbor.
    # These are typically noise (empty background rectangles) or very isolated labels.
    print('\nMerging tiny clusters (<=4 cells) into nearest neighbor...')
    merged_count = 0
    for small_idx in list(range(len(clusters))):
        if small_idx >= len(clusters):
            break
        if len(clusters[small_idx]) > 4:
            continue

        cl_small = clusters[small_idx]
        # Skip if has meaningful text content
        if any(c.value and c.value.strip() for c in cl_small):
            continue

        # Find nearest neighbor (any cluster)
        small_center_x = sum(c.x for c in cl_small if c.x is not None) / max(len([c for c in cl_small if c.x is not None]), 1)
        small_center_y = sum(c.y for c in cl_small if c.y is not None) / max(len([c for c in cl_small if c.y is not None]), 1)

        best_dist = float('inf')
        best_large_idx = None
        for j, cl_large in enumerate(clusters):
            if j == small_idx:
                continue
            large_center_x = sum(c.x for c in cl_large if c.x is not None) / max(len([c for c in cl_large if c.x is not None]), 1)
            large_center_y = sum(c.y for c in cl_large if c.y is not None) / max(len([c for c in cl_large if c.y is not None]), 1)
            dist = math.sqrt((small_center_x - large_center_x)**2 + (small_center_y - large_center_y)**2)
            if dist < best_dist:
                best_dist = dist
                best_large_idx = j

        if best_large_idx is not None and best_dist < 1000:
            clusters[best_large_idx].extend(clusters[small_idx])
            cluster_edges_list[best_large_idx].extend(cluster_edges_list[small_idx])
            clusters.pop(small_idx)
            cluster_edges_list.pop(small_idx)
            merged_count += 1

    # Re-number remaining clusters
    print(f'  Total merges: {merged_count}')
    print(f'  Remaining clusters: {len(clusters)}')
    for i, cl in enumerate(clusters):
        min_x = min(c.x for c in cl)
        max_x = max(c.x + c.w for c in cl)
        min_y = min(c.y for c in cl)
        max_y = max(c.y + c.h for c in cl)
        print(f'  Cluster {i}: {len(cl):3d} cells  X=[{min_x:5.0f}, {max_x:5.0f}]  Y=[{min_y:5.0f}, {max_y:5.0f}]')

    # Generate output files
    print('\nGenerating sub-diagram files...')
    base_name = os.path.splitext(os.path.basename(input_file))[0]

    generated = 0

    for i, (cl, edges) in enumerate(zip(clusters, cluster_edges_list)):
        output = generate_sub_diagram(cl, edges, header, i, original_content, cells_by_id, output_dir)
        if output:
            output_filename = os.path.join(output_dir, f'{base_name}_子图{i+1}.drawio')
            with open(output_filename, 'w', encoding='utf-8') as f:
                f.write(output)
            print(f'  Created: {os.path.basename(output_filename)}')
            generated += 1

    print(f'\nDone! Generated {generated} sub-diagram files.')


if __name__ == '__main__':
    main()
