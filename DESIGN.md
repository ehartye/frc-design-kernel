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
  cli.py             the validate, build, measure, screen, try, status and piece-geometry commands
  status.py          which records are current, which are stale, and why
  errors.py          DesignError: where, what is wrong, how to fix it
  version.py         library version and commit, for information
  motor.py           the DC motor model, shared by the trials and the electrical measure

  motion/            the motion vocabulary. Pure arithmetic, no CAD kernel.
    matrix.py        rigid transforms as 3x4 number tables
    ops.py           translation, rotation, gravity-drop, path at fraction t
    paths.py         straight, arc and smooth curves through points
    screw.py         smooth movement from one pose to the next
    stages.py        a body's whole movement as stages, with a proven speed limit
    sampling.py      any placement written as one turn and one slide
    joints.py        a drive's joint: its placement at a joint value, and the value read back from a placement

  source/            reading the design source. No CAD kernel needed.
    expressions.py   safe arithmetic for "=..." values
    schema.py        a small JSON Schema checker with plain messages
    design.schema.json
    subsystem.schema.json
    trial.schema.json
    expand.py        "each" rows and "=..." values turned into plain numbers
    checks.py        cross-references: names exist, no loops, no double mass
    motions.py       drives and motions: motor solids, joints, one cause per motion, no loop of chained starts
    sourced.py       a physical input's number and the range it may lie in
    uses.py          which parameters something depends on
    subsystems.py    what a subsystem file holds, and naming its file in a problem
    load.py          files to checked, plain design

  kernel/            thin wrappers over the CAD kernel (OCP). Few lines each.
    shapes.py        box (sharp or rounded), cylinder, cone, sphere, torus, prism, tube
    booleans.py      union, difference, intersection
    props.py         volume, bounds, validity, solid count, centre of volume
    between.py       the gap between two shapes, shared volume, facing contact area
    section.py       a solid cut by a plane: its outline as segments and arcs
    split.py         a solid with no construction to read, split into convex pieces at its own faces
    transform.py     apply a rigid transform to a shape
    step_read.py     STEP file to named solids
    step_write.py    named solids to a STEP file
    quiet.py         stop the kernel's own console chatter
    mesh.py          a solid as triangles, for drawing or for a physics engine
    hull.py          a convex hull grown to contain a solid; the faces of the hull of any points

  builder/           the build layer (named builder so the build() function keeps its name)
    shape.py         a shape entry to one solid
    parts.py         solids taken from STEP files by name
    custom.py        the escape hatch: load, check and report custom code
    placement.py     who is carried by whom; chained starts and drive commands; transforms per group
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
    mass.py          mass with its range, centre of mass, and the inertia of groups about any line
    electrical.py    a motion's load: torque, current and motor voltage per drive, and the bus voltage
    extremes.py      clearance at both ends of every mechanical adjustment
    screen.py        screen facts: is an interaction the same in every section?
    symmetry.py      what kind of shape a solid is, read from its faces
    compression.py   how deep a solid presses into a ball or ring
    piece_geometry.py  each piece's shape measured on its own: bounds, symmetry, hull, bore
    run.py           sharing work between worker processes, handed back as each piece finishes
    jobs.py          the kinds of measuring job: fields, file names, what each draws on, how each is answered
    records.py       one file per job, written as it finishes; carried while current
    summary.py       the jobs the measure command asks, and what each kind of job uses besides shapes
  trials/            the try layer. Reads an Assembly and trial data; writes results. See section 13.
    inputs.py        a trial's case and its physical inputs with their sources
    assumptions.py   what the planar engine cannot see, with stable ids
    plan.py          the cheapest sufficient bracket plan
    ready.py         plain facts a 3D engine would need settled
    scene.py         a trial's case and named solids turned into a runnable scene
    contact.py       round piece against segment or arc; two friction laws
    drives.py        belts, rollers and wheels: imposed or motor-driven
    rules.py         conditions and events as data
    air.py           drag and Magnus lift on a free piece
    frames.py        the piece's place in a group's own drawing coordinates
    planar.py        the fixed-step solver for one piece in a plane
    record.py        criterion, ranges, step comparison, sensitivity, result word, hand-forward
    fit.py           a trace reduced to one path operation
    custom.py        custom force laws and criteria through the narrow door
    campaign.py      plan the runs, count the cost, run them, write the record
    engines.py       which engine builds and runs a trial; the engine stamp
    mujoco_scene.py  a trial's case as a MuJoCo model (plain text; no MuJoCo import)
    convex.py        a hollow or cut shape as its true convex pieces, from how it was built
    mujoco_parts.py  the piece, moved groups and flaps of that model
    mujoco_contact.py  the library's own contact law at the points MuJoCo finds
    mujoco_run.py    run that model and report it like a planar run (the only module that imports MuJoCo)
```

**Import direction.** `motion` and `motor` import nothing from the rest. `source` imports `motion` (to check
operations). `kernel` imports only OCP and the error type. `builder` imports `source`, `motion` and `kernel`.
`measure` imports `builder`, `motion`, `motor`, `kernel` and `source`; `trials` does too. Nothing imports upward,
and nothing imports in a circle. A test enforces the no-circle rule.

## 4. The design source

One JSON file per design, or one top file plus one file per subsystem (4.9). The schema is
`frc_design_kernel/source/design.schema.json`. Units are fixed: millimetres and kilograms. Angles are degrees. The
file says so in `units` so a reader never has to guess.

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

**Weight.** `massKg` and `densityKgM3` take a plain number or the sourced form of section 4.5b:

```json
"massKg": 0.4
"massKg": {"value": 0.4, "measured": "shop scale"}
"massKg": {"value": 0.4, "assumed": [0.3, 0.55]}
"densityKgM3": {"value": 2700, "assumed": [2650, 2800]}
```

A plain number and a measured value are exact: they count at both ends of the weight range. Only an assumed range
widens it. A density weighs the drawn volume, so use it for a solid drawn as the real shape. A blockout solid (a box
standing for a gearbox) takes a stated `massKg`, because its drawn volume is not the part's. A robot solid with no
weight, and no lump on its group, is listed as unweighed.

**Shapes.** Each is a few lines over the CAD kernel.

| `kind` | Fields |
|---|---|
| `box` | `fromMm`, `toMm`: two opposite corners, in any order. Optional `edgeRadiusMm` rounds all twelve edges to that radius, and the corners become parts of a ball. It must be less than half the smallest side, or no flat face would be left; a larger one is refused |
| `cylinder` | `fromMm`, `toMm`: the two end centres; `radiusMm`. Optional `sweepDeg` and `sweepFrom` (a direction) make a pie slice |
| `cone` | `fromMm`, `toMm`: the two end centres; `radiusFromMm`, `radiusToMm`: the radius at each end. A frustum (a cone with its point cut off). One radius may be 0, for a point, but not both. Equal radii give a cylinder |
| `sphere` | `centerMm`, `radiusMm` |
| `torus` | `centerMm`, `axis`, `majorRadiusMm` (from the centre to the middle of the ring), `minorRadiusMm` (the ring's own radius). A ring. `minorRadiusMm` must be smaller than `majorRadiusMm`, so a hole goes through the middle |
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
group this one rides on: when the carrier moves, this group moves with it. `massKg` on a group (plain or sourced) is
one lump figure for the whole group, spread over its solids by volume; its solids then must not carry their own mass,
so nothing is counted twice.

`place` on a group moves every solid in it once, when the design is built. Use it to draw a mechanism in its own
handy coordinates and then put it in the robot frame.

**One group, one rigid body.** If a left hook and a right hook turn in opposite directions, they are two groups, even
though a person would call them "the hooks". Solids that never move relative to each other belong in one group.

### 4.3a Weight with no solid

```json
"extraMass": [{"name": "wiring", "group": "base", "massKg": {"value": 0.8, "assumed": [0.5, 1.2]},
               "note": "Loom, connectors and ties; not drawn."}]
```

Some weight has no solid worth drawing: wiring, fasteners, paint, a growth allowance. Each entry names it once,
gives its `massKg` (plain or sourced) and puts it in a `group` that holds at least one robot solid. It sits at the
centre of that group's volume and moves with the group. It adds to the group's weight; it does not weigh the
group's unweighed solids.

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

### 4.5b Pieces, materials, motors, drives and the battery

The physical facts that trials use live in the design source, once, in physical units. They belong to no engine.

```json
"pieces":    {"ball": {"shape": {"kind": "sphere", "centerMm": [0, 0, 0], "radiusMm": 75},
                       "massKg": {"value": 0.215, "measured": "kitchen scale, 3 pieces"}}},
"materials": {"tread": {"stiffnessNPerM": {"value": 80000, "assumed": [40000, 160000]},
                        "restitution":    {"value": 0.3,   "assumed": [0.2, 0.5]},
                        "friction":       {"value": 0.8,   "assumed": [0.6, 1.0]}}},
"motors":    {"small": {"ktNmPerA": {"value": 0.0097, "measured": "maker's data sheet"}, "ohm": {...}, "keVsPerRad": {...}}},
"drives":    {"belt":  {"motor": "small", "motorSolid": "belt motor", "gear": 2, "efficiency": {...}, "radiusMm": 18.5, "movingKg": {...},
                        "statorLimitA": 40, "supplyLimitA": 30,
                        "turns": [{"solid": "belt module", "axis": [0, 1, 0]}, {"solid": "top roller", "axis": [0, 1, 0], "ratio": 2}]},
              "pivot": {"motor": "small", "motorSolid": "arm motor", "count": 2, "gear": 60, "efficiency": {...}, "supplyLimitA": 40,
                        "joint": {"group": "arm", "kind": "rotation", "axis": [0, -1, 0], "originMm": [0, 0, 100], "travel": [-10, 120]}},
              "lift":  {"motor": "small", "motorSolid": "lift motor", "gear": 5,
                        "joint": {"group": "carriage", "kind": "slide", "axis": [0, 0, 1], "perOutputTurn": 100, "travel": [0, 400]}}},
"battery":   {"openCircuitV": {"value": 12.6, "assumed": [12.2, 12.9]}, "resistanceOhm": {"value": 0.02, "assumed": [0.015, 0.03]},
              "note": "Bench figures for the packs in use."}
