# The rules data format

One folder holds one edition of a game's rules. A person or an agent reads it instead of the manual. A program reads
the same numbers from it. Every number is written once.

Examples here are invented.

## 1. The files

| File | Holds | Who needs it |
|---|---|---|
| `game.json` | Edition, sources, what changes a number (`variants`), where positions are measured from, people | everyone |
| `clock.json` | Periods, windows (spans of time with a name), states (things that are true for a while) | strategy, rehearsal, controls |
| `field.json` | Size, zones, lines, solids, ways through, things robots hang on, vision tags | every design phase, vision |
| `pieces.json` | Each piece: shape, size, mass | every design phase |
| `places.json` | Everywhere a piece can be: where it starts, comes from, can be put, and goes next | strategy, rehearsal, concepts |
| `scoring.json` | What earns points, what is counted, what fouls cost | strategy, rehearsal, concepts |
| `conduct.json` | What robots and people may not do, and what it costs | strategy, rehearsal, controls |
| `robot.json` | What a robot must be | every design phase, inspection |
| `terms.json` | The manual's defined words | everyone |

**A place is both a target and a supply.** A piece put in one place often comes out of another. Follow `takes`, `gives`
and `then`, and no piece is lost or made.

**Two kinds of content.** What a program computes from has named fields, below. Everything else is `says`: words that are
enough for a reader who never opens the manual. Do not give structure to a rule that only people judge.

All nine files must be there. Each is one JSON object. IDs start with a letter and use letters, digits and underscores.
An ID is used once in the folder. **A path is the ID and then field names,** with no file name: `bale.mass`,
`barn.opening.bottom`. Some begin with a word instead: `size.length`, `limits.reach.far`, `tags.t4.at.x`, `total.bale`,
`judged.late.after_teleop`, `parts.wire.main.thinnest`.

## 2. Fields any record may have

| Field | Holds |
|---|---|
| `says` | The whole meaning in our own words. Numbers come from the fields: `{height}` is this record's, `{bale.mass}` another's |
| `code` | The manual's rule code, or a list. Codes change each season, so programs never use them |
| `src` | Where it is written: `"manual 3.2"`, or a list. The first word is an ID in `sources` |
| `unknown` | A list: what a reader would look for and **no source gives**. A known fact never goes here |
| `differs` | Another source that says something different (section 3) |
| `was` | Earlier values or wording, on a record or on one value: a list of `{"until": "2031-02-04", "is": "104 lb", "src": "update3 R7"}`, or with `says` |

**Every rule code has a record of its own, with its own `says`.** A number that a limit holds is named there, not typed. If a
rule is a whole list in `parts`, its `says` gives the rule and names the group.

**In `says` a limit prints without its words:** `{limits.height.max}` prints `4 ft`, so write "at most {limits.height.max}".

**A record may hold more values than this page names,** such as `"gate_width": "38 in"`. Use a name of letters, digits and
underscores that says what it is, or add `of`. A name that is nearly one this page gives that kind of record is refused as
a slip. An extra value is a number, a `true` or `false`, or `{"text": "words"}`.

## 3. Values

**A number is written as it is printed.**

| You write | It means |
|---|---|
| `"71 in"`, `"5 ft 4 3/8 in"`, `"1 min 50 s"`, `"17 deg"` | A quantity. Feet with inches, and minutes with seconds, may be joined |
| `"6.4 oz +/- 0.3"`, `"290 in +5 -1"` | With a tolerance, in the same unit |
| `"0.7 to 0.9 lb"` | A range: both ends are printed |
| `"at most 96 in"`, `"at least 3/8 in"`, `"less than 2 1/4 in"`, `"more than 7 s"`, `"at most 6"`, `"1 to 2"` | A limit or a range, on a quantity or a count |
| `{"any": [{"deep": "at most 1 in"}, {"wide": "at most 9 in"}]}` | One of these limits is enough |
| `45` | A count |
| `"= size.length / 2"` | Worked out (below) |

Units that convert: `in ft mm cm m`, `lb oz kg g`, `s min`, `deg`. Units kept as printed: `A V W Wh Ah ohm psi bar cfm scfm
uF AWG mm2 USD Mbit/s lb/ft3 kg/m3 nm Hz rpm`. No others. A thicker wire has a smaller AWG, so use `thinnest`.

A value that needs more is an object:

