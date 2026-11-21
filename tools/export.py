"""Export a part to STEP, STL and 3MF.

    python -m tools.export PART [-o out] [--name NAME] [--formats step,stl,3mf]
                                [--tol 0.01] [--ang 0.1]

STEP is the exact BRep (mm) and is what FreeCAD reviews. STL/3MF are meshes for
slicing; --tol is the chordal deviation in mm (0.01 is plenty for FDM).
For a multi-part model (build() returns a dict), each part is written as
NAME-<key>.* and the STEP also gets a combined NAME.step assembly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.model_io import load_parts

import build123d as bd


def export_part(shape: bd.Shape, outdir: Path, name: str, formats, tol=0.01, ang=0.1):
    outdir.mkdir(parents=True, exist_ok=True)
    written = []
    if "step" in formats:
        p = outdir / f"{name}.step"
        shape.label = shape.label or name
        if not bd.export_step(shape, p):
            raise RuntimeError(f"STEP export failed: {p}")
        written.append(p)
    if "stl" in formats:
        p = outdir / f"{name}.stl"
        if not bd.export_stl(shape, p, tolerance=tol, angular_tolerance=ang):
            raise RuntimeError(f"STL export failed: {p}")
        written.append(p)
    if "3mf" in formats:
        p = outdir / f"{name}.3mf"
        m = bd.Mesher()
        m.add_shape(shape, linear_deflection=tol, angular_deflection=ang,
                    part_number=name)
        m.write(str(p))
        written.append(p)
    return written


def export(src, outdir="out", name=None, formats=("step", "stl", "3mf"),
           tol=0.01, ang=0.1) -> list[Path]:
    parts = load_parts(src)
    outdir = Path(outdir)
    if len(parts) == 1:
        (key, shape), = parts.items()
        return export_part(shape, outdir, name or key, formats, tol, ang)
    name = name or "assembly"
    written = []
    for key, shape in parts.items():
        shape.label = key
        written += export_part(shape, outdir, f"{name}-{key}", formats, tol, ang)
    if "step" in formats:
        asm = bd.Compound(children=list(parts.values()), label=name)
        p = outdir / f"{name}.step"
        bd.export_step(asm, p)
        written.append(p)
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part")
    ap.add_argument("-o", "--outdir", default="out")
    ap.add_argument("--name")
    ap.add_argument("--formats", default="step,stl,3mf")
    ap.add_argument("--tol", type=float, default=0.01)
    ap.add_argument("--ang", type=float, default=0.1)
    a = ap.parse_args(argv)
    for p in export(a.part, a.outdir, a.name, a.formats.split(","), a.tol, a.ang):
        print(f"{p}  ({p.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    sys.exit(main())
