# =============================================================================
# CAMP DEMISOUL - THE PROVING GROUNDS (archery + sparring training complex)
# Run in Blender's Scripting tab (3.6 / 4.x). Safe to re-run: it only replaces
# its own collection ("ProvingGrounds_GameReady"). Same engine, scale (3 studs per
# metre), palette system and station-marker system as the Entrance and Forge District.
#
# LAYOUT (origin = centre of the Muster Yard, +Y = north = the way arrows fly)
#   Muster Yard (hub) -> west: Archers' Walk -> Waiting Terrace -> 5 archery lanes (40/70/100 studs)
#                                              + Hydra Bay (boss target at 60 studs)
#                     -> north: THE CAUSEWAY (raised two-sided viewing walk) -> Pavilion -> Trophy Shrine
#                     -> east: Gladiators' Way -> Drill Yard (6 dummies, 2 duel rings) -> Sparring Arena
#
# EMBLEM RULES (extends the Forge District rules; one meaning per crest)
#   BULL (cream) = the camp.  LAUREL (bull in a wreath) = the Proving Grounds as a whole.
#   ARCHERY (gold) = bow + crossed arrows: west half.   SPARRING (gold) = helmet over crossed
#   practice swords: east half.   FORGE / ARMORY crests are NOT used here.
#
# GAMEPLAY HOOKS
#   * Every interactive piece is its own mesh with its origin at its floor/face centre:
#     Archery_Target_01..15 (shared meshes), Archery_Hydra + Archery_HydraHead_01..05,
#     Sparring_Dummy_01..06, Sparring_DuelRing_01..02, queue boards, racks, signs, gates...
#   * Companion meshes: <name>_Glow (set Neon).  Zone volumes (safe / archery / hydra / arena)
#     and station anchors are written to JSON + a Roblox Lua setup script.
#   * Palette v3: the first 39 colours are identical to palette v2 (Forge) and the first 20 to the
#     entrance palette, so every district can share this one PNG.
# =============================================================================

import bpy, bmesh, math, os, random, struct, zlib, json
from contextlib import contextmanager
from mathutils import Vector, Matrix

# ------------------------------ SETTINGS -------------------------------------
STUD_SCALE = 3.0        # studs per modelled metre (same as the entrance)
EXPORT = True
EXPORT_DIR = ""         # blank = next to your .blend (or home folder if unsaved)
COLLECTION_NAME = "ProvingGrounds_GameReady"
TRI_WARN = 20000
SEED = 52
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
    # proving grounds additions (39-50)
    ("STRAW", "#C9A45C"), ("STRAW_DARK", "#8F7338"), ("ROPE", "#B08A55"), ("CANVAS", "#D8CDA8"),
    ("TARGET_RED", "#B4301F"), ("TARGET_BLUE", "#2E6F82"), ("TARGET_YELLOW", "#F0B21A"), ("MEADOW_GOLD", "#B8A04A"),
    ("SAND", "#C8B079"), ("OLIVE", "#7C8A5A"), ("CYPRESS", "#2B4A35"), ("BARK", "#4A3A2B"),
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
        d = os.path.join(base, "CampDemiSoul_Proving_Export")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception as exc:
        print("Could not create export folder:", exc)
        return None


OUT = output_dir()
PNG_PATH = None
if OUT:
    try:
        PNG_PATH = os.path.join(OUT, "DemiSoul_Palette_v3.png")
        write_palette_png(PNG_PATH)
    except Exception as exc:
        print("Could not write palette PNG:", exc)
        PNG_PATH = None


def make_material(png_path):
    mat = bpy.data.materials.get("DemiSoul_Palette_v3") or bpy.data.materials.new("DemiSoul_Palette_v3")
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
    elif kind == "archery":
        # a bow drawn with a single arrow: belly toward the target (right), string pulled back to the nock
        sh = 0.17                                                              # centre the emblem
        bow = [(-0.20, 0.90), (0.20, 0.55), (0.35, 0.0), (0.20, -0.55), (-0.20, -0.90)]
        stroke(bm, [S((x - sh, z)) for x, z in bow], c, 0.11 * s, color, t, flat)           # limbs
        stroke(bm, [S((-0.20 - sh, 0.90)), S((-0.50 - sh, 0.0)), S((-0.20 - sh, -0.90))], c, 0.04 * s, color, t, flat)  # string
        line((-0.50 - sh, 0.0), (0.66 - sh, 0.0), 0.065)                                     # arrow shaft
        _tri(bm, S((0.90 - sh, 0.0)), (1.0, 0.0), (0.0, 1.0), 0.28 * s, 0.10 * s, c, 1.0, t, color, flat)   # arrowhead
        for k in (0.0, 0.12):                                                                  # fletching
            x0 = -0.50 - sh + k
            line((x0, 0.0), (x0 - 0.12, 0.13), 0.045)
            line((x0, 0.0), (x0 - 0.12, -0.13), 0.045)
    elif kind == "sparring":
        # crested helmet over two crossed practice swords
        for sx in (-1, 1):
            a, b = (-sx * 0.72, -0.86), (sx * 0.60, 0.22)
            d = unit(a, b)
            n = (-d[1], d[0])
            line(a, (b[0] - d[0] * 0.18, b[1] - d[1] * 0.18), 0.10)
            _tri(bm, S((b[0] + d[0] * 0.14, b[1] + d[1] * 0.14)), d, n, 0.30 * s, 0.07 * s, c, 1.0, t, color, flat)
            g = (a[0] + d[0] * 0.26, a[1] + d[1] * 0.26)
            line((g[0] - n[0] * 0.20, g[1] - n[1] * 0.20), (g[0] + n[0] * 0.20, g[1] + n[1] * 0.20), 0.07)
        helm = [(-0.34, 0.30), (-0.38, 0.60), (-0.20, 0.86), (0.20, 0.86), (0.38, 0.60), (0.34, 0.30),
                (0.12, 0.30), (0.12, 0.50), (-0.12, 0.50), (-0.12, 0.30)]
        prism(bm, helm, (c[0], c[1] - 0.012, c[2]), s, t, color, 1, flat)
        prism(bm, [(-0.30, 0.84), (0.30, 0.84), (0.24, 1.0), (0.0, 1.12), (-0.24, 1.0)],
              (c[0], c[1] - 0.012, c[2]), s, t, color, 1, flat)                      # crest
    elif kind == "laurel":
        # the bull inside a laurel wreath
        emblem(bm, (c[0], c[1], c[2] - 0.02 * s), s * 0.58, color, dark, t=t, flat=flat)
        for sx in (-1, 1):
            for i in range(9):
                ang = math.radians(-112 + i * 24)                     # arc on the right side, mirrored by sx
                px, pz = 0.92 * math.cos(ang), 0.92 * math.sin(ang)
                rot = ang + math.pi / 2
                leaf = [(0, 0), (0.075, 0.12), (0, 0.28), (-0.075, 0.12)]
                pts = [(px * sx + (lx * math.cos(rot) - lz * math.sin(rot)) * sx,
                        pz + (lx * math.sin(rot) + lz * math.cos(rot))) for lx, lz in leaf]
                prism(bm, pts, (c[0], c[1] - 0.006, c[2]), s, t, color, 1, flat)
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
    "0": (0.62, [[(0.31, 1.0), (0.62, 0.5), (0.31, 0.0), (0.0, 0.5), (0.31, 1.0)]]),
    "1": (0.30, [[(0.02, 0.78), (0.24, 1.0), (0.24, 0.0)]]),
    "2": (0.60, [[(0.0, 0.84), (0.30, 1.0), (0.60, 0.80), (0.0, 0.0), (0.60, 0.0)]]),
    "3": (0.60, [[(0.0, 1.0), (0.60, 1.0), (0.26, 0.55), (0.60, 0.30), (0.30, 0.0), (0.0, 0.10)]]),
    "4": (0.65, [[(0.45, 0.0), (0.45, 1.0), (0.0, 0.30), (0.65, 0.30)]]),
    "5": (0.60, [[(0.60, 1.0), (0.05, 1.0), (0.0, 0.55), (0.50, 0.60), (0.60, 0.25), (0.30, 0.0), (0.0, 0.10)]]),
    "6": (0.60, [[(0.55, 1.0), (0.0, 0.50), (0.05, 0.10), (0.30, 0.0), (0.58, 0.18), (0.55, 0.42), (0.05, 0.40)]]),
    "7": (0.60, [[(0.0, 1.0), (0.60, 1.0), (0.22, 0.0)]]),
    "8": (0.60, [[(0.30, 0.5), (0.02, 0.75), (0.30, 1.0), (0.58, 0.75), (0.30, 0.5), (0.0, 0.25), (0.30, 0.0), (0.60, 0.25), (0.30, 0.5)]]),
    "9": (0.60, [[(0.05, 0.0), (0.60, 0.50), (0.55, 0.90), (0.30, 1.0), (0.02, 0.82), (0.05, 0.58), (0.55, 0.60)]]),
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
            collider=True, colliders=None, trim=True, **meta):
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
        me, bb = bake(name, main, trim)
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




# ============================ LAYOUT (authored in STUDS, built in metres) =====
# All coordinates below are studs from the Muster Yard centre; mt() converts to metres.
def mt(v):
    return v / 3.0


def rc(x0, y0, x1, y1):
    """Stud rectangle -> (cx, cy, width, depth) in metres."""
    return mt((x0 + x1) / 2), mt((y0 + y1) / 2), mt(x1 - x0), mt(y1 - y0)


YARD = (-36, -26, 36, 26)
TERR = (-152, 7, -38, 29)            # archery waiting terrace (also serves the Hydra Bay)
FIELD = (-108, 29, -38, 147)         # five archery lanes
BAY = (-152, 29, -114, 147)          # Hydra Bay
BERM = (-114, 29, -108, 147)
FIRE_Y = 35
LANE_CX = [-101, -87, -73, -59, -45]
NEAR_Y, MID_Y, FAR_Y = 75, 105, 135
BACK_Y0, BACK_Y1 = 147, 157
HYDRA_C = (-133, 95)
CW_HALF, CW_STAIR0, CW_WALK0, CW_WALK1, SHR_Y0, SHR_Y1 = 12, 26, 38, 120, 135, 165
PAV = (-20, 84, 20, 108)
DRILL = (44, 22, 108, 59)
RING = (44, 71, 108, 119)
APRON = 12
GROUND = (-190, -100, 160, 200)

ROADS = {
    "approach": ([(0, -100), (2, -80), (-3, -60), (0, -42), (0, -26)], 6.0),
    "archers_walk": ([(-36, 0), (-46, -1), (-56, 2), (-62, 8), (-62, 16)], 6.0),
    "gladiators_way": ([(36, 0), (50, -2), (66, 3), (76, 12), (76, 26)], 6.0),
}


