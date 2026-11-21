"""Manufacturability analysis: mould draft/undercuts and FDM overhangs.

    python -m tools.mfg draft    PART [--pull 0,0,1] [--min-draft 1.0] [--part NAME]
    python -m tools.mfg overhang PART [--orient rx,ry,rz] [--angle 45] [--part NAME]
         common: [-o out/mfg] [--views iso,iso_below,bottom] [--max-bad-area MM2]

PART may be a model.py assembly: then every part is analysed (or --part NAME)
using PULL / PRINT_ORIENT from model.py for that part.

draft    (injection moulding, straight-pull two-plate tool)
  Each surface triangle gets a draft angle = asin(n . pull) in degrees:
  +ve faces release toward +pull (cavity), -ve toward -pull (core).
  |draft| < min-draft  -> "no draft"      (walls parallel to the pull)
  a face whose ray along its release direction hits the part again
                       -> "undercut"      (needs a slider/lifter or redesign)
  Faces exactly perpendicular to the pull (n . pull = +-1) are fine.

overhang (FDM, after rotating by --orient and dropping onto the bed)
  Downward-facing triangles steeper than --angle from vertical need support
  (angle measured from vertical; 45 is a safe default for PLA/PETG on an
  X1C). Faces on the bed (z = 0) are "bed contact".

Writes colour-coded PNGs (<name>_<part>_draft_<view>.png etc.) and prints
area totals. Exit non-zero if the problem area exceeds --max-bad-area.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from tools.model_io import edge_lines, load_assembly, to_pyvista

import build123d as bd
import numpy as np
import pyvista as pv
import vtk

# categorical maps (value -> colour)
DRAFT_CATS = {0: ("release +pull", "#5b8fd9"), 1: ("release -pull", "#5fb36b"),
              2: ("no draft", "#f2c14e"), 3: ("undercut", "#d9534f"),
              4: ("flat", "#c9d6e8")}
OVER_CATS = {0: ("ok", "#7fb685"), 1: ("needs support", "#d9534f"),
             2: ("bed contact", "#5b8fd9"), 3: ("near limit", "#f2c14e")}


def orient(shape: bd.Shape, rot=(0, 0, 0)) -> bd.Shape:
    """Rotate by (rx, ry, rz) degrees (X then Y then Z) and drop onto z=0,
    centred in XY."""
    s = shape
    for ax, ang in zip((bd.Axis.X, bd.Axis.Y, bd.Axis.Z), rot):
        if ang:
            s = s.rotate(ax, ang)
    bb = s.bounding_box()
    return s.translate((-bb.center().X, -bb.center().Y, -bb.min.Z))


def _mesh(shape, tol=0.02):
    m = to_pyvista(shape, tol=tol)
    m = m.compute_normals(cell_normals=True, point_normals=False,
                          consistent_normals=False, auto_orient_normals=False)
    m = m.compute_cell_sizes(length=False, volume=False)
    return m


def _tree(mesh):
    t = vtk.vtkOBBTree()
    t.SetDataSet(mesh)
    t.BuildLocator()
    return t


def _hits(tree, a, b) -> bool:
    pts = vtk.vtkPoints()
    return tree.IntersectWithLine(a, b, pts, None) != 0 and pts.GetNumberOfPoints() > 0


def draft_analysis(shape: bd.Shape, pull=(0, 0, 1), min_draft=1.0,
                   flat_tol_deg=0.5):
    pull = np.asarray(pull, float)
    pull /= np.linalg.norm(pull)
    m = _mesh(shape)
    n = m.cell_data["Normals"]
    dot = np.clip(n @ pull, -1, 1)
    ang = np.degrees(np.arcsin(dot))
    cat = np.where(ang > 0, 0, 1)
    cat = np.where(np.abs(ang) < min_draft, 2, cat)
    cat = np.where(np.abs(ang) > 90 - flat_tol_deg, 4, cat)
    # undercut: shoot from each released face along its release direction
    tree = _tree(m)
    centers = m.cell_centers().points
    span = float(np.linalg.norm(np.ptp(m.points, axis=0))) * 2
    eps = 1e-3
    for i in np.where(cat != 2)[0]:
        d = pull if dot[i] > 0 else -pull
        a = centers[i] + d * eps
        if _hits(tree, a, a + d * span):
            cat[i] = 3
    m.cell_data["draft_deg"] = ang
    m.cell_data["category"] = cat.astype(float)
    area = m.cell_data["Area"]
    totals = {DRAFT_CATS[k][0]: float(area[cat == k].sum()) for k in DRAFT_CATS}
    return m, totals


def overhang_analysis(shape: bd.Shape, rot=(0, 0, 0), angle=45.0, warn_band=5.0):
    s = orient(shape, rot)
    m = _mesh(s)
    n = m.cell_data["Normals"]
    centers = m.cell_centers().points
    zmin = m.bounds[4]
    # angle of the face from vertical, for downward-facing faces only
    down = -n[:, 2]
    # from_vertical: 0 for a vertical wall, 90 for a flat ceiling
    from_vertical = np.degrees(np.arcsin(np.clip(down, -1, 1)))
    cat = np.zeros(len(n), int)
    downward = down > 1e-6
    cat[downward & (from_vertical > angle - warn_band)] = 3
    cat[downward & (from_vertical > angle)] = 1
    on_bed = (np.abs(centers[:, 2] - zmin) < 1e-3) & (down > 0.999)
    cat[on_bed] = 2
    m.cell_data["overhang_from_vertical"] = np.where(downward, from_vertical, 0)
    m.cell_data["category"] = cat.astype(float)
    area = m.cell_data["Area"]
    totals = {OVER_CATS[k][0]: float(area[cat == k].sum()) for k in OVER_CATS}
    bb = s.bounding_box()
    totals["_height_mm"] = bb.size.Z
    totals["_footprint_xy"] = (bb.size.X, bb.size.Y)
    return s, m, totals


def _render_cats_simple(mesh, shape, cats, out_png, view, title, plane=None):
    """Categorical map with a text legend (scalar bars are poor at categories).
    plane: optional (origin, normal); the +normal side is clipped away so
    internal faces (e.g. undercuts inside a shell) become visible."""
    from tools.render import VIEWS, _finish, _setup_camera

    if plane is not None:
        o, n = plane
        mesh = mesh.clip(normal=tuple(n), origin=tuple(o), invert=True)
        from tools.render import section_shape
        shape, _ = section_shape(shape, bd.Plane(origin=tuple(o), z_dir=tuple(n)))

    pl = pv.Plotter(off_screen=True, window_size=(1200, 900))
    pl.set_background("white")
    rgb = np.array([[int(cats[int(c)][1][i:i + 2], 16) for i in (1, 3, 5)]
                    for c in mesh.cell_data["category"]], np.uint8)
    mesh = mesh.copy()
    mesh.cell_data["rgb"] = rgb
    pl.add_mesh(mesh, scalars="rgb", rgb=True, smooth_shading=False,
                ambient=0.55, diffuse=0.5, specular=0.0)
    e = edge_lines(shape) if shape is not None else None
    if e is not None:
        pl.add_mesh(e, color="#1a1a1a", line_width=1, opacity=0.6)
    present = sorted(set(int(c) for c in mesh.cell_data["category"]))
    pl.add_legend([[cats[k][0], cats[k][1]] for k in present], bcolor="white",
                  face="rectangle", size=(0.24, 0.04 * len(present)),
                  loc="upper right", border=True)
    d, up = VIEWS[view]
    b = np.array(mesh.bounds)
    _setup_camera(pl, b[0::2], b[1::2], d, up, (1200, 900), 1.15)
    return _finish(pl, Path(out_png), f"{title}  [{view}]")


def _vec(s):
    return tuple(float(x) for x in s.split(","))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["draft", "overhang"])
    ap.add_argument("part")
    ap.add_argument("--part", dest="only", help="only this part of an assembly")
    ap.add_argument("--pull", help="mould pull direction x,y,z (default 0,0,1)")
    ap.add_argument("--min-draft", type=float, default=1.0)
    ap.add_argument("--orient", help="print rotation rx,ry,rz degrees")
    ap.add_argument("--angle", type=float, default=45.0)
    ap.add_argument("--max-bad-area", type=float, default=None,
                    help="fail if undercut+no-draft (draft) or support area "
                         "(overhang) exceeds this, mm^2")
    ap.add_argument("-o", "--outdir", default="out/mfg")
    ap.add_argument("--views", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--section", help="also render maps clipped at plane "
                    "'y=0' or 'ox,oy,oz:nx,ny,nz' (shows internal faces)")
    a = ap.parse_args(argv)
    plane = None
    if a.section:
        from tools.render import parse_plane
        pp = parse_plane(a.section)
        plane = (tuple(pp.origin), tuple(pp.z_dir))
    asm = load_assembly(a.part)
    name = a.name or ("assembly" if len(asm) > 1 else next(iter(asm.parts)))
    out = Path(a.outdir)
    bad_total = 0.0
    for k, s in asm.parts.items():
        if a.only and k != a.only:
            continue
        if a.mode == "draft":
            pull = _vec(a.pull) if a.pull else tuple(asm.pull.get(k, (0, 0, 1)))
            m, t = draft_analysis(s, pull, a.min_draft)
            bad = t["undercut"] + t["no draft"]
            print(f"[draft] {k}: pull={pull} min_draft={a.min_draft}°")
            views = (a.views or "iso,iso_below,front").split(",")
            shp = s
            cats = DRAFT_CATS
        else:
            rot = _vec(a.orient) if a.orient else tuple(asm.print_orient.get(k, (0, 0, 0)))
            shp, m, t = overhang_analysis(s, rot, a.angle)
            bad = t["needs support"]
            fx, fy = t["_footprint_xy"]
            print(f"[overhang] {k}: orient={rot} angle={a.angle}° -> "
                  f"{fx:.1f} x {fy:.1f} x {t['_height_mm']:.1f} mm on bed")
            views = (a.views or "iso,iso_below,bottom").split(",")
            cats = OVER_CATS
        for label, area in t.items():
            if not label.startswith("_"):
                print(f"    {label:22s} {area:10.2f} mm^2")
        bad_total += bad
        for v in views:
            p = _render_cats_simple(m, shp, cats, out / f"{name}_{k}_{a.mode}_{v}.png",
                                    v, f"{k} {a.mode}")
            print(f"    {p}")
        if plane is not None:
            for v in views:
                p = _render_cats_simple(m, shp, cats,
                                        out / f"{name}_{k}_{a.mode}_section_{v}.png",
                                        v, f"{k} {a.mode} (section)", plane)
                print(f"    {p}")
    if a.max_bad_area is not None:
        ok = bad_total <= a.max_bad_area
        print(f"MFG {a.mode.upper()} {'PASS' if ok else 'FAIL'}: problem area "
              f"{bad_total:.2f} mm^2 (limit {a.max_bad_area})")
        return 0 if ok else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