```

- A **piece** is a game piece or other free body, declared with its real 3D shape. An engine works out what it needs
  from that (the planar engine takes a round section and its inertia).
- A **material** is how the piece meets a surface of that kind: spring, bounce or damping ratio, friction.
- A **drive** is a motor and what it moves. Its `motor` names a motor model; `count` motors share the load; `gear` is
  motor turns per turn of the output (default 1); `efficiency` defaults to 1.
- **Every motor is a solid.** A drive with a `motor` names the robot solid that is the motor in `motorSolid`, so the
  motor is weighed like any solid and sits where it is mounted. A motor drive without one is refused.
- A drive's **joint** is the one movement it gives a group (section 4.7): `{group, kind, axis, travel}`, with
  `originMm` (a point on the turning line) for a `rotation`, or `perOutputTurn` (mm per turn of the gear's output: a
  lead, or a pulley's circumference) for a `slide`. The joint value is degrees or mm from the group as drawn, so 0 is
  the drawing. A rotation joint turns its group `360 / gear` degrees per motor turn about the line through `originMm`
  along `axis` (right-hand rule); a slide moves it `perOutputTurn / gear` mm per motor turn along `axis`. `travel` is
  `[low, high]`, the joint values at its two stops. The joint is in the group's own coordinates, before its carrier
  moves it, so a joint rides on its carrier. A joint needs a motor.
- A drive may also be **declared on solids** for trials: "this solid turns about this axis" (right-hand rule), with
  its `radiusMm` and what the motor has to speed up (`movingKg` or `inertiaKgM2`). Which way a surface runs in a
  section follows from the axis. A drive with a joint may keep `radiusMm` and `turns` for the surfaces it runs. A
  drive says at least one of the two; a trial may use only a drive with `radiusMm`.
- A drive's **current limits** are per motor: `statorLimitA` (the winding) and `supplyLimitA` (from the bus).
- The **battery** is one per design, in the top file: its `openCircuitV` (volts with no load) and its
  `resistanceOhm` (the pack, its leads and the main breaker, as one figure), each sourced. The low open-circuit
  voltage and the high resistance together are the weak pack. The electrical measure (12.7) uses it; without one a
  motion's currents are still worked out, and no bus voltage is stated.
- **Every physical input states its source**: `{"value": v, "assumed": [low, high]}` or `{"value": v, "measured":
  "where"}`. An assumed value with a range is a normal, complete state: a best guess. A measured value only narrows
  the range to nothing. A plain number states neither, so nothing says how far it may be off; a trial that uses it
  is incomplete (section 13.3).

### 4.5c Adjustments

The owner's principle: "real measurement can never be the bar for leaving design. we take our best guess and build
in configurability." So what the built robot can change is design data too:

```json
"adjustments": {
  "nip squeeze":   {"input": "parameters.squeeze", "kind": "mechanical", "range": [4, 10], "step": 1, "note": "Slotted bearing blocks."},
  "flap preload":  {"input": "flaps.flap.preloadNm", "kind": "spring", "range": [0.02, 0.08]},
  "belt setpoint": {"input": "commands.belt.setpointMps", "kind": "setpoint", "range": [2.0, 4.0]}
}
```

`kind` is `mechanical` (a slot, shim or spacer), `spring` (a preload or rate) or `setpoint` (a speed, voltage or
position set in software). `input` is a design parameter (`parameters.NAME`) or a path into a trial. A mechanical
adjustment is always a design parameter, so the solids move with it: `measure --extremes` builds and measures the
design at both ends of each such adjustment, so clearance is known across the range. Only mechanical adjustments are
measured (a setpoint or a spring moves no solid), only the pairs with a solid that end moves (`moves`), shared between
the same workers as the rest of `measure`, and only the motions and poses `--motion` and `--pose` name. A trial lists the adjustments
that apply to it under `adjustments`; the campaign then asks whether they cover its uncertain inputs (section 13.3).

### 4.5d Interactions and what solids are made of

An interaction is a piece meeting some solids in a section plane: the thing a trial would be about. Declaring it lets
the screen facts (section 12.6a) be worked out at the arrangement stage, before any trial exists.

```json
"interactions": {"pickup": {"piece": "ball", "plane": {"normal": "y", "atMm": 0}, "solids": ["belt module", "bumper"],
                            "guides": ["side plate left", "side plate right"], "pieceAtMm": [[420, 0, 75]], "motions": ["intake deploy"],
                            "pieceSolid": "drawn ball", "squeezeMotion": "ball through intake", "piecesAtOnce": 1,
                            "approach": {"angleDeg": [-10, 10], "offsetMm": [-15, 15]}, "targetOffPlane": false}}
```

`approach` (the angles and offsets the piece may arrive with) and `targetOffPlane` are things geometry cannot know;
they are stated here and simply echoed. A solid may also say what it is made of: `"material": {"class": "rigid"}`
(the default), `"compliant"` (with a `stiffnessNPerM`, or a force-deflection `curve` of points marked measured or
assumed) or `"flexible"` (`kind`: belt, net, chain, tubing or fabric).

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

A motion says how groups get from one place to another, and what makes them move. Every motion states what moves
it: motors, through drive commands, or a stated cause for typed geometry.

**Drive commands.** The motion says what each motor does, and the library works out where every group is:

```json
"raise arm": {"from": "stowed", "to": "up", "drive": {"pivot": {"to": 95}}, "durationS": {"value": 0.5, "assumed": [0.4, 0.7]}},
"lift":      {"drive": {"lift": {"by": 300}}, "durationS": {"value": 0.8, "assumed": [0.6, 1.0]},
              "alsoRunning": [{"drive": "drivetrain", "atLimit": true}], "extraLoad": {"lift": {"value": 15, "assumed": [5, 30]}}}
```

- `drive` maps each drive to `{"to": joint value}` or `{"by": joint change}`, in degrees for a rotation joint and mm
  for a slide. Each commanded joint's group turns or slides at an even rate over the stroke, from the joint value it
  starts at to the one commanded.
- The joint value a motion starts at is carried along a chain of motions (below). Otherwise it is read from the
  group's own placement at the start: as drawn it is 0, and at a pose it is the value the joint must have to put the
  group there. A turn is read as the angle inside the travel nearest 0. A group whose start the joint cannot give
  (a pose that also shifts it sideways) is refused.
- `durationS` (sourced) is how long the motion takes. A motion that commands drives must give it.
- `alsoRunning` lists drives that run at the same time without being part of the motion, such as the drivetrain
  during a lift, each with `currentA` (sourced, the whole drive's current from the bus) or `"atLimit": true` (its
  current limit times its `count`, so it needs a limit). A drive the motion commands is already running and is not
  listed.
- `extraLoad` is `{drive: load}` (sourced) for a commanded drive: a load at its joint beyond the moved groups'
  weight and acceleration, such as a spring or friction. It is N m about the joint for a rotation and N along it
  for a slide.
- The library states these numbers. Torque, current and bus voltage are worked out from them by the electrical
  measure (12.7); whether they are enough is for a tool that judges.

**Refused:** a command that starts or ends outside its joint's `travel`; two drives in one motion whose joints move
the same group (two motors on one joint are one drive with `count`); a typed operation on a group a commanded drive
moves; a drive with no joint; `through` in a driven motion. A driven motion may also move other groups by typed
moves, such as a piece pushed along, when it says what moves them with `by`.

**A stated cause.** A motion no motor drives says what does, in `by`, and is written as typed geometry:

```json
"hand off": {"from": "raised", "to": "set down", "by": "hand",
             "moves": {"load": [{"kind": "path", "curve": "arc", "throughMm": [[0, 0, 350], [130, 0, 400], [260, 0, 350]]}]}},
