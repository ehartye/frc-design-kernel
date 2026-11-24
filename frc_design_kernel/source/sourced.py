"""A physical input's number and the range it may lie in.

An input is a plain number, `{"value": v, "measured": "where"}` or `{"value": v, "assumed": [low, high]}`. A plain
number and a measured value are exact: both ends of the range are the value. Only an assumed value widens it.
"""


def span(item):
    """(value, low, high) of a plain or sourced number."""
    if isinstance(item, dict):
        value = float(item["value"])
        low, high = item.get("assumed", (value, value))
        return value, float(low), float(high)
    return float(item), float(item), float(item)
