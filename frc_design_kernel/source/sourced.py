"""A physical input's number and the range it may lie in.

An input is a plain number, `{"value": v, "measured": "where"}` or `{"value": v, "assumed": [low, high]}`. A plain
number and a measured value are exact: both ends of the range are the value. Only an assumed value widens it.
"""
from ..errors import DesignError


def span(item):
    """(value, low, high) of a plain or sourced number."""
    if isinstance(item, dict):
        value = float(item["value"])
        low, high = item.get("assumed", (value, value))
        return value, float(low), float(high)
    return float(item), float(item), float(item)


def check_sourced(value, where):
    """A physical input that states its source must state exactly one, and an assumed range must hold its value."""
    if isinstance(value, dict) and "value" in value:
        if ("measured" in value) == ("assumed" in value):
            raise DesignError(where, 'needs exactly one of "measured" or "assumed"', 'Say where it was measured, or give the range it is believed to lie in')
        if "assumed" in value and not value["assumed"][0] <= value["value"] <= value["assumed"][1]:
            raise DesignError(where, f'its value {value["value"]:g} is outside its assumed range {value["assumed"]}', "Give the range as [low, high] around the value")
    elif isinstance(value, dict):
        for key, item in value.items():
            check_sourced(item, f"{where}.{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            check_sourced(item, f"{where}[{i}]")
