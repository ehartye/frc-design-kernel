"""Enough of a thing's identity to tell later whether it has changed: for records that say what they used.

A solid is known by its group, kind, volume and bounding box as drawn (which fixes where it is). Names of designs
and notes are not part of any identity, so renaming a design or editing a note changes nothing here.
"""
from ..kernel import props

PLACES = 6


def tidy(value):
    if isinstance(value, float):
        return round(value, PLACES) + 0.0
    if isinstance(value, list):
        return [tidy(v) for v in value]
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items() if k != "note"}
    return value


def solid(assembly, name):
    found = assembly.solids[name]
    return {"group": found.group, "kind": found.kind, "volumeMm3": round(props.volume(found.shape), 3),
            "boundsMm": [round(v, 4) for v in props.bounds(found.shape)], "massKg": found.mass_kg,
            "massRangeKg": None if found.mass_range_kg is None else list(found.mass_range_kg)}


def solids(assembly, names):
    """{name: identity} for the named solids."""
    return {name: solid(assembly, name) for name in sorted(names)}


def differences(recorded, current, what):
    """Plain statements of how two {name: identity} tables differ."""
    found = []
    for name in sorted(set(recorded) | set(current)):
        if name not in current:
            found.append(f'{what} "{name}" is no longer there')
        elif name not in recorded:
            found.append(f'{what} "{name}" is new')
        elif tidy(recorded[name]) != tidy(current[name]):
            old, new = tidy(recorded[name]), tidy(current[name])
            fields = [key for key in sorted(set(old) | set(new)) if old.get(key) != new.get(key)] if isinstance(old, dict) and isinstance(new, dict) else []
            found.append(f'{what} "{name}" changed' + (f" ({', '.join(fields)})" if fields else f": {old} to {new}"))
    return found
