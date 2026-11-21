"""Loading parts from STEP files or project model.py files, and meshing them.

A "part source" is one of:
  * a build123d Shape object (when called from Python),
  * a path to a .step/.stp file,
  * a path to a .brep file,
  * a path to a model.py that defines ``build()`` returning a Shape
    (or a dict {name: Shape} for multi-part projects).
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

# Prefer EGL for every VTK window we create: headless, GPU-accelerated, and it
# skips the noisy "bad X server connection" attempt when DISPLAY is unset.
os.environ.setdefault("VTK_DEFAULT_OPENGL_WINDOW", "vtkEGLRenderWindow")

import build123d as bd
import numpy as np

PartLike = "bd.Shape | str | os.PathLike"

# Default tessellation tolerances (mm / rad). Fine enough for renders & checks.
LINEAR_TOL = 0.01
ANGULAR_TOL = 0.1


def load_module(path: str | os.PathLike):
    """Import a python file by path (its directory goes on sys.path so that
    `import params` works from model.py)."""
    path = Path(path).resolve()
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    name = f"_cadmodel_{path.parent.name}_{path.stem}"
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_parts(src) -> dict[str, bd.Shape]:
    """Return {name: Shape} for any part source."""
    if isinstance(src, bd.Shape):
        return {getattr(src, "label", "") or "part": src}
    if isinstance(src, dict):
        return dict(src)
    p = Path(src)
    if not p.exists():
        raise FileNotFoundError(p)
    suf = p.suffix.lower()
    if suf in (".step", ".stp"):
        return {p.stem: bd.import_step(p)}
    if suf == ".brep":
        return {p.stem: bd.import_brep(p)}
    if suf == ".py":
        mod = load_module(p)
        if not hasattr(mod, "build"):
            raise AttributeError(f"{p} has no build() function")
        out = mod.build()
        if isinstance(out, dict):
            return out
        name = getattr(mod, "NAME", None) or p.parent.name
        return {name: out}
    raise ValueError(f"don't know how to load {p}")


def load_part(src) -> bd.Shape:
    """Single shape from a source; multi-part sources become one Compound."""
    parts = load_parts(src)
    if len(parts) == 1:
        return next(iter(parts.values()))
    return bd.Compound(children=list(parts.values()))


def mesh_arrays(shape: bd.Shape, tol=LINEAR_TOL, ang=ANGULAR_TOL):
    """Tessellate into (vertices Nx3 float, faces Mx3 int)."""
    verts, tris = shape.tessellate(tol, ang)
    v = np.array([(p.X, p.Y, p.Z) for p in verts], dtype=float)
    f = np.array(tris, dtype=np.int64).reshape(-1, 3)
    return v, f


def to_trimesh(shape: bd.Shape, tol=LINEAR_TOL, ang=ANGULAR_TOL):
    import trimesh

    v, f = mesh_arrays(shape, tol, ang)
    # merge_tex/merge_norm: OCC emits duplicate vertices along face seams.
    m = trimesh.Trimesh(vertices=v, faces=f, process=True)
    m.merge_vertices(merge_tex=True, merge_norm=True)
    return m


def to_pyvista(shape: bd.Shape, tol=LINEAR_TOL, ang=ANGULAR_TOL):
    """Surface mesh as pyvista PolyData, with a per-cell 'face_id' array
    mapping triangles back to BRep faces (used for highlighting)."""
    import pyvista as pv

    all_v, all_f, ids = [], [], []
    off = 0
    for i, face in enumerate(shape.faces()):
        v, f = mesh_arrays(face, tol, ang)
        if len(f) == 0:
            continue
        all_v.append(v)
        all_f.append(f + off)
        ids.append(np.full(len(f), i))
        off += len(v)
    if not all_v:
        raise ValueError("shape produced an empty mesh")
    v = np.vstack(all_v)
    f = np.vstack(all_f)
    cells = np.hstack([np.full((len(f), 1), 3), f]).ravel()
    mesh = pv.PolyData(v, cells)
    mesh.cell_data["face_id"] = np.concatenate(ids)
    return mesh


def edge_lines(shape: bd.Shape, tol=0.05):
    """All BRep edges as a pyvista PolyData of polylines (for crisp outlines)."""
    import pyvista as pv

    pts, lines = [], []
    off = 0
    for e in shape.edges():
        if e.geom_type == bd.GeomType.LINE:
            n = 2
        else:
            n = int(np.clip(e.length / max(tol * 20, 0.2), 8, 256))
        p = np.array([tuple(e @ t) for t in np.linspace(0, 1, n)])
        pts.append(p)
        lines.append(np.concatenate([[n], np.arange(off, off + n)]))
        off += n
    if not pts:
        return None
    return pv.PolyData(np.vstack(pts), lines=np.concatenate(lines))


# ------------------------------------------------------------------ assemblies
PALETTE = ["#8fa8c8", "#e0a458", "#7fb685", "#c97c8a", "#9d8ec7", "#6fb7b7",
           "#d4c26a", "#b0b0b0", "#e07a5f", "#81b29a", "#f2cc8f", "#5e81ac"]


class Assembly:
    """Parts plus optional per-part metadata declared in model.py:

        COLORS          {name: "#rrggbb"}
        EXPLODE         {name: (dx, dy, dz)}   offset (mm) for exploded views
        ALLOWED_CONTACT [("a", "b"), ...]       pairs allowed to touch/overlap
                                                (press fits, screws in bosses)
        MIN_CLEARANCE   {("a", "b"): mm}        pairs that must keep a gap
        PRINT_ORIENT    {name: (rx, ry, rz)}    degrees, applied before FDM
                                                export/slice/overhang checks
        PULL            {name: (x, y, z)}       mould pull direction (molded)
    """

    def __init__(self, parts, module=None):
        self.parts: dict[str, bd.Shape] = dict(parts)
        self.module = module
        g = lambda k, d: dict(getattr(module, k, None) or d) if module else d
        self.colors = g("COLORS", {})
        for i, (k, s) in enumerate(self.parts.items()):
            if k not in self.colors:
                c = getattr(s, "color", None)
                self.colors[k] = (_hex(c) if c is not None
                                  else PALETTE[i % len(PALETTE)])
        self.explode = g("EXPLODE", {})
        self.allowed_contact = {frozenset(p) for p in
                                (getattr(module, "ALLOWED_CONTACT", None) or [])}
        self.min_clearance = {frozenset(k): v for k, v in
                              g("MIN_CLEARANCE", {}).items()}
        self.print_orient = g("PRINT_ORIENT", {})
        self.pull = g("PULL", {})

    def __len__(self):
        return len(self.parts)

    def compound(self):
        kids = []
        for k, s in self.parts.items():
            s.label = k
            s.color = bd.Color(self.colors[k])
            kids.append(s)
        return bd.Compound(children=kids)


def _hex(c) -> str:
    r, g, b, *_ = tuple(c)
    return "#%02x%02x%02x" % tuple(int(round(255 * x)) for x in (r, g, b))


def load_assembly(src) -> Assembly:
    """Like load_parts, but keeps model.py metadata, and splits a STEP whose
    top-level compound has labelled children into named parts."""
    if isinstance(src, Assembly):
        return src
    if isinstance(src, (str, os.PathLike)) and Path(src).suffix == ".py":
        mod = load_module(src)
        out = mod.build()
        if not isinstance(out, dict):
            out = {getattr(mod, "NAME", None) or Path(src).resolve().parent.name: out}
        return Assembly(out, mod)
    parts = load_parts(src)
    if len(parts) == 1:
        (k, s), = parts.items()
        kids = list(getattr(s, "children", []) or [])
        if len(kids) > 1 and all(getattr(c, "label", "") for c in kids):
            return Assembly({c.label: c for c in kids})
    return Assembly(parts)
