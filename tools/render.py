"""Headless PNG renders of a part or assembly.

    python -m tools.render PART [-o OUTDIR] [--views front,top,right,iso]
                           [--section y=0 | --section 10,0,0:1,0,0]
                           [--exploded [SCALE]] [--xray part1,part2]
                           [--only part1,part2] [--annotate] [--size 1200x900]

PART is a .step/.brep file or a project model.py (see tools.model_io). For
assemblies (build() returns a dict) every part gets its own colour (COLORS in
model.py, else a palette); --exploded offsets parts by EXPLODE in model.py
(or radially from the assembly centre); --xray draws the named parts
translucent so the insides show.

Writes <name>_<view>.png per view plus <name>_sheet.png (all views tiled) and
prints the paths. Uses VTK's EGL window: no X/Wayland display needed.

Conventions (right-handed, Z up, matches FreeCAD's standard views):
  front = looking along +Y (camera at -Y)     top  = looking down -Z
  right = looking along -X (camera at +X)     iso  = camera at (+1,-1,+1)
Section: material on the +normal side of the plane is removed from every part
and the camera looks back along -normal; cut faces are drawn in a darker,
saturated shade of the part colour.
"""

from __future__ import annotations

import argparse
import colorsys
import math
import sys
from dataclasses import dataclass
from pathlib import Path

from tools.model_io import Assembly, edge_lines, load_assembly, to_pyvista

import build123d as bd
import numpy as np
import pyvista as pv

pv.OFF_SCREEN = True

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
    "iso_back": ((-1, 1, 1), (0, 0, 1)),
    "iso_below": ((1, -1, -1), (0, 0, 1)),
}
DEFAULT_VIEWS = ["front", "top", "right", "iso"]


@dataclass
class Item:
    shape: bd.Shape
    color: str = "#8fa8c8"
    opacity: float = 1.0
    name: str = ""
    cut_faces: tuple = ()          # face indices drawn as section faces
    edges: bool = True


def parse_plane(spec: str) -> bd.Plane:
    """'x=5' | 'y=0' | 'z=-2.5' | 'ox,oy,oz:nx,ny,nz'."""
    s = spec.replace(" ", "").lower()
    if "=" in s and s[0] in "xyz":
        ax, val = s.split("=", 1)
        v = float(val)
        normal = {"x": (1, 0, 0), "y": (0, 1, 0), "z": (0, 0, 1)}[ax]
        return bd.Plane(origin=tuple(v * c for c in normal), z_dir=normal)
    o, n = s.split(":")
    return bd.Plane(origin=tuple(map(float, o.split(","))),
                    z_dir=tuple(map(float, n.split(","))))


def section_shape(shape: bd.Shape, plane: bd.Plane):
    """Cut shape with plane; return (kept shape or None, cut-face indices)."""
    try:
        kept = shape.split(plane, keep=bd.Keep.BOTTOM)
    except Exception:
        return None, []
    if isinstance(kept, (list, tuple)):
        kept = bd.Compound(children=list(kept)) if kept else None
    if kept is None or not kept.faces():
        return None, []
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


def _rgb(hexcol: str) -> np.ndarray:
    h = hexcol.lstrip("#")
    return np.array([int(h[i:i + 2], 16) for i in (0, 2, 4)], float) / 255


def _cut_color(hexcol: str) -> np.ndarray:
    r, g, b = _rgb(hexcol)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return np.array(colorsys.hls_to_rgb(h, max(0.25, l * 0.6), min(1, s + 0.35)))


def _bounds(items):
    bbs = [it.shape.bounding_box() for it in items]
    lo = np.min([tuple(b.min) for b in bbs], axis=0)
    hi = np.max([tuple(b.max) for b in bbs], axis=0)
    return lo, hi


def _setup_camera(pl, lo, hi, d, up, size, margin):
    d = np.asarray(d, float)
    d /= np.linalg.norm(d)
    c = (lo + hi) / 2
    diag = max(np.linalg.norm(hi - lo), 1e-6)
    pl.camera_position = [tuple(c + d * diag * 3), tuple(c), tuple(up)]
    pl.enable_parallel_projection()
    pl.reset_camera()
    # Fit the *projected* bbox (reset_camera fits the bounding sphere, which
    # leaves thin parts tiny in edge-on views).
    up = np.asarray(up, float)
    up = up - np.dot(up, d) * d
    up /= np.linalg.norm(up)
    right = np.cross(up, d)
    corners = np.array([(x, y, z) for x in (lo[0], hi[0])
                        for y in (lo[1], hi[1]) for z in (lo[2], hi[2])])
    w = np.ptp(corners @ right)
    h = np.ptp(corners @ up)
    pl.camera.parallel_scale = max(h / 2, w / 2 / (size[0] / size[1]), 1e-3) * margin


