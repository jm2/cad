"""Base (bottom housing), battery door and skates.

Base: rolled flanks up to the parting plane, floor, battery channel (inverted
U, open to the door), receiver garage (pocket opening on the underside),
screw bosses with counterbores under the skates, board standoffs, sensor
window, USB-C opening in the nose, power-switch slot and connect-button hole,
skate pockets.

Door: the floor inside the battery aperture, inset by GAP, with two hinge
hooks at the tail end and a snap latch at the front.
"""

from __future__ import annotations

import math
from functools import lru_cache

import build123d as bd

import form
import layout as L
import params as P

FT = L.FLOOR_TOP
LATCH_X = (-5.5, 5.5)      # door snap latches, offset from the battery axis


def zbox(x0, x1, y0, y1, z0, z1) -> bd.Solid:
    return L.box((x0 + x1) / 2, (y0 + y1) / 2, z0, x1 - x0, y1 - y0, z1 - z0)


def oval(cx, cy, lx, ly, z0, h) -> bd.Part:
    with bd.BuildSketch(bd.Plane.XY.offset(z0)) as sk:
        with bd.Locations((cx, cy)):
            bd.SlotOverall(max(lx, ly), min(lx, ly), rotation=0 if lx >= ly else 90)
    return bd.extrude(sk.sketch, amount=h)


def skate_spots():
    """(cx, cy, lx, ly) of every skate."""
    s = [(x, y, *P.SKATE) for x, y in P.SCREW_XY]
    fx, fy = P.SKATE_FRONT_XY
    s += [(-fx, fy, *P.SKATE_FRONT), (fx, fy, *P.SKATE_FRONT)]
    y0, y1 = P.BAT_Y
    s.append((P.BAT_X, (y0 + y1) / 2, 9.0, 30.0))          # on the door
    return s


def door_aperture():
    """(x0, x1, y0, y1) of the battery door opening."""
    return (P.BAT_X - L.BAT_R_IN, P.BAT_X + L.BAT_R_IN, P.BAT_Y[0], P.BAT_Y[1])


TEAR_CAP_OUT = L.TOPB_Z - 1.0            # flat top of the channel (FDM)
TEAR_CAP_IN = TEAR_CAP_OUT - P.BAT_WALL


def _teardrop_y(cx, y0, cz, r, length, cap) -> bd.Part:
    """Cylinder along +Y with a 45-degree roof, flat-topped at z=cap: prints
    without support (45 deg flanks + a short bridge)."""
    c = L.cyl_y(cx, y0, cz, 2 * r, length)
    d = r * math.sqrt(2)
    diamond = bd.Pos(cx, y0 + length / 2, cz) * bd.Rot(0, 45, 0) * bd.Box(d, length, d)
    upper = L.box(cx, y0 + length / 2, cz, 2 * r + 2, length, cap - cz)
    return c + (diamond & upper)


def channel_roof_z(x) -> float:
    """Outer roof height of the battery channel at offset x from its axis."""
    import math as m
    r = L.BAT_R_OUT
    circ = L.BAT_AXIS_Z + m.sqrt(max(r * r - x * x, 0))
    if not P.FDM:
        return circ
    return min(TEAR_CAP_OUT, max(circ, L.BAT_AXIS_Z + r * m.sqrt(2) - abs(x)))


def battery_channel() -> bd.Part:
    y0, y1 = P.BAT_Y
    t = P.BAT_WALL
    if P.FDM:     # teardrop bore and roof: the overhang stays within 45 deg
        outer = _teardrop_y(P.BAT_X, y0 - t, L.BAT_AXIS_Z, L.BAT_R_OUT, y1 - y0 + 2 * t, TEAR_CAP_OUT)
        inner = _teardrop_y(P.BAT_X, y0, L.BAT_AXIS_Z, L.BAT_R_IN, y1 - y0, TEAR_CAP_IN)
    else:
        outer = L.cyl_y(P.BAT_X, y0 - t, L.BAT_AXIS_Z, 2 * L.BAT_R_OUT, y1 - y0 + 2 * t)
        inner = L.cyl_y(P.BAT_X, y0, L.BAT_AXIS_Z, 2 * L.BAT_R_IN, y1 - y0)
    # fill under the tube's lower half down to the floor, then hollow
    skirt = zbox(P.BAT_X - L.BAT_R_OUT, P.BAT_X + L.BAT_R_OUT, y0 - t, y1 + t,
                 P.Z_BASE + 0.1, L.BAT_AXIS_Z)
    ch = (outer + skirt) - inner
    ch -= zbox(P.BAT_X - L.BAT_R_IN, P.BAT_X + L.BAT_R_IN, y0, y1, -1, L.BAT_AXIS_Z)
    # contact slots in the end walls (spring plate / flat contact tabs)
    ch -= zbox(-5.5, 5.5, y0 - t - 0.1, y0 - t + 0.8, L.BAT_AXIS_Z - 5, L.BAT_AXIS_Z + 5.5)
    return ch