"swing":    {"by": "hand", "through": ["stowed", "half", "raised"]}
```

`by` is `hand`, `spring`, `gravity` or `piece` (a payload moved by what it touches, whose path comes from a trial
fit). A motion with neither `drive` nor `by` is refused. Typed geometry is one of two forms:

- **Moves:** start at a pose (or after another motion, below), then apply operations by stroke fraction `t`.
- **Through:** pass smoothly through a list of poses, as one motion. Between each pair of poses a group turns and
  slides at an even rate along the one natural path between them (a turn about a fixed axis plus a slide along that
  axis). An arm drawn at two angles about its pivot therefore swings about that pivot. The poses share the stroke
  evenly. A `through` motion starts at its first pose, so it takes no `from` or `to`.

Such a motion has no electrical load unless it lists `alsoRunning`.

**Where a motion starts.** `from` is a pose, or nothing (as drawn), or `{"after": "<motion>"}`: each group then
starts at its own placement at the end of that motion, the earlier motion's own start included.

- **How a chained start composes.** Every group's own placement at the end of the earlier motion is worked out
  (its start, then its commanded joint, then its typed moves) before carriers, and becomes the group's start, as if
  it were a pose. The later motion's own drive commands and moves apply after it, and carriers are added last, as
  for any pose. So a carried group ends the earlier motion and starts the later one in the same place, and a joint
  rides on its carrier in both.
- **A joint value follows the chain.** A drive the earlier motion commanded starts the later motion at the value it
  was commanded to, so `{"by": -45}` counts from there, even past a whole turn. A drive whose group the earlier
  motion did not move starts at the value it had at the earlier motion's start, and so on up the chain. A group the
  earlier motion moved some other way (by typed moves, through poses, or another drive) has its value read from
  its placement.
- **Known by where it is, never by name.** A chained start is kept as the placement it works out to, with arithmetic
  noise in the last digits removed. Records of the later motion hold that placement and the joint values (section
  12.4), not the name of the earlier motion. Changing how the earlier motion gets to its end, without changing where
  it ends, leaves the later motion's records current.
- A chain that loops back on itself is refused, naming every motion in the loop. A chain is worked out once per
  motion, so a long chain costs one working-out per link.

`to` is optional on any motion with a start. When it is given, the build checks that the motion really ends at that
pose and refuses if not. `validate` checks joint travel and end poses too; it needs no CAD kernel.

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
| Type an arm's swing as a rotation by hand | a drive command through the motor's joint (4.5b, 4.7) |
| Write the same start pose for every step of a sequence | `"from": {"after": "<motion>"}` (4.7) |
| Draw a second copy of a mechanism in its other position | a named pose (4.6) |
| Fix the STEP header time and names so builds repeat | the library does it (7) |
| Revolve a profile, sweep or loft a section | a custom shape (6), until two projects need the same one |
| Change a supplier's solid (stretch a shaft, trim a housing) | not offered. A part is placed, never changed. Draw the changed solid, or use a custom shape that builds it from numbers |
| Simplify a detailed supplier assembly into a few envelope blocks | not offered. Do it once outside the library and keep the result as a STEP file used through `part` |
| Read numbers from a trial result or another file | not offered. The source holds the numbers; whoever produces new numbers edits the source |
| Fit moves to a recorded trace | not offered here. This will belong with the try layer, which owns traces |
| Pick a variant with an `if` | not offered. A variant is its own source file |
| Check clearances, starting size or reach, and stop the build | not here, ever. The measure layer will report numbers; tools that judge decide |
| Write budgets, receipts, review pages | not here, ever (section 2) |

### 4.9 Subsystem files

A large design is easier to edit in pieces: an agent or a student reads only the subsystem it changes. The top file
keeps what belongs to the whole design and lists the subsystem files:

```json
{
  "schema": "frc-design-kernel/design@1",
  "name": "Bench lifter",
  "units": {"length": "mm", "mass": "kg"},
  "parameters": {"post_x": -120},
  "custom": {},
  "fixtures": [],
  "pieces": {}, "materials": {}, "motors": {}, "trials": {},
  "subsystems": [{"file": "subsystems/base.json"}, {"file": "subsystems/carriage.json"}]
}
```

Each subsystem file (`frc-design-kernel/subsystem@1`, schema `source/subsystem.schema.json`) holds that subsystem's
`groups`, `solids`, `mounts`, `contacts`, `drives`, `motions`, `poses`, `adjustments`, `interactions` and
`extraMass`, and an optional `note`:

```json
{
  "schema": "frc-design-kernel/subsystem@1",
  "note": "The carriage, its tines and the load it carries.",
  "groups": {"carriage": {"role": "mechanism", "carriedBy": "base"}},
  "solids": [{"name": "carriage plate", "group": "carriage", "shape": {"kind": "box", "fromMm": ["=post_x + 20", -130, 85], "toMm": ["=post_x + 26", 130, 145]}}]
}
```

- **One place for each kind of entry.** The top file keeps `schema`, `name`, `units`, `frame`, `parameters`,
  `custom`, `fixtures`, `battery`, `pieces`, `materials`, `motors` and `trials`. A top file that lists `subsystems` holds none
  of the subsystem entries; a subsystem file holds none of the whole-design ones. Each section has one definition,
  in `design.schema.json`, which the subsystem schema refers to.
- **Merged on load.** The library reads the top file, then each subsystem file in the order listed, and joins their
  sections into one design. Everything after loading (the build, the measures, the trials, `status`) sees only the
  merged design.
- **A name is defined once.** A group, solid, motion, pose, drive, adjustment, interaction or extra mass defined in
  two files is refused, and the message names both files. A solid's name is checked after its `each` rows are
  written out, and a subsystem solid may not take a fixture's name.
- **References cross files freely.** A solid names a group from another file, a group is `carriedBy` a group in
  another file, a mount or contact names solids anywhere, a motion starts `{"after": ...}` a motion in another file,
  and a drive's joint group and motor solid may be in any file.
- **Numbers come from the top file.** `each` rows and `=` expressions work inside subsystem files with the top
  file's parameters. A changed parameter reaches every file.
- **Paths are relative to the top file.** Subsystem files, part files (`part.file`) and custom code
  (`custom/<name>.py`) are all found from the top file's folder, wherever the subsystem file sits. Each subsystem file
  must be inside that folder and listed once.
- **Where an entry lives changes nothing measured.** Identities and `used` blocks come from the merged design. Solids
  are known by name and shape, so their order does not matter. Mounts, contacts and extra masses have no order that
  means anything, so the library keeps them sorted. Moving an entry to another file leaves every record current.
- **Problems name the file.** A problem in a subsystem file is reported as `subsystem "subsystems/carriage.json"
  solids[2] "carriage plate" ...`, with the entry's place in that file.
- **The source hash covers every file.** `sha256` (`sourceSha256` in records) is the hash of the top file's bytes
  followed by each subsystem file's bytes, in the order listed. For a design in one file it is that file's own hash.
  `Design.files` lists every file read.

A small design needs no subsystem files. One file without `subsystems` holds everything, as before.

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
| the same, with `"turnDeg": [a, ...], "turnAxis": [x, y, z]` | Follow the curve the same way and also turn, about the line through the followed point along `turnAxis` (right-hand rule), by the angle gained since the first point |

- `straight`: straight lines from point to point.
- `arc`: exactly three points; the circle through them, from the first, past the second, to the third.
- `smooth`: a smooth curve through every point (a centripetal Catmull-Rom spline: it passes through each point and
  does not overshoot between them).

A turning path gives one angle per listed point in `turnDeg`, and one `turnAxis` for the whole path. Between two
neighbouring points the angle grows evenly with the length covered: on an arc the middle point sits at its own share
of the length, and on a smooth curve each point at its knot. The turn is counted from the first point's angle, so the
path starts with no movement whatever that angle is, and any run of neighbouring points with their angles is itself
a path that does the same part of the movement. A quarter arc turned a quarter turn about its own axis is exactly a
swing about the arc's centre.

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
kind, volume, bounding box, mass, its range and where the mass came from); each group (role, carrier, members); the
weight with no solid; mounts; poses and motions with every number worked out, and for each drive command what it
works out to (`commands`: its group, the joint values it goes `from` and `to`, the `change` and the `motorTurns` it
takes); parts used (file, fingerprint, solid name); custom shapes used; the mass block; and the library version
and commit.

The mass block is the robot's weight, fixtures left out:

```json
"mass": {"totalKg": 24.6, "rangeKg": [22.9, 27.1],
         "groups": {"base": {"massKg": 15.2, "rangeKg": [14.1, 16.8], "from": "solids", "extra": ["wiring"]}},
         "unweighed": ["spool"]}
```

`totalKg` adds the nominal values. `rangeKg` adds the low ends and the high ends separately. Each robot group states
the same, with `from` (`solids` or `group massKg`) and the names of its extra masses. `unweighed` lists the robot
solids that no figure covers. The library states these numbers; a tool that judges compares them with its limits.

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
6. **A `path` operation turns about one fixed direction.** Its angle grows evenly with length between points, so a
   turn made standing still cannot be written, and a turn whose axis itself swings needs a `through` motion.
7. **Mounts are records, not constraints.** Nothing yet checks that the two solids meet at the mount point.
8. **A weight range is two ends added separately.** The low ends add to the low total and the high ends to the high
   total, as though every assumed weight were at its end at once. That is the safe bound, not a likely total. If a
   statistical spread is ever wanted, it belongs here as a stated choice.
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
17. **Trials in three dimensions.** The owner has decided: option A below, an optional engine adapter with MuJoCo
    as an optional extra. Fixed surfaces, driven surfaces and moved groups are built (section 16); "bring your own results" (option B) is not wanted.
    The options are kept for the record.
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
20. **A hand-off passes the piece's end state, and drive speeds when asked (`carryDrives`).** Flap angles start fresh.
21. **A joint has one degree of freedom and one drive per motion.** Two motors on one joint are one drive with
    `count`. A differential, or a joint two drives share by adding their movements, is not offered; it is two groups.
22. **A joint value read from a pose takes the turn inside the travel nearest 0.** A pose cannot say which whole turn a
    rotation joint is on; a chain of motions carries the exact value instead. If a joint ever travels more than a
    turn from a pose, the pose will need to state its joint values.
23. **A motor-driven motion's geometry moves each joint at an even rate, and its electrical load takes a triangle
    speed profile.** The placements share the stroke evenly, so the geometry needs no timing. `durationS` is the
    whole motion's time, and the electrical measure (12.7) speeds each joint up evenly over the first half and
    slows it over the second, the gentlest profile that makes the time. If a motion ever needs its own profile
    (a trapezoid, a speed cap), it belongs on the motion as a stated choice.
24. **The electrical load is a peak load.** Each drive's peak current is added to the others as though the peaks
    came at once, a motor's winding current is counted as drawn from the bus in full, and a back-driven gear is
    charged as though it were driving. All three overstate the load. Heat, a breaker's trip curve and how long a
    current lasts are not modelled. If a statistical or timed load is ever wanted, it belongs here.

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
   `path` moves at exactly the curve's length; a turning path adds its fastest turn (the largest change of angle over
   a share of the length) times the farthest corner's distance from the followed point. A `through` motion moves at its fastest screw. A carried solid adds
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
| `mass.roll_up` | What does it weigh, within what range, and where is the centre of mass, at a pose? | Per group and whole: `totalKg`, `rangeKg`, `centreMm`, `unweighed`. A solid's mass sits at the centre of its volume; a lump group mass is spread over the group by volume; weight with no solid is a point at the centre of the group's volume. A pose moves solids rigidly, so the centre as drawn is moved by the group's placement and no shape is measured again |
| `mass.inertia` | What is the inertia of these groups about this line, at a pose or a point of a motion? | `kgM2` and `rangeKgM2`, from each solid's second moments of volume times its mass over its volume, turned with its group and moved to the line; weight with no solid as a point. Unweighed solids are named |
| `compression.indentation` | How deep does a solid press into a ball or a round ring along a motion? | Deepest sample, and a proven ceiling |
| `electrical.measured` | What does a motion ask of its motors and the battery? | Per commanded drive: load, current, motor voltage; the bus voltage (12.7) |

`attachment` takes its own inputs as data: the touching `gap`, the `floor_z`, solids to `ignore` (a game piece, a
gauge), a `base` solid, and declared `contacts`. Without a `base`, the largest connected set is the base.

### 12.3 Workers

`measure/run.py` shares measuring work between worker processes and does no measuring itself. A clearance along a
motion is dealt out in shares of its pairs; rows come back in pair order, so the result is the same for any worker
count (tested). Every other job is one task. Tasks come back as each one finishes, so a job is stored as soon as its
last task is in. The caller chooses the count. The default is half the machine's cores.

### 12.4 The records: one file per job

Every measurement is a **job**: one question about a design, given as plain data. A tool that judges a design asks
for the jobs it needs, and the library keeps each answer as its own file:

```python
from frc_design_kernel.measure import records
records.record("design.json", [
    {"kind": "clearance", "motion": "lift", "minGapMm": 1.0, "includeStill": True},
    {"kind": "reach", "motion": "lift", "pair": ["hook", "bar"], "withinMm": 2.0, "window": [0.9, 1.0]},
    {"kind": "indentation", "motion": "squeeze", "piece": "ball", "contact": "roller", "maxDepthMm": 4.0},
], "out", workers=4)
```

writes `out/measurements/clearance.motion.lift.json`, `out/measurements/reach.lift.hook.bar.json` and
`out/measurements/indentation.squeeze.ball.roller.json`. The kinds, with their fields and defaults:

| Kind | Asks | Fields (default) |
|---|---|---|
| `clearance` along a `motion` | How close each pair comes over the stroke (12.1) | `minGapMm` (0), `depth` (9), `includeStill` (false), `nearMm` (0), `contacts` (`"declared"`), `absent` ([]), `displace` ({}) |
| `clearance` at a `pose` (`null` is as drawn) | The pairs closer than the gap there | `minGapMm` (0), `contacts` (`"declared"`), `absent` ([]) |
| `reach` along a `motion` | Do two solids come within a distance in a window (12.2) | `pair`, `withinMm`, `window` ([0, 1]), `absent` ([]), `depth` (9) |
| `indentation` along a `motion` | How deep a solid presses into a ball or ring (12.2) | `piece`, `contact`, `maxDepthMm`, `absent` ([]), `depth` (9) |
| `withdrawal` along a `motion` | How far the moved solids end from the rest (12.2) | `absent` ([]) |
| `attachment` at a `pose` | What touches what, what is loose, mounts, fixtures off the floor (12.2) | `touchGapMm` (0), `floorZMm` (0), `ignore` ([]), `base` (null), `contacts` (`"declared"`), `absent` ([]), `pairs` (true) |
| `mass` at a `pose` | Mass and centre of mass (12.2) | `absent` ([]) |
| `electrical` along a `motion` | Torque, current and motor voltage per drive, and the bus voltage (12.7) | `samples` (32) |

`contacts` is `"declared"` (the source's declared contacts for that motion, or those declared for every motion at a
pose, each with both solids present) or a list of pairs. A job with `displace` is a control (12.6b); it names its
own `contacts`, usually `[]`. A field the kind does not have, a missing one, or a motion, pose or solid that is not
in the design is refused, naming the job by its place in the list.

**File names.** A job's id is its file name: the kind, then what it is about, each name in lower case with anything
else turned into a dash: `clearance.motion.lift`, `clearance.pose.raised`, `clearance.drawn`,
`clearance.motion.lift.displaced.post`, `reach.lift.hook.bar`, `indentation.squeeze.ball.roller`,
`withdrawal.pin-out`, `attachment.pose.raised`, `mass.drawn`, `electrical.lift`. A job may give its own `"id"` (lower-case letters,
digits, dots, dashes and underscores). Two jobs with the same id in one list are refused; give one of them an id.

**One job file:**

```json
{"schema": "frc-design-kernel/measurement-job@1",
 "generator": {"library": "frc-design-kernel", "version": "...", "commit": "..."},
 "id": "indentation.squeeze.ball.roller",
 "job": {"kind": "indentation", "motion": "squeeze", "piece": "ball", "contact": "roller", "maxDepthMm": 4.0,
         "absent": [], "depth": 9},
 "inputs": {"rules": {"maxDepthMm": 4.0, "depthLimit": 9},
            "solids": {"ball": "3f9c0d2a71b84e65", "roller": "a07e5b1c9d2f3846"}},
 "used": {},
 "checked": {"measured": "whole"},
 "result": {"motion": "squeeze", "piece": "ball", "contact": "roller", "deepestMm": 2.0, "t": 1.0, "...": "..."}}
