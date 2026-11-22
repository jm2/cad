"""Internal layout: placeholder bodies for bought-in parts (boards, switches,
sensor, battery, connectors, screws) and the positions everything else is
designed around. Real electronics are out of scope; these are envelopes.

Every position is derived from params.py and the master form, so moving a
parameter moves the dependent parts and the checks follow.
"""

from __future__ import annotations

import math
from functools import lru_cache

import build123d as bd

import form
import params as P

MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def box(cx, cy, z0, sx, sy, sz) -> bd.Solid:
    return bd.Pos(cx, cy, z0) * bd.Box(sx, sy, sz, align=MIN)


def cyl_z(cx, cy, z0, d, h) -> bd.Solid:
    return bd.Pos(cx, cy, z0) * bd.Cylinder(d / 2, h, align=MIN)


def post_z(cx, cy, z0, d, h, free_end="top") -> bd.Solid:
    """Vertical post/boss of diameter d at its root; in the moulded variant
    it tapers by BOSS_DRAFT toward its free end so it releases from the tool."""
    if not P.BOSS_DRAFT:
        return cyl_z(cx, cy, z0, d, h)
    r_root = d / 2
    r_free = max(r_root - h * math.tan(math.radians(P.BOSS_DRAFT)), 0.3)
    rb, rt = (r_root, r_free) if free_end == "top" else (r_free, r_root)
    return bd.Pos(cx, cy, z0) * bd.Cone(rb, rt, h, align=MIN)


def cyl_x(x0, cy, cz, d, length) -> bd.Solid:
    """Cylinder along +X starting at x0."""
    return bd.Pos(x0, cy, cz) * bd.Rot(0, 90, 0) * bd.Cylinder(d / 2, length, align=MIN)


def cyl_y(cx, y0, cz, d, length) -> bd.Solid:
    """Cylinder along +Y starting at y0."""
    return bd.Pos(cx, y0, cz) * bd.Rot(-90, 0, 0) * bd.Cylinder(d / 2, length, align=MIN)


# ------------------------------------------------------------ derived values
PCB_TOP = P.PCB_Z + P.PCB_T
FLOOR_TOP = P.Z_BASE + P.FLOOR

# battery: rests on the door (flush with the floor top), axis along Y
BAT_AXIS_Z = FLOOR_TOP + P.BAT_CLEAR + P.AA_D / 2
BAT_R_IN = P.AA_D / 2 + P.BAT_CLEAR
BAT_R_OUT = BAT_R_IN + P.BAT_WALL

# top board (DPI + mode switches) above the battery channel
TOPB_Z = BAT_AXIS_Z + BAT_R_OUT + 1.2
TOPB_Y = (-9.0, 20.0)
TOPB_W = 20.0

# side boards (one per flank) for the side buttons
SIDEB_Y = (-17.0, 16.0)
SIDEB_Z = (P.SIDE_BTN_Z - 6.0, P.SIDE_BTN_Z + 4.5)   # top kept under the FDM hinge


@lru_cache(maxsize=1)
def wheel_axis_z() -> float:
    top = form.surface_z(form.outer(), 0.0, P.WHEEL_Y)
    return top + P.WHEEL_PROUD - P.WHEEL_D / 2


@lru_cache(maxsize=1)
def side_inner_x() -> float:
    """Smallest |x| of the top shell's inner flank over the side buttons'
    flange footprints (the flange must clear it)."""
    fl = 1.2  # = P.FLANGE (kept literal to avoid an import cycle in docs)
    ly, lz, zc = P.SIDE_BTN_LEN, P.SIDE_BTN_H, P.SIDE_BTN_Z
    return min(form.half_width(form.top_cavity(), y, z)
               for cy in P.SIDE_BTN_Y
               for y in (cy - ly / 2 - fl, cy, cy + ly / 2 + fl)
               for z in (zc - lz / 2 - fl, zc, zc + lz / 2 + fl))


