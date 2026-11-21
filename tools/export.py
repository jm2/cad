"""Export a part to STEP, STL and 3MF.

    python -m tools.export PART [-o out] [--name NAME] [--formats step,stl,3mf]
                                [--tol 0.01] [--ang 0.1]

STEP is the exact BRep (mm) and is what FreeCAD reviews. STL/3MF are meshes for
slicing; --tol is the chordal deviation in mm (0.01 is plenty for FDM).
For a multi-part model (build() returns a dict), each part is written as
NAME-<key>.* and the STEP also gets a combined NAME.step assembly (part
names and colours preserved, so FreeCAD shows a labelled tree).
--print writes per-part STL/3MF rotated by PRINT_ORIENT and dropped onto z=0.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.model_io import load_assembly

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
    asm = load_assembly(src)
    parts = asm.parts
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
        comp = asm.compound()
        comp.label = name
        p = outdir / f"{name}.step"
        bd.export_step(comp, p)
        written.append(p)
    return written


def export_print(src, outdir="out/print", formats=("stl", "3mf"), tol=0.01,
                 ang=0.1, only=None) -> list[Path]:
    """FDM export: each part rotated by PRINT_ORIENT (model.py) and dropped
    onto z=0, one mesh per part, ready to arrange on a plate and slice."""
    from tools.mfg import orient

    asm = load_assembly(src)
    written = []
    for k, s in asm.parts.items():
        if only and k not in only:
            continue
        o = orient(s, tuple(asm.print_orient.get(k, (0, 0, 0))))
        written += export_part(o, Path(outdir), k, formats, tol, ang)
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
    ap.add_argument("--print", action="store_true",
                    help="per-part meshes in PRINT_ORIENT, on z=0 (FDM)")
    ap.add_argument("--only", default="", help="with --print: these parts only")
    a = ap.parse_args(argv)
    if a.print:
        fm = [f for f in a.formats.split(",") if f != "step"] or ["stl"]
        only = [x for x in a.only.split(",") if x] or None
        paths = export_print(a.part, a.outdir, fm, a.tol, a.ang, only)
    else:
        paths = export(a.part, a.outdir, a.name, a.formats.split(","), a.tol, a.ang)
    for p in paths:
        print(f"{p}  ({p.stat().st_size / 1024:.1f} KiB)")


if __name__ == "__main__":
    sys.exit(main())
