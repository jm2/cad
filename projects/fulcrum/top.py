"""Top shell and the buttons cut from it.

Main buttons (L/R)
  molded  slots along the inner and outer edges; the rear edge stays joined to
          the shell and is thinned underneath to FLEX_T over FLEX_BAND, so each
          button is a flexure moulded in one piece with the shell.
  fdm     slotted all round into separate parts; two L-shaped knuckles per
          button turn on a steel dowel held by lugs under the fixed shell.
  Each button carries a post that stops SW_PRETRAVEL above its switch plunger.

Small buttons (wheel mode, DPI up/down, 2 side buttons per flank)
  The pad is cut from the shell itself (flush with the surface, GAP all
  round), with a retaining flange behind the wall and a post to its switch.
"""

from __future__ import annotations

import math
from functools import lru_cache

import build123d as bd

import form
import layout as L
import params as P

MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)
BIG = 200.0


# ------------------------------------------------------------- helpers
def zbox(x0, x1, y0, y1, z0, z1) -> bd.Solid:
    return bd.Pos((x0 + x1) / 2, (y0 + y1) / 2, z0) * bd.Box(x1 - x0, y1 - y0, z1 - z0, align=MIN)


def strip(points, width, z0=None, z1=45.0) -> bd.Part:
    """Vertical slot cutter along a plan polyline (x, y), `width` wide."""
    z0 = P.Z_SPLIT - 1.0 if z0 is None else z0
    out = None
    for (xa, ya), (xb, yb) in zip(points[:-1], points[1:]):
        L_ = math.hypot(xb - xa, yb - ya)
        ang = math.degrees(math.atan2(yb - ya, xb - xa))
        seg = bd.Pos((xa + xb) / 2, (ya + yb) / 2, z0) * bd.Rot(0, 0, ang) * bd.Box(
            L_ + width, width, z1 - z0, align=MIN)
        out = seg if out is None else out + seg
    return out


def rrect_face(lx, ly, r, plane: bd.Plane) -> bd.Face:
    with bd.BuildSketch(plane) as sk:
        bd.RectangleRounded(lx, ly, min(r, 0.49 * min(lx, ly)))
    return sk.sketch.faces()[0]


def prism_z(cx, cy, lx, ly, r, z0, z1) -> bd.Part:
    f = rrect_face(lx, ly, r, bd.Plane.XY.offset(z0).shift_origin((cx, cy, z0)))
    return bd.extrude(f, amount=z1 - z0)


def prism_x(cy, cz, ly, lz, r, x0, x1) -> bd.Part:
    """Rounded-rect prism along +X from x0 to x1 (profile in YZ)."""
    pl = bd.Plane(origin=(x0, cy, cz), x_dir=(0, 1, 0), z_dir=(1, 0, 0))
    f = rrect_face(ly, lz, min(ly, lz) / 2, pl)
    return bd.extrude(f, amount=x1 - x0)


def ceiling(x, y) -> float:
    """Underside of the top shell (cavity roof) at (x, y)."""
    return form.surface_z(form.top_cavity(), x, y)


# ------------------------------------------------------ main button plan
def wheel_slot_half():
    return P.WHEEL_W / 2 + P.WHEEL_CLEAR


def wheel_slot_y():
    """(rear, front) y of the wheel opening: the full wheel diameter plus
    clearance (the shell slopes down ahead of the wheel, so a chord-sized
    slot leaves the tyre too close to the underside just past it)."""
    half = P.WHEEL_D / 2 + P.WHEEL_CLEAR
    return P.WHEEL_Y - half, P.WHEEL_Y + half


def outer_x(y):
    xn, xr = P.BTN_OUTER_X
    t = (P.Y_NOSE + 6 - y) / (P.Y_NOSE + 6 - P.BTN_REAR_Y)
    return xn + (xr - xn) * t


