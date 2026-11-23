# Design

This document is the plan the code follows. If the code and this document disagree, one of them has a bug.

**Current period: settling.**

## 1. The two periods

The library lives through two periods. They are named so nobody has to guess which rules apply.

### Settling (now)

There is **no compatibility promise**. The library may change in ways that break its first three consumer projects,
and that is accepted. The owner's ruling:

> "we don't implement the no-breaking changes until [the three projects] settle. i'm fine fighting fires between those
> 3. make that clear in the library design."

What this means in practice:

- The design source format, the Python functions and the manifest may all change without a migration path.
- A consumer that breaks fixes its design source, or raises the problem here. It does not pin an old copy.
- Tests in this period protect correctness (a box has the right volume), not sameness (the output never changes).

### Stable (later)

**Trigger:** the stable period begins when all three first consumer projects have an *effective* preliminary design
that was built, measured and tried on this library. The owner declares it; this section is then edited to say so.

From then on:

- No breaking changes to the design source format, the Python functions or the manifest.
- Strict testing: saved "golden" outputs that must not change, and tests that run the consumers' own design sources.
- One exception: a **correction to a wrong measurement** is allowed. It is announced in the change that makes it,
  with the old value, the new value and the reason.

## 2. Scope

The owner's ruling: **build, measure, try — nothing else.**

| Layer | Job | Package | State |
|---|---|---|---|
| Build | Design source to named solids, poses, motions, STEP and manifest | `source/`, `kernel/`, `motion/`, `build/` | Here now |
| Measure | Clearance and interference along a motion, contacts, mass roll-up | `measure/` | Empty slot |
| Try | Physics trials defined as data | `trials/` | Empty slot |

Out of scope, for good: clearance guidelines, receipts, readiness criteria, review pages, publishing and CI policy.
Those belong to tools that judge a design. This library reports numbers; it never says pass or fail.

The library is **season-neutral and self-standing**. It holds no game, season, team or project names, and no paths
from any machine. Its fixtures are invented. It does not import or mention any agent plugin. It is an ordinary
library that a robot project and a tooling plugin can both import.

## 3. Module map

```
frc_design_kernel/
  __init__.py        the public functions: load, build, export
  __main__.py        python -m frc_design_kernel
  cli.py             the build and validate commands
  errors.py          DesignError: where, what is wrong, how to fix it
  version.py         library version and commit, for information

  source/            reading the design source. No CAD kernel needed.
    expressions.py   safe arithmetic for "=..." values
    schema.py        a small JSON Schema checker with plain messages
    design.schema.json
    expand.py        "each" rows and "=..." values turned into plain numbers
    checks.py        cross-references: names exist, no loops, no double mass
    load.py          file to checked, plain design

  motion/            the motion vocabulary. Pure arithmetic, no CAD kernel.
    matrix.py        rigid transforms as 3x4 number tables
    ops.py           translation, rotation, gravity-drop, path at fraction t
    paths.py         straight, arc and smooth curves through points
    screw.py         smooth movement from one pose to the next

  kernel/            thin wrappers over the CAD kernel (OCP). Few lines each.
    shapes.py        box, cylinder, sphere, prism, tube
    booleans.py      union, difference, intersection
    props.py         volume, bounds, validity, solid count
    transform.py     apply a rigid transform to a shape
    step_read.py     STEP file to named solids
    step_write.py    named solids to a STEP file

  build/             the build layer
    shape.py         a shape entry to one solid
    parts.py         solids taken from STEP files by name
    custom.py        the escape hatch: load, call and check a custom shape
    assembly.py      the built design: solids, groups, poses, motions
    placement.py     who is carried by whom; transforms per group
    manifest.py      the manifest
    export.py        write the STEP files and the manifest

  measure/           EMPTY SLOT. Reads an Assembly; writes numbers.
  trials/            EMPTY SLOT. Reads an Assembly and trial data; writes results.
```

**What will go in `measure/`:** the smallest gap between two solids at a pose; the smallest gap and any overlap along
a motion (sampled at fractions `t`, with a stated bound on what the samples can miss); which solids touch; mass
roll-up by group with a centre of mass; the swept outer size of the robot. It takes an `Assembly` and returns plain
data. It never applies a guideline.

**What will go in `trials/`:** a trial described as data (bodies, contacts, drives, a stop condition), a solver, and
a result record. It takes solids and masses from the `Assembly` so a trial and the layout cannot disagree.

**Import direction.** `source` and `motion` import nothing from the rest. `kernel` imports only OCP. `build` imports
`source`, `motion` and `kernel`. `measure` and `trials` will import `build`, `motion` and `kernel`. Nothing imports
upward, and nothing imports in a circle. A test enforces the no-circle rule.

