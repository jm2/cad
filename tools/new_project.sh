#!/usr/bin/env bash
# Scaffold ~/cad/projects/<name>/ with params.py, model.py, test_model.py and a
# Makefile (build / render / check / export / slice / roundtrip / view).
#   tools/new_project.sh <name>
set -euo pipefail
CAD="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
name="${1:?usage: new_project.sh <name>}"
[[ "$name" =~ ^[A-Za-z0-9_-]+$ ]] || { echo "name must be [A-Za-z0-9_-]+" >&2; exit 2; }
dir="$CAD/projects/$name"
[[ -e "$dir" ]] && { echo "$dir already exists" >&2; exit 1; }
mkdir -p "$dir"

cat > "$dir/params.py" <<'EOF'
"""All dimensions for this project, in millimetres. model.py and the tests
read from here; never hard-code a dimension anywhere else."""

# plate
LENGTH = 80.0          # X
WIDTH = 40.0           # Y
THICKNESS = 6.0        # Z
CORNER_R = 6.0         # vertical-edge fillet radius

# mounting holes (M6 clearance, ISO 273 medium)
HOLE_D = 6.6
HOLE_SPACING = 60.0    # centre-to-centre along X, centred on the plate

# fabrication
MIN_WALL = 1.2         # mm, smallest wall allowed (≈3 perimeters @ 0.4 nozzle)
DENSITY = 1.24         # g/cm^3 (PLA)
EOF

cat > "$dir/model.py" <<'EOF'
"""Parametric model. build() must return a build123d Part (or a dict
{name: Part} for multi-part projects). Dimensions come from params.py."""

from build123d import (Align, Axis, Box, BuildPart, Cylinder, Locations, Mode,
                       fillet)

import params as P

NAME = "__NAME__"


def build():
    with BuildPart() as part:
        Box(P.LENGTH, P.WIDTH, P.THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        fillet(part.edges().filter_by(Axis.Z), radius=P.CORNER_R)
        with Locations((-P.HOLE_SPACING / 2, 0), (P.HOLE_SPACING / 2, 0)):
            Cylinder(P.HOLE_D / 2, P.THICKNESS, mode=Mode.SUBTRACT,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
    p = part.part
    p.label = NAME
    return p


if __name__ == "__main__":
    # `python model.py` pushes the part to the OCP CAD Viewer in VS Code
    # (start the viewer first; see ~/cad/CLAUDE.md).
    from ocp_vscode import show

    show(build(), names=[NAME])
EOF
sed -i "s/__NAME__/$name/" "$dir/model.py"

cat > "$dir/test_model.py" <<'EOF'
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
EOF

cat > "$dir/Makefile" <<EOF
# Targets: build render check export slice roundtrip view all clean
# Vars:    SECTION=y=0  RENDER_ARGS=--annotate  PRINTER=X1C|H2D  FILAMENT="Bambu PLA Basic"
#          PROCESS="0.20mm Standard"  CHECK_ARGS=
NAME     := $name
EOF
cat >> "$dir/Makefile" <<'EOF'
CAD      ?= $(abspath ../..)
PY       := $(CAD)/.venv/bin/python
export PYTHONPATH := $(CAD)
export VTK_DEFAULT_OPENGL_WINDOW := vtkEGLRenderWindow
OUT      := out
STEP     := $(OUT)/$(NAME).step
SRC      := $(filter-out test_%.py,$(wildcard *.py))
PRINTER  ?= X1C
FILAMENT ?= Bambu PLA Basic
PROCESS  ?= 0.20mm Standard
SECTION  ?= y=0
RENDER_ARGS ?= --annotate
CHECK_ARGS  ?= --wall --min-wall $(shell $(PY) -c 'import params; print(getattr(params,"MIN_WALL",0.8))') --density $(shell $(PY) -c 'import params; print(getattr(params,"DENSITY",1.24))')

.PHONY: all build render check test export slice roundtrip view clean
all: build render check

build: $(STEP)
$(STEP): $(SRC)
	$(PY) -m tools.build model.py -o $(OUT) --name $(NAME)

render: $(STEP)
	$(PY) -m tools.render $(STEP) -o $(OUT)/renders --name $(NAME) \
	  $(if $(SECTION),--section $(SECTION)) $(RENDER_ARGS)

check: $(STEP) test
	$(PY) -m tools.check $(STEP) $(CHECK_ARGS)

test:
	$(PY) -m pytest -q -s test_model.py

export: $(STEP)
	$(PY) -m tools.export model.py -o $(OUT) --name $(NAME)

slice: export
	$(PY) -m tools.slice $(OUT)/$(NAME).stl -o $(OUT)/slice \
	  --printer "$(PRINTER)" --filament "$(FILAMENT)" --process "$(PROCESS)"

roundtrip: $(STEP)
	$(PY) -m tools.roundtrip $(STEP)

view:
	$(PY) model.py

clean:
	rm -rf $(OUT)
EOF

echo "created $dir"
ls "$dir"
