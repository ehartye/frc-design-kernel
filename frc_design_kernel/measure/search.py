"""The adaptive search that proves nothing was missed between samples.

A value (a gap) is sampled at stroke fractions. Between two fractions lo and hi, sampled at their midpoint, the value
cannot fall more than speed * (hi - lo) / 2 below the sample, because no point moves faster than speed per unit of
t. If that floor is still above the threshold, the whole interval is settled. If not, the interval is halved and
both halves are sampled, down to a depth limit. This replaces "how finely did you split it" with a proof.
"""
import math

DEFAULT_DEPTH = 9
MAX_DEPTH = 18


def search(value_at, speed, threshold, depth=DEFAULT_DEPTH, window=(0.0, 1.0), hit=None, inclusive=False):
    """Search a window of the stroke for a value at or below a threshold.

    value_at(t) gives the value at fraction t. hit(t, value) says whether that sample is a finding (default: the
    value is below the threshold). The search stops at the first finding.

    Returns {"hit": (t, value) or None, "unresolved": [lo, hi] or None, "floor": the proven lowest the value can
    be when there is no hit and nothing unresolved (math.inf if the ends alone settled it), "lowest": (t, value)
    of the smallest sample, "samples": how many fractions were sampled}.
    """
    if not (isinstance(depth, int) and 0 <= depth <= MAX_DEPTH):
        raise ValueError(f"the depth limit must be a whole number from 0 to {MAX_DEPTH}")
    hit = hit or (lambda t, value: value < threshold)
    seen = {}

    def sample(t):
        if t not in seen:
            seen[t] = value_at(t)
        return seen[t]

    def result(found=None, unresolved=None, floor=math.inf):
        lowest = min(seen.items(), key=lambda item: (item[1], item[0]))
        return {"hit": found, "unresolved": unresolved, "floor": floor, "lowest": lowest, "samples": len(seen)}

    low, high = window
    for t in (low, high):
        if hit(t, sample(t)):
            return result((t, seen[t]))
    pending, unresolved, floor = [(low, high, 0)], None, math.inf
    while pending:
        lo, hi, level = pending.pop()
        mid = (lo + hi) / 2
        value = sample(mid)
        if hit(mid, value):
            return result((mid, value))
        lower = value - speed * (hi - lo) / 2
        if lower > threshold or (inclusive and lower >= threshold):
            floor = min(floor, lower)
        elif level == depth:
            unresolved = unresolved or [lo, hi]
        else:
            pending.extend([(mid, hi, level + 1), (lo, mid, level + 1)])
    return result(None, unresolved, floor)
