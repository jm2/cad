"""Master form: the outer body of the mouse, split at the parting plane
Z_SPLIT into a top dome and a base, plus their cavities.

top   Lofted along Y through mirror-symmetric XZ sections (one upper spline
      from the parting line over the crest and back, closed by a line on the
      parting plane). In the end zones the sections shrink along a quarter
      ellipse and the loft closes in a point on the parting line, so nose and
      tail round off without fillets.
base  Lofted along Z through horizontal plan outlines: the parting-line
      outline at the top, each lower outline inset by a rolled curve (3 deg
      draft at the parting line, rolling inward toward the underside), so the
      flanks, nose and tail all tuck under the same way, every face of the
      base releases downward (moulding) and the parting line is the widest
      silhouette.

Both halves derive their parting-line outline from the same w(y) and the same
end-zone ellipse, so they meet on the parting plane.
"""

from __future__ import annotations

import math
from functools import lru_cache

import build123d as bd
import numpy as np
from scipy.interpolate import PchipInterpolator

import params as P

_INTERP = {k: PchipInterpolator(P.FORM_Y, v) for k, v in P.FORM.items()}
TUMBLE_MEAN = 3.5


CONTOUR_N = 40     # stations per side of every closed plan contour


def closed_spline(pts) -> bd.Wire:
    """Periodic interpolating spline with UNIFORM parameters. Every contour
    has the same point count and parameterisation, so their knot vectors
    match and lofts stay compact (chord-length knots differ per contour and
    OCCT merges them, which made a 127 MB assembly STEP)."""
    n = len(pts)
    return bd.Wire([bd.Edge.make_spline(pts, periodic=True,
                                        parameters=list(np.linspace(0, 1, n + 1)))])


def _cos_stations(a, b, n=CONTOUR_N):
    """n stations from a to b clustered toward both ends (ends excluded)."""
    k = np.linspace(0, math.pi, n + 2)[1:-1]
    return list(a + (b - a) * (1 - np.cos(k)) / 2)


def form_at(y: float) -> dict:
    d = {k: float(f(y)) for k, f in _INTERP.items()}
    d.setdefault("flare", 0.0)
    return d


def shelf(dz: float) -> float:
    """Thumb/finger-rest profile: 1 at and below the parting line, falling
    smoothly to 0 over ~SHELF_H above it (rounded lip, sloped shelf top,
    concave groove above). Multiplied by flare(y) and added to the section's
    half-width; it never makes the flank overhang (x stays non-increasing
    with height), so the top shell still releases upward."""
    if dz <= 0:
        return 1.0
    return math.exp(-(dz / getattr(P, "SHELF_H", 3.0)) ** 3)


def has_flare() -> bool:
    return "flare" in P.FORM and max(P.FORM["flare"]) > 0


# ------------------------------------------------------------- end zones
def end_scale(y, d=0.0):
    """Quarter-ellipse shrink factor in the end zones (1 in the middle, 0 at
    the tips). d > 0 = an inset body: tips and zone lengths shortened by d."""
    yt, yn = P.Y_TAIL + d, P.Y_NOSE - d
    lt, ln = P.END_TAIL - d, P.END_NOSE - d
    u = 0.0
    if y < yt + lt:
        u = (yt + lt - y) / lt
    elif y > yn - ln:
        u = (y - (yn - ln)) / ln
    return math.sqrt(max(0.0, 1.0 - min(u, 1.0) ** 2))


def _end_stations(d=0.0, n_end=7, step=None):
    """Sine-spaced stations in the end zones (dense near the tips, tips
    excluded), uniform in the middle."""
    step = step or P.LOFT_STEP
    yt, yn = P.Y_TAIL + d, P.Y_NOSE - d
    lt, ln = P.END_TAIL - d, P.END_NOSE - d
    q = lambda k: math.sin(0.5 * math.pi * k / (n_end + 0.6))
    out = [yt + lt - lt * q(k) for k in range(n_end, 0, -1)]
    a, b = yt + lt, yn - ln
    n = max(1, int(round((b - a) / step)))
    out += list(np.linspace(a, b, n + 1))
    out += [yn - ln + ln * q(k) for k in range(1, n_end + 1)]
    return sorted(set(round(float(v), 4) for v in out))


