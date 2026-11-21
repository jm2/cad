"""Fulcrum: ambidextrous wired/wireless mouse, full assembly.

FULCRUM_VARIANT=molded|fdm selects the manufacturing intent (see params.py).
Parts are cached as BREP under out/cache/ keyed on the source hash.
"""
import base
import cache
import layout
import params as P
import top
import wheel

NAME = f"fulcrum_{P.VARIANT}"


def _build():
    parts = {}
    parts.update(top.build_top())
    parts.update(base.build_base())
    parts.update(wheel.build_wheel())
    parts.update(layout.dummies())
    return parts


def build():
    return cache.cached(_build)


GREY, DARK, LIGHT = "#c9d1dc", "#3c4552", "#e9edf2"
COLORS = {"top_shell": GREY, "base": DARK, "door": "#4d5868", "spine": "#262b33",
          "btn_left": LIGHT, "btn_right": LIGHT, "wheel": "#a7adb5", "yoke": "#6c7a89", "axle": "#b8bec6"}
for _n in ("btn_mode", "btn_dpi_up", "btn_dpi_down"):
    COLORS[_n] = "#f0a04b"
for _s in "lr":
    for _i in "12":
        COLORS[f"btn_side_{_s}{_i}"] = LIGHT
for _i in range(1, 8):
    COLORS[f"skate_{_i}"] = "#f4f1ea"

# exploded view offsets (mm)
EXPLODE = {"top_shell": (0, 0, 40), "spine": (0, 0, 58), "btn_left": (-12, 0, 55), "btn_right": (12, 0, 55),
           "btn_mode": (0, 0, 70), "btn_dpi_up": (0, 0, 70), "btn_dpi_down": (0, 0, 70),
           "btn_side_l1": (-30, 0, 40), "btn_side_l2": (-30, 0, 40),
           "btn_side_r1": (30, 0, 40), "btn_side_r2": (30, 0, 40),
           "wheel": (0, 0, 80), "axle": (0, 0, 80),
           "enc_magnet": (0, 0, 80), "yoke": (0, 0, 64), "encoder": (0, 0, 64),
           "door": (0, 0, -25), "battery": (0, 0, -12), "receiver": (0, 0, -20)}
for _i in range(1, 8):
    EXPLODE[f"skate_{_i}"] = (0, 0, -35)
for _i in range(1, 5):
    EXPLODE[f"screw_{_i}"] = (0, 0, -45)

# pairs that touch or overlap by design
ALLOWED_CONTACT = [
    ("top_shell", "base"),
    ("pcb_main", "sensor"), ("pcb_main", "sw_left"), ("pcb_main", "sw_right"),
    ("pcb_main", "power_switch"), ("pcb_main", "conn_button"), ("pcb_main", "usb_c"),
    ("pcb_main", "sw_click"), ("pcb_main", "sw_tilt_l"), ("pcb_main", "sw_tilt_r"),
    ("pcb_top", "sw_dpi_up"), ("pcb_top", "sw_dpi_down"), ("pcb_top", "sw_mode"),
    ("pcb_side_l", "sw_side_l1"), ("pcb_side_l", "sw_side_l2"),
    ("pcb_side_r", "sw_side_r1"), ("pcb_side_r", "sw_side_r2"),
    ("battery", "bat_spring"), ("battery", "bat_plate"),
    ("base", "bat_spring"), ("base", "bat_plate"),
    ("base", "pcb_main"), ("base", "pcb_side_l"), ("base", "pcb_side_r"), ("base", "pcb_top"),
    ("wheel", "axle"), ("yoke", "encoder"),
    ("wheel", "enc_magnet"), ("enc_magnet", "axle"),
    ("topb_post_l", "pcb_main"), ("topb_post_r", "pcb_main"),
    ("topb_post_l", "pcb_top"), ("topb_post_r", "pcb_top"),
    ("door", "skate_7"),
    ("spine", "pcb_main"),      # front support pillar stands on the board
    ("spine", "base"),          # spine's nose end sits on the base rim
]
ALLOWED_CONTACT += [("base", f"skate_{i}") for i in range(1, 7)]
ALLOWED_CONTACT += [("top_shell", f"screw_{i}") for i in range(1, 5)]
if P.FDM:
    ALLOWED_CONTACT += [("wheel", f"wheel_dowel_{i}") for i in range(1, 7)]
    ALLOWED_CONTACT += [("top_shell", "pin_left"), ("top_shell", "pin_right"),
                        ("btn_left", "pin_left"), ("btn_right", "pin_right")]

# moving parts that must keep a running clearance
MIN_CLEARANCE = {("wheel", "top_shell"): 0.5, ("wheel", "yoke"): 0.4,
                 ("enc_magnet", "encoder"): 0.4,
                 ("enc_magnet", "top_shell"): 0.5,
                 ("btn_left", "top_shell"): 0.25, ("btn_right", "top_shell"): 0.25,
                 ("btn_left", "base"): 0.5, ("btn_right", "base"): 0.5}
for _n in ("btn_mode", "btn_dpi_up", "btn_dpi_down"):
    MIN_CLEARANCE[(_n, "spine")] = 0.2          # top buttons run in the spine
for _n in ("btn_side_l1", "btn_side_l2", "btn_side_r1", "btn_side_r2"):
    MIN_CLEARANCE[(_n, "top_shell")] = 0.2
MIN_CLEARANCE.update({("spine", "top_shell"): 0.1, ("wheel", "spine"): 0.5, ("enc_magnet", "spine"): 0.5,
                      ("btn_left", "spine"): 0.15, ("btn_right", "spine"): 0.15})

# FDM print orientations (deg about X, Y, Z): shells and door as moulded
# (flat underside / parting plane on the bed), side buttons pad-up
PRINT_ORIENT = {"btn_side_r1": (0, -90, 0), "btn_side_r2": (0, -90, 0),
                "btn_side_l1": (0, 90, 0), "btn_side_l2": (0, 90, 0)}
PULL = {}   # default +Z for every part
