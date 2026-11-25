"""Finding records of a rules folder by code, ID or words, and telling one in full.

    Finder(rules)         for the Rules of a folder
      .find(asked)        ([the Entry or the Entries asked for], [others that have what was asked for an ID or a code])
      .line(entry)        one line about a record
      .full(entry)        the lines that tell all of a record, with `says` filled in and the number of each formula
"""
import functools
import json
import re

from . import fields, meanings, says
from .read import word_list

WORD = re.compile(r"[a-z0-9]+")
LONG = 100          # a line about a record tells no more letters than this
NOTHING = "nothing"


def name_of(entry):
    return entry.path or f"{entry.file}.json"


def _codes(entry):
    code = entry.data.get("code", ())
    return {one.casefold() for one in ([code] if isinstance(code, str) else code)}


def _holds(words, text):
    """Whether every word is in a text, whole or as the beginning of a longer one; a number or a short word only whole."""
    there = set(WORD.findall(text.casefold()))
    return all(word in there or len(word) > 2 and not word.isdigit() and any(one.startswith(word) for one in there) for word in words)


def _about_limit(entry):
    return meanings.find(entry.path)[0]


def _by_variant(found):
    """A text, or the text for each choice of variants."""
    return " or ".join(f"{text} ({', '.join(chosen)})" if chosen else text for chosen, text in found)


class Finder:
    """Finds the records of one folder, and tells them."""

    def __init__(self, rules):
        self.rules = rules

    # -- which records

    def find(self, asked):
        """The record with that path; else those with that ID; else those with that code; else those that hold every word."""
        asked, entries = asked.strip().casefold(), self.rules.book.entries
        by_path, by_id, by_code = ([entry for entry in entries if asked in of(entry)] for of in (
            lambda entry: {name_of(entry).casefold()}, lambda entry: {entry.id.casefold()} - {""}, _codes))
        found = by_path or by_id or by_code
        if found:
            others = [entry for entry in (*by_id, *by_code) if not any(entry is one for one in found)]
            return (found, others) if len(found) == 1 else (found + others, [])
        words = WORD.findall(asked)
        return [entry for entry in entries if words and _holds(words, self._text(entry))], []

    def _text(self, entry):
        """All the words of a record: its name, what is written in it, its `says` filled in, and what a limit means."""
        text = [name_of(entry), entry.kind, json.dumps(entry.data, ensure_ascii=False), *self._said_in.get(entry.where, ())]
        if entry.kind == "limit":
            about = _about_limit(entry)
            text += [about.means, *(field.means for field in about.fields if field.key.rpartition(".")[2] in entry.data)]
        return " ".join(text)

    # -- what is worked out

    def each(self, work):
        """[(the variants' names, a text)] of what work(worker) gives: one text when it is the same for every variant."""
        found = self.rules.season.each(work)
        return found if len({text for _, text in found}) > 1 else [((), found[0][1])]

    @functools.cached_property
    def _says(self):
        """[(record, object, its `says` filled in, for each variant that it needs)] for every record and what is inside it."""
        found = []
        for field in fields.walk(self.rules.book, []):
            if field.holds == "says":
                before = field.where.partition(" ")[2].removeprefix(f"{field.entry.path}.").split(".")[:-1]
                found.append((field.entry, field.owner, self.each(lambda worker, field=field, before=before: says.fill(worker, field.entry, field.owner, before, field.node))))
        return found

    @functools.cached_property
    def said(self):
        """{id of an object: its `says` filled in, for each variant that it needs}."""
        return {id(owner): texts for _, owner, texts in self._says}

    @functools.cached_property
    def _said_in(self):
        found = {}
        for entry, _, texts in self._says:
            found.setdefault(entry.where, []).extend(text for _, text in texts)
        return found

    # -- what is told

    def line(self, entry):
        """What a record says, else its name, else what it holds; what a limit means, and its numbers."""
        said = self.said.get(id(entry.data))
        named = next((entry.data[name] for name in ("name", "title", "for") if isinstance(entry.data.get(name), str)), None)
        held = {name: node for name, node in entry.data.items() if name not in ("src", "code", "says", "alliance")}
        short = "; ".join(_Full(self, entry).short(held)) or f"has {', '.join(held) or NOTHING}"
        text = f"{_about_limit(entry).means} {short}" if entry.kind == "limit" else said[0][1] if said else named or short
        return f"{name_of(entry)} ({entry.kind}): {text if len(text) <= LONG else text[:LONG].rpartition(' ')[0] + ' ...'}"

    def full(self, entry):
        return [f"{name_of(entry)} ({entry.file}.json, {entry.kind})", *("  " + one for one in _Full(self, entry).lines())]


class _Full:
    """Tells the fields of a record as they are written, with what is worked out from them."""

    def __init__(self, finder, entry):
        self.finder, self.entry = finder, entry

    def lines(self):
        return self.object(self.entry.data, ())

    def short(self, held):
        """The fields that go on one line."""
        return [f"{name} {self.row(node)}" for name, node in held.items() if _on_one_line(node)]

    def object(self, data, steps):
        found = []
        for name, node in data.items():
            if name == "says" and id(data) in self.finder.said:
                found += [f"says{f' ({', '.join(chosen)})' if chosen else ''}: {text}" for chosen, text in self.finder.said[id(data)]]
            elif steps == ("starts",) and isinstance(node, str) and node in word_list("starts"):
                found.append(f"{name}: {self.worked(lambda worker, name=name: worker.get(f'{self.entry.path}.starts.{name}'))} ({node})")
            elif _on_one_line(node):
                found.append(f"{name}: {self.row(node)}")
            else:
                inner = self.object(node, (*steps, name)) if isinstance(node, dict) else self.items(node, (*steps, name))
                found += [f"{name}:", *("  " + one for one in inner)]
        return found

    def items(self, node, steps):
        """A line for each thing in a list, or several for an object."""
        found = []
        for one in node:
            first, *rest = self.object(one, steps) if isinstance(one, dict) and one else [self.row(one)]
            found += [f"- {first}", *("  " + line for line in rest)]
        return found

    def row(self, node, inside=False):
        """What goes on one line."""
        if isinstance(node, list):
            text = ", ".join(self.row(one, True) for one in node) or NOTHING
            return f"[{text}]" if inside else text
        if isinstance(node, dict):
            return f"{{{', '.join(f'{name}: {self.row(one, True)}' for name, one in node.items())}}}" if node else NOTHING
        if isinstance(node, str) and node.startswith("="):
            return f"{self.worked(lambda worker: worker.formula(node))} ({node})"
        return str(node).lower() if isinstance(node, bool) else str(node)

    def worked(self, work):
        return _by_variant(self.finder.each(lambda worker: work(worker).printed))


def _on_one_line(node):
    """Whether it is one value, a list of them, or a list of such lists that are no conditions."""
    if isinstance(node, list):
        return all(not isinstance(one, (dict, list)) for one in node) or all(isinstance(one, list) and not _is_condition(one) and _on_one_line(one) for one in node)
    return not isinstance(node, dict) or not node


def _is_condition(node):
    return len(node) == 3 and isinstance(node[1], str) and node[1] in (*word_list("measures"), *word_list("compares"))
