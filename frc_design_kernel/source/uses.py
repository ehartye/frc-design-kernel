"""Which parameters something in the source depends on, directly or through other parameters."""
import ast

from .expressions import is_expression


def names_in(value):
    """Every name used by the "=..." expressions inside value."""
    found = set()
    if is_expression(value):
        try:
            found = {node.id for node in ast.walk(ast.parse(value[1:].strip(), mode="eval")) if isinstance(node, ast.Name)}
        except SyntaxError:
            found = set()
    elif isinstance(value, dict):
        for item in value.values():
            found |= names_in(item)
    elif isinstance(value, list):
        for item in value:
            found |= names_in(item)
    return found


def parameters_used(raw, value):
    """The parameters the expressions inside value depend on, followed through parameters that use other parameters."""
    table = raw.get("parameters", {})
    used, waiting = set(), [name for name in names_in(value) if name in table]
    while waiting:
        name = waiting.pop()
        if name not in used:
            used.add(name)
            waiting += [other for other in names_in(table[name]) if other in table]
    return sorted(used)
