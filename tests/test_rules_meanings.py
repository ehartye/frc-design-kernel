"""fields.json is the format: every property, word and form says what it means, its examples read, and the example uses it all."""
import copy
import json
import re
import unittest

from .rules_cases import FILES, _text, example

GROUPS = {"records": ("scoring", "fouls"), "people": ("game", "people"), "tags": ("field", "tags"), "limits": ("robot", "limits"), "parts": ("robot", "parts"), "variants": ("game", "variants")}
NAMED = {"piece count": "bale", "after period": "after_teleop"}     # forms that go with the name of their field


def described(data):
    """(key path, node) for everything in fields.json that must say what it means."""
    yield "the format", data
    for section in ("joined", "kept", "roots"):
        yield section, data[section]
    for section in ("units", "forms", "files", "kinds", "limits", "shapes", "outlines", "words"):
        for name, about in data[section].items():
            yield f"{section}.{name}", about
            for inner in ("fields", "words"):
                for one, node in about.get(inner, {}).items():
                    yield f"{section}.{name}.{one}", node


def no_meaning(data):
    """Whatever of fields.json does not say what it means."""
    return [key for key, node in described(data) if not says_something(node.get("means"), key == "the format")]


def says_something(means, a_list):
    """Whether a meaning is words; what the whole format is says it in a list of sentences."""
    sentences = means if a_list and isinstance(means, list) else [means]
    return bool(sentences) and isinstance(means, list) == a_list and all(isinstance(one, str) and one.strip() for one in sentences)


def no_form(data):
    """Every `holds` in fields.json that no form says how to write."""
    from frc_design_kernel.rules import meanings
    return sorted({node["holds"] for _, node in described(data) if "holds" in node and meanings.form_of(node["holds"], data) is None})


def does_not_read(data):
    """Every example of a form that the reader refuses, with its first fault."""
    found = []
    for name, form in data["forms"].items():
        for given in form["examples"]:
            faults = faults_of(name, form.get("as", name), given)
            found += [f"{name}: {faults[0]}"] if faults else []
        if not form["examples"]:
            found.append(f"{name}: no example")
    return found


def faults_of(name, holds, given):
    """What the reader finds wrong with one example, read as a field of the invented example."""
    from frc_design_kernel.errors import DesignError
    from frc_design_kernel.rules import fields, read, values, words
    data, faults = example(), []
    if name in GROUPS:
        file, group = GROUPS[name]
        data[file][group] = {**data[file][group], **given}
        book, faults = read.gather("", data)
        return [str(f) for f in faults + words.check(book)]
    book, _ = read.gather("", data)
    if name == "id":
        return [] if given in book.ids else [f"{given} is no ID"]
    if name == "path":
        try:
            book.look(given)
            return []
        except DesignError as problem:
            return [str(problem)]
    field = NAMED.get(name, "says" if name == "says" else "example")
    entry = read.Entry("conduct", "example", "example", {"kind": "relay"})
    spec = fields.Spec({field: fields.Property("", holds, "")})
    reader, checker, leaves = values.Reader(book, faults), words.Words(book, faults), []
    for one in fields.object_fields(entry, {field: given}, spec, "conduct.json example", faults):
        leaves += [*reader.read(one.entry, one.node, one.where, one.holds), *checker.field(one)]
    checker.formulas(leaves)
    return [str(f) for f in faults]


