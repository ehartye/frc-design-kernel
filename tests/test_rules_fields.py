"""The fields of every record: their names, and the values that they hold (RULES.md)."""
import unittest

from .rules_cases import Checked, example, rename


class FieldNames(Checked):
    """fields.check: the names that a record may use."""

    def test_the_example_has_no_faults(self):
        """Control for every refusal in this class and the next: the example as it is passes."""
        self.assertEqual(self.faults(), [])

    def test_a_slip_in_a_field_name(self):
        """Catches openning for opening: the opening would be lost, and read as one that is not there."""
        self.refused(lambda d: rename(d["places"]["barn"], "opening", "openning"), "places.json barn", '"openning"', '"opening"')
        self.refused(lambda d: rename(d["clock"]["states"]["lit"], "grace", "graces"), "clock.json lit", '"grace"')
        self.refused(lambda d: rename(d["field"]["zones"]["yard"], "outline", "outlin"), "yard", '"outline"')

    def test_a_slip_inside_a_field(self):
        """Catches a slip in an object inside a record: an opening, a spot, a cost, a part, a limit, a tag, a source."""
        self.refused(lambda d: rename(d["places"]["barn"]["opening"], "bottom", "botom"), "places.json barn.opening", '"bottom"')
        self.refused(lambda d: rename(d["places"]["stall"]["spots"]["near"], "faces", "facess"), "stall.spots.near", '"faces"')
        self.refused(lambda d: rename(d["robot"]["limits"]["bumpers"], "tolerance", "toleranse"), "limits.bumpers", '"tolerance"')
        self.refused(lambda d: rename(d["robot"]["parts"]["motors"]["mule"], "part_numbers", "part_numers"), "parts.motors.mule", '"part_numbers"')
        self.refused(lambda d: rename(d["field"]["tags"]["t3"], "panel", "panell"), "tags.t3", '"panel"')
        self.refused(lambda d: rename(d["game"]["sources"]["manual"], "edition", "edittion"), "sources.manual", '"edition"')
        self.refused(lambda d: rename(d["field"]["guardrail"], "gate_width", "gate_with"), "field.json guardrail", '"gate_width"')
        self.refused(lambda d: rename(d["game"]["accuracy"], "decimal", "decimals"), "game.json accuracy", '"decimal"')
        self.refused(lambda d: rename(d["places"]["barn"]["takes"][0], "counts", "count"), "barn.takes[0]", '"counts"')

    def test_a_slip_in_a_group(self):
        """Catches windws for windows: every window in it would be lost."""
        self.refused(lambda d: rename(d["field"], "passages", "pasages"), "field.json", '"passages"')

    def test_a_part_of_a_fixed_form(self):
        """Catches a field that a fixed form does not have: a cost, a pattern, a shape, a value, people together."""
        self.refused(lambda d: d["conduct"]["G92"]["cost"][1].update(per="6 s"), "G92.cost[1]", '"per"', "every")
        self.refused(lambda d: d["places"]["rack"]["spots"].update(turns=2), "rack.spots", '"turns"', "ring")
        self.refused(lambda d: d["field"]["solids"]["crate"]["shape"].update(tall="3 in"), "crate.shape")
        self.refused(lambda d: d["pieces"]["bale"]["shape"]["tube"].update(wall="1 in"), "bale.shape.tube", '"wall"')
        self.refused(lambda d: d["pieces"]["hoop"]["mass"].update(scale="1 lb"), "hoop.mass", '"scale"')
        self.refused(lambda d: d["game"]["people"]["together"][0].update(least=1), "people.together[0]", '"least"')

    def test_extra_fields_are_allowed(self):
        """Catches a check so tight that an author can not add what this game has and others do not."""
        self.accepted(lambda d: d["places"]["barn"].update(door_width="30 in", doors=2, painted=True, hue={"text": "red"}, corner={"is": "2 in", "of": "its radius"}))
        self.accepted(lambda d: d["places"]["barn"].update(frame={"wide": "3 in", "inside": {"deep": "1 in"}, "src": "manual 3.5"}, sides=["1 in", "2 in"]))
        self.accepted(lambda d: d["places"]["barn"].update(by_gate={"by": "gate", "low_gate": "1 in", "high_gate": {"by": "field", "welded": "2 in", "bolted": "3 in"}}))
        self.accepted(lambda d: d["robot"]["parts"]["wire"]["main"].update(gauge_swg=7))
        self.accepted(lambda d: d["robot"]["limits"]["air"].update(relief="115 psi"))
        self.accepted(lambda d: [d["field"]["guardrail"].update(paint_width="2 in"), d["game"]["accuracy"].update(checked=True)])

    def test_guardrail_and_accuracy_may_be_left_out(self):
        """Catches a game refused because its manual prints no guardrail or no tolerance. A part of either may be missing too."""
        self.accepted(lambda d: [d["field"].pop("guardrail"), d["game"].pop("accuracy")])
        self.accepted(lambda d: [d["field"].update(guardrail={"src": "manual 3.1"}), d["game"].update(accuracy={"says": "Sizes are nominal.", "src": "manual 2"})])
        self.refused(lambda d: d["field"].update(guardrail="22 in"), "field.json guardrail", "object")
        self.refused(lambda d: d["game"].update(accuracy=[]), "game.json accuracy", "object")

    def test_an_extra_text_that_is_not_written_as_text(self):
        """Catches words in an extra field, which a program could take for a number that failed to read."""
        self.refused(lambda d: d["places"]["barn"].update(hue="red"), "places.json barn.hue", '{"text": ...}')
        self.refused(lambda d: d["field"]["size"].update(surface="carpet"), "field.json size.surface", "text")
        self.refused(lambda d: d["places"]["barn"].update(note_size="14 by 10"), "barn.note_size")
        self.refused(lambda d: d["places"]["barn"].update(frame={"hue": "red"}), "barn.frame.hue")

    def test_a_field_name_that_is_not_one(self):
        """Catches a field name with a space or a dash, which a formula or a {name} in says could not give."""
        self.refused(lambda d: d["places"]["barn"].update({"door width": "3 in"}), "barn", "letters")
        self.refused(lambda d: d["places"]["barn"].update(frame={"1st": "3 in"}), "barn.frame", "letter")
        self.refused(lambda d: d["field"].update({"my fence": {"tall": "3 in"}}), "field.json", '"my fence"')

    def test_a_limit_that_is_not_a_name(self):
        """Catches a limit that no program asks for: "No other names"."""
        self.refused(lambda d: d["robot"]["limits"].update(power={"says": "x", "src": "manual R98"}), "limits.power", "perimeter")
        self.refused(lambda d: rename(d["robot"]["limits"], "battery", "batteries"), "limits.batteries", 'Did you mean "battery"')

    def test_a_weight_that_is_not_a_name(self):
        """Catches a weight limit that no program asks for. A plain extra value beside the weights is allowed."""
        self.refused(lambda d: d["robot"]["limits"]["weight"].update(naked={"max": "at most 100 lb", "without": []}), "limits.weight", '"naked"', "robot")
        self.accepted(lambda d: d["robot"]["limits"]["weight"].update(cable={"is": "at most 12 in", "of": "that counts as battery"}))

    def test_what_a_record_must_have(self):
        """Catches a conduct rule without says or cost, a construction rule without says, and a part without a source."""
        self.refused(lambda d: d["conduct"]["G90"].pop("cost"), "conduct.json G90", '"cost"')
        self.refused(lambda d: d["conduct"]["G91"].pop("says"), "conduct.json G91", '"says"')
        self.refused(lambda d: d["conduct"]["G91"].update(says=" "), "conduct.json G91.says")
        self.refused(lambda d: d["robot"]["rules"]["R94"].pop("says"), "robot.json R94", '"says"')
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"].pop("src"), "parts.motors.mule", '"src"')
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"].pop("name"), "parts.motors.mule", "name", "for")
        self.refused(lambda d: d["robot"]["parts"]["power"]["about"].pop("allow"), "parts.power.about", '"allow"')
        self.refused(lambda d: d["places"]["stall"]["spots"]["far"].pop("at"), "stall.spots.far", '"at"')
        self.refused(lambda d: d["scoring"]["awards"]["hang"]["points"][0].pop("when"), "hang.points[0]", '"when"')
        self.refused(lambda d: d["places"]["barn"]["takes"][0].pop("piece"), "barn.takes[0]", '"piece"')


