"""Which times and states can be true together: rows of points that tie, and states that need each other.

    tie(worker, entry)    the numbers of two rows of an award that may both be true with as many names, or None
    round(book, entry)    the states that a state needs, back to itself, or None

A row counts when all its names are true. Of the rows that are true the one with the most names counts, so two with as many
names must never be true at once. All that can be true at some moment is tried: each stretch of time in a period between the
ends of its windows, each variant, and each state that is not made of others, true or false.
"""
import itertools

from . import times
from .conditions import moments


def round(book, entry):
    """The states that a state's `true` needs, back to itself, or None."""
    trail = [entry.id]

    def walk(state):
        for moment in _moments(book, state):
            if moment.name == entry.id:
                return [*trail, moment.name]
            if moment.name not in trail:
                trail.append(moment.name)
                if found := walk(moment.entry):
                    return found
                trail.pop()
        return None
    return walk(entry)


def _moments(book, state):
    """Every state that a state's `true` names."""
    return [m for names in state.data.get("true", ()) for m in moments(book, names) if m.kind == "state"]


def tie(worker, entry):
    """The numbers, from 1, of two rows of an award that may both be true with as many names in their `when`, or None."""
    rows = [list(row["when"]) for row in entry.data.get("points", ())]
    also = list(entry.data.get("when", ()))
    for (i, one), (j, other) in itertools.combinations(enumerate(rows, 1), 2):
        if len(one) == len(other) and together(worker, [*one, *other, *also]):
            return i, j
    return None


def together(worker, names):
    """Whether all of some names can be true at once."""
    wanted = moments(worker.book, names)
    facts = _Facts(worker, wanted)
    return any(all(facts.true(m, moment, states) for m in wanted) for moment in facts.stretches() for states in facts.states())


class _Facts:
    """What can be so at a moment, as far as some names ask. The variants are those of the worker."""

    def __init__(self, worker, wanted):
        self.worker, self.free = worker, set()
        self._free(wanted, "my")

    def _free(self, wanted, seen_by):
        for moment in wanted:
            if moment.kind == "state" and moment.entry.data.get("true"):
                for names in moment.entry.data["true"]:
                    self._free(moments(self.worker.book, names), _whose(moment, seen_by) or "my")
            elif moment.kind == "state":
                self.free.add((moment.name, _whose(moment, seen_by)))

    def states(self):
        """{(state, whose): true or false}, every way that it may be."""
        for way in itertools.product((False, True), repeat=len(self.free)):
            yield dict(zip(sorted(self.free, key=str), way))

    def stretches(self):
        """(period, the names of the windows that are open), for every stretch of time."""
        windows = times.windows(self.worker).values()
        for period, entry in self.worker.book.of_kind("period").items():
            own = [w for w in windows if w.period == period]
            last = [times.seconds(self.worker, f"{period}.lasts")] if "lasts" in entry.data else [max((w.end for w in own), default=0) + 1]
            cuts = sorted({0, *last, *(n for w in own for n in (w.start, w.end))})
            for at in [(a + b) / 2 for a, b in zip(cuts, cuts[1:])]:
                yield period, {w.name for w in own if w.start < at < w.end}

    def true(self, moment, stretch, states, seen_by="my"):
        period, windows = stretch
        if moment.kind == "period":
            so = moment.name == period
        elif moment.kind == "window":
            so = moment.name in windows
        elif moment.kind == "variant":
            so = self.worker.choice.get(moment.of) == moment.name
        elif moment.entry.data.get("true"):
            side = _whose(moment, seen_by) or "my"
            so = any(all(self.true(m, stretch, states, side) for m in moments(self.worker.book, names)) for names in moment.entry.data["true"])
        else:
            so = states[moment.name, _whose(moment, seen_by)]
        return so != moment.negated


def _whose(moment, seen_by):
    """Whose a state is, as the one who asked sees it: `their` of `their` is mine. A match's state is nobody's."""
    if moment.entry.data.get("of") == "match":
        return None
    return "their" if ((moment.whose or "my") == "their") != (seen_by == "their") else "my"
