"""All dimensions for this project, in millimetres. model.py and the tests
read from here; never hard-code a dimension anywhere else."""

# plate
LENGTH = 80.0          # X
WIDTH = 40.0           # Y
THICKNESS = 6.0        # Z
CORNER_R = 6.0         # vertical-edge fillet radius

# mounting holes (M6 clearance, ISO 273 medium)
HOLE_D = 6.6
HOLE_SPACING = 60.0    # centre-to-centre along X, centred on the plate

# fabrication
MIN_WALL = 1.2         # mm, smallest wall allowed (≈3 perimeters @ 0.4 nozzle)
DENSITY = 1.24         # g/cm^3 (PLA)
