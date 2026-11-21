"""Headless PNG renders of a part: front / top / right / iso (+ optional section).

    python -m tools.render PART [-o OUTDIR] [--views front,top,right,iso]
                           [--section y=0 | --section 10,0,0:1,0,0]
                           [--annotate] [--size 1200x900]

PART is a .step/.brep file or a project model.py (see tools.model_io).
Writes <name>_<view>.png per view plus <name>_sheet.png (all views tiled),
and prints the paths. Uses VTK's EGL window: no X/Wayland display needed.

Conventions (right-handed, Z up, matches FreeCAD's standard views):
  front = looking along +Y (camera at -Y)     top  = looking down -Z
  right = looking along -X (camera at +X)     iso  = camera at (+1,-1,+1)
Section: the material on the +normal side of the plane is removed and the
camera looks back along -normal at the cut face (cut faces drawn in red).
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from tools.model_io import edge_lines, load_parts, to_pyvista  # sets EGL env

import build123d as bd
import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True

BODY = "#8fa8c8"
EDGE = "#1a1a1a"
CUT = "#d9534f"

# view -> (camera direction from focal point, view-up)
VIEWS = {
    "front": ((0, -1, 0), (0, 0, 1)),
    "top": ((0, 0, 1), (0, 1, 0)),
    "right": ((1, 0, 0), (0, 0, 1)),
    "iso": ((1, -1, 1), (0, 0, 1)),
    "back": ((0, 1, 0), (0, 0, 1)),
    "bottom": ((0, 0, -1), (0, -1, 0)),
    "left": ((-1, 0, 0), (0, 0, 1)),
}
DEFAULT_VIEWS = ["front", "top", "right", "iso"]


def parse_plane(spec: str) -> bd.Plane:
    """'x=5' | 'y=0' | 'z=-2.5' | 'ox,oy,oz:nx,ny,nz'."""
    s = spec.replace(" ", "").lower()
    if "=" in s and s[0] in "xyz":
        ax, val = s.split("=", 1)
        v = float(val)
        normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[ax]
        origin = tuple(v * c for c in normal)
        return bd.Plane(origin=origin, z_dir=normal)
    o, n = s.split(":")
    return bd.Plane(
        origin=tuple(map(float, o.split(","))), z_dir=tuple(map(float, n.split(",")))
    )


def section_shape(shape: bd.Shape, plane: bd.Plane):
    """Cut shape with plane; return (kept shape, list of cut-face indices)."""
    kept = shape.split(plane, keep=bd.Keep.BOTTOM)
    if isinstance(kept, (list, tuple)):
        kept = bd.Compound(children=list(kept))
    if kept is None or not kept.faces():
        raise ValueError(f"section plane {plane.origin} misses the part")
    n = np.array(tuple(plane.z_dir))
    o = np.array(tuple(plane.origin))
    cut_ids = []
    for i, f in enumerate(kept.faces()):
        try:
            c = np.array(tuple(f.center()))
            fn = np.array(tuple(f.normal_at()))
        except Exception:
            continue
        if abs(np.dot(c - o, n)) < 1e-4 and abs(abs(np.dot(fn, n)) - 1) < 1e-6:
            cut_ids.append(i)
    return kept, cut_ids


def _bbox_text(shape: bd.Shape) -> str:
    bb = shape.bounding_box()
    return (
        f"X {bb.size.X:.2f}  Y {bb.size.Y:.2f}  Z {bb.size.Z:.2f} mm\n"
        f"min ({bb.min.X:.2f}, {bb.min.Y:.2f}, {bb.min.Z:.2f})"
    )


def render_view(
    shape: bd.Shape,
    out_png: Path,
    view: str,
    title: str = "",
    annotate: bool = False,
    size=(1200, 900),
    highlight_faces: list[int] | None = None,
    camera_dir=None,
    view_up=None,
):
    mesh = to_pyvista(shape)
    mesh = mesh.compute_normals(
        cell_normals=False, split_vertices=False, consistent_normals=False,
        auto_orient_normals=False,
    )
    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background("white")
    if highlight_faces:
        mesh.cell_data["cut"] = np.isin(mesh.cell_data["face_id"],
                                        highlight_faces).astype(float)
        pl.add_mesh(mesh, scalars="cut", cmap=[BODY, CUT], clim=(0, 1),
                    show_scalar_bar=False, smooth_shading=True, specular=0.2)
    else:
        pl.add_mesh(mesh, color=BODY, smooth_shading=True, specular=0.2)
    edges = edge_lines(shape)
    if edges is not None:
        pl.add_mesh(edges, color=EDGE, line_width=2)

    d, up = (camera_dir, view_up) if camera_dir is not None else VIEWS[view]
    d = np.asarray(d, float)
    d /= np.linalg.norm(d)
    bb = shape.bounding_box()
    c = np.array(tuple(bb.center()))
    diag = max(bb.diagonal, 1e-6)
    pl.camera_position = [tuple(c + d * diag * 3), tuple(c), tuple(up)]
    pl.enable_parallel_projection()
    pl.reset_camera()
    # Fit the *projected* bbox (reset_camera fits the bounding sphere, which
    # leaves thin parts tiny in edge-on views).
    up = np.asarray(up, float)
    up = up - np.dot(up, d) * d
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    corners = np.array([(x, y, z) for x in (bb.min.X, bb.max.X)
                        for y in (bb.min.Y, bb.max.Y) for z in (bb.min.Z, bb.max.Z)])
    w = np.ptp(corners @ right)
    h = np.ptp(corners @ up)
    aspect = size[0] / size[1]
    margin = 1.45 if annotate else 1.15
    pl.camera.parallel_scale = max(h / 2, w / 2 / aspect, 1e-3) * margin

    if annotate:
        pl.add_mesh(pv.Box(bounds=(bb.min.X, bb.max.X, bb.min.Y, bb.max.Y,
                                   bb.min.Z, bb.max.Z)).outline(),
                    color="#888888", line_width=1)
        ext = np.array(tuple(bb.size))
        nl = [2 if e < 0.2 * ext.max() else 5 for e in ext]
        pl.show_bounds(location="outer", grid=False, ticks="outside",
                       n_xlabels=nl[0], n_ylabels=nl[1], n_zlabels=nl[2],
                       xtitle="X mm", ytitle="Y mm", ztitle="Z mm",
                       font_size=10, color="#333333", fmt="%.1f")
        pl.add_text(_bbox_text(shape), position="lower_left", font_size=10,
                    color="#222222")
    label = f"{title}  [{view}]" if title else view
    pl.add_text(label, position="upper_left", font_size=11, color="#222222")
    # tiny axis triad so orientation is never ambiguous
    pl.add_axes(line_width=3, labels_off=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out_png))
    pl.close()
    return out_png


def contact_sheet(pngs: list[Path], out_png: Path, cols: int = 2):
    from PIL import Image

    ims = [Image.open(p).convert("RGB") for p in pngs]
    w, h = ims[0].size
    w2, h2 = w // 2, h // 2
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w2, rows * h2), "white")
    for i, im in enumerate(ims):
        sheet.paste(im.resize((w2, h2), Image.LANCZOS), ((i % cols) * w2, (i // cols) * h2))
    sheet.save(out_png)
    return out_png


def render(
    src,
    outdir: str | Path = "out/renders",
    views=DEFAULT_VIEWS,
    section: str | bd.Plane | None = None,
    annotate: bool = False,
    size=(1200, 900),
    name: str | None = None,
) -> list[Path]:
    parts = load_parts(src)
    if name is None:
        name = "_".join(parts) if len(parts) <= 3 else "assembly"
    shape = next(iter(parts.values())) if len(parts) == 1 else bd.Compound(
        children=list(parts.values()))
    outdir = Path(outdir)
    pngs = [
        render_view(shape, outdir / f"{name}_{v}.png", v, name, annotate, size)
        for v in views
    ]
    if section is not None:
        plane = parse_plane(section) if isinstance(section, str) else section
        kept, cut_ids = section_shape(shape, plane)
        n = np.array(tuple(plane.z_dir))
        # look back at the cut face; pick an up vector not parallel to n
        up = (0, 0, 1) if abs(n[2]) < 0.9 else (0, 1, 0)
        fmt = lambda v: "(" + ", ".join(f"{x:g}" for x in np.round(v, 3)) + ")"
        pngs.append(render_view(kept, outdir / f"{name}_section.png",
                                f"section @ {fmt(tuple(plane.origin))} n={fmt(n)}", name,
                                annotate, size, cut_ids, camera_dir=n, view_up=up))
        iso_dir = n + np.array([0.6, -0.6, 0.6]) * (1 - abs(n))  # oblique-ish
        if np.linalg.norm(np.cross(iso_dir, up)) < 1e-6:
            iso_dir = n + np.array([0.5, -0.5, 0])
        pngs.append(render_view(kept, outdir / f"{name}_section_iso.png",
                                "section (oblique)", name, annotate, size,
                                cut_ids, camera_dir=iso_dir, view_up=up))
    pngs.append(contact_sheet(pngs, outdir / f"{name}_sheet.png"))
    return pngs


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("part")
    ap.add_argument("-o", "--outdir", default="out/renders")
    ap.add_argument("--views", default=",".join(DEFAULT_VIEWS),
                    help=f"comma list from {','.join(VIEWS)}")
    ap.add_argument("--section", help="plane: 'y=0' or 'ox,oy,oz:nx,ny,nz'")
    ap.add_argument("--annotate", action="store_true",
                    help="bbox outline, axis rulers and dimension text")
    ap.add_argument("--size", default="1200x900")
    ap.add_argument("--name")
    a = ap.parse_args(argv)
    size = tuple(int(x) for x in a.size.lower().split("x"))
    views = [v for v in a.views.split(",") if v]
    for p in render(a.part, a.outdir, views, a.section, a.annotate, size, a.name):
        print(p)


if __name__ == "__main__":
    sys.exit(main())
