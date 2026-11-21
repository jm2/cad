"""Mass and centre-of-gravity estimate for the assembled mouse.

Plastic / metal parts use their modelled volume x density; bought-in parts
whose envelope is not their real volume use a typical catalogue mass.
"""
from __future__ import annotations

import params as P
from tools.model_io import mass_props

FIXED_G = {   # typical masses of bought-in parts (g)
    "battery": 27.0,          # NiMH AA (Eneloop ~27 g); weight slug ~22 g
    "receiver": 1.8, "sensor": 1.6, "usb_c": 0.7, "encoder": 0.3,
    "bat_spring": 0.5, "bat_plate": 0.3, "power_switch": 0.4,
    "sw_left": 0.6, "sw_right": 0.6,
}
TACT_G = 0.25


def density(name: str) -> float:
    D = P.DENSITY
    if name.startswith(("screw", "pin_", "axle")):
        return D["steel"]
    if name.startswith("skate"):
        return D["ptfe"]
    if name == "wheel_tyre":
        return D["rubber"]
    if name.startswith("pcb"):
        return D["pcb"]
    return D["shell"]


def estimate(parts: dict) -> dict:
    total, mx, my, mz = 0.0, 0.0, 0.0, 0.0
    rows = []
    for n, s in parts.items():
        v, (x, y, z) = mass_props(s)
        if n in FIXED_G:
            m = FIXED_G[n]
        elif n.startswith("sw_"):
            m = TACT_G
        else:
            m = v * density(n) / 1000.0
        rows.append((n, m))
        total += m
        mx, my, mz = mx + m * x, my + m * y, mz + m * z
    return {"mass_g": total, "cog": (mx / total, my / total, mz / total),
            "parts": sorted(rows, key=lambda r: -r[1])}


if __name__ == "__main__":
    import model
    r = estimate(model.build())
    print(f"total {r['mass_g']:.1f} g   CoG ({r['cog'][0]:.2f}, {r['cog'][1]:.2f}, {r['cog'][2]:.2f})"
          f"   sensor at y={P.SENSOR_XY[1]}")
    for n, m in r["parts"][:14]:
        print(f"  {n:16s} {m:6.2f} g")