def unused(data):
    """Every property and word of fields.json that the invented example does not use."""
    from frc_design_kernel.rules import fields, read
    book, _ = read.gather("", example())
    used = list(fields.walk(book, []))
    keys = {field.key for field in used}
    text = "\n".join(_text(name) for name in FILES)
    missing = [f"{kind}.{name}" for kind, about in data["kinds"].items() if kind not in ("value", "differs", "was") for name in about["fields"] if f"{kind}.{name}" not in keys]
    missing += [f"{file}.{name}" for file, about in data["files"].items() for name in about.get("fields", {}) if name not in example()[file]]
    missing += [f"limits.{limit}.{name}" for limit, about in data["limits"].items() for name in about["fields"] if f"limits.{limit}.{name}" not in keys]
    missing += [f"limits.{limit}" for limit in data["limits"] if limit not in example()["robot"]["limits"]]
    missing += [f"{kind}.{name}" for kind in ("value", "differs", "was") for name in data["kinds"][kind]["fields"] if not has_word(text, f'"{name}":')]
    missing += [f"{section}.{form}" for section in ("shapes", "outlines") for form in data[section] if f'"{form}":' not in text]
    missing += [f"{form}.{size}" for section in ("shapes", "outlines") for form, about in data[section].items() for size in about.get("fields", {}) if f'"{size}":' not in text]
    for name, words in data["words"].items():
        holding = [field.node for field in used if field.holds in (f"word {name}", f"words {name}")]
        if holding:
            there = {word for node in holding for word in (node if isinstance(node, list) else [node])}
            missing += [f"{name}: {word}" for word in words["words"] if word not in there]
        elif name != "axis":
            missing += [f"{name}: {word}" for word in words["words"] if not has_word(text, word)]
    units = [unit for group in (*data["units"].values(), data["kept"]) for unit in group["units"]]
    return missing + [f"unit: {unit}" for unit in units if not re.search(rf"\d {re.escape(unit)}(?![\w/])", text)]


def has_word(text, word):
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


class Meanings(unittest.TestCase):
    """The one description of the format."""

    def setUp(self):
        from frc_design_kernel.rules import read
        self.data = copy.deepcopy(read.names())

    def test_everything_says_what_it_means(self):
        """Catches a property, word or form that an author would have to look up in a document that does not exist."""
        self.assertEqual(no_meaning(self.data), [])

    def test_a_missing_meaning_is_caught(self):
        """Control: a property, a word, a form, a limit and a size of a shape with no meaning are each found, and so is a blank one."""
        del self.data["kinds"]["opening"]["fields"]["lip"]["means"]
        self.data["words"]["edge"]["words"]["tape inside"]["means"] = " "
        self.data["forms"]["range"]["means"] = ""
        self.data["limits"]["reach"]["fields"]["far"]["means"] = 3
        del self.data["shapes"]["taper"]["fields"]["tall"]["means"]
        for nothing in ([], "Nine files.", ["Nine files.", ""]):
            self.data["means"] = nothing
            self.assertIn("the format", no_meaning(self.data))
        self.data["means"] = ["Nine files."]
        self.assertEqual(sorted(no_meaning(self.data)), ["forms.range", "kinds.opening.lip", "limits.reach.far", "shapes.taper.tall", "words.edge.tape inside"])

    def test_every_thing_held_has_a_form(self):
        """Catches a property that holds something which nothing says how to write."""
        self.assertEqual(no_form(self.data), [])

    def test_a_missing_form_is_caught(self):
        """Control: a property that holds a thing with no form is found."""
        self.data["kinds"]["opening"]["fields"]["curve"] = {"holds": "bend", "means": "How it bends."}
        del self.data["forms"]["cost"]
        self.assertEqual(no_form(self.data), ["bend", "cost"])

    def test_every_example_reads(self):
        """Catches an example of a form that an author copies and that the reader refuses."""
        self.assertEqual(does_not_read(self.data), [])

    def test_an_example_that_does_not_read_is_caught(self):
        """Control: a bad example of a value, a name, a group, a path and an ID are each found, and so is a form with none."""
        for form, bad in [("range", "0.9 to 0.7 lb"), ("award", "hung"), ("limits", {"rech": {}}), ("path", "bale.mas"), ("id", "bail"), ("formula", "= size.lenght / 2"), ("says", "At most {limits.reach.fra}."),
                          ("conditions", [["my bumpers", "in", "my yard"]]), ("spots", {"near": {}}), ("variants", {"field": "welded"}), ("piece count", "many"), ("cost", [{"foul": "miner"}])]:
            self.data["forms"][form]["examples"].append(bad)
        self.data["forms"]["timer"]["examples"] = []
        self.assertEqual(sorted(found.split(":")[0] for found in does_not_read(self.data)),
                         ["award", "conditions", "cost", "formula", "id", "limits", "path", "piece count", "range", "says", "spots", "timer", "variants"])

    def test_the_example_uses_every_property_and_word(self):
        """Catches a property or a word that no test ever reads, because the example does not use it."""
        self.assertEqual(unused(self.data), [])

    def test_a_property_that_the_example_does_not_use_is_caught(self):
        """Control: a property, a word, a limit's property, a shape, a size and a unit that the example does not have are each found."""
        new = {"holds": "length", "means": "x"}
        self.data["kinds"]["opening"]["fields"]["tip"] = new      # a post has a tip, and an opening has not
        self.data["words"]["act"]["words"]["sing"] = {"means": "x"}
        self.data["limits"]["drive"]["fields"]["wheels"] = new
        self.data["shapes"]["cone"] = {"means": "x", "fields": {"apex": new}}
        self.data["units"]["length"]["units"]["yd"] = 914.4
        self.assertEqual(sorted(unused(self.data)), ["act: sing", "cone.apex", "limits.drive.wheels", "opening.tip", "shapes.cone", "unit: yd"])