def spine_hw(y) -> float:
    """Half-width of the centre spine at y: narrow at the tail, widening to
    SPINE_HW[1] by y = +20 and constant forward of that."""
    a, b = P.SPINE_HW
    t = min(max((y - P.SPINE_Y[0]) / (20.0 - P.SPINE_Y[0]), 0.0), 1.0)
    return a + (b - a) * t


def spine_prism(extra=0.0, y0=None, y1=None, z0=None, h=60.0) -> bd.Part:
    """Vertical prism over the spine's plan outline grown by `extra`, with a
    rounded tail end and running out past the nose."""
    import numpy as np
    y0 = P.SPINE_Y[0] if y0 is None else y0
    y1 = P.SPINE_Y[1] if y1 is None else y1
    z0 = P.Z_SPLIT - 1.0 if z0 is None else z0
    r0 = spine_hw(y0) + extra
    ys = list(y0 - extra + (r0 + extra) * (1 - np.cos(np.linspace(0, math.pi / 2, 7)))) + \
        list(np.linspace(y0 + r0, y1, 24))[1:]
    right = []
    for y in ys:
        hw = spine_hw(y) + extra
        dy = (y0 + r0) - y
        if dy > 0:                       # rounded (elliptical) tail end
            hw *= math.sqrt(max(0.0, 1 - (dy / (r0 + extra)) ** 2))
        right.append(bd.Vector(max(hw, 0.0), y, 0))
    left = [bd.Vector(-v.X, v.Y, 0) for v in reversed(right)]
    pts = right + left[:-1] if right[0].X == 0 else right + left
    w = bd.Wire.make_polygon(pts, close=True)
    return bd.extrude(bd.Face(w).moved(bd.Location((0, 0, z0))), amount=h, dir=(0, 0, 1))


def flange_band(sign) -> bd.Part:
    """Plan band along one spine edge where its retaining flange runs (only
    behind the main buttons, under fixed shell)."""
    import numpy as np
    y0, y1 = P.SPINE_FLANGE_Y
    ys = np.linspace(y0, y1, 16)
    inner = [bd.Vector(sign * (spine_hw(y) - 1.0), y, 0) for y in ys]
    outer = [bd.Vector(sign * (spine_hw(y) + P.GAP / 2 + P.SPINE_FLANGE[0]), y, 0) for y in reversed(ys)]
    w = bd.Wire.make_polygon(inner + outer, close=True)
    return bd.extrude(bd.Face(w).moved(bd.Location((0, 0, P.Z_SPLIT))), amount=50, dir=(0, 0, 1))


def button_region(sign) -> bd.Solid:
    """Plan region of one main button (prism): from the spine gap to its
    outer slot line, from the rear edge out over the nose."""
    import numpy as np
    yN = P.Y_NOSE + 6
    ys = np.linspace(P.BTN_REAR_Y, yN, 16)
    inner = [(spine_hw(y) + P.GAP / 2, y) for y in ys]
    pts = inner + [(outer_x(yN), yN), (outer_x(P.BTN_REAR_Y), P.BTN_REAR_Y)]
    pts = [(sign * x, y) for x, y in pts]
    w = bd.Wire.make_polygon([bd.Vector(x, y, 0) for x, y in pts], close=True)
    f = bd.Face(w)
    # explicit +Z: the mirrored (left) outline has a reversed face normal,
    # and a plain extrude then went DOWN and missed the shell
    return bd.extrude(f.moved(bd.Location((0, 0, P.Z_SPLIT - 1))), amount=40, dir=(0, 0, 1))


def slot_lines(sign, rear=True):
    """Slot centre lines of one main button (the spine gap bounds its inner
    edge): the outer edge, plus the rear edge for separate (FDM) buttons."""
    yN = P.Y_NOSE + 6
    xr = spine_hw(P.BTN_REAR_Y) + P.GAP / 2
    lines = [[(outer_x(P.BTN_REAR_Y), P.BTN_REAR_Y), (outer_x(yN), yN)]]
    if rear:
        lines.append([(xr - P.GAP / 2, P.BTN_REAR_Y), (outer_x(P.BTN_REAR_Y), P.BTN_REAR_Y)])
    return [[(sign * x, y) for x, y in ln] for ln in lines]


