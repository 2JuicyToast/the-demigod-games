# =============================================================================
# CAMP DEMISOUL - MAIN ENTRANCE (game-ready rebuild)
# Run in Blender's Scripting tab (Blender 3.6 / 4.x). Safe to re-run: it only
# replaces its own collection ("CampEntrance_GameReady").
#
# What this builds (each is ONE mesh = ONE draw call in Roblox):
#   Entrance_PillarL / Entrance_PillarR   banners, ivy, moss included
#   Entrance_Lintel                       Greek-key frieze, CAMP DEMISOUL lettering, bull crest
#   Entrance_Palladium                    rock mound, stepped EMPTY pedestal (for a Roblox NPC)
#   Entrance_Brazier_L / _R               one shared mesh, placed twice
#   Entrance_Glow                         flames, halo, gem  -> set Material = Neon in Studio
#   Entrance_Path                         single smooth ribbon, worn centre strip
#   Entrance_Foliage                      shrubs, grass tufts, flowers, rocks
#   Entrance_Ground                       optional grass slab (use Terrain if you prefer)
#
# Everything shares ONE 256x256 palette texture (written next to the export),
# so there are no per-object textures and no UV unwrapping headaches.
# Front of the entrance faces -Y. Camp/lobby is toward +Y.
# =============================================================================

import bpy, bmesh, math, os, random, struct, zlib
from mathutils import Vector, Matrix

# ------------------------------ SETTINGS -------------------------------------
STUD_SCALE = 3.0        # studs per modelled metre. Gate opening = 12 m -> 36 studs.
                        # Lower it (2.8 = true human scale) if the gate feels too big.
EXPORT = True           # write palette PNG + FBX
EXPORT_DIR = ""         # blank = next to your .blend (or your home folder if unsaved)
COLLECTION_NAME = "CampEntrance_GameReady"
TRI_WARN = 20000        # Roblox per-mesh limit to stay under
SEED = 24

# --------------------------- PALETTE (one texture) ---------------------------
PALETTE = [
    ("STONE", "#9A927F"), ("STONE_LIGHT", "#C2B9A2"), ("STONE_DARK", "#5E5E56"), ("MARBLE", "#E8E1D0"),
    ("BRONZE", "#9C7A3C"), ("BRONZE_DARK", "#5A431F"), ("MAROON", "#5E1D2E"), ("CREAM", "#F1ECDF"),
    ("DIRT", "#9B7446"), ("DIRT_LIGHT", "#BE9A62"), ("GRASS", "#4A6B2E"), ("GRASS_LIGHT", "#6E8E3E"),
    ("LEAF_DARK", "#1F4A2E"), ("LEAF_MID", "#2F6B3F"), ("LEAF_LIGHT", "#58954F"), ("MOSS", "#62803A"),
    ("WOOD", "#5A3B22"), ("GLOW", "#FFC24A"), ("FLOWER_WHITE", "#E8D8A8"), ("FLOWER_PURPLE", "#7A55A8"),
]
C = {name: i for i, (name, _) in enumerate(PALETTE)}
GRID, CELL = 8, 32
TEX = GRID * CELL

rng = random.Random(SEED)


# ------------------------------ PALETTE PNG ----------------------------------
def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def write_palette_png(path):
    rows = []
    for r in range(TEX):
        cy = (TEX - 1 - r) // CELL          # PNG rows run top->bottom, UV v runs bottom->top
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
        d = os.path.join(base, "CampDemiSoul_Entrance_Export")
        os.makedirs(d, exist_ok=True)
        return d
    except Exception as exc:
        print("Could not create export folder:", exc)
        return None


OUT = output_dir()
PNG_PATH = None
if OUT:
    try:
        PNG_PATH = os.path.join(OUT, "DemiSoul_Palette.png")
        write_palette_png(PNG_PATH)
    except Exception as exc:
        print("Could not write palette PNG:", exc)
        PNG_PATH = None


def make_material(png_path):
    mat = bpy.data.materials.get("DemiSoul_Palette") or bpy.data.materials.new("DemiSoul_Palette")
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


# ------------------------------ CLEAN RE-RUN ---------------------------------
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