def _annotate(pl, lo, hi):
    pl.add_mesh(pv.Box(bounds=(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])).outline(),
                color="#888888", line_width=1)
    ext = hi - lo
    nl = [2 if e < 0.2 * ext.max() else 5 for e in ext]
    pl.show_bounds(bounds=(lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]),
                   location="outer", grid=False, ticks="outside",
                   n_xlabels=nl[0], n_ylabels=nl[1], n_zlabels=nl[2],
                   xtitle="X mm", ytitle="Y mm", ztitle="Z mm",
                   font_size=10, color="#333333", fmt="%.1f")
    pl.add_text(f"X {ext[0]:.2f}  Y {ext[1]:.2f}  Z {ext[2]:.2f} mm\n"
                f"min ({lo[0]:.2f}, {lo[1]:.2f}, {lo[2]:.2f})",
                position="lower_left", font_size=10, color="#222222")


def _finish(pl, out_png, label):
    pl.add_text(label, position="upper_left", font_size=11, color="#222222")
    pl.add_axes(line_width=3, labels_off=False)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    pl.screenshot(str(out_png))
    pl.close()
    return out_png


def render_items(items: list[Item], out_png: Path, view: str = "iso", title="",
                 annotate=False, size=(1200, 900), camera_dir=None, view_up=None,
                 legend=False):
    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background("white")
    for it in items:
        mesh = to_pyvista(it.shape).compute_normals(
            cell_normals=False, split_vertices=False, consistent_normals=False,
            auto_orient_normals=False)
        # Every mesh goes through the same per-cell RGB path: mixing plain
        # colour actors with RGB-scalar actors made VTK render the later ones
        # speckled (order-dependent).
        base = _rgb(it.color)
        cut = np.isin(mesh.cell_data["face_id"], it.cut_faces) if it.cut_faces else \
            np.zeros(mesh.n_cells, bool)
        cols = np.where(cut[:, None], _cut_color(it.color), base)
        mesh.cell_data["rgb"] = (cols * 255).astype(np.uint8)
        pl.add_mesh(mesh, scalars="rgb", rgb=True, opacity=it.opacity,
                    smooth_shading=True, specular=0.2)
        if it.edges:
            e = edge_lines(it.shape)
            if e is not None:
                pl.add_mesh(e, color=EDGE, line_width=2 if it.opacity > 0.6 else 1,
                            opacity=1.0 if it.opacity > 0.6 else 0.35)
    if legend and 1 < len({it.name for it in items}) <= 12:
        seen = {}
        for it in items:
            seen.setdefault(it.name, it.color)
        pl.add_legend([[n, c] for n, c in seen.items() if n], bcolor="white",
                      face="rectangle", size=(0.18, 0.04 * min(len(seen), 14)),
                      loc="upper right")
    d, up = (camera_dir, view_up) if camera_dir is not None else VIEWS[view]
    lo, hi = _bounds(items)
    _setup_camera(pl, lo, hi, d, up, size, 1.45 if annotate else 1.15)
    if annotate:
        _annotate(pl, lo, hi)
    return _finish(pl, out_png, f"{title}  [{view}]" if title else view)


# backwards-compatible single-shape entry point
def render_view(shape, out_png, view, title="", annotate=False, size=(1200, 900),
                highlight_faces=None, camera_dir=None, view_up=None):
    it = Item(shape, cut_faces=tuple(highlight_faces or ()))
    return render_items([it], Path(out_png), view, title, annotate, size,
                        camera_dir, view_up)


def render_scalar(mesh: pv.PolyData, scalar: str, out_png: Path, view="iso",
                  title="", cmap="RdYlGn", clim=None, size=(1200, 900),
                  edges=None, scalar_title=None, camera_dir=None, view_up=None,
                  below_color=None, above_color=None):
    """Render a mesh coloured by a per-cell scalar (draft/overhang/thickness)."""
    pl = pv.Plotter(off_screen=True, window_size=size)
    pl.set_background("white")
    pl.add_mesh(mesh, scalars=scalar, cmap=cmap, clim=clim,
                below_color=below_color, above_color=above_color,
                scalar_bar_args={"title": scalar_title or scalar, "color": "#222222",
                                 "vertical": True, "position_x": 0.86,
                                 "position_y": 0.25, "height": 0.5, "width": 0.06},
                smooth_shading=False)
    if edges is not None:
        pl.add_mesh(edges, color=EDGE, line_width=1, opacity=0.5)
    d, up = (camera_dir, view_up) if camera_dir is not None else VIEWS[view]
    b = np.array(mesh.bounds)
    _setup_camera(pl, b[0::2], b[1::2], d, up, size, 1.15)
    return _finish(pl, out_png, f"{title}  [{view}]" if title else view)


