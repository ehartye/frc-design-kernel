"""The command line. Each command prints plain one-line messages saying what it did."""
import argparse
import sys

from .errors import DesignError
from .source.load import load
from .version import generator


def count(n, word):
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def summary(design):
    data = design.data
    parts = [count(len(data["solids"]), "solid"), count(len(data["fixtures"]), "fixture"), count(len(data["groups"]), "group"),
             count(len(data["poses"]), "pose"), count(len(data["motions"]), "motion"), count(len(design.custom_used), "custom shape")]
    return ", ".join(parts)


def validate(args):
    design = load(args.source)
    print(f'OK "{design.data["name"]}": {summary(design)}. Nothing was built.')


def build(args):
    from .builder.assembly import build as build_assembly    # the CAD kernel is needed only from here on
    from .builder.export import export
    design = load(args.source)
    record = export(build_assembly(design), args.out, args.pose)
    written = [name for name in record["files"].values() if name] + ["manifest.json"]
    pose = f'at the pose "{args.pose}"' if args.pose else "as drawn"
    print(f'Built "{design.data["name"]}" {pose}: {summary(design)}.')
    for row in record["custom"]:
        print(f'Custom shape "{row["name"]}" ({row["file"]}, {count(row["lines"], "line")}) is used by {count(len(row["usedBy"]), "solid")}.')
    unweighed = len(record["mass"]["unweighed"])
    print(f'Robot mass {record["mass"]["totalKg"]:.3f} kg' + (f'; {count(unweighed, "solid")} with no mass.' if unweighed else "."))
    print(f'Wrote {", ".join(written)} to {args.out}.')


def measure(args):
    import json
    from pathlib import Path
    from .measure.summary import measure_design    # the CAD kernel is needed only from here on
    record = measure_design(args.source, args.min_gap, args.touch_gap, args.floor_z, args.ignore, args.workers, args.depth)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "measurements.json").write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f'Measured "{record["design"]["name"]}" against a gap of {args.min_gap:g} mm, touching within {args.touch_gap:g} mm.')
    for name, found in record["motions"].items():
        nearest = found["closest"]
        near = f'closest {nearest["pair"][0]} and {nearest["pair"][1]} at {nearest["gapMm"]:.3f} mm' if nearest else "no pair near enough to measure"
        print(f'Motion "{name}": {near}; {count(len(found["closer"]), "pair")} closer than the gap; {count(len(found["unresolved"]), "pair")} not settled.')
    for row in record["poses"]:
        label = f'Pose "{row["pose"]}"' if row["pose"] else "As drawn"
        hold, weight = row["attachment"], row["mass"]
        print(f'{label}: {count(len(row["clearance"]["closer"]), "pair")} closer than the gap; {count(len(hold["notConnectedToBase"]), "solid")} not connected to the base; '
              f'{count(len(hold["fixturesOffFloor"]), "fixture")} off the floor; mass {weight["totalKg"]:.3f} kg.')
    print(f"Wrote measurements.json to {args.out}.")


def main(argv=None):
    made = generator()
    parser = argparse.ArgumentParser(prog="python -m frc_design_kernel", description="Build a preliminary robot design from a design source.")
    parser.add_argument("--version", action="version", version=f"{made['library']} {made['version']} (commit {made['commit'] or 'unknown'})")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("validate", help="check a design source without building it")
    check.add_argument("source", help="the design source JSON file")
    check.set_defaults(run=validate)
    make = commands.add_parser("build", help="build the solids and write the STEP files and the manifest")
    make.add_argument("source", help="the design source JSON file")
    make.add_argument("--out", required=True, help="the folder to write into")
    make.add_argument("--pose", help="the named pose to export (default: as drawn)")
    make.set_defaults(run=build)
    gauge = commands.add_parser("measure", help="measure clearance, attachment and mass, and write measurements.json")
    gauge.add_argument("source", help="the design source JSON file")
    gauge.add_argument("--out", required=True, help="the folder to write into")
    gauge.add_argument("--min-gap", type=float, default=0.0, help="the gap in mm to test every pair against (default 0)")
    gauge.add_argument("--touch-gap", type=float, default=0.0, help="how near in mm two surfaces count as touching (default 0)")
    gauge.add_argument("--floor-z", type=float, default=0.0, help="the height of the floor in mm (default 0)")
    gauge.add_argument("--ignore", action="append", default=[], metavar="SOLID", help="a solid to leave out of the attachment record; may be repeated")
    gauge.add_argument("--workers", type=int, help="worker processes (default: half the cores)")
    gauge.add_argument("--depth", type=int, default=9, help="how many times the search may halve the stroke (default 9)")
    gauge.set_defaults(run=measure)
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except DesignError as problem:
        print(f"Error: {problem}", file=sys.stderr)
        return 1
    return 0
