"""A drive's joint: the one movement it gives a group, counted as a joint value from the group as drawn.

    {"group": g, "kind": "rotation", "axis": [x, y, z], "originMm": [x, y, z], "travel": [low, high]}     degrees
    {"group": g, "kind": "slide", "axis": [x, y, z], "perOutputTurn": mm, "travel": [low, high]}         mm

A rotation joint at value v turns its group v degrees about the line through originMm along axis (right-hand rule);
a slide joint at value v moves it v mm along axis. Value 0 is the group as drawn. The joint is drawn in the group's
own coordinates, before its carrier moves it, so it rides on the carrier like any pose of the group.
"""
import math

from . import matrix as mx

TOLERANCE_MM = 1e-3     # how far, at 1 m, a placement may be from the joint and still be read as on it


def placement(joint, value):
    """The group's own placement at a joint value."""
    if joint["kind"] == "rotation":
        return mx.rotation(joint["originMm"], joint["axis"], value)
    return mx.translation(mx.scale(mx.unit(joint["axis"]), value))


def operation(joint, change):
    """A motion operation that changes the joint value by change over the stroke."""
    if joint["kind"] == "rotation":
        return {"kind": "rotation", "originMm": list(joint["originMm"]), "axis": list(joint["axis"]), "travelDeg": change}
    return {"kind": "translation", "travelMm": list(mx.scale(mx.unit(joint["axis"]), change))}


def turn_angle(joint, placed):
    """The angle in (-180, 180] that the placement turns about the joint's axis."""
    u = mx.unit(joint["axis"])
    sine = mx.dot(u, ((placed[9] - placed[6]) / 2, (placed[2] - placed[8]) / 2, (placed[4] - placed[1]) / 2))
    cosine = (placed[0] + placed[5] + placed[10] - 1) / 2
    return math.degrees(math.atan2(sine, cosine))


def nearest_turn(angle, travel):
    """Of angle and its whole turns either way, the one inside travel nearest zero, or angle when none is inside."""
    low, high = travel
    inside = [angle + 360 * k for k in range(math.ceil((low - angle) / 360), math.floor((high - angle) / 360) + 1)]
    return min(inside, key=abs) if inside else angle


def value_of(joint, placed):
    """The joint value that gives a group's own placement, or None when the joint cannot give that placement."""
    if joint["kind"] == "rotation":
        found = nearest_turn(turn_angle(joint, placed), joint["travel"])
    else:
        found = mx.dot(mx.unit(joint["axis"]), (placed[3], placed[7], placed[11]))
    return found if mx.gap(placed, placement(joint, found)) <= TOLERANCE_MM else None


def motor_turns(joint, gear, change):
    """Turns of the motor for a change of joint value: gear is motor turns per turn of the gear's output."""
    output = change / 360 if joint["kind"] == "rotation" else change / joint["perOutputTurn"]
    return output * gear
