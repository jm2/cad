"""Fulcrum: every dimension in mm, every choice in one place.

Ambidextrous: the form is mirror-symmetric about the YZ plane (x = 0), with
two side buttons on each flank.

Coordinates: Z up, desk at z = 0. Y is the long axis, nose (buttons) at +Y,
tail at -Y; X is across (+X = right). Render view names follow FreeCAD, so
the *back* view (camera at +Y) looks at the nose and *front* at the tail.

VARIANT selects the manufacturing intent (env FULCRUM_VARIANT):
  "molded"  injection moulding: drafted walls, 1.8 mm walls, flexure buttons
            moulded into the top shell, self-tapping screws into bosses.
  "fdm"     printable on a Bambu Lab X1C: 2.0 mm walls, separate buttons on
            steel pivot pins, M2 heat-set inserts, looser fits.
"""

import os

VARIANT = os.environ.get("FULCRUM_VARIANT", "molded").lower()
assert VARIANT in ("molded", "fdm"), VARIANT
MOLDED = VARIANT == "molded"
FDM = not MOLDED

# ------------------------------------------------------------------ overall
LENGTH = 128.0             # Y, nose to tail
Y_NOSE = LENGTH / 2        # +64
Y_TAIL = -LENGTH / 2       # -64

SKATE_T = 0.8              # PTFE skate thickness
SKATE_RECESS = 0.3         # pocket depth in base -> skates stand 0.5 proud
Z_BASE = SKATE_T - SKATE_RECESS   # base underside, 0.5 above the desk
Z_SPLIT = 15.0             # parting plane base | top shell (widest silhouette)

WALL = 1.8 if MOLDED else 2.0          # shell walls
FLOOR = 1.6 if MOLDED else 2.0         # base floor
DRAFT = 3.0                # deg, outer walls each side of the parting line
FIT = 0.15 if MOLDED else 0.3          # sliding / mating clearance
GAP = 0.4 if MOLDED else 0.5           # visible split gaps around buttons

# ------------------------------------------------------------- master form
# Cross-section keyframes along Y (sampled smoothly between stations); every
# section is mirror-symmetric about x = 0.
#   h      crest height (z)
#   w      half-width at the parting plane (widest point of the section)
#   crown  how far the shoulders sit below the crest (rounder top = smaller)
#   tumble inset of the base underside vs the split outline (each side)
FORM_Y = [-64.0, -56.0, -46.0, -30.0, -12.0, 6.0, 24.0, 42.0, 56.0, 64.0]
FORM = {   # pebble: widest at the palm, steady taper to the nose, one low arch
    "h":      [24.0, 30.0, 34.5, 37.0, 37.5, 36.0, 33.0, 29.0, 25.5, 24.0],
    "w":      [27.0, 30.0, 31.5, 32.0, 31.5, 30.5, 29.5, 28.5, 27.5, 27.0],
    # cross-section squareness above the parting line: 2 = ellipse, larger =
    # fuller shoulders (boxier); the section is a super-ellipse
    "sq":     [2.0,  2.1,  2.25, 2.35, 2.4,  2.4,  2.35, 2.3,  2.2,  2.1],
    "tumble": [3.0,  3.2,  3.5,  3.5,  3.5,  3.5,  3.5,  3.4,  3.2,  3.0],
}
# End zones: over the last END_TAIL / END_NOSE mm the sections shrink along a
# quarter ellipse (width, and height about the parting plane) and the loft
# closes in a point on the parting plane, which rounds both ends without any
# fillets. END_ZPOW < 1 keeps the ends fuller in elevation than in plan.
END_TAIL = 22.0
END_NOSE = 9.0
END_ZPOW = 0.7
LOFT_STEP = 4.0            # section spacing in the middle zone

# ---------------------------------------------------------------- internals
# Main PCB: placeholder envelope, real board out of scope.
PCB_T = 1.6
PCB_Z = 7.4                # PCB underside above the desk: typical PixArt
                           # LM19-LSI lens stack (verify vs sensor datasheet)
PCB_Y = (5.0, 59.0)        # front/back extent of the main board
PCB_TOP_KEEPOUT = 4.0      # generic component height above board
PCB_BOT_KEEPOUT = 1.2      # below board (where nothing else is placed)

# Optical sensor + lens (dummy)
SENSOR_XY = (0.0, 16.0)
LENS = (21.0, 19.0, 5.0)   # x, y, height below the PCB
LENS_TO_DESK = 2.4         # lens reference plane to tracking surface
SENSOR_IC = (9.0, 13.0, 3.2)  # above PCB
SENSOR_WINDOW = (11.0, 9.0)   # opening in the base floor

# Main button switches (12.8 x 5.8 x 6.5 tactile, e.g. D2F-class footprint)
SW_MAIN = (5.8, 12.8, 6.5)    # x, y, body height
SW_PLUNGER = (1.6, 7.3)       # diameter, free height of plunger top above PCB
SW_PRETRAVEL = 0.3 if MOLDED else 0.4  # gap button post -> plunger at rest
SW_L_XY = (-13.0, 44.0)
SW_R_XY = (13.0, 44.0)

