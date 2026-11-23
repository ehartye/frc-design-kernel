"""What an engine cannot see. Every trial record repeats these beside its outcome.

Each assumption has a stable id and plain words. The ids let a later tool turn a trial's list into the list of
things a fuller engine should test.
"""

PLANAR = [
    {"id": "in-plane", "text": "The piece stays in the section plane: no sideways drift, yaw or tilt, and nothing touches it off the plane."},
    {"id": "single-piece", "text": "One free piece. No other piece is present or touches it."},
    {"id": "round-piece", "text": "The piece is round in the section and stays round; it is squashed only through the contact spring."},
    {"id": "rigid-surfaces", "text": "Surfaces do not bend or shift. All give is in the contact spring of each material."},
    {"id": "spring-contact", "text": "Contact is a spring and damper with friction, not a measured force curve."},
    {"id": "section-outline", "text": "Each solid acts through its outline in the section plane, the same along the whole width of the piece."},
    {"id": "no-air", "text": "No air drag or lift, unless a custom force law adds one."},
    {"id": "fixed-step", "text": "Time moves in fixed steps; the half-step repeat is the check on the step."},
]
MUJOCO = [
    {"id": "rigid-bodies", "text": "Every body is rigid. All give is in the contact between the piece and a surface."},
    {"id": "single-piece", "text": "One free piece. No other piece is present or touches it."},
    {"id": "convex-shapes", "text": "A tube, a box with boxes cut out, a prism and a pie slice are run as their true convex pieces. Any other hollow, cut or imported solid is used as its convex hull; the record lists which, and says when the piece touched one."},
    {"id": "mapped-contact", "text": "Each material's spring and damper are handed to the engine's own soft contact for the piece's mass; the engine's friction is a hard limit, not a spring."},
    {"id": "no-resting-depth", "text": "Under a steady load the engine holds the piece at almost no depth: contact forces compare with the planar engine, resting depths do not."},
    {"id": "fixed-surfaces", "text": "Surfaces stand still. Drives, flaps, loads and movers are not run by this engine yet."},
    {"id": "no-air", "text": "No air drag or lift."},
    {"id": "fixed-step", "text": "Time moves in fixed steps; the half-step repeat is the check on the step."},
]
STANDING = {"planar": PLANAR, "mujoco": MUJOCO}


def stated(trial):
    """(the author's assumptions, the engine's standing ones) for a trial."""
    return [dict(row) for row in trial.get("assumes", [])], [dict(row) for row in STANDING[trial.get("engine", "planar")]]