# ------------------------------ PRIMITIVES -----------------------------------
# Every primitive writes into a bmesh and tags its faces with a palette index
# (stored in material_index until finish() turns it into UVs).
# Faces are oriented outward automatically, so winding mistakes can't happen.

def T(c):
    return Matrix.Translation(Vector(c))


ROT_X90 = Matrix.Rotation(math.pi / 2, 4, "X")   # local +Z -> world -Y (faces the viewer)


def add_face(bm, vs, ref, color):
    """Create a face wound so its normal points away from `ref` (an interior point)."""
    p = [v.co for v in vs]
    n = (p[1] - p[0]).cross(p[2] - p[1])
    cen = sum(p, Vector((0, 0, 0))) / len(p)
    if n.dot(cen - ref) < 0:
        vs = vs[::-1]
    try:
        f = bm.faces.new(vs)
    except ValueError:
        return None
    f.material_index = color
    return f


def box(bm, c, s, color, rot=0.0, ch=0.0):
    """Box centred at c, size s=(x,y,z), optional Z rotation and chamfer `ch`."""
    hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
    half = (hx, hy, hz)
    M = T(c) @ Matrix.Rotation(rot, 4, "Z")
    ref = Vector(c)
    signs = [(sx, sy, sz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]

    def ordered(a, sg):
        b1, b2 = [i for i in range(3) if i != a]
        cs = [S for S in signs if S[a] == sg]
        cs.sort(key=lambda S: math.atan2(S[b2], S[b1]))
        return cs

    if ch <= 0:
        V = {S: bm.verts.new(M @ Vector((S[0] * hx, S[1] * hy, S[2] * hz))) for S in signs}
        for a in range(3):
            for sg in (-1, 1):
                add_face(bm, [V[S] for S in ordered(a, sg)], ref, color)
        return

    k = min(ch, 0.9 * min(hx, hy, hz))
    V = {}
    for a in range(3):
        for S in signs:
            p = [S[i] * (half[i] - k) for i in range(3)]
            p[a] = S[a] * half[a]
            V[(a, S)] = bm.verts.new(M @ Vector(p))
    for a in range(3):                                    # six inset faces
        for sg in (-1, 1):
            add_face(bm, [V[(a, S)] for S in ordered(a, sg)], ref, color)
    for a, b in ((0, 1), (0, 2), (1, 2)):                 # twelve chamfer strips
        c3 = 3 - a - b
        for sa in (-1, 1):
            for sb in (-1, 1):
                S1 = [0, 0, 0]; S2 = [0, 0, 0]
                S1[a] = S2[a] = sa
                S1[b] = S2[b] = sb
                S1[c3], S2[c3] = -1, 1
                S1, S2 = tuple(S1), tuple(S2)
                add_face(bm, [V[(a, S1)], V[(a, S2)], V[(b, S2)], V[(b, S1)]], ref, color)
    for S in signs:                                       # eight corner triangles
        add_face(bm, [V[(0, S)], V[(1, S)], V[(2, S)]], ref, color)


def frustum(bm, M, r0, r1, h, color, segs=8, jitter=0.0):
    """Cylinder/cone along local +Z starting at M's origin. r1~0 makes a point."""
    apex = r1 <= 0.0005
    bot, top = [], []
    for j in range(segs):
        a = math.tau * j / segs
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
    """Low-poly lumpy sphere (foliage, rocks, heads). rings=2 gives a flat diamond leaf."""
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
    """Flat annulus along local +Z (halo, trim rings)."""
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


def prism(bm, pts, c, sc, t, color, mx=1):
    """Flat extruded polygon in the XZ plane, thickness t along Y, centred at c.
    pts are (x, z) pairs. Used for the bull emblem and swallow-tail banners."""
    P = [(mx * x * sc, z * sc) for x, z in pts]
    n = len(P)
    area = sum(P[i][0] * P[(i + 1) % n][1] - P[(i + 1) % n][0] * P[i][1] for i in range(n))
    if abs(area) < 1e-9:
        return
    f = [bm.verts.new((c[0] + x, c[1] - t / 2, c[2] + z)) for x, z in P]
    b = [bm.verts.new((c[0] + x, c[1] + t / 2, c[2] + z)) for x, z in P]
    ccw = area > 0

    def new(vs):
        try:
            fc = bm.faces.new(vs)
            fc.material_index = color
        except ValueError:
            pass

    new(f if ccw else f[::-1])          # front faces -Y
    new(b[::-1] if ccw else b)          # back faces +Y
    for i in range(n):
        j = (i + 1) % n
        new([f[j], f[i], b[i], b[j]] if ccw else [f[i], f[j], b[j], b[i]])


# Bull-head emblem (matches the flag), drawn facing -Y.
HEAD = [(-0.40, 0.28), (0.40, 0.28), (0.46, 0.02), (0.26, -0.40), (0.0, -0.52), (-0.26, -0.40), (-0.46, 0.02)]
HORN = [(-0.28, 0.18), (-0.66, 0.06), (-0.98, 0.18), (-1.12, 0.48), (-1.06, 0.86), (-0.92, 1.04),
        (-0.86, 0.74), (-0.84, 0.50), (-0.64, 0.30), (-0.30, 0.34)]
EAR = [(-0.46, 0.02), (-0.90, 0.10), (-0.80, -0.10), (-0.46, -0.10)]
EYE = [(-0.34, 0.06), (-0.10, -0.02), (-0.10, 0.08), (-0.34, 0.14)]
MUZZLE = [(-0.18, -0.28), (0.18, -0.28), (0.15, -0.36), (-0.15, -0.36)]


def emblem(bm, c, sc, light, dark, t=0.08):
    """c = centre of the emblem's back face-ish plane; features sit slightly proud."""
    fy = c[1] - t * 0.45
    for mx in (1, -1):
        prism(bm, HORN, c, sc, t, light, mx)
        prism(bm, EAR, c, sc, t, light, mx)
        prism(bm, EYE, (c[0], fy, c[2]), sc, t * 0.6, dark, mx)
    prism(bm, HEAD, c, sc, t, light)
    prism(bm, MUZZLE, (c[0], fy, c[2]), sc, t * 0.6, dark)



# Angular stroke lettering (echoes the flag). Each glyph = (width, [polylines]) in a 1-unit-tall cell.
GLYPHS = {
    "C": (0.65, [[(0.62, 0.95), (0.08, 0.5), (0.62, 0.05)]]),
    "A": (0.70, [[(0.0, 0.0), (0.35, 1.0), (0.70, 0.0)], [(0.14, 0.36), (0.56, 0.36)]]),
    "M": (0.70, [[(0.0, 0.0), (0.0, 1.0), (0.35, 0.45), (0.70, 1.0), (0.70, 0.0)]]),
    "P": (0.65, [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.65, 0.76), (0.0, 0.52)]]),
    "D": (0.65, [[(0.0, 0.0), (0.0, 1.0), (0.65, 0.5), (0.0, 0.0)]]),
    "E": (0.60, [[(0.6, 1.0), (0.0, 1.0), (0.0, 0.0), (0.6, 0.0)], [(0.0, 0.5), (0.45, 0.5)]]),
    "I": (0.10, [[(0.05, 0.0), (0.05, 1.0)]]),
    "S": (0.60, [[(0.6, 0.95), (0.04, 0.8), (0.04, 0.62), (0.56, 0.38), (0.56, 0.2), (0.0, 0.05)]]),
    "O": (0.70, [[(0.35, 1.0), (0.70, 0.5), (0.35, 0.0), (0.0, 0.5), (0.35, 1.0)]]),
    "U": (0.70, [[(0.0, 1.0), (0.0, 0.22), (0.35, 0.0), (0.70, 0.22), (0.70, 1.0)]]),
    "L": (0.55, [[(0.0, 1.0), (0.0, 0.0), (0.55, 0.0)]]),
}


