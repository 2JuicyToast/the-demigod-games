# =============================================================================
# CAMP DEMISOUL - THE FORGE & ARMORY DISTRICT (game-ready)
# Run in Blender's Scripting tab (3.6 / 4.x). Safe to re-run: it only replaces
# its own collection ("CampForge_GameReady").
#
# WHAT THIS BUILDS  (front of every building faces -Y in its own frame)
#   Plaza + the Great Anvil monument, ringed by four eternal-flame bowls
#   Beacon of Craft tower, Shield Wall, Forge Gate, Promenade, banners & standards
#   THE GREAT FORGE   (west)  basilica hall: 4 furnaces/kilns, 6 anvils, 2 quench
#                             troughs, 2 grindstones, casting station, 2 assembly
#                             benches, racks, ore/coal bins, chimneys
#   THE ARMORY        (east)  columned temple hall: 3 merchant counters, 2 inspection
#                             daises with turntables, 8 armour displays, weapon
#                             showcase bays, golden Panoply centrepiece
#
# EMBLEM RULES (one meaning per crest, used consistently everywhere)
#   BULL    (cream)  Camp DemiSoul itself: gate centre, tower, shield wall, building pediments/gables, floor
#                    medallions, promenade poles, north/south faces of the monument.
#   FORGE   (gold)   hammer crossed with a sword - anything owned by the Forge: its banners, shields, furnace
#                    plaque, back-wall roundel, west banners/stall in the plaza, west plinth face, gate's left side.
#   ARMORY  (gold)   round shield + crossed spears - anything owned by the Armory: its banners, shields, counters,
#                    displays, showcases, east banners/stall in the plaza, east plinth face, gate's right side.
#   The plaza is split down the middle: WEST half = Forge side, EAST half = Armory side.
#
# GAMEPLAY HOOKS
#   * Every interactive piece is its OWN mesh, origin at its floor centre, named
#     Forge_Anvil_01, Armory_Counter_02 ... (rotating/animated parts are separate
#     meshes: *_Turntable).  Fire / molten metal / water come as companion meshes
#     named <station>_Glow (set Material = Neon) and <station>_Water.
#   * A StationMarkers JSON + a Roblox Lua setup script are written next to the
#     FBX: collision boxes + ProximityPrompt anchors for every station.
#   * One shared 256x256 palette (first 20 colours identical to the entrance
#     palette, so the entrance can reuse this same PNG).
# =============================================================================

import bpy, bmesh, math, os, random, struct, zlib, json
from contextlib import contextmanager
from mathutils import Vector, Matrix

# ------------------------------ SETTINGS -------------------------------------
STUD_SCALE = 3.0        # studs per modelled metre (same as the entrance)
EXPORT = True
EXPORT_DIR = ""         # blank = next to your .blend (or home folder if unsaved)
COLLECTION_NAME = "CampForge_GameReady"
TRI_WARN = 20000
SEED = 37
rng = random.Random(SEED)

# --------------------------- PALETTE (one texture) ---------------------------
PALETTE = [
    # 0-19 identical to the entrance palette
    ("STONE", "#9A927F"), ("STONE_LIGHT", "#C2B9A2"), ("STONE_DARK", "#5E5E56"), ("MARBLE", "#E8E1D0"),
    ("BRONZE", "#9C7A3C"), ("BRONZE_DARK", "#5A431F"), ("MAROON", "#5E1D2E"), ("CREAM", "#F1ECDF"),
    ("DIRT", "#9B7446"), ("DIRT_LIGHT", "#BE9A62"), ("GRASS", "#4A6B2E"), ("GRASS_LIGHT", "#6E8E3E"),
    ("LEAF_DARK", "#1F4A2E"), ("LEAF_MID", "#2F6B3F"), ("LEAF_LIGHT", "#58954F"), ("MOSS", "#62803A"),
    ("WOOD", "#5A3B22"), ("GLOW", "#FFC24A"), ("FLOWER_WHITE", "#E8D8A8"), ("FLOWER_PURPLE", "#7A55A8"),
    # forge & armory additions
    ("WOOD_LIGHT", "#8A6238"), ("WOOD_DARK", "#33241A"), ("ROOF", "#4A453B"), ("ROOF_LIGHT", "#6E6657"),
    ("IRON", "#3B4044"), ("IRON_LIGHT", "#8C969B"), ("STEEL", "#C3CBCF"), ("GOLD", "#D9A93C"),
    ("LEATHER", "#5E3421"), ("COAL", "#1B1B1C"), ("ORE_COPPER", "#B4663A"), ("EMBER", "#FF5A1F"),
    ("MOLTEN", "#FFB03A"), ("WATER", "#2F7F93"), ("MAROON_DARK", "#3E1220"), ("PLASTER", "#D9CDB0"),
    ("TERRACOTTA", "#A65B3F"), ("SLATE", "#59606A"), ("PLANK", "#A67C4A"),
]


class _Pal:
    pass


for _i, (_n, _h) in enumerate(PALETTE):
    setattr(_Pal, _n, _i)
C = _Pal
GRID, CELL = 8, 32
TEX = GRID * CELL


# ------------------------------ PALETTE PNG ----------------------------------
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def write_palette_png(path):
    rows = []
    for r in range(TEX):
        cy = (TEX - 1 - r) // CELL
        row = bytearray()
        for cx in range(GRID):
            idx = cy * GRID + cx
            rgb = hex_rgb(PALETTE[idx][1]) if idx < len(PALETTE) else (255, 0, 255)
            row += bytes(rgb + (255,)) * CELL
        rows.append(b"\x00" + bytes(row))

    def chunk(tag, data):
        body = tag + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", TEX, TEX, 8, 6, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as fh:
        fh.write(png)


def output_dir():
    try:
        base = EXPORT_DIR or (bpy.path.abspath("//") if bpy.data.filepath else os.path.expanduser("~"))
        d = os.path.join(base, "CampDemiSoul_Forge_Export")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception as exc:
        print("Could not create export folder:", exc)
        return None


OUT = output_dir()
PNG_PATH = None
if OUT:
    try:
        PNG_PATH = os.path.join(OUT, "DemiSoul_Palette_v2.png")
        write_palette_png(PNG_PATH)
    except Exception as exc:
        print("Could not write palette PNG:", exc)
        PNG_PATH = None


def make_material(png_path):
    mat = bpy.data.materials.get("DemiSoul_Palette_v2") or bpy.data.materials.new("DemiSoul_Palette_v2")
    mat.use_nodes = True
    nt = mat.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Roughness"].default_value = 1.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    if png_path:
        tex = nt.nodes.new("ShaderNodeTexImage")
        img = bpy.data.images.load(png_path, check_existing=True)
        img.reload()
        tex.image = img
        tex.interpolation = "Closest"
        nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


MAT = make_material(PNG_PATH)


def clear_collection(name):
    col = bpy.data.collections.get(name)
    if not col:
        return
    for obj in list(col.objects):
        me = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if me is not None and me.users == 0:
            bpy.data.meshes.remove(me)
    bpy.data.collections.remove(col)


clear_collection(COLLECTION_NAME)
COL = bpy.data.collections.new(COLLECTION_NAME)
bpy.context.scene.collection.children.link(COL)


# ------------------------------ MESH SINK ------------------------------------
# A Sink wraps a bmesh and applies a transform stack to everything built into it,
# so a banner/wall/rack can be built once facing -Y and placed anywhere with
#   with bm.at((x, y, z), rz=angle): ...
class _Verts:
    def __init__(self, k):
        self.k = k

    def new(self, co):
        return self.k.bm.verts.new(self.k.M @ Vector(co))


class _Faces:
    def __init__(self, k):
        self.k = k

    def new(self, vs):
        return self.k.bm.faces.new(vs)


class Sink:
    def __init__(self):
        self.bm = bmesh.new()
        self.M = Matrix.Identity(4)
        self._stack = []
        self.verts = _Verts(self)
        self.faces = _Faces(self)

    def tf(self, p):
        return self.M @ Vector(p)

    def empty(self):
        return len(self.bm.faces) == 0

    @contextmanager
    def at(self, loc=(0, 0, 0), rz=0.0, rx=0.0):
        self._stack.append(self.M)
        self.M = (self.M @ Matrix.Translation(Vector(loc))
                  @ Matrix.Rotation(rz, 4, "Z") @ Matrix.Rotation(rx, 4, "X"))
        try:
            yield self
        finally:
            self.M = self._stack.pop()


class Extras:
    """Companion meshes of a station/static: <name>_Glow (Neon), <name>_Water, <name>_Turntable..."""

    def __init__(self):
        self.d = {}

    def get(self, suffix):
        if suffix not in self.d:
            self.d[suffix] = Sink()
        return self.d[suffix]

    @property
    def glow(self):
        return self.get("_Glow")

    @property
    def water(self):
        return self.get("_Water")


# ------------------------------ PRIMITIVES -----------------------------------
def T(c):
    return Matrix.Translation(Vector(c))


ROT_X90 = Matrix.Rotation(math.pi / 2, 4, "X")     # local +Z -> -Y (faces the viewer)
ROT_Y90 = Matrix.Rotation(math.pi / 2, 4, "Y")     # local +Z -> +X


def add_face(bm, vs, ref, color):
    """Create a face wound so its normal points away from `ref` (an interior point)."""
    p = [v.co for v in vs]
    n = (p[1] - p[0]).cross(p[2] - p[1])
    cen = sum(p, Vector((0, 0, 0))) / len(p)
    r = bm.tf(ref) if hasattr(bm, "tf") else Vector(ref)
    if n.dot(cen - r) < 0:
        vs = vs[::-1]
    try:
        f = bm.faces.new(vs)
    except ValueError:
        return None
    f.material_index = color
    return f


_SIGNS = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]


def _ordered(a, sg):
    b1, b2 = [i for i in range(3) if i != a]
    cs = [S for S in _SIGNS if S[a] == sg]
    cs.sort(key=lambda S: math.atan2(S[b2], S[b1]))
    return cs


def box(bm, c, s, color, rot=0.0, ch=0.0):
    """Box centred at c, size s=(x,y,z), optional Z rotation and chamfer `ch`."""
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    half = (hx, hy, hz)
    M = T(c) @ Matrix.Rotation(rot, 4, "Z")
    ref = Vector(c)
    if ch <= 0:
        V = {S: bm.verts.new(M @ Vector((S[0] * hx, S[1] * hy, S[2] * hz))) for S in _SIGNS}
        for a in range(3):
            for sg in (-1, 1):
                add_face(bm, [V[S] for S in _ordered(a, sg)], ref, color)
        return
    k = min(ch, 0.9 * min(hx, hy, hz))
    V = {}
    for a in range(3):
        for S in _SIGNS:
            p = [S[i] * (half[i] - k) for i in range(3)]
            p[a] = S[a] * half[a]
            V[(a, S)] = bm.verts.new(M @ Vector(p))
    for a in range(3):
        for sg in (-1, 1):
            add_face(bm, [V[(a, S)] for S in _ordered(a, sg)], ref, color)
    for a, b in ((0, 1), (0, 2), (1, 2)):
        c3 = 3 - a - b
        for sa in (-1, 1):
            for sb in (-1, 1):
                S1 = [0, 0, 0]
                S2 = [0, 0, 0]
                S1[a] = S2[a] = sa
                S1[b] = S2[b] = sb
                S1[c3], S2[c3] = -1, 1
                S1, S2 = tuple(S1), tuple(S2)
                add_face(bm, [V[(a, S1)], V[(a, S2)], V[(b, S2)], V[(b, S1)]], ref, color)
    for S in _SIGNS:
        add_face(bm, [V[(0, S)], V[(1, S)], V[(2, S)]], ref, color)


def sbeam(bm, a, b, w, d, color):
    """Square-section beam from a to b (w x d cross-section)."""
    a, b = Vector(a), Vector(b)
    v = b - a
    L = v.length
    if L < 1e-6:
        return
    up = "Y" if abs(v.normalized().y) < 0.99 else "X"
    M = T(a) @ v.to_track_quat("Z", up).to_matrix().to_4x4()
    V = {S: bm.verts.new(M @ Vector((S[0] * w / 2, S[1] * d / 2, (S[2] + 1) * L / 2))) for S in _SIGNS}
    ref = (a + b) / 2
    for ax in range(3):
        for sg in (-1, 1):
            add_face(bm, [V[S] for S in _ordered(ax, sg)], ref, color)


def quad_slab(bm, pts, th, color):
    """Four points (top surface) extruded downward by th. Used for roofs and awnings."""
    P = [Vector(p) for p in pts]
    n = (P[1] - P[0]).cross(P[3] - P[0]).normalized()
    if n.z < 0:
        n = -n
    Bt = [p - n * th for p in P]
    vt = [bm.verts.new(p) for p in P]
    vb = [bm.verts.new(p) for p in Bt]
    ref = sum(P + Bt, Vector((0, 0, 0))) / 8
    add_face(bm, vt, ref, color)
    add_face(bm, vb, ref, color)
    for i in range(4):
        j = (i + 1) % 4
        add_face(bm, [vt[i], vt[j], vb[j], vb[i]], ref, color)


def frustum(bm, M, r0, r1, h, color, segs=8, jitter=0.0, rot=0.0):
    """Cylinder/cone along local +Z from M's origin. r1~0 makes a point."""
    apex = r1 <= 0.0005
    bot, top = [], []
    for j in range(segs):
        a = rot + math.tau * j / segs
        ca, sa = math.cos(a), math.sin(a)
        k0 = 1.0 + (rng.uniform(-jitter, jitter) if jitter else 0.0)
        bot.append(bm.verts.new(M @ Vector((r0 * k0 * ca, r0 * k0 * sa, 0.0))))
        if not apex:
            k1 = 1.0 + (rng.uniform(-jitter, jitter) if jitter else 0.0)
            top.append(bm.verts.new(M @ Vector((r1 * k1 * ca, r1 * k1 * sa, h))))
    ref = M @ Vector((0, 0, h * 0.5))
    if apex:
        tip = bm.verts.new(M @ Vector((0, 0, h)))
        for j in range(segs):
            add_face(bm, [bot[j], bot[(j + 1) % segs], tip], ref, color)
    else:
        for j in range(segs):
            k = (j + 1) % segs
            add_face(bm, [bot[j], bot[k], top[k], top[j]], ref, color)
        add_face(bm, top, ref, color)
    add_face(bm, bot, ref, color)


def beam(bm, a, b, r0, r1, color, segs=6):
    a, b = Vector(a), Vector(b)
    d = b - a
    L = d.length
    if L < 1e-6:
        return
    up = "Y" if abs(d.normalized().y) < 0.99 else "X"
    M = T(a) @ d.to_track_quat("Z", up).to_matrix().to_4x4()
    frustum(bm, M, r0, r1, L, color, segs)


def blob(bm, c, r, color, segs=6, rings=4, jitter=0.0, rot=0.0):
    rx, ry, rz = r
    ref = Vector(c)
    top = bm.verts.new((c[0], c[1], c[2] + rz))
    bot = bm.verts.new((c[0], c[1], c[2] - rz))
    rows = []
    for i in range(1, rings):
        phi = math.pi * i / rings
        row = []
        for j in range(segs):
            th = rot + math.tau * j / segs
            k = 1.0 + (rng.uniform(-jitter, jitter) if jitter else 0.0)
            row.append(bm.verts.new((c[0] + rx * math.sin(phi) * math.cos(th) * k,
                                     c[1] + ry * math.sin(phi) * math.sin(th) * k,
                                     c[2] + rz * math.cos(phi) * k)))
        rows.append(row)
    for j in range(segs):
        k = (j + 1) % segs
        add_face(bm, [top, rows[0][j], rows[0][k]], ref, color)
        add_face(bm, [bot, rows[-1][j], rows[-1][k]], ref, color)
    for a, b in zip(rows[:-1], rows[1:]):
        for j in range(segs):
            k = (j + 1) % segs
            add_face(bm, [a[j], b[j], b[k], a[k]], ref, color)


def ring(bm, M, r_out, r_in, th, color, segs=16):
    rm = (r_out + r_in) / 2
    ob, ib, ot, it = [], [], [], []
    for j in range(segs):
        a = math.tau * j / segs
        ca, sa = math.cos(a), math.sin(a)
        ob.append(bm.verts.new(M @ Vector((r_out * ca, r_out * sa, 0))))
        ib.append(bm.verts.new(M @ Vector((r_in * ca, r_in * sa, 0))))
        ot.append(bm.verts.new(M @ Vector((r_out * ca, r_out * sa, th))))
        it.append(bm.verts.new(M @ Vector((r_in * ca, r_in * sa, th))))
    for j in range(segs):
        k = (j + 1) % segs
        am = math.tau * (j + 0.5) / segs
        ref = M @ Vector((rm * math.cos(am), rm * math.sin(am), th / 2))
        add_face(bm, [ob[j], ob[k], ot[k], ot[j]], ref, color)
        add_face(bm, [ib[j], ib[k], it[k], it[j]], ref, color)
        add_face(bm, [ot[j], ot[k], it[k], it[j]], ref, color)
        add_face(bm, [ob[j], ob[k], ib[k], ib[j]], ref, color)


