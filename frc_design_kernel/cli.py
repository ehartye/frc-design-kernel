"""The command line. Each command prints plain one-line messages saying what it did."""
import argparse
import json
import math
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
    from .builder import placement      # placements need no CAD kernel
    design = load(args.source)
    placement.check_motions(design.data)
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


def pairs_line(label, found):
    """What a clearance measured now and what it carried or left out, as one line."""
    checked, total = found["checked"], found["counts"]["pairs"]
    why = [f'those with {", ".join(checked["measuredSolids"])}'] if checked["measuredSolids"] else []
    if checked["measuredPairs"]:
        why.append(f'{count(len(checked["measuredPairs"]), "pair")} whose declared contact changed')
    why = f' ({"; ".join(why)})' if why else ""
    if checked["pairsNotMeasured"]:
        return f'{label}: measured {checked["pairsMeasured"]} of {count(total, "pair")}{why}; {checked["pairsNotMeasured"]} not measured.'
    return f'{label}: measured {checked["pairsMeasured"]} of {count(total, "pair")} again{why}, carried {checked["pairsCarried"]}.'


def clearance_facts(job, found):
    nearest = found["closest"]
    near = [f'closest {nearest["pair"][0]} and {nearest["pair"][1]} at {nearest["gapMm"]:.3f} mm'] if nearest else []
    settled = [f'{count(len(found["unresolved"]), "pair")} not settled'] if "motion" in job else []
    return "; ".join([*near, f'{count(len(found["closer"]), "pair")} closer than the gap', *settled])


FACTS = {
    "clearance": clearance_facts,
    "reach": lambda job, found: (f'reached, {found["gapMm"]:.3f} mm at t = {found["t"]:.3f}' if found["reached"]
                                 else f'not reached; closest {found["gapMm"]:.3f} mm at t = {found["t"]:.3f}'),
    "indentation": lambda job, found: f'deepest {found["deepestMm"]:.3f} mm at t = {found["t"]:.3f}' + ("; deeper than the limit" if found["deeperThanLimit"] else ""),
    "withdrawal": lambda job, found: f'the moved solids end {found["smallestBoxGapMm"]:.3f} mm from the rest, box to box',
    "attachment": lambda job, found: (f'{count(len(found["notConnectedToBase"]), "solid")} not connected to the base; '
                                      f'{count(len(found["fixturesOffFloor"]), "fixture")} off the floor'),
    "mass": lambda job, found: f'{found["totalKg"]:.3f} kg' + (f'; {count(len(found["unweighed"]), "solid")} with no mass' if found["unweighed"] else ""),
    "electrical": lambda job, found: "; ".join(
        [f'{name} {drive["currentA"]["range"][1]:.1f} A per motor at most' + (" (clamped at its limit)" if drive["clamped"] else "")
         for name, drive in found["drives"].items()]
        + [f'bus {found["bus"]["volts"]["range"][0]:.2f} to {found["bus"]["volts"]["range"][1]:.2f} V under {found["bus"]["loadA"]["range"][1]:.1f} A at most'
           if found["bus"] else "no battery, so no bus voltage"]),
}


def job_lines(entry, detail):
    """One line per finished job: what it found, or that it was carried; with detail, what a clearance measured and carried."""
    name, held = entry["id"], entry["record"]
    if entry["action"] == "carried":
        print(f"{name}: carried; its record is current.")
        return
    facts = FACTS.get(held["job"]["kind"])
    print(f'{name}: {facts(held["job"], held["result"]) if facts else "measured"}.')
    if detail and "counts" in held:
        print(pairs_line(name, held))


def measure(args):
    from .measure import records, summary as measures    # the CAD kernel is needed only from here on
    data = load(args.source).data
    part = bool(args.motion or args.pose)
    motions, poses = ((args.motion or []), (args.pose or [])) if part else (None, None)
    jobs = measures.design_jobs(data, args.min_gap, args.touch_gap, args.floor_z, args.ignore, args.depth, args.near, motions, poses)
    folder = Path(args.out) / records.FOLDER
    if args.carry and not folder.is_dir():
        raise DesignError("", f"--carry needs earlier job records in {folder} to carry from", "Measure once without --carry first")
    print(f'Measuring "{data["name"]}": {count(len(jobs), "job")} against a gap of {args.min_gap:g} mm, touching within {args.touch_gap:g} mm.')
    entries = records.record(args.source, jobs, args.out, args.workers, carry=args.carry, focus=args.focus,
                             report=lambda entry: job_lines(entry, bool(args.carry or args.focus)))
    if args.extremes:
        extremes(args, motions, poses)
    carried = sum(1 for entry in entries if entry["action"] == "carried")
    print(f'Wrote {count(len(entries) - carried, "job record")} to {folder}' + (f"; carried {carried} that were current." if carried else "."))


