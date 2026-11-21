"""Bambu Studio integration: locate the install, resolve system profiles.

Bambu Studio's CLI does not follow a profile's "inherits" chain for filament
presets (density, vendor, ... silently come out as 0/undefined), so every
preset is flattened here into one self-contained JSON before slicing.

    python -m tools.bambu list [printer|process|filament] [--grep X1C]
    python -m tools.bambu show "Bambu PLA Basic @BBL X1C"
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

CANDIDATES = [
    os.environ.get("BAMBU_STUDIO", ""),
    str(Path.home() / ".local/opt/bambustudio/current/squashfs-root/AppRun"),
    shutil.which("bambu-studio") or "",
]

# short printer names -> (machine preset, process preset suffix)
PRINTERS = {
    "X1C": ("Bambu Lab X1 Carbon 0.4 nozzle", "@BBL X1C"),
    "H2D": ("Bambu Lab H2D 0.4 nozzle", "@BBL H2D"),
}


def exe() -> str:
    for c in CANDIDATES:
        if c and Path(c).exists():
            return c
    raise FileNotFoundError("Bambu Studio not found (set $BAMBU_STUDIO or install "
                            "to ~/.local/opt/bambustudio/current)")


def profiles_dir() -> Path:
    root = Path(exe()).resolve().parent
    for p in (root / "resources/profiles/BBL",
              root.parent / "resources/profiles/BBL"):
        if p.is_dir():
            return p
    raise FileNotFoundError("Bambu profiles directory not found")


@lru_cache(maxsize=1)
def index() -> dict[str, Path]:
    idx = {}
    for f in glob.glob(str(profiles_dir() / "**/*.json"), recursive=True):
        try:
            d = json.load(open(f))
        except Exception:
            continue
        if isinstance(d, dict) and "name" in d:
            idx[d["name"]] = Path(f)
    return idx


def kind_of(name: str) -> str:
    rel = index()[name].relative_to(profiles_dir()).parts[0]
    return {"machine": "printer"}.get(rel, rel)


def resolve(name: str) -> dict:
    """Merge a preset with all its ancestors (child keys win)."""
    chain = []
    n = name
    while n:
        if n not in index():
            raise KeyError(f"Bambu preset not found: {n!r}")
        d = json.load(open(index()[n]))
        chain.append(d)
        n = d.get("inherits")
    out = {}
    for d in reversed(chain):
        out.update(d)
    out.pop("inherits", None)
    out["name"] = name
    return out


def write_resolved(names: list[str], outdir: Path) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = []
    for n in names:
        p = outdir / (n.replace("/", "_") + ".json")
        p.write_text(json.dumps(resolve(n), indent=1))
        paths.append(p)
    return paths


def presets(printer="X1C", process="0.20mm Standard", filament="Bambu PLA Basic"):
    """Expand short names to full preset names for a printer."""
    machine, suffix = PRINTERS.get(printer, (printer, ""))
    proc = process if "@" in process else f"{process} {suffix}"
    fil = filament if "@" in filament else f"{filament} {suffix}"
    for n in (machine, proc, fil):
        if n not in index():
            close = [k for k in index() if n.split(" @")[0] in k][:8]
            raise KeyError(f"preset {n!r} not found; similar: {close}")
    return machine, proc, fil


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list")
    l.add_argument("kind", nargs="?", choices=["printer", "process", "filament"])
    l.add_argument("--grep", default="")
    s = sub.add_parser("show")
    s.add_argument("name")
    a = ap.parse_args(argv)
    if a.cmd == "list":
        for n in sorted(index()):
            d = json.load(open(index()[n]))
            if d.get("instantiation") != "true":
                continue
            if a.kind and kind_of(n) != a.kind:
                continue
            if a.grep.lower() in n.lower():
                print(f"{kind_of(n):9s} {n}")
    else:
        print(json.dumps(resolve(a.name), indent=1))


if __name__ == "__main__":
    sys.exit(main())
