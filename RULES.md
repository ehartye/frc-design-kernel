# The rules data format

One folder holds one edition of a game's rules. A person or an agent reads it instead of the manual. A program reads
the same numbers from it. Every number is written once.

Examples here are invented.

## 1. What the format has to say

Everything in a game is one of these. Each has one file.

| File | Holds | Who needs it |
|---|---|---|
| `game.json` | Edition, sources, the kinds of field and event that change a number, where positions are measured from | everyone |
| `clock.json` | Periods, windows (spans of time with a name) and states (things that are true for a while) | strategy, rehearsal, controls |
| `field.json` | Size, zones, lines, things robots meet, ways through, things robots hang on, vision tags | every design phase, vision |
| `pieces.json` | Each piece: shape, size, mass | every design phase |
| `places.json` | Everywhere a piece can be: where it starts, where it comes from, where it can be put, where it goes next | strategy, rehearsal, concepts |
| `scoring.json` | What earns points, and what counts | strategy, rehearsal, concepts |
| `conduct.json` | What robots and people may not do, and what it costs | strategy, rehearsal, controls |
| `robot.json` | What a robot must be | every design phase, inspection |
| `terms.json` | The manual's defined words | everyone |

**A place is both a target and a supply.** A piece put in one place often comes out of another, so a place says what it
takes, what it gives and where a piece goes next. Follow those and no piece is lost or made.

All nine files must be there. Each is one JSON object. Its fields are named, so there is no table of keys: a program asks
for `pieces.<id>.mass` or `limits.weight`, in every season. IDs start with a letter and use letters, digits and
underscores. An ID is used once in the folder.

## 2. Fields any record may have

| Field | Holds |
|---|---|
| `says` | The whole meaning in our own words: every condition, exception and measuring method. Numbers come from the fields: `{height}` is this record's, `{bale.mass}` another's |
| `code` | The manual's rule code, or a list. Codes change each season, so programs never use them |
| `src` | Where it is written: `"manual 3.2"`, or a list. The first word is an ID in `game.json` |
| `unknown` | A list: what a reader would look for and no source gives, and where sources disagree |
| `was` | A list of earlier values: `{"until": "2031-02-04", "is": "104 lb", "src": "update3 R7"}` |

## 3. Values

**A number is written as it is printed.**

| You write | It means |
|---|---|
| `"71 in"`, `"5 ft 4 3/8 in"`, `"1 min 50 s"`, `"17 deg"` | A quantity. Feet with inches, and minutes with seconds, may be joined |
| `"6.4 oz +/- 0.3"`, `"290 in +5 -1"` | With a tolerance, in the same unit |
| `"0.7 to 0.9 lb"` | A range: both ends are printed |
| `"at most 96 in"`, `"at least 3/8 in"`, `"less than 2 1/4 in"`, `"more than 7 s"`, `"at most 6"` | A limit, on a quantity or a count. The words say which way it goes |
| `45` | A count |
| `"= size.length / 2"` | Worked out. Names are `record.field`, and a list's parts are `.x`, `.y`, `.z`. A bare number has no unit, so only multiply or divide by it |
| `true`, `"plain words"` | A yes or no, or text |

Units that convert: `in ft mm cm m`, `lb oz kg g`, `s min`, `deg`. Others (`A V W psi AWG Ah USD lb/ft3`) are kept as
printed.

A value that needs more than the number is an object:

| You write | Use it when |
|---|---|
| `{"is": "37.5 in", "of": "across the flats"}` | The field's name does not say what is measured |
| `{"is": "44 in", "src": "drawings sheet 3"}` | It comes from a different source than the record |
| `{"is": "9 in", "assumed": "scaled from figure 5-2"}` | No source prints it |
| `{"by": "field", "welded": "612.40 in", "bolted": "611.75 in"}` | It depends on the kind of field, event or match (section 4) |

## 4. `game.json`

```json
{
  "name": "Hay Day", "season": 2031, "edition": "manual 4, 2031-03-14",
  "sources": {"manual": {"title": "Game manual", "edition": "4", "url": "https://..."}},
  "variants": {"field": ["welded", "bolted"], "event": ["regional", "championship"], "match": ["qualification", "playoff"]},
  "frame": {"origin": "blue wall, scoring table side, on the carpet", "x": "toward the red wall", "y": "away from the scoring table", "z": "up"}
}
```

A value written `by` a variant gives one answer for each name of it. A question that does not name one gets the first.

## 5. Both alliances from one record

`"alliance": "each"` means that blue and red each have one. Write blue's. Red's is made by `symmetry` in `field.json`:

| Symmetry | Point (x, y) becomes | Direction a becomes |
|---|---|---|
| `mirror` | (length - x, y) | 180 - a |
| `turn` | (length - x, width - y) | a + 180 |

A record may have its own `"symmetry"`, when that one thing is different. `mirror` also swaps left and right in an
outline that is not the same on both sides; `turn` does not.

