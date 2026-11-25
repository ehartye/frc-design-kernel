"""How many of each piece there are where, at the start of a match.

    starts(worker, piece)             {"stall@blue": 20, "stall@red": 20, "centre_bales": 6}, for every place that has some
    left_over(worker, entry, piece)   what one alliance's record has of what the other places do not use
    count(worker, entry, piece)       what one alliance's record has, all its spots together

What is left over is the total less everything that other places start with, half for each alliance when the place is for
each. More pieces than there are, or a part of one, is a DesignError.
"""
from ..errors import DesignError
from .alliances import spots
from .read import word_list
from .worth import one_number


def placed(worker, piece):
    """Every place that starts with some of a piece."""
    return [entry for entry in worker.book.of_kind("place").values() if isinstance(entry.data.get("starts"), dict) and piece in entry.data["starts"]]


def sides(entry):
    """How many alliances have this place: each of them, or neither (one)."""
    return 2 if entry.data.get("alliance") == "each" else 1


def is_left_over(worker, entry, piece):
    node = worker.unwrap(entry.data["starts"][piece])[0]
    return isinstance(node, str) and node in word_list("starts")


def count(worker, entry, piece):
    """How many the record of one alliance has, or the one record when neither owns it: all its spots together."""
    if is_left_over(worker, entry, piece):
        return left_over(worker, entry, piece)
    node, about = worker.unwrap(entry.data["starts"][piece])
    number, each, many = one_number(worker.value(node, entry, "number")), about.get("each"), len(spots(entry))
    if each == "spot" and many:
        return number * many
    if each == "alliance":
        return number * (2 // sides(entry))
    if each:
        why = "is for each spot, and it has none" if each == "spot" else f'is for each "{each}", and a count at the start may be for each spot or each alliance'
        raise DesignError(f"{entry.where}.starts.{piece}", why, 'Write the number for one alliance, all its spots together, or {"each": "spot", "is": 1}, or {"each": "alliance", "is": 4}')
    return number


def left_over(worker, entry, piece):
    """What the record of one alliance has of what the other places do not use."""
    where = f"{entry.where}.starts.{piece}"
    if piece not in worker.book.data["scoring"].get("total", {}):
        raise DesignError(where, f"is left over, and there is no total of {piece}", "Give the total in scoring.json")
    if len(several := [one for one in placed(worker, piece) if is_left_over(worker, one, piece)]) > 1:
        raise DesignError(f"{several[1].where}.starts.{piece}", f"is left over, and so is that of {several[0].id}", "Write how many there are in one of them")
    worker.begin(f"left over {piece}")
    try:
        total = one_number(worker.get(f"total.{piece}"))
        used = sum(count(worker, other, piece) * sides(other) for other in placed(worker, piece) if other is not entry)
    finally:
        worker.doing.pop()
    share = (total - used) / sides(entry)
    if share < 0 or share != int(share):
        half = " for each alliance" if sides(entry) == 2 else ""
        raise DesignError(where, f"is what is left over of {total:g}: {used:g} start elsewhere, which leaves {share:g}{half}", "Check the total, and what the other places start with")
    return int(share)


def starts(worker, piece):
    """{record: how many of a piece it has at the start}, for each place and each alliance."""
    found = {}
    for entry in placed(worker, piece):
        many = count(worker, entry, piece)
        for name in ([f"{entry.id}@blue", f"{entry.id}@red"] if sides(entry) == 2 else [entry.id]):
            found[name] = many
    return found


def check(worker, piece):
    """A DesignError when places start with more of a piece than there are."""
    staged = sum(starts(worker, piece).values())
    total = worker.book.data["scoring"].get("total", {})
    if piece in total and staged > (there := one_number(worker.get(f"total.{piece}"))):
        raise DesignError(f"scoring.json total.{piece}", f"is {there:g}, and {staged:g} start on the field", "Check the total, and what each place starts with")
