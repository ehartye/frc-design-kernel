"""Words with their numbers filled in: "At most {limits.reach.far} out" becomes "At most 1 ft 2 in out".

    fill(worker, entry, owner, before, text)    the words; owner is the object that the text is in, before the path to it
    path_of(entry, before)                      the path to the words

A limit prints without its words, so that "at most {limits.reach.far}" reads well.
"""
from ..errors import DesignError
from .words import IN_SAYS
from .worth import Value, Wrong, words_of


def fill(worker, entry, owner, before, text):
    worker.begin(path_of(entry, before))
    try:
        return IN_SAYS.sub(lambda found: words_of(_value(worker, entry, owner, before, found[1])), text)
    finally:
        worker.doing.pop()


def path_of(entry, before):
    """The path to the words, by which words that name themselves are seen."""
    return ".".join([entry.path, *before, "says"])


def _value(worker, entry, owner, before, path):
    """The Value that {path} stands for, or Values."""
    try:
        got = _found(worker, entry, owner, before, path)
    except Wrong:
        raise
    except DesignError as problem:
        raise DesignError("", f"names {{{path}}}, which {problem.problem}", problem.fix) from None
    if not isinstance(got, Value) and not (isinstance(got, list) and all(isinstance(one, Value) for one in got)):
        raise DesignError("", f"names {{{path}}}, which is a shape or an outline and does not print", "Name one of its sizes")
    return got


def _found(worker, entry, owner, before, path):
    """What {path} stands for: a field of its own object, of its own record, or any other path."""
    head, *steps = path.split(".")
    for data, start in ((owner, before), (entry.data, ())):
        if head in data:
            found = worker.book.within(data, path, entry, worker.choice)
            worker.check(entry, None, [*start, head, *steps])
            return worker.field(found.node, entry, [*start, head, *steps], found.end)
    return worker.get(path)
