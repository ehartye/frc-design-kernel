"""Safe arithmetic for values written as "=...". Only numbers, names, + - * / **, brackets and a short list of functions."""
import ast
import difflib
import math
import operator

from ..errors import DesignError

FUNCTIONS = {"sin": math.sin, "cos": math.cos, "tan": math.tan, "asin": math.asin, "acos": math.acos, "atan": math.atan,
             "atan2": math.atan2, "sqrt": math.sqrt, "abs": abs, "min": min, "max": max, "radians": math.radians,
             "degrees": math.degrees}
CONSTANTS = {"pi": math.pi}
POWER_BITS = 1100      # an exact whole-number power longer than this many bits is far past any float, so it is refused


def power(base, exponent):
    """base ** exponent, refusing at once a whole-number power too large for any ordinary number (9 ** 9 ** 9)."""
    if isinstance(base, int) and isinstance(exponent, int) and abs(base) > 1 and exponent > 0 \
            and exponent * math.log2(abs(base)) > POWER_BITS:
        raise OverflowError("the power is too large")
    return operator.pow(base, exponent)


BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv, ast.Pow: power}
UNARY = {ast.USub: operator.neg, ast.UAdd: operator.pos}
ALLOWED = "Use numbers, parameter names, + - * / **, brackets and: " + ", ".join([*FUNCTIONS, *CONSTANTS])


def is_expression(value):
    return isinstance(value, str) and value.startswith("=")


def evaluate(text, names):
    """The number that the expression text (starting with "=") stands for, given {name: number}."""
    try:
        tree = ast.parse(text[1:].strip(), mode="eval")
    except SyntaxError:
        raise DesignError("", f'the expression "{text}" is not valid arithmetic', ALLOWED) from None
    try:
        value = _walk(tree.body, names, text)
    except DesignError:
        raise                   # already says what is wrong with the expression; it is a ValueError too
    except (ZeroDivisionError, ValueError, OverflowError, TypeError) as problem:
        raise DesignError("", f'the expression "{text}" cannot be worked out ({problem})', "Check the numbers it uses") from None
    if isinstance(value, complex) or not math.isfinite(value):
        raise DesignError("", f'the expression "{text}" does not give an ordinary number', "Check the numbers it uses")
    return value


def _walk(node, names, text):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return node.value
    if isinstance(node, ast.Name):
        if node.id in names:
            return names[node.id]
        if node.id in CONSTANTS:
            return CONSTANTS[node.id]
        close = difflib.get_close_matches(node.id, names, 1)
        hint = f'Did you mean "{close[0]}"? ' if close else ""
        raise DesignError("", f'the expression "{text}" uses "{node.id}", which is not a parameter', f"{hint}Add it to parameters, above where it is used")
    if isinstance(node, ast.BinOp) and type(node.op) in BINARY:
        return BINARY[type(node.op)](_walk(node.left, names, text), _walk(node.right, names, text))
    if isinstance(node, ast.UnaryOp) and type(node.op) in UNARY:
        return UNARY[type(node.op)](_walk(node.operand, names, text))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
        return FUNCTIONS[node.func.id](*[_walk(a, names, text) for a in node.args])
    raise DesignError("", f'the expression "{text}" uses something that is not allowed', ALLOWED)
