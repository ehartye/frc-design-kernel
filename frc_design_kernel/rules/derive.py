"""Everything that is worked out, worked out once for each variant that it needs: what cannot be is a fault.

    faults(book, found)    [DesignError], beside those found in reading

One mistake is told once, where it is written. What needs a value that does not read, or that cannot be worked out, is passed
over: so everything is looked at once, and then again without what uses a value that was at fault.
"""
from ..errors import DesignError, unknown
from . import alliances, conditions, fields, outlines, parts, pieces, quantity, says, shapes, ties, times, words
from .read import names
from .values import in_words
from .worker import Loop, Season, TooLong, Wrong, inside


def faults(book, found=()):
    """Every fault in what is worked out, in the order of the files."""
    if book.missing:
        return []
    all_of_it = words.leaves(book), list(fields.walk(book, []))
    bad = {_place(f) for f in found}
    first = _Check(book, all_of_it, bad).all()
    again = _Check(book, all_of_it, bad | {_place(f) for f in first}, bad).all() if len(first) > 1 else first
    return sorted(again, key=lambda fault: _files().index(fault.where.split(" ")[0]))


def _first(leaf):
    """The name of the field of its record that a Leaf is in."""
    return leaf.where.removeprefix(f"{leaf.entry.where}.").partition(".")[0].partition("[")[0]


def _place(fault):
    """The file and the path of a fault."""
    return " ".join(fault.where.split(" ")[:2])


def _files():
    return [f"{file}.json" for file in names()["files"]]


