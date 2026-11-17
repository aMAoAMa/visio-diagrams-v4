"""3-D to editable native Visio 2-D. Standard library only.

Analytical line occlusion against opaque convex planar faces. Filled faces use
painter ordering, not a general polygon intersection/BSP renderer.
"""
import argparse
import json
import math
from pathlib import Path

EPS = 1e-9
IDENTITY = [[1., 0., 0.], [0., 1., 0.], [0., 0., 1.]]
def vec(v, n=3):
    if not isinstance(v, (list, tuple)) or len(v) != n or any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in v):
        raise ValueError(f'Expected finite {n}-vector: {v!r}')
    return list(map(float, v))
def number(x, positive=False):
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) or (positive and x <= 0): raise ValueError(f'Invalid number: {x!r}')
    return float(x)
def add(a, b): return [x+y for x, y in zip(a, b)]
def sub(a, b): return [x-y for x, y in zip(a, b)]
def mul(a, t): return [x*t for x in a]
def dot(a, b): return sum(x*y for x, y in zip(a, b))
def cross(a, b): return [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
def norm(a): return math.sqrt(dot(a, a))
def unit(a):
    n = norm(a)
    if n < EPS: raise ValueError('Zero or collinear direction')
    return mul(a, 1/n)
def mv(m, v): return [dot(row, v) for row in m]
def mm(a, b): return [[sum(a[i][k]*b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]
def rotation(euler):
    r, p, y = map(math.radians, vec(euler))
    cr, sr, cp, sp, cy, sy = math.cos(r), math.sin(r), math.cos(p), math.sin(p), math.cos(y), math.sin(y)
    return [[cy*cp, cy*sp*sr-sy*cr, cy*sp*cr+sy*sr], [sy*cp, sy*sp*sr+cy*cr, sy*sp*cr-cy*sr], [-sp, cp*sr, cp*cr]]
def orientation(s):
    if sum(k in s for k in ('euler_deg', 'matrix', 'quaternion_xyzw')) > 1: raise ValueError('Choose one rotation representation')
    if 'matrix' in s:
        r = [vec(row) for row in s['matrix']]
        if len(r) != 3: raise ValueError('Rotation matrix must be 3 by 3')
    elif 'quaternion_xyzw' in s:
        q = vec(s['quaternion_xyzw'], 4)
        if abs(norm(q)-1) > 1e-6: raise ValueError('Quaternion must have unit norm')
        x, y, z, w = q
        r = [[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]]
    else: r = rotation(s.get('euler_deg', [0, 0, 0]))
    if any(abs(dot(r[i], r[j])-(i == j)) > 1e-6 for i in range(3) for j in range(3)) or abs(dot(cross(r[0], r[1]), r[2])-1) > 1e-6:
        raise ValueError('Rotation must be orthonormal and right-handed (det=+1)')
    return r
def resolve_poses(specs):
    if 'world' in specs: raise ValueError('world is reserved')
    poses = {'world': ([0., 0., 0.], IDENTITY)}; active = set()
    def resolve(name):
        if name in poses: return poses[name]
        if name in active: raise ValueError('Cyclic pose parent: '+name)
        if name not in specs: raise ValueError('Unknown pose: '+name)
        active.add(name); s = specs[name]; o, r = resolve(s.get('parent', 'world'))
        poses[name] = (add(o, mv(r, vec(s.get('origin', [0, 0, 0])))), mm(r, orientation(s)))
        active.remove(name); return poses[name]
    for name in specs: resolve(name)
    return poses

class Camera:
    def __init__(self, c):
        self.eye = vec(c['eye']); self.target = vec(c.get('target', [0, 0, 0]))
        self.forward = unit(sub(self.target, self.eye)); self.right = unit(cross(self.forward, vec(c.get('up', [0, 0, 1])))); self.up = unit(cross(self.right, self.forward))
        self.scale = number(c.get('scale', 1), True); self.origin = vec(c.get('origin', [0, 0]), 2)
        self.mode = c.get('projection', 'orthographic'); self.near = number(c.get('near', .01), True)
        self.focal = number(c.get('focal_length', norm(sub(self.eye, self.target))), True)
        if self.mode not in ('orthographic', 'perspective'): raise ValueError('Unknown projection')
    def depth(self, p): return dot(sub(p, self.eye), self.forward)
    def project(self, p):
        z = self.depth(p)
        if self.mode == 'perspective':
            if z < self.near-EPS: raise ValueError('Point behind near plane')
            v = sub(p, self.eye); scale = self.scale*self.focal/z
        else: v = sub(p, self.target); scale = self.scale
        return add(self.origin, [scale*dot(v, self.right), scale*dot(v, self.up)])
    def metric(self, p): return 1/self.depth(p) if self.mode == 'perspective' else -self.depth(p)
    def clip_line(self, a, b):
        if self.mode != 'perspective': return a, b, True, True
        za, zb = self.depth(a), self.depth(b)
        if max(za, zb) < self.near: return None
        aa, bb = a, b
        if za < self.near: aa = add(a, mul(sub(b, a), (self.near-za)/(zb-za)))
        if zb < self.near: bb = add(a, mul(sub(b, a), (self.near-za)/(zb-za)))
        return aa, bb, za >= self.near, zb >= self.near
    def clip_face(self, ps):
        if self.mode != 'perspective': return ps
        out = []
        for a, b in zip(ps, ps[1:]+ps[:1]):
            za, zb = self.depth(a), self.depth(b)
            if za >= self.near: out.append(a)
            if (za >= self.near) != (zb >= self.near): out.append(add(a, mul(sub(b, a), (self.near-za)/(zb-za))))
        return out

def barycentric(p, tri):
    a, b, c = tri; v, w, q = sub(b, a), sub(c, a), sub(p, a); d = v[0]*w[1]-w[0]*v[1]
    if abs(d) < EPS: return None
    y = (q[0]*w[1]-w[0]*q[1])/d; z = (v[0]*q[1]-q[0]*v[1])/d
    return [1-y-z, y, z]
def hidden_intervals(a, b, qa, qb, triangles):
    """Interval union; affine inverse-depth is used for perspective correctness."""
    intervals = []
    for tri, qs in triangles:
        ba, bb = barycentric(a, tri), barycentric(b, tri)
        if ba is None: continue
        lo, hi = 0., 1.
        for u, v in zip(ba, bb):
            d = v-u
            if abs(d) < EPS:
                if u < -EPS: hi = -1; break
            elif d > 0: lo = max(lo, -u/d)
            else: hi = min(hi, -u/d)
        if hi-lo <= EPS: continue
        da, db = dot(ba, qs)-qa, dot(bb, qs)-qb
        tolerance = 1e-7*max(1, abs(qa), abs(qb), *map(abs, qs)); d = db-da
        if abs(d) < EPS:
            if da <= tolerance: continue
        elif d > 0: lo = max(lo, (tolerance-da)/d)
        else: hi = min(hi, (tolerance-da)/d)
        if hi-lo > EPS: intervals.append((max(0., lo), min(1., hi)))
    merged = []
    for lo, hi in sorted(intervals):
        if merged and lo <= merged[-1][1]+EPS: merged[-1] = (merged[-1][0], max(hi, merged[-1][1]))
        else: merged.append((lo, hi))
    return merged

def mesh_geometry(a):
    if a['kind'] == 'mesh': return [vec(v) for v in a['vertices']], a['faces']
    if a['kind'] == 'box':
        center, size = vec(a.get('center', [0, 0, 0])), vec(a['size3d'])
        if min(size) <= 0: raise ValueError('Box dimensions must be positive')
        vs = [add(center, [x*size[0]/2, y*size[1]/2, z*size[2]/2]) for z in (-1, 1) for y in (-1, 1) for x in (-1, 1)]
        return vs, [[0, 2, 3, 1], [4, 5, 7, 6], [0, 1, 5, 4], [2, 6, 7, 3], [0, 4, 6, 2], [1, 3, 7, 5]]
    center = vec(a.get('center', [0, 0, 0])); axis = unit(vec(a.get('axis', [0, 0, 1])))
    radius, length = number(a['radius'], True), number(a['length'], True); count = a.get('segments', 24)
    if isinstance(count, bool) or not isinstance(count, int) or not 6 <= count <= 256: raise ValueError('Cylinder segments must be integer 6..256')
    helper = min(IDENTITY, key=lambda e: abs(dot(e, axis))); u = unit(cross(helper, axis)); v = cross(axis, u)
    vs = [add(add(center, mul(axis, h*length/2)), mul(add(mul(u, math.cos(2*math.pi*k/count)), mul(v, math.sin(2*math.pi*k/count))), radius)) for h in (-1, 1) for k in range(count)]
    return vs, [list(reversed(range(count))), list(range(count, 2*count))]+[[k, (k+1)%count, (k+1)%count+count, k+count] for k in range(count)]
def face_normal(ps):
    if len(ps) < 3: raise ValueError('Face needs three vertices')
    local = [sub(p, ps[0]) for p in ps]
    n = unit([sum(cross(a, b)[k] for a, b in zip(local, local[1:]+local[:1])) for k in range(3)])
    extent = max(1., *(norm(sub(p, ps[0])) for p in ps))
    if any(abs(dot(sub(p, ps[0]), n)) > 1e-7*extent for p in ps): raise ValueError('Nonplanar face; triangulate explicitly')
    if any(dot(cross(sub(b, a), sub(c, b)), n) < -1e-8*extent*extent for a, b, c in zip(ps, ps[1:]+ps[:1], ps[2:]+ps[:2])): raise ValueError('Nonconvex face; triangulate explicitly')
    return n
def shade(color, f):
    if not isinstance(color, str) or len(color) != 7 or color[0] != '#': raise ValueError('Expected #RRGGBB')
    return '#'+''.join(f'{min(255, max(0, round(int(color[i:i+2], 16)*f))):02X}' for i in (1, 3, 5))
def frame_diagnostic(cam, origin, r, lengths):
    p = cam.project(origin); axes = [sub(cam.project(add(origin, mv(r, mul(IDENTITY[k], lengths[k])))), p) for k in range(3)]
    lens = list(map(norm, axes)); angles = []
    for i, j in ((0, 1), (1, 2), (2, 0)):
        angle = math.degrees(math.acos(max(-1, min(1, dot(axes[i], axes[j])/max(EPS, lens[i]*lens[j]))))); angles.append(min(angle, 180-angle))
    return {'projected_lengths': lens, 'length_ratio': min(lens)/max(EPS, max(lens)), 'min_axis_separation_deg': min(angles)}

def compile_scene(s):
    number(s['width'], True); number(s['height'], True); layers = {}; semantics = set()
    for layer in s['layers']:
        key = (layer['owner'], layer['concept'])
        if layer['name'] in layers or key in semantics: raise ValueError('Duplicate layer or owner/concept')
        layers[layer['name']] = layer; semantics.add(key)
    cams = {'main': Camera(s['camera'])}
    if 'main' in s.get('views', {}): raise ValueError('main view is reserved')
    cams.update({k: Camera(v) for k, v in s.get('views', {}).items()}); poses = resolve_poses(s.get('poses', {})); primitives = s['primitives']; ids = set()
    for a in primitives:
        if not a.get('id') or a['id'] in ids: raise ValueError('Missing/duplicate primitive id')
        ids.add(a['id'])
        if a['layer'] not in layers: raise ValueError('Unknown layer: '+a['layer'])
        if a.get('view', 'main') not in cams: raise ValueError('Unknown view')
        if a.get('pose', 'world') not in poses: raise ValueError('Unknown pose')
    entries, diagnostics, projected_faces = [], [], []; occluders = {key: [] for key in cams}; geometries = {}
    def put(item, order=200, depth=0): entries.append((order, -depth, len(entries), item))
    def context(a):
        o, r = poses[a.get('pose', 'world')]; return cams[a.get('view', 'main')], o, r
    def style(a): return {k: a[k] for k in ('layer', 'line', 'fill', 'weight', 'dash', 'alpha', 'color', 'size', 'font', 'fontEastAsia') if k in a}
    for a in primitives:
        if a['kind'] not in ('mesh', 'box', 'cylinder'): continue
        cam, o, r = context(a); vs, faces = mesh_geometry(a); vs = [add(o, mv(r, p)) for p in vs]; geometry = []
        for j, face in enumerate(faces):
            if any(isinstance(k, bool) or not isinstance(k, int) or k < 0 or k >= len(vs) for k in face): raise ValueError('Face index out of range')
            if len(set(face)) != len(face): raise ValueError('Repeated face vertex')
            ps = [vs[k] for k in face]; n = face_normal(ps); clipped = cam.clip_face(ps); geometry.append((face, n))
            if len(clipped) < 3: continue
            xy = [cam.project(p) for p in clipped]; qs = [cam.metric(p) for p in clipped]
            if 'fill' in a and a.get('alpha', 0) == 0 and a.get('occluder', True):
                occluders[a.get('view', 'main')] += [([xy[0], xy[k], xy[k+1]], [qs[0], qs[k], qs[k+1]]) for k in range(1, len(xy)-1)]
            center = mul([sum(p[k] for p in ps) for k in range(3)], 1/len(ps)); facing = sub(cam.eye, center) if cam.mode == 'perspective' else mul(cam.forward, -1)
            if a.get('cull', True) and dot(n, facing) <= EPS: continue
            if 'fill' not in a: continue
            light = unit(vec(a.get('light', [-.3, -.5, 1])))
            put(dict(style(a), id=f"{a['id']}-face-{j}", kind='poly', points=xy, closed=True, noLine=True, fill=shade(a['fill'], .76+.24*max(0, dot(n, light)))), a.get('order', 100), cam.depth(center))
            projected_faces.append((a['id'], a.get('view', 'main'), min(cam.depth(p) for p in ps), max(cam.depth(p) for p in ps), xy))
        geometries[a['id']] = vs, geometry
    def line(a, ident, pts, end_arrow=False, start_arrow=False, order=200, extra=None):
        cam, _, _ = context(a); mode = a.get('visibility', 'occlude'); hidden = a.get('hidden', 'omit'); pieces = []
        if mode not in ('occlude', 'overlay') or hidden not in ('omit', 'dash'): raise ValueError('Invalid visibility/hidden policy')
        for segment, (pa, pb) in enumerate(zip(pts, pts[1:])):
            clipped = cam.clip_line(pa, pb)
            if clipped is None: continue
            aa, bb, original_a, original_b = clipped; xa, xb = cam.project(aa), cam.project(bb)
            if norm(sub(xb, xa)) < 1e-7: continue
            intervals = hidden_intervals(xa, xb, cam.metric(aa), cam.metric(bb), occluders[a.get('view', 'main')]) if mode == 'occlude' else []
            bounds = sorted(set([0., 1.]+[v for pair in intervals for v in pair]))
            for lo, hi in zip(bounds, bounds[1:]):
                if hi-lo < EPS: continue
                mid = (lo+hi)/2; invisible = any(l-EPS < mid < h+EPS for l, h in intervals)
                if invisible and hidden == 'omit': continue
                p, q = add(xa, mul(sub(xb, xa), lo)), add(xa, mul(sub(xb, xa), hi))
                if norm(sub(q, p)) < 1e-6: continue
                end = end_arrow and segment == len(pts)-2 and hi >= 1-EPS and original_b and not invisible
                start = start_arrow and segment == 0 and lo <= EPS and original_a and not invisible
                if pieces and pieces[-1][1] == invisible and norm(sub(pieces[-1][0][-1], p)) < 1e-7:
                    pieces[-1][0].append(q); pieces[-1][2] = end
                else: pieces.append([[p, q], invisible, end, start])
        for k, (points, invisible, end, start) in enumerate(pieces):
            item = dict(style(a), id=ident if len(pieces) == 1 else f'{ident}-part-{k}', kind='poly', points=points, endArrow=end, startArrow=start); item.pop('fill', None)
            if extra: item.update(extra)
            if invisible: item.update(dash=True, line=a.get('hidden_line', '#9AA6AE'), weight=a.get('hidden_weight', .65), endArrow=False, startArrow=False)
            put(item, order)
    def label(a, ident, p, text, offset=None, color=None, notation=False):
        cam, _, _ = context(a)
        if cam.mode == 'perspective' and cam.depth(p) < cam.near: diagnostics.append({'id': ident, 'issue': 'label-behind-near-plane'}); return
        xy = cam.project(p); offset = vec(offset if offset is not None else a.get('offset', [.05, .05]), 2); w, h = number(a.get('w', 1.3), True), number(a.get('h', .38), True); x, y = add(xy, offset)
        item = dict(style(a), id=ident, kind='text', x=x, y=y, w=w, h=h, text=text, size=number(a.get('size', 20), True), color=color or a.get('color', '#243646'), notation=notation)
        item.pop('fill', None)
        if 'italic' in a: item['italic'] = a['italic']
        put(item, a.get('order', 300))
        if a.get('leader'):
            end = [min(max(xy[0], x), x+w), min(max(xy[1], y), y+h)]; put(dict(id=ident+'-leader', kind='poly', layer=a.get('leader_layer', a['layer']), points=[xy, end], line=a.get('leader_color', '#758895'), weight=.8), 295)
    for a in primitives:
        cam, o, r = context(a); ident = a['id']; kind = a['kind']
        def point(p): return add(o, mv(r, vec(p)))
        if kind in ('mesh', 'box', 'cylinder'):
            vs, faces = geometries[ident]; edges = {}
            for face, n in faces:
                for i, j in zip(face, face[1:]+face[:1]): edges.setdefault(tuple(sorted((i, j))), []).append(n)
            for (i, j), ns in edges.items():
                mode = a.get('edge_mode', 'feature')
                if mode == 'none': continue
                if mode not in ('feature', 'all'): raise ValueError('Unknown edge_mode')
                if mode == 'feature' and len(ns) == 2 and dot(ns[0], ns[1]) > math.cos(math.radians(number(a.get('crease_deg', 25)))):
                    mid = mul(add(vs[i], vs[j]), .5); view = sub(cam.eye, mid) if cam.mode == 'perspective' else mul(cam.forward, -1)
                    if dot(ns[0], view)*dot(ns[1], view) >= 0: continue
                edge = dict(a); edge.setdefault('hidden', 'dash'); line(edge, f'{ident}-edge-{i}-{j}', [vs[i], vs[j]], order=a.get('edge_order', a.get('order', 100)+10))
        elif kind in ('polyline', 'arrow', 'vector'):
            if kind == 'vector':
                anchor = point(a['anchor']); vector_pose = a.get('vector_pose', a.get('pose', 'world'))
                if vector_pose not in poses: raise ValueError('Unknown vector_pose')
                direction = mv(poses[vector_pose][1], vec(a['components']))
                if norm(direction) < EPS: raise ValueError('Zero vector has no arrow direction')
                ps = [anchor, add(anchor, mul(direction, number(a.get('length_scale', 1), True)))]
            else: ps = [point(p) for p in a['points']]
            if len(ps) < 2: raise ValueError('Line needs two points')
            if a.get('closed') and ps[0] != ps[-1]: ps.append(ps[0])
            line(a, ident, ps, kind in ('arrow', 'vector') or a.get('endArrow', False), a.get('startArrow', False), a.get('order', 200))
        elif kind == 'frame':
            origin = point(a.get('origin', [0, 0, 0])); lengths = vec(a.get('lengths', [1, 1, 1]))
            if min(lengths) <= 0: raise ValueError('Frame lengths must be positive')
            colors, names = a.get('colors', ['#BC543F', '#287F75', '#376DB5']), a.get('labels', ['x', 'y', 'z'])
            if len(colors) != 3 or len(names) != 3: raise ValueError('Frame needs three labels/colors')
            try:
                d = frame_diagnostic(cam, origin, r, lengths)
                if d['length_ratio'] < .3 or d['min_axis_separation_deg'] < 25: diagnostics.append(dict(id=ident, issue='foreshortened-or-overlapping-axes', **d))
            except ValueError: diagnostics.append({'id': ident, 'issue': 'frame-crosses-near-plane'})
            if a.get('visibility') == 'overlay': diagnostics.append({'id': ident, 'issue': 'overlay-frame', 'note': 'Mark displaced/x-ray reference explicitly when applicable'})
            for k in range(3):
                end = add(origin, mv(r, mul(IDENTITY[k], lengths[k])))
                line(a, f'{ident}-axis-{k}', [origin, end], True, order=210, extra={'line': colors[k], 'weight': a.get('weight', 2)})
                if 'label_offsets' in a: offset = a['label_offsets'][k]
                elif cam.mode != 'perspective' or min(cam.depth(origin), cam.depth(end)) >= cam.near:
                    dv = sub(cam.project(end), cam.project(origin)); dx, dy = mul(dv, .12/max(EPS, norm(dv))); offset = [dx+(-a.get('label_width', .85) if dx < -.02 else 0), dy+(-.38 if dy < -.02 else 0)]
                else: offset = [.05, .05]
                label(dict(a, w=a.get('label_width', .85), h=.38), f'{ident}-label-{k}', end, names[k], offset, colors[k], True)
            if cam.mode != 'perspective' or cam.depth(origin) >= cam.near:
                xy = cam.project(origin); hidden = a.get('visibility', 'occlude') != 'overlay' and bool(hidden_intervals(xy, add(xy, [1e-6, 0]), cam.metric(origin), cam.metric(origin), occluders[a.get('view', 'main')]))
                if not hidden: put(dict(id=ident+'-origin', kind='ellipse', layer=a['layer'], x=xy[0]-.035, y=xy[1]-.035, w=.07, h=.07, line='#243646', fill='#243646'), 220)
                else: diagnostics.append({'id': ident, 'issue': 'occluded-frame-origin'})
        elif kind == 'label': label(a, ident, point(a['anchor']), a['text'], notation=a.get('notation', False))
        elif kind == 'arc':
            center = point(a['center']); n = unit(mv(r, vec(a['normal']))); u = mv(r, vec(a['start_direction'])); u = unit(sub(u, mul(n, dot(n, u)))); v = cross(n, u)
            sweep = number(a['sweep_deg']); radius = number(a['radius'], True)
            if abs(sweep) > 360 or abs(sweep) < EPS: raise ValueError('Arc sweep must be nonzero and at most 360 degrees')
            count = max(8, math.ceil(abs(sweep)/max(.25, number(a.get('step_deg', 4), True))))
            ps = [add(center, mul(add(mul(u, math.cos(math.radians(sweep)*k/count)), mul(v, math.sin(math.radians(sweep)*k/count))), radius)) for k in range(count+1)]
            line(a, ident, ps, a.get('endArrow', True), a.get('startArrow', False), a.get('order', 220))
        else: raise ValueError('Unsupported primitive: '+kind)
    ambiguous = set()
    for j, (aid, view, zmin, zmax, xy) in enumerate(projected_faces):
        for bid, bv, bmin, bmax, bxy in projected_faces[j+1:]:
            if aid == bid or view != bv or min(zmax, bmax)-max(zmin, bmin) <= EPS: continue
            if all(min(max(p[k] for p in xy), max(p[k] for p in bxy))-max(min(p[k] for p in xy), min(p[k] for p in bxy)) > EPS for k in (0, 1)): ambiguous.add(tuple(sorted((aid, bid))))
    for pair in sorted(ambiguous): diagnostics.append({'ids': pair, 'issue': 'face-order-review', 'note': 'Overlapping projected bounds/depth ranges; split intersecting faces or inspect rendering'})
    out = {k: s[k] for k in ('name', 'width', 'height', 'layers')}; out.update(font=s.get('font', 'Arial'), fontEastAsia=s.get('fontEastAsia', 'Microsoft YaHei'), shapes=[a for _, _, _, a in sorted(entries)]+s.get('overlays', []), projectionDiagnostics=diagnostics)
    output_ids = set()
    for item in out['shapes']:
        if item['id'] in output_ids: raise ValueError('Generated/overlay id collision: '+item['id'])
        output_ids.add(item['id'])
        if item['layer'] not in layers: raise ValueError('Unknown output/leader layer')
    return out

def compile_payload(data): return {'scenes': [compile_scene(s) for s in data['scenes']]}
def suggest_cameras(s):
    poses = resolve_poses(s.get('poses', {})); baseline = s['camera']; target = vec(baseline.get('target', [0, 0, 0])); distance = norm(sub(vec(baseline['eye']), target))
    frames = [a for a in s['primitives'] if a['kind'] == 'frame' and a.get('view', 'main') == 'main']
    if not frames: raise ValueError('No main-view frames to score')
    up = unit(vec(baseline.get('up', [0, 0, 1]))); helper = min(IDENTITY, key=lambda e: abs(dot(e, up))); u = unit(cross(helper, up)); v = cross(up, u); ranked = []
    for elevation in (20, 30, 40, 50):
        for azimuth in range(0, 360, 15):
            az, el = math.radians(azimuth), math.radians(elevation); direction = add(mul(add(mul(u, math.cos(az)), mul(v, math.sin(az))), math.cos(el)), mul(up, math.sin(el)))
            candidate = dict(baseline, eye=add(target, mul(direction, distance))); cam = Camera(candidate)
            try: ds = [frame_diagnostic(cam, add(poses[a.get('pose', 'world')][0], mv(poses[a.get('pose', 'world')][1], vec(a.get('origin', [0, 0, 0])))), poses[a.get('pose', 'world')][1], vec(a.get('lengths', [1, 1, 1]))) for a in frames]
            except ValueError: continue
            score = min(min(d['length_ratio']/.3, 1)*min(d['min_axis_separation_deg']/40, 1) for d in ds)
            ranked.append({'score': round(score, 4), 'camera': candidate, 'frames': ds})
    return sorted(ranked, key=lambda a: a['score'], reverse=True)[:5]
def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--input', required=True); p.add_argument('--output', required=True); p.add_argument('--suggest-camera', action='store_true'); args = p.parse_args()
    data = json.loads(Path(args.input).read_text(encoding='utf-8-sig'))
    out = {'suggestions': [{'scene': s['name'], 'candidates': suggest_cameras(s)} for s in data['scenes']]} if args.suggest_camera else compile_payload(data)
    Path(args.output).write_text(json.dumps(out, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8'); print('Wrote '+args.output)
if __name__ == '__main__': main()