## 4. The design source

One JSON file per design. The schema is `frc_design_kernel/source/design.schema.json`. Units are fixed: millimetres
and kilograms. Angles are degrees. The file says so in `units` so a reader never has to guess.

```json
{
  "schema": "frc-design-kernel/design@1",
  "name": "Lifter",
  "units": {"length": "mm", "mass": "kg"},
  "frame": "Origin on the floor at the base centre. +X forward, +Y left, +Z up.",
  "parameters": {},
  "groups": {},
  "custom": {},
  "solids": [],
  "fixtures": [],
  "mounts": [],
  "poses": {},
  "motions": {}
}
```

### 4.1 Numbers and parameters

Any number may be written as a plain number or as a string that starts with `=`:

```json
"parameters": {"post_top": 300, "arm_z": "=post_top - 20", "rise": "=180 * tan(radians(30))"}
```

- Parameters are read top to bottom. A parameter may use the ones above it.
- An expression may use `+ - * / **`, brackets, parameter names, and `sin cos tan asin acos atan atan2 sqrt abs min
  max radians degrees pi`. Trig works in radians; use `radians(30)` for degrees.
- Nothing else is allowed: no text, no comparisons, no function calls outside that list.

This exists because real blockouts derive most sizes from a few others. Without it every project writes a program
just to do the arithmetic.

### 4.2 Solids

```json
{"name": "post", "group": "base", "shape": {"kind": "box", "fromMm": [0, 0, 0], "toMm": [30, 30, 300]},
 "place": [], "massKg": 0.4, "note": "25 mm square tube allocation"}
```

Each solid has a unique `name`, a `group`, and exactly one of `shape` or `part`. Optional: `place` (a list of motion
operations applied in full, to move the solid after it is made), `massKg` **or** `densityKgM3`, and a `note`.

**Shapes.** Each is a few lines over the CAD kernel.

| `kind` | Fields |
|---|---|
| `box` | `fromMm`, `toMm`: two opposite corners, in any order |
| `cylinder` | `fromMm`, `toMm`: the two end centres; `radiusMm`. Optional `sweepDeg` and `sweepFrom` (a direction) make a pie slice |
| `sphere` | `centerMm`, `radiusMm` |
| `prism` | `plane` (`xy`, `xz` or `yz`), `outlineMm` (a closed 2D outline in that plane), `fromMm` and `toMm` (the two levels along the third axis). A plate is a thin prism |
| `tube` | `section` `round`: `fromMm`, `toMm`, `outerDiameterMm`, `wallMm`. `section` `rectangular`: `fromMm`, `toMm`, `widthMm`, `heightMm`, `wallMm`, optional `up` (the direction `heightMm` is measured in) |
| `union` | `of`: a list of shapes joined into one solid |
| `difference` | `from`: a shape; `cut`: a list of shapes removed from it |
| `intersection` | `of`: a list of shapes; the result is what they share |
| `custom` | `use`: a registered custom shape; `parameters`. See section 6 |

Every shape must come out as **exactly one valid solid with volume**. Two boxes that do not touch are not a union;
the build refuses and names the entry.

**Parts.** A solid taken from a supplier's STEP file, by the solid's name in that file:

```json
{"name": "gearbox", "group": "drive", "part": {"file": "parts/gearbox.step", "solid": "Gearbox housing"},
 "place": [{"kind": "translation", "travelMm": [120, 0, 40]}], "massKg": 1.1}
```

The file path is relative to the design source. The part is placed, never changed: the build checks that its volume
is the same after placement. The manifest records the file and its SHA-256 fingerprint.

**Repeating.** `each` makes one entry into several. This replaces the "for left and right" loops in hand-written
builders:

```json
{"name": "post {side}", "group": "base",
 "each": [{"side": "left", "s": 1}, {"side": "right", "s": -1}],
 "shape": {"kind": "box", "fromMm": [0, "=s * 100", 0], "toMm": [30, "=s * 130", 300]}}
```

Text values fill `{side}` in any text field. Number values may be used in expressions. `each` works on solids,
fixtures and mounts.

### 4.3 Groups

```json
"groups": {
  "base":  {"role": "structure"},
  "stage": {"role": "mechanism", "carriedBy": "base"},
  "hook":  {"role": "mechanism", "carriedBy": "stage", "massKg": 0.6}
}
```

A group is a set of solids that move as one rigid body. `role` is free text for the reader. `carriedBy` names the
group this one rides on: when the carrier moves, this group moves with it. `massKg` on a group is one lump figure for
the whole group; its solids then must not carry their own mass, so nothing is counted twice.

`place` on a group moves every solid in it once, when the design is built. Use it to draw a mechanism in its own
handy coordinates and then put it in the robot frame.

