"""Contact between a round piece and a surface piece, in the plane. Pure arithmetic, SI units.

A surface piece is a straight segment or an arc, treated as a thin curve the piece may touch from either side. The
normal force is a spring and damper, never pulling. Friction follows one of two laws:

    smooth   Coulomb friction eased near zero slip. Simple, but a piece on a slope always creeps a little.
    stick    a tangential spring capped at friction * normal force, with memory. A clamped or resting piece holds still.
"""
import math

TWO_PI = 2 * math.pi


def segment(a, b):
    """A runtime segment from a to b (metres). The surface runs from a toward b."""
    length = math.dist(a, b)
    return ("s", a[0], a[1], b[0], b[1], (b[0] - a[0]) / length, (b[1] - a[1]) / length)


def arc(centre, radius, start, sweep):
    """A runtime arc (metres, radians). The surface runs the way the sweep turns: counter-clockwise when positive."""
    return ("a", centre[0], centre[1], radius, start, sweep)


def nearest(prim, px, pz):
    """(closest point x, z, surface run direction x, z) on a surface piece to the point (px, pz)."""
    if prim[0] == "s":
        _, ax, az, bx, bz, tx, tz = prim
        dx, dz = bx - ax, bz - az
        along = ((px - ax) * dx + (pz - az) * dz) / (dx * dx + dz * dz)
        along = 0.0 if along < 0 else 1.0 if along > 1 else along
        return ax + along * dx, az + along * dz, tx, tz
    _, cx, cz, radius, start, sweep = prim
    angle = math.atan2(pz - cz, px - cx)
    turn = (angle - start) % TWO_PI if sweep > 0 else (start - angle) % TWO_PI
    span = abs(sweep)
    if turn > span + 1e-12:         # outside the arc: the nearer end
        angle = start + sweep if turn - span < TWO_PI - turn else start
    way = 1.0 if sweep > 0 else -1.0
    return cx + radius * math.cos(angle), cz + radius * math.sin(angle), -way * math.sin(angle), way * math.cos(angle)


def damping(stiffness, mass, restitution=None, ratio=None):
    """The damper for a contact spring, from a bounce (restitution, 0 to 1) or a damping ratio."""
    if ratio is None:
        e = min(max(restitution, 1e-3), 0.999)
        ratio = -math.log(e) / math.sqrt(math.pi ** 2 + math.log(e) ** 2)
    return 2 * ratio * math.sqrt(stiffness * mass)


def push(key, memory, state, radius, q, mat, surface_velocity, dt, arm_on_piece):
    """The force of one contact on the piece, or None when not touching.

    Returns (fx, fz, torque, normal force, friction force, depth, tangent x, tangent z); the friction force acts
    along the tangent.

    state is (x, z, vx, vz, spin). q is the closest surface point. memory holds the stick law's spring stretch per
    contact key; it is dropped when the contact opens. arm_on_piece puts the contact point on the undeformed rim of
    the piece (one radius from its centre) instead of on the surface.
    """
    x, z, vx, vz, w = state
    dx, dz = x - q[0], z - q[1]
    gap = math.hypot(dx, dz)
    depth = radius - gap
    if depth <= 0 or gap == 0:
        memory.pop(key, None)
        return None
    nx, nz = dx / gap, dz / gap
    rx, rz = (-nx * radius, -nz * radius) if arm_on_piece else (q[0] - x, q[1] - z)
    relx, relz = vx - w * rz - surface_velocity[0], vz + w * rx - surface_velocity[1]
    vn = relx * nx + relz * nz
    fn = mat["k"] * depth - mat["c"] * vn
    if fn <= 0:         # overlapping but parting fast enough that the spring and damper cancel: touching, no force
        memory.pop(key, None)
        return 0.0, 0.0, 0.0, 0.0, 0.0, depth, -nz, nx
    tx, tz = -nz, nx
    vt = relx * tx + relz * tz
    if mat["law"] == "smooth":
        ft = -mat["mu"] * fn * vt / math.sqrt(vt * vt + mat["eps"] ** 2)
    else:
        stretch = memory.get(key, 0.0) + vt * dt
        ft = -mat["kt"] * stretch - mat["ct"] * vt
        cap = mat["mu"] * fn
        if abs(ft) > cap:
            ft = math.copysign(cap, ft)
            stretch = -ft / mat["kt"]
        memory[key] = stretch
    fx, fz = fn * nx + ft * tx, fn * nz + ft * tz
    return fx, fz, rx * fz - rz * fx, fn, ft, depth, tx, tz
