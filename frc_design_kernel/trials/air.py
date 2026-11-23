"""Air on a free piece: drag against its motion, and the lift its spin gives it (the Magnus force).

A trial that states `"air": {"densityKgM3": ...}` turns air on. The piece then needs its own numbers, in the design
source beside its mass: `dragCoefficient` and `frontalAreaM2`, and for lift `liftSlope` (the lift coefficient per unit
of spin ratio) with an optional `liftMax` (its cap). Each is a physical input with its source, so ranges, coverage and
sensitivity reach it.

    drag = 1/2 rho Cd A |v| v, against the motion through still air
    lift = 1/2 rho A Cl |v|^2, along spin x velocity, with Cl = liftSlope * (spin * radius / |v|), at most liftMax

Spin does not decay in the air, and the piece's attitude does not change its area. Both engines use these numbers.
Nothing here imports MuJoCo.
"""
import math

from ..errors import DesignError

FIELDS = ("dragCoefficient", "frontalAreaM2", "liftSlope", "liftMax")


def params(case, use, radius_m, where):
    """What the air law needs for one piece of a case (numbers only), or None when the trial has no air."""
    if "air" not in case:
        return None
    piece = case["pieces"][use]
    for field in ("dragCoefficient", "frontalAreaM2"):
        if field not in piece:
            raise DesignError(where, f'the trial has air, but the piece "{use}" has no {field}', f"Give the piece a {field} with its source")
    return {"rho": case["air"]["densityKgM3"], "cd": piece["dragCoefficient"], "area": piece["frontalAreaM2"],
            "slope": piece.get("liftSlope", 0.0), "most": piece.get("liftMax"), "radius": radius_m}


def force(p, v, omega):
    """(force on the piece, drag size, lift size), in newtons, for velocity v (m/s) and spin omega (rad/s), both 3D."""
    speed = math.sqrt(sum(c * c for c in v))
    if p is None or speed == 0.0:
        return (0.0, 0.0, 0.0), 0.0, 0.0
    q = 0.5 * p["rho"] * p["area"]
    drag = [-q * p["cd"] * speed * c for c in v]
    turn = (omega[1] * v[2] - omega[2] * v[1], omega[2] * v[0] - omega[0] * v[2], omega[0] * v[1] - omega[1] * v[0])
    across = math.sqrt(sum(c * c for c in turn))
    spin = math.sqrt(sum(c * c for c in omega))
    lift = [0.0, 0.0, 0.0]
    if p["slope"] and across > 0.0:
        cl = p["slope"] * spin * p["radius"] / speed
        if p["most"] is not None:
            cl = min(cl, p["most"])
        lift = [q * cl * speed * speed * c / across for c in turn]
    total = tuple(a + b for a, b in zip(drag, lift))
    return total, q * p["cd"] * speed * speed, math.sqrt(sum(c * c for c in lift))


def in_plane(p, vx, vz, w):
    """(fx, fz, drag size, lift size) for a planar piece: spin w is counter-clockwise in the plane's two axes."""
    (fx, fz, _), drag, lift = force(p, (vx, vz, 0.0), (0.0, 0.0, w))
    return fx, fz, drag, lift
