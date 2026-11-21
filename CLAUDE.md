# Code-first CAD workspace

Parametric parts are Python (build123d on OCP/OCCT). Claude renders them
headlessly, inspects the PNGs, checks geometry in code, and exports STEP for
human review in FreeCAD. STEP is the only interchange with FreeCAD.

## Layout

```
~/cad/
  pyproject.toml, .venv/     uv venv (Python 3.14): build123d, ocp_vscode, pyvista,
                             vtk, trimesh, manifold3d, numpy, pytest
  tools/
    model_io.py              load STEP/BREP/model.py -> Shape; tessellation helpers
    build.py                 model.py -> out/NAME.step (+ validity/bbox/volume line)
    render.py                PNGs: front/top/right/iso, --section PLANE, --annotate,
                             plus NAME_sheet.png tiling every view
    check.py                 validity, watertight, bbox, volume/mass, wall thickness,
                             interference(), cylinders(), Dims asserts
    export.py                STEP + STL + 3MF into out/ (--print: per-part, print-oriented)
    assembly.py              pairwise interference / contact / clearance matrix
    mfg.py                   draft + undercut maps (moulding), overhang maps (FDM)
    selftest/model.py        assembly with deliberate faults: run tools against it
                             after changing them (expected results in its docstring)
    slice.py                 slicer wrapper: Bambu Studio (default) or PrusaSlicer
    bambu.py                 Bambu install + preset resolver (`python -m tools.bambu list`)
    roundtrip.py             compare STEP in build123d vs FreeCAD (freecadcmd)
    freecad_inspect.py       runs inside FreeCAD's Python only
    freecadcmd.sh            finds native or Flatpak freecadcmd
    new_project.sh           scaffold a project
    profiles/                PrusaSlicer .ini files (generic, legacy fallback only)
  projects/<name>/
    params.py                EVERY dimension, in mm
    model.py                 build() -> Part (or {name: Part}); `python model.py` = view
    test_model.py            dimension asserts (pytest + tools.check.Dims)
    Makefile                 build render check export slice roundtrip view clean
    out/                     generated (gitignored): STEP/STL/3MF/gcode/renders
```

## Workflow (follow every iteration)

1. **Edit** `params.py` and/or `model.py`. New dimension? It goes in `params.py`.
2. **Build:** `make build` (writes `out/NAME.step`, fails if invalid).
3. **Render and look:** `make render` (add `SECTION=x=0` etc. as needed). Then
   **open and view every PNG** in `out/renders/`: front, top, right, iso,
   section, section_iso (the `_sheet.png` shows them all at once; open single
   views to check detail). Check the features exist, sit in the right place,
   face the right way, and match the intent.
4. **Check:** `make check` runs the pytest dimension asserts, then
   `tools.check` (BRep valid, watertight, manifold, mesh-vs-BRep volume,
   wall thickness against `params.MIN_WALL`, mass at `params.DENSITY`).
   Add asserts to `test_model.py` for every feature that matters.
5. **Export:** `make export` writes STEP/STL/3MF to `out/`.
6. **Slice** (printed parts only): `make slice` (Bambu Studio, X1C, 0.20mm
   Standard, Bambu PLA Basic). Override with `PRINTER=H2D`,
   `FILAMENT="Bambu PETG HF"`, `PROCESS="0.16mm Optimal"`.
7. **Commit** once it builds, renders correctly and passes checks:
   `git add -A && git commit -m "<project>: <what changed>"`.

## Assemblies

`build()` may return `{name: Part}`. Optional metadata in model.py:
`COLORS`, `EXPLODE` (offsets for exploded renders), `ALLOWED_CONTACT` (pairs
that may touch/overlap), `MIN_CLEARANCE` ({(a, b): mm}), `PRINT_ORIENT`
({name: (rx, ry, rz)} degrees), `PULL` ({name: mould pull direction}).
Extra make targets: `asm`, `exploded`, `draft`, `overhang`, `print`,
`slice-print`. Renders accept `--xray part1,part2` (translucent) and
`--only ...`; mfg maps accept `--section PLANE` to reveal internal faces.

## Rules

- **Never call a change done until you have viewed the renders**, every view,
  after the latest build. Passing tests is not enough; look at the images.
- **All dimensions live in `params.py`** (mm). No magic numbers in `model.py`
  or the tests; tests compare against `params`.
- **Commit after each working iteration** (builds, renders correctly,
  `make check` passes). Never commit `out/`.
- Do NOT install or import FreeCAD modules in the venv (different OCCT build).
  FreeCAD runs only through `tools/freecadcmd.sh` and `make roundtrip`.
- Target printer is a Bambu Lab X1 Carbon (0.4 nozzle); H2D only if a part
  truly needs it. Use Bambu's system presets; don't invent slicer settings.
- Temp/scratch files go under `${TMPDIR:-/var/tmp}`, never `/tmp`.

## Commands

```bash
tools/new_project.sh myproj && cd projects/myproj
make build render check          # the inner loop (also: `make all`)
make render SECTION=y=0          # section plane: x=, y=, z=, or 'ox,oy,oz:nx,ny,nz'
make render RENDER_ARGS=         # without rulers/bbox annotation
make export                      # STEP/STL/3MF
make slice                       # Bambu Studio, X1C; PRINTER=H2D FILAMENT=...
make roundtrip                   # STEP volume/bbox in FreeCAD == build123d
make view                        # push to OCP CAD Viewer in VS Code
```