def receiver_garage():
    """(walls to add, pocket to cut) for the underside receiver garage."""
    x, y = P.RECEIVER_XY
    rx, ry, rz = P.RECEIVER
    c = P.FIT
    pocket = zbox(x - rx / 2 - c, x + rx / 2 + c, y - ry / 2 - c, y + ry / 2 + c, -1, P.Z_BASE + rz + 0.6)
    walls = zbox(x - rx / 2 - c - P.WALL, x + rx / 2 + c + P.WALL, y - ry / 2 - c - P.WALL,
                 y + ry / 2 + c + P.WALL, P.Z_BASE + 0.1, P.Z_BASE + rz + 0.6 + P.FLOOR)
    # finger notch to pull the receiver out
    notch = L.cyl_z(x, y - ry / 2, -1, 9.0, P.Z_BASE + 2.5)
    return walls, pocket + notch


def boss(x, y):
    """Base boss under the top-shell boss: clearance hole + counterbore for
    the screw head (the head sits under a skate)."""
    hd, hh = P.SCREW_HEAD
    col = L.post_z(x, y, P.Z_BASE + 0.1, P.BOSS_OD + 1.0, P.Z_SPLIT - P.Z_BASE - 0.1)
    hole = L.cyl_z(x, y, -1, P.SCREW_D + 0.4, P.Z_SPLIT + 2)
    cbore = L.cyl_z(x, y, -1, hd + 0.4, L.SCREW_HEAD_Z + hh + 0.2 + 1)
    return col, hole + cbore


def standoffs():
    out = []
    # main board: four pads under its corners/edges
    for x, y in ((-18.0, 10.0), (18.0, 10.0), (-18.0, 55.0), (18.0, 55.0)):
        out.append(L.post_z(x, y, FT - 0.1, 4.0, P.PCB_Z - FT + 0.1))
    # side boards: two posts each, up to the board's lower edge
    xb = L.side_board_x() - P.PCB_T / 2
    for sgn in (-1, 1):
        for y in (L.SIDEB_Y[0] + 4.0, L.SIDEB_Y[1] - 4.0):
            out.append(L.box(sgn * xb, y, FT - 0.1, 3.0, 4.0, L.SIDEB_Z[0] - FT + 0.1))
    # top board: two posts on the battery channel, two from the floor
    for y in (-6.0, 1.0):
        for sgn in (-1, 1):
            # start just inside the channel's outer roof (never in the bore)
            z0 = channel_roof_z(7.0) - 0.5
            out.append(L.post_z(sgn * 7.0, y, z0, 3.0, L.TOPB_Z - z0))
    return out


def topboard_front_posts():
    """Front supports of the top board stand on the main board, beside the
    sensor IC (a floor post there would pass through the lens)."""
    return [L.cyl_z(s * 8.0, 18.0, L.PCB_TOP, 3.0, L.TOPB_Z - L.PCB_TOP) for s in (-1, 1)]


def nose_tabs():
    """Locating tabs rising from the base rim into the top shell at the nose
    (all screws are behind the buttons). On the base, so the top shell's rim
    prints flat on the bed in the FDM variant."""
    _, y = P.NOSE_TAB_XY
    tx, ty, h = P.NOSE_TAB
    xt = form.half_width(form.top_cavity(), y, P.Z_SPLIT + h) - 0.2
    out = []
    for sgn in (-1, 1):
        lo = zbox(xt - tx, xt + 3.0, y - ty / 2, y + ty / 2, P.Z_SPLIT - 2.5, P.Z_SPLIT) & form.base_outer()
        hi = zbox(xt - tx, xt, y - ty / 2, y + ty / 2, P.Z_SPLIT - 0.01, P.Z_SPLIT + h)
        t = lo + hi
        out.append(t.mirror(bd.Plane.YZ) if sgn < 0 else t)
    return out


