"""fields.json and RULES.md name the same things, the example uses them all, and the package stands alone."""
import json
import re
import subprocess
import sys
import unittest

from .rules_cases import FILES, ROOT, _text, example
from .test_size_rules import PACKAGE, import_graph


def sections(rules):
    """{number: the code in that section of RULES.md}: everything between backticks, and every example."""
    parts = re.split(r"^## (\d+)\. .*$", rules, flags=re.M)
    return {int(number): "\n".join(block or line for block, line in re.findall(r"```json\n(.*?)```|`([^`]+)`", text, flags=re.S))
            for number, text in zip(parts[1::2], parts[2::2])}


def has_word(code, word):
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", code) is not None


def not_in_rules(rules, data):
    """Every name of fields.json that its section of RULES.md does not give."""
    code = sections(rules)
    asked = [(kind["section"], name) for kind in (*data["kinds"].values(), *data["files"].values()) for name in kind.get("fields", {})]
    asked += [(1, f"{name}.json") for name in data["files"]] + [(1, root) for root in data["roots"]] + [(2, name) for name in data["every"]]
    asked += [(235, name) for name in data["value"]] + [(2, name) for form in ("differs", "was") for name in data[form]] + [(3, unit) for units in data["units"].values() for unit in units]
    asked += [(3, name) for name in (*data["kept"], *data["limit_words"], *data["functions"])]
    asked += [(7, name) for forms in (data["shapes"], data["outlines"]) for form, sizes in forms.items() for name in (form, *(sizes if isinstance(sizes, dict) else ()))]
    asked += [(12, name) for name in (*data["acts_need"], *data["cost_main"])]
    asked += [(13, name) for limit, fields in data["limits"].items() for name in (limit, *(fields if isinstance(fields, dict) else ()))]
    asked += [(0, name) for name in data["placed"]] + [(0, word) for words in data["words"].values() for word in words]
    code[0], code[235] = "\n".join(code.values()), "\n".join(code[n] for n in (2, 3, 5))     # anywhere; wherever values are explained
    return sorted({name for section, name in asked if not has_word(code[section], name)})


def not_in_fields(rules, data):
    """Every name that RULES.md gives in its text or tables, or uses in an example, that fields.json does not know."""
    known = set(_strings(data))
    examples = {"paint_width", "near", "far", "bale", "welded", "bolted", "deep", "wide", "false"}     # what RULES.md invents to show a form, and JSON's own word
    found = set()
    for code in re.findall(r"`([^`]+)`", re.sub(r"```.*?```", "", rules, flags=re.S)):
        if re.fullmatch(r"[a-z][a-z_0-9]*", code):
            found.add(code)
        elif re.fullmatch(r"\{[a-z_, ]+\}", code):
            found.update(re.findall(r"[a-z_]+", code))
        found.update(re.findall(r'"([a-z_]+)":', code))
    return sorted(found - known - examples)


def _strings(node):
    if isinstance(node, dict):
        return [s for key, value in node.items() for s in (key, *_strings(value))]
    return [s for value in node for s in _strings(value)] if isinstance(node, list) else [node] if isinstance(node, str) else []


