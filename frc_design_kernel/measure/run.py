"""A bench: one loaded design, ready to be measured, in this process or shared between worker processes.

Nothing here measures; it only hands out work and gathers it. The design is built once in each process that measures,
the first time that process is asked something. A clearance along a motion is cut into shares, each every n-th pair of
the motion, so the rows come back in the same order whichever worker did which share, and the result is the same for
any worker count; any other job is one task. Every asking is measured: nothing is kept from one asking to the next.
"""
import math
from contextlib import closing
from dataclasses import dataclass, field

from ..source.load import load
from ..workers import EVERY_S, Crew
from . import jobs as kinds

PAIRS_PER_SHARE = 500    # a motion with fewer pairs than this is one piece of work


@dataclass(frozen=True)
class Ask:
    """One job to answer: the normalized job, what progress calls it, and what it is limited to or built with."""
    job: dict
    label: dict                                     # {"job": id}, and at an adjustment's end which end it is
    focus: tuple | None = None                      # a clearance of only the pairs with one of these solids in them
    parameters: dict = field(default_factory=dict)  # parameters set to other values than the design's


@dataclass(frozen=True)
class Task:
    """What a process is given: an ask, its share of the pairs (None for a whole job), and which asking it belongs to."""
    ask: Ask
    share: tuple | None
    asking: int


class Built:
    """The design as built in one process: as it is and, one at a time, with parameters set to other values."""

    def __init__(self, design):
        self.design, self.nominal, self.variant = design, None, (None, None)
        self.fixed_of, self.fixed = None, {}        # what fixed pairs measured, shared by the jobs of one asking of one build

    def assembly(self, parameters=None):
        from ..builder.assembly import build
        if not parameters:
            self.nominal = self.nominal or build(self.design)
            return self.nominal
        key = tuple(sorted(parameters.items()))
        if self.variant[0] != key:
            self.variant = (key, build(load(self.design.path, parameters, self.design.field)))
        return self.variant[1]

    def answer(self, task, meter):
        ask, assembly = task.ask, self.assembly(task.ask.parameters)
        if task.share is None:
            return kinds.perform(assembly, ask.job, ask.focus, meter)
        key = (task.asking, tuple(sorted(ask.parameters.items())))
        if self.fixed_of != key:
            self.fixed_of, self.fixed = key, {}
        return kinds.perform_share(assembly, ask.job, task.share, ask.focus, self.fixed, meter)


def begin(design):
    """What a worker process starts with: the function that answers its tasks."""
    return Built(design).answer


class Counts:
    """The progress of one asking: the counts of every task, added up for the job it is part of."""

    def __init__(self, asks, owners, totals, progress):
        self.asks, self.owners, self.totals, self.progress = asks, owners, totals, progress
        self.done = {}

    def hear(self, slot, process, done, of):
        mine = self.owners[slot]
        self.done[slot] = done
        whole = sum(count for other, count in self.done.items() if self.owners[other] == mine)
        self.progress({**self.asks[mine].label, "process": process, "processDone": done, "processOf": of, "done": whole,
                       "of": of if self.totals[mine] is None else self.totals[mine]})


class Bench:
    """A loaded design to measure. progress, when given, hears where the work is, at most every every_s seconds from each
    process: {"job": id, "done", "of", "process", "processDone", "processOf"} (pairs for a clearance or an attachment)."""

    def __init__(self, design, workers=None, progress=None, every_s=EVERY_S):
        self.design, self.progress, self.built, self.askings = design, progress, Built(design), 0
        self.crew = Crew(begin, (design,), workers, every_s, self.built.answer)
        self.workers = self.crew.workers

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.crew.close()

    @property
    def assembly(self):
        """The design as built in this process."""
        return self.built.assembly()

    def pairs(self, ask):
        """How many pairs of solids a clearance along a motion looks at; None for any other job."""
        if ask.job["kind"] != "clearance" or "motion" not in ask.job:
            return None
        names = kinds.present(self.design.data, ask.job)
        others = len(set(names) - set(ask.focus)) if ask.focus else 0
        return math.comb(len(names), 2) - math.comb(others, 2)

    def answers(self, asks):
        """Yield (ask index, the job's answer) as each job finishes: in order in this process, else as the workers finish.

        Closing this generator stops the work and ends the worker processes.
        """
        self.askings += 1
        totals, tasks, owners, parts = [self.pairs(ask) for ask in asks], [], [], []
        for index, ask in enumerate(asks):
            count = 1 if totals[index] is None or totals[index] < PAIRS_PER_SHARE else self.workers
            shares = [None] if totals[index] is None else [(first, count) for first in range(count)]
            tasks += [Task(ask, share, self.askings) for share in shares]
            parts.append({len(owners) + n: None for n in range(len(shares))})
            owners += [index] * len(shares)
        counts = Counts(asks, owners, totals, self.progress) if self.progress else None
        with closing(self.crew.ask(tasks, counts.hear) if counts else self.crew.ask(tasks)) as given:
            for slot, _, part in given:
                mine = owners[slot]
                parts[mine][slot] = part
                if all(found is not None for found in parts[mine].values()):
                    ask = asks[mine]
                    found = list(parts[mine].values())
                    yield mine, found[0] if totals[mine] is None else kinds.combined(self.design.data, ask.job, ask.focus, found)
