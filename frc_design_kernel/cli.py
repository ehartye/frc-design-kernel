"""The command line. Each command prints plain one-line messages saying what it did."""
import argparse
import json
import sys
import time
from pathlib import Path

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


def write(folder, name, record):
    out = Path(folder)
    out.mkdir(parents=True, exist_ok=True)
    (out / name).write_text(json.dumps(record, indent=1) + "\n", encoding="utf-8", newline="\n")


def earlier(folder, name):
    """A record already in the folder, for a run of only part of the design to be put into; or None."""
    path = Path(folder) / name
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


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
    from .measure import summary as measures    # the CAD kernel is needed only from here on
    part = bool(args.motion or args.pose)
    record = measures.measure_design(args.source, args.min_gap, args.touch_gap, args.floor_z, args.ignore, args.workers, args.depth,
                                     (args.motion or []) if part else None, (args.pose or []) if part else None)
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
    if args.extremes:
        from .measure.extremes import at_extremes
        record["adjustments"] = at_extremes(args.source, args.min_gap, args.depth)
        for name, found in record["adjustments"].items():
            for row in found["settings"]:
                closer = sum(len(m["closer"]) for m in row["motions"].values()) + sum(len(p["closer"]) for p in row["poses"])
                print(f'Adjustment "{name}" at {row["setting"]:g}: {count(closer, "pair")} closer than the gap over every motion and pose.')
    old = earlier(args.out, "measurements.json") if part else None
    write(args.out, "measurements.json", measures.merged(old, record) if old else record)
    print(f"Wrote measurements.json to {args.out}" + (", keeping the parts that were not measured again." if old else "."))


def screen(args):
    from .builder.assembly import build as build_assembly    # the CAD kernel is needed only from here on
    from .measure.screen import facts
    design = load(args.source)
    assembly = build_assembly(design)
    names = args.interaction or list(design.data["interactions"])
    record = {"schema": "frc-design-kernel/screen@1", "generator": generator(), "design": {"name": design.data["name"], "source": design.path.name},
              "interactions": {name: facts(assembly, name) for name in names}}
    for name, found in record["interactions"].items():
        piece = found["piece"]
        uneven = [f'{solid} by {row["largestDifferenceMm"]:.2f} mm' if row["largestDifferenceMm"] else f"{solid} (it ends inside the width)"
                  for solid, row in found["sections"].items() if row["largestDifferenceMm"] or row["notCutAtLevelsMm"]]
        loose = sum(1 for hold in found["sidewaysHold"] for side in ("plus", "minus") if hold[side] is None)
        ratio = found["squeeze"]["ratio"]
        print(f'Interaction "{name}": the piece "{piece["name"]}" is a {piece["class"]}; sections differ across its width for '
              f'{", ".join(uneven) if uneven else "no solid"}; {count(loose, "side")} unguided; {count(len(found["mechanismOutOfPlane"]), "movement")} out of the plane; '
              f'{count(found["piecesAtOnce"], "piece")} at once; squeeze {"not known" if ratio is None else f"{ratio:.1%} of its thickness"}; '
              f'{count(len(found["notRigid"]), "solid")} not rigid.')
    if args.out:
        write(args.out, "screen.json", record)
        print(f"Wrote screen.json to {args.out}.")


def announce(cost):
    print(f'Campaign: {count(len(cost["trials"]), "trial")}, at most {count(cost["runs"], "run")} and {cost["steps"]} steps, about {cost["aboutSeconds"]:g} s.')


def trials(args):
    from .trials import campaign    # the CAD kernel is needed only from here on
    if args.estimate:
        announce(campaign.estimate(load(args.source), args.trial or None))
        return
    began = time.perf_counter()
    record = campaign.run_campaign(args.source, args.trial or None, args.max_steps, args.workers or 1, announce)
    spent = time.perf_counter() - began
    for name, found in record["trials"].items():
        control = "no control" if found["control"] is None else ("control rejected" if found["control"]["rejected"] else "control NOT rejected")
        held = sum(1 for r in found["ranges"] if r["held"])
        cover = [row for row in found["coverage"] if row["someSettingPassesEach"]]
        steps = "half step agrees" if found["stepComparison"]["converged"] else "half step differs"
        first = found["sensitivity"][0]["input"] if found["sensitivity"] else "none"
        print(f'Trial "{name}": {found["result"]}. Nominal outcome "{found["nominal"]["outcome"]}"; {control}; '
              f'{held} of {count(len(found["ranges"]), "input")} held across its range; {steps}; most sensitive to {first}'
              + (f'; {len(cover)} of {count(len(found["coverage"]), "input-adjustment pair")} covered.' if found["coverage"] else "."))
    old = earlier(args.out, "trials.json") if args.trial else None
    if old:
        record["trials"] = {**old.get("trials", {}), **record["trials"]}
    write(args.out, "trials.json", record)
    print(f'Ran {count(record["cost"]["runs"], "run")} and {record["cost"]["stepsRun"]} steps in {spent:.1f} s. Wrote trials.json to {args.out}'
          + (", keeping the trials that were not run again." if old else "."))


