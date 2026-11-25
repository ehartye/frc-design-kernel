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
        for key, own in [("zone.at", "placed.at"), ("limits.reach.code", "every.code"), ("opening.says", "every.says"), ("row.says", None), ("post.at", None)]:
            self.assertEqual(self.keys(key), [own] if own else [], key)
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

    def of_path(self, path, change=None):
        from frc_design_kernel.rules import meanings, read
        data = example()
        if change:
            change(data)
        book, _ = read.gather("", data)
        one = meanings.of_path(book, path)
        return one.key if one else None

    def test_of_a_spot(self):
        """Catches a path to a spot that is told what spots are, or what its record is, and not what the property at its end is."""
        for path, key in [("near_bales.spots.1.at", "spot.at"), ("near_bales.spots.1.at.x", "spot.at"), ("rack.spots.3.b.faces", "spot.faces"), ("rack.spots.3.b.post.tip", "post.tip"), ("gateway.spots.near.at.x", "spot.at"),
                          ("rack@red.3.b.post.tip", "post.tip"), ("stall@red.near.opening.bottom", "opening.bottom"), ("stall.spots.far.opening.lip", "opening.lip"), ("rack@red.3.b.pair", None),
                          ("rack@red.3.b", "spot"), ("barn@red.opening.bottom", "opening.bottom"), ("rack.spots.step", "ring.step"), ("rack.spots", "placed.spots")]:
            self.assertEqual(self.of_path(path), key, path)

    def test_of_an_extra_value_of_a_spot(self):
        """Catches a value of a spot's own that is told what its record is."""
        def change(d):
            d["places"]["stall"]["spots"]["near"]["lean"] = "1 in"
            d["places"]["rack"]["spots"]["first"]["a"]["lean"] = "1 in"
            d["places"]["near_bales"]["spots"]["first"]["lean"] = "1 in"
        for path in ["stall.spots.near.lean", "stall@red.near.lean", "rack.spots.3.a.lean", "rack@red.3.a.lean", "near_bales.spots.2.lean", "near_bales@red.2.lean"]:
            self.assertIsNone(self.of_path(path, change), path)
        self.assertEqual(self.of_path("stall@red.near.faces", change), "spot.faces")

    def test_of_a_size(self):
        """Catches a size in a shape or an outline that is told what the whole shape is."""
        for path, key in [("pumpkin.shape.ball.diameter", "ball.diameter"), ("pumpkin.shape.ball.diameter.low", "ball.diameter"), ("bale.shape.tube.length", "tube.length"), ("hoop.shape.ring.inside", "ring.inside"),
                          ("crate.shape", "solid.shape"), ("crate.shape.box.z", "shape: box"), ("crate@red.shape.box.z", "shape: box"), ("barn_body.shape.cut.y.box.x", "shape: box"), ("barn_body.shape.cut.y.at.z", "shape: cut"),
                          ("pen.shape.prism.tall", "prism.tall"), ("pen.shape.prism.outline", "prism.outline"), ("manger.shape.taper.top.rectangle.x", "outline: rectangle"), ("trestle.shape.join.y.prism.outline.hexagon.flats", "hexagon.flats"),
                          ("yard.outline.rectangle.x", "outline: rectangle"), ("loft.opening.outline.circle", "outline: circle"), ("lane.outline", "zone.outline"), ("yard.deep", "zone.deep")]:
            self.assertEqual(self.of_path(path), key, path)

    def test_of_a_size_by_variant(self):
        """Catches the name of a variant on the way to a size that hides the size."""
        def change(d):
            d["field"]["zones"]["pond"]["outline"] = {"by": "gate", "low_gate": {"circle": "46 in"}, "high_gate": {"circle": {"is": "48 in"}}}
        for path in ["pond.outline.high_gate.circle", "pond.outline.circle", "pond.outline.high_gate.circle.is"]:
            self.assertEqual(self.of_path(path, change), "outline: circle", path)
        self.assertEqual(self.of_path("pond.outline.high_gate", change), "zone.outline")

    def test_what_must_be_there(self):
        """Catches an author who is not told which names a record must have, and which others it may not."""
        from frc_design_kernel.rules import meanings

        def notes(key):
            return [note for one in meanings.everything() if one.key == key for note in one.notes]
        self.assertEqual(notes("window"), ["It must have `in`.", "It has exactly one of `first`, `last` and `timer`."])
        self.assertEqual(notes("part"), ["It must have `src`.", "It has at least one of `name` and `for`."])
        self.assertEqual(notes("zone"), ["It may have the fields of `placed`.", "It needs geometry, or `no_geometry`, when a rule or a score names it."])
        self.assertEqual(notes("row"), ["It has no extra values.", "It must have `row`, `step` and `first`."])
        self.assertEqual(notes("award"), ["With `per` robot it must have `looked_at`."])
        self.assertEqual(notes("conduct"), ["It must have `says` and `cost`.", "With an `act` it has at least one of `must_not`, `only_if` and `limit`."])
        self.assertEqual(notes("game.json"), ["It must have `name`, `season`, `edition`, `sources` and `frame`."])
        self.assertEqual(notes("pieces.json"), ["Each name in it is the ID of a record of the kind `piece`."])
        self.assertEqual((notes("limits.hold"), notes("total")), (["Its fields are the IDs of pieces."], ["Its fields are the IDs of pieces."]))
        self.assertEqual((notes("cylinder.axis"), notes("cylinder.length")), (["It may be left out."], []))

    def test_every_flag_is_told(self):
        """Catches a new flag in fields.json that says what must be there and that nobody who asks is told."""
        from frc_design_kernel.rules import meanings, read
        self.assertEqual(not_told(read.names(), meanings.NOTES), [])

    def test_a_flag_that_is_not_told_is_caught(self):
        """Control: a flag of a kind and one of a field that no note tells are found."""
        from frc_design_kernel.rules import meanings
        self.data = {"kinds": {"zone": {"means": "x", "fields": {"at": {"holds": "x", "never": 1}}, "just_one": True}}}
        self.assertEqual(not_told(self.data, meanings.NOTES), ["zone.just_one", "zone.at.never"])

    def test_the_fields_of_a_kind(self):
        """Catches a kind of record or a shape that is asked for and does not say what its fields are, or says another's."""
        from frc_design_kernel.rules import meanings
        fields = {one.key: [field.key for field in one.fields] for one in meanings.everything()}
        self.assertEqual(fields["post"], ["post.tip", "post.slope", "post.diameter", "post.length"])
        self.assertEqual(fields["shape: ring"], ["ring.inside", "ring.outside", "ring.thick"])
        self.assertEqual(fields["ring"], ["ring.ring", "ring.around", "ring.step", "ring.first", "ring.names"])
        self.assertEqual(fields["limits.reach"], ["limits.reach.far", "limits.reach.sides"])
        self.assertEqual(fields["clock.json"], ["clock.periods", "clock.windows", "clock.states"])

    def test_names_that_are_near(self):
        """Catches a slip that is told nothing, and a name that is near nothing and is told something."""
        from frc_design_kernel.rules import meanings
        self.assertIn("bottom", meanings.near("botom"))
        self.assertIn("opening.bottom", meanings.near("opening.botom"))
        self.assertEqual(meanings.near("xyzzyq"), [])


def not_told(data, notes):
    """Each flag of fields.json, such as needs, that no note tells. What these names hold is told otherwise."""
    told = {"means", "fields", "holds", "words", "examples", *notes}
    found = []
    for section in ("files", "kinds", "limits", "shapes", "outlines"):
        for name, about in data.get(section, {}).items():
            found += [f"{name}.{flag}" for flag in about if flag not in told]
            found += [f"{name}.{field}.{flag}" for field, one in about.get("fields", {}).items() for flag in one if flag not in told]
    return found


if __name__ == "__main__":
    unittest.main()