| You write | Use it when |
|---|---|
| `{"is": "37.5 in", "of": "across the flats"}` | The name does not say what is measured, from where to where |
| `{"is": "44 in", "src": "drawings sheet 3"}` | It comes from a different source than the record |
| `{"is": "9 in", "assumed": "scaled from figure 5-2"}` | No source prints it |
| `{"by": "field", "welded": "612.40 in", "bolted": "611.75 in"}` | It depends on a variant. One may hold another |
| `{"is": "36 in", "differs": [{"is": "36.4 in", "src": "drawings sheet 9"}]}` | Two sources disagree. `is` is the one to use. On a whole record, `differs` holds `says` |

**Formulas** name paths. A list's parts are `.x`, `.y`, `.z`; a range's are `.low` and `.high`. Adding needs the same kind of
number, and a bare number only multiplies or divides. `sin cos tan atan2 sqrt abs min max` are allowed, and an angle needs no
conversion. A formula that names a value with variants has the same variants.

## 4. `game.json`

```json
{
  "name": "Hay Day", "season": 2031, "edition": "manual 4, 2031-03-14",
  "sources": {"manual": {"title": "Game manual", "edition": "4", "url": "https://..."}},
  "variants": {"field": ["welded", "bolted"], "event": ["regional", "championship"], "match": ["qualification", "playoff"], "gate": ["low", "high"]},
  "frame": {"origin": "blue wall, scoring table side, on the carpet", "x": "toward the red wall", "y": "away from the scoring table", "z": "up"},
  "people": {"coach": {"says": "Guides the team.", "most": 1}, "driver": {"says": "Runs the robot."}, "feeder": {"says": "Handles bales."},
             "together": [{"of": ["driver", "feeder"], "most": 3}]}
}
```

`variants` are the kinds of field, event and match, and anything that a team chooses, such as a gate's height. A question
that names none gets the first.

## 5. Both alliances from one record

`"alliance": "each"` means that blue and red each have one. Write blue's. Red's is made by `symmetry` in `field.json`:

| Symmetry | Point (x, y) becomes | Direction a becomes |
|---|---|---|
| `mirror` | (length - x, y) | 180 - a |
| `turn` | (length - x, width - y) | a + 180 |

A record may have its own `"symmetry"`. `mirror` also swaps left and right in an outline that is not the same on both sides.

- A place that belongs to an alliance but stands at the other end is still written as blue's, where blue's stands.
- In a position, `stall.at.x` means the same alliance's stall. To name one from outside, write `stall@red`.
- In rules, write `my` and `their`. **They are always seen from the robot that acts,** so they never change color.

**Several of one thing.** `spots` names each: `{"near": {"at": [...]}, "far": {"at": [...]}}`. Or a pattern:
`{"row": 4, "step": ["0 in", "48 in"], "first": {...}}`, `{"ring": 6, "around": [x, y], "step": "60 deg", "first": {...}}`,
numbered from 1 or named by `"names"`. `first` may hold several named spots, which makes `1.a`, `1.b`, `2.a` and so on. A ring
turns each spot's `faces` too.

**A count belongs to the record** of one alliance, all its spots together: `"starts": {"bale": 12}`. For one spot, write
`{"each": "spot", "is": 1}`. Do not type a count that the spots already make.

## 6. `clock.json`

```json
{
  "periods": {"auto": {"lasts": "12 s", "control": "none"}, "gap": {"lasts": "2 s", "control": "none"}, "teleop": {"lasts": "1 min 50 s", "control": "drivers"}},
  "windows": {"endgame": {"in": "teleop", "last": "25 s"}, "early": {"in": "teleop", "first": "35 s"}, "market": {"in": "teleop", "timer": ["1:15", "0:50"]}},
  "states": {
    "lit": {"of": "alliance", "starts": "a person presses the lamp", "needs": [["my banked_bales", "at least", 3]], "lasts": "9 s", "or_until": "5 bales go in", "grace": "2 s"},
    "barn_open": {"of": "alliance", "true": [["auto"], ["market", "not lit"], ["endgame"]]}
  }
}
```

A window says its `first`, its `last` or its `timer` (as the match timer counts down). Windows may overlap. A state is `of`
an `alliance`, a `robot`, a `piece`, a `place` or the `match`.

**`when`** is used everywhere. It lists names of periods, windows, states and variants that must all be true:
`["teleop", "lit"]`, `["not endgame"]`, `["their lit"]`. A state with no word in front is mine. A state's `true` is a list of
`when` lists, and any one is enough.

## 7. `field.json`

