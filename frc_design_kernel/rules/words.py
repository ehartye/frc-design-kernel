"""Every word and every ID that a field names: conditions, times, costs, people, places, parts, sources and paths.

    load(folder)     (Book, [DesignError]) with every fault; the Book is None when the JSON itself does not read
    check(book)      [DesignError] for a Book: what fields.py finds, and every word and ID that is wrong
    leaves(book)     every Leaf (values.py) of the fields, and those inside conditions and longer_than
    paths_in(text)   the paths that a formula names

What a condition means, when a name is true and what a formula gives are not worked out here: only that each of them is
written with words of the lists, and names things that are there.
"""
import re
from dataclasses import replace
from fractions import Fraction

from ..errors import DesignError, unknown
from . import fields, quantity, read, values
from .read import ID, names, word_list

PLACED = tuple(kind for kind, about in names()["kinds"].items() if about.get("placed"))             # what a position can be given for
NEED_GEOMETRY = tuple(kind for kind, about in names()["kinds"].items() if about.get("geometry"))    # whoever names one needs to know where it is
PATH = re.compile(r"(?<![\w.@])[A-Za-z][A-Za-z0-9_]*(?:@[a-z]+)?(?:\.[A-Za-z0-9_]+)*(?!\s*\()(?![\w.@])")
IN_SAYS = re.compile(r"\{([^{}]*)\}")
WHEN = re.compile(r"(?:not )?(?:(my|their) )?([A-Za-z][A-Za-z0-9_]*)")
TYPED = re.compile(r"(?<![\w.:/-])" + quantity.PLUS + r"(?![\w:/-]|\.\d)")
OTHER = re.compile(r"\.(?:was|differs)\[")          # in the place of a Leaf that is not the value to use
ONE_NUMBER = re.compile("(?<![A-Za-z0-9])" + quantity.NUMBER)


def load(folder):
    """(the Book, every fault); (None, the faults) when a file does not read."""
    data, faults = read.read_files(folder)
    if faults:
        return None, faults
    book, faults = read.gather(folder, data)
    return book, faults + check(book)


def check(book):
    """Every fault in the names, values, words and IDs of a book, in the order of its files."""
    faults = []
    for _ in leaves(book, faults):
        pass
    files = [f"{file}.json" for file in names()["files"]]
    return sorted(faults, key=lambda fault: files.index(fault.where.split(" ")[0]))


def leaves(book, faults=None):
    """Every Leaf of a book. What is wrong goes into faults."""
    faults = [] if faults is None else faults
    found = list(fields.leaves(book, faults))
    words = Words(book, faults)
    words.left_over()
    for field in fields.walk(book, []):
        found += words.field(field)
    words.formulas(found)
    words.geometry()
    words.typed_twice(found)
    return found


def paths_in(text):
    """The paths that a formula names, in order. A name before a bracket is a function."""
    return [found[0] for found in PATH.finditer(text)]


