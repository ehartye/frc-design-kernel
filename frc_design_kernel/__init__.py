"""frc-design-kernel: build, measure and try a preliminary robot design from one data file.

    import frc_design_kernel as kernel
    assembly = kernel.build(kernel.load("design.json"))
    kernel.export(assembly, "out")

load needs only the standard library. build and export need the CAD kernel, which is imported when they are called.
"""
from .errors import DesignError
from .source.load import Design, load
from .version import generator

__all__ = ["Design", "DesignError", "build", "export", "generator", "load", "placements", "sampled"]


def build(design):
    """Build every solid of a loaded design into an Assembly."""
    from .builder.assembly import build as run
    return run(design)


def export(assembly, out, pose=None):
    """Write design.step, fixtures.step and manifest.json into the folder out. Returns the manifest."""
    from .builder.export import export as run
    return run(assembly, out, pose)


def sampled(design, motion, steps):
    """A motion as steps + 1 still placements written with translation and rotation only. Needs no CAD kernel."""
    from .builder.placement import sampled as run
    return run(design.data, motion, steps)


def placements(design, pose=None, motion=None, t=0.0):
    """Where every group is, as numbers: {group: 12 numbers (three rows of rotation x 3, shift)}. Needs no CAD kernel.

    With motion, the placement at stroke fraction t of that motion; otherwise at the named pose (None is as drawn).
    Applying a group's transform to its solids as drawn puts them where the pose or motion has them.
    """
    from .builder import placement
    return placement.at_motion(design.data, motion, t) if motion is not None else placement.at_pose(design.data, pose)