```

- `job` is the question with every field filled in.
- `inputs.rules` are the caller's numbers the answer depends on; `inputs.solids` the identity (12.4a) of every solid
  the answer depends on: every solid present for a clearance, a withdrawal or an attachment (the ignored ones left
  out), the two named solids for a reach or an indentation, and for a mass the solids whose shape the roll-up uses
  (those with a mass, and every member of a group with a lump mass or with extra mass, which sits at the centre of
  its group's volume).
- `used` holds the other design facts the answer depends on: for every job along a motion, the motion's resolved
  `start` (each group's whole placement at `t` = 0, carriers included, as 12 numbers, groups as drawn left out) and
  its `joints` (each commanded joint, by its group: `kind`, and the values it goes `from` and `to`), so a chained start
  is known by where it is and never by the motion it starts after, and a renamed drive changes nothing; a
  clearance's declared `contacts`; an attachment's
  `contacts`, `mounts` (notes left out), `fixtures` and a digest of which group each solid is in; a mass's `masses`,
  `massRanges`, `groupMasses` (each as value, low, high), `extraMass` (notes left out of the comparison),
  `unweighed` and the same group digest. A change to a range alone, or to any weight with no solid, makes it stale.
  An electrical job's are in 12.7.
- `checked` says what this run did: for a clearance, the pairs measured and carried (12.4a); for an attachment, its
  touching pairs and mounts measured and carried; for the others `{"measured": "whole"}`.
- A clearance also has `counts`: every pair, under exactly one of `declaredContacts`, `bothStill`, `farApart`,
  `fixedFarApart`, `measured` and `notInFocus`.
- `result` is the measure's own answer (12.1, 12.2), without the parts above.

**What a clearance file keeps.** Only the rows of pairs that needed more than the broad phase to settle: a pair
closer than the gap, a pair not settled, and a pair whose proven floor (`lowerBoundMm`) is under the gap plus
`nearMm`. A pair proven farther than that is counted under `measured`, not stored. `closest` is the closest kept row,
or `null` when none is kept. With the default `nearMm` of 0 a file holds the failures and their witnesses only; a
tool that wants near misses on a page asks for a band. On a carry a pair with no stored row is counted again by the
broad phase, which is cheap, so a carried file still equals a fresh one. On an invented design of 228 solids, 74
motions and 8 poses, the 106 jobs a judging tool asks for take 1.3 MB, most of it the solid identities.

**Written as each job finishes.** A job's file is written whole the moment its job is done: into a temporary file
beside it, then moved into place. A run is partial when a job asked for has no file; there is no flag and no file
rewritten as a whole. A stopped or failed run keeps every job it finished.

**Carried while current.** `record()` reads each job's file first. A job is **current** when its file's `job`,
`inputs` and `used` are what the design gives now, and it was measured whole (not under a focus alone). A current
job is carried: not measured and not written again, so its file's bytes do not change. Any other job is measured,
carrying from its earlier file what it can (12.4a), and its file is replaced. `carry=False` measures every job
afresh. `records.check(source, jobs, folder)` says, without measuring, which of the jobs asked are current, stale
(with what changed) or missing. Files of jobs that are not asked for are left alone.

`record()` returns one entry per job, in job order: `{"id", "kind", "action": "carried" | "measured", "file",
"record"}`, and calls `report(entry)`, when given, as each job is carried or finished.

**The command.**

```
python -m frc_design_kernel measure SOURCE --out DIR [--min-gap MM] [--touch-gap MM] [--floor-z MM]
                                                     [--ignore SOLID] [--workers N] [--depth N] [--near MM]
                                                     [--motion NAME] [--pose NAME] [--extremes]
                                                     [--carry] [--focus SOLID]
```

records a clearance job along every motion, an electrical job for every motion that commands a drive or lists one
under `alsoRunning`, and a clearance, an attachment and a mass job as drawn and at every pose (only those named with `--motion` and `--pose`), into `DIR/measurements/`. It prints one line per job as it
finishes, with numbers and counts, not verdicts, and then how many it wrote and how many were carried. `--extremes`
also writes `DIR/adjustments.json` (section 4.5c).

### 12.4a Measuring again only what changed

A pair's clearance depends only on its two solids, where each stands along the motion (or at the pose), and the
rules it was measured under. So every clearance result (`clearance.along`, `clearance.at_pose`, each
`run.clearances` job, each clearance job file) records its `inputs`:

```json
"inputs": {"rules": {"minGapMm": 1.0, "depthLimit": 9, "includeStill": true, "nearMm": 0.0},
           "solids": {"arm": "3f9c0d2a71b84e65", "post": "a07e5b1c9d2f3846"}}
```

(`nearMm` is a rule of a job file only.) Each solid's identity is a short digest of figures the build already
produces: its volume, the centre of its volume, its second moments of volume about that centre and its bounding box
as drawn; its group's whole placement along that motion or at that pose (carriers included); and any `displace`
shift. A solid absent from the case has no entry. At a pose the rules are the gap alone. No file bytes, names,
notes, status words or versions enter it, so a renamed design, a renamed solid or an edited note changes no
identity. The one limit: two different shapes with the same volume, centre, second moments and box would be taken
for the same solid.

Given an earlier result of the same question (`earlier=`, the job field `"earlier"`, or the job's file), only these
are measured:

- every pair with a solid whose identity changed, a new solid, or a solid named in `focus`;
- every pair whose declared contact changed (`measuredPairs`).

Every other pair is carried: its earlier row, if it had one, under its current names, and its place in `counts`
worked out as a full measurement would put it (contact, both still, or by the broad phase: far, fixed and far, or
measured), so the merged result equals a full measurement of the design as it is now. A renamed solid is found by
its identity alone and its rows are carried under the new name. A result with nothing to measure is not handed to a
worker at all. Every pair is measured when the rules differ, when the earlier result records no inputs, or when it
was only part measured.

Each result says what it did in `checked`:

```json
"checked": {"measuredSolids": ["arm"], "measuredPairs": [], "pairsMeasured": 7, "pairsCarried": 21,
            "pairsNotMeasured": 0, "renamed": {}}
