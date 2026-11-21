"""Build cache: parts are stored as BREP files under out/cache/<key>/, keyed
on a hash of the geometry sources plus the VARIANT, so any edit
rebuilds and an unchanged model loads in a second instead of minutes."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import build123d as bd

import params as P

HERE = Path(__file__).parent


GEOMETRY_SOURCES = ("params.py", "form.py", "layout.py", "top.py", "base.py", "wheel.py")


def key() -> str:
    """Hash of the geometry-defining sources + variant (tests, reports and
    model metadata like colours do not invalidate the cache)."""
    h = hashlib.sha256(P.VARIANT.encode())
    for name in GEOMETRY_SOURCES:
        h.update(name.encode())
        h.update((HERE / name).read_bytes())
    return h.hexdigest()[:16]


def cached(build_fn):
    d = HERE / "out" / "cache" / f"{P.VARIANT}-{key()}"
    index = d / "index.json"
    if index.exists():
        names = json.loads(index.read_text())
        return {n: bd.import_brep(d / f"{i:02d}.brep") for i, n in enumerate(names)}
    parts = build_fn()
    d.mkdir(parents=True, exist_ok=True)
    for i, (n, s) in enumerate(parts.items()):
        bd.export_brep(s, d / f"{i:02d}.brep")
    index.write_text(json.dumps(list(parts)))
    return parts
