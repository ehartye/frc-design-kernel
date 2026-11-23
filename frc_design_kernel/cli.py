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
    args = parser.parse_args(argv)
    try:
        args.run(args)
    except DesignError as problem:
        print(f"Error: {problem}", file=sys.stderr)
        return 1
    return 0
