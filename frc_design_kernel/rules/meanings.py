"""What a property, a word or a form of the format means, as fields.json says it. No rules folder is needed, but for of_path.

    find(name)            every Meaning of a name ("bottom", "tape inside", "range") or of a key ("opening.bottom")
    of_path(book, path)   the Meaning of the property that a path into a rules folder names, or None for an extra value
    everything()          every Meaning, in the order of fields.json
    near(name)            the names that are nearly this one
    fields_of(one)        a Meaning for each field of a kind of record, or of the kind that a property holds
    form_of(holds)        the name of the form that says how to write what a property holds, or None
"""
import difflib
from dataclasses import dataclass

from . import fields
from .read import at_spot, names
from .worker import Season

BEGINS = ("records", "record", "list of", "words", "word")      # a form for every holds that begins so
NOTES = {                                                       # what fields.json says with a flag, told in words
    "records": lambda kind: f"Each name in it is the ID of a record of the kind `{kind}`.",
    "placed": lambda _: "It may have the fields of `placed`.",
    "geometry": lambda _: "It needs geometry, or `no_geometry`, when a rule or a score names it.",
    "by_piece": lambda _: "Its fields are the IDs of pieces.",
    "closed": lambda _: "It has no extra values.",
    "needs": lambda given: f"It must have {_listed(given)}.",
    "one_of": lambda given: f"It has exactly one of {_listed(given)}.",
    "any_of": lambda given: f"It has at least one of {_listed(given)}.",
    "needs_with": lambda given: " ".join(f"With `{name}` {word} it must have {_listed(needs)}." for name, cases in given.items() for word, needs in cases.items()),
    "act_needs": lambda given: f"With an `act` it has at least one of {_listed(given)}.",
    "optional": lambda _: "It may be left out.",
    "one": lambda _: "One number is needed here: no range, and no limits of which one is enough.",
}


@dataclass(frozen=True)
class Meaning:
    """One entry of fields.json, for whoever asks what it means and how it is written."""
    key: str                # "opening.bottom", "zone", "limits.reach.far", "conduct.json", "edge: tape inside", "form: range"
    means: str
    holds: str = ""         # what a property holds
    form: str = ""          # the form that says how to write that
    examples: tuple = ()    # how it is written
    words: tuple = ()       # a Meaning for each word that may be written
    fields: tuple = ()      # a Meaning for each property of a file, a kind of record, a limit or a shape
    notes: tuple = ()       # what must be there, and what may not

    @property
    def names(self):
        """What it may be asked by: its key, and its last name."""
        return {self.key, self.key.rpartition(": ")[2], self.key if ": " in self.key else self.key.rpartition(".")[2], self.key.removesuffix(".json")}


def form_of(holds, data=None):
    """The form that says how to write what a property holds: its own, one for a unit that is kept, or one for its beginning."""
    data = data or names()
    if holds in data["forms"]:
        return holds
    if holds in data["kept"]["units"]:
        return "printed unit"
    return next((start for start in BEGINS if holds.startswith(start + " ") and start in data["forms"]), None)


def words_of(name):
    return tuple(Meaning(f"{name}: {word}", about["means"]) for word, about in names()["words"][name]["words"].items())


def _listed(given):
    """Some names in words: `a`, `b` and `c`."""
    quoted = [f"`{one}`" for one in given]
    return quoted[0] if len(quoted) == 1 else f"{', '.join(quoted[:-1])} and {quoted[-1]}"


def _notes(about):
    return tuple(tell(about[flag]) for flag, tell in NOTES.items() if about.get(flag))


def _property(key, about):
    form = form_of(about["holds"]) or ""
    first, _, rest = about["holds"].partition(" ")
    words = words_of(rest) if first in ("word", "words") else ()
    examples = () if words else tuple(names()["forms"][form]["examples"]) if form and form not in BEGINS else ()
    return Meaning(key, about["means"], about["holds"], form, examples, words, notes=_notes(about))


def _properties(label, about):
    return tuple(_property(f"{label}.{name}", one) for name, one in about.get("fields", {}).items())


