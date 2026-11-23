# frc-design-kernel

> **Current period: settling.** There is no compatibility promise yet. This library may change in ways that break the
> projects that use it. See [The two periods](#the-two-periods).

A small Python library for the first stage of robot design: the **blockout**. A blockout is the whole robot drawn as
about 30 to 80 simple named solids, the ways its parts move, what they weigh, and a few physics trials.

The library does three things and nothing else:

| Layer | What it does | State |
|---|---|---|
| **Build** | Turns one design source file (JSON) into named solids, poses, motions, a STEP file and a manifest. | Here now |
| **Measure** | Clearance along a motion with a proof that nothing was missed, what touches what, mass and centre of mass. | Here now |
| **Try** | Physics trials described as data. | Empty slot, planned |

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

There are no numbered releases to choose from. **`main` is the release.** What runs on a machine is whatever was last
installed there; run the command again to update. Every file the library writes records the library version and
commit. That record is information for the reader. Nothing checks it or refuses to run because of it.

## A short example

A design source is one JSON file. This one is a base with a post and a swinging arm:

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
     "shape": {"kind": "box", "fromMm": [0, -10, "=post_top"], "toMm": [200, 10, "=post_top + 20"]}}
  ],
  "poses": {
    "down": {},
    "up": {"arm": [{"kind": "rotation", "originMm": [0, 0, "=post_top"], "axis": [0, -1, 0], "travelDeg": 90}]}
  },
  "motions": {"raise": {"through": ["down", "up"]}}
}
```

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

`measure` writes `out/measurements.json`: for every motion, how close each pair of solids comes over the whole
stroke; for every pose, what touches what, what is not connected to the base, and the mass with its centre. The
closeness is proven, not sampled at fixed steps: the library knows how fast each solid can move, so it knows what
cannot happen between two samples.

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