@lru_cache(maxsize=1)
def build_base() -> dict[str, bd.Solid]:
    b = form.base_shell_raw()
    clip = form.base_outer()                  # keep internal features inside
    add = battery_channel()
    walls, pocket = receiver_garage()
    add += walls
    cuts = [pocket]
    for x, y in P.SCREW_XY:
        col, hole = boss(x, y)
        add += col
        cuts.append(hole)
    for s in standoffs():
        add += s
    b = b + (add & clip)
    for t in nose_tabs():
        b = b + t
    # openings
    ax0, ax1, ay0, ay1 = door_aperture()
    cuts.append(zbox(ax0, ax1, ay0, ay1, -1, FT + 0.01))
    sx, sy = P.SENSOR_XY
    wx, wy = P.SENSOR_WINDOW
    cuts.append(zbox(sx - wx / 2, sx + wx / 2, sy - wy / 2, sy + wy / 2, -1, FT + 1))
    # lens pocket: the lens must sit LENS_TO_DESK above the desk whatever
    # the floor thickness (the FDM floor is thicker)
    lx, ly, _ = P.LENS
    cuts.append(zbox(sx - lx / 2 - P.FIT, sx + lx / 2 + P.FIT, sy - ly / 2 - P.FIT,
                     sy + ly / 2 + P.FIT, P.LENS_TO_DESK - 0.3, FT + 1))
    px, py = P.POWER_SW_XY
    cuts.append(zbox(px - 2.6, px + 2.6, py - 1.2, py + 1.2, -1, FT + 1))
    cx, cy = P.CONN_BTN_XY
    cuts.append(L.cyl_z(cx, cy, -1, 4.2, FT + 2))
    w, h = P.USBC_PLUG
    zc = P.PCB_Z + P.PCB_T / 2
    usb = bd.Pos(0, L.USBC_FRONT - 0.5, zc) * bd.Rot(-90, 0, 0) * bd.extrude(
        bd.Sketch() + bd.RectangleRounded(w, h, h / 2 - 0.01), amount=20)
    cuts.append(usb)
    for (cx_, cy_, lx, ly) in skate_spots():
        cuts.append(oval(cx_, cy_, lx + 0.2, ly + 0.2, P.Z_BASE - 1, 1 + P.SKATE_RECESS))
    # pockets in the channel end walls for the door's hinge hooks and latch
    for sgn in (-1, 1):
        hx = P.BAT_X + sgn * 4.0
        cuts.append(zbox(hx - 1.5 - P.FIT, hx + 1.5 + P.FIT, ay0 - 2.3, ay0 + 0.1, FT - 0.01, FT + 1.5))
    for lx in LATCH_X:
        cuts.append(zbox(P.BAT_X + lx - 1.25 - P.FIT, P.BAT_X + lx + 1.25 + P.FIT,
                         ay1 - 0.1, ay1 + 1.1, FT - 0.01, FT + 1.4))
    for c in cuts:
        b = b - c
    base = b.solids()[0] if len(b.solids()) == 1 else max(b.solids(), key=lambda s: s.volume)

    # battery door: the floor slab inside the aperture, inset by GAP
    g = P.GAP
    slab = form.base_outer() & zbox(ax0 + g, ax1 - g, ay0 + g, ay1 - g, -1, FT)
    door = slab
    # hinge hooks at the tail end: tabs reaching under the floor's inner edge
    for sgn in (-1, 1):
        door += zbox(P.BAT_X + sgn * 4.0 - 1.5, P.BAT_X + sgn * 4.0 + 1.5,
                     ay0 - 2.0, ay0 + g + 0.5, FT + 0.2, FT + 1.2)
        door += zbox(P.BAT_X + sgn * 4.0 - 1.5, P.BAT_X + sgn * 4.0 + 1.5,
                     ay0 + g, ay0 + g + 0.5, FT - 0.5, FT + 1.2)
    # snap latch at the front: a cantilever whose hook catches the floor's
    # top surface beyond the aperture edge
    # (two, either side of the battery's front end, where it curves away)
    for lx in LATCH_X:
        x0, x1 = P.BAT_X + lx - 1.25, P.BAT_X + lx + 1.25
        door += zbox(x0, x1, ay1 - g - 0.9, ay1 - g, FT - 0.5, FT + 1.1)
        door += zbox(x0, x1, ay1 - g - 0.9, ay1 + 0.8, FT + 0.1, FT + 1.1)
    door -= oval(P.BAT_X, (ay0 + ay1) / 2, 9.2, 30.2, P.Z_BASE - 1, 1 + P.SKATE_RECESS)
    door = door.solids()[0] if len(door.solids()) == 1 else door

    parts = {"base": base, "door": door}
    posts = topboard_front_posts()
    parts["topb_post_l"], parts["topb_post_r"] = posts[0].solids()[0], posts[1].solids()[0]
    for i, (cx_, cy_, lx, ly) in enumerate(skate_spots()):
        parts[f"skate_{i + 1}"] = oval(cx_, cy_, lx, ly, P.Z_BASE - (P.SKATE_T - P.SKATE_RECESS),
                                       P.SKATE_T).solids()[0]
    return parts