### 4.4 Fixtures

Fixtures are solids that are not part of the robot: field elements, a test stand, a game piece. They take the same
form as solids, usually a `part` from a STEP file. They go in `fixtures`, are written to their own STEP file, and are
left out of the robot's mass. Their group defaults to `fixtures`.

### 4.5 Mounts

```json
"mounts": [{"group": "stage", "member": "stage rail left", "on": "post left", "atMm": [0, 100, 250],
            "note": "Rail runs in two bearing blocks on the post"}]
```

A mount says what a group is attached to, and where. `on` is the name of the solid it attaches to. `member` is
optional and names the solid of the group that makes the joint. Mounts are checked (the names must exist) and passed
to the manifest. The measure layer will use them to ask "does anything actually touch there?"

### 4.6 Poses

```json
"poses": {
  "stowed":  {},
  "raised":  {"stage": [{"kind": "translation", "travelMm": [0, 0, 180]}]}
}
```

A pose is a named placement of the moving groups. Each group lists motion operations, applied in full, starting from
where the solids were drawn. A group not listed stays where it was drawn. A carried group gets its own operations
first and then everything its carrier gets.

### 4.7 Motions

A motion says how groups get from one pose to another. There are two ways to write one.

**Moves:** start at a pose, then apply operations by stroke fraction `t`:

```json
"raise": {"from": "stowed", "to": "raised",
          "moves": {"stage": [{"kind": "translation", "travelMm": [0, 0, 180]}]}}
```

`to` is optional. When it is given, the build checks that the motion really ends at that pose and refuses if not.

**Through:** pass smoothly through a list of poses, as one motion:

```json
"swing": {"through": ["stowed", "half", "raised"]}
```

Between each pair of poses a group turns and slides at an even rate along the one natural path between them (a turn
about a fixed axis plus a slide along that axis). An arm drawn at two angles about its pivot therefore swings about
that pivot. The poses share the stroke evenly.

## 5. The motion vocabulary

Other tools already speak this vocabulary, so it is carried over unchanged. A move is a list of operations. They are
applied in order. Each is evaluated at a stroke fraction `t` from 0 to 1. A start pose is a list of the same
operations applied in full (`t` = 1).

| Operation | Meaning at fraction `t` |
|---|---|
| `{"kind": "translation", "travelMm": [x, y, z]}` | Slide by `t` times the travel |
| `{"kind": "rotation", "originMm": [x, y, z], "axis": [x, y, z], "travelDeg": d}` | Turn by `t` times `d` degrees about the line through the origin along the axis (right-hand rule) |
| `{"kind": "gravity-drop", "fallMm": h, "quadraticFraction": w}` | Move down by `h * ((1 - w) * t + w * t * t)`. With `w` = 1 this is a free fall from rest |

One operation is new. It lets an author describe a curved movement as **one** motion, not dozens of short straight
ones:

| Operation | Meaning at fraction `t` |
|---|---|
| `{"kind": "path", "throughMm": [[x, y, z], ...], "curve": "straight" \| "arc" \| "smooth"}` | Slide, without turning, so that a point starting at the first listed point follows the curve. `t` is the fraction of the curve's length covered |

- `straight`: straight lines from point to point.
- `arc`: exactly three points; the circle through them, from the first, past the second, to the third.
- `smooth`: a smooth curve through every point (a centripetal Catmull-Rom spline: it passes through each point and
  does not overshoot between them).

Together with `through` motions (section 4.7), an author never has to cut a curve into pieces by hand. A tool that
only knows the three old operations can ask the library for sampled positions instead.

## 6. The escape hatch: custom shapes

Some shapes cannot be said with the shapes above. The owner's ruling is that an escape hatch is necessary, and that
it is also where bad habits creep in. So the door is **narrow, declared and reported**. A separate auditor must be
able to tell fair use from misuse by reading the design source and the manifest.

### The contract

1. **Registered by name in the design source**, with a required reason and limits:

   ```json
   "custom": {"hook": {"reason": "The hook jaw is a curved slot; no listed shape makes it.",
                       "limits": "Outline only. Jaw radius is a guess until the bar is measured."}}
   ```

2. **Code lives in one known folder.** The shape named `hook` is the file `custom/hook.py` beside the design source.
   Nowhere else. The name is letters, digits and underscores.

3. **Fixed form.** The file defines `build(parameters)`. It receives the `parameters` given where the shape is used
   (plain numbers and text) and returns **exactly one solid**.

4. **It only makes a shape.** It does not place itself in the robot (that is what `place` is for), write files, read
   other files, or return several bodies.

