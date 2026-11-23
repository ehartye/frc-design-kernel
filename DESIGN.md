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
| Build | Design source to named solids, poses, motions, STEP and manifest | `source/`, `motion/`, `kernel/`, `builder/` | Here now |
| Measure | Clearance along a motion with a proof, what touches what, mass and centre of mass | `measure/` | Here now |
| Try | Physics trials defined as data | `trials/` | Here now: planar trials. 3D is undecided (section 11) |

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
  cli.py             the build, validate, measure, try and status commands
  status.py          which records are current, which are stale, and why
  errors.py          DesignError: where, what is wrong, how to fix it
  version.py         library version and commit, for information

  motion/            the motion vocabulary. Pure arithmetic, no CAD kernel.
    matrix.py        rigid transforms as 3x4 number tables
    ops.py           translation, rotation, gravity-drop, path at fraction t
    paths.py         straight, arc and smooth curves through points
    screw.py         smooth movement from one pose to the next
    stages.py        a body's whole movement as stages, with a proven speed limit
    sampling.py      any placement written as one turn and one slide

  source/            reading the design source. No CAD kernel needed.
    expressions.py   safe arithmetic for "=..." values
    schema.py        a small JSON Schema checker with plain messages
    design.schema.json
    trial.schema.json
    expand.py        "each" rows and "=..." values turned into plain numbers
    checks.py        cross-references: names exist, no loops, no double mass
    uses.py          which parameters something depends on
    load.py          file to checked, plain design

  kernel/            thin wrappers over the CAD kernel (OCP). Few lines each.
    shapes.py        box, cylinder, sphere, prism, tube
    booleans.py      union, difference, intersection
    props.py         volume, bounds, validity, solid count, centre of volume
    between.py       the gap between two shapes, shared volume, facing contact area
    section.py       a solid cut by a plane: its outline as segments and arcs
    transform.py     apply a rigid transform to a shape
    step_read.py     STEP file to named solids
    step_write.py    named solids to a STEP file
    quiet.py         stop the kernel's own console chatter

  builder/           the build layer (named builder so the build() function keeps its name)
    shape.py         a shape entry to one solid
    parts.py         solids taken from STEP files by name
    custom.py        the escape hatch: load, check and report custom code
    placement.py     who is carried by whom; transforms per group
    assembly.py      the built design: solids as drawn, placed at a pose or along a motion
    identity.py      enough of a solid's identity to tell later whether it changed
    manifest.py      the manifest
    export.py        write the STEP files and the manifest

  measure/           the measure layer. Reads an Assembly; writes numbers. See section 12.
    scene.py         solids set up for measuring: start, box, speed limit
    pairs.py         broad phase: which pairs are near enough to measure
    search.py        the adaptive search that proves nothing was missed
    proofs.py        exact shortcuts for straight slides
    clearance.py     gaps along a motion and at a pose
    approach.py      does a pair meet, is a seat bearing, is a set withdrawn
    attachment.py    what touches what, what is loose, measured mounts
    sets.py          connected sets
    mass.py          mass and centre of mass
    compression.py   how deep a solid presses into a ball or ring
    run.py           sharing work between worker processes
    summary.py       everything about one design as one record
  trials/            the try layer. Reads an Assembly and trial data; writes results. See section 13.
    inputs.py        a trial's case and its physical inputs with their sources
    assumptions.py   what the planar engine cannot see, with stable ids
    plan.py          the cheapest sufficient bracket plan
    ready.py         plain facts a 3D engine would need settled
    scene.py         a trial's case and named solids turned into a runnable scene
    contact.py       round piece against segment or arc; two friction laws
    drives.py        belts, rollers and wheels: imposed or motor-driven
    rules.py         conditions and events as data
    planar.py        the fixed-step solver for one piece in a plane
    record.py        criterion, ranges, step comparison, sensitivity, result word, hand-forward
    fit.py           a trace reduced to one path operation
    custom.py        custom force laws and criteria through the narrow door
    campaign.py      plan the runs, count the cost, run them, write the record