# ---------------------------------------------------------- small buttons
SMALL_TOP = {   # name: (cx, cy, lx, ly, switch name)
    "btn_mode": (0.0, P.MODE_BTN_Y, P.MODE_BTN[0], P.MODE_BTN[1], "sw_mode"),
    "btn_dpi_up": (0.0, P.DPI_Y[0], P.DPI_BTN[0], P.DPI_BTN[1], "sw_dpi_up"),
    "btn_dpi_down": (0.0, P.DPI_Y[1], P.DPI_BTN[0], P.DPI_BTN[1], "sw_dpi_down"),
}


def small_side():
    out = {}
    for side, sign in (("l", -1), ("r", 1)):
        for i, y in enumerate(P.SIDE_BTN_Y):
            out[f"btn_side_{side}{i + 1}"] = (sign, y, f"sw_side_{side}{i + 1}")
    return out


def top_stem_z():
    return L.TOPB_Z + P.PCB_T + P.SW_TACT_PLUNGER[1]


def side_stem_x():
    return L.side_board_x() + P.SW_TACT_PLUNGER[1]


def small_top_button(cx, cy, lx, ly):
    r = min(lx, ly) / 2
    fl = P.FLANGE
    # flange sits below the lowest roof point over its footprint
    xs = [cx - lx / 2 - fl, cx, cx + lx / 2 + fl]
    ys = [cy - ly / 2 - fl, cy, cy + ly / 2 + fl]
    # the top buttons sit in the spine, whose underside is SPINE_RECESS
    # below the shell's
    roof = min(ceiling(x, y) for x in xs for y in ys) - P.SPINE_RECESS
    f_top = roof - 0.3
    f_bot = f_top - P.FLANGE_T
    pad = prism_z(cx, cy, lx, ly, r, f_bot, 60) & form.top_outer()
    flange = prism_z(cx, cy, lx + 2 * fl, ly + 2 * fl, r + fl, f_bot, f_top)
    stem = top_stem_z() + P.SW_PRETRAVEL
    post = L.post_z(cx, cy, stem, P.POST_D, f_bot - stem + 0.01, free_end="bottom")
    return (pad + flange + post).solids()[0], prism_z(cx, cy, lx + 2 * P.GAP, ly + 2 * P.GAP, r + P.GAP, f_top - 2, 60)


def small_side_button(sign, cy):
    ly, lz, zc = P.SIDE_BTN_LEN, P.SIDE_BTN_H, P.SIDE_BTN_Z
    fl = P.FLANGE
    f_out = L.side_inner_x() - 0.3
    f_in = f_out - P.FLANGE_T
    pad = prism_x(cy, zc, ly, lz, 0, f_in, 60) & form.top_outer()
    flange = prism_x(cy, zc, ly + 2 * fl, lz + 2 * fl, 0, f_in, f_out)
    stem = side_stem_x() + P.SW_PRETRAVEL
    post = L.cyl_x(stem, cy, zc, P.POST_D, f_in - stem + 0.01)
    btn = (pad + flange + post).solids()[0]
    cut = prism_x(cy, zc, ly + 2 * P.GAP, lz + 2 * P.GAP, 0, f_out - 2, 60)
    if sign < 0:
        btn = btn.mirror(bd.Plane.YZ)
        cut = cut.mirror(bd.Plane.YZ)
    return btn, cut


# ----------------------------------------------------------------- FDM hinge
def hinge_geom(sign):
    """(axis y, axis z, knuckle x-centres, lug x-centres) for one button:
    knuckle - lug - knuckle, packed between the spine and the side boards
    (inside the button's own plan region so the knuckles never touch the
    fixed spine)."""
    yr = P.BTN_REAR_Y
    kx, _ = P.HINGE_KNUCKLE
    xa = spine_hw(yr) + P.GAP / 2 + P.FIT + kx / 2 + 0.05
    xl = xa + kx + P.FIT + 0.05
    xb = xl + kx + P.FIT + 0.05
    ya = yr - 1.5
    za = min(ceiling(sign * x, yr) for x in (xa, xb)) - 3.2
    return ya, za, [sign * xa, sign * xb], [sign * xl]


