"""What a property, a word or a form of the format means, as fields.json says it. No rules folder is needed, but for of_path.

    find(name)            every Meaning of a name ("bottom", "tape inside", "range") or of a key ("opening.bottom")
    of_path(book, path)   the Meaning of the property that a path into a rules folder names, or None for an extra value
    everything()          every Meaning, in the order of fields.json
    form_of(holds)        the name of the form that says how to write what a property holds, or None
"""
from dataclasses import dataclass

from . import fields
from .read import ALLIANCES, names

BEGINS = ("records", "record", "list of", "words", "word")      # a form for every holds that begins so


@dataclass(frozen=True)
class Meaning:
    """One entry of fields.json, for whoever asks what it means and how it is written."""
    key: str                # "opening.bottom", "zone", "limits.reach.far", "conduct.json", "edge: tape inside", "form: range"
    means: str
    holds: str = ""         # what a property holds
    form: str = ""          # the form that says how to write that
    examples: tuple = ()    # how it is written
    words: tuple = ()       # a Meaning for each word that may be written

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


def _property(key, about):
    form = form_of(about["holds"]) or ""
    first, _, rest = about["holds"].partition(" ")
    words = words_of(rest) if first in ("word", "words") else ()
    examples = () if words else tuple(names()["forms"][form]["examples"]) if form and form not in BEGINS else ()
    return Meaning(key, about["means"], about["holds"], form, examples, words)


def _properties(label, about):
    return [_property(f"{label}.{name}", one) for name, one in about.get("fields", {}).items()]


def everything():
    """Every Meaning, in the order of fields.json. What the whole format is comes first, with the key "rules"."""
    data = names()
    found = [Meaning("rules", " ".join(data["means"]))]
    found += [Meaning(f"unit: {name}", about["means"], examples=tuple(about["units"])) for name, about in (*data["units"].items(), ("kept", data["kept"]))]
    found.append(Meaning("unit: joined", data["joined"]["means"]))
    found += [Meaning(f"form: {name}", about["means"], examples=tuple(about["examples"])) for name, about in data["forms"].items()]
    for name, about in data["files"].items():
        found += [Meaning(f"{name}.json", about["means"]), *_properties(name, about)]
    found.append(Meaning("roots", data["roots"]["means"], examples=tuple(data["roots"]["words"])))
    for label, section in (("", "kinds"), ("limits.", "limits"), ("", "shapes"), ("", "outlines")):
        for name, about in data[section].items():
            key = f"{label}{name}" if section not in ("shapes", "outlines") else f"{section[:-1]}: {name}"
            found += [Meaning(key, about["means"], about.get("holds", "")), *_properties(f"{label}{name}", about)]
    for name, about in data["words"].items():
        found += [Meaning(f"words: {name}", about["means"], words=words_of(name)), *words_of(name)]
    return found


def find(name):
    """Every Meaning with this name or key; a key that is whole finds only its own."""
    found = [one for one in everything() if name in one.names]
    return [one for one in found if one.key == name] if "." in name else found


def of_path(book, path):
    """The Meaning of the property that a path names: of the longest part of it that is a property, a limit or a record."""
    head, *steps = path.split(".")
    ident, at, alliance = head.partition("@")
    entry = book.ids.get(ident)
    if at and entry and alliance in ALLIANCES and (spot := book.look(path).spot):
        steps = steps[spot.count(".") + 1:]
        known = {**fields.spec_for(entry).known, **fields.spec_of("spot").known}
        return _of_key(known[steps[0]].key) if steps and steps[0] in known else None
    plain = ".".join([ident, *steps])
    at_path = {field.where.partition(" ")[2]: field.key or ("" if field.holds != "piece count" else _record_key(field.entry)) for field in fields.walk(book, [])}
    at_path.update({entry.path: _record_key(entry) for entry in book.entries if entry.path})
    for i in range(len(steps) + 1, 0, -1):
        part = ".".join(plain.split(".")[:i])
        if part in at_path:
            return _of_key(at_path[part]) if at_path[part] else None
    return None


def _record_key(entry):
    return f"limits.{entry.id}" if entry.kind == "limit" else entry.kind


def _of_key(key):
    return next((one for one in everything() if one.key == key), None)
