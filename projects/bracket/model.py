"""Parametric model. build() must return a build123d Part (or a dict
{name: Part} for multi-part projects). Dimensions come from params.py."""

from build123d import (Align, Axis, Box, BuildPart, Cylinder, Locations, Mode,
                       fillet)

import params as P

NAME = "bracket"


def build():
    with BuildPart() as part:
        Box(P.LENGTH, P.WIDTH, P.THICKNESS,
            align=(Align.CENTER, Align.CENTER, Align.MIN))
        fillet(part.edges().filter_by(Axis.Z), radius=P.CORNER_R)
        with Locations((-P.HOLE_SPACING / 2, 0), (P.HOLE_SPACING / 2, 0)):
            Cylinder(P.HOLE_D / 2, P.THICKNESS, mode=Mode.SUBTRACT,
                     align=(Align.CENTER, Align.CENTER, Align.MIN))
    p = part.part
    p.label = NAME
    return p


if __name__ == "__main__":
    # `python model.py` pushes the part to the OCP CAD Viewer in VS Code
    # (start the viewer first; see ~/cad/CLAUDE.md).
    from ocp_vscode import show

    show(build(), names=[NAME])