def contact_sheet(pngs: list[Path], out_png: Path, cols: int = 2):
    from PIL import Image

    ims = [Image.open(p).convert("RGB") for p in pngs]
    w, h = ims[0].size
    w2, h2 = w // 2, h // 2
    rows = math.ceil(len(ims) / cols)
    sheet = Image.new("RGB", (cols * w2, rows * h2), "white")
    for i, im in enumerate(ims):
        sheet.paste(im.resize((w2, h2), Image.LANCZOS),
                    ((i % cols) * w2, (i // cols) * h2))
    sheet.save(out_png)
    return out_png


def _explode_offsets(asm: Assembly, scale: float) -> dict[str, np.ndarray]:
    if asm.explode:
        return {k: np.array(asm.explode.get(k, (0, 0, 0)), float) * scale
                for k in asm.parts}
    # radial fallback: push each part away from the assembly centre
    lo, hi = _bounds([Item(s) for s in asm.parts.values()])
    c = (lo + hi) / 2
    diag = np.linalg.norm(hi - lo)
    out = {}
    for k, s in asm.parts.items():
        v = np.array(tuple(s.bounding_box().center())) - c
        n = np.linalg.norm(v)
        out[k] = (v / n * 0.35 * diag * scale) if n > 1e-6 else np.zeros(3)
    return out


def assembly_items(asm: Assembly, exploded: float = 0.0, xray=(), only=None,
                   plane: bd.Plane | None = None) -> list[Item]:
    offs = _explode_offsets(asm, exploded) if exploded else {}
    items = []
    for k, s in asm.parts.items():
        if only and k not in only:
            continue
        cut = ()
        if plane is not None:
            s, cut = section_shape(s, plane)
            if s is None:
                continue
        if exploded and np.any(offs[k]):
            s = bd.Pos(*offs[k]) * s
        items.append(Item(s, asm.colors[k], 0.22 if k in xray else 1.0, k,
                          tuple(cut)))
    if not items:
        raise ValueError("nothing to render (section plane misses every part?)")
    return items


def render(src, outdir: str | Path = "out/renders", views=DEFAULT_VIEWS,
           section: str | bd.Plane | None = None, annotate: bool = False,
           size=(1200, 900), name: str | None = None, exploded: float = 0.0,
           xray=(), only=None) -> list[Path]:
    asm = load_assembly(src)
    if name is None:
        name = "_".join(asm.parts) if len(asm) <= 2 else "assembly"
    outdir = Path(outdir)
    legend = len(asm) > 1
    tag = "_exploded" if exploded else ""
    items = assembly_items(asm, exploded, xray, only)
    pngs = [render_items(items, outdir / f"{name}{tag}_{v}.png", v, name,
                         annotate, size, legend=legend) for v in views]
    if section is not None:
        plane = parse_plane(section) if isinstance(section, str) else section
        sitems = assembly_items(asm, 0.0, xray, only, plane)
        n = np.array(tuple(plane.z_dir), float)
        up = (0, 0, 1) if abs(n[2]) < 0.9 else (0, 1, 0)
        fmt = lambda v: "(" + ", ".join(f"{x:g}" for x in np.round(v, 3)) + ")"
        pngs.append(render_items(
            sitems, outdir / f"{name}_section.png",
            f"section @ {fmt(tuple(plane.origin))} n={fmt(n)}", name, annotate,
            size, camera_dir=n, view_up=up, legend=legend))
        iso_dir = n + np.array([0.6, -0.6, 0.6]) * (1 - np.abs(n))
        if np.linalg.norm(np.cross(iso_dir, up)) < 1e-6:
            iso_dir = n + np.array([0.5, -0.5, 0])
        pngs.append(render_items(sitems, outdir / f"{name}_section_iso.png",
                                 "section (oblique)", name, annotate, size,
                                 camera_dir=iso_dir, view_up=up, legend=legend))
    pngs.append(contact_sheet(pngs, outdir / f"{name}{tag}_sheet.png"))
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
    ap.add_argument("--exploded", nargs="?", type=float, const=1.0, default=0.0,
                    help="exploded view, optional scale on EXPLODE offsets")
    ap.add_argument("--xray", default="", help="parts drawn translucent")
    ap.add_argument("--only", default="", help="render only these parts")
    ap.add_argument("--size", default="1200x900")
    ap.add_argument("--name")
    a = ap.parse_args(argv)
    size = tuple(int(x) for x in a.size.lower().split("x"))
    views = [v for v in a.views.split(",") if v]
    split = lambda s: [x for x in s.split(",") if x]
    for p in render(a.part, a.outdir, views, a.section, a.annotate, size, a.name,
                    a.exploded, split(a.xray), split(a.only) or None):
        print(p)


if __name__ == "__main__":
    sys.exit(main())
