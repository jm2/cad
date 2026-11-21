"""Fulcrum dimension and function asserts (run: make test VARIANT=...).
Every expectation is collected and reported together."""
import math
from pathlib import Path

import pytest

import form
import layout as L
import mass
import params as P
from tools.check import Dims, report
from tools.model_io import load_module

model = load_module(Path(__file__).with_name("model.py"))


@pytest.fixture(scope="module")
def parts():
    return model.build()


def _below(shape, x, y):
    """Lowest point of `shape` on the vertical line through (x, y)."""
    return form.surface_z(shape, x, y, from_top=False)


def test_overall(parts):
    import build123d as bd
    outer = bd.Compound(children=[parts["top_shell"], parts["base"]])
    d = Dims(outer)
    import numpy as np
    # the black base's bell foot is the widest / longest part (at the lip)
    width = 2 * max(form.bell_x(y, P.Z_LIP) for y in np.linspace(-60, 60, 241))
    length = P.LENGTH + 2 * form.bell_offset(P.Y_TAIL, P.Z_LIP, skirt=form._skirt_end())
    d.expect("length (incl. bell foot)", d.size.Y, length, tol=0.6)
    d.expect("width (across the rests)", d.size.X, width, tol=0.6)
    d.expect("height (top above desk)", d.bbox.max.Z, max(P.FORM["h"]), tol=0.5)
    d.expect("base underside", parts["base"].bounding_box().min.Z, P.Z_BASE, tol=0.05)
    skates_min = min(parts[k].bounding_box().min.Z for k in parts if k.startswith("skate"))
    d.expect("skates touch the desk", skates_min, 0.0, tol=0.01)
    lowest_other = min(v.bounding_box().min.Z for k, v in parts.items() if not k.startswith("skate"))
    d.expect_ge("nothing else below the skates", lowest_other, 0.3)
    print(d.summary())
    d.verify()


def test_switch_pretravel(parts):
    d = Dims()
    host = "top_shell" if P.MOLDED else None
    for name, (x, y) in (("btn_left", P.SW_L_XY), ("btn_right", P.SW_R_XY)):
        shape = parts[host or name]
        d.expect(f"{name} post -> plunger", _below(shape, x, y) - L.plunger_top_main(),
                 P.SW_PRETRAVEL, tol=0.02)
    stem_top = L.TOPB_Z + P.PCB_T + P.SW_TACT_PLUNGER[1]
    for name, y in (("btn_mode", P.MODE_BTN_Y), ("btn_dpi_up", P.DPI_Y[0]), ("btn_dpi_down", P.DPI_Y[1])):
        d.expect(f"{name} post -> stem", _below(parts[name], 0, y) - stem_top, P.SW_PRETRAVEL, tol=0.02)
    stem_x = L.side_board_x() + P.SW_TACT_PLUNGER[1]
    for side, sign in (("l", -1), ("r", 1)):
        for i, y in enumerate(P.SIDE_BTN_Y):
            hits = [p[0] for p in form._hits(parts[f"btn_side_{side}{i + 1}"],
                                             (0, y, P.SIDE_BTN_Z), (sign, 0, 0))]
            d.expect(f"btn_side_{side}{i + 1} post -> stem", min(abs(h) for h in hits) - stem_x,
                     P.SW_PRETRAVEL, tol=0.02)
    print(d.summary())
    d.verify()


def test_wheel_and_sensor(parts):
    d = Dims()
    shell_top = form.surface_z(form.top_outer(), 0, P.WHEEL_Y)
    d.expect("wheel proud of shell", parts["wheel"].bounding_box().max.Z - shell_top,
             P.WHEEL_PROUD, tol=0.1)
    d.expect("lens to desk", parts["sensor"].bounding_box().min.Z, P.LENS_TO_DESK, tol=0.01)
    bay = P.BAT_Y[1] - P.BAT_Y[0]
    d.expect_ge("battery bay length", bay, P.AA_L + P.BAT_SPRING_COMP + P.BAT_PLATE_T)
    d.expect_ge("battery bay diameter", 2 * L.BAT_R_IN, P.AA_D + 0.5)
    print(d.summary())
    d.verify()


def test_mass_balance(parts):
    r = mass.estimate(parts)
    cx, cy, cz = r["cog"]
    d = Dims()
    d.expect_between("mass with NiMH AA (g) [FDM: solid-plastic upper bound]", r["mass_g"], 70, 140)
    d.expect("CoG on the centre line", cx, 0.0, tol=1.5)
    d.expect("CoG near the sensor (y)", cy, P.SENSOR_XY[1], tol=25.0)
    print(d.summary(), f"\n  mass {r['mass_g']:.1f} g, CoG ({cx:.1f}, {cy:.1f}, {cz:.1f})")
    d.verify()


def test_shell_walls(parts):
    """Bulk wall thickness (5th percentile) within 80% of nominal; the
    thinnest 1% may include the moulded flexure bands (FLEX_T), the battery
    contact slots and latch pockets (known local thin spots)."""
    d = Dims()
    for name in ("top_shell", "base"):
        r = report(parts[name], density=P.DENSITY["shell"], wall=True)
        d.expect_true(f"{name} valid + watertight", r.valid and r.watertight)
        # moulded base ribs are RIB_T thick by design (~65% of the wall)
        p5_min = 0.8 * P.WALL if (name != "base" or P.FDM) else min(0.8 * P.WALL, P.RIB_T)
        d.expect_ge(f"{name} wall p5", r.wall["p05"] + 1e-6, p5_min)
        d.expect_ge(f"{name} wall p1", r.wall["p01"], 0.4 * P.WALL)
        d.expect_ge(f"{name} wall median", r.wall["median"], 0.95 * min(P.WALL, P.FLOOR))
    print(d.summary())
    d.verify()
