"""Slice a mesh with the PrusaSlicer CLI and report time / filament / warnings.

    python -m tools.slice MODEL.stl|.3mf [--profile tools/profiles/X.ini ...]
                          [-o out/model.gcode] [--set key=value ...]

Profiles: pass one or more --profile .ini files (later ones override earlier).
Default is tools/profiles/generic_pla_0.4.ini, a GENERIC placeholder - export
your real printer/filament/print config from the PrusaSlicer GUI
(File > Export > Export Config) into tools/profiles/ and use that.
Exit status non-zero if slicing fails.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

PROFILES = Path(__file__).parent / "profiles"
DEFAULT_PROFILE = PROFILES / "generic_pla_0.4.ini"

_STATS = {
    "time_normal": r"estimated printing time \(normal mode\)\s*=\s*(.+)",
    "time_silent": r"estimated printing time \(silent mode\)\s*=\s*(.+)",
    "filament_mm": r"filament used \[mm\]\s*=\s*([\d.]+)",
    "filament_cm3": r"filament used \[cm3\]\s*=\s*([\d.]+)",
    "filament_g": r"(?:total )?filament used \[g\]\s*=\s*([\d.]+)",
    "filament_cost": r"(?:total )?filament cost\s*=\s*([\d.]+)",
    "layer_height": r"^; layer_height = ([\d.]+)",
    "nozzle": r"^; nozzle_diameter = ([\d.,]+)",
    "filament_type": r"^; filament_type = (.+)",
    "fill_density": r"^; fill_density = (.+)",
}


def _bed_center(profiles) -> str | None:
    for p in reversed(profiles):
        m = re.search(r"^bed_shape\s*=\s*(.+)$", Path(p).read_text(), re.M)
        if m:
            pts = [tuple(map(float, xy.split("x"))) for xy in m.group(1).split(",")]
            xs, ys = zip(*pts)
            return f"{(min(xs) + max(xs)) / 2:g},{(min(ys) + max(ys)) / 2:g}"
    return None


def slice_model(model, profiles=None, out=None, overrides=(), exe="prusa-slicer"):
    model = Path(model)
    profiles = [Path(p) for p in (profiles or [DEFAULT_PROFILE])]
    out = Path(out) if out else model.with_suffix(".gcode")
    out.parent.mkdir(parents=True, exist_ok=True)
    if not shutil.which(exe):
        raise FileNotFoundError(f"{exe} not on PATH")
    cmd = [exe, "--export-gcode", "--loglevel", "2"]
    for p in profiles:
        cmd += ["--load", str(p)]
    c = _bed_center(profiles)
    if c:
        cmd += ["--center", c]
    for kv in overrides:
        k, v = kv.split("=", 1)
        cmd += [f"--{k.replace('_', '-')}", v]
    cmd += ["-o", str(out), str(model)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log = (proc.stdout + "\n" + proc.stderr).strip()
    ok = proc.returncode == 0 and out.exists() and out.stat().st_size > 0
    warnings = [l.strip() for l in log.splitlines()
                if re.search(r"warn|error|empty|not printable|outside|collision|"
                             r"exceed|fail", l, re.I)]
    stats = {}
    if ok:
        text = out.read_text(errors="replace")
        # stats live in the trailing comment block; config block also at end
        for k, rx in _STATS.items():
            m = re.search(rx, text, re.M)
            if m:
                stats[k] = m.group(1).strip()
        stats["layers"] = len(re.findall(r"^;LAYER_CHANGE", text, re.M))
    return {"ok": ok, "returncode": proc.returncode, "gcode": str(out),
            "cmd": " ".join(cmd), "warnings": warnings, "stats": stats, "log": log}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model")
    ap.add_argument("--profile", action="append",
                    help="PrusaSlicer .ini (repeatable; later overrides earlier)")
    ap.add_argument("-o", "--out")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a setting, e.g. --set fill_density=40%%")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    r = slice_model(a.model, a.profile, a.out, a.set)
    print(f"slice          : {'OK' if r['ok'] else 'FAILED'} (exit {r['returncode']})")
    print(f"profiles       : {', '.join(a.profile or [str(DEFAULT_PROFILE)])}")
    if a.verbose or not r["ok"]:
        print(f"command        : {r['cmd']}")
    s = r["stats"]
    if r["ok"]:
        print(f"gcode          : {r['gcode']}")
        print(f"print time     : {s.get('time_normal', '?')}")
        print(f"filament       : {s.get('filament_mm', '?')} mm, "
              f"{s.get('filament_cm3', '?')} cm3, {s.get('filament_g', '?')} g"
              f"  (cost {s.get('filament_cost', '?')})")
        print(f"settings       : {s.get('filament_type', '?')}, nozzle "
              f"{s.get('nozzle', '?')}, layer {s.get('layer_height', '?')}, "
              f"infill {s.get('fill_density', '?')}, {s.get('layers', '?')} layers")
    print(f"warnings       : {len(r['warnings'])}")
    for w in r["warnings"]:
        print(f"  ! {w}")
    if a.verbose or not r["ok"]:
        print("---- slicer log ----\n" + r["log"])
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
