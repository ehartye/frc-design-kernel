"""A small JSON Schema checker with plain messages.

It understands only the keywords listed in KEYWORDS, which are the ones design.schema.json uses. A test fails if
the schema file starts using a keyword that is not listed here. The first problem found is raised as a DesignError
that names the entry and says how to fix it.
"""
import difflib
import functools
import json
import re
from pathlib import Path

from ..errors import DesignError

SCHEMA_FILE = Path(__file__).with_name("design.schema.json")
CHECKED = {"$ref", "type", "const", "enum", "properties", "required", "additionalProperties", "propertyNames", "minProperties",
           "items", "minItems", "maxItems", "minLength", "pattern", "oneOf"}
NOTES = {"$schema", "$id", "$defs", "title", "description", "fix"}
KEYWORDS = CHECKED | NOTES
TYPES = {"object": dict, "array": list, "string": str, "number": (int, float), "boolean": bool, "null": type(None)}
WORDS = {"object": "an object in { }", "array": "a list in [ ]", "string": "text in quotes", "number": "a number", "boolean": "true or false", "null": "null"}


@functools.cache
def load_schema(name="design"):
    """The schema named name, read once. Callers must not change it."""
    return json.loads(SCHEMA_FILE.with_name(f"{name}.schema.json").read_text(encoding="utf-8"))


def describe(value):
    if isinstance(value, bool):
        return "true or false"
    return next((WORDS[name] for name, kind in TYPES.items() if isinstance(value, kind)), "nothing (null)")


def is_type(value, name):
    if isinstance(value, bool):
        return name == "boolean"
    return isinstance(value, TYPES[name])


def step(where, key, value=None):
    """The place of a child: a field after a dot, a list item in brackets, with the entry's name when it has one."""
    if isinstance(key, int):
        place = f"{where}[{key}]"
    else:
        place = f"{where}.{key}" if where and not where.endswith(('"', ")")) else f"{where} {key}".strip()
    name = value.get("name") if isinstance(value, dict) else None
    return f'{place} "{name}"' if isinstance(name, str) and isinstance(key, int) else place


def check(value, schema, root=None, where=""):
    """Raise a DesignError for the first place value does not fit schema."""
    root = schema if root is None else root
    fix = schema.get("fix", "")
    if "$ref" in schema:
        file, _, pointer = schema["$ref"].partition("#")
        root = load_schema(file.removesuffix(".schema.json")) if file else root    # a reference into another schema file
        target = root
        for part in filter(None, pointer.split("/")):
            target = target[part]
        return check(value, target, root, where)
    if "oneOf" in schema:
        return _one_of(value, schema, root, where)
    if "const" in schema and value != schema["const"]:
        raise DesignError(where, f"must be {json.dumps(schema['const'])}", fix)
    if "enum" in schema and value not in schema["enum"]:
        raise DesignError(where, f"must be one of {', '.join(json.dumps(v) for v in schema['enum'])}", fix)
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(is_type(value, n) for n in names):
            raise DesignError(where, f"must be {' or '.join(WORDS[n] for n in names)}, not {describe(value)}", fix)
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise DesignError(where, f"is too short (at least {schema['minLength']} characters)", fix or "Write it out")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise DesignError(where, f'"{value}" is not in the allowed form', fix)
    if isinstance(value, list):
        _list(value, schema, root, where, fix)
    if isinstance(value, dict):
        _object(value, schema, root, where, fix)


def _list(value, schema, root, where, fix):
    low, high = schema.get("minItems", 0), schema.get("maxItems")
    if len(value) < low or (high is not None and len(value) > high):
        need = f"exactly {low}" if low == high else (f"at least {low}" if high is None else f"{low} to {high}")
        raise DesignError(where, f"must have {need} items, not {len(value)}", fix)
    if "items" in schema:
        for i, item in enumerate(value):
            check(item, schema["items"], root, step(where, i, item))


def _object(value, schema, root, where, fix):
    known = schema.get("properties", {})
    for key in schema.get("required", []):
        if key not in value:
            raise DesignError(where, f'is missing "{key}"', f'Add "{key}"')
    if len(value) < schema.get("minProperties", 0):
        raise DesignError(where, "must not be empty", fix or "Add at least one entry")
    extra = schema.get("additionalProperties", True)
    for key, item in value.items():
        if "propertyNames" in schema:
            check(key, schema["propertyNames"], root, step(where, key))
        if key in known:
            check(item, known[key], root, step(where, key))
        elif extra is False:
            close = difflib.get_close_matches(key, known, 1)
            hint = f'Did you mean "{close[0]}"? ' if close else ""
            raise DesignError(where, f'has an unknown field "{key}"', f"{hint}Allowed fields: {', '.join(k for k in known if k != '$schema')}")
        elif isinstance(extra, dict):
            check(item, extra, root, step(where, key))


def _one_of(value, schema, root, where):
    """A oneOf whose branches each fix "kind" picks its branch by kind; any other oneOf must fit exactly one branch."""
    branches = schema["oneOf"]
    kinds = [b.get("properties", {}).get("kind", {}).get("const") for b in branches]
    if all(kinds):
        if not isinstance(value, dict):
            raise DesignError(where, f'must be an object in {{ }} with a "kind", not {describe(value)}', f"Use one of the kinds: {', '.join(kinds)}")
        if value.get("kind") not in kinds:
            close = difflib.get_close_matches(str(value.get("kind")), kinds, 1)
            hint = f'Did you mean "{close[0]}"? ' if close else ""
            raise DesignError(where, f'has the unknown kind {json.dumps(value.get("kind"))}', f"{hint}Allowed kinds: {', '.join(kinds)}")
        return check(value, branches[kinds.index(value["kind"])], root, where)
    fits = 0
    for branch in branches:
        try:
            check(value, branch, root, where)
            fits += 1
        except DesignError:
            pass
    if fits != 1:
        raise DesignError(where, f"{json.dumps(value)} is not an allowed value", schema.get("fix", ""))