class _Check:
    """Looks at everything. bad is where a value is at fault; unread, where it does not even read."""

    def __init__(self, book, all_of_it, bad, unread=None):
        self.book, self.faults, self.told = book, {}, set()
        self.leaves, self.fields = all_of_it
        self.unread = set(bad if unread is None else unread)
        several = self.several()
        self.unread |= several
        self.season = Season(book, bad | several)

    def several(self):
        """Where a range is written, or limits of which one is enough, and one number is needed."""
        held = [field.where for field in self.fields if field.one]
        found = set()
        for leaf in self.leaves:
            a_range = _is_range(leaf.node)
            needed = leaf.one or next((one for one in held if inside(leaf.where, one)), None) if a_range or ".any[" in leaf.where else None
            rest, any_of, _ = leaf.where.removeprefix(needed or "").partition(".any[")      # before the place there may be one of a group of conditions
            if needed and (a_range or any_of):
                where = needed + rest
                found.add(where)
                what = "lists limits of which one is enough" if any_of else f'"{leaf.node}" is a range'
                self.fault(DesignError(where, f"{what}, and one number is needed here", "Write one number; with +/- it may have a tolerance"))
        return found

    def all(self):
        for leaf in self.leaves:
            if isinstance(leaf.node, str) and leaf.node.startswith("=") and self.reads(leaf.where):
                self.formula(leaf)
        for entry in self.book.entries:
            if entry.path:
                getattr(self, f"of_{entry.kind}", self.of_any)(entry)
        for field in self.fields:
            if self.reads(field.where):
                self.field(field)
        for piece in self.book.of_kind("piece"):
            self.piece(piece)
        return list(self.faults.values())

    def reads(self, *wheres):
        """Whether reading found no fault at any of some places, in them or around them."""
        return not any(inside(one, where) or inside(where, one) for one in self.unread for where in wheres)

    # -- one thing, for every variant that it needs

    def over(self, work, where):
        """Do work(worker) for each variant that it needs. What is wrong is a fault at where, or at the place it tells."""
        self.season.each(lambda worker: self._one(worker, work, where))

    def _one(self, worker, work, where):
        worker.own = where
        try:
            work(worker)
        except Wrong:
            pass            # a formula, which is told where it is written
        except DesignError as problem:
            self.fault(problem if problem.where.split(" ")[0] in _files() else problem.under(where))
        finally:
            worker.own = None

    def fault(self, problem):
        self.faults.setdefault(str(problem), problem)

    def formula(self, leaf):
        """One formula: whether it can be worked out, and gives what its field holds."""
        def work(worker):
            try:
                kind = worker.once(leaf.where, lambda: worker.formula(leaf.node)).kind     # as long a chain as for whoever asks for it
            except Wrong as problem:
                return self.tell(problem, leaf.node, leaf.where)
            if kind == "mass" and leaf.entry.path == "limits.weight" and (name := _first(leaf)) not in fields.spec_for(leaf.entry).known:
                raise unknown(leaf.entry.where, "weight", name, names()["limits"]["weight"]["fields"])
            if leaf.kind not in (None, kind):
                raise DesignError(leaf.where, f'the formula "{leaf.node}" gives {in_words(kind)}, not {in_words(leaf.kind)}', f"Write {in_words(leaf.kind)}")
        self.over(work, leaf.where)

    def words(self, worker, field, before):
        """One text of words: whether each {name} in it can be filled in."""
        try:
            worker.once(field.where, lambda: says.fill(worker, field.entry, field.owner, before, field.node))
        except Wrong as problem:
            self.tell(problem, says.path_of(field.entry, before), field.where)

    def tell(self, problem, own, where):
        """Raise what is wrong with a formula or words at their own place. What another place tells is passed over, and a loop, or
        a chain that is too long, is told once."""
        told = frozenset(problem.texts) if isinstance(problem, Loop) else TooLong if isinstance(problem, TooLong) else None
        if told in self.told or problem.text != own and told is not TooLong:
            return
        if told:
            self.told.add(told)
        raise DesignError(where, problem.problem, problem.fix) from None

    # -- records

    def of_any(self, entry):
        if not alliances.moves(entry, "faces") or not self.reads(*(f"{entry.where}.{name}" for name in (*alliances.MOVES, "spots", "symmetry", "alliance"))):
            return
        outline = entry.data.get("outline")
        if alliances.moves(entry, "outline") and isinstance(outline, dict) and not {"is", "by"} & set(outline) and not {"at", "spots", "no_geometry"} & set(entry.data):
            self.fault(DesignError(entry.where, 'has an outline around a middle, and no "at"', 'Give it its "at", or "no_geometry": "why"'))
        known = alliances.spots(entry) or [None]
        for alliance, spot in [*(("blue", spot) for spot in known), *([("red", known[0])] if entry.data.get("alliance") == "each" else [])]:
            self.over(lambda worker: self._place(worker, entry, alliance, spot), entry.where)     # red needs only the field's size besides

    def _place(self, worker, entry, alliance, spot):
        place = alliances.Place(worker, entry, alliance, spot)
        for name in ("at", "from", "to"):
            if name in place.data and alliances.moves(entry, name):
                alliances.numbers(place.point(name))
        place.faces()

    def of_window(self, entry):
        if self.reads(entry.where):
            self.over(lambda worker: times.window(worker, entry), entry.where)

    def of_judged(self, entry):
        for award in entry.data["awards"] if self.reads(*(one.where for one in self.book.of_kind("judged").values())) else ():
            self.over(lambda worker: times.judged(worker, award), entry.where)

    def of_state(self, entry):
        if self.reads(entry.where) and self._clock() and (found := ties.round(self.book, entry)) and frozenset(found) not in self.told:
            self.told.add(frozenset(found))
            self.fault(DesignError(f"{entry.where}.true", f"needs itself: {' needs '.join(found)}", "Say what makes one of them true without the others"))

    def _clock(self):
        return not any(where.startswith("clock.json") for where in self.unread)

    def of_award(self, entry):
        if not self._clock() or not self.reads(f"{entry.where}.points", f"{entry.where}.when") or any(ties.round(self.book, state) for state in self.book.of_kind("state").values()):
            return

        def work(worker):
            if found := ties.tie(worker, entry):
                raise DesignError(f"{entry.where}.points", f"rows {found[0]} and {found[1]} may both be true, and have as many names in their when", 'Add a name to one of them, such as "not lit"')
        self.over(work, entry.where)

    def of_place(self, entry):
        self.of_any(entry)
        for piece in entry.data.get("starts", ()) if self.reads(f"{entry.where}.starts") else ():
            if self._counted(piece):
                self.over(lambda worker: pieces.count(worker, entry, piece), f"{entry.where}.starts.{piece}")

    def _counted(self, piece):
        """Whether all that the counts of a piece are worked out from reads."""
        return self.reads(f"scoring.json total.{piece}", *(f"{entry.where}.{name}" for entry in self.book.of_kind("place").values() for name in (f"starts.{piece}", "spots", "alliance")))

    def piece(self, piece):
        if self._counted(piece):
            self.over(lambda worker: pieces.check(worker, piece), f"scoring.json total.{piece}")

    def of_part(self, entry):
        if "kind" in entry.data and self.reads(entry.where, *(f"{load.where}.on" for load in parts.loads(self.book))):
            self.over(lambda worker: parts.runs(worker, entry.path), entry.where)

    # -- fields

    def field(self, field):
        if field.holds == "shape":
            self.over(lambda worker: shapes.drawn(worker, field.entry, field.node, False), field.where)
        elif field.holds == "outline":
            self.over(lambda worker: outlines.checked(worker, field.entry, field.node, False), field.where)
        elif field.holds == "says":
            before = field.where.partition(" ")[2].removeprefix(field.entry.path + ".").split(".")[:-1]
            self.over(lambda worker: self.words(worker, field, before), field.where)
        elif field.key in ("tag.at", "tag.faces"):
            self.over(lambda worker: worker.get(field.where.partition(" ")[2]), field.where)


def _is_range(node):
    try:
        return isinstance(node, str) and quantity.read(node).value is None
    except DesignError:
        return False