def plan_half_width(y, d=0.0):
    """Half-width of the parting-line outline at y, inset by d."""
    return (form_at(y)["w"] - d) * end_scale(y, d)


# ------------------------------------------------------------------- top
# Cross-section above the parting line (half, x >= 0), with t = (z - zs)/B:
#   x(t) = A (1 - t^n)^(1/n)  -  tan(DRAFT) B t (1 - t)
# A = half-width at the parting line, B = crest height above it, n = "sq".
# The second term leans the flank in by exactly DRAFT at the parting line and
# vanishes at the crest. End zones scale A by s and B by s^END_ZPOW.

def top_AB(y, inset=0.0, dend=None):
    """(A, B, n) of the section at y for the outer (inset=0) or cavity."""
    p = form_at(y)
    dend = inset if dend is None else dend
    s = end_scale(y, dend)
    A = max(p["w"] - inset, 0.0) * s
    B = max(p["h"] - P.Z_SPLIT - inset, 0.0) * s ** P.END_ZPOW
    return A, B, p["sq"]


def section_x(t, A, B, n):
    t = min(max(t, 0.0), 1.0)
    return A * (1 - t ** n) ** (1 / n) - math.tan(math.radians(P.DRAFT)) * B * t * (1 - t)


def _contour_ys(fun_ok, y0, y1, n=90):
    """Find the y-range where fun_ok(y) holds (assumed one interval) and
    return stations clustered toward both ends."""
    ys = np.linspace(y0, y1, 2001)
    ok = np.array([fun_ok(y) for y in ys])
    if not ok.any():
        return None
    i0, i1 = np.argmax(ok), len(ok) - 1 - np.argmax(ok[::-1])
    a, b = ys[i0], ys[i1]
    k = np.linspace(0, math.pi, n)
    return a, b, list(a + (b - a) * (1 - np.cos(k)) / 2)


def contour_wire(z, inset=0.0, dend=None, zs_shift=0.0) -> bd.Wire | None:
    """Closed plan contour of the dome (outer or cavity) at height z."""
    zs = P.Z_SPLIT + zs_shift
    dend = inset if dend is None else dend
    y0, y1 = P.Y_TAIL + dend, P.Y_NOSE - dend

    def x_at(y):
        A, B, n = top_AB(y, inset, dend)
        if B <= 1e-9:
            return 0.0
        x = section_x((z - zs) / B, A, B, n)
        fl = form_at(y)["flare"] * end_scale(y, dend)
        if fl > 0:
            # cavity: the shelf profile sits one wall higher, so the shelf's
            # top keeps a wall's thickness (not just its side)
            x += fl * shelf(z - zs - (P.WALL if inset else 0.0))
        return max(x, 0.0)

    rng = _contour_ys(lambda y: x_at(y) > 0.05, y0, y1)
    if rng is None:
        return None
    a, b, _ = rng
    right = [(x_at(y), y) for y in _cos_stations(a, b)]
    pts = ([bd.Vector(0, a, z)] + [bd.Vector(x, y, z) for x, y in right] +
           [bd.Vector(0, b, z)] + [bd.Vector(-x, y, z) for x, y in reversed(right)])
    return closed_spline(pts)


