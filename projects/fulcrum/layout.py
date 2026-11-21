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
SIDEB_Z = (P.SIDE_BTN_Z - 6.0, P.SIDE_BTN_Z + 6.0)


@lru_cache(maxsize=1)
def wheel_axis_z() -> float:
    top = form.surface_z(form.outer(), 0.0, P.WHEEL_Y)
    return top + P.WHEEL_PROUD - P.WHEEL_D / 2


@lru_cache(maxsize=1)
def side_board_x() -> float:
    """Outer face (+x side) of the right side board: leaves room for switch
    body + stem + pre-travel + button post inside the flank."""
    inner = min(form.half_width(form.cavity(), y, P.SIDE_BTN_Z) for y in P.SIDE_BTN_Y)
    return inner - 2.5 - (P.SW_TACT[2] + 1.5)


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


def usb_c() -> bd.Solid:
    w, l, h = P.USBC
    y_front = 61.0
    return box(0, y_front - l / 2, P.PCB_Z + P.PCB_T / 2 - h / 2, w, l, h)


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
    x, y = RECEIVER_XY
    return box(x, y, FLOOR_TOP, *P.RECEIVER)


RECEIVER_XY = (BAT_R_OUT + 1.0 + P.RECEIVER[0] / 2, -26.0)


def encoder() -> bd.Solid:
    """Wheel encoder (dummy): on the right of the wheel, axle through it."""
    ex, ey, ez = P.ENCODER
    x0 = P.WHEEL_W / 2 + 1.6       # leaves room for the yoke arm
    return box(x0 + ex / 2, P.WHEEL_Y, wheel_axis_z() - ez / 2, ex, ey, ez)


def power_switch() -> bd.Solid:
    """Slide switch on the PCB underside, knob through the base floor."""
    x, y = P.POWER_SW_XY
    body = box(x, y, P.PCB_Z - 3.5, 8.6, 3.6, 3.5)
    knob = box(x, y, P.PCB_Z - 3.5 - 2.6, 1.5, 1.5, 2.7)
    return (body + knob).solids()[0]


def conn_button() -> bd.Solid:
    x, y = P.CONN_BTN_XY
    return tact(x, y, P.PCB_Z, "-z")


def screw(x, y) -> bd.Solid:
    """M2 pan head from below; head sits in a counterbore under a skate."""
    hd, hh = P.SCREW_HEAD
    z_head = P.Z_BASE + 0.2           # head underside 0.2 above base face
    head = cyl_z(x, y, z_head, hd, hh)
    shank = cyl_z(x, y, z_head + hh - 0.05, P.SCREW_D, 8.0 + 0.05)
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