def text(bm, s, c, h, color, depth=0.08, stroke=0.16, gap=0.38, space=0.8):
    """Raised lettering facing -Y. c = centre (x, y, z) of the text block, h = letter height."""
    x, spans = 0.0, []
    for ch in s:
        if ch == " ":
            x += space
        else:
            spans.append((ch, x))
            x += GLYPHS[ch][0] + gap
    total = x - gap
    x0 = c[0] - total * h / 2
    hw = stroke * h / 2
    for ch, ox in spans:
        for line in GLYPHS[ch][1]:
            pts = [(x0 + (ox + px) * h - c[0], (pz - 0.5) * h) for px, pz in line]
            for a, b in zip(pts[:-1], pts[1:]):
                dx, dz = b[0] - a[0], b[1] - a[1]
                L = math.hypot(dx, dz)
                if L < 1e-6:
                    continue
                nx, nz = -dz / L * hw, dx / L * hw
                prism(bm, [(a[0] + nx, a[1] + nz), (b[0] + nx, b[1] + nz),
                           (b[0] - nx, b[1] - nz), (a[0] - nx, a[1] - nz)], c, 1.0, depth, color)
            for px, pz in pts:                        # filled joints so corners stay solid
                prism(bm, [(px - hw, pz), (px, pz + hw), (px + hw, pz), (px, pz - hw)], c, 1.0, depth, color)