@lru_cache(maxsize=4)
def top_body(inset: float = 0.0, dend: float | None = None, below: float = 0.0) -> bd.Solid:
    """Dome lofted through horizontal contours from the parting plane (or
    `below` mm under it, vertical there) up to just under the crest."""
    zs = P.Z_SPLIT
    Bmax = max(top_AB(y, inset, dend)[1] for y in np.linspace(P.Y_TAIL, P.Y_NOSE, 257))
    K = 20
    # sine spacing (dense near the crest); the last contour sits at 99.93% of
    # the crest height so the flat cap that closes the loft is ~4 mm across
    levels = [zs + Bmax * math.sin(0.5 * math.pi * k / K) * 0.9993 for k in range(K + 1)]
    if has_flare():   # the shelf changes fast just above the parting line
        h = getattr(P, "SHELF_H", 3.0)
        levels = sorted(set(levels) | {zs + 0.5 * k for k in range(1, int(3.2 * h / 0.5) + 1)})
    wires = []
    if below:
        w0 = contour_wire(zs, inset, dend)
        wires.append(w0.moved(bd.Location((0, 0, -below))))
    for z in levels:
        w = contour_wire(z, inset, dend)
        if w is not None:
            wires.append(w)
    return bd.Solid.make_loft(wires, ruled=False)


# ------------------------------------------------------------------ base
def _roll_a():
    return math.tan(math.radians(P.DRAFT)) * (P.Z_SPLIT - P.Z_BASE) / TUMBLE_MEAN


def roll(u: float) -> float:
    """Base flank inset profile, 0 at the parting line (u=0) to 1 at the
    underside (u=1): DRAFT degrees at the top, rolling inward below. u < 0
    (above the parting line) continues the draft line, so lofts through a
    level above the parting plane stay smooth."""
    a = _roll_a()
    if u < 0:
        return a * u
    return a * u + (1 - a) * u ** 2.4


def roll_slope(u: float, tb: float = TUMBLE_MEAN) -> float:
    """d(inset)/dz of the roll for a total tuck-in tb (wall compensation)."""
    a = _roll_a()
    u = max(u, 0.0)
    return tb * (a + (1 - a) * 2.4 * u ** 1.4) / (P.Z_SPLIT - P.Z_BASE)


def plan_wire(z: float, d_side, d_end) -> bd.Wire:
    """Closed periodic-spline plan outline at height z. d_side(y) is the
    inset along the flanks, d_end shortens the end zones (same inset there)."""
    yt, yn = P.Y_TAIL + d_end, P.Y_NOSE - d_end
    def half(y):
        f = form_at(y)
        return (f["w"] + f["flare"] - d_side(y)) * end_scale(y, d_end)

    right = [(max(half(y), 0.05), y) for y in _cos_stations(yt, yn)]
    pts = ([bd.Vector(0, yt, z)] + [bd.Vector(x, y, z) for x, y in right] +
           [bd.Vector(0, yn, z)] + [bd.Vector(-x, y, z) for x, y in reversed(right)])
    return closed_spline(pts)


# ------------------------------------------------- bell-foot base (Z_LIP set)
# Cross-section of the black base when P.Z_LIP is set: from the parting line
# down to the lip the flank flares OUT along a concave power curve (the foot
# of a bell curve, continuing the top shell's flank tangentially), widest and
# shallowest at the lip, where it makes a thin, wide rest; under the lip it
# tucks back in quickly to the usual footprint. "skirt" (mm) sets the flare
# per station. Moulding: a two-part base tool split at the lip (constant
# height): everything above the lip releases up, everything below releases
# down.

def bell_offset(y, z, skirt=None) -> float:
    """Outward offset of the base's half-width from w(y) at height z."""
    f = form_at(y)
    zs, zl, zb = P.Z_SPLIT, P.Z_LIP, P.Z_BASE
    t = math.tan(math.radians(P.DRAFT))
    F = f.get("skirt", 0.0) if skirt is None else skirt
    if z >= zl:
        v = max((zs - z) / (zs - zl), 0.0)
        return (zs - z) * t + F * v ** P.BELL_Q
    x_lip = (zs - zl) * t + F
    # a short upright band gives the lip real thickness, then a gentle
    # rounded tuck (LIP_TUCK mm) down to the underside: the foot runs out
    # almost to the desk, like a bell curve's tail
    band = getattr(P, "LIP_BAND", 0.0)
    if z >= zl - band:
        return x_lip
    u = min((zl - band - z) / (zl - band - zb), 1.0)
    return x_lip - P.LIP_TUCK * (1 - (1 - u) ** P.TUCK_P)