def extremes(args, motions, poses):
    """Clearance at both ends of every mechanical adjustment, written to adjustments.json."""
    from .measure.extremes import at_extremes
    found = at_extremes(args.source, args.min_gap, args.depth, args.workers, motions, poses)
    for name, entry in found.items():
        for row in entry["settings"]:
            closer = sum(len(m["closer"]) for m in row["motions"].values()) + sum(len(p["closer"]) for p in row["poses"])
            print(f'Adjustment "{name}" at {row["setting"]:g}: moves {count(len(row["moves"]), "solid")}; '
                  f'{count(closer, "pair")} with one of them closer than the gap over the motions and poses measured.')
    write(args.out, "adjustments.json", {"schema": "frc-design-kernel/adjustments@1", "generator": generator(), "adjustments": found})
    print(f"Wrote adjustments.json to {args.out}.")


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
    print(f'Checked {count(len(found["records"]), "record")} in {found["seconds"]:.2f} s.')
    ready = found["readyFor3d"]
    print(f'For a 3D engine: {count(len(ready["concaveWithNoBreakdown"]), "trial solid")} concave with no convex breakdown; '
          f'{count(len(ready["solidsWithNoMass"]), "solid")} with no mass; {count(len(ready["groupsNotOneHingeOrSlider"]), "moving group")} not one hinge or slider; '
          f'{count(len(ready["drivesNotOnASolid"]), "drive")} not on a solid; {count(len(ready["surfacesNotFromSolids"]), "trial surface")} not from a solid.')
    if args.json:
        print(json.dumps(found, indent=1))


def piece_geometry(args):
    from .measure import piece_geometry as geometry    # the CAD kernel is needed only from here on
    record = geometry.measure(geometry.read(args.source), args.linear_mm, args.angular_rad)
    out = Path(args.out)
    try:
        write(out.parent, out.name, record)
    except OSError as problem:
        raise DesignError(str(out), f"the record cannot be written there ({problem.strerror or problem})",
                          "Give --out as a file path in a folder you can write to") from None
    failed = 0
    for name, found in record["shapes"].items():
        if not found["ok"]:
            failed += 1
            print(f"Error: {DesignError(**found['error'])}", file=sys.stderr)
            continue
        bore = found["bore"]
        print(f'Piece "{name}": {found["symmetry"]["class"]}, {found["volumeMm3"]:.0f} mm3, hull of {count(len(found["hullMm"]), "corner")} '
              f'grown {found["hullToleranceMm"]:g} mm' + (f'; a through-bore {bore["diameterMm"]:g} mm across.' if bore else "."))
    print(f'Measured {len(record["shapes"]) - failed} of {count(len(record["shapes"]), "shape")}. Wrote {out}.')
    return 1 if failed else 0


def above_zero(text):
    """A finite number greater than 0, for the meshing flags; anything else is a usage error."""
    try:
        value = float(text)
    except ValueError:
        value = math.nan
    if not (math.isfinite(value) and value > 0):
        raise argparse.ArgumentTypeError(f"must be a finite number greater than 0, not {text}")
    return value


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
    gauge = commands.add_parser("measure", help="measure clearance, attachment and mass, one job record each under measurements/")
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
    gauge.add_argument("--near", type=float, default=0.0, help="also keep the rows of pairs that may come within this many mm of the gap "
                       "(default 0: only pairs closer than the gap, or not settled)")
    gauge.add_argument("--extremes", action="store_true", help="also measure at both ends of every mechanical adjustment, the pairs with a solid it "
                       "moves, and write adjustments.json")
    gauge.add_argument("--carry", action="store_true", help="carry from the job records already in --out: a current record is kept as it "
                       "is, and a stale clearance or attachment measures again only the pairs whose solids, placements or rules changed")
    gauge.add_argument("--focus", action="append", metavar="SOLID", help="measure the pairs with this solid in them (again, with --carry; "
                       "without it, only those, and the record says how many were not measured); may be repeated")
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
    state.add_argument("folder", help="the folder holding measurements/ and trials.json")
    state.add_argument("--json", action="store_true", help="also print everything as JSON")
    state.set_defaults(run=status)
    geometry = commands.add_parser("piece-geometry", help="measure each game piece's shape on its own: bounds, symmetry, hull and bore")
    geometry.add_argument("source", help='a JSON file holding a "pieces" block, as in a design source')
    geometry.add_argument("--out", required=True, help="the JSON file to write the record to")
    geometry.add_argument("--linear-mm", type=above_zero, default=0.2, help="the mesh's linear deflection for the hull, in mm (default 0.2)")
    geometry.add_argument("--angular-rad", type=above_zero, default=0.3, help="the mesh's angular deflection for the hull, in radians (default 0.3)")
    geometry.set_defaults(run=piece_geometry)
    args = parser.parse_args(argv)
    if args.command == "try" and not (args.out or args.estimate):
        parser.error("try needs --out DIR, or --estimate")
    try:
        return args.run(args) or 0    # a command that writes its record despite failures returns 1 itself
    except DesignError as problem:
        print(f"Error: {problem}", file=sys.stderr)
        return 1