```json
{
  "size": {"length": "612 in", "width": "300 in"}, "symmetry": "turn",
  "zones": {"yard": {"alliance": "each", "at": ["27 in", "40 in"], "outline": {"rectangle": ["54 in", "21 in"]}, "edge": "tape inside", "height": "none"}},
  "lines": {"centre": {"from": ["= size.length / 2", "0 in"], "to": ["= size.length / 2", "= size.width"]}},
  "solids": {"crate": {"alliance": "each", "at": ["131 in", "150 in", "0 in"], "faces": "0 deg", "shape": {"box": ["22 in", "55 in", "15 in"]}}},
  "passages": {"arch": {"alliance": "each", "kind": "under", "at": ["200 in", "30 in"], "width": "44 in", "height": "26 3/4 in"}},
  "equipment": {"barn_light": {"alliance": "each", "says": "On while the barn is open."}},
  "hangs": {"bar": {"alliance": "each", "kind": "bar", "at": ["40 in", "150 in", "33 in"], "faces": "0 deg", "diameter": "1 1/2 in", "width": "29 1/2 in"}},
  "tags": {"family": "36h11", "black": "5 1/2 in", "panel": "9 in", "t1": {"at": ["480 in", "12 in", "40 in"], "faces": "135 deg", "tilt": "0 deg"}}
}
```

- `at` is `[x, y]` or `[x, y, z]`. `faces` is a direction in plan: 0 deg is +X, 90 deg is +Y, anticlockwise from above.
  A tag's `tilt` is how far it leans down from upright.
- **An outline** is a list of points in the field's frame, or a shape with its middle at `at`, turned by `faces`:
  `{"rectangle": [along faces, across]}`, `{"hexagon": {"flats": "40 in", "points": "90 deg"}}` (across the flats, and one
  direction that a point looks), `{"circle": "40 in"}`.
- **A zone, line, solid or hang that a rule or a score names must have an outline, `from` and `to`, a `shape`, or an `at`.**
  If no source gives it, it has `"no_geometry": "why"`, and the loader lists it.