- A place that belongs to an alliance but stands at the other end is still written as blue's, where blue's stands.
- In a position, `stall.at.x` means the same alliance's stall. To name one from outside, write `stall@red`.
- In rules, write `my` and `their`. **They are always seen from the robot that acts,** so they never change color.

**Several of one thing.** `spots` names each: `{"near": {"at": [...]}, "far": {"at": [...]}}`. Or a pattern:
`{"row": 4, "step": ["0 in", "48 in"], "first": {...}}`, `{"ring": 6, "around": [x, y], "step": "60 deg", "first": {...}}`.
A pattern's spots are numbered from 1, or named by `"names"`.

## 6. `clock.json`

```json
{
  "periods": {"auto": {"lasts": "12 s", "control": "none"}, "gap": {"lasts": "2 s"}, "teleop": {"lasts": "1 min 50 s", "control": "drivers"}},
  "windows": {"endgame": {"in": "teleop", "last": "25 s"}, "early": {"in": "teleop", "first": "35 s"}, "market": {"in": "teleop", "timer": ["1:15", "0:50"]}},
  "states": {
    "lit": {"of": "alliance", "starts": "a person presses the lamp", "needs": [["my lamp", "at least", 3]], "lasts": "9 s", "or until": "5 bales go in", "grace": "2 s"},
    "barn_open": {"of": "alliance", "true": [["auto"], ["market", "not lit"], ["endgame"]]}
  }
}
```

A window says its `first`, its `last` or its `timer` (as the match timer counts down). Windows may overlap. A state
belongs to an `alliance`, a `robot`, a `piece`, a `place` or the `match`.

**`when`** is used everywhere. It is a list of names of periods, windows, states and variants that must all be true:
`["teleop", "lit"]`, `["not endgame"]`, `["their lit"]`. A state with no word in front is mine. A state's `true` is a list
of `when` lists, and any one is enough.

## 7. `field.json`

```json
{
  "size": {"length": "612 in", "width": "300 in"}, "symmetry": "turn",
  "zones": {"yard": {"alliance": "each", "outline": [["0 in", "0 in"], ["54 in", "0 in"], ["54 in", "21 in"], ["0 in", "21 in"]], "edge": "the tape is inside", "height": "no limit"}},
  "lines": {"centre": {"from": ["= size.length / 2", "0 in"], "to": ["= size.length / 2", "= size.width"]}},
  "solids": {"crate": {"alliance": "each", "at": ["131 in", "150 in", "0 in"], "shape": {"box": ["22 in", "55 in", "15 in"]}}},
  "passages": {"arch": {"alliance": "each", "kind": "under", "width": "44 in", "height": "26 3/4 in"}},
  "hangs": {"bar": {"alliance": "each", "kind": "bar", "height": {"is": "33 in", "of": "floor to its centre"}, "diameter": "1 1/2 in", "width": "29 1/2 in"}},
  "tags": {"family": "36h11", "size": "7 in", "places": {"t1": ["480 in", "12 in", "40 in", "135 deg"]}}
}
```

- `at` is `[x, y]` or `[x, y, z]`; `faces` is a direction in plan: 0 deg is +X, 90 deg is +Y, anticlockwise from above.
- A box is `[along faces, across, up]`, centred on `at` in plan and standing on it. Other shapes: `cylinder`
  `{diameter, length, axis}`, `ball` `{diameter}`, `ring` `{inside, outside, thick}`, `tube` `{inside, outside, length}`,
  `prism` `{outline, tall}`, and `join` or `cut`: lists of shapes, each with its own `at`.
- `passages` are `under` (a height), `over` (a rise and a slope) or `between` (a width).
- `hangs` are `bar`, `chain`, `frame`, `post` or `ledge`. `may touch` and `may not touch` list what a robot may use.

## 8. `pieces.json`

```json
{"bale": {"shape": {"tube": {"inside": "3 in", "outside": "5 in", "length": "9 1/4 in"}}, "mass": "0.7 to 0.9 lb", "counts if": "it still looks about like a bale"}}
```

## 9. `places.json`

| Field | Holds |
|---|---|
| `at`, `faces`, `spots` | Where it is |
| `starts` | What is there when the match starts: `{"bale": 17}`. `"left over"` is what the other places do not use |
| `holds` | The most it can hold |
| `opening` | A hole: `outline` (`circle` with a diameter, `rectangle` `[width, height]`, `hexagon` `{"flats", "points"}`: across the flats, and the direction a point looks), `slope` (0 deg is flat, 90 deg is upright), `from` (`front`, `above` or `below`: the side pieces come from), `bottom` and `top` (carpet to its lowest and highest edge), `depth`, `lip` |
| `post` | A rod that goes through a piece: `tip` (carpet to the top), `slope`, `diameter`, `length`. A slope of 90 deg stands upright |
| `surface` | Something to rest on: `edge` (carpet to the edge), `size`, `slope` |
| `slide` | The slope of a slide behind an opening that people feed pieces down |
| `takes` | A list: `piece`, `by` (`robot`, `human`), `how` (`enter`, `rest`, `surround`), `counts` (what must be true), `score` (an ID in `scoring.json`), `most` |
| `gives` | A list: `piece`, `by` (`human`, `field`), `to` (a place, a zone, `floor` or `robot`), `how` |
| `then` | Where a piece goes when it has been taken |

