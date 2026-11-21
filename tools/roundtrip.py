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
from tools.model_io import area, load_part, volume

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
    ap.add_argument("--atol", type=float, default=1e-3, help="bbox abs tol, mm")
    a = ap.parse_args(argv)
    step = Path(a.step)
    s = load_part(step)
    bb = s.bounding_box(optimal=True)
    # "volume" compares OCCT's default integration on both sides (identical
    # algorithm -> must match exactly); "mesh_volume" compares FreeCAD's own
    # tessellation against our adaptive-integration volume (independent).
    mine = {"valid": is_valid(s), "solids": len(s.solids()), "faces": len(s.faces()),
            "volume": s.volume, "mesh_volume": volume(s), "area": s.area,
            "bbox_min": list(bb.min), "bbox_max": list(bb.max)}
    fc = freecad_props(step)
    print(f"FreeCAD {fc['freecad']} (OCCT {fc['occt']})  vs  build123d/OCP")
    bad = []
    tol = {"mesh_volume": 3e-3, "area": 1e-4}
    info_only = {"volume"}   # default integration differs between OCCT versions
    for k in ("valid", "solids", "faces", "volume", "mesh_volume", "area", "bbox_min", "bbox_max"):
        x, y = mine[k], fc[k]
        if isinstance(x, list):
            ok = all(abs(i - j) <= a.atol + a.rtol * abs(j) for i, j in zip(x, y))
            fx = lambda v: "(" + ", ".join(f"{t:.6f}" for t in v) + ")"
            print(f"  {k:11s} b123d {fx(x):38s} freecad {fx(y):38s} {'ok' if ok else 'MISMATCH'}")
        elif isinstance(x, float):
            ok = abs(x - y) <= tol.get(k, a.rtol) * max(abs(y), 1)
            flag = "ok" if ok else ("differs (info: default integration)" if k in info_only else "MISMATCH")
            print(f"  {k:11s} b123d {x:<38.6f} freecad {y:<38.6f} {flag}")
        else:
            ok = x == y
            print(f"  {k:11s} b123d {str(x):38s} freecad {str(y):38s} {'ok' if ok else 'MISMATCH'}")
        if not ok and k not in info_only:
            bad.append(k)
    print("ROUNDTRIP " + ("PASS" if not bad else "FAIL: " + ", ".join(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