- `edge` is `tape inside` or `tape outside`. `height` is `none` (no limit) or a quantity. `for` is `people` when no robot goes there.
- **A shape is drawn around its record's `at`, turned by `faces`,** and stands on the height in `at`. A box is `[along faces,
  across, up]`. Other shapes: `taper` `{bottom, top, tall}` (two outlines, for faces that lean), `cylinder` `{diameter, length, axis}`, `ball` `{diameter}`, `ring` `{inside, outside, thick}`, `tube` `{inside, outside, length}`, `prism`
  `{outline, tall}`, and `join` or `cut`: lists of shapes, each with its own `at`.
  Points of an outline inside a shape are from `at`, along `faces`. If no source gives the height a solid starts at, leave it
  out of `at` and put that in `unknown`.
- `equipment` is lights, station shelves, buttons and the like. A tag may have its own `panel`.
- `passages` are `under` (`height`), `over` (`rise`, `slope`) or `between` (`width`).
- `hangs` are `bar`, `chain`, `frame`, `post` or `ledge`. `at` is the middle of a bar, the lowest point of a chain, the middle
  of the bottom of a frame or post. `may_touch` and `may_not_touch` list IDs, or words for a part that has none.

## 8. `pieces.json`

```json
{"bale": {"shape": {"tube": {"inside": "3 in", "outside": "5 in", "length": "9 1/4 in"}}, "mass": "0.7 to 0.9 lb", "stiff": true, "still_one_if": "it looks about like a bale"}}
```

## 9. `places.json`

| Field | Holds |
|---|---|
| `at`, `faces`, `spots` | Where it is: the middle of an opening or a surface, the tip of a post, the middle of where pieces rest |
| `starts` | What is there at the start: `{"bale": 17}`, or `{"bale": "left over"}` for what the other places do not use |
| `holds` | The most it can hold |
| `opening` | `outline` (a circle, rectangle `[width, height]` or hexagon), `slope` (0 deg is flat, 90 deg is upright), `from` (`front`, `above` or `below`), `bottom` and `top` (carpet to its lowest and highest edge), `depth`, `lip` |
| `post` | A rod that goes through a piece: `tip` (carpet to the top), `slope` (90 deg is upright), `diameter`, `length` |
| `surface` | Something to rest on: `edge` (carpet to the edge), `size`, `slope` |
| `slide` | The slope of a slide behind an opening that people feed pieces down |
| `takes` | A list: `piece`, `by` (`robot`, `human`, `field`), `how` (`enter`, `rest`, `surround`), `counts` (words: what must be true), `score` (an award), `most` |
| `gives` | A list: `piece`, `by` (`human`, `field`), `to` (an ID, `floor` or `robot`), `how` (words) |
| `then` | Where a piece goes once taken: `{"to": ID, "of": "mine" or "theirs", "how": words}`, or `{"to": "out"}` |

## 10. `scoring.json`

```json
{
  "total": {"bale": 60},
  "counts": {
    "loft_points": {"of": "alliance", "adds": ["hang", "park"]},
    "hanging_robots": {"of": "alliance", "counts": ["hang"]},
    "banked_bales": {"of": "alliance", "says": "Bales put in since the lamp was last lit."}
  },
  "awards": {
    "bale_in_barn": {"per": "piece", "points": [{"when": ["auto"], "points": 7}, {"when": ["teleop"], "points": 3}, {"when": ["teleop", "lit"], "points": 6}]},
    "hang": {"per": "robot", "points": [{"when": ["teleop"], "points": 9}], "says": "Off the carpet on the bar."},
    "park": {"per": "robot", "points": [{"when": ["teleop"], "points": 4}], "needs": [["my bumpers", "partly in", "my yard"]], "unless": ["hang"]},
    "loft_rp": {"per": "match", "rp": 1, "when": ["qualification"], "needs": [["my loft_points", "at least", 12], ["my hanging_robots", "at least", 2]]}
  },
  "judged": {"late": {"awards": ["bale_in_barn"], "after_auto": "2 s", "after_teleop": "2 s"}, "climbs": {"awards": ["park", "hang"], "after_teleop": "4 s", "or_sooner": "all robots rest"}},
  "fouls": {"minor": {"points_to_them": 3}, "yellow_card": {"says": "A warning. A second becomes a red card."}}
}
```

- Of the rows that are true, the one with the most words in `when` counts; two that tie are refused.
- **`judged`** says how long after a period an award is still looked at. A piece counted then belongs to the period that ended.
- `most` is a cap: `{"each": "barn", "is": 1}`. `unless` names awards that cancel this one. `also_needs` names an award whose
  `needs` apply too. `easier` holds the `needs` that are enough at its `when`.
- **`counts`** names everything that a condition counts. It `adds` the points of awards, `counts` how often awards are earned
  (with a `when`, only then), or takes the `smallest_of` or `third_largest_of` the pieces in some places, or `says` it.

## 11. Conditions

A condition is `[who, how, what]`. It reads as English, and only these words are used.

| | Words |
|---|---|
| **Who** | `my`, `their` or `either`, then `robot`, `bumpers`, `person`, `alliance` or an ID from `counts`. Or `the piece`, or `the` and a piece's ID |
| **How** | `partly in`, `fully in`, `fully outside`, `beyond`, `over`, `above`, `through`, `from`, `touching`, `not touching`, `touching only`, `at least`, `at most`, `exactly` |
| **What** | `my`, `their` or `any`, then an ID; `carpet`; a number or formula; `every robot`; or a list, which may hold words for a part that has no ID |

- `partly in` is true when any part is in, and so also when all of it is. `over` a line is any part over it.
- `beyond` a line or zone is completely past it, on the side away from the robot's own wall.
- A list of conditions must all be true. `{"any": [...]}` needs one, `{"all": [...], "when": [...]}` groups some at a time.

## 12. `conduct.json`

Keyed by rule code, or by an ID when the manual gives no code (setup, cards, the order of placing robots).

**Every rule has `says` and `cost`.** A rule that costs nothing has `"cost": []`. A rule that a program computes from has one of five `act`s as well:

| `act` | For | Fields |
|---|---|---|
| `touch` | Contact that depends on a zone, a time or a thing | `what` (`their robot` or IDs), `through_pieces`, `whoever_starts` |
| `launch` | Where a piece may be launched or put | `piece`, `into` (an ID, if it matters) |
| `hold` | How many pieces | `limit`: a number for each piece; `longer_than` (a term or a time); `where` (IDs), if it is about keeping them somewhere |
| `cross` | Where a robot may be, or how many robots | `limit` (robots of one alliance), if any |
| `feed` | How pieces may enter or be kept | `piece`, `who`, `limit` |

with `must_not` (`true`, or the conditions that make it wrong) or `only_if` (those that make it right), `when`, and `unless`
(exceptions, in words). `who` is `robot` if left out, or a list of `robot`, people from `game.json`, or `anyone`. `who` and
`when` may be on any rule.

```json
{
  "G90": {
    "says": "A robot may not touch an opponent when either robot's bumpers are partly in the opponent's yard in the last {endgame.last}, whoever starts it, directly or through a piece.",
    "act": "touch", "what": "their robot", "through_pieces": true, "whoever_starts": true,
    "must_not": [["either bumpers", "partly in", "their yard"]], "when": ["endgame"],
    "cost": ["minor", {"award": "loft_rp", "to": "their alliance", "when": ["qualification"]}]
  },
  "G91": {"says": "A robot may not be unsafe.", "cost": [{"foul": "yellow_card", "again": "event"}, {"words": "the match does not start"}]}
}
```

`cost` is a list, and all of it adds up. Each is a foul ID, or an object with one of `foul`, `award` (given `to` someone),
`deny` (a list of awards lost), `either` (a list of fouls, one of which is given) or `words`; and, when needed:

| Field | Meaning |
|---|---|
| `if` | Only then (words) |
| `again` | Only when it happens again in the same `match`, `phase` or `event` |
| `instead_of` | A foul in this list that is then not given |
| `times`, `each`, `every` | How many; once per this (words); once more for every time that passes (a time) |
| `against` | `robot`, `team`, `alliance` or `person`, if it is not the one that broke the rule |
| `next_match` | `true`: given in the next match |
| `when` | As everywhere |

## 13. `robot.json`

**`limits`** has the same names every season. A season with no such rule leaves the name out, and a program reads that as no
limit.

| Name | Holds |
|---|---|
| `perimeter` | `size` (string around it), `bump` (how far a bolt head may stick out) |
| `start` | `height`, and `where`: conditions true when the match starts |
| `height` | `max`: the tallest it may ever be |
| `reach` | `far` (beyond the perimeter), `sides` (how many at once) |
| `weight` | Named limits: `robot`, `bumpers`, `with_bumpers`, `inspected` (all that is brought to inspection). Each has `max` and `without`: what is left off the scale |
| `hold`, `preload` | The most pieces, by piece |
| `bumpers` | `low` and `high` (the zone, from the floor), `out` (their outside from the perimeter), `hard` (hard parts from the perimeter), `gap` (between segments), `corner` (padding out from a corner), `tolerance` (allowed on each size at inspection), `padding`, `backing`, `numbers` |
| `drive` | `motors`: how many may drive it |
| `price`, `console`, `radio`, `air`, `battery` | Their numbers |

No other names. Each also has `says` where the measuring needs it.

**`parts`** is groups of records: what may be used, and how it is wired. An ID is used once in a group.

```json
{
  "motors": {"about": {"allow": "only"}, "mule": {"name": "Mule 12", "part_numbers": ["217-0000", "mu-12"], "on": {"controller": 2, "relay": 1}}},
  "controllers": {"about": {"allow": "only"}, "reins": {"name": "Reins", "part_numbers": ["rn-1"], "kind": "controller"}},
  "power": {"about": {"allow": "only", "one_of": true}, "panel": {"name": "Panel", "number": 1}},
  "branch": {"motor": {"for": "a motor controller", "protection": "at most 40 A", "each": 1}},
  "wire": {"main": {"for": "the battery to the panel", "thinnest": "6 AWG"}}
}
```

| Field | Holds |
|---|---|
| `about` | Of the whole group: `allow` is `only` (nothing else may be used) or `examples`; `one_of` is `true` if one of them is picked |
| `name`, `part_numbers`, `number` | What it is called, its part numbers, and how many there must be |
| `kind` | For a device that runs others: `controller`, `relay`, `pneumatics` or `own` (built into one motor) |
| `on` | For a motor or other load: how many one device of each kind may run. A kind that is left out may not run it. `"any"` is no limit, and `{"is": 1, "of": "each channel"}` is per channel |
| `protection`, `each` | The breaker or fuse of a circuit, and how many circuits it may feed (a number, `any`, or an object) |
| `thinnest`, `area` | The thinnest wire |
| `for` | What a row is about, in words |

**`rules`** has a record for every construction and inspection rule, keyed by code, each with its own `says`. Numbers come
from `limits`, `parts` or its own fields.

## 14. `terms.json`

```json
{"momentary": {"says": "Less than about {lasts}.", "lasts": "4 s"}}
```

A word that is already the ID of something else (a zone, a piece) has no term: its `says` is there.

## 15. Reading the sources

- **Read every change notice, not only the last edition.** The last edition may print a number that only the last event
  used. For each value that a notice changes, write what each kind of event used (`by`), and what it was before (`was`).
- **Look at the page when it has a table, a figure or struck-out words.** Text taken out of a file scrambles tables and
  loses the strike-through.
- **A drawing and the manual often differ a little.** Use the official drawing for geometry if the manual says that it
  governs, and keep the other in `differs`.
- **Say what is measured,** from where to where. If the source does not say, write that in `unknown`.
- **Never fill a gap from memory.** Use `unknown`, or `assumed` with its reason.
- **If two values are equal because one is the other,** write a formula. A target at a tag's place names the tag.
