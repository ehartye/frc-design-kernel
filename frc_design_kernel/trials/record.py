"""The method around a trial, as plain data: was the criterion met, what the control showed, brackets, step comparison.

Nothing here runs physics. It reads run summaries and states what they show. A trial is only reported as passed when
its method is complete: a control that was rejected, brackets, and a half-step repeat that agrees.
"""


def judge(run, criterion, custom=None):
    """(met, first thing not met) for one run against the trial's pass criterion.

    criterion: {"outcomes": [texts], "limits": [{"measure": name, "atMost": n, "atLeast": n}], "custom": {...}}.
    custom is a callable (run, parameters) -> bool for a registered custom criterion, with its parameters.
    """
    if "outcomes" in criterion and run["outcome"] not in criterion["outcomes"]:
        return False, f'outcome was "{run["outcome"]}"'
    for limit in criterion.get("limits", []):
        value = run["measures"].get(limit["measure"])
        if value is None:
            return False, f'{limit["measure"]} has no value'
        if "atMost" in limit and value > limit["atMost"]:
            return False, f'{limit["measure"]} {value:.6g} is above {limit["atMost"]:g}'
        if "atLeast" in limit and value < limit["atLeast"]:
            return False, f'{limit["measure"]} {value:.6g} is below {limit["atLeast"]:g}'
    if custom is not None:
        law, parameters = custom
        summary = {key: run[key] for key in ("outcome", "endS", "events", "measures", "end")}
        if not law(summary, parameters):
            return False, "the custom criterion was not met"
    return True, None


def bracket(entry, nominal, rows):
    """One input's bracket: the passing value nearest a failing one, and the failing value nearest the nominal.

    rows are [{"value": v, "passed": bool, "outcome": text, "run": id}], the nominal value included.
    """
    good = [r for r in rows if r["passed"]]
    bad = [r for r in rows if not r["passed"]]
    failing = min(bad, key=lambda r: abs(r["value"] - nominal))["value"] if bad else None
    passing = min(good, key=lambda r: abs(r["value"] - (failing if failing is not None else nominal)))["value"] if good else None
    return {"input": entry["input"], "unit": entry.get("unit", ""), "nominal": nominal, "values": rows,
            "passing": passing, "failing": failing, "bracketed": passing is not None and failing is not None}


def step_comparison(coarse, fine, coarse_met, fine_met):
    """How the nominal run compares with the same run at half the step."""
    measures = {name: [coarse["measures"][name], fine["measures"][name]] for name in coarse["measures"]}
    same = coarse["outcome"] == fine["outcome"] and coarse_met == fine_met
    return {"coarseS": coarse["stepS"], "fineS": fine["stepS"], "coarseOutcome": coarse["outcome"], "fineOutcome": fine["outcome"],
            "sameOutcome": same, "measures": measures, "converged": same}


def result(nominal_met, control, brackets, steps):
    """(result word, findings) for a trial. The words: incomplete, failed, control not rejected, not converged, passed."""
    findings = []
    if control is None:
        findings.append("no control is defined, so nothing shows the trial can fail")
    if not brackets:
        findings.append("no brackets are defined, so nothing shows how far the inputs can move")
    if findings:
        return "incomplete", findings
    findings += [f'input "{b["input"]}" has no failing value in its range' for b in brackets if b["failing"] is None]
    findings += [f'input "{b["input"]}" has no passing value in its range' for b in brackets if b["passing"] is None]
    if not nominal_met:
        return "failed", findings
    if not control["rejected"]:
        return "control not rejected", findings + ["the control met the criterion, so the trial does not show what it claims"]
    if not steps["converged"]:
        return "not converged", findings + ["the outcome changes when the step is halved, so the step is too large to trust"]
    return "passed", findings