def knuckle(x, ya, za, button_roof):
    kx, kl = P.HINGE_KNUCKLE
    yr = P.BTN_REAR_Y
    drop = zbox(x - kx / 2, x + kx / 2, yr + P.GAP / 2 + 0.3, yr + P.GAP / 2 + 3.3, za - 2.5, button_roof + 1)
    arm = zbox(x - kx / 2, x + kx / 2, ya - 2.5, yr + P.GAP / 2 + 3.3, za - 2.5, za + 2.5)
    k = drop + arm - L.cyl_x(x - kx, ya, za, P.HINGE_PIN_D + 2 * P.FIT, 2 * kx)
    return k


def lug(x, ya, za, roof):
    kx, _ = P.HINGE_KNUCKLE
    yr = P.BTN_REAR_Y
    b = zbox(x - kx / 2, x + kx / 2, ya - 2.5, yr - P.GAP / 2 - 0.3, za - 2.5, roof + 1)
    return b - L.cyl_x(x - kx, ya, za, P.HINGE_PIN_D + 0.05, 2 * kx)   # press fit pin


def hinge_pin(sign):
    ya, za, ks, ls = hinge_geom(sign)
    xs = sorted(ks + ls)
    kx, _ = P.HINGE_KNUCKLE
    x0, x1 = xs[0] - kx / 2 + 0.3, xs[-1] + kx / 2 - 0.3
    return L.cyl_x(x0, ya, za, P.HINGE_PIN_D, x1 - x0)


# ------------------------------------------------------- bosses and tabs
def top_boss(x, y):
    """(boss to add, hole to cut): moulded = self-tapping pilot; FDM = M2
    heat-set insert pocket with a pilot beyond it for the screw tip."""
    z0 = P.Z_SPLIT
    col = L.post_z(x, y, z0, P.BOSS_OD, ceiling(x, y) + 1.0 - z0, free_end="bottom") & form.top_outer()
    if P.MOLDED:
        hole = L.cyl_z(x, y, z0 - 1, P.BOSS_HOLE, 1 + 9.0)
    else:
        d, l = P.INSERT
        hole = L.cyl_z(x, y, z0 - 1, P.BOSS_HOLE, 1 + l + 0.5) + L.cyl_z(x, y, z0, 2.2, 9.0)
    return col, hole


# ------------------------------------------------------------------ build
def post(x, y):
    z0 = L.plunger_top_main() + P.SW_PRETRAVEL
    return L.post_z(x, y, z0, P.POST_D, ceiling(x, y) + 1.0 - z0, free_end="bottom")


def build_spine(shell_raw) -> bd.Solid:
    """The spine: the shell's material inside the spine outline, dropped by
    SPINE_RECESS, with the wheel slot, retaining flanges under the fixed
    shell behind the buttons, and a pillar down to the main board at the
    front."""
    sp = shell_raw & spine_prism(0.0)
    sp = bd.Pos(0, 0, -P.SPINE_RECESS) * sp.solids()[0]
    ws0, ws1 = wheel_slot_y()
    xs = wheel_slot_half()
    sp = sp - zbox(-xs, xs, ws0, ws1, P.Z_SPLIT - 2, 50)
    # underside relief over the wheel hub (detent ring, encoder magnet)
    hub_r = max(8.5 / 2, P.ENC_MAGNET[0] / 2)
    z_rel = L.wheel_axis_z() + hub_r + 0.6
    sp = sp - zbox(-P.YOKE_ARM_X[1], P.YOKE_ARM_X[1], P.WHEEL_Y - 6, P.WHEEL_Y + 6, P.Z_SPLIT - 2, z_rel)
    layer = (bd.Pos(0, 0, -0.2) * form.top_cavity()) - (bd.Pos(0, 0, -0.2 - P.SPINE_FLANGE[1]) * form.top_cavity())
    for sign in (-1, 1):
        sp = sp + (layer & flange_band(sign))
    px, py = P.SPINE_PILLAR_XY
    top = ceiling(px, py) - P.SPINE_RECESS + 0.3
    sp = sp + L.cyl_z(px, py, L.PCB_TOP, 3.0, top - L.PCB_TOP)
    return sp