5. **Limited imports.** The file may import only `math`, the CAD kernel (`OCP`) and `frc_design_kernel`. The library
   reads the file and refuses anything else before running it.

6. **Checked.** The library checks what it can: the result is one solid, is valid, and has volume. It refuses
   otherwise, and names the shape and the entry that used it.

7. **Reported.** The manifest lists every custom shape used: its name, source file, line count, fingerprint, reason,
   limits, and the solids that use it. A registered shape that nothing uses is an error: remove it.

### What counts as misuse

- Building several solids, or a whole mechanism, in one custom shape and fusing them to pass the one-solid check.
- Using a custom shape for something a listed shape can make (a box, a plate, a tube).
- Doing design arithmetic in the custom file that belongs in `parameters`, so the numbers are hidden from the source.
- Reading files, the clock, the network or the environment, so the shape is not a pure function of its parameters.
- Placing the solid at its final position inside the code, so that `place` and poses no longer tell the truth.
- Keeping shape code outside `custom/`, or importing a project's own modules through `frc_design_kernel` tricks.
- A `reason` that does not say why the listed shapes cannot do it, or `limits` left as filler.
- Many long custom files. One or two short ones is normal. The line counts in the manifest make growth visible.

The library cannot detect all of these. It makes them visible. Judging them is the auditor's job.

## 7. Outputs

`build SOURCE --out DIR` writes:

- `DIR/design.step`: every robot solid, each under its own name, in millimetres.
- `DIR/fixtures.step`: every fixture, when there are any.
- `DIR/manifest.json`: the record of what was built.

The manifest holds: the source file name and fingerprint; units; the pose that was exported; each solid (name, group,
kind, volume, bounding box, mass and where the mass came from); each group (role, carrier, members, mass); mounts;
poses and motions with every number worked out; parts used (file, fingerprint, solid name); custom shapes used; mass
totals and the solids with no mass; and the library version and commit.

**Deterministic.** The same source gives the same manifest, byte for byte, and the same STEP files. The STEP header
carries a fixed timestamp for that reason. A test builds twice and compares.

**Version is information only.** The manifest records the library version and commit so a reader can tell what made
a file. Nothing in the library reads that record back or refuses to work because of it.

## 8. Installing, and what "main is the release" means

```
pip install git+https://github.com/ehartye/frc-design-kernel
```

- There are no version pins and no release branches. The newest commit on `main` is the release.
- What is on a machine is what was last installed there. Two machines can hold different commits. Run the install
  command again to move to the newest.
- Each output file carries the version and commit that made it. If two results differ, compare those first.
- During settling, an update may break a consumer. That is the accepted cost (section 1).
- Consumers do not pin a commit. A consumer that needs an old behaviour says so here, and the library is changed.

## 9. The size and no-circle rules

The owner's ruling: "sooo important we don't have 1k+ line monoliths in the library."

- No module is longer than **600 lines**.
- No function is longer than **120 lines**.
- No module imports in a circle.

`tests/test_size_rules.py` fails the build on any of these. The limits are ceilings, not targets. A module that
nears 300 lines should already be asking whether it is two jobs.

## 10. Testing by need and risk

- Every test states, in its docstring, **the failure it catches**.
- Each kind of check keeps a **control**: a test that proves the check can fail (a too-long module is caught; two
  separate boxes are refused; a motion that misses its end pose is refused).
- The whole suite runs in about a minute.
- In settling, tests guard correctness. Golden-output and consumer tests arrive with the stable period.

## 11. Decisions to revisit

These were the simpler choice at the time. Any of them may change while the library is settling.

1. **Expressions are a small arithmetic language in strings.** The alternative was a separate program per project to
   compute numbers. If expressions grow conditions or loops, stop and rethink.
2. **`each` is the only repetition.** There is no mirror or pattern command. A mirrored copy is an `each` row with a
   sign.
3. **Parameters are single numbers.** No lists or tables. Variants of a design are separate source files.
4. **Solids are drawn in robot coordinates.** `carriedBy` only passes poses and motions down; it does not move where
   a carried group is drawn.
5. **A `through` motion shares the stroke evenly between poses.** There is no timing control yet.
6. **A `path` operation slides without turning.** Turning while following a curve needs a `through` motion.
7. **Mounts are records, not constraints.** Nothing yet checks that the two solids meet at the mount point.
8. **Mass is a single figure**, per solid or per group. Ranges (low and high) are left to the tools that budget.
9. **Custom shape imports are checked by reading the file.** That stops honest mistakes, not a determined author.
10. **Solid names are plain text without checks on characters** beyond being unique. If a STEP reader mangles a name,
    restrict the allowed characters.
11. **No revolve, sweep or loft shapes.** They are custom-shape cases until a second project needs one.
