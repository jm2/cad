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
    export.py                STEP + STL + 3MF into out/
    slice.py                 PrusaSlicer CLI wrapper (time, filament, warnings)
    roundtrip.py             compare STEP in build123d vs FreeCAD (freecadcmd)
    freecad_inspect.py       runs inside FreeCAD's Python only
    freecadcmd.sh            finds native or Flatpak freecadcmd
    new_project.sh           scaffold a project
    profiles/                PrusaSlicer .ini files (generic_pla_0.4.ini = placeholder)
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
6. **Slice** (printed parts only): `make slice PROFILE=tools/profiles/<real>.ini`.
   The generic profile is only a smoke test. Its time and filament numbers
   don't describe the user's printer.
7. **Commit** once it builds, renders correctly and passes checks:
   `git add -A && git commit -m "<project>: <what changed>"`.

## Rules

- **Never call a change done until you have viewed the renders**, every view,
  after the latest build. Passing tests is not enough; look at the images.
- **All dimensions live in `params.py`** (mm). No magic numbers in `model.py`
  or the tests; tests compare against `params`.
- **Commit after each working iteration** (builds, renders correctly,
  `make check` passes). Never commit `out/`.
- Do NOT install or import FreeCAD modules in the venv (different OCCT build).
  FreeCAD runs only through `tools/freecadcmd.sh` and `make roundtrip`.
- Ask the user for real printer, material and nozzle details. Don't guess
  slicer settings.
- Temp/scratch files go under `${TMPDIR:-/var/tmp}`, never `/tmp`.

## Commands

```bash
tools/new_project.sh myproj && cd projects/myproj
make build render check          # the inner loop (also: `make all`)
make render SECTION=y=0          # section plane: x=, y=, z=, or 'ox,oy,oz:nx,ny,nz'
make render RENDER_ARGS=         # without rulers/bbox annotation
make export                      # STEP/STL/3MF
make slice PROFILE=../../tools/profiles/generic_pla_0.4.ini
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

## Known quirks

- Wall-thickness is a ray-cast estimate. Assert on p1, not min.
- `tools/profiles/generic_pla_0.4.ini` is not the user's printer.
- lib3mf emits DeprecationWarnings on Python 3.14; pytest filters them.
