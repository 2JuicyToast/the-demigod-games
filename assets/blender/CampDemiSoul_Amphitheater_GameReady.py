# =============================================================================
# CAMP DEMISOUL - ANNOUNCEMENT AMPHITHEATER + LOOKOUT LODGE (game-ready rebuild)
# Run in Blender's Scripting tab (Blender 3.6 / 4.x / 5.x). Safe to re-run: it
# only replaces its own collection ("CampAmphitheater_GameReady").
#
# Built with the same toolkit as CampDemiSoul_Entrance_GameReady.py: one shared
# palette texture, chamfered stone, Greek-key friezes, maroon swallow-tail
# banners with the bull crest, entrance-style pillars and braziers.
#
# Layout (metres before STUD_SCALE, orchestra centre = origin):
#   +Y  stage + skene (scene building), backstage exit toward camp
#    0  orchestra with the ceremonial campfire
#   -Y  rising seating (cavea): 10 lower rows, a cross-walk (diazoma),
#       8 upper rows, then the top promenade and the Lookout Lodge + tower
#   +-X side entrances (parodoi) through two entrance-style gates
#
# Meshes (each ONE draw call in Roblox, all < 20k tris):
#   Amphi_CaveaLower / Amphi_CaveaUpper   seating tiers, aisle stairs, walkways
#   Amphi_Orchestra   paving, campfire hearth, forecourt
#   Amphi_Stage       stage, skene facade, pediment, banners, masks
#   Amphi_Gates       two side-entrance gates ("AMPHITHEATER")
#   Lodge_Shell       podium, walls, portico, rear stair
#   Lodge_Roof        roof, pediments, rafters
#   Lodge_Tower       octagonal lookout tower, spiral stair, floors, flag
#   Lodge_Interior    furniture, storage, rugs, sconces, chandeliers
#   Amphi_Props       braziers, cushions, crates and other exterior props
#   Amphi_Glow        every flame / candle  -> set Material = Neon in Studio
#   Amphi_Berm        hillside the seating is cut into
#   Amphi_Paths, Amphi_Foliage, Amphi_Ground (optional grass slab)
#
# Also written next to the FBX:
#   DemiSoul_Palette.png              superset of the entrance palette (first 20
#                                     colours identical, so one texture serves both)
#   AmphitheaterSetup.server.lua      drop into the imported Model: adds PointLights
#                                     at every flame and Seats on the furniture
# =============================================================================

import bpy, bmesh, math, os, random, struct, zlib
from mathutils import Vector, Matrix

# ------------------------------ SETTINGS -------------------------------------
STUD_SCALE = 3.0        # studs per modelled metre (same as the entrance)
EXPORT = True           # write palette PNG + FBX + Roblox setup script
EXPORT_DIR = ""         # blank = next to your .blend (or your home folder if unsaved)
COLLECTION_NAME = "CampAmphitheater_GameReady"
TRI_WARN = 20000        # Roblox per-mesh limit to stay under
SEED = 24

