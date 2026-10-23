# =====================================================================================
#  CAMP DEMISOUL - THE GOD HOUSE
#  "Two worlds became one here."
#
#  Blender 3.6 / 4.x. Open the Scripting workspace, paste or open this file, press Run.
#  Re-running replaces only its own "GodHouse" collection; nothing else in your scene is touched.
#
#  Units: metres (Blender default). Front of the building faces -Y (south).
#  Every object stays under ~18,000 triangles (Roblox's per-mesh limit is 20,000): big parts are
#  split automatically into _01, _02 ... pieces.
#
#  NO STATUES. Wherever a statue would stand there is an EMPTY ceremonial pedestal, and on top of each
#  one an Empty object called "NPC_Spot_<name>" (collection 13_NPC_Spots) marks where a Roblox NPC /
#  character statue goes. The same list is written to the Blender text block "GodHouse_NPC_Spots"
#  (in metres and in studs) and printed to the system console.
#
#  Layout (plan, metres):
#      north  - rear courtyard: reflecting pool and quiet memorial garden          (Hades)
#               rear block: Council Chamber / Quest Planning / Administration / roof garden
#      centre - the Garden Atrium: a great round drum open to the sky, the sacred tree at its heart,
#               a spiral stair round the trunk up to two galleries and the Observation Balcony,
#               and down into the Hidden Undercroft among the roots, with secret vaults in the hill
#      west   - the glass greenhouse wing: Library and Archives (nature)
#      east   - the Doric temple: Grand Assembly Hall (Olympus / Hephaestus craftsmanship)
#      south  - the Hall of Founders (Hades and Hephaestus), forged bronze doors, the podium,
#               the ceremonial forecourt, and the grand staircase down the hill
# =====================================================================================

import bpy
import math
import random
from math import sin, cos, pi, tau, sqrt, radians

rng = random.Random(1907)

ROOT_NAME = "GodHouse"
TRI_LIMIT = 18000          # per object (Roblox limit is 20,000)
STUD_SCALE = 3.0           # studs per metre used across Camp DemiSoul (for the NPC spot list)
ADD_LIGHTS = True          # Blender preview lights (braziers, atrium, undercroft, a low sunset sun)

# ---------------------------------------------------------------- key heights (metres)
H = 16.0                   # top of the hill plateau (forecourt level)
G = H + 1.2                # ground floor of the God House (top of the podium)
L1 = G + 6.5               # first gallery / upper floors
L2 = G + 13.0              # second gallery / roof terraces
OBS = G + 19.5             # Observation Balcony (top of the drum)
U = G - 6.2                # floor of the Hidden Undercroft
RC = (0.0, 4.0)            # centre of the Garden Atrium (and of the sacred tree)
R_IN, R_OUT = 12.0, 13.0   # the drum wall
SP_IN, SP_OUT = 3.4, 5.8   # spiral stair annulus round the trunk
TRUNK_R = 3.0
A0 = -90.0                 # the spiral starts on the south side (facing the Hall of Founders)
SP_STEP_DEG = 18.0
UP_RISE = 6.5 / 20         # 20 steps per turn, one turn per floor
DN_RISE = 6.2 / 19


