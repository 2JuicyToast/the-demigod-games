# =============================================================================
# CAMP DEMISOUL - DINING PAVILION (game-ready rebuild)
# Run in Blender's Scripting tab (Blender 3.6 / 4.x). Safe to re-run: it only
# replaces its own collection ("CampDiningPavilion_GameReady"). It does NOT touch
# your old "CampDiningPavilion" collection or the entrance - hide/delete the old
# one yourself once you're happy.
#
# Built with the exact same toolkit as the Entrance script (same primitives,
# same 8x8 palette layout, same STUD_SCALE, front of the camp faces -Y), so the
# two read as one world. The first 20 palette swatches are IDENTICAL to the
# entrance palette; this script just appends more, so one texture can serve both.
#
# LAYOUT (metres, pavilion centred on 0,0; main entry faces -Y like the gate)
#   - 16-column Ionic outer colonnade + 16 plain inner columns carry a stone ring
#     roof (radial beams -> architrave -> Greek-key frieze -> dentils -> corona).
#   - The roof ring is open to the sky in the middle around a great bronze hearth.
#   - 16 long banquet tables under the roof + 8 in the courtyard = ~300 seats.
#     Every table has real benches, aisles line up with the gaps in the colonnade.
#   - Kitchen & serving hall (pedimented, tiled roof) sits behind the ring (+Y).
#   - Forecourt with notice board, dinner bell, braziers and banner poles (-Y).
#
# MESHES (each is ONE mesh = ONE draw call in Roblox; tables/braziers are shared
# mesh data placed many times, exactly like the entrance braziers):
#   Pavilion_Floor  Pavilion_ColumnsOuter  Pavilion_ColumnsInner
#   Pavilion_Entablature  Pavilion_Banners  Pavilion_Hardware  Pavilion_Hearth
#   Pavilion_Glow (-> set Material = Neon in Studio)  Pavilion_Kitchen
#   Pavilion_Forecourt  Pavilion_Vines  Pavilion_Groundcover  Pavilion_Trees
#   Pavilion_Path  Pavilion_Ground  Pavilion_Brazier  Pavilion_Table_* (x4 shared)
# =============================================================================

import bpy, bmesh, math, os, random, struct, zlib
from mathutils import Vector, Matrix

# ------------------------------ SETTINGS -------------------------------------
STUD_SCALE = 3.0        # studs per modelled metre (same as the entrance)
EXPORT = True           # write palette PNG + FBX
EXPORT_DIR = ""         # blank = next to your .blend (or your home folder if unsaved)
COLLECTION_NAME = "CampDiningPavilion_GameReady"
TRI_WARN = 20000        # Roblox per-mesh limit to stay under
SEED = 27

TABLE_H = 0.95          # tabletop height (m). 0.78 = true scale, a little taller reads better in Roblox
BENCH_H = 0.55          # bench seat height (m)

