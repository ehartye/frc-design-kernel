"""The commands that answer from a game's rules: rules find, check, means and get.

    add(commands)       puts them beside the other commands of the command line
    folder_of(given)    the rules folder: the one given, or of the dated ones in it the newest by name

Each takes --rules, but means, which needs no folder. What get does not know as a flag is a kind of variant of the folder. get
--json prints one object: the answer's `unit` is what its `value`, `low` and `high` are in (mm, kg, s, deg, or that of --unit).
"""
import argparse
import json
import re
import sys
from pathlib import Path

from ..errors import DesignError, unknown
from . import answers, meanings, quantity, words
from .find import Finder
from .read import ALLIANCES, names
from .rules import examine, load_rules
from .values import DATE

FOLDER = "a dated folder of rules, or a folder of dated ones, of which the newest by name is read"
GET_FLAGS = ("--rules", "--alliance", "--spot", "--unit", "--json", "--help")


class _Parser(argparse.ArgumentParser):
    """A parser that may take a flag for each kind of variant, whichever there are in the folder."""
    takes_variants = False

    def parse_known_args(self, args=None, namespace=None):
        if not self.takes_variants:
            return super().parse_known_args(args, namespace)
        rest, chosen, given = [], {}, list(args)
        while given:
            flag, equals, name = given.pop(0).partition("=")
            if not flag.startswith("--") or flag == "--" or flag in GET_FLAGS:
                rest.append(flag + equals + name)
            elif not equals and (not given or given[0].startswith("-")):
                self.error(f"argument {flag}: expected one argument")
            else:
                chosen[flag[2:]] = name if equals else given.pop(0)
        found, more = super().parse_known_args(rest, namespace)
        found.variants = chosen
        return found, more


def add(commands):
    asked = commands.add_parser("rules", help="answer from a game's rules folder").add_subparsers(dest="asked", metavar="{find,check,means,get}", required=True, parser_class=_Parser)
    one = asked.add_parser("find", help="one record in full, by its rule code, its ID or words of it")
    one.add_argument("words", nargs="+", help="a rule code, an ID, or words that must all be there")
    one.add_argument("--rules", required=True, metavar="DIR", help=FOLDER)
    one.set_defaults(run=find)
    one = asked.add_parser("check", help="every fault of a folder, and places to look for what is missing or written twice")
    one.add_argument("--rules", required=True, metavar="DIR", help=FOLDER)
    one.set_defaults(run=check)
    one = asked.add_parser("means", help="what a property, a word or a form means and how it is written; the whole format if none is named")
    one.add_argument("name", nargs="*", help="such as bottom, opening.bottom, limits.reach.far, tape inside or range")
    one.set_defaults(run=means)
    one = asked.add_parser("get", help="a value and what its property means",
                           epilog="Each kind of variant of the folder is a flag too, such as --field welded. One that is not given is the first in game.json.")
    one.takes_variants = True
    one.add_argument("path", help="such as limits.reach.far, or an ID and then its fields")
    one.add_argument("--rules", required=True, metavar="DIR", help=FOLDER)
    one.add_argument("--alliance", default=ALLIANCES[0], help=f"{' or '.join(ALLIANCES)} (default {ALLIANCES[0]})")
    one.add_argument("--spot", help="which of its spots")
    one.add_argument("--unit", help="tell it in this unit")
    one.add_argument("--json", action="store_true", help="tell it as plain data")
    one.set_defaults(run=get)


def folder_of(given):
    folder = Path(given)
    if not folder.is_dir():
        raise DesignError(str(folder), "is not a folder", f"Give {FOLDER}")
    try:
        dated = sorted(one.name for one in folder.iterdir() if DATE.fullmatch(one.name) and one.is_dir())
    except OSError as problem:
        raise DesignError(str(folder), f"cannot be read ({problem.strerror})", "Check the folder") from None
    folder = folder / dated[-1] if dated else folder
    if not any((folder / f"{name}.json").is_file() for name in names()["files"]):
        raise DesignError(str(folder), f"holds no rules: none of {', '.join(f'{name}.json' for name in names()['files'])}", f"Give {FOLDER}")
    return folder


def _count(number, word):
    return f"{number} {word}" if number == 1 else f"{number} {word}s"


def _in(lines):
    return ["  " + line for line in lines]


# ---- find

def find(args):
    finder, asked = Finder(load_rules(folder_of(args.rules))), " ".join(args.words)
    found, others = finder.find(asked)
    if not found:
        raise DesignError("", f'no record has the code, the ID or all the words of "{asked}"', "Try fewer words, or the beginning of one")
    lines = [finder.line(entry) for entry in found] if len(found) > 1 else finder.full(found[0])
    if others:
        lines += ["Also with this ID or code:", *_in(finder.line(entry) for entry in others)]
    print("\n".join(lines))


# ---- check