Tools also work directly (from `~/cad`, with `PYTHONPATH=.`):
`.venv/bin/python -m tools.check a.step --interfere b.step`,
`python -m tools.render part.step --views iso,bottom --section 0,0,3:0,0,1`.

Python API for tests: `Dims(part).expect(name, actual, nominal, tol)`,
`expect_between/le/ge/true`, `.verify()` raises with all failures listed;
`report(part, density, min_wall=...)`, `interference(a, b)` (mm³),
`min_distance(a, b)`, `cylinders(part)` (radius, `axis_pos`, `axis_dir`).
Hole positions: use `axis_pos`, not `center` (the face centroid).

## FreeCAD

FreeCAD 1.1.4 (bundles OCCT 7.8.1; the venv's OCP is OCCT 8.0.1) comes from the
official AppImage, extracted to `~/.local/opt/freecad/<version>/squashfs-root`.
`~/.local/opt/freecad/current` points at the active version. Wrappers
`~/.local/bin/freecadcmd` (headless) and `~/.local/bin/freecad` (GUI) go
through that symlink. To upgrade: download the new AppImage and its
`-SHA256.txt` from github.com/FreeCAD/FreeCAD/releases into a new version dir,
run `sha256sum -c`, `--appimage-extract`, then `ln -sfn <ver> current` and
`make roundtrip`. Review a part with `freecad out/NAME.step`.

## Slicer (Bambu Studio)

Bambu Studio 02.09.01.70 (AGPL, official AppImage, digest-verified), extracted to
`~/.local/opt/bambustudio/<version>/squashfs-root`; `current` symlink;
wrapper `~/.local/bin/bambu-studio` (GUI). The CLI slices headless with
DISPLAY unset. Upgrades go the same way as FreeCAD (new version dir, check the
GitHub asset digest, extract, move `current`, re-slice the bracket).

## Headless rendering

VTK uses EGL on the AMD RX 6400 (Mesa radeonsi); no X/Wayland display needed.
`tools.model_io` sets `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`. Views are
orthographic: front = looking +Y, top = looking −Z, right = looking −X,
iso = camera at (+1,−1,+1), Z up (same as FreeCAD's standard views).
For a section, material on the +normal side of the plane is removed, and the
camera looks back along −normal at the cut face (red).

## Live view (OCP CAD Viewer)

VS Code extension `bernhard-42.ocp-cad-viewer` (matches `ocp_vscode` 4.3.0).
Open `~/cad` in VS Code and select `.venv/bin/python` as the interpreter.
Start the viewer: Command Palette → "OCP CAD Viewer: Open Viewer" (or the OCP
icon in the sidebar). It listens on port 3939. Then `make view` or run
`model.py` (its `__main__` calls `ocp_vscode.show`). In other scripts use
`from ocp_vscode import show; show(part)`.

## Fulcrum (projects/fulcrum)

Ambidextrous wired/wireless mouse, two variants from one master:
`make <target> VARIANT=molded|fdm`; targets: build render exploded sections
test asm check draft overhang export print slice roundtrip mass.
Sources: params.py (everything) -> form.py (master surfaces) -> layout.py
(bought-in envelopes, derived positions) -> top.py / base.py / wheel.py ->
model.py (assembly metadata) ; test_model.py (functional asserts), mass.py.
Parts are cached as BREP in out/cache/<variant>-<hash of geometry sources>;
a cold build is ~3-5 min, cached loads are instant. After changing geometry,
run `make test asm` for BOTH variants and look at renders + sections.
Design rules learned the hard way: keep every closed contour at the same
point count with uniform parameters (form.closed_spline) or lofts and STEP
files explode in size; derive positions from the form via form.surface_z /
half_width rather than hard-coding heights.

## Known quirks

- build123d's `tessellate()` asks OCCT for a RELATIVE deflection; use
  tools.model_io.mesh_arrays/to_pyvista (absolute) for anything quantitative.
- build123d's `Shape.volume`/`.area` use fixed-order integration that can be
  tens of % wrong on lofted B-spline solids: use tools.model_io.mass_props /
  volume / area (adaptive).
- tools.assembly is mesh-first (manifold3d booleans + min_gap) and confirms
  flagged pairs with exact BRep booleans; `--exact` forces BRep everywhere.
- Plane-split / boolean with a loft that closes in an apex vertex is fragile;
  close lofts with tiny end sections or contour lofts instead.

- Wall-thickness is a ray-cast estimate. Assert on p1, not min.
- Bambu Studio's CLI ignores `inherits` in presets; `tools.bambu.resolve`
  flattens them first. Without that, density=0 (0 g) and process defaults are wrong.
- Bambu Studio logs a glfw/Wayland error with no display (it's only the
  thumbnail renderer); slicing is unaffected and slice.py filters it.
- Bambu's G-code says "filament volume [cm^3]" but the number is mm³;
  slice.py computes cm³ from length.
- lib3mf emits DeprecationWarnings on Python 3.14; pytest filters them.
