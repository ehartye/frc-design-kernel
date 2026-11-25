"""What each device of `parts` may run.

    runs(worker, device)    {"parts.motors.mule": how many} of every load that one such device may run

A device has a `kind`; a load has `on`, how many of it one device of each kind may run. A kind that is left out of `on` may
not run the load. With `only_for` the device runs those loads and no others.
"""
from ..errors import DesignError, unknown


def loads(book):
    return [entry for entry in book.entries if entry.kind == "part" and isinstance(entry.data.get("on"), dict)]


def device(book, name):
    """The part that a name stands for: its ID, its group and ID, or its path."""
    known = {entry.path: entry for entry in book.entries if entry.kind == "part"}
    found = [path for path in known if name in (path, path.removeprefix("parts."), path.rpartition(".")[2])]
    if not found:
        raise unknown("", "part", name, [path.removeprefix("parts.") for path in known] + [entry.id for entry in known.values()])
    if len(found) > 1:
        raise DesignError("", f'"{name}" is in more than one group', f"Name one: {', '.join(path.removeprefix('parts.') for path in found)}")
    return known[found[0]]


def runs(worker, name):
    """{path of a load: how many of it, a Value} for every load that one such device may run. No limit has the kind `any`."""
    entry = device(worker.book, name)
    if "kind" not in entry.data:
        raise DesignError(entry.where, "runs nothing: it has no kind", "Ask for a device that runs others")
    kind, only = entry.data["kind"], entry.data.get("only_for")
    found = {}
    for load in loads(worker.book):
        if only is not None and load.id not in only:
            continue
        if kind in load.data["on"]:
            found[load.path] = worker.get(f"{load.path}.on.{kind}")
        elif only is not None:
            raise DesignError(entry.where, f"is only for {load.id}, whose on does not say how many of it one {kind} may run", f"Write it in the on of {load.id}")
    return found