def check(args):
    folder = folder_of(args.rules)
    book, faults = examine(folder)
    for fault in faults:
        print(f"Error: {fault}", file=sys.stderr)
    print(f"{folder.resolve().name}: {_count(len(faults), 'fault') if faults else 'no faults'}.")
    if book:
        bare = [f"{entry.path}: {entry.data['no_geometry']}" for entry in book.entries if entry.path and "no_geometry" in entry.data]
        equal = _equal_numbers(book)
        print("\n".join([f"{_count(len(bare), 'record')} with no geometry:", *_in(bare),
                         f"{_count(len(equal), 'number')} in more than one record, each a place to look for a value written twice:", *_in(equal)]))
    return 1 if faults else 0


def _equal_numbers(book):
    """A line for each number that more than one record holds with the same unit: the number, and every field that holds it."""
    held = {}
    for leaf in words.leaves(book):
        if isinstance(leaf.node, str) and not words.OTHER.search(leaf.where):
            try:
                got = quantity.read(leaf.node)
            except DesignError:
                continue        # a formula; or a fault, and told as one
            if got.unit:
                numbers = (got.low, got.high) if got.value is None else got.value
                held.setdefault((got.unit, numbers), []).append((leaf, got.printed.removeprefix(f"{got.limit} ")))
    return [f"{min((number for _, number in found), key=len)}: {', '.join(_path(leaf) for leaf, _ in found)}" for found in held.values() if len({leaf.entry.where for leaf, _ in found}) > 1]


def _path(leaf):
    """The path to a value, without the `is` and the `any` that a path leaves out."""
    return re.sub(r"\.is(?=\.|$)|\.any\[[0-9]+\]", "", leaf.where.partition(" ")[2])


# ---- means

def means(args):
    name = " ".join(args.name)
    if not name:
        print("\n".join(line for one in meanings.everything() for line in _short(one)))
        return
    found = meanings.find(name)
    if not found:
        near = " or ".join(f'"{one}"' for one in meanings.near(name))
        raise DesignError("", f'no property, word or form is called "{name}"', f"{f'Did you mean {near}? ' if near else ''}Or run `rules means` with no name to see them all")
    print("\n\n".join("\n".join(_long(one)) for one in found))


def _short(one):
    """One Meaning in the whole format: what it means and what must be there, and for a form its examples."""
    lines = [f"{one.key}{f' ({one.holds})' if one.holds else ''}: {' '.join([one.means, *one.notes])}"]
    return lines + (_in(_examples(one)) if one.key.startswith(("form: ", "unit: ", "roots")) else [])


def _examples(one):
    """How it is written: each example as JSON, or the names of units or of what paths begin with on one line."""
    if one.key.startswith(("unit: ", "roots")):
        return [", ".join(one.examples)] if one.examples else []
    return [json.dumps(example) for example in one.examples]


def _long(one):
    """One Meaning for whoever asks for it, with what it holds and how that is written."""
    lines = [one.means, *one.notes]
    if one.holds:
        lines.append(" ".join([f"Holds: {one.holds}.", *(form.means for form in meanings.find(f"form: {one.form}"))]))
    lines += [f"Written: {example}" for example in _examples(one)]
    lines += [f"{word.key.partition(': ')[2]}: {word.means}" for word in one.words]
    lines += [f"{field.key.rpartition('.')[2]} ({field.holds}): {' '.join([field.means, *field.notes])}" for field in meanings.fields_of(one)]
    return [one.key, *_in(lines)]


# ---- get

def get(args):
    rules = load_rules(folder_of(args.rules))
    for kind in args.variants:
        if kind not in rules.season.variants:
            raise unknown(f"--{kind}", "kind of variant", kind, rules.season.variants)
    worker = rules.season.worker(**args.variants)
    got = rules.get(args.path, args.alliance, args.spot, **args.variants)
    taken = {kind: worker.choice[kind] for kind in rules.season.variants if kind in worker.asked}
    entry, _, own_spot, rest = worker.address(args.path)
    meaning = meanings.of_path(rules.book, args.path if own_spot or not args.spot else ".".join([entry.path, "spots", args.spot, *rest]))
    try:
        if args.json:
            print(json.dumps({
                "path": args.path, "alliance": args.alliance, "spot": args.spot, "variants": taken,
                "means": {"key": meaning.key, "means": meaning.means} if meaning else None, "answer": answers.plain(rules, got, args.unit)}))
            return
        lines = answers.lines(rules, args.path, got, args.unit)
    except DesignError as problem:
        raise problem.under("--unit") from None
    if taken:
        lines.append(f"  variants: {'; '.join(_taken(kind, name, rules.season.variants[kind]) for kind, name in taken.items())}")
    lines.append(f"  {meaning.key}: {meaning.means}" if meaning else f"  {args.path}: a value of this record's own, which the format does not name.")
    print("\n".join(lines))


def _taken(kind, name, known):
    """Which variant an answer is for, and which others there are."""
    others = [one for one in known if one != name]
    return f"{kind} {name}, not {' or '.join(others)}" if others else f"{kind} {name}"