def status(args):
    from .status import status as compare    # the CAD kernel is needed only from here on
    found = compare(args.source, args.folder)
    print(f'Records in {args.folder} against "{found["design"]}" as it is now:')
    if not found["records"]:
        print("No records found.")
    for row in found["records"]:
        print(f'{row["record"]}: {row["state"]}' + ("" if not row["changes"] else " - " + "; ".join(row["changes"][:6])
                                                   + (f'; and {len(row["changes"]) - 6} more' if len(row["changes"]) > 6 else "")))
    ready = found["readyFor3d"]
    print(f'For a 3D engine: {count(len(ready["concaveWithNoBreakdown"]), "trial solid")} concave with no convex breakdown; '
          f'{count(len(ready["solidsWithNoMass"]), "solid")} with no mass; {count(len(ready["groupsNotOneHingeOrSlider"]), "moving group")} not one hinge or slider; '
          f'{count(len(ready["drivesNotOnASolid"]), "drive")} not on a solid; {count(len(ready["surfacesNotFromSolids"]), "trial surface")} not from a solid.')
    if args.json:
        print(json.dumps(found, indent=1))


def main(argv=None):
    made = generator()
    parser = argparse.ArgumentParser(prog="python -m frc_design_kernel", description="Build, measure and try a preliminary robot design from a design source.")
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
    gauge.add_argument("--motion", action="append", metavar="NAME", help="measure only this motion; may be repeated")
    gauge.add_argument("--pose", action="append", metavar="NAME", help="measure only this pose; may be repeated")
    gauge.add_argument("--min-gap", type=float, default=0.0, help="the gap in mm to test every pair against (default 0)")
    gauge.add_argument("--touch-gap", type=float, default=0.0, help="how near in mm two surfaces count as touching (default 0)")
    gauge.add_argument("--floor-z", type=float, default=0.0, help="the height of the floor in mm (default 0)")
    gauge.add_argument("--ignore", action="append", default=[], metavar="SOLID", help="a solid to leave out of the attachment record; may be repeated")
    gauge.add_argument("--workers", type=int, help="worker processes (default: half the cores)")
    gauge.add_argument("--depth", type=int, default=9, help="how many times the search may halve the stroke (default 9)")
    gauge.add_argument("--extremes", action="store_true", help="also measure at both ends of every adjustment of a design parameter")
    gauge.set_defaults(run=measure)
    sieve = commands.add_parser("screen", help="report plain facts about each interaction: is it the same in every section?")
    sieve.add_argument("source", help="the design source JSON file")
    sieve.add_argument("--out", help="the folder to write screen.json into")
    sieve.add_argument("--interaction", action="append", metavar="NAME", help="an interaction to report (default: all); may be repeated")
    sieve.set_defaults(run=screen)
    attempt = commands.add_parser("try", help="run the design's physics trials and write trials.json")
    attempt.add_argument("source", help="the design source JSON file")
    attempt.add_argument("--out", help="the folder to write into")
    attempt.add_argument("--trial", action="append", default=[], metavar="NAME", help="a trial to run (default: all); may be repeated")
    attempt.add_argument("--max-steps", type=int, help="refuse a campaign whose estimate is above this many steps")
    attempt.add_argument("--workers", type=int, help="worker processes for the runs (default 1)")
    attempt.add_argument("--estimate", action="store_true", help="print the cost and stop")
    attempt.set_defaults(run=trials)
    state = commands.add_parser("status", help="say which records in a folder are current and which are stale, and why")
    state.add_argument("source", help="the design source JSON file")
    state.add_argument("folder", help="the folder holding measurements.json and trials.json")
    state.add_argument("--json", action="store_true", help="also print everything as JSON")
    state.set_defaults(run=status)
    args = parser.parse_args(argv)
    if args.command == "try" and not (args.out or args.estimate):
        parser.error("try needs --out DIR, or --estimate")
    try:
        args.run(args)
    except DesignError as problem:
        print(f"Error: {problem}", file=sys.stderr)
        return 1
    return 0