```

`measuredSolids` is `null` when every pair was measured. `pairsMeasured` counts the pairs looked at now, including
those that boxes proved far apart (`counts.measured` is only the pairs that needed more than the boxes). `focus`
without an earlier result measures only the focus solids' pairs and leaves the rest out (`pairsNotMeasured`); such
a result is never carried from.

Attachment, mass, reach, indentation, withdrawal and electrical jobs are carried whole when current. A stale attachment still
carries from its earlier file: the touching gaps and mount distances of pairs of unchanged solids are copied, only
pairs and mounts with a changed solid are measured, and the sets, loose solids and fixtures are worked out again
from them. Its `checked` gives `pairsMeasured`, `pairsCarried`, `mountsMeasured` and `mountsCarried`, or
`{"measured": "whole"}` when nothing could be carried (such as across a new touching gap). The others are measured
whole when stale.

`measure --carry` carries from the job files already in `DIR/measurements/` (it refuses when there is no such
folder); `--focus SOLID` measures that solid's pairs again as well, or, without `--carry`, only those. Both print,
for each clearance measured, how many pairs were measured and how many carried.

On a design of about 230 solids, 74 motions and 75 poses, the decision costs well under a second beyond the build
(about 3 s); one solid moved measures its pairs along all 74 motions in about 12 s with four workers, and its pairs,
touching gaps and mounts at a pose in about 0.2 s, where a whole pose takes about 35 s for clearance and 40 s for
attachment.

### 12.5 For tools that only know the three old operations

`frc_design_kernel.sampled(design, motion, steps)` turns any motion, curved or through poses, into `steps + 1` still
placements. Each placement is written as at most one `rotation` and one `translation`, applied in full. An older
tool can read those as start poses.

### 12.6a Screen facts

`python -m frc_design_kernel screen SOURCE [--out DIR]` reports plain facts about each declared interaction, so a
tool that judges can decide, before any trial runs, how far a planar trial of it can be trusted. Nothing is labelled
good or bad, and nothing says which engine to use.

| Fact | What is reported |
|---|---|
| Piece symmetry | `sphere`, `body of revolution` (with its axis), `prismatic` or `general`, read from the faces of the piece's 3D shape. A ring is a body of revolution, not a sphere. A box or a prism is `prismatic` only when every face is flat: a box with rounded edges is `general`, because its section changes near every face. A cone is a body of revolution. |
| Section constancy | Each meeting solid is cut at the centre plane and at four more levels across the piece's width (plus `marginMm`). The largest difference between a section and the centre section is given in mm, with the level; levels where the solid is not cut at all (it ends inside the width); and in words which faces change across the plane: a cone or taper, a dome, a sloped face, a round face lying across. |
| Sideways hold | At each `pieceAtMm`, the gap from the piece to the nearest guide on each side along the plane's normal, or none (unguided). The probe is the piece's shadow pushed out sideways. |
| Mechanism in the plane | For each motion named, the moving groups whose hinge, or whose path's turn, is not square to the plane, whose slide crosses it, or whose path or poses leave it. |
| Pieces at once | The number the interaction declares. |
| Squeeze ratio | When a drawn piece solid and a motion are named: the deepest any meeting solid presses into the piece along that motion (the compression measure), divided by the piece's thickness, and where. |
| Not rigid | The involved solids whose `material` is compliant or flexible, with what was declared. |
| Echoed | `approach` and `targetOffPlane`, as declared. |

### 12.6b For other tools

- `attachment.at_pose(..., pairs=False)` gives the connected sets, loose solids and fixtures off the floor without
  the full list of touching pairs, measuring only what the sets need. It is much quicker on a detailed scene.
- A pair that keeps its relative pose is measured once per process and remembered by the two solids and where each
  stands, so the same pair in another motion costs nothing.

- `clearance.along(..., displace={solid: [dx, dy, dz]})` and the job field `"displace"` shift named solids for one
  question, with no second source file: a control that shows a check can report an interference.
- `frc_design_kernel.placements(design, pose=None, motion=None, t=0.0)` gives `{group: 12 numbers}`.
- `assembly.mesh(name, deflection_mm)` gives a solid as triangles.

### 12.6c Piece geometry: each piece's shape on its own

```
python -m frc_design_kernel piece-geometry PIECES.json --out GEOMETRY.json [--linear-mm 0.2] [--angular-rad 0.3]
```

measures game pieces with no design source. It gives the numbers a tool needs to work out where a piece can go,
such as a delivery envelope: the piece's bounds, volume, symmetry, a convex hull that holds it and any hole through
it. It does not say whether a piece fits anything.

**The input** is a design source's own `pieces` block: `{"pieces": {name: {"shape": {...}, ...}}}`. Only `shape` is
read. `massKg`, `note` and any other field are ignored, so a block copied from a design source, or written by another
tool, is read as it is. Each shape is checked against the schema's shape definition, then its `"=..."` texts are
worked out with no parameters, then it is built as one solid. An expression that names a parameter is an error for
that shape (`the expression "=tall" uses "tall", but piece-geometry has no parameters. Fix: Write the number
itself`). A `custom` shape is refused, because it needs a design folder and its code (section 6).

**The record** is always written, even when some shapes fail:

```json
{"schema": "frc-design-kernel/piece-geometry@1",
 "generator": {"library": "frc-design-kernel", "version": "0.1.0", "commit": "..."},
 "used": {"library": "0.1.0", "meshing": {"linearMm": 0.2, "angularRad": 0.3}},
 "shapes": {
  "ring": {"ok": true,
           "identity": {"kind": "torus", "volumeMm3": 1850550.825, "boundsMm": [[-15, -180, -145], [35, 170, 205]]},
           "boundsMm": [[-15, -180, -145], [35, 170, 205]], "volumeMm3": 1850550.825, "centreMm": [10, -5, 30],
           "symmetry": {"class": "body of revolution", "axis": [1, 0, 0]},
           "hullMm": [[-15.159, -156.864, 32.566], ...], "hullToleranceMm": 0.228,
           "bore": {"diameterMm": 250, "axis": [1, 0, 0], "centreMm": [10, -5, 30]}},
  "fat ring": {"ok": false, "error": {"where": "pieces \"fat ring\" shape",
                                      "problem": "minorRadiusMm must be smaller than majorRadiusMm",
                                      "fix": "A ring needs a hole through its middle"}}}}