@lru_cache(maxsize=1)
def build_top() -> dict[str, bd.Solid]:
    raw = form.top_shell_raw()
    shell = raw
    parts = {}
    # screw bosses
    for x, y in P.SCREW_XY:
        col, hole = top_boss(x, y)
        shell = shell + col - hole
    # the spine is its own part: cut its outline (+ gap) out of the shell
    spine = build_spine(raw)
    shell = shell - spine_prism(P.GAP / 2)
    # small buttons: top ones in the spine, side ones in the shell
    for name, (cx, cy, lx, ly, _) in SMALL_TOP.items():
        btn, cut = small_top_button(cx, cy, lx, ly)
        spine = spine - cut
        parts[name] = btn
    for name, (sign, cy, _) in small_side().items():
        btn, cut = small_side_button(sign, cy)
        shell = shell - cut
        parts[name] = btn
    parts["spine"] = spine.solids()[0] if len(spine.solids()) == 1 else spine
    # main buttons
    for sign, name in ((-1, "btn_left"), (1, "btn_right")):
        for ln in slot_lines(sign, rear=P.FDM):
            shell = shell - strip(ln, P.GAP)
        # nose edge clears the base rim by NOSE_GAP (room for button travel)
        shell = shell - (button_region(sign) & zbox(-40, 40, -70, 80, P.Z_SPLIT - 1, P.Z_SPLIT + P.NOSE_GAP))
        sw = P.SW_L_XY if sign < 0 else P.SW_R_XY
        if P.MOLDED:
            x0 = spine_hw(P.BTN_REAR_Y) + P.GAP / 2
            band = zbox(min(sign * x0, sign * outer_x(P.BTN_REAR_Y)),
                        max(sign * x0, sign * outer_x(P.BTN_REAR_Y)),
                        P.BTN_REAR_Y - P.FLEX_BAND / 2, P.BTN_REAR_Y + P.FLEX_BAND / 2,
                        P.Z_SPLIT, 50)
            thin = bd.Pos(0, 0, P.WALL - P.FLEX_T) * form.top_cavity()
            shell = shell - (thin & band)
            shell = shell + post(*sw)
    if P.FDM:
        pieces = shell.solids()
        keep = []
        for pc in pieces:
            c = pc.center()
            if c.Y > P.BTN_REAR_Y and abs(c.X) > 1 and pc.volume > 100:
                sign = 1 if c.X > 0 else -1
                ya, za, ks, ls = hinge_geom(sign)
                sw = P.SW_L_XY if sign < 0 else P.SW_R_XY
                b = pc + post(*sw)
                for kxc in ks:
                    b = b + knuckle(kxc, ya, za, ceiling(kxc, P.BTN_REAR_Y + 2))
                parts["btn_left" if sign < 0 else "btn_right"] = b.solids()[0]
            else:
                keep.append(pc)
        shell = max(keep, key=lambda s: s.volume)
        for sign in (-1, 1):
            ya, za, ks, ls = hinge_geom(sign)
            for lxc in ls:
                shell = shell + lug(lxc, ya, za, ceiling(lxc, P.BTN_REAR_Y - 3))
            parts[f"pin_{'left' if sign < 0 else 'right'}"] = hinge_pin(sign)
    parts["top_shell"] = shell.solids()[0] if len(shell.solids()) == 1 else shell
    return parts
