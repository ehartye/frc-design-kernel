"""The arithmetic of one formula, such as "= size.length / 2 - pen.side * cos(pen.lean)".

    work(text, named)    (kind, number in base units); named(path) gives the same for each path that the formula names

First the kinds are checked: adding needs the same kind, and a bare number only multiplies or divides. Then the library's
own evaluator works the number out. An angle goes into it in radians and comes out in degrees, so an author converts
nothing. What is wrong is told with the author's own text.
"""
import ast
import math

from ..errors import DesignError
from ..source.expressions import evaluate
from .read import word_list
from .values import in_words
from .words import PATH

GIVES = {"sin": "number", "cos": "number", "tan": "number", "sqrt": "number", "atan2": "angle"}     # the others give what they are given
TAKES = {"sin": "angle", "cos": "angle", "tan": "angle", "sqrt": "number"}                          # the others take any one kind
HOW_MANY = {"sin": 1, "cos": 1, "tan": 1, "sqrt": 1, "abs": 1, "atan2": 2}                          # the others take two or more


def work(text, named):
    """(kind, number in base units) of a formula. named(path) gives the same for a path, or raises a DesignError."""
    own = {}        # {path: a plain name that can not be one of the evaluator's own}
    plain = PATH.sub(lambda found: own.setdefault(found[0], f"value_{len(own)}_"), text[1:]).strip()
    held = {name: named(path) for path, name in own.items()}
    if plain in held:
        return held[plain]      # a path alone is exact: an angle does not go through radians
    try:
        kind = _kind(ast.parse(plain, mode="eval").body, {name: kind for name, (kind, _) in held.items()})
        number = evaluate("=" + plain, {name: math.radians(n) if kind == "angle" else n for name, (kind, n) in held.items()})
    except DesignError as problem:
        raise _wrong(text, problem.problem.replace(f'the expression "={plain}" ', ""), problem.fix) from None
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        raise _wrong(text, "is not valid arithmetic") from None
    return kind, math.degrees(number) if kind == "angle" else number


def _wrong(text, why, fix=None):
    return DesignError("", f'the formula "{text}" {why}', fix or _allowed())


def _allowed():
    return f"Use paths, numbers, + - * /, brackets and: {', '.join(word_list('function'))}"


def _not(why, fix=None):
    """What is wrong with a part of a formula; work() tells which formula."""
    return DesignError("", why, fix or _allowed())


def _kind(node, kinds):
    """The kind of what a part of a formula gives."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return "number"
    if isinstance(node, ast.Name) and node.id in kinds:
        return kinds[node.id]
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _kind(node.operand, kinds)
    if isinstance(node, ast.BinOp):
        return _both(node.op, _kind(node.left, kinds), _kind(node.right, kinds))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
        return _function(node.func.id, [_kind(one, kinds) for one in node.args])
    raise _not("uses something that is not arithmetic")


def _both(op, left, right):
    if isinstance(op, (ast.Add, ast.Sub)) and left == right:
        return left
    if isinstance(op, (ast.Add, ast.Sub)):
        raise _not(f"{'adds' if isinstance(op, ast.Add) else 'subtracts'} {in_words(right)} {'to' if isinstance(op, ast.Add) else 'from'} {in_words(left)}",
                     "Both must be of the same kind; a bare number only multiplies or divides")
    if isinstance(op, ast.Mult) and "number" in (left, right):
        return right if left == "number" else left
    if isinstance(op, ast.Mult):
        raise _not(f"multiplies {in_words(left)} by {in_words(right)}", "One of the two must be a bare number")
    if isinstance(op, ast.Div) and right in (left, "number"):
        return "number" if left == right else left
    if isinstance(op, ast.Div):
        raise _not(f"divides {in_words(left)} by {in_words(right)}", "Divide by a bare number, or by the same kind")
    raise _not("uses something that is not arithmetic")


def _function(name, given):
    if name not in word_list("function"):
        raise _not(f'uses "{name}", which is not a function that may be used')
    many = HOW_MANY.get(name, max(2, len(given)))
    if len(given) != many:
        raise _not(f"gives {name} the wrong number of values: {len(given)}", f"Give it {HOW_MANY.get(name, 'two or more')}")
    if name in TAKES and given != [TAKES[name]]:
        raise _not(f"takes {name} of {in_words(given[0])}", f"Give it {in_words(TAKES[name])}" + (", such as one printed in deg" if TAKES[name] == "angle" else ""))
    if len(set(given)) > 1:
        raise _not(f"takes {name} of {' and '.join(in_words(kind) for kind in dict.fromkeys(given))}", "Give it numbers of one kind")
    return GIVES.get(name, given[0])
