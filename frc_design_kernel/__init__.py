"""frc-design-kernel: build, measure and try a preliminary robot design from one data file.

    import frc_design_kernel as kernel
    assembly = kernel.build(kernel.load("design.json"))
    kernel.export(assembly, "out")

load needs only the standard library. build and export need the CAD kernel, which is imported when they are called.
"""
from .errors import DesignError
from .source.load import Design, load
from .version import generator

__all__ = ["Design", "DesignError", "build", "export", "generator", "load"]


def build(design):
    """Build every solid of a loaded design into an Assembly."""
    from .builder.assembly import build as run
    return run(design)


def export(assembly, out, pose=None):
    """Write design.step, fixtures.step and manifest.json into the folder out. Returns the manifest."""
    from .builder.export import export as run
    return run(assembly, out, pose)
