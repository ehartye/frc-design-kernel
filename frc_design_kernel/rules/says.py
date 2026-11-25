"""Words with their numbers filled in: "At most {limits.reach.far} out" becomes "At most 1 ft 2 in out".

    fill(worker, field)           the words of a Field, as a Value: whether one of its numbers is, or uses, a position goes with it
    named(worker, field, path)    the Value that {path} stands for in them, or Values

A limit prints without its words, so that "at most {limits.reach.far}" reads well.
"""
from ..errors import DesignError
from .words import IN_SAYS
from .worth import Value, Wrong, moves, words_of


def fill(worker, field):
    worker.begin(path_of(field))
    try:
        found = {path: named(worker, field, path) for path in IN_SAYS.findall(field.node)}
    finally:
        worker.season.doing.pop()
    text = IN_SAYS.sub(lambda path: words_of(found[path[1]]), field.node)
    return Value("text", text, printed=text, moves=moves(list(found.values())))


def path_of(field):
    """The path to the words as they are written, by which words that name themselves are seen."""
    return field.where.partition(" ")[2]


def named(worker, field, path):
    try:
        got = _found(worker, field, path)
    except Wrong:
        raise
    except DesignError as problem:
        raise DesignError("", f"names {{{path}}}, which {problem.problem}", problem.fix) from None
    if not isinstance(got, Value) and not (isinstance(got, list) and all(isinstance(one, Value) for one in got)):
        raise DesignError("", f"names {{{path}}}, which is a shape or an outline and does not print", "Name one of its sizes")
    return got


def _found(worker, field, path):
    """What {path} stands for: a field of its own object, of its own record, or any other path."""
    entry, steps = field.entry, path.split(".")
    before = path_of(field).removeprefix(f"{entry.path}.").split(".")[:-1]
    for data, start in ((field.owner, before), (entry.data, [])):
        if steps[0] in data:
            found = worker.book.within(data, path, entry, worker.choice)
            worker.check(entry, None, [*start, *steps])
            return worker.season.marked(worker.field(found.node, entry, [*start, *steps], found.end, about=found.about), entry, None, [*start, *steps])
    return worker.get(path)