# ------------------------------ FINISH / OBJECT ------------------------------
def finish(name, bm, trim=True, location=None):
    bm.normal_update()
    if trim:   # drop faces under the ground and bottoms that sit on it (never seen)
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
    for vert in bm.verts:
        vert.co *= STUD_SCALE
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(MAT)
    obj = bpy.data.objects.new(name, me)
    COL.objects.link(obj)
    if location:
        obj.location = tuple(v * STUD_SCALE for v in location)
    return obj


# ------------------------------ LAYOUT HELPERS -------------------------------
def catmull(pts, per=6):
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


PATH_PTS = [(-3, -30), (-4, -24), (-1.5, -18), (1.5, -13), (1.2, -9.5),
            (0, -5), (0, 0), (2.2, 6), (1.5, 12), (-1, 18)]
PATH = catmull(PATH_PTS, 6)
PX, PY = -16.0, -3.5          # Palladium mound centre (where the tree used to be)


def near_path(x, y, m):
    return any((x - px) ** 2 + (y - py) ** 2 < m * m for px, py in PATH)


def clear_of_landmarks(x, y, pad=0.0):
    if abs(x) < 9.8 + pad and -11 - pad < y < -3.5 + pad:       # gate footprint
        return False
    if (x - PX) ** 2 + (y - PY) ** 2 < (8.4 + pad) ** 2:        # palladium mound
        return False
    return True


# ============================ 1) GATE PILLARS ================================
GATE_Y = -7.2


def vine(bm, x, y, z0, z1, phase):
    n = 6
    pts = [(x + 0.18 * math.sin(i / n * 5 + phase), y, z0 + (z1 - z0) * i / n) for i in range(n + 1)]
    for a, b in zip(pts[:-1], pts[1:]):
        beam(bm, a, b, 0.05, 0.045, C["LEAF_DARK"], segs=4)
    for i, p in enumerate(pts):
        side = 1 if i % 2 else -1
        for k in (0, 1):
            blob(bm, (p[0] + side * (0.13 + 0.09 * k), p[1] - 0.03, p[2] + 0.06 * k),
                 (0.14, 0.03, 0.09), rng.choice([C["LEAF_MID"], C["LEAF_LIGHT"], C["LEAF_DARK"]]),
                 segs=4, rings=2, rot=rng.uniform(0, 1.5))