```

**Import direction.** `motion` imports nothing from the rest. `source` imports `motion` (to check operations).
`kernel` imports only OCP. `builder` imports `source`, `motion` and `kernel`. `measure` imports `builder`, `motion`
and `kernel`; `trials` does too. Nothing imports upward, and nothing imports in a circle. A test enforces the
no-circle rule.

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

**One group, one rigid body.** If a left hook and a right hook turn in opposite directions, they are two groups, even
though a person would call them "the hooks". Solids that never move relative to each other belong in one group.

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

### 4.5a Contacts

```json
"contacts": [{"pair": ["crate", "tine left"], "during": ["hand off"], "note": "The crate rests on the tine."}]
```

A contact says that two solids are meant to touch. It is a fact about the design, written where the design is
written. The measure layer leaves a declared pair out of its clearance search and counts it. `during` is optional and
limits the contact to the named motions; without it the contact holds always. `each` works here too.

### 4.5b Pieces, materials, motors and drives

The physical facts that trials use live in the design source, once, in physical units. They belong to no engine.

```json
"pieces":    {"ball": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 75},
                       "massKg": {"value": 0.215, "measured": "kitchen scale, 3 pieces"}}},
"materials": {"tread": {"stiffnessNPerM": {"value": 80000, "assumed": [40000, 160000]},
                        "restitution":    {"value": 0.3,   "assumed": [0.2, 0.5]},
                        "friction":       {"value": 0.8,   "assumed": [0.6, 1.0]}}},
"motors":    {"small": {"ktNmPerA": {"value": 0.0097, "measured": "maker's data sheet"}, "ohm": {...}, "keVsPerRad": {...}}},
"drives":    {"belt":  {"motor": "small", "gear": 2, "efficiency": {...}, "radiusMm": 18.5, "movingKg": {...},
                        "statorLimitA": 40, "supplyLimitA": 30,
                        "turns": [{"solid": "belt module", "axis": [0, 1, 0]}, {"solid": "top roller", "axis": [0, 1, 0], "ratio": 2}]}}
