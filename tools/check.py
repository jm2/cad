"""Geometry checks: validity, watertightness, bbox, volume/mass, interference,
minimum wall thickness estimate, and loud dimension asserts.

CLI:
    python -m tools.check PART [--density 1.24] [--wall] [--min-wall 1.2]
                               [--interfere OTHER_PART] [--json]
Exit status is non-zero if any check FAILS.

Python (in tests):
    from tools.check import Dims, report, interference
    d = Dims(part)
    d.expect("width", d.size.X, 80, tol=0.01)
    d.expect_le("mass_g", report(part).mass_g, 50)
    d.verify()          # raises DimensionError listing EVERY failure
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field

from tools.model_io import area as _area, load_part, mass_props, to_trimesh, volume as _volume

import build123d as bd
import numpy as np

# g/cm^3
DENSITY = {"PLA": 1.24, "PETG": 1.27, "ABS": 1.04, "ASA": 1.07, "TPU": 1.21,
           "PA": 1.14, "PC": 1.20, "aluminium": 2.70, "steel": 7.85}


# --------------------------------------------------------------------- report
@dataclass
class Report:
    valid: bool
    n_solids: int
    watertight: bool
    winding_consistent: bool
    manifold_ok: bool
    euler: int
    bbox_min: tuple
    bbox_max: tuple
    size: tuple
    volume_mm3: float
    area_mm2: float
    center_of_mass: tuple
    density_g_cm3: float
    mass_g: float
    mesh_volume_mm3: float
    wall: dict | None = None
    failures: list = field(default_factory=list)

    def ok(self) -> bool:
        return not self.failures

    def text(self) -> str:
        f = lambda t: "(" + ", ".join(f"{x:.3f}" for x in t) + ")"
        L = [
            f"valid (BRepCheck)    : {self.valid}   solids: {self.n_solids}",
            f"watertight mesh      : {self.watertight}   winding ok: "
            f"{self.winding_consistent}   manifold3d ok: {self.manifold_ok}   "
            f"euler: {self.euler}",
            f"bbox min / max       : {f(self.bbox_min)} / {f(self.bbox_max)}",
            f"size X Y Z           : {f(self.size)} mm",
            f"volume               : {self.volume_mm3:.3f} mm^3 "
            f"(mesh {self.mesh_volume_mm3:.3f}, "
            f"{_pct(self.mesh_volume_mm3, self.volume_mm3):+.3f}%)",
            f"area                 : {self.area_mm2:.3f} mm^2",
            f"center of mass       : {f(self.center_of_mass)}",
            f"mass @ {self.density_g_cm3:g} g/cm^3   : {self.mass_g:.3f} g",
        ]
        if self.wall:
            w = self.wall
            L.append(f"wall thickness est.  : min {w['min']:.3f}  p1 {w['p01']:.3f}  "
                     f"p5 {w['p05']:.3f}  median {w['median']:.3f} mm  "
                     f"({w['samples']} rays; thinnest near {f(w['min_at'])})")
        L.append("RESULT               : " + ("PASS" if self.ok() else
                 "FAIL\n  - " + "\n  - ".join(self.failures)))
        return "\n".join(L)


def _pct(a, b):
    return 100.0 * (a - b) / b if b else 0.0


def is_valid(shape: bd.Shape) -> bool:
    from OCP.BRepCheck import BRepCheck_Analyzer

    return bool(shape.is_valid) and BRepCheck_Analyzer(shape.wrapped).IsValid()


def manifold_ok(mesh) -> bool:
    import manifold3d as m3

    try:
        man = m3.Manifold(m3.Mesh(vert_properties=np.asarray(mesh.vertices, np.float32),
                                  tri_verts=np.asarray(mesh.faces, np.uint32)))
        return man.status() == m3.Error.NoError and not man.is_empty()
    except Exception:
        return False


def report(src, density: float = DENSITY["PLA"], wall: bool = False,
           min_wall: float | None = None, wall_samples: int = 3000) -> Report:
    shape = load_part(src)
    bb = shape.bounding_box()
    mesh = to_trimesh(shape)
    vol, com = mass_props(shape)
    solids = shape.solids()
    r = Report(
        valid=is_valid(shape),
        n_solids=len(solids),
        watertight=bool(mesh.is_watertight),
        winding_consistent=bool(mesh.is_winding_consistent),
        manifold_ok=manifold_ok(mesh),
        euler=int(mesh.euler_number),
        bbox_min=tuple(bb.min), bbox_max=tuple(bb.max), size=tuple(bb.size),
        volume_mm3=vol, area_mm2=_area(shape), center_of_mass=tuple(com),
        density_g_cm3=density, mass_g=vol * density / 1000.0,
        mesh_volume_mm3=float(abs(mesh.volume)),
    )
    if not r.valid:
        r.failures.append("BRep is not valid")
    if r.n_solids == 0:
        r.failures.append("no solids in shape")
    if not r.watertight:
        r.failures.append("tessellated mesh is not watertight")
    if not r.manifold_ok:
        r.failures.append("manifold3d rejected the mesh")
    if vol <= 0:
        r.failures.append(f"non-positive volume {vol}")
    elif abs(_pct(r.mesh_volume_mm3, vol)) > 1.0:
        r.failures.append(f"mesh volume differs from BRep volume by "
                          f"{_pct(r.mesh_volume_mm3, vol):.2f}%")
    if wall or min_wall is not None:
        r.wall = wall_thickness(mesh, wall_samples)
        if min_wall is not None and r.wall["p01"] < min_wall:
            r.failures.append(f"wall thickness p1={r.wall['p01']:.3f} mm < "
                              f"min_wall {min_wall} mm (near {r.wall['min_at']})")
    return r


# ------------------------------------------------------------ wall thickness
def wall_thickness(mesh, samples: int = 3000, seed: int = 0) -> dict:
    """Ray-cast estimate of local wall thickness.

    Area-weighted random surface points shoot a ray along the inward normal;
    the distance to the first surface where the ray *exits* material (hit
    normal facing along the ray) is the local thickness. Reported as min and
    low percentiles: 'min' can be noisy at sharp edges, so assert on p01.
    """
    import pyvista as pv
    import trimesh
    import vtk

    pts, fidx = trimesh.sample.sample_surface(mesh, samples, seed=seed)
    normals = mesh.face_normals[fidx]
    poly = pv.wrap(mesh)
    tree = vtk.vtkOBBTree()
    tree.SetDataSet(poly)
    tree.BuildLocator()
    fn = mesh.face_normals
    span = float(np.linalg.norm(mesh.extents)) * 2
    eps = 1e-4 * span + 1e-6
    hits_p, hits_c = vtk.vtkPoints(), vtk.vtkIdList()
    th, at = [], []
    for p, n in zip(pts, normals):
        d = -n
        a = p + d * eps
        b = p + d * span
        hits_p.Reset(); hits_c.Reset()
        if tree.IntersectWithLine(a, b, hits_p, hits_c) == 0:
            continue
        for k in range(hits_p.GetNumberOfPoints()):
            if np.dot(fn[hits_c.GetId(k)], d) > 0.1:   # exiting surface
                q = np.array(hits_p.GetPoint(k))
                th.append(float(np.linalg.norm(q - p)))
                at.append(p)
                break
    if not th:
        return {"min": math.nan, "p01": math.nan, "p05": math.nan,
                "median": math.nan, "samples": 0, "min_at": (math.nan,) * 3}
    th = np.array(th)
    i = int(np.argmin(th))
    return {"min": float(th.min()), "p01": float(np.percentile(th, 1)),
            "p05": float(np.percentile(th, 5)), "median": float(np.median(th)),
            "samples": int(len(th)), "min_at": tuple(float(x) for x in at[i])}


# --------------------------------------------------------------- interference
def interference(a, b, tol_mm3: float = 1e-6) -> float:
    """Overlap volume (mm^3) between two parts; 0.0 means no interference."""
    sa, sb = load_part(a), load_part(b)
    common = sa & sb
    v = _volume(common) if common is not None and common.solids() else 0.0
    return v if v > tol_mm3 else 0.0


def min_distance(a, b) -> float:
    """Closest distance between two parts (0 if touching/overlapping)."""
    return load_part(a).distance_to(load_part(b))


# --------------------------------------------------------- feature measuring
def cylinders(src) -> list[dict]:
    """Cylindrical faces: radius, diameter, axis direction, axis location.
    Handy for asserting hole sizes and positions."""
    shape = load_part(src)
    out = []
    for f in shape.faces().filter_by(bd.GeomType.CYLINDER):
        ax = f.axis_of_rotation if hasattr(f, "axis_of_rotation") else None
        out.append({"radius": f.radius, "diameter": 2 * f.radius,
                    "axis_dir": tuple(ax.direction) if ax else None,
                    "axis_pos": tuple(ax.position) if ax else None,
                    "center": tuple(f.center(bd.CenterOf.MASS))})
    return out


# ------------------------------------------------------------ dimension asserts
class DimensionError(AssertionError):
    pass


class Dims:
    """Collects dimension expectations and fails loudly with all of them.

        d = Dims(part)                 # part: Shape / STEP path / model.py
        d.expect("width", d.size.X, 80)            # default tol 0.01 mm
        d.expect("hole", d.holes()[0], 5.5, tol=0.05)
        d.expect_between("mass", m, 10, 20)
        d.verify()
    """

    def __init__(self, src=None, default_tol: float = 0.01):
        self.shape = load_part(src) if src is not None else None
        self.tol = default_tol
        self.results: list[tuple[bool, str]] = []

    # convenient measurements
    @property
    def bbox(self):
        return self.shape.bounding_box()

    @property
    def size(self):
        return self.bbox.size

    @property
    def volume(self):
        return _volume(self.shape)

    def holes(self) -> list[float]:
        """Sorted diameters of all cylindrical faces (holes & bosses)."""
        return sorted(c["diameter"] for c in cylinders(self.shape))

    # expectations
    def _add(self, ok, msg):
        self.results.append((bool(ok), msg))
        return ok

    def expect(self, name, actual, nominal, tol=None):
        tol = self.tol if tol is None else tol
        ok = abs(actual - nominal) <= tol
        return self._add(ok, f"{name}: {actual:.4f} vs {nominal:.4f} ±{tol} "
                             f"(Δ {actual - nominal:+.4f})")

    def expect_between(self, name, actual, lo, hi):
        return self._add(lo <= actual <= hi, f"{name}: {actual:.4f} in [{lo}, {hi}]")

    def expect_le(self, name, actual, hi):
        return self._add(actual <= hi, f"{name}: {actual:.4f} <= {hi}")

    def expect_ge(self, name, actual, lo):
        return self._add(actual >= lo, f"{name}: {actual:.4f} >= {lo}")

    def expect_true(self, name, cond):
        return self._add(cond, f"{name}")

    def verify(self):
        bad = [m for ok, m in self.results if not ok]
        if bad:
            raise DimensionError(
                f"\n{'=' * 60}\n{len(bad)} of {len(self.results)} DIMENSION "
                f"CHECKS FAILED:\n  ✗ " + "\n  ✗ ".join(bad) + f"\n{'=' * 60}")
        return True

    def summary(self) -> str:
        return "\n".join(("  ✓ " if ok else "  ✗ ") + m for ok, m in self.results)


# ------------------------------------------------------------------------ CLI
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part")
    ap.add_argument("--density", default="PLA",
                    help=f"g/cm^3 or one of {','.join(DENSITY)}")
    ap.add_argument("--wall", action="store_true", help="estimate wall thickness")
    ap.add_argument("--min-wall", type=float, help="fail if p1 wall < this (mm)")
    ap.add_argument("--interfere", help="second part to test interference with")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    dens = DENSITY.get(a.density, None) or float(a.density)
    r = report(a.part, dens, a.wall, a.min_wall)
    if a.interfere:
        v = interference(a.part, a.interfere)
        dist = min_distance(a.part, a.interfere)
        r.failures += [f"interferes with {a.interfere}: {v:.4f} mm^3"] if v else []
        extra = f"interference         : {v:.4f} mm^3   min distance: {dist:.4f} mm"
    else:
        extra = None
    if a.json:
        print(json.dumps(asdict(r), indent=2, default=str))
    else:
        print(r.text())
        if extra:
            print(extra)
    return 0 if r.ok() else 1


if __name__ == "__main__":
    sys.exit(main())