class Asked(unittest.TestCase):
    """meanings.py: what one property, word or form means, for whoever asks."""

    def keys(self, name):
        from frc_design_kernel.rules import meanings
        return [one.key for one in meanings.find(name)]

    def test_by_name(self):
        """Catches a name that finds nothing, or only one of the things that have it."""
        self.assertEqual(self.keys("bottom"), ["opening.bottom", "taper.bottom"])
        self.assertEqual(self.keys("tape inside"), ["edge: tape inside"])
        self.assertEqual(self.keys("opening"), ["place.opening", "opening"])
        self.assertIn("form: range", self.keys("range"))
        self.assertIn("limits.reach", self.keys("reach"))
        self.assertEqual(self.keys("no such thing"), [])

    def test_the_whole_format(self):
        """Catches a reader who asks for the whole format and does not get what it is first, in full."""
        from frc_design_kernel.rules import meanings, read
        whole = meanings.everything()[0]
        self.assertEqual((whole.key, whole.means), ("rules", " ".join(read.names()["means"])))

    def test_by_path(self):
        """Catches a name with its kind that finds the wrong one: the bottom of an opening, not of a taper."""
        from frc_design_kernel.rules import meanings, read
        for key in ["opening.bottom", "limits.reach.far", "game.variants", "judged.after_", "taper.tall"]:
            self.assertEqual(self.keys(key), [key])
        one = meanings.find("opening.bottom")[0]
        self.assertEqual((one.holds, one.means), ("length", read.names()["kinds"]["opening"]["fields"]["bottom"]["means"]))

    def test_how_it_is_written(self):
        """Catches a property with no form to copy from, and a word list without its words."""
        from frc_design_kernel.rules import meanings
        self.assertEqual(meanings.find("surface.size")[0].form, "2 lengths")
        self.assertIn("at most 40 A", meanings.find("part.protection")[0].examples)
        self.assertEqual([one.key for one in meanings.find("zone.edge")[0].words], ["edge: tape inside", "edge: tape outside"])

    def test_of_a_value(self):
        """Catches a path into a season whose property is not found: in a record, a limit, a spot, a tag, a list or a variant."""
        from frc_design_kernel.rules import meanings, read
        book, _ = read.gather("", example())
        for path, key in [("barn.opening.bottom", "opening.bottom"), ("limits.reach.far", "limits.reach.far"), ("size.length", "size.length"), ("size.length.welded", "size.length"),
                          ("rack.spots.first.a.at.x", "spot.at"), ("rack@red.3.b.at.x", "spot.at"), ("tags.t3.tilt", "tag.tilt"), ("judged.late.after_teleop", "judged.after_"), ("barn.at.y", "placed.at"),
                          ("total.bale", "total"), ("bale.mass.low", "piece.mass"), ("parts.wire.main.thinnest", "part.thinnest"), ("barn.out", None), ("yard", "zone"), ("limits.hold.bale", "limits.hold"), ("no.such", None)]:
            one = meanings.of_path(book, path)
            self.assertEqual(one.key if one else None, key, path)


if __name__ == "__main__":
    unittest.main()
