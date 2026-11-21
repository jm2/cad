# Runs INSIDE FreeCAD's own Python (freecadcmd), never in the uv venv.
# Usage: FC_STEP=/abs/path/part.step tools/freecadcmd.sh tools/freecad_inspect.py
# Prints one line: FCJSON {...} with volume, area, bbox, validity.
import json
import os

import FreeCAD
import Part

path = os.environ["FC_STEP"]
shape = Part.Shape()
shape.read(path)
bb = shape.BoundBox
print("FCJSON " + json.dumps({
    "freecad": ".".join(FreeCAD.Version()[:3]),
    "occt": Part.OCC_VERSION,
    "file": path,
    "valid": shape.isValid(),
    "solids": len(shape.Solids),
    "faces": len(shape.Faces),
    "volume": shape.Volume,
    "area": shape.Area,
    "bbox_min": [bb.XMin, bb.YMin, bb.ZMin],
    "bbox_max": [bb.XMax, bb.YMax, bb.ZMax],
}), flush=True)