```

| Field | What it is |
|---|---|
| `identity` | The built solid's kind, volume and bounds. A tool that keeps a record compares these with a fresh run to tell whether the shape changed. It is figures, never a fingerprint of the file, so rewriting the file or a note changes nothing. |
| `boundsMm`, `volumeMm3`, `centreMm` | The box fitted to the true surfaces, as `[[low x, y, z], [high x, y, z]]`; the volume; the centre of volume. Positions to 0.0001 mm, volume to 0.001 mm³. |
| `symmetry` | `sphere`, `body of revolution` with its axis, `prismatic` or `general`, as in screen facts (12.6a). |
| `axis` (in `symmetry` and `bore`) | A unit direction, written one way: its first component that is not zero (larger than 10⁻⁹) is positive. A pipe drawn from its top end down and one drawn from its bottom up give the same record. |
| `hullMm`, `hullToleranceMm` | The corners of a convex hull that holds the whole solid, and how far it was grown (below). |
| `bore` | A hole straight through, by the one rule below, or `null`. |

`used` gives the library version and the meshing the hull was made with. The `status` command does not read this
record: there is no design source to compare it with.

**Exit codes.** 0 when every shape was measured. 1 when any shape failed: the file is still written, and each failed
shape gets one line on stderr, `Error: where: problem. Fix: fix`. 1 also when the file is missing, is not JSON or has
no `pieces` block, or when `--out` cannot be written (a folder, or a place with no write access); then nothing is
written. 2 for a usage error: no `--out`, or a `--linear-mm` or `--angular-rad` that is not a finite number greater
than 0 (`hull()` itself refuses such a value with a DesignError).

**The hull holds the true solid** (`kernel/hull.py`: `hull(shape, linear_mm=0.2, angular_rad=0.3)`, and
`planes(points)` for the faces of the hull of any points).

- The solid is meshed into triangles at the linear deflection `--linear-mm` and the angular deflection
  `--angular-rad`. The mesh's corners lie on the true surface, but its flat triangles cut inside a round one, so the
  hull of the corners alone sits a little inside the solid: up to 0.15 mm inside a ball 120 mm across.
- So each face of that hull, each face of the box fitted to the true surfaces, and the trimming planes described
  below are pushed outward by t. The corners where the pushed planes meet are reported, each coordinate rounded away
  from the middle to 0.001 mm.
- t is 4/3 of the largest gap between the middle of a triangle edge and the true surface, plus 0.002 mm for the
  rounding and the arithmetic, rounded up to 0.001 mm. Over a small triangle the gap is close to a quadratic (a curve
  shaped like a parabola) that is zero at the triangle's corners, and such a curve rises at most 4/3 of its largest
  edge-middle value. A solid with any round face takes at least `--linear-mm`, the deflection the mesher is asked
  to keep to. The gap has to be measured as well, because the mesher can overshoot its deflection on a round face
  meshed as a grid. On a ball 50 mm across at 0.2 mm the gap reaches 0.40 mm: a hull grown by 0.2 mm alone leaves
  0.05 mm of the ball outside. There t is 0.542 mm. A solid with only flat faces is meshed exactly, so its gap is 0
  and t is 0.002 mm.
- Each edge middle is projected onto its face's surface. Near the face's edge, the surface's nearest point can lie
  past that edge, where it is not part of the solid: at a frustum's narrow rim, or a ball with a slice cut off. The
  projection then finds no point, or only one on the far side of the surface. Such a middle is measured to the
  trimmed face itself instead, which never understates the gap.
- The hull is found by quickhull, on points snapped to a grid 2⁻⁴⁰ of their size, so every inside-or-outside test is
  exact and near-flat clusters of points cannot tangle it. Points that all lie on one line or in one plane enclose
  no volume and are refused.

**Thin rims are trimmed.** Where two faces of the ungrown hull meet at a small angle, as at the rim of a flat cone
or a lens, pushing both out moves the line where they meet far outward: by t over the sine of half the angle between
them. A cone 200 mm across and 2 mm high would reach 20 mm past its rim at t = 0.2 mm. So at every edge and corner
of the ungrown hull where the faces turn by more than 15 degrees, trimming planes are added whose directions fill the
turn, none more than 15 degrees from the next or from a face. Each plane touches that corner and is pushed out by t
like the faces. That cone now reaches 0.207 mm past its rim.

**What "within the tolerance" means.** The guarantee: the hull holds the whole solid, and no point of it lies more
than t / cos 15° (1.036 t) plus 0.002 mm outside the hull of the mesh's corners. That hull lies inside the solid's own
convex hull, so for a convex solid no hull corner is farther than that from the solid; for a solid with a hollow or
a notch, the bound is to its convex hull. At t = 0.202 mm the bound is 0.211 mm. The hull also stands at most t
clear of a flat face of the solid, and its extent along x, y or z exceeds the solid's by exactly t on each side. On
a box, each hull corner is within t of the box's corner along every axis.

**The bore, by one rule.** A shape that classifies as a body of revolution has a bore straight through it when its
axis line does not meet the solid. The line is drawn through the centre of volume, which lies on the axis of every
body of revolution, and runs well past the bounding box. The diameter is twice the line's smallest distance from the
solid. The centre is the centre of volume, the point of the axis nearest it. This covers a ring (2 × (major radius −
minor radius)), a round tube (outer diameter − 2 × wall) and a disc with a hole cut through it. A solid bar, a cone,
a ball, a box and a cup closed at one end give `null`. Only a hole on the axis of a body of revolution is reported:
a disc with a hole drilled off its centre is not a body of revolution (`general`), and its bore is `null`.

**Limits.**

- Where a slanted cut meets a round face, a chord along that edge may be measured to the uncut surface, which is a
  little less than the edge curve's own bulge. The mesher keeps each edge's chords within `--linear-mm` of the edge,
  and t is never below that, so the hull still holds. A test with a ball cut on a slant checks this.
- The record is large: a ball 120 mm across has about 3,000 hull corners, one 240 mm across about 5,000, and a disc
  200 mm across about 2,300. Pushing the faces out turns each corner of the mesh's hull into a small cluster of
  corners, and the trimming planes add more along every sharp edge.
- One solid per shape, and no mass, inertia or orientation. Whether a piece can be delivered is for the tool that
  reads the record.

### 12.6 What the measure layer leaves out

- **Guidelines and verdicts.** No built-in gap, no "floating is an error", no pass or fail.
- **Reading evidence files.** A declared contact is a pair of names. Whether a trial justifies it is not asked here.
- **Weight limits and electrical budgets.** The library states the mass and its range, the currents and the bus
  voltage; comparing them with a limit or a minimum is a judging tool's work.
- **Electrical physics beyond the bus.** Heat, a breaker's trip curve and how long a current lasts (decision 24).
- **Progress lines, receipts and advice text.**
- **Line-of-sight checks** and the advisory test for a solid that turns about its own axis. They can be added as
  measures when a second project needs them.

### 12.7 The electrical load of a motion

The question: what does a motion ask of its motors and of the battery? `measure/electrical.py` answers it as the
`electrical` job, one per motion that commands a drive or lists one under `alsoRunning`. A motion with neither has
no electrical load, and asking for one is refused.

**The load.** Every drive the motion commands, plus every drive it lists under `alsoRunning` (4.7). Nothing is
picked by hand: placing a motor and commanding it is what puts it in the load.

**Each commanded drive**, worked out at `samples` + 1 even stroke fractions (32 by default):

1. **The moved groups** are the joint's group and every group it carries, at any depth. Their weight comes from the
   mass roll-up (4.2, 4.3a): each solid's share at the centre of its volume, a lump spread by volume, extra mass at
   its group's centre. Fixtures are not weighed, so a carried game piece's weight is stated as `extraLoad` or
   `extraMass`.
2. **The joint's line** rides on its group's carrier: at each fraction it is placed by the carrier's placement, so a
   wrist on a moving arm is worked out about where its pivot is.
3. **Gravity** (9.80665 m/s^2 along -z) on the moved groups about the joint: the torque `(r x m g) . axis` about a
   rotation joint, in N m, or the force `m g . axis` along a slide, in N. The worst over the motion is reported.
4. **Acceleration** from the speed profile, a triangle (decision 23): the joint speeds up evenly over the first half
   of `durationS` and slows evenly over the second. Its acceleration is `4 * change / durationS^2` and its peak
   speed `2 * change / durationS`, at mid-stroke. The inertia is the moved groups' about the joint's line
   (`mass.inertia`) for a rotation, or their mass for a slide.
5. **The load at the joint** at each fraction is `inertia * acceleration - gravity` (signed along the joint, speeding
   up over the first half and slowing over the second, both at mid-stroke). `peak` is the most of it over the
   motion, the still loads at the start and the end included, plus `extraLoad`. `hold` is the still load at the end,
   gravity plus `extraLoad`: what holding there takes.
6. **Current per motor** from the motor model (`motor.py`): the load as a torque at the gear's output (a slide's
   force times `perOutputTurn / 2 pi`), over `kt * gear * efficiency * count`. `neededA` is what the peak needs.
   `currentA` is that clamped at the drive's **limit**, the lower of its stated `statorLimitA` and `supplyLimitA`
   (`null` when it states neither), and `clamped` says whether the high end was cut. `holdA` is the hold's current.
7. **Required motor voltage** at the peak speed: `neededA * ohm + ke * motor speed`, the motor speed being the
   output's turning speed times `gear`. Peak current and peak speed are taken together, which overstates it.
8. **Bus current** of the drive: `count * currentA`.

**Each drive running beside it** draws its `currentA` (the whole drive), or `count` times its limit for `atLimit`,
at both ends.

**The bus** sums every drive's bus current `I` and takes the battery (4.5b): `[Voc low - I high * R high, Voc high
- I low * R low]`, with the nominal `Voc - I * R`. Without a battery `bus` is `null`.

**Ranges.** Every figure is `{"value": nominal, "range": [low, high]}`. The weights are taken all at their low ends
or all at their high ends at once, as the roll-up adds them (decision 8); each load's range is the least and the
most over those and the two ends of `durationS`. The current's low end takes the high `kt` and efficiency, its high
end the low ones. The motor voltage's high end takes the high `ohm` and `ke`. The bus's low end is the weak pack
under the high current.

**Conservative peaks.** The record says so in `conservative`: each drive's peak current is added as though the
peaks came at once, and a motor's winding current is counted as drawn from the bus in full (decision 24). Efficiency
divides the torque whichever way the load turns the gear.

**One job file** (`electrical.<motion>`; `job`, `inputs`, `checked` as in 12.4):

```json
{"job": {"kind": "electrical", "motion": "raise", "samples": 32},
 "inputs": {"rules": {"samples": 32}, "solids": {"arm bar": "1f0e9a2b3c4d5e6f"}},
 "used": {"start": {}, "joints": {"arm": {"kind": "rotation", "from": 0.0, "to": 30}},
          "masses": {"arm bar": 2.0}, "massRanges": {"arm bar": [2.0, 2.0]}, "groupMasses": {}, "extraMass": [],
          "unweighed": [], "groups": "9a8b7c6d5e4f3a2b",
          "drives": {"pivot": {"motor": {"ktNmPerA": [0.02, 0.019, 0.021], "ohm": [0.05, 0.045, 0.06], "keVsPerRad": [0.02, 0.019, 0.021]},
                               "gear": 60, "count": 1, "efficiency": [0.9, 0.85, 0.95], "limits": {"supplyLimitA": 40},
                               "joint": {"group": "arm", "kind": "rotation", "axis": [0, -1, 0], "originMm": [0, 0, 500], "travel": [-10, 120]}}},
          "durationS": [0.5, 0.4, 0.7], "extraLoad": {}, "alsoRunning": [],
          "battery": {"openCircuitV": [12.6, 12.2, 12.9], "resistanceOhm": [0.02, 0.015, 0.03]}},
 "result": {"motion": "raise", "profile": "triangle: ...", "samples": 32, "durationS": {"value": 0.5, "range": [0.4, 0.7]},
            "drives": {"pivot": {"group": "arm", "kind": "rotation", "moved": ["arm"], "count": 1, "change": 30.0,
                                 "load": {"unit": "N m", "gravity": {...}, "acceleration": {...}, "extra": {...}, "hold": {...}, "peak": {...}},
                                 "peakSpeed": {"unit": "deg/s", "value": 120.0, "range": [85.7, 150.0]}, "motorRadPerS": {...},
                                 "neededA": {...}, "limitA": 40.0, "clamped": false, "currentA": {...}, "holdA": {...},
                                 "motorV": {...}, "busA": {...}, "unweighed": []}},
            "alsoRunning": [{"drive": "wheels", "from": "atLimit", "busA": {"value": 160.0, "range": [160.0, 160.0]}}],
            "bus": {"loadA": {...}, "openCircuitV": [12.6, 12.2, 12.9], "resistanceOhm": [0.02, 0.015, 0.03], "volts": {...}},
            "conservative": "conservative: each drive's peak current is added ..."}}
