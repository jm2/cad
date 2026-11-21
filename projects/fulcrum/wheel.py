"""Scroll wheel module: one-piece metal wheel (die-cast zinc; FDM: printed with
steel dowel weights) with the magnetic encoder ring and
the detent ring (ratchet mode), steel axle, and the cradle (yoke) that floats
on the click switch and the two tilt switches.

The ratchet spring and the mode toggle's latch are not modelled (like the
PCB, they are bought-in / out of scope); the toggle button and its switch are.
"""

from __future__ import annotations

import math
from functools import lru_cache

import build123d as bd

import layout as L
import params as P


def _ring_x(x0, x1, r_in, r_out, y, z):
    return L.cyl_x(x0, y, z, 2 * r_out, x1 - x0) - L.cyl_x(x0 - 1, y, z, 2 * r_in, x1 - x0 + 2)


def wheel() -> bd.Solid:
    """One-piece metal wheel (moulded variant: die-cast zinc, plated): rim
    with machined axial ribs, web, hub boss out to the encoder magnet, and
    the ratchet detent ring. Its mass (~18 g) is the flywheel that makes
    free-spin coast. FDM variant: same part printed, with steel dowels
    pressed into the six web holes for mass (see weights())."""
    y, z = P.WHEEL_Y, L.wheel_axis_z()
    w, R = P.WHEEL_W, P.WHEEL_D / 2
    c = L.cyl_x(-w / 2, y, z, 2 * R, w)
    rib = bd.Box(w + 2, P.WHEEL_RIB[0], 2 * P.WHEEL_RIB[1])
    for k in range(P.WHEEL_TREAD_N):
        a = 360.0 * k / P.WHEEL_TREAD_N
        c -= bd.Pos(0, y, z) * bd.Rot(a, 0, 0) * bd.Pos(0, 0, R) * rib
    # recessed web faces: rim and hub stay full width
    for side in (-1, 1):
        x0 = side * (w / 2 - P.WHEEL_WEB_RECESS) if side > 0 else -w / 2 - 0.01
        c -= _ring_x(x0, x0 + P.WHEEL_WEB_RECESS + 0.01, 3.0, R - 2.0, y, z)
    od, idm, t = P.ENC_MAGNET
    c += L.cyl_x(w / 2 - 0.4, y, z, idm + 2.4, P.ENC_MAGNET_X - (w / 2 - 0.4) + t)
    ring = L.cyl_x(-w / 2 - 1.2, y, z, 8.5, 1.6)
    notch = bd.Box(3, 0.9, 1.0)
    for k in range(P.WHEEL_DETENTS):
        a = 360.0 * (k + 0.5) / P.WHEEL_DETENTS
        ring -= bd.Pos(-w / 2 - 0.4, y, z) * bd.Rot(a, 0, 0) * bd.Pos(0, 0, 4.25) * notch
    c += ring
    for k in range(6):
        a = math.radians(60 * k)
        c -= L.cyl_x(-w, y + 6.2 * math.cos(a), z + 6.2 * math.sin(a), _hole_d(), 2 * w)
    c -= L.cyl_x(-20, y, z, P.AXLE_D, 40)
    return c.solids()[0]


def _hole_d():
    return P.WHEEL_DOWEL[0] - 0.05 if P.FDM else 3.4   # FDM: press fit for dowels


def weights() -> dict[str, bd.Solid]:
    """FDM only: 3 x 6 mm steel dowels pressed into the wheel's web holes."""
    if not P.FDM:
        return {}
    y, z = P.WHEEL_Y, L.wheel_axis_z()
    d, l = P.WHEEL_DOWEL
    out = {}
    for k in range(6):
        a = math.radians(60 * k)
        out[f"wheel_dowel_{k + 1}"] = L.cyl_x(-l / 2, y + 6.2 * math.cos(a), z + 6.2 * math.sin(a), d, l)
    return out


def yoke_x():
    t = P.YOKE_T
    return (P.YOKE_ARM_X[0] - t, P.YOKE_ARM_X[0]), (P.YOKE_ARM_X[1], P.YOKE_ARM_X[1] + t)


def axle() -> bd.Solid:
    (l0, _), (_, r1) = yoke_x()
    return L.cyl_x(l0, P.WHEEL_Y, L.wheel_axis_z(), P.AXLE_D, r1 - l0)


def yoke() -> bd.Solid:
    y, z = P.WHEEL_Y, L.wheel_axis_z()
    t = P.YOKE_T
    (l0, l1), (r0, r1) = yoke_x()
    zb = L.PCB_TOP + P.SW_TACT_PLUNGER[1] + P.SW_PRETRAVEL   # sits on the click stem
    zt = zb + t
    yr0, yf0 = P.YOKE_BEAM_Y[0] - t, P.YOKE_BEAM_Y[1]
    yr1, yf1 = P.YOKE_BEAM_Y[0], P.YOKE_BEAM_Y[1] + t
    zbox = lambda x0, x1, y0, y1, z0, z1: L.box((x0 + x1) / 2, (y0 + y1) / 2, z0, x1 - x0, y1 - y0, z1 - z0)
    f = zbox(l0, r1, yf0, yf1, zb, zt)                 # front beam (on click switch)
    f += zbox(l0, r1, yr0, yr1, zb, zt)                # rear beam
    f += zbox(l0, l1, yr0, yf1, zb, zt)                # side rails
    f += zbox(r0, r1, yr0, yf1, zb, zt)
    arm_bot = L.PCB_TOP + 0.5                          # reaches the tilt stems
    for x0, x1 in ((l0, l1), (r0, r1)):
        f += zbox(x0, x1, y - 4, y + 4, arm_bot, z + 3.0)
    f -= L.cyl_x(l0 - 1, y, z, P.AXLE_D + 2 * P.FIT, r1 - l0 + 2)
    return f.solids()[0]


def magnet() -> bd.Solid:
    """Multipole ring magnet (bought-in) on the hub, right of the tyre."""
    od, idm, t = P.ENC_MAGNET
    return _ring_x(P.ENC_MAGNET_X, P.ENC_MAGNET_X + t, idm / 2 + 1.2, od / 2,
                   P.WHEEL_Y, L.wheel_axis_z())


@lru_cache(maxsize=1)
def build_wheel() -> dict[str, bd.Solid]:
    parts = {"wheel": wheel(), "enc_magnet": magnet(), "axle": axle(), "yoke": yoke()}
    parts.update(weights())
    return parts