def build_pillar(bm, x, vines):
    Y = GATE_Y
    box(bm, (x, Y, 0.25), (3.0, 2.5, 0.7), C["STONE_DARK"], ch=0.12)       # footing
    box(bm, (x, Y, 0.85), (2.65, 2.25, 0.5), C["STONE_LIGHT"], ch=0.08)    # plinth
    box(bm, (x, Y, 4.10), (2.15, 1.9, 6.0), C["STONE"], ch=0.10)           # shaft
    box(bm, (x, Y, 7.35), (2.70, 2.2, 0.5), C["STONE_LIGHT"], ch=0.08)     # capital
    fy = Y - 0.95 - 0.015
    for row in range(1, 6):                                                # masonry courses
        box(bm, (x, fy, 1.1 + row), (2.1, 0.03, 0.04), C["STONE_DARK"])
        for sx in (-1, 1):
            box(bm, (x + sx * 1.09, Y, 1.1 + row), (0.03, 1.86, 0.04), C["STONE_DARK"])
    for row in range(6):                                                   # staggered joints
        off = 0.45 if row % 2 == 0 else -0.45
        box(bm, (x + off, fy, 1.6 + row), (0.04, 0.03, 0.96), C["STONE_DARK"])
    box(bm, (x - 0.35, fy - 0.005, 1.55), (0.95, 0.04, 0.50), C["MOSS"])    # moss patches
    box(bm, (x + 0.55, fy - 0.005, 2.20), (0.60, 0.04, 0.40), C["MOSS"])
    box(bm, (x - 0.60, fy - 0.005, 6.65), (0.70, 0.04, 0.30), C["MOSS"])
    for vx, z0, z1, ph in vines:
        vine(bm, x + vx, fy - 0.04, z0, z1, ph)
    # maroon swallow-tail banner with the bull crest, hung from a bronze rod
    by = fy - 0.07
    prism(bm, [(-0.55, 0), (0.55, 0), (0.55, -2.4), (0, -1.95), (-0.55, -2.4)],
          (x, by, 5.95), 1.0, 0.08, C["MAROON"])
    box(bm, (x, by, 6.0), (1.5, 0.12, 0.09), C["BRONZE"])
    for sx in (-1, 1):
        blob(bm, (x + sx * 0.78, by, 6.0), (0.10, 0.10, 0.10), C["BRONZE"], segs=6, rings=3)
    emblem(bm, (x, by - 0.07, 4.95), 0.42, C["CREAM"], C["MAROON"], t=0.05)


# ============================ 2) LINTEL ======================================
def key_frieze(bm, y, z, x0, x1):
    H, t, unit = 0.30, 0.07, 0.9
    bm_mid = (x0 + x1) / 2
    box(bm, (bm_mid, y, z + H / 2), (x1 - x0, 0.05, 0.05), C["BRONZE"])
    box(bm, (bm_mid, y, z - H / 2), (x1 - x0, 0.05, 0.05), C["BRONZE"])
    for i in range(int((x1 - x0) / unit)):
        xc = x0 + unit * (i + 0.5)
        box(bm, (xc - 0.32, y, z), (t, 0.05, H - 0.06), C["STONE_DARK"])
        box(bm, (xc - 0.10, y, z + 0.07), (0.44, 0.05, t), C["STONE_DARK"])
        box(bm, (xc + 0.12, y, z - 0.02), (t, 0.05, 0.20), C["STONE_DARK"])
        box(bm, (xc - 0.02, y, z - 0.10), (0.30, 0.05, t), C["STONE_DARK"])


def build_lintel(bm):
    Y = GATE_Y
    box(bm, (0, Y, 7.72), (18.0, 2.45, 0.24), C["STONE_LIGHT"], ch=0.05)   # lower trim
    box(bm, (0, Y, 8.69), (17.5, 2.30, 1.70), C["STONE"], ch=0.10)         # main block
    box(bm, (0, Y, 9.66), (18.0, 2.45, 0.24), C["STONE_LIGHT"], ch=0.05)   # upper trim
    box(bm, (0, Y, 9.88), (18.35, 2.6, 0.20), C["STONE"], ch=0.05)         # crown
    front = Y - 1.15
    key_frieze(bm, front - 0.025, 8.12, -7.8, 7.8)
    # sign panel with raised lettering
    box(bm, (0, front - 0.05, 8.92), (12.7, 0.10, 1.00), C["STONE_LIGHT"])
    for dz in (-0.53, 0.53):
        box(bm, (0, front - 0.06, 8.92 + dz), (12.9, 0.12, 0.06), C["BRONZE"])
    for sx in (-1, 1):
        box(bm, (sx * 6.45, front - 0.06, 8.92), (0.06, 0.12, 1.12), C["BRONZE"])
    text(bm, "CAMP DEMISOUL", (0, front - 0.14, 8.92), 0.80, C["BRONZE_DARK"], depth=0.08, stroke=0.18)
    # bull crest on top
    box(bm, (0, Y, 10.24), (2.8, 1.2, 0.5), C["STONE_LIGHT"], ch=0.06)
    frustum(bm, T((0, -6.8, 11.4)) @ ROT_X90, 1.43, 1.43, 0.30, C["BRONZE"], segs=16)
    frustum(bm, T((0, -6.8, 11.4)) @ ROT_X90, 1.28, 1.28, 0.40, C["MAROON"], segs=16)
    emblem(bm, (0, -7.25, 11.25), 0.78, C["CREAM"], C["MAROON"], t=0.10)


