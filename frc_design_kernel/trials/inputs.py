"""A trial's case: the trial with the design tables it draws on, and the physical inputs in it with their sources.

A physical input is a number the physics depends on that somebody had to measure or guess: a stiffness, a friction, a
bounce, a mass, a motor constant. Each one states its source in the design source:

    {"value": 0.35, "measured": "bench pull test, sheet 3"}
    {"value": 0.35, "assumed": [0.15, 0.5]}

An assumed value with a range is a normal, complete state: a best guess, to be covered by adjustment. A measured
value simply has no range to cover. A plain number states neither, so nothing says how far it may be off; the
record lists it as unstated, and a trial with unstated inputs is incomplete.
"""
import copy

TABLES = ("pieces", "materials", "motors", "drives")
PHYSICAL = {
    "pieces": ("massKg", "inertiaKgM2", "dragCoefficient", "frontalAreaM2", "liftSlope", "liftMax"),
    "materials": ("stiffnessNPerM", "restitution", "dampingRatio", "friction"),
    "motors": ("ktNmPerA", "ohm", "keVsPerRad"),
    "drives": ("efficiency", "movingKg", "inertiaKgM2", "dragNm"),
    "flaps": ("inertiaKgM2", "preloadNm", "springNmPerRad", "dampingNmSPerRad", "stopRestitution"),
}


def val(item):
    """The number of a physical input, whether or not it states its source."""
    return item["value"] if isinstance(item, dict) and "value" in item else item


def plain(item):
    """A copy with every sourced input replaced by its number."""
    if isinstance(item, dict):
        return item["value"] if "value" in item and ("measured" in item or "assumed" in item) else {k: plain(v) for k, v in item.items()}
    return [plain(v) for v in item] if isinstance(item, list) else item


def drives_used(data, trial):
    """Names of the design drives a trial uses: commanded, named by a surface, or turning a solid the trial cuts."""
    cut = {s["solid"] for s in trial["surfaces"] if "solid" in s}
    turning = {name for name, drive in data["drives"].items() if any(t["solid"] in cut for t in drive.get("turns", []))}
    return sorted(turning | set(trial.get("commands", {})) | {s["drive"] for s in trial["surfaces"] if "drive" in s})


def case(data, trial):
    """The trial with the entries of the design tables it uses, as one table that changes can be made to by path."""
    out = copy.deepcopy(trial)
    drives = drives_used(data, trial)
    materials = sorted({s["material"] for s in [*trial["surfaces"], *trial.get("flaps", [])]} | ({trial["betweenPieces"]} if "betweenPieces" in trial else set()))
    out["pieces"] = {use: copy.deepcopy(data["pieces"][use]) for use in sorted({trial["piece"]["use"]} | {other["use"] for other in trial.get("others", [])})}
    out["materials"] = {name: copy.deepcopy(data["materials"][name]) for name in materials}
    out["drives"] = {name: copy.deepcopy(data["drives"][name]) for name in drives}
    out["motors"] = {name: copy.deepcopy(data["motors"][name]) for name in sorted({d["motor"] for d in out["drives"].values() if "motor" in d})}
    return out


def physical_inputs(a_case):
    """Every physical input of a case: [{"path", "value", "source": "measured" | "assumed" | "unstated", ...}]."""
    found = []
    for table, fields in PHYSICAL.items():
        entries = a_case.get(table, {})
        named = {e["name"]: e for e in entries}.items() if isinstance(entries, list) else entries.items()
        for name, entry in named:
            for field in fields:
                if field not in entry:
                    continue
                item, row = entry[field], {"path": f"{table}.{name}.{field}", "value": val(entry[field])}
                if isinstance(item, dict) and "measured" in item:
                    row.update(source="measured", reference=item["measured"])
                elif isinstance(item, dict) and "assumed" in item:
                    row.update(source="assumed", range=list(item["assumed"]))
                else:
                    row["source"] = "unstated"
                found.append(row)
    if "air" in a_case:         # the air the piece flies through: one entry with no name
        item, row = a_case["air"]["densityKgM3"], {"path": "air.densityKgM3", "value": val(a_case["air"]["densityKgM3"])}
        if isinstance(item, dict) and "measured" in item:
            row.update(source="measured", reference=item["measured"])
        elif isinstance(item, dict) and "assumed" in item:
            row.update(source="assumed", range=list(item["assumed"]))
        else:
            row["source"] = "unstated"
        found.append(row)
    return found
