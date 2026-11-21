"""Fulcrum mouse assembly (work in progress)."""
import form
import layout
import top

NAME = "fulcrum"


def build():
    parts = dict(top.build_top())
    parts["base"] = form.base_shell_raw()
    parts.update(layout.dummies())
    return parts


COLORS = {"top_shell": "#c9d1dc", "base": "#4a5566", "btn_left": "#e6ebf2",
          "btn_right": "#e6ebf2"}

# switches sit on their boards, battery between its contacts
ALLOWED_CONTACT = [
    ("pcb_main", "sensor"), ("pcb_main", "sw_left"), ("pcb_main", "sw_right"),
    ("pcb_main", "power_switch"), ("pcb_main", "conn_button"), ("pcb_main", "usb_c"),
    ("pcb_top", "sw_dpi_up"), ("pcb_top", "sw_dpi_down"), ("pcb_top", "sw_mode"),
    ("pcb_side_l", "sw_side_l1"), ("pcb_side_l", "sw_side_l2"),
    ("pcb_side_r", "sw_side_r1"), ("pcb_side_r", "sw_side_r2"),
    ("battery", "bat_spring"), ("battery", "bat_plate"),
    ("top_shell", "base"),
]