def _skirt_end():
    return float(PchipInterpolator(P.FORM_Y, P.FORM["skirt"])(P.Y_TAIL)) if "skirt" in P.FORM else 0.0


def bell_x(y, z, extra_d=0.0) -> float:
    """Outer half-width of the bell base at (y, z); the ends grow/shrink with
    the same offset (end-zone ellipse), extra_d shortens them further."""
    d_end = -bell_offset(P.Y_TAIL, z, skirt=_skirt_end()) + extra_d
    return (form_at(y)["w"] + bell_offset(y, z)) * end_scale(y, d_end)


def bell_cavity_x(y, z, n=13) -> float:
    """Exact inner offset (erosion) of the outer section profile by WALL:
    min over s in [z-W, z+W] of x(s) - sqrt(W^2 - (s-z)^2); the ends are
    pulled in by WALL too."""
    W = P.WALL
    best = 1e9
    for k in range(n):
        ds = -W + 2 * W * k / (n - 1)
        sz = max(z + ds, P.Z_BASE)
        best = min(best, bell_x(y, sz, extra_d=W) - math.sqrt(max(W * W - ds * ds, 0.0)))
    return best


def bell_wire(z, xfun, d_tip) -> bd.Wire:
    yt, yn = P.Y_TAIL + d_tip, P.Y_NOSE - d_tip
    # trim to where the contour really has width (an eroded cavity contour
    # goes negative near the tips; clamping there made zero-width slivers)
    ys = np.linspace(yt, yn, 801)
    ok = np.array([xfun(y, z) > 0.3 for y in ys])
    i0, i1 = int(np.argmax(ok)), len(ok) - 1 - int(np.argmax(ok[::-1]))
    yt, yn = ys[max(i0 - 1, 0)], ys[min(i1 + 1, len(ys) - 1)]
    right = [(max(xfun(y, z), 0.05), y) for y in _cos_stations(yt, yn)]
    pts = ([bd.Vector(0, yt, z)] + [bd.Vector(x, y, z) for x, y in right] +
           [bd.Vector(0, yn, z)] + [bd.Vector(-x, y, z) for x, y in reversed(right)])
    return closed_spline(pts)


def _bell_base_body(cavity: bool) -> bd.Solid:
    zs, zl, zb = P.Z_SPLIT, P.Z_LIP, P.Z_BASE
    z0 = zb + (P.FLOOR if cavity else 0.0)
    below = list(np.linspace(z0, zl, 9)) + [zl - getattr(P, "LIP_BAND", 0.0)]
    above = list(zl + (zs - zl) * np.linspace(0, 1, 14) ** 1.6)
    levels = sorted(set(round(v, 5) for v in below + above))
    if cavity:
        levels.append(zs + 1.0)
    wires = []
    for z in levels:
        if not cavity and abs(z - zs) < 1e-9:
            wires.append(contour_wire(zs))     # identical to the dome's base
            continue
        d_tip = -bell_offset(P.Y_TAIL, z, skirt=_skirt_end()) + (P.WALL if cavity else 0.0)
        wires.append(bell_wire(z, bell_cavity_x if cavity else bell_x, d_tip))
    return bd.Solid.make_loft(wires, ruled=False)