```

- A **piece** is a game piece or other free body, declared with its real 3D shape. An engine works out what it needs
  from that (the planar engine takes a round section and its inertia).
- A **material** is how the piece meets a surface of that kind: spring, bounce or damping ratio, friction.
- A **drive** is declared on solids: "this solid turns about this axis" (right-hand rule), with its motor, gear and
  what the motor has to speed up. Which way a surface runs in a section follows from the axis.
- **Every physical input states its source**: `{"value": v, "measured": "where"}` or `{"value": v, "assumed":
  [low, high]}`. A plain number has no stated source; a trial that uses it is incomplete (section 13.3).

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

### 4.8 What the source does not say, and where it goes

A hand-written builder program can do anything. A design source cannot, on purpose. This table says where each thing
a builder used to do now lives.

| A builder used to... | Now |
|---|---|
| Work out sizes from other sizes, with trig | `parameters` and `=` expressions (4.1) |
| Loop over left and right, or four corners | `each` rows (4.2) |
| Join, cut or clip simple shapes into one solid | `union`, `difference`, `intersection` (4.2) |
| Draw a pie slice of a cylinder, a hollow tube, a ball | `cylinder` with `sweepDeg`, `tube`, `sphere` (4.2) |
| Place a supplier's solid, picked by name | `part` (4.2) |
| Move a mechanism's members together, and what rides on them | groups and `carriedBy` (4.3) |
| Split a curved move into many straight cases | one `path` operation or one `through` motion (4.7, 5) |
| Draw a second copy of a mechanism in its other position | a named pose (4.6) |
| Fix the STEP header time and names so builds repeat | the library does it (7) |
| Revolve a profile, sweep or loft a section | a custom shape (6), until two projects need the same one |
| Change a supplier's solid (stretch a shaft, trim a housing) | not offered. A part is placed, never changed. Draw the changed solid, or use a custom shape that builds it from numbers |
| Simplify a detailed supplier assembly into a few envelope blocks | not offered. Do it once outside the library and keep the result as a STEP file used through `part` |
| Read numbers from a trial result or another file | not offered. The source holds the numbers; whoever produces new numbers edits the source |
| Fit moves to a recorded trace | not offered here. This will belong with the try layer, which owns traces |
| Pick a variant with an `if` | not offered. A variant is its own source file |
| Check clearances, starting size or reach, and stop the build | not here, ever. The measure layer will report numbers; tools that judge decide |
| Write budgets, records, review pages | not here, ever (section 2) |

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

5. **Limited imports.** The file may import only `math`, the CAD kernel (`OCP`) and `frc_design_kernel`. It may not
   use `open`, `exec`, `eval` or similar. The library reads the file and refuses anything else before running it.

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

`validate SOURCE` checks everything that needs no CAD kernel: the schema, names, loops, files present. `build` then
checks the rest: every shape is one valid solid, every part's solid name exists in its file, every motion with a
`to` really ends there. `build --pose NAME` exports the solids at a named pose; without it they are exported as
drawn.

The manifest also gives the box around the whole robot as exported and at every named pose.

**One body per name.** A moved or imported solid is, inside the CAD kernel, a shared body plus a placement. Written
to STEP like that, the name lands on the wrong level of the file. The export works the placement into the geometry
first, so each name in the file holds exactly one plain solid.

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
10. **Solid names are plain ASCII text.** The CAD kernel damages accented letters and symbols when it writes a STEP
    file, so the build refuses them. Names read from a supplier's STEP file are repaired where possible.
11. **No revolve, sweep or loft shapes.** They are custom-shape cases until a second project needs one.
12. **A group is one rigid body**, so mirrored members that move differently are separate groups. If that makes
    group lists long, add a way to gather groups under one heading for the reader.
13. **Fixtures move like any group.** A tool that draws the field moving past a still robot poses the fixture
    groups. There is no separate idea of "the robot drives".
14. **Touching solids are closer than any gap above zero.** Two solids bolted together in one group touch, so a
    clearance run with `min_gap` above 0 lists them unless the source declares them as a contact or draws a small
    split between them. This is carried over from the engine the measure layer was ported from. If declaring every
    joint becomes a chore, leave pairs inside one rigid group out of the motion search and report them at the pose.
15. **The speed limit is taken from a box.** It is sound but can be loose for a long solid turning about a far
    pivot, which costs samples, never correctness.
16. **Measure results are not rounded.** The same source gives the same numbers on one machine; tiny differences
    between machines or kernel versions are possible in the last digits.
17. **Trials in three dimensions and with several bodies are not built yet.** The owner has decided: option A below,
    an optional engine adapter with MuJoCo as an optional extra, is built next. The options are kept for the record.
    What was weighed: **Trials in three dimensions and with several bodies.** A flow of many balls, a chain climb, a ring
    modelled as linked capsules and anything a general physics engine does are outside the planar solver. The owner
    decides how they come under the same trial definition and record. The options, with cost and dependency:

    | Option | What it is | Cost | Needs |
    |---|---|---|---|
    | A. Engine adapter | An optional module turns the trial definition and the named solids (as meshes or primitives) into a scene for an external physics engine, runs it, and reads the result back into the same record. The campaign still runs the control, brackets and half-step repeat itself. | About 600 to 900 lines here, plus a mapping per body kind. Results depend on the engine's contact model, which differs from the planar laws. | An optional dependency such as MuJoCo, installed only by projects that use it. The core stays on `cadquery-ocp` alone. |
    | B. Bring-your-own results | The project runs its own 3D solver and hands the campaign run summaries in the record's run format. The library does the method (criterion, control, brackets, step comparison, fit) and stamps the record. | About 100 lines here: a checked import of run summaries. No shared physics; each project keeps a solver. | Nothing new. |
    | C. Native 3D solver | Extend the solver to spheres and rigid bodies in 3D with body-to-body contact. | The largest: likely 1,500 lines or more, and the hardest to prove correct. Fights the size rule. | Nothing new, but probably `numpy` to be fast enough. |
    | D. Planar reductions | Keep to planes: a second free piece, piece-to-piece contact and a rigid polygon body, so more cases fit the planar solver. | About 300 to 400 lines. Covers a second pipe and a hung robot in side view, not a flow of balls or a chain. | Nothing new. |

    A and B can both be had; B first is cheapest and keeps one record format for everything. D is independent of
    the others and closes most of the planar gaps listed in section 13.7.
18. **A trial's solver runs in plain Python.** It manages about 200,000 steps a second. If campaigns grow past a few
    million steps, the inner loop is the place to spend effort.
19. **The default plan moves one input at a time.** Combinations are only run when a trial asks for a grid.
20. **A hand-off passes the piece's end state only.** Drive speeds and flap angles start fresh in the next trial.

## 12. The measure layer

The measure layer answers questions about a built design with numbers. It never says pass or fail. Every limit it
compares against (a minimum gap, a touching distance, a depth) is a number the caller gives it, and the result says
so.

### 12.1 Clearance along a motion, with a proof

The question: over the whole of a motion, how close does each pair of solids come?

Sampling the motion at fixed steps cannot answer that. A thin part can pass through another between two samples,
and "how finely did you split it" has no good answer. The library proves its answer instead:

1. **A speed limit for every solid.** From the motion's stages the library works out a limit on how fast any point
   of a solid can move, in millimetres per unit of the stroke fraction `t` (`motion/stages.py`). A slide moves at its
   length. A turn moves the farthest corner of the solid's box at the angle times its distance from the pivot. A
   `path` moves at exactly the curve's length. A `through` motion moves at its fastest screw. A carried solid adds
   its carrier's limit. The limit is never lower than the real speed; a test checks that on every kind of movement.
2. **Sample and bound.** The gap is measured at `t` = 0 and 1, then at the middle of an interval. Between `lo` and
   `hi` the gap cannot fall more than `speed * (hi - lo) / 2` below the middle sample. If that floor is still above
   the asked gap, the whole interval is settled. If not, the interval is halved and both halves are sampled.
3. **A depth limit.** Halving stops after `depth` levels (default 9). A pair still not settled is reported with
   `"proven": false` and the interval that was left. It is never passed off as clear.

Before sampling, cheaper exact tests remove most pairs: two boxes that the speed limit cannot bring together; two
boxes that stay apart along one axis for the whole stroke (worked out exactly for slides and drops); and, for a pair
whose relative movement is one straight slide, the solid swept by the moving one.

Each row of the result:

```json
{"pair": ["arm", "post"], "method": "adaptive search", "gapMm": 4.91, "t": 0.484, "overlapMm3": 0.0,
 "lowerBoundMm": 4.02, "proven": true, "closerThanMinGap": false, "samples": 37}