class Words:
    """Checks what fields name, against the book's own records."""

    def __init__(self, book, faults):
        self.book, self.faults = book, faults
        self.reader = values.Reader(book, faults)
        self.ids = {kind: book.of_kind(kind) for kind in names()["kinds"]}
        self.things = book.of_kind(*PLACED, "piece")
        self.loads = [e.id for e in book.entries if e.kind == "part" and "on" in e.data]
        self.named = {}         # {ID of a thing: where a rule names it and must know where it is}
        self.found = []         # the Leaves of the field that is being read
        self.said = []          # every field of words that has been read
        self.missing = book.missing

    def fault(self, where, problem, fix):
        self.faults.append(DesignError(where, problem, fix))

    def field(self, field):
        """Check what one field names; the Leaves of the values in it."""
        self.found = []
        method = getattr(self, "holds_" + field.holds.replace(" ", "_"), None)
        if method:
            method(field, field.node, field.where)
        if field.holds == "says" and isinstance(field.node, str):
            self._says(field)
            self.said.append(field)
        if field.entry.kind == "conduct" and field.name == "act" and not set(names()["kinds"]["conduct"]["act_needs"]) & set(field.entry.data):
            self.fault(field.entry.where, "has an act with nothing to judge", "Give it must_not, only_if or limit, or leave out the act")
        return self.found

    # -- names of one kind

    def one(self, node, known, what, where):
        if not isinstance(node, str) or node not in known:
            self.faults.append(unknown(where, what, node, known))

    def list(self, node, where):
        """(one thing, its place) for each of a list."""
        if not isinstance(node, list):
            self.fault(where, "is not a list", "Write it between [ and ]")
            return []
        return [(one, f"{where}[{i}]") for i, one in enumerate(node)]

    def several(self, node, known, what, where):
        for one, at in self.list(node, where):
            self.one(one, known, what, at)

    def either(self, node, where):
        """(one thing, its place) for one name or a list of them."""
        return self.list(node, where) if isinstance(node, list) else [(node, where)]

    def holds_award(self, field, node, where):
        self.one(node, self.ids["award"], "award", where)

    def holds_awards(self, field, node, where):
        self.several(node, self.ids["award"], "award", where)

    def holds_foul(self, field, node, where):
        self.one(node, self.ids["foul"], "foul", where)

    def holds_fouls(self, field, node, where):
        self.several(node, self.ids["foul"], "foul", where)

    def holds_places(self, field, node, where):
        self.several(node, self.ids["place"], "place", where)

    def holds_piece(self, field, node, where):
        self.one(node, self.ids["piece"], "piece", where)

    def holds_pieces(self, field, node, where):
        for one, at in self.either(node, where):
            self.one(one, self.ids["piece"], "piece", at)

    def holds_by_piece(self, field, node, where):
        for piece in node if isinstance(node, dict) else ():
            self.one(piece, self.ids["piece"], "piece", where)

    def holds_starts(self, field, node, where):
        self.holds_by_piece(field, node, where)
        spots = len(read.spot_names(field.owner.get("spots")))
        for piece, given in node.items() if isinstance(node, dict) else ():
            many = given.get("is") if isinstance(given, dict) and "each" not in given else given
            if spots and many == spots:
                self.fault(f"{where}.{piece}", f"types {many}, which its {spots} spots already make", 'Write {"each": "spot", "is": 1}')

    def left_over(self):
        """Only one place starts with what is left over of a piece."""
        first = {}
        for entry in self.ids["place"].values():
            starts = entry.data.get("starts")
            for piece, given in starts.items() if isinstance(starts, dict) else ():
                if given in word_list("starts"):
                    if piece in first:
                        self.fault(f"{entry.where}.starts.{piece}", f'is left over, and so is that of {first[piece]}', "Write how many there are in one of them")
                    first.setdefault(piece, entry.id)

    def holds_hold_limit(self, field, node, where):
        if values.is_group(node):
            self.holds_by_piece(field, node, where)

    def holds_piece_count(self, field, node, where):
        self.one(field.name, self.ids["piece"], "piece", field.entry.where)

    def holds_period(self, field, node, where):
        if "periods" not in self.missing:
            self.one(node, self.ids["period"], "period", where)

    def holds_after_period(self, field, node, where):
        self.holds_period(field, field.name.removeprefix("after_"), where)

    def holds_given_to(self, field, node, where):
        self.one(node, [*word_list("gives_to"), *self.book.of_kind(*PLACED)], "place", where)

    def holds_goes_to(self, field, node, where):
        self.one(node, [*word_list("goes_to"), *self.book.of_kind(*PLACED)], "place", where)

    def holds_several_people(self, field, node, where):
        self.several(node, self.book.people, "person", where)

    def holds_who(self, field, node, where):
        self.several(node, [*word_list("who"), *self.book.people], "person", where)

    def holds_loads(self, field, node, where):
        self.several(node, self.loads, "load", where)
        if "kind" not in field.entry.data:
            self.fault(where, "is on a thing that runs nothing: it has no kind", "Give it the kind of device that it is, or leave only_for out")

    def holds_longer_than(self, field, node, where):
        if isinstance(node, str) and ID.fullmatch(node):
            self.one(node, self.ids["term"], "term", where)
        else:
            self.found += self.reader.value(field.entry, node, "time", where)

    # -- things, as my, their or any and an ID

    def thing(self, node, where, bare=False, measured=False, also=()):
        """An ID of a thing with whose it is; bare allows the ID alone, and also has more words for a hint."""
        owner, space, name = node.partition(" ") if isinstance(node, str) else ("", "", "")
        if not space and (bare or self.of_each(owner)):
            name = owner
            if self.of_each(name):
                owners = [f"{who} {name}" for who in word_list("owners")]
                self.fault(where, f'"{name}" is one of each alliance, and nobody is in front', f"Write {', '.join(owners[:-1])} or {owners[-1]}")
                return
        elif owner not in word_list("owners") or not space:
            self.fault(where, f'"{node}" does not name a thing', f"Write {', '.join(word_list('owners'))} and then an ID")
            return
        self.one(name, [*self.things, *also], "thing", where)
        kind = self.things[name].kind if name in self.things else None
        if kind in NEED_GEOMETRY or measured and kind in PLACED:
            self.named.setdefault(name, where)

    def of_each(self, name):
        return name in self.things and self.things[name].data.get("alliance") == "each"

    def words_or_things(self, node, where, measured=False):
        """A list in which my, their or any with one ID, or an ID alone, is a thing, and all else is words."""
        for one, at in self.list(node, where):
            if not isinstance(one, str) or not one.strip():
                self.fault(at, "is not words", "Write words between quotes")
            elif re.fullmatch(rf"(?:{'|'.join(word_list('owners'))}) {ID.pattern}", one) or one in self.things:
                self.thing(one, at, bare=True, measured=measured)

    def holds_things(self, field, node, where):
        for one, at in self.either(node, where):
            self.thing(one, at, bare=True)

    def holds_things_touched(self, field, node, where):
        for one, at in self.either(node, where):
            if one not in (words := word_list("touched")):
                self.thing(one, at, bare=True, also=[word.partition(" ")[2] for word in words])

    def holds_touchable(self, field, node, where):
        self.words_or_things(node, where)

    # -- when and conditions

    def holds_when(self, field, node, where):
        known = [*self.ids["period"], *self.ids["window"], *self.ids["state"], *(name for kind in self.book.variants.values() for name in kind)]
        for one, at in self.list(node, where):
            got = WHEN.fullmatch(one) if isinstance(one, str) else None
            if not got:
                self.fault(at, f'"{one}" is not a name of a period, window, state or variant', 'Write the name, with "not", "my" or "their" in front if need be')
            elif got[1] and got[2] in known and got[2] not in self.ids["state"]:
                self.fault(at, f'"{got[2]}" is nobody\'s: only a state can be my or their', f'Write "{got[2]}"')
            elif "periods" not in self.missing:
                self.one(got[2], known, "period, window, state or variant", at)

    def holds_variants(self, field, node, where):
        """A variant's name is its own: no period, window or state has it, and no other kind of variant."""
        seen = {}
        for kind, given in self.book.variants.items():
            for name in dict.fromkeys(given):
                taken = next((what for what in ("period", "window", "state") if name in self.ids[what]), None)
                if taken or name in seen:
                    other = f"a {taken} of that name" if taken else f"a variant of {seen[name]} of that name"
                    self.fault(f"{where}.{kind}", f'"{name}" is taken: there is {other}', "Choose another name, so that a when can mean only one of them")
                seen.setdefault(name, kind)

    def holds_list_of_whens(self, field, node, where):
        for one, at in self.list(node, where):
            self.holds_when(field, one, at)

    def holds_cap(self, field, node, where):
        if isinstance(node, dict) and "when" in node:
            self.holds_when(field, node["when"], f"{where}.when")

    def holds_must_not(self, field, node, where):
        if node is not True:
            self.holds_conditions(field, node, where)

    def holds_conditions(self, field, node, where):
        conditions = self.list(node, where)
        if node == []:
            self.fault(where, "lists no conditions", 'Write conditions, such as [["my bumpers", "partly in", "my yard"]]')
        for one, at in conditions:
            if isinstance(one, dict):
                self._any_or_all(field, one, at)
            elif isinstance(one, list) and len(one) == 3:
                self._condition(field, one, at)
            else:
                self.fault(at, "is not a condition", "Write [who, how, what], or {\"any\": [...]} or {\"all\": [...]} of them")

    def _any_or_all(self, field, node, where):
        groups = word_list("groups")
        for name in node:
            if name not in (*groups, "when"):
                self.faults.append(unknown(where, "field of a group of conditions", name, (*groups, "when")))
                return
        if len(set(groups) & set(node)) != 1:
            self.fault(where, "does not say one of any or all", 'Write {"any": [...]} or {"all": [...], "when": [...]}')
        for name, inner in node.items():
            (self.holds_when if name == "when" else self.holds_conditions)(field, inner, f"{where}.{name}")

    def _condition(self, field, condition, where):
        who, how, what = condition
        self._someone(who, where)
        self.one(how, [*word_list("measures"), *word_list("compares")], "word", where)
        if isinstance(what, list):
            if not what:
                self.fault(where, "names nothing in its list", "Name things, or words for a part that has no ID")
            self.words_or_things(what, where, measured=how in word_list("measures"))
        elif not isinstance(what, str) or what.startswith("=") or re.match(r"-?[0-9]", what):
            leaves = self.reader.value(field.entry, what, None if not isinstance(what, bool) else "number", where)
            self.found += [replace(leaf, one=where) for leaf in leaves] if how in word_list("compares") else leaves
        elif what not in word_list("what"):
            self._what(what, where, how in word_list("measures"))

    def _what(self, what, where, measured):
        owner, _, rest = what.partition(" ")
        if owner in word_list("owners") and rest or self.of_each(what):
            self.thing(what, where, measured=measured)
        else:
            self.fault(where, f'"{what}" names nothing', f'Write my, their or any and an ID, a number, or one of: {", ".join(word_list("what"))}')

    def _someone(self, who, where):
        owner, _, name = who.partition(" ") if isinstance(who, str) else ("", "", "")
        if owner in word_list("the"):
            self.one(name, [*word_list("the_piece"), *self.ids["piece"]], "piece", where)
        elif owner in word_list("sides"):
            self.one(name, [*word_list("someone"), *self.ids["count"]], "actor or count", where)
        else:
            self.fault(where, f'"{who}" is not someone or something counted',
                       f"Write {', '.join(word_list("sides"))} and then {', '.join(word_list("someone"))} or an ID of counts; or the and a piece")

    # -- costs

    def holds_cost(self, field, node, where):
        costs = self.list(node, where) if isinstance(node, list) else []     # fields.py says that it is not a list
        for i, (one, at) in enumerate(costs):
            if isinstance(one, str):
                self.holds_foul(field, one, at)
            elif isinstance(one, dict):
                self._one_cost(one, [c for j, (c, _) in enumerate(costs) if j != i], at)

    def _one_cost(self, one, others, where):
        if "award" in one and "to" not in one:
            self.fault(where, 'gives an award and has no "to"', 'Say who gets it, such as "to": "their alliance"')
        if "instead_of" in one:
            given = [c for c in others if isinstance(c, str)]
            for c in others:
                given += [c.get("foul")] if isinstance(c, dict) and "foul" in c else c["either"] if isinstance(c, dict) and isinstance(c.get("either"), list) else []
            if isinstance(one["instead_of"], str) and one["instead_of"] in self.ids["foul"] and one["instead_of"] not in given:
                self.faults.append(unknown(f"{where}.instead_of", "foul of this cost", one["instead_of"], [g for g in given if isinstance(g, str)]))

    # -- paths in words and formulas

    def _says(self, field):
        if "{" in IN_SAYS.sub("", field.node):
            self.fault(field.where, "has a { that is not closed", "Close the name between { and }, such as {limits.reach.far}")
        for path in IN_SAYS.findall(field.node):
            try:
                self.own_or_any(field, path)
            except DesignError as problem:
                self.faults.append(problem.under(field.where))

    def own_or_any(self, field, path):
        """What a {name} in says names: a field of its own object or record, or else a path."""
        head = path.partition(".")[0]
        for data in (field.owner, field.entry.data):
            if head in data:
                return self.book.within(data, path, field.entry)
        if head in self.missing:
            return None
        return self.book.look(path)

    def formulas(self, found):
        for leaf in found:
            for path in paths_in(leaf.node) if isinstance(leaf.node, str) and leaf.node.startswith("=") else ():
                if path.partition(".")[0] in self.missing:
                    continue
                try:
                    self.book.look(path)
                except DesignError as problem:
                    self.faults.append(problem.under(leaf.where))

    # -- what needs the whole book

    def geometry(self):
        """Whatever a rule or a score names must say where it is, or say why it does not."""
        for name, where in self.named.items():
            record = self.things[name]
            if not {"outline", "shape", "at", "spots", "no_geometry"} & set(record.data) and not {"from", "to"} <= set(record.data):
                self.fault(record.where, f"has no geometry, and {where} names it", 'Give it an outline, a from and to, a shape or an at, or "no_geometry": "why"')

    def typed_twice(self, found):
        """A single number typed in says that the record holds as a whole value: it would not change with the value."""
        own = {}
        for leaf in found:
            number = _whole(leaf)
            if number is not None and not OTHER.search(leaf.where):
                own.setdefault(leaf.entry.where, {}).setdefault(number, leaf.where)
        for field in self.said:
            for typed in TYPED.findall(IN_SAYS.sub("", field.node)):
                held = own.get(field.entry.where, {}).get(_exact(typed))
                if held:
                    self.fault(field.where, f'types {typed}, which {held.split(" ", 1)[1]} holds', "Name the field between { and }, so that the number is written once")


def _exact(text):
    try:
        return quantity.exact(text)
    except (ValueError, ZeroDivisionError):
        return None


def _whole(leaf):
    """The number of a value that is one plain number, or None."""
    if isinstance(leaf.node, bool) or not isinstance(leaf.node, (int, float, str)):
        return None
    if not isinstance(leaf.node, str):
        return Fraction(leaf.node)
    numbers = [] if leaf.node.startswith("=") else ONE_NUMBER.findall(leaf.node)
    return _exact(numbers[0]) if len(numbers) == 1 else None