@lru_cache(maxsize=2)
def base_body(cavity: bool = False) -> bd.Solid:
    if getattr(P, "Z_LIP", None) is not None:
        return _bell_base_body(cavity)
    zs, zb = P.Z_SPLIT, P.Z_BASE
    H = zs - zb
    z0 = zb + (P.FLOOR if cavity else 0.0)
    # dense near the parting line (u^1.6 spacing): with sparse contours there
    # the smooth loft bulged past the parting outline and lost its draft
    ks = 14
    levels = sorted(zs - (zs - z0) * (k / ks) ** 1.6 for k in range(ks + 1))
    if cavity:
        levels.append(zs + 1.0)        # poke through the parting plane
    tb_end = form_at(P.Y_TAIL)["tumble"]
    wires = []
    for z in levels:
        u = min(1.0, (zs - z) / H)
        r = roll(u)
        if not cavity and abs(z - zs) < 1e-9:
            wires.append(contour_wire(zs))     # identical to the dome's base
            continue

        def d_side(y, r=r, u=u):
            # under a thumb shelf the base tucks in by tumble + flare, so the
            # footprint on the desk is unchanged
            f = form_at(y)
            tb = f["tumble"] + f["flare"]
            wall = P.WALL * math.sqrt(1 + roll_slope(u, tb) ** 2) if cavity else 0.0
            return tb * r + wall

        wall_end = P.WALL * math.sqrt(1 + roll_slope(u, tb_end) ** 2) if cavity else 0.0
        wires.append(plan_wire(z, d_side, tb_end * r + wall_end))
    return bd.Solid.make_loft(wires, ruled=False)


# --------------------------------------------------------------- public
def top_outer():
    return top_body(0.0)


def top_cavity():
    """Cavity of the top: inset by WALL (ends by WALL + 1), extended 0.6 mm
    below the parting plane so it cuts cleanly."""
    return top_body(P.WALL, dend=P.WALL + 1.0, below=0.6)


def base_outer():
    return base_body(False)


def base_cavity():
    return base_body(True)


def outer() -> bd.Compound:
    """Whole outer form (top + base meeting on the parting plane)."""
    return bd.Compound(children=[top_outer(), base_outer()])


def cavity() -> bd.Compound:
    return bd.Compound(children=[top_cavity(), base_cavity()])


@lru_cache(maxsize=1)
def top_shell_raw() -> bd.Solid:
    return (top_outer() - top_cavity()).solids()[0]


@lru_cache(maxsize=1)
def base_shell_raw() -> bd.Solid:
    return (base_outer() - base_cavity()).solids()[0]


# ------------------------------------------------------------- probing
def _hits(shape, origin, direction):
    from OCP.BRepIntCurveSurface import BRepIntCurveSurface_Inter
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt

    it = BRepIntCurveSurface_Inter()
    it.Init(shape.wrapped, gp_Lin(gp_Pnt(*origin), gp_Dir(*direction)), 1e-6)
    out = []
    while it.More():
        p = it.Pnt()
        out.append((p.X(), p.Y(), p.Z()))
        it.Next()
    return out


def surface_z(shape, x, y, from_top=True) -> float:
    zs = [p[2] for p in _hits(shape, (x, y, -10), (0, 0, 1))]
    if not zs:
        raise ValueError(f"no surface at ({x}, {y})")
    return max(zs) if from_top else min(zs)


def half_width(shape, y, z) -> float:
    xs = [p[0] for p in _hits(shape, (-100, y, z), (1, 0, 0))]
    if not xs:
        raise ValueError(f"no surface at y={y}, z={z}")
    return max(xs)


if __name__ == "__main__":
    import time
    for name, fn in (("top_outer", top_outer), ("top_cavity", top_cavity),
                     ("base_outer", base_outer), ("base_cavity", base_cavity),
                     ("top_shell", top_shell_raw), ("base_shell", base_shell_raw)):
        t = time.time()
        s = fn()
        bb = s.bounding_box()
        print(f"{name:12s} valid {s.is_valid} faces {len(s.faces()):3d} vol {s.volume:9.0f} "
              f"size {tuple(round(v, 2) for v in bb.size)} minz {bb.min.Z:.2f} "
              f"{time.time()-t:.1f}s")