```

**What it uses** (`used`): the motion's resolved `start` and `joints` (12.4); the moved groups' weights (`masses`,
`massRanges`, `groupMasses`, `extraMass`, `unweighed`, the group digest); each drive in the load (its motor's
figures, `gear`, `count`, `efficiency`, `limits`, and a commanded drive's `joint`); `durationS`, `extraLoad` and
`alsoRunning`; and the battery's two figures. `inputs.solids` holds the identities of the moved groups' robot
solids. Each sourced figure is kept as (value, low, high) and notes are left out, so a note edit, or the weight of a
solid the motion does not move, leaves the record current, and a changed mass, range, motor, gear, duration, drive
beside it or battery figure makes it stale. The result names each drive, so a renamed drive does too. The job takes
a few milliseconds beyond the build, so it is carried whole or measured whole.

**What it does not say.** Whether the bus is high enough, or a current low enough, is for a tool that judges. The
library compares nothing with a minimum.

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
| `engine` | Which engine runs it. `planar` is the default. `mujoco` is the optional 3D engine (section 16). Both read the same definition. |
| `assumes` | What this trial takes for granted beyond the engine's standing assumptions: a list of `{"id", "text"}`. Without it the trial is incomplete. |
| `plane` | The flat section the trial lives in: square to one axis (`normal`), at a level (`atMm`). Gravity acts down the second in-plane axis. |
| `pose` | The named pose the solids are in. |
| `piece` | `{"use": name, "start": ...}`: a piece from the design's `pieces`, and where it starts (point, velocity, spin) or `{"after": trial}` to start where another trial's piece ended. |
| `surfaces` | What the piece can touch. Each names a `material` and one of: `solid` (the outline where the plane cuts that named solid), `segmentsMm`, `circleMm`. A solid that a drive turns runs with that drive. A typed surface may state `speedMps`. |
| `flaps` | Hinged, sprung flaps: hinge point, length, rest direction, inertia, preload, spring, damping, a travel limit. |
| `commands` | How each drive is commanded: `imposed` (a speed), `voltage`, a `speed` loop or a position `hold`; bus voltage; and `rules` that change the command when a condition holds. |
| `planar` | Choices that belong to the planar engine only: the friction law (`stick` or `smooth`) and its two constants, and where on the piece a contact acts. |
| `air` | `{"densityKgM3": ...}`: the piece flies through still air of that density, with the drag and lift numbers its piece entry states (section 13.2). Without it there is no air. |
| `loads` | The frame the piece rides in speeding up or slowing down: an acceleration along a direction, as a step or a half-sine pulse, at a time or after an event. |
| `movers` | A steady slide of chosen surfaces, started at a time or after an event: a stated velocity, or a straight motion of a group from the design source. |
| `frames` | Where the piece is in a group's own drawing coordinates: `{"cassette": {"group": "Cassette", "mover": "approach"}}` adds `cassette.xMm` and `cassette.zMm` (the plane's two axes). They are measured before the group's own `place`, the pose and the mover's motion, so a seat test is written where the mechanism was drawn and holds while the robot drives. When the solids were drawn in another pose (taken from a STEP file, say), the frame's own `place` sets its origin and axes within the drawing. |
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
- **Motors.** Torque from current, back-EMF from speed, winding resistance, gear and efficiency (`motor.py`, the same
  model the electrical measure uses); a winding current limit and an optional supply limit. Bus voltage `null` is power off (coasting); 0 is shorted windings (a brake).
- **Air**, when the trial states `air`. Drag is 1/2 rho Cd A v^2 against the piece's motion through still air. Lift
  is the spin's Magnus force, 1/2 rho A Cl v^2 along spin x velocity, with Cl = `liftSlope` times the spin ratio
  (spin times radius over speed), capped at `liftMax` when it is given. `dragCoefficient`, `frontalAreaM2`,
  `liftSlope` and `liftMax` sit on the piece in the design source and the density on the trial, each a physical input
  with its source, so ranges, coverage and sensitivity reach them. Spin does not decay and the piece's attitude does
  not change its area; the record states that as the standing assumption `air-law` in place of `no-air`. The signals
  `air.dragN` and `air.liftN` give the two forces. Both engines use the same law (`trials/air.py`).
- **Integration.** Fixed step; forces from the state at the start of the step; speeds advance before positions.

Tests hold the solver to closed-form answers within 1%: free flight, drag deceleration, terminal speed, the Magnus circle and its cap, both friction laws at the slope threshold, a
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
5. **Coverage.** For each adjustment the trial names: at each end of each uncertain input's range where the outcome
   changed (an input that held needs no adjustment, and costs no runs), the adjustment's
   own range is searched for settings that pass. A few points are tried (both ends and the nominal setting), and
   the edge between a passing and a failing setting is closed in on by halving, twice. The record then states, per
   uncertain input and adjustment, the window of settings that passes at the low end and at the high end, whether
   some setting passes at each, and whether one fixed setting passes at both (and which).
6. **A grid only when asked.** `"grid": {"inputs": [...]}` also runs every combination of those inputs' range ends.

A change to null removes the thing it names, except a `busV`, where null is the power off. A change is a path into the trial's case (`materials.tread.friction`, `commands.belt`,
`loads.braking.accelerationMps2`; list items by name) or a design parameter (`parameters.squeeze`). A parameter
change rebuilds the design, so the real solids move.

The result is one word, with findings in plain text:

| Result | Meaning |
|---|---|
| `incomplete` | The method lacks something: no control, no stated assumptions, an input with no stated source, or nothing with a range. Reported even if the nominal run met the criterion. |
| `failed` | The nominal run did not meet the criterion. |
| `control not rejected` | The control met the criterion, so the trial does not show what it claims. |
| `not converged` | The outcome changes at half the step. |
| `not covered` | The outcome changes inside an input's assumed range, and no adjustment named by the trial has a setting that passes at each end of that range. The record says which input, between which two values, and what each adjustment could reach. |
| `covered by adjustment` | The outcome changes inside an assumed range, and an adjustment recovers it: some setting passes at each end. The record gives the windows and whether one fixed setting passes at both. |
| `passed` | Criterion met, control rejected, half step agrees, and the outcome holds across every assumed range as drawn. |

These words state what the method found. Whether a design may go forward on them is for the tools that judge.

**Sensitivity before fidelity.** From the same one-at-a-time runs the record ranks the inputs by how much they move
the outcome: first the ones that change it, then by the largest change in any measure as a fraction of its nominal
value. The top of that list is the input the result leans on most: the one an adjustment should reach first. It costs no
extra runs.

### 13.4 Cost before it runs, time after

`campaign.estimate` counts the most runs and steps a campaign can take and a rough time, at each engine's own pace
(about 200,000 steps a second planar, about 2,000 in 3D on a pickup scene). `try` prints that before
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
- `fit`: the piece's path as **one `path` operation** within `fitToleranceMm` of every trace sample. When the trace
  has the piece's spin, the path also turns: `turnDeg` is the spin summed over the trace (0 at the first sample),
  `turnAxis` the plane's normal signed the way both engines count spin, and a point is also kept where the angle
  strays by more than the turn tolerance (5 degrees; a trial field `fitToleranceDeg` is planned). `throughMm`,
  `turnDeg` and `atS` have one entry per kept point. Only the turn in the plane is fitted, and a turn made standing
  still shows as `maxTurnDeviationDeg` rather than being written.

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
- A flap's angle carried from one trial into the next. (A drive's speed can be: `"start": {"after": trial,
  "carryDrives": true}`. Several pieces loading one drive at once is `"piecesOnDrive": n` on its command.)
- Surfaces carried by a turning motion of the design (only straight slides).
- A flap that is not a one-way sprung flap (a powered or two-way hinge).
- A rope, winch or spring between bodies.
- Anything in three dimensions.

## 14. Records say what they used

The intended way of working is in stages: arrange and measure, then planar trials, then a fuller check on the
settled layout. When a later stage finds a problem, the author changes the design source and comes back up, running
again only what the change touched. To make that possible:

- Every measurement job record carries its `inputs` (its rules and the identity of each solid its answer depends
  on) and a `used` block (the other design facts it depends on: contacts, mounts, fixtures, masses, and for an
  electrical load its drives, the battery and what runs beside it), sections 12.4 and 12.7.
  Every trial record carries a `used` block: the solids it drew on, each with its group, kind, volume, bounding box
  as drawn and mass; the motions it follows, as their resolved stages (so a chained start counts by where it is),
  and the pose; the parameters its numbers were worked out from, with their values.
- `python -m frc_design_kernel status SOURCE DIR` works those out again from the source as it is now, for every job
  file under `DIR/measurements/` and every trial in `DIR/trials.json`, and prints, per record, `current` or
  `stale` and what changed: `solid "belt bed" changed`, `massRanges "gate" changed: [0.2, 0.2] to [0.3, 0.3]`, `the motion
  "lift" is no longer in the source`, `parameter "squeeze" changed: 20 to 15`, `the trial definition changed at
  materials.tread.friction.value`. Plain facts. It does not say whether to run anything again, and it decides from
  what each record's answer depends on, never from file bytes. It ends with how long it took, the build included:
  0.4 s on the 228-solid design of section 12.4, and about 2 s expected on a design whose build reads a large STEP
  file. `status()` returns the same as `seconds`.
- A design's name and every `note` are outside all identities. Renaming a design or editing a note makes nothing
  stale.
- A targeted rerun is one command: `measure --motion NAME` or `--pose NAME`, and `try --trial NAME`. Each writes
  only its own records and keeps the rest.
- `measure --carry` goes further: a current job is not measured at all, and inside every stale clearance it
  measures only the pairs whose solids, placements, rules or declared contacts changed, carries the rest, and says
  which (section 12.4a). It decides from figures the build already produces, so the decision takes seconds and a
  rename or a note measures nothing.

A clearance along a motion, a withdrawal and an attachment use every solid present: any of them may be the obstacle
or the support. A reach or an indentation uses its two named solids, and a mass the solids it weighs. A trial uses
only the solids its plane cut.

`status` also prints the facts a 3D engine would need settled (section 15).

## 15. When to go beyond planar, and what planar hands on

### 15.1 Escalation, in plain words

- **Use planar when the question is planar**: the piece moves in one section, what it touches is the same along
  its width, and one piece is enough to answer.
- **Go to 3D when the answer depends on what planar cannot see**: the piece's orientation (it can tip, yaw or
  arrive skewed), contact off the section plane (an end, a corner, a side wall), or many bodies at once.
- **Go to 3D when a planar result that a decision hinges on is not covered and no adjustment can be added to cover
  it**, and the doubt is about something planar cannot see. First look at the sensitivity ranking and the coverage
  windows: a wider slot or a setpoint range is usually cheaper than a fuller engine.
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
   would have to be driven along a path); drives not tied to a solid; trial surfaces that were typed in; and pieces
   whose shape is not a ball, a cylinder, a tube or a sharp box (`piecesNotPrimitive`), a box with rounded edges
   among them. A cone and a rounded box count as convex; a torus is reported as `a ring (a torus)`. How a shape was
   built from boxes, cylinders and unions stays in the design source, so an exact convex breakdown can be worked out
   later; it is not thrown away at export.
7. **Results hand forward.** Each trial's `handForward` block gives the nominal inputs, the range each held over,
   the marginal edges, the sensitivity order and the control, so a later engine can run the nominal case and only
   the marginal edges, with the same control.

## 16. The MuJoCo engine (optional, in stages)

A trial that writes `"engine": "mujoco"` is run in three dimensions by MuJoCo, behind the same trial definition, the
same method (nominal, half step, control, ranges, coverage) and the same record. The record stamps the engine's name
and version, and repeats the engine's own standing assumptions.

**Optional.** MuJoCo is an extra:

```
pip install "frc-design-kernel[mujoco] @ git+https://github.com/ehartye/frc-design-kernel"
```

The library never imports it unless a trial names that engine. Without it, such a trial is refused with that
install line. `mujoco_scene.py` writes the model as plain text and imports nothing; only `mujoco_run.py` imports
MuJoCo.

**How the scene is made from the design source.**

- Each solid the trial names becomes a fixed body at the trial's pose. A sharp box, a ball and a full cylinder
  become that exact primitive. A cone and a box with rounded edges are convex but have no primitive, so each becomes
  one convex mesh of its triangles at 0.2 mm. A union becomes its parts. A prism with a convex outline becomes its
  exact hull.
- A hollow or cut shape whose construction allows it is run as its **true convex pieces** (`trials/convex.py`): a
  rectangular tube as four walls, a sharp box with sharp boxes cut out as the boxes that are left (a rounded box is
  never split this way), a prism of any outline as triangles pushed through (all exact); a round tube as a ring of
  24 wedges and a pie slice as slices of at most a half turn (their round faces become flat facets, and
  `saw.faceted` states by how much).
- Anything else (a shape cut by a round, a custom shape, an imported part) is **split at its own faces**
  (`kernel/split.py`). A solid is convex when all of it lies on the inner side of each face's plane: the plane of a
  flat face, or a plane touching a round face that bulges outward. Where some of it does not, that plane cuts it in
  two, and each half is split again. A bracket, an angle, a bevelled blade or a plate with windows from a supplier's
  STEP file comes apart into exact convex pieces. A cut the CAD kernel's splitter will not take (a plane lying exactly
  on an edge of an imported part) is tried again 0.001 mm to either side.
- **A round face that dips inward is wedged about its own axis.** A bore, a countersink, a belt's wrap round its
  pulley, the inside of a relieved land: each is an inward cylinder or cone. Planes through its axis halve it until no
  wedge spans more of it than keeps the flat chord within **0.2 mm** of the arc (`FACET_MM`); a plane through a wedge's
  chord cuts it again if any other material lies in front of that chord. Each wedge is then convex but for the
  sliver between chord and arc, and is run as flat facets. The record states the most any wedge of a solid sits inside
  its face, under `saw.faceted` (`"its inward round faces (bores, countersinks, wraps) as flat facets, at most 0.06 mm
  inside them"`), beside the construction notes above. The test fixtures are a bore, a countersink, a belt wrap, a
  relieved roller land and a cross-drilled block; each is checked against its own surface, not the splitter's word.
