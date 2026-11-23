"""Turn a schema-checked source into a plain design: "each" rows written out and every "=..." worked out."""
import copy

from ..errors import DesignError
from .expressions import evaluate, is_expression
from .schema import step

REPEATABLE = ("solids", "fixtures", "mounts", "contacts")
PLAIN = ("groups", "poses", "motions")


def text_of(value):
    return str(int(value)) if isinstance(value, float) and value.is_integer() else str(value)


def fill(value, row):
    """Replace {key} in every text inside value with the row's value for that key."""
    if isinstance(value, str):
        for key, item in row.items():
            value = value.replace("{" + key + "}", text_of(item))
        return value
    if isinstance(value, list):
        return [fill(v, row) for v in value]
    if isinstance(value, dict):
        return {k: fill(v, row) for k, v in value.items()}
    return value


def work_out(value, names, where):
    """Replace every "=..." text inside value with its number."""
    if is_expression(value):
        try:
            return evaluate(value, names)
        except DesignError as problem:
            raise problem.under(where) from None
    if isinstance(value, list):
        return [work_out(v, names, step(where, i)) for i, v in enumerate(value)]
    if isinstance(value, dict):
        return {k: work_out(v, names, step(where, k)) for k, v in value.items()}
    return value


def parameters(raw):
    """Parameters worked out top to bottom; each may use the ones above it."""
    names = {}
    for key, value in raw.get("parameters", {}).items():
        names[key] = work_out(value, names, f"parameters.{key}")
    return names


def rows(entries, section, names):
    """Each entry written out once per "each" row, with its numbers worked out."""
    out = []
    for i, entry in enumerate(entries):
        where = step(section, i, entry)
        if "each" not in entry:
            out.append(work_out(entry, names, where))
            continue
        body = {k: v for k, v in entry.items() if k != "each"}
        for n, row in enumerate(entry["each"]):
            clash = sorted(set(row) & set(names))
            if clash:
                raise DesignError(where, f'the each key "{clash[0]}" is also a parameter', "Rename one of them")
            numbers = {k: v for k, v in row.items() if not isinstance(v, str)}
            out.append(work_out(fill(copy.deepcopy(body), row), {**names, **numbers}, f"{where} (each row {n + 1})"))
    return out


def expand(raw):
    """The plain design: no "each", no expressions. Every list and table the build reads is present."""
    names = parameters(raw)
    plain = {k: raw[k] for k in ("schema", "name", "units")}
    plain["frame"] = raw.get("frame", "")
    plain["parameters"] = names
    plain["custom"] = copy.deepcopy(raw.get("custom", {}))
    for section in PLAIN:
        plain[section] = work_out(copy.deepcopy(raw.get(section, {})), names, section)
    for section in REPEATABLE:
        plain[section] = rows(raw.get(section, []), section, names)
    return plain