```

- `gapMm` at `t` is the smallest gap that was sampled. `lowerBoundMm` is the proven floor for the whole stroke.
- `closerThanMinGap` is a fact about the caller's `min_gap`: a sample was closer, or the solids shared volume.
- `method` is `adaptive search`, `enclosed straight stroke` (settled exactly, no samples) or `fixed relative pose`
  (the two solids do not move against each other, so one measurement is the whole answer).
- Pairs that boxes prove far apart get no row. They are counted under `counts`.

Inputs that are data, not looked up from anywhere: `min_gap`; `contacts` (pairs meant to touch, left out and
counted); `absent` (solids taken out of the scene, such as a cover removed before a part is lifted out); `depth`.

`clearance.at_pose` asks the same of a still pose and lists only the pairs closer than `min_gap`.

### 12.2 The other measures

| Module | Question | Answer |
|---|---|---|
| `approach.reach` | Do two solids come within a distance, in a window of a motion? | A witness (`gapMm`, `t`), or a proof that they do not |
| `approach.seat` | How do two solids sit on each other at a fraction `t`? | Flat area in contact, shared volume |
| `approach.withdrawn` | At the end of a motion, how far are the moved solids from everything that stayed? | Box gap per moved solid |
| `attachment.at_pose` | What touches what within a gap? What hangs together? What is not connected to the base? Which fixtures float above the floor? | Touching pairs with gaps, connected sets, loose solids with their nearest neighbour, fixtures off the floor |
| `attachment` (mounts) | Is each mount real? | Per mount: the true gap between its two solids, and the stated point's distance to each |
| `mass.roll_up` | What does it weigh and where is the centre of mass, at a pose? | Per group and whole. A solid's mass sits at the centre of its volume; a lump group mass at the centre of the group's volume |
| `compression.indentation` | How deep does a solid press into a ball or a round ring along a motion? | Deepest sample, and a proven ceiling |

`attachment` takes its own inputs as data: the touching `gap`, the `floor_z`, solids to `ignore` (a game piece, a
gauge), a `base` solid, and declared `contacts`. Without a `base`, the largest connected set is the base.

### 12.3 Workers

`measure/run.py` shares clearance work between worker processes and does no measuring itself. A motion's pairs are
dealt out in shares; rows come back in pair order, so the result is the same for any worker count (tested). The
caller chooses the count. The default is half the machine's cores.

### 12.4 The record and the command

```
python -m frc_design_kernel measure SOURCE --out DIR [--min-gap MM] [--touch-gap MM] [--floor-z MM]
                                                     [--ignore SOLID] [--workers N] [--depth N]