# --------------------------- PALETTE (one texture) ---------------------------
# Indices 0-19 match the entrance script exactly; new colours are appended.
PALETTE = [
    ("STONE", "#9A927F"), ("STONE_LIGHT", "#C2B9A2"), ("STONE_DARK", "#5E5E56"), ("MARBLE", "#E8E1D0"),
    ("BRONZE", "#9C7A3C"), ("BRONZE_DARK", "#5A431F"), ("MAROON", "#5E1D2E"), ("CREAM", "#F1ECDF"),
    ("DIRT", "#9B7446"), ("DIRT_LIGHT", "#BE9A62"), ("GRASS", "#4A6B2E"), ("GRASS_LIGHT", "#6E8E3E"),
    ("LEAF_DARK", "#1F4A2E"), ("LEAF_MID", "#2F6B3F"), ("LEAF_LIGHT", "#58954F"), ("MOSS", "#62803A"),
    ("WOOD", "#5A3B22"), ("GLOW", "#FFC24A"), ("FLOWER_WHITE", "#E8D8A8"), ("FLOWER_PURPLE", "#7A55A8"),
    ("WOOD_LIGHT", "#8A6238"), ("TERRACOTTA", "#A8552F"), ("TERRACOTTA_DARK", "#6E3520"), ("CHARCOAL", "#2A2420"),
    ("OLIVE_LEAF", "#7E9160"), ("CYPRESS", "#1C3A26"),
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
        d = os.path.join(base, "CampDemiSoul_Amphitheater_Export")
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
    # Own material name so re-running the entrance script never swaps our texture.
    mat = bpy.data.materials.get("DemiSoul_Palette_Amphi") or bpy.data.materials.new("DemiSoul_Palette_Amphi")
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
# Same primitives as the entrance: every face is tagged with a palette index
# (material_index until finish() turns it into UVs) and wound outward.

def T(c):
    return Matrix.Translation(Vector(c))


def Rz(a):
    return Matrix.Rotation(a, 4, "Z")


ROT_X90 = Matrix.Rotation(math.pi / 2, 4, "X")     # local +Z -> world -Y (faces the viewer)
ROT_XN90 = Matrix.Rotation(-math.pi / 2, 4, "X")   # local +Z -> world +Y


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
    M = T(c) @ Rz(rot)
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
    pts are (x, z) pairs. Used for the bull emblem, banners, pediments and walls."""
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


def hexa(bm, pts, color):
    """Any six-sided solid from 8 points: 4 bottom (in order) then the 4 above them."""
    V = [bm.verts.new(p) for p in pts]
    ref = sum((Vector(p) for p in pts), Vector((0, 0, 0))) / 8
    add_face(bm, V[0:4], ref, color)
    add_face(bm, V[4:8], ref, color)
    for i in range(4):
        j = (i + 1) % 4
        add_face(bm, [V[i], V[j], V[j + 4], V[i + 4]], ref, color)


def wedge(bm, r0, r1, a0, a1, z0, z1, color, segs=None, max_len=1.5):
    """Solid curved block between radii r0..r1, angles a0..a1 (around the origin)."""
    if segs is None:
        segs = max(1, math.ceil(abs(a1 - a0) * r1 / max_len))
    V = [[[None] * (segs + 1) for _ in range(2)] for _ in range(2)]   # [layer][ring][i]
    for L, z in enumerate((z0, z1)):
        for R, r in enumerate((r0, r1)):
            for i in range(segs + 1):
                a = a0 + (a1 - a0) * i / segs
                V[L][R][i] = bm.verts.new((r * math.cos(a), r * math.sin(a), z))
    rm, zm = (r0 + r1) / 2, (z0 + z1) / 2

    def ref_at(i):
        am = a0 + (a1 - a0) * (i + 0.5) / segs
        return Vector((rm * math.cos(am), rm * math.sin(am), zm))

    for i in range(segs):
        j, ref = i + 1, ref_at(i)
        add_face(bm, [V[1][0][i], V[1][0][j], V[1][1][j], V[1][1][i]], ref, color)   # top
        add_face(bm, [V[0][0][i], V[0][0][j], V[0][1][j], V[0][1][i]], ref, color)   # bottom
        add_face(bm, [V[0][0][i], V[0][0][j], V[1][0][j], V[1][0][i]], ref, color)   # inner
        add_face(bm, [V[0][1][i], V[0][1][j], V[1][1][j], V[1][1][i]], ref, color)   # outer
    for i, k in ((0, 0), (segs, segs - 1)):                                          # end caps
        add_face(bm, [V[0][0][i], V[0][1][i], V[1][1][i], V[1][0][i]], ref_at(k), color)


def polar(r, a, z=0.0):
    return (r * math.cos(a), r * math.sin(a), z)


rad = math.radians


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
    "T": (0.70, [[(0.0, 1.0), (0.70, 1.0)], [(0.35, 1.0), (0.35, 0.0)]]),
    "H": (0.65, [[(0.0, 0.0), (0.0, 1.0)], [(0.65, 0.0), (0.65, 1.0)], [(0.0, 0.5), (0.65, 0.5)]]),
    "R": (0.65, [[(0.0, 0.0), (0.0, 1.0), (0.65, 0.76), (0.0, 0.52), (0.65, 0.0)]]),
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


def key_frieze(bm, y, z, x0, x1):
    """Greek-key band facing -Y (same as the entrance lintel)."""
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


# ------------------------- PLACEMENT / GAMEPLAY DATA -------------------------
# Place() lets a prop be modelled at the origin and then moved/rotated as a
# unit. Lights and seats registered inside a Place() follow the same transform.
XF = []
LIGHTS = []      # (world point, range in studs, brightness, shadows)
SEATS = []       # (world point of seat top, facing vector, kind)


class Place:
    def __init__(self, M, *bms):
        self.M, self.bms = M, bms

    def __enter__(self):
        self.n = [len(b.verts) for b in self.bms]
        XF.append(self.M)
        return self

    def __exit__(self, *exc):
        XF.pop()
        for b, n in zip(self.bms, self.n):
            b.verts.ensure_lookup_table()
            for i in range(n, len(b.verts)):
                b.verts[i].co = self.M @ b.verts[i].co
        return False


def world(p):
    v = Vector(p)
    for M in reversed(XF):
        v = M @ v
    return v


def add_light(p, range_studs=16, brightness=1.5, shadows=False):
    LIGHTS.append((world(p), range_studs, brightness, shadows))


def add_seat(p, face_angle, kind="furniture"):
    a = Vector(p)
    b = a + Vector((math.cos(face_angle), math.sin(face_angle), 0))
    pa, pb = world(a), world(b)
    SEATS.append((pa, pb - pa, kind))


# ------------------------------ WALLS ----------------------------------------
def wall(bm, a, b, z0, z1, t, color, openings=(), ext=0.0, frames=True, frame_color=None):
    """Straight wall on the plan line a->b, thickness t, from z0 to z1.
    openings = (u_centre, width, z_bottom, z_top), u measured from a along the wall.
    Openings may share the same u (e.g. a slit window under a big window)."""
    ax, ay = a
    bx, by = b
    L = math.hypot(bx - ax, by - ay)
    ang = math.atan2(by - ay, bx - ax)
    ux, uy = (bx - ax) / L, (by - ay) / L
    holes = [(uc - w / 2, uc + w / 2, zb, zt) for uc, w, zb, zt in openings]
    cuts = sorted({-ext, L + ext} | {h[0] for h in holes} | {h[1] for h in holes})
    for u0, u1 in zip(cuts[:-1], cuts[1:]):
        if u1 - u0 < 1e-4:
            continue
        um = (u0 + u1) / 2
        x, y = ax + ux * um, ay + uy * um
        gaps = sorted((h[2], h[3]) for h in holes if h[0] < um < h[1])
        z = z0
        for g0, g1 in gaps + [(z1, z1)]:
            g0 = min(g0, z1)
            if g0 - z > 1e-4:
                box(bm, (x, y, (z + g0) / 2), (u1 - u0, t, g0 - z), color, rot=ang)
            z = max(z, min(g1, z1))
    if not frames:
        return
    fc = C["MARBLE"] if frame_color is None else frame_color
    for u0, u1, zb, zt in holes:
        um, w = (u0 + u1) / 2, u1 - u0
        x, y = ax + ux * um, ay + uy * um
        if zb > z0 + 0.01:                                      # window: sill + lintel
            box(bm, (x, y, zb - 0.06), (w + 0.3, t + 0.14, 0.12), fc, rot=ang)
        else:                                                   # door: two jambs
            for s in (-1, 1):
                jx, jy = ax + ux * (um + s * (w / 2 + 0.1)), ay + uy * (um + s * (w / 2 + 0.1))
                box(bm, (jx, jy, (zb + zt) / 2), (0.2, t + 0.14, zt - zb), fc, rot=ang)
        if zt + 0.26 < z1:
            box(bm, (x, y, zt + 0.13), (w + 0.5, t + 0.12, 0.26), fc, rot=ang)


def wall_full(bm, a, b, z0, z1, t, openings=(), ext=0.0, band=True):
    """Stone wall with a dark base course (gapped for doors) and a light top band."""
    wall(bm, a, b, z0, z1, t, C["STONE"], openings, ext)
    doors = [o for o in openings if o[2] <= z0 + 0.01]
    wall(bm, a, b, z0, z0 + 0.4, t + 0.14, C["STONE_DARK"], doors, ext + 0.07, frames=False)
    if band:
        wall(bm, a, b, z1 - 0.3, z1, t + 0.1, C["STONE_LIGHT"], (), ext + 0.05, frames=False)


# ------------------------------ FINISH / OBJECT ------------------------------
def finish(name, bm, trim=True):
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
    return obj


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


# =============================================================================
#                               LAYOUT CONSTANTS
# =============================================================================
R_ORCH = 9.0            # paved orchestra radius
R_WALK = 10.5           # front walkway outer edge = first seating row
ROW_D, RISE = 1.1, 0.45 # row depth / height (aisle steps are half of RISE)
LOWER_ROWS, UPPER_ROWS = 10, 8
R_DIAZ0 = R_WALK + LOWER_ROWS * ROW_D          # 21.5  cross-walk
Z_DIAZ = LOWER_ROWS * RISE                     # 4.5
R_UP0 = R_DIAZ0 + 2.5                          # 24.0
R_PROM0 = R_UP0 + UPPER_ROWS * ROW_D           # 32.8  top promenade
Z_TOP = Z_DIAZ + UPPER_ROWS * RISE             # 8.1
R_PROM1 = 37.0
R_CREST, R_FOOT = 40.0, 58.0                   # berm crest / foot
A_MIN, A_MAX = rad(172), rad(368)              # seating sweep (196 deg, opens toward +Y)
AISLE_W, CENTER_AISLE_W = 1.6, 2.4
LOWER_AISLES = [200, 235, 270, 305, 340]
UPPER_AISLES = [200, 235, 252.5, 270, 287.5, 305, 340]
END_WALL_T = 0.8

STAGE_Y0, STAGE_Y1, BACK_Y1 = 10.5, 19.0, 24.0
STAGE_H, STAGE_TOP, STAGE_HW = 1.45, 1.52, 17.5
SKENE_HW, SKENE_T = 17.5, 1.2

F = Z_TOP + 0.3                                # lodge + tower ground floor
LODGE_YF, LODGE_YR, LODGE_HX = -39.5, -50.5, 9.0
LODGE_WALL_T, LODGE_WALL_H = 0.5, 5.3
TX, TY = -15.3, -45.0                          # lookout tower centre
TOWER_R, TOWER_T = 4.8, 0.55                   # octagon circumradius / wall thickness
L1, L2 = F + 4.4, F + 8.8                      # watch room / roof deck
R_STAIR, R_FLOOR = 2.2, 4.3
STEP_RISE = 4.4 / 16
A0 = rad(22.5)                                 # spiral starts just left of the door


def in_sweep(a):
    a = a % math.tau
    return a >= A_MIN or a <= A_MAX - math.tau


def berm_noise(r, a):
    return 0.18 * math.sin(r * 0.9 + a * 7.0) * math.sin(a * 5.0) if R_CREST < r < R_FOOT else 0.0


def berm_z(x, y):
    r, a = math.hypot(x, y), math.atan2(y, x)
    if r < R_PROM1 or not in_sweep(a):
        return 0.0
    if r <= R_CREST:
        return Z_TOP
    return max(0.0, Z_TOP * (R_FOOT - r) / (R_FOOT - R_CREST) + berm_noise(r, a))


# =============================================================================
#                               SHARED PROPS
# =============================================================================
def brazier(bm, glow, x, y, z, s=1.0, light=True):
    """The entrance brazier, scaled."""
    frustum(bm, T((x, y, z)), 0.50 * s, 0.40 * s, 0.30 * s, C["STONE_DARK"], segs=8)
    frustum(bm, T((x, y, z + 0.30 * s)), 0.20 * s, 0.14 * s, 1.30 * s, C["BRONZE_DARK"], segs=8)
    frustum(bm, T((x, y, z + 1.60 * s)), 0.16 * s, 0.55 * s, 0.50 * s, C["BRONZE"], segs=8)
    frustum(glow, T((x, y, z + 2.10 * s)), 0.38 * s, 0.0, 0.95 * s, C["GLOW"], segs=6)
    if light:
        add_light((x, y, z + 2.6 * s), 22 * s, 2.0)


def banner(bm, s=1.0, rod=1.5):
    """Entrance pillar banner at the origin: top of the cloth at z=0, facing -Y."""
    prism(bm, [(-0.55, 0), (0.55, 0), (0.55, -2.4), (0, -1.95), (-0.55, -2.4)], (0, 0, 0), s, 0.08, C["MAROON"])
    box(bm, (0, 0, 0.05 * s), (rod * s, 0.12, 0.09), C["BRONZE"])
    for sx in (-1, 1):
        blob(bm, (sx * rod * s / 2 + sx * 0.03, 0, 0.05 * s), (0.10, 0.10, 0.10), C["BRONZE"], segs=6, rings=3)
    emblem(bm, (0, -0.07, -1.0 * s), 0.42 * s, C["CREAM"], C["MAROON"], t=0.05)


def sconce(bm, glow):
    """Wall torch at the origin, wall plane y=0, sticking out toward +Y."""
    box(bm, (0, 0.025, 0), (0.18, 0.05, 0.36), C["BRONZE_DARK"])
    beam(bm, (0, 0.05, -0.12), (0, 0.32, 0.05), 0.035, 0.03, C["BRONZE"], segs=5)
    frustum(bm, T((0, 0.32, 0.03)), 0.06, 0.12, 0.14, C["BRONZE"], segs=6)
    frustum(glow, T((0, 0.32, 0.17)), 0.09, 0.0, 0.32, C["GLOW"], segs=5)
    add_light((0, 0.45, 0.35), 14, 1.3)


def table(bm, L, W, H=0.8):
    box(bm, (0, 0, H - 0.04), (L, W, 0.08), C["WOOD_LIGHT"], ch=0.02)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(bm, (sx * (L / 2 - 0.15), sy * (W / 2 - 0.12), (H - 0.08) / 2), (0.1, 0.1, H - 0.08), C["WOOD"])
    for sy in (-1, 1):
        box(bm, (0, sy * (W / 2 - 0.12), H - 0.16), (L - 0.3, 0.05, 0.1), C["WOOD"])


def bench(bm, L, H=0.45, W=0.42):
    box(bm, (0, 0, H - 0.04), (L, W, 0.08), C["WOOD_LIGHT"], ch=0.02)
    n = 3 if L > 3 else 2
    for i in range(n):
        x = -L / 2 + 0.3 + (L - 0.6) * i / (n - 1)
        box(bm, (x, 0, (H - 0.08) / 2), (0.08, W - 0.06, H - 0.08), C["WOOD"])


def klismos(bm):
    """Greek klismos chair at the origin, facing +Y, seat top ~0.52."""
    box(bm, (0, 0, 0.46), (0.5, 0.5, 0.06), C["WOOD_LIGHT"])
    box(bm, (0, 0.01, 0.515), (0.44, 0.44, 0.05), C["MAROON"])
    for sx in (-1, 1):
        beam(bm, (sx * 0.21, 0.21, 0.44), (sx * 0.26, 0.33, 0.0), 0.03, 0.025, C["WOOD"], segs=4)
        beam(bm, (sx * 0.21, -0.21, 0.44), (sx * 0.26, -0.35, 0.0), 0.03, 0.025, C["WOOD"], segs=4)
        beam(bm, (sx * 0.21, -0.21, 0.44), (sx * 0.23, -0.33, 0.95), 0.03, 0.025, C["WOOD"], segs=4)
    box(bm, (0, -0.32, 0.86), (0.52, 0.06, 0.17), C["WOOD_LIGHT"])
    add_seat((0, 0, 0.54), math.pi / 2)


def amphora(bm, h=0.9, color=None):
    s = h / 0.9
    col = C["TERRACOTTA"] if color is None else color
    frustum(bm, T((0, 0, 0)), 0.12 * s, 0.08 * s, 0.06 * s, col, segs=8)
    frustum(bm, T((0, 0, 0.06 * s)), 0.08 * s, 0.26 * s, 0.30 * s, col, segs=8)
    frustum(bm, T((0, 0, 0.36 * s)), 0.26 * s, 0.20 * s, 0.25 * s, col, segs=8)
    frustum(bm, T((0, 0, 0.42 * s)), 0.255 * s, 0.25 * s, 0.07 * s, C["TERRACOTTA_DARK"], segs=8)
    frustum(bm, T((0, 0, 0.61 * s)), 0.20 * s, 0.07 * s, 0.12 * s, col, segs=8)
    frustum(bm, T((0, 0, 0.73 * s)), 0.07 * s, 0.06 * s, 0.12 * s, col, segs=8)
    frustum(bm, T((0, 0, 0.85 * s)), 0.09 * s, 0.09 * s, 0.05 * s, col, segs=8)
    for sx in (-1, 1):
        beam(bm, (sx * 0.06 * s, 0, 0.82 * s), (sx * 0.19 * s, 0, 0.64 * s), 0.025 * s, 0.025 * s, col, segs=4)


def crate(bm, s=0.7, color=None):
    box(bm, (0, 0, s / 2), (s, s, s), C["WOOD"] if color is None else color, ch=0.03)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(bm, (sx * (s / 2 - 0.03), sy * (s / 2 - 0.03), s / 2), (0.08, 0.08, s + 0.01), C["WOOD_LIGHT"])
    box(bm, (0, 0, s / 2), (s + 0.02, s + 0.02, 0.08), C["WOOD_LIGHT"])


def chest(bm):
    box(bm, (0, 0, 0.23), (1.0, 0.55, 0.46), C["WOOD"], ch=0.03)
    box(bm, (0, 0, 0.52), (1.04, 0.59, 0.14), C["WOOD_LIGHT"], ch=0.03)
    for sx in (-1, 1):
        box(bm, (sx * 0.3, 0, 0.3), (0.07, 0.61, 0.61), C["BRONZE"])
    box(bm, (0, -0.3, 0.42), (0.14, 0.04, 0.16), C["BRONZE_DARK"])


def scroll(bm, x, y, z, L=0.45, rot=0.0):
    dx, dy = math.cos(rot) * L / 2, math.sin(rot) * L / 2
    beam(bm, (x - dx, y - dy, z), (x + dx, y + dy, z), 0.055, 0.055, C["CREAM"], segs=6)
    for s in (-1, 1):
        beam(bm, (x + s * dx, y + s * dy, z), (x + s * dx * 1.12, y + s * dy * 1.12, z), 0.03, 0.03, C["MAROON"], segs=4)


def shelf(bm, W=2.0, H=2.0, D=0.4):
    """Open shelf at the origin, back against y=-D/2, front toward +Y."""
    for sx in (-1, 1):
        box(bm, (sx * W / 2, 0, H / 2), (0.08, D, H), C["WOOD"])
    for z in (0.08, 0.68, 1.28, 1.88):
        box(bm, (0, 0, z), (W, D, 0.05), C["WOOD_LIGHT"])
        if z > 1.8:
            continue
        x = -W / 2 + 0.25
        while x < W / 2 - 0.2:
            pick = rng.random()
            if pick < 0.45:
                scroll(bm, x, 0, z + 0.08, 0.35, rot=math.pi / 2 + rng.uniform(-0.2, 0.2))
                x += 0.16
            elif pick < 0.8:
                amphora_small(bm, x, 0, z + 0.025)
                x += 0.3
            else:
                frustum(bm, T((x, 0, z + 0.025)), 0.07, 0.09, 0.12, C["BRONZE"], segs=6)
                x += 0.22


def amphora_small(bm, x, y, z):
    h = rng.uniform(0.32, 0.45)
    with Place(T((x, y, z)), bm):
        amphora(bm, h, rng.choice([C["TERRACOTTA"], C["TERRACOTTA"], C["STONE_DARK"]]))


def shield(bm, M, r=0.45):
    """Round hoplite shield; M points local +Z out of the shield face."""
    frustum(bm, M, r, r, 0.07, C["BRONZE"], segs=14)
    frustum(bm, M @ T((0, 0, 0.07)), r * 0.84, r * 0.84, 0.02, C["MAROON"], segs=14)
    ring(bm, M @ T((0, 0, 0.09)), r * 0.5, r * 0.4, 0.02, C["CREAM"], segs=12)


def weapon_rack(bm, W=2.0):
    """Spear rack at the origin, front toward +Y."""
    for sx in (-1, 1):
        box(bm, (sx * W / 2, 0, 0.95), (0.1, 0.1, 1.9), C["WOOD"])
        box(bm, (sx * W / 2, 0, 0.04), (0.2, 0.45, 0.08), C["WOOD"])
    for z in (0.35, 1.55):
        box(bm, (0, 0, z), (W, 0.08, 0.08), C["WOOD_LIGHT"])
    for i in range(5):
        x = -W / 2 + 0.3 + i * (W - 0.6) / 4
        beam(bm, (x, 0.07, 0.05), (x, 0.0, 2.25), 0.03, 0.03, C["WOOD"], segs=4)
        beam(bm, (x, 0.0, 2.25), (x, -0.005, 2.55), 0.05, 0.0, C["BRONZE"], segs=4)
    for sx in (-1, 1):
        shield(bm, T((sx * 0.5, 0.12, 0.95)) @ ROT_XN90, 0.42)


def rug(bm, L, W, z=0.065):
    box(bm, (0, 0, z - 0.015), (L, W, 0.03), C["MAROON"])
    for sy in (-1, 1):
        box(bm, (0, sy * (W / 2 - 0.12), z - 0.01), (L - 0.12, 0.1, 0.03), C["CREAM"])
    for sx in (-1, 1):
        box(bm, (sx * (L / 2 - 0.12), 0, z - 0.01), (0.1, W - 0.12, 0.03), C["CREAM"])


def chandelier(bm, glow, hang_z, low_z):
    """Bronze ring of candles at the origin (x,y), hanging from hang_z down to low_z."""
    ring(bm, T((0, 0, low_z)), 0.85, 0.72, 0.07, C["BRONZE"], segs=16)
    for i in range(3):
        a = math.tau * i / 3
        beam(bm, (0.78 * math.cos(a), 0.78 * math.sin(a), low_z + 0.07), (0, 0, hang_z - 0.4), 0.02, 0.02, C["BRONZE_DARK"], 4)
    beam(bm, (0, 0, hang_z - 0.4), (0, 0, hang_z), 0.03, 0.03, C["BRONZE_DARK"], 4)
    for i in range(8):
        a = math.tau * (i + 0.5) / 8
        x, y = 0.785 * math.cos(a), 0.785 * math.sin(a)
        frustum(bm, T((x, y, low_z + 0.07)), 0.04, 0.04, 0.16, C["CREAM"], segs=5)
        blob(glow, (x, y, low_z + 0.29), (0.04, 0.04, 0.07), C["GLOW"], segs=5, rings=3)
    add_light((0, 0, low_z + 0.2), 18, 1.6, shadows=True)


def campfire(bm, glow, r, flames, logs=7):
    """Logs and flames sitting on z=0 inside a basin of radius r."""
    for i in range(logs):
        a = i * 2.399
        rr = r * (0.3 + (i % 3) * 0.12)
        beam(bm, (rr * math.cos(a), rr * math.sin(a), 0.05),
             (-0.25 * rr * math.cos(a), -0.25 * rr * math.sin(a), 0.35 * r), 0.09 * r, 0.08 * r, C["WOOD"], segs=5)
    for x, y, h, fr in flames:
        frustum(glow, T((x * r, y * r, 0.1)), fr * r, 0.0, h * r, C["GLOW"], segs=6)


def cypress(bm, x, y, z, h):
    beam(bm, (x, y, z - 0.2), (x, y, z + 0.9), 0.2, 0.16, C["WOOD"], segs=5)
    frustum(bm, T((x, y, z + 0.5)), 0.95 * h / 8, 0.0, h, C["CYPRESS"], segs=7, jitter=0.1)
    frustum(bm, T((x + 0.15, y - 0.1, z + 0.9)), 0.75 * h / 8, 0.0, h * 0.8, C["LEAF_DARK"], segs=6, jitter=0.1)


def olive_tree(bm, x, y, z, s=1.0):
    p0 = (x, y, z - 0.1)
    p1 = (x + 0.3 * s, y - 0.2 * s, z + 1.2 * s)
    p2 = (x - 0.2 * s, y + 0.15 * s, z + 2.1 * s)
    beam(bm, p0, p1, 0.24 * s, 0.17 * s, C["WOOD"], segs=6)
    beam(bm, p1, p2, 0.17 * s, 0.12 * s, C["WOOD"], segs=6)
    beam(bm, p1, (x + 0.9 * s, y, z + 2.0 * s), 0.12 * s, 0.08 * s, C["WOOD"], segs=5)
    for dx, dy, dz, rr in ((0, 0, 2.5, 1.2), (0.9, 0.2, 2.2, 0.9), (-0.7, 0.3, 2.3, 0.9), (0.2, -0.6, 2.8, 0.8)):
        blob(bm, (x + dx * s, y + dy * s, z + dz * s), (rr * s, rr * 0.9 * s, rr * 0.6 * s),
             rng.choice([C["OLIVE_LEAF"], C["OLIVE_LEAF"], C["LEAF_MID"]]), segs=7, rings=4, jitter=0.15)


# Entrance pillar, generalised to any position (used for the side gates and the
# stage pylons so every major opening reads like the camp's main gate).
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


def build_pillar(bm, x, Y, vines):
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
    for vx, z0, z1, ph in vines:
        vine(bm, x + vx, fy - 0.04, z0, z1, ph)
    with Place(T((x, fy - 0.07, 5.95)), bm):
        banner(bm)


# =============================================================================
#                            1) SEATING (CAVEA)
# =============================================================================
SEAT_SPOTS = []    # (radius of seat line, a0, a1, seat-top z) for props + Roblox seats


def aisle_gaps(aisles, r_mid):
    gaps = []
    for a in sorted(aisles):
        w = CENTER_AISLE_W if a == 270 else AISLE_W
        h = (w / 2) / r_mid
        gaps.append((rad(a) - h, rad(a) + h, a))
    return gaps


def build_tiers(bm, rows, r_start, z_start, aisles):
    for k in range(rows):
        r0 = r_start + k * ROW_D
        r1 = r0 + ROW_D
        top = z_start + (k + 1) * RISE
        rm = r0 + ROW_D / 2
        gaps = aisle_gaps(aisles, rm)
        cursor, sections = A_MIN, []
        for g0, g1, _ in gaps:
            sections.append((cursor, g0))
            cursor = g1
        sections.append((cursor, A_MAX))
        for a0, a1 in sections:
            wedge(bm, r0, r1, a0, a1, 0.0, top, C["STONE"])
            pad = 0.05 / r0
            # raised seat slab on the front half of each row, footwell behind it
            wedge(bm, r0 + 0.03, r0 + 0.6, a0 + pad, a1 - pad, top, top + 0.08, C["STONE_LIGHT"])
            SEAT_SPOTS.append((r0 + 0.32, a0 + pad, a1 - pad, top + 0.08))
        for g0, g1, a in gaps:                                  # two half-height steps per row
            wedge(bm, r0, rm, g0, g1, 0.0, top - RISE / 2, C["MARBLE"], segs=1)
            wedge(bm, rm, r1, g0, g1, 0.0, top, C["STONE_LIGHT"], segs=1)
            if a == 270:                                        # ceremonial runner up the axis
                h = 0.55 / rm
                wedge(bm, r0, rm, rad(270) - h, rad(270) + h, top - RISE / 2, top - RISE / 2 + 0.03, C["MAROON"], segs=1)
                wedge(bm, rm, r1, rad(270) - h, rad(270) + h, top, top + 0.03, C["MAROON"], segs=1)


def ring_walk(bm, r0, r1, z, pieces, kerb=True):
    """Solid paved walkway following the seating sweep, alternating stone colours."""
    for i in range(pieces):
        a0 = A_MIN + (A_MAX - A_MIN) * i / pieces
        a1 = A_MIN + (A_MAX - A_MIN) * (i + 1) / pieces
        wedge(bm, r0, r1, a0, a1, 0.0, z, C["STONE_LIGHT"] if i % 2 else C["STONE"])
    if kerb:
        wedge(bm, r1 - 0.25, r1, A_MIN, A_MAX, z, z + 0.06, C["MARBLE"], max_len=2.0)
    h = 0.55 / ((r0 + r1) / 2)
    wedge(bm, r0, r1 - 0.25, rad(270) - h, rad(270) + h, z, z + 0.03, C["MAROON"], segs=1)


def throne(bm, big=False):
    """Marble seat of honour at the origin, facing +Y."""
    w = 0.95 if big else 0.8
    box(bm, (0, 0, 0.25), (w, 0.62, 0.5), C["MARBLE"], ch=0.04)
    box(bm, (0, -0.27, 0.8), (w, 0.14, 1.1 if big else 0.95), C["MARBLE"], ch=0.03)
    for sx in (-1, 1):
        box(bm, (sx * (w / 2 - 0.05), 0.02, 0.66), (0.12, 0.55, 0.12), C["STONE_LIGHT"], ch=0.02)
        box(bm, (sx * (w / 2 - 0.05), 0.24, 0.12), (0.16, 0.18, 0.24), C["BRONZE"], ch=0.02)
    box(bm, (0, 0.02, 0.53), (w - 0.2, 0.5, 0.06), C["MAROON"])
    if big:
        box(bm, (0, -0.27, 1.4), (w + 0.1, 0.18, 0.1), C["BRONZE"])
        with Place(T((0, -0.18, 1.12)) @ Rz(math.pi), bm):
            emblem(bm, (0, 0, 0), 0.18, C["BRONZE"], C["MAROON"], t=0.04)
    add_seat((0, 0.02, 0.56), math.pi / 2, "throne")


def build_cavea(bm_lo, bm_up, bm_props, glow):
    build_tiers(bm_lo, LOWER_ROWS, R_WALK, 0.0, LOWER_AISLES)
    ring_walk(bm_lo, R_DIAZ0, R_UP0, Z_DIAZ, 14)                       # diazoma cross-walk
    build_tiers(bm_up, UPPER_ROWS, R_UP0, Z_DIAZ, UPPER_AISLES)
    ring_walk(bm_up, R_PROM0, R_PROM1, Z_TOP, 26)                      # top promenade

    # Sloped retaining walls (analemmata) close both ends of the seating and the berm.
    poly = [(R_WALK - 0.5, 0), (R_FOOT, 0), (R_FOOT, 0.3), (R_CREST, Z_TOP + 0.9),
            (R_PROM0, Z_TOP + 0.9), (R_WALK, 1.3), (R_WALK - 0.5, 1.3)]
    for ang, side in ((A_MIN, -1), (A_MAX, 1)):
        yoff = side * END_WALL_T / 2
        with Place(Rz(ang), bm_up, bm_props, glow):
            prism(bm_up, poly, (0, yoff, 0), 1.0, END_WALL_T, C["STONE"])
            # marble coping along the sloped top
            for (x0, z0), (x1, z1) in ((poly[5], poly[4]), (poly[4], poly[3])):
                beam(bm_up, (x0, yoff, z0 + 0.04), (x1, yoff, z1 + 0.04), 0.5, 0.5, C["MARBLE"], segs=4)
            brazier(bm_props, glow, R_WALK + 0.2, yoff, 1.3 + 0.4, 0.9)
            brazier(bm_props, glow, R_PROM0 + 0.6, yoff, Z_TOP + 0.9 + 0.4, 0.9)

    # Seats of honour (prohedria) in the two central wedges, facing the fire.
    for lo, hi in ((235, 270), (270, 305)):
        r = 9.95
        h0 = (AISLE_W / 2 + 0.5) / r if lo == 235 else (CENTER_AISLE_W / 2 + 0.5) / r
        h1 = (CENTER_AISLE_W / 2 + 0.5) / r if lo == 235 else (AISLE_W / 2 + 0.5) / r
        a0, a1 = rad(lo) + h0, rad(hi) - h1
        for i in range(4):
            a = a0 + (a1 - a0) * (i + 0.5) / 4
            big = (lo == 235 and i == 3) or (lo == 270 and i == 0)
            with Place(T(polar(r, a, 0.12)) @ Rz(a + math.pi / 2), bm_lo):
                throne(bm_lo, big)


# =============================================================================
#                      2) ORCHESTRA + CEREMONIAL CAMPFIRE
# =============================================================================
def build_orchestra(bm, glow, props):
    for r0, r1, n in ((2.1, 4.2, 20), (4.2, 6.6, 28), (6.6, R_ORCH, 36)):
        for i in range(n):
            a0, a1 = math.tau * i / n, math.tau * (i + 1) / n
            wedge(bm, r0, r1, a0, a1, 0.0, 0.12, C["STONE_LIGHT"] if (i + n) % 2 else C["STONE"], segs=1)
    for r in (4.2, 6.6):                                       # bronze inlay rings
        ring(bm, T((0, 0, 0.12)), r + 0.06, r - 0.06, 0.02, C["BRONZE"], segs=40)
    ring(bm, T((0, 0, 0)), R_ORCH + 0.3, R_ORCH, 0.04, C["STONE_DARK"], segs=48)   # drainage channel
    wedge(bm, R_ORCH + 0.3, R_WALK, 0, math.tau, 0.0, 0.12, C["STONE_LIGHT"], max_len=2.0)
    # paved forecourt between the orchestra and the stage
    for gx in range(12):
        for gy in range(4):
            x = -16.5 + gx * 3.0
            y = 1.3125 + gy * 2.625
            box(bm, (x, y, 0.04), (2.96, 2.59, 0.08), C["STONE"] if (gx + gy) % 2 else C["STONE_LIGHT"])
    # axis runner from the orchestra edge into the seating
    box(bm, (0, -(R_ORCH + R_WALK) / 2 - 0.15, 0.135), (1.1, R_WALK - R_ORCH + 0.3, 0.03), C["MAROON"])

    # Ceremonial hearth: dark foundation, light rim, rim blocks, logs, big fire.
    frustum(bm, T((0, 0, 0)), 2.15, 2.05, 0.35, C["STONE_DARK"], segs=16)
    ring(bm, T((0, 0, 0.35)), 1.85, 1.35, 0.35, C["STONE_LIGHT"], segs=16)
    frustum(bm, T((0, 0, 0.35)), 1.36, 1.36, 0.12, C["CHARCOAL"], segs=16)
    for i in range(12):
        a = math.tau * i / 12
        box(bm, (1.6 * math.cos(a), 1.6 * math.sin(a), 0.79), (0.62, 0.44, 0.18),
            C["MARBLE"] if i % 3 == 0 else C["STONE"], rot=a, ch=0.04)
    with Place(T((0, 0, 0.47)), bm, glow):
        campfire(bm, glow, 1.3, [(-0.27, 0.04, 1.6, 0.30), (0.17, -0.09, 2.0, 0.34), (0.37, 0.12, 1.4, 0.27),
                                 (-0.04, 0.29, 1.3, 0.24), (-0.32, -0.19, 1.1, 0.23), (0.0, 0.0, 2.4, 0.22)])
    add_light((0, 0, 2.2), 60, 3.0, shadows=True)

    # Story stones around the fire, on the audience side
    for a in (200, 235, 305, 340):
        x, y, _ = polar(4.7, rad(a))
        frustum(props, T((x, y, 0.12)), 0.48, 0.44, 0.38, C["STONE_LIGHT"], segs=10)
        frustum(props, T((x, y, 0.5)), 0.53, 0.53, 0.1, C["STONE"], segs=10)
        add_seat((x, y, 0.6), rad(a) + math.pi, "stool")


# =============================================================================
#                          3) STAGE + SKENE FACADE
# =============================================================================
MASK_COMEDY = [(-0.35, 0.45), (0.35, 0.45), (0.42, 0.0), (0.25, -0.45), (0.0, -0.58), (-0.25, -0.45), (-0.42, 0.0)]


def mask(bm, x, y, z, happy):
    prism(bm, MASK_COMEDY, (x, y, z), 1.0, 0.12, C["CREAM"])
    fy = y - 0.08
    for sx in (-1, 1):
        prism(bm, [(-0.1, -0.05), (0.1, -0.05), (0.1, 0.05), (-0.1, 0.05)],
              (x + sx * 0.16, fy, z + 0.12 + (0.0 if happy else -0.03)), 1.0, 0.05, C["CHARCOAL"])
    if happy:
        mouth = [(-0.2, 0.0), (0.2, 0.0), (0.12, -0.12), (-0.12, -0.12)]
    else:
        mouth = [(-0.12, 0.0), (0.12, 0.0), (0.2, -0.12), (-0.2, -0.12)]
    prism(bm, mouth, (x, fy, z - 0.18), 1.0, 0.05, C["CHARCOAL"])
    box(bm, (x, y + 0.04, z + 0.62), (0.1, 0.05, 0.25), C["BRONZE"])


def build_stage(bm, props, glow):
    depth = BACK_Y1 - STAGE_Y0
    yc = (STAGE_Y0 + BACK_Y1) / 2
    box(bm, (0, yc, (STAGE_H - 0.02) / 2), (STAGE_HW * 2, depth, STAGE_H - 0.02), C["STONE"], ch=0.06)
    box(bm, (0, yc, 0.2), (STAGE_HW * 2 + 0.2, depth + 0.2, 0.4), C["STONE_DARK"], ch=0.05)
    for i in range(17):                                         # plank floor
        y = STAGE_Y0 + 0.35 + i * 0.5
        box(bm, (0, y, STAGE_H + 0.025), (STAGE_HW * 2 - 0.3, 0.49, 0.07), C["WOOD"] if i % 2 else C["WOOD_LIGHT"])
    box(bm, (0, STAGE_Y0 + 0.08, STAGE_H + 0.02), (STAGE_HW * 2 + 0.1, 0.3, 0.14), C["MARBLE"])
    key_frieze(bm, STAGE_Y0 - 0.03, 0.85, -15.75, 15.75)

    # Stairs from the orchestra: wide centre flight + two side flights
    for xc, w in ((0.0, 6.0), (-11.0, 3.0), (11.0, 3.0)):
        for i in range(4):
            top = STAGE_H - (STAGE_H / 5) * (i + 1)
            box(bm, (xc, STAGE_Y0 - 0.2 - 0.4 * i, top / 2), (w, 0.42, top), C["STONE_LIGHT"] if i % 2 else C["MARBLE"])

    # Herald's podium (bema) - the focal point for announcements
    frustum(bm, T((0, 12.9, STAGE_TOP)) @ Rz(math.pi / 8), 1.35, 1.25, 0.22, C["STONE_LIGHT"], segs=8)
    frustum(bm, T((0, 12.9, STAGE_TOP + 0.22)) @ Rz(math.pi / 8), 1.05, 1.0, 0.18, C["MARBLE"], segs=8)
    ring(bm, T((0, 12.9, STAGE_TOP + 0.4)) @ Rz(math.pi / 8), 1.03, 0.93, 0.03, C["BRONZE"], segs=8)
    beam(bm, (0, 12.3, STAGE_TOP + 0.4), (0, 12.3, STAGE_TOP + 1.45), 0.07, 0.06, C["BRONZE"], segs=6)
    box(bm, (0, 12.3, STAGE_TOP + 1.5), (0.8, 0.5, 0.07), C["BRONZE_DARK"])
    scroll(props, 0, 12.3, STAGE_TOP + 1.58, 0.5)

    # Skene wall with a grand central door and two side doors
    z0 = STAGE_H
    wall(bm, (-SKENE_HW, STAGE_Y1 + SKENE_T / 2), (SKENE_HW, STAGE_Y1 + SKENE_T / 2), z0, 8.6, SKENE_T, C["STONE"],
         [(SKENE_HW, 4.0, z0, z0 + 5.6), (SKENE_HW - 8, 2.6, z0, z0 + 4.0), (SKENE_HW + 8, 2.6, z0, z0 + 4.0)])
    # engaged columns
    for x in (-16.2, -13.1, -10.6, -5.4, -2.9, 2.9, 5.4, 10.6, 13.1, 16.2):
        y = STAGE_Y1 - 0.45
        box(bm, (x, y, STAGE_TOP + 0.15), (1.1, 1.1, 0.3), C["STONE_LIGHT"], ch=0.04)
        frustum(bm, T((x, y, STAGE_TOP + 0.3)), 0.52, 0.44, 0.2, C["MARBLE"], segs=12)
        frustum(bm, T((x, y, STAGE_TOP + 0.5)), 0.42, 0.36, 6.3, C["STONE_LIGHT"], segs=12)
        frustum(bm, T((x, y, 8.3)), 0.36, 0.56, 0.18, C["MARBLE"], segs=12)
        box(bm, (x, y, 8.5), (1.2, 1.2, 0.2), C["MARBLE"], ch=0.03)
        frustum(bm, T((x, y, 8.12)), 0.385, 0.385, 0.1, C["BRONZE"], segs=12)
    # entablature, Greek key, cornice
    box(bm, (0, 19.15, 8.95), (SKENE_HW * 2 + 0.4, 2.3, 0.7), C["STONE_LIGHT"], ch=0.05)
    key_frieze(bm, 17.97, 8.95, -17.0, 17.0)
    box(bm, (0, 19.1, 9.45), (SKENE_HW * 2 + 1.2, 2.6, 0.3), C["MARBLE"], ch=0.05)
    # central pediment with the maroon tympanum and bull crest
    prism(bm, [(-7.0, 0), (7.0, 0), (0, 2.9)], (0, 19.4, 9.6), 1.0, 1.2, C["STONE_LIGHT"])
    prism(bm, [(-5.6, 0.18), (5.6, 0.18), (0, 2.4)], (0, 18.78, 9.6), 1.0, 0.06, C["MAROON"])
    emblem(bm, (0, 18.70, 10.5), 0.75, C["CREAM"], C["MAROON"], t=0.08)
    for sx in (-1, 1):
        beam(bm, (sx * 7.3, 19.4, 9.55), (0, 19.4, 12.62), 0.2, 0.2, C["MARBLE"], segs=4)
        blob(bm, (sx * 7.0, 19.4, 9.85), (0.3, 0.3, 0.3), C["BRONZE"], segs=6, rings=4)
    blob(bm, (0, 19.4, 12.75), (0.38, 0.38, 0.38), C["BRONZE"], segs=6, rings=4)

    # banners between the columns, masks above the side doors
    for x in (-11.85, -4.15, 4.15, 11.85):
        with Place(T((x, STAGE_Y1 - 0.08, 7.75)), bm):
            banner(bm, 1.35, rod=1.15)
    mask(bm, -8.0, STAGE_Y1 - 0.1, 6.35, True)
    mask(bm, 8.0, STAGE_Y1 - 0.1, 6.35, False)
    for x in (-9.75, 9.75, -2.35, 2.35):
        with Place(T((x, STAGE_Y1, 4.3 if abs(x) > 5 else 5.2)) @ Rz(math.pi), props, glow):
            sconce(props, glow)

    # Paraskenia: entrance-style pylons frame the stage and link back to the skene
    for sx, vines in ((-1, [(-0.8, 1.2, 5.0, 0.4), (0.85, 1.2, 3.2, 2.2)]), (1, [(0.8, 1.2, 4.4, 1.3), (-0.85, 1.2, 2.9, 3.1)])):
        build_pillar(bm, sx * 18.5, 15.0, vines)
        wall(bm, (sx * 17.9, 16.1), (sx * 17.9, BACK_Y1), 0.0, 6.0, 0.8, C["STONE"], frames=False)
        box(bm, (sx * 17.9, (16.1 + BACK_Y1) / 2, 6.1), (1.0, BACK_Y1 - 16.1, 0.25), C["STONE_LIGHT"], ch=0.03)

    # Backstage exit stairs toward camp
    for i in range(4):
        top = STAGE_H - (STAGE_H / 5) * (i + 1)
        box(bm, (0, BACK_Y1 + 0.21 + 0.42 * i, top / 2), (4.0, 0.44, top), C["STONE_LIGHT"])

    # Braziers on the forecourt
    for x in (-4.3, 4.3, -14.6, 14.6):
        brazier(props, glow, x, 9.65, 0.08, 1.0)

    # Backstage clutter: props for the next show
    with Place(T((-12.5, 22.6, STAGE_TOP)), props):
        chest(props)
    with Place(T((-10.6, 23.1, STAGE_TOP)) @ Rz(0.3), props):
        crate(props, 0.75)
    with Place(T((-10.4, 23.0, STAGE_TOP + 0.75)) @ Rz(0.9), props):
        crate(props, 0.5)
    with Place(T((11.5, 23.3, STAGE_TOP)) @ Rz(math.pi), props):
        weapon_rack(props, 1.8)
    for i, x in enumerate((13.6, 14.3, 14.0)):
        with Place(T((x, 21.0 + i * 0.6, STAGE_TOP)), props):
            amphora(props, 0.85)


# =============================================================================
#                      4) SIDE GATES (PARODOI) - "AMPHITHEATER"
# =============================================================================
def build_gate(bm, props, glow):
    """Smaller twin of the main entrance, modelled facing -Y at the origin."""
    build_pillar(bm, -4.3, 0.0, [(-0.80, 1.2, 4.8, 0.0), (0.85, 1.2, 3.0, 2.0)])
    build_pillar(bm, 4.3, 0.0, [(0.80, 1.2, 4.2, 1.0), (-0.85, 1.2, 2.6, 3.0)])
    box(bm, (0, 0, 7.72), (11.2, 2.45, 0.24), C["STONE_LIGHT"], ch=0.05)
    box(bm, (0, 0, 8.69), (10.8, 2.30, 1.70), C["STONE"], ch=0.10)
    box(bm, (0, 0, 9.66), (11.2, 2.45, 0.24), C["STONE_LIGHT"], ch=0.05)
    box(bm, (0, 0, 9.88), (11.5, 2.6, 0.20), C["STONE"], ch=0.05)
    for front, rot in ((-1.15, 0.0), (1.15, math.pi)):          # both faces are signed
        with Place(Rz(rot), bm):
            key_frieze(bm, -1.175, 8.12, -4.95, 4.95)
            box(bm, (0, -1.2, 8.92), (8.2, 0.10, 1.00), C["STONE_LIGHT"])
            for dz in (-0.53, 0.53):
                box(bm, (0, -1.21, 8.92 + dz), (8.4, 0.12, 0.06), C["BRONZE"])
            for sx in (-1, 1):
                box(bm, (sx * 4.2, -1.21, 8.92), (0.06, 0.12, 1.12), C["BRONZE"])
            text(bm, "AMPHITHEATER", (0, -1.29, 8.92), 0.55, C["BRONZE_DARK"], depth=0.08, stroke=0.18)
    box(bm, (0, 0, 10.24), (2.4, 1.2, 0.5), C["STONE_LIGHT"], ch=0.06)
    frustum(bm, T((0, 0.4, 11.25)) @ ROT_X90, 1.2, 1.2, 0.30, C["BRONZE"], segs=16)
    frustum(bm, T((0, 0.4, 11.25)) @ ROT_X90, 1.07, 1.07, 0.40, C["MAROON"], segs=16)
    emblem(bm, (0, -0.05, 11.1), 0.65, C["CREAM"], C["MAROON"], t=0.10)
    for sx in (-1, 1):
        brazier(props, glow, sx * 4.3, -2.4, 0.0, 0.9)


# =============================================================================
#                       5) LOOKOUT LODGE (overlooks the stage)
# =============================================================================
def build_lodge_shell(bm, props, glow):
    # podium (top cap separate so nothing is coplanar)
    yc, depth = (-36.8 + -51.7) / 2, 51.7 - 36.8
    box(bm, (0, yc, (F - 0.25) / 2), (20.8, depth, F - 0.25), C["STONE"], ch=0.08)
    box(bm, (0, yc, 0.3), (21.2, depth + 0.4, 0.6), C["STONE_DARK"], ch=0.06)
    box(bm, (0, yc, F - 0.125), (21.0, depth + 0.2, 0.25), C["STONE_LIGHT"], ch=0.04)
    for i in range(1, int(F)):                                  # masonry courses on the podium
        for sx in (-1, 1):
            box(bm, (sx * 10.41, yc, i * 1.0), (0.03, depth - 0.2, 0.04), C["STONE_DARK"])
        box(bm, (0, -51.71, i * 1.0), (20.6, 0.03, 0.04), C["STONE_DARK"])

    # walls: big overlook windows facing the stage, doors front/back/tower side
    hx, yf, yr, t, top = LODGE_HX, LODGE_YF, LODGE_YR, LODGE_WALL_T, F + LODGE_WALL_H
    win = lambda u, w=2.2, s=0.9, h=3.4: (u, w, F + s, F + h)
    wall_full(bm, (-hx, yf), (hx, yf), F, top, t,
              [(hx, 2.4, F, F + 3.4), win(hx - 6.8), win(hx - 3.6), win(hx + 3.6), win(hx + 6.8)], ext=t / 2)
    wall_full(bm, (-hx, yr), (hx, yr), F, top, t,
              [(hx, 2.0, F, F + 3.0), win(hx - 5.0, 1.6, 1.2, 3.0), win(hx + 5.0, 1.6, 1.2, 3.0)], ext=t / 2)
    wall_full(bm, (-hx, yf), (-hx, yr), F, top, t,
              [(yf - TY, 1.8, F, F + 3.0), win(1.7, 1.4, 1.0, 3.2), win(9.3, 1.4, 1.0, 3.2)], ext=t / 2)
    wall_full(bm, (hx, yf), (hx, yr), F, top, t,
              [win(2.5, 1.8, 1.0, 3.4), win(8.5, 1.8, 1.0, 3.4)], ext=t / 2)
    for sx in (-1, 1):                                          # eave beams close the roof line
        box(bm, (sx * hx, (yf + yr) / 2, top + 0.22), (0.7, yf - yr + 0.7, 0.45), C["STONE_LIGHT"])
    for sx in (-1, 1):                                          # corner pilasters
        for y in (yf, yr):
            box(bm, (sx * (hx + 0.05), y, (F + top) / 2), (0.75, 0.75, top - F), C["STONE_LIGHT"], ch=0.04)

    # front portico: six columns, entablature with Greek key
    for x in (-9.6, -5.8, -2.0, 2.0, 5.8, 9.6):
        y = -37.7
        box(bm, (x, y, F + 0.12), (0.95, 0.95, 0.24), C["STONE_LIGHT"], ch=0.03)
        frustum(bm, T((x, y, F + 0.24)), 0.4, 0.34, 4.0, C["MARBLE"], segs=12)
        frustum(bm, T((x, y, F + 4.24)), 0.34, 0.52, 0.18, C["MARBLE"], segs=12)
        box(bm, (x, y, F + 4.5), (1.05, 1.05, 0.2), C["STONE_LIGHT"], ch=0.03)
    box(bm, (0, -37.7, F + 4.95), (20.8, 1.1, 0.7), C["STONE_LIGHT"], ch=0.04)
    with Place(T((0, -37.15, F + 4.95)) @ Rz(math.pi), bm):
        key_frieze(bm, 0, 0, -10.0, 10.0)
    for sx in (-1, 1):                                          # portico side beams to the wall
        box(bm, (sx * 9.6, -38.6, F + 4.95), (0.6, 1.9, 0.7), C["STONE_LIGHT"])

    # rear stair down the hillside, with sloped stringer walls
    n = int(math.ceil(F / 0.3))
    rise, run, y0 = F / n, 0.42, -51.7
    for i in range(n):
        top_z = F - rise * (i + 1)
        if top_z <= 0.01:
            break
        box(bm, (0, y0 - run * (i + 0.5), top_z / 2), (3.0, run + 0.02, top_z), C["STONE_LIGHT"] if i % 2 else C["STONE"])
    y_end = y0 - run * n
    for sx in (-1, 1):
        with Place(T((sx * 1.75, 0, 0)) @ Rz(math.pi / 2), bm):
            # local x = world y, local y = world -x
            prism(bm, [(y0 + 0.2, 0), (y0 + 0.2, F + 0.7), (y_end, 0.7), (y_end, 0)], (0, 0, 0), 1.0, 0.5, C["STONE"])
    for sx in (-1, 1):
        brazier(props, glow, sx * 1.75, y_end + 0.2, 0.7, 0.8)

    # covered passage to the tower
    x_out = TX + TOWER_R * math.cos(math.pi / 8)
    for sy in (-1, 1):
        wall(bm, (-hx - t / 2, TY + sy * 1.3), (x_out, TY + sy * 1.3), F, F + 3.6, 0.4, C["STONE"], ext=0.2, frames=False)
    box(bm, ((-hx + x_out) / 2 - 0.1, TY, F + 3.75), (abs(x_out + hx) + 0.4, 3.1, 0.3), C["STONE_LIGHT"], ch=0.04)
    box(bm, ((-hx + x_out) / 2, TY, F + 0.005), (abs(x_out + hx) + 0.3, 2.2, 0.05), C["STONE_LIGHT"])

    # portico life: gong for announcements, potted olives, braziers by the door
    with Place(T((8.3, -38.45, F)) @ Rz(-math.pi / 2), props):
        for sx in (-1, 1):
            box(props, (sx * 0.65, 0, 1.0), (0.12, 0.12, 2.0), C["WOOD"])
            box(props, (sx * 0.65, 0, 0.04), (0.2, 0.6, 0.08), C["WOOD"])
        box(props, (0, 0, 2.02), (1.55, 0.14, 0.14), C["WOOD_LIGHT"])
        for sx in (-1, 1):
            beam(props, (sx * 0.3, 0, 1.95), (sx * 0.25, 0, 1.68), 0.02, 0.02, C["BRONZE_DARK"], 4)
        frustum(props, T((0, 0.03, 1.12)) @ ROT_X90, 0.52, 0.52, 0.06, C["BRONZE"], segs=16)
        ring(props, T((0, -0.04, 1.12)) @ ROT_X90, 0.42, 0.35, 0.03, C["BRONZE_DARK"], segs=16)
        frustum(props, T((0, -0.06, 1.12)) @ ROT_X90, 0.15, 0.15, 0.03, C["BRONZE_DARK"], segs=10)
        beam(props, (0.55, 0.3, 0.0), (0.7, 0.2, 0.9), 0.03, 0.03, C["WOOD"], 4)
        blob(props, (0.71, 0.2, 0.95), (0.09, 0.09, 0.09), C["MAROON"], segs=6, rings=3)
    for x in (-7.7,):
        frustum(props, T((x, -38.5, F)), 0.35, 0.5, 0.6, C["TERRACOTTA"], segs=8)
        ring(props, T((x, -38.5, F + 0.6)), 0.54, 0.44, 0.06, C["TERRACOTTA_DARK"], segs=8)
        olive_tree(props, x, -38.5, F + 0.55, 0.65)
    for x in (-1.75, 1.75):                                     # flank the door, keep the windows clear
        brazier(props, glow, x, -38.7, F, 0.9)


def build_lodge_roof(bm):
    top = F + LODGE_WALL_H
    ridge, eave, ew = F + 8.1, F + 5.45, 10.6
    yA, yB = -36.9, -51.3
    for sx in (-1, 1):
        hexa(bm, [(0, yA, ridge - 0.3), (sx * ew, yA, eave - 0.3), (sx * ew, yB, eave - 0.3), (0, yB, ridge - 0.3),
                  (0, yA, ridge), (sx * ew, yA, eave), (sx * ew, yB, eave), (0, yB, ridge)], C["STONE_DARK"])
        y = yA - 0.3
        while y > yB + 0.2:                                     # tile ribs
            beam(bm, (0, y, ridge + 0.02), (sx * (ew + 0.05), y, eave + 0.02), 0.07, 0.07, C["STONE"], segs=4)
            y -= 0.9
        beam(bm, (sx * ew, yA - 0.05, eave - 0.1), (sx * ew, yB + 0.05, eave - 0.1), 0.14, 0.14, C["MARBLE"], segs=4)
    beam(bm, (0, yA - 0.1, ridge + 0.05), (0, yB + 0.1, ridge + 0.05), 0.17, 0.17, C["MARBLE"], segs=6)
    for y in (yA - 0.1, yB + 0.1):
        blob(bm, (0, y, ridge + 0.35), (0.3, 0.3, 0.35), C["BRONZE"], segs=6, rings=4)

    # front pediment over the portico, tympanum + bull crest facing the stage
    prism(bm, [(-10.4, 0), (10.4, 0), (0, 2.65)], (0, -37.55, top), 1.0, 0.9, C["STONE_LIGHT"])
    prism(bm, [(-8.6, 0.2), (8.6, 0.2), (0, 2.2)], (0, -37.07, top), 1.0, 0.06, C["MAROON"])
    with Place(T((0, -36.98, top + 1.0)) @ Rz(math.pi), bm):
        emblem(bm, (0, 0, 0), 0.65, C["CREAM"], C["MAROON"], t=0.08)
    # gables over the front and rear walls (kept just inside the roof slab)
    gable = [(-9.4, 0), (9.4, 0), (9.4, 0.3), (0, 2.65), (-9.4, 0.3)]
    for y in (LODGE_YF, LODGE_YR):
        prism(bm, gable, (0, y, top), 1.0, LODGE_WALL_T, C["STONE"])
    prism(bm, [(-9.6, 0), (9.6, 0), (0, 2.4)], (0, LODGE_YR - 0.28, top), 1.0, 0.06, C["STONE_LIGHT"])

    # exposed timber: tie beams, king posts, ridge beam
    for y in (-42.0, -45.0, -48.0):
        box(bm, (0, y, top - 0.15), (2 * LODGE_HX, 0.3, 0.35), C["WOOD"])
        box(bm, (0, y, (top + ridge - 0.3) / 2), (0.22, 0.22, ridge - 0.3 - top), C["WOOD"])
        for sx in (-1, 1):
            beam(bm, (sx * 0.1, y, top + 0.05), (sx * 4.5, y, top + 0.05 + (ridge - 0.45 - top) * 0.55), 0.09, 0.09, C["WOOD"], 4)
    box(bm, (0, (LODGE_YF + LODGE_YR) / 2, ridge - 0.45), (0.28, LODGE_YF - LODGE_YR, 0.3), C["WOOD"])


def build_lodge_interior(bm, glow):
    hx, yf, yr = LODGE_HX - LODGE_WALL_T / 2, LODGE_YF - LODGE_WALL_T / 2, LODGE_YR + LODGE_WALL_T / 2
    ymid = (yf + yr) / 2
    with Place(T((0, 0, F)), bm, glow):
        # plank floor
        n = int(round(2 * hx / 0.5))
        for i in range(n):
            x = -hx + 0.25 + i * 0.5
            box(bm, (x, ymid, 0.025), (0.49, yf - yr, 0.05), C["WOOD"] if i % 2 else C["WOOD_LIGHT"])
        # runner from the front door to the hearth, rug under the council table
        with Place(T((0, -41.95, 0)) @ Rz(math.pi / 2), bm):
            rug(bm, 4.3, 1.5)
        with Place(T((-5.0, -42.1, 0)), bm):
            rug(bm, 4.6, 3.2, 0.072)

        # central hearth with a hanging cauldron
        hy = -45.6
        frustum(bm, T((0, hy, 0.05)) @ Rz(math.pi / 8), 1.2, 1.15, 0.12, C["STONE_DARK"], segs=8)
        ring(bm, T((0, hy, 0.17)) @ Rz(math.pi / 8), 1.08, 0.8, 0.35, C["STONE_LIGHT"], segs=8)
        frustum(bm, T((0, hy, 0.17)), 0.82, 0.82, 0.06, C["CHARCOAL"], segs=8)
        with Place(T((0, hy, 0.23)), bm, glow):
            campfire(bm, glow, 0.75, [(-0.2, 0.05, 1.3, 0.35), (0.2, -0.1, 1.5, 0.35), (0.0, 0.25, 1.1, 0.3)], logs=5)
        for i in range(3):
            a = math.tau * i / 3 + 0.3
            beam(bm, (1.0 * math.cos(a), hy + 1.0 * math.sin(a), 0.1), (0, hy, 2.0), 0.04, 0.03, C["BRONZE_DARK"], 4)
        beam(bm, (0, hy, 2.0), (0, hy, 1.45), 0.02, 0.02, C["BRONZE_DARK"], 4)
        frustum(bm, T((0, hy, 1.08)), 0.28, 0.38, 0.32, C["BRONZE_DARK"], segs=8)
        ring(bm, T((0, hy, 1.4)), 0.4, 0.33, 0.04, C["BRONZE"], segs=8)
        add_light((0, hy, 1.2), 26, 2.2, shadows=True)

        # council / map table with klismos chairs, under the window that faces the stage
        cx, cy = -5.0, -42.1
        with Place(T((cx, cy, 0)), bm):
            table(bm, 3.2, 1.5)
            box(bm, (0.1, 0, 0.815), (2.2, 1.1, 0.01), C["CREAM"])
            box(bm, (0.1, 0, 0.82), (2.0, 0.04, 0.005), C["MAROON"])
            for mx, my, col in ((-0.6, 0.2, "MAROON"), (0.3, -0.25, "BRONZE"), (0.7, 0.3, "MAROON"), (-0.2, -0.3, "STONE_DARK")):
                frustum(bm, T((mx, my, 0.82)), 0.05, 0.03, 0.12, C[col], segs=5)
            scroll(bm, -1.3, 0.35, 0.86, 0.5, rot=0.4)
            frustum(bm, T((1.35, -0.4, 0.8)), 0.06, 0.08, 0.14, C["BRONZE"], segs=6)
        for px, py, face in ((cx - 0.8, cy + 1.25, -90), (cx + 0.8, cy + 1.25, -90),
                             (cx - 0.8, cy - 1.25, 90), (cx + 0.8, cy - 1.25, 90),
                             (cx - 2.15, cy, 0), (cx + 2.15, cy, 180)):
            with Place(T((px, py, 0)) @ Rz(rad(face) - math.pi / 2), bm):
                klismos(bm)
        hang = LODGE_WALL_H - 0.33                              # underside of the tie beams
        with Place(T((cx, -42.0, 0)), bm, glow):
            chandelier(bm, glow, hang, 3.4)

        # long feasting table with benches and the remains of dinner
        tx, ty0, ty1 = 5.2, -41.6, -48.6
        tyc, tl = (ty0 + ty1) / 2, ty0 - ty1
        with Place(T((tx, tyc, 0)) @ Rz(math.pi / 2), bm):
            table(bm, tl, 1.2)
        for bx, face in ((tx - 1.15, 0.0), (tx + 1.15, math.pi)):
            with Place(T((bx, tyc, 0)) @ Rz(math.pi / 2), bm):
                bench(bm, tl - 0.4)
            for i in range(5):
                add_seat((bx, ty0 - 0.9 - i * 1.3, 0.47), face)
        for i in range(9):
            y = ty0 - 0.5 - i * 0.75
            for sx in (-1, 1):
                if rng.random() < 0.75:
                    frustum(bm, T((tx + sx * 0.32, y, 0.8)), 0.13, 0.15, 0.03, C["TERRACOTTA"] if i % 2 else C["BRONZE"], segs=8)
            if i % 3 == 1:
                with Place(T((tx, y, 0.8)), bm):
                    amphora(bm, 0.42)
            elif i % 3 == 2:
                frustum(bm, T((tx, y, 0.8)), 0.12, 0.22, 0.1, C["TERRACOTTA_DARK"], segs=8)
                for k in range(4):
                    blob(bm, (tx + rng.uniform(-0.08, 0.08), y + rng.uniform(-0.08, 0.08), 0.95),
                         (0.07, 0.07, 0.07), rng.choice([C["FLOWER_PURPLE"], C["OLIVE_LEAF"], C["DIRT_LIGHT"]]), segs=5, rings=3)
        with Place(T((tx, -45.0, 0)), bm, glow):
            chandelier(bm, glow, hang, 3.4)

        # window seat looking out over the seating toward the stage
        with Place(T((5.2, yf - 0.4, 0)), bm):
            bench(bm, 5.6)
        for i in range(4):
            add_seat((3.1 + i * 1.4, yf - 0.4, 0.47), math.pi / 2)

        # storage: weapon rack, pithoi, crates, chests, shelves
        with Place(T((-hx + 0.3, -47.8, 0)) @ Rz(-math.pi / 2), bm):
            weapon_rack(bm, 2.0)
        for x, y, h in ((-7.95, -49.6, 1.3), (-7.1, -49.75, 1.1)):
            with Place(T((x, y, 0)), bm):
                amphora(bm, h, C["TERRACOTTA_DARK"])
        with Place(T((-5.3, yr + 0.25, 0)), bm):
            shelf(bm, 2.0, 2.0, 0.4)
        with Place(T((3.2, yr + 0.25, 0)), bm):
            shelf(bm, 2.0, 2.0, 0.4)
        for x, y, s, r in ((-2.8, -49.5, 0.75, 0.2), (-3.6, -49.6, 0.6, -0.3)):
            with Place(T((x, y, 0)) @ Rz(r), bm):
                crate(bm, s)
        with Place(T((-2.85, -49.45, 0.75)) @ Rz(0.6), bm):
            crate(bm, 0.5)
        with Place(T((7.6, -49.75, 0)), bm):
            chest(bm)
        with Place(T((-8.2, -43.6, 0)), bm):
            amphora(bm, 0.8)

        # wall torches all round, banners and shields
        sc = [((-5.2, yf, 2.7), -90), ((5.2, yf, 2.7), -90),
              ((-2.1, yr, 2.6), 90), ((2.1, yr, 2.6), 90), ((-7.6, yr, 2.6), 90), ((7.6, yr, 2.6), 90),
              ((hx, -40.4, 2.6), 180), ((hx, -45.0, 2.6), 180), ((hx, -49.6, 2.6), 180),
              ((-hx, -43.0, 2.6), 0), ((-hx, -46.45, 2.6), 0)]
        for (x, y, z), face in sc:
            with Place(T((x, y, z)) @ Rz(rad(face) - math.pi / 2), bm, glow):
                sconce(bm, glow)
        with Place(T((0, yr + 0.06, 5.15)) @ Rz(math.pi), bm):
            banner(bm, 0.75, rod=1.4)
        with Place(T((0, yf - 0.06, 5.25)), bm):
            banner(bm, 0.65, rod=1.4)
        for x in (-3.6, 3.6):
            shield(bm, T((x, yr + 0.02, 3.3)) @ ROT_XN90, 0.5)


# =============================================================================
#                       6) OCTAGONAL LOOKOUT TOWER
# =============================================================================
def build_tower(bm, inter, glow):
    ap_out = TOWER_R * math.cos(math.pi / 8)
    ap_mid = ap_out - TOWER_T / 2
    r_mid = ap_mid / math.cos(math.pi / 8)
    side = 2 * r_mid * math.sin(math.pi / 8)
    ext = TOWER_T * math.tan(math.pi / 8) + 0.05
    top = L2 + 1.1
    with Place(T((TX, TY, 0)), bm, inter, glow):
        rot8 = Rz(math.pi / 8)
        frustum(bm, rot8, TOWER_R + 0.4, TOWER_R + 0.2, F - 0.25, C["STONE"], segs=8)
        frustum(bm, T((0, 0, F - 0.25)) @ rot8, TOWER_R + 0.35, TOWER_R + 0.35, 0.25, C["STONE_LIGHT"], segs=8)
        frustum(bm, rot8, TOWER_R + 0.6, TOWER_R + 0.6, 0.6, C["STONE_DARK"], segs=8)

        for i in range(8):
            phi = i * math.pi / 4
            a = (r_mid * math.cos(phi - math.pi / 8), r_mid * math.sin(phi - math.pi / 8))
            b = (r_mid * math.cos(phi + math.pi / 8), r_mid * math.sin(phi + math.pi / 8))
            u = side / 2
            ops = []
            if i == 0:
                ops.append((u, 1.8, F, F + 3.0))                         # door from the lodge passage
            elif i in (2, 4, 6):
                ops.append((u, 0.5, F + 1.2, F + 2.9))                   # arrow slits
            if i != 0:
                ops.append((u, 1.5, L1 + 0.9, L1 + 3.0))                 # watch-room windows
            wall(bm, a, b, F, top, TOWER_T, C["STONE"], ops, ext)
            doors = [o for o in ops if o[2] <= F + 0.01]
            wall(bm, a, b, F, F + 0.45, TOWER_T + 0.14, C["STONE_DARK"], doors, ext + 0.06, frames=False)
            wall(bm, a, b, L1 - 0.25, L1, TOWER_T + 0.16, C["STONE_LIGHT"], (), ext + 0.07, frames=False)
            wall(bm, a, b, top, top + 0.2, TOWER_T + 0.24, C["MARBLE"], (), ext + 0.1, frames=False)
            for f in (0.25, 0.75):                                        # merlons
                ux, uy = (b[0] - a[0]) / side, (b[1] - a[1]) / side
                box(bm, (a[0] + ux * side * f, a[1] + uy * side * f, top + 0.45), (0.7, TOWER_T, 0.5),
                    C["STONE_LIGHT"], rot=math.atan2(uy, ux), ch=0.03)

        # floors (watch room + roof deck) with the stair opening
        for lvl in (L1, L2):
            for k in range(16):
                a0 = A0 + k * math.pi / 8
                a1 = a0 + math.pi / 8
                r0 = R_STAIR + 0.02 if 7 <= k <= 14 else 0.33
                wedge(bm, r0, R_FLOOR, a0, a1, lvl - 0.3, lvl, C["STONE_LIGHT"] if k % 2 else C["STONE"], segs=1)
        # spiral stair around a central newel: 16 rises per storey
        frustum(bm, T((0, 0, F)), 0.36, 0.36, L2 + 1.0 - F, C["STONE_LIGHT"], segs=10)
        blob(bm, (0, 0, L2 + 1.05), (0.3, 0.3, 0.25), C["BRONZE"], segs=8, rings=4)
        for base in (F, L1):
            for k in range(15):
                a0 = A0 + k * math.pi / 8
                ztop = base + (k + 1) * STEP_RISE
                wedge(bm, 0.33, R_STAIR, a0, a0 + math.pi / 8, ztop - 0.3, ztop,
                      C["MARBLE"] if k % 2 else C["STONE_LIGHT"], segs=2)
        # bronze railings round the stairwell openings
        for lvl in (L1, L2):
            angs = [A0 + k * math.pi / 8 for k in range(7, 16)]
            pts = [polar(R_STAIR + 0.1, a) for a in angs]
            for p in pts:
                beam(bm, (p[0], p[1], lvl), (p[0], p[1], lvl + 1.0), 0.05, 0.05, C["BRONZE"], 5)
            for p, q in zip(pts[:-1], pts[1:]):
                for h in (0.5, 1.0):
                    beam(bm, (p[0], p[1], lvl + h), (q[0], q[1], lvl + h), 0.035, 0.035, C["BRONZE"], 4)
        a7 = A0 + 7 * math.pi / 8
        for r in (0.5, 1.35, R_STAIR + 0.1):
            p = polar(r, a7)
            beam(bm, (p[0], p[1], L2), (p[0], p[1], L2 + 1.0), 0.05, 0.05, C["BRONZE"], 5)
        p, q = polar(0.5, a7), polar(R_STAIR + 0.1, a7)
        for h in (0.5, 1.0):
            beam(bm, (p[0], p[1], L2 + h), (q[0], q[1], L2 + h), 0.035, 0.035, C["BRONZE"], 4)

        # roof-deck canopy on eight columns, with the camp flag on top
        rc = 3.55
        cols = [polar(rc, math.pi / 8 + i * math.pi / 4) for i in range(8)]
        for x, y, _ in cols:
            frustum(bm, T((x, y, L2)), 0.3, 0.3, 0.15, C["STONE_LIGHT"], segs=8)
            frustum(bm, T((x, y, L2 + 0.15)), 0.22, 0.19, 2.65, C["MARBLE"], segs=8)
            box(bm, (x, y, L2 + 2.9), (0.55, 0.55, 0.2), C["MARBLE"])
        for i in range(8):
            (x0, y0, _), (x1, y1, _) = cols[i], cols[(i + 1) % 8]
            box(bm, ((x0 + x1) / 2, (y0 + y1) / 2, L2 + 3.2), (math.hypot(x1 - x0, y1 - y0) + 0.5, 0.5, 0.4),
                C["STONE_LIGHT"], rot=math.atan2(y1 - y0, x1 - x0))
        frustum(bm, T((0, 0, L2 + 3.4)) @ rot8, 4.6, 0.25, 2.0, C["STONE_DARK"], segs=8)
        blob(bm, (0, 0, L2 + 5.45), (0.35, 0.35, 0.3), C["BRONZE"], segs=8, rings=4)
        beam(bm, (0, 0, L2 + 5.4), (0, 0, L2 + 10.0), 0.08, 0.06, C["WOOD"], 6)
        blob(bm, (0, 0, L2 + 10.05), (0.14, 0.14, 0.14), C["BRONZE"], segs=6, rings=3)
        fz = L2 + 8.0
        prism(bm, [(0.08, 0), (2.9, 0), (2.9, 1.8), (0.08, 1.8)], (0, 0, fz), 1.0, 0.05, C["MAROON"])
        for (x0, z0), (x1, z1) in (((0.18, 0.1), (2.8, 0.1)), ((0.18, 1.7), (2.8, 1.7)), ((0.18, 0.1), (0.18, 1.7)), ((2.8, 0.1), (2.8, 1.7))):
            box(bm, ((x0 + x1) / 2, 0, fz + (z0 + z1) / 2), (abs(x1 - x0) + 0.06, 0.07, abs(z1 - z0) + 0.06), C["CREAM"])
        for rot in (0.0, math.pi):
            with Place(T((1.5, 0, fz + 0.95)) @ Rz(rot), bm):
                emblem(bm, (0, -0.045, 0), 0.4, C["CREAM"], C["MAROON"], t=0.03)

        # ---- interior: ground floor ----
        for ang in (157.5, 202.5):
            x, y, _ = polar(3.65, rad(ang))
            with Place(T((x, y, F)) @ Rz(rad(ang)), inter):
                crate(inter, 0.65)
        x, y, _ = polar(3.55, rad(180))
        with Place(T((x, y, F + 0.65)) @ Rz(0.5), inter):
            crate(inter, 0.45)
        for i in (1, 3, 5, 7):
            phi = i * math.pi / 4
            x, y, _ = polar(ap_out - TOWER_T, phi)
            with Place(T((x, y, F + 2.4)) @ Rz(phi + math.pi / 2), inter, glow):
                sconce(inter, glow)
        # ---- interior: watch room ----
        x, y, _ = polar(ap_out - TOWER_T - 0.35, math.pi / 2)
        with Place(T((x, y, L1)), inter):
            table(inter, 1.3, 0.6)
            box(inter, (0, 0, 0.815), (0.9, 0.45, 0.01), C["CREAM"])
            scroll(inter, 0.45, 0.1, 0.86, 0.35)
        x, y, _ = polar(ap_out - TOWER_T - 0.4, math.pi / 2 - 0.62)
        frustum(inter, T((x, y, L1)), 0.2, 0.22, 0.45, C["WOOD"], segs=8)
        frustum(inter, T((x, y, L1 + 0.45)), 0.24, 0.24, 0.05, C["WOOD_LIGHT"], segs=8)
        add_seat((x, y, L1 + 0.5), math.pi / 2, "stool")
        x, y, _ = polar(ap_out - TOWER_T - 0.45, rad(225))
        with Place(T((x, y, L1)) @ Rz(rad(225) + math.pi / 2), inter):
            box(inter, (0, 0, 0.32), (1.9, 0.8, 0.12), C["WOOD_LIGHT"])
            for sx in (-1, 1):
                for sy in (-1, 1):
                    box(inter, (sx * 0.85, sy * 0.33, 0.13), (0.08, 0.08, 0.26), C["WOOD"])
            box(inter, (0.1, 0, 0.42), (1.6, 0.7, 0.08), C["MAROON"])
            box(inter, (-0.75, 0, 0.47), (0.35, 0.6, 0.1), C["CREAM"])
        x, y, _ = polar(3.6, rad(157.5))
        with Place(T((x, y, L1)) @ Rz(rad(157.5) + math.pi / 2), inter):
            weapon_rack(inter, 1.1)
        x, y, _ = polar(3.65, rad(292.5))
        with Place(T((x, y, L1)) @ Rz(rad(292.5) + math.pi / 2), inter):
            chest(inter)
        for off in (-0.9, 0.9):
            x, y = ap_out - TOWER_T, off
            with Place(T((x, y, L1 + 2.4)) @ Rz(math.pi / 2), inter, glow):
                sconce(inter, glow)
        # ---- roof deck: signal beacon and herald's horn ----
        bx, by, _ = polar(1.35, rad(100))
        frustum(inter, T((bx, by, L2)), 0.6, 0.5, 0.35, C["STONE_DARK"], segs=8)
        frustum(inter, T((bx, by, L2 + 0.35)), 0.28, 0.22, 0.6, C["BRONZE_DARK"], segs=8)
        frustum(inter, T((bx, by, L2 + 0.95)), 0.25, 0.75, 0.45, C["BRONZE"], segs=10)
        frustum(glow, T((bx, by, L2 + 1.4)), 0.55, 0.0, 1.4, C["GLOW"], segs=7)
        add_light((bx, by, L2 + 2.0), 45, 2.5, shadows=True)
        x, y, _ = polar(3.3, rad(60))
        beam(inter, (x, y, L2), (x, y, L2 + 1.1), 0.05, 0.05, C["WOOD"], 5)
        beam(inter, (x - 0.35, y, L2 + 1.15), (x + 0.45, y + 0.1, L2 + 1.3), 0.04, 0.18, C["BRONZE"], 8)


# =============================================================================
#                       7) TERRAIN, PATHS, FOLIAGE, PROPS
# =============================================================================
def build_berm(bm):
    radii = [R_PROM1, R_CREST, 44, 48, 52, 55, R_FOOT]
    na = 49
    angs = [A_MIN + (A_MAX - A_MIN) * i / (na - 1) for i in range(na)]
    G = []
    for a in angs:
        col = []
        for r in radii:
            x, y = r * math.cos(a), r * math.sin(a)
            z = Z_TOP if r <= R_CREST else max(0.0, Z_TOP * (R_FOOT - r) / (R_FOOT - R_CREST) + berm_noise(r, a))
            col.append(bm.verts.new((x, y, z)))
        G.append(col)
    for i in range(na - 1):
        for j in range(len(radii) - 1):
            vs = [G[i][j], G[i + 1][j], G[i + 1][j + 1], G[i][j + 1]]
            cen = sum((v.co for v in vs), Vector((0, 0, 0))) / 4
            add_face(bm, vs, cen - Vector((0, 0, 5)), C["GRASS"] if (i + j) % 5 else C["GRASS_LIGHT"])
    # skirts so the berm is a closed solid
    ref_mid = lambda a: Vector(polar((R_PROM1 + R_FOOT) / 2, a, Z_TOP / 3))
    for i in range(na - 1):
        v0, v1 = G[i][0], G[i + 1][0]
        b0 = bm.verts.new((v0.co.x, v0.co.y, 0.0))
        b1 = bm.verts.new((v1.co.x, v1.co.y, 0.0))
        add_face(bm, [v0, v1, b1, b0], ref_mid((angs[i] + angs[i + 1]) / 2), C["GRASS"])
    for i, other in ((0, rad(270)), (na - 1, rad(270))):
        for j in range(len(radii) - 1):
            v0, v1 = G[i][j], G[i][j + 1]
            if v0.co.z < 0.01 and v1.co.z < 0.01:
                continue
            b0 = bm.verts.new((v0.co.x, v0.co.y, 0.0))
            b1 = bm.verts.new((v1.co.x, v1.co.y, 0.0))
            add_face(bm, [v0, v1, b1, b0], ref_mid(other), C["GRASS"])


def path(bm, pts, hw0=2.0):
    """Entrance-style dirt ribbon with a worn, lighter centre strip."""
    P = catmull(pts, 6)
    rows = []
    n = len(P)
    for i, (x, y) in enumerate(P):
        a = P[max(i - 1, 0)]
        b = P[min(i + 1, n - 1)]
        tx, ty = b[0] - a[0], b[1] - a[1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        hw = hw0 + 0.3 * math.sin(i * 0.7) + 0.15 * math.sin(i * 1.9)
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
    return P


GATE_X, GATE_Y = 24.5, 10.4
PATHS = [
    [(-16.5, 5.5), (-20, 7.5), (-GATE_X, GATE_Y), (-31, 11), (-38, 14), (-45, 19), (-52, 25), (-62, 32)],
    [(16.5, 5.5), (20, 7.5), (GATE_X, GATE_Y), (31, 11), (38, 14), (45, 19), (52, 25), (62, 32)],
    [(0, BACK_Y1 + 2.0), (0.6, 31), (-0.8, 38), (0.5, 46), (0, 58)],
]


def lodge_stair_end():
    n = int(math.ceil(F / 0.3))
    return -51.7 - 0.42 * n


def blocked(x, y, pad=0.0):
    r, a = math.hypot(x, y), math.atan2(y, x)
    if r < R_PROM1 + pad and (in_sweep(a) or y < 1.5):
        return True                                             # seating + orchestra
    if r < R_WALK + pad:
        return True
    if abs(x) < 21 + pad and -1 - pad < y < BACK_Y1 + 3 + pad:
        return True                                             # forecourt + stage
    if -21 - pad < x < 11 + pad and -53 - pad < y < -35 - pad:
        return True                                             # lodge + tower
    if abs(x) < 2.6 + pad and lodge_stair_end() - 1 - pad < y < -50:
        return True                                             # rear stair
    if abs(abs(x) - GATE_X) < 2 + pad and abs(y - GATE_Y) < 7 + pad:
        return True                                             # side gates
    return False


def near_path(x, y, m):
    return any((x - px) ** 2 + (y - py) ** 2 < m * m for P in PATH_PTS for px, py in P)


PATH_PTS = []


def build_paths(bm):
    for pts in PATHS:
        PATH_PTS.append(path(bm, pts))
    y_end = lodge_stair_end()
    PATH_PTS.append(path(bm, [(0, y_end - 0.5), (0.6, y_end - 4), (-0.5, y_end - 8), (0, -78)], 1.8))


def build_ground(bm):
    box(bm, (0, -8, -0.5), (140, 140, 1.0), C["GRASS"])
    for _ in range(26):
        x, y = rng.uniform(-66, 66), rng.uniform(-74, 58)
        box(bm, (x, y, 0.012), (rng.uniform(3, 9), rng.uniform(3, 9), 0.03),
            C["GRASS_LIGHT"], rot=rng.uniform(0, math.pi))


def build_foliage(bm):
    # cypress rows on the berm crest frame the seating (kept clear of the lodge view)
    for deg in list(range(178, 240, 9)) + list(range(302, 364, 9)):
        a = rad(deg)
        r = 39.2
        x, y = r * math.cos(a), r * math.sin(a)
        cypress(bm, x, y, berm_z(x, y), rng.uniform(7.0, 9.0))
    for deg in range(180, 361, 14):                              # second, lower row down the slope
        a = rad(deg + 7)
        r = 50.5
        x, y = r * math.cos(a), r * math.sin(a)
        if blocked(x, y, 1.5):
            continue
        cypress(bm, x, y, berm_z(x, y), rng.uniform(5.0, 6.5))
    # olive trees and shrubs around the parodoi and the stage wings
    for x, y, s in ((-30, 20, 1.1), (30, 21, 1.0), (-26, 30, 0.9), (27, 31, 1.2), (-40, 26, 1.0),
                    (41, 27, 0.9), (-12, 33, 1.0), (12, 34, 1.1), (-34, 0.5, 0.8), (34, 1.0, 0.9)):
        if not near_path(x, y, 3.2):
            olive_tree(bm, x, y, 0.0, s)
    placed, tries = 0, 0
    while placed < 30 and tries < 2000:
        tries += 1
        x, y = rng.uniform(-66, 66), rng.uniform(-74, 58)
        if blocked(x, y, 2.0) or near_path(x, y, 3.6):
            continue
        s = rng.uniform(0.9, 1.6)
        z = berm_z(x, y)
        blob(bm, (x, y, z + 0.3), (s, s * 0.78, s * 0.5), C["LEAF_DARK"] if placed % 2 else C["LEAF_MID"],
             segs=7, rings=4, jitter=0.12)
        for _ in range(2):
            blob(bm, (x + rng.uniform(-0.45, 0.45) * s, y + rng.uniform(-0.35, 0.35) * s, z + 0.55 + rng.uniform(0, 0.3)),
                 (s * 0.42, s * 0.36, s * 0.36), rng.choice([C["LEAF_DARK"], C["LEAF_MID"], C["LEAF_LIGHT"]]),
                 segs=6, rings=3, jitter=0.12)
        placed += 1
    placed, tries = 0, 0
    while placed < 90 and tries < 4000:                          # grass tufts + wildflowers
        tries += 1
        x, y = rng.uniform(-64, 64), rng.uniform(-72, 56)
        if blocked(x, y, 0.5) or near_path(x, y, 3.4):
            continue
        z = berm_z(x, y)
        for _ in range(3):
            h = rng.uniform(0.35, 0.7)
            beam(bm, (x + rng.uniform(-0.1, 0.1), y + rng.uniform(-0.1, 0.1), z),
                 (x + rng.uniform(-0.2, 0.2), y + rng.uniform(-0.2, 0.2), z + h), 0.05, 0.0, C["GRASS_LIGHT"], segs=3)
        if placed % 3 == 0:
            blob(bm, (x, y, z + 0.62), (0.11, 0.11, 0.08), C["FLOWER_WHITE"] if placed % 2 else C["FLOWER_PURPLE"],
                 segs=5, rings=3)
        placed += 1
    placed, tries = 0, 0
    while placed < 36 and tries < 3000:                          # rocks
        tries += 1
        x, y = rng.uniform(-64, 64), rng.uniform(-72, 56)
        if blocked(x, y, 0.8) or near_path(x, y, 2.9):
            continue
        s = rng.uniform(0.25, 0.8)
        blob(bm, (x, y, berm_z(x, y) + 0.05), (s, s * 0.9, s * 0.6),
             rng.choice([C["STONE"], C["STONE_LIGHT"], C["STONE_DARK"]]), segs=5, rings=3, jitter=0.18)
        placed += 1


def build_exterior_props(bm, glow):
    # braziers on the diazoma and along the top promenade
    for deg in (186, 217.5, 322.5, 354):
        x, y, _ = polar(R_UP0 - 0.55, rad(deg))
        brazier(bm, glow, x, y, Z_DIAZ, 0.85)
    for deg in (185, 200, 220, 235, 252.5, 287.5, 305, 320, 340, 355):
        x, y, _ = polar(R_PROM1 - 0.6, rad(deg))
        brazier(bm, glow, x, y, Z_TOP, 1.1)
    # water jars on the diazoma
    for deg in (190, 213, 327, 350):
        x, y, _ = polar(R_UP0 - 0.5, rad(deg))
        with Place(T((x, y, Z_DIAZ)), bm):
            amphora(bm, 0.75)
    # lived-in seating: cushions, a few forgotten helmets, a shield and a scroll
    spots = [s for s in SEAT_SPOTS if (s[2] - s[1]) * s[0] > 2.0]
    for i in range(60):
        r, a0, a1, z = rng.choice(spots)
        a = rng.uniform(a0 + 0.6 / r, a1 - 0.6 / r)
        x, y, _ = polar(r, a)
        box(bm, (x, y, z + 0.04), (0.5, 0.42, 0.08), C["MAROON"] if i % 3 else C["CREAM"], rot=a + math.pi / 2 + rng.uniform(-0.3, 0.3), ch=0.02)
    for i in range(4):
        r, a0, a1, z = rng.choice(spots)
        a = rng.uniform(a0 + 0.6 / r, a1 - 0.6 / r)
        x, y, _ = polar(r, a)
        with Place(T((x, y, z)) @ Rz(a + rng.uniform(-1, 1)), bm):
            blob(bm, (0, 0, 0.17), (0.17, 0.2, 0.17), C["BRONZE"], segs=8, rings=4)
            box(bm, (0, 0.17, 0.12), (0.22, 0.05, 0.2), C["BRONZE_DARK"])
            for k in range(5):
                t = k / 4
                beam(bm, (0, -0.2 + 0.4 * t, 0.33 + 0.06 * math.sin(t * math.pi)),
                     (0, -0.2 + 0.4 * t, 0.42 + 0.08 * math.sin(t * math.pi)), 0.05, 0.03, C["MAROON"], 4)
    r, a0, a1, z = rng.choice(spots)
    a = (a0 + a1) / 2
    x, y, _ = polar(r + 0.3, a)
    shield(bm, T((x, y, z + 0.42)) @ Rz(a + math.pi / 2) @ Matrix.Rotation(rad(-70), 4, "X"), 0.45)
    r, a0, a1, z = rng.choice(spots)
    x, y, _ = polar(r, (a0 + a1) / 2)
    scroll(bm, x, y, z + 0.06, 0.4, rot=(a0 + a1) / 2)


# =============================================================================
#                             BUILD EVERYTHING
# =============================================================================
names = ["Amphi_CaveaLower", "Amphi_CaveaUpper", "Amphi_Orchestra", "Amphi_Stage", "Amphi_Gates",
         "Lodge_Shell", "Lodge_Roof", "Lodge_Tower", "Lodge_Interior", "Amphi_Props", "Amphi_Glow",
         "Amphi_Berm", "Amphi_Paths", "Amphi_Foliage", "Amphi_Ground"]
B = {n: bmesh.new() for n in names}

build_cavea(B["Amphi_CaveaLower"], B["Amphi_CaveaUpper"], B["Amphi_Props"], B["Amphi_Glow"])
build_orchestra(B["Amphi_Orchestra"], B["Amphi_Glow"], B["Amphi_Props"])
build_stage(B["Amphi_Stage"], B["Amphi_Props"], B["Amphi_Glow"])
for sx in (-1, 1):
    with Place(T((sx * GATE_X, GATE_Y, 0)) @ Rz(sx * math.pi / 2), B["Amphi_Gates"], B["Amphi_Props"], B["Amphi_Glow"]):
        build_gate(B["Amphi_Gates"], B["Amphi_Props"], B["Amphi_Glow"])
build_lodge_shell(B["Lodge_Shell"], B["Amphi_Props"], B["Amphi_Glow"])
build_lodge_roof(B["Lodge_Roof"])
build_lodge_interior(B["Lodge_Interior"], B["Amphi_Glow"])
build_tower(B["Lodge_Tower"], B["Lodge_Interior"], B["Amphi_Glow"])
build_berm(B["Amphi_Berm"])
build_paths(B["Amphi_Paths"])
build_foliage(B["Amphi_Foliage"])
build_exterior_props(B["Amphi_Props"], B["Amphi_Glow"])
build_ground(B["Amphi_Ground"])

objs = [finish(n, B[n], trim=n not in ("Amphi_Glow", "Amphi_Ground")) for n in names]


# ============================ REPORT =========================================
print("\n=== Camp DemiSoul amphitheater: game-ready report (units = studs) ===")
total = 0
for o in objs:
    tris = len(o.data.polygons)
    total += tris
    d = o.dimensions
    flag = "  <-- OVER BUDGET" if tris > TRI_WARN else ""
    print(f"{o.name:20s} {tris:6d} tris   {d.x:6.1f} x {d.y:6.1f} x {d.z:6.1f}{flag}")
print(f"{'TOTAL':20s} {total:6d} tris   ({len(objs)} draw calls + 1 shared texture)")
print(f"Seating: {LOWER_ROWS + UPPER_ROWS} rows, outer radius {R_PROM1 * STUD_SCALE:.0f} studs | "
      f"lodge floor {F * STUD_SCALE:.0f} studs up | tower deck {L2 * STUD_SCALE:.0f} studs up")
print(f"Lights: {len(LIGHTS)} | furniture seats: {sum(1 for s in SEATS if s[2] != 'tier')}")


# ======================= ROBLOX SETUP SCRIPT (lights + seats) =================
def roblox_setup_lua():
    ref = next(o for o in objs if o.name == "Amphi_Orchestra")
    bb = [Vector(c) for c in ref.bound_box]
    rc = sum(bb, Vector((0, 0, 0))) / 8                 # bbox centre = MeshPart.Position in Studio

    def rbx(v):                                         # Blender (x, y, z) -> Roblox (x, z, -y)
        return (v.x, v.z, -v.y)

    ox, oy, oz = rbx(rc)
    L = ["-- Auto-generated by CampDemiSoul_Amphitheater_GameReady.py",
         "-- Put this Script inside the imported Model (the one containing Amphi_Orchestra).",
         "-- It adds a PointLight at every flame and Seats on the thrones / chairs / benches.",
         "local ADD_LIGHTS = true",
         "local ADD_FURNITURE_SEATS = true",
         "local ADD_TIER_SEATS = false   -- prompt-to-sit seats along the stone rows",
         "",
         "local model = script.Parent",
         'local ref = model:FindFirstChild("Amphi_Orchestra", true)',
         'if not ref then warn("Amphi_Orchestra not found next to this script") return end',
         f"local origin = ref.CFrame * CFrame.new({-ox:.3f}, {-oy:.3f}, {-oz:.3f})",
         'local folder = Instance.new("Folder")',
         'folder.Name = "AmphitheaterRuntime"',
         "folder.Parent = model",
         "",
         "local LIGHTS = { -- x, y, z, range, brightness, shadows"]
    for p, r, b, sh in LIGHTS:
        x, y, z = rbx(p * STUD_SCALE)
        L.append(f"\t{{{x:.2f}, {y:.2f}, {z:.2f}, {min(r, 60):.0f}, {b:.1f}, {1 if sh else 0}}},")
    L.append("}")
    L.append("local SEATS = { -- x, y, z, lookX, lookZ, tier")
    tier = []
    for r0, a0, a1, z in SEAT_SPOTS:
        n = int((a1 - a0) * r0 / 1.6)
        for i in range(n):
            a = a0 + (a1 - a0) * (i + 0.5) / n
            tier.append((Vector(polar(r0, a, z)), Vector((-math.cos(a), -math.sin(a), 0)), "tier"))
    for p, d, kind in SEATS + tier:
        x, y, z = rbx(p * STUD_SCALE)
        dx, _, dz = rbx(d.normalized())
        L.append(f"\t{{{x:.2f}, {y - 0.2:.2f}, {z:.2f}, {dx:.3f}, {dz:.3f}, {1 if kind == 'tier' else 0}}},")
    L.append("}")
    L += [
        "",
        "if ADD_LIGHTS then",
        "\tfor i, l in ipairs(LIGHTS) do",
        '\t\tlocal p = Instance.new("Part")',
        '\t\tp.Name = "FlameLight" .. i',
        "\t\tp.Anchored, p.CanCollide, p.CanQuery, p.CanTouch = true, false, false, false",
        "\t\tp.Transparency = 1",
        "\t\tp.Size = Vector3.new(0.2, 0.2, 0.2)",
        "\t\tp.CFrame = origin * CFrame.new(l[1], l[2], l[3])",
        '\t\tlocal light = Instance.new("PointLight")',
        "\t\tlight.Color = Color3.fromRGB(255, 168, 82)",
        "\t\tlight.Range, light.Brightness, light.Shadows = l[4], l[5], l[6] == 1",
        "\t\tlight.Parent = p",
        "\t\tp.Parent = folder",
        "\tend",
        "end",
        "",
        "for i, s in ipairs(SEATS) do",
        "\tlocal isTier = s[6] == 1",
        "\tif (isTier and ADD_TIER_SEATS) or (not isTier and ADD_FURNITURE_SEATS) then",
        "\t\tlocal pos = origin * Vector3.new(s[1], s[2], s[3])",
        "\t\tlocal look = origin:VectorToWorldSpace(Vector3.new(s[4], 0, s[5]))",
        '\t\tlocal seat = Instance.new("Seat")',
        '\t\tseat.Name = (isTier and "TierSeat" or "Seat") .. i',
        "\t\tseat.Anchored, seat.CanCollide = true, false",
        "\t\tseat.Transparency = 1",
        "\t\tseat.Size = Vector3.new(1.8, 0.4, 1.8)",
        "\t\tseat.CFrame = CFrame.lookAt(pos, pos + look)",
        "\t\tif isTier then -- walking along the rows should not auto-sit you",
        "\t\t\tseat.Disabled = true",
        '\t\t\tlocal prompt = Instance.new("ProximityPrompt")',
        '\t\t\tprompt.ActionText = "Sit"',
        "\t\t\tprompt.MaxActivationDistance = 6",
        "\t\t\tprompt.RequiresLineOfSight = false",
        "\t\t\tprompt.Parent = seat",
        "\t\t\tprompt.Triggered:Connect(function(player)",
        '\t\t\t\tlocal hum = player.Character and player.Character:FindFirstChildOfClass("Humanoid")',
        "\t\t\t\tif hum and not seat.Occupant then",
        "\t\t\t\t\tseat.Disabled = false",
        "\t\t\t\t\tseat:Sit(hum)",
        "\t\t\t\tend",
        "\t\t\tend)",
        '\t\t\tseat:GetPropertyChangedSignal("Occupant"):Connect(function()',
        "\t\t\t\tif not seat.Occupant then seat.Disabled = true end",
        "\t\t\tend)",
        "\t\tend",
        "\t\tseat.Parent = folder",
        "\tend",
        "end",
    ]
    return "\n".join(L) + "\n"


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
        lua_path = os.path.join(OUT, "AmphitheaterSetup.server.lua")
        with open(lua_path, "w") as fh:
            fh.write(roblox_setup_lua())
        print("Roblox setup:", lua_path)
    except Exception as exc:
        print("Could not write the Roblox setup script:", exc)
    try:
        fbx_path = os.path.join(OUT, "CampDemiSoul_Amphitheater.fbx")
        export_fbx(fbx_path)
        print("Exported:", fbx_path)
        print("Palette :", PNG_PATH)
    except Exception as exc:
        print("FBX export failed (the models are still in the scene):", exc)

print("Studio tips: Amphi_Glow -> Material Neon, CanCollide off | Foliage/Props/Glow CanCollide off |"
      " Cavea, Stage, Lodge_*, Gates, Berm -> CollisionFidelity PreciseConvexDecomposition")

try:
    for area in bpy.context.screen.areas:
        if area.type == "VIEW_3D":
            area.spaces[0].shading.type = "SOLID"
            area.spaces[0].shading.color_type = "TEXTURE"
except Exception:
    pass
