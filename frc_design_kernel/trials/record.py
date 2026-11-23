"""The method around a trial, as plain data: was the criterion met, what the control showed, ranges, step comparison.

Nothing here runs physics. It reads run summaries and states what they show. A trial is only reported as passed when
its method is complete and nothing inside an assumed range changes the outcome.
"""

WORDS = ("incomplete", "failed", "control not rejected", "not converged", "flips in range", "passed")


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


def step_comparison(coarse, fine, coarse_met, fine_met):
    """How the nominal run compares with the same run at half the step."""
    measures = {name: [coarse["measures"][name], fine["measures"][name]] for name in coarse["measures"]}
    same = coarse["outcome"] == fine["outcome"] and coarse_met == fine_met
    return {"coarseS": coarse["stepS"], "fineS": fine["stepS"], "coarseOutcome": coarse["outcome"], "fineOutcome": fine["outcome"],
            "sameOutcome": same, "measures": measures, "converged": same}


def sensitivity(brackets, nominal_measures):
    """Inputs ranked by how much they move the outcome, from the one-at-a-time runs: which measurement would narrow the result most.

    An input that changes the outcome ranks above any that does not. After that, inputs rank by the largest change they
    cause in any measure, as a fraction of that measure's nominal value.
    """
    ranked = []
    for found in brackets:
        largest = {"measure": None, "relativeChange": 0.0}
        for name, nominal in nominal_measures.items():
            seen = [row["measures"].get(name) for row in found["values"]] + [nominal]
            seen = [v for v in seen if isinstance(v, (int, float))]
            if len(seen) < 2 or not isinstance(nominal, (int, float)):
                continue
            change = (max(seen) - min(seen)) / max(abs(nominal), 1e-9)
            if change > largest["relativeChange"]:
                largest = {"measure": name, "relativeChange": change, "lowest": min(seen), "highest": max(seen)}
        ranked.append({"input": found["input"], "changesOutcome": not found["held"], "largestChange": largest})
    return sorted(ranked, key=lambda row: (not row["changesOutcome"], -row["largestChange"]["relativeChange"], row["input"]))


def result(nominal_met, control, brackets, steps, missing, grid=None):
    """(result word, findings) for a trial.

    missing lists what the method lacks (no control, no stated assumptions, inputs with no stated source, nothing
    bracketed). Any of those makes the trial incomplete whatever its runs showed.
    """
    if missing:
        return "incomplete", list(missing)
    findings = []
    if not nominal_met:
        return "failed", findings
    if not control["rejected"]:
        return "control not rejected", ["the control met the criterion, so the trial does not show what it claims"]
    if not steps["converged"]:
        return "not converged", ["the outcome changes when the step is halved, so the step is too large to trust"]
    for found in brackets:
        for flip in found["flips"]:
            where = "its assumed range" if found["source"] == "assumed" else "its listed values"
            findings.append(f'the outcome changes inside {where} of "{found["input"]}": it holds at {flip["holdsAt"]:g} and changes at {flip["changesAt"]:g}')
    if grid and not grid["allMet"]:
        findings.append("the outcome changes at a combination of range ends, though no single input changes it alone")
    flips = any(found["flips"] and found["source"] == "assumed" for found in brackets) or bool(grid and not grid["allMet"])
    return ("flips in range" if flips else "passed"), findings


def hand_forward(inputs, brackets, ranking, control, assumptions):
    """What a later, fuller engine needs from this trial: the nominal settings, where it held, where it is marginal, what to keep."""
    passing, edges = {}, []
    for found in brackets:
        held = [row["value"] for row in found["values"] if row["met"]] + [found["nominal"]]
        passing[found["input"]] = [min(held), max(held)]
        edges += [{"input": found["input"], **flip} for flip in found["flips"]]
    return {"nominal": {row["path"]: row["value"] for row in inputs}, "passingRanges": passing, "marginalEdges": edges,
            "sensitivity": [row["input"] for row in ranking], "control": control and control["change"],
            "assumptionIds": [row["id"] for row in assumptions if "id" in row]}
