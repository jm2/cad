# Runs INSIDE FreeCAD's own Python (freecadcmd), never in the uv venv.
# Usage: FC_STEP=/abs/path/part.step tools/freecadcmd.sh tools/freecad_inspect.py
# Prints one line: FCJSON {...} with volume, area, bbox, validity.
import json
import os

import FreeCAD
import MeshPart
import Part

path = os.environ["FC_STEP"]
shape = Part.Shape()
shape.read(path)
# optimal box (tight on B-splines); BoundBox is built from control points
bb = shape.optimalBoundingBox(False, False)
print("FCJSON " + json.dumps({
    "freecad": ".".join(FreeCAD.Version()[:3]),
    "occt": Part.OCC_VERSION,
    "file": path,
    "valid": shape.isValid(),
    "solids": len(shape.Solids),
    "faces": len(shape.Faces),
    "volume": shape.Volume,            # OCCT default (fixed-order) integration
    "mesh_volume": MeshPart.meshFromShape(Shape=shape, LinearDeflection=0.01,
                                          AngularDeflection=0.1, Relative=False).Volume,
    "area": shape.Area,
    "bbox_min": [bb.XMin, bb.YMin, bb.ZMin],
    "bbox_max": [bb.XMax, bb.YMax, bb.ZMax],
}), flush=True)