def prism(bm, pts, c, sc, t, color, mx=1, flat=False):
    """Extruded polygon in the XZ plane facing -Y. flat=True builds only the front face
    (for decals/emblems glued to cloth or walls - saves two thirds of the triangles)."""
    P = [(mx * x * sc, z * sc) for x, z in pts]
    n = len(P)
    area = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
    if abs(area) < 1e-9:
        return
    ccw = area > 0
    f = [bm.verts.new((c[0] + x, c[1] - t / 2, c[2] + z)) for x, z in P]

    def new(vs):
        try:
            fc = bm.faces.new(vs)
            fc.material_index = color
        except ValueError:
            pass

    new(f if ccw else f[::-1])
    if flat:
        return
    b = [bm.verts.new((c[0] + x, c[1] + t / 2, c[2] + z)) for x, z in P]
    new(b[::-1] if ccw else b)
    for i in range(n):
        j = (i + 1) % n
        new([f[j], f[i], b[i], b[j]] if ccw else [f[i], f[j], b[j], b[i]])


def stroke(bm, pts, c, w, color, depth=0.08, flat=False):
    """Polyline stroke (x,z relative to c) with filled joints; used for lettering and insignia."""
    hw = w / 2
    for a, b in zip(pts[:-1], pts[1:]):
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dz)
        if L < 1e-6:
            continue
        nx, nz = -dz / L * hw, dx / L * hw
        prism(bm, [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz),
                   (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)], c, 1.0, depth, color, flat=flat)
    for px, pz in pts:
        prism(bm, [(px - hw, pz), (px, pz + hw), (px + hw, pz), (px, pz - hw)], c, 1.0, depth, color, flat=flat)


# ------------------------------ EMBLEMS & LETTERING --------------------------
HEAD = [(-0.40, 0.28), (0.40, 0.28), (0.46, 0.02), (0.26, -0.40), (0.0, -0.52), (-0.26, -0.40), (-0.46, 0.02)]
HORN = [(-0.28, 0.18), (-0.66, 0.06), (-0.98, 0.18), (-1.12, 0.48), (-1.06, 0.86), (-0.92, 1.04),
        (-0.86, 0.74), (-0.84, 0.50), (-0.64, 0.30), (-0.30, 0.34)]
EAR = [(-0.46, 0.02), (-0.90, 0.10), (-0.80, -0.10), (-0.46, -0.10)]
EYE = [(-0.34, 0.06), (-0.10, -0.02), (-0.10, 0.08), (-0.34, 0.14)]
MUZZLE = [(-0.18, -0.28), (0.18, -0.28), (0.15, -0.36), (-0.15, -0.36)]


def emblem(bm, c, sc, light, dark, t=0.08, flat=False):
    """Camp DemiSoul bull. c = centre. flat=True -> decal (front faces only)."""
    fy = c[1] - t * 0.45
    for mx in (1, -1):
        prism(bm, HORN, c, sc, t, light, mx, flat)
        prism(bm, EAR, c, sc, t, light, mx, flat)
        prism(bm, EYE, (c[0], fy, c[2]), sc, t * 0.6, dark, mx, flat)
    prism(bm, HEAD, c, sc, t, light, 1, flat)
    prism(bm, MUZZLE, (c[0], fy, c[2]), sc, t * 0.6, dark, 1, flat)


def _tri(bm, a, d, n, back, half, c, s, t, color, flat):
    """Pointed blade/spear tip: triangle whose point is at `a`, pointing along d."""
    base = (a[0] - d[0] * back, a[1] - d[1] * back)
    prism(bm, [(base[0] + n[0] * half, base[1] + n[1] * half), a, (base[0] - n[0] * half, base[1] - n[1] * half)],
          c, s, t, color, 1, flat)


def insignia(bm, kind, c, s, color, flat=True, dark=C.MAROON, t=0.04):
    """The three crests of the district (all face -Y, centred on c, ~1.6*s across):
         'bull'   - Camp DemiSoul crest      -> camp-wide things (gate, tower, shield wall, pediments, floors)
         'forge'  - hammer crossed w/ sword  -> everything that belongs to the Forge
         'armory' - round shield + crossed spears -> everything that belongs to the Armory
    flat=True builds a decal (front faces only)."""
    if kind == "bull":
        emblem(bm, c, s, color, dark, t=t, flat=flat)
        return

    def S(p):
        return (p[0] * s, p[1] * s)

    def line(a, b, w):
        stroke(bm, [S(a), S(b)], c, w * s, color, t, flat)

    def unit(a, b):
        dx, dz = b[0] - a[0], b[1] - a[1]
        L = math.hypot(dx, dz)
        return (dx / L, dz / L)

    if kind == "forge":
        # sword: hilt lower-left, point upper-right
        H, Tp = (-0.58, -0.70), (0.66, 0.74)
        d = unit(H, Tp)
        n = (-d[1], d[0])
        G = (H[0] + d[0] * 0.34, H[1] + d[1] * 0.34)
        line(H, (H[0] + d[0] * 0.30, H[1] + d[1] * 0.30), 0.10)                       # grip
        line((G[0] - n[0] * 0.27, G[1] - n[1] * 0.27), (G[0] + n[0] * 0.27, G[1] + n[1] * 0.27), 0.09)   # crossguard
        blade_end = (Tp[0] - d[0] * 0.24, Tp[1] - d[1] * 0.24)
        line((G[0] + d[0] * 0.04, G[1] + d[1] * 0.04), blade_end, 0.13)               # blade
        _tri(bm, S(Tp), d, n, 0.26 * s, 0.065 * s, c, 1.0, t, color, flat)           # point
        prism(bm, [(S(H)[0] - 0.06 * s, S(H)[1]), (S(H)[0], S(H)[1] + 0.06 * s), (S(H)[0] + 0.06 * s, S(H)[1]),
                   (S(H)[0], S(H)[1] - 0.06 * s)], c, 1.0, t, color, 1, flat)         # pommel
        # hammer: head upper-left, haft lower-right (crosses the sword at the centre)
        E, Hc = (0.62, -0.70), (-0.46, 0.50)
        e = unit(E, Hc)
        n2 = (-e[1], e[0])
        line(E, (Hc[0] - e[0] * 0.18, Hc[1] - e[1] * 0.18), 0.11)                     # haft
        line((Hc[0] - n2[0] * 0.32, Hc[1] - n2[1] * 0.32), (Hc[0] + n2[0] * 0.32, Hc[1] + n2[1] * 0.32), 0.30)  # head
    else:   # armory: two spears crossed behind a round shield
        for sx in (-1, 1):
            a, b = (-sx * 0.62, -0.84), (sx * 0.62, 0.84)
            d = unit(a, b)
            n = (-d[1], d[0])
            line(a, (b[0] - d[0] * 0.2, b[1] - d[1] * 0.2), 0.075)
            _tri(bm, S((b[0] + d[0] * 0.20, b[1] + d[1] * 0.20)), d, n, 0.40 * s, 0.09 * s, c, 1.0, t, color, flat)
        for r, col, off in ((0.42, color, 0.010), (0.33, dark, 0.020), (0.22, color, 0.030), (0.09, dark, 0.040)):
            pts = [(r * math.cos(math.tau * (i + 0.5) / 8), r * math.sin(math.tau * (i + 0.5) / 8)) for i in range(8)]
            prism(bm, pts, (c[0], c[1] - off, c[2]), s, t, col, 1, flat)


GLYPHS = {
    "A": (0.70, [[(0.0, 0.0), (0.35, 1.0), (0.70, 0.0)], [(0.14, 0.36), (0.56, 0.36)]]),
    "B": (0.62, [[(0.0, 0.0), (0.0, 1.0), (0.55, 0.80), (0.0, 0.52), (0.60, 0.28), (0.0, 0.0)]]),
    "C": (0.65, [[(0.62, 0.95), (0.08, 0.5), (0.62, 0.05)]]),
    "D": (0.65, [[(0.0, 0.0), (0.0, 1.0), (0.65, 0.5), (0.0, 0.0)]]),
    "E": (0.60, [[(0.6, 1.0), (0.0, 1.0), (0.0, 0.0), (0.6, 0.0)], [(0.0, 0.5), (0.45, 0.5)]]),
    "F": (0.58, [[(0.0, 0.0), (0.0, 1.0), (0.58, 1.0)], [(0.0, 0.52), (0.44, 0.52)]]),
    "G": (0.65, [[(0.62, 0.92), (0.08, 0.7), (0.08, 0.3), (0.62, 0.08), (0.62, 0.46), (0.36, 0.46)]]),
    "H": (0.62, [[(0.0, 0.0), (0.0, 1.0)], [(0.62, 0.0), (0.62, 1.0)], [(0.0, 0.5), (0.62, 0.5)]]),
    "I": (0.10, [[(0.05, 0.0), (0.05, 1.0)]]),
    "L": (0.55, [[(0.0, 1.0), (0.0, 0.0), (0.55, 0.0)]]),
    "M": (0.70, [[(0.0, 0.0), (0.0, 1.0), (0.35, 0.45), (0.70, 1.0), (0.70, 0.0)]]),
    "N": (0.62, [[(0.0, 0.0), (0.0, 1.0), (0.62, 0.0), (0.62, 1.0)]]),
    "O": (0.70, [[(0.35, 1.0), (0.70, 0.5), (0.35, 0.0), (0.0, 0.5), (0.35, 1.0)]]),
    "P": (0.65, [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.65, 0.76), (0.0, 0.52)]]),
    "R": (0.65, [[(0.0, 0.0), (0.0, 1.0), (0.62, 0.80), (0.0, 0.54)], [(0.22, 0.54), (0.65, 0.0)]]),
    "S": (0.60, [[(0.6, 0.95), (0.04, 0.8), (0.04, 0.62), (0.56, 0.38), (0.56, 0.2), (0.0, 0.05)]]),
    "T": (0.70, [[(0.0, 1.0), (0.70, 1.0)], [(0.35, 1.0), (0.35, 0.0)]]),
    "U": (0.70, [[(0.0, 1.0), (0.0, 0.22), (0.35, 0.0), (0.70, 0.22), (0.70, 1.0)]]),
    "V": (0.70, [[(0.0, 1.0), (0.35, 0.0), (0.70, 1.0)]]),
    "W": (0.85, [[(0.0, 1.0), (0.21, 0.0), (0.425, 0.62), (0.64, 0.0), (0.85, 1.0)]]),
    "Y": (0.70, [[(0.0, 1.0), (0.35, 0.5), (0.70, 1.0)], [(0.35, 0.5), (0.35, 0.0)]]),
}


def text(bm, s, c, h, color, depth=0.08, stroke_w=0.16, gap=0.38, space=0.8, flat=False):
    """Raised angular lettering facing -Y. c = centre of the text block, h = letter height."""
    x, spans = 0.0, []
    for ch in s:
        if ch == " ":
            x += space
        else:
            spans.append((ch, x))
            x += GLYPHS[ch][0] + gap
    total = x - gap
    x0 = c[0] - total * h / 2
    for ch, ox in spans:
        for line in GLYPHS[ch][1]:
            pts = [(x0 + (ox + px) * h - c[0], (pz - 0.5) * h) for px, pz in line]
            stroke(bm, pts, c, stroke_w * h, color, depth, flat)


# ============================ BAKE / PLACE / REGISTRY ========================
STATIONS = []        # interaction anchors  -> JSON + Lua
COLLIDERS = []       # simple collision boxes -> JSON + Lua
OBJECTS = []         # every Blender object created
MESHES = {}          # unique mesh name -> triangle count
SHARED = {}          # share-key -> (mesh, bbox, {suffix: mesh})


class Frame:
    """A building's placement: local (x, y) -> world. Front of every building is local -Y."""

    def __init__(self, cx, cy, rot=0.0):
        self.cx, self.cy, self.rot = cx, cy, rot

    def w(self, lx, ly):
        c, s = math.cos(self.rot), math.sin(self.rot)
        return (self.cx + lx * c - ly * s, self.cy + lx * s + ly * c)


FR = Frame(0.0, 0.0, 0.0)


def use_frame(f):
    global FR
    FR = f