# ================================================================ small vector helpers
def v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_mul(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def v_len(a): return sqrt(v_dot(a, a))


def v_norm(a):
    L = v_len(a)
    return (a[0] / L, a[1] / L, a[2] / L) if L > 1e-12 else (0.0, 0.0, 1.0)


def basis(w):
    """Right-handed (u, v, w) with w = given axis."""
    w = v_norm(w)
    ref = (0.0, 0.0, 1.0) if abs(w[2]) < 0.9 else (1.0, 0.0, 0.0)
    u = v_norm(v_cross(ref, w))
    v = v_cross(w, u)
    return u, v, w


def polar(c, r, deg, z=0.0):
    a = radians(deg)
    return (c[0] + r * cos(a), c[1] + r * sin(a), z)


def smoothstep(e0, e1, x):
    t = min(1.0, max(0.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


# ================================================================ transform stack + parts
_XF = [(0.0, 0.0, 0.0, 1.0, 0.0)]


class at:
    """Place what is built inside the block at local origin o, rotated by rz radians."""
    def __init__(self, o, rz=0.0):
        self.o, self.rz = o, rz

    def __enter__(self):
        ox, oy, oz, c, s = _XF[-1]
        x, y, z = self.o
        c2 = c * cos(self.rz) - s * sin(self.rz)
        s2 = s * cos(self.rz) + c * sin(self.rz)
        _XF.append((ox + c * x - s * y, oy + s * x + c * y, oz + z, c2, s2))
        return self

    def __exit__(self, *a):
        _XF.pop()


def W(p):
    ox, oy, oz, c, s = _XF[-1]
    return (ox + c * p[0] - s * p[1], oy + s * p[0] + c * p[1], oz + p[2])


PARTS = {}           # part name -> list of chunks
PART_GROUP = {}      # part name -> collection
_CUR = ["Misc"]
NPC_SPOTS = []
LIGHTS = []


class part:
    def __init__(self, name, group):
        self.name = name
        PART_GROUP.setdefault(name, group)

    def __enter__(self):
        _CUR.append(self.name)
        return self

    def __exit__(self, *a):
        _CUR.pop()


def emit(mat, verts, faces, smooth=False):
    if not faces:
        return
    vs = [W(v) for v in verts]
    nt = sum(len(f) - 2 for f in faces)
    chunks = PARTS.setdefault(_CUR[-1], [])
    if not chunks or chunks[-1]["tris"] + nt > TRI_LIMIT:
        chunks.append({"v": [], "f": [], "s": [], "m": [], "tris": 0})
    ch = chunks[-1]
    b = len(ch["v"])
    ch["v"].extend(vs)
    ch["f"].extend([tuple(i + b for i in f) for f in faces])
    sm = smooth if isinstance(smooth, list) else [smooth] * len(faces)
    ch["s"].extend(sm)
    ch["m"].extend([mat] * len(faces))
    ch["tris"] += nt


def newell(pts):
    n = [0.0, 0.0, 0.0]
    for i in range(len(pts)):
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    return tuple(n)


def orient(verts, faces, ref):
    """Flip any face whose normal points toward `ref` (an interior point)."""
    out = []
    for f in faces:
        P = [verts[i] for i in f]
        c = v_mul(tuple(map(sum, zip(*P))), 1.0 / len(P))
        out.append(tuple(f) if v_dot(newell(P), v_sub(c, ref)) >= 0 else tuple(reversed(f)))
    return out


# ================================================================ primitives
def box(mat, c, size, rz=0.0, ch=0.0):
    """Box centred at c (size = full extents), optional chamfer `ch` on every edge."""
    hx, hy, hz = size[0] / 2, size[1] / 2, size[2] / 2
    cr, sr = cos(rz), sin(rz)

    def P(x, y, z):
        return (c[0] + cr * x - sr * y, c[1] + sr * x + cr * y, c[2] + z)
    ch = min(ch, hx * 0.45, hy * 0.45, hz * 0.45)
    if ch <= 1e-4:
        V = [P(sx * hx, sy * hy, sz * hz) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
        F = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        emit(mat, V, F)
        return
    V, idx = [], {}
    for i in (-1, 1):
        for j in (-1, 1):
            for k in (-1, 1):
                for t, p in (("x", (i * hx, j * (hy - ch), k * (hz - ch))), ("y", (i * (hx - ch), j * hy, k * (hz - ch))),
                             ("z", (i * (hx - ch), j * (hy - ch), k * hz))):
                    idx[(i, j, k, t)] = len(V)
                    V.append(p)
    F = []
    for i in (-1, 1):
        F.append([idx[(i, j, k, "x")] for j, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for j in (-1, 1):
        F.append([idx[(i, j, k, "y")] for i, k in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for k in (-1, 1):
        F.append([idx[(i, j, k, "z")] for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    for j in (-1, 1):
        for k in (-1, 1):
            F.append([idx[(-1, j, k, "y")], idx[(1, j, k, "y")], idx[(1, j, k, "z")], idx[(-1, j, k, "z")]])
    for i in (-1, 1):
        for k in (-1, 1):
            F.append([idx[(i, -1, k, "x")], idx[(i, 1, k, "x")], idx[(i, 1, k, "z")], idx[(i, -1, k, "z")]])
    for i in (-1, 1):
        for j in (-1, 1):
            F.append([idx[(i, j, -1, "x")], idx[(i, j, 1, "x")], idx[(i, j, 1, "y")], idx[(i, j, -1, "y")]])
    for i in (-1, 1):
        for j in (-1, 1):
            for k in (-1, 1):
                F.append([idx[(i, j, k, "x")], idx[(i, j, k, "y")], idx[(i, j, k, "z")]])
    F = orient(V, F, (0.0, 0.0, 0.0))
    emit(mat, [P(*p) for p in V], F)


def box2(mat, x0, y0, z0, x1, y1, z1, ch=0.0):
    box(mat, ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (abs(x1 - x0), abs(y1 - y0), abs(z1 - z0)), ch=ch)


def frustum(mat, base, r0, r1, h, segs=12, axis=(0, 0, 1), caps=True, smooth=True, a0=0.0):
    """Cone/cylinder from `base` along `axis`, radius r0 at the base, r1 at the far end."""
    u, v, w = basis(axis)

    def P(r, ang, t):
        return v_add(base, v_add(v_add(v_mul(u, r * cos(ang)), v_mul(v, r * sin(ang))), v_mul(w, t)))
    n = segs
    V = []
    for i in range(n):
        a = a0 + tau * i / n
        V.append(P(r0, a, 0.0))
        V.append(P(r1, a, h))
    F = []
    for i in range(n):
        j = (i + 1) % n
        F.append((2 * i, 2 * j, 2 * j + 1, 2 * i + 1))
    S = [smooth] * len(F)
    if caps:
        b0 = len(V)
        for i in range(n):
            V.append(P(r0, a0 + tau * i / n, 0.0))
        if r0 > 1e-4:
            F.append(tuple(b0 + i for i in reversed(range(n))))
            S.append(False)
        b1 = len(V)
        for i in range(n):
            V.append(P(r1, a0 + tau * i / n, h))
        if r1 > 1e-4:
            F.append(tuple(b1 + i for i in range(n)))
            S.append(False)
    emit(mat, V, F, S)


def tube(mat, p0, p1, r0, r1, segs=8, caps=True, smooth=True):
    d = v_sub(p1, p0)
    L = v_len(d)
    if L < 1e-5:
        return
    frustum(mat, p0, r0, r1, L, segs, axis=d, caps=caps, smooth=smooth)


def path_tube(mat, pts, radii, segs=7, caps=True, smooth=True):
    """Tapered tube through points (roots, branches, vines). radii: one per point."""
    if len(pts) < 2:
        return
    tans = []
    for i in range(len(pts)):
        a = pts[max(i - 1, 0)]
        b = pts[min(i + 1, len(pts) - 1)]
        tans.append(v_norm(v_sub(b, a)))
    u, v, w = basis(tans[0])
    frames = [(u, v)]
    for i in range(1, len(pts)):
        t = tans[i]
        u = v_sub(u, v_mul(t, v_dot(u, t)))
        u = v_norm(u)
        v = v_cross(t, u)
        frames.append((u, v))
    V, F = [], []
    for i, p in enumerate(pts):
        u, v = frames[i]
        r = radii[i]
        for k in range(segs):
            a = tau * k / segs
            V.append(v_add(p, v_add(v_mul(u, r * cos(a)), v_mul(v, r * sin(a)))))
    for i in range(len(pts) - 1):
        for k in range(segs):
            k2 = (k + 1) % segs
            F.append((i * segs + k, i * segs + k2, (i + 1) * segs + k2, (i + 1) * segs + k))
    S = [smooth] * len(F)
    if caps:
        for end, rev in ((0, True), (len(pts) - 1, False)):
            if radii[end] > 1e-4:
                b = len(V)
                u, v = frames[end]
                for k in range(segs):
                    a = tau * k / segs
                    V.append(v_add(pts[end], v_add(v_mul(u, radii[end] * cos(a)), v_mul(v, radii[end] * sin(a)))))
                f = tuple(b + k for k in range(segs))
                F.append(tuple(reversed(f)) if rev else f)
                S.append(False)
    emit(mat, V, F, S)


def blob(mat, c, r, segs=8, rings=5, jitter=0.0, smooth=True):
    rx, ry, rz = r if isinstance(r, tuple) else (r, r, r)
    V = [(c[0], c[1], c[2] - rz)]
    for i in range(1, rings):
        ph = -pi / 2 + pi * i / rings
        for k in range(segs):
            a = tau * k / segs
            j = 1.0 + (rng.uniform(-jitter, jitter) if jitter else 0.0)
            V.append((c[0] + rx * j * cos(ph) * cos(a), c[1] + ry * j * cos(ph) * sin(a), c[2] + rz * j * sin(ph)))
    V.append((c[0], c[1], c[2] + rz))
    top = len(V) - 1
    F = []
    for k in range(segs):
        F.append((0, 1 + (k + 1) % segs, 1 + k))
    for i in range(rings - 2):
        for k in range(segs):
            a = 1 + i * segs + k
            b = 1 + i * segs + (k + 1) % segs
            F.append((a, b, b + segs, a + segs))
    base = 1 + (rings - 2) * segs
    for k in range(segs):
        F.append((base + k, base + (k + 1) % segs, top))
    F = orient(V, F, c)
    emit(mat, V, F, smooth)


def annulus(mat, c, r_out, r_in, z0, z1, a0=0.0, a1=360.0, segs=None, smooth=False):
    """Ring / ring-sector slab about a vertical axis (angles in degrees)."""
    span = a1 - a0
    full = abs(span) >= 359.999
    n = segs or max(3, int(abs(span) / 7.5))
    angs = [radians(a0 + span * i / n) for i in range(n + (0 if full else 1))]
    m = len(angs)
    V = []
    for a in angs:
        for r in (r_out, r_in):
            for z in (z0, z1):
                V.append((c[0] + r * cos(a), c[1] + r * sin(a), z))

    def I(i, ro, top):
        return 4 * (i % m) + (0 if ro else 2) + (1 if top else 0)
    F, S = [], []
    for i in range(n):
        j = i + 1
        F.append((I(i, 1, 0), I(j, 1, 0), I(j, 1, 1), I(i, 1, 1))); S.append(smooth)
        if r_in > 1e-4:
            F.append((I(j, 0, 0), I(i, 0, 0), I(i, 0, 1), I(j, 0, 1))); S.append(smooth)
        F.append((I(i, 0, 1), I(i, 1, 1), I(j, 1, 1), I(j, 0, 1))); S.append(False)
        F.append((I(j, 0, 0), I(j, 1, 0), I(i, 1, 0), I(i, 0, 0))); S.append(False)
    if span < 0:
        F = [tuple(reversed(f)) for f in F]
    if not full:
        rm, zm = (r_out + r_in) / 2, (z0 + z1) / 2
        for i, d in ((0, 1), (m - 1, -1)):
            am = (angs[i] + angs[i + d]) / 2
            ref = (c[0] + rm * cos(am), c[1] + rm * sin(am), zm)
            cap = orient(V, [(I(i, 1, 0), I(i, 0, 0), I(i, 0, 1), I(i, 1, 1))], ref)
            F += cap
            S.append(False)
    emit(mat, V, F, S)


def earclip(poly):
    """Triangulate a simple CCW polygon (list of 2D points) -> index triples."""
    idx = list(range(len(poly)))
    tris = []

    def area2(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def inside(p, a, b, c):
        return area2(a, b, p) >= -1e-12 and area2(b, c, p) >= -1e-12 and area2(c, a, p) >= -1e-12
    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = poly[i0], poly[i1], poly[i2]
            if area2(a, b, c) <= 1e-12:
                continue
            if any(inside(poly[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


def poly_area(pts):
    return 0.5 * sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))


def prism_frame(mat, pts, origin, u, v, w, depth, convex=None, smooth=False):
    """Extrude a 2D polygon (in the u,v plane through origin) by `depth` along w."""
    if poly_area(pts) < 0:
        pts = pts[::-1]
    n = len(pts)

    def P(a, b, t):
        return v_add(origin, v_add(v_add(v_mul(u, a), v_mul(v, b)), v_mul(w, t)))
    V = [P(a, b, 0.0) for a, b in pts] + [P(a, b, depth) for a, b in pts]
    F = []
    if convex or (convex is None and n <= 4):
        F.append(tuple(n + i for i in range(n)))
        F.append(tuple(reversed(range(n))))
    else:
        for t in earclip(pts):
            F.append((n + t[0], n + t[1], n + t[2]))
            F.append((t[2], t[1], t[0]))
    for i in range(n):
        j = (i + 1) % n
        F.append((i, j, n + j, n + i))
    if v_dot(v_cross(u, v), w) * depth < 0:
        F = [tuple(reversed(f)) for f in F]
    emit(mat, V, F, smooth)


def slab(mat, pts, z0, z1, convex=None):
    """Horizontal slab from a plan polygon."""
    prism_frame(mat, pts, (0, 0, z0), (1, 0, 0), (0, 1, 0), (0, 0, 1), z1 - z0, convex)


def vprism(mat, pts_xz, y, depth):
    """Vertical profile drawn in x (right) / z (up), extruded from y toward +y by depth (front face at y)."""
    prism_frame(mat, pts_xz, (0, y, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), depth)


def wall_xy(mat, a, b, z0, z1, t, ch=0.0):
    """Wall from plan point a to b, thickness t (centred), from z0 to z1."""
    L = math.dist(a, b)
    box(mat, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (z0 + z1) / 2), (L, t, z1 - z0), rz=math.atan2(b[1] - a[1], b[0] - a[0]), ch=ch)


def wall_open(mat, axis, a0, a1, c, z0, z1, t, openings=(), ch=0.0):
    """Straight wall along x ('x') or y ('y') from a0..a1 at cross position c, rectangular openings
    [(oa0, oa1, oz0, oz1)] cut through it."""
    cuts = sorted(set([a0, a1] + [min(max(o[0], a0), a1) for o in openings] + [min(max(o[1], a0), a1) for o in openings]))
    for s0, s1 in zip(cuts[:-1], cuts[1:]):
        if s1 - s0 < 1e-3:
            continue
        mid = (s0 + s1) / 2
        holes = sorted((o[2], o[3]) for o in openings if o[0] < mid < o[1])
        zc = z0
        spans = []
        for h0, h1 in holes:
            if h0 > zc:
                spans.append((zc, h0))
            zc = max(zc, h1)
        if zc < z1:
            spans.append((zc, z1))
        for q0, q1 in spans:
            if q1 - q0 < 1e-3:
                continue
            if axis == "x":
                box2(mat, s0, c - t / 2, q0, s1, c + t / 2, q1, ch)
            else:
                box2(mat, c - t / 2, s0, q0, c + t / 2, s1, q1, ch)


def arc_wall(mat, c, r_out, r_in, z0, z1, openings=(), seg_deg=6.0, a0=0.0, a1=360.0):
    """Curved wall with openings [(centre_deg, half_width_m, oz0, oz1)]."""
    n = max(1, int(round((a1 - a0) / seg_deg)))
    rm = (r_in + r_out) / 2
    for i in range(n):
        s0 = a0 + (a1 - a0) * i / n
        s1 = a0 + (a1 - a0) * (i + 1) / n
        mid = (s0 + s1) / 2
        holes = []
        for (oc, hw, h0, h1) in openings:
            d = ((mid - oc + 180) % 360) - 180
            if abs(radians(d)) * rm < hw:
                holes.append((h0, h1))
        holes.sort()
        zc = z0
        spans = []
        for h0, h1 in holes:
            if h0 > zc:
                spans.append((zc, h0))
            zc = max(zc, h1)
        if zc < z1:
            spans.append((zc, z1))
        for q0, q1 in spans:
            if q1 - q0 > 1e-3:
                annulus(mat, c, r_out, r_in, q0, q1, s0, s1, segs=1)


# ---------------------------------------------------------------- polygon minus disc (floors around the drum)
def _ccw(poly):
    return poly if poly_area(poly) > 0 else poly[::-1]


def ray_span(c, d, poly):
    P = _ccw(poly)
    t0, t1 = -1e9, 1e9
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        nx, ny = b[1] - a[1], -(b[0] - a[0])
        num = nx * (c[0] - a[0]) + ny * (c[1] - a[1])
        den = nx * d[0] + ny * d[1]
        if abs(den) < 1e-12:
            if num > 0:
                return None
            continue
        t = -num / den
        if den > 0:
            t1 = min(t1, t)
        else:
            t0 = max(t0, t)
    return (t0, t1) if t0 < t1 else None


def circle_poly_angles(c, r, poly):
    out = []
    for i in range(len(poly)):
        a, b = poly[i], poly[(i + 1) % len(poly)]
        dx, dy = b[0] - a[0], b[1] - a[1]
        fx, fy = a[0] - c[0], a[1] - c[1]
        A, B, Cc = dx * dx + dy * dy, 2 * (fx * dx + fy * dy), fx * fx + fy * fy - r * r
        disc = B * B - 4 * A * Cc
        if disc < 0:
            continue
        for s in (-1, 1):
            t = (-B + s * sqrt(disc)) / (2 * A)
            if 0 <= t <= 1:
                out.append(math.atan2(a[1] + t * dy - c[1], a[0] + t * dx - c[0]) % tau)
    return out


def region_minus_disc(mat, poly, c, r_in, z0, z1, n=96):
    """Slab over a convex polygon with a disc (centre c, radius r_in) removed. Built from wedge cells so
    nothing overlaps (no z-fighting)."""
    angs = {round(tau * i / n, 7) for i in range(n)}
    angs |= {round(math.atan2(y - c[1], x - c[0]) % tau, 7) for x, y in poly}
    angs |= {round(a, 7) for a in circle_poly_angles(c, r_in, poly)}
    angs = sorted(angs)
    inside_c = ray_span(c, (1.0, 0.0), poly) is not None and ray_span(c, (1.0, 0.0), poly)[0] <= 0

    def span(a):
        s = ray_span(c, (cos(a), sin(a)), poly)
        if not s:
            return None
        ta, tb = max(s[0], 0.0, r_in), s[1]
        if tb < ta + 1e-4:
            return None
        return ta, tb
    for a0, a1 in zip(angs, angs[1:] + [angs[0] + tau]):
        s0, s1 = span(a0 + 1e-6), span(a1 - 1e-6)
        if not s0 or not s1:
            continue
        d0, d1 = (cos(a0), sin(a0)), (cos(a1), sin(a1))
        q = [(c[0] + s0[0] * d0[0], c[1] + s0[0] * d0[1]), (c[0] + s1[0] * d1[0], c[1] + s1[0] * d1[1]),
             (c[0] + s1[1] * d1[0], c[1] + s1[1] * d1[1]), (c[0] + s0[1] * d0[0], c[1] + s0[1] * d0[1])]
        dq = [q[0]]
        for p in q[1:]:
            if math.dist(p, dq[-1]) > 1e-4:
                dq.append(p)
        if math.dist(dq[0], dq[-1]) < 1e-4:
            dq.pop()
        if len(dq) >= 3 and abs(poly_area(dq)) > 1e-5:
            slab(mat, dq, z0, z1, convex=True)
    return inside_c


def rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


# ================================================================ materials
MAT_DEFS = {
    # name: (rgb, metallic, roughness, extra)
    "marble_warm":   ((0.80, 0.76, 0.68), 0.0, 0.42, "stone"),
    "marble_white":  ((0.90, 0.88, 0.83), 0.0, 0.35, "stone"),
    "marble_dark":   ((0.07, 0.07, 0.08), 0.0, 0.16, "stone"),      # Hades: polished black marble
    "stone_old":     ((0.36, 0.35, 0.33), 0.0, 0.85, "stone"),      # ancient foundations
    "stone_light":   ((0.62, 0.59, 0.53), 0.0, 0.75, "stone"),
    "slate":         ((0.12, 0.13, 0.15), 0.0, 0.55, "stone"),
    "bronze":        ((0.55, 0.33, 0.14), 1.0, 0.33, "metal"),
    "bronze_dark":   ((0.25, 0.15, 0.08), 1.0, 0.45, "metal"),
    "gold":          ((0.83, 0.58, 0.18), 1.0, 0.24, "metal"),
    "iron":          ((0.10, 0.10, 0.11), 1.0, 0.55, "metal"),
    "glass":         ((0.70, 0.85, 0.80), 0.0, 0.04, "glass"),
    "wood_dark":     ((0.20, 0.11, 0.06), 0.0, 0.65, "wood"),
    "wood_light":    ((0.47, 0.30, 0.16), 0.0, 0.60, "wood"),
    "bark":          ((0.22, 0.16, 0.11), 0.0, 0.90, "bark"),
    "root":          ((0.30, 0.22, 0.15), 0.0, 0.85, "bark"),
    "leaf_dark":     ((0.05, 0.16, 0.06), 0.0, 0.70, "leaf"),
    "leaf_mid":      ((0.13, 0.30, 0.09), 0.0, 0.65, "leaf"),
    "leaf_light":    ((0.30, 0.45, 0.14), 0.0, 0.62, "leaf"),
    "moss":          ((0.19, 0.30, 0.10), 0.0, 0.95, "leaf"),
    "grass":         ((0.17, 0.33, 0.10), 0.0, 0.95, "grass"),
    "soil":          ((0.17, 0.11, 0.07), 0.0, 1.00, "grass"),
    "path":          ((0.55, 0.48, 0.38), 0.0, 0.90, "stone"),
    "flower_pink":   ((0.86, 0.32, 0.52), 0.0, 0.60, None),
    "flower_purple": ((0.45, 0.24, 0.66), 0.0, 0.60, None),
    "flower_white":  ((0.93, 0.92, 0.86), 0.0, 0.60, None),
    "maroon":        ((0.36, 0.04, 0.08), 0.0, 0.80, "cloth"),
    "cream":         ((0.92, 0.86, 0.72), 0.0, 0.75, "cloth"),
    "leather":       ((0.35, 0.18, 0.09), 0.0, 0.70, None),
    "parchment":     ((0.86, 0.79, 0.62), 0.0, 0.85, None),
    "book_red":      ((0.40, 0.08, 0.07), 0.0, 0.70, None),
    "book_blue":     ((0.09, 0.15, 0.30), 0.0, 0.70, None),
    "book_green":    ((0.10, 0.24, 0.13), 0.0, 0.70, None),
    "water":         ((0.02, 0.04, 0.05), 0.0, 0.03, "water"),
    "fire":          ((1.00, 0.42, 0.08), 0.0, 0.50, ("emit", 12.0)),
    "rift_gold":     ((1.00, 0.72, 0.30), 0.0, 0.50, ("emit", 8.0)),
    "spirit":        ((0.55, 0.85, 1.00), 0.0, 0.50, ("emit", 6.0)),
    "candle":        ((1.00, 0.80, 0.50), 0.0, 0.50, ("emit", 5.0)),
}
MATS = {}


def _input(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    return None


def make_material(name):
    rgb, metal, rough, extra = MAT_DEFS[name]
    full = "GodHouse | " + name
    m = bpy.data.materials.get(full) or bpy.data.materials.new(full)
    m.diffuse_color = (*rgb, 1.0)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        return m
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = rough
    try:
        if extra == "glass":
            t = _input(bsdf, "Transmission Weight", "Transmission")
            if t:
                t.default_value = 0.95
            m.blend_method = "BLEND" if hasattr(m, "blend_method") else None
        elif extra == "water":
            bsdf.inputs["Roughness"].default_value = 0.02
        elif isinstance(extra, tuple) and extra[0] == "emit":
            e = _input(bsdf, "Emission Color", "Emission")
            if e:
                e.default_value = (*rgb, 1.0)
            s = _input(bsdf, "Emission Strength")
            if s:
                s.default_value = extra[1]
        elif extra in ("stone", "wood", "bark", "leaf", "grass", "cloth"):
            # gentle procedural variation + bump so surfaces don't read as flat plastic in Blender
            scale = {"stone": 2.5, "wood": 6.0, "bark": 3.0, "leaf": 4.0, "grass": 1.2, "cloth": 12.0}[extra]
            tc = nt.nodes.new("ShaderNodeTexCoord")
            nz = nt.nodes.new("ShaderNodeTexNoise")
            nz.inputs["Scale"].default_value = scale
            nz.inputs["Detail"].default_value = 6.0
            ramp = nt.nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (rgb[0] * 0.78, rgb[1] * 0.78, rgb[2] * 0.78, 1.0)
            ramp.color_ramp.elements[1].color = (min(1, rgb[0] * 1.12), min(1, rgb[1] * 1.12), min(1, rgb[2] * 1.12), 1.0)
            bump = nt.nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = 0.25 if extra != "stone" else 0.12
            nt.links.new(tc.outputs["Object"], nz.inputs["Vector"])
            nt.links.new(nz.outputs["Fac"], ramp.inputs["Fac"])
            nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
            nt.links.new(nz.outputs["Fac"], bump.inputs["Height"])
            nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    except Exception as ex:          # never let a node-API difference stop the build
        print("GodHouse: simplified material", name, ex)
    return m


def MAT(name):
    if name not in MATS:
        MATS[name] = make_material(name)
    return MATS[name]


# ================================================================ SITE: the hill, roads, plateau, podium, forecourt
PLAT = [(-50, -46), (50, -46), (58, -36), (58, 40), (48, 50), (-48, 50), (-58, 40), (-58, -36)]   # plateau rim (convex)
PODIUM = (-44.0, -28.0, 44.0, 38.0)
FC = (0.0, -38.5)                      # forecourt centre (concentric paving, the great round pedestal)
STAIR_HW, LAND_HW = 8.0, 13.0          # grand stair half-width, landing half-width
FLIGHTS, PER_FLIGHT = 4, 15
RISE = H / (FLIGHTS * PER_FLIGHT)        # 60 risers down the hill: four flights with a landing between each
TREAD, LAND_LEN = 0.8, 6.0
GRID, GRID_EXT, SLOPE_LEN = 3.0, 135.0, 66.0
DEEP = None                              # (set below) hill height hidden under the plateau


def inset_poly(poly, d):
    """Inset a convex CCW polygon by d."""
    P = _ccw(poly)
    n = len(P)
    lines = []
    for i in range(n):
        a, b = P[i], P[(i + 1) % n]
        dx, dy = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dy)
        nx, ny = -dy / L, dx / L                     # inward normal for CCW
        lines.append(((a[0] + nx * d, a[1] + ny * d), (dx, dy)))
    out = []
    for i in range(n):
        (p1, d1), (p2, d2) = lines[i - 1], lines[i]
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((p2[0] - p1[0]) * d2[1] - (p2[1] - p1[1]) * d2[0]) / den
        out.append((p1[0] + d1[0] * t, p1[1] + d1[1] * t))
    return out


def poly_sdist(p, poly):
    """Signed distance to a convex polygon (negative inside)."""
    P = _ccw(poly)
    best_out, inside = 1e9, True
    max_in = -1e9
    for i in range(len(P)):
        a, b = P[i], P[(i + 1) % len(P)]
        ex, ey = b[0] - a[0], b[1] - a[1]
        L = math.hypot(ex, ey)
        nx, ny = ey / L, -ex / L                      # outward normal
        dd = (p[0] - a[0]) * nx + (p[1] - a[1]) * ny
        max_in = max(max_in, dd)
        if dd > 0:
            inside = False
        t = max(0.0, min(1.0, ((p[0] - a[0]) * ex + (p[1] - a[1]) * ey) / (L * L)))
        best_out = min(best_out, math.hypot(p[0] - a[0] - ex * t, p[1] - a[1] - ey * t))
    return max_in if inside else best_out


# ---- grand stair profile (y -> top of tread)
STAIR_SEGS = []          # (y_hi, y_lo, top_z, kind)


def _build_stair_profile():
    y, k = -46.0, 0
    for flight in range(FLIGHTS):
        for s in range(PER_FLIGHT - 1):
            k += 1
            STAIR_SEGS.append((y, y - TREAD, H - RISE * k, "step"))
            y -= TREAD
        k += 1
        if flight < FLIGHTS - 1:
            STAIR_SEGS.append((y, y - LAND_LEN, H - RISE * k, "landing"))
            y -= LAND_LEN
        else:
            STAIR_SEGS.append((y, y - TREAD, H - RISE * k, "step"))   # last riser lands on the road (top = 0)
            y -= TREAD


_build_stair_profile()
STAIR_FOOT = STAIR_SEGS[-1][1]


def stair_top(y):
    for (yh, yl, z, kind) in STAIR_SEGS:
        if yl <= y <= yh:
            return z
    return 0.0 if y < STAIR_FOOT else H


def hill_fn(x, y):
    d = poly_sdist((x, y), PLAT)
    if d <= 0:
        return H - 0.6 if d > -3.2 else U - 3.0
    t = min(1.0, d / SLOPE_LEN)
    h = (H - 0.6) * (1.0 - smoothstep(0.0, SLOPE_LEN, d * 0.85 + 0.15 * SLOPE_LEN * t * t))
    h += (1.6 * sin(x * 0.07) * cos(y * 0.06) + 0.8 * sin(x * 0.17 + y * 0.13)) * sin(pi * t)
    h = max(h, -0.2)
    if abs(x) < LAND_HW + 1.6 and STAIR_FOOT - 1.0 < y < -46.0:
        h = min(h, stair_top(y) - 0.6)
    return h


HILL = {}


def hill_z(x, y):
    """Height of the actual hill mesh at (x, y) (max of both quad diagonals, so ribbons never sink)."""
    gx, gy = (x + GRID_EXT) / GRID, (y + GRID_EXT) / GRID
    i, j = int(math.floor(gx)), int(math.floor(gy))
    fx, fy = gx - i, gy - j
    z00, z10 = HILL.get((i, j), 0.0), HILL.get((i + 1, j), 0.0)
    z01, z11 = HILL.get((i, j + 1), 0.0), HILL.get((i + 1, j + 1), 0.0)
    a = z00 + (z10 - z00) * fx + (z11 - z10) * fy if fx >= fy else z00 + (z11 - z01) * fx + (z01 - z00) * fy
    b = z00 + (z10 - z00) * fx + (z01 - z00) * fy if fx + fy <= 1 else z11 + (z01 - z11) * (1 - fx) + (z10 - z11) * (1 - fy)
    return max(a, b)


def build_hill():
    n = int(2 * GRID_EXT / GRID)
    for i in range(n + 1):
        for j in range(n + 1):
            x, y = -GRID_EXT + i * GRID, -GRID_EXT + j * GRID
            HILL[(i, j)] = hill_fn(x, y)
    V, F = [], []
    idx = {}
    for i in range(n + 1):
        for j in range(n + 1):
            idx[(i, j)] = len(V)
            V.append((-GRID_EXT + i * GRID, -GRID_EXT + j * GRID, HILL[(i, j)]))
    deep = lambda i, j: HILL[(i, j)] < U - 2.0
    for i in range(n):
        for j in range(n):
            if all(deep(a, b) for a, b in ((i, j), (i + 1, j), (i, j + 1), (i + 1, j + 1))):
                continue
            F.append((idx[(i, j)], idx[(i + 1, j)], idx[(i + 1, j + 1)], idx[(i, j + 1)]))
    with part("Hill", "01_Hill_Roads"):
        emit("grass", V, F, True)
    # boulders and outcrops on the slopes (never on the stair or the roads)
    with part("Hill_Rocks", "01_Hill_Roads"):
        k = 0
        while k < 60:
            x, y = rng.uniform(-125, 125), rng.uniform(-125, 125)
            d = poly_sdist((x, y), PLAT)
            if not (4 < d < 64) or (abs(x) < 20 and y < -40) or near_road(x, y, 6.0):
                continue
            s = rng.uniform(0.8, 2.4)
            blob("stone_old", (x, y, hill_z(x, y) + s * 0.15), (s, s * 0.8, s * 0.55), segs=7, rings=4, jitter=0.18)
            k += 1


# ---- roads that lead up to the God House
ROADS = [
    [(0.0, -134.0), (0.0, STAIR_FOOT - 0.2)],                                                 # south: to the grand stair
    [(134.0, -60.0), (112.0, -52.0), (94.0, -36.0), (78.0, -16.0), (66.0, -4.0), (59.6, 0.0)],  # east
    [(-134.0, -60.0), (-112.0, -52.0), (-94.0, -36.0), (-78.0, -16.0), (-66.0, -4.0), (-59.6, 0.0)],
]


def _densify(pts, step=1.5):
    out = [pts[0]]
    for a, b in zip(pts[:-1], pts[1:]):
        L = math.dist(a, b)
        n = max(1, int(L / step))
        for i in range(1, n + 1):
            t = i / n
            # gentle curve: Catmull-Rom-ish smoothing is overkill here; straight runs with many samples
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
    return out


def near_road(x, y, m):
    for r in ROADS:
        for a, b in zip(r[:-1], r[1:]):
            ex, ey = b[0] - a[0], b[1] - a[1]
            L2_ = ex * ex + ey * ey
            t = max(0.0, min(1.0, ((x - a[0]) * ex + (y - a[1]) * ey) / L2_))
            if math.hypot(x - a[0] - ex * t, y - a[1] - ey * t) < m:
                return True
    return False


def build_roads():
    with part("Roads", "01_Hill_Roads"):
        for r, hw in zip(ROADS, (6.0, 3.2, 3.2)):
            pts = _densify(r)
            V, F = [], []
            for i, (x, y) in enumerate(pts):
                a = pts[max(i - 1, 0)]
                b = pts[min(i + 1, len(pts) - 1)]
                tx, ty = b[0] - a[0], b[1] - a[1]
                L = math.hypot(tx, ty) or 1.0
                nx, ny = -ty / L, tx / L
                for s in (-1.0, -0.55, 0.55, 1.0):
                    px, py = x + nx * hw * s, y + ny * hw * s
                    V.append((px, py, hill_z(px, py) + 0.10))
            for i in range(len(pts) - 1):
                for k in range(3):
                    F.append((4 * i + k, 4 * i + k + 1, 4 * (i + 1) + k + 1, 4 * (i + 1) + k))
            # orient upward
            F = [f if newell([V[q] for q in f])[2] > 0 else tuple(reversed(f)) for f in F]
            emit("path", V, F)
            # kerb stones along both edges
            for i in range(0, len(pts) - 1, 2):
                for s in (-1, 1):
                    x, y = pts[i]
                    a = pts[max(i - 1, 0)]
                    b = pts[min(i + 1, len(pts) - 1)]
                    L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
                    nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
                    px, py = x + nx * (hw + 0.25) * s, y + ny * (hw + 0.25) * s
                    box("stone_light", (px, py, hill_z(px, py) + 0.12), (0.45, 1.3, 0.3), rz=math.atan2(b[1] - a[1], b[0] - a[0]) + pi / 2)
        # side entries: three steps from the road up through the rim wall onto the plateau
        for sx in (-1, 1):
            for k in range(3):
                top = H - 0.6 + 0.2 * (k + 1)
                x = sx * (59.8 - 0.6 * k - 0.3)
                box("stone_light", (x, 0.0, (top + H - 3.0) / 2), (0.6, 6.4, top - (H - 3.0)), ch=0.02)
            box("stone_light", (sx * 57.4, 0.0, H - 0.25), (1.2, 6.4, 0.5))       # fills the rim-wall gap


# ---- the grand stair down the hill
def cheek(x0, x1, ya, yb, top_fn):
    """Retaining cheek wall between x0..x1 along y from ya (south) to yb (north); top follows top_fn(y)."""
    n = max(2, int((yb - ya) / 1.0))
    tops = [(ya + (yb - ya) * i / n, top_fn(ya + (yb - ya) * i / n)) for i in range(n + 1)]
    pts = [(ya, -1.0), (yb, -1.0)] + [(y, z) for y, z in reversed(tops)]
    prism_frame("stone_old", pts, (x0, 0, 0), (0, 1, 0), (0, 0, 1), (1, 0, 0), x1 - x0)
    # dark-marble coping, raised 6 cm so it never shares a surface with the wall
    for (y0, z0), (y1, z1) in zip(tops[:-1], tops[1:]):
        L = math.hypot(y1 - y0, z1 - z0)
        box("marble_dark", ((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2 + 0.08), (x1 - x0 + 0.16, L + 0.02, 0.16))


def build_grand_stair():
    with part("Grand_Stair", "01_Hill_Roads"):
        for (yh, yl, z, kind) in STAIR_SEGS:
            hw = LAND_HW if kind == "landing" else STAIR_HW
            if z <= 1e-3:
                continue
            box("marble_white" if kind == "step" else "marble_warm", (0, (yh + yl) / 2, (z - 1.0) / 2), (2 * hw, yh - yl, z + 1.0), ch=0.02)
            if kind == "step":                                                   # bronze nosing, proud of the riser
                box("bronze", (0, yl - 0.03, z - 0.02), (2 * hw - 0.6, 0.06, 0.08))
            else:                                                                # landing inlay: dark marble rings
                annulus("marble_dark", (0, (yh + yl) / 2), 2.6, 2.3, z, z + 0.03, segs=32)
                annulus("gold", (0, (yh + yl) / 2), 1.2, 1.05, z, z + 0.03, segs=24)
        # cheek walls along each flight and round each landing
        flights = []
        cur = None
        for seg in STAIR_SEGS:
            if seg[3] == "step":
                cur = (seg[0], seg[1]) if cur is None else (cur[0], seg[1])
            else:
                flights.append(cur)
                cur = None
        flights.append(cur)

        def top_at(x):
            return lambda y: max(stair_top(min(y, -46.0)) + 1.1, hill_z(x, y) + 0.5)
        for (yh, yl) in flights:
            for sx in (-1, 1):
                x0, x1 = (STAIR_HW, STAIR_HW + 1.2) if sx > 0 else (-STAIR_HW - 1.2, -STAIR_HW)
                cheek(x0, x1, yl, yh + (0.0 if yh < -46.5 else 0.0), top_at(sx * (STAIR_HW + 1.4)))
        for (yh, yl, z, kind) in STAIR_SEGS:
            if kind != "landing":
                continue
            for sx in (-1, 1):
                xa, xb = (LAND_HW, LAND_HW + 1.2) if sx > 0 else (-LAND_HW - 1.2, -LAND_HW)
                cheek(xa, xb, yl - 1.2, yh + 1.2, top_at(sx * (LAND_HW + 1.4)))
                for yy in (yl - 0.6, yh + 0.6):                                   # step-back walls to the flight cheeks
                    x0, x1 = sorted((sx * (STAIR_HW + 1.2), sx * LAND_HW))
                    tz = max(z + 1.1, hill_z(sx * (LAND_HW - 1), yy) + 0.5)
                    box("stone_old", ((x0 + x1) / 2, yy, (tz - 1.0) / 2), (x1 - x0, 1.2, tz + 1.0))
                    box("marble_dark", ((x0 + x1) / 2, yy, tz + 0.08), (x1 - x0 + 0.16, 1.36, 0.16))
        # lanterns on the cheek walls
        y = -50.0
        while y > STAIR_FOOT + 1:
            if stair_top(y) > 0 and all(not (sg[1] - 1 <= y <= sg[0] + 1) or sg[3] == "step" for sg in STAIR_SEGS):
                for sx in (-1, 1):
                    x = sx * (STAIR_HW + 0.6)
                    z = max(stair_top(y) + 1.1, hill_z(sx * (STAIR_HW + 1.4), y) + 0.5) + 0.16
                    lantern(x, y, z)
            y -= 7.0


def lantern(x, y, z):
    box("bronze_dark", (x, y, z + 0.06), (0.4, 0.4, 0.12))
    frustum("bronze", (x, y, z + 0.12), 0.05, 0.05, 0.5, 6)
    box("bronze", (x, y, z + 0.66), (0.34, 0.34, 0.06))
    box("candle", (x, y, z + 0.84), (0.22, 0.22, 0.3))
    frustum("bronze", (x, y, z + 0.99), 0.26, 0.02, 0.28, 4, a0=pi / 4)


# ---- plateau, rim walls, podium
def build_plateau():
    inner = inset_poly(PLAT, 1.2)
    with part("Plateau", "02_Forecourt_Podium"):
        region_minus_disc("marble_warm", inner, RC, R_OUT, H - 0.25, H, n=128)
        P = _ccw(PLAT)
        openings = {"S": (-8.0, 8.0), "E": (-3.2, 3.2), "W": (-3.2, 3.2)}
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L = math.hypot(dx, dy)
            ux, uy = dx / L, dy / L
            nx, ny = -uy, ux                                     # inward
            cx, cy = (a[0] + b[0]) / 2 + nx * 0.6, (a[1] + b[1]) / 2 + ny * 0.6
            ang = math.atan2(dy, dx)
            # which side is this edge? cut openings for the stair (south) and side roads (east, west)
            cut = None
            if abs(dy) < 1e-6 and a[1] < 0:
                cut = openings["S"]
                coord = lambda t: a[0] + ux * t
            elif abs(dx) < 1e-6 and a[0] > 0:
                cut = openings["E"]
                coord = lambda t: a[1] + uy * t
            elif abs(dx) < 1e-6 and a[0] < 0:
                cut = openings["W"]
                coord = lambda t: a[1] + uy * t
            spans = [(-0.6, L + 0.6)]
            if cut:
                t0 = sorted([(cut[0] - (a[0] if abs(dy) < 1e-6 else a[1])) / (ux if abs(dy) < 1e-6 else uy),
                             (cut[1] - (a[0] if abs(dy) < 1e-6 else a[1])) / (ux if abs(dy) < 1e-6 else uy)])
                spans = [(-0.6, t0[0]), (t0[1], L + 0.6)]
            for (s0, s1) in spans:
                mx, my = a[0] + ux * (s0 + s1) / 2 + nx * 0.6, a[1] + uy * (s0 + s1) / 2 + ny * 0.6
                box("stone_old", (mx, my, H - 1.75), (s1 - s0, 1.2, 3.5), rz=ang)
                ps0, ps1 = max(s0, 0.0), min(s1, L)
                px, py = a[0] + ux * (ps0 + ps1) / 2 + nx * 0.35, a[1] + uy * (ps0 + ps1) / 2 + ny * 0.35
                box("marble_warm", (px, py, H + 0.35), (ps1 - ps0, 0.7, 0.7), rz=ang, ch=0.04)       # parapet
                box("marble_dark", (px, py, H + 0.76), (ps1 - ps0 + 0.04, 0.84, 0.12), rz=ang)       # coping
            if cut:                                                                                 # fill the rim gap
                mid = (cut[0] + cut[1]) / 2
                if abs(dy) < 1e-6:
                    box("marble_warm", (mid, a[1] + 0.6, H - 0.25), (cut[1] - cut[0], 1.2, 0.5))
        # gold band round the rim, proud of the wall face
        for i in range(len(P)):
            a, b = P[i], P[(i + 1) % len(P)]
            wall_xy("gold", (a[0], a[1]), (b[0], b[1]), H - 0.75, H - 0.6, 0.06)


def build_podium():
    x0, y0, x1, y1 = PODIUM
    with part("Podium", "02_Forecourt_Podium"):
        region_minus_disc("marble_dark", rect(x0, y0, x1, y1), RC, R_OUT, H, G - 0.12, n=128)       # Hades' dark base
        region_minus_disc("marble_warm", rect(x0, y0, x1, y1), RC, R_OUT, G - 0.12, G, n=128)       # paving
        for (a, b) in (((x0, y0), (x1, y0)), ((x1, y0), (x1, y1)), ((x1, y1), (x0, y1)), ((x0, y1), (x0, y0))):
            wall_xy("gold", a, b, G - 0.62, G - 0.5, 0.08)
        # front steps across the whole front (5 x 0.24 m), side steps east/west, rear steps north
        for k in range(1, 6):
            top = H + 0.24 * k
            y = y0 - 0.6 * (5 - k) - 0.3
            box("marble_white", (0, y, (H + top) / 2), (2 * x1, 0.6, top - H), ch=0.015)
        for sx in (-1, 1):
            for k in range(1, 6):
                top = H + 0.24 * k
                x = sx * (x1 + 0.6 * (5 - k) + 0.3)
                box("marble_white", (x, 0.0, (H + top) / 2), (0.6, 8.0, top - H), ch=0.015)
        for k in range(1, 6):
            top = H + 0.24 * k
            y = y1 + 0.6 * (5 - k) + 0.3
            box("marble_white", (0, y, (H + top) / 2), (16.0, 0.6, top - H), ch=0.015)


def arc_band(mat, c, r0, r1, z0, z1, step=4):
    annulus(mat, c, r1, r0, z0, z1, segs=int(360 / step))


def build_forecourt():
    with part("Forecourt", "02_Forecourt_Podium"):
        for (r0, r1, m) in ((3.1, 3.25, "gold"), (3.9, 4.7, "slate"), (4.7, 4.82, "gold"), (5.6, 6.3, "slate"),
                            (6.3, 6.42, "gold"), (7.0, 7.2, "marble_dark")):
            arc_band(m, FC, r0, r1, H, H + 0.04)
        # four radiating gold lines (compass of the camp roads)
        for d in (45, 135, 225, 315):
            a = radians(d)
            box("gold", (FC[0] + 5.2 * cos(a), FC[1] + 5.2 * sin(a), H + 0.02), (3.4, 0.12, 0.04), rz=a)
        # low planter walls along the forecourt sides, flowering shrubs
        for sx in (-1, 1):
            for (xa, xb) in ((14.0, 30.0), (34.0, 52.0)):
                x0_, x1_ = sorted((sx * xa, sx * xb))
                box2("marble_warm", x0_, -44.0, H, x1_, -42.6, H + 0.7, ch=0.04)
                box2("soil", x0_ + 0.15, -43.85, H + 0.7, x1_ - 0.15, -42.75, H + 0.74)
                x = x0_ + 0.8
                while x < x1_ - 0.6:
                    shrub(x, -43.3, H + 0.74, 0.55)
                    x += 1.6
        # benches facing the forecourt rings
        for sx in (-1, 1):
            for y in (-41.5, -35.5):
                bench(sx * 11.0, y, H, rz=pi / 2 * sx)


def build_rear_courtyard():
    """North of the podium, at plateau level: the quiet garden of remembrance (Hades)."""
    with part("Rear_Courtyard", "02_Forecourt_Podium"):
        # reflecting pool: dark stone rim with the water inside (water surface 3 cm above the basin floor)
        x0, y0, x1, y1 = -10.0, 42.0, 10.0, 48.0
        for (a, b, c_, d) in ((x0, y0, x1, y0 + 0.5), (x0, y1 - 0.5, x1, y1), (x0, y0 + 0.5, x0 + 0.5, y1 - 0.5), (x1 - 0.5, y0 + 0.5, x1, y1 - 0.5)):
            box2("marble_dark", a, b, H, c_, d, H + 0.5, ch=0.03)
        box2("slate", x0 + 0.5, y0 + 0.5, H, x1 - 0.5, y1 - 0.5, H + 0.08)
        box2("water", x0 + 0.5, y0 + 0.5, H + 0.08, x1 - 0.5, y1 - 0.5, H + 0.38)
        for x in (-6.0, 0.0, 6.0):                                                     # floating candle stones
            frustum("stone_light", (x, 45.0, H + 0.38), 0.3, 0.26, 0.08, 10)
            box("candle", (x, 45.0, H + 0.53), (0.1, 0.1, 0.22))
        for sx in (-1, 1):
            bench(sx * 13.0, 45.0, H, rz=pi / 2 * sx)
            for y in (41.0, 45.0, 49.0):
                cypress(sx * 17.5, y, H)
        for x in (-30, -24, 24, 30):
            cypress(x, 46.0, H)


def bench(x, y, z, rz=0.0):
    with at((x, y, z), rz):
        for sx in (-1, 1):
            box("marble_warm", (sx * 0.9, 0, 0.22), (0.3, 0.5, 0.44), ch=0.03)
        box("marble_white", (0, 0, 0.5), (2.4, 0.6, 0.12), ch=0.03)


def shrub(x, y, z, s=0.6, flowers=True):
    blob(rng.choice(["leaf_dark", "leaf_mid"]), (x, y, z + s * 0.55), (s, s * 0.9, s * 0.65), segs=6, rings=4, jitter=0.15)
    if flowers:
        for k in range(3):
            a = rng.uniform(0, tau)
            blob(rng.choice(["flower_pink", "flower_purple", "flower_white"]),
                 (x + s * 0.6 * cos(a), y + s * 0.6 * sin(a), z + s * 0.95), 0.12, segs=4, rings=3)


def cypress(x, y, z, h=None):
    h = h or rng.uniform(6.5, 9.0)
    frustum("bark", (x, y, z), 0.22, 0.15, 1.2, 6)
    frustum("leaf_dark", (x, y, z + 0.8), 1.0, 0.0, h, 8, smooth=True)
    frustum("leaf_mid", (x, y, z + 1.4), 0.85, 0.05, h * 0.75, 7, smooth=True, a0=0.3)


def pine(x, y, z, h=None):
    h = h or rng.uniform(9, 14)
    frustum("bark", (x, y, z - 0.3), 0.35, 0.2, h * 0.45, 6)
    for k in range(4):
        zz = z + h * (0.22 + 0.18 * k)
        r = 2.6 * (1 - 0.2 * k)
        frustum("leaf_dark" if k % 2 == 0 else "leaf_mid", (x, y, zz), r, 0.15, h * 0.32, 8, a0=k * 0.4)


def build_hill_trees():
    with part("Hill_Trees", "01_Hill_Roads"):
        k = 0
        while k < 90:
            x, y = rng.uniform(-128, 128), rng.uniform(-128, 128)
            d = poly_sdist((x, y), PLAT)
            if d < 6 or (abs(x) < 22 and y < -40) or near_road(x, y, 7.0):
                continue
            pine(x, y, hill_z(x, y))
            k += 1


# ================================================================ THE GARDEN ATRIUM, THE SACRED TREE, THE UNDERCROFT
def rel(deg):
    """Angle measured from the spiral's start (A0)."""
    return A0 + deg


def rail_arc(c, r, z, a0, a1, step=10.0, mat="bronze", h=1.1):
    n = max(1, int(round((a1 - a0) / step)))
    for i in range(n + 1):
        a = a0 + (a1 - a0) * i / n
        p = polar(c, r, a, z + h / 2)
        box(mat, p, (0.1, 0.1, h), rz=radians(a))
    annulus(mat, c, r + 0.06, r - 0.06, z + h - 0.1, z + h, a0, a1, segs=max(2, n * 2))
    annulus(mat, c, r + 0.04, r - 0.04, z + h * 0.45, z + h * 0.45 + 0.06, a0, a1, segs=max(2, n * 2))
    # Hephaestus' ironwork: a small ring between every pair of posts
    for i in range(n):
        a = a0 + (a1 - a0) * (i + 0.5) / n
        p = polar(c, r, a, z + h * 0.72)
        tang = radians(a) + pi / 2
        frustum(mat, v_add(p, (0.0, 0.0, 0.0)), 0.16, 0.16, 0.04, 8, axis=(cos(radians(a)), sin(radians(a)), 0), caps=False, smooth=False)


DRUM_OPENINGS = [
    # (centre deg, half width m, z0, z1)
    (-90, 2.5, G - 0.5, G + 5.5), (0, 2.5, G - 0.5, G + 5.5), (180, 2.5, G - 0.5, G + 5.5), (90, 2.5, G - 0.5, G + 5.5),
    (0, 2.0, U - 0.5, U + 4.7), (90, 2.0, U - 0.5, U + 4.7), (180, 2.0, U - 0.5, U + 4.7),                  # vault tunnels
    (90, 2.0, L1, L1 + 4.8),                                                                # rear upper floor
    (-90, 2.0, L2, L2 + 4.8), (90, 2.0, L2, L2 + 4.8),                                      # hall roof terrace, rear roof garden
] + [(22.5 + 45 * k, 1.1, G + 8.0, G + 12.0) for k in range(8)] + [(22.5 + 45 * k, 1.1, G + 14.6, G + 18.2) for k in range(8)]


def build_drum():
    with part("Atrium_Drum", "04_Garden_Atrium"):
        arc_wall("marble_warm", RC, R_OUT, R_IN, U - 0.5, OBS - 0.4, DRUM_OPENINGS, seg_deg=4.0)
        # bronze reveals (frames) round the ground doors
        for d in (-90, 0, 90, 180):
            for s in (-1, 1):
                a = d + s * math.degrees(2.62 / R_OUT)
                p = polar(RC, R_OUT + 0.1, a)
                box("bronze", (p[0], p[1], G + 2.75), (0.25, 0.3, 5.5), rz=radians(a))
            p = polar(RC, R_OUT + 0.1, d)
            box("bronze", (p[0], p[1], G + 5.65), (0.3, 5.6, 0.3), rz=radians(d))
        # exterior gold bands and pilasters (between the openings)
        for z in (G + 6.15, G + 12.7):
            annulus("gold", RC, R_OUT + 0.08, R_OUT - 0.02, z, z + 0.14, segs=96)
        for k in range(12):
            a = 15 + 30 * k
            p = polar(RC, R_OUT + 0.12, a)
            box("marble_white", (p[0], p[1], (G + OBS - 0.9) / 2), (0.28, 0.9, OBS - 0.9 - G), rz=radians(a))
            p2 = polar(RC, R_OUT + 0.2, a)
            box("bronze", (p2[0], p2[1], OBS - 1.15), (0.3, 1.1, 0.5), rz=radians(a))
        annulus("bronze", RC, R_OUT + 0.5, R_OUT - 0.05, OBS - 0.9, OBS - 0.4, segs=96)       # cornice under the balcony
        # inner window sills (dark marble), proud of the wall
        for k in range(8):
            a = 22.5 + 45 * k
            for z in (G + 8.0, G + 14.6):
                p = polar(RC, R_IN - 0.08, a)
                box("marble_dark", (p[0], p[1], z), (0.24, 2.3, 0.12), rz=radians(a))


def build_atrium_floors():
    with part("Atrium_Floor", "04_Garden_Atrium"):
        annulus("marble_warm", RC, R_IN + 0.02, SP_OUT, G - 0.5, G, segs=96)
        annulus("marble_warm", RC, SP_OUT + 0.01, TRUNK_R + 0.08, G - 0.5, G, rel(-10), rel(10), segs=4)  # spiral landing
        annulus("marble_dark", RC, 10.15, 9.85, G, G + 0.03, segs=96)                            # dark ring inlay
        # garden beds round the tree (paths open at the four doors)
        gaps = [-90, 0, 90, 180]
        half = math.degrees(1.9 / 7.0)
        for k in range(4):
            a0 = gaps[k] + half
            a1 = gaps[(k + 1) % 4] + (360 if k == 3 else 0) - half
            annulus("marble_dark", RC, 8.0, 7.8, G, G + 0.5, a0, a1)
            annulus("marble_dark", RC, 6.2, 6.0, G, G + 0.5, a0, a1)
            annulus("soil", RC, 7.8, 6.2, G, G + 0.42, a0, a1)
            n = int((a1 - a0) / 9)
            for i in range(n):
                a = a0 + (a1 - a0) * (i + 0.5) / n
                if min(abs(((a - d + 180) % 360) - 180) for d in (45, 135, 225, 315)) < 14:
                    continue                                                    # room for the pedestals
                p = polar(RC, 7.0 + rng.uniform(-0.25, 0.25), a)
                shrub(p[0], p[1], G + 0.42, rng.uniform(0.45, 0.7))
        rail_arc(RC, SP_OUT + 0.12, G, rel(14), rel(346), step=12)                              # round the stair well
        # galleries (L1, L2) and the Observation Balcony (OBS) with engineered bronze brackets
        for z in (L1, L2):
            annulus("marble_warm", RC, R_IN + 0.02, 8.5, z - 0.4, z, segs=96)
            annulus("bronze", RC, 8.55, 8.45, z - 0.55, z - 0.05, segs=96)
            for k in range(24):
                a = k * 15 + 7.5
                with at((RC[0], RC[1], 0), radians(a)):
                    prism_frame("bronze_dark", [(8.6, z - 0.4), (11.95, z - 0.4), (11.95, z - 1.6)], (0, -0.1, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), 0.2)
            rail_arc(RC, 8.65, z, rel(7), rel(353), step=12)
            # radial bridge from the spiral to the gallery
            annulus("marble_warm", RC, 8.52, SP_OUT - 0.02, z - 0.4, z, rel(-7), rel(7), segs=2)
            for s in (-1, 1):
                for r0_, r1_ in ((SP_OUT, 8.5),):
                    pa = polar(RC, r0_, rel(s * 7), z + 1.05)
                    pb = polar(RC, r1_, rel(s * 7), z + 1.05)
                    tube("bronze", pa, pb, 0.05, 0.05, 6)
                    for t in (0.0, 0.5, 1.0):
                        p = v_add(pa, v_mul(v_sub(pb, pa), t))
                        box("bronze", (p[0], p[1], z + 0.52), (0.1, 0.1, 1.05))
        annulus("marble_warm", RC, 13.8, 8.5, OBS - 0.4, OBS, segs=96)
        annulus("marble_dark", RC, 11.15, 10.85, OBS, OBS + 0.03, segs=96)
        rail_arc(RC, 13.65, OBS, 0, 360, step=10)
        rail_arc(RC, 8.65, OBS, rel(7), rel(353), step=12)
        annulus("marble_warm", RC, 8.52, SP_OUT - 0.02, OBS - 0.4, OBS, rel(-7), rel(7), segs=2)
        annulus("marble_warm", RC, SP_OUT, TRUNK_R + 0.08, OBS - 0.4, OBS, rel(-9), rel(75), segs=10)    # top landing
        rail_arc(RC, SP_OUT - 0.12, OBS, rel(9), rel(75), step=12)


def build_spiral():
    with part("Spiral_Stair", "04_Garden_Atrium"):
        # up: 60 steps round the trunk (one turn per floor) - solid near the floor, floating treads above
        for k in range(1, 60):
            top = G + k * UP_RISE
            a = rel(SP_STEP_DEG * k)
            bot = top - 0.35
            annulus("marble_white", RC, SP_OUT, SP_IN, bot, top, a - 9.2, a + 9.2, segs=2)
            p = polar(RC, SP_OUT - 0.02, a - 9.0)
            box("bronze", (p[0], p[1], top - 0.02), (0.08, 0.08, 0.08))
        # down: 19 steps into the Hidden Undercroft
        for j in range(1, 20):
            top = G - j * DN_RISE
            a = rel(-SP_STEP_DEG * j)
            annulus("marble_dark", RC, SP_OUT, SP_IN, top - 0.35, top, a - 9.2, a + 9.2, segs=2)
        # helical bronze handrails (outer edge), up and down
        for ka, kb in ((1, 19), (21, 39), (41, 59)):                     # open where the bridges leave the stair
            up = [polar(RC, SP_OUT - 0.1, rel(SP_STEP_DEG * k), G + k * UP_RISE + 1.0) for k in range(ka, kb + 1)]
            path_tube("bronze", up, [0.05] * len(up), segs=6)
        for k in range(1, 60, 2):
            p = polar(RC, SP_OUT - 0.1, rel(SP_STEP_DEG * k), G + k * UP_RISE)
            box("bronze", (p[0], p[1], p[2] + 0.5), (0.08, 0.08, 1.0))
        dn = [polar(RC, SP_OUT - 0.1, rel(-SP_STEP_DEG * j), G - j * DN_RISE + 1.0) for j in range(1, 20)]
        path_tube("bronze", dn, [0.05] * len(dn), segs=6)
        for j in range(1, 20, 2):
            p = polar(RC, SP_OUT - 0.1, rel(-SP_STEP_DEG * j), G - j * DN_RISE)
            box("bronze", (p[0], p[1], p[2] + 0.5), (0.08, 0.08, 1.0))


# ---------------------------------------------------------------- the sacred tree
TREE_TOP = OBS + 11.0


def build_tree():
    cx, cy = RC
    with part("Sacred_Tree_Trunk", "09_Sacred_Tree"):
        prof = [(U - 0.3, 3.7), (U + 0.6, 3.25), (U + 1.6, 3.05), (G, 3.0), (G + 8, 2.95), (G + 16, 2.85), (OBS, 2.75),
                (OBS + 4, 2.5), (TREE_TOP, 1.9)]
        pts = [(cx + 0.15 * sin(z * 0.3), cy + 0.12 * cos(z * 0.23), z) for z, r in prof]
        path_tube("bark", pts, [r for z, r in prof], segs=18)
        # bark ridges (kept tight to the trunk so they never reach the stair)
        for k in range(9):
            a = tau * k / 9 + 0.2
            ridge = []
            for z in [U + 1.0 + i * 1.6 for i in range(int((TREE_TOP - U - 2) / 1.6))]:
                r = 2.85 if z < OBS else 2.55
                wob = 0.12 * sin(z * 0.7 + k)
                ridge.append((cx + r * cos(a + wob * 0.2), cy + r * sin(a + wob * 0.2), z))
            path_tube("bark", ridge, [0.3] * len(ridge), segs=5)
    with part("Sacred_Tree_Branches", "09_Sacred_Tree"):
        ENDS = []
        for k in range(7):
            a = tau * k / 7 + 0.35
            reach = rng.uniform(19, 26)
            z0 = OBS + 5.6 + (k % 3) * 1.0
            pts = []
            for t in (0.0, 0.25, 0.5, 0.75, 1.0):
                r = 2.0 + reach * t
                z = z0 + 10.0 * sin(t * pi * 0.62) + 4.0 * t
                if 7.0 < r < 15.0:
                    z = max(z, OBS + 6.2)
                pts.append((cx + r * cos(a + 0.18 * t), cy + r * sin(a + 0.18 * t), z))
            path_tube("bark", pts, [1.25, 0.95, 0.7, 0.45, 0.25], segs=10)
            ENDS.append(pts)
            for s in (-1, 1):                                                   # sub-branches
                p0 = pts[2]
                tgt = (p0[0] + 7 * cos(a + s * 0.7), p0[1] + 7 * sin(a + s * 0.7), p0[2] + 5)
                path_tube("bark", [p0, v_mul(v_add(p0, tgt), 0.5), tgt], [0.45, 0.32, 0.15], segs=7)
                ENDS.append([p0, tgt])
        for k in range(3):                                                      # crown leaders
            a = tau * k / 3
            p = [(cx, cy, TREE_TOP - 1), (cx + 2 * cos(a), cy + 2 * sin(a), TREE_TOP + 5), (cx + 4 * cos(a), cy + 4 * sin(a), TREE_TOP + 9)]
            path_tube("bark", p, [1.0, 0.6, 0.25], segs=8)
            ENDS.append(p)
    with part("Sacred_Tree_Canopy", "09_Sacred_Tree"):
        for pts in ENDS:
            for i, p in enumerate(pts[1:]):
                n = 2 if i < len(pts) - 2 else 4
                for _ in range(n):
                    r = rng.uniform(2.6, 4.6)
                    c = (p[0] + rng.uniform(-2.5, 2.5), p[1] + rng.uniform(-2.5, 2.5), p[2] + rng.uniform(0.5, 2.5))
                    rr = math.hypot(c[0] - cx, c[1] - cy)
                    if rr < 15.5:
                        c = (c[0], c[1], max(c[2], OBS + 5.6 + r * 0.6))                # keep the balcony clear
                    blob(rng.choice(["leaf_dark", "leaf_mid", "leaf_mid", "leaf_light"]), c, (r, r, r * 0.72),
                         segs=9, rings=6, jitter=0.16)
        for _ in range(14):                                                     # crown mass
            a, rr = rng.uniform(0, tau), rng.uniform(0, 8)
            r = rng.uniform(4, 6)
            blob(rng.choice(["leaf_dark", "leaf_mid"]), (cx + rr * cos(a), cy + rr * sin(a), TREE_TOP + rng.uniform(3, 9)),
                 (r, r, r * 0.75), segs=10, rings=6, jitter=0.15)
    build_roots()


def root_path(pts, r0, r1, mat="root", segs=8):
    n = len(pts)
    path_tube(mat, pts, [r0 + (r1 - r0) * i / (n - 1) for i in range(n)], segs=segs)


def build_roots():
    cx, cy = RC
    with part("Sacred_Tree_Roots", "09_Sacred_Tree"):
        # --- roots that arch over the Observation Balcony and pour down the outside of the building
        drapes = [
            # (angle, path down the outside after the arch)
            (-100, [(-2.6, -9.6, L2 + 0.35), (-3.6, -15.0, L2 + 0.3), (-4.4, -21.0, L2 + 0.5), (-4.6, -22.6, L2 - 1.0),
                    (-4.6, -22.75, G + 6.0), (-4.5, -22.7, G + 0.3)]),
            (-80, [(2.6, -9.6, L2 + 0.35), (3.4, -15.5, L2 + 0.3), (4.4, -21.0, L2 + 0.5), (4.6, -22.6, L2 - 1.0),
                   (4.6, -22.75, G + 7.0), (4.5, -22.7, G + 0.3)]),
            (165, [(-14.6, 7.9, G + 8.6), (-17.0, 8.6, G + 12.5), (-20.0, 8.3, G + 14.0)]),
            (196, [(-14.6, 0.5, G + 8.6), (-17.5, -1.0, G + 13.2)]),
            (12, [(14.6, 7.5, G + 3.0), (15.6, 8.6, G + 1.2)]),
            (-14, [(14.4, 0.0, G + 4.0), (15.0, -0.8, G + 1.2)]),
            (112, [(-5.0, 18.0, L2 + 0.4), (-7.0, 22.0, L2 + 0.35), (-8.4, 26.0, L2 + 0.45)]),
        ]
        for ang, tail in drapes:
            a = radians(ang)
            arch = [(cx + 2.2 * cos(a), cy + 2.2 * sin(a), OBS + 6.2), (cx + 8.0 * cos(a), cy + 8.0 * sin(a), OBS + 7.3),
                    (cx + 13.6 * cos(a), cy + 13.6 * sin(a), OBS + 6.6), (cx + 15.4 * cos(a), cy + 15.4 * sin(a), OBS + 2.8),
                    (cx + 14.6 * cos(a), cy + 14.6 * sin(a), OBS - 2.0)]
            # follow the drum down to where the tail starts
            first = tail[0]
            mid = (cx + 14.3 * cos(a), cy + 14.3 * sin(a), (OBS - 2.0 + first[2]) / 2)
            pts = arch + [mid] + tail
            root_path(pts, 1.35, 0.3, segs=9)
            # flowering vines ride along the big roots
            for i in range(3, len(pts) - 1):
                leafy(pts[i], 0.7)
        # --- roots climbing the inside of the drum (from the undercroft, up between the windows)
        for ang in (45, 135, 225, 315):
            pts = []
            for i, z in enumerate([G - 0.6, G + 1.5, G + 3.0, G + 4.5, G + 5.6]):
                a = radians(ang + 2.5 * sin(i * 1.3))
                pts.append((cx + 11.55 * cos(a), cy + 11.55 * sin(a), z))
            root_path(pts, 0.42, 0.18)
            for z in (L1 + 0.5, L1 + 3.0, L2 + 0.5, L2 + 3.0):                    # ivy higher up the wall
                a = radians(ang + rng.uniform(-3, 3))
                leafy((cx + 11.9 * cos(a), cy + 11.9 * sin(a), z), 0.32)
        # --- the undercroft: the trunk's great buttress roots
        for k in range(10):
            ang = 55 + k * 22.0                     # stays out of the sector where the last stair steps come down
            if ang > 278:
                continue
            a = radians(ang)
            pts = [(cx + 3.0 * cos(a), cy + 3.0 * sin(a), U + 1.8), (cx + 4.2 * cos(a), cy + 4.2 * sin(a), U + 0.6),
                   (cx + 5.4 * cos(a), cy + 5.4 * sin(a), U + 0.05), (cx + 5.9 * cos(a), cy + 5.9 * sin(a), U - 0.6)]
            root_path(pts, 0.85, 0.4)
        for k in range(12):                         # roots crawling across the ceiling and down the walls
            ang = 15 + k * 30
            a = radians(ang)
            z_c = G - 1.0
            pts = [(cx + 6.2 * cos(a), cy + 6.2 * sin(a), G - 0.55), (cx + 7.5 * cos(a), cy + 7.5 * sin(a), z_c),
                   (cx + 9.5 * cos(a + 0.03), cy + 9.5 * sin(a + 0.03), z_c - 0.1),
                   (cx + 11.55 * cos(a), cy + 11.55 * sin(a), z_c - 0.6), (cx + 11.6 * cos(a), cy + 11.6 * sin(a), U + 2.2),
                   (cx + 11.4 * cos(a), cy + 11.4 * sin(a), U - 0.2)]
            root_path(pts, 0.32, 0.22, segs=6)
        # hanging rootlets
        for k in range(26):
            a = rng.uniform(0, tau)
            r = rng.uniform(6.5, 11.0)
            if min(abs(((math.degrees(a) - d + 180) % 360) - 180) for d in (0, 90, 180)) < 12:
                continue
            p = (cx + r * cos(a), cy + r * sin(a), G - 0.6)
            q = (p[0] + 0.2, p[1], G - rng.uniform(1.0, 1.4))
            tube("root", p, q, 0.06, 0.015, 5, caps=False)


def leafy(p, s):
    for _ in range(3):
        blob(rng.choice(["leaf_dark", "leaf_mid", "leaf_light"]), (p[0] + rng.uniform(-s, s), p[1] + rng.uniform(-s, s), p[2] + rng.uniform(-s, s)),
             s * rng.uniform(0.5, 0.8), segs=5, rings=3, jitter=0.15)
    if rng.random() < 0.6:
        blob(rng.choice(["flower_pink", "flower_purple", "flower_white"]), (p[0], p[1], p[2] + s * 0.6), 0.14, segs=4, rings=3)


# ---------------------------------------------------------------- the Hidden Undercroft and the secret vaults
def build_undercroft():
    cx, cy = RC
    with part("Undercroft", "08_Undercroft_Vaults"):
        frustum("marble_dark", (cx, cy, U - 0.4), R_IN, R_IN, 0.4, 90, smooth=False)
        annulus("gold", RC, 9.2, 9.0, U, U + 0.03, segs=64)
        annulus("slate", RC, 12.0, 11.2, U, U + 0.03, segs=64)
        # engineered ceiling ribs (Hephaestus holding up Hades' hall)
        for k in range(12):
            a = k * 30
            p0, p1 = polar(RC, SP_OUT + 0.3, a, G - 0.75), polar(RC, R_IN - 0.05, a, G - 0.75)
            box("bronze_dark", ((p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2, G - 0.75), (math.dist(p0[:2], p1[:2]), 0.35, 0.5), rz=radians(a))
        annulus("bronze_dark", RC, SP_OUT + 0.4, SP_OUT + 0.05, G - 1.0, G - 0.5, segs=48)
        # remembrance niches: dark frames, memorial plaques, candles
        for a in (45, 135, 225, 270, 315):
            with at((cx, cy, 0), radians(a)):
                x = R_IN - 0.1
                box("marble_dark", (x, 0, U + 2.0), (0.2, 2.6, 3.2))
                box("bronze", (x - 0.12, 0, U + 3.75), (0.2, 2.9, 0.3))
                box("bronze_dark", (x - 0.14, 0, U + 1.6), (0.06, 1.4, 0.8))
                box("stone_light", (x - 0.45, 0, U + 0.5), (0.7, 2.4, 1.0), ch=0.03)
                for dy in (-0.8, -0.3, 0.3, 0.8):
                    frustum("cream", (x - 0.45, dy, U + 1.0), 0.05, 0.05, 0.2 + 0.1 * abs(dy), 6)
                    blob("candle", (x - 0.45, dy, U + 1.3 + 0.1 * abs(dy)), (0.04, 0.04, 0.07), segs=4, rings=3)
                light("Undercroft_Candles_%d" % a, (cx + (x - 1.0) * cos(radians(a)), cy + (x - 1.0) * sin(radians(a)), U + 1.6), 60, (1.0, 0.7, 0.4))
        # spirit-light crystals in the walls (teal glow)
        for k in range(10):
            a = 18 + k * 36
            if min(abs(((a - d + 180) % 360) - 180) for d in (0, 90, 180)) < 15:
                a += 18
            p = polar(RC, R_IN - 0.05, a, U + rng.uniform(3.0, 4.6))
            blob("spirit", p, (0.18, 0.18, 0.32), segs=5, rings=3, jitter=0.2)
        light("Undercroft_Spirit", (cx, cy + 8.0, U + 3.6), 180, (0.5, 0.8, 1.0), size=2.0)
    with part("Secret_Vaults", "08_Undercroft_Vaults"):
        for ang, name in ((0, "East"), (90, "North"), (180, "West")):
            with at((cx, cy, 0), radians(ang)):
                x0, x1 = R_OUT - 0.2, 21.0
                box2("marble_dark", R_IN - 0.25, -2.0, U - 0.4, x1, 2.0, U)                                     # tunnel floor
                box2("stone_old", x0, -2.6, U - 0.4, x1, -2.0, U + 4.95)                               # walls
                box2("stone_old", x0, 2.0, U - 0.4, x1, 2.6, U + 4.95)
                box2("stone_old", x0, -2.6, U + 4.7, x1, 2.6, U + 4.95)                                # ceiling
                for x in (16.0, 19.0):
                    box2("bronze_dark", x - 0.2, -2.6, U + 4.7, x + 0.2, -2.0, U + 4.9)                # iron straps on the walls
                    box2("bronze_dark", x - 0.2, 2.0, U + 4.7, x + 0.2, 2.6, U + 4.9)
                # the vault: 9 x 9 chamber, round forged door standing open
                X0, X1 = 21.0, 30.0
                box2("marble_dark", X0, -4.5, U - 0.4, X1, 4.5, U)
                for (a_, b_, c_, d_) in ((X0, -5.1, X1 + 0.6, -4.5), (X0, 4.5, X1 + 0.6, 5.1), (X1, -4.5, X1 + 0.6, 4.5)):
                    box2("stone_old", a_, b_, U - 0.4, c_, d_, U + 4.95)
                wall_open("stone_old", "y", -5.1, 5.1, X0 + 0.3, U - 0.4, U + 4.95, 0.6, [(-2.0, 2.0, U - 0.4, U + 4.7)])
                box2("stone_old", X0, -5.1, U + 4.7, X1 + 0.6, 5.1, U + 4.95)
                with at((X0 + 0.95, 3.15, U), -pi / 2):                                                 # the round door, swung open flat to the wall
                    frustum("bronze", (0.0, 0.0, 1.75), 1.45, 1.45, 0.35, 24, axis=(0, 1, 0), smooth=False)
                    frustum("bronze_dark", (0.0, -0.05, 1.75), 0.9, 0.9, 0.45, 18, axis=(0, 1, 0), smooth=False)
                    for k in range(8):
                        aa = tau * k / 8
                        box("gold", (1.15 * cos(aa), -0.1, 1.75 + 1.15 * sin(aa)), (0.24, 0.12, 0.24))
                    for k in range(12):                                                                 # gear teeth on the rim
                        aa = tau * k / 12
                        box("bronze", (1.52 * cos(aa), 0.17, 1.75 + 1.52 * sin(aa)), (0.22, 0.3, 0.22))
                # shelves of scrolls and chests along the side walls
                for sy in (-1, 1):
                    y = sy * 4.0
                    box2("wood_dark", 22.0, y - 0.45 if sy > 0 else y - 0.45, U, 28.5, y + 0.45, U + 0.12)
                    for lvl in range(4):
                        z = U + 0.4 + lvl * 0.85
                        box2("wood_dark", 22.0, y - 0.45, z, 28.5, y + 0.45, z + 0.06)
                        for i in range(9):
                            xx = 22.4 + i * 0.7
                            frustum("parchment", (xx, y - 0.35, z + 0.2), 0.11, 0.11, 0.7, 6, axis=(0, 1, 0))
                    for xx in (22.0, 28.5):
                        box2("wood_dark", xx - 0.06, y - 0.45, U, xx + 0.06, y + 0.45, U + 3.4)
                for x in (23.5, 26.5):
                    box("wood_dark", (x, -2.3, U + 0.35), (1.2, 0.8, 0.7), ch=0.04)
                    box("bronze", (x, -2.3, U + 0.72), (1.25, 0.85, 0.06))
                light("Vault_" + name, (cx + 25.5 * cos(radians(ang)), cy + 25.5 * sin(radians(ang)), U + 3.2), 120, (1.0, 0.75, 0.45))


# ================================================================ THE HALL OF FOUNDERS (south, the front door)
HALL_X = 9.0
HALL_Y0 = -22.0                      # front face of the facade


def drum_y_south(x, r=R_OUT):
    return RC[1] - sqrt(max(0.0, r * r - x * x))


def build_hall():
    x0, x1 = -HALL_X, HALL_X
    yf, yi = HALL_Y0, HALL_Y0 + 1.2            # facade outer / inner faces
    top = L2 + 1.2                             # walls rise above the roof as the terrace parapet
    with part("Hall_of_Founders", "03_Hall_of_Founders"):
        # facade with the great door (6 x 9 m)
        wall_open("marble_warm", "x", x0, x1, (yf + yi) / 2, G, top, 1.2, [(-3.0, 3.0, G - 0.1, G + 9.0)])
        # side walls (meet the drum), tall windows with bronze grilles
        for sx in (-1, 1):
            xc = sx * (HALL_X - 0.4)
            wall_open("marble_warm", "y", yf, drum_y_south(HALL_X), xc, G, top, 0.8,
                      [(-18.6, -16.4, G + 3.0, G + 10.0), (-12.6, -10.4, G + 3.0, G + 10.0)])
            for (ya, yb_) in ((-18.6, -16.4), (-12.6, -10.4)):
                for k in range(5):
                    yy = ya + (yb_ - ya) * (k + 0.5) / 5
                    box("bronze_dark", (xc, yy, G + 6.5), (0.1, 0.08, 7.0))
                for zz in (G + 4.5, G + 6.5, G + 8.5):
                    box("bronze_dark", (xc, (ya + yb_) / 2, zz), (0.1, yb_ - ya, 0.08))
                box("glass", (xc, (ya + yb_) / 2, G + 6.5), (0.04, yb_ - ya, 7.0))
        # roof terrace (cut round the drum) and its coffered ceiling below
        region_minus_disc("marble_warm", rect(x0 + 0.8, yi, x1 - 0.8, drum_y_south(HALL_X - 0.8)), RC, R_OUT, L2 - 0.4, L2, n=72)
        for x in (-6.0, -3.0, 0.0, 3.0, 6.0):
            y_end = drum_y_south(abs(x)) - 0.05
            box2("bronze_dark", x - 0.18, yi, L2 - 0.9, x + 0.18, y_end, L2 - 0.4)
        box2("marble_dark", x0 - 0.05, yf - 0.05, top, x1 + 0.05, yi, top + 0.15)                       # coping (front)
        # floor: the two founders' halves - dark marble (Hades, west) and bronze-lined marble (Hephaestus, east)
        region_minus_disc("marble_dark", rect(x0 + 0.8, yi, -0.12, drum_y_south(0.12)), RC, R_OUT, G, G + 0.02, n=48)
        for x in (1.5, 3.0, 4.5, 6.0, 7.5):
            box2("bronze", x - 0.05, yi, G, x + 0.05, drum_y_south(x) - 0.05, G + 0.02)
        box2("rift_gold", -0.12, yi, G, 0.12, drum_y_south(0.0) - 0.02, G + 0.04)                      # the seam
        # interior pilasters with bronze capitals
        for sx in (-1, 1):
            for y in (-19.6, -14.5, -9.4):
                xi = sx * (HALL_X - 0.8 - 0.2)
                box("marble_white", (xi, y, (G + L2 - 0.95) / 2), (0.4, 0.9, L2 - 0.95 - G))
                box("bronze", (xi, y, L2 - 1.15), (0.5, 1.1, 0.5))
        # chandeliers
        for y in (-17.0, -11.0):
            chandelier(0.0, y, L2 - 0.9, G + 8.0)
    build_hall_facade()
    build_forged_doors()
    # empty pedestals: the two founders, four hero memorials
    pedestal("Founder_Hades", -5.4, -14.5, G, facing=0, size=3.2, height=1.9, theme="hades")
    pedestal("Founder_Hephaestus", 5.4, -14.5, G, facing=180, size=3.2, height=1.9, theme="hephaestus")
    for sx, nm in ((-1, "West"), (1, "East")):
        pedestal("Hero_Memorial_%s_Front" % nm, sx * 7.0, -18.7, G, facing=0 if sx < 0 else 180, size=2.2, height=1.2)
        pedestal("Hero_Memorial_%s_Back" % nm, sx * 7.0, -9.8, G, facing=0 if sx < 0 else 180, size=2.2, height=1.2)
    for sx in (-1, 1):
        brazier(sx * 7.3, -16.3, G, 0.8)
        brazier(sx * 4.6, -10.4, G, 0.8)
    # founders' banners: Hades on the west wall, Hephaestus on the east
    banner(-(HALL_X - 0.8 - 0.12), -14.5, G + 11.6, 2.4, 6.0, rz=pi / 2, kind="hades")
    banner(HALL_X - 0.8 - 0.12, -14.5, G + 11.6, 2.4, 6.0, rz=-pi / 2, kind="hephaestus")


def build_hall_facade():
    yf = HALL_Y0
    with part("Hall_of_Founders_Facade", "03_Hall_of_Founders"):
        for (xa, xb) in ((-HALL_X - 0.2, -3.3), (3.3, HALL_X + 0.2)):                                   # Hades' plinth (open at the door)
            box2("marble_dark", xa, yf - 0.3, G, xb, yf, G + 1.2)
        for x in (-8.6, -4.6, 4.6, 8.6):                                                                # giant pilasters
            box2("marble_white", x - 0.45, yf - 0.35, G + 1.2, x + 0.45, yf, L2 - 0.6)
            box2("bronze", x - 0.6, yf - 0.5, L2 - 0.95, x + 0.6, yf, L2 - 0.6)
            for k in range(4):                                                                          # flutes (proud ribs)
                xx = x - 0.3 + 0.2 * k
                box2("stone_light", xx - 0.03, yf - 0.4, G + 1.4, xx + 0.03, yf - 0.35, L2 - 1.2)
        # bronze door frame (proud of the wall)
        for sx in (-1, 1):
            box2("bronze", sx * 3.0 - 0.3, yf - 0.3, G, sx * 3.0 + 0.3, yf, G + 9.4)
        box2("bronze", -3.6, yf - 0.35, G + 9.0, 3.6, yf, G + 9.6)
        # cornice and gold band at the roof line
        box2("bronze", -HALL_X - 0.3, yf - 0.6, L2 - 0.6, HALL_X + 0.3, yf, L2 - 0.2)
        box2("gold", -HALL_X - 0.3, yf - 0.66, L2 - 0.45, HALL_X + 0.3, yf - 0.6, L2 - 0.35)
        # the crest above the door: the camp bull in bronze on a dark shield, gold rim
        shield = [(0.0, G + 13.0 - 0.6), (1.9, G + 12.0 - 0.2), (1.75, G + 10.6), (0.0, G + 9.75), (-1.75, G + 10.6), (-1.9, G + 12.0 - 0.2)]
        vprism("marble_dark", shield, yf - 0.35, 0.35)
        ring_pts = shield + [shield[0]]
        for a, b in zip(ring_pts[:-1], ring_pts[1:]):
            L = math.dist(a, b)
            ang = math.atan2(b[1] - a[1], b[0] - a[0])
            with at(((a[0] + b[0]) / 2, yf - 0.42, (a[1] + b[1]) / 2)):
                prism_frame("gold", [(-L / 2 - 0.06, -0.07), (L / 2 + 0.06, -0.07), (L / 2 + 0.06, 0.07), (-L / 2 - 0.06, 0.07)],
                            (0, 0, 0), (cos(ang), 0, sin(ang)), (-sin(ang), 0, cos(ang)), (0, 1, 0), 0.07)
        emblem_bull("bronze", 0.0, yf - 0.5, G + 11.25, 1.25, 0.15, eyes="rift_gold")
        # the seam between two worlds: a gold crack from the roof down to the crest
        crack = [(0.0, L2 + 1.2), (0.25, L2 + 0.4), (-0.15, L2 - 0.4), (0.18, G + 12.2), (0.0, G + 11.9)]
        for (xa, za), (xb, zb) in zip(crack[:-1], crack[1:]):
            tube("rift_gold", (xa, yf - 0.38, za), (xb, yf - 0.38, zb), 0.09, 0.09, 5)
        # bronze lanterns either side of the door
        for sx in (-1, 1):
            box("bronze", (sx * 3.9, yf - 0.4, G + 6.0), (0.3, 0.5, 0.3))
            lantern(sx * 3.9, yf - 0.6, G + 6.1)
        light("Hall_Door", (0.0, yf - 3.0, G + 7.0), 600, (1.0, 0.7, 0.4), size=1.5)


def build_forged_doors():
    """Two forged bronze leaves (3 x 9 m) standing open against the inside of the facade."""
    yi = HALL_Y0 + 1.2
    with part("Forged_Doors", "03_Hall_of_Founders"):
        for sx, sym in ((-1, "hades"), (1, "hephaestus")):
            with at((sx * 3.0, yi, G), -sx * pi / 2 * 0.0):
                # leaf turned 90 degrees inward: it runs along +y from the hinge
                x = sx * 0.2
                box2("bronze", x - 0.14, 0.0, 0.02, x + 0.14, 3.0, 9.0)
                for zz in (0.6, 3.0, 6.0, 8.4):                                                          # forged straps
                    box2("bronze_dark", x - 0.2, 0.05, zz - 0.15, x + 0.2, 2.95, zz + 0.15)
                for yy in (0.4, 1.5, 2.6):                                                               # rivets
                    for zz in (0.6, 3.0, 6.0, 8.4):
                        box("gold", (x - sx * 0.22, yy, zz), (0.08, 0.12, 0.12))
                # gear medallion with the founder's sign
                frustum("bronze_dark", (x - sx * 0.16, 1.5, 4.5), 1.05, 1.05, 0.08, 20, axis=(-sx, 0, 0), smooth=False)
                for k in range(14):
                    a = tau * k / 14
                    box("bronze", (x - sx * 0.2, 1.5 + 1.15 * cos(a), 4.5 + 1.15 * sin(a)), (0.1, 0.24, 0.24))
                if sym == "hades":
                    emblem_shape("gold", BIDENT, (x - sx * 0.22, 1.5, 4.5), 0.8, 0.05, 180 if sx > 0 else 0)
                else:
                    emblem_shape("gold", HAMMER, (x - sx * 0.22, 1.5, 4.5), 0.8, 0.05, 180 if sx > 0 else 0)


def chandelier(x, y, z_ceiling, z):
    tube("bronze_dark", (x, y, z_ceiling), (x, y, z + 0.2), 0.04, 0.04, 5)
    annulus("bronze", (x, y), 1.6, 1.45, z, z + 0.12, segs=24)
    annulus("bronze", (x, y), 0.8, 0.7, z + 0.6, z + 0.7, segs=16)
    for k in range(4):
        a = tau * k / 4
        tube("bronze_dark", (x + 1.5 * cos(a), y + 1.5 * sin(a), z + 0.1), (x, y, z + 1.2), 0.03, 0.03, 4)
    for k in range(10):
        a = tau * k / 10
        frustum("cream", (x + 1.52 * cos(a), y + 1.52 * sin(a), z + 0.12), 0.05, 0.05, 0.25, 5)
        blob("candle", (x + 1.52 * cos(a), y + 1.52 * sin(a), z + 0.45), (0.05, 0.05, 0.09), segs=4, rings=3)
    light("Chandelier_%.0f_%.0f" % (x, y), (x, y, z - 0.3), 250, (1.0, 0.72, 0.45), size=1.2)


# ================================================================ THE TEMPLE: GRAND ASSEMBLY HALL (east)
# A Doric peripteral temple in the manner of the Temple of Hephaestus in Athens: 6 x 11 fluted columns,
# triglyph-and-metope frieze (bronze metopes), a dark slate pediment with the hearth-flame medallion.
TX0, TX1, TY0, TY1 = 15.0, 41.0, -24.0, 20.0
T = G + 1.2                                   # temple floor (top of the stylobate)
COL_H, COL_R0, COL_R1 = 9.0, 0.85, 0.68
COLS_X = [16.6 + 4.56 * k for k in range(6)]
COLS_Y = [-22.4 + 4.08 * k for k in range(11)]
ENT0 = T + 10.0                               # underside of the architrave
CORNICE = T + 13.1
RIDGE = CORNICE + 3.0
CELLA = (18.6, -16.0, 37.4, 16.0)             # cella outer walls (pronaos walls run on to y = -19.6)


def fluted_column(x, y, z, h=COL_H, r0=COL_R0, r1=COL_R1, flutes=20):
    n = flutes * 2
    rows = [0.0, 0.3, 0.62, 1.0]
    V, F = [], []
    for t in rows:
        r = r0 + (r1 - r0) * t + 0.03 * sin(pi * t)              # entasis
        for k in range(n):
            a = tau * k / n
            rr = r * (1.0 if k % 2 == 0 else 0.93)
            V.append((x + rr * cos(a), y + rr * sin(a), z + h * t))
    for i in range(len(rows) - 1):
        for k in range(n):
            k2 = (k + 1) % n
            F.append((i * n + k, i * n + k2, (i + 1) * n + k2, (i + 1) * n + k))
    emit("marble_white", V, F, True)
    frustum("marble_white", (x, y, z + h), r1 * 1.02, r1 * 1.45, 0.55, 20)              # echinus
    box("marble_white", (x, y, z + h + 0.775), (2.1, 2.1, 0.45), ch=0.03)              # abacus
    annulus("bronze", (x, y), r1 * 1.05, r1 * 0.98, z + h - 0.25, z + h - 0.12, segs=20)  # bronze necking ring


def build_temple():
    with part("Temple_Base", "05_Temple_Assembly_Hall"):
        box2("marble_white", TX0, TY0, G, TX1, TY1, T, ch=0.02)                                    # stylobate
        box2("marble_dark", TX0 - 0.02, TY0 - 0.02, G + 0.25, TX1 + 0.02, TY1 + 0.02, G + 0.35)     # dark band (proud)
        for k in range(1, 4):                                                                      # 3 steps S, E, N
            top = G + 0.4 * k
            d = 0.6 * (3 - k) + 0.6
            box2("marble_white", TX0 + 0.0, TY0 - d, G, TX1 + d, TY0 - d + 0.6, top)
            box2("marble_white", TX1 + d - 0.6, TY0 - d, G, TX1 + d, TY1 + d, top)
            box2("marble_white", TX0, TY1 + d - 0.6, G, TX1 + d, TY1 + d, top)
            box2("marble_white", TX0 - d, 1.4, G, TX0 - d + 0.6, 6.8, top)                        # west steps (to the atrium)
    with part("Temple_Columns", "05_Temple_Assembly_Hall"):
        for x in COLS_X:
            for y in (COLS_Y[0], COLS_Y[-1]):
                fluted_column(x, y, T)
        for y in COLS_Y[1:-1]:
            for x in (COLS_X[0], COLS_X[-1]):
                fluted_column(x, y, T)
        for x in (24.2, 31.8):                                                                    # in antis
            fluted_column(x, -19.4, T, h=COL_H, r0=0.7, r1=0.58)
    with part("Temple_Entablature", "05_Temple_Assembly_Hall"):
        ax0, ay0, ax1, ay1 = COLS_X[0] - 1.05, COLS_Y[0] - 1.05, COLS_X[-1] + 1.05, COLS_Y[-1] + 1.05
        w = 2.1
        for (a, b, c_, d_) in ((ax0, ay0, ax1, ay0 + w), (ax0, ay1 - w, ax1, ay1), (ax0, ay0 + w, ax0 + w, ay1 - w), (ax1 - w, ay0 + w, ax1, ay1 - w)):
            box2("marble_warm", a, b, ENT0, c_, d_, ENT0 + 1.3)                                    # architrave
            box2("marble_warm", a, b, ENT0 + 1.3, c_, d_, ENT0 + 2.6)                                # frieze
        for (a, b, c_, d_) in ((ax0 - 0.04, ay0 - 0.04, ax1 + 0.04, ay0), (ax0 - 0.04, ay1, ax1 + 0.04, ay1 + 0.04),
                               (ax0 - 0.04, ay0, ax0, ay1), (ax1, ay0, ax1 + 0.04, ay1)):
            box2("gold", a, b, ENT0 + 1.16, c_, d_, ENT0 + 1.28)                                  # taenia (gold), outside only
        # triglyphs (dark) and bronze metopes on all four faces
        def frieze_face(p0, p1, normal):
            L = math.dist(p0, p1)
            n = int(L / 1.14)
            ux, uy = (p1[0] - p0[0]) / L, (p1[1] - p0[1]) / L
            for i in range(n + 1):
                t = i * L / n
                cx_, cy_ = p0[0] + ux * t + normal[0] * 0.06, p0[1] + uy * t + normal[1] * 0.06
                box("marble_dark", (cx_, cy_, ENT0 + 1.95), (0.55, 0.12, 1.3), rz=math.atan2(uy, ux))
                if i < n:
                    mx, my = p0[0] + ux * (t + L / n / 2) + normal[0] * 0.03, p0[1] + uy * (t + L / n / 2) + normal[1] * 0.03
                    box("bronze", (mx, my, ENT0 + 1.95), (0.5, 0.06, 0.95), rz=math.atan2(uy, ux))
        frieze_face((ax0, ay0), (ax1, ay0), (0, -1))
        frieze_face((ax0, ay1), (ax1, ay1), (0, 1))
        frieze_face((ax0, ay0), (ax0, ay1), (-1, 0))
        frieze_face((ax1, ay0), (ax1, ay1), (1, 0))
        box2("marble_white", TX0, TY0, ENT0 + 2.6, TX1, TY1, CORNICE)                              # cornice (overhangs)
        box2("bronze", TX0 - 0.03, TY0 - 0.03, CORNICE - 0.18, TX1 + 0.03, TY1 + 0.03, CORNICE - 0.08)
        # ceilings: cella + peristyle (coffered with bronze beams)
        box2("marble_warm", ax0 + w, ay0 + w, ENT0 + 0.0, ax1 - w, ay1 - w, ENT0 + 0.4)
        for y in [ay0 + w + 1.5 + 3.0 * k for k in range(13)]:
            if y < ay1 - w - 0.5:
                box2("bronze_dark", ax0 + w, y - 0.15, ENT0 - 0.3, ax1 - w, y + 0.15, ENT0)
    with part("Temple_Roof", "05_Temple_Assembly_Hall"):
        xm = (TX0 + TX1) / 2
        # attic mass (the pediments are its ends, set back behind the raking cornices)
        prism_frame("marble_warm", [(TX0 + 0.3, CORNICE), (TX1 - 0.3, CORNICE), (xm, RIDGE - 0.15)], (0, TY0 + 0.6, 0), (1, 0, 0), (0, 0, 1), (0, 1, 0), (TY1 - 0.6) - (TY0 + 0.6))
        # roof slopes with tile ribs (marble tiles)
        slope = math.atan2(RIDGE - CORNICE, xm - TX0)
        for side in (-1, 1):
            xe = TX0 if side < 0 else TX1
            p0 = (xe - side * 0.0, CORNICE - 0.05)
            p1 = (xm, RIDGE)
            Ls = math.dist(p0, p1)
            u = ((p1[0] - p0[0]) / Ls, 0.0, (p1[1] - p0[1]) / Ls)
            nrm = (side * u[2], 0.0, -side * u[0])                     # outward (up and away from the ridge)
            o = (p0[0] - u[0] * 0.5, TY0 - 0.5, p0[1] - u[2] * 0.5)
            prism_frame("marble_white", [(0, 0), (Ls + 0.55, 0), (Ls + 0.55, TY1 - TY0 + 1.0), (0, TY1 - TY0 + 1.0)],
                        o, u, (0, 1, 0), nrm, 0.3)
            # cover-tile ribs
            y = TY0 - 0.2
            while y < TY1 + 0.3:
                a = v_add(o, v_add(v_mul(u, 0.1), (0, y - (TY0 - 0.5), 0)))
                b = v_add(o, v_add(v_mul(u, Ls + 0.4), (0, y - (TY0 - 0.5), 0)))
                tube("marble_warm", v_add(a, v_mul(nrm, 0.32)), v_add(b, v_mul(nrm, 0.32)), 0.09, 0.09, 5, smooth=True)
                y += 0.8
        box2("marble_white", xm - 0.35, TY0 - 0.5, RIDGE - 0.1, xm + 0.35, TY1 + 0.5, RIDGE + 0.45)    # ridge
        # pediments: dark slate tympanum inside raking cornices; hearth-flame medallion (front), bident + hammer (back)
        for (yfc, sgn) in ((TY0 + 0.6, -1), (TY1 - 0.6, 1)):
            tri = [(TX0 + 1.2, CORNICE + 0.25), (TX1 - 1.2, CORNICE + 0.25), (xm, RIDGE - 0.75)]
            if sgn < 0:
                vprism("slate", tri, yfc - 0.05, 0.05)
            else:
                vprism("slate", tri, yfc, 0.05)
            for (a, b) in (((TX0 - 0.1, CORNICE), (xm, RIDGE + 0.15)), ((xm, RIDGE + 0.15), (TX1 + 0.1, CORNICE))):
                L = math.dist(a, b)
                ang = math.atan2(b[1] - a[1], b[0] - a[0])
                yy = TY0 - 0.5 if sgn < 0 else TY1 - 0.6
                prism_frame("marble_white", [(-0.2, -0.45), (L + 0.2, -0.45), (L + 0.2, 0.15), (-0.2, 0.15)],
                            (a[0], yy, a[1]), (cos(ang), 0, sin(ang)), (-sin(ang), 0, cos(ang)), (0, 1, 0), 1.1)
            zc = CORNICE + 1.15
            yfront = (yfc - 0.05) if sgn < 0 else (yfc + 0.05)
            fdeg = -90 if sgn < 0 else 90
            medallion_ring(xm, yfront, zc, 1.0, fdeg)
            if sgn < 0:
                emblem_shape("gold", FLAME, (xm, yfront + sgn * 0.08, zc), 0.85, 0.08, fdeg)
                emblem_shape("bronze", HAMMER, (xm - 6.0, yfront + sgn * 0.05, zc - 0.25), 0.7, 0.06, fdeg)
                emblem_shape("bronze", BIDENT, (xm + 6.0, yfront + sgn * 0.05, zc - 0.25), 0.7, 0.06, fdeg)
            else:
                emblem_bull("bronze", xm, yfront + 0.08, zc, 0.8, 0.08, facing=90)
            for (ax_, az_) in ((TX0 - 0.1, CORNICE), (TX1 + 0.1, CORNICE), (xm, RIDGE + 0.2)):           # acroteria
                emblem_shape("bronze", PALMETTE, (ax_, (TY0 - 0.2) if sgn < 0 else (TY1 + 0.2), az_ + 0.55), 0.7, 0.15, fdeg)
    with part("Temple_Cella", "05_Temple_Assembly_Hall"):
        cx0, cy0, cx1, cy1 = CELLA
        t_ = 0.9
        wall_open("marble_warm", "x", cx0, cx1, cy0 + t_ / 2, T, ENT0, t_, [(25.5, 30.5, T - 0.1, T + 8.0)])      # door wall
        wall_open("marble_warm", "x", cx0, cx1, cy1 - t_ / 2, T, ENT0, t_)
        wall_open("marble_warm", "y", -19.6, cy1, cx0 + t_ / 2, T, ENT0, t_, [(2.0, 6.2, T - 0.1, T + 6.0)])     # west door
        wall_open("marble_warm", "y", -19.6, cy1, cx1 - t_ / 2, T, ENT0, t_)
        for (x, y0_) in ((cx0, -19.6), (cx1, -19.6)):                                                          # antae caps
            box("bronze", (x + (t_ / 2 if x == cx0 else -t_ / 2), y0_ + 0.3, ENT0 - 0.4), (1.1, 0.7, 0.5))
        box2("bronze", 25.2, cy0 - 0.08, T, 25.5, cy0 + t_ + 0.08, T + 8.3)                                    # door frame
        box2("bronze", 30.5, cy0 - 0.08, T, 30.8, cy0 + t_ + 0.08, T + 8.3)
        box2("bronze", 25.2, cy0 - 0.1, T + 8.0, 30.8, cy0 + t_ + 0.1, T + 8.5)
        # interior: gold-ringed floor, rows of benches, the dais
        annulus("gold", (28.0, -2.0), 4.1, 3.9, T, T + 0.03, segs=48)
        annulus("marble_dark", (28.0, -2.0), 3.0, 2.5, T, T + 0.03, segs=48)
        for y in (-11.5, -9.0, -6.5, 2.5, 5.0, 7.5):
            for (xa, xb) in ((20.4, 25.6), (30.4, 35.6)):
                box2("marble_white", xa, y - 0.35, T, xb, y + 0.35, T + 0.48, ch=0.03)
                box2("wood_light", xa + 0.05, y - 0.3, T + 0.48, xb - 0.05, y + 0.3, T + 0.56)
        for k in range(3):                                                                                     # the dais
            box2("marble_white", 20.0 + k * 0.6, 10.8 + k * 0.6, T, 36.0 - k * 0.6, cy1 - t_, T + 0.25 * (k + 1), ch=0.02)
        box("bronze", (28.0, 13.6, T + 0.75 + 0.6), (1.2, 0.7, 1.2), ch=0.05)                                 # lectern
        for x in (20.6, 35.4):
            for y in ((-12.0, -4.0, 9.5, 13.5) if x < 28 else (-12.0, -4.0, 4.0, 12.0)):
                box("marble_white", (19.75 if x < 28 else 36.25, y, (T + ENT0) / 2), (0.5, 1.0, ENT0 - T))
        for y in (-10.0, -2.0, 6.0):
            chandelier(28.0, y, ENT0, T + 6.5)
    pedestal("Assembly_Dais_West", 23.0, 13.55, T + 0.75, facing=-90, size=2.4, height=1.3, theme="hephaestus")
    pedestal("Assembly_Dais_East", 33.0, 13.55, T + 0.75, facing=-90, size=2.4, height=1.3, theme="hephaestus")
    pedestal("Temple_Pronaos_West", 21.0, -18.0, T, facing=-90, size=2.2, height=1.2)
    pedestal("Temple_Pronaos_East", 35.0, -18.0, T, facing=-90, size=2.2, height=1.2)
    for x in (21.2, 34.8):
        brazier(x, -20.6, T, 0.8)
    # maroon camp banners hung between the front columns (high: 5 m clear underneath)
    for i in range(5):
        x = (COLS_X[i] + COLS_X[i + 1]) / 2
        banner(x, COLS_Y[0], ENT0 - 0.2, 1.7, 4.6, rz=0.0, kind="bull")
    for y in (-8.0, 0.0, 8.0):
        banner(CELLA[2] - 1.02, y, ENT0 - 1.0, 1.6, 4.0, rz=-pi / 2, kind="bull")
    # vines woven round the columns nearest the atrium (the two worlds meeting)
    with part("Temple_Vines", "10_Greenery"):
        for y in COLS_Y[3:6] + COLS_Y[8:9]:
            spiral_vine(COLS_X[0], y, T, COL_R0 + 0.12, COL_H - 0.5, turns=2.5)
        for x in COLS_X[:2]:
            spiral_vine(x, COLS_Y[0], T, COL_R0 + 0.12, COL_H - 1.5, turns=2.0)


def medallion_ring(x, y, z, r, facing_deg):
    f = (cos(radians(facing_deg)), sin(radians(facing_deg)), 0.0)
    frustum("slate", (x, y, z), r * 0.92, r * 0.92, 0.06, 28, axis=f, smooth=False)
    pts_o = [(r * cos(tau * i / 28), r * sin(tau * i / 28)) for i in range(28)]
    for i in range(28):
        a0, a1 = tau * i / 28, tau * (i + 1) / 28
        q = [(r * cos(a0), r * sin(a0)), (r * cos(a1), r * sin(a1)), (r * 0.86 * cos(a1), r * 0.86 * sin(a1)), (r * 0.86 * cos(a0), r * 0.86 * sin(a0))]
        emblem_shape("gold", q, (x, y, z), 1.0, 0.12, facing_deg)


# ================================================================ THE GREENHOUSE: LIBRARY AND ARCHIVES (west)
GX0, GX1, GY0, GY1 = -42.0, -14.6, -20.0, 20.0
G_EAVE, G_RISE = G + 8.0, 7.0
GXC, G_HALF = (GX0 + GX1) / 2, (GX1 - GX0) / 2
G_TREE = (GXC, -2.0)
BAY = 4.0
PROFILE_N = 14


def gh_profile():
    return [(GXC + G_HALF * cos(pi * i / PROFILE_N), G_EAVE + G_RISE * sin(pi * i / PROFILE_N)) for i in range(PROFILE_N + 1)]


def pane(mat, a, b, y0, y1, t=0.05, out=None):
    """Thin panel between profile points a -> b (x, z), from y0 to y1, thickness t toward `out` (normal)."""
    L = math.dist(a, b)
    u = ((b[0] - a[0]) / L, 0.0, (b[1] - a[1]) / L)
    n = out or (-u[2], 0.0, u[0])
    prism_frame(mat, [(0, 0), (L, 0), (L, y1 - y0), (0, y1 - y0)], (a[0], y0, a[1]), u, (0, 1, 0), n, t)


def build_greenhouse():
    prof = gh_profile()
    with part("Greenhouse_Frame", "06_Greenhouse_Library"):
        # knee wall (ancient dark stone, bronze cap) with doors: south, north, east (to the atrium)
        doors_y = [(-30.8, -25.8, G - 0.1, G + 5.4)]
        wall_open("stone_old", "x", GX0, GX1, GY0 + 0.3, G, G + 1.2, 0.6, doors_y)
        wall_open("stone_old", "x", GX0, GX1, GY1 - 0.3, G, G + 1.2, 0.6, doors_y)
        wall_open("stone_old", "y", GY0 + 0.6, GY1 - 0.6, GX0 + 0.3, G, G + 1.2, 0.6)
        wall_open("stone_old", "y", GY0 + 0.6, GY1 - 0.6, GX1 - 0.3, G, G + 1.2, 0.6, [(1.5, 6.5, G - 0.1, G + 5.4)])
        cap_segments = [((GX0, GY0), (-30.8, GY0)), ((-25.8, GY0), (GX1, GY0)), ((GX0, GY1), (-30.8, GY1)), ((-25.8, GY1), (GX1, GY1)),
                        ((GX0, GY0), (GX0, GY1)), ((GX1, GY0), (GX1, 1.5)), ((GX1, 6.5), (GX1, GY1))]
        for (a, b) in cap_segments:
            wall_xy("bronze", a, b, G + 1.2, G + 1.34, 0.72)
        # glass walls: bronze mullions every 2 m, transoms, glass between
        def glass_wall(axis, a0, a1, c, openings=(), ztop=G_EAVE):
            pos = a0
            while pos < a1 - 1e-3:
                nxt = min(pos + 2.0, a1)
                mid = (pos + nxt) / 2
                z0 = G + 1.34
                for (oa, ob, oz0, oz1) in openings:
                    if oa - 0.01 <= mid <= ob + 0.01:
                        z0 = max(z0, oz1 + 0.15)
                if axis == "x":
                    box2("glass", pos, c - 0.03, z0, nxt, c + 0.03, ztop)
                else:
                    box2("glass", c - 0.03, pos, z0, c + 0.03, nxt, ztop)
                pos = nxt
            pos = a0
            while pos <= a1 + 1e-3:
                if axis == "x":
                    box2("bronze", pos - 0.08, c - 0.12, G + 1.34, pos + 0.08, c + 0.12, ztop)
                else:
                    box2("bronze", c - 0.12, pos - 0.08, G + 1.34, c + 0.12, pos + 0.08, ztop)
                pos += 2.0
            for z in (G + 4.6, ztop - 0.12):
                if axis == "x":
                    box2("bronze", a0, c - 0.1, z - 0.06, a1, c + 0.1, z + 0.06)
                else:
                    box2("bronze", c - 0.1, a0, z - 0.06, c + 0.1, a1, z + 0.06)
        glass_wall("y", GY0 + 0.3, GY1 - 0.3, GX0 + 0.3)
        glass_wall("y", GY0 + 0.3, 1.5, GX1 - 0.3)
        glass_wall("y", 6.5, GY1 - 0.3, GX1 - 0.3)
        for yy in (GY0 + 0.3, GY1 - 0.3):
            glass_wall("x", GX0 + 0.3, -30.8, yy, ztop=G + 5.6)
            glass_wall("x", -25.8, GX1 - 0.3, yy, ztop=G + 5.6)
            box2("bronze", -30.8, yy - 0.12, G + 5.4, -25.8, yy + 0.12, G + 5.6)                     # door head
        # east wall above the atrium door: glass, and the mezzanine door into the drum
        box2("glass", GX1 - 0.33, 1.5, G + 6.15, GX1 - 0.27, 6.5, G_EAVE)
        # door canopies (bronze) and a throat to the drum
        for yy, s in ((GY0, -1), (GY1, 1)):
            box2("bronze", -31.3, yy - (1.6 if s < 0 else 0.0), G + 5.62, -25.3, yy + (1.6 if s > 0 else 0.0), G + 5.82)
        for sy in (-1, 1):
            box2("marble_warm", GX1, 4.0 + sy * 2.6 - 0.3, G, -12.7, 4.0 + sy * 2.6 + 0.3, G + 6.0)            # ground throat walls
        box2("marble_warm", GX1, 1.4, G + 5.5, -12.7, 6.6, G + 6.15)                                      # throat roof
        # the vault: bronze ribs every 4 m, purlins, a ridge lantern
        ys = [GY0 + BAY * i for i in range(int((GY1 - GY0) / BAY) + 1)]
        for y in ys:
            path_tube("bronze", [(x, y, z) for x, z in prof], [0.14] * len(prof), segs=6)
        for (x, z) in prof:
            box2("bronze", x - 0.07, GY0, z - 0.07, x + 0.07, GY1, z + 0.07)
        box2("bronze_dark", GXC - 1.4, GY0 - 0.2, G_EAVE + G_RISE - 0.05, GXC + 1.4, GY1 + 0.2, G_EAVE + G_RISE + 0.12)
        for y in ys:
            for sx in (-1, 1):
                box2("bronze", GXC + sx * 1.3 - 0.06, y - 0.06, G_EAVE + G_RISE, GXC + sx * 1.3 + 0.06, y + 0.06, G_EAVE + G_RISE + 1.0)
        box2("bronze_dark", GXC - 1.6, GY0 - 0.3, G_EAVE + G_RISE + 1.0, GXC + 1.6, GY1 + 0.3, G_EAVE + G_RISE + 1.15)
        # gable fans (sunburst mullions) at both ends
        for yy in (GY0 + 0.3, GY1 - 0.3):
            hub = (GXC, G + 6.9)
            for (x, z) in prof[1:-1]:
                tube("bronze", (hub[0], yy, hub[1]), (x, yy, z), 0.07, 0.07, 5)
            frustum("bronze", (GXC, yy - 0.12, G + 6.9), 1.1, 1.1, 0.24, 20, axis=(0, 1, 0), smooth=False)
    with part("Greenhouse_Glass", "06_Greenhouse_Library"):
        ys = [GY0 + BAY * i for i in range(int((GY1 - GY0) / BAY) + 1)]
        for y0, y1 in zip(ys[:-1], ys[1:]):
            for i, (a, b) in enumerate(zip(prof[:-1], prof[1:])):
                if y0 <= G_TREE[1] < y1 + 0.01 and 5 <= i <= 8:
                    continue                                            # the tree grows out through this bay
                pane("glass", a, b, y0 + 0.07, y1 - 0.07)
        for yy in (GY0 + 0.3, GY1 - 0.3):                                # gable glass
            pts = [(GX0 + 0.3, G + 5.6), (GX1 - 0.3, G + 5.6)] + [(x, z - 0.05) for x, z in prof[1:-1]]
            pts = [(min(max(x, GX0 + 0.3), GX1 - 0.3), z) for x, z in pts]
            vprism("glass", pts, yy - 0.03, 0.06)
    build_greenhouse_interior()


def build_greenhouse_interior():
    with part("Library_Mezzanine", "06_Greenhouse_Library"):
        for (xa, xb) in ((GX0 + 0.6, -37.8), (-18.6, GX1 - 0.6)):
            box2("wood_dark", xa, GY0 + 0.6, L1 - 0.4, xb, GY1 - 0.6, L1)
            xe = xb if xa < -30 else xa
            y = GY0 + 2.0
            while y < GY1 - 1:
                box2("bronze", xe - 0.15, y - 0.15, G, xe + 0.15, y + 0.15, L1 - 0.4)                    # cast bronze posts
                box2("bronze", xe - 0.3, y - 0.3, L1 - 0.75, xe + 0.3, y + 0.3, L1 - 0.4)
                y += 4.0
        box2("wood_dark", -37.8, 13.0, L1 - 0.4, -18.6, 16.0, L1)                                       # bridge across the nave
        # railings (open where the stair arrives and where the bridge meets)
        def rail_y(x, y0, y1, z):
            if y1 - y0 < 0.3:
                return
            box2("bronze", x - 0.05, y0, z + 1.0, x + 0.05, y1, z + 1.1)
            y = y0
            while y <= y1 + 1e-3:
                box2("bronze", x - 0.05, y - 0.05, z, x + 0.05, y + 0.05, z + 1.0)
                y += 1.0

        def rail_x(y, x0, x1, z):
            box2("bronze", x0, y - 0.05, z + 1.0, x1, y + 0.05, z + 1.1)
            x = x0
            while x <= x1 + 1e-3:
                box2("bronze", x - 0.05, y - 0.05, z, x + 0.05, y + 0.05, z + 1.0)
                x += 1.0
        rail_y(-37.85, GY0 + 0.6, 13.0, L1)
        rail_y(-37.85, 16.0, GY1 - 0.6, L1)
        rail_y(-18.55, GY0 + 0.6, -7.6, L1)
        rail_y(-18.55, -5.6, 13.0, L1)
        rail_y(-18.55, 16.0, GY1 - 0.6, L1)
        for y in (13.0, 16.0):
            rail_x(y, -37.8, -18.6, L1)
        # stair from the reading room up to the east mezzanine (20 x 0.325 m)
        for k in range(1, 20):
            top = G + k * UP_RISE
            y0 = -14.0 + 0.32 * (k - 1)
            box2("wood_dark", -20.8, y0, G if top < G + 2.6 else top - 0.3, -18.6, y0 + 0.32, top)
        box2("wood_dark", -20.8, -7.92, L1 - 0.4, -18.6, -5.6, L1)
        rail_y(-20.85, -14.0, -5.6, G)                                   # (simple rail at the outer side)
    with part("Library_Furniture", "06_Greenhouse_Library"):
        # archive stacks under the mezzanines
        for (xa, xb) in ((GX0 + 0.7, -38.1), (-18.3, GX1 - 0.7)):
            y = GY0 + 2.2
            while y < GY1 - 2.0:
                if not (-1.0 < y < 9.0 and xa > -30):
                    bookcase(xa, xb, y, G, 3.2)
                y += 3.0
        # mezzanine shelves along the glass, reading desks
        for (xa, xb) in ((GX0 + 0.7, GX0 + 1.4), (GX1 - 1.4, GX1 - 0.7)):
            y = GY0 + 1.5
            while y < GY1 - 2.0:
                if not (1.2 < y < 6.8 and xa > -30):
                    bookcase(xa, xb, y, L1, 2.6, along="y", length=2.4)
                y += 3.0
        for y in (-14.0, -8.0, 8.0):
            for x in (-33.0, -23.6):
                reading_table(x, y, G)
        # planters and the reading-room benches round the tree
        frustum("stone_old", (G_TREE[0], G_TREE[1], G), 3.2, 3.2, 0.5, 32, smooth=False)
        frustum("soil", (G_TREE[0], G_TREE[1], G + 0.5), 2.9, 2.9, 0.02, 32, smooth=False)
        for k in range(6):
            a = tau * k / 6 + 0.3
            bench(G_TREE[0] + 4.4 * cos(a), G_TREE[1] + 4.4 * sin(a), G, rz=a + pi / 2)
        for (x, y) in ((-33.5, 13.5), (-23.0, 13.5)):
            box2("stone_old", x - 1.4, y - 0.9, G, x + 1.4, y + 0.9, G + 0.6, ch=0.03)
            box2("soil", x - 1.25, y - 0.75, G + 0.6, x + 1.25, y + 0.75, G + 0.63)
            for k in range(3):
                shrub(x - 0.8 + 0.8 * k, y, G + 0.63, 0.5)
        light("Library_Warm", (GXC, 0.0, G + 7.0), 500, (1.0, 0.8, 0.55), size=4.0)
    with part("Greenhouse_Tree", "10_Greenery"):
        cx, cy = G_TREE
        trunk = [(cx, cy, G + 0.3), (cx + 0.3, cy + 0.2, G + 5), (cx - 0.2, cy + 0.1, G + 10), (cx + 0.1, cy, G + 15.5), (cx, cy, G + 18)]
        path_tube("bark", trunk, [1.1, 0.85, 0.7, 0.55, 0.4], segs=12)
        for k in range(5):
            a = tau * k / 5
            path_tube("root", [(cx + 0.6 * cos(a), cy + 0.6 * sin(a), G + 1.4), (cx + 1.8 * cos(a), cy + 1.8 * sin(a), G + 0.7),
                               (cx + 2.7 * cos(a), cy + 2.7 * sin(a), G + 0.45)], [0.4, 0.28, 0.12], segs=6)
        for k in range(5):
            a = tau * k / 5 + 0.6
            p0 = (cx, cy, G + 15.0)
            p1 = (cx + 4 * cos(a), cy + 2.5 * sin(a), G + 18.5)
            path_tube("bark", [p0, p1], [0.35, 0.12], segs=6)
            blob(rng.choice(["leaf_mid", "leaf_light"]), (p1[0], p1[1], p1[2] + 1.0), (2.8, 2.4, 2.0), segs=8, rings=5, jitter=0.15)
        blob("leaf_mid", (cx, cy, G + 20.5), (3.6, 3.2, 2.4), segs=9, rings=5, jitter=0.15)
    with part("Hanging_Gardens", "10_Greenery"):
        # planters hung from the vault ribs on bronze chains, vines trailing down (5 m+ clear underneath)
        prof = gh_profile()
        for y in [GY0 + BAY * i for i in range(1, 10)]:
            if abs(y - G_TREE[1]) < 3.0 or 11.5 < y < 17.5:          # (clear of the tree and the mezzanine bridge)
                continue
            for i in (4, 10):
                x, z = prof[i]
                pz = G + 10.4
                tube("bronze_dark", (x, y, z - 0.1), (x, y, pz + 0.5), 0.03, 0.03, 4)
                box("wood_light", (x, y, pz + 0.25), (1.2, 0.8, 0.5), ch=0.04)
                blob("leaf_mid", (x, y, pz + 0.6), (0.7, 0.5, 0.35), segs=6, rings=3)
                for k in range(3):
                    vine_strand((x - 0.4 + 0.4 * k, y + rng.uniform(-0.3, 0.3), pz), rng.uniform(1.6, 2.6))
        # outside: hanging-garden terraces stepping down the west side of the podium
        for k in range(4):
            y0 = -20.0 + k * 10.5
            box2("stone_old", -48.5, y0, H, -44.0, y0 + 8.0, H + 0.9, ch=0.04)
            box2("soil", -48.3, y0 + 0.2, H + 0.9, -44.2, y0 + 7.8, H + 0.93)
            for j in range(4):
                shrub(-46.2 + rng.uniform(-1, 1), y0 + 1.2 + 1.9 * j, H + 0.93, 0.6)
        # flowering vines climbing the south glass wall
        for x in (-40.0, -36.0, -22.0, -18.0):
            pts = [(x + 0.3 * sin(z), GY0 - 0.2, z) for z in [G + 1.3 + 0.9 * i for i in range(8)]]
            path_tube("leaf_dark", pts, [0.08] * len(pts), segs=5)
            for p in pts[1::2]:
                leafy(p, 0.45)


def bookcase(xa, xb, y, z, h, along="x", length=None):
    """Shelving unit. along='x': spans xa..xb at y (0.5 deep). along='y': depth xa..xb, spans y..y+length."""
    if along == "x":
        x0, x1, y0, y1 = xa, xb, y - 0.25, y + 0.25
    else:
        x0, x1, y0, y1 = xa, xb, y, y + length
    box2("wood_dark", x0, y0, z, x1, y1, z + 0.1)
    box2("wood_dark", x0, y0, z + h - 0.08, x1, y1, z + h)
    for e in ((x0, x0 + 0.08) if along == "x" else (y0, y0 + 0.08), (x1 - 0.08, x1) if along == "x" else (y1 - 0.08, y1)):
        if along == "x":
            box2("wood_dark", e[0], y0, z, e[1], y1, z + h)
        else:
            box2("wood_dark", x0, e[0], z, x1, e[1], z + h)
    nshelf = int(h / 0.75)
    for s in range(nshelf):
        zs = z + 0.1 + s * 0.75
        if s:
            if along == "x":
                box2("wood_dark", x0, y0, zs - 0.04, x1, y1, zs)
            else:
                box2("wood_dark", x0, y0, zs - 0.04, x1, y1, zs)
        # books: a few colour blocks per shelf (raised off the shelf so they never share a face)
        span0, span1 = (x0 + 0.1, x1 - 0.1) if along == "x" else (y0 + 0.1, y1 - 0.1)
        p = span0
        while p < span1 - 0.2:
            w = rng.uniform(0.25, 0.55)
            q = min(p + w, span1)
            hh = rng.uniform(0.38, 0.55)
            m = rng.choice(["book_red", "book_blue", "book_green", "leather", "parchment"])
            if along == "x":
                box2(m, p, y0 + 0.05, zs + 0.01, q, y1 - 0.05, zs + 0.01 + hh)
            else:
                box2(m, x0 + 0.05, p, zs + 0.01, x1 - 0.05, q, zs + 0.01 + hh)
            p = q + rng.uniform(0.02, 0.15)


def reading_table(x, y, z):
    box("wood_light", (x, y, z + 0.78), (2.8, 1.2, 0.08), ch=0.02)
    for sx in (-1, 1):
        box("wood_dark", (x + sx * 1.2, y, z + 0.37), (0.12, 1.0, 0.74))
    for sx in (-1, 1):
        for sy in (-1, 1):
            box("wood_dark", (x + sx * 0.7, y + sy * 1.0, z + 0.25), (0.5, 0.45, 0.5), ch=0.02)
    box("parchment", (x - 0.4, y, z + 0.83), (0.6, 0.4, 0.02))
    box("leather", (x + 0.5, y + 0.1, z + 0.9), (0.4, 0.3, 0.16))
    frustum("bronze", (x + 1.0, y - 0.3, z + 0.82), 0.12, 0.08, 0.35, 8)
    blob("candle", (x + 1.0, y - 0.3, z + 1.25), (0.07, 0.07, 0.1), segs=5, rings=3)


def vine_strand(p, length):
    pts = [(p[0] + 0.15 * sin(i * 1.3), p[1] + 0.12 * cos(i * 1.1), p[2] - length * i / 5) for i in range(6)]
    path_tube("leaf_dark", pts, [0.05] * 6, segs=4, caps=False)
    for q in pts[1::2]:
        blob(rng.choice(["leaf_mid", "leaf_light"]), q, (0.22, 0.22, 0.18), segs=5, rings=3)
    if rng.random() < 0.5:
        blob(rng.choice(["flower_pink", "flower_purple"]), pts[-1], 0.12, segs=4, rings=3)


# ================================================================ REAR WING: COUNCIL / QUEST PLANNING / ADMINISTRATION
RX, RY0, RY1 = 12.0, 9.0, 34.0
ST1 = (8.8, 11.2, 26.6, 33.2)     # stair ground -> L1 (x0, x1, y_top, y_bottom): climbs southward
ST2 = (8.8, 11.2, 19.2, 25.6)     # stair L1 -> L2 (a 1 m landing at L1 between the flights)


def drum_y_north(x, r=R_OUT):
    return RC[1] + sqrt(max(0.0, r * r - x * x))


def build_rear():
    t = 0.8
    xi = RX - t
    yi = RY1 - t
    with part("Rear_Wing", "07_Rear_Wing"):
        # outer walls (ground in dark-based stone, upper floor marble with bronze-framed windows)
        for sx in (-1, 1):
            wins = [(13.0, 15.5, G + 1.6, G + 5.2), (19.0, 21.5, G + 1.6, G + 5.2), (25.0, 27.5, G + 1.6, G + 5.2),
                    (13.0, 15.5, L1 + 1.4, L1 + 5.0), (19.0, 21.5, L1 + 1.4, L1 + 5.0), (25.0, 27.5, L1 + 1.4, L1 + 5.0), (29.5, 32.0, L1 + 1.4, L1 + 5.0)]
            if sx > 0:
                wins = [w for w in wins if not (w[0] > 18 and w[2] > L1)]          # the stair runs along the east wall upstairs
            wall_open("marble_warm", "y", drum_y_north(RX) - 0.3, RY1, sx * (RX - t / 2), G, L2 + 1.1, t, wins)
            for (a, b, z0, z1) in wins:
                win_frame("x", sx * (RX - t / 2), a, b, z0, z1, sx)
        nwins = [(-2.5, 2.5, G - 0.1, G + 5.0), (-9.5, -6.0, G + 1.6, G + 5.2), (6.0, 9.5, G + 1.6, G + 5.2),
                 (-9.5, -6.0, L1 + 1.4, L1 + 5.0), (-4.5, -1.0, L1 + 1.4, L1 + 5.0), (1.0, 4.5, L1 + 1.4, L1 + 5.0)]
        wall_open("marble_warm", "x", -RX, RX, RY1 - t / 2, G, L2 + 1.1, t, nwins)
        for (a, b, z0, z1) in nwins[1:]:
            win_frame("y", RY1 - t / 2, a, b, z0, z1, 1)
        for (xa, xb) in ((-RX - 0.1, -2.6), (2.6, RX + 0.1)):                                              # dark plinth (open at the door)
            box2("marble_dark", xa, RY1 - 0.05, G, xb, RY1 + 0.15, G + 1.0)
        for sx in (-1, 1):
            box2("marble_dark", sx * RX - 0.1 if sx > 0 else -RX - 0.15, drum_y_north(RX), G, sx * RX + 0.15 if sx > 0 else -RX + 0.1, RY1 + 0.15, G + 1.0)
        for z in (L1 - 0.2, L2 - 0.2):                                                                       # gold string courses
            box2("gold", -RX - 0.06, RY1 - 0.02, z, RX + 0.06, RY1 + 0.06, z + 0.14)
        box2("bronze", -RX - 0.3, RY1 - 0.3, L2 + 0.95, RX + 0.3, RY1 + 0.3, L2 + 1.25)                      # cornice
        # floors (cut round the drum, holes over the stairs)
        for r_ in ((-xi, RY0, ST1[0], yi), (ST1[0], RY0, xi, ST1[2])):
            region_minus_disc("wood_dark", rect(*r_), RC, R_OUT, L1 - 0.4, L1, n=48)
        for r_ in ((-xi, RY0, ST2[0], yi), (ST2[0], RY0, xi, ST2[2]), (ST2[0], ST2[3], xi, yi)):     # roof, open over ST2
            region_minus_disc("marble_warm", rect(*r_), RC, R_OUT, L2 - 0.4, L2, n=48)
        # stairs: ground -> L1 -> L2 along the east wall (stone, bronze nosings)
        for (sx0, sx1, ytop, ybot), zb in ((ST1, G), (ST2, L1)):
            n = 20
            run = (ybot - ytop) / n
            for k in range(1, n + 1):
                top = zb + k * UP_RISE
                y1_ = ybot - run * (k - 1)
                y0_ = ybot - run * k
                box2("marble_white", sx0, y0_, zb if top < zb + 2.6 else top - 0.32, sx1, y1_, top)
                box2("bronze", sx0 + 0.05, y0_ - 0.03, top - 0.06, sx1 - 0.05, y0_ + 0.03, top + 0.02)
        # railings round the stair wells
        for (z, (x0_, x1_, ya, yb)) in ((L1, ST1), (L2, ST2)):
            box2("bronze", x0_ - 0.1, ya + 0.2, z, x0_, yb, z + 1.1)
        # interior: partition upstairs (Administration | Quest Planning), lobby clear by the drum door
        wall_open("marble_warm", "y", 21.0, yi, 0.0, L1, L2 - 0.4, 0.3, [(26.5, 29.0, L1 - 0.1, L1 + 4.2)])
        # the roof garden: planters on the parapets, a bronze pergola with vines, a kiosk over the stair
        for (x0_, x1_, y0_, y1_) in ((-xi, -xi + 1.2, drum_y_north(xi), yi), (xi - 1.2, xi, drum_y_north(xi), ST2[2] - 1.0),
                                      (-xi, 8.4, yi - 1.2, yi)):
            if x1_ - x0_ > 0.5 and y1_ - y0_ > 0.5:
                box2("stone_old", x0_, y0_, L2, x1_, y1_, L2 + 0.7)
                box2("soil", x0_ + 0.12, y0_ + 0.12, L2 + 0.7, x1_ - 0.12, y1_ - 0.12, L2 + 0.73)
                n = int(max(x1_ - x0_, y1_ - y0_) / 1.5)
                for k in range(n):
                    t_ = (k + 0.5) / n
                    px = x0_ + (x1_ - x0_) * (t_ if x1_ - x0_ > y1_ - y0_ else 0.5)
                    py = y0_ + (y1_ - y0_) * (t_ if y1_ - y0_ >= x1_ - x0_ else 0.5)
                    shrub(px, py, L2 + 0.73, 0.5)
        for sx in (-1, 1):                                                                                   # vines over the parapet
            for y in (14.0, 20.0, 26.0, 31.0):
                for k in range(2):
                    vine_strand((sx * (RX + 0.25), y + k * 0.8, L2 + 0.9), rng.uniform(2.5, 4.5))
        for x in (-8.0, -4.0, 0.0, 4.0):
            vine_strand((x, RY1 + 0.25, L2 + 0.9), rng.uniform(2.5, 4.5))
        # pergola
        for x in (-6.0, -1.0, 4.0):
            for y in (24.0, 30.0):
                frustum("bronze", (x, y, L2), 0.14, 0.12, 3.4, 8)
        for y in (24.0, 30.0):
            box2("bronze", -6.3, y - 0.1, L2 + 3.4, 4.3, y + 0.1, L2 + 3.6)
        for x in (-6.0, -4.0, -2.0, 0.0, 2.0, 4.0):
            box2("wood_dark", x - 0.08, 23.6, L2 + 3.6, x + 0.08, 30.4, L2 + 3.75)
        for k in range(14):
            leafy((rng.uniform(-6, 4), rng.uniform(24, 30), L2 + 3.9), 0.6)
        for x in (ST2[0] - 0.2, ST2[1] - 0.1):                                                               # stair kiosk
            for y in (ST2[2] - 0.2, ST2[3] + 0.2):
                frustum("bronze", (x, y, L2), 0.12, 0.12, 4.8, 8)
        box2("bronze_dark", ST2[0] - 0.5, ST2[2] - 0.5, L2 + 4.8, ST2[1] + 0.3, ST2[3] + 0.5, L2 + 5.0)
        for sx in (-1, 1):
            bench(sx * 4.0, 18.6 + 1.0, L2, rz=0.0)
        # ground floor: the Council Chamber - a round table of twelve
        frustum("wood_dark", (0.0, 25.8, G + 0.72), 3.0, 3.0, 0.1, 36, smooth=False)
        frustum("bronze", (0.0, 25.8, G + 0.69), 3.05, 3.05, 0.03, 36, smooth=False)
        frustum("wood_dark", (0.0, 25.8, G), 0.8, 0.5, 0.69, 12)
        annulus("gold", (0.0, 25.8), 1.2, 1.0, G + 0.82, G + 0.84, segs=24)
        for k in range(12):
            a = tau * k / 12
            x, y = 3.8 * cos(a), 25.8 + 3.8 * sin(a)
            with at((x, y, G), a + pi / 2):
                box("wood_dark", (0, 0, 0.45), (0.6, 0.55, 0.08))
                box("wood_dark", (0, 0.28, 1.0), (0.6, 0.08, 1.1))
                for (lx, ly) in ((-0.25, -0.22), (0.25, -0.22), (-0.25, 0.22), (0.25, 0.22)):
                    box("wood_dark", (lx, ly, 0.21), (0.06, 0.06, 0.42))
        chandelier(0.0, 25.8, L1 - 0.4, G + 4.6)
        for x in (-8.0, -4.0):
            banner(x, yi - 0.12, L1 - 0.6, 1.4, 3.4, rz=0.0, kind="bull")
        # upstairs west: Camp Administration (desks, cabinets)
        for (x, y) in ((-8.5, 23.5), (-4.5, 23.5), (-8.5, 29.5), (-4.5, 29.5)):
            box("wood_light", (x, y, L1 + 0.76), (2.2, 1.1, 0.08), ch=0.02)
            for sx in (-1, 1):
                box("wood_dark", (x + sx * 0.95, y, L1 + 0.36), (0.12, 1.0, 0.72))
            box("wood_dark", (x, y + 0.9, L1 + 0.25), (0.5, 0.45, 0.5), ch=0.02)
            box("parchment", (x - 0.3, y, L1 + 0.81), (0.5, 0.35, 0.02))
        for y in (22.0, 26.0, 30.0):
            box2("wood_dark", -xi, y - 1.2, L1, -xi + 0.6, y + 1.2, L1 + 2.2)
            for k in range(4):
                box2("bronze", -xi + 0.6, y - 1.0, L1 + 0.3 + 0.5 * k, -xi + 0.64, y + 1.0, L1 + 0.34 + 0.5 * k)
        # upstairs east: the Quest Planning Chamber - a great map table with the camp in miniature
        box2("wood_dark", 2.0, 21.8, L1, 7.6, 27.2, L1 + 0.9, ch=0.03)
        box2("parchment", 2.2, 22.0, L1 + 0.9, 7.4, 27.0, L1 + 0.93)
        mx, my = 4.8, 24.5
        frustum("leaf_mid", (mx, my, L1 + 0.93), 0.35, 0.05, 0.6, 7)
        for k in range(10):
            a = rng.uniform(0, tau)
            r = rng.uniform(0.9, 2.2)
            box(rng.choice(["marble_white", "wood_light", "bronze"]), (mx + r * cos(a), my + r * 0.9 * sin(a), L1 + 1.0), (0.25, 0.25, 0.14))
        for k in range(6):
            frustum("leaf_dark", (mx + rng.uniform(-2.3, 2.3), my + rng.uniform(-2.2, 2.2), L1 + 0.93), 0.12, 0.0, 0.35, 5)
        for x in (2.5, 5.0):                                                                                  # wall maps
            box2("wood_dark", x - 1.1, yi - 0.1, L1 + 1.2, x + 1.1, yi, L1 + 3.2)
            box2("parchment", x - 1.0, yi - 0.13, L1 + 1.3, x + 1.0, yi - 0.1, L1 + 3.1)
        chandelier(4.8, 24.5, L2 - 0.4, L1 + 4.7)
    # empty pedestals at the hall intersections (where the drum door opens into the wing, and on the roof garden)
    pedestal("Council_Lobby_West", -6.6, 19.4, G, facing=0, size=2.2, height=1.2)
    pedestal("Council_Lobby_East", 6.6, 19.4, G, facing=180, size=2.2, height=1.2)
    pedestal("Roof_Garden_Centre", -1.0, 27.0, L2, facing=-90, size=2.4, height=1.0)


def win_frame(axis, c, a, b, z0, z1, s):
    """Bronze frame + mullion + glass in a rectangular wall opening."""
    if axis == "x":                                                       # wall runs along y at x = c
        box2("glass", c - 0.03, a, z0, c + 0.03, b, z1)
        for yy in (a, b):
            box2("bronze", c - 0.5, yy - 0.08, z0, c + 0.5, yy + 0.08, z1)
        for zz in (z0, z1):
            box2("bronze", c - 0.5, a - 0.08, zz - 0.08, c + 0.5, b + 0.08, zz + 0.08)
        box2("bronze", c - 0.08, (a + b) / 2 - 0.05, z0, c + 0.08, (a + b) / 2 + 0.05, z1)
    else:                                                                 # wall runs along x at y = c
        box2("glass", a, c - 0.03, z0, b, c + 0.03, z1)
        for xx in (a, b):
            box2("bronze", xx - 0.08, c - 0.5, z0, xx + 0.08, c + 0.5, z1)
        for zz in (z0, z1):
            box2("bronze", a - 0.08, c - 0.5, zz - 0.08, b + 0.08, c + 0.5, zz + 0.08)
        box2("bronze", (a + b) / 2 - 0.05, c - 0.08, z0, (a + b) / 2 + 0.05, c + 0.08, z1)


# ================================================================ SHAPES (emblems drawn as 2D outlines, then extruded)
_BH = [(0.0, -0.62), (0.17, -0.58), (0.26, -0.36), (0.30, -0.12), (0.52, -0.03), (0.37, 0.12), (0.42, 0.22),
       (0.72, 0.28), (0.92, 0.50), (0.98, 0.86), (0.84, 0.62), (0.62, 0.44), (0.36, 0.40), (0.0, 0.36)]
BULL = _BH + [(-x, z) for (x, z) in reversed(_BH)][1:-1]
BIDENT = [(-0.06, -0.95), (0.06, -0.95), (0.06, 0.25), (0.32, 0.30), (0.34, 0.95), (0.24, 0.95), (0.22, 0.42),
          (-0.22, 0.42), (-0.24, 0.95), (-0.34, 0.95), (-0.32, 0.30), (-0.06, 0.25)]
HAMMER = [(-0.07, -0.95), (0.07, -0.95), (0.07, 0.38), (0.55, 0.38), (0.62, 0.48), (0.62, 0.78), (-0.48, 0.78),
          (-0.62, 0.62), (-0.48, 0.38), (-0.07, 0.38)]
FLAME = [(0.0, 0.95), (0.20, 0.55), (0.42, 0.22), (0.40, -0.25), (0.20, -0.55), (0.0, -0.62), (-0.20, -0.55),
         (-0.40, -0.25), (-0.42, 0.22), (-0.26, 0.40), (-0.12, 0.30), (-0.10, 0.62)]
PALMETTE = [(0.0, 0.9), (0.18, 0.55), (0.42, 0.62), (0.32, 0.25), (0.52, 0.15), (0.25, -0.05), (0.18, -0.45),
            (-0.18, -0.45), (-0.25, -0.05), (-0.52, 0.15), (-0.32, 0.25), (-0.42, 0.62), (-0.18, 0.55)]
GEAR = [((1.0 if (k // 2) % 2 == 0 else 0.8) * cos(tau * k / 32 + (tau / 64 if k % 2 else -tau / 64) * 0),
         (1.0 if (k // 2) % 2 == 0 else 0.8) * sin(tau * k / 32)) for k in range(32)]


def emblem_shape(mat, pts, c, s, depth, facing_deg):
    """Raised relief of outline `pts` (x right, z up), centred at c, scale s, standing `depth` proud toward facing."""
    f = (cos(radians(facing_deg)), sin(radians(facing_deg)), 0.0)
    u = (-f[1], f[0], 0.0)
    prism_frame(mat, [(x * s, z * s) for x, z in pts], c, u, (0, 0, 1), f, depth)


def emblem_bull(mat, x, y, z, s, depth, facing=-90, eyes=None):
    emblem_shape(mat, BULL, (x, y, z), s, depth, facing)
    if eyes:
        f = (cos(radians(facing)), sin(radians(facing)), 0.0)
        u = (-f[1], f[0], 0.0)
        for sx in (-1, 1):
            p = (x + u[0] * 0.13 * s * sx + f[0] * depth, y + u[1] * 0.13 * s * sx + f[1] * depth, z + 0.02 * s)
            emblem_shape(eyes, [(-0.07, -0.03), (0.07, -0.03), (0.05, 0.03), (-0.05, 0.03)], p, s, 0.02, facing)


# ================================================================ EMPTY PEDESTALS (no statues - NPC spots)
def pedestal(name, x, y, z, facing=-90, size=2.4, height=1.4, theme="camp", round_=False, base=0.55):
    """A ceremonial, symmetrical, EMPTY pedestal sized for a Roblox character. `facing`: the direction a figure
    standing on it should look (degrees, 0 = +X, -90 = south / toward the camp)."""
    body = {"camp": "marble_warm", "hades": "marble_dark", "hephaestus": "marble_warm"}[theme]
    trim = {"camp": "gold", "hades": "gold", "hephaestus": "bronze"}[theme]
    with part("Pedestal_" + name, "11_Empty_Pedestals"):
        with at((x, y, z), radians(facing + 90)):         # local -y faces `facing`
            if round_:
                r = size / 2
                frustum("stone_old", (0, 0, 0), r + base, r + base - 0.05, 0.3, 40, smooth=False)
                frustum(body, (0, 0, 0.3), r + 0.12, r + 0.05, height, 40)
                annulus(trim, (0, 0), r + 0.1, r - 0.02, 0.3 + height - 0.3, 0.3 + height - 0.18, segs=40)
                annulus(trim, (0, 0), r + 0.12, r, 0.42, 0.52, segs=40)
                frustum("marble_white", (0, 0, 0.3 + height), r + 0.28, r + 0.25, 0.25, 40, smooth=False)
                emblem_bull(trim, 0.0, -(r + 0.07), 0.3 + height * 0.5, 0.42, 0.06, facing=-90)
                top = 0.3 + height + 0.25
            else:
                h = height
                box("stone_old", (0, 0, 0.15), (size + 0.7, size + 0.7, 0.3), ch=0.04)               # ground step
                box("marble_dark" if theme != "hades" else "slate", (0, 0, 0.42), (size + 0.35, size + 0.35, 0.24), ch=0.03)
                box(body, (0, 0, 0.54 + h / 2), (size, size, h), ch=0.05)                             # the block
                for cx_ in (-1, 1):                                                                   # corner pilasters
                    for cy_ in (-1, 1):
                        box(trim if theme == "hephaestus" else "marble_white", (cx_ * (size / 2 - 0.12), cy_ * (size / 2 - 0.12), 0.54 + h / 2),
                            (0.32, 0.32, h - 0.1), ch=0.03)
                box(trim, (0, 0, 0.54 + h - 0.2), (size + 0.06, size + 0.06, 0.1))                    # band (below the top)
                box("marble_white", (0, 0, 0.54 + h + 0.13), (size + 0.4, size + 0.4, 0.26), ch=0.04)  # cap
                top = 0.54 + h + 0.26
                # front plaque (blank, for a name later) and the founder's sign on the sides
                box("bronze_dark", (0, -size / 2 - 0.02, 0.54 + h * 0.48), (size * 0.5, 0.06, h * 0.42))
                box(trim, (0, -size / 2 - 0.05, 0.54 + h * 0.48), (size * 0.44, 0.04, h * 0.34))
                sign = {"camp": BULL, "hades": BIDENT, "hephaestus": HAMMER}[theme]
                for sx in (-1, 1):
                    emblem_shape(trim, sign, (sx * (size / 2 + 0.0), 0.0, 0.54 + h * 0.5), min(0.5, h * 0.32), 0.05, 0 if sx > 0 else 180)
    NPC_SPOTS.append({"name": name, "pos": (x, y, z + top), "facing": (facing + 180) % 360 - 180, "top": round(size + (0.5 if round_ else 0.4), 2)})


# ================================================================ MECHANICAL BRAZIERS (Hephaestus)
def brazier(x, y, z, s=1.0, spirit=False):
    with part("Braziers", "12_Braziers_Banners"):
        with at((x, y, z)):
            frustum("stone_old", (0, 0, 0), 0.75 * s, 0.7 * s, 0.25 * s, 10, smooth=False)
            for k in range(3):                                                   # tripod legs
                a = tau * k / 3 + pi / 6
                tube("bronze_dark", (0.62 * s * cos(a), 0.62 * s * sin(a), 0.25 * s), (0.18 * s * cos(a), 0.18 * s * sin(a), 1.25 * s), 0.07 * s, 0.05 * s, 6)
            frustum("bronze", (0, 0, 0.25 * s), 0.14 * s, 0.12 * s, 1.15 * s, 8)
            annulus("bronze", (0, 0), 0.62 * s, 0.48 * s, 1.0 * s, 1.1 * s, segs=24)      # gear ring
            for k in range(12):
                a = tau * k / 12
                box("bronze", (0.66 * s * cos(a), 0.66 * s * sin(a), 1.05 * s), (0.12 * s, 0.12 * s, 0.1 * s), rz=a)
            frustum("bronze", (0, 0, 1.3 * s), 0.28 * s, 0.68 * s, 0.42 * s, 16)          # bowl
            annulus("gold", (0, 0), 0.72 * s, 0.64 * s, 1.68 * s, 1.74 * s, segs=24)
            blob("slate", (0, 0, 1.68 * s), (0.5 * s, 0.5 * s, 0.14 * s), segs=8, rings=3)
            fire = "spirit" if spirit else "fire"
            frustum(fire, (0, 0, 1.7 * s), 0.42 * s, 0.0, 1.1 * s, 7, smooth=True)
            frustum(fire, (0.12 * s, 0.05 * s, 1.72 * s), 0.25 * s, 0.0, 1.45 * s, 6, smooth=True, a0=0.5)
            frustum("candle", (-0.1 * s, -0.08 * s, 1.72 * s), 0.18 * s, 0.0, 0.8 * s, 5, smooth=True)
    light("Brazier_%.0f_%.0f_%.0f" % (x, y, z), (x, y, z + 2.4 * s), 220 * s, (0.6, 0.85, 1.0) if spirit else (1.0, 0.5, 0.18), size=0.5)


# ================================================================ BANNERS
def banner(x, y, z_top, w, h, rz=0.0, kind="bull"):
    """Cloth banner hanging from a bronze rod. Front faces local -y (rz rotates it)."""
    cloth = {"bull": "maroon", "hades": "slate", "hephaestus": "leather"}[kind]
    with part("Banners", "12_Braziers_Banners"):
        with at((x, y, 0), rz):
            tube("bronze", (-w / 2 - 0.25, 0.0, z_top), (w / 2 + 0.25, 0.0, z_top), 0.05, 0.05, 6)
            for sx in (-1, 1):
                blob("gold", (sx * (w / 2 + 0.28), 0.0, z_top), 0.09, segs=5, rings=3)
            pts = [(-w / 2, z_top - 0.08), (w / 2, z_top - 0.08), (w / 2, z_top - h), (0.0, z_top - h + 0.45), (-w / 2, z_top - h)]
            vprism(cloth, pts, -0.03, 0.06)
            box("gold", (0, -0.035, z_top - 0.35), (w * 0.86, 0.02, 0.08))
            box("gold", (0, -0.035, z_top - h + 0.75), (w * 0.86, 0.02, 0.06))
            zc = z_top - h * 0.45
            if kind == "bull":
                emblem_bull("cream", 0.0, -0.03, zc, w * 0.36, 0.025, facing=-90)
            elif kind == "hades":
                emblem_shape("bronze", BIDENT, (0.0, -0.03, zc), w * 0.4, 0.025, -90)
            else:
                emblem_shape("gold", HAMMER, (0.0, -0.03, zc), w * 0.4, 0.025, -90)


def spiral_vine(x, y, z, r, h, turns=2.0):
    n = int(turns * 12)
    pts = [(x + r * cos(tau * turns * i / n), y + r * sin(tau * turns * i / n), z + h * i / n) for i in range(n + 1)]
    path_tube("leaf_dark", pts, [0.07] * len(pts), segs=5)
    for p in pts[2::3]:
        blob(rng.choice(["leaf_mid", "leaf_light", "leaf_dark"]), (p[0], p[1], p[2]), (0.32, 0.32, 0.24), segs=5, rings=3, jitter=0.2)
        if rng.random() < 0.35:
            blob(rng.choice(["flower_pink", "flower_purple", "flower_white"]), (p[0], p[1], p[2] + 0.2), 0.11, segs=4, rings=3)


# ================================================================ BUILD EVERYTHING
def build_site_props():
    # the forecourt: the great round pedestal at the heart of the rings
    pedestal("Forecourt_Centre", FC[0], FC[1], H, facing=-90, size=4.6, height=1.5, round_=True)
    with part("Forecourt", "02_Forecourt_Podium"):
        for k in range(14):
            a = tau * k / 14
            shrub(FC[0] + 3.2 * cos(a), FC[1] + 3.2 * sin(a), H, 0.35)
    # founders' guard: a large pair flanking the podium steps (where the reference had Hades and Hephaestus)
    pedestal("Founders_Guard_West", -14.5, -33.2, H, facing=-90, size=3.0, height=1.8, theme="hades")
    pedestal("Founders_Guard_East", 14.5, -33.2, H, facing=-90, size=3.0, height=1.8, theme="hephaestus")
    # porch, flanking the forged doors
    pedestal("Porch_West", -6.4, -24.9, G, facing=-90, size=2.4, height=1.3)
    pedestal("Porch_East", 6.4, -24.9, G, facing=-90, size=2.4, height=1.3)
    # the grand stair landings (alcoves either side of the walking line)
    for (yh, yl, z, kind) in STAIR_SEGS:
        if kind == "landing":
            ym = (yh + yl) / 2
            for sx in (-1, 1):
                pedestal("Stair_Landing_%s_%d" % ("West" if sx < 0 else "East", int(-ym)), sx * 10.6, ym, z, facing=0 if sx < 0 else 180,
                         size=2.2, height=1.2)
                brazier(sx * 12.0, yh - 0.9, z, 0.7)
    # braziers: stair head, stair foot, podium steps, porch (spirit-fire pair at the door, like the reference)
    for sx in (-1, 1):
        brazier(sx * 9.8, -44.6, H, 1.0)
        brazier(sx * 9.6, STAIR_FOOT - 1.6, 0.0 + max(0.0, hill_z(sx * 9.6, STAIR_FOOT - 1.6)), 1.0)
        brazier(sx * 19.5, -30.0, H, 1.0)
        brazier(sx * 3.9, -25.2, G, 0.9, spirit=True)
    # the greenhouse doors, the temple front, the side entries, the rear courtyard
    pedestal("Greenhouse_South_West", -33.6, -22.6, G, facing=-90, size=2.2, height=1.2)
    pedestal("Greenhouse_South_East", -23.0, -22.6, G, facing=-90, size=2.2, height=1.2)
    pedestal("Temple_Steps_West", 17.0, -27.0, G, facing=-90, size=2.2, height=1.2)
    pedestal("Temple_Steps_East", 39.0, -27.0, G, facing=-90, size=2.2, height=1.2)
    pedestal("Remembrance_West", -13.0, 41.2, H, facing=90, size=2.2, height=1.1, theme="hades")
    pedestal("Remembrance_East", 13.0, 41.2, H, facing=90, size=2.2, height=1.1, theme="hades")
    # the atrium: four pedestals at the diagonals of the garden ring, facing the tree
    for d in (45, 135, 225, 315):                                   # set into the garden beds, off the walkway
        p = polar(RC, 7.25, d)
        pedestal("Atrium_%03d" % d, p[0], p[1], G, facing=d, size=1.6, height=1.0, round_=True, base=0.4)
    # the undercroft: hero memorials round the walls
    for d in (30, 150, 210, 330):
        p = polar(RC, 10.0, d)
        pedestal("Undercroft_Memorial_%03d" % d, p[0], p[1], U, facing=d + 180, size=2.0, height=1.0, theme="hades")
    # each secret vault keeps one empty relic pedestal
    for ang, nm in ((0, "East"), (90, "North"), (180, "West")):
        p = polar(RC, 26.0, ang)
        pedestal("Vault_" + nm, p[0], p[1], U, facing=ang + 180, size=2.0, height=1.1, theme="hephaestus")
    # observation balcony lamps
    with part("Observation_Lamps", "12_Braziers_Banners"):
        for k in range(8):
            p = polar(RC, 13.65, 22.5 + 45 * k, OBS + 1.15)
            lantern(p[0], p[1], p[2])
    # lights: a low warm sunset sun, the atrium, the observation balcony
    light("Sunset_Sun", (60.0, -80.0, 60.0), 3.5, (1.0, 0.72, 0.45), kind="SUN", rot=(radians(78), 0.0, radians(-35)))
    light("Atrium_Glow", (RC[0], RC[1] - 7.0, G + 4.0), 900, (1.0, 0.82, 0.55), size=3.0)
    light("Observation", (RC[0], RC[1], OBS + 3.0), 600, (1.0, 0.8, 0.55), size=3.0)


def build_all():
    build_hill()
    build_roads()
    build_grand_stair()
    build_plateau()
    build_podium()
    build_forecourt()
    build_rear_courtyard()
    build_hill_trees()
    build_drum()
    build_atrium_floors()
    build_spiral()
    build_tree()
    build_undercroft()
    build_hall()
    build_temple()
    build_greenhouse()
    build_rear()
    build_site_props()


# ================================================================ create the Blender objects
GROUPS = ["01_Hill_Roads", "02_Forecourt_Podium", "03_Hall_of_Founders", "04_Garden_Atrium", "05_Temple_Assembly_Hall",
          "06_Greenhouse_Library", "07_Rear_Wing", "08_Undercroft_Vaults", "09_Sacred_Tree", "10_Greenery",
          "11_Empty_Pedestals", "12_Braziers_Banners", "13_NPC_Spots", "14_Lights"]


def remove_old():
    old = bpy.data.collections.get(ROOT_NAME)
    if not old:
        return
    for ob in list(old.all_objects):
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        try:
            if data is not None and data.users == 0:
                if hasattr(bpy.data, "meshes") and data.__class__.__name__ == "Mesh":
                    bpy.data.meshes.remove(data)
        except Exception:
            pass
    for ch in list(old.children_recursive) if hasattr(old, "children_recursive") else []:
        bpy.data.collections.remove(ch)
    bpy.data.collections.remove(old)


def realize():
    remove_old()
    root = bpy.data.collections.new(ROOT_NAME)
    bpy.context.scene.collection.children.link(root)
    COL = {}
    for g in GROUPS:
        COL[g] = bpy.data.collections.new("GH " + g)
        root.children.link(COL[g])
    made, total = [], 0
    for name, chunks in PARTS.items():
        group = PART_GROUP.get(name, "10_Greenery")
        for k, ch in enumerate(chunks):
            oname = "GH_" + name + ("" if len(chunks) == 1 else "_%02d" % (k + 1))
            me = bpy.data.meshes.new(oname)
            me.from_pydata(ch["v"], [], ch["f"])
            slots = sorted(set(ch["m"]))
            for s in slots:
                me.materials.append(MAT(s))
            me.polygons.foreach_set("material_index", [slots.index(m) for m in ch["m"]])
            me.polygons.foreach_set("use_smooth", ch["s"])
            me.update()
            me.validate(clean_customdata=False)
            ob = bpy.data.objects.new(oname, me)
            COL[group].objects.link(ob)
            made.append((oname, ch["tris"]))
            total += ch["tris"]
    # NPC spot markers (empties) on top of every empty pedestal
    lines = ["GOD HOUSE - NPC SPOTS (top centre of each EMPTY pedestal)",
             "name, x_m, y_m, z_m, facing_deg, studs_x, studs_y, studs_z (at %.1f studs/m)" % STUD_SCALE]
    for s in NPC_SPOTS:
        e = bpy.data.objects.new("NPC_Spot_" + s["name"], None)
        e.empty_display_type = "SINGLE_ARROW"
        e.empty_display_size = 1.2
        e.location = s["pos"]
        e.rotation_euler = (0.0, 0.0, radians(s["facing"]))
        e["npc_spot"] = True
        e["pedestal_top_m"] = s["top"]
        COL["13_NPC_Spots"].objects.link(e)
        x, y, z = s["pos"]
        lines.append("%s, %.2f, %.2f, %.2f, %.0f, %.1f, %.1f, %.1f" % (s["name"], x, y, z, s["facing"], x * STUD_SCALE, y * STUD_SCALE, z * STUD_SCALE))
    txt = bpy.data.texts.get("GodHouse_NPC_Spots") or bpy.data.texts.new("GodHouse_NPC_Spots")
    txt.clear()
    txt.write("\n".join(lines) + "\n")
    if ADD_LIGHTS:
        for L in LIGHTS:
            ld = bpy.data.lights.new("GH_" + L["name"], L["type"])
            ld.energy = L["energy"]
            ld.color = L["color"]
            if L["type"] == "POINT":
                ld.shadow_soft_size = L.get("size", 0.3)
            lo = bpy.data.objects.new("GH_" + L["name"], ld)
            lo.location = L["pos"]
            if "rot" in L:
                lo.rotation_euler = L["rot"]
            COL["14_Lights"].objects.link(lo)
    print("\n".join(lines))
    print("God House built: %d objects, %d triangles, %d empty pedestals." % (len(made), total, len(NPC_SPOTS)))
    big = sorted(made, key=lambda t: -t[1])[:8]
    for n, t in big:
        print("   %-44s %6d tris" % (n, t))
    return made, total


def light(name, pos, energy, color=(1.0, 0.55, 0.25), kind="POINT", size=0.3, rot=None):
    d = dict(name=name, pos=pos, energy=energy, color=color, type=kind, size=size)
    if rot:
        d["rot"] = rot
    LIGHTS.append(d)


build_all()
realize()
