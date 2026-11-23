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
    {"id": "listed-pieces", "text": "The trial's piece and any others the trial lists are the only free bodies."},
    {"id": "convex-shapes", "text": "A tube, a box with boxes cut out, a prism and a pie slice are run as their true convex pieces. Any other hollow, cut or imported solid is used as its convex hull; the record lists which, and says when the piece touched one."},
    {"id": "own-contact-law", "text": "MuJoCo finds where shapes overlap and moves the bodies. The forces there are this library's spring, damper and friction law, the same as the planar engine's."},
    {"id": "shared-spring", "text": "Where a piece touches one surface at several points, the surface's spring is shared among the points by depth."},
    {"id": "driven-not-driving", "text": "A moved group follows its motion and a driven surface runs at its drive's speed; contact loads the drive's motor model but cannot push a mechanism off its motion."},
    {"id": "driven-surface-still", "text": "A roller, wheel or belt that a drive turns is a still shape whose surface runs at the drive's speed across the turn's axis."},
    {"id": "teleported-paths", "text": "A group whose motion is not one hinge or one slider is carried along its path without its speed being felt in contact."},
    {"id": "flap-as-drawn", "text": "A flap is its drawn solid on a sprung hinge about the plane's normal; its stops do not bounce."},
    {"id": "ring-of-capsules", "text": "A ring piece is a closed chain of straight round segments; the record says how many."},
    {"id": "pieces-alike", "text": "With more than one piece, piece against piece takes the one material the trial names; only the trial's own piece is reported contact by contact."},
    {"id": "not-yet-run", "text": "Custom forces are not run by this engine yet; a trial that has them is refused."},
    {"id": "no-air", "text": "No air drag or lift."},
    {"id": "fixed-step", "text": "Time moves in fixed steps; the half-step repeat is the check on the step."},
]
STANDING = {"planar": PLANAR, "mujoco": MUJOCO}
AIR = {"id": "air-law", "text": "Air drags the piece by 1/2 rho Cd A v^2 against its motion through still air, and its spin lifts it by the Magnus "
                               "force with a lift coefficient proportional to the spin ratio, up to its cap. Spin does not decay; attitude does not change the area."}


def stated(trial):
    """(the author's assumptions, the engine's standing ones) for a trial. A trial with air has the air law in place of no air."""
    standing = [dict(AIR) if row["id"] == "no-air" and trial.get("air") else dict(row) for row in STANDING[trial.get("engine", "planar")]]
    return [dict(row) for row in trial.get("assumes", [])], standing