def bake(name, sink, trim=True):
    """Finish a Sink into a triangulated, UV'd, stud-scaled mesh. Returns (mesh, bbox_in_metres)."""
    bm = sink.bm
    bm.normal_update()
    if trim:
        kill = []
        for f in bm.faces:
            z = f.calc_center_median().z
            if z < -0.02 or (f.normal.z < -0.9 and z < 0.05):
                kill.append(f)
        if kill:
            bmesh.ops.delete(bm, geom=kill, context="FACES")
    bmesh.ops.triangulate(bm, faces=bm.faces[:], quad_method="BEAUTY", ngon_method="EAR_CLIP")
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        i = f.material_index
        u = ((i % GRID) + 0.5) / GRID
        v = ((i // GRID) + 0.5) / GRID
        for l in f.loops:
            l[uv].uv = (u, v)
        f.material_index = 0
    pts = [v.co.copy() for v in bm.verts]
    if pts:
        mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    else:
        mn = mx = Vector((0, 0, 0))
    for vert in bm.verts:
        vert.co *= STUD_SCALE
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT)
    MESHES[name] = len(me.polygons)
    return me, (mn, mx)


def spawn(name, me, loc, rz):
    obj = bpy.data.objects.new(name, me)
    COL.objects.link(obj)
    obj.location = tuple(v * STUD_SCALE for v in loc)
    obj.rotation_euler = (0.0, 0.0, rz)
    OBJECTS.append(obj)
    return obj


def static(name, builder, trim=True):
    """Build a whole structure in the current building frame. Object origin = frame origin."""
    main, ex = Sink(), Extras()
    builder(main, ex)
    if not main.empty():
        me, _ = bake(name, main, trim)
        spawn(name, me, (FR.cx, FR.cy, 0.0), FR.rot)
    for sfx, s in ex.d.items():
        if not s.empty():
            me, _ = bake(name + sfx, s, trim)
            spawn(name + sfx, me, (FR.cx, FR.cy, 0.0), FR.rot)


def collide(name, lx, ly, lz, sx, sy, sz, lrot=0.0):
    """Record an invisible collision box (local to the current frame, centre + size in metres)."""
    wx, wy = FR.w(lx, ly)
    COLLIDERS.append(dict(name=name, pos=(wx, wy, lz), size=(sx, sy, sz), rot=FR.rot + lrot))


def station(name, kind, label, builder, lx, ly, lz=0.0, lrot=0.0, share=None, prompt_h=1.3,
            collider=True, colliders=None, **meta):
    """Build an interactive piece as its own mesh (origin = floor centre) and register it."""
    wx, wy = FR.w(lx, ly)
    rz = FR.rot + lrot
    if share and share in SHARED:
        me, bb, extras = SHARED[share]
        spawn(name, me, (wx, wy, lz), rz)
        for sfx, eme in extras.items():
            spawn(name + sfx, eme, (wx, wy, lz), rz)
    else:
        main, ex = Sink(), Extras()
        builder(main, ex)
        me, bb = bake(name, main)
        spawn(name, me, (wx, wy, lz), rz)
        extras = {}
        for sfx, s in ex.d.items():
            if s.empty():
                continue
            eme, _ = bake(name + sfx, s)
            extras[sfx] = eme
            spawn(name + sfx, eme, (wx, wy, lz), rz)
        if share:
            SHARED[share] = (me, bb, extras)
    STATIONS.append(dict(name=name, kind=kind, label=label, pos=(wx, wy, lz + prompt_h), rot=rz, **meta))
    cr, sr = math.cos(rz), math.sin(rz)

    def add_box(cx, cy, cz, sx, sy, sz):
        COLLIDERS.append(dict(name=name + "_Collider", pos=(wx + cx * cr - cy * sr, wy + cx * sr + cy * cr, lz + cz),
                              size=(sx, sy, sz), rot=rz))

    if colliders:
        for (cx, cy, cz, sx, sy, sz) in colliders:
            add_box(cx, cy, cz, sx, sy, sz)
    elif collider:
        mn, mx = bb
        c = (mn + mx) / 2
        s = mx - mn
        add_box(c.x, c.y, c.z, s.x, s.y, s.z)


def marker(name, kind, label, lx, ly, lz, **meta):
    wx, wy = FR.w(lx, ly)
    STATIONS.append(dict(name=name, kind=kind, label=label, pos=(wx, wy, lz), rot=FR.rot, **meta))


# ============================ ARCHITECTURE COMPONENTS ========================
def wall(bm, axis, a0, a1, c, z0, z1, t, color, openings=(), ch=0.0, name=None):
    """Wall along `axis` ('x' or 'y') spanning a0..a1 at cross-coordinate c, with rectangular
    openings [(oa0, oa1, oz0, oz1)]. Records colliders when `name` is given."""
    cuts = sorted(openings)
    segs, cur = [], a0
    for o in cuts:
        if o[0] > cur:
            segs.append((cur, o[0]))
        cur = o[1]
    if a1 > cur:
        segs.append((cur, a1))

    def B(m0, m1, za, zb, solid):
        if m1 - m0 < 1e-3 or zb - za < 1e-3:
            return
        mid, ln, zc, hz = (m0 + m1) / 2, m1 - m0, (za + zb) / 2, zb - za
        if axis == "x":
            box(bm, (mid, c, zc), (ln, t, hz), color, ch=ch)
            if name and solid:
                collide(name, mid, c, zc, ln, t, hz)
        else:
            box(bm, (c, mid, zc), (t, ln, hz), color, ch=ch)
            if name and solid:
                collide(name, c, mid, zc, t, ln, hz)

    for s0, s1 in segs:
        B(s0, s1, z0, z1, True)
    for oa0, oa1, oz0, oz1 in cuts:
        B(oa0, oa1, z0, oz0, True)
        B(oa0, oa1, oz1, z1, False)


def timber_post(bm, x, y, h, s=0.7, name=None):
    box(bm, (x, y, 0.25), (s + 0.5, s + 0.5, 0.5), C.STONE, ch=0.06)
    box(bm, (x, y, 0.5 + h / 2), (s, s, h), C.WOOD, ch=0.05)
    box(bm, (x, y, 0.5 + h + 0.12), (s + 0.3, s + 0.3, 0.24), C.WOOD_LIGHT, ch=0.04)
    for dz in (1.0, h - 1.0):
        box(bm, (x, y, 0.5 + dz), (s + 0.06, s + 0.06, 0.10), C.IRON)
    if name:
        collide(name, x, y, (0.5 + h) / 2, s + 0.5, s + 0.5, 0.5 + h)


def stone_column(bm, x, y, h, r=0.62, name=None):
    """Classical column: plinth, tapered shaft with bronze bands, capital + abacus. Height = h + 1.15."""
    frustum(bm, T((x, y, 0)), r * 1.55, r * 1.45, 0.35, C.STONE_LIGHT, segs=12)
    frustum(bm, T((x, y, 0.35)), r * 1.12, r * 1.12, 0.25, C.MARBLE, segs=12)
    frustum(bm, T((x, y, 0.60)), r * 0.95, r * 0.80, h, C.STONE_LIGHT, segs=12)
    for dz in (1.2, h - 0.5):
        frustum(bm, T((x, y, 0.60 + dz)), r * 0.93 - 0.02 * dz / h * r, r * 0.93 - 0.02 * dz / h * r, 0.12, C.BRONZE, segs=12)
    frustum(bm, T((x, y, 0.60 + h)), r * 0.85, r * 1.35, 0.35, C.MARBLE, segs=12)
    box(bm, (x, y, 0.60 + h + 0.35 + 0.1), (r * 2.9, r * 2.9, 0.2), C.STONE_LIGHT, ch=0.03)
    if name:
        collide(name, x, y, (h + 1.15) / 2, r * 2.0, r * 2.0, h + 1.15)


def roof_slope(bm, la, lb, hb, ha, th, base, line, courses=6, tails=True, rafters=0.0):
    """One roof plane. la/lb = low edge points, ha/hb = high edge points (la<->ha, lb<->hb pair up).
    Shingle courses are raised strips; optional rafters underneath and rafter tails at the eave."""
    la, lb, hb, ha = Vector(la), Vector(lb), Vector(hb), Vector(ha)
    n = (lb - la).cross(ha - la).normalized()
    if n.z < 0:
        n = -n
    quad_slab(bm, [la, lb, hb, ha], th, base)
    for i in range(1, courses):
        t0 = i / courses
        t1 = t0 + 0.13 / courses
        p0, p1 = la + (ha - la) * t0, lb + (hb - lb) * t0
        q0, q1 = la + (ha - la) * t1, lb + (hb - lb) * t1
        quad_slab(bm, [p0 + n * 0.035, p1 + n * 0.035, q1 + n * 0.035, q0 + n * 0.035], 0.05, line)
    slope = (ha - la).normalized()
    if tails:
        length = (lb - la).length
        count = max(2, int(length / 1.5))
        for i in range(count + 1):
            u = i / count
            p = la + (lb - la) * u
            sbeam(bm, p - slope * 0.5 - n * (th + 0.08), p + slope * 0.9 - n * (th + 0.08), 0.16, 0.20, C.WOOD_LIGHT)
    if rafters:
        length = (lb - la).length
        count = max(2, int(length / rafters))
        for i in range(count + 1):
            u = i / count
            sbeam(bm, la + (lb - la) * u - n * (th + 0.1), ha + (hb - ha) * u - n * (th + 0.1), 0.16, 0.22, C.WOOD)
        for t in (0.33, 0.66):
            sbeam(bm, la + (ha - la) * t - n * (th + 0.2), lb + (hb - lb) * t - n * (th + 0.2), 0.14, 0.16, C.WOOD_DARK)


def truss(bm, y, half_span, z_plate, z_ridge, x_off=0.0):
    """King-post truss in the XZ plane at depth y, centred at x_off."""
    a, b, r = (x_off - half_span, y, z_plate), (x_off + half_span, y, z_plate), (x_off, y, z_ridge)
    sbeam(bm, a, b, 0.30, 0.36, C.WOOD)                                  # tie beam
    sbeam(bm, a, r, 0.26, 0.32, C.WOOD)
    sbeam(bm, b, r, 0.26, 0.32, C.WOOD)
    sbeam(bm, (x_off, y, z_plate), r, 0.26, 0.30, C.WOOD_DARK)           # king post
    zm = z_plate + (z_ridge - z_plate) * 0.45
    for s in (-1, 1):
        sbeam(bm, (x_off, y, zm), (x_off + s * half_span * 0.52, y, z_plate + (z_ridge - z_plate) * 0.0), 0.2, 0.24, C.WOOD_LIGHT)
        blob(bm, (x_off + s * half_span * 0.52, y, z_plate), (0.18, 0.2, 0.18), C.IRON, segs=5, rings=3)
    box(bm, (x_off, y, z_plate), (0.5, 0.42, 0.14), C.IRON)


def lantern(bm, ex, x, y, z, hang=0.0):
    """Hanging lantern. Glow part goes to the companion Neon mesh."""
    if hang > 0:
        sbeam(bm, (x, y, z), (x, y, z + hang), 0.05, 0.05, C.IRON)
    box(bm, (x, y, z - 0.05), (0.34, 0.34, 0.08), C.IRON)
    box(bm, (x, y, z + 0.40), (0.34, 0.34, 0.08), C.IRON)
    frustum(bm, T((x, y, z + 0.44)), 0.26, 0.0, 0.22, C.IRON, segs=4, rot=math.pi / 4)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(bm, (x + sx * 0.15, y + sy * 0.15, z + 0.17), (0.03, 0.03, 0.44), C.IRON)
    box(ex.glow, (x, y, z + 0.17), (0.24, 0.24, 0.34), C.GLOW)


def flame(ex, x, y, z, r=0.3, h=0.8):
    frustum(ex.glow, T((x, y, z)), r, 0.0, h, C.EMBER, segs=6)
    frustum(ex.glow, T((x, y, z)), r * 0.55, 0.0, h * 0.7, C.MOLTEN, segs=5)


def standing_brazier(bm, ex, x, y, h=1.6):
    frustum(bm, T((x, y, 0)), 0.45, 0.36, 0.28, C.STONE_DARK, segs=8)
    frustum(bm, T((x, y, 0.28)), 0.17, 0.12, h - 0.5, C.BRONZE_DARK, segs=8)
    frustum(bm, T((x, y, h - 0.22)), 0.15, 0.55, 0.52, C.BRONZE, segs=8)
    for i in range(3):
        a = math.tau * i / 3
        beam(bm, (x, y, 0.35), (x + 0.5 * math.cos(a), y + 0.5 * math.sin(a), 0.0), 0.05, 0.04, C.BRONZE_DARK, 4)
    flame(ex, x, y, h + 0.30, 0.34, 0.9)


def wall_sconce(bm, ex, x, y, z, facing=-1):
    box(bm, (x, y, z), (0.16, 0.2, 0.5), C.IRON)
    frustum(bm, T((x, y + facing * 0.1, z + 0.2)), 0.1, 0.22, 0.24, C.IRON, segs=6)
    flame(ex, x, y + facing * 0.1, z + 0.44, 0.15, 0.45)


def barrel(bm, x, y, z=0.0, r=0.45, h=1.0):
    frustum(bm, T((x, y, z)), r * 0.84, r, h / 2, C.WOOD, segs=10)
    frustum(bm, T((x, y, z + h / 2)), r, r * 0.84, h / 2, C.WOOD, segs=10)
    for dz in (0.14 * h, 0.86 * h):
        rr = r * (0.84 + 0.16 * (1 - abs(dz / h - 0.5) * 2) ) + 0.02
        frustum(bm, T((x, y, z + dz - 0.04)), rr, rr, 0.08, C.IRON, segs=10)


def crate(bm, x, y, z=0.0, s=0.9, rot=0.0):
    box(bm, (x, y, z + s / 2), (s, s, s), C.WOOD_LIGHT, rot=rot, ch=0.03)
    for dx in (-1, 1):
        box(bm, (x + dx * s * 0.34 * math.cos(rot), y + dx * s * 0.34 * math.sin(rot), z + s / 2),
            (0.09, s + 0.03, s + 0.03), C.WOOD_DARK, rot=rot)


def logs(bm, x, y, rot=0.0, n=6):
    with bm.at((x, y, 0), rz=rot):
        for i in range(n):
            row, col = (0, i) if i < 3 else (1, i - 3 + 0.5)
            frustum(bm, T((col * 0.42 - 0.42, 0.8, 0.22 + row * 0.36)) @ ROT_X90, 0.19, 0.19, 1.6, C.WOOD, segs=6)


def ingots(bm, x, y, z, rows=3):
    for r in range(rows):
        for c in range(rows - r):
            box(bm, (x + (c - (rows - r - 1) / 2) * 0.42, y, z + 0.09 + r * 0.17), (0.38, 0.2, 0.15), C.IRON_LIGHT, ch=0.02)


def ore_heap(bm, x, y, color, r=0.7, n=7):
    for i in range(n):
        a = rng.uniform(0, math.tau)
        d = rng.uniform(0, r * 0.7)
        s = rng.uniform(0.18, 0.3)
        blob(bm, (x + d * math.cos(a), y + d * math.sin(a), 0.1 + (r - d) * 0.25), (s, s, s * 0.8),
             color, segs=5, rings=3, jitter=0.2)


def planter(bm, x, y, w=2.2, d=0.9):
    box(bm, (x, y, 0.3), (w, d, 0.6), C.STONE_LIGHT, ch=0.05)
    box(bm, (x, y, 0.62), (w - 0.2, d - 0.2, 0.06), C.DIRT)
    for i in range(int(w / 0.7)):
        bx = x - w / 2 + 0.45 + i * 0.7
        blob(bm, (bx, y, 0.95), (0.42, 0.4, 0.38), rng.choice([C.LEAF_MID, C.LEAF_DARK, C.LEAF_LIGHT]),
             segs=6, rings=3, jitter=0.15)


# ----------------------------- WEAPONS & SHIELDS -----------------------------
def sword(bm, x, y, z, length=1.1, grip=C.LEATHER, guard=C.GOLD, blade=C.STEEL, flat=False):
    """Upright sword facing -Y, hilt at z, point up."""
    bl = length * 0.78
    prism(bm, [(-0.055, 0.0), (0.055, 0.0), (0.05, bl * 0.9), (0.0, bl), (-0.05, bl * 0.9)], (x, y, z + length * 0.22), 1.0,
          0.03, blade, flat=False)
    box(bm, (x, y, z + length * 0.22), (0.32, 0.07, 0.06), guard)
    box(bm, (x, y, z + length * 0.10), (0.06, 0.06, length * 0.2), grip)
    blob(bm, (x, y, z + 0.02), (0.07, 0.07, 0.07), guard, segs=5, rings=3)


def spear(bm, x, y, z, length=2.6, lean=(0.0, 0.0)):
    top = (x + lean[0] * length, y + lean[1] * length, z + length)
    beam(bm, (x, y, z), top, 0.035, 0.03, C.WOOD, 5)
    d = Vector(top) - Vector((x, y, z))
    d = d.normalized()
    tip = Vector(top) + d * 0.42
    beam(bm, top, tip, 0.07, 0.0, C.STEEL, 4)


def axe(bm, x, y, z, length=1.3):
    beam(bm, (x, y, z), (x, y, z + length), 0.035, 0.03, C.WOOD, 5)
    prism(bm, [(0, 0.0), (0.36, -0.08), (0.34, 0.34), (0, 0.22)], (x, y, z + length - 0.28), 1.0, 0.04, C.STEEL)


def shield(bm, c, r, face=C.MAROON, rim=C.BRONZE, motif="bull", motif_col=C.CREAM):
    """Round shield facing -Y, centre c."""
    with bm.at(c):
        frustum(bm, ROT_X90, r, r, 0.10, rim, segs=12)
        frustum(bm, T((0, -0.09, 0)) @ ROT_X90, r * 0.88, r * 0.88, 0.03, face, segs=12)
        ring(bm, T((0, -0.09, 0)) @ ROT_X90, r, r * 0.88, 0.05, rim, segs=12)
        blob(bm, (0, -0.15, 0), (r * 0.12, 0.06, r * 0.12), rim, segs=6, rings=3)
        insignia(bm, motif, (0, -0.125, 0), r * 0.40, motif_col, flat=True)


def helmet(bm, c, s=1.0, metal=C.BRONZE, crest=C.MAROON):
    x, y, z = c
    blob(bm, (x, y, z), (0.30 * s, 0.32 * s, 0.30 * s), metal, segs=8, rings=4)
    for sx in (-1, 1):
        box(bm, (x + sx * 0.27 * s, y - 0.06 * s, z - 0.14 * s), (0.05 * s, 0.26 * s, 0.34 * s), metal)
    box(bm, (x, y - 0.30 * s, z - 0.05 * s), (0.06 * s, 0.05 * s, 0.30 * s), metal)
    pts = [(-0.26, 0.20), (-0.12, 0.34), (0.06, 0.38), (0.24, 0.30), (0.34, 0.12), (0.38, -0.08)]
    for (y0, z0), (y1, z1) in zip(pts[:-1], pts[1:]):
        beam(bm, (x, y + y0 * s, z + z0 * s), (x, y + y1 * s, z + z1 * s), 0.055 * s, 0.055 * s, crest, 4)


def armor_suit(bm, tier="bronze", s=1.0, z0=0.0, base_z_pole=True):
    """Display armour on a stand, facing -Y. Origin at the stand's feet."""
    metal, trim, crest = {"bronze": (C.BRONZE, C.BRONZE_DARK, C.MAROON), "iron": (C.IRON_LIGHT, C.IRON, C.MAROON),
                          "steel": (C.STEEL, C.IRON_LIGHT, C.CREAM), "gold": (C.GOLD, C.BRONZE, C.MAROON)}[tier]
    if base_z_pole:
        beam(bm, (0, 0, z0), (0, 0, z0 + 1.45 * s), 0.07 * s, 0.07 * s, C.WOOD_DARK, 6)
        box(bm, (0, 0, z0 + 0.04), (0.8 * s, 0.6 * s, 0.08), C.WOOD_DARK, ch=0.02)
    for sx in (-1, 1):                                                                   # greaves + knees
        frustum(bm, T((sx * 0.17 * s, 0, z0 + 0.10)), 0.10 * s, 0.14 * s, 0.62 * s, metal, segs=7)
        blob(bm, (sx * 0.17 * s, -0.04 * s, z0 + 0.78 * s), (0.13 * s, 0.12 * s, 0.11 * s), trim, segs=6, rings=3)
    frustum(bm, T((0, 0, z0 + 0.84 * s)), 0.30 * s, 0.50 * s, 0.34 * s, trim, segs=10)    # skirt
    for i in range(10):                                                                  # pteryges strips
        a = math.tau * i / 10
        box(bm, (0.46 * s * math.cos(a), 0.46 * s * math.sin(a), z0 + 0.74 * s), (0.12 * s, 0.05 * s, 0.30 * s),
            C.LEATHER, rot=a + math.pi / 2)
    frustum(bm, T((0, 0, z0 + 1.15 * s)), 0.28 * s, 0.34 * s, 0.50 * s, metal, segs=10)   # cuirass
    frustum(bm, T((0, 0, z0 + 1.60 * s)), 0.34 * s, 0.22 * s, 0.30 * s, metal, segs=10)
    box(bm, (0, -0.30 * s, z0 + 1.42 * s), (0.2 * s, 0.04, 0.2 * s), C.GOLD)
    for sx in (-1, 1):                                                                   # pauldrons + vambraces
        blob(bm, (sx * 0.38 * s, 0, z0 + 1.82 * s), (0.17 * s, 0.17 * s, 0.12 * s), trim, segs=6, rings=3)
        beam(bm, (sx * 0.40 * s, 0, z0 + 1.76 * s), (sx * 0.62 * s, -0.12 * s, z0 + 1.30 * s), 0.07 * s, 0.06 * s, metal, 5)
    helmet(bm, (0, 0, z0 + 2.08 * s), s * 0.95, metal, crest)
    shield(bm, (0.78 * s, -0.12 * s, z0 + 1.30 * s), 0.42 * s, C.MAROON, trim, "armory", C.GOLD)
    spear(bm, -0.80 * s, -0.08 * s, z0 + 0.04, 2.9 * s)


# ============================ STATION BUILDERS ===============================
# Each builds around the station's floor centre (0,0,0); front = -Y; extras go to companion meshes.

def b_anvil(bm, ex):
    frustum(bm, T((0, 0, 0)), 0.52, 0.46, 0.62, C.WOOD, segs=10)
    frustum(bm, T((0, 0, 0)), 0.55, 0.55, 0.08, C.IRON, segs=10)
    frustum(bm, T((0, 0, 0.54)), 0.50, 0.50, 0.08, C.IRON, segs=10)
    box(bm, (0, 0, 0.68), (0.70, 0.42, 0.12), C.IRON, ch=0.02)            # foot
    box(bm, (0, 0, 0.82), (0.34, 0.26, 0.16), C.IRON)                     # waist
    box(bm, (0, 0, 0.96), (1.10, 0.40, 0.12), C.STEEL, ch=0.02)           # face
    frustum(bm, T((0.55, 0, 0.96)) @ ROT_Y90, 0.13, 0.03, 0.55, C.STEEL, segs=6)    # horn
    box(bm, (-0.62, 0, 0.93), (0.20, 0.34, 0.10), C.IRON)                 # heel
    box(bm, (-0.35, 0, 1.025), (0.07, 0.07, 0.012), C.COAL)               # hardy hole
    box(bm, (0.12, 0, 1.025), (0.05, 0.05, 0.012), C.COAL)                # pritchel hole


def b_trough(bm, ex):
    box(bm, (0, 0, 0.10), (3.0, 1.1, 0.14), C.WOOD_DARK)
    for sy in (-1, 1):
        box(bm, (0, sy * 0.50, 0.52), (3.0, 0.10, 0.84), C.WOOD, ch=0.02)
    for sx in (-1, 1):
        box(bm, (sx * 1.45, 0, 0.52), (0.10, 1.1, 0.84), C.WOOD, ch=0.02)
    for x in (-1.0, 0.0, 1.0):
        for sy in (-1, 1):
            box(bm, (x, sy * 0.52, 0.52), (0.10, 0.14, 0.86), C.IRON)
    for sx in (-1, 1):
        box(bm, (sx * 1.3, 0, 0.04), (0.35, 1.2, 0.08), C.STONE_DARK)
    box(ex.water, (0, 0, 0.80), (2.84, 0.9, 0.06), C.WATER)
    beam(bm, (1.2, -0.58, 0.96), (1.2, -0.58, 0.60), 0.03, 0.03, C.IRON, 4)   # dipper hook
    frustum(bm, T((1.2, -0.58, 0.56)), 0.1, 0.07, 0.1, C.IRON, segs=6)


def b_grind(bm, ex):
    for sx in (-1, 1):
        box(bm, (sx * 0.34, 0, 0.55), (0.10, 0.7, 1.1), C.WOOD, ch=0.02)
    box(bm, (0, 0, 0.28), (0.8, 0.12, 0.10), C.WOOD_DARK)
    frustum(bm, T((-0.12, 0, 0.98)) @ ROT_Y90, 0.62, 0.62, 0.24, C.STONE_LIGHT, segs=14)
    beam(bm, (-0.55, 0, 0.98), (0.62, 0, 0.98), 0.05, 0.05, C.IRON, 6)
    beam(bm, (0.62, 0, 0.98), (0.62, 0.38, 0.98), 0.04, 0.04, C.IRON, 5)
    beam(bm, (0.62, 0.38, 0.98), (0.84, 0.38, 0.98), 0.05, 0.05, C.WOOD, 5)
    box(bm, (0, 0.05, 0.14), (0.9, 0.9, 0.18), C.WOOD_DARK, ch=0.02)              # tray
    box(ex.water, (0, 0.05, 0.24), (0.7, 0.7, 0.03), C.WATER)
    box(bm, (0, -0.48, 0.80), (0.7, 0.10, 0.06), C.IRON)                          # tool rest
    sbeam(bm, (0, -0.48, 0.8), (0, -0.35, 0.5), 0.06, 0.06, C.IRON)


def b_furnace(bm, ex, side=1):
    """Great furnace 4.6 x 3.6, backs onto +Y wall. Bellows on the `side` flank."""
    box(bm, (0, 0, 0.10), (5.0, 4.0, 0.20), C.STONE_DARK)
    box(bm, (0, 0, 0.70), (4.6, 3.6, 1.0), C.STONE, ch=0.06)
    box(bm, (0, 0, 1.90), (4.0, 3.2, 1.4), C.STONE, ch=0.05)
    for z in (1.2, 2.6):
        box(bm, (0, 0, z), (4.7, 3.7, 0.10), C.BRONZE)
    box(bm, (0, -1.62, 1.75), (2.0, 0.06, 0.95), C.COAL)                          # fire mouth
    box(bm, (0, -1.68, 2.32), (2.5, 0.22, 0.26), C.STONE_LIGHT, ch=0.03)          # lintel
    for sx in (-1, 1):
        box(bm, (sx * 1.15, -1.66, 1.75), (0.30, 0.14, 1.0), C.STONE_LIGHT, ch=0.03)
    box(bm, (0, -1.66, 2.5), (2.0, 0.05, 0.06), C.IRON)
    box(ex.glow, (0, -1.60, 1.50), (1.8, 0.06, 0.55), C.EMBER)
    blob(ex.glow, (0, -1.58, 1.62), (0.7, 0.12, 0.35), C.MOLTEN, segs=6, rings=3)
    box(bm, (0, 0, 3.0), (3.5, 2.9, 0.6), C.STONE, ch=0.05)                       # corbelled hood
    box(bm, (0, 0.1, 3.5), (2.5, 2.2, 0.5), C.STONE, ch=0.05)
    box(bm, (0, 0.3, 4.15), (1.5, 1.5, 0.9), C.STONE_DARK, ch=0.04)               # flue
    shield(bm, (0, -1.46, 3.0), 0.46, C.MAROON, C.BRONZE, "forge", C.GOLD)
    sbeam(bm, (-1.7, -1.9, 0.0), (-1.7, -1.9, 1.6), 0.07, 0.07, C.IRON)            # poker + tongs rack
    box(bm, (-1.7, -1.9, 1.6), (0.2, 0.05, 0.05), C.IRON)
    ore_heap(bm, 1.6, -2.3, C.COAL, 0.6, 6)
    # bellows on the flank
    bx = side * 3.1
    box(bm, (bx, 0.0, 0.40), (1.3, 0.62, 0.10), C.WOOD_LIGHT)
    box(bm, (bx, 0.0, 0.62), (1.0, 0.56, 0.34), C.LEATHER, ch=0.04)
    sbeam(bm, (bx - 0.6, 0, 0.9), (bx + 0.6, 0, 0.66), 0.62, 0.07, C.WOOD_LIGHT)
    beam(bm, (bx, 0, 0.95), (bx, 0, 1.9), 0.04, 0.04, C.WOOD, 5)
    beam(bm, (bx - side * 0.65, 0, 0.5), (bx - side * 1.15, 0, 0.9), 0.07, 0.04, C.IRON, 6)
    # tuyere pipe into the furnace
    beam(bm, (bx - side * 0.65, 0, 0.5), (side * 2.0, 0, 1.0), 0.06, 0.06, C.IRON, 6)


def b_kiln(bm, ex):
    frustum(bm, T((0, 0, 0)), 1.5, 1.5, 0.2, C.STONE_DARK, segs=12)
    frustum(bm, T((0, 0, 0.2)), 1.3, 1.25, 1.0, C.STONE, segs=12)
    blob(bm, (0, 0, 1.2), (1.25, 1.25, 1.1), C.STONE, segs=12, rings=5)
    for z, r in ((0.55, 1.33), (1.05, 1.31)):
        frustum(bm, T((0, 0, z)), r, r, 0.09, C.IRON, segs=12)
    frustum(bm, T((0, 0, 2.1)), 0.42, 0.34, 1.9, C.STONE_DARK, segs=8)             # stack
    frustum(bm, T((0, 0, 3.95)), 0.50, 0.50, 0.14, C.IRON, segs=8)
    with bm.at((0, -1.25, 0.65)):
        box(bm, (0, 0, 0.3), (0.9, 0.2, 0.8), C.COAL)
        box(bm, (0, -0.02, 0.8), (1.1, 0.24, 0.2), C.STONE_LIGHT, ch=0.03)
    box(ex.glow, (0, -1.37, 0.95), (0.7, 0.05, 0.5), C.EMBER)
    ore_heap(bm, 1.3, -1.5, C.ORE_COPPER, 0.5, 5)


def b_casting(bm, ex):
    box(bm, (0, 0, 0.20), (6.0, 5.0, 0.40), C.STONE_DARK, ch=0.06)
    for sy in (-1, 1):
        box(bm, (0, sy * 2.35, 0.41), (5.8, 0.10, 0.04), C.BRONZE)
    # crucible in a tilting cradle (left)
    for sy in (-1, 1):
        box(bm, (-1.2, sy * 1.2, 1.0), (0.4, 0.4, 1.2), C.WOOD, ch=0.04)
        box(bm, (-1.2, sy * 1.2, 0.5), (0.9, 0.9, 0.2), C.STONE_LIGHT, ch=0.03)
    beam(bm, (-1.2, -1.2, 1.35), (-1.2, 1.2, 1.35), 0.08, 0.08, C.IRON, 6)
    frustum(bm, T((-1.2, 0, 0.75)), 0.55, 0.85, 0.9, C.IRON, segs=10)
    ring(bm, T((-1.2, 0, 1.58)), 0.92, 0.78, 0.10, C.IRON_LIGHT, segs=10)
    frustum(ex.glow, T((-1.2, 0, 1.6)), 0.8, 0.8, 0.05, C.MOLTEN, segs=10)
    beam(bm, (-1.2, -0.9, 1.1), (-1.2, -2.3, 0.75), 0.06, 0.05, C.WOOD_DARK, 5)    # tilt lever
    blob(bm, (-1.2, -2.3, 0.75), (0.1, 0.1, 0.1), C.IRON, segs=5, rings=3)
    # mould bed (right)
    box(bm, (1.7, 0, 0.75), (2.8, 1.8, 0.7), C.STONE, ch=0.05)
    box(bm, (1.7, 0, 1.12), (2.6, 1.6, 0.06), C.BRONZE)
    box(bm, (1.7, 0.1, 1.16), (2.2, 0.18, 0.03), C.COAL)                            # sword mould
    box(bm, (0.78, 0.1, 1.16), (0.06, 0.5, 0.03), C.COAL)
    frustum(bm, T((2.5, -0.35, 1.145)), 0.32, 0.32, 0.03, C.COAL, segs=10)           # shield mould
    for i in range(3):
        box(bm, (1.1 + i * 0.5, -0.5, 1.16), (0.34, 0.2, 0.03), C.COAL)              # ingot moulds
    box(ex.glow, (1.7, 0.1, 1.185), (1.4, 0.08, 0.02), C.MOLTEN)                     # metal in the mould
    # overhead hoist
    for sy in (-1, 1):
        box(bm, (-1.2, sy * 2.35, 2.7), (0.4, 0.4, 4.6), C.WOOD, ch=0.04)
        sbeam(bm, (-1.2, sy * 2.35, 4.0), (-1.2, sy * 1.5, 4.8), 0.2, 0.2, C.WOOD_LIGHT)
    sbeam(bm, (-1.2, -2.35, 5.0), (-1.2, 2.35, 5.0), 0.34, 0.40, C.WOOD)
    for i in range(7):
        sbeam(bm, (-1.2, 0.0, 4.8 - i * 0.40), (-1.2, 0.0, 4.55 - i * 0.40), 0.07, 0.07 if i % 2 else 0.13, C.IRON)
    beam(bm, (-1.2, 0.0, 2.0), (-1.2, 0.0, 1.7), 0.07, 0.04, C.IRON, 5)


def b_bench(bm, ex):
    box(bm, (0, 0, 0.95), (3.4, 1.2, 0.12), C.WOOD_LIGHT, ch=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(bm, (sx * 1.55, sy * 0.45, 0.45), (0.2, 0.2, 0.9), C.WOOD, ch=0.02)
    box(bm, (0, 0, 0.35), (3.1, 0.9, 0.08), C.WOOD_DARK)
    box(bm, (-1.45, -0.15, 1.12), (0.30, 0.34, 0.22), C.IRON, ch=0.02)             # vise
    beam(bm, (-1.45, -0.34, 1.12), (-1.45, -0.7, 1.12), 0.03, 0.03, C.IRON, 5)
    box(bm, (0.1, -0.1, 1.03), (1.5, 0.14, 0.03), C.STEEL)                          # blade blank
    box(bm, (-0.7, -0.1, 1.05), (0.07, 0.34, 0.05), C.GOLD)                         # guard
    box(bm, (-0.95, -0.1, 1.045), (0.34, 0.07, 0.05), C.LEATHER)                    # grip
    frustum(bm, T((0.9, 0.2, 1.01)) @ ROT_Y90, 0.09, 0.09, 0.5, C.LEATHER, segs=6)  # leather roll
    box(bm, (1.3, -0.3, 1.04), (0.3, 0.1, 0.03), C.IRON_LIGHT)                       # file
    box(bm, (0, 0.55, 1.75), (3.4, 0.08, 1.3), C.WOOD, ch=0.02)                      # pegboard
    for i, x in enumerate((-1.3, -0.6, 0.2, 0.9, 1.4)):
        beam(bm, (x, 0.5, 2.1), (x, 0.5, 1.5), 0.04, 0.04, C.WOOD, 5)
        box(bm, (x, 0.5, 1.45 if i % 2 else 1.4), (0.22 if i % 2 else 0.1, 0.07, 0.16), C.IRON)
    for sx in (-1, 1):
        sbeam(bm, (sx * 1.7, 0.55, 0.9), (sx * 1.7, 0.55, 2.5), 0.12, 0.12, C.WOOD)


def b_counter(bm, ex):
    box(bm, (0, 0, 0.55), (4.4, 1.4, 1.1), C.STONE_LIGHT, ch=0.05)
    box(bm, (0, 0, 1.16), (4.7, 1.7, 0.12), C.WOOD_LIGHT, ch=0.03)
    box(bm, (0, -0.72, 0.60), (3.2, 0.05, 0.6), C.BRONZE_DARK)
    insignia(bm, "armory", (0, -0.77, 0.60), 0.34, C.GOLD, True)
    # coin chest, scales, ledger, helmet on display
    box(bm, (-1.7, 0.1, 1.36), (0.8, 0.5, 0.28), C.WOOD_DARK, ch=0.03)
    box(bm, (-1.7, 0.1, 1.52), (0.84, 0.54, 0.06), C.GOLD)
    for i in range(4):
        blob(bm, (-1.7 + i * 0.16 - 0.24, -0.25, 1.28), (0.09, 0.09, 0.03), C.GOLD, segs=5, rings=2)
    beam(bm, (0.9, 0.1, 1.22), (0.9, 0.1, 1.95), 0.04, 0.04, C.IRON, 5)
    sbeam(bm, (0.5, 0.1, 1.92), (1.3, 0.1, 1.92), 0.06, 0.06, C.GOLD)
    for sx in (0.5, 1.3):
        frustum(bm, T((sx, 0.1, 1.45)), 0.2, 0.2, 0.05, C.GOLD, segs=8)
        for a in (0, 2.1, 4.2):
            beam(bm, (sx, 0.1, 1.92), (sx + 0.15 * math.cos(a), 0.1 + 0.15 * math.sin(a), 1.5), 0.01, 0.01, C.IRON, 3)
    box(bm, (-0.4, 0.0, 1.26), (0.5, 0.36, 0.08), C.LEATHER)
    box(bm, (-0.4, 0.0, 1.31), (0.46, 0.32, 0.03), C.CREAM)
    helmet(bm, (1.8, 0.2, 1.46), 0.9, C.BRONZE, C.MAROON)
    # striped awning, posts and valance
    for sx in (-1, 1):
        box(bm, (sx * 2.4, 0.9, 2.2), (0.3, 0.3, 4.4), C.WOOD, ch=0.04)
    n = 6
    for i in range(n):
        x0 = -2.6 + 5.2 * i / n
        x1 = -2.6 + 5.2 * (i + 1) / n
        quad_slab(bm, [(x0, 1.1, 4.45), (x1, 1.1, 4.45), (x1, -1.1, 4.0), (x0, -1.1, 4.0)], 0.08,
                  C.MAROON if i % 2 == 0 else C.CREAM)
    prism(bm, [(-2.6, 0), (2.6, 0), (2.6, -0.42), (1.7, -0.75), (0.85, -0.42), (0, -0.75), (-0.85, -0.42),
               (-1.7, -0.75), (-2.6, -0.42)], (0, -1.12, 4.02), 1.0, 0.05, C.MAROON_DARK)
    insignia(bm, "armory", (0, -1.16, 3.62), 0.36, C.GOLD, True)
    lantern(bm, ex, -1.9, 0.0, 3.3, 0.7)
    lantern(bm, ex, 1.9, 0.0, 3.3, 0.7)


def b_dais(bm, ex):
    frustum(bm, T((0, 0, 0)), 1.95, 1.85, 0.25, C.STONE_LIGHT, segs=20)
    ring(bm, T((0, 0, 0.25)), 1.85, 1.68, 0.06, C.BRONZE, segs=20)
    tt = ex.get("_Turntable")                                                     # rotating top
    frustum(tt, T((0, 0, 0.25)), 1.62, 1.62, 0.14, C.MARBLE, segs=20)
    ring(tt, T((0, 0, 0.39)), 1.62, 1.45, 0.03, C.BRONZE, segs=20)
    with tt.at((0, 0, 0.425), rx=-math.pi / 2):
        insignia(tt, "armory", (0, 0, 0), 0.9, C.MAROON, True, dark=C.CREAM)
    for i in range(4):
        a = math.pi / 4 + math.pi / 2 * i
        box(bm, (2.2 * math.cos(a), 2.2 * math.sin(a), 0.5), (0.22, 0.22, 1.0), C.STONE_LIGHT, ch=0.03)
        blob(bm, (2.2 * math.cos(a), 2.2 * math.sin(a), 1.15), (0.17, 0.17, 0.17), C.BRONZE, segs=6, rings=3)


def b_display(bm, ex, tier="bronze"):
    box(bm, (0, 0, 0.22), (1.9, 1.7, 0.44), C.STONE_LIGHT, ch=0.04)
    box(bm, (0, 0, 0.46), (2.0, 1.8, 0.06), C.BRONZE)
    with bm.at((0, 0, 0.49)):
        armor_suit(bm, tier, 1.0)
    for sx in (-1, 1):                                                            # niche posts
        box(bm, (sx * 1.15, 0.5, 1.5), (0.22, 0.3, 3.0), C.STONE, ch=0.03)
    box(bm, (0, 0.5, 3.1), (2.5, 0.3, 0.22), C.STONE_LIGHT, ch=0.03)
    insignia(bm, "armory", (0, 0.33, 2.7), 0.22, C.GOLD, True)
    if tier == "gold":
        blob(ex.glow, (0, 0, 0.62), (0.1, 0.1, 0.05), C.GLOW, segs=5, rings=3)


def b_panoply(bm, ex):
    frustum(bm, T((0, 0, 0)), 3.0, 2.85, 0.30, C.STONE_LIGHT, segs=24)
    frustum(bm, T((0, 0, 0.30)), 2.6, 2.5, 0.26, C.MARBLE, segs=24)
    ring(bm, T((0, 0, 0.56)), 2.5, 2.3, 0.06, C.BRONZE, segs=24)
    frustum(bm, T((0, 0, 0.56)), 1.1, 1.0, 0.34, C.STONE_LIGHT, segs=12)
    with bm.at((0, 0, 0.90)):
        armor_suit(bm, "gold", 1.5, base_z_pole=True)
    for i in range(4):
        a = math.pi / 4 + math.pi / 2 * i
        stone_column(bm, 2.35 * math.cos(a), 2.35 * math.sin(a), 3.8, 0.42)
        flame(ex, 2.35 * math.cos(a), 2.35 * math.sin(a), 5.05, 0.28, 0.8)
    ring(bm, T((0, 0, 5.1)), 2.9, 2.0, 0.22, C.BRONZE, segs=24)
    ring(ex.glow, T((0, 0.5, 4.15)) @ ROT_X90, 0.95, 0.80, 0.08, C.GLOW, segs=20)
    for i in range(8):
        a = math.tau * (i + 0.5) / 8
        beam(ex.glow, (1.05 * math.cos(a), 0.5, 4.15 + 1.05 * math.sin(a)),
             (1.35 * math.cos(a), 0.5, 4.15 + 1.35 * math.sin(a)), 0.05, 0.0, C.GLOW, 3)


def b_showcase(bm, ex):
    box(bm, (0, 0.4, 2.4), (6.0, 0.25, 4.8), C.WOOD_DARK, ch=0.02)
    for sx in (-1, 1):
        box(bm, (sx * 3.0, 0.1, 2.4), (0.4, 0.9, 4.8), C.STONE_LIGHT, ch=0.04)
    box(bm, (0, 0.1, 4.82), (6.6, 1.0, 0.34), C.STONE_LIGHT, ch=0.04)
    box(bm, (0, -0.4, 4.7), (6.0, 0.06, 0.1), C.BRONZE)
    for z in (1.0, 2.2, 3.4):
        box(bm, (0, -0.05, z), (5.4, 0.7, 0.08), C.WOOD_LIGHT, ch=0.02)
    for x in (-1.8, 0.0, 1.8):
        shield(bm, (x, -0.3, 1.0 + 0.58), 0.55, C.MAROON, C.BRONZE, "armory", C.GOLD)
    for i in range(7):
        sword(bm, -2.25 + i * 0.75, -0.15, 2.24, 1.2)
    for i, x in enumerate((-2.1, -1.05, 0.0, 1.05, 2.1)):
        helmet(bm, (x, -0.1, 3.4 + 0.34), 0.9, C.BRONZE if i % 2 else C.IRON_LIGHT, C.MAROON if i % 2 else C.CREAM)
    insignia(bm, "armory", (0, -0.35, 4.3), 0.30, C.GOLD, True)
    lantern(bm, ex, -2.4, -0.2, 4.9)
    lantern(bm, ex, 2.4, -0.2, 4.9)


# ============================ SHARED DECOR HELPERS ===========================
def banner(bm, x, y, ztop, w, h, cloth=C.MAROON, motif="bull", col=C.CREAM, both=True):
    """Hanging swallow-tail banner facing -Y (emblem on both sides when both=True)."""
    prism(bm, [(-w / 2, 0), (w / 2, 0), (w / 2, -h), (0, -h * 0.86), (-w / 2, -h)], (x, y, ztop), 1.0, 0.05, cloth)
    box(bm, (x, y, ztop + 0.05), (w + 0.35, 0.10, 0.09), C.WOOD_DARK)
    for sx in (-1, 1):
        blob(bm, (x + sx * (w / 2 + 0.2), y, ztop + 0.05), (0.1, 0.1, 0.1), C.GOLD, segs=5, rings=3)
    box(bm, (x, y - 0.03, ztop - h * 0.93), (w * 0.62, 0.02, 0.05), C.GOLD)
    insignia(bm, motif, (x, y - 0.03, ztop - h * 0.38), w * 0.40, col, True)
    if both:
        with bm.at((x, y, 0), rz=math.pi):
            insignia(bm, motif, (0, -0.03, ztop - h * 0.38), w * 0.40, col, True)


def floor_emblem(bm, x, y, z, r, rim=C.BRONZE, disc=C.MAROON, motif=C.CREAM):
    frustum(bm, T((x, y, z)), r, r, 0.04, rim, segs=24)
    frustum(bm, T((x, y, z + 0.04)), r * 0.86, r * 0.86, 0.02, disc, segs=24)
    with bm.at((x, y, z + 0.065), rx=-math.pi / 2):
        emblem(bm, (0, 0, 0), r * 0.62, motif, disc, t=0.02, flat=True)


def window(bm, axis, c, a0, a1, z0, z1, t=0.9):
    m, w, h, zc = (a0 + a1) / 2, a1 - a0, z1 - z0, (z0 + z1) / 2
    loc = (m, c, zc) if axis == "x" else (c, m, zc)
    with bm.at(loc, rz=0.0 if axis == "x" else math.pi / 2):
        for sz in (-1, 1):
            box(bm, (0, 0, sz * (h / 2 + 0.07)), (w + 0.5, t + 0.14, 0.14), C.STONE_LIGHT, ch=0.02)
        for sx in (-1, 1):
            box(bm, (sx * (w / 2 + 0.07), 0, 0), (0.14, t + 0.14, h), C.STONE_LIGHT, ch=0.02)
        for i in (-1, 0, 1):
            box(bm, (i * w / 4, 0, 0), (0.05, 0.05, h), C.IRON)


def chimney(bm, ex, x, y):
    box(bm, (x, y - 0.55, 3.2), (3.6, 1.5, 6.4), C.STONE, ch=0.06)              # breast against the wall
    box(bm, (x, y, 9.9), (2.6, 2.2, 7.8), C.STONE, ch=0.05)                      # stack through the roof
    for dz, dw in ((0.0, 0.0), (0.4, 0.2)):
        box(bm, (x, y, 13.85 + dz), (3.0 + dw, 2.6 + dw, 0.3), C.STONE_LIGHT, ch=0.04)
    box(bm, (x, y, 14.2), (1.6, 1.2, 0.2), C.COAL)
    box(ex.glow, (x, y, 14.12), (1.2, 0.8, 0.06), C.EMBER)
    for sz in (-1, 1):
        box(bm, (x + sz * 1.45, y, 9.0), (0.14, 2.3, 0.4), C.BRONZE)


# ============================ THE GREAT FORGE ================================
FORGE_FR = Frame(-32.0, 0.0, math.pi / 2)
NAVE_XS = [-13.5, -9.0, -4.5, 0.0, 4.5, 9.0, 13.5]
H0F = 0.45


def forge_shell(bm, ex):
    # floor, joints, runner, steps
    box(bm, (0, 0, H0F / 2), (31.2, 27.2, H0F), C.STONE_DARK, ch=0.05)
    collide("Forge_Floor", 0, 0, H0F / 2, 31.2, 27.2, H0F)
    for x in range(-12, 13, 3):
        box(bm, (x, 0, H0F + 0.005), (0.05, 27.0, 0.012), C.COAL)
    for y in range(-12, 13, 3):
        box(bm, (0, y, H0F + 0.005), (31.0, 0.05, 0.012), C.COAL)
    box(bm, (0, -6.0, H0F + 0.012), (3.2, 14.0, 0.02), C.MAROON)
    for sx in (-1, 1):
        box(bm, (sx * 1.7, -6.0, H0F + 0.015), (0.12, 14.0, 0.02), C.GOLD)
    floor_emblem(bm, 0, -9.0, H0F + 0.02, 1.35)
    for sx in (-1, 1):
        box(bm, (sx * 6.0, 8.0, H0F + 0.008), (4.2, 1.8, 0.012), C.COAL)         # scorch marks
    box(bm, (0, -14.0, 0.15), (14.0, 0.8, 0.30), C.STONE, ch=0.03)
    box(bm, (0, -14.8, 0.075), (14.0, 0.8, 0.15), C.STONE, ch=0.03)
    collide("Forge_Step2", 0, -14.0, 0.15, 14.0, 0.8, 0.30)
    collide("Forge_Step1", 0, -14.8, 0.075, 14.0, 0.8, 0.15)

    # posts: front colonnade, two nave rows with clerestory posts and braces
    for x in NAVE_XS:
        timber_post(bm, x, -12.6, 4.6, 0.7, name="Forge_FrontPost")
        for y in (-6.5, 6.5):
            timber_post(bm, x, y, 7.1, 0.8, name="Forge_NavePost")
            box(bm, (x, y, 8.45), (0.5, 0.5, 1.3), C.WOOD_DARK)
            for s in (-1, 1):
                sbeam(bm, (x, y, 6.5), (x + s * 1.3, y, 7.9), 0.2, 0.24, C.WOOD_LIGHT)
    sbeam(bm, (-15.4, -12.6, 5.3), (15.4, -12.6, 5.3), 0.5, 0.45, C.WOOD)
    for y in (-6.5, 6.5):
        sbeam(bm, (-15.4, y, 7.9), (15.4, y, 7.9), 0.55, 0.5, C.WOOD)
        sbeam(bm, (-15.4, y, 9.0), (15.4, y, 9.0), 0.55, 0.5, C.WOOD)
    for z in (8.15, 8.45, 8.75):                                                  # clerestory louvres
        for y in (-6.5, 6.5):
            box(bm, (0, y, z), (30.4, 0.1, 0.12), C.WOOD_DARK)

    # back wall with windows + central bull roundel
    wall(bm, "x", -15.4, 15.4, 12.9, 0, 5.9, 0.8, C.STONE, openings=[(-12.2, -9.8, 3.2, 5.2), (9.8, 12.2, 3.2, 5.2)],
         ch=0.04, name="Forge_BackWall")
    for x0, x1 in ((-12.2, -9.8), (9.8, 12.2)):
        window(bm, "x", 12.9, x0, x1, 3.2, 5.2)
    frustum(bm, T((0, 12.45, 4.4)) @ ROT_X90, 1.7, 1.7, 0.1, C.BRONZE, segs=20)
    frustum(bm, T((0, 12.35, 4.4)) @ ROT_X90, 1.5, 1.5, 0.05, C.MAROON, segs=20)
    insignia(bm, "forge", (0, 12.30, 4.4), 1.55, C.GOLD, True)
    chimney(bm, ex, -6.0, 12.4)
    chimney(bm, ex, 6.0, 12.4)

    # end walls: lower wall with a service door, gable above, bull relief
    pts = [(-13.4, 5.2), (13.4, 5.2), (6.9, 7.7), (6.9, 9.0), (0, 13.0), (-6.9, 9.0), (-6.9, 7.7)]
    for sx in (-1, 1):
        with bm.at((sx * 15.0, 0, 0), rz=sx * math.pi / 2):
            wall(bm, "x", -13.4, 13.4, 0, 0, 5.2, 0.8, C.STONE, openings=[(-2.2, 2.2, 0.45, 4.5)], ch=0.04)
            prism(bm, pts, (0, 0, 0), 1.0, 0.8, C.STONE)
            emblem(bm, (0, -0.46, 9.5), 1.7, C.BRONZE, C.MAROON, t=0.12)
            box(bm, (0, 0, 4.7), (5.2, 1.0, 0.45), C.WOOD)
            for s in (-1, 1):
                box(bm, (s * 2.4, 0, 2.5), (0.4, 0.95, 4.1), C.WOOD)
        collide("Forge_EndWall", sx * 15.0, -7.8, 2.6, 0.8, 11.2, 5.2)
        collide("Forge_EndWall", sx * 15.0, 7.8, 2.6, 0.8, 11.2, 5.2)

    # roofs: nave (high) and two aisle lean-tos, rafters visible from inside
    X0, X1 = -15.7, 15.7
    roof_slope(bm, (X0, -6.9, 9.0), (X1, -6.9, 9.0), (X1, 0, 13.0), (X0, 0, 13.0), 0.24, C.ROOF, C.ROOF_LIGHT, 8, rafters=2.25)
    roof_slope(bm, (X0, 6.9, 9.0), (X1, 6.9, 9.0), (X1, 0, 13.0), (X0, 0, 13.0), 0.24, C.ROOF, C.ROOF_LIGHT, 8, rafters=2.25)
    roof_slope(bm, (X0, -13.9, 5.4), (X1, -13.9, 5.4), (X1, -6.9, 7.9), (X0, -6.9, 7.9), 0.22, C.ROOF, C.ROOF_LIGHT, 6, rafters=2.25)
    roof_slope(bm, (X0, 13.9, 5.4), (X1, 13.9, 5.4), (X1, 6.9, 7.9), (X0, 6.9, 7.9), 0.22, C.ROOF, C.ROOF_LIGHT, 6, rafters=2.25)
    sbeam(bm, (X0, 0, 13.1), (X1, 0, 13.1), 0.5, 0.4, C.ROOF_LIGHT)
    for x in NAVE_XS:
        with bm.at((x, 0, 0), rz=math.pi / 2):
            truss(bm, 0, 6.9, 9.0, 13.0)

    # lanterns, banners, sign
    for x in (-13.5, -4.5, 4.5, 13.5):
        for y in (-3.5, 3.5):
            lantern(bm, ex, x, y, 7.0, hang=2.0)
    for x in (-11.25, -6.75, 6.75, 11.25):
        banner(bm, x, -12.95, 5.1, 1.8, 3.8, motif="forge", col=C.GOLD)
    box(bm, (0, -12.95, 4.5), (8.4, 0.22, 1.25), C.WOOD, ch=0.03)
    for sx in (-1, 1):
        sbeam(bm, (sx * 4.0, -12.95, 5.25), (sx * 4.0, -12.95, 5.05), 0.08, 0.08, C.IRON)
    text(bm, "GREAT FORGE", (0, -13.1, 4.5), 0.62, C.CREAM, depth=0.06, stroke_w=0.17)


def forge_props(bm, ex):
    z = H0F
    # blade rack between the chimneys
    for sx in (-1, 1):
        box(bm, (sx * 3.4, 12.4, z + 1.75), (0.25, 0.4, 3.5), C.WOOD)
    for rz_ in (0.9, 2.4):
        box(bm, (0, 12.4, z + rz_ - 0.15), (7.0, 0.35, 0.12), C.WOOD_DARK)
    for row, rz_ in enumerate((0.9, 2.4)):
        for i in range(9):
            sword(bm, -3.0 + i * 0.75, 12.2, z + rz_, 1.15 if row == 0 else 1.0, blade=C.STEEL if i % 2 else C.IRON_LIGHT)
    # ore & coal bins, tool racks, storage clusters
    for sx, col in ((-1, C.ORE_COPPER), (1, C.COAL)):
        x = sx * 13.3
        for dx, dy, w, d in ((0, -1.2, 2.4, 0.14), (0, 1.2, 2.4, 0.14), (-1.2, 0, 0.14, 2.4), (1.2, 0, 0.14, 2.4)):
            box(bm, (x + dx, 11.4 + dy, z + 0.55), (w, d, 1.1), C.WOOD, ch=0.02)
        for dx, dy in ((-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)):
            box(bm, (x + dx, 11.4 + dy, z + 0.6), (0.2, 0.2, 1.2), C.WOOD_DARK)
        ore_heap(bm, x, 11.4, col, 1.0, 11)
        collide("Forge_Bin", x, 11.4, z + 0.55, 2.6, 2.6, 1.1)
    for sx in (-1, 1):
        for i in range(3):
            barrel(bm, sx * 13.9, -9.0 - i * 1.0, z)
        crate(bm, sx * 13.7, -12.0, z, 1.0, rot=0.3 * sx)
        crate(bm, sx * 13.7, -12.0, z + 1.0, 0.8, rot=-0.2 * sx)
        logs(bm, sx * 14.0, -1.0, 0.0, 6)
        ingots(bm, sx * 4.2, 6.0, z, 3)
    # hammer / tongs rack mid-aisle, wall tool boards
    for sx in (-1, 1):
        for i in range(5):
            x = sx * (1.5 + i * 0.5)
            beam(bm, (x, 12.35, z + 3.0), (x, 12.35, z + 2.4), 0.03, 0.03, C.WOOD, 5)
            box(bm, (x, 12.35, z + 2.35), (0.2 if i % 2 else 0.09, 0.07, 0.16), C.IRON)
    # shields on the nave posts (alternating motifs) - insignia everywhere
    for y in (-6.5, 6.5):
        for i, x in enumerate(NAVE_XS):
            shield(bm, (x, y - 0.55, z + 3.4), 0.5, C.MAROON, C.BRONZE, "forge", C.GOLD)
    # hanging chains with hooks over the aisles
    for x in (-9.0, 9.0):
        for i in range(5):
            sbeam(bm, (x, -9.5, 8.0 - i * 0.35), (x, -9.5, 7.75 - i * 0.35), 0.06, 0.06 if i % 2 else 0.11, C.IRON)


def build_forge():
    use_frame(FORGE_FR)
    static("Forge_Hall_Shell", forge_shell)
    static("Forge_Hall_Props", forge_props)
    z = H0F
    # smelting furnaces (two great, two kilns)
    station("Forge_Furnace_01", "furnace", "Smelt Ore", lambda b, e: b_furnace(b, e, -1), -6.0, 10.8, z,
            prompt_h=1.6, colliders=[(0, 0, 2.3, 4.6, 3.6, 4.6)])
    station("Forge_Furnace_02", "furnace", "Smelt Ore", lambda b, e: b_furnace(b, e, 1), 6.0, 10.8, z,
            prompt_h=1.6, colliders=[(0, 0, 2.3, 4.6, 3.6, 4.6)])
    station("Forge_Kiln_01", "kiln", "Fire Kiln", b_kiln, -12.9, 7.2, z, lrot=math.pi / 2, share="forge_kiln", prompt_h=1.4)
    station("Forge_Kiln_02", "kiln", "Fire Kiln", b_kiln, 12.9, 7.2, z, lrot=-math.pi / 2, share="forge_kiln", prompt_h=1.4)
    # casting
    station("Forge_Casting_01", "casting", "Cast Metal", b_casting, 0.0, 4.2, z, prompt_h=1.6,
            colliders=[(0, 0, 0.2, 6.0, 5.0, 0.4), (1.7, 0, 0.75, 2.8, 1.8, 0.7), (-1.2, 0, 1.0, 1.9, 1.9, 1.2)])
    # forging anvils - the core mini-game stations
    for i, x in enumerate((-12.0, -8.0, -4.0, 4.0, 8.0, 12.0)):
        station("Forge_Anvil_%02d" % (i + 1), "anvil", "Forge Weapon", b_anvil, x, -3.0, z, share="forge_anvil",
                prompt_h=1.5)
    for i, x in enumerate((-8.0, 8.0)):
        station("Forge_Trough_%02d" % (i + 1), "quench", "Quench Blade", b_trough, x, 0.6, z, share="forge_trough", prompt_h=1.4)
    for i, x in enumerate((-12.8, 12.8)):
        station("Forge_Grindstone_%02d" % (i + 1), "grind", "Sharpen Blade", b_grind, x, 2.6, z,
                share="forge_grind", prompt_h=1.5)
    for i, x in enumerate((-9.0, 9.0)):
        station("Forge_Bench_%02d" % (i + 1), "assembly", "Assemble & Finish", b_bench, x, -9.8, z,
                share="forge_bench", prompt_h=1.5)
    marker("Forge_Smoke_01", "effect_smoke", "Chimney smoke", -6.0, 12.4, 14.6)
    marker("Forge_Smoke_02", "effect_smoke", "Chimney smoke", 6.0, 12.4, 14.6)
    marker("Forge_Entrance", "zone", "Great Forge entrance", 0.0, -14.5, 0.8)


# ============================ THE ARMORY =====================================
ARMORY_FR = Frame(34.0, 0.0, -math.pi / 2)
H0A = 0.9
ARC_YS = [-10.0, -5.0, 0.0, 5.0, 10.0]


def chandelier(bm, ex, x, y, z, top=11.0):
    ring(bm, T((x, y, z)), 1.35, 1.2, 0.12, C.IRON, segs=16)
    for i in range(4):
        a = math.tau * i / 4 + math.pi / 4
        beam(bm, (x + 1.28 * math.cos(a), y + 1.28 * math.sin(a), z + 0.06), (x, y, z + 1.4), 0.03, 0.03, C.IRON, 4)
    beam(bm, (x, y, z + 1.4), (x, y, top), 0.05, 0.05, C.IRON, 5)
    for i in range(8):
        a = math.tau * i / 8
        px, py = x + 1.28 * math.cos(a), y + 1.28 * math.sin(a)
        frustum(bm, T((px, py, z + 0.12)), 0.05, 0.05, 0.22, C.CREAM, segs=5)
        flame(ex, px, py, z + 0.34, 0.07, 0.2)
    blob(bm, (x, y, z - 0.2), (0.18, 0.18, 0.3), C.BRONZE, segs=6, rings=3)


def armory_shell(bm, ex):
    # floors, porch, steps
    box(bm, (0, 0, H0A / 2), (29.0, 29.0, H0A), C.STONE_LIGHT, ch=0.05)
    box(bm, (0, -16.5, H0A / 2), (25.0, 5.0, H0A), C.STONE_LIGHT, ch=0.05)
    collide("Armory_Floor", 0, 0, H0A / 2, 29.0, 29.0, H0A)
    collide("Armory_PorchFloor", 0, -16.5, H0A / 2, 25.0, 5.0, H0A)
    for j in range(4):
        top = (j + 1) * 0.18
        yc = -19.3 - 0.6 * (3 - j) - 0.0
        box(bm, (0, yc - 0.0, top / 2), (24.0, 0.6, top), C.STONE, ch=0.02)
        collide("Armory_Step", 0, yc, top / 2, 24.0, 0.6, top)
    zt = H0A + 0.012
    for y in range(-10, 14, 5):
        box(bm, (0, y, zt), (28.0, 0.06, 0.02), C.STONE_DARK)
    for sx in (-1, 1):
        box(bm, (sx * 7.0, 0, zt), (0.14, 28.0, 0.025), C.BRONZE)
    box(bm, (0, -2.5, zt + 0.01), (3.2, 23.0, 0.02), C.MAROON)
    for sx in (-1, 1):
        box(bm, (sx * 1.7, -2.5, zt + 0.015), (0.12, 23.0, 0.02), C.GOLD)
    floor_emblem(bm, 0, -8.0, zt + 0.02, 2.4)
    ring(bm, T((0, 2.0, zt + 0.02)), 3.75, 3.55, 0.03, C.BRONZE, segs=32)
    for sx in (-1, 1):
        box(bm, (sx * 8.5, 10.8, H0A + 0.075), (5.4, 2.8, 0.15), C.STONE_DARK, ch=0.02)   # merchant platforms
    box(bm, (0, 10.8, H0A + 0.075), (5.4, 2.8, 0.15), C.STONE_DARK, ch=0.02)

    # porch colonnade, entablature, lettering, pediment
    for x in (-10.0, -6.0, -2.0, 2.0, 6.0, 10.0):
        stone_column(bm, x, -17.4, 7.85, 0.62, name="Armory_PorchColumn")
    box(bm, (0, -17.4, 9.4), (23.4, 1.5, 0.8), C.STONE_LIGHT, ch=0.03)
    box(bm, (0, -17.4, 10.4), (23.0, 1.3, 1.2), C.STONE, ch=0.03)
    box(bm, (0, -18.06, 10.4), (13.0, 0.10, 1.0), C.MAROON)
    text(bm, "ARMORY", (0, -18.15, 10.4), 0.8, C.CREAM, depth=0.07, stroke_w=0.17)
    for sx in (-1, 1):
        for i in range(4):
            box(bm, (sx * (7.6 + i * 0.9), -18.1, 10.4), (0.35, 0.08, 0.9), C.STONE_DARK)     # triglyphs
    box(bm, (0, -17.4, 11.2), (24.0, 1.8, 0.4), C.STONE_LIGHT, ch=0.04)
    prism(bm, [(-12.2, 0), (12.2, 0), (0, 4.4)], (0, -17.4, 11.4), 1.0, 1.2, C.STONE_LIGHT)
    prism(bm, [(-10.6, 0.4), (10.6, 0.4), (0, 3.5)], (0, -18.05, 11.4), 1.0, 0.15, C.PLASTER)
    emblem(bm, (0, -18.2, 12.5), 1.5, C.BRONZE, C.MAROON, t=0.12)
    box(bm, (0, -15.95, 9.95), (23.0, 2.9, 0.25), C.STONE, ch=0.02)                              # porch ceiling
    for x in range(-10, 11, 3):
        sbeam(bm, (x, -17.4, 9.75), (x, -14.5, 9.75), 0.3, 0.3, C.WOOD_DARK)

    # facade with grand doorway and tall windows
    wall(bm, "x", -14.5, 14.5, -14.0, 0, 11.0, 1.0, C.STONE,
         openings=[(-3.6, 3.6, 0.0, 7.8), (-10.6, -7.4, H0A + 2.0, 7.4), (7.4, 10.6, H0A + 2.0, 7.4)],
         ch=0.03, name="Armory_Facade")
    box(bm, (0, -14.0, 7.95), (8.2, 1.2, 0.4), C.STONE_LIGHT, ch=0.03)
    for sx in (-1, 1):
        box(bm, (sx * 3.85, -14.0, 4.4), (0.45, 1.2, 7.5), C.STONE_LIGHT, ch=0.03)
    for x0, x1 in ((-10.6, -7.4), (7.4, 10.6)):
        window(bm, "x", -14.0, x0, x1, H0A + 2.0, 7.4, 1.0)
    shield(bm, (0, -14.55, 8.95), 0.85, C.MAROON, C.BRONZE, "armory", C.GOLD)

    # side walls (windows above the display niches) and back wall with giant bull roundel
    for sx in (-1, 1):
        ops = [(y - 1.2, y + 1.2, 5.2, 9.2) for y in (-8.0, -3.0, 2.0, 7.0)]
        wall(bm, "y", -14.5, 14.5, sx * 14.0, 0, 11.0, 1.0, C.STONE, openings=ops, ch=0.03, name="Armory_SideWall")
        for y in (-8.0, -3.0, 2.0, 7.0):
            window(bm, "y", sx * 14.0, y - 1.2, y + 1.2, 5.2, 9.2, 1.0)
    wall(bm, "x", -14.5, 14.5, 14.0, 0, 11.0, 1.0, C.STONE, ch=0.03, name="Armory_BackWall")
    prism(bm, [(-14.9, 0), (14.9, 0), (0, 4.7)], (0, 14.0, 11.0), 1.0, 1.0, C.STONE)
    frustum(bm, T((0, 13.5, 6.4)) @ ROT_X90, 3.0, 3.0, 0.12, C.BRONZE, segs=24)
    frustum(bm, T((0, 13.4, 6.4)) @ ROT_X90, 2.7, 2.7, 0.06, C.MAROON, segs=24)
    insignia(bm, "armory", (0, 13.3, 6.3), 2.05, C.GOLD, True)

    # interior colonnade, arcade beams, trusses, roof
    for sx in (-1, 1):
        for y in ARC_YS:
            stone_column(bm, sx * 7.0, y, 7.45, 0.62, name="Armory_NaveColumn")
            box(bm, (sx * 7.0, y, 10.25), (0.5, 0.5, 1.5), C.WOOD_DARK)
        sbeam(bm, (sx * 7.0, -12.0, 9.2), (sx * 7.0, 12.0, 9.2), 0.9, 0.8, C.STONE_LIGHT)
        sbeam(bm, (sx * 7.0, -12.0, 8.8), (sx * 7.0, 12.0, 8.8), 1.0, 0.2, C.BRONZE)
    for y in ARC_YS:
        truss(bm, y, 14.6, 11.0, 15.5)
    roof_slope(bm, (-14.9, -16.8, 11.0), (-14.9, 14.9, 11.0), (0, 14.9, 15.6), (0, -16.8, 15.6), 0.26,
               C.ROOF, C.ROOF_LIGHT, 10, rafters=2.5)
    roof_slope(bm, (14.9, -16.8, 11.0), (14.9, 14.9, 11.0), (0, 14.9, 15.6), (0, -16.8, 15.6), 0.26,
               C.ROOF, C.ROOF_LIGHT, 10, rafters=2.5)
    sbeam(bm, (0, -16.8, 15.7), (0, 14.9, 15.7), 0.5, 0.4, C.ROOF_LIGHT)
    for sx in (-1, 1):
        standing_brazier(bm, ex, sx * 12.4, -16.6, 1.7)
    for y in (-10.0, -5.0, 10.0):
        chandelier(bm, ex, 0.0, y, 7.2)
    for sx in (-1, 1):
        for y in (-8.0, -3.0, 2.0, 7.0):
            lantern(bm, ex, sx * 13.3, y - 1.9, 4.2, 0.0)


def armory_props(bm, ex):
    z = H0A
    for x in (-8.0, -4.0, 0.0, 4.0, 8.0):                                     # tall facade banners
        banner(bm, x, -17.4, 8.9, 1.8, 6.6, motif="armory", col=C.GOLD)
    for sx in (-1, 1):
        for y in (-7.5, -2.5, 2.5, 7.5):                                       # nave banners facing the aisle
            with bm.at((sx * 6.4, y, 0), rz=-sx * math.pi / 2):
                banner(bm, 0, 0, 8.7, 1.7, 4.6, motif="armory", col=C.GOLD)
        for y in ARC_YS:                                                       # shield on every column
            with bm.at((sx * 7.0, y, 0), rz=-sx * math.pi / 2):
                shield(bm, (0, -0.85, 3.7), 0.5, C.MAROON, C.BRONZE, "armory", C.GOLD)
    for sx in (-1, 1):                                                         # honour-guard statues by the door
        with bm.at((sx * 5.6, -12.2, z)):
            box(bm, (0, 0, 0.35), (1.7, 1.7, 0.7), C.STONE_LIGHT, ch=0.04)
            box(bm, (0, 0, 0.72), (1.8, 1.8, 0.06), C.BRONZE)
            armor_suit(bm, "steel", 1.25, z0=0.75)
        collide("Armory_Statue", sx * 5.6, -12.2, z + 1.6, 1.7, 1.7, 3.2)
    for sx in (-1, 1):                                                         # spear stands flanking the nave end
        for i in range(5):
            spear(bm, sx * 13.0 + (i - 2) * 0.0, 11.8 + 0.3 * i - 0.6, z + 0.2, 3.0 + 0.1 * (i % 2), lean=(0.0, 0.0))
        box(bm, (sx * 13.0, 12.1, z + 0.12), (0.6, 1.8, 0.24), C.WOOD_DARK)
    for sx in (-1, 1):
        box(bm, (sx * 8.5, 13.2, z + 2.2), (4.6, 0.12, 0.5), C.WOOD_DARK)         # merchant shelf behind counters
        for i in range(4):
            helmet(bm, (sx * 8.5 - 1.6 + i * 1.07, 13.0, z + 2.65), 0.8, C.BRONZE if i % 2 else C.IRON_LIGHT)


def build_armory():
    use_frame(ARMORY_FR)
    static("Armory_Hall_Shell", armory_shell)
    static("Armory_Hall_Props", armory_props)
    z = H0A
    for i, x in enumerate((-5.0, 5.0)):
        station("Armory_Inspect_%02d" % (i + 1), "inspect", "Inspect Gear", b_dais, x, -3.5, z, share="arm_dais",
                prompt_h=1.6, colliders=[(0, 0, 0.15, 3.9, 3.9, 0.3)])
    station("Armory_Panoply_01", "featured", "View Golden Panoply", b_panoply, 0.0, 2.0, z, prompt_h=2.0,
            colliders=[(0, 0, 0.3, 6.0, 6.0, 0.6)])
    for i, x in enumerate((-8.5, 0.0, 8.5)):
        station("Armory_Counter_%02d" % (i + 1), "merchant", "Browse & Buy", b_counter, x, 9.0, z, share="arm_counter",
                prompt_h=1.8, colliders=[(0, 0, 0.65, 4.5, 1.5, 1.3)])
        marker("Armory_Merchant_%02d" % (i + 1), "npc_spot", "Merchant stands here", x, 10.7, z + 0.15)
    tiers = ["bronze", "iron", "steel", "gold"]
    for side, sx in enumerate((-1, 1)):
        for k, y in enumerate((-8.0, -3.0, 2.0, 7.0)):
            tier = tiers[k] if side == 0 else tiers[3 - k]
            station("Armory_Display_%02d" % (side * 4 + k + 1), "armor_display", "Inspect %s Armor" % tier.title(),
                    lambda b, e, t=tier: b_display(b, e, t), sx * 12.6, y, z, lrot=-sx * math.pi / 2,
                    share="arm_disp_" + tier, prompt_h=1.8, tier=tier)
    for i, x in enumerate((-8.0, 8.0)):
        station("Armory_Showcase_%02d" % (i + 1), "weapon_showcase", "View Weapons", b_showcase, x, 13.0, z,
                share="arm_show", prompt_h=1.6, colliders=[(0, 0, 2.4, 6.2, 1.1, 4.8)])
    marker("Armory_Entrance", "zone", "Armory entrance", 0.0, -20.5, 0.4)


# ============================ DISTRICT: PLAZA, LANDMARKS =====================
DIST_FR = Frame(0.0, 0.0, 0.0)


def bench(bm, x, y, rot=0.0):
    with bm.at((x, y, 0), rz=rot):
        for sx in (-1, 1):
            box(bm, (sx * 0.9, 0, 0.25), (0.25, 0.6, 0.5), C.STONE_LIGHT, ch=0.03)
        box(bm, (0, 0, 0.55), (2.4, 0.6, 0.10), C.WOOD_LIGHT, ch=0.02)
        box(bm, (0, 0.26, 0.92), (2.4, 0.08, 0.5), C.WOOD, ch=0.02)


def banner_pole(bm, ex, x, y, h=8.5, motif="bull", col=C.CREAM):
    box(bm, (x, y, 0.3), (1.1, 1.1, 0.6), C.STONE_LIGHT, ch=0.05)
    beam(bm, (x, y, 0.5), (x, y, h), 0.13, 0.09, C.WOOD_DARK, 8)
    sbeam(bm, (x - 1.1, y, h - 0.55), (x + 1.1, y, h - 0.55), 0.10, 0.10, C.WOOD_DARK)
    blob(bm, (x, y, h + 0.15), (0.16, 0.16, 0.2), C.GOLD, segs=6, rings=3)
    frustum(bm, T((x, y, h + 0.3)), 0.10, 0.0, 0.45, C.GOLD, segs=5)
    banner(bm, x, y - 0.12, h - 0.5, 1.8, 4.4, motif=motif, col=col)


def signpost(bm, x, y, word, d):
    beam(bm, (x, y, 0), (x, y, 4.3), 0.12, 0.12, C.WOOD_DARK, 8)
    prism(bm, [(-1.9 * d, -0.45), (1.5 * d, -0.45), (2.3 * d, 0), (1.5 * d, 0.45), (-1.9 * d, 0.45)],
          (x, y - 0.12, 3.5), 1.0, 0.10, C.MAROON)
    text(bm, word, (x - 0.15 * d, y - 0.2, 3.5), 0.5, C.CREAM, depth=0.04, stroke_w=0.18)
    blob(bm, (x, y, 4.45), (0.16, 0.16, 0.2), C.GOLD, segs=6, rings=3)


def dummy(bm, x, y, rot=0.0):
    with bm.at((x, y, 0), rz=rot):
        box(bm, (0, 0, 0.15), (1.0, 1.0, 0.3), C.STONE, ch=0.03)
        beam(bm, (0, 0, 0.3), (0, 0, 2.3), 0.10, 0.10, C.WOOD, 6)
        sbeam(bm, (-0.75, 0, 1.8), (0.75, 0, 1.8), 0.12, 0.12, C.WOOD)
        blob(bm, (0, 0, 1.45), (0.3, 0.2, 0.42), C.PLASTER, segs=6, rings=4)
        blob(bm, (0, 0, 2.45), (0.22, 0.22, 0.24), C.PLASTER, segs=6, rings=3)
        helmet(bm, (0, 0, 2.58), 0.75, C.IRON_LIGHT, C.MAROON)
        shield(bm, (-0.62, -0.28, 1.55), 0.34, C.MAROON, C.BRONZE, "bull")
        box(bm, (0.62, -0.1, 1.5), (0.08, 0.08, 0.9), C.WOOD_DARK)


def stall(bm, ex, x, y, rot=0.0, motif="forge"):
    with bm.at((x, y, 0), rz=rot):
        for sx in (-1, 1):
            for sy in (-1, 1):
                box(bm, (sx * 1.8, sy * 1.0, 1.6), (0.2, 0.2, 3.2), C.WOOD, ch=0.02)
        for i in range(6):
            x0, x1 = -2.2 + 4.4 * i / 6, -2.2 + 4.4 * (i + 1) / 6
            quad_slab(bm, [(x0, 1.3, 3.7), (x1, 1.3, 3.7), (x1, -1.3, 3.25), (x0, -1.3, 3.25)], 0.08,
                      C.MAROON if i % 2 == 0 else C.CREAM)
        box(bm, (0, -0.7, 0.55), (3.4, 0.9, 1.1), C.WOOD_LIGHT, ch=0.03)
        box(bm, (0, -0.7, 1.15), (3.6, 1.1, 0.10), C.PLANK, ch=0.02)
        helmet(bm, (-1.0, -0.7, 1.45), 0.8, C.BRONZE, C.MAROON)
        helmet(bm, (0.2, -0.7, 1.45), 0.8, C.IRON_LIGHT, C.CREAM)
        shield(bm, (1.2, -0.35, 1.7), 0.45, C.MAROON, C.BRONZE, motif, C.GOLD)
        for i in range(3):
            sword(bm, -1.4 + i * 0.35, 0.75, 0.05, 1.1)
        barrel(bm, 1.2, 0.9)
        lantern(bm, ex, 0.0, 0.0, 2.6, 0.55)
        banner(bm, 0.0, -1.35, 3.2, 1.2, 1.8, motif=motif, col=C.GOLD, both=False)


def plaza_floor(bm, ex):
    box(bm, (0, 0, -0.04), (30.0, 32.0, 0.24), C.STONE, ch=0.03)
    collide("Plaza", 0, 0, -0.04, 30.0, 32.0, 0.24)
    z = 0.086
    for x in range(-12, 13, 3):
        box(bm, (x, 0, z), (0.07, 32.0, 0.012), C.STONE_DARK)
    for y in range(-15, 16, 3):
        box(bm, (0, y, z), (30.0, 0.07, 0.012), C.STONE_DARK)
    for _ in range(26):
        box(bm, (rng.uniform(-13, 13), rng.uniform(-14, 14), z + 0.004), (rng.uniform(1.8, 2.6), rng.uniform(1.8, 2.6), 0.012),
            C.STONE_LIGHT, rot=0.0)
    ring(bm, T((0, 0, z + 0.01)), 7.4, 7.15, 0.02, C.BRONZE, segs=48)
    ring(bm, T((0, 0, z + 0.01)), 9.2, 9.05, 0.02, C.MAROON, segs=48)
    for i in range(8):
        a = math.tau * i / 8
        box(bm, (5.4 * math.cos(a), 5.4 * math.sin(a), z + 0.02), (3.6, 0.14, 0.012), C.BRONZE, rot=a)
    for sy in (-1, 1):
        box(bm, (0, sy * 16.1, 0.18), (30.4, 0.5, 0.36), C.STONE_LIGHT, ch=0.04)
    for sx in (-1, 1):
        box(bm, (sx * 15.1, 0, 0.18), (0.5, 32.4, 0.36), C.STONE_LIGHT, ch=0.04)
    for sx in (-1, 1):
        for sy in (-1, 1):
            planter(bm, sx * 13.0, sy * 14.4, 2.4, 1.0)
        planter(bm, sx * 6.0, 14.9, 2.4, 0.9)
    for sx in (-1, 1):
        bench(bm, sx * 11.0, -8.0, 0.0)
        bench(bm, sx * 11.0, 9.0, math.pi)


def fire_bowl(bm, ex, x, y):
    """Eternal-flame bowl on a stone pedestal (four of them ring the monument)."""
    box(bm, (x, y, 0.25), (1.5, 1.5, 0.5), C.STONE_LIGHT, ch=0.05)
    frustum(bm, T((x, y, 0.5)), 0.55, 0.42, 1.5, C.STONE_LIGHT, segs=8)
    for dz in (0.7, 1.7):
        frustum(bm, T((x, y, dz)), 0.50, 0.50, 0.10, C.BRONZE, segs=8)
    frustum(bm, T((x, y, 2.0)), 0.45, 1.15, 0.7, C.BRONZE, segs=12)
    ring(bm, T((x, y, 2.7)), 1.22, 1.05, 0.10, C.GOLD, segs=12)
    flame(ex, x, y, 2.75, 0.85, 1.9)
    collide("Plaza_FireBowl", x, y, 1.0, 1.5, 1.5, 2.0)


def plaza_props(bm, ex):
    for sx in (-1, 1):                                        # west half = Forge, east half = Armory
        for sy in (-1, 1):
            banner_pole(bm, ex, sx * 9.5, sy * 9.5, 9.5, "forge" if sx < 0 else "armory", C.GOLD)
    for sx in (-1, 1):
        for sy in (-1, 1):
            fire_bowl(bm, ex, sx * 5.94, sy * 5.94)
    for i, (x, y) in enumerate(((-10.5, 11.5), (-7.5, 12.5), (7.5, 12.5), (10.5, 11.5))):
        dummy(bm, x, y, 0.0)
    stall(bm, ex, -11.0, -12.0, 0.0, "forge")
    stall(bm, ex, 11.0, -12.0, 0.0, "armory")
    signpost(bm, -4.6, -14.4, "FORGE", -1)
    signpost(bm, 4.6, -14.4, "ARMORY", 1)
    for sx in (-1, 1):
        barrel(bm, sx * 14.0, -4.0)
        barrel(bm, sx * 14.0 + 0.1, -5.0)
        crate(bm, sx * 14.0, 4.0, 0.0, 1.0, rot=0.4)


def monument(bm, ex):
    """The Great Anvil: a clean sculpture on a stepped plinth. Crests on the plinth point to what is
    behind them: Forge (west), Armory (east), camp bull (south toward the gate / north toward the tower).
    The eternal flames burn in four separate fire bowls around it (see fire_bowl)."""
    z0 = 0.08
    for i, (r0, r1) in enumerate(((6.3, 6.1), (5.2, 5.0), (4.2, 4.0))):
        frustum(bm, T((0, 0, z0 + i * 0.22)), r0, r1, 0.22, (C.STONE_LIGHT, C.STONE, C.MARBLE)[i], segs=28)
        collide("Monument_Tier", 0, 0, z0 + i * 0.22 + 0.11, r0 * 2, r0 * 2, 0.22)
    zp = z0 + 0.66
    box(bm, (0, 0, zp + 0.8), (3.6, 3.6, 1.6), C.MARBLE, ch=0.06)
    for dz in (0.1, 1.5):
        box(bm, (0, 0, zp + dz), (3.75, 3.75, 0.12), C.BRONZE)
    for k, kind, col in ((0, "bull", C.CREAM), (1, "armory", C.GOLD), (2, "bull", C.CREAM), (3, "forge", C.GOLD)):
        with bm.at((0, 0, zp + 0.8), rz=k * math.pi / 2):
            box(bm, (0, -1.81, 0), (2.1, 0.05, 1.3), C.MAROON)
            insignia(bm, kind, (0, -1.85, 0), 0.72, col, True)
    collide("Monument_Plinth", 0, 0, zp + 0.8, 3.7, 3.7, 1.6)
    za = zp + 1.6
    box(bm, (0, 0, za + 0.15), (2.9, 1.9, 0.30), C.IRON, ch=0.04)               # foot
    box(bm, (0, 0, za + 0.78), (1.7, 1.3, 1.1), C.IRON, ch=0.05)                # waist
    box(bm, (0, 0, za + 0.55), (1.85, 1.45, 0.14), C.BRONZE)                    # bronze band
    box(bm, (0, 0, za + 1.42), (4.6, 1.6, 0.44), C.STEEL, ch=0.06)              # face
    frustum(bm, T((2.3, 0, za + 1.42)) @ ROT_Y90, 0.62, 0.10, 2.3, C.STEEL, segs=10)   # horn
    box(bm, (-2.6, 0, za + 1.30), (0.8, 1.4, 0.4), C.IRON, ch=0.03)             # heel
    box(bm, (-1.4, 0, za + 1.645), (0.30, 0.30, 0.02), C.COAL)                  # hardy hole
    box(bm, (-0.5, 0, za + 1.645), (0.16, 0.16, 0.02), C.COAL)                  # pritchel hole
    collide("Monument_Anvil", 0, 0, za + 0.9, 4.6, 1.6, 1.8)


def beacon_tower(bm, ex):
    """Beacon of Craft: octagonal tower, bronze bands, lamp room, bull-horn crown."""
    box(bm, (0, 0, 0.2), (11.0, 11.0, 0.4), C.STONE_LIGHT, ch=0.05)
    collide("Beacon_Base", 0, 0, 0.2, 11.0, 11.0, 0.4)
    for j in range(3):
        box(bm, (0, -5.9 - 0.5 * j, 0.1 * (3 - j)), (6.0 + 1.0 * j, 0.5, 0.2 * (3 - j) if j < 3 else 0.1), C.STONE, ch=0.02)
    H, r0, r1 = 18.0, 3.7, 2.6

    def rad(z):
        return r0 - (r0 - r1) * (z - 0.4) / H

    frustum(bm, T((0, 0, 0.4)), r0, r1, H, C.STONE, segs=8, rot=math.pi / 8)
    collide("Beacon_Shaft", 0, 0, 9.4, 6.6, 6.6, 18.0)
    for z in (3.0, 8.0, 13.0):
        frustum(bm, T((0, 0, z)), rad(z) + 0.08, rad(z + 0.4) + 0.08, 0.4, C.BRONZE, segs=8, rot=math.pi / 8)
    for z in (5.0, 9.5, 14.0):
        a = rad(z) * math.cos(math.pi / 8)
        box(bm, (0, -a, z), (0.45, 0.14, 1.5), C.COAL)
        for sx in (-1, 1):
            box(bm, (sx * 0.34, -a, z), (0.12, 0.18, 1.6), C.STONE_LIGHT)
    a0 = rad(1.6) * math.cos(math.pi / 8)
    box(bm, (0, -a0, 1.8), (2.0, 0.2, 2.8), C.WOOD_DARK)
    box(bm, (0, -a0 - 0.05, 3.3), (2.5, 0.3, 0.3), C.STONE_LIGHT, ch=0.03)
    # balcony, lamp room, crown
    frustum(bm, T((0, 0, 18.4)), 4.1, 4.1, 0.4, C.STONE_LIGHT, segs=16)
    ring(bm, T((0, 0, 18.8)), 4.0, 3.9, 0.9, C.BRONZE, segs=16)
    for i in range(8):
        a = math.tau * i / 8 + math.pi / 8
        box(bm, (3.0 * math.cos(a), 3.0 * math.sin(a), 18.8 + 1.15), (0.4, 0.4, 2.3), C.STONE_LIGHT, ch=0.04)
    frustum(ex.glow, T((0, 0, 18.8)), 1.6, 1.1, 2.4, C.EMBER, segs=8)
    frustum(ex.glow, T((0, 0, 18.8)), 0.9, 0.5, 3.0, C.MOLTEN, segs=6)
    frustum(bm, T((0, 0, 21.1)), 3.6, 3.4, 0.35, C.BRONZE, segs=16)
    frustum(bm, T((0, 0, 21.45)), 3.4, 0.0, 3.0, C.ROOF, segs=16)
    for sx in (-1, 1):
        pts = [(sx * 0.4, 24.2), (sx * 1.1, 24.6), (sx * 1.7, 25.5), (sx * 1.65, 26.6)]
        for k in range(3):
            beam(bm, (pts[k][0], 0, pts[k][1]), (pts[k + 1][0], 0, pts[k + 1][1]), 0.16 - 0.03 * k, 0.13 - 0.03 * k, C.GOLD, 5)
    blob(bm, (0, 0, 24.5), (0.3, 0.3, 0.4), C.GOLD, segs=6, rings=3)
    a1 = rad(8.0) * math.cos(math.pi / 8)
    banner(bm, -1.3, -a1 - 0.18, 16.6, 2.2, 8.4, motif="bull")
    banner(bm, 1.3, -a1 - 0.18, 16.6, 2.2, 8.4, motif="bull")
    for x in (-1.3, 1.3):
        sbeam(bm, (x, -rad(16.6) * 0.92, 16.6), (x, -a1 - 0.18, 16.6), 0.14, 0.14, C.WOOD_DARK)
    marker("Beacon_Flame", "effect_fire", "Beacon of Craft", 0, 0, 22.0)


def shield_wall(bm, ex):
    for sx in (-1, 1):
        x0, x1 = (6.9, 16.6) if sx > 0 else (-16.6, -6.9)
        xc = (x0 + x1) / 2
        box(bm, (xc, 16.5, 1.8), (x1 - x0, 1.0, 3.6), C.STONE, ch=0.04)
        box(bm, (xc, 16.5, 3.75), (x1 - x0 + 0.4, 1.4, 0.3), C.STONE_LIGHT, ch=0.03)
        collide("ShieldWall", xc, 16.5, 1.8, x1 - x0, 1.0, 3.6)
        for i in range(4):
            x = (x0 + 1.2 + i * (x1 - x0 - 2.4) / 3)
            shield(bm, (x, 15.92, 2.0), 1.0, C.MAROON, C.BRONZE, "bull", C.CREAM)
            box(bm, (x, 16.3, 3.4), (0.14, 0.2, 0.2), C.IRON)
        for x in (x0 + 0.2, x1 - 0.2):
            box(bm, (x, 16.5, 2.5), (1.0, 1.5, 5.0), C.STONE_LIGHT, ch=0.04)
            frustum(bm, T((x, 16.5, 5.0)), 0.5, 0.85, 0.5, C.BRONZE, segs=8)
            flame(ex, x, 16.5, 5.55, 0.5, 1.3)
            collide("ShieldWall_Pylon", x, 16.5, 2.5, 1.0, 1.5, 5.0)


def forge_gate(bm, ex):
    """Grand entrance to the district; the promenade runs through it."""
    for sx in (-1, 1):
        x = sx * 6.5
        box(bm, (x, 0, 0.3), (3.8, 3.8, 0.6), C.STONE_DARK, ch=0.06)
        box(bm, (x, 0, 4.8), (3.0, 3.0, 8.4), C.STONE, ch=0.08)
        box(bm, (x, 0, 9.3), (3.6, 3.6, 0.7), C.STONE_LIGHT, ch=0.06)
        for z in (1.8, 7.6):
            box(bm, (x, 0, z), (3.15, 3.15, 0.16), C.BRONZE)
        shield(bm, (x, -1.55, 5.0), 1.0, C.MAROON, C.BRONZE, "forge" if sx < 0 else "armory", C.GOLD)
        frustum(bm, T((x, 0, 9.65)), 0.7, 1.2, 0.7, C.BRONZE, segs=10)
        flame(ex, x, 0, 10.4, 0.8, 2.0)
        collide("Gate_Pylon", x, 0, 4.8, 3.8, 3.8, 9.6)
        box(bm, (sx * 12.0, 0, 0.8), (7.2, 1.0, 1.6), C.STONE, ch=0.04)
        box(bm, (sx * 12.0, 0, 1.7), (7.6, 1.3, 0.25), C.STONE_LIGHT, ch=0.03)
        collide("Gate_Wall", sx * 12.0, 0, 0.8, 7.2, 1.0, 1.6)
    box(bm, (0, 0, 10.2), (16.4, 2.4, 1.6), C.STONE, ch=0.06)
    box(bm, (0, 0, 11.2), (17.0, 2.7, 0.4), C.STONE_LIGHT, ch=0.04)
    box(bm, (0, -1.28, 10.2), (14.4, 0.10, 1.2), C.MAROON)
    text(bm, "FORGE", (-3.6, -1.38, 10.2), 0.78, C.CREAM, depth=0.07, stroke_w=0.17)
    text(bm, "ARMORY", (3.7, -1.38, 10.2), 0.78, C.CREAM, depth=0.07, stroke_w=0.17)
    frustum(bm, T((0, -1.25, 10.2)) @ ROT_X90, 0.78, 0.78, 0.14, C.BRONZE, segs=14)
    emblem(bm, (0, -1.43, 10.1), 0.5, C.CREAM, C.MAROON, t=0.05, flat=True)
    banner(bm, -2.7, -1.5, 9.4, 1.5, 3.2, motif="forge", col=C.GOLD)
    banner(bm, 2.7, -1.5, 9.4, 1.5, 3.2, motif="armory", col=C.GOLD)


def promenade(bm, ex):
    box(bm, (0, -25.0, -0.04), (14.0, 18.0, 0.24), C.STONE, ch=0.03)
    collide("Promenade", 0, -25.0, -0.04, 14.0, 18.0, 0.24)
    z = 0.086
    for y in range(-33, -15, 3):
        box(bm, (0, y, z), (14.0, 0.07, 0.012), C.STONE_DARK)
    for x in (-3, 0, 3):
        box(bm, (x, -25.0, z), (0.07, 18.0, 0.012), C.STONE_DARK)
    box(bm, (0, -25.0, z + 0.01), (2.6, 18.0, 0.012), C.MAROON)
    for sx in (-1, 1):
        box(bm, (sx * 1.4, -25.0, z + 0.015), (0.12, 18.0, 0.012), C.GOLD)
        box(bm, (sx * 7.15, -25.0, 0.18), (0.5, 18.0, 0.36), C.STONE_LIGHT, ch=0.04)
    for y in (-31.0, -22.0):
        floor_emblem(bm, 0, y, z + 0.02, 1.2)


def promenade_props(bm, ex):
    for i, y in enumerate((-31.0, -27.0, -23.0, -19.0)):
        for sx in (-1, 1):
            banner_pole(bm, ex, sx * 8.2, y, 8.5, "bull", C.CREAM)
    for y in (-29.0, -25.0, -21.0):
        for sx in (-1, 1):
            standing_brazier(bm, ex, sx * 6.2, y, 1.7)
    for sx in (-1, 1):
        bench(bm, sx * 6.6, -17.5, 0.0)


def district_ground(bm, ex):
    box(bm, (0, -5, -0.5), (140.0, 120.0, 1.0), C.GRASS)
    for _ in range(40):
        box(bm, (rng.uniform(-60, 60), rng.uniform(-55, 45), 0.012), (rng.uniform(4, 10), rng.uniform(4, 10), 0.03),
            C.GRASS_LIGHT, rot=rng.uniform(0, math.pi))
    collide("DistrictGround", 0, -5, -0.5, 140.0, 120.0, 1.0)


def build_district():
    use_frame(DIST_FR)
    static("Forge_Plaza", plaza_floor)
    static("Forge_Plaza_Props", plaza_props)
    static("Forge_AnvilMonument", monument)
    frame_t = Frame(0.0, 23.0, 0.0)
    use_frame(frame_t)
    static("Forge_BeaconTower", beacon_tower)
    use_frame(DIST_FR)
    static("Forge_ShieldWall", shield_wall)
    use_frame(Frame(0.0, -34.0, 0.0))
    static("Forge_Gate", forge_gate)
    use_frame(DIST_FR)
    static("Forge_Promenade", promenade)
    static("Forge_Promenade_Props", promenade_props)
    static("Forge_Ground", district_ground, trim=False)
    marker("District_Spawn", "spawn", "Arrival point", 0.0, -30.0, 0.4)
    marker("Monument_Plaza", "zone", "Plaza centre", 0.0, -10.0, 0.4)
    for i, (sx, sy) in enumerate(((-1, -1), (1, -1), (-1, 1), (1, 1))):
        marker("Plaza_Flame_%02d" % (i + 1), "effect_fire", "Eternal flame", sx * 5.94, sy * 5.94, 3.2)


# ============================ BUILD EVERYTHING ===============================
build_district()
build_forge()
build_armory()


# ============================ REPORT =========================================
print("\n=== Camp DemiSoul Forge & Armory district: report (units = studs) ===")
over = [n for n, t in MESHES.items() if t > TRI_WARN]
tot = sum(MESHES.values())
big = sorted(MESHES.items(), key=lambda kv: -kv[1])[:10]
print("Objects in scene : %d   (unique meshes: %d)" % (len(OBJECTS), len(MESHES)))
print("Unique triangles : %d   (largest single mesh below)" % tot)
for n, t in big:
    print("   %-28s %6d tris%s" % (n, t, "   <-- OVER BUDGET" if t > TRI_WARN else ""))
print("Stations/markers : %d   Collision boxes: %d" % (len(STATIONS), len(COLLIDERS)))
kinds = {}
for s in STATIONS:
    kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
print("By kind          :", ", ".join("%s x%d" % kv for kv in sorted(kinds.items())))
if over:
    print("WARNING over budget:", over)


# ============================ EXPORT: JSON + LUA + FBX =======================
def rbx(p):
    return [round(p[0] * STUD_SCALE, 2), round(p[2] * STUD_SCALE, 2), round(-p[1] * STUD_SCALE, 2)]


def lua_table(items, kind):
    rows = []
    for it in items:
        p = rbx(it["pos"])
        deg = round(math.degrees(it["rot"]), 2)
        if kind == "collider":
            s = it["size"]
            rows.append('  {name=%s, pos=Vector3.new(%s,%s,%s), rotY=%s, size=Vector3.new(%s,%s,%s)},' % (
                json.dumps(it["name"]), p[0], p[1], p[2], deg,
                round(s[0] * STUD_SCALE, 2), round(s[2] * STUD_SCALE, 2), round(s[1] * STUD_SCALE, 2)))
        else:
            rows.append('  {name=%s, kind=%s, label=%s, pos=Vector3.new(%s,%s,%s), rotY=%s},' % (
                json.dumps(it["name"]), json.dumps(it["kind"]), json.dumps(it["label"]), p[0], p[1], p[2], deg))
    return "\n".join(rows)


LUA_HEAD = '''-- Camp DemiSoul Forge & Armory: collision + interaction setup. Generated by the Blender script.
-- 1) Import the FBX at the world origin. 2) Paste this into the Studio command bar (or a Script run once).
-- Creates Model "ForgeDistrict_Interaction": invisible collision boxes + ProximityPrompt anchors.
-- If the imported meshes are offset/mirrored, move this whole model by the same amount (or tell me).
local root = workspace:FindFirstChild("ForgeDistrict_Interaction")
if root then root:Destroy() end
root = Instance.new("Model"); root.Name = "ForgeDistrict_Interaction"; root.Parent = workspace
local colFolder = Instance.new("Folder"); colFolder.Name = "Collision"; colFolder.Parent = root
local stFolder = Instance.new("Folder"); stFolder.Name = "Stations"; stFolder.Parent = root
local COLLIDERS = {
'''
LUA_MID = '''}
local STATIONS = {
'''
LUA_TAIL = '''}
for _, c in ipairs(COLLIDERS) do
  local p = Instance.new("Part")
  p.Name = c.name; p.Anchored = true; p.CanCollide = true; p.Transparency = 1
  p.CanTouch = false
  p.Size = c.size; p.CFrame = CFrame.new(c.pos) * CFrame.Angles(0, math.rad(c.rotY), 0)
  p.Parent = colFolder
end
local PROMPT_KINDS = {furnace=true, kiln=true, casting=true, anvil=true, quench=true, grind=true, assembly=true,
  merchant=true, inspect=true, armor_display=true, weapon_showcase=true, featured=true}
for _, s in ipairs(STATIONS) do
  local a = Instance.new("Part")
  a.Name = s.name; a.Anchored = true; a.CanCollide = false; a.CanTouch = false; a.CanQuery = false
  a.Transparency = 1; a.Size = Vector3.new(1, 1, 1)
  a.CFrame = CFrame.new(s.pos) * CFrame.Angles(0, math.rad(s.rotY), 0)
  a:SetAttribute("StationType", s.kind); a:SetAttribute("StationLabel", s.label)
  a.Parent = stFolder
  if PROMPT_KINDS[s.kind] then
    local pp = Instance.new("ProximityPrompt")
    pp.ActionText = s.label; pp.ObjectText = s.name:gsub("_", " ")
    pp.HoldDuration = 0; pp.MaxActivationDistance = 12; pp.RequiresLineOfSight = false
    pp.Parent = a
  end
end
print(("ForgeDistrict_Interaction: %d collision boxes, %d stations"):format(#COLLIDERS, #STATIONS))
'''


def write_exports():
    if not OUT:
        return
    data = {
        "units": "studs", "note": "Roblox position = (x*S, z*S, -y*S); rotY degrees about +Y; size = (x, z, y)*S",
        "stud_scale": STUD_SCALE,
        "stations": [dict(s, pos=rbx(s["pos"]), rotY=round(math.degrees(s["rot"]), 2)) for s in STATIONS],
        "colliders": [dict(c, pos=rbx(c["pos"]), size=[round(c["size"][0] * STUD_SCALE, 2), round(c["size"][2] * STUD_SCALE, 2),
                                                       round(c["size"][1] * STUD_SCALE, 2)],
                           rotY=round(math.degrees(c["rot"]), 2)) for c in COLLIDERS],
    }
    for s in data["stations"]:
        s.pop("rot", None)
    for c in data["colliders"]:
        c.pop("rot", None)
    with open(os.path.join(OUT, "Forge_StationMarkers.json"), "w") as fh:
        json.dump(data, fh, indent=1)
    with open(os.path.join(OUT, "Forge_District_Setup.lua"), "w") as fh:
        fh.write(LUA_HEAD + lua_table(COLLIDERS, "collider") + LUA_MID + lua_table(STATIONS, "station") + LUA_TAIL)


def export_fbx(path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in OBJECTS:
        o.select_set(True)
    bpy.context.view_layer.objects.active = OBJECTS[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                             add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE")


if EXPORT and OUT:
    try:
        write_exports()
        print("Wrote StationMarkers.json + Forge_District_Setup.lua to:", OUT)
    except Exception as exc:
        print("Marker/Lua export failed:", exc)
    try:
        fbx_path = os.path.join(OUT, "CampDemiSoul_ForgeDistrict.fbx")
        export_fbx(fbx_path)
        print("Exported:", fbx_path)
        print("Palette :", PNG_PATH)
    except Exception as exc:
        print("FBX export failed (the models are still in the scene):", exc)

try:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces[0].shading.type = "SOLID"
            area.spaces[0].shading.color_type = "TEXTURE"
except Exception:
    pass