def everything():
    """Every Meaning, in the order of fields.json. What the whole format is comes first, with the key "rules"."""
    data = names()
    found = [Meaning("rules", " ".join(data["means"]))]
    found += [Meaning(f"unit: {name}", about["means"], examples=tuple(about["units"])) for name, about in (*data["units"].items(), ("kept", data["kept"]))]
    found.append(Meaning("unit: joined", data["joined"]["means"]))
    found += [Meaning(f"form: {name}", about["means"], examples=tuple(about["examples"])) for name, about in data["forms"].items()]
    for name, about in data["files"].items():
        own = _properties(name, about)
        found += [Meaning(f"{name}.json", about["means"], fields=own, notes=_notes(about)), *own]
    found.append(Meaning("roots", data["roots"]["means"], examples=tuple(data["roots"]["words"])))
    for label, section in (("", "kinds"), ("limits.", "limits"), ("", "shapes"), ("", "outlines")):
        for name, about in data[section].items():
            key = f"{label}{name}" if section not in ("shapes", "outlines") else f"{section[:-1]}: {name}"
            own = _properties(f"{label}{name}", about)
            found += [Meaning(key, about["means"], about.get("holds", ""), form_of(about["holds"]) if "holds" in about else "", fields=own, notes=_notes(about)), *own]
    for name, about in data["words"].items():
        found += [Meaning(f"words: {name}", about["means"], words=words_of(name)), *words_of(name)]
    return found


def find(name):
    """Every Meaning with this name or key. A key that is whole finds only its own: for "zone.at", what any record that stands
    somewhere has."""
    found = [one for one in everything() if name in one.names]
    if "." not in name:
        return found
    kind, _, field = name.rpartition(".")
    spec = fields.spec_of(kind) if kind in names()["kinds"] else fields.spec_of_limit(kind.removeprefix("limits."))
    own = spec.known[field].key if spec and field in spec.known else name
    return [one for one in found if one.key == name] or [one for one in everything() if one.key == own]


def fields_of(one):
    """A Meaning for each field of a kind of record: of its own, or of the kind that a property holds."""
    kind = one.holds.rpartition(" ")[2] if one.holds.startswith(("record ", "records ", "list of ")) else None
    return one.fields or tuple(field for other in everything() if other.key == kind for field in other.fields)


def near(name):
    """The names that are nearly this one, the nearest first."""
    return difflib.get_close_matches(name, dict.fromkeys(name for one in everything() for name in one.names), 5)


def of_path(book, path):
    """The Meaning of the property that a path names: of the longest part of it that is a property, a limit or a record, or of
    the form or the size that the rest of it leads to in a shape or an outline."""
    head, *steps = path.split(".")
    ident, at, _ = head.partition("@")
    entry, starts, least = book.ids.get(ident), [ident], 0
    if entry and (at or steps[:1] == ["spots"]) and (spotted := at_spot(entry.data, steps if at else steps[1:]))[0]:
        spot, _, steps = spotted
        if not steps:
            return _of_key("spot")
        own, *of_spot = Season(book).starts(entry, spot)
        starts, least = [*of_spot, own], 1
    at_path = {field.where.partition(" ")[2]: field.key or ("" if field.holds != "piece count" else _record_key(field.entry)) for field in fields.walk(book, [])}
    at_path.update({entry.path: _record_key(entry) for entry in book.entries if entry.path})
    for i in range(len(steps), least - 1, -1):
        part = next((part for start in starts if (part := ".".join([start, *steps[:i]])) in at_path), None)
        if part:
            return _in_drawing(_of_key(at_path[part]), steps[i:]) if at_path[part] else None
    return None


def _in_drawing(one, steps):
    """The Meaning of a form or a size in a shape or an outline, where the steps after its property lead to one."""
    known = {other.key: other for other in everything()} if one.holds in ("shape", "outline") and steps else {}
    for name in steps:
        one = known.get(f"{one.holds.removesuffix('s')}: {name}") or known.get(f"{one.key.rpartition(': ')[2]}.{name}") or one
    return one


def _record_key(entry):
    return f"limits.{entry.id}" if entry.kind == "limit" else entry.kind


def _of_key(key):
    return next((one for one in everything() if one.key == key), None)