# --------------------------- PALETTE (one texture) ---------------------------
PALETTE = [
    # ---- identical to the entrance palette (indices 0-19) ----
    ("STONE", "#9A927F"), ("STONE_LIGHT", "#C2B9A2"), ("STONE_DARK", "#5E5E56"), ("MARBLE", "#E8E1D0"),
    ("BRONZE", "#9C7A3C"), ("BRONZE_DARK", "#5A431F"), ("MAROON", "#5E1D2E"), ("CREAM", "#F1ECDF"),
    ("DIRT", "#9B7446"), ("DIRT_LIGHT", "#BE9A62"), ("GRASS", "#4A6B2E"), ("GRASS_LIGHT", "#6E8E3E"),
    ("LEAF_DARK", "#1F4A2E"), ("LEAF_MID", "#2F6B3F"), ("LEAF_LIGHT", "#58954F"), ("MOSS", "#62803A"),
    ("WOOD", "#5A3B22"), ("GLOW", "#FFC24A"), ("FLOWER_WHITE", "#E8D8A8"), ("FLOWER_PURPLE", "#7A55A8"),
    # ---- new for the pavilion ----
    ("WOOD_LIGHT", "#8A6238"), ("WOOD_DARK", "#3A2614"), ("IRON", "#3B3B3F"), ("CHARCOAL", "#242426"),
    ("TERRACOTTA", "#B5623E"), ("TILE_DARK", "#8A4630"), ("LINEN", "#CDBE98"), ("BREAD", "#C98A3E"),
    ("APPLE", "#A8322E"), ("GOLD_LEAF", "#D79A2B"), ("RUST_LEAF", "#B5532A"), ("BIRCH_BARK", "#E4E0D2"),
    ("BIRCH_MARK", "#3A3631"), ("FLOWER_RED", "#B03A48"), ("FLOWER_YELLOW", "#E2B93B"),
    ("BANNER_TEAL", "#2F7C86"), ("BANNER_GOLD", "#D6A02E"), ("BANNER_PURPLE", "#6A3F7A"),
    ("BANNER_BLUE", "#3A5A92"), ("BANNER_ORANGE", "#D0702A"), ("STONE_MOSSY", "#7C8466"),
    ("FLAME_ORANGE", "#FF7A1F"), ("WATER", "#5E8FA8"),
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
        d = os.path.join(base, "CampDemiSoul_Dining_Export")
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
# Same toolkit as the entrance: every primitive writes into a bmesh and tags its
# faces with a palette index; faces are oriented outward automatically.

def T(c):
    return Matrix.Translation(Vector(c))


ROT_X90 = Matrix.Rotation(math.pi / 2, 4, "X")     # local +Z -> world -Y
ROT_XN90 = Matrix.Rotation(-math.pi / 2, 4, "X")   # local +Z -> world +Y


def Rz(a):
    return Matrix.Rotation(a, 4, "Z")


def polar(r, a, z=0.0):
    return (r * math.cos(a), r * math.sin(a), z)


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
    """Low-poly lumpy sphere (foliage, rocks, sacks). rings=2 gives a flat diamond leaf."""
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
    """Flat annulus along local +Z (halo, trim rings, roof slabs)."""
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
    pts are (x, z) pairs. Used for emblems, banners, pennants, symbols."""
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


def sector(bm, r0, r1, a0, a1, z0, z1, color, bottom=False):
    """Annular block (paver, kerb) between radii r0..r1 and angles a0..a1. No bottom unless asked."""
    am, rm = (a0 + a1) / 2, (r0 + r1) / 2
    ref = Vector((rm * math.cos(am), rm * math.sin(am), (z0 + z1) / 2))

    def V(r, a, z):
        return bm.verts.new((r * math.cos(a), r * math.sin(a), z))

    b0, b1, b2, b3 = V(r0, a0, z0), V(r1, a0, z0), V(r1, a1, z0), V(r0, a1, z0)
    t0, t1, t2, t3 = V(r0, a0, z1), V(r1, a0, z1), V(r1, a1, z1), V(r0, a1, z1)
    add_face(bm, [t0, t1, t2, t3], ref, color)
    add_face(bm, [b0, t0, t3, b3], ref, color)
    add_face(bm, [b1, b2, t2, t1], ref, color)
    add_face(bm, [b0, b1, t1, t0], ref, color)
    add_face(bm, [b3, b2, t2, t3], ref, color)
    if bottom:
        add_face(bm, [b0, b1, b2, b3], ref, color)


def extrude(bm, pts, vec, color):
    """Convex polygon (3D points) pushed along vec. Used for roof planes."""
    P = [Vector(p) for p in pts]
    Q = [p + Vector(vec) for p in P]
    ref = sum(P + Q, Vector((0, 0, 0))) / (2 * len(P))
    top = [bm.verts.new(p) for p in P]
    bot = [bm.verts.new(q) for q in Q]
    add_face(bm, top, ref, color)
    add_face(bm, bot, ref, color)
    n = len(P)
    for i in range(n):
        j = (i + 1) % n
        add_face(bm, [top[i], top[j], bot[j], bot[i]], ref, color)


def merge(dst, src, M, free=True):
    """Copy a locally-built bmesh into dst through matrix M (rotation+translation only)."""
    mp = {}
    for v in src.verts:
        mp[v] = dst.verts.new(M @ v.co)
    for f in src.faces:
        try:
            nf = dst.faces.new([mp[v] for v in f.verts])
            nf.material_index = f.material_index
        except ValueError:
            pass
    if free:
        src.free()


def frame_in(a, r, z=0.0):
    """Local +Y points radially outward, local -Y (the 'front' of every prism) faces the centre."""
    return T(polar(r, a, z)) @ Rz(a - math.pi / 2)


def frame_out(a, r, z=0.0):
    """Local -Y (the 'front') faces radially outward, e.g. for facade decoration."""
    return T(polar(r, a, z)) @ Rz(a + math.pi / 2)


# Bull-head emblem (matches the flag and the entrance), drawn facing -Y.
HEAD = [(-0.40, 0.28), (0.40, 0.28), (0.46, 0.02), (0.26, -0.40), (0.0, -0.52), (-0.26, -0.40), (-0.46, 0.02)]
HORN = [(-0.28, 0.18), (-0.66, 0.06), (-0.98, 0.18), (-1.12, 0.48), (-1.06, 0.86), (-0.92, 1.04),
        (-0.86, 0.74), (-0.84, 0.50), (-0.64, 0.30), (-0.30, 0.34)]
EAR = [(-0.46, 0.02), (-0.90, 0.10), (-0.80, -0.10), (-0.46, -0.10)]
EYE = [(-0.34, 0.06), (-0.10, -0.02), (-0.10, 0.08), (-0.34, 0.14)]
MUZZLE = [(-0.18, -0.28), (0.18, -0.28), (0.15, -0.36), (-0.15, -0.36)]


def emblem(bm, c, sc, light, dark, t=0.08):
    fy = c[1] - t * 0.45
    for mx in (1, -1):
        prism(bm, HORN, c, sc, t, light, mx)
        prism(bm, EAR, c, sc, t, light, mx)
        prism(bm, EYE, (c[0], fy, c[2]), sc, t * 0.6, dark, mx)
    prism(bm, HEAD, c, sc, t, light)
    prism(bm, MUZZLE, (c[0], fy, c[2]), sc, t * 0.6, dark)


def symbol(bm, kind, c, s, color, t=0.05):
    """Small mythological device (cabin banners). Centre c, roughly s tall, faces -Y."""
    col = C[color]

    def P(pts, mx=1):
        prism(bm, pts, c, s, t, col, mx)

    if kind == "BOLT":
        P([(-0.05, 0.50), (0.17, 0.50), (0.04, 0.10), (0.17, 0.10), (-0.14, -0.50), (-0.03, -0.04), (-0.17, -0.04)])
    elif kind == "TRIDENT":
        P([(-0.03, -0.50), (0.03, -0.50), (0.03, 0.38), (-0.03, 0.38)])
        P([(-0.21, 0.04), (0.21, 0.04), (0.21, 0.10), (-0.21, 0.10)])
        for mx in (1, -1):
            P([(0.17, 0.04), (0.23, 0.04), (0.23, 0.40), (0.20, 0.50), (0.17, 0.40)], mx)
        P([(-0.03, 0.36), (0.03, 0.36), (0.03, 0.42), (0.0, 0.54), (-0.03, 0.42)])
    elif kind == "SUN":
        P([(0.17 * math.cos(math.tau * i / 8), 0.17 * math.sin(math.tau * i / 8)) for i in range(8)])
        for i in range(8):
            an = math.tau * i / 8
            P([(0.22 * math.cos(an - 0.2), 0.22 * math.sin(an - 0.2)),
               (0.22 * math.cos(an + 0.2), 0.22 * math.sin(an + 0.2)),
               (0.46 * math.cos(an), 0.46 * math.sin(an))])
    elif kind == "CRESCENT":
        outer = [(0.40 * math.cos(math.radians(60 + 240 * k / 12)), 0.40 * math.sin(math.radians(60 + 240 * k / 12)))
                 for k in range(13)]
        inner = [(0.16 + 0.33 * math.cos(math.radians(290 - 220 * k / 12)),
                  0.33 * math.sin(math.radians(290 - 220 * k / 12))) for k in range(13)]
        P(outer + inner)
    elif kind == "LAUREL":
        for i in range(10):
            an = math.tau * i / 10
            cx, cz = 0.32 * math.cos(an), 0.32 * math.sin(an)
            tx, tz = -math.sin(an), math.cos(an)
            nx, nz = math.cos(an), math.sin(an)
            P([(cx - tx * 0.11, cz - tz * 0.11), (cx + nx * 0.05, cz + nz * 0.05),
               (cx + tx * 0.11, cz + tz * 0.11), (cx - nx * 0.05, cz - nz * 0.05)])
        P([(-0.05, -0.10), (0.05, -0.10), (0.05, 0.10), (-0.05, 0.10)])


# Angular stroke lettering (echoes the flag and the entrance sign).
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
    "T": (0.70, [[(0.0, 1.0), (0.70, 1.0)], [(0.35, 1.0), (0.35, 0.0)]]),
    "R": (0.65, [[(0.0, 0.0), (0.0, 1.0)], [(0.0, 1.0), (0.62, 0.78), (0.0, 0.52)], [(0.22, 0.55), (0.65, 0.0)]]),
    "Z": (0.65, [[(0.0, 1.0), (0.65, 1.0), (0.0, 0.0), (0.65, 0.0)]]),
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
def finish(name, bm, trim=True, location=None, rotation=None):
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
    if rotation:
        obj.rotation_euler = (0.0, 0.0, rotation)
    return obj


def instance(src, name, location, rotation=0.0):
    """Another placement of an existing mesh (shared data = one MeshPart asset in Roblox)."""
    obj = bpy.data.objects.new(name, src.data)
    COL.objects.link(obj)
    obj.location = tuple(v * STUD_SCALE for v in location)
    obj.rotation_euler = (0.0, 0.0, rotation)
    return obj


# ------------------------------ LAYOUT CONSTANTS -----------------------------
FZ = 0.60                       # finished floor height
R_COL_IN, R_COL_OUT = 11.2, 18.0
N_COL = 16
COL_ANG = [math.tau * (i + 0.5) / N_COL for i in range(N_COL)]   # columns; the GAPS (aisles/exits) sit at i*22.5 deg
STEP = math.tau / N_COL
Z0 = FZ + 7.6                   # underside of the roof beams (top of every capital)
FRONT = 1.5 * math.pi           # -Y, the main entry

ARCH_IN, ARCH_OUT = 10.6, 18.6
FR_IN, FR_OUT = 10.5, 18.7
Z_ARCH0, Z_FRIEZE0, Z_CORONA0 = Z0 + 0.45, Z0 + 1.15, Z0 + 1.80
Z_SLAB0, Z_TOP = Z0 + 2.10, Z0 + 2.60
Z_FRIEZE_C = Z_FRIEZE0 + 0.325
RING_SEGS = 96

RING_A_R, RING_B_R = 14.6, 7.3          # table rings
HEARTH_Z = 0.98                         # top of the hearth dais

KX0, KX1 = -9.0, 9.0                    # kitchen post lines
KY0, KY1 = 22.7, 30.2
KZT, KZR = FZ + 4.4, FZ + 7.0           # kitchen eave / ridge heights


def angle_dist(a, b):
    return abs(((a - b + math.pi) % math.tau) - math.pi)


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


MAIN_PTS = [(5, -78), (-3, -64), (1.5, -50), (-1.5, -39), (0.5, -32), (0, -28.5)]
SERVICE_PTS = [(52, 31), (38, 30), (26, 28.5), (17, 27.4), (11.4, 26.6)]
PATHS = [catmull(MAIN_PTS, 6), catmull(SERVICE_PTS, 6)]


def near_path(x, y, m):
    return any((x - px) ** 2 + (y - py) ** 2 < m * m for pth in PATHS for px, py in pth)


def clear_of_landmarks(x, y, pad=0.0):
    if x * x + y * y < (24.5 + pad) ** 2:                          # platform
        return False
    if abs(x) < 11.5 + pad and -31 - pad < y < -21.5 + pad:         # forecourt
        return False
    if abs(x) < 12.5 + pad and 18.5 - pad < y < 33.5 + pad:         # kitchen
        return False
    return True


# ============================ 1) COLUMNS =====================================
def column_ionic():
    """Fluted Ionic column, local frame: +Y radial outward, z up from the floor."""
    b = bmesh.new()
    box(b, (0, 0, 0.20), (1.62, 1.62, 0.40), C["STONE_DARK"], ch=0.07)               # plinth
    frustum(b, T((0, 0, 0.40)), 0.74, 0.68, 0.20, C["STONE_LIGHT"], segs=12)         # lower torus
    frustum(b, T((0, 0, 0.60)), 0.62, 0.58, 0.14, C["STONE"], segs=12)               # upper torus
    frustum(b, T((0, 0, 0.74)), 0.52, 0.43, 5.92, C["STONE_LIGHT"], segs=12)         # shaft
    frustum(b, T((0, 0, 0.76)), 0.527, 0.509, 1.0, C["STONE"], segs=12)              # grime band
    for j in range(12):                                                              # fluting
        an = math.tau * (j + 0.5) / 12
        r0, r1 = 0.52 * 0.972, 0.43 * 0.972
        beam(b, (r0 * math.cos(an), r0 * math.sin(an), 0.80),
             (r1 * math.cos(an), r1 * math.sin(an), 6.58), 0.032, 0.030, C["STONE_DARK"], segs=3)
    frustum(b, T((0, 0, 6.66)), 0.45, 0.45, 0.08, C["STONE_DARK"], segs=12)          # necking
    frustum(b, T((0, 0, 6.74)), 0.46, 0.64, 0.20, C["STONE_LIGHT"], segs=12)         # echinus
    box(b, (0, 0, 7.14), (1.22, 0.78, 0.34), C["STONE"], ch=0.05)                    # bolster
    for sx in (-1, 1):                                                               # volutes
        for sy in (-1, 1):
            Mv = ROT_XN90 if sy > 0 else ROT_X90
            frustum(b, T((sx * 0.58, sy * 0.36, 7.14)) @ Mv, 0.21, 0.21, 0.15, C["STONE_LIGHT"], segs=12)
            frustum(b, T((sx * 0.58, sy * 0.49, 7.14)) @ Mv, 0.09, 0.09, 0.06, C["STONE_DARK"], segs=8)
    box(b, (0, 0, 7.47), (1.62, 1.62, 0.26), C["STONE_LIGHT"], ch=0.05)              # abacus
    return b


def column_plain():
    """Slimmer inner column with a plain Tuscan capital."""
    b = bmesh.new()
    box(b, (0, 0, 0.17), (1.2, 1.2, 0.34), C["STONE_DARK"], ch=0.06)
    frustum(b, T((0, 0, 0.34)), 0.52, 0.46, 0.18, C["STONE_LIGHT"], segs=10)
    frustum(b, T((0, 0, 0.52)), 0.40, 0.31, 6.78, C["STONE_LIGHT"], segs=10)
    frustum(b, T((0, 0, 0.54)), 0.406, 0.392, 0.9, C["STONE"], segs=10)
    for j in range(10):
        an = math.tau * (j + 0.5) / 10
        r0, r1 = 0.40 * 0.965, 0.31 * 0.965
        beam(b, (r0 * math.cos(an), r0 * math.sin(an), 0.60),
             (r1 * math.cos(an), r1 * math.sin(an), 7.22), 0.026, 0.024, C["STONE_DARK"], segs=3)
    frustum(b, T((0, 0, 7.02)), 0.332, 0.332, 0.07, C["BRONZE"], segs=10)            # bronze collar
    frustum(b, T((0, 0, 7.30)), 0.34, 0.50, 0.12, C["STONE"], segs=10)
    box(b, (0, 0, 7.51), (1.14, 1.14, 0.18), C["STONE_LIGHT"], ch=0.04)
    return b


# ============================ 2) ENTABLATURE / ROOF ==========================
def key_unit():
    b = bmesh.new()
    H, t, z = 0.34, 0.07, Z_FRIEZE_C
    box(b, (-0.30, -0.025, z), (t, 0.05, H - 0.06), C["STONE_DARK"])
    box(b, (-0.08, -0.025, z + 0.07), (0.44, 0.05, t), C["STONE_DARK"])
    box(b, (0.14, -0.025, z - 0.02), (t, 0.05, 0.20), C["STONE_DARK"])
    box(b, (0.00, -0.025, z - 0.10), (0.30, 0.05, t), C["STONE_DARK"])
    return b


def build_entablature(bm):
    span = R_COL_OUT - R_COL_IN
    for a in COL_ANG:                                               # radial stone beams tie both colonnades
        box(bm, polar((R_COL_IN + R_COL_OUT) / 2, a, Z0 + 0.225), (0.85, span + 1.5, 0.45),
            C["STONE_LIGHT"], rot=a - math.pi / 2, ch=0.05)
    ring(bm, T((0, 0, Z_ARCH0)), ARCH_OUT, ARCH_IN, 0.70, C["STONE"], RING_SEGS)             # architrave
    ring(bm, T((0, 0, Z_FRIEZE0)), FR_OUT, FR_IN, 0.65, C["STONE_LIGHT"], RING_SEGS)         # frieze
    ring(bm, T((0, 0, Z_CORONA0)), 19.3, 10.4, 0.30, C["STONE_LIGHT"], RING_SEGS)            # corona
    ring(bm, T((0, 0, Z_SLAB0)), 19.15, 10.3, 0.50, C["STONE"], RING_SEGS)                   # roof slab
    ring(bm, T((0, 0, Z_TOP)), 19.15, 18.75, 0.26, C["STONE_LIGHT"], RING_SEGS)              # outer crown
    ring(bm, T((0, 0, Z_TOP)), 10.75, 10.30, 0.20, C["STONE_LIGHT"], RING_SEGS)              # inner crown

    for i in range(96):                                             # dentils under the corona
        a = math.tau * (i + 0.5) / 96
        box(bm, polar(18.82, a, 9.90), (0.24, 0.22, 0.20), C["STONE"], rot=a - math.pi / 2)

    zf = Z_FRIEZE_C                                                 # Greek-key frieze + bronze rails
    ring(bm, T((0, 0, zf + 0.17)), FR_OUT + 0.04, FR_OUT - 0.01, 0.04, C["BRONZE"], RING_SEGS)
    ring(bm, T((0, 0, zf - 0.21)), FR_OUT + 0.04, FR_OUT - 0.01, 0.04, C["BRONZE"], RING_SEGS)
    unit = key_unit()
    n = int(math.tau * FR_OUT / 1.15)
    for i in range(n):
        a = math.tau * (i + 0.5) / n
        if angle_dist(a, FRONT) * FR_OUT < 3.0:
            continue                                                # leave room for the sign
        merge(bm, unit, frame_out(a, FR_OUT, 0.0), free=False)
    unit.free()

    fy = -FR_OUT                                                    # entry sign, same style as the gate lintel
    box(bm, (0, fy - 0.04, zf), (4.4, 0.26, 0.60), C["STONE_LIGHT"], ch=0.03)
    for dz in (-0.33, 0.33):
        box(bm, (0, fy - 0.15, zf + dz), (4.6, 0.10, 0.06), C["BRONZE"])
    for sx in (-1, 1):
        box(bm, (sx * 2.25, fy - 0.15, zf), (0.07, 0.10, 0.72), C["BRONZE"])
    text(bm, "TRAPEZA", (0, fy - 0.19, zf), 0.38, C["BRONZE_DARK"], depth=0.06, stroke=0.20)

    zc = Z_TOP + 0.26                                               # finials above every column
    for a in COL_ANG:
        box(bm, polar(18.95, a, zc + 0.11), (0.36, 0.36, 0.22), C["STONE_LIGHT"], rot=a, ch=0.03)
        frustum(bm, T(polar(18.95, a, zc + 0.22)), 0.17, 0.0, 0.62, C["BRONZE"], segs=6)
    box(bm, (0, -18.95, zc + 0.30), (3.0, 1.0, 0.60), C["STONE_LIGHT"], ch=0.06)           # bull crest, as on the gate
    Y0, ZR = -18.75, zc + 0.60 + 1.45
    frustum(bm, T((0, Y0, ZR)) @ ROT_X90, 1.43, 1.43, 0.30, C["BRONZE"], segs=20)
    frustum(bm, T((0, Y0, ZR)) @ ROT_X90, 1.28, 1.28, 0.40, C["MAROON"], segs=20)
    emblem(bm, (0, Y0 - 0.45, ZR - 0.05), 0.78, C["CREAM"], C["MAROON"], t=0.10)

    for _ in range(46):                                             # rain streaks under the corona
        a = rng.uniform(0, math.tau)
        if angle_dist(a, FRONT) * FR_OUT < 3.0:
            continue
        h = rng.uniform(0.25, 0.60)
        box(bm, polar(FR_OUT + 0.005, a, Z_CORONA0 - h / 2), (rng.uniform(0.08, 0.20), 0.025, h),
            C["STONE_DARK"], rot=a - math.pi / 2)
    for _ in range(26):                                             # moss on the roof top
        a = rng.uniform(0, math.tau)
        box(bm, polar(rng.uniform(13.0, 18.5), a, Z_SLAB0 + 0.5 + 0.012),
            (rng.uniform(0.8, 2.2), rng.uniform(0.4, 1.2), 0.025), C["MOSS"], rot=a - math.pi / 2)


# ============================ 3) BANNERS =====================================
def banner_local(b, w, h, cloth, kind, symcol="CREAM", stand=0.25):
    """Swallow-tail banner hanging from a bronze rod. Local: front faces -Y, rod at z=0, +Y = toward the wall."""
    prism(b, [(-w / 2, 0), (w / 2, 0), (w / 2, -h), (0, -h * 0.82), (-w / 2, -h)], (0, 0, 0), 1.0, 0.06, C[cloth])
    prism(b, [(-w / 2 + 0.06, -0.10), (w / 2 - 0.06, -0.10), (w / 2 - 0.06, -0.17), (-w / 2 + 0.06, -0.17)],
          (0, -0.04, 0), 1.0, 0.02, C["CREAM"])
    box(b, (0, 0, 0.05), (w + 0.36, 0.10, 0.08), C["BRONZE"])
    for sx in (-1, 1):
        blob(b, (sx * (w / 2 + 0.20), 0, 0.05), (0.09, 0.09, 0.09), C["BRONZE"], segs=6, rings=3)
        box(b, (sx * (w / 2 - 0.10), stand / 2 + 0.03, 0.05), (0.07, stand + 0.06, 0.07), C["BRONZE_DARK"])
    zc = -h * 0.42
    if kind == "BULL":
        emblem(b, (0, -0.055, zc), 0.36 * w / 1.1, C["CREAM"], C["MAROON"], t=0.05)
    elif kind:
        symbol(b, kind, (0, -0.055, zc), w * 0.95, symcol, t=0.05)


CABIN = [("BANNER_TEAL", "TRIDENT"), ("BANNER_GOLD", "SUN"), ("BANNER_PURPLE", "BOLT"), ("BANNER_BLUE", "CRESCENT"),
         ("MAROON", "BULL"), ("BANNER_ORANGE", "LAUREL"), ("BANNER_TEAL", "LAUREL"), ("BANNER_GOLD", "BOLT")]
PENNANT = ["MAROON", "CREAM", "BANNER_GOLD", "BANNER_TEAL", "MAROON", "CREAM", "BANNER_PURPLE", "BANNER_ORANGE"]


def swag_local(b, hw, sag, n=8):
    pts = []
    for k in range(13):
        x = -hw + 2 * hw * k / 12
        pts.append((x, 0.0, -sag * (1 - (x / hw) ** 2)))
    for p, q in zip(pts[:-1], pts[1:]):
        beam(b, p, q, 0.016, 0.016, C["LINEN"], segs=3)
    for i in range(n):
        x = -hw + 2 * hw * (i + 0.5) / n
        z = -sag * (1 - (x / hw) ** 2)
        prism(b, [(-0.17, 0), (0.17, 0), (0, -0.46)], (x, 0, z - 0.02), 1.0, 0.025, C[PENNANT[i % len(PENNANT)]])


def build_banners(bm):
    zt = FZ + 6.55
    for i, a in enumerate(COL_ANG):
        cloth, kind = CABIN[i % len(CABIN)]          # cabin banners on the inner columns, facing the courtyard
        b = bmesh.new()
        banner_local(b, 1.0, 2.5, cloth, kind, "MAROON" if cloth == "BANNER_GOLD" else "CREAM", stand=0.30)
        merge(bm, b, frame_in(a, R_COL_IN - 0.62, zt))
        b = bmesh.new()                              # camp maroon + bull on the outer columns, facing the tables
        banner_local(b, 1.15, 2.8, "MAROON", "BULL", stand=0.25)
        merge(bm, b, frame_in(a, R_COL_OUT - 0.66, zt))
        if i % 2 == 0:                               # and some facing the world outside
            b = bmesh.new()
            banner_local(b, 1.15, 2.8, "MAROON", "BULL", stand=0.25)
            merge(bm, b, frame_out(a, R_COL_OUT + 0.66, zt))
    step = STEP
    for i in range(N_COL):                           # pennant swags between the outer columns
        a1 = COL_ANG[i]
        am = a1 + step / 2
        hw = R_COL_OUT * math.sin(step / 2) - 0.42
        b = bmesh.new()
        swag_local(b, hw, 0.7)
        merge(bm, b, frame_in(am, R_COL_OUT * math.cos(step / 2), FZ + 6.4))


# ============================ 4) HARDWARE, LANTERNS, TORCHES =================
def shield_local(b):
    frustum(b, ROT_X90, 0.50, 0.50, 0.12, C["BRONZE"], segs=16)
    frustum(b, T((0, -0.12, 0)) @ ROT_X90, 0.42, 0.42, 0.04, C["MAROON"], segs=16)
    ring(b, T((0, -0.16, 0)) @ ROT_X90, 0.50, 0.42, 0.04, C["BRONZE_DARK"], segs=16)
    emblem(b, (0, -0.185, 0), 0.30, C["CREAM"], C["MAROON"], t=0.05)


def bracket_local(b, g):
    box(b, (0, 0, 0), (0.18, 0.10, 0.46), C["BRONZE_DARK"], ch=0.02)
    beam(b, (0, 0, 0), (0, -0.55, 0.18), 0.04, 0.035, C["BRONZE"], segs=6)
    beam(b, (0, -0.02, -0.22), (0, -0.45, 0.06), 0.03, 0.03, C["BRONZE"], segs=5)
    frustum(b, T((0, -0.55, 0.16)), 0.10, 0.17, 0.16, C["BRONZE"], segs=8)
    frustum(g, T((0, -0.55, 0.32)), 0.14, 0.0, 0.55, C["FLAME_ORANGE"], segs=6)
    frustum(g, T((0, -0.55, 0.32)), 0.07, 0.0, 0.34, C["GLOW"], segs=5)


def lantern_local(b, g):
    """Hanging bronze lantern, local origin = hanging point (top)."""
    frustum(b, T((0, 0, -0.70)), 0.20, 0.22, 0.06, C["BRONZE_DARK"], segs=8)
    for sx in (-1, 1):
        for sy in (-1, 1):
            beam(b, (sx * 0.16, sy * 0.16, -0.64), (sx * 0.14, sy * 0.14, -0.14), 0.018, 0.018, C["BRONZE"], segs=4)
    frustum(b, T((0, 0, -0.16)), 0.27, 0.05, 0.16, C["BRONZE"], segs=8)
    blob(b, (0, 0, -0.02), (0.06, 0.06, 0.06), C["BRONZE"], segs=6, rings=3)
    box(g, (0, 0, -0.40), (0.20, 0.20, 0.34), C["GLOW"])


def build_hardware(bm, g):
    for a in COL_ANG:
        b = bmesh.new()
        shield_local(b)
        merge(bm, b, frame_in(a, FR_IN, Z_FRIEZE_C))                 # shield on the inner frieze, facing the courtyard
        b, gb = bmesh.new(), bmesh.new()
        bracket_local(b, gb)
        M = frame_in(a, R_COL_IN - 0.36, FZ + 3.0)                   # torch holder on every inner column
        merge(bm, b, M)
        merge(g, gb, M)
        x, y, _ = polar(RING_A_R, a)                                 # lantern over every long table
        beam(bm, (x, y, Z0), (x, y, Z0 - 1.3), 0.03, 0.03, C["IRON"], segs=4)
        b, gb = bmesh.new(), bmesh.new()
        lantern_local(b, gb)
        M = T((x, y, Z0 - 1.3))
        merge(bm, b, M)
        merge(g, gb, M)


# ============================ 5) HEARTH ======================================
def build_hearth(bm, g):
    zb = HEARTH_Z
    frustum(bm, T((0, 0, zb)), 1.15, 0.95, 0.30, C["BRONZE_DARK"], segs=10)
    for i in range(6):
        an = math.tau * i / 6 + 0.3
        beam(bm, (1.7 * math.cos(an), 1.7 * math.sin(an), zb), (0.85 * math.cos(an), 0.85 * math.sin(an), zb + 1.1),
             0.11, 0.09, C["IRON"], segs=6)
    frustum(bm, T((0, 0, zb + 0.30)), 0.95, 0.80, 0.78, C["BRONZE_DARK"], segs=10)
    frustum(bm, T((0, 0, zb + 1.05)), 0.85, 2.10, 0.95, C["BRONZE_DARK"], segs=14)           # the great bowl
    frustum(bm, T((0, 0, zb + 1.52)), 1.52, 1.58, 0.07, C["BRONZE"], segs=14)
    ring(bm, T((0, 0, zb + 1.95)), 2.25, 2.02, 0.12, C["BRONZE"], segs=14)
    for sx in (-1, 1):                                                                       # carrying handles
        beam(bm, (sx * 2.15, 0, zb + 1.95), (sx * 2.65, 0, zb + 1.55), 0.07, 0.07, C["BRONZE"], segs=6)
        blob(bm, (sx * 2.7, 0, zb + 1.5), (0.14, 0.14, 0.14), C["BRONZE"], segs=6, rings=3)
    for i in range(3):
        box(bm, (0, 0, zb + 2.12), (2.2, 0.22, 0.20), C["CHARCOAL"], rot=0.5 + i * math.pi / 3, ch=0.04)
    frustum(g, T((0, 0, zb + 2.01)), 1.80, 1.80, 0.04, C["FLAME_ORANGE"], segs=14)           # embers
    for x, y, r, h in [(0, 0, 0.60, 2.4), (-0.7, 0.2, 0.42, 1.7), (0.6, -0.3, 0.44, 1.8), (0.2, 0.75, 0.36, 1.4),
                       (-0.3, -0.75, 0.36, 1.3), (1.1, 0.4, 0.30, 1.0), (-1.1, -0.3, 0.30, 0.95)]:
        frustum(g, T((x, y, zb + 2.1)), r, 0.0, h, C["FLAME_ORANGE"], segs=6)
        frustum(g, T((x, y, zb + 2.1)), r * 0.5, 0.0, h * 0.65, C["GLOW"], segs=5)


# ============================ 6) FLOOR =======================================
def build_floor(bm):
    frustum(bm, T((0, 0, 0)), 23.4, 23.2, 0.20, C["STONE_DARK"], segs=72)
    frustum(bm, T((0, 0, 0.20)), 22.9, 22.7, 0.20, C["STONE"], segs=72)
    frustum(bm, T((0, 0, 0.40)), 22.4, 22.3, 0.16, C["STONE_LIGHT"], segs=72)
    for i in range(96):                                              # kerb, broken by the front steps and the kitchen
        a0, a1 = math.tau * i / 96, math.tau * (i + 1) / 96
        am = (a0 + a1) / 2
        if angle_dist(am, FRONT) < 0.30 or angle_dist(am, math.pi / 2) < 0.40:
            continue
        sector(bm, 21.8, 22.4, a0, a1, 0.56, 0.62, C["STONE_LIGHT"] if i % 3 else C["STONE"])
    rings_n, r_start, r_end = 12, 4.5, 21.7                          # flagstones in concentric courses
    rw = (r_end - r_start) / rings_n
    for k in range(rings_n):
        r0 = r_start + k * rw + 0.02
        r1 = r0 + rw - 0.04
        rm = (r0 + r1) / 2
        n = max(8, round(math.tau * rm / 2.3))
        off = rng.uniform(0, math.tau)
        g = 0.025 / rm
        for j in range(n):
            a0 = off + math.tau * j / n + g
            a1 = off + math.tau * (j + 1) / n - g
            am = (a0 + a1) / 2
            axis = min(angle_dist(am, ang) for ang in (0, math.pi / 2, math.pi, 1.5 * math.pi))
            if axis < 0.5 / rm:
                col = C["STONE_LIGHT"]                                # worn light paving along the four aisles
            else:
                q = rng.random()
                col = (C["STONE"] if q < 0.55 else C["STONE_LIGHT"] if q < 0.78 else
                       C["STONE_DARK"] if q < 0.93 else C["STONE_MOSSY"])
            sector(bm, r0, r1, a0, a1, 0.56, FZ + rng.uniform(-0.012, 0.006), col)
    frustum(bm, T((0, 0, 0.56)), 4.3, 4.1, 0.20, C["STONE_DARK"], segs=24)       # hearth dais
    frustum(bm, T((0, 0, 0.76)), 3.8, 3.6, 0.20, C["STONE_LIGHT"], segs=24)
    ring(bm, T((0, 0, 0.96)), 3.1, 2.95, 0.02, C["BRONZE"], segs=24)
    for i in range(8):                                                           # bronze studs round the dais
        an = math.tau * i / 8
        frustum(bm, T(polar(3.45, an, 0.96)), 0.12, 0.10, 0.03, C["BRONZE"], segs=6)


# ============================ 7) TABLES (shared meshes) ======================
def build_table(L, variant):
    """One long banquet table with benches; local X along the table, z=0 on the floor."""
    b = bmesh.new()
    W, ts = 1.25, 0.14
    box(b, (0, 0, TABLE_H - ts / 2), (L, W, ts), C["STONE_LIGHT"], ch=0.045)                      # slab
    box(b, (0, 0, TABLE_H + 0.006), (L - 0.7, 0.36, 0.012), C["MAROON"])                          # cloth runner
    box(b, (0, 0, TABLE_H + 0.008), (L - 0.7, 0.04, 0.012), C["BRONZE"])
    for sx in (-1, 1):
        x = sx * (L / 2 - 0.62)
        box(b, (x, 0, (TABLE_H - ts) / 2), (0.26, W * 0.78, TABLE_H - ts), C["STONE"], ch=0.03)    # carved end slabs
        box(b, (x, 0, 0.07), (0.40, W * 0.92, 0.14), C["STONE_DARK"], ch=0.03)
        box(b, (x, 0, TABLE_H - ts - 0.06), (0.34, W * 0.84, 0.12), C["STONE_LIGHT"], ch=0.03)
    box(b, (0, 0, 0.34), (L - 1.4, 0.14, 0.12), C["STONE"], ch=0.02)                              # stretcher
    for _ in range(2):                                                                            # worn patches
        box(b, (rng.uniform(-L / 2 + 0.6, L / 2 - 0.6), rng.uniform(-0.45, 0.45), TABLE_H + 0.003),
            (rng.uniform(0.3, 0.6), rng.uniform(0.2, 0.4), 0.004), C["STONE"])
    bd = 0.42
    for sy in (-1, 1):                                                                            # benches
        yb = sy * (W / 2 + 0.14 + bd / 2)
        for sx in (-1, 1):
            box(b, (sx * (L / 2 - 0.6), yb, (BENCH_H - 0.08) / 2), (0.28, bd * 0.9, BENCH_H - 0.08), C["STONE"], ch=0.03)
        box(b, (0, yb, BENCH_H - 0.04), (L - 0.15, bd, 0.08), C["WOOD_LIGHT"], ch=0.02)
        box(b, (0, yb, BENCH_H - 0.14), (L - 1.3, 0.10, 0.10), C["WOOD"])
    n = int((L - 0.5) / 0.62)
    xs = [(-(n - 1) / 2 + i) * 0.62 for i in range(n)]
    zt = TABLE_H + 0.012
    for sy in (-1, 1):                                                                            # place settings
        for i, x in enumerate(xs):
            if variant == "B" and (i * 7 + (sy > 0) * 3) % 5 in (0, 3):
                continue
            frustum(b, T((x, sy * 0.33, zt)), 0.17, 0.15, 0.025, C["CREAM"], segs=8)
            if variant == "A" and i % 3 == 0:
                blob(b, (x, sy * 0.33, zt + 0.045), (0.08, 0.07, 0.04), C["BREAD"], segs=6, rings=3)
            frustum(b, T((x + 0.2, sy * 0.58, zt)), 0.045, 0.06, 0.11, C["BRONZE"], segs=6)
    for sx in (-1, 1):                                                                            # platters + jugs
        x = sx * L * 0.22
        frustum(b, T((x, 0, zt + 0.006)), 0.30, 0.27, 0.03, C["BRONZE_DARK"], segs=10)
        if variant == "A":
            for k in range(3):
                an = k * 2.1 + sx
                blob(b, (x + 0.11 * math.cos(an), 0.11 * math.sin(an), zt + 0.08), (0.07, 0.07, 0.06),
                     C["APPLE"] if k else C["BREAD"], segs=6, rings=3)
        frustum(b, T((sx * L * 0.06, 0.12, zt + 0.006)), 0.09, 0.07, 0.26, C["TERRACOTTA"], segs=8)
        frustum(b, T((sx * L * 0.06, 0.12, zt + 0.266)), 0.07, 0.05, 0.07, C["TERRACOTTA"], segs=8)
    return b


# ============================ 8) BRAZIER (shared mesh) =======================
def build_brazier(bm):
    frustum(bm, T((0, 0, 0)), 0.50, 0.40, 0.30, C["STONE_DARK"], segs=8)
    frustum(bm, T((0, 0, 0.30)), 0.20, 0.14, 1.30, C["BRONZE_DARK"], segs=8)
    frustum(bm, T((0, 0, 1.60)), 0.16, 0.55, 0.50, C["BRONZE"], segs=8)
    ring(bm, T((0, 0, 2.05)), 0.57, 0.50, 0.06, C["BRONZE"], segs=8)


# ============================ 9) PROPS (crates, barrels, ...) ================
def crate(bm, x, y, z, s=0.7, rot=0.0):
    box(bm, (x, y, z + s / 2), (s, s, s), C["WOOD"], rot=rot)
    for dz in (0.04, s - 0.04):
        box(bm, (x, y, z + dz), (s + 0.025, s + 0.025, 0.07), C["WOOD_DARK"], rot=rot)
    for k in (-1, 1):
        box(bm, (x + k * s * 0.5 * math.cos(rot), y + k * s * 0.5 * math.sin(rot), z + s / 2),
            (0.07, s + 0.025, s + 0.01), C["WOOD_DARK"], rot=rot)


def barrel(bm, x, y, z, s=1.0, col="WOOD"):
    frustum(bm, T((x, y, z)), 0.34 * s, 0.40 * s, 0.45 * s, C[col], segs=10)
    frustum(bm, T((x, y, z + 0.45 * s)), 0.40 * s, 0.34 * s, 0.45 * s, C[col], segs=10)
    for h in (0.20, 0.70):
        r = (0.34 + 0.06 * (h / 0.45)) if h < 0.45 else (0.40 - 0.06 * ((h - 0.45) / 0.45))
        frustum(bm, T((x, y, z + (h - 0.03) * s)), (r + 0.012) * s, (r + 0.012) * s, 0.06 * s, C["IRON"], segs=10)


def sack(bm, x, y, z, s=1.0):
    blob(bm, (x, y, z + 0.26 * s), (0.30 * s, 0.24 * s, 0.28 * s), C["LINEN"], segs=7, rings=4, jitter=0.06)
    blob(bm, (x, y, z + 0.54 * s), (0.10 * s, 0.10 * s, 0.07 * s), C["LINEN"], segs=5, rings=3)


def amphora(bm, x, y, z, s=1.0, col="TERRACOTTA"):
    frustum(bm, T((x, y, z)), 0.08 * s, 0.22 * s, 0.18 * s, C[col], segs=8)
    frustum(bm, T((x, y, z + 0.18 * s)), 0.22 * s, 0.14 * s, 0.22 * s, C[col], segs=8)
    frustum(bm, T((x, y, z + 0.40 * s)), 0.14 * s, 0.09 * s, 0.12 * s, C[col], segs=8)
    frustum(bm, T((x, y, z + 0.52 * s)), 0.11 * s, 0.11 * s, 0.04 * s, C["TILE_DARK"], segs=8)


def log_stack(bm, x, y, z, rows=3, length=1.4, along_x=True):
    for r in range(rows):
        for k in range(rows - r):
            off = (k - (rows - r - 1) / 2) * 0.27
            zz = z + 0.14 + r * 0.24
            if along_x:
                beam(bm, (x - length / 2, y + off, zz), (x + length / 2, y + off, zz), 0.13, 0.13, C["WOOD"], segs=6)
            else:
                beam(bm, (x + off, y - length / 2, zz), (x + off, y + length / 2, zz), 0.13, 0.13, C["WOOD"], segs=6)


def bench_local(b, L=2.2):
    for sx in (-1, 1):
        box(b, (sx * (L / 2 - 0.3), 0, 0.2), (0.28, 0.40, 0.40), C["STONE"], ch=0.03)
    box(b, (0, 0, 0.44), (L, 0.44, 0.08), C["WOOD_LIGHT"], ch=0.02)


# ============================ 10) KITCHEN & SERVING HALL =====================
def build_kitchen(bm, g):
    # terrace
    box(bm, (0, 25.8, 0.14), (22.4, 13.4, 0.28), C["STONE_DARK"], ch=0.06)
    box(bm, (0, 25.8, 0.28), (21.0, 12.0, 0.56), C["STONE"], ch=0.06)
    for ix in range(-5, 6):
        for iy in range(5):
            q = rng.random()
            box(bm, (ix * 1.8, 23.0 + iy * 1.75, 0.58), (1.72, 1.68, 0.04),
                C["STONE"] if q < 0.6 else C["STONE_LIGHT"] if q < 0.85 else C["STONE_DARK"])
    # posts, plates, rafters
    post_pts = [(x, KY0) for x in (-9.0, -3.0, 3.0, 9.0)] + [(x, KY1) for x in (-9.0, -3.0, 3.0, 9.0)] + \
               [(-9.0, 26.45), (9.0, 26.45)]
    for x, y in post_pts:
        box(bm, (x, y, FZ + 0.17), (0.80, 0.80, 0.34), C["STONE_DARK"], ch=0.05)
        box(bm, (x, y, FZ + 0.34 + (KZT - FZ - 0.34) / 2), (0.38, 0.38, KZT - FZ - 0.34), C["WOOD"], ch=0.02)
        box(bm, (x, y, FZ + 1.10), (0.44, 0.44, 0.08), C["BRONZE_DARK"])
    for y in (KY0, KY1):
        beam(bm, (-9.4, y, KZT + 0.12), (9.4, y, KZT + 0.12), 0.16, 0.16, C["WOOD_DARK"], segs=6)
    for sx in (-1, 1):
        beam(bm, (sx * 9.0, KY0, KZT + 0.12), (sx * 9.0, KY1, KZT + 0.12), 0.16, 0.16, C["WOOD_DARK"], segs=6)
    ys = [KY0 + k * (KY1 - KY0) / 7 for k in range(8)]
    for k, y in enumerate(ys):
        for sx in (-1, 1):
            beam(bm, (sx * 9.9, y, KZT - 0.05), (0, y, KZR), 0.09, 0.09, C["WOOD"], segs=5)
        if 0 < k < 7:
            beam(bm, (-9.0, y, KZT + 0.12), (9.0, y, KZT + 0.12), 0.07, 0.07, C["WOOD"], segs=5)
            beam(bm, (0, y, KZT + 0.12), (0, y, KZR - 0.05), 0.06, 0.06, C["WOOD"], segs=5)
    beam(bm, (0, KY0 - 0.6, KZR), (0, KY1 + 0.6, KZR), 0.14, 0.14, C["WOOD_DARK"], segs=6)
    # tiled roof
    def zt(x):
        return KZR + 0.14 - (KZR - KZT) / 9.9 * abs(x)
    y0, y1 = KY0 - 0.9, KY1 + 0.9
    for sx in (-1, 1):
        xe = sx * 10.7
        extrude(bm, [(0, y0, zt(0)), (xe, y0, zt(xe)), (xe, y1, zt(xe)), (0, y1, zt(0))], (0, 0, -0.22), C["TERRACOTTA"])
        for j in range(15):
            x = sx * (0.55 + j * 0.69)
            beam(bm, (x, y0 + 0.02, zt(x) + 0.035), (x, y1 - 0.02, zt(x) + 0.035), 0.045, 0.045, C["TILE_DARK"], segs=4)
        beam(bm, (xe, y0, zt(xe) - 0.12), (xe, y1, zt(xe) - 0.12), 0.09, 0.09, C["MAROON"], segs=5)
    beam(bm, (0, y0, zt(0) + 0.08), (0, y1, zt(0) + 0.08), 0.15, 0.13, C["TILE_DARK"], segs=6)
    # pediment facing the dining ring
    prism(bm, [(-9.7, KZT), (9.7, KZT), (0, KZR + 0.02)], (0, y0 + 0.25, 0), 1.0, 0.30, C["STONE_LIGHT"])
    prism(bm, [(-8.4, KZT + 0.38), (8.4, KZT + 0.38), (0, KZR - 0.55)], (0, y0 + 0.25 - 0.18, 0), 1.0, 0.06, C["MAROON"])
    emblem(bm, (0, y0 + 0.25 - 0.25, KZT + 1.45), 1.3, C["CREAM"], C["MAROON"], t=0.08)
    for sx in (-1, 1):
        beam(bm, (sx * 9.95, y0 + 0.05, KZT - 0.05), (0, y0 + 0.05, KZR + 0.06), 0.13, 0.13, C["WOOD_DARK"], segs=5)
    beam(bm, (-9.95, y0 + 0.05, KZT - 0.05), (9.95, y0 + 0.05, KZT - 0.05), 0.13, 0.13, C["WOOD_DARK"], segs=5)
    # walls
    wh = KZT + 0.1 - FZ
    box(bm, (0, KY1 + 0.5, FZ + wh / 2), (19.4, 0.6, wh), C["STONE"], ch=0.05)
    for row in range(1, 5):
        box(bm, (0, KY1 + 0.5 - 0.31, FZ + row * 0.85), (19.0, 0.02, 0.04), C["STONE_DARK"])
    for sx in (-1, 1):
        box(bm, (sx * 9.35, 26.75, FZ + 0.55), (0.5, 7.9, 1.10), C["STONE"], ch=0.04)
        box(bm, (sx * 9.35, 26.75, FZ + 1.14), (0.62, 8.0, 0.08), C["STONE_LIGHT"], ch=0.02)
    # shelves with stores
    for sx in (-1, 1):
        cx = sx * 5.4
        for lvl in (1.35, 2.35, 3.35):
            box(bm, (cx, KY1 + 0.17, FZ + lvl), (5.8, 0.45, 0.07), C["WOOD"], ch=0.015)
            for bx in (-2.6, 0.0, 2.6):
                box(bm, (cx + bx, KY1 + 0.17, FZ + lvl - 0.22), (0.10, 0.4, 0.34), C["WOOD_DARK"])
            for k in range(5):
                px = cx - 2.4 + k * 1.2 + rng.uniform(-0.15, 0.15)
                if rng.random() < 0.6:
                    amphora(bm, px, KY1 + 0.17, FZ + lvl + 0.035, rng.uniform(0.7, 0.9),
                            "TERRACOTTA" if rng.random() < 0.7 else "TILE_DARK")
                else:
                    frustum(bm, T((px, KY1 + 0.17, FZ + lvl + 0.035)), 0.17, 0.17, 0.2, C["CREAM"], segs=8)
    for k, (x, z) in enumerate([(-1.0, 0), (-0.45, 0), (0.15, 0), (0.75, 0), (-0.7, 0.45), (0.5, 0.45), (-0.1, 0.9)]):
        sack(bm, x, KY1 - 0.1 + (0.15 if k % 2 else 0), FZ + z, 1.0)
    # serving counters
    for sx in (-1, 1):
        cx, cy = sx * 6.0, 23.55
        box(bm, (cx, cy, FZ + 0.52), (5.4, 0.9, 1.04), C["STONE"], ch=0.04)
        box(bm, (cx, cy, FZ + 1.09), (5.7, 1.1, 0.10), C["WOOD_LIGHT"], ch=0.03)
        box(bm, (cx, cy - 0.46, FZ + 0.55), (4.8, 0.02, 0.60), C["MAROON"])
        box(bm, (cx, cy - 0.47, FZ + 0.88), (4.9, 0.02, 0.05), C["BRONZE"])
        zc = FZ + 1.14
        for dx in (-2.1, 0.0, 2.1):
            frustum(bm, T((cx + dx, cy + 0.05, zc)), 0.20, 0.20, 0.20, C["CREAM"], segs=8)
        for dx in (-1.05, 1.05):
            box(bm, (cx + dx, cy - 0.05, zc + 0.015), (0.8, 0.5, 0.03), C["WOOD"], ch=0.01)
            for k in range(3):
                blob(bm, (cx + dx + (k - 1) * 0.22, cy - 0.05, zc + 0.08), (0.09, 0.08, 0.06), C["BREAD"], segs=6, rings=3)
        frustum(bm, T((cx + 2.4, cy, zc)), 0.09, 0.07, 0.26, C["TERRACOTTA"], segs=8)
        frustum(bm, T((cx - 2.45, cy + 0.05, zc)), 0.28, 0.24, 0.32, C["BRONZE_DARK"], segs=8)
        beam(bm, (cx - 2.7, cy - 0.35, FZ + 2.55), (cx + 2.7, cy - 0.35, FZ + 2.55), 0.04, 0.04, C["WOOD_DARK"], segs=5)
        for k in range(5):
            lx = cx - 2.0 + k * 1.0
            beam(bm, (lx, cy - 0.35, FZ + 2.55), (lx, cy - 0.35, FZ + 2.05), 0.015, 0.015, C["BRONZE"], segs=3)
            blob(bm, (lx, cy - 0.35, FZ + 2.03), (0.08, 0.08, 0.04), C["BRONZE"], segs=6, rings=3)
    # cauldron stations
    for sx in (-1, 1):
        x, y = sx * 6.4, 26.6
        frustum(bm, T((x, y, FZ)), 1.15, 1.05, 0.34, C["STONE_DARK"], segs=10)
        frustum(bm, T((x, y, FZ + 0.30)), 0.80, 0.80, 0.05, C["CHARCOAL"], segs=10)
        for k in range(3):
            an = math.tau * k / 3 + 0.5
            beam(bm, (x + 1.1 * math.cos(an), y + 1.1 * math.sin(an), FZ + 0.2), (x, y, FZ + 2.95), 0.06, 0.05, C["IRON"], segs=5)
        beam(bm, (x, y, FZ + 2.9), (x, y, FZ + 1.9), 0.03, 0.03, C["IRON"], segs=4)
        blob(bm, (x, y, FZ + 1.22), (0.86, 0.86, 0.62), C["BRONZE_DARK"], segs=10, rings=5)
        frustum(bm, T((x, y, FZ + 1.74)), 0.52, 0.42, 0.10, C["BRONZE"], segs=10)
        blob(bm, (x, y, FZ + 1.88), (0.09, 0.09, 0.07), C["BRONZE"], segs=6, rings=3)
        for k in range(3):
            box(bm, (x, y, FZ + 0.42), (1.2, 0.16, 0.16), C["WOOD"], rot=0.6 + k * 1.05, ch=0.03)
        for k in range(4):
            an = math.tau * k / 4 + 0.4
            frustum(g, T((x + 0.55 * math.cos(an), y + 0.55 * math.sin(an), FZ + 0.34)), 0.26, 0.0, 0.75, C["FLAME_ORANGE"], segs=6)
        log_stack(bm, sx * 8.2, 28.1, FZ, rows=3, length=1.2, along_x=False)
    # bread oven
    ox, oy = -6.8, 29.0
    box(bm, (ox, oy, FZ + 0.55), (3.2, 2.8, 1.10), C["STONE"], ch=0.06)
    blob(bm, (ox, oy, FZ + 1.05), (1.5, 1.3, 1.0), C["STONE_LIGHT"], segs=10, rings=5, jitter=0.02)
    box(bm, (ox, oy - 1.27, FZ + 0.95), (1.05, 0.32, 0.85), C["STONE_DARK"], ch=0.04)
    box(g, (ox, oy - 1.44, FZ + 0.90), (0.75, 0.06, 0.55), C["FLAME_ORANGE"])
    frustum(bm, T((ox, oy + 0.4, FZ + 1.9)), 0.32, 0.26, 1.3, C["STONE"], segs=8)
    beam(bm, (ox + 1.9, oy - 1.4, FZ), (ox + 1.7, oy - 1.55, FZ + 2.4), 0.04, 0.04, C["WOOD_LIGHT"], segs=5)
    box(bm, (ox + 1.7, oy - 1.55, FZ + 2.45), (0.45, 0.05, 0.4), C["WOOD_LIGHT"])
    log_stack(bm, ox + 1.2, oy - 1.9, FZ, rows=3, length=1.2)
    # prep tables
    for sx in (-1, 1):
        x, y = sx * 3.6, 26.4
        box(bm, (x, y, FZ + 0.94), (1.5, 3.6, 0.08), C["WOOD_LIGHT"], ch=0.015)
        for lx in (-0.65, 0.65):
            for ly in (-1.6, 1.6):
                box(bm, (x + lx, y + ly, FZ + 0.45), (0.12, 0.12, 0.90), C["WOOD"])
        box(bm, (x, y, FZ + 0.30), (1.3, 3.3, 0.05), C["WOOD"])
        zt0 = FZ + 0.98
        box(bm, (x + 0.1, y - 1.1, zt0 + 0.02), (0.7, 0.5, 0.04), C["WOOD"], ch=0.01)
        box(bm, (x + 0.1, y - 1.1, zt0 + 0.06), (0.30, 0.04, 0.012), C["IRON"], rot=0.4)
        for k in range(4):
            blob(bm, (x - 0.3 + 0.2 * (k % 2), y + 0.1 + 0.25 * k, zt0 + 0.10), (0.13, 0.13, 0.11),
                 C["LEAF_LIGHT"] if k % 2 else C["APPLE"], segs=6, rings=3)
        frustum(bm, T((x, y + 1.3, zt0)), 0.24, 0.20, 0.14, C["CREAM"], segs=8)
        sack(bm, x + sx * 0.0, y - 1.95 + 0.0, FZ, 0.8) if False else None
    # wash trough and water barrels
    box(bm, (7.2, 29.2, FZ + 0.42), (2.6, 0.9, 0.84), C["STONE"], ch=0.04)
    box(bm, (7.2, 29.2, FZ + 0.85), (2.3, 0.65, 0.02), C["WATER"])
    barrel(bm, 8.3, 27.8, FZ, 1.0, "WOOD")
    barrel(bm, 8.35, 28.6, FZ, 1.0, "WOOD")
    barrel(bm, 5.3, 29.6, FZ, 0.9, "WOOD_DARK")
    crate(bm, 4.1, 29.6, FZ, 0.75, 0.1)
    crate(bm, 4.15, 29.6, FZ + 0.75, 0.7, 0.4)
    crate(bm, -3.9, 29.6, FZ, 0.8, -0.1)
    crate(bm, -2.9, 29.65, FZ, 0.7, 0.2)
    # things hanging from the tie beams
    for k, (x, y) in enumerate([(-5.0, ys[2]), (5.0, ys[2]), (-2.0, ys[4]), (2.0, ys[4]), (-6.5, ys[5]), (6.5, ys[5]),
                                (-1.0, ys[6]), (1.0, ys[6])]):
        zt_ = KZT + 0.12
        if k % 3 == 0:
            b, gb = bmesh.new(), bmesh.new()
            lantern_local(b, gb)
            merge(bm, b, T((x, y, zt_ - 0.9)))
            merge(g, gb, T((x, y, zt_ - 0.9)))
            beam(bm, (x, y, zt_), (x, y, zt_ - 0.9), 0.025, 0.025, C["IRON"], segs=4)
        elif k % 3 == 1:
            beam(bm, (x, y, zt_), (x, y, zt_ - 0.6), 0.02, 0.02, C["IRON"], segs=4)
            blob(bm, (x, y, zt_ - 0.8), (0.24, 0.24, 0.20), C["BRONZE_DARK"], segs=7, rings=4)
        else:
            beam(bm, (x, y, zt_), (x, y, zt_ - 0.35), 0.015, 0.015, C["LINEN"], segs=3)
            for j in range(3):
                blob(bm, (x + (j - 1) * 0.14, y, zt_ - 0.55 - 0.05 * j), (0.09, 0.06, 0.18), C["LEAF_MID"], segs=5, rings=3)


# ============================ 11) FORECOURT & PROPS ==========================
def notice_board_local(b):
    for sx in (-1, 1):
        beam(b, (sx * 1.25, 0, 0), (sx * 1.25, 0, 3.1), 0.11, 0.10, C["WOOD"], segs=6)
        box(b, (sx * 1.25, 0, 0.12), (0.4, 0.4, 0.24), C["STONE_DARK"], ch=0.03)
    box(b, (0, 0, 2.0), (2.8, 0.12, 1.9), C["WOOD_LIGHT"], ch=0.03)
    box(b, (0, -0.07, 2.0), (2.5, 0.04, 1.6), C["DIRT_LIGHT"])
    for _ in range(9):
        w, h = rng.uniform(0.35, 0.6), rng.uniform(0.45, 0.7)
        px, pz = rng.uniform(-0.95, 0.95), rng.uniform(1.55, 2.5)
        box(b, (px, -0.10, pz), (w, 0.015, h), C["LINEN"])
        blob(b, (px, -0.115, pz + h / 2 - 0.06), (0.03, 0.02, 0.03), C["APPLE"], segs=4, rings=2)
    box(b, (0, 0, 3.25), (3.2, 0.16, 0.42), C["MAROON"], ch=0.03)
    emblem(b, (0, -0.115, 3.25), 0.17, C["CREAM"], C["MAROON"], t=0.04)
    box(b, (0, 0, 3.62), (3.5, 0.55, 0.10), C["WOOD_DARK"])


def bell_frame_local(b):
    for sx in (-1, 1):
        beam(b, (sx * 0.9, 0, 0), (sx * 0.9, 0, 3.2), 0.12, 0.11, C["WOOD"], segs=6)
        box(b, (sx * 0.9, 0, 0.12), (0.4, 0.4, 0.24), C["STONE_DARK"], ch=0.03)
    beam(b, (-1.05, 0, 3.2), (1.05, 0, 3.2), 0.10, 0.10, C["WOOD"], segs=6)
    frustum(b, T((0, 0, 2.35)), 0.42, 0.18, 0.62, C["BRONZE"], segs=10)
    frustum(b, T((0, 0, 2.97)), 0.18, 0.12, 0.15, C["BRONZE_DARK"], segs=8)
    beam(b, (0, 0, 3.12), (0, 0, 3.2), 0.04, 0.04, C["IRON"], segs=4)
    blob(b, (0, 0, 2.30), (0.08, 0.08, 0.08), C["IRON"], segs=6, rings=3)
    beam(b, (0, -0.05, 2.30), (0, -0.05, 1.3), 0.02, 0.02, C["LINEN"], segs=3)
    blob(b, (0, -0.05, 1.28), (0.06, 0.06, 0.06), C["LINEN"], segs=5, rings=3)


def build_forecourt(bm, g):
    box(bm, (0, -26.2, 0.10), (11.0, 6.0, 0.20), C["STONE_LIGHT"], ch=0.04)                 # landing
    for ix in range(-2, 3):
        for iy in range(3):
            q = rng.random()
            box(bm, (ix * 2.1, -24.4 - iy * 1.9, 0.205), (2.0, 1.8, 0.01),
                C["STONE"] if q < 0.5 else C["STONE_LIGHT"] if q < 0.8 else C["STONE_DARK"])
    for sx in (-1, 1):                                                                        # low side walls
        box(bm, (sx * 5.7, -26.2, 0.55), (0.45, 6.0, 0.7), C["STONE"], ch=0.04)
        box(bm, (sx * 5.7, -26.2, 0.93), (0.56, 6.1, 0.08), C["STONE_LIGHT"], ch=0.02)
    # floor medallion with the bull
    frustum(bm, T((0, -26.4, 0.20)), 1.9, 1.85, 0.04, C["STONE_DARK"], segs=20)
    ring(bm, T((0, -26.4, 0.24)), 1.75, 1.55, 0.015, C["BRONZE"], segs=20)
    frustum(bm, T((0, -26.4, 0.24)), 1.55, 1.55, 0.012, C["MAROON"], segs=20)
    eb = bmesh.new()
    emblem(eb, (0, 0, 0), 0.95, C["CREAM"], C["MAROON"], t=0.012)
    merge(bm, eb, T((0, -26.4, 0.262)) @ ROT_XN90)
    # notice board, bell, bench, pole banners, stores
    nb = bmesh.new()
    notice_board_local(nb)
    merge(bm, nb, T((-8.4, -27.6, 0)))
    bf = bmesh.new()
    bell_frame_local(bf)
    merge(bm, bf, T((8.4, -27.6, 0)))
    bn = bmesh.new()
    bench_local(bn, 2.4)
    merge(bm, bn, T((-8.4, -26.2, 0)))
    for sx in (-1, 1):
        beam(bm, (sx * 4.7, -27.4, 0.2), (sx * 4.7, -27.4, 6.4), 0.09, 0.08, C["WOOD"], segs=6)
        blob(bm, (sx * 4.7, -27.4, 6.5), (0.14, 0.14, 0.14), C["BRONZE"], segs=6, rings=3)
        b = bmesh.new()
        banner_local(b, 1.1, 3.0, "MAROON", "BULL", stand=0.0)
        merge(bm, b, T((sx * 4.7, -27.52, 6.0)))
    crate(bm, 9.9, -25.2, 0, 0.8, 0.2)
    crate(bm, 9.95, -25.2, 0.8, 0.7, -0.3)
    barrel(bm, 10.8, -26.0, 0, 1.0)
    sack(bm, 9.4, -26.3, 0, 1.0)
    amphora(bm, -10.8, -26.5, 0, 1.4)


# ============================ 12) GREENERY & AGEING ==========================
LEAF_COLORS = [C["LEAF_MID"], C["LEAF_LIGHT"], C["LEAF_DARK"]]


def vine_on_column(bm, cx, cy, r_at, z0, z1, phase):
    n = 11
    pts = []
    for i in range(n + 1):
        t = i / n
        z = z0 + (z1 - z0) * t
        r = r_at(z) + 0.045
        th = phase + t * math.tau * 1.3
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th), z))
    for a, b in zip(pts[:-1], pts[1:]):
        beam(bm, a, b, 0.045, 0.040, C["LEAF_DARK"], segs=4)
    for p in pts:
        for _ in range(2):
            an = rng.uniform(0, math.tau)
            blob(bm, (p[0] + 0.10 * math.cos(an), p[1] + 0.10 * math.sin(an), p[2] + rng.uniform(-0.05, 0.1)),
                 (0.16, 0.05, 0.11), rng.choice(LEAF_COLORS), segs=4, rings=2, rot=rng.uniform(0, 1.5))


def ivy_strand(bm, x, y, z, length, dx=0.0, dy=0.0):
    n = max(2, int(length / 0.30))
    pts = [(x + dx * i / n + 0.05 * math.sin(i * 1.7), y + dy * i / n, z - length * i / n) for i in range(n + 1)]
    for a, b in zip(pts[:-1], pts[1:]):
        beam(bm, a, b, 0.03, 0.025, C["LEAF_DARK"], segs=3)
    for p in pts[1:]:
        blob(bm, (p[0] + rng.uniform(-0.1, 0.1), p[1] + rng.uniform(-0.05, 0.05), p[2]),
             (0.16, 0.05, 0.11), rng.choice(LEAF_COLORS), segs=4, rings=2, rot=rng.uniform(0, 1.5))


def build_vines(bm):
    outer_r = lambda z: 0.52 - 0.09 * (z - FZ - 0.74) / 5.92
    inner_r = lambda z: 0.40 - 0.09 * (z - FZ - 0.52) / 6.78
    for i in rng.sample(range(N_COL), 11):                          # climbing vines on the outer colonnade
        cx, cy, _ = polar(R_COL_OUT, COL_ANG[i])
        vine_on_column(bm, cx, cy, outer_r, FZ + 0.9, FZ + rng.uniform(3.2, 6.4), rng.uniform(0, math.tau))
    for i in rng.sample(range(N_COL), 6):                           # and on some inner columns
        cx, cy, _ = polar(R_COL_IN, COL_ANG[i])
        vine_on_column(bm, cx, cy, inner_r, FZ + 0.7, FZ + rng.uniform(2.8, 5.2), rng.uniform(0, math.tau))
    for _ in range(30):                                             # ivy curtains off the roof edge
        a = rng.uniform(0, math.tau)
        if angle_dist(a, FRONT) < 0.22:
            continue
        x, y, _ = polar(19.2, a)
        ivy_strand(bm, x, y, Z_CORONA0, rng.uniform(1.2, 3.4), -0.12 * math.cos(a), -0.12 * math.sin(a))
    for _ in range(12):                                             # and over the courtyard edge
        a = rng.uniform(0, math.tau)
        x, y, _ = polar(10.35, a)
        ivy_strand(bm, x, y, Z_CORONA0, rng.uniform(0.8, 2.2), 0.1 * math.cos(a), 0.1 * math.sin(a))
    for x, y in [(-9.0, KY0), (9.0, KY0), (-3.0, KY0), (3.0, KY0)]:  # kitchen posts
        vine_on_column(bm, x, y, lambda z: 0.19, FZ + 0.4, FZ + rng.uniform(2.0, 3.8), rng.uniform(0, math.tau))
    for _ in range(9):
        x = rng.uniform(-9.5, 9.5)
        ivy_strand(bm, x, KY0 - 0.9, KZT - 0.05, rng.uniform(0.8, 2.0))


def planter(bm, x, y, kind):
    frustum(bm, T((x, y, FZ)), 0.78, 0.64, 0.50, C["STONE_DARK"], segs=8)
    ring(bm, T((x, y, FZ + 0.50)), 0.80, 0.66, 0.07, C["STONE_LIGHT"], segs=8)
    frustum(bm, T((x, y, FZ + 0.52)), 0.66, 0.66, 0.04, C["DIRT"], segs=8)
    if kind == 0:                                                  # cypress
        frustum(bm, T((x, y, FZ + 0.55)), 0.50, 0.0, 2.6, C["LEAF_DARK"], segs=7, jitter=0.08)
        blob(bm, (x, y, FZ + 1.5), (0.40, 0.40, 0.7), C["LEAF_MID"], segs=6, rings=3, jitter=0.1)
    elif kind == 1:                                                # flowering shrub
        blob(bm, (x, y, FZ + 0.85), (0.62, 0.55, 0.42), C["LEAF_MID"], segs=7, rings=4, jitter=0.1)
        for _ in range(7):
            an = rng.uniform(0, math.tau)
            r = rng.uniform(0.15, 0.5)
            blob(bm, (x + r * math.cos(an), y + r * math.sin(an), FZ + 1.0 + rng.uniform(0, 0.25)),
                 (0.08, 0.08, 0.06), rng.choice([C["FLOWER_RED"], C["FLOWER_WHITE"], C["FLOWER_YELLOW"]]), segs=5, rings=3)
    else:                                                          # trailing greenery
        blob(bm, (x, y, FZ + 0.78), (0.55, 0.50, 0.30), C["LEAF_LIGHT"], segs=7, rings=4, jitter=0.1)
        for k in range(4):
            an = math.tau * k / 4 + 0.6
            ivy_strand(bm, x + 0.6 * math.cos(an), y + 0.6 * math.sin(an), FZ + 0.62, 0.55,
                       0.1 * math.cos(an), 0.1 * math.sin(an))


def grass_tuft(bm, x, y, z=0.0, flowers=False):
    for _ in range(3):
        h = rng.uniform(0.35, 0.7)
        beam(bm, (x + rng.uniform(-0.1, 0.1), y + rng.uniform(-0.1, 0.1), z),
             (x + rng.uniform(-0.2, 0.2), y + rng.uniform(-0.2, 0.2), z + h), 0.05, 0.0, C["GRASS_LIGHT"], segs=3)
    if flowers:
        blob(bm, (x, y, z + 0.62), (0.11, 0.11, 0.08),
             rng.choice([C["FLOWER_WHITE"], C["FLOWER_PURPLE"], C["FLOWER_YELLOW"], C["FLOWER_RED"]]), segs=5, rings=3)


def rock(bm, x, y, s, z=0.05):
    blob(bm, (x, y, z), (s, s * 0.9, s * 0.6), rng.choice([C["STONE"], C["STONE_LIGHT"], C["STONE_DARK"]]),
         segs=5, rings=3, jitter=0.18)


def build_groundcover(bm):
    for i, a in enumerate(COL_ANG):                                 # planters just outside the colonnade
        x, y, _ = polar(20.4, a)
        planter(bm, x, y, i % 3)
    for _ in range(46):                                             # moss on the floor, steps and column feet
        a = rng.uniform(0, math.tau)
        if rng.random() < 0.5:
            r, z = rng.choice([R_COL_OUT, R_COL_IN]), FZ + 0.008
            r += rng.uniform(-0.9, 0.9)
        else:
            r = rng.uniform(21.0, 22.8)
            z = FZ + 0.008 if r < 22.3 else (0.4 + 0.008 if r < 22.7 else 0.2 + 0.008)
            z = 0.56 + 0.008 if r < 21.8 else z
        if angle_dist(a, FRONT) < 0.3:
            continue
        box(bm, polar(r, a, z), (rng.uniform(0.5, 1.4), rng.uniform(0.3, 0.8), 0.02), C["MOSS"], rot=a)
    for i in range(N_COL):                                          # moss and weeds at every column foot
        for R in (R_COL_OUT, R_COL_IN):
            a = COL_ANG[i] + rng.uniform(-0.03, 0.03)
            x, y, _ = polar(R + 0.62, a)
            blob(bm, (x, y, FZ + 0.42), (0.28, 0.20, 0.07), C["MOSS"], segs=5, rings=3, rot=a)
            if rng.random() < 0.5:
                grass_tuft(bm, *polar(R + 0.9, a + rng.uniform(-0.05, 0.05))[:2], z=FZ, flowers=True)
    for _ in range(26):                                             # weeds in the paving cracks & step edges
        a = rng.uniform(0, math.tau)
        if angle_dist(a, FRONT) < 0.3:
            continue
        r = rng.uniform(4.6, 21.0)
        if abs(r - RING_A_R) < 1.6 or abs(r - RING_B_R) < 1.6:
            continue
        grass_tuft(bm, *polar(r, a)[:2], z=FZ)
    for _ in range(40):                                             # tufts round the platform edge
        a = rng.uniform(0, math.tau)
        x, y, _ = polar(rng.uniform(23.4, 25.2), a)
        if near_path(x, y, 3.0) or not clear_of_landmarks(x, y, -0.8):
            continue
        grass_tuft(bm, x, y, flowers=rng.random() < 0.3)
    for sx in (-1, 1):                                              # flower beds beside the entry steps
        bx = sx * 8.0
        box(bm, (bx, -23.9, 0.18), (3.2, 1.6, 0.36), C["STONE"], ch=0.04)
        box(bm, (bx, -23.9, 0.36), (2.8, 1.2, 0.04), C["DIRT"])
        for k in range(9):
            blob(bm, (bx + rng.uniform(-1.2, 1.2), -23.9 + rng.uniform(-0.4, 0.4), 0.55 + rng.uniform(0, 0.2)),
                 (0.20, 0.20, 0.17), rng.choice(LEAF_COLORS), segs=6, rings=3)
        for k in range(10):
            blob(bm, (bx + rng.uniform(-1.3, 1.3), -23.9 + rng.uniform(-0.5, 0.5), 0.78 + rng.uniform(0, 0.15)),
                 (0.09, 0.09, 0.07), rng.choice([C["FLOWER_RED"], C["FLOWER_WHITE"], C["FLOWER_YELLOW"], C["FLOWER_PURPLE"]]),
                 segs=5, rings=3)
    shrubs = 0
    while shrubs < 30:                                              # shrubs framing the grounds
        a = rng.uniform(0, math.tau)
        r = rng.uniform(26.5, 38.0)
        x, y = r * math.cos(a), r * math.sin(a)
        if near_path(x, y, 4.0) or not clear_of_landmarks(x, y, 1.0):
            continue
        s = rng.uniform(0.9, 1.7)
        blob(bm, (x, y, 0.30), (s, s * 0.78, s * 0.5), rng.choice(LEAF_COLORS), segs=7, rings=4, jitter=0.12)
        for _ in range(3):
            blob(bm, (x + rng.uniform(-0.45, 0.45) * s, y + rng.uniform(-0.35, 0.35) * s, 0.55 + rng.uniform(0, 0.3)),
                 (s * 0.42, s * 0.36, s * 0.36), rng.choice(LEAF_COLORS), segs=6, rings=3, jitter=0.12)
        shrubs += 1
    rocks = 0
    while rocks < 26:                                               # mossy rocks and boulders
        a = rng.uniform(0, math.tau)
        r = rng.uniform(25.0, 40.0)
        x, y = r * math.cos(a), r * math.sin(a)
        if near_path(x, y, 3.2) or not clear_of_landmarks(x, y, 0.5):
            continue
        s = rng.uniform(0.25, 0.9)
        rock(bm, x, y, s)
        if s > 0.5:
            blob(bm, (x, y, 0.05 + s * 0.45), (s * 0.7, s * 0.6, s * 0.18), C["MOSS"], segs=5, rings=3)
        rocks += 1
    for sx in (-1, 1):                                              # a mossy boulder pair by the service path
        rock(bm, sx * 14.0 + 12.0, 34.0, 1.0)


def tree(bm, x, y, kind, s=1.0):
    h = rng.uniform(6.2, 8.4) * s
    if kind == "birch":
        tr = 0.24 * s
        frustum(bm, T((x, y, 0)), tr, tr * 0.55, h, C["BIRCH_BARK"], segs=7, jitter=0.04)
        for _ in range(11):
            an = rng.uniform(0, math.tau)
            zz = rng.uniform(0.8, h - 1.0)
            rr = tr * (1 - 0.45 * zz / h) * 0.98
            blob(bm, (x + rr * math.cos(an), y + rr * math.sin(an), zz), (0.07, 0.07, 0.04), C["BIRCH_MARK"], segs=4, rings=2)
        cols = [C["GOLD_LEAF"], C["LEAF_LIGHT"], C["GOLD_LEAF"], C["RUST_LEAF"], C["LEAF_MID"]]
        for k in range(6):
            an = math.tau * k / 6 + rng.uniform(-0.3, 0.3)
            rr = rng.uniform(0.6, 1.6) * s
            rad = rng.uniform(1.3, 1.9) * s
            blob(bm, (x + rr * math.cos(an), y + rr * math.sin(an), h * 0.88 + rng.uniform(-0.8, 0.8)),
                 (rad, rad, rad * 0.8), rng.choice(cols), segs=7, rings=4, jitter=0.12)
    else:
        tr = 0.55 * s
        frustum(bm, T((x, y, 0)), tr, tr * 0.6, h * 0.65, C["WOOD"], segs=7, jitter=0.06)
        for k in range(4):
            an = math.tau * k / 4 + rng.uniform(-0.4, 0.4)
            beam(bm, (x + tr * 0.9 * math.cos(an), y + tr * 0.9 * math.sin(an), 0.45),
                 (x + 1.4 * s * math.cos(an), y + 1.4 * s * math.sin(an), -0.05), 0.2 * s, 0.07 * s, C["WOOD"], segs=5)
        tops = []
        for k in range(3):
            an = math.tau * k / 3 + rng.uniform(-0.4, 0.4)
            tops.append((x + 1.5 * s * math.cos(an), y + 1.5 * s * math.sin(an), h * 0.88))
            beam(bm, (x, y, h * 0.5), tops[-1], 0.2 * s, 0.1 * s, C["WOOD"], segs=5)
        for k in range(7):
            an = math.tau * k / 7 + rng.uniform(-0.3, 0.3)
            rr = rng.uniform(0.8, 2.3) * s
            rad = rng.uniform(1.7, 2.5) * s
            cols = [C["LEAF_DARK"], C["LEAF_MID"], C["LEAF_LIGHT"], C["LEAF_MID"]] + ([C["GOLD_LEAF"]] if rng.random() < 0.25 else [])
            blob(bm, (x + rr * math.cos(an), y + rr * math.sin(an), h * 0.92 + rng.uniform(-0.8, 1.0)),
                 (rad, rad, rad * 0.78), rng.choice(cols), segs=7, rings=4, jitter=0.12)


TREE_SPOTS = [(-30, -8, "birch"), (-33, 2, "oak"), (-29, 14, "birch"), (-25, 27, "oak"), (30, -6, "oak"),
              (34, 6, "birch"), (28, 17, "birch"), (-14, -34, "oak"), (15, -35, "birch"), (-24, -24, "birch"),
              (26, -26, "oak"), (-9, -48, "birch"), (11, -52, "oak"), (0, 42, "oak"), (-15, 37, "birch"),
              (17, 39, "birch"), (-36, -20, "oak")]


def build_trees(bm):
    for x, y, kind in TREE_SPOTS:
        tree(bm, x, y, kind, rng.uniform(0.9, 1.2))


# ============================ 13) PATHS + GROUND =============================
def build_path(bm):
    for pth in PATHS:
        rows = []
        n = len(pth)
        for i, (x, y) in enumerate(pth):
            a = pth[max(i - 1, 0)]
            b = pth[min(i + 1, n - 1)]
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


def build_ground(bm):
    box(bm, (0, -8, -0.5), (110, 100, 1.0), C["GRASS"])
    for _ in range(26):
        x, y = rng.uniform(-50, 50), rng.uniform(-55, 40)
        box(bm, (x, y, 0.012), (rng.uniform(3, 9), rng.uniform(3, 9), 0.03), C["GRASS_LIGHT"], rot=rng.uniform(0, math.pi))


# ============================ BUILD EVERYTHING ===============================
bm_floor, bm_out, bm_in, bm_ent = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()
bm_ban, bm_hw, bm_hearth, bm_glow = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()
bm_kit, bm_fore, bm_vine, bm_gc = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()
bm_tree, bm_path, bm_gnd, bm_braz = bmesh.new(), bmesh.new(), bmesh.new(), bmesh.new()

build_floor(bm_floor)

tpl = column_ionic()                       # one template column, stamped round the ring
for a in COL_ANG:
    merge(bm_out, tpl, frame_in(a, R_COL_OUT, FZ), free=False)
tpl.free()
tpl = column_plain()
for a in COL_ANG:
    merge(bm_in, tpl, frame_in(a, R_COL_IN, FZ), free=False)
tpl.free()

build_entablature(bm_ent)
build_banners(bm_ban)
build_hardware(bm_hw, bm_glow)
build_hearth(bm_hearth, bm_glow)
build_kitchen(bm_kit, bm_glow)
build_forecourt(bm_fore, bm_glow)
build_vines(bm_vine)
build_groundcover(bm_gc)
build_trees(bm_tree)
build_path(bm_path)
build_ground(bm_gnd)
build_brazier(bm_braz)

objs = [
    finish("Pavilion_Floor", bm_floor),
    finish("Pavilion_ColumnsOuter", bm_out),
    finish("Pavilion_ColumnsInner", bm_in),
    finish("Pavilion_Entablature", bm_ent),
    finish("Pavilion_Banners", bm_ban),
    finish("Pavilion_Hardware", bm_hw),
    finish("Pavilion_Hearth", bm_hearth),
    finish("Pavilion_Kitchen", bm_kit),
    finish("Pavilion_Forecourt", bm_fore),
    finish("Pavilion_Vines", bm_vine),
    finish("Pavilion_Groundcover", bm_gc),
    finish("Pavilion_Trees", bm_tree),
    finish("Pavilion_Path", bm_path),
    finish("Pavilion_Ground", bm_gnd, trim=False),
]

# ---- braziers: one shared mesh, placed 8 times (flames go in the Glow mesh) ----
BRAZIER_SPOTS = [(-3.4, -25.0, 0.20), (3.4, -25.0, 0.20),
                 (20.4, -3.0, FZ), (20.4, 3.0, FZ), (-20.4, -3.0, FZ), (-20.4, 3.0, FZ),
                 (-2.8, 20.6, FZ), (2.8, 20.6, FZ)]
brazier_src = finish("Pavilion_Brazier", bm_braz, location=BRAZIER_SPOTS[0])
objs.append(brazier_src)
for i, (bx, by, bz) in enumerate(BRAZIER_SPOTS[1:], start=2):
    instance(brazier_src, f"Pavilion_Brazier_{i}", (bx, by, bz))
brazier_src.location = (BRAZIER_SPOTS[0][0] * STUD_SCALE, BRAZIER_SPOTS[0][1] * STUD_SCALE, BRAZIER_SPOTS[0][2] * STUD_SCALE)
bm_g2 = bm_glow
for bx, by, bz in BRAZIER_SPOTS:
    frustum(bm_g2, T((bx, by, bz + 2.10)), 0.38, 0.0, 0.95, C["FLAME_ORANGE"], segs=6)
    frustum(bm_g2, T((bx, by, bz + 2.10)), 0.20, 0.0, 0.62, C["GLOW"], segs=5)
objs.append(finish("Pavilion_Glow", bm_glow, trim=False))

# ---- banquet tables: four shared meshes, 24 placements ----
tables = {}
table_objs = []
for key, (L, var) in {"LongA": (4.3, "A"), "LongB": (4.3, "B"), "ShortA": (3.4, "A"), "ShortB": (3.4, "B")}.items():
    tables[key] = None
placed = 0
placements = []
for i, a in enumerate(COL_ANG):                                   # ring under the roof, centred on the columns
    x, y, _ = polar(RING_A_R, a)
    placements.append((("LongA", "LongB")[i % 2], x, y, a + math.pi / 2))
for k in range(8):                                                # courtyard ring, aisles on the compass axes
    a = math.radians(22.5 + 45 * k)
    x, y, _ = polar(RING_B_R, a)
    placements.append((("ShortA", "ShortB")[k % 2], x, y, a + math.pi / 2))
spec = {"LongA": (4.3, "A"), "LongB": (4.3, "B"), "ShortA": (3.4, "A"), "ShortB": (3.4, "B")}
counts = {}
for key, x, y, rot in placements:
    counts[key] = counts.get(key, 0) + 1
    if tables[key] is None:
        L, var = spec[key]
        tables[key] = finish("Pavilion_Table_" + key, build_table(L, var), location=(x, y, FZ), rotation=rot)
        table_objs.append(tables[key])
        objs.append(tables[key])
    else:
        instance(tables[key], f"Pavilion_Table_{key}_{counts[key]}", (x, y, FZ), rot)
    placed += 1


# ============================ REPORT =========================================
print("\n=== Camp DemiSoul dining pavilion: game-ready report (units = studs) ===")
total = 0
for o in objs:
    tris = len(o.data.polygons)
    total += tris
    d = o.dimensions
    flag = "  <-- OVER BUDGET" if tris > TRI_WARN else ""
    print(f"{o.name:26s} {tris:6d} tris   {d.x:6.1f} x {d.y:6.1f} x {d.z:6.1f}{flag}")
print(f"{'TOTAL (unique meshes)':26s} {total:6d} tris   ({len(objs)} unique meshes + 1 shared texture)")
print("Table placements:", placed, "| seats approx:", sum(
    2 * int((spec[k][0] - 0.5) / 0.62) * n for k, n in counts.items()))
print("Outer colonnade diameter:", round(2 * R_COL_OUT * STUD_SCALE), "studs | column height:", round(7.6 * STUD_SCALE), "studs")


# ============================ EXPORT =========================================
def export_fbx(path):
    bpy.ops.object.select_all(action="DESELECT")
    for o in COL.objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.export_scene.fbx(filepath=path, use_selection=True, object_types={"MESH"},
                             add_leaf_bones=False, bake_anim=False, mesh_smooth_type="FACE")


if EXPORT and OUT:
    try:
        fbx_path = os.path.join(OUT, "CampDemiSoul_DiningPavilion.fbx")
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