class TheOneList(unittest.TestCase):
    """fields.json and RULES.md name the same things, and the example uses them all."""

    def setUp(self):
        from frc_design_kernel.rules import read
        self.rules = (ROOT / "RULES.md").read_text(encoding="utf-8")
        self.data = json.loads(json.dumps(read.names()))

    def test_every_name_is_in_rules_md(self):
        """Catches a field, unit or word that the reader accepts and no author is told of."""
        self.assertEqual(not_in_rules(self.rules, self.data), [])

    def test_a_name_that_rules_md_does_not_give_is_caught(self):
        """Control: a field, a unit, a limit and a word that are only in fields.json are each found."""
        self.data["kinds"]["opening"]["fields"]["curve"] = "angle"
        self.data["units"]["length"]["yd"] = 914.4
        self.data["limits"]["drive"]["wheels"] = "number"
        self.data["words"]["edge"].append("paint inside")
        self.assertEqual(not_in_rules(self.rules, self.data), ["curve", "paint inside", "wheels", "yd"])

    def test_a_name_of_another_section_is_not_enough(self):
        """Control: a name has to be in its own section, so that "tip" of a post does not stand for a tip of a bar."""
        self.data["kinds"]["hang"]["fields"]["tip"] = "length"
        self.assertEqual(not_in_rules(self.rules, self.data), ["tip"])

    def test_every_name_of_rules_md_is_known(self):
        """Catches a field or a word that RULES.md gives an author and the reader would refuse or not check."""
        self.assertEqual(not_in_fields(self.rules, self.data), [])

    def test_a_name_that_fields_json_does_not_know_is_caught(self):
        """Control: a name taken out of fields.json, and one put in RULES.md, are each found."""
        del self.data["kinds"]["opening"]["fields"]["lip"]
        self.assertEqual(not_in_fields(self.rules + "\n`curve` and `{inside, bulge}` and `\"paint\": 1`\n", self.data), ["bulge", "curve", "lip", "paint"])

    def test_the_examples_in_rules_md_use_known_names(self):
        """Catches an example in RULES.md with a field that the reader takes for an extra one."""
        self.assertEqual(self.extras(self.rules), [])

    def test_an_extra_name_in_an_example_is_caught(self):
        """Control: a field that RULES.md does not give, in one of its examples, is found."""
        self.assertEqual(self.extras(self.rules.replace('"last": "25 s"', '"last": "25 s", "past": "3 s"')), ["clock.json endgame.past"])

    def extras(self, rules):
        from frc_design_kernel.rules import fields, read
        blocks = {int(n): json.loads(text) for n, text in re.findall(r"^## (\d+)\. (?:(?!^## ).)*?```json\n(.*?)```", rules, flags=re.M | re.S)}
        files = {file: blocks[about["section"]] for file, about in self.data["files"].items() if about["section"] in blocks}
        self.assertEqual(len(files), 8)
        files["robot"] = {"parts": files["robot"]}
        book, faults = read.gather("", files)
        self.assertEqual([str(f) for f in faults], [])
        return [f.where for f in fields.walk(book, []) if f.holds == "extra"]

    def test_the_example_uses_every_name(self):
        """Catches a field or a word that no test ever reads, because the example does not use it."""
        self.assertEqual(self.unused(self.data), [])

    def test_a_name_that_the_example_does_not_use_is_caught(self):
        """Control: a field, a word and a shape that the example does not have are each found."""
        self.data["kinds"]["opening"]["fields"]["curve"] = "angle"
        self.data["words"]["act"].append("sing")
        self.data["shapes"]["cone"] = {"apex": "length"}
        self.assertEqual(self.unused(self.data), ["apex", "cone", "opening.curve", "sing"])

    def unused(self, data):
        """Names of fields.json that the example does not use: a field by its kind of record, a word or a unit anywhere."""
        from frc_design_kernel.rules import fields, read
        book, _ = read.gather("", example())
        text = "\n".join(_text(name) for name in FILES)
        used = {}
        for field in fields.walk(book, []):
            used.setdefault(field.name, []).append(set(field.owner))
        missing = [f"{kind}.{name}" for kind, about in data["kinds"].items() for name in about["fields"] if not any(self.fits(about, names) for names in used.get(name, ()))]
        words = [w for name, words in data["words"].items() if name != "axis" for w in words] + [*data["every"], *data["placed"], *data["value"], *data["kept"], *data["limit_words"], *data["functions"]]
        words += [unit for units in data["units"].values() for unit in units] + [n for forms in (data["shapes"], data["outlines"]) for form, sizes in forms.items() for n in (form, *(sizes if isinstance(sizes, dict) else ()))]
        words += [n for limit, about in data["limits"].items() for n in (limit, *(about if isinstance(about, dict) else ()))]
        return sorted(missing + [w for w in words if not has_word(text, w)])

    def fits(self, about, owner):
        """Whether an object that has a field may be of this kind: it has no field of no kind at all."""
        return bool(owner & set(about["fields"]))


class Alone(unittest.TestCase):
    """What the package may import."""

    def test_rules_imports_only_source_and_errors(self):
        """Catches the rules reader needing the CAD kernel, or anything above it, only to read nine text files."""
        self.assertEqual(outside(import_graph(PACKAGE)), [])

    def test_an_import_from_above_is_caught(self):
        """Control: a rules module that imports the kernel or the builder is found."""
        graph = {"frc_design_kernel.rules.read": {"frc_design_kernel.errors", "frc_design_kernel.rules.quantity", "frc_design_kernel.source.expressions", "frc_design_kernel.kernel.shapes"},
                 "frc_design_kernel.builder.shape": {"frc_design_kernel.kernel.shapes"}}
        self.assertEqual(outside(graph), ["frc_design_kernel.rules.read imports frc_design_kernel.kernel.shapes"])

    def test_nothing_is_imported_from_outside_the_standard_library(self):
        """Catches the rules reader needing a package that is not there, such as the CAD kernel, to be imported."""
        code = "import sys; from frc_design_kernel.rules import words; print(sorted(m for m in sys.modules if m.split('.')[0] in ('OCP', 'mujoco', 'numpy')))"
        self.assertEqual(subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=ROOT).stdout.strip(), "[]")


def outside(graph):
    """Each import by a rules module of something in the package that is not rules, source or errors."""
    allowed = ("frc_design_kernel.rules", "frc_design_kernel.source", "frc_design_kernel.errors")
    return [f"{name} imports {other}" for name in sorted(graph) if name.startswith("frc_design_kernel.rules")
            for other in sorted(graph[name]) if other != "frc_design_kernel" and not other.startswith(allowed)]


if __name__ == "__main__":
    unittest.main()
