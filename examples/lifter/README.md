# Example: bench lifter

An invented mechanism, used by the tests. It is not a real robot.

Two posts stand on a base plate. A carriage slides up the posts and carries two fork tines. A crate rides on the
tines. A gearmotor and a spool sit on the base.

| Shown here | Where |
|---|---|
| Parameters and `=` expressions | `parameters`, and most sizes |
| `each` rows for left and right | posts, gussets, sleeves, tines, mounts |
| Tubes, a prism, a cylinder, boxes | `solids` |
| Two solids taken from a STEP file by name | `gearmotor body`, `gearmotor shaft` (from `parts/gearmotor.step`) |
| A custom shape, registered with a reason and limits | `tine` (code in `custom/tine.py`) |
| A lump mass for a whole group | `carriage` |
| A moving group that carries another | `carriage` carries `load` |
| Fixtures | `bench top` (imported), `crate` (drawn) |
| Declared contacts | the crate on the tines, the spool on the shaft |
| Poses | `lowered`, `raised`, `set down` |
| A motion by operations, checked against its end pose | `lift` |
| A curved move as one operation | `hand off` (an arc) |
| A motion through several poses | `whole cycle` |

Build it from the repository root:

```
python -m frc_design_kernel build examples/lifter/design.json --out out
```

Measure it:

```
python -m frc_design_kernel measure examples/lifter/design.json --out out --touch-gap 1
```

The two STEP files in `parts/` are invented stand-ins for a supplier's file. `parts/make_parts.py` made them.
