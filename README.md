# frc-design-kernel

> **Current period: settling.** There is no compatibility promise yet. This library may change in ways that break the
> projects that use it. See [The two periods](#the-two-periods).

A small Python library for the first stage of robot design: the **blockout**. A blockout is the whole robot drawn as
about 30 to 80 simple named solids, the ways its parts move, what they weigh, and a few physics trials.

The library does three things and nothing else:

| Layer | What it does | State |
|---|---|---|
| **Build** | Turns one design source (a JSON file, or a top file and one file per subsystem) into named solids, poses, motions, a STEP file and a manifest. | Here now |
| **Measure** | Clearance along a motion with a proof that nothing was missed, what touches what, mass and centre of mass. | Here now |
| **Try** | Physics trials described as data: one round piece in a plane, with a control, brackets and a half-step repeat. | Here now (planar) |

It builds and measures. It does not judge. Clearance guidelines, pass or fail criteria, review pages and publishing
belong to the tools that use it. The full design is in [DESIGN.md](DESIGN.md).

## The two periods

**Settling (now).** The first three projects that use the library are still finding out what they need from it. Until
they settle, a change here may break any of them, and that is accepted. If your project breaks, fix the design source
or raise the problem. Do not pin an old copy.

**Stable (later).** This period begins when all three first consumer projects have an effective preliminary design
that was built, measured and tried with this library. From then on there are no breaking changes, and every change is
tested against saved outputs and against the consumers' own files. One exception stays: a correction to a wrong
measurement is allowed, and is announced.

## Install

```
pip install git+https://github.com/ehartye/frc-design-kernel
```

Needs Python 3.11 or newer. The only dependency is `cadquery-ocp`, the CAD kernel.

Trials can also be run in 3D by MuJoCo, an optional extra that is only loaded when a trial names it:

```
pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"
```

There are no numbered releases to choose from. **`main` is the release.** What runs on a machine is whatever was last
installed there; run the command again to update. Every file the library writes records the library version and
commit. That record is information for the reader. Nothing checks it or refuses to run because of it.

## A short example

A design source is one JSON file. This one is a base with a post and an arm that a geared motor swings:

```json
{
  "schema": "frc-design-kernel/design@1",
  "name": "Swing arm",
  "units": {"length": "mm", "mass": "kg"},
  "parameters": {"post_top": 300},
  "groups": {"base": {"role": "structure"}, "arm": {"role": "mechanism", "carriedBy": "base"}},
  "solids": [
    {"name": "base plate", "group": "base", "densityKgM3": 2700,
     "shape": {"kind": "box", "fromMm": [-150, -100, 0], "toMm": [150, 100, 6]}},
    {"name": "post", "group": "base", "massKg": 0.4,
     "shape": {"kind": "tube", "section": "round", "fromMm": [0, 0, 6], "toMm": [0, 0, "=post_top"],
               "outerDiameterMm": 30, "wallMm": 2}},
    {"name": "arm", "group": "arm", "massKg": 0.3,
     "shape": {"kind": "box", "fromMm": [0, -10, "=post_top"], "toMm": [200, 10, "=post_top + 20"]}},
    {"name": "shoulder motor", "group": "base", "massKg": 0.5,
     "shape": {"kind": "cylinder", "fromMm": [0, 20, "=post_top - 40"], "toMm": [0, 70, "=post_top - 40"], "radiusMm": 25}}
  ],
  "motors": {"small motor": {"ktNmPerA": {"value": 0.018, "assumed": [0.016, 0.02]},
                             "ohm": {"value": 0.1, "assumed": [0.08, 0.12]},
                             "keVsPerRad": {"value": 0.018, "assumed": [0.016, 0.02]}}},
  "drives": {"shoulder": {"motor": "small motor", "motorSolid": "shoulder motor", "gear": 60,
                          "joint": {"group": "arm", "kind": "rotation", "axis": [0, -1, 0],
                                    "originMm": [0, 0, "=post_top"], "travel": [0, 100]}}},
  "poses": {
    "down": {},
    "up": {"arm": [{"kind": "rotation", "originMm": [0, 0, "=post_top"], "axis": [0, -1, 0], "travelDeg": 90}]}
  },
  "motions": {"raise": {"from": "down", "to": "up", "drive": {"shoulder": {"to": 90}},
                        "durationS": {"value": 0.6, "assumed": [0.4, 0.9]}}}
}
```

The motor is a solid like any other, so it is weighed and has a place. The motion is a motor command: the shoulder
joint goes to 90 degrees, and the library works out where the arm is at every point of the stroke. A motion that no
motor makes says what does, with `"by": "hand"`, `"spring"`, `"gravity"` or `"piece"`, and is written as moves.

Check it, then build it:

```
python -m frc_design_kernel validate swing-arm.json
python -m frc_design_kernel build swing-arm.json --out out
```

`build` writes `out/design.step` (every solid, by name) and `out/manifest.json` (each solid's volume, bounding box,
mass and group, plus the poses, the motions and the library version). The same source always gives the same manifest.

Then measure it:

```
python -m frc_design_kernel measure swing-arm.json --out out
```

`measure` writes one file per measuring job into `out/measurements/`, each the moment its job finishes: for every
motion, how close each pair of solids comes over the whole stroke; for every pose, what touches what, what is not
connected to the base, and the mass with its centre; for every motion its motors drive, the torque, current and
motor voltage of each drive and the battery's voltage under them all. The closeness is proven, not sampled at fixed steps: the
library knows how fast each solid can move, so it knows what cannot happen between two samples. A stopped run keeps
the jobs it finished, and `measure --carry` measures only the rest.

Trials are data in the same file. Run them with:

```
python -m frc_design_kernel try swing-arm.json --out out
```

`try` first prints what the campaign may cost (runs, steps, rough time), then writes `out/trials.json`. Every trial
states what it assumes, every physical input says whether it was measured or assumed (with a range), and a trial is
only reported as passed when a control was rejected, a repeat at half the step agrees, and the outcome holds across
every assumed range. A best guess with a range is a complete input. Where the outcome changes inside a range, the
campaign asks whether an adjustment the robot is built with (a slot, a spring, a setpoint) covers it, and reports the
settings that pass at each end. See [DESIGN.md](DESIGN.md) section 13.

After a change to the source, ask which records it touched:

```
python -m frc_design_kernel status swing-arm.json out
```

`status` prints, per record, `current` or `stale` and what changed. `measure --motion NAME` and `try --trial NAME`
run again only the part you name.

To measure game pieces on their own, with no design source:

```
python -m frc_design_kernel piece-geometry pieces.json --out geometry.json
```

`pieces.json` holds a `pieces` block written as in a design source. For each piece, `geometry.json` gives its bounds,
volume, symmetry, a convex hull that holds the whole piece, and any hole straight through it. See
[DESIGN.md](DESIGN.md) section 12.6c.

The same thing from Python:

```python
import frc_design_kernel as kernel

assembly = kernel.build(kernel.load("swing-arm.json"))
halfway = assembly.at_motion("raise", 0.5)      # {solid name: placed shape}
kernel.export(assembly, "out")

from frc_design_kernel.measure import clearance
result = clearance.along(assembly, "raise", min_gap=1.0)    # plain data: rows per pair, counts, closest
```

A fuller example, with an imported part and a custom shape, is in [examples/lifter](examples/lifter).

## The size rule

The library stays lean. No module is longer than **600 lines** and no function is longer than **120 lines**. No
module imports in a circle. Tests fail the build when any of these is broken. Aim well below the limits: one small
module for one job.

## For contributors

Read [AGENTS.md](AGENTS.md). Run the tests with:

```
python -m unittest discover -s tests -t .
```

## License

MIT. See [LICENSE](LICENSE).