# Main buttons: plan outline on the top surface (right button; left mirrors)
BTN_REAR_Y = 10.0          # rear edge (flexure line / pivot) of L/R buttons
BTN_OUTER_X = (19.5, 21.0)  # outer edge x at the nose / at the rear edge
SPINE_HALF = 5.6           # half-width of the centre spine (wheel, mode btn)
FLEX_T = 1.0               # moulded flexure: wall thinned to this...
FLEX_BAND = 4.0            # ...over this band along the rear edge
POST_D = 3.6               # button plunger posts
HINGE_PIN_D = 2.0          # FDM: steel dowel pin through the knuckles
HINGE_KNUCKLE = (3.0, 4.0)  # FDM: knuckle thickness (x), length (y)
FLANGE = 1.2               # small buttons: retaining flange overhang
FLANGE_T = 1.0

# Small tact switches (DPI, mode, thumb, wheel click/tilt)
SW_TACT = (6.0, 6.0, 3.5)     # body x, y, height
SW_TACT_PLUNGER = (3.5, 5.0)  # stem diameter, free height of stem top

# Scroll wheel
WHEEL_D = 24.0
WHEEL_W = 7.0
WHEEL_Y = 33.0
WHEEL_PROUD = 5.0          # how far the wheel top stands above the shell
WHEEL_HUB_D = 9.0
WHEEL_TREAD_N = 30         # rubber tread ribs
WHEEL_DETENTS = 24
AXLE_D = 2.0
WHEEL_CLEAR = 0.8          # wheel to shell slot, each side / ends
# Optical wheel encoder: slotted disc on the wheel's right flank read by a
# U-shaped photo-interrupter (low, frictionless; suits free-spin)
ENC_DISC_D = 17.0          # slotted disc diameter
ENC_DISC_T = 0.8
ENC_SLOTS = 24
ENCODER = (6.0, 5.0, 8.0)  # interrupter body x, y, z (dummy)
ENC_GAP = 2.0              # slot in the interrupter the disc runs through

# Wheel-mode toggle behind the wheel
MODE_BTN_Y = 17.0
MODE_BTN = (6.0, 9.0)      # x, y footprint

# DPI up/down on the centre line behind the wheel-mode toggle
DPI_Y = [5.0, -5.0]
DPI_BTN = (7.0, 7.5)       # x, y footprint

# Side buttons: two per flank (mirrored), forward + back
SIDE_BTN_Y = [8.0, -9.0]   # centres along Y
SIDE_BTN_LEN = 15.0
SIDE_BTN_H = 7.0
SIDE_BTN_Z = 21.5          # centre height on the flank
# AA battery bay (also takes an AA-size weight slug in wired mode)
AA_D = 14.5                # IEC LR6/HR6 max
AA_L = 50.5
BAT_X = 0.0
BAT_Y = (-50.5, 4.5)       # bay inner length incl. contacts
BAT_SPRING_COMP = 3.5      # compressed spring contact (negative end)
BAT_PLATE_T = 1.0
BAT_CLEAR = 0.35           # radial play
BAT_WALL = 1.6 if MOLDED else 2.0
WEIGHT_SLUG_DENSITY = 2.70  # aluminium, ~ matches a NiMH AA's mass

# Receiver garage (generic 2.4 GHz nano receiver)
RECEIVER = (15.0, 19.0, 6.0)
RECEIVER_XY = (0.0, -30.0)   # stowed under the battery door, beside... set in layout

# USB-C receptacle (mid-mount) and plug overmold clearance
USBC = (8.94, 7.35, 3.26)
USBC_PLUG = (12.5, 7.0)    # opening for the plug overmold (x, z)

# Base switches (on main PCB underside): power slide + connection mode button
POWER_SW_XY = (11.0, 50.0)
CONN_BTN_XY = (-11.0, 50.0)

# Fasteners: base -> top shell
SCREW_XY = [(-19.0, 47.0), (19.0, 47.0), (-18.0, -42.0), (18.0, -42.0)]
SCREW_D = 2.0
SCREW_HEAD = (3.8, 1.6)    # head diameter, height (under the skates)
BOSS_OD = 5.0 if MOLDED else 6.2
BOSS_HOLE = 1.7 if MOLDED else 3.2     # self-tapping pilot | heat-set insert
INSERT = (3.2, 3.0)        # M2 heat-set insert OD, length (fdm)

# Skates (PTFE): ovals over the screws + one on the battery door
SKATE = (13.0, 8.0)

# Materials (g/cm^3) for the mass / centre-of-gravity estimate
DENSITY = {"shell": 1.20 if MOLDED else 1.26,   # PC/ABS | PLA
           "pcb": 1.85, "switch": 1.6, "nimh_aa": 2.86,  # 27 g / 9.4 cm3
           "steel": 7.85, "ptfe": 2.2, "rubber": 1.2, "aluminium": 2.70}
