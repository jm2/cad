"""Tooling self-test assembly with DELIBERATE faults (not a real design).

Expected results:
  tools.assembly : pin/lid overlap FAIL; base/lid touching = allowed contact;
                   knob/lid clearance FAIL (0.2 mm gap < 0.5 required)
  tools.mfg draft (base, pull +Z): vertical walls "no draft", inner lip
                   underside "undercut"
  tools.mfg overhang (lid as-is): lip underside "needs support"
"""
from build123d import Align, Box, Cylinder, Pos

A = (Align.CENTER, Align.CENTER, Align.MIN)


def build():
    base = Box(40, 30, 20, align=A) - Pos(0, 0, 2) * Box(36, 26, 20, align=A)
    base += Pos(0, 13 - 1.5, 15) * Box(30, 3, 2, align=A)      # inner lip -> undercut
    lid = Pos(0, 0, 20) * Box(40, 30, 2, align=A)
    lid += Pos(0, 0, 18) * Box(30, 20, 2, align=A) - Pos(0, 0, 18) * Box(26, 16, 2, align=A)
    pin = Pos(15, 0, 17) * Cylinder(1.5, 8, align=A)            # pokes into lid
    knob = Pos(-10, 0, 22.2) * Cylinder(4, 5, align=A)          # 0.2 mm above lid
    return {"base": base, "lid": lid, "pin": pin, "knob": knob}


COLORS = {"base": "#8fa8c8", "lid": "#e0a458", "pin": "#c97c8a", "knob": "#7fb685"}
EXPLODE = {"lid": (0, 0, 25), "pin": (0, 0, 45), "knob": (0, 0, 55)}
ALLOWED_CONTACT = [("base", "lid")]
MIN_CLEARANCE = {("knob", "lid"): 0.5}
PRINT_ORIENT = {"lid": (0, 0, 0)}
PULL = {"base": (0, 0, 1)}
