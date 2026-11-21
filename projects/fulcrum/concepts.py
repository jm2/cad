"""Form concepts (styling exploration on the outer surfaces only).

    FULCRUM_CONCEPT=A|B|C  python -m tools.render concepts.py ...

A "spine"    recessed contrasting centre spine nose-to-tail (wheel, mode,
             DPI live in it); the main buttons become wings either side
B "sculpted" concave grip scoops on both flanks around the side buttons,
             plus a 0.6 mm shadow-line step where the top meets the base
C "chevron"  higher rear hump, lower front, tail cut by two drafted planes
             into a sharp backward-pointing chevron at the parting line
D "spine + rests"  A, plus a low symmetric shelf on each flank (thumb rest
             in one hand, ring/pinky rest in the other) with a concave groove
             above it; parting line lowered onto the shelf lip
E "spine + bell"   A, with the black base flaring out below the parting line
             like the foot of a bell curve into thin, wide symmetric rests
             (widest along the grip, a slight flare all round)
"""
import math
import os

import build123d as bd

import params as P

CONCEPT = os.environ.get("FULCRUM_CONCEPT", "A").upper()

if CONCEPT == "C":   # silhouette change must happen before form builds
    P.FORM["h"] = [27.0, 34.0, 38.5, 39.5, 38.0, 35.0, 31.0, 27.0, 23.5, 22.0]
    P.FORM["w"] = [30.0, 31.5, 32.0, 32.0, 31.0, 30.0, 29.0, 28.0, 27.0, 26.5]
    P.END_TAIL = 7.0

if CONCEPT == "D":
    P.Z_SPLIT = 13.0
    P.SHELF_H = 2.2
    P.FORM["w"] = [27.0, 29.5, 30.0, 29.8, 29.5, 28.8, 28.5, 28.5, 27.5, 27.0]
    P.FORM["flare"] = [0.0, 0.0, 1.0, 4.0, 5.0, 4.6, 2.4, 0.3, 0.0, 0.0]

if CONCEPT == "E":
    P.Z_LIP = 4.5            # lip (widest point) of the bell foot
    P.BELL_Q = 2.5           # concavity of the foot
    P.LIP_BAND = 1.0         # upright band at the lip (thickness)
    P.LIP_TUCK = 2.0         # rounded tuck from the lip to the underside
    P.TUCK_P = 1.6
    P.FORM["w"] = [27.0, 29.0, 29.5, 29.0, 28.5, 28.0, 28.0, 28.0, 27.5, 27.0]
    P.FORM["skirt"] = [1.0, 1.2, 2.5, 5.5, 7.0, 6.5, 4.0, 1.8, 1.0, 1.0]

import form      # noqa: E402
import layout as L   # noqa: E402
import wheel     # noqa: E402

NAME = f"concept_{CONCEPT}"
MIN = (bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN)


def _plan_strip(hw_of_y, y0, y1, z0=5.0, h=60.0, n=40):
    import numpy as np
    ys = list(np.linspace(y0, y1, n))
    right = [bd.Vector(hw_of_y(y), y, 0) for y in ys]
    left = [bd.Vector(-hw_of_y(y), y, 0) for y in reversed(ys)]
    w = bd.Wire([bd.Edge.make_spline(right), bd.Edge.make_line(right[-1], left[0]),
                 bd.Edge.make_spline(left), bd.Edge.make_line(left[-1], right[0])])
    return bd.extrude(bd.Face(w).moved(bd.Location((0, 0, z0))), amount=h, dir=(0, 0, 1))


def _wheel_and_slot():
    half_y = P.WHEEL_D / 2 + P.WHEEL_CLEAR
    xs = P.WHEEL_W / 2 + P.WHEEL_CLEAR
    slot = bd.Pos(0, P.WHEEL_Y, P.Z_SPLIT) * bd.Box(2 * xs, 2 * half_y, 40, align=MIN)
    return wheel.tyre(), slot


def _ellipsoid(c, a, b, cz_axes):
    from OCP.BRepBuilderAPI import BRepBuilderAPI_GTransform
    from OCP.gp import gp_GTrsf, gp_Mat, gp_XYZ
    s = bd.Solid.make_sphere(1.0)
    g = gp_GTrsf(gp_Mat(a, 0, 0, 0, b, 0, 0, 0, cz_axes), gp_XYZ(*c))
    return bd.Solid(BRepBuilderAPI_GTransform(s.wrapped, g, True).Shape())


def build():
    top, base = form.top_outer(), form.base_outer()
    tyre, slot = _wheel_and_slot()
    parts = {}
    if CONCEPT in ("A", "D", "E"):
        def hw(y):               # 6.5 mm wide half at the front, 2.5 at the tail
            t = min(max((y + 60) / 80, 0), 1)
            return 2.5 + 4.0 * t
        strip = _plan_strip(hw, -61, 70)
        gap = _plan_strip(lambda y: hw(y) + 0.4, -61.5, 71)
        spine = (top & strip) - slot
        parts["top"] = top - gap
        parts["spine"] = bd.Pos(0, 0, -0.6) * spine.solids()[0]
    elif CONCEPT == "B":
        top = form.top_body(0.6)                       # shadow line at the split
        for s in (-1, 1):
            w = form.form_at(0)["w"]
            scoop = _ellipsoid((s * (w + 25 - 2.4), -1.0, 22.5), 25, 46, 14)
            top = top - scoop
            base = base - scoop
        parts["top"] = top - slot
    else:   # C: chevron tail from two drafted planes meeting at the parting line
        yp = P.Y_TAIL + 0.5
        a = math.radians(30)
        big = 400
        # (subtract the far side: intersecting with the near side fails in OCCT)
        cut_top = bd.Pos(0, yp, P.Z_SPLIT) * bd.Rot(-math.degrees(a), 0, 0) * bd.Box(
            big, big, big, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER))
        cut_bot = bd.Pos(0, yp, P.Z_SPLIT) * bd.Rot(math.degrees(a), 0, 0) * bd.Box(
            big, big, big, align=(bd.Align.CENTER, bd.Align.MAX, bd.Align.CENTER))
        parts["top"] = (top - cut_top) - slot
        base = base - cut_bot
    parts["base"] = base
    parts["wheel"] = tyre
    return {k: (v.solids()[0] if len(v.solids()) == 1 else v) for k, v in parts.items()}


COLORS = {"top": "#c9d1dc", "base": "#3c4552", "spine": "#262b33", "wheel": "#2b2f36"}
