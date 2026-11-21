#!/usr/bin/env bash
# Run FreeCAD's headless command-line interpreter, native or Flatpak.
# Env vars named FC_* are forwarded into the Flatpak sandbox.
set -euo pipefail
if command -v freecadcmd >/dev/null 2>&1; then exec freecadcmd "$@"; fi
if command -v FreeCADCmd >/dev/null 2>&1; then exec FreeCADCmd "$@"; fi
if flatpak info org.freecad.FreeCAD >/dev/null 2>&1; then
  envs=()
  while IFS='=' read -r k _; do envs+=("--env=$k=${!k}"); done < <(env | grep '^FC_' || true)
  exec flatpak run --filesystem=home "${envs[@]}" --command=FreeCADCmd org.freecad.FreeCAD "$@"
fi
echo "freecadcmd not found (no native package, no org.freecad.FreeCAD flatpak)" >&2
exit 127