- **Only a truly rough piece is hulled.** A face no wedge about one axis can make convex (a free-form face, a torus,
  an inward ball such as a dimple) leaves its piece rough, as does a piece that will not cut or would take a solid past
  128 pieces. Wedging still runs on such a piece first, so what is left rough is as small as it can be. A rough piece
  is used as its convex hull, which fills its hollow. The record lists every solid with such a piece under
  `saw.hulled`, and the share of its volume in them under `saw.hulledShare`. **When a piece pressed into a rough
  piece's own hull during any run, the result word says so** (`passed, on a hulled surface`), `touchedHulled` names
  the solid and a finding explains: the outcome may rest on a surface that is not there. Each MuJoCo run lists those
  solids under `touchedRough`; a touch on the same solid's exact pieces does not count.
- The piece is a free body built from its one 3D definition: its shape, its mass, and the inertia that shape gives.
  The planar start (point, velocity, spin) is placed on the trial's plane.
- **The contact law is the library's own, the same one the planar engine uses** (`trials/mujoco_contact.py`).
  MuJoCo does two jobs: it finds where shapes overlap, and it moves the bodies. At each touching point the library
  works out the spring and damper force along the normal and the friction across it (the stick law by default, or
  the smooth law, as the trial's `planar` options say) and applies it to the piece, and back onto a flap or another
  piece. So a material's stiffness, bounce and friction mean the same thing in both engines. Each step is two
  passes: one with MuJoCo's contacts on, only to find the overlaps, and one with them off, to move everything.
- **Why not MuJoCo's own contact forces.** They were tried first, with each material's spring and damper mapped
  onto MuJoCo's soft contact. One contact at a time agreed with planar within a few percent. A squeeze did not: a
  block pressed 1 mm into each of two surfaces of 200 N/mm should feel 200 N, and MuJoCo gave 4200 N. Across the
  settings tried the error ran from 4 to 21 times. A resting piece also sank to a twentieth of the spring's depth,
  and a contact that kept slipping raised its own pressing force and chattered. Squeeze force is a decision signal
  for grip and structure, so the engine's own solver is not used for contact.
- **One rule is added for three dimensions.** Where a piece touches one surface at several points (a ring lying
  flat touches at dozens), the surface's spring is shared among the points by depth: the surface presses with its
  stiffness times the deepest overlap, split between the points in proportion to their depths. One point gets it
  all, as in planar.
- **A round piece meets an edge or a corner at its true direction.** Where a ball or a ring's round segment meets a
  shape MuJoCo collides by its general convex method (a mesh or a cylinder), MuJoCo reports the nearest face's
  direction at an edge or a corner, and too shallow a depth. On a ring pressed onto a bevelled lip the direction was
  22 to 37 degrees off, so the lip pushed the ring along the floor instead of lifting it. The library works each such
  point out again from the piece's core (the ball's centre, or the segment's centre line): the nearest point of the
  shape to the core gives the direction and the depth, measured by MuJoCo's own distance query, which is exact while
  the core is outside the shape. Boxes, balls and the floor already come out exact and are left as MuJoCo gives them.
- **A driven surface** is any solid a declared drive turns (`turns`): a roller, a wheel or a belt. It stays a still
  shape. Its surface runs at the drive's speed across the turn's axis, and the friction law sees that speed. The
  friction along the surface loads the drive's motor model, so current and sag come out as in planar.
- **A moved group** is a group whose surface names a mover that follows a design motion. One slide becomes a slider,
  one turn becomes a hinge, and its joint is set each step so contact feels its speed. Any other motion (several
  steps, a path, a motion through poses) is carried along its path, and its speed is not felt in contact; the record
  says which under `saw.bodies`. A group carried by a moving group takes its carrier's movement too. Mechanisms are
  driven, not driving: contact cannot push one off its motion.
- **A driven surface on a moved group** adds the group's own speed at the point of contact (not for a path-carried
  group, whose speed is not known to the engine).
- **A ring piece** (a torus) is a closed chain of straight round segments along its centre circle, 32 unless the
  trial says otherwise (`"mujoco": {"ringSegments": 48}`); its hole is real. The record states the count, so a trial
  can be repeated with more to show the count does not decide the outcome.
- **A flap** is its drawn solid (`"solid"` on the flap) on a hinge about the plane's normal at `hingeMm`, with the
  same spring, preload, damping, inertia and limit the planar engine reads. Its stops do not bounce. In both
  engines a flap opens counter-clockwise in the trial's plane, or clockwise when `limitDeg` is written negative;
  the angle reported is how far it has opened. A flap that names a mover rides that moved group.
- **A load** is the same data and the same force as in planar.
- **More than one piece.** A trial may list `others`: more free pieces, each with a piece to use, a start point on
  the plane, an optional `acrossMm` to set it beside the plane, and an optional velocity. `betweenPieces` names the
  one material for piece against piece. Each adds the signals `other.<name>.<axis>Mm`, `other.<name>.offPlaneMm`,
  `other.<name>.speedMps` and `contact.piece <name>.forceN`. Driven surfaces and loads act on every piece. Events,
  rest and the contact record still follow the trial's own piece. The planar engine refuses `others` by name.
- Two signals are added to the planar ones: `offPlaneMm` (how far the piece has left the trial's plane) and
  `tiltDeg` (how far it has tipped). On a case that truly is planar both stay at zero; when they do not, the planar
  assumption `in-plane` has been tested and found wanting.
- **Frames** (section 13.1) are read the same way in both engines, from the piece's centre. A frame that names a
  mover follows that mover's design motion, whatever the engine makes of the group.

**Calibration.** The same trial definition is run in both engines on cases that truly are planar, as part of the
engine's own tests. With one contact law the two agree far more closely than a decision needs:

| Case | Closed form | Planar | MuJoCo |
|---|---|---|---|
| Ball rolling 100 mm down a 20 degree slope | 0.2889 s | 0.2890 s | 0.2890 s |
| Bar rolling the same | 0.2991 s | 0.2992 s | 0.2991 s |
| Bounce from 200 mm, bounce value 0.5: rebound | | 60.22 mm | 60.22 mm |
| Same bounce: deepest press | | 2.345 mm | 2.345 mm |
| Same bounce: peak contact force | | 523.4 N | 523.4 N |
| 1 kg at rest on 200 N/mm: force and depth | 9.807 N, 0.049 mm | 9.807 N, 0.049 mm | 9.807 N, 0.049 mm |
| Block squeezed 1 mm into each of two surfaces of 200 N/mm: lid, bed | 195.1 N, 204.9 N | 195.1 N, 204.9 N | 195.1 N, 204.9 N |
| Block on a 20 degree slope at friction 0.5 | holds | holds, no creep | holds, no creep |
| Same on 30 degrees | slides | slides | slides |
| Block dragged by a roller against a slick wall: wall force | 5.18 N | within 3% | within 3% |
| Same, holding speed: motor current | 3.10 A | within 5% | within 5% |
| Block set on a belt at 1 m/s: speed at 0.1 s, then at 0.4 s | 0.49, 1.00 m/s | within 0.02 | within 0.02 |
| Ball pushed by a sliding gate: distance | | (reference) | within 5% |
| Load of 3 m/s2 for 0.1 s, then 0.2 s coasting: travel | 75 mm | within 1 mm | within 1 mm |
| Block thrown back by a sprung flap: most the flap opens | | 32.62 deg | 32.59 deg |
| Block on a 1 m/s belt on a cart moving at 0.5 m/s: speed | 1.5 m/s | | within 0.03 |
| One block strikes another like it, bounce value 0.5: speeds after | 0.25 and 0.75 m/s | | 0.23 and 0.77, momentum within 1% |
| Ring dropped over a post that fits its hole: rests | on the floor | | on the floor (and on the post when the post is too wide) |

What still differs between the engines is geometry, which is the reason to run the 3D one: the piece can leave the
plane, tip, and touch a surface at more than one place across its width.

**The calibration set, for this and any future engine.** An engine is not trusted on agreement in one kind of
case. Every engine listed in `ENGINES` (`tests/trial_cases.py`) runs the same trial definitions, and must give:

1. the closed-form rolling time of a ball and of a bar down a slope;
2. the weight, and the spring's depth, on a piece at rest;
3. the same peak force, deepest press and rebound in a bounce;
4. **the springs' force in a squeeze between two surfaces, and twice the force at twice the squash;**
5. hold with no creep below the friction angle, and slide above it;
6. the closed-form wall force and motor current when a driven roller drags a block;
7. belt speed reached at friction times g; a load's closed-form travel; the same flap opening.
8. **for an engine that runs pieces in 3D (`ENGINES_3D`): the standing seating case** (`tests/seating_case.py`). An
   invented carriage drives onto a ring; a curved blade with a faceted nose gets under it, a belt carries it up a
   tilted deck past a sprung flap, two driven side belts pinch it 5 mm each side, and it comes to rest against a
   stop. The engine must seat it within 0.03 s of the recorded time, on the recorded path within 1 mm over the lip
   and 5 mm after, with each side belt pressing its spring's 22.5 N. With the belt stopped it must not seat, and
   with a face's direction at the edge the path must leave the 1 mm band. The planar engine cannot take a ring's
   section and must refuse it by name.

Cases 4 and 8 are there because of mistakes worth stating plainly. Both passed every single-contact case and were
caught only by a real seated pickup. The second was a ring meeting a lip's faceted nose: MuJoCo's general convex method
gave it a face's direction, 22 to 37 degrees off, and the lip pushed the ring along the floor (see "A round piece meets
an edge or a corner" above). The first: **Before the contact law was made the library's own, each
material's spring and damper were mapped onto MuJoCo's native soft contact, and the mapping was checked on single
contacts only: a roll, a rest, a bounce. Those agreed within a few percent, and the engine was reported as
calibrated. It was not. In a squeeze the native solver gave 4 to 21 times the spring force, at every setting tried,
because its "spring" is a target acceleration shared between fighting contacts, not a force law.** The error
surfaced only when a real pickup trial, in which a piece starts pressed against a roller, was compared with an
earlier run of the same trial. Do not map a material's spring onto any engine's native soft contact. Use the
engine for geometry and motion, apply the library's contact law, and run the whole set above.

**Stages.**

| Stage | What | State |
|---|---|---|
| 1 | Fixed surfaces from the named solids, one free piece, the shared method and record, calibration against planar | Built |
| 2 | Driven surfaces (rollers, wheels) with the declared motor and gear; moved groups as hinges, sliders or paths, carriers included | Built |
| 3 | Belts: the same driven surface, since only the surface speed differs | Built |
| 4 | Flaps, loads, a driven surface on a moved group, a ring piece | Built |
| 5 | More than one piece | Built |

A trial that uses a part the engine does not run yet is refused by name; nothing is silently left out.

