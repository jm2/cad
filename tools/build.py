"""Build a project's model.py and write the STEP of record to out/NAME.step.

    python -m tools.build model.py [-o out] [--name NAME]

Prints a one-line summary (validity, bbox, volume). Exits non-zero if build()
raises or the result is not a valid solid.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from tools.check import is_valid
from tools.export import export
from tools.model_io import load_parts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("model", nargs="?", default="model.py")
    ap.add_argument("-o", "--outdir", default="out")
    ap.add_argument("--name")
    a = ap.parse_args(argv)
    t0 = time.perf_counter()
    parts = load_parts(a.model)
    dt = time.perf_counter() - t0
    bad = 0
    for key, s in parts.items():
        bb = s.bounding_box()
        v = is_valid(s)
        bad += (not v) or not s.solids()
        print(f"built {key}: valid={v} solids={len(s.solids())} "
              f"size=({bb.size.X:.3f}, {bb.size.Y:.3f}, {bb.size.Z:.3f}) "
              f"volume={s.volume:.3f} mm^3  [{dt:.2f}s]")
    name = a.name or (next(iter(parts)) if len(parts) == 1 else Path(a.model).resolve().parent.name)
    for p in export(parts, a.outdir, name, formats=("step",)):
        print(f"wrote {p}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