def catmull(pts, per=8):
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for s in range(per):
            t = s / per
            t2, t3 = t * t, t * t * t
            out.append(tuple(0.5 * ((2 * p1[k]) + (-p0[k] + p2[k]) * t
                                    + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t2
                                    + (-p0[k] + 3 * p1[k] - 3 * p2[k] + p3[k]) * t3) for k in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


ROAD_SAMPLES = []
for _k, (_pts, _hw) in ROADS.items():
    ROAD_SAMPLES += catmull(_pts, 6)


def near_road(x, y, margin):
    return any((x - px) ** 2 + (y - py) ** 2 < margin * margin for px, py in ROAD_SAMPLES)


# footprints (studs) that scatter must keep clear of: everything walkable or built
KEEP_OUT = [YARD, TERR, FIELD, BAY, BERM, (-152, 147, -38, 160),
            (-CW_HALF - 4, CW_STAIR0, CW_HALF + 4, SHR_Y1), (-36, 80, 36, 112), (-20, SHR_Y0, 20, SHR_Y1 + 6),
            (DRILL[0] - 4, DRILL[1] - 4, DRILL[2] + 4, DRILL[3]),
            (RING[0] - APRON - 8, RING[1] - APRON - 4, RING[2] + APRON + 8, RING[3] + APRON + 6),
            (-60, -100, 60, -26)]


def dist_rect(x, y, r):
    dx = max(r[0] - x, 0, x - r[2])
    dy = max(r[1] - y, 0, y - r[3])
    return math.hypot(dx, dy)


def free_of_builds(x, y, margin):
    if near_road(x, y, 7 + margin):
        return False
    return all(dist_rect(x, y, r) > margin for r in KEEP_OUT)


# ============================ HELPERS =========================================
use_frame(Frame(0.0, 0.0, 0.0))


def slab(bm, rect, color, top=0.08, th=0.24, ch=0.03, name=None):
    cx, cy, w, d = rc(*rect)
    box(bm, (cx, cy, top - th / 2), (w, d, th), color, ch=ch)
    if name:
        collide(name, cx, cy, top - th / 2, w, d, th)
    return cx, cy, w, d


def joints(bm, rect, step, color, top=0.08, w=0.05):
    cx, cy, W, D = rc(*rect)
    x = cx - W / 2 + step
    while x < cx + W / 2 - 0.05:
        box(bm, (x, cy, top + 0.004), (w, D, 0.012), color)
        x += step
    y = cy - D / 2 + step
    while y < cy + D / 2 - 0.05:
        box(bm, (cx, y, top + 0.004), (W, w, 0.012), color)
        y += step


def patches(bm, rect, n, colors, top=0.08, size=(1.2, 2.2)):
    cx, cy, W, D = rc(*rect)
    for _ in range(n):
        box(bm, (cx + rng.uniform(-W / 2 + 1.2, W / 2 - 1.2), cy + rng.uniform(-D / 2 + 1.2, D / 2 - 1.2), top + 0.006),
            (rng.uniform(*size), rng.uniform(*size), 0.012), rng.choice(colors), rot=rng.uniform(0, math.pi))


def ribbon(bm, pts_studs, half_studs, edge=C.DIRT, mid=C.DIRT_LIGHT, z=0.07):
    P = [(mt(x), mt(y)) for x, y in catmull(pts_studs, 8)]
    hw0 = mt(half_studs)
    rows = []
    n = len(P)
    for i, (x, y) in enumerate(P):
        a, b = P[max(i - 1, 0)], P[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        hw = hw0 * (1 + 0.04 * math.sin(i * 0.9))
        offs = (-(hw + 0.25), -hw, -hw * 0.35, hw * 0.35, hw, hw + 0.25)
        zs = (-0.02, z, z + 0.02, z + 0.02, z, -0.02)
        rows.append([bm.verts.new((x + nx * o, y + ny * o, zz)) for o, zz in zip(offs, zs)])
    cols = (edge, edge, mid, edge, edge)
    for r0, r1 in zip(rows[:-1], rows[1:]):
        for s in range(5):
            vs = [r0[s], r0[s + 1], r1[s + 1], r1[s]]
            p = [v.co for v in vs]
            if (p[1] - p[0]).cross(p[2] - p[1]).z < 0:
                vs = vs[::-1]
            try:
                bm.faces.new(vs).material_index = cols[s]
            except ValueError:
                pass


def fence_run(bm, a, b, gaps=(), spacing=2.67, name="Fence", h=1.33):
    """Post-and-rail fence from stud point a to b. gaps = [(s0, s1)] in studs along the run.
    Gate-side posts are taller with bronze caps. One collision box per solid stretch."""
    ax, ay, bx, by = mt(a[0]), mt(a[1]), mt(b[0]), mt(b[1])
    L = math.hypot(bx - ax, by - ay)
    dx, dy = (bx - ax) / L, (by - ay) / L
    ang = math.atan2(dy, dx)
    gaps = sorted((mt(g0), mt(g1)) for g0, g1 in gaps)
    solids, cur = [], 0.0
    for g0, g1 in gaps:
        if g0 > cur + 0.05:
            solids.append((cur, g0, cur > 0, True))
        cur = g1
    if cur < L - 0.05:
        solids.append((cur, L, cur > 0, False))
    for k, (s0, s1, gate0, gate1) in enumerate(solids):
        n = max(1, int(round((s1 - s0) / spacing)))
        xs = [s0 + (s1 - s0) * i / n for i in range(n + 1)]
        for i, s in enumerate(xs):
            px, py = ax + dx * s, ay + dy * s
            gate = (i == 0 and gate0) or (i == n and gate1)
            ph = h * (1.4 if gate else 1.0)
            box(bm, (px, py, ph / 2), (0.18, 0.18, ph), C.WOOD, rot=ang)
            box(bm, (px, py, 0.11), (0.34, 0.34, 0.22), C.STONE_DARK, rot=ang)
            if gate:
                blob(bm, (px, py, ph + 0.1), (0.16, 0.16, 0.16), C.BRONZE, segs=5, rings=3)
        for z in (0.45, 0.95):
            sbeam(bm, (ax + dx * s0, ay + dy * s0, z), (ax + dx * s1, ay + dy * s1, z), 0.09, 0.10, C.WOOD_LIGHT)
        cm = (s0 + s1) / 2
        collide(name, ax + dx * cm, ay + dy * cm, 0.7, s1 - s0, 0.3, 1.4, lrot=ang)


def sign_arch(bm, ex, cx, cy, span, word, kind, text_h=0.6, post_h=5.0):
    """Timber gate arch with a maroon sign plate, lettering and a crest. Faces -Y."""
    for sx in (-1, 1):
        x = cx + sx * span / 2
        box(bm, (x, cy, 0.2), (0.9, 0.9, 0.4), C.STONE_DARK, ch=0.04)
        box(bm, (x, cy, 0.4 + (post_h - 0.4) / 2), (0.55, 0.55, post_h - 0.4), C.WOOD, ch=0.04)
        for dz in (1.0, 3.2):
            box(bm, (x, cy, dz), (0.62, 0.62, 0.1), C.IRON)
        collide("Arch_Post", x, cy, post_h / 2, 0.9, 0.9, post_h)
        lantern(bm, ex, x, cy - 0.5, post_h - 1.3, 0.0)
    zl = post_h + 0.25
    box(bm, (cx, cy, zl), (span + 1.2, 0.6, 1.1), C.WOOD_LIGHT, ch=0.05)
    box(bm, (cx, cy - 0.34, zl), (span - 0.2, 0.08, 0.9), C.MAROON)
    text(bm, word, (cx, cy - 0.42, zl), text_h, C.CREAM, depth=0.05, stroke_w=0.17)
    frustum(bm, T((cx, cy - 0.1, zl + 1.6)) @ ROT_X90, 0.78, 0.78, 0.12, C.BRONZE, segs=16)
    insignia(bm, kind, (cx, cy - 0.30, zl + 1.6), 0.5, C.GOLD, True)
    box(bm, (cx, cy, zl + 0.85), (0.5, 0.4, 0.5), C.WOOD_DARK)


@contextmanager
def at_all(bm, ex, loc=(0, 0, 0), rz=0.0, rx=0.0):
    """Place the main mesh AND its glow/water companions with the same offset (a plain bm.at() leaves the
    companions behind, which floated lantern glows and sank flames)."""
    with bm.at(loc, rz, rx), ex.glow.at(loc, rz, rx), ex.water.at(loc, rz, rx):
        yield


def zone(name, kind, label, rect, z0=0.0, z1=40.0):
    cx, cy, w, d = rc(*rect)
    STATIONS.append(dict(name=name, kind=kind, label=label, pos=(cx, cy, (z0 + z1) / 2), rot=0.0, size=(w, d, z1 - z0)))


# ---- instancing: build a variant mesh once, drop many linked copies ----------
def variant(name, builder):
    s, ex = Sink(), Extras()
    builder(s, ex)
    me, _ = bake(name, s)
    return me


def put(name, me, x, y, z=0.0, rz=0.0, scale=1.0):
    o = spawn(name, me, (x, y, z), rz)
    if scale != 1.0:
        o.scale = (scale, scale, scale)
    return o


# ============================ MUSTER YARD (hub) ===============================
def campfire(bm, ex, x, y):
    for i in range(10):
        a = math.tau * i / 10
        blob(bm, (x + 1.15 * math.cos(a), y + 1.15 * math.sin(a), 0.18), (0.32, 0.30, 0.22),
             rng.choice([C.STONE, C.STONE_DARK, C.STONE_LIGHT]), segs=5, rings=3, jitter=0.15)
    for i in range(4):
        a = math.pi / 4 + i * math.pi / 2
        beam(bm, (x + 0.9 * math.cos(a), y + 0.9 * math.sin(a), 0.3), (x - 0.2 * math.cos(a), y - 0.2 * math.sin(a), 0.65),
             0.13, 0.11, C.WOOD, 5)
    flame(ex, x, y, 0.45, 0.55, 1.3)
    for i in range(5):                                                  # log seats around the fire
        a = math.tau * i / 5 + 0.3
        with bm.at((x + 2.2 * math.cos(a), y + 2.2 * math.sin(a), 0), rz=a + math.pi / 2):
            frustum(bm, T((-0.8, 0, 0.3)) @ ROT_Y90, 0.28, 0.28, 1.6, C.WOOD, segs=6)
            box(bm, (-0.55, 0, 0.1), (0.2, 0.3, 0.2), C.STONE_DARK)
            box(bm, (0.55, 0, 0.1), (0.2, 0.3, 0.2), C.STONE_DARK)


def yard_floor(bm, ex):
    slab(bm, YARD, C.STONE, name="Yard_Floor")
    joints(bm, YARD, 2.0, C.STONE_DARK)
    patches(bm, YARD, 16, [C.STONE_LIGHT, C.SLATE])
    floor_emblem(bm, 0, 0, 0.09, 3.0)
    ring(bm, T((0, 0, 0.10)), 4.2, 4.05, 0.02, C.BRONZE, segs=32)
    ring(bm, T((0, 0, 0.10)), 5.5, 5.4, 0.02, C.MAROON, segs=32)
    for i in range(8):
        a = math.tau * i / 8 + math.pi / 8
        box(bm, (4.7 * math.cos(a), 4.7 * math.sin(a), 0.10), (1.0, 0.12, 0.012), C.BRONZE, rot=a)
    cx, cy, w, d = rc(*YARD)
    for sy in (-1, 1):
        box(bm, (0, cy + sy * (d / 2 + 0.2), 0.12), (w + 0.8, 0.4, 0.24), C.STONE_LIGHT, ch=0.03)
    for sx in (-1, 1):
        box(bm, (sx * (w / 2 + 0.2), 0, 0.12), (0.4, d, 0.24), C.STONE_LIGHT, ch=0.03)
    campfire(bm, ex, -7.2, -5.6)                      # south-west corner, clear of the cross-paths
    planter(bm, 5.6, -7.7, 2.0, 0.9)
    planter(bm, 8.4, -7.7, 2.0, 0.9)
    marker("Yard_Campfire", "effect_fire", "Muster campfire", -7.2, -5.6, 0.6)


def yard_props(bm, ex):
    for sx in (-1, 1):
        for sy in (-1, 1):
            banner_pole(bm, ex, sx * 11.3, sy * 4.0, 6.2, "archery" if sx < 0 else "sparring", C.GOLD)
    signpost(bm, -9.0, 3.3, "ARCHERY", -1)             # beside the path, never on it
    signpost(bm, 9.0, 3.3, "SPARRING", 1)
    barrel(bm, 10.0, -6.8)
    barrel(bm, 10.7, -6.2)
    crate(bm, 8.8, -7.2, 0.0, 0.9, rot=0.3)


def b_quarter(bm, ex):
    """Quartermaster's lean-to: counter, shelves of kit, striped awning."""
    box(bm, (0, -0.6, 0.55), (5.6, 1.0, 1.1), C.WOOD_LIGHT, ch=0.03)
    box(bm, (0, -0.6, 1.14), (6.0, 1.3, 0.10), C.PLANK, ch=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(bm, (sx * 3.1, sy * 1.4, 1.7), (0.28, 0.28, 3.4 if sy < 0 else 2.7), C.WOOD, ch=0.03)
    box(bm, (0, 1.55, 1.4), (6.4, 0.2, 2.8), C.WOOD_DARK, ch=0.02)
    for z in (1.2, 2.0):
        box(bm, (0, 1.3, z), (5.6, 0.5, 0.08), C.WOOD_LIGHT)
    for i in range(4):
        helmet(bm, (-2.2 + i * 1.5, 1.3, 2.35), 0.8, C.BRONZE if i % 2 else C.IRON_LIGHT, C.MAROON)
    for i in range(3):
        shield(bm, (-1.6 + i * 1.6, 1.4, 1.65), 0.42, C.MAROON, C.BRONZE, "laurel", C.CREAM)
    box(bm, (-2.2, -0.5, 1.30), (0.55, 0.4, 0.28), C.LEATHER, ch=0.03)                     # quiver bundle
    for k in range(5):
        beam(bm, (-2.4 + k * 0.1, -0.5, 1.4), (-2.3 + k * 0.1, -0.5, 2.1), 0.03, 0.02, C.WOOD, 4)
    sword(bm, 1.4, -0.5, 1.22, 1.0, blade=C.WOOD_LIGHT)
    sword(bm, 1.9, -0.5, 1.22, 1.0, blade=C.WOOD_LIGHT)
    for i in range(8):
        x0, x1 = -3.5 + 7.0 * i / 8, -3.5 + 7.0 * (i + 1) / 8
        quad_slab(bm, [(x0, -2.0, 3.45), (x1, -2.0, 3.45), (x1, 1.8, 2.75), (x0, 1.8, 2.75)], 0.08,
                  C.MAROON if i % 2 == 0 else C.CANVAS)
    box(bm, (0, -2.05, 3.0), (2.6, 0.1, 0.7), C.WOOD, ch=0.02)
    text(bm, "GEAR", (0, -2.13, 3.0), 0.5, C.CREAM, depth=0.04, stroke_w=0.18)
    lantern(bm, ex, -2.0, -0.2, 2.5, 0.6)
    lantern(bm, ex, 2.0, -0.2, 2.5, 0.6)


def b_notice(bm, ex):
    for sx in (-1, 1):
        box(bm, (sx * 1.6, 0, 1.4), (0.26, 0.26, 2.8), C.WOOD, ch=0.03)
        box(bm, (sx * 1.6, 0, 0.12), (0.5, 0.5, 0.24), C.STONE_DARK, ch=0.03)
    box(bm, (0, 0.08, 1.75), (3.5, 0.14, 1.9), C.WOOD_DARK, ch=0.02)
    box(bm, (0, 0.0, 2.95), (3.9, 0.7, 0.14), C.ROOF_LIGHT, ch=0.03)
    box(bm, (0, -0.02, 2.62), (3.2, 0.05, 0.42), C.MAROON)
    text(bm, "TRAINING", (0, -0.07, 2.62), 0.28, C.CREAM, depth=0.03, stroke_w=0.18)
    for i, (x, z, w, h) in enumerate(((-1.1, 1.9, 0.8, 0.6), (-0.1, 2.0, 0.7, 0.8), (1.0, 1.9, 0.8, 0.6),
                                      (-0.9, 1.1, 0.7, 0.5), (0.2, 1.15, 0.9, 0.6), (1.2, 1.1, 0.5, 0.5))):
        box(bm, (x, -0.05, z), (w, 0.03, h), C.CANVAS, rot=0.0)
        blob(bm, (x, -0.08, z + h / 2 - 0.08), (0.05, 0.03, 0.05), C.IRON, segs=4, rings=2)


def proving_gate(bm, ex):
    sign_arch(bm, ex, 0.0, -8.0, 11.0, "THE PROVING GROUNDS", "laurel", text_h=0.55, post_h=5.2)


def roads(bm, ex):
    for key, (pts, hw) in ROADS.items():
        ribbon(bm, pts, hw)


# ============================ ARCHERY: terrain, fences, props =================
def archery_ground(bm, ex):
    slab(bm, TERR, C.STONE, name="Archery_Terrace")
    joints(bm, TERR, 2.0, C.STONE_DARK)
    patches(bm, TERR, 26, [C.STONE_LIGHT, C.SLATE])
    slab(bm, FIELD, C.DIRT, top=0.06, name="Archery_Field")
    slab(bm, BAY, C.DIRT, top=0.06, name="Hydra_Bay_Floor")
    y0, y1 = mt(FIRE_Y), mt(BACK_Y0)
    for cx in LANE_CX:
        box(bm, (mt(cx), (y0 + y1) / 2, 0.066), (mt(11), y1 - y0, 0.012), C.DIRT_LIGHT)
    for i in range(6):
        box(bm, (mt(LANE_CX[0] - 7 + 14 * i), (y0 + y1) / 2, 0.07), (0.16, y1 - y0, 0.012), C.SAND)
    box(bm, (mt(-133), (y0 + y1) / 2, 0.066), (mt(8), y1 - y0, 0.012), C.DIRT_LIGHT)
    # berm between the lanes and the Hydra Bay
    bx, by, bw, bd = rc(*BERM)
    box(bm, (bx, by, 0.5), (bw, bd, 1.0), C.DIRT, ch=0.3)
    box(bm, (bx, by, 1.02), (bw - 0.4, bd, 0.08), C.GRASS_LIGHT)
    collide("Archery_Berm", bx, by, 0.5, bw, bd, 1.0)
    # firing lines + standing marks
    box(bm, (mt(-73), mt(FIRE_Y), 0.1), (mt(70), 0.35, 0.14), C.WOOD, ch=0.03)
    box(bm, (mt(-133), mt(FIRE_Y), 0.1), (mt(38), 0.35, 0.14), C.WOOD, ch=0.03)
    for cx in LANE_CX + [-143, -133, -123]:
        box(bm, (mt(cx), mt(FIRE_Y - 2.5), 0.09), (0.9, 0.9, 0.08), C.STONE, ch=0.03)
    # backstop bank + straw bale wall
    bx, by, bw, bd = rc(-152, BACK_Y0, -38, BACK_Y1)
    box(bm, (bx, by, 1.1), (bw, bd, 2.2), C.DIRT, ch=0.5)
    box(bm, (bx, by, 2.22), (bw - 0.8, bd - 0.8, 0.1), C.GRASS)
    collide("Archery_Backstop", bx, by, 1.1, bw, bd, 2.2)
    yb = mt(BACK_Y0) - 0.55
    rows = 0
    for lane, cx in enumerate(LANE_CX):
        for row in range(2):
            for k in range(4):
                x = mt(cx) + (k - 1.5) * 1.15 + (0.55 if row else 0)
                box(bm, (x, yb, 0.28 + row * 0.55), (1.12, 0.55, 0.52), C.STRAW if (k + row) % 2 else C.STRAW_DARK)
    for row in range(2):
        for k in range(11):
            x = mt(-152) + 0.7 + k * 1.15 + (0.55 if row else 0)
            box(bm, (x, yb, 0.28 + row * 0.55), (1.12, 0.55, 0.52), C.STRAW if (k + row) % 2 else C.STRAW_DARK)


def archery_fences(bm, ex):
    gates = []
    for cx in LANE_CX + [-143, -123]:
        gates.append((cx - 5.1 - (-152), cx + 5.1 - (-152)))
    fence_run(bm, (-152, 29), (-38, 29), gates, name="Archery_Rail")
    fence_run(bm, (-152, 7), (-152, 29), name="Terrace_West")
    fence_run(bm, (-38, 29), (-38, 147), name="Field_East")
    fence_run(bm, (-111, 29), (-111, 147), name="Berm_Fence")
    fence_run(bm, (-152, 29), (-152, 147), name="Bay_West")


def dist_sign(bm, x, y, label):
    with bm.at((x, y, 0), rz=-math.pi / 2):
        for sx in (-1, 1):
            box(bm, (sx * 0.9, 0, 0.6), (0.14, 0.14, 1.2), C.WOOD)
        box(bm, (0, 0, 1.15), (2.1, 0.12, 0.8), C.MAROON)
        text(bm, label, (0, -0.08, 1.15), 0.5, C.CREAM, depth=0.03, stroke_w=0.2)


def pennant(bm, x, y):
    beam(bm, (x, y, 0), (x, y, 4.6), 0.07, 0.05, C.WOOD_DARK, 5)
    prism(bm, [(0, 0), (1.5, -0.32), (0, -0.64)], (x, y, 4.5), 1.0, 0.04, C.MAROON)
    blob(bm, (x, y, 4.65), (0.1, 0.1, 0.1), C.GOLD, segs=5, rings=3)


def archery_props(bm, ex):
    for x in (-146, -130, -98, -74):
        bench(bm, mt(x), 3.1, math.pi)
    for x in (-140, -120, -91):
        banner_pole(bm, ex, mt(x), 4.5, 6.0, "archery", C.GOLD)
    for y, sy in ((NEAR_Y, mt(NEAR_Y) - 1.2), (MID_Y, mt(MID_Y) + 3.4), (FAR_Y, mt(FAR_Y) - 1.2)):
        dist_sign(bm, mt(-35), sy, str(y - FIRE_Y))                  # on the outside of the east fence, clear of the stair foot
        pennant(bm, mt(-36.5), sy + 2.6)


# ============================ ARCHERY: targets, gates, stations ===============
def b_target(bm, ex, d, zc):
    """Round target on a timber stand. d = face diameter, zc = height of the face centre (metres).
    Tiers are staggered in height (near low, far high) so every target stays visible down its lane."""
    r = d / 2
    for sx in (-1, 1):
        sbeam(bm, (sx * r * 0.85, 0.7, 0.0), (sx * r * 0.45, 0.22, zc + r * 0.6), 0.14, 0.14, C.WOOD)
    sbeam(bm, (0, 1.9 + zc * 0.25, 0.0), (0, 0.25, zc + r * 0.1), 0.12, 0.12, C.WOOD)
    sbeam(bm, (-r * 0.9, 0.3, zc - r * 0.55), (r * 0.9, 0.3, zc - r * 0.55), 0.12, 0.12, C.WOOD_LIGHT)
    if zc > 2.5:
        sbeam(bm, (-r * 0.7, 0.45, zc * 0.45), (r * 0.7, 0.45, zc * 0.45), 0.12, 0.12, C.WOOD_LIGHT)
    with bm.at((0, 0, zc)):
        frustum(bm, T((0, 0.22, 0)) @ ROT_X90, r * 1.12, r * 1.12, 0.26, C.STRAW_DARK, segs=16)
        ring(bm, T((0, -0.03, 0)) @ ROT_X90, r * 1.12, r * 1.0, 0.07, C.ROPE, segs=16)
        for i, (rad, col) in enumerate(((1.0, C.CREAM), (0.8, C.COAL), (0.6, C.TARGET_BLUE),
                                        (0.4, C.TARGET_RED), (0.2, C.TARGET_YELLOW))):
            frustum(bm, T((0, -0.045 - 0.014 * i, 0)) @ ROT_X90, r * rad, r * rad, 0.014, col, segs=14)


def b_lane_gate(bm, ex, n):
    for sx in (-1, 1):
        x = sx * 1.7
        box(bm, (x, 0, 0.18), (0.7, 0.7, 0.36), C.STONE_DARK, ch=0.04)
        box(bm, (x, 0, 2.7), (0.4, 0.4, 5.0), C.WOOD, ch=0.04)
        box(bm, (x, 0, 5.2), (0.55, 0.55, 0.2), C.WOOD_LIGHT, ch=0.03)
    box(bm, (0, 0, 5.0), (4.0, 0.35, 0.5), C.WOOD_LIGHT, ch=0.04)
    box(bm, (0, -0.22, 5.65), (1.9, 0.12, 1.0), C.MAROON)
    text(bm, str(n), (0, -0.30, 5.65), 0.7, C.CREAM, depth=0.05, stroke_w=0.2)
    insignia(bm, "archery", (0, -0.25, 6.55), 0.34, C.GOLD, True)
    box(bm, (0, 0, 6.2), (0.45, 0.3, 0.4), C.WOOD_DARK)


def b_hydra_gate(bm, ex):
    for sx in (-1, 1):
        x = sx * 1.7
        box(bm, (x, 0, 0.18), (0.7, 0.7, 0.36), C.STONE_DARK, ch=0.04)
        box(bm, (x, 0, 2.7), (0.4, 0.4, 5.0), C.WOOD, ch=0.04)
    box(bm, (0, 0, 5.0), (4.0, 0.35, 0.5), C.WOOD_LIGHT, ch=0.04)
    box(bm, (0, -0.22, 5.65), (3.3, 0.12, 0.9), C.MAROON)
    text(bm, "HYDRA", (0, -0.30, 5.65), 0.5, C.CREAM, depth=0.05, stroke_w=0.18)
    insignia(bm, "archery", (0, -0.25, 6.5), 0.3, C.GOLD, True)


def b_ammo(bm, ex):
    barrel(bm, 0, 0, 0.0, 0.5, 1.1)
    for i in range(9):
        a = i * 0.7
        r = 0.22 * (i % 3) / 2
        beam(bm, (r * math.cos(a), r * math.sin(a), 1.05), (r * math.cos(a) * 1.6, r * math.sin(a) * 1.6, 1.85 + 0.06 * (i % 4)),
             0.022, 0.018, C.WOOD_LIGHT, 4)
        blob(bm, (r * math.cos(a) * 1.6, r * math.sin(a) * 1.6, 1.88 + 0.06 * (i % 4)), (0.06, 0.06, 0.1), C.CREAM, segs=4, rings=2)


def b_bow_rack(bm, ex):
    for sx in (-1, 1):
        box(bm, (sx * 1.6, 0, 1.2), (0.22, 0.22, 2.4), C.WOOD, ch=0.03)
        box(bm, (sx * 1.6, 0, 0.1), (0.5, 0.5, 0.2), C.STONE_DARK, ch=0.03)
    for z in (0.8, 1.7):
        sbeam(bm, (-1.6, 0, z), (1.6, 0, z), 0.12, 0.12, C.WOOD_LIGHT)
    for i in range(6):
        x = -1.25 + i * 0.5
        arc = [(0.0, 0.0), (0.18, 0.4), (0.22, 0.9), (0.18, 1.4), (0.0, 1.8)]
        for (a0, z0), (a1, z1) in zip(arc[:-1], arc[1:]):
            beam(bm, (x, -0.12 - a0, 0.55 + z0 * 0.8), (x, -0.12 - a1, 0.55 + z1 * 0.8), 0.045, 0.045, C.WOOD_LIGHT, 4)
        beam(bm, (x, -0.12, 0.55), (x, -0.12, 0.55 + 1.44), 0.012, 0.012, C.ROPE, 3)
    insignia(bm, "archery", (0, -0.14, 2.6), 0.34, C.GOLD, True)
    box(bm, (0, 0, 2.52), (3.6, 0.2, 0.14), C.WOOD_DARK)


def b_scoreboard(bm, ex, word="ARCHERY"):
    for sx in (-1, 1):
        box(bm, (sx * 1.7, 0, 1.6), (0.3, 0.3, 3.2), C.WOOD, ch=0.03)
        box(bm, (sx * 1.7, 0, 0.12), (0.6, 0.6, 0.24), C.STONE_DARK, ch=0.03)
    box(bm, (0, 0.05, 2.3), (3.5, 0.16, 3.0), C.WOOD_DARK, ch=0.03)
    box(bm, (0, -0.06, 3.35), (3.2, 0.06, 0.6), C.MAROON)
    text(bm, word, (0, -0.12, 3.35), 0.36, C.CREAM, depth=0.04, stroke_w=0.18)
    box(bm, (0, -0.05, 2.0), (3.0, 0.04, 1.9), C.COAL)                    # blank slate for the live scores
    box(bm, (0, 0.0, 3.82), (4.1, 0.5, 0.14), C.ROOF_LIGHT, ch=0.03)


# ============================ HYDRA (an original five-headed straw boss) ======
def bez3(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u ** 3 * p0[i] + 3 * u * u * t * p1[i] + 3 * u * t * t * p2[i] + t ** 3 * p3[i] for i in range(3))


HEADS = [(-4.6, -0.3, 4.5), (-2.4, -0.3, 5.7), (0.0, -0.3, 6.0), (2.4, -0.3, 5.6), (4.6, -0.3, 4.3)]
ATTACH = [(-1.1, 0.0, 3.7), (-0.55, 0.0, 3.95), (0.0, 0.0, 4.05), (0.55, 0.0, 3.95), (1.1, 0.0, 3.7)]


def b_hydra_body(bm, ex):
    # heavy timber gantry
    for sx in (-1, 1):
        x = sx * 5.6
        box(bm, (x, 0, 0.2), (1.2, 1.2, 0.4), C.STONE_DARK, ch=0.05)
        box(bm, (x, 0, 3.95), (0.62, 0.66, 7.7), C.WOOD_LIGHT, ch=0.05)
        sbeam(bm, (x, 0, 2.6), (x - sx * 1.7, 0, 0.3), 0.22, 0.22, C.WOOD)
    sbeam(bm, (-6.5, 0, 7.45), (6.5, 0, 7.45), 0.62, 0.72, C.WOOD_LIGHT)
    for sx in (-1, 1):
        box(bm, (sx * 6.6, 0, 7.45), (0.24, 0.8, 0.9), C.WOOD_DARK)
        banner(bm, sx * 5.6, -0.55, 6.9, 1.2, 2.6, motif="archery", col=C.GOLD)
    for x in (-2.4, 0.0, 2.4):
        beam(bm, (x, -0.03, 7.1), (x, -0.03, 3.9 if x == 0 else 3.75), 0.05, 0.05, C.ROPE, 5)
        ring(bm, T((x, -0.03, 7.0)) @ ROT_X90, 0.18, 0.1, 0.06, C.ROPE, segs=8)
    # torso, belly wraps, tail, legs
    blob(bm, (0, 0, 3.0), (1.95, 0.85, 0.95), C.STRAW, segs=10, rings=6)
    blob(bm, (0, -0.1, 2.72), (1.6, 0.82, 0.55), C.STRAW_DARK, segs=10, rings=4)
    for i in range(7):
        blob(bm, (-1.5 + i * 0.5, -0.62, 3.0), (0.07, 0.3, 0.95), C.STRAW_DARK, segs=4, rings=3)
    disc = T((0, -0.8, 3.0)) @ ROT_X90                                    # weak-spot on the chest
    frustum(bm, disc, 0.5, 0.5, 0.04, C.CREAM, segs=14)
    frustum(bm, T((0, -0.84, 3.0)) @ ROT_X90, 0.34, 0.34, 0.03, C.TARGET_RED, segs=14)
    frustum(bm, T((0, -0.87, 3.0)) @ ROT_X90, 0.16, 0.16, 0.03, C.TARGET_YELLOW, segs=10)
    tail = [(1.7, 0.0, 2.9), (3.0, -0.2, 2.35), (4.2, -0.3, 2.0), (4.95, -0.2, 2.5)]
    for k, (a, b) in enumerate(zip(tail[:-1], tail[1:])):
        beam(bm, a, b, 0.5 - 0.12 * k, 0.5 - 0.12 * (k + 1), C.STRAW, 6)
        blob(bm, b, (0.2, 0.2, 0.2), C.STRAW_DARK, segs=5, rings=3)
    for sx in (-1, 1):
        for off in (0.0, 0.0):
            hip = (sx * 0.9, 0.0, 2.55)
            knee = (sx * 1.55, -0.1, 1.4)
            foot = (sx * 1.15, -0.25, 0.12)
            beam(bm, hip, knee, 0.34, 0.26, C.STRAW, 6)
            beam(bm, knee, foot, 0.26, 0.2, C.STRAW, 6)
            blob(bm, (foot[0], foot[1] - 0.1, 0.12), (0.34, 0.44, 0.14), C.STRAW_DARK, segs=5, rings=3)


def b_hydra_head(bm, ex, k):
    hx, hy, hz = HEADS[k]
    ax, ay, az = ATTACH[k]
    A = (ax - hx, ay - hy, az - hz)
    P3 = (0.0, 0.45, -0.1)
    drop = abs(A[2])
    P1 = (A[0], A[1], A[2] + drop * 0.55)
    P2 = (P3[0] + A[0] * 0.25, P3[1] + 0.25, P3[2] - drop * 0.5)
    pts = [bez3(A, P1, P2, P3, i / 7) for i in range(8)]
    for i, (a, b) in enumerate(zip(pts[:-1], pts[1:])):
        r0, r1 = 0.44 - 0.016 * i * 2, 0.44 - 0.016 * (i + 1) * 2
        beam(bm, a, b, r0, r1, C.STRAW, 6)
        frustum(bm, T(a) @ Matrix.Rotation(0.0, 4, "X"), r0 + 0.06, r0 + 0.06, 0.09, C.STRAW_DARK, segs=6)
    blob(bm, (0, -0.1, 0), (0.58, 0.78, 0.46), C.STRAW, segs=8, rings=4)
    frustum(bm, T((0, -0.55, -0.08)) @ ROT_X90, 0.40, 0.22, 0.6, C.STRAW, segs=7)           # snout
    blob(bm, (0, -0.5, -0.38), (0.34, 0.5, 0.18), C.STRAW_DARK, segs=6, rings=3)             # jaw
    for sx in (-1, 1):
        blob(bm, (sx * 0.32, -0.5, 0.22), (0.1, 0.08, 0.1), C.COAL, segs=5, rings=3)
        frustum(bm, T((sx * 0.3, 0.1, 0.35)) @ Matrix.Rotation(sx * 0.4, 4, "Y"), 0.1, 0.0, 0.5, C.STRAW_DARK, segs=4)
    frustum(bm, T((0, -0.62, 0.3)) @ ROT_X90, 0.34, 0.34, 0.04, C.CREAM, segs=12)            # weak-spot disc
    frustum(bm, T((0, -0.66, 0.3)) @ ROT_X90, 0.22, 0.22, 0.03, C.TARGET_RED, segs=12)
    frustum(bm, T((0, -0.69, 0.3)) @ ROT_X90, 0.1, 0.1, 0.03, C.TARGET_YELLOW, segs=8)


# ============================ THE CAUSEWAY, PAVILION, SHRINE ==================
ZW = 1.33                      # walk height (4 studs)
PAV_Y0, PAV_Y1, PAV_HALF = mt(PAV[1]), mt(PAV[3]), mt(PAV[2])


def parapet(bm, x, y0, y1, side):
    cy, L = (y0 + y1) / 2, y1 - y0
    box(bm, (x, cy, ZW + 0.3), (0.4, L, 0.6), C.STONE_LIGHT, ch=0.04)
    box(bm, (x, cy, ZW + 0.63), (0.55, L, 0.1), C.STONE, ch=0.02)
    n = max(1, int(L / 4.0))
    for i in range(n + 1):
        box(bm, (x, y0 + L * i / n, ZW + 0.5), (0.6, 0.6, 1.0), C.STONE_LIGHT, ch=0.05)
    collide("Causeway_Parapet", x, cy, ZW + 0.4, 0.5, L, 0.8)


def causeway(bm, ex):
    xh = mt(CW_HALF)
    y_s0, y_w0, y_w1 = mt(CW_STAIR0), mt(CW_WALK0), mt(CW_WALK1)
    n = 8
    rise, tread = ZW / n, (y_w0 - y_s0) / n
    for i in range(n):                                            # south stair flight (from the Muster Yard)
        top = (i + 1) * rise
        yc = y_s0 + tread * (i + 0.5)
        box(bm, (0, yc, top / 2), (2 * xh, tread, top), C.STONE, ch=0.02)
        collide("Causeway_Step", 0, yc, top / 2, 2 * xh, tread, top)

    def walk(y0, y1, half):
        cy, L = (y0 + y1) / 2, y1 - y0
        box(bm, (0, cy, 0.58), (2 * half, L, 1.16), C.STONE, ch=0.05)
        box(bm, (0, cy, 1.26), (2 * half, L, 0.14), C.STONE_LIGHT, ch=0.02)
        collide("Causeway_Walk", 0, cy, ZW / 2, 2 * half, L, ZW)
        y = y0 + 2.0
        while y < y1 - 0.1:
            box(bm, (0, y, ZW + 0.004), (2 * half, 0.05, 0.012), C.STONE_DARK)
            y += 2.0

    walk(y_w0, PAV_Y0, xh)
    walk(PAV_Y0, PAV_Y1, PAV_HALF)
    walk(PAV_Y1, y_w1, xh)
    box(bm, (0, (y_w0 + y_w1) / 2, ZW + 0.01), (1.4, y_w1 - y_w0, 0.012), C.MAROON)
    for sx in (-1, 1):
        box(bm, (sx * 0.8, (y_w0 + y_w1) / 2, ZW + 0.014), (0.1, y_w1 - y_w0, 0.012), C.GOLD)
    floor_emblem(bm, 0, (PAV_Y0 + PAV_Y1) / 2, ZW + 0.02, 2.6)
    floor_emblem(bm, 0, (y_w0 + PAV_Y0) / 2, ZW + 0.02, 1.4)
    floor_emblem(bm, 0, (PAV_Y1 + y_w1) / 2, ZW + 0.02, 1.4)
    for sx in (-1, 1):
        parapet(bm, sx * (xh - 0.2), y_w0, PAV_Y0, sx)
        parapet(bm, sx * (xh - 0.2), PAV_Y1, y_w1, sx)
        parapet(bm, sx * (PAV_HALF - 0.2), PAV_Y0, PAV_Y0 + 2.0, sx)
        parapet(bm, sx * (PAV_HALF - 0.2), PAV_Y1 - 2.0, PAV_Y1, sx)
    with bm.at((0, 0, ZW)):                                       # standards along the walk
        for y in (16.0, 23.0, 38.0):
            for sx in (-1, 1):
                banner_pole(bm, ex, sx * (xh - 0.9), y, 6.0, "laurel", C.GOLD)


def pavilion(bm, ex):
    """Two-sided viewing pavilion: archery lanes to the west, the arena to the east."""
    yc = (PAV_Y0 + PAV_Y1) / 2
    ys = (PAV_Y0 + 0.7, yc, PAV_Y1 - 0.7)
    with at_all(bm, ex, (0, 0, ZW)):
        for sx in (-1, 1):
            for y in (ys[0], ys[2]):                              # end posts only: the middle bay stays open to the stairs
                timber_post(bm, sx * (PAV_HALF - 0.55), y, 4.3, 0.5)
        for y in ys:
            truss(bm, y, PAV_HALF - 0.4, 5.0, 6.8)
        sbeam(bm, (0, PAV_Y0 - 0.5, 6.95), (0, PAV_Y1 + 0.5, 6.95), 0.4, 0.4, C.WOOD_DARK)
        n = 7
        for i in range(n):
            ya = PAV_Y0 - 0.5 + (PAV_Y1 - PAV_Y0 + 1.0) * i / n
            yb = PAV_Y0 - 0.5 + (PAV_Y1 - PAV_Y0 + 1.0) * (i + 1) / n
            col = C.MAROON if i % 2 == 0 else C.CANVAS
            for sx in (-1, 1):
                quad_slab(bm, [(sx * (PAV_HALF + 0.6), ya, 4.9), (sx * (PAV_HALF + 0.6), yb, 4.9), (0, yb, 6.9), (0, ya, 6.9)],
                          0.1, col)
        for sx in (-1, 1):                                           # benches leave a 3 m gap for the side stairs
            for y in (yc - 2.7, yc + 2.7):
                bench(bm, sx * (PAV_HALF - 1.9), y, sx * math.pi / 2)
            for y in (yc - 2.7, yc + 2.7):                           # banners above the benches, not in the stair aisle
                with bm.at((sx * (PAV_HALF - 0.9), y, 0), rz=-sx * math.pi / 2):
                    banner(bm, 0, 0, 4.8, 1.6, 3.0, motif="laurel", col=C.GOLD)
        for y in ys:
            lantern(bm, ex, 0.0, y, 4.8, hang=2.0)                  # lantern bottoms stay above 4.7 m
        # steps down to the lawns on both sides (archery side / arena side)
        n = 8
        rise = ZW / n
        for sx in (-1, 1):
            for i in range(n - 1):
                top = ZW - rise * (i + 1)
                x = sx * (PAV_HALF + 0.25 + i * 0.5)
                box(bm, (x, yc, top / 2 - ZW), (0.5, 3.0, top), C.STONE, ch=0.02)
    for sx in (-1, 1):
        for y in (ys[0], ys[2]):
            collide("Pavilion_Post", sx * (PAV_HALF - 0.55), y, ZW + 2.5, 0.9, 0.9, 5.0)
        for i in range(7):
            top = ZW - (ZW / 8) * (i + 1)
            collide("Pavilion_Step", sx * (PAV_HALF + 0.25 + i * 0.5), yc, top / 2, 0.5, 3.0, top)


def shrine(bm, ex):
    """Trophy shrine at the head of the Causeway: small columned temple, flame, bull pediment."""
    y_w1, sy0, sy1 = mt(CW_WALK1), mt(SHR_Y0), mt(SHR_Y1)
    cy = (sy0 + sy1) / 2
    n = 10
    rise, tread = (3.0 - ZW) / n, (sy0 - 0.2 - y_w1) / n
    for i in range(n):
        top = ZW + rise * (i + 1)
        yc = y_w1 + tread * (i + 0.5)
        box(bm, (0, yc, top / 2), (6.4, tread, top), C.STONE, ch=0.02)
        collide("Shrine_Step", 0, yc, top / 2, 6.4, tread, top)
    box(bm, (0, cy, 0.9), (11.4, 10.4, 1.8), C.STONE_DARK, ch=0.06)
    box(bm, (0, cy, 2.15), (10.6, 9.6, 0.7), C.STONE, ch=0.05)
    box(bm, (0, cy, 2.75), (10.0, 9.0, 0.5), C.MARBLE, ch=0.04)
    collide("Shrine_Platform", 0, cy, 1.5, 11.4, 10.4, 3.0)
    floor_emblem(bm, 0, cy - 0.6, 3.01, 2.2)
    with at_all(bm, ex, (0, 0, 3.0)):
        for y in (cy - 3.8, cy + 3.6):
            for x in (-4.2, -1.9, 1.9, 4.2):
                stone_column(bm, x, y, 3.4, 0.42)
        box(bm, (0, cy + 4.3, 2.3), (9.2, 0.7, 4.6), C.STONE_LIGHT, ch=0.04)
        box(bm, (0, cy, 4.8), (9.8, 9.0, 0.5), C.STONE_LIGHT, ch=0.04)
        box(bm, (0, cy, 5.1), (10.2, 9.4, 0.12), C.BRONZE)
        z0 = 5.35
        roof_slope(bm, (-5.2, cy - 5.0, z0), (-5.2, cy + 5.0, z0), (0, cy + 5.0, z0 + 1.7), (0, cy - 5.0, z0 + 1.7),
                   0.22, C.TERRACOTTA, C.ROOF_LIGHT, 7, rafters=2.5)
        roof_slope(bm, (5.2, cy - 5.0, z0), (5.2, cy + 5.0, z0), (0, cy + 5.0, z0 + 1.7), (0, cy - 5.0, z0 + 1.7),
                   0.22, C.TERRACOTTA, C.ROOF_LIGHT, 7, rafters=2.5)
        sbeam(bm, (0, cy - 5.0, z0 + 1.75), (0, cy + 5.0, z0 + 1.75), 0.4, 0.3, C.ROOF_LIGHT)
        prism(bm, [(-4.9, 0), (4.9, 0), (0, 1.7)], (0, cy - 4.7, z0), 1.0, 0.7, C.STONE_LIGHT)
        emblem(bm, (0, cy - 5.1, z0 + 0.35), 0.9, C.BRONZE, C.MAROON, t=0.1)
        for sx in (-1, 1):
            standing_brazier(bm, ex, sx * 4.6, cy - 4.4, 1.7)
        for sx in (-1, 1):                                                                    # trophy flames flank the stele
            fx, fy = sx * 3.6, cy + 0.9
            frustum(bm, T((fx, fy, 0)), 0.55, 0.45, 1.0, C.STONE_LIGHT, segs=10)
            frustum(bm, T((fx, fy, 1.0)), 0.4, 1.0, 0.55, C.BRONZE, segs=12)
            ring(bm, T((fx, fy, 1.55)), 1.08, 0.92, 0.1, C.GOLD, segs=12)
            flame(ex, fx, fy, 1.6, 0.8, 1.8)
            collide("Shrine_FireBowl", fx, fy, 3.0 + 0.9, 1.2, 1.2, 1.8)
    for x in (-4.2, -1.9, 1.9, 4.2):
        for y in (cy - 3.8, cy + 3.6):
            collide("Shrine_Column", x, y, 5.0, 0.9, 0.9, 4.0)
    marker("Shrine_Flame_W", "effect_fire", "Trophy flame", -3.6, cy + 0.9, 5.0)
    marker("Shrine_Flame_E", "effect_fire", "Trophy flame", 3.6, cy + 0.9, 5.0)


def b_stele(bm, ex):
    box(bm, (0, 0, 0.25), (4.6, 0.9, 0.5), C.STONE_DARK, ch=0.05)
    box(bm, (0, 0, 2.3), (4.2, 0.45, 3.6), C.STONE_LIGHT, ch=0.05)
    box(bm, (0, -0.26, 3.75), (3.7, 0.08, 0.8), C.MAROON)
    text(bm, "HEROES", (0, -0.33, 3.75), 0.5, C.CREAM, depth=0.04, stroke_w=0.18)
    box(bm, (0, -0.25, 2.1), (3.5, 0.06, 2.0), C.COAL)
    for sx in (-1, 1):
        box(bm, (sx * 1.95, -0.24, 2.3), (0.14, 0.1, 3.4), C.BRONZE)
    insignia(bm, "laurel", (0, -0.28, 4.4), 0.34, C.GOLD, True)


# ============================ SPARRING: arena, apron, gates ===================
ARC = rc(*RING)                      # ring centre / size in metres
AP = (RING[0] - APRON, RING[1] - APRON, RING[2] + APRON, RING[3] + APRON)


def arena_floor(bm, ex):
    slab(bm, AP, C.STONE, name="Arena_Apron")
    joints(bm, AP, 2.0, C.STONE_DARK)
    patches(bm, AP, 20, [C.STONE_LIGHT, C.SLATE])
    cx, cy, w, d = ARC
    box(bm, (cx, cy, 0.12), (w + 0.5, d + 0.5, 0.3), C.STONE_DARK, ch=0.05)
    collide("Arena_Floor", cx, cy, 0.12, w + 0.5, d + 0.5, 0.3)
    top = 0.27
    x = cx - w / 2 + 2.0
    while x < cx + w / 2 - 0.1:
        box(bm, (x, cy, top + 0.004), (0.05, d, 0.012), C.COAL)
        x += 2.0
    y = cy - d / 2 + 2.0
    while y < cy + d / 2 - 0.1:
        box(bm, (cx, y, top + 0.004), (w, 0.05, 0.012), C.COAL)
        y += 2.0
    for _ in range(34):
        box(bm, (cx + rng.uniform(-w / 2 + 1, w / 2 - 1), cy + rng.uniform(-d / 2 + 1, d / 2 - 1), top + 0.006),
            (rng.uniform(1.0, 1.9), rng.uniform(1.0, 1.9), 0.012), rng.choice([C.STONE_LIGHT, C.STONE, C.SLATE]),
            rot=rng.uniform(0, 3.14))
    floor_emblem(bm, cx, cy, top + 0.01, 4.0)
    for i in range(16):
        a = math.tau * i / 16
        box(bm, (cx + 5.1 * math.cos(a), cy + 5.1 * math.sin(a), top + 0.014), (1.3, 0.1, 0.012), C.BRONZE, rot=a)
    for i in range(24):
        a = math.tau * i / 24
        if i % 4:
            box(bm, (cx + 6.1 * math.cos(a), cy + 6.1 * math.sin(a), top + 0.014), (0.5, 0.1, 0.012), C.BRONZE, rot=a)
    # low parapet with four gate gaps (gate width 14 studs = 4.67 m)
    hg, t, g = 1.05, 0.5, mt(7)
    wall(bm, "x", cx - w / 2 - 0.5, cx + w / 2 + 0.5, cy - d / 2 - 0.25, 0, hg, t, C.STONE,
         openings=[(cx - g, cx + g, 0, hg)], ch=0.03, name="Arena_Parapet")
    wall(bm, "x", cx - w / 2 - 0.5, cx + w / 2 + 0.5, cy + d / 2 + 0.25, 0, hg, t, C.STONE,
         openings=[(cx - g, cx + g, 0, hg)], ch=0.03, name="Arena_Parapet")
    wall(bm, "y", cy - d / 2, cy + d / 2, cx - w / 2 - 0.25, 0, hg, t, C.STONE,
         openings=[(cy - g, cy + g, 0, hg)], ch=0.03, name="Arena_Parapet")
    wall(bm, "y", cy - d / 2, cy + d / 2, cx + w / 2 + 0.25, 0, hg, t, C.STONE,
         openings=[(cy - g, cy + g, 0, hg)], ch=0.03, name="Arena_Parapet")
    bi = 0
    for sx in (-1, 1):
        for sy in (-1, 1):
            bi += 1
            box(bm, (cx + sx * (w / 2 + 0.25), cy + sy * (d / 2 + 0.25), 0.9), (0.9, 0.9, 1.8), C.STONE_LIGHT, ch=0.05)
            frustum(bm, T((cx + sx * (w / 2 + 0.25), cy + sy * (d / 2 + 0.25), 1.8)), 0.4, 0.55, 0.3, C.BRONZE, segs=8)
            standing_brazier(bm, ex, cx + sx * (w / 2 + 3.8), cy + sy * (d / 2 + 3.3), 1.7)
            marker("Arena_Brazier_%02d" % bi, "effect_fire", "Arena brazier", cx + sx * (w / 2 + 3.8), cy + sy * (d / 2 + 3.3), 2.4)
    for sx in (-1, 1):                                           # spectator benches on the apron, facing the ring
        for dy in (-8.0, -5.0, 5.0, 8.0):
            bench(bm, cx + sx * (w / 2 + 3.7), cy + dy, -sx * math.pi / 2)         # against the outer edge: ~3 m walk strip stays clear


def arena_props(bm, ex):
    """Spectator awning on the apron's north-east side. Posts stand on the OUTER edge only, the canopy
    cantilevers over the walk strip (>= 4.8 m clear) and the bench row sits against the outer edge,
    so the 3 m circulation strip and the north gate's approach stay open."""
    cx, cy, w, d = ARC
    yo = cy + d / 2 + 3.9                       # outer-edge line
    x0, x1 = cx + 4.8, cx + 12.4
    xp = (x0 + 0.4, (x0 + x1) / 2, x1 - 0.4)
    for x in xp:
        box(bm, (x, yo + 0.1, 2.85), (0.3, 0.3, 5.7), C.WOOD, ch=0.03)
        box(bm, (x, yo + 0.1, 0.15), (0.6, 0.6, 0.3), C.STONE_DARK, ch=0.04)
        sbeam(bm, (x, yo + 0.1, 4.5), (x, yo - 2.3, 5.2), 0.16, 0.16, C.WOOD_LIGHT)       # cantilever brace
    n = 8
    for i in range(n):
        xa, xb = x0 + (x1 - x0) * i / n, x0 + (x1 - x0) * (i + 1) / n
        quad_slab(bm, [(xa, yo + 0.5, 5.9), (xb, yo + 0.5, 5.9), (xb, yo - 2.6, 5.0), (xa, yo - 2.6, 5.0)], 0.1,
                  C.CANVAS if i % 2 == 0 else C.MAROON)
    for k in range(3):
        bench(bm, x0 + 1.4 + k * 2.4, yo - 0.2, math.pi)
    lantern(bm, ex, (x0 + x1) / 2 - 1.8, yo - 0.6, 4.9, 0.9)
    lantern(bm, ex, (x0 + x1) / 2 + 1.8, yo - 0.6, 4.9, 0.9)
    for x in (xp[0], xp[2]):
        collide("Awning_Post", x, yo + 0.1, 2.85, 0.4, 0.4, 5.7)


def b_arena_gate(bm, ex):
    for sx in (-1, 1):
        x = sx * 2.85
        box(bm, (x, 0, 0.25), (1.5, 1.5, 0.5), C.STONE_DARK, ch=0.05)
        box(bm, (x, 0, 2.75), (1.1, 1.1, 4.5), C.STONE_LIGHT, ch=0.06)
        box(bm, (x, 0, 5.1), (1.4, 1.4, 0.3), C.STONE, ch=0.05)
        for z in (1.2, 3.6):
            box(bm, (x, 0, z), (1.2, 1.2, 0.1), C.BRONZE)
        banner(bm, x, -0.60, 4.4, 0.85, 2.6, motif="sparring", col=C.GOLD, both=False)
    box(bm, (0, 0, 5.35), (6.9, 0.9, 0.9), C.STONE_LIGHT, ch=0.06)
    box(bm, (0, -0.47, 5.35), (4.4, 0.08, 0.7), C.MAROON)
    insignia(bm, "sparring", (0, -0.52, 5.4), 0.34, C.GOLD, True)
    for sx in (-1, 1):
        box(bm, (sx * 3.5, -0.1, 2.95), (0.5, 0.3, 0.1), C.IRON)
        lantern(bm, ex, sx * 3.55, -0.1, 3.0, 0.0)


def b_queue(bm, ex):
    for sx in (-1, 1):
        box(bm, (sx * 1.4, 0, 1.4), (0.26, 0.26, 2.8), C.WOOD, ch=0.03)
        box(bm, (sx * 1.4, 0, 0.12), (0.5, 0.5, 0.24), C.STONE_DARK, ch=0.03)
    box(bm, (0, 0.05, 1.9), (3.1, 0.14, 1.9), C.WOOD_DARK, ch=0.02)
    box(bm, (0, -0.04, 2.55), (2.7, 0.06, 0.5), C.MAROON)
    text(bm, "DUEL", (0, -0.1, 2.55), 0.34, C.CREAM, depth=0.04, stroke_w=0.2)
    box(bm, (0, -0.04, 1.65), (2.6, 0.04, 1.1), C.COAL)
    insignia(bm, "sparring", (0, -0.08, 1.0), 0.22, C.GOLD, True)
    box(bm, (0, 0.0, 3.05), (3.5, 0.6, 0.12), C.ROOF_LIGHT, ch=0.03)


# ============================ SPARRING: drill yard, dummies, rings, racks =====
def drill_floor(bm, ex):
    slab(bm, DRILL, C.DIRT, top=0.06, name="Drill_Floor")
    cx, cy, w, d = rc(*DRILL)
    patches(bm, DRILL, 22, [C.DIRT_LIGHT, C.SAND], top=0.06, size=(1.2, 2.6))
    fence_run(bm, (DRILL[0], DRILL[1]), (DRILL[0], DRILL[3]), name="Drill_West")
    fence_run(bm, (DRILL[2], DRILL[1]), (DRILL[2], DRILL[3]), name="Drill_East")
    for sx in (-1, 1):
        barrel(bm, cx + sx * (w / 2 - 0.9), mt(DRILL[1]) + 0.9)
        barrel(bm, cx + sx * (w / 2 - 1.5), mt(DRILL[1]) + 0.8)


def entry_arches(bm, ex):
    sign_arch(bm, ex, mt(-62), 4.3, 6.0, "ARCHERY", "archery", text_h=0.6, post_h=5.0)
    sign_arch(bm, ex, mt(76), mt(23.5), 6.5, "SPARRING", "sparring", text_h=0.6, post_h=5.0)


def b_dummy(bm, ex):
    box(bm, (0, 0, 0.18), (1.3, 1.3, 0.36), C.STONE, ch=0.05)
    beam(bm, (0, 0, 0.3), (0, 0, 2.5), 0.12, 0.10, C.WOOD, 6)
    sbeam(bm, (-0.95, 0, 1.95), (0.95, 0, 1.95), 0.14, 0.14, C.WOOD)
    blob(bm, (0, 0, 1.55), (0.38, 0.26, 0.52), C.STRAW, segs=6, rings=4)
    for sx in (-1, 1):
        beam(bm, (sx * 0.4, 0, 1.95), (sx * 0.95, 0, 1.95), 0.14, 0.12, C.STRAW, 5)
    frustum(bm, T((0, -0.27, 1.6)) @ ROT_X90, 0.24, 0.24, 0.04, C.CREAM, segs=10)           # strike target on the chest
    frustum(bm, T((0, -0.31, 1.6)) @ ROT_X90, 0.14, 0.14, 0.03, C.TARGET_RED, segs=10)
    blob(bm, (0, 0, 2.55), (0.26, 0.26, 0.28), C.STRAW, segs=6, rings=3)
    helmet(bm, (0, 0, 2.68), 0.8, C.IRON_LIGHT, C.MAROON)
    shield(bm, (-0.75, -0.3, 1.5), 0.4, C.MAROON, C.BRONZE, "sparring", C.GOLD)
    box(bm, (0.78, -0.12, 1.45), (0.09, 0.09, 1.1), C.WOOD_LIGHT)


def b_duel_ring(bm, ex):
    frustum(bm, T((0, 0, 0)), 3.5, 3.5, 0.2, C.SAND, segs=28)
    ring(bm, T((0, 0, 0.0)), 3.65, 3.38, 0.26, C.STONE_LIGHT, segs=28)
    ring(bm, T((0, 0, 0.2)), 2.6, 2.5, 0.02, C.BRONZE, segs=24)
    with bm.at((0, 0, 0.225), rx=-math.pi / 2):
        insignia(bm, "sparring", (0, 0, 0), 1.3, C.MAROON, True, dark=C.SAND)
    for i in range(4):
        a = math.pi / 4 + math.pi / 2 * i
        box(bm, (3.9 * math.cos(a), 3.9 * math.sin(a), 0.4), (0.5, 0.5, 0.8), C.STONE_LIGHT, ch=0.04, rot=a)


def b_weapon_rack(bm, ex):
    for sx in (-1, 1):
        box(bm, (sx * 2.0, 0, 1.3), (0.26, 0.26, 2.6), C.WOOD, ch=0.03)
        box(bm, (sx * 2.0, 0, 0.12), (0.6, 0.6, 0.24), C.STONE_DARK, ch=0.03)
    for z in (0.7, 1.8):
        sbeam(bm, (-2.0, 0, z), (2.0, 0, z), 0.14, 0.14, C.WOOD_LIGHT)
    for i in range(6):
        sword(bm, -1.6 + i * 0.5, -0.12, 0.72, 1.15, blade=C.WOOD_LIGHT, grip=C.LEATHER, guard=C.WOOD_DARK)
    for i in range(3):
        spear(bm, -1.4 + i * 0.5, 0.2, 0.2, 2.5)
    for i in range(2):
        shield(bm, (0.9 + i * 0.95, -0.2, 1.45), 0.42, C.MAROON, C.WOOD_DARK, "sparring", C.GOLD)
    box(bm, (0, 0, 2.62), (4.4, 0.2, 0.14), C.WOOD_DARK)
    insignia(bm, "sparring", (0, -0.14, 2.95), 0.3, C.GOLD, True)


# ============================ TERRAIN, RIDGE, SCATTER =========================
def ground_base(bm, ex):
    cx, cy, w, d = rc(*GROUND)
    box(bm, (cx, cy, -0.5), (w, d, 1.0), C.GRASS)
    collide("Ground", cx, cy, -0.5, w, d, 1.0)
    for _ in range(90):                                   # dry golden meadow in the archery half, olive near the arena
        x = rng.uniform(GROUND[0] + 10, GROUND[2] - 10)
        y = rng.uniform(GROUND[1] + 10, GROUND[3] - 10)
        col = rng.choice([C.MEADOW_GOLD, C.MEADOW_GOLD, C.GRASS_LIGHT]) if x < 0 else rng.choice([C.GRASS_LIGHT, C.MOSS])
        box(bm, (mt(x), mt(y), 0.012), (rng.uniform(3, 9), rng.uniform(3, 9), 0.03), col, rot=rng.uniform(0, 3.14))
    # invisible map-edge walls (north, west, east) so nobody walks into the void
    collide("Boundary_N", cx, mt(GROUND[3]) - 0.5, 15, w, 1.0, 30)
    collide("Boundary_W", mt(GROUND[0]) + 0.5, cy, 15, 1.0, d, 30)
    collide("Boundary_E", mt(GROUND[2]) - 0.5, cy, 15, 1.0, d, 30)


def ridge(bm, ex):
    rocks = [C.STONE_DARK, C.STONE, C.SLATE, C.STONE_LIGHT]
    x0, x1 = mt(GROUND[0]) + 5, mt(GROUND[2]) - 5
    yn = mt(GROUND[3]) - 10
    for i in range(30):
        x = x0 + (x1 - x0) * i / 29 + rng.uniform(-1, 1)
        rx, ry, rz = rng.uniform(2.2, 4.5), rng.uniform(2.0, 3.6), rng.uniform(2.5, 6.0)
        blob(bm, (x, yn + rng.uniform(-1.5, 3.5), rz * 0.55), (rx, ry, rz), rng.choice(rocks), segs=6, rings=4, jitter=0.2)
    for i in range(9):
        x = x0 + (x1 - x0) * (i + 0.5) / 9 + rng.uniform(-3, 3)
        frustum(bm, T((x, yn + rng.uniform(1.5, 4), -0.3)), rng.uniform(2.8, 4.2), rng.uniform(1.4, 2.4),
                rng.uniform(5.5, 9.0), rng.choice([C.STONE_DARK, C.STONE]), segs=7, jitter=0.12)
    for sx, xe in ((-1, mt(GROUND[0]) + 3), (1, mt(GROUND[2]) - 3)):
        for k in range(11):
            y = mt(GROUND[1]) + 8 + k * 8.2 + rng.uniform(-1.5, 1.5)
            blob(bm, (xe + rng.uniform(-1, 1), y, 1.5), (rng.uniform(1.8, 3.2), rng.uniform(1.8, 3.2), rng.uniform(1.6, 3.4)),
                 rng.choice(rocks), segs=6, rings=4, jitter=0.2)


def make_pine(tiers, h, rb):
    def b(bm, ex):
        th = h * 0.22
        frustum(bm, T((0, 0, 0)), 0.28, 0.14, th + 0.6, C.BARK, segs=6)
        step = (h - th) / tiers
        for i in range(tiers):
            frustum(bm, T((0, 0, th * 0.8 + i * step * 0.92)), rb * (1 - i / (tiers + 0.6)), 0.0, step * 1.4,
                    C.LEAF_DARK if i % 2 else C.LEAF_MID, segs=7, jitter=0.07)
    return b


def make_cypress(h, r):
    def b(bm, ex):
        frustum(bm, T((0, 0, 0)), 0.2, 0.12, 0.8, C.BARK, segs=5)
        frustum(bm, T((0, 0, 0.6)), r, r * 0.55, h * 0.55, C.CYPRESS, segs=6, jitter=0.05)
        frustum(bm, T((0, 0, 0.6 + h * 0.5)), r * 0.6, 0.0, h * 0.55, C.CYPRESS, segs=6, jitter=0.05)
    return b


def make_olive(seed):
    def b(bm, ex):
        r = random.Random(seed)
        beam(bm, (0, 0, 0), (0.25, 0.1, 1.6), 0.3, 0.2, C.BARK, 6)
        beam(bm, (0.1, 0, 0.8), (-0.55, 0.2, 2.2), 0.18, 0.12, C.BARK, 5)
        for dx, dy, dz, s in ((0.3, 0.1, 2.5, 1.2), (-0.7, 0.3, 2.7, 1.0), (0.1, -0.5, 3.0, 1.0), (0.9, 0.5, 2.3, 0.8)):
            blob(bm, (dx, dy, dz), (s * 1.1, s, s * 0.7), r.choice([C.OLIVE, C.LEAF_LIGHT]), segs=6, rings=3, jitter=0.15)
    return b


def make_rock(seed, s):
    def b(bm, ex):
        r = random.Random(seed)
        blob(bm, (0, 0, s * 0.3), (s * r.uniform(0.9, 1.4), s * r.uniform(0.8, 1.2), s * 0.7), r.choice([C.STONE, C.STONE_DARK, C.SLATE]),
             segs=6, rings=4, jitter=0.2)
        if seed % 2:
            blob(bm, (s * 0.8, s * 0.3, s * 0.15), (s * 0.5, s * 0.45, s * 0.35), C.STONE_LIGHT, segs=5, rings=3, jitter=0.2)
    return b


def make_flowers(seed):
    def b(bm, ex):
        r = random.Random(seed)
        for i in range(6):
            x, y = r.uniform(-0.5, 0.5), r.uniform(-0.5, 0.5)
            h = r.uniform(0.35, 0.7)
            beam(bm, (x, y, 0), (x + r.uniform(-0.1, 0.1), y, h), 0.025, 0.0, C.LEAF_MID, 3)
            blob(bm, (x, y, h + 0.04), (0.1, 0.1, 0.07), r.choice([C.FLOWER_WHITE, C.FLOWER_PURPLE, C.GOLD]), segs=5, rings=3)
    return b


def scatter():
    pines = [variant("Tree_Pine_A", make_pine(5, 10.5, 2.1)), variant("Tree_Pine_B", make_pine(4, 8.5, 2.4)),
             variant("Tree_Pine_C", make_pine(6, 12.5, 1.9))]
    rocks = [variant("Rock_%d" % i, make_rock(i, 0.5 + 0.25 * i)) for i in range(6)]
    flowers = [variant("Flowers_%d" % i, make_flowers(i)) for i in range(2)]
    cyp = [variant("Tree_Cypress_A", make_cypress(7.0, 0.95)), variant("Tree_Cypress_B", make_cypress(5.5, 0.8))]
    oli = [variant("Tree_Olive_A", make_olive(1)), variant("Tree_Olive_B", make_olive(2))]
    n_tree = n_rock = n_flower = 0
    tries = 0
    while n_tree < 110 and tries < 30000:
        tries += 1
        x, y = rng.uniform(GROUND[0] + 6, GROUND[2] - 6), rng.uniform(GROUND[1] + 6, GROUND[3] - 18)
        if not free_of_builds(x, y, 16):
            continue
        outer = x < -158 or x > 126 or y > 160 or y < -84
        if rng.random() > (0.65 if outer else 0.10):
            continue
        put("Tree_Pine", rng.choice(pines), mt(x), mt(y), 0.0, rng.uniform(0, math.tau), rng.uniform(0.85, 1.25))
        n_tree += 1
    tries = 0
    while n_rock < 64 and tries < 30000:
        tries += 1
        x, y = rng.uniform(GROUND[0] + 6, GROUND[2] - 6), rng.uniform(GROUND[1] + 6, GROUND[3] - 18)
        if not free_of_builds(x, y, 3) or free_of_builds(x, y, 26) or rng.random() > 0.12:
            continue
        put("Rock", rng.choice(rocks), mt(x), mt(y), 0.0, rng.uniform(0, math.tau), rng.uniform(0.8, 1.6))
        n_rock += 1
    tries = 0
    while n_flower < 56 and tries < 30000:
        tries += 1
        x, y = rng.uniform(GROUND[0] + 6, GROUND[2] - 6), rng.uniform(GROUND[1] + 6, GROUND[3] - 18)
        if not free_of_builds(x, y, 4) or free_of_builds(x, y, 30) or rng.random() > 0.15:
            continue
        put("Flowers", rng.choice(flowers), mt(x), mt(y), 0.0, rng.uniform(0, math.tau))
        n_flower += 1
    for sx in (-1, 1):                                              # olives line the Causeway, cypresses guard the shrine
        for y in (14.0, 20.0, 25.0, 39.0):
            put("Tree_Olive", rng.choice(oli), sx * 7.6, y, 0.0, rng.uniform(0, math.tau), rng.uniform(0.9, 1.15))
        for y in (46.5, 54.0):
            put("Tree_Cypress", rng.choice(cyp), sx * 7.4, y, 0.0, 0.0, rng.uniform(0.95, 1.2))
    return n_tree, n_rock, n_flower


# ============================ BUILD EVERYTHING ================================
use_frame(Frame(0.0, 0.0, 0.0))
static("Proving_Ground", ground_base, trim=False)
static("Proving_Roads", roads)
static("Proving_MusterYard", yard_floor)
static("Proving_MusterYard_Props", yard_props)
static("Proving_Gate", proving_gate)
static("Proving_EntryArches", entry_arches)
static("Archery_Ground", archery_ground)
static("Archery_Fences", archery_fences)
static("Archery_Props", archery_props)
static("Proving_Causeway", causeway)
static("Proving_Pavilion", pavilion)
static("Proving_Shrine", shrine)
static("Sparring_Arena", arena_floor)
static("Sparring_Arena_Props", arena_props)
static("Sparring_DrillYard", drill_floor)
static("Proving_Ridge", ridge)

# ---- hub stations
station("Yard_Quartermaster", "quartermaster", "Get Gear", b_quarter, -6.9, 6.4, prompt_h=1.8,
        colliders=[(0, -0.6, 0.65, 5.8, 1.2, 1.3)])
station("Yard_NoticeBoard", "noticeboard", "Training Board", b_notice, 7.4, 6.8, prompt_h=1.6,
        colliders=[(-1.6, 0, 1.4, 0.4, 0.4, 2.8), (1.6, 0, 1.4, 0.4, 0.4, 2.8)])
marker("Yard_Spawn", "spawn", "Arrival point", 0.0, mt(-30), 0.4)
marker("Camp_Road_Connection", "link", "Connect the camp road here", 0.0, mt(-100), 0.4)

# ---- archery stations
n = 1
for lane, cx in enumerate(LANE_CX):
    station("Archery_Lane_%02d" % (lane + 1), "lane", "Lane %d" % (lane + 1),
            lambda b, e, k=lane + 1: b_lane_gate(b, e, k), mt(cx), mt(29), prompt_h=2.0,
            colliders=[(-1.7, 0, 2.5, 0.7, 0.7, 5.0), (1.7, 0, 2.5, 0.7, 0.7, 5.0)], lane=lane + 1)
    # sight-line-checked layout: face diameter 5 / 6.5 / 8 studs, centre height 3.5 / 4.5 / 10 studs,
    # lateral offsets -4 / +3.5 / -1 studs -> >= 90% of every target is visible from anywhere in its lane
    for key, dx, yd, d, zc in (("near", -4.0, NEAR_Y, 5 / 3, 3.5 / 3), ("mid", 3.5, MID_Y, 6.5 / 3, 4.5 / 3),
                               ("far", -1.0, FAR_Y, 8 / 3, 10 / 3)):
        station("Archery_Target_%02d" % n, "target", "Target (%s)" % key, lambda b, e, d=d, zc=zc: b_target(b, e, d, zc),
                mt(cx + dx), mt(yd), share="target_" + key, prompt_h=zc,
                colliders=[(0, 0.2, zc, d * 1.1, 0.5, d * 1.1)], lane=lane + 1, dist=yd - FIRE_Y)
        n += 1
for i, bx in enumerate([LANE_CX[0] + 7 + 14 * k for k in range(4)] + [-135.2, -130.8]):
    # shared ammo barrels sit on the lane boundaries / between the hydra gates: never inside a gate opening
    station("Archery_Ammo_%02d" % (i + 1), "ammo", "Take Arrows", b_ammo, mt(bx), mt(32.4), share="ammo",
            prompt_h=1.4, colliders=[(0, 0, 0.55, 1.1, 1.1, 1.1)])
for i, cx in enumerate((-143, -123)):
    station("Hydra_Gate_%02d" % (i + 1), "gate", "Hydra Bay gate", b_hydra_gate, mt(cx), mt(29), share="hydra_gate",
            prompt_h=2.0, colliders=[(-1.7, 0, 2.5, 0.7, 0.7, 5.0), (1.7, 0, 2.5, 0.7, 0.7, 5.0)])
for i, cx in enumerate((-84, -112)):
    station("Archery_BowRack_%02d" % (i + 1), "bow_rack", "Take a Bow", b_bow_rack, mt(cx), 3.3, lrot=math.pi,
            share="bow_rack", prompt_h=1.6, colliders=[(0, 0, 1.2, 3.6, 0.5, 2.4)])
station("Archery_Scoreboard", "scoreboard", "Archery Scores", b_scoreboard, mt(-44), mt(14), prompt_h=1.8,
        colliders=[(-1.7, 0, 1.6, 0.5, 0.5, 3.2), (1.7, 0, 1.6, 0.5, 0.5, 3.2)])
hx_m, hy_m = mt(HYDRA_C[0]), mt(HYDRA_C[1])
station("Archery_Hydra", "hydra_body", "Hydra", b_hydra_body, hx_m, hy_m, prompt_h=3.0,
        colliders=[(-5.6, 0, 3.95, 0.8, 0.9, 7.7), (5.6, 0, 3.95, 0.8, 0.9, 7.7)])
for k in range(5):
    hx, hy, hz = HEADS[k]
    station("Archery_HydraHead_%02d" % (k + 1), "hydra_head", "Hydra Head %d" % (k + 1),
            lambda b, e, k=k: b_hydra_head(b, e, k), hx_m + hx, hy_m + hy, hz, prompt_h=0.0, trim=False,
            colliders=[(0, -0.2, 0.0, 1.3, 1.7, 1.1)], head=k + 1)

# ---- sparring stations
cx, cy, w, d = ARC
for i, (sx, sy, rot) in enumerate(((0, -1, 0.0), (1, 0, math.pi / 2), (0, 1, math.pi), (-1, 0, -math.pi / 2))):
    gx, gy = cx + sx * (w / 2 + 0.25), cy + sy * (d / 2 + 0.25)
    station("Sparring_Gate_%s" % "SENW"[i], "gate", "Arena gate", b_arena_gate, gx, gy, lrot=rot, share="arena_gate",
            prompt_h=2.0, colliders=[(-2.85, 0, 2.5, 1.5, 1.5, 5.0), (2.85, 0, 2.5, 1.5, 1.5, 5.0)])
    qx, qy = gx + sx * 3.6 + (-sy * 4.4), gy + sy * 3.6 + (sx * 4.4)
    station("Sparring_Queue_%s" % "SENW"[i], "queue", "Join Duel Queue", b_queue, qx, qy, lrot=rot, share="queue",
            prompt_h=1.6, colliders=[(-1.4, 0, 1.4, 0.4, 0.4, 2.8), (1.4, 0, 1.4, 0.4, 0.4, 2.8)])
for i, dx in enumerate((16.2, 19.0, 21.8, 28.9, 31.7, 34.5)):         # two groups, 4.4 m aisle on the Gladiators' Way axis
    station("Sparring_Dummy_%02d" % (i + 1), "dummy", "Strike Dummy", b_dummy, dx, 18.7, share="dummy",
            prompt_h=1.8, colliders=[(0, 0, 1.2, 1.5, 1.5, 2.4)])
for i, x in enumerate((19.6, 31.1)):
    station("Sparring_DuelRing_%02d" % (i + 1), "duel_ring", "Challenge a Duel", b_duel_ring, x, 13.4, share="duel_ring",
            prompt_h=1.0, colliders=[(0, 0, 0.13, 7.3, 7.3, 0.26)])
for i, (x, rot) in enumerate(((15.1, math.pi / 2), (35.6, -math.pi / 2))):      # on the fences, facing into the yard
    station("Sparring_WeaponRack_%02d" % (i + 1), "weapon_rack", "Take Practice Weapon", b_weapon_rack, x, 14.0,
            lrot=rot, share="weapon_rack", prompt_h=1.6, colliders=[(0, 0, 1.3, 4.3, 0.5, 2.6)])
station("Proving_Stele", "leaderboard", "Heroes' Board", b_stele, 0.0, mt(SHR_Y0 + SHR_Y1) / 2 + 3.0, 3.0, prompt_h=2.0,
        colliders=[(0, 0, 2.2, 4.6, 0.9, 4.4)])

# ---- zone volumes (combat rules for your scripts) + landmarks
zone("Zone_Safe_Hub", "zone_safe", "Muster Yard", YARD)
zone("Zone_Safe_Terrace", "zone_safe", "Archery terrace", TERR, 0, 20)
zone("Zone_Safe_Causeway", "zone_safe", "Causeway, pavilion and shrine", (-20, CW_STAIR0, 20, SHR_Y1 + 10))
zone("Zone_Archery", "zone_archery", "Archery field (projectiles on, PvP off)", (-108, FIRE_Y, -38, BACK_Y1))
zone("Zone_Hydra", "zone_hydra", "Hydra Bay (projectiles on, PvP off)", (-152, FIRE_Y, -114, BACK_Y1))
zone("Zone_Drill", "zone_drill", "Drill Yard (dummies on, PvP off)", DRILL)
zone("Zone_Arena", "zone_arena", "Sparring Arena (melee PvP on)", RING)
marker("Arena_Center", "marker", "Arena centre", ARC[0], ARC[1], 0.5)
marker("Archery_Firing_Line", "marker", "Firing line", mt(-73), mt(FIRE_Y), 0.3)
marker("Hydra_Firing_Line", "marker", "Hydra firing line", mt(-133), mt(FIRE_Y), 0.3)

n_tree, n_rock, n_flower = scatter()


# ============================ REPORT =========================================
print("\n=== Camp DemiSoul Proving Grounds: report (units = studs) ===")
over = [k for k, t in MESHES.items() if t > TRI_WARN]
tot = sum(MESHES.values())
big = sorted(MESHES.items(), key=lambda kv: -kv[1])[:10]
print("Objects in scene : %d   (unique meshes: %d)" % (len(OBJECTS), len(MESHES)))
print("Unique triangles : %d   (largest meshes below)" % tot)
for k, t in big:
    print("   %-30s %6d tris%s" % (k, t, "   <-- OVER BUDGET" if t > TRI_WARN else ""))
print("Instances        : %d pines, %d rocks, %d flower clusters (+ olives/cypresses)" % (n_tree, n_rock, n_flower))
kinds = {}
for s in STATIONS:
    kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
print("Stations/markers : %d   Collision boxes: %d" % (len(STATIONS), len(COLLIDERS)))
print("By kind          :", ", ".join("%s x%d" % kv for kv in sorted(kinds.items())))
if over:
    print("WARNING over budget:", over)


# ============================ EXPORT: JSON + LUA + FBX =======================
def rbx(p):
    return [round(p[0] * STUD_SCALE, 2), round(p[2] * STUD_SCALE, 2), round(-p[1] * STUD_SCALE, 2)]


def rsize(s):
    return [round(s[0] * STUD_SCALE, 2), round(s[2] * STUD_SCALE, 2), round(s[1] * STUD_SCALE, 2)]


def lua_table(items, kind):
    rows = []
    for it in items:
        p = rbx(it["pos"])
        deg = round(math.degrees(it["rot"]), 2)
        if kind == "collider":
            s = rsize(it["size"])
            rows.append('  {name=%s, pos=Vector3.new(%s,%s,%s), rotY=%s, size=Vector3.new(%s,%s,%s)},' % (
                json.dumps(it["name"]), p[0], p[1], p[2], deg, s[0], s[1], s[2]))
        else:
            extra = ""
            if "size" in it:
                s = rsize(it["size"])
                extra = ", size=Vector3.new(%s,%s,%s)" % (s[0], s[1], s[2])
            rows.append('  {name=%s, kind=%s, label=%s, pos=Vector3.new(%s,%s,%s), rotY=%s%s},' % (
                json.dumps(it["name"]), json.dumps(it["kind"]), json.dumps(it["label"]), p[0], p[1], p[2], deg, extra))
    return "\n".join(rows)


LUA_HEAD = '''-- Camp DemiSoul Proving Grounds: collision + interaction + combat-zone setup (generated by the Blender script).
-- 1) Import the FBX at the world origin.  2) Paste this into the Studio command bar (or a Script run once).
-- Creates Model "ProvingGrounds_Interaction": invisible collision boxes, ProximityPrompt anchors, zone volumes.
-- If the imported meshes are offset, move this whole model by the same amount (or tell me).
local root = workspace:FindFirstChild("ProvingGrounds_Interaction")
if root then root:Destroy() end
root = Instance.new("Model"); root.Name = "ProvingGrounds_Interaction"; root.Parent = workspace
local colFolder = Instance.new("Folder"); colFolder.Name = "Collision"; colFolder.Parent = root
local stFolder = Instance.new("Folder"); stFolder.Name = "Stations"; stFolder.Parent = root
local zoneFolder = Instance.new("Folder"); zoneFolder.Name = "Zones"; zoneFolder.Parent = root
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
local PROMPT_KINDS = {quartermaster=true, noticeboard=true, ammo=true, bow_rack=true, weapon_rack=true, queue=true,
  duel_ring=true, leaderboard=true, scoreboard=true}
for _, s in ipairs(STATIONS) do
  local a = Instance.new("Part")
  a.Name = s.name; a.Anchored = true; a.CanCollide = false; a.Transparency = 1
  a.CFrame = CFrame.new(s.pos) * CFrame.Angles(0, math.rad(s.rotY), 0)
  if s.size then                                   -- zone volume: detect players with GetPartsInPart / Touched
    a.Size = s.size; a.CanTouch = true; a.CanQuery = true
    a:SetAttribute("ZoneType", s.kind); a:SetAttribute("ZoneLabel", s.label)
    a.Parent = zoneFolder
  else
    a.Size = Vector3.new(1, 1, 1); a.CanTouch = false; a.CanQuery = false
    a:SetAttribute("StationType", s.kind); a:SetAttribute("StationLabel", s.label)
    a.Parent = stFolder
    if PROMPT_KINDS[s.kind] then
      local pp = Instance.new("ProximityPrompt")
      pp.ActionText = s.label; pp.ObjectText = s.name:gsub("_", " ")
      pp.HoldDuration = 0; pp.MaxActivationDistance = 12; pp.RequiresLineOfSight = false
      pp.Parent = a
    end
  end
end
print(("ProvingGrounds_Interaction: %d collision boxes, %d stations/zones"):format(#COLLIDERS, #STATIONS))
'''


def write_exports():
    if not OUT:
        return
    data = {
        "units": "studs", "stud_scale": STUD_SCALE,
        "note": "Roblox position = (x*S, z*S, -y*S); rotY degrees about +Y; size = (x, z, y)*S",
        "stations": [], "colliders": [],
    }
    for s in STATIONS:
        e = dict(s, pos=rbx(s["pos"]), rotY=round(math.degrees(s["rot"]), 2))
        e.pop("rot", None)
        if "size" in e:
            e["size"] = rsize(e["size"])
        data["stations"].append(e)
    for c in COLLIDERS:
        e = dict(c, pos=rbx(c["pos"]), size=rsize(c["size"]), rotY=round(math.degrees(c["rot"]), 2))
        e.pop("rot", None)
        data["colliders"].append(e)
    with open(os.path.join(OUT, "Proving_StationMarkers.json"), "w") as fh:
        json.dump(data, fh, indent=1)
    with open(os.path.join(OUT, "Proving_Grounds_Setup.lua"), "w") as fh:
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
        print("Wrote Proving_StationMarkers.json + Proving_Grounds_Setup.lua to:", OUT)
    except Exception as exc:
        print("Marker/Lua export failed:", exc)
    try:
        fbx_path = os.path.join(OUT, "CampDemiSoul_ProvingGrounds.fbx")
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