class FieldValues(Checked):
    """fields.check: what each field holds."""

    def test_a_unit_that_is_not_listed(self):
        """Catches 54 feet, which would be a length that no program can read."""
        self.refused(lambda d: d["field"]["size"].update(width="25 feet"), "field.json size.width", "feet")
        self.refused(lambda d: d["robot"]["limits"]["air"].update(flow="at most 1.1 scfh"), "limits.air.flow", "scfm")

    def test_a_value_that_does_not_read(self):
        """Catches words, nothing, or an empty list where a number must be."""
        for bad in ["wide", None, {}, "", {"is": None}, {"text": "wide"}, ["1 in"]]:
            self.refused(lambda d, bad=bad: d["field"]["hangs"]["bar"].update(width=bad), "field.json bar.width")

    def test_a_value_of_the_wrong_kind(self):
        """Catches a mass where a length must be, and a wire or circuit size that is not one."""
        self.refused(lambda d: d["field"]["hangs"]["bar"].update(width="3 lb"), "bar.width", "length", "mass")
        self.refused(lambda d: d["field"]["hangs"]["bar"].update(width=3), "bar.width", "length")
        self.refused(lambda d: d["robot"]["parts"]["wire"]["main"].update(thinnest="6 gauge"), "parts.wire.main.thinnest", "gauge")
        self.refused(lambda d: d["robot"]["parts"]["wire"]["main"].update(thinnest="6 mm2"), "parts.wire.main.thinnest", "AWG")
        self.refused(lambda d: d["robot"]["parts"]["branch"]["motor"].update(protection="at most 40 W"), "parts.branch.motor.protection")
        self.refused(lambda d: d["clock"]["periods"]["auto"].update(lasts="12 in"), "auto.lasts", "time")
        self.refused(lambda d: d["field"]["guardrail"].update(gates="3 in"), "field.json guardrail.gates", "count")
        self.refused(lambda d: d["game"]["accuracy"].update(angle="1 in"), "game.json accuracy.angle", "angle")
        self.refused(lambda d: d["pieces"]["bale"].update(stiff="yes"), "bale.stiff", "true or false")
        self.refused(lambda d: d["scoring"]["fouls"]["minor"].update(points_to_them="3 in"), "minor.points_to_them")
        self.refused(lambda d: d["conduct"]["G92"]["cost"][1].update(every="3 in"), "G92.cost[1].every", "time")
        self.refused(lambda d: d["conduct"]["G95"]["cost"][0].update(every=True), "G95.cost[0].every", "time")

    def test_a_formula_is_left_for_later(self):
        """Control: a formula is not read here, whatever it says, and neither is it refused."""
        self.accepted(lambda d: d["field"]["hangs"]["bar"].update(width="= yard.no_such + 3"))

    def test_a_range_the_wrong_way_round(self):
        """Catches a range whose low is above its high."""
        self.refused(lambda d: d["pieces"]["bale"].update(mass="9 to 8 oz"), "pieces.json bale.mass", "low")

    def test_one_of_these_is_enough(self):
        """Catches an any whose limits do not read, or that is not a list of named values."""
        for bad in [[{"deep": "a bit"}], [], {"deep": "1 in"}, ["at most 1 in"], [{}]]:
            self.refused(lambda d, bad=bad: d["robot"]["limits"]["bumpers"].update(frame_gap={"any": bad}), "limits.bumpers.frame_gap")
        self.refused(lambda d: d["robot"]["limits"]["bumpers"].update(gap={"any": [{"deep": "1 lb"}]}), "limits.bumpers.gap", "length")
        self.refused(lambda d: d["robot"]["limits"]["bumpers"].update(gap={"any": [{"how deep": "1 in"}]}), "limits.bumpers.gap.any[0]", '"how deep"')

    def test_a_variant(self):
        """Catches a value with a variant left out, one that is not there, or a kind of variant that is not."""
        size = lambda d: d["field"]["size"]
        self.refused(lambda d: size(d)["length"].pop("bolted"), "field.json size.length", '"bolted"')
        self.refused(lambda d: size(d)["length"].update(glued="3 in"), "size.length", '"glued"', "welded")
        self.refused(lambda d: size(d)["length"].update(by="feild"), "size.length", 'Did you mean "field"')
        self.refused(lambda d: size(d)["length"].update(bolted="3 feet"), "size.length.bolted", "feet")
        self.refused(lambda d: d["scoring"]["awards"]["bale_on_bench"]["points"][0]["points"].pop("championship"), "bale_on_bench.points[0].points", '"championship"')

    def test_variants(self):
        """Catches variants that are not lists of names, or a name that is there twice."""
        for bad in ["welded", [], ["welded", 3], ["welded", "welded"], ["wel ded", "bolted"]]:
            self.assertTrue(any("game.json variants.match" in f for f in self.faults(lambda d, bad=bad: d["game"]["variants"].update(match=bad))), bad)

    def test_points(self):
        """Catches a position with one number, with four, or with a bare number, and an outline with two points."""
        zones = lambda d: d["field"]["zones"]
        for bad in [["1 in"], ["1 in"] * 4, ["1 in", 2], "1 in", [], ["1 in", "2 deg"]]:
            self.refused(lambda d, bad=bad: zones(d)["yard"].update(at=bad), "field.json yard.at")
        for bad in [[["0 in", "0 in"], ["1 in", "1 in"]], [["0 in", "0 in"], ["1 in", "1 in"], ["1 in"]], "round", {}, {"circle": "4 in", "rectangle": ["1 in", "1 in"]}, {"square": "4 in"},
                    {"rectangle": ["1 in"]}, {"hexagon": {"flats": "4 in"}}, {"hexagon": {"flats": "4 in", "points": ["0 deg", "180 deg"]}}, {"circle": "4 deg"}]:
            self.assertEqual([f.split(".outline")[0] for f in self.faults(lambda d, bad=bad: zones(d)["yard"].update(outline=bad))], ["field.json yard"], bad)
        self.accepted(lambda d: zones(d)["yard"].update(at={"by": "gate", "low_gate": ["1 in", "2 in"], "high_gate": {"is": ["3 in", "4 in"], "src": "manual 3"}}))

    def test_shapes(self):
        """Catches a shape that the library could not draw: an unknown one, a size left out, two at once, a join with nothing in it."""
        for bad in [{"cone": {"diameter": "1 in"}}, {"box": ["1 in", "2 in"]}, {"cylinder": {"diameter": "1 in"}}, {"cylinder": {"diameter": "1 in", "length": "2 in", "axis": "up"}},
                    {"ball": "3 in"}, {"ball": {"diameter": "3 in"}, "box": ["1 in", "1 in", "1 in"]}, {"join": []}, {"join": [{"box": ["1 in", "1 in", "1 in"]}]}, {}, [],
                    {"prism": {"outline": [["0 in", "0 in"]], "tall": "1 in"}}, {"taper": {"bottom": {"circle": "1 in"}, "top": {"circle": "1 in"}}},
                    {"ball": {"diameter": "3 in"}, "at": ["0 in", "0 in", "0 in"]}]:
            self.assertEqual([f.split(".shape")[0] for f in self.faults(lambda d, bad=bad: d["field"]["solids"]["crate"].update(shape=bad))], ["field.json crate"], bad)

    def test_spots(self):
        """Catches a pattern that makes the wrong number: names that are not as many as the spots, or no whole number of them."""
        rope = lambda d: d["field"]["hangs"]["rope"]["spots"]
        self.refused(lambda d: rope(d)["names"].pop(), "field.json rope.spots", "3", "2")
        self.refused(lambda d: rope(d)["names"].__setitem__(1, "front"), "rope.spots.names", '"front"')
        self.refused(lambda d: rope(d).pop("step"), "rope.spots", '"step"')
        self.refused(lambda d: rope(d).update(step="3 in"), "rope.spots.step", "angle")
        self.refused(lambda d: d["places"]["near_bales"]["spots"].update(row=0), "near_bales.spots.row")
        self.refused(lambda d: d["places"]["near_bales"]["spots"].update(row="= 2 * 2"), "near_bales.spots.row")
        self.refused(lambda d: d["places"]["near_bales"]["spots"].update(first={}), "near_bales.spots.first", '"at"')
        self.refused(lambda d: d["places"]["rack"]["spots"]["first"]["a"].pop("at"), "rack.spots.first.a", '"at"')
        self.refused(lambda d: d["places"]["stall"].update(spots={}), "stall.spots")
        self.refused(lambda d: rename(d["places"]["stall"]["spots"], "far", "far.2"), "stall.spots", '"far.2"')
        self.refused(lambda d: rope(d)["names"].__setitem__(1, "left side"), "rope.spots.names", '"left side"')
        self.refused(lambda d: rename(d["places"]["rack"]["spots"]["first"], "a", "a b"), "rack.spots.first", '"a b"')
        self.refused(lambda d: d["places"]["stall"].update(spots=["near"]), "stall.spots")

    def test_words_of_a_list(self):
        """Catches a word that is not in the lists: an edge, a kind of hang, a symmetry, an act, a device."""
        for change, where, hint in [
                (lambda d: d["field"]["zones"]["yard"].update(edge="the tape is inside"), "yard.edge", "tape inside"),
                (lambda d: d["field"]["zones"]["yard"].update(height="low"), "yard.height", "none"),
                (lambda d: d["field"]["zones"]["stands"].update({"for": "robots"}), "stands.for", "people"),
                (lambda d: d["field"].update(symmetry="mirrored"), "field.json symmetry", "mirror"),
                (lambda d: d["field"]["zones"]["lane"].update(symmetry="flip"), "lane.symmetry", "turn"),
                (lambda d: d["field"]["zones"]["yard"].update(alliance="blue"), "yard.alliance", "each"),
                (lambda d: d["field"]["hangs"]["bar"].update(kind="pole"), "bar.kind", "post"),
                (lambda d: d["field"]["passages"]["arch"].update(kind="below"), "arch.kind", "under"),
                (lambda d: d["clock"]["states"]["lit"].update(of="team"), "lit.of", "alliance"),
                (lambda d: d["places"]["barn"]["opening"].update({"from": "side"}), "barn.opening.from", "front"),
                (lambda d: d["places"]["barn"]["takes"][0].update(by=["robots"]), "barn.takes[0].by", "robot"),
                (lambda d: d["places"]["barn"]["takes"][0].update(how="drop"), "barn.takes[0].how", "enter"),
                (lambda d: d["places"]["stall"]["gives"][0].update(by="robot"), "stall.gives[0].by", "human"),
                (lambda d: d["places"]["barn"]["then"].update(of="ours"), "barn.then.of", "theirs"),
                (lambda d: d["conduct"]["G90"].update(act="shoot"), "G90.act", "launch"),
                (lambda d: d["conduct"]["G91"]["cost"][0].update(again="season"), "G91.cost[0].again", "event"),
                (lambda d: d["conduct"]["G97"]["cost"][0].update(against="crew"), "G97.cost[0].against", "team"),
                (lambda d: d["robot"]["parts"]["controllers"]["reins"].update(kind="box"), "parts.controllers.reins.kind", "controller"),
                (lambda d: d["robot"]["parts"]["power"]["about"].update(allow="some"), "parts.power.about.allow", "only")]:
            self.refused(change, where, hint)

    def test_text(self):
        """Catches a number, a list or nothing where words must be."""
        self.refused(lambda d: d["clock"]["states"]["lit"].update(starts=3), "lit.starts", "words")
        self.refused(lambda d: d["pieces"]["hoop"].update(unknown="no mass"), "hoop.unknown", "list")
        self.refused(lambda d: d["robot"]["limits"]["reach"].update(code=[3]), "limits.reach.code")
        self.refused(lambda d: d["field"]["zones"]["stands"].update(no_geometry=True), "stands.no_geometry")
        self.refused(lambda d: d["field"]["size"]["carpet"].update(text=3), "size.carpet.text", "words")
        self.refused(lambda d: d["pieces"]["hoop"]["mass"].update(assumed=""), "hoop.mass.assumed", "words")

    def test_timers(self):
        """Catches a timer that is not two times, or that runs the wrong way: it counts down."""
        for bad in ["1:15", ["1:15"], ["1:15", 50], ["0:50", "1:15"], ["1:75", "0:50"], ["75", "50"], ["1:15", "1:15"]]:
            self.refused(lambda d, bad=bad: d["clock"]["windows"]["market"].update(timer=bad), "clock.json market.timer")

    def test_a_window_says_one_of_three(self):
        """Catches a window with no first, last or timer, or with two, so that nobody knows when it is."""
        self.refused(lambda d: d["clock"]["windows"]["market"].pop("timer"), "clock.json market", "first, last or timer")
        self.refused(lambda d: d["clock"]["windows"]["market"].update(first="3 s"), "clock.json market", "first, last or timer")

    def test_counts(self):
        """Catches a count by piece that is not a number, a cap with no number, and starts in other words."""
        self.refused(lambda d: d["places"]["near_bales"]["starts"].update(bale="many"), "near_bales.starts.bale")
        self.refused(lambda d: d["places"]["near_bales"]["starts"].update(bale={"each": "spot"}), "near_bales.starts.bale")
        self.refused(lambda d: d["places"]["stall"]["holds"].update(bale="left over"), "stall.holds.bale")
        self.refused(lambda d: d["places"]["stall"].update(holds=30), "stall.holds")
        self.refused(lambda d: d["scoring"]["total"].update(bale="sixty"), "scoring.json total.bale")
        self.refused(lambda d: d["scoring"]["awards"]["hang"].update(most={"each": "alliance"}), "hang.most")
        self.refused(lambda d: d["places"]["loft"]["takes"][0].update(most="5 in"), "loft.takes[0].most")
        self.accepted(lambda d: d["scoring"]["awards"]["hang"].update(most={"each": "alliance", "is": 2, "when": ["teleop"]}))

    def test_what_a_device_runs(self):
        """Catches a load on a kind of device that is not there, or with no number, and a circuit count in words."""
        self.refused(lambda d: rename(d["robot"]["parts"]["motors"]["mule"]["on"], "controller", "contoller"), "parts.motors.mule.on", 'Did you mean "controller"')
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"]["on"].update(relay="some"), "parts.motors.mule.on.relay")
        self.refused(lambda d: d["robot"]["parts"]["motors"]["latch"]["on"]["pneumatics"].pop("is"), "parts.motors.latch.on.pneumatics")
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"].update(on="controller"), "parts.motors.mule.on")
        self.refused(lambda d: d["robot"]["parts"]["branch"]["lamps"].update(each="many"), "parts.branch.lamps.each")

    def test_sources(self):
        """Catches a source that is not in game.json, anywhere: on a record, a value, a part, a difference or a history."""
        self.refused(lambda d: d["places"]["barn"].update(src="manal 5.3"), "places.json barn.src", 'Did you mean "manual"')
        self.refused(lambda d: d["places"]["barn"].update(src=["manual 5.3", "drawing 3"]), "barn.src", "drawings")
        self.refused(lambda d: d["field"]["size"]["length"]["bolted"].update(src="drwaings 2"), "size.length.bolted.src")
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"].update(src="manal R97"), "parts.motors.mule.src")
        self.refused(lambda d: d["field"]["zones"]["fold"]["differs"][0].update(src="rumour"), "fold.differs[0].src")
        self.refused(lambda d: d["clock"]["states"]["lit"]["was"][0].update(src="update9 5"), "lit.was[0].src")
        self.refused(lambda d: d["places"]["barn"].update(src=3), "barn.src")
        self.refused(lambda d: d["robot"]["parts"]["motors"]["mule"].update(src=[]), "parts.motors.mule.src", "no source")

    def test_differs(self):
        """Catches a difference with no source, with nothing said, or whose number does not read."""
        wide = lambda d: d["places"]["barn"]["opening"]["outline"]["rectangle"][1]["differs"][0]
        self.refused(lambda d: wide(d).pop("src"), "barn.opening.outline.rectangle.y.differs[0]", '"src"')
        self.refused(lambda d: wide(d).pop("is"), "differs[0]", "is or says")
        self.refused(lambda d: wide(d).update({"is": "15 inches"}), "differs[0].is", "inches")
        self.refused(lambda d: d["field"]["zones"]["fold"].update(differs={"says": "x", "src": "manual 3"}), "fold.differs", "list")
        self.refused(lambda d: d["field"]["zones"]["fold"].update(differs=["not so"]), "fold.differs[0]", "object")
        self.refused(lambda d: d["field"]["zones"]["fold"]["differs"][0].update(page=3), "fold.differs[0]", '"page"', "src")

    def test_history(self):
        """Catches a history that is not a list, has no date or source, has nothing in it, or does not read; on a record or a value."""
        was = lambda d: d["robot"]["limits"]["weight"]["robot"]["max"]["was"][0]
        self.refused(lambda d: was(d).pop("until"), "limits.weight.robot.max.was[0]", '"until"')
        self.refused(lambda d: was(d).pop("src"), "was[0]", '"src"')
        self.refused(lambda d: was(d).pop("is"), "was[0]", "is or says")
        self.refused(lambda d: was(d).update({"is": "125 pounds"}), "was[0].is", "pounds")
        self.refused(lambda d: was(d).update(until="4 Feb"), "was[0].until", "2031-02-04")
        self.refused(lambda d: was(d).update(until="2031-02-30"), "was[0].until")
        self.refused(lambda d: d["robot"]["limits"]["weight"]["robot"]["max"].update(was={"is": "at most 125 lb"}), "limits.weight.robot.max.was", "list")
        self.refused(lambda d: d["clock"]["states"]["lit"].update(was="before"), "clock.json lit.was", "list")
        self.refused(lambda d: d["robot"]["parts"]["branch"]["valve"]["was"][0].pop("says"), "parts.branch.valve.was[0]", "is or says")

    def test_leaves(self):
        """Catches a value that a later step would never see: a formula in a list, a shape, a spot, a variant or a history."""
        from frc_design_kernel.rules import fields, read
        book, _ = read.gather("", example())
        leaves = {leaf.where: leaf for leaf in fields.leaves(book)}
        for where, kind, node in [
                ("field.json lane.outline[1].x", "length", "= lane.long"), ("field.json swing.at.z.high_gate", "length", "= swing.at.z.low_gate + swing.lift"),
                ("field.json pen.lean.is", None, "60 deg"), ("field.json tags.t3.tilt", "angle", "15 deg"),
                ("places.json rack.spots.first.a.at.x", "length", "= mast.at.x - rack.out"), ("field.json barn_body.shape.cut[1].box.x", "length", "= barn_body.deep * 2"),
                ("places.json barn.opening.outline.rectangle.y.is", "length", "16 in"), ("conduct.json G94.limit.bale", "number", "= limits.hold.bale"),
                ("robot.json limits.bumpers.frame_gap.any[1].wide", None, "at most 9 in"), ("scoring.json judged.late.after_teleop.was[0].is", None, "2 s")]:
            self.assertIn(where, leaves)
            self.assertEqual((leaves[where].kind, leaves[where].node), (kind, node), where)


if __name__ == "__main__":
    unittest.main()