@lru_cache(maxsize=1)
def side_board_x() -> float:
    """Outer face (+x side) of the right side board: flange clearance 0.3 +
    flange + 1.0 mm post + pre-travel + switch stem height."""
    return (side_inner_x() - 0.3 - P.FLANGE_T - 1.0 - P.SW_PRETRAVEL
            - P.SW_TACT_PLUNGER[1])


# ------------------------------------------------------------------- parts
def board_outline(y0, y1, z0, z1, clear=1.0, step=2.0) -> bd.Face:
    """Symmetric plan outline that fits inside the cavity between heights
    z0..z1 with `clear` mm to the walls, from y0 to y1 (sampled every step)."""
    import numpy as np

    cav = form.cavity()
    ys = list(np.arange(y0, y1, step)) + [y1]
    xs = [min(form.half_width(cav, y, z0), form.half_width(cav, y, z1)) - clear for y in ys]
    right = [bd.Vector(x, y, 0) for x, y in zip(xs, ys)]
    left = [bd.Vector(-x, y, 0) for x, y in zip(reversed(xs), reversed(ys))]
    edges = [bd.Edge.make_spline(right),
             bd.Edge.make_line(right[-1], left[0]),
             bd.Edge.make_spline(left),
             bd.Edge.make_line(left[-1], right[0])]
    return bd.Face(bd.Wire(edges))


@lru_cache(maxsize=1)
def pcb_main() -> bd.Solid:
    """Main board: fills the cavity between PCB_Y with 1 mm clearance, with
    clearance holes for the front screw bosses."""
    f = board_outline(P.PCB_Y[0], P.PCB_Y[1], P.PCB_Z, PCB_TOP)
    board = bd.extrude(f.moved(bd.Location((0, 0, P.PCB_Z))), amount=P.PCB_T)
    for x, y in P.SCREW_XY:
        if P.PCB_Y[0] < y < P.PCB_Y[1]:
            board -= cyl_z(x, y, P.PCB_Z - 1, P.BOSS_OD + 1.0, P.PCB_T + 2)
    # slot for the mid-mount USB-C receptacle (straddles the board)
    w, l, h = P.USBC
    board -= box(0, USBC_FRONT - l / 2 - 1.0, P.PCB_Z - 1, w + 0.4, l + 2.0, P.PCB_T + 2)
    return board.solids()[0]


def pcb_top() -> bd.Solid:
    return box(0, sum(TOPB_Y) / 2, TOPB_Z, TOPB_W, TOPB_Y[1] - TOPB_Y[0], P.PCB_T)


def pcb_side(sign: int) -> bd.Solid:
    x_out = side_board_x()
    return box(sign * (x_out - P.PCB_T / 2), sum(SIDEB_Y) / 2, SIDEB_Z[0],
               P.PCB_T, SIDEB_Y[1] - SIDEB_Y[0], SIDEB_Z[1] - SIDEB_Z[0])


def sensor() -> bd.Solid:
    x, y = P.SENSOR_XY
    lx, ly, lh = P.LENS
    lens = box(x, y, P.PCB_Z - lh, lx, ly, lh)
    ic = box(x, y, PCB_TOP, *P.SENSOR_IC)
    return (lens + ic).solids()[0] if len((lens + ic).solids()) == 1 else bd.Compound(children=[lens, ic])


def switch_main(x, y) -> bd.Solid:
    """12.8 x 5.8 tactile switch on the main board, plunger centred."""
    sx, sy, sh = P.SW_MAIN
    body = box(x, y, PCB_TOP, sx, sy, sh)
    d, top = P.SW_PLUNGER
    return (body + cyl_z(x, y, PCB_TOP + sh - 0.1, d, top - sh + 0.1)).solids()[0]


def plunger_top_main() -> float:
    return PCB_TOP + P.SW_PLUNGER[1]


