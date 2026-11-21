"""Dimension asserts. Run with `make check` (or `make test`).
Every expectation is collected and reported together; any failure fails."""

import math
from pathlib import Path

import pytest

import params as P
from tools.check import Dims, cylinders, report
from tools.model_io import load_module

model = load_module(Path(__file__).with_name("model.py"))


@pytest.fixture(scope="module")
def part():
    return model.build()


def test_valid_and_watertight(part):
    r = report(part, density=P.DENSITY, min_wall=P.MIN_WALL)
    assert r.ok(), r.text()


def test_dimensions(part):
    d = Dims(part)
    d.expect("length X", d.size.X, P.LENGTH)
    d.expect("width Y", d.size.Y, P.WIDTH)
    d.expect("thickness Z", d.size.Z, P.THICKNESS)
    d.expect("bottom on Z=0", d.bbox.min.Z, 0.0)

    holes = [c for c in cylinders(part) if abs(c["diameter"] - P.HOLE_D) < 0.01]
    d.expect("hole count", len(holes), 2, tol=0)
    xs = sorted(c["axis_pos"][0] for c in holes)
    if len(xs) == 2:
        d.expect("hole spacing", xs[1] - xs[0], P.HOLE_SPACING)
        d.expect("holes centred", xs[0] + xs[1], 0.0)

    # analytic volume: rectangle minus fillet corners minus holes, times thickness
    r = P.CORNER_R
    area = (P.LENGTH * P.WIDTH - 4 * (r * r - math.pi * r * r / 4)
            - 2 * math.pi * (P.HOLE_D / 2) ** 2)
    d.expect("volume", d.volume, area * P.THICKNESS, tol=1e-3)
    print(d.summary())
    d.verify()