## 10. `scoring.json`

```json
{
  "awards": {
    "bale_in_barn": {"per": "piece", "points": [{"when": ["auto"], "points": 7}, {"when": ["teleop"], "points": 3}, {"when": ["teleop", "lit"], "points": 6}]},
    "park": {"per": "robot", "points": [{"when": ["teleop"], "points": 4}], "needs": [["my bumpers", "partly in", "my yard"]], "unless": ["hang"], "judged": "4 s after the end, or when all robots rest"},
    "loft_rp": {"per": "match", "rp": 1, "when": ["qualification"], "needs": [["my loft points", "at least", 12], ["my hanging robots", "at least", 2]]}
  },
  "fouls": {"minor": {"points to them": 3}}
}
```

Of the rows that are true, the one with the most words in `when` counts; two that tie are refused. A row that is true at
no time scores nothing. `most` is a cap: `{"each": "barn", "is": 1}`. `needs` are conditions
(section 11). `unless` names awards that cancel this one.

## 11. Conditions

A condition is three things in a row: `[who, how, what]`. It reads as English, and only these words are used.

| | Words |
|---|---|
| **Who** | `my robot`, `my bumpers`, `their robot`, `their bumpers`, `either robot`, `either bumpers`, `my alliance`, `the piece`, `my <place>` or `their <place>` (the pieces in it), or something counted, such as `my hanging robots` |
| **How** | `partly in`, `fully in`, `fully outside`, `past` (completely over a line), `over` (any part over it), `above`, `touching`, `not touching`, `touching only`, `at least`, `at most`, `exactly`, `is`, `is not` |
| **What** | `my <id>`, `their <id>`, `any <id>`, a list, a number, a state |

`partly in` is true when any part is in, and so also when all of it is. A list of conditions must all be true.
`{"any": [...]}` needs one of them.

## 12. `conduct.json`

Keyed by rule code.

```json
{
  "G90": {
    "says": "A robot may not touch an opponent when either robot's bumpers are partly in the opponent's yard in the last {endgame.last}, whoever starts it.",
    "act": "touch", "what": "their robot", "also": ["through a piece that either robot holds"], "whoever starts it": true,
    "must not": [["either bumpers", "partly in", "their yard"]], "when": ["endgame"],
    "cost": ["major", {"give": "loft_rp", "to": "their alliance", "when": ["qualification"]}]
  }
}
```

| Field | Holds |
|---|---|
| `who` | `robot` (if left out), `human`, `drive team`, `team`, `alliance` |
| `act` | `touch`, `launch`, `place`, `hold`, `enter`, `cross`, `reach`, `grab`, `pin`, `block`, `damage`, `eject`, `unscore`, `catch`, `feed`, `store`, `hang`, `behave` |
| `what`, `into`, `from` | What it is done to, where it goes, where it comes from |
| `must not` | `true`, or the conditions that make it wrong |
| `only if` | The conditions that make it right |
| `limit` | The most allowed: a number, or a number for each piece |
| `when` | The times it applies; always, if left out |
| `unless` | Exceptions, as conditions or words |
| `cost` | A list of foul IDs, or objects: `give`, `each` (per what), `to`, `if` (`repeated`, `strategic`, `robot cannot drive`, or words), `every` (a time), `when` |

A rule that only people judge has `"act": "behave"`, `says` and `cost`.

## 13. `robot.json`

`limits` has the same names every season. A season with no such rule leaves the name out, and a program reads that as no
limit. Each has a `code`.

| Name | Holds |
|---|---|
| `perimeter` | `size` (string around it), `bump` (how far a bolt head may stick out) |
| `start` | `height`, `overhang` |
| `height` | `max`, and how it is measured |
| `reach` | `far` (beyond the perimeter), `sides` (how many at once) |
| `weight` | Named limits: `{"robot": {"max": "at most 105 lb", "without": ["bumpers", "battery"]}}` |
| `hold`, `preload` | The most pieces, by piece |
| `bumpers` | `zone` (low and high), `out` (how far from the perimeter), `hard` (how far hard parts stick out), `padding`, `backing`, `gap`, `corner`, `tolerance`, `cover`, `numbers`, `fixing` |
| `drive` | `motors` (how many may drive it) |
| `power` | `battery`, `main breaker`, `branch`, `wire`, `fuses` |
| `motors`, `controllers` | Lists: name and part numbers, and what each controller may run |
| `air` | Pressures, the compressor, required parts |
| `price`, `console`, `radio`, `computer` | As named |

`rules` holds every other construction and inspection rule, keyed by code, with `says` and any values.

## 14. `terms.json`

```json
{"momentary": {"says": "Less than about {lasts}.", "lasts": "4 s"}}
```
