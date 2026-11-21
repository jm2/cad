"""Slice meshes and report time / filament / warnings.

Default slicer is Bambu Studio with Bambu's own system presets (target
printer: Bambu Lab X1 Carbon, 0.4 nozzle):

    python -m tools.slice MODEL.stl [MORE.stl ...] [--printer X1C|H2D]
        [--process "0.20mm Standard"] [--filament "Bambu PLA Basic"]
        [-o out/slice] [--set key=value ...] [-v]

Several models are arranged together on one plate (e.g. every part of an
FDM variant). Models are sliced in the orientation they were exported in
(auto-orient is off), so export them print-oriented first.
List presets with `python -m tools.bambu list filament --grep X1C`.

PrusaSlicer remains available:  --slicer prusa [--profile file.ini ...]
Exit status non-zero if slicing fails.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROFILES = Path(__file__).parent / "profiles"
DEFAULT_PRUSA_PROFILE = PROFILES / "generic_pla_0.4.ini"

_NOISE = re.compile(r"glfw|Failed to connect to display|no filament colors|"
                    r"tree support default to organic", re.I)


# ----------------------------------------------------------------- bambu
def slice_bambu(models, out=None, printer="X1C", process="0.20mm Standard",
                filament="Bambu PLA Basic", overrides=()):
    from tools import bambu

    models = [Path(m).resolve() for m in models]
    outdir = Path(out or models[0].parent / "slice").resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    machine, proc, fil = bambu.presets(printer, process, filament)
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        m_p, p_p, f_p = bambu.write_resolved([machine, proc, fil], td)
        if overrides:
            d = json.loads(p_p.read_text())
            for kv in overrides:
                k, v = kv.split("=", 1)
                d[k] = v
            p_p.write_text(json.dumps(d, indent=1))
        name = models[0].stem if len(models) == 1 else "plate"
        cmd = [bambu.exe(), "--slice", "0", "--arrange", "1", "--orient", "0",
               "--debug", "2", "--load-settings", f"{m_p};{p_p}",
               "--load-filaments", str(f_p), "--outputdir", str(outdir),
               "--export-3mf", f"{name}_sliced.3mf", *map(str, models)]
        env = {k: v for k, v in __import__("os").environ.items()
               if k not in ("DISPLAY", "WAYLAND_DISPLAY")}
        proc_r = subprocess.run(cmd, capture_output=True, text=True, env=env,
                                timeout=1800)
    log = (proc_r.stdout + "\n" + proc_r.stderr).strip()
    res_p = outdir / "result.json"
    res = json.loads(res_p.read_text()) if res_p.exists() else {}
    gcode = outdir / "plate_1.gcode"
    ok = proc_r.returncode == 0 and res.get("return_code", 1) == 0 and gcode.exists()
    stats = {}
    if gcode.exists():
        final = outdir / f"{name}.gcode"
        gcode.replace(final)
        gcode = final
        head = gcode.read_text(errors="replace")
        rx = {
            "time": r"total estimated time:\s*([^;\n]+)",
            "filament_mm": r"total filament length \[mm\]\s*:\s*([\d.]+)",
            "filament_g": r"total filament weight \[g\]\s*:\s*([\d.]+)",
            "layers": r"total layer number:\s*(\d+)",
            "filament_type": r"^; filament_type = (.+)",
            "layer_height": r"^; layer_height = ([\d.]+)",
            "nozzle": r"^; nozzle_diameter = ([\d.,]+)",
            "infill": r"^; sparse_infill_density = (.+)",
            "walls": r"^; wall_loops = (\d+)",
            "printer": r"^; printer_model = (.+)",
            "supports": r"^; enable_support = (\d)",
            "diameter": r"^; filament_diameter = ([\d.]+)",
        }
        for k, r in rx.items():
            mm = re.search(r, head, re.M)
            if mm:
                stats[k] = mm.group(1).strip()
        if "filament_mm" in stats and "diameter" in stats:
            dmm = float(stats["diameter"].split(",")[0])
            stats["filament_cm3"] = (f"{float(stats['filament_mm']) * math.pi * dmm ** 2 / 4 / 1000:.2f}")
    warnings = [l.strip() for l in log.splitlines()
                if re.search(r"\[(warning|error)\]", l) and not _NOISE.search(l)
                and "cli mode" not in l]
    if res.get("error_string") not in (None, "Success."):
        warnings.append(f"result: {res.get('error_string')}")
    return {"ok": ok, "returncode": proc_r.returncode, "gcode": str(gcode),
            "slicer": "Bambu Studio", "presets": [machine, proc, fil],
            "cmd": " ".join(f'"{c}"' if " " in c else c for c in cmd),
            "warnings": warnings, "stats": stats, "log": log}


# ----------------------------------------------------------------- prusa
def _bed_center(profiles) -> str | None:
    for p in reversed(profiles):
        m = re.search(r"^bed_shape\s*=\s*(.+)$", Path(p).read_text(), re.M)
        if m:
            pts = [tuple(map(float, xy.split("x"))) for xy in m.group(1).split(",")]
            xs, ys = zip(*pts)
            return f"{(min(xs) + max(xs)) / 2:g},{(min(ys) + max(ys)) / 2:g}"
    return None


def slice_prusa(models, profiles=None, out=None, overrides=(), exe="prusa-slicer"):
    model = Path(models[0])
    profiles = [Path(p) for p in (profiles or [DEFAULT_PRUSA_PROFILE])]
    outdir = Path(out or model.parent / "slice")
    outdir.mkdir(parents=True, exist_ok=True)
    gcode = outdir / f"{model.stem if len(models) == 1 else 'plate'}.gcode"
    if not shutil.which(exe):
        raise FileNotFoundError(f"{exe} not on PATH")
    cmd = [exe, "--export-gcode", "--loglevel", "2"]
    for p in profiles:
        cmd += ["--load", str(p)]
    if len(models) > 1:
        cmd += ["--merge"]
    elif (c := _bed_center(profiles)):
        cmd += ["--center", c]
    for kv in overrides:
        k, v = kv.split("=", 1)
        cmd += [f"--{k.replace('_', '-')}", v]
    cmd += ["-o", str(gcode), *map(str, models)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    log = (proc.stdout + "\n" + proc.stderr).strip()
    ok = proc.returncode == 0 and gcode.exists() and gcode.stat().st_size > 0
    warnings = [l.strip() for l in log.splitlines()
                if re.search(r"warn|error|empty|not printable|outside|collision|"
                             r"exceed|fail", l, re.I)]
    stats = {}
    if ok:
        text = gcode.read_text(errors="replace")
        rx = {"time": r"estimated printing time \(normal mode\)\s*=\s*(.+)",
              "filament_mm": r"filament used \[mm\]\s*=\s*([\d.]+)",
              "filament_cm3": r"filament used \[cm3\]\s*=\s*([\d.]+)",
              "filament_g": r"(?:total )?filament used \[g\]\s*=\s*([\d.]+)",
              "layer_height": r"^; layer_height = ([\d.]+)",
              "nozzle": r"^; nozzle_diameter = ([\d.,]+)",
              "filament_type": r"^; filament_type = (.+)",
              "infill": r"^; fill_density = (.+)",
              "walls": r"^; perimeters = (\d+)"}
        for k, r in rx.items():
            m = re.search(r, text, re.M)
            if m:
                stats[k] = m.group(1).strip()
        stats["layers"] = len(re.findall(r"^;LAYER_CHANGE", text, re.M))
        stats["printer"] = "generic (PrusaSlicer profile)"
    return {"ok": ok, "returncode": proc.returncode, "gcode": str(gcode),
            "slicer": "PrusaSlicer", "presets": [str(p) for p in profiles],
            "cmd": " ".join(cmd), "warnings": warnings, "stats": stats, "log": log}


# ------------------------------------------------------------------- CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("models", nargs="+")
    ap.add_argument("--slicer", choices=["bambu", "prusa"], default="bambu")
    ap.add_argument("--printer", default="X1C", help="X1C | H2D | full preset name")
    ap.add_argument("--process", default="0.20mm Standard")
    ap.add_argument("--filament", default="Bambu PLA Basic")
    ap.add_argument("--profile", action="append", help="PrusaSlicer .ini (prusa only)")
    ap.add_argument("-o", "--out", help="output directory")
    ap.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="override a process setting, e.g. --set wall_loops=4")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)
    if a.slicer == "bambu":
        r = slice_bambu(a.models, a.out, a.printer, a.process, a.filament, a.set)
    else:
        r = slice_prusa(a.models, a.profile, a.out, a.set)
    s = r["stats"]
    print(f"slice          : {'OK' if r['ok'] else 'FAILED'} (exit {r['returncode']}) "
          f"via {r['slicer']}")
    print(f"presets        : {' | '.join(r['presets'])}")
    if a.verbose or not r["ok"]:
        print(f"command        : {r['cmd']}")
    if r["ok"]:
        print(f"printer        : {s.get('printer', '?')}")
        print(f"gcode          : {r['gcode']}")
        print(f"print time     : {s.get('time', '?')}")
        print(f"filament       : {s.get('filament_mm', '?')} mm, "
              f"{s.get('filament_cm3', '?')} cm3, {s.get('filament_g', '?')} g")
        print(f"settings       : {s.get('filament_type', '?')}, nozzle "
              f"{s.get('nozzle', '?')}, layer {s.get('layer_height', '?')}, "
              f"{s.get('walls', '?')} walls, infill {s.get('infill', '?')}, "
              f"{s.get('layers', '?')} layers"
              + (f", supports {'on' if s.get('supports') == '1' else 'off'}"
                 if 'supports' in s else ""))
    print(f"warnings       : {len(r['warnings'])}")
    for w in r["warnings"]:
        print(f"  ! {w}")
    if a.verbose or not r["ok"]:
        print("---- slicer log ----\n" + r["log"])
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
