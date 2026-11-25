"""When things are: windows in seconds, and how long after a period an award is still looked at.

    windows(worker)          {name: Window}, in seconds from the start of its period
    window(worker, entry)    one Window; a DesignError when it does not fit in its period
    judged(worker, award)    {period: seconds after it in which the award still counts for that period}
"""
from dataclasses import dataclass

from ..errors import DesignError, unknown
from .values import TIMER
from .worth import one_number


@dataclass(frozen=True)
class Window:
    """A span of time with a name, in seconds from the start of its period."""
    name: str
    period: str
    start: float
    end: float


def windows(worker):
    return {name: window(worker, entry) for name, entry in worker.book.of_kind("window").items()}


def seconds(worker, path):
    return one_number(worker.get(path))


def window(worker, entry):
    """A window of one period: the first of it, the last of it, or between two times of the timer, which counts down."""
    name, period, data = entry.id, entry.data["in"], entry.data
    if "lasts" not in worker.book.ids[period].data and "first" not in data:
        raise DesignError(entry.where, f"is counted from the end of {period}, which has no lasts", f"Give {period} its lasts")
    long = seconds(worker, f"{period}.lasts") if "lasts" in worker.book.ids[period].data else None
    if "first" in data:
        start, end = 0, seconds(worker, f"{name}.first")
    elif "last" in data:
        start, end = long - seconds(worker, f"{name}.last"), long
    else:
        start, end = (long - int(found[1]) * 60 - int(found[2]) for found in map(TIMER.fullmatch, data["timer"]))
    if start < 0 or long is not None and end > long:
        raise DesignError(entry.where, f"does not fit in {period}, which lasts {long:g} s", "Check its times, and the times of its period")
    return Window(name, period, start, end)


def judged(worker, award):
    """{period: seconds after it in which an award still counts for that period}; nothing for a period after which it does not."""
    known, found = worker.book.of_kind("award"), {}
    if award not in known:
        raise unknown("", "award", award, known)
    for entry in worker.book.of_kind("judged").values():
        for name in entry.data if award in entry.data["awards"] else ():
            period = name.removeprefix("after_")
            if period == name:
                continue
            if period in found:
                raise DesignError(entry.where, f"says how long {award} is looked at after {period}, and so does another", "Write it once")
            found[period] = seconds(worker, f"{entry.path}.{name}")
    return found