# ============================ 3) PALLADIUM ===================================
def P(x, y, z):
    return (PX + x, PY + y, z)


def build_palladium(bm, glow):
    ZB = 4.4         # top of the plinth = where a Roblox NPC will stand

    # rocky raised mound (replaces the old tree), irregular on purpose
    frustum(bm, T((PX, PY, -0.3)), 7.7, 7.4, 0.65, C["STONE_DARK"], segs=12, jitter=0.07)
    frustum(bm, T((PX, PY, 0.35)), 7.35, 7.05, 0.65, C["STONE"], segs=12, jitter=0.07)
    frustum(bm, T((PX, PY, 1.0)), 7.0, 6.4, 0.35, C["GRASS"], segs=12, jitter=0.05)
    for i in range(8):                                    # boulders around the base
        ang = math.tau * i / 8 + rng.uniform(-0.2, 0.2)
        r = rng.uniform(7.1, 7.9)
        sz = rng.uniform(0.7, 1.2)
        blob(bm, (PX + r * math.cos(ang), PY + r * math.sin(ang), 0.25),
             (sz, sz * 0.9, sz * 0.65), rng.choice([C["STONE"], C["STONE_LIGHT"], C["STONE_DARK"]]),
             segs=6, rings=3, jitter=0.15)

    # stepped platform and a larger plinth
    frustum(bm, T(P(0, 0, 1.35)), 4.6, 4.4, 0.25, C["STONE_LIGHT"], segs=20)
    frustum(bm, T(P(0, 0, 1.60)), 3.8, 3.7, 0.25, C["STONE"], segs=20)
    box(bm, P(0, 0, 2.15), (3.4, 3.4, 0.6), C["MARBLE"], ch=0.07)
    box(bm, P(0, 0, 3.25), (2.4, 2.4, 1.6), C["MARBLE"], ch=0.06)
    box(bm, P(0, 0, 2.50), (2.5, 2.5, 0.08), C["BRONZE"])
    box(bm, P(0, 0, 4.00), (2.5, 2.5, 0.08), C["BRONZE"])
    box(bm, P(0, 0, 4.225), (3.0, 3.0, 0.35), C["MARBLE"], ch=0.06)
    box(bm, P(0, -1.23, 3.25), (2.2, 0.06, 0.6), C["BRONZE_DARK"])           # name plaque
    text(bm, "PALLADIUM", P(0, -1.275, 3.25), 0.24, C["CREAM"], depth=0.03, stroke=0.2)

    # The statue has been removed: the plinth stays EMPTY for a future Roblox NPC / character statue.
    # Stand the NPC on the top face of the plinth: world (PX, PY), height ZB, in metres x STUD_SCALE.
    print("Palladium pedestal (empty) top centre, studs:", (PX * STUD_SCALE, PY * STUD_SCALE, ZB * STUD_SCALE))


# ============================ 4) BRAZIER =====================================
def build_brazier(bm):
    frustum(bm, T((0, 0, 0)), 0.50, 0.40, 0.30, C["STONE_DARK"], segs=8)
    frustum(bm, T((0, 0, 0.30)), 0.20, 0.14, 1.30, C["BRONZE_DARK"], segs=8)
    frustum(bm, T((0, 0, 1.60)), 0.16, 0.55, 0.50, C["BRONZE"], segs=8)