def tact(x, y, z0, axis: str = "+z") -> bd.Solid:
    """6x6 tact switch whose base sits on z0 (or on a board face for side
    boards: axis '+x' / '-x' means the stem points along that direction)."""
    bx, by, bh = P.SW_TACT
    sd, stop = P.SW_TACT_PLUNGER
    s = box(0, 0, 0, bx, by, bh) + cyl_z(0, 0, bh - 0.1, sd, stop - bh + 0.1)
    if axis == "+z":
        return bd.Pos(x, y, z0) * s
    if axis == "-z":
        return bd.Pos(x, y, z0) * bd.Rot(180, 0, 0) * s
    if axis == "+x":
        return bd.Pos(z0, y, x) * bd.Rot(0, 90, 0) * s
    if axis == "-x":
        return bd.Pos(z0, y, x) * bd.Rot(0, -90, 0) * s
    raise ValueError(axis)


def tact_stem_len() -> float:
    return P.SW_TACT_PLUNGER[1]


USBC_FRONT = 60.0
USBC_Z = P.PCB_Z + P.PCB_T / 2      # receptacle / plug axis height


def usb_plug() -> bd.Part:
    """Oversized USB-C cable plug, fully inserted: overmold envelope + cable
    running straight forward. Not a part of the mouse: test_model checks it
    clears everything (the cable must plug in while the mouse is in use)."""
    w, h, ln = P.USBC_PLUG
    y0 = USBC_FRONT + 0.2               # overmold face seats on the receptacle
    om = bd.Pos(0, y0 + ln / 2, USBC_Z) * bd.Box(w, ln, h)
    om = om.fillet(min(h / 2 - 0.1, 2.5), om.edges().filter_by(bd.Axis.Y))
    cable = cyl_y(0, y0 + ln - 1, USBC_Z, P.USBC_CABLE_D, 60)
    return om + cable


def usb_c() -> bd.Solid:
    w, l, h = P.USBC
    return box(0, USBC_FRONT - l / 2, P.PCB_Z + P.PCB_T / 2 - h / 2, w, l, h)


def battery() -> bd.Solid:
    y0 = P.BAT_Y[0] + P.BAT_SPRING_COMP
    return cyl_y(P.BAT_X, y0, BAT_AXIS_Z, P.AA_D, P.AA_L)


def bat_spring() -> bd.Solid:
    """Conical spring contact, compressed (negative end, at the tail)."""
    y0 = P.BAT_Y[0]
    cone = bd.Pos(P.BAT_X, y0, BAT_AXIS_Z) * bd.Rot(-90, 0, 0) * bd.Cone(
        4.5, 2.0, P.BAT_SPRING_COMP, align=MIN)
    plate = cyl_y(P.BAT_X, y0 - 0.4, BAT_AXIS_Z, 11.0, 0.4)
    return (cone + plate).solids()[0]


def bat_plate() -> bd.Solid:
    y1 = P.BAT_Y[1]
    return cyl_y(P.BAT_X, y1 - P.BAT_PLATE_T, BAT_AXIS_Z, 9.0, P.BAT_PLATE_T)


def receiver() -> bd.Solid:
    """2.4 GHz receiver stowed in its underside garage (lying flat, its
    bottom 0.3 mm inside the base face)."""
    x, y = P.RECEIVER_XY
    rx, ry, rz = P.RECEIVER
    return box(x, y, P.Z_BASE + 0.3, rx, ry, rz)


def encoder() -> bd.Solid:
    """Hall-sensor board (dummy) under the hub's ring magnet: a small board
    reaching from the right yoke arm, two Hall ICs facing the magnet rim."""
    od, _, t = P.ENC_MAGNET
    zc = wheel_axis_z()
    bt, bl = P.ENC_BOARD
    ic_h = 1.0
    z_ic_top = zc - od / 2 - P.ENC_GAP
    z_b1 = z_ic_top - ic_h
    xm = P.ENC_MAGNET_X + t / 2
    board = box((xm - 2.0 + P.YOKE_ARM_X[1]) / 2, P.WHEEL_Y, z_b1 - bt,
                P.YOKE_ARM_X[1] - (xm - 2.0), bl, bt)
    ics = box(xm, P.WHEEL_Y - 1.6, z_b1, 1.6, 2.0, ic_h) + box(xm, P.WHEEL_Y + 1.6, z_b1, 1.6, 2.0, ic_h)
    return (board + ics).solids()[0] if len((board + ics).solids()) == 1 else bd.Compound(children=[board, ics])


