"""The cheapest sufficient bracket plan: one input at a time about the nominal, stopping at the first failure.

An input with an assumed range is run at both ends of the range. If an end changes the outcome, the edge is closed in
on by halving between the last value that held and the first that did not, a few times. An input with a listed set of
values is run outward from the nominal on each side, and a side stops at its first failure. Nothing here is a grid.
"""

DEFAULT_REFINE = 3


class Bracket:
    """One input's plan. ask() gives the values to run next; tell() takes each result; summary() reports what was found."""

    def __init__(self, path, nominal, unit="", low_high=None, values=None, refine=DEFAULT_REFINE):
        self.path, self.nominal, self.unit, self.range = path, nominal, unit, low_high
        self.refine = refine if low_high is not None else 0
        self.rows, self.nominal_met = {}, None
        if low_high is not None:
            todo = [[v] for v in low_high if v != nominal]
        else:
            todo = [sorted((v for v in values if v < nominal), reverse=True), sorted(v for v in values if v > nominal)]
        # Each side walks outward from the nominal: what is left to run, the last value that held, and its edge once found.
        self.sides = [{"todo": values, "held": nominal, "edge": None} for values in todo if values]

    def most_runs(self):
        return sum(len(side["todo"]) + self.refine for side in self.sides)

    def ask(self):
        """The values to run in this round: the next of each side still going, and the next halving of each open edge."""
        wanted = []
        for side in self.sides:
            if side["edge"] is None and side["todo"]:
                wanted.append(side["todo"][0])
            elif side["edge"] is not None and side["edge"][2] > 0:
                wanted.append((side["edge"][0] + side["edge"][1]) / 2)
        return wanted

    def tell(self, value, met, outcome, measures, run_id):
        self.rows[value] = {"value": value, "met": met, "outcome": outcome, "measures": measures, "run": run_id}
        same = met == self.nominal_met
        for side in self.sides:
            edge = side["edge"]
            if edge is None and side["todo"] and side["todo"][0] == value:
                side["todo"].pop(0)
                if same:
                    side["held"] = value
                else:
                    side["edge"] = [side["held"], value, self.refine]       # this side stops at its first change of outcome
            elif edge is not None and edge[2] > 0 and value == (edge[0] + edge[1]) / 2:
                edge[0 if same else 1] = value
                edge[2] -= 1

    def summary(self):
        """What this input's runs showed. "held" means no value tried changed the outcome."""
        flips = [{"holdsAt": side["edge"][0], "changesAt": side["edge"][1]} for side in self.sides if side["edge"] is not None]
        out = {"input": self.path, "unit": self.unit, "nominal": self.nominal, "source": "assumed" if self.range is not None else "listed",
               "values": [self.rows[v] for v in sorted(self.rows)], "held": not flips, "flips": flips}
        if self.range is not None:
            out["range"] = list(self.range)
        return out


class Window:
    """The settings of one adjustment that pass, while an uncertain input is held at one end of its range.

    A few points are tried: both ends of the adjustment's range and its nominal setting. Where a passing setting sits
    next to a failing one, the edge is closed in on by halving, a round or two. A stepped adjustment only takes its steps.
    """

    def __init__(self, low, high, nominal, step=None, refine=2):
        self.low, self.high, self.step, self.left = low, high, step, refine
        self.points = sorted({self.snap(v) for v in (low, high, nominal) if low <= v <= high})
        self.rows = {}

    def snap(self, value):
        if not self.step:
            return value
        return min(self.high, max(self.low, self.low + round((value - self.low) / self.step) * self.step))

    def most_runs(self):
        return len(self.points) + 2 * self.left

    def ask(self):
        """The settings to run in this round."""
        fresh = [v for v in self.points if v not in self.rows]
        if fresh or self.left <= 0:
            return fresh
        tried = sorted(self.rows)
        halves = {self.snap((a + b) / 2) for a, b in zip(tried, tried[1:]) if self.rows[a] != self.rows[b]}
        return sorted(v for v in halves if v not in self.rows)

    def tell(self, results):
        """Take {setting: met} for the settings of one round."""
        if all(v in self.rows for v in self.points):
            self.left -= 1
        self.rows.update(results)

    def summary(self, value):
        passing = [v for v in sorted(self.rows) if self.rows[v]]
        return {"value": value, "passes": [passing[0], passing[-1]] if passing else None, "tried": [[v, self.rows[v]] for v in sorted(self.rows)]}


def coverage(path, adjustment, entry, low, high):
    """Whether an adjustment's range covers an uncertain input: its passing window at each end, and what they share."""
    a, b = low["passes"], high["passes"]
    shared = [max(a[0], b[0]), min(a[1], b[1])] if a and b else None
    both = bool(shared and shared[0] <= shared[1])
    return {"input": path, "adjustment": adjustment, "kind": entry["kind"], "adjusts": entry["input"], "range": entry["range"],
            "atLow": low, "atHigh": high, "someSettingPassesEach": bool(a and b), "oneSettingPassesBoth": both,
            "setting": middle(shared, entry) if both else None}


def middle(shared, entry):
    """A setting in the middle of a window; for a stepped adjustment, the step nearest the middle that is inside it."""
    centre, step = (shared[0] + shared[1]) / 2, entry.get("step")
    if not step:
        return centre
    low = entry["range"][0]
    near = sorted({low + round((centre - low) / step + shift) * step for shift in (-1, 0, 1)}, key=lambda v: abs(v - centre))
    return next((v for v in near if shared[0] <= v <= shared[1]), shared[0])