# ============================ 5) PATH + GROUND ===============================
def build_path(bm):
    rows = []
    n = len(PATH)
    for i, (x, y) in enumerate(PATH):
        a = PATH[max(i - 1, 0)]
        b = PATH[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        hw = 2.3 + 0.35 * math.sin(i * 0.7) + 0.2 * math.sin(i * 1.9)
        offs = (-(hw + 0.35), -hw, -hw * 0.3, hw * 0.3, hw, hw + 0.35)
        zs = (-0.02, 0.07, 0.09, 0.09, 0.07, -0.02)
        rows.append([bm.verts.new((x + nx * o, y + ny * o, z)) for o, z in zip(offs, zs)])
    strip_colors = (C["DIRT"], C["DIRT"], C["DIRT_LIGHT"], C["DIRT"], C["DIRT"])
    for r0, r1 in zip(rows[:-1], rows[1:]):
        for s in range(5):
            vs = [r0[s], r0[s + 1], r1[s + 1], r1[s]]
            p = [v.co for v in vs]
            if (p[1] - p[0]).cross(p[2] - p[1]).z < 0:
                vs = vs[::-1]
            try:
                bm.faces.new(vs).material_index = strip_colors[s]
            except ValueError:
                pass
    # threshold medallion just inside the gate
    frustum(bm, T((0, -5.6, 0.0)), 1.2, 1.1, 0.16, C["STONE_LIGHT"], segs=16)
    ring(bm, T((0, -5.6, 0.16)), 0.90, 0.72, 0.04, C["BRONZE"], segs=16)
    frustum(bm, T((0, -5.6, 0.16)), 0.62, 0.55, 0.05, C["MAROON"], segs=16)


def build_ground(bm):
    box(bm, (0, -5, -0.5), (60, 54, 1.0), C["GRASS"])
    for _ in range(16):
        x, y = rng.uniform(-27, 27), rng.uniform(-30, 20)
        box(bm, (x, y, 0.012), (rng.uniform(3, 8), rng.uniform(3, 8), 0.03),
            C["GRASS_LIGHT"], rot=rng.uniform(0, math.pi))


# ============================ 6) FOLIAGE & PROPS =============================
def build_foliage(bm):
    shrubs = [(-11, -15, 1.2), (-10, -21, 1.0), (-5, -24, 0.9), (10, -18, 1.2), (12, -12, 1.1),
              (11, -23, 1.0), (-22, -13, 1.5), (22, -10, 1.5), (-24, 2, 1.7), (24, 5, 1.6),
              (-9, 7, 1.1), (9, 10, 1.2), (-21, 12, 1.8), (21, 15, 1.7)]
    for i, (x, y, s) in enumerate(shrubs):
        if near_path(x, y, 3.6) or not clear_of_landmarks(x, y, 1.0):
            continue
        blob(bm, (x, y, 0.30), (s, s * 0.78, s * 0.5), C["LEAF_DARK"] if i % 2 else C["LEAF_MID"],
             segs=7, rings=4, jitter=0.12)
        for _ in range(3):
            blob(bm, (x + rng.uniform(-0.45, 0.45) * s, y + rng.uniform(-0.35, 0.35) * s,
                      0.55 + rng.uniform(0, 0.3)),
                 (s * 0.42, s * 0.36, s * 0.36),
                 rng.choice([C["LEAF_DARK"], C["LEAF_MID"], C["LEAF_LIGHT"]]), segs=6, rings=3, jitter=0.12)
    placed = 0
    while placed < 44:                                     # grass tufts, three blades each
        x, y = rng.uniform(-26, 26), rng.uniform(-27, 20)
        if near_path(x, y, 3.8) or not clear_of_landmarks(x, y, 0.5):
            continue
        for _ in range(3):
            h = rng.uniform(0.35, 0.7)
            beam(bm, (x + rng.uniform(-0.1, 0.1), y + rng.uniform(-0.1, 0.1), 0.0),
                 (x + rng.uniform(-0.2, 0.2), y + rng.uniform(-0.2, 0.2), h),
                 0.05, 0.0, C["GRASS_LIGHT"], segs=3)
        if placed % 3 == 0:
            blob(bm, (x, y, 0.62), (0.11, 0.11, 0.08),
                 C["FLOWER_WHITE"] if placed % 2 else C["FLOWER_PURPLE"], segs=5, rings=3)
        placed += 1
    placed = 0
    while placed < 22:                                     # loose rocks along both path edges
        px, py = rng.choice(PATH[:-1])
        side = rng.choice((-1, 1))
        x = px + side * rng.uniform(3.0, 5.0)
        y = py + rng.uniform(-2.0, 2.0)
        if near_path(x, y, 2.9) or not clear_of_landmarks(x, y, 0.3):
            continue
        s = rng.uniform(0.18, 0.45)
        blob(bm, (x, y, 0.05), (s, s * 0.9, s * 0.6), rng.choice([C["STONE"], C["STONE_LIGHT"], C["STONE_DARK"]]),
             segs=5, rings=3, jitter=0.18)
        placed += 1


# ============================ BUILD EVERYTHING ===============================
bm_pl, bm_pr, bm_lin = bmesh.new(), bmesh.new(), bmesh.new()
bm_pal, bm_glow, bm_braz = bmesh.new(), bmesh.new(), bmesh.new()
bm_path, bm_fol, bm_gnd = bmesh.new(), bmesh.new(), bmesh.new()

build_pillar(bm_pl, -7.4, [(-0.80, 1.2, 5.2, 0.0), (0.85, 1.2, 3.4, 2.0)])
build_pillar(bm_pr, 7.4, [(0.80, 1.2, 4.6, 1.0), (-0.85, 1.2, 3.0, 3.0)])
build_lintel(bm_lin)
build_palladium(bm_pal, bm_glow)
build_brazier(bm_braz)
for fx in (-5.2, 5.2):                                         # braziers' flames
    frustum(bm_glow, T((fx, -6.3, 2.1)), 0.38, 0.0, 0.95, C["GLOW"], segs=6)
build_path(bm_path)
build_foliage(bm_fol)
build_ground(bm_gnd)

objs = [
    finish("Entrance_PillarL", bm_pl),
    finish("Entrance_PillarR", bm_pr),
    finish("Entrance_Lintel", bm_lin),
    finish("Entrance_Palladium", bm_pal),
    finish("Entrance_Glow", bm_glow, trim=False),
    finish("Entrance_Path", bm_path),
    finish("Entrance_Foliage", bm_fol),
    finish("Entrance_Ground", bm_gnd, trim=False),
]
brazier_L = finish("Entrance_Brazier_L", bm_braz, location=(-5.2, -6.3, 0.0))
brazier_R = bpy.data.objects.new("Entrance_Brazier_R", brazier_L.data)   # shared mesh data
COL.objects.link(brazier_R)
brazier_R.location = (5.2 * STUD_SCALE, -6.3 * STUD_SCALE, 0.0)
objs += [brazier_L, brazier_R]


# ============================ REPORT =========================================
print("\n=== Camp DemiSoul entrance: game-ready report (units = studs) ===")
total = 0
for o in objs:
    tris = len(o.data.polygons)
    if o.name != "Entrance_Brazier_R":
        total += tris
    d = o.dimensions
    flag = "  <-- OVER BUDGET" if tris > TRI_WARN else ""
    print(f"{o.name:24s} {tris:6d} tris   {d.x:6.1f} x {d.y:6.1f} x {d.z:6.1f}{flag}")
print(f"{'TOTAL':24s} {total:6d} tris   (7 unique draw calls + 1 shared texture)")
print("Gate opening:", round(12 * STUD_SCALE), "studs wide | pillar height:", round(7.6 * STUD_SCALE), "studs")


# ============================ EXPORT =========================================
def export_fbx(path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                             add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE")


if EXPORT and OUT:
    try:
        fbx_path = os.path.join(OUT, "CampDemiSoul_Entrance.fbx")
        export_fbx(fbx_path)
        print("Exported:", fbx_path)
        print("Palette :", PNG_PATH)
    except Exception as exc:
        print("FBX export failed (the models are still in the scene):", exc)

# Show the palette in the viewport
try:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces[0].shading.type = "SOLID"
            area.spaces[0].shading.color_type = "TEXTURE"
except Exception:
    pass