def sw_click() -> bd.Solid:
    """Wheel click: tact switch under the yoke's front beam."""
    return tact(0, P.YOKE_BEAM_Y[1] + P.YOKE_T / 2, PCB_TOP)


def sw_tilt(sign) -> bd.Solid:
    """Right-angle tact switch on the main board, stem pointing at the yoke
    arm's outer face (tilt left / right)."""
    bx, by, bz, stem = P.SW_RA
    arm_out = (P.YOKE_ARM_X[0] - P.YOKE_T) if sign < 0 else (P.YOKE_ARM_X[1] + P.YOKE_T)
    tip = arm_out + sign * P.SW_PRETRAVEL
    sx0 = tip + sign * stem                     # stem base = body face
    body_c = sx0 + sign * bx / 2
    body = box(body_c, P.WHEEL_Y, PCB_TOP, bx, by, bz)
    st = cyl_x(min(tip, sx0), P.WHEEL_Y, PCB_TOP + bz / 2, 1.6, stem)
    return (body + st).solids()[0]


def power_switch() -> bd.Solid:
    """Slide switch on the PCB underside, knob through the base floor."""
    x, y = P.POWER_SW_XY
    body = box(x, y, P.PCB_Z - 3.5, 8.6, 3.6, 3.5)
    knob = box(x, y, P.PCB_Z - 3.5 - 2.6, 1.5, 1.5, 2.7)
    return (body + knob).solids()[0]


def conn_button() -> bd.Solid:
    x, y = P.CONN_BTN_XY
    return tact(x, y, P.PCB_Z, "-z")


SCREW_L = 18.0     # M2 x 18: through the base boss into the top-shell boss
SCREW_HEAD_Z = P.Z_BASE + P.SKATE_RECESS + 0.1   # 0.1 above the skate's top


def screw(x, y) -> bd.Solid:
    """M2 pan head from below; head sits in a counterbore under a skate."""
    hd, hh = P.SCREW_HEAD
    z_head = SCREW_HEAD_Z
    head = cyl_z(x, y, z_head, hd, hh)
    shank = cyl_z(x, y, z_head + hh - 0.05, P.SCREW_D, SCREW_L + 0.05)
    return (head + shank).solids()[0]


def dummies() -> dict[str, bd.Solid]:
    d = {
        "pcb_main": pcb_main(),
        "pcb_top": pcb_top(),
        "pcb_side_l": pcb_side(-1),
        "pcb_side_r": pcb_side(+1),
        "sensor": sensor(),
        "sw_left": switch_main(*P.SW_L_XY),
        "sw_right": switch_main(*P.SW_R_XY),
        "usb_c": usb_c(),
        "battery": battery(),
        "bat_spring": bat_spring(),
        "bat_plate": bat_plate(),
        "receiver": receiver(),
        "encoder": encoder(),
        "sw_click": sw_click(),
        "sw_tilt_l": sw_tilt(-1),
        "sw_tilt_r": sw_tilt(+1),
        "power_switch": power_switch(),
        "conn_button": conn_button(),
    }
    # top-board switches: DPI up/down + wheel mode
    for i, y in enumerate(P.DPI_Y):
        d[f"sw_dpi_{'up' if i == 0 else 'down'}"] = tact(0, y, TOPB_Z + P.PCB_T)
    d["sw_mode"] = tact(0, P.MODE_BTN_Y, TOPB_Z + P.PCB_T)
    # side buttons: switches on the outer face of each side board
    x_out = side_board_x()
    for side, sign in (("l", -1), ("r", +1)):
        for i, y in enumerate(P.SIDE_BTN_Y):
            d[f"sw_side_{side}{i + 1}"] = tact(P.SIDE_BTN_Z, y, sign * x_out,
                                               "+x" if sign > 0 else "-x")
    for i, (x, y) in enumerate(P.SCREW_XY):
        d[f"screw_{i + 1}"] = screw(x, y)
    return d
