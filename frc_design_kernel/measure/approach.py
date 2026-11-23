"""Questions about one pair or one moving set along a motion: does a pair come together, is a seat bearing, is a set withdrawn."""
from ..errors import DesignError
from ..kernel import props
from ..kernel.between import bearing_area, common, distance
from . import scene as scenes
from .pairs import box_around, box_gap
from .search import DEFAULT_DEPTH, search


def named(scene, *names):
    for name in names:
        if name not in scene.names:
            raise DesignError("", f'the solid "{name}" is not present', f"Present solids: {', '.join(scene.names)}")


def reach(assembly, motion, pair, within, window=(0.0, 1.0), absent=(), depth=DEFAULT_DEPTH):
    """Whether two solids come within a distance of each other somewhere in a window of a motion.

    "reached" with its gap and t is a witness. When not reached, "proven" says the search settled the whole window
    (and "lowerBoundMm" is the closest they can come), or hit its depth limit first.
    """
    scene = scenes.for_motion(assembly, motion, absent)
    a, b = pair
    named(scene, a, b)
    if not (0 <= window[0] <= window[1] <= 1):
        raise DesignError("", "the window must be two stroke fractions in order, from 0 to 1", "For example [0.9, 1.0]")
    speed = scene.rates[a] + scene.rates[b]
    found = search(lambda t: distance(scene.at(a, t), scene.at(b, t)), speed, within, depth, tuple(window), hit=lambda t, gap: gap <= within)
    t, gap = found["hit"] or found["lowest"]
    settled = found["hit"] is not None or found["unresolved"] is None
    return {"motion": motion, "pair": [a, b], "withinMm": float(within), "window": list(window), "reached": found["hit"] is not None,
            "gapMm": gap, "t": t, "proven": settled, "samples": found["samples"],
            "lowerBoundMm": min(found["floor"], gap) if settled and not found["hit"] else None}


def seat(assembly, motion, pair, t=1.0, absent=()):
    """How two solids sit on each other at a stroke fraction: flat area in contact and any shared volume."""
    scene = scenes.for_motion(assembly, motion, absent)
    a, b = pair
    named(scene, a, b)
    first, second = scene.at(a, t), scene.at(b, t)
    return {"motion": motion, "pair": [a, b], "t": t, "bearingAreaMm2": bearing_area(first, second), "overlapMm3": common(first, second)}


def withdrawn(assembly, motion, absent=()):
    """At the end of a motion, how far the box around each moved solid is from the box around everything that stayed still."""
    scene = scenes.for_motion(assembly, motion, absent)
    moving = [name for name in scene.names if not scene.still(name)]
    still = [scene.boxes[name] for name in scene.names if scene.still(name)]
    if not moving or not still:
        raise DesignError(f'motions "{motion}"', "needs at least one solid that moves and one that stays", "Check the motion's moves")
    rest = box_around(still)
    gaps = {name: box_gap(props.bounds(scene.at(name, 1.0)), rest) for name in moving}
    return {"motion": motion, "moving": moving, "restBoundsMm": rest, "boxGapMm": gaps, "smallestBoxGapMm": min(gaps.values())}
