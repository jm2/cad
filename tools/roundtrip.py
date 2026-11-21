"""Compare a STEP file as seen by build123d (OCP) and by FreeCAD (freecadcmd).

    python -m tools.roundtrip out/part.step [--rtol 1e-6]

Confirms the STEP interchange is lossless: volume, area, bbox, solid count.
Exit non-zero on mismatch or if FreeCAD is unavailable.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

from tools.check import is_valid
from tools.model_io import load_part

HERE = Path(__file__).parent


def freecad_props(step: Path) -> dict:
    env = dict(os.environ, FC_STEP=str(step.resolve()))
    p = subprocess.run([str(HERE / "freecadcmd.sh"), str(HERE / "freecad_inspect.py")],
                       capture_output=True, text=True, env=env)
    for line in (p.stdout + p.stderr).splitlines():
        if line.startswith("FCJSON "):
            return json.loads(line[7:])
    raise RuntimeError(f"freecadcmd failed (exit {p.returncode}):\n{p.stdout}\n{p.stderr}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("step")
    ap.add_argument("--rtol", type=float, default=1e-6)
    ap.add_argument("--atol", type=float, default=1e-6, help="bbox abs tol, mm")
    a = ap.parse_args(argv)
    step = Path(a.step)
    s = load_part(step)
    bb = s.bounding_box(optimal=True)
    mine = {"valid": is_valid(s), "solids": len(s.solids()), "faces": len(s.faces()),
            "volume": s.volume, "area": s.area,
            "bbox_min": list(bb.min), "bbox_max": list(bb.max)}
    fc = freecad_props(step)
    print(f"FreeCAD {fc['freecad']} (OCCT {fc['occt']})  vs  build123d/OCP")
    bad = []
    for k in ("valid", "solids", "faces", "volume", "area", "bbox_min", "bbox_max"):
        x, y = mine[k], fc[k]
        if isinstance(x, list):
            ok = all(abs(i - j) <= a.atol + a.rtol * abs(j) for i, j in zip(x, y))
            fx = lambda v: "(" + ", ".join(f"{t:.6f}" for t in v) + ")"
            print(f"  {k:9s} b123d {fx(x):40s} freecad {fx(y):40s} {'ok' if ok else 'MISMATCH'}")
        elif isinstance(x, float):
            ok = abs(x - y) <= a.rtol * max(abs(y), 1)
            print(f"  {k:9s} b123d {x:<40.6f} freecad {y:<40.6f} {'ok' if ok else 'MISMATCH'}")
        else:
            ok = x == y
            print(f"  {k:9s} b123d {str(x):40s} freecad {str(y):40s} {'ok' if ok else 'MISMATCH'}")
        if not ok:
            bad.append(k)
    print("ROUNDTRIP " + ("PASS" if not bad else "FAIL: " + ", ".join(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