```

writes `DIR/measurements.json`:

```json
{"schema": "frc-design-kernel/measurements@1",
 "generator": {"library": "frc-design-kernel", "version": "...", "commit": "..."},
 "design": {"name": "...", "source": "design.json", "sourceSha256": "..."},
 "settings": {"minGapMm": 1.0, "touchGapMm": 3.0, "floorZMm": 0.0, "ignored": [], "depthLimit": 9},
 "motions": {"lift": {"motion": "lift", "counts": {}, "proven": true, "closer": [], "unresolved": [], "closest": {}, "pairs": []}},
 "poses": [{"pose": null, "clearance": {}, "attachment": {}, "mass": {}}]}
```

The command prints one line per motion and per pose. It prints numbers and counts, not verdicts.

### 12.5 For tools that only know the three old operations

`frc_design_kernel.sampled(design, motion, steps)` turns any motion, curved or through poses, into `steps + 1` still
placements. Each placement is written as at most one `rotation` and one `translation`, applied in full. An older
tool can read those as start poses.

### 12.6 What the measure layer leaves out

- **Guidelines and verdicts.** No built-in gap, no "floating is an error", no pass or fail.
- **Reading evidence files.** A declared contact is a pair of names. Whether a trial justifies it is not asked here.
- **Mass ranges, weight limits and electrical budgets.** Mass is one figure; budgeting is a judging tool's work.
- **Progress lines, receipts and advice text.**
- **Line-of-sight checks** and the advisory test for a solid that turns about its own axis. They can be added as
  measures when a second project needs them.

## 13. The try layer: planar trials

A trial answers "does this work?" with physics: does the piece get picked up, does it stay seated when the robot is
hit, does it reach the wheel. The owner's aim for this layer: "physical accuracy that can guide decision making ahead
of detailed design ... without sacrificing time needlessly." So every trial says what it cannot see, every input
says where its number came from, and the runner spends the fewest runs that can show whether the answer is safe.

### 13.1 What a trial is

A trial is data in the design source under `trials`, or a file beside the source that the source names
(`"trials": {"receive": {"file": "trials/receive.json"}}`). Its schema is `source/trial.schema.json`. Any number may
be an `=` expression over the design's parameters.

| Part | What it says |
|---|---|
| `engine` | Which engine runs it. `planar` is the default and the only one built. A second engine will read the same definition. |
| `assumes` | What this trial takes for granted beyond the engine's standing assumptions: a list of `{"id", "text"}`. Without it the trial is incomplete. |
| `plane` | The flat section the trial lives in: square to one axis (`normal`), at a level (`atMm`). Gravity acts down the second in-plane axis. |
| `pose` | The named pose the solids are in. |
| `piece` | `{"use": name, "start": ...}`: a piece from the design's `pieces`, and where it starts (point, velocity, spin) or `{"after": trial}` to start where another trial's piece ended. |
| `surfaces` | What the piece can touch. Each names a `material` and one of: `solid` (the outline where the plane cuts that named solid), `segmentsMm`, `circleMm`. A solid that a drive turns runs with that drive. A typed surface may state `speedMps`. |
| `flaps` | Hinged, sprung flaps: hinge point, length, rest direction, inertia, preload, spring, damping, a travel limit. |
| `commands` | How each drive is commanded: `imposed` (a speed), `voltage`, a `speed` loop or a position `hold`; bus voltage; and `rules` that change the command when a condition holds. |
| `planar` | Choices that belong to the planar engine only: the friction law (`stick` or `smooth`) and its two constants, and where on the piece a contact acts. |
| `loads` | The frame the piece rides in speeding up or slowing down: an acceleration along a direction, as a step or a half-sine pulse, at a time or after an event. |
| `movers` | A steady slide of chosen surfaces, started at a time or after an event: a stated velocity, or a straight motion of a group from the design source. |
| `events`, `measures`, `pass` | What counts as what; numbers to keep; the criterion. |
| `control`, `brackets`, `grid` | The method inputs. See 13.3. |
| `stepS`, `durationS` | The fixed step and the longest a run may last. |

**Conditions are data.** `{"signal": name, "above": n}`, `{"after": event, "delayS": s}`, `{"notYet": event}`,
`{"restFor": s}`, and `all`, `any`, `not` over those. A sensor lag is a `delayS`. An interlock is a drive rule on a
signal. A ready band is a rule on a drive's speed.

### 13.2 The physics

- **Contact.** A spring and damper along the normal that never pulls.
- **Friction, two laws.** `smooth`: Coulomb friction eased near zero slip; a piece on a slope always creeps.
  `stick`: a tangential spring capped at friction times normal force, with memory; a clamped piece holds still.
- **Moving surfaces.** A belt, roller or wheel is a surface with a speed along itself. The friction it gives the
  piece is fed back to its drive as a load.
- **Motors.** Torque from current, back-EMF from speed, winding resistance, gear and efficiency; a winding current
  limit and an optional supply limit. Bus voltage `null` is power off (coasting); 0 is shorted windings (a brake).
- **Integration.** Fixed step; forces from the state at the start of the step; speeds advance before positions.

Tests hold the solver to closed-form answers within 1%: free flight, both friction laws at the slope threshold, a
belt bringing a block and a bar to its surface speed, a weight settling a sprung flap, a bounce, and a motor's free
speed, current limits, speed loop, coast and brake.

### 13.3 The method every trial gets

The campaign, not the trial, performs the method:

1. **Nominal**: the trial as written.
2. **Half step**: the same at half the step.
3. **Control**: the trial with `control.change` made. It must *not* meet the criterion.
4. **Ranges, the cheapest way.** Every input with an assumed range is run at the two ends of its range, one input
   at a time. If an end changes the outcome, the edge is closed in on by halving between the last value that held
   and the first that did not (three times by default, `rangeRefine`). An input listed under `brackets` is run
   outward from the nominal and **each side stops at its first failure**. Measured inputs are not varied.
5. **A grid only when asked.** `"grid": {"inputs": [...]}` also runs every combination of those inputs' range ends.

A change is a path into the trial's case (`materials.tread.friction`, `commands.belt`,
`loads.braking.accelerationMps2`; list items by name) or a design parameter (`parameters.squeeze`). A parameter
change rebuilds the design, so the real solids move.

The result is one word, with findings in plain text:

| Result | Meaning |
|---|---|
| `incomplete` | The method lacks something: no control, no stated assumptions, an input with no stated source, or nothing with a range. Reported even if the nominal run met the criterion. |
| `failed` | The nominal run did not meet the criterion. |
| `control not rejected` | The control met the criterion, so the trial does not show what it claims. |
| `not converged` | The outcome changes at half the step. |
| `flips in range` | The outcome changes somewhere inside an input's assumed range. **A measurement is needed before this result can carry a decision.** The record says which input and between which two values. |
| `passed` | Criterion met, control rejected, half step agrees, and the outcome holds across every assumed range. |

These words state what the method found. Whether a design may go forward on them is for the tools that judge.

**Sensitivity before fidelity.** From the same one-at-a-time runs the record ranks the inputs by how much they move
the outcome: first the ones that change it, then by the largest change in any measure as a fraction of its nominal
value. The top of that list is the measurement that would narrow the result most. It costs no extra runs.

### 13.4 Cost before it runs, time after

`campaign.estimate` counts the most runs and steps a campaign can take and a rough time. `try` prints that before
anything runs; `--estimate` prints it and stops; `--max-steps` refuses a larger campaign. Afterwards `try` prints the
runs made, the steps run and the seconds spent. How long a campaign ought to take is a judgement that lives
elsewhere; the library reports the numbers.

### 13.5 The record

`try SOURCE --out DIR` writes `DIR/trials.json`, schema `frc-design-kernel/trial-campaign@2`. Per trial:

- `engine`: the engine's name and version.
- `definition`: the trial with the pieces, materials, motors and drives it drew on, as run.
- `assumptions`: the author's and the engine's standing ones, each with an id and plain words.
- `inputs`: every physical input with its value and whether it was measured (and where), assumed (and the range) or
  unstated.
- `saw`: the section plane, the section taken of the piece, each solid that was cut and how many segments and arcs
  it gave, and any surface that was typed in.
- `used`: what the trial depended on, for the status command (section 14).
- `result`, `findings`; the `nominal` run with a **replayable trace** and contact rows per surface; `stepComparison`;
  `control`; `ranges` (per input: held or flipped, and between which values); `grid`; `sensitivity`.
- `handForward`: the nominal inputs, the range each input held over, the marginal edges, the sensitivity order, the
  control and the assumption ids, for a later engine to pick up (section 15).
- `runs`: **every run's inputs and outcome**.
- `fit`: the piece's path as **one `path` operation** within `fitToleranceMm` of every trace sample.

The same source gives the same record. `try --trial NAME` runs only that trial (and any it starts after) and puts
the result into an existing `trials.json`, keeping the rest.

### 13.6 The escape hatch for trials

The same narrow door as custom shapes (section 6): registered by name under `custom` with a `kind`, a `reason` and
`limits`; code only in `custom/<name>.py`; a fixed function; checked before it runs; listed in the record with its
file, line count and fingerprint.

| Kind | Function | May do |
|---|---|---|
| `force` | `force(signals, parameters)` returns `(fx, fz, torque)` on the piece | Add a force law the layer lacks: drag, lift, rolling resistance, a magnet. |
| `criterion` | `judge(run, parameters)` returns true or false | Decide pass from a run's outcome, events, measures and end state. |

Custom trial code may import only `math`. It **cannot** replace the control, the ranges or the half-step repeat,
and it never writes the record: the campaign runs all of those around it, and reports the custom code beside them.

What counts as misuse:

- A force law that moves the piece where the author wants it (a "guide" force), so the trial cannot fail.
- A force law that stands in for a contact, drive or load the layer already has.
- A criterion that returns true whatever the run shows, or reads only what flatters the design.
- A criterion that re-implements the outcome logic that belongs in `events`, hiding what counts as success.
- Keeping trial numbers inside custom code so ranges cannot reach them.
- State kept between calls, so two runs of the same inputs differ.
- Many custom laws in one trial. One short law is normal.

### 13.7 What the planar engine assumes, and what it cannot express

Its standing assumptions go into every record, each with a stable id: `in-plane`, `single-piece`, `round-piece`,
`rigid-surfaces`, `spring-contact`, `section-outline`, `no-air`, `fixed-step`.

Not expressible yet, each a known gap and not a place for project code to hide:

- A second free piece, or piece-to-piece contact.
- A body that is not round (a robot hung on hooks, a box).
- More than one piece loading the same drive at once.
- A drive's speed or a flap's angle carried from one trial into the next.
- Surfaces carried by a turning motion of the design (only straight slides).
- A flap that is not a one-way sprung flap (a powered or two-way hinge).
- A rope, winch or spring between bodies.
- Anything in three dimensions.

## 14. Records say what they used

The intended way of working is in stages: arrange and measure, then planar trials, then a fuller check on the
settled layout. When a later stage finds a problem, the author changes the design source and comes back up, running
again only what the change touched. To make that possible:

- Every measurement and every trial record carries a `used` block: the solids it drew on, each with its group,
  kind, volume, bounding box as drawn and mass; the motion's operations and the poses it names; the groups and who
  carries whom; mounts and declared contacts; the parameters a trial's numbers were worked out from, with their
  values.
- `python -m frc_design_kernel status SOURCE DIR` rebuilds those blocks from the source as it is now and prints,
  per record, `current` or `stale` and what changed: `solid "belt bed" changed (boundsMm, volumeMm3)`,
  `parameter "squeeze" changed: 20 to 15`, `the trial definition changed at materials.tread.friction.value`.
  Plain facts. It does not say whether to run anything again.
- A design's name and every `note` are outside all identities. Renaming a design or editing a note makes nothing
  stale.
- A targeted rerun is one command: `measure --motion NAME` or `--pose NAME`, and `try --trial NAME`. Each puts its
  result into the existing record and keeps the rest.

A clearance along a motion, and the measures at a pose, use every solid present: any of them may be the obstacle or
the weight. A trial uses only the solids its plane cut.

`status` also prints the facts a 3D engine would need settled (section 15).

## 15. When to go beyond planar, and what planar hands on

### 15.1 Escalation, in plain words

- **Use planar when the question is planar**: the piece moves in one section, what it touches is the same along
  its width, and one piece is enough to answer.
- **Go to 3D when the answer depends on what planar cannot see**: the piece's orientation (it can tip, yaw or
  arrive skewed), contact off the section plane (an end, a corner, a side wall), or many bodies at once.
- **Go to 3D when a planar result that a decision hinges on flips inside its range and a measurement cannot settle
  it.** First look at the sensitivity ranking: if one measurement would settle it, measure.
- **Never run a trial whose outcome could not change a decision.** If both answers lead to the same design, the
  time is better spent elsewhere.

### 15.2 What the planar stage hands to 3D

Nothing below is the 3D engine. These are choices of data shape made now so that a second engine can run the same
trials with no re-authoring.

1. **The piece is defined once, in 3D.** The planar engine works out its own section and says which it took.
2. **One parameter set.** Stiffness, friction, bounce, masses and motor constants live in the design source with
   their sources and ranges, in physical units. The planar friction law and its constants sit under `planar`, apart.
3. **Surfaces come from named solids, and the cut is recorded.** A trial that names solids can be run in 3D against
   the same solids.
4. **Drives are declared on solids**: this solid turns about this axis, driven by this motor through this gear.
5. **Assumptions have ids.** A trial's list is the list of things a fuller engine should test.
6. **Readiness is reported as plain facts** by `status`: trial solids that are concave with no convex breakdown to
   be had from how they were built; solids with no mass; moving groups that are not one hinge or one slider (they
   would have to be driven along a path); drives not tied to a solid; trial surfaces that were typed in. How a shape
   was built from boxes, cylinders and unions stays in the design source, so an exact convex breakdown can be worked
   out later; it is not thrown away at export.
7. **Results hand forward.** Each trial's `handForward` block gives the nominal inputs, the range each held over,
   the marginal edges, the sensitivity order and the control, so a later engine can run the nominal case and only
   the marginal edges, with the same control.
