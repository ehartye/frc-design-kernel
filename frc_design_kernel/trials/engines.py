"""The engines a trial can name. Both read the same trial definition and give runs of the same shape.

    planar   the default: one round piece in a section plane, in plain Python
    mujoco   3D rigid bodies through MuJoCo, an optional extra that is only imported when a trial names it
"""
from ..version import generator
from ..workers import silent
from . import planar, scene as planar_scene

NAMES = ("planar", "mujoco")


def build(assembly, name, case, handed=None):
    """The runnable scene for a trial's case, for the engine the case names."""
    if case.get("engine", "planar") == "planar":
        return planar_scene.build(assembly, name, case, handed)
    from . import mujoco_run, mujoco_scene
    scene = mujoco_scene.build(assembly, name, case, handed)
    planar_scene.check_names(case, scene, f'trials "{name}"', mujoco_run.signal_names(scene))
    return scene


def run(scene, step=None, forces=(), tick=silent):
    """One run of a scene on the engine that built it. tick hears the number of steps done, now and then."""
    if scene.get("engine") == "mujoco":
        from . import mujoco_run
        return mujoco_run.run(scene, step, forces, tick)
    return planar.run(scene, step, forces, tick)


def stamp(name):
    """{"name", "version"} of an engine, for the record."""
    if name == "mujoco":
        from . import mujoco_run
        return {"name": "mujoco", "version": mujoco_run.version()}
    made = generator()
    return {"name": "planar", "version": made["version"], "commit": made["commit"]}
