"""Conditions and events as data: what counts as captured, seated or lost, and when a controller changes its command.

A condition is one of:
    {"signal": name, "above": n}   {"signal": name, "below": n}
    {"after": event, "delayS": s}      the event happened at least s seconds ago (s defaults to 0)
    {"notYet": event}                  the event has not happened
    {"restFor": s}                     the piece has been at rest for s seconds without a break
    {"all": [conditions]}   {"any": [conditions]}   {"not": condition}
"""


def holds(condition, signals, happened, rest_since, t):
    """Whether a condition is true now. happened is {event: time}. rest_since is when the piece last came to rest, or None."""
    if "signal" in condition:
        value = signals[condition["signal"]]
        return value > condition["above"] if "above" in condition else value < condition["below"]
    if "after" in condition:
        when = happened.get(condition["after"])
        return when is not None and t - when >= condition.get("delayS", 0.0)
    if "notYet" in condition:
        return condition["notYet"] not in happened
    if "restFor" in condition:
        return rest_since is not None and t - rest_since >= condition["restFor"]
    if "all" in condition:
        return all(holds(c, signals, happened, rest_since, t) for c in condition["all"])
    if "any" in condition:
        return any(holds(c, signals, happened, rest_since, t) for c in condition["any"])
    return not holds(condition["not"], signals, happened, rest_since, t)


def names_in(condition):
    """(signals, events) a condition refers to, for checking a trial before it runs."""
    signals, events = set(), set()
    if "signal" in condition:
        signals.add(condition["signal"])
    for key in ("after", "notYet"):
        if key in condition:
            events.add(condition[key])
    inner = [*condition.get("all", []), *condition.get("any", []), *([condition["not"]] if "not" in condition else [])]
    for part in inner:
        more = names_in(part)
        signals |= more[0]
        events |= more[1]
    return signals, events


def started(trigger, happened, t):
    """The time a triggered thing began, or None if it has not: {"startS": s} or {"after": event, "delayS": s}."""
    if "after" in trigger:
        when = happened.get(trigger["after"])
        begin = None if when is None else when + trigger.get("delayS", 0.0)
    else:
        begin = trigger.get("startS", 0.0)
    return begin if begin is not None and t >= begin else None
