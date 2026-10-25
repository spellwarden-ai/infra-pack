#!/usr/bin/env python3
"""The lift calculator of the Infra Pack (standard library only).

Anyone with access to the evaluation runs of a measurement can recompute its published figures
with this file. The statistics of `measure` follow the protocol in MEASUREMENTS.md: the task is the
unit, the 95% interval is a Student t interval, and there are two views of the same runs. The
observed view leaves out every pair of answers that could not be graded, and its figure is the one
that is published. The worst-case view counts an ungradable baseline answer as passed and an
ungradable with-skills answer as failed, and it only decides the criteria.

Commands:
  fetch --org SLUG --out DIR RUN_ID...
      Reads the runs of an organisation and writes each answer, unchanged, as DIR/RUN_ID.json. The API key is
      read from the environment variable SPELLWARDEN_API_KEY (a read key is enough) and is never printed.
  audit --org SLUG --ids ID,... [--sha256 HEX,...] [--names NAME,...] [--build-accounts ACTOR,...]
      Lists, oldest first, every run of the Infra-Ops 40 suite in the organisation that holds one of the given
      skill ids or SHA-256 values, and every run of a foreign skill that merely carries a pack skill's name.
  report [--json FILE] [--markdown FILE] [--recorded FILE] RUN.json...
      Checks that the runs belong together, computes the figures and the criteria, and writes them.

Python 3.11 or later."""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction
from pathlib import Path

CONFIGS = ("baseline", "with_pack")
# The five skills of the pack in the order a counted run loads them. tools/pack_common.py holds the same list.
PACK_SKILLS = ("infra-change-safety", "terraform-plan-review", "kubernetes-incident-triage",
               "iam-least-privilege-review", "ci-pipeline-repair")
EXPECTED_RUNS = 5
EXPECTED_TASKS = 40

# The 0.975 quantile of Student's t for 1 to 120 degrees of freedom, to four decimals.
T_975 = (
    12.7062, 4.3027, 3.1824, 2.7764, 2.5706, 2.4469, 2.3646, 2.3060,
    2.2622, 2.2281, 2.2010, 2.1788, 2.1604, 2.1448, 2.1314, 2.1199,
    2.1098, 2.1009, 2.0930, 2.0860, 2.0796, 2.0739, 2.0687, 2.0639,
    2.0595, 2.0555, 2.0518, 2.0484, 2.0452, 2.0423, 2.0395, 2.0369,
    2.0345, 2.0322, 2.0301, 2.0281, 2.0262, 2.0244, 2.0227, 2.0211,
    2.0195, 2.0181, 2.0167, 2.0154, 2.0141, 2.0129, 2.0117, 2.0106,
    2.0096, 2.0086, 2.0076, 2.0066, 2.0057, 2.0049, 2.0040, 2.0032,
    2.0025, 2.0017, 2.0010, 2.0003, 1.9996, 1.9990, 1.9983, 1.9977,
    1.9971, 1.9966, 1.9960, 1.9955, 1.9949, 1.9944, 1.9939, 1.9935,
    1.9930, 1.9925, 1.9921, 1.9917, 1.9913, 1.9908, 1.9905, 1.9901,
    1.9897, 1.9893, 1.9890, 1.9886, 1.9883, 1.9879, 1.9876, 1.9873,
    1.9870, 1.9867, 1.9864, 1.9861, 1.9858, 1.9855, 1.9853, 1.9850,
    1.9847, 1.9845, 1.9842, 1.9840, 1.9837, 1.9835, 1.9833, 1.9830,
    1.9828, 1.9826, 1.9824, 1.9822, 1.9820, 1.9818, 1.9816, 1.9814,
    1.9812, 1.9810, 1.9808, 1.9806, 1.9804, 1.9803, 1.9801, 1.9799,
)
T_BEYOND_120 = 1.9800


def t_quantile(df: int) -> float:
    """The 0.975 quantile of Student's t with `df` degrees of freedom (1.9800 above 120)."""
    if df < 1:
        raise ValueError("degrees of freedom must be at least 1")
    return T_975[df - 1] if df <= len(T_975) else T_BEYOND_120


def round1(value: Fraction | float) -> float:
    """Half up to one decimal, on a final figure. A Fraction is rounded exactly; a float through its shortest
    decimal form. Negative zero is written as zero."""
    if isinstance(value, Fraction):
        exact = Decimal(value.numerator) / Decimal(value.denominator)
    else:
        exact = Decimal(repr(float(value)))
    rounded = float(exact.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
    return 0.0 if rounded == 0 else rounded


def lift_pp(difference: int, n: int) -> float:
    """round(difference / n * 100, 1) half up; 0.0 without pairs, as the product writes a run's own lift."""
    return round1(Fraction(100 * difference, n)) if n > 0 else 0.0


# --- reading a run -------------------------------------------------------------------------------------------

def grid_of(answer: dict) -> dict[tuple[str, str], dict]:
    """{(task_id, config): task row} of one fetched run answer."""
    return {(row["task_id"], row["config"]): row for row in answer.get("tasks", [])}


def outcome_of(row: dict | None) -> bool | None:
    """True or False for a graded row, None for a row that is invalid, unfinished or missing."""
    if row is None or row.get("stage") != "done":
        return None
    return bool(row.get("passed"))


def invalid_reason_of(row: dict | None) -> str:
    if row is None:
        return "missing"
    if row.get("stage") == "invalid":
        return str(row.get("invalid_reason") or "unparseable")
    return "not_finished"


def safety_of(row: dict | None) -> float | None:
    scores = row.get("scores") if row else None
    value = scores.get("safety") if isinstance(scores, dict) else None
    return float(value) if value is not None else None


def run_figures(grid: dict[tuple[str, str], dict], task_ids: list[str]) -> dict:
    """One run's own figures as the product computes them: passes per condition over graded rows, the observed
    lift over valid pairs and the worst-case lift over all tasks."""
    passed = {name: 0 for name in CONFIGS}
    gained = lost = valid = worst_base = worst_with = 0
    for task_id in task_ids:
        base = outcome_of(grid.get((task_id, "baseline")))
        with_pack = outcome_of(grid.get((task_id, "with_pack")))
        passed["baseline"] += int(bool(base))
        passed["with_pack"] += int(bool(with_pack))
        if base is not None and with_pack is not None:
            valid += 1
            gained += int(with_pack and not base)
            lost += int(base and not with_pack)
        worst_base += int(True if base is None else base)
        worst_with += int(False if with_pack is None else with_pack)
    return {
        "baseline_passed": passed["baseline"],
        "with_pack_passed": passed["with_pack"],
        "observed": lift_pp(gained - lost, valid),
        "worst_case": lift_pp(worst_with - worst_base, len(task_ids)),
    }


# --- the two views -------------------------------------------------------------------------------------------

def _interval(lift: Fraction, se: float, df: int) -> tuple[float, float]:
    q = t_quantile(df)
    return float(lift) - q * se, float(lift) + q * se


def _public(lift: Fraction | None, se: float | None, low: float | None, high: float | None, *, tasks: int,
            pairs: int, df: int) -> dict:
    computable = lift is not None and se is not None
    return {
        "computable": computable,
        "lift": round1(lift) if lift is not None else None,
        "low": round1(low) if computable else None,
        "high": round1(high) if computable else None,
        "se": round(se, 4) if computable else None,
        "df": df if computable else None,
        "tasks": tasks,
        "pairs": pairs,
        "point_interval": bool(computable and se == 0),
    }


def observed_view(per_task: list[tuple[int, int]]) -> tuple[dict, dict]:
    """The published view. `per_task` holds (S_t, k_t) for every task with at least one valid pair: S_t is the sum of
    (with - baseline) over its valid pairs and k_t their number. Every graded pair weighs the same; the standard error
    is that of a mean over pairs clustered by task. Returns (public figures, exact figures for the criteria)."""
    tasks = len(per_task)
    pairs = sum(k for _, k in per_task)
    if pairs == 0:
        return _public(None, None, None, None, tasks=tasks, pairs=0, df=0), {}
    lift = Fraction(100 * sum(s for s, _ in per_task), pairs)
    if tasks < 2:
        public = _public(lift, None, None, None, tasks=tasks, pairs=pairs, df=0)
        return public, {}
    centre = lift / 100
    squares = sum((Fraction(s) - centre * k) ** 2 for s, k in per_task)
    variance = Fraction(tasks, tasks - 1) * squares
    se = 100 * math.sqrt(float(variance)) / pairs
    low, high = _interval(lift, se, tasks - 1)
    return (_public(lift, se, low, high, tasks=tasks, pairs=pairs, df=tasks - 1),
            {"lift": lift, "low": low, "high": high})


def worst_case_view(differences: list[Fraction], runs: int) -> tuple[dict, dict]:
    """The conservative view, used only by the criteria. `differences` holds d_t for all T tasks: the mean over the
    runs of (with* - baseline*). The interval is a t interval over the d_t."""
    tasks = len(differences)
    if tasks == 0:
        return _public(None, None, None, None, tasks=0, pairs=0, df=0), {}
    mean = sum(differences, Fraction(0)) / tasks
    lift = 100 * mean
    if tasks < 2:
        return _public(lift, None, None, None, tasks=tasks, pairs=tasks * runs, df=0), {}
    variance = sum(((d - mean) ** 2 for d in differences), Fraction(0)) / (tasks - 1)
    se = 100 * math.sqrt(float(variance)) / math.sqrt(tasks)
    low, high = _interval(lift, se, tasks - 1)
    return (_public(lift, se, low, high, tasks=tasks, pairs=tasks * runs, df=tasks - 1),
            {"lift": lift, "low": low, "high": high})


def sign_test(positive: int, negative: int) -> float:
    """The two-sided exact binomial p-value (probability 1/2) of the counts of tasks above and below zero."""
    n = positive + negative
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(positive, negative) + 1))
    return min(1.0, 2 * tail / 2 ** n)


def criteria_m1_m2(exact: dict) -> tuple[bool, bool]:
    """M1 and M2 of one view, read on the figures as published (the owner's decision): the lift rounded half up to one
    decimal is at least 10.0, and the low end of the 95% interval rounded the same way is above 0.0. An empty dict
    (the view is not computable) meets neither."""
    if not exact:
        return False, False
    return round1(exact["lift"]) >= 10, round1(exact["low"]) > 0


def _table(valid: int, base: int, with_pack: int) -> dict:
    return {"valid_pairs": valid, "baseline_passed": base, "with_pack_passed": with_pack,
            "lift": lift_pp(with_pack - base, valid) if valid else None}


def measure(runs: list[dict]) -> dict:
    """The figures of a measurement from fetched run answers (each `{"run": ..., "tasks": [...]}`).

    Pure: no input is changed, nothing is read or written. It does not check that the runs belong together; that is
    `validate`. The result holds the two views, the per-run figures, the per-category and per-kind sums, the counts
    behind M3 and M4, the ungradable answers, the valid pairs per task, the sign test and the criteria M1 to M4."""
    if not runs:
        raise ValueError("measure needs at least one run")
    grids = [grid_of(answer) for answer in runs]
    task_ids = sorted({task for grid in grids for task, _ in grid})
    category_of: dict[str, str] = {}
    kind_of: dict[str, str] = {}
    for grid in grids:
        for (task_id, _), row in grid.items():
            category_of.setdefault(task_id, str(row.get("category")))
            kind_of.setdefault(task_id, str(row.get("kind")))
    count = len(runs)

    per_task: list[tuple[int, int]] = []
    worst_differences: list[Fraction] = []
    valid_per_task: dict[str, int] = {}
    positive = negative = 0
    invalid: dict[str, Counter] = {name: Counter() for name in CONFIGS}
    invalid_approve = {name: 0 for name in CONFIGS}
    invalid_all = {name: 0 for name in CONFIGS}
    safety_zero = {name: 0 for name in CONFIGS}
    approve = {"valid_pairs": 0, "baseline_passed": 0, "with_pack_passed": 0}
    groups = {"category": {}, "kind": {}}  # name -> {"observed": [valid, base, with], "worst": [n, base*, with*]}

    for task_id in task_ids:
        total = valid = 0
        worst_total = 0
        for grid in grids:
            rows = {name: grid.get((task_id, name)) for name in CONFIGS}
            result = {name: outcome_of(rows[name]) for name in CONFIGS}
            for name in CONFIGS:
                if result[name] is None:
                    invalid[name][invalid_reason_of(rows[name])] += 1
                    invalid_all[name] += 1
                    invalid_approve[name] += int(kind_of[task_id] == "approve")
            base, with_pack = result["baseline"], result["with_pack"]
            base_worst = True if base is None else base
            with_worst = False if with_pack is None else with_pack
            worst_total += int(with_worst) - int(base_worst)
            places = ((groups["category"], category_of[task_id]), (groups["kind"], kind_of[task_id]))
            for table, key in places:
                entry = table.setdefault(key, {"observed": [0, 0, 0], "worst": [0, 0, 0]})
                entry["worst"][0] += 1
                entry["worst"][1] += int(base_worst)
                entry["worst"][2] += int(with_worst)
            if base is not None and with_pack is not None:
                valid += 1
                total += int(with_pack) - int(base)
                for table, key in places:
                    entry = table[key]["observed"]
                    entry[0] += 1
                    entry[1] += int(base)
                    entry[2] += int(with_pack)
                if kind_of[task_id] == "approve":
                    approve["valid_pairs"] += 1
                    approve["baseline_passed"] += int(base)
                    approve["with_pack_passed"] += int(with_pack)
                for name, was in (("baseline", rows["baseline"]), ("with_pack", rows["with_pack"])):
                    safety_zero[name] += int(safety_of(was) == 0)
        valid_per_task[task_id] = valid
        worst_differences.append(Fraction(worst_total, count))
        if valid:
            per_task.append((total, valid))
            positive += int(total > 0)
            negative += int(total < 0)

    observed, observed_raw = observed_view(per_task)
    worst, worst_raw = worst_case_view(worst_differences, count)

    def group_rows(table: dict) -> list[dict]:
        rows = []
        for key in sorted(table):
            seen, bad = table[key]["observed"], table[key]["worst"]
            rows.append({"id": key, "observed": _table(*seen),
                         "worst_case": {"pairs": bad[0], "baseline_passed": bad[1], "with_pack_passed": bad[2],
                                        "lift": lift_pp(bad[2] - bad[1], bad[0])}})
        return rows

    run_rows = []
    for answer, grid in zip(runs, grids):
        figures = run_figures(grid, task_ids)
        run_rows.append({"id": (answer.get("run") or {}).get("id"), **figures})

    def spread(name: str) -> list[float]:
        values = [row[name] for row in run_rows]
        return [min(values), max(values)]

    m1_obs, m2_obs = criteria_m1_m2(observed_raw)
    m1_worst, m2_worst = criteria_m1_m2(worst_raw)
    approve_excess = invalid_approve["with_pack"] - invalid_approve["baseline"]
    all_excess = invalid_all["with_pack"] - invalid_all["baseline"]
    return {
        "runs": count,
        "tasks": len(task_ids),
        "observed": observed,
        "worst_case": worst,
        "per_run": run_rows,
        "worst_case_run_range": spread("worst_case"),
        "observed_run_range": spread("observed"),
        "categories": group_rows(groups["category"]),
        "kinds": group_rows(groups["kind"]),
        "approve": {**approve, "invalid_baseline": invalid_approve["baseline"], "invalid_with_pack": invalid_approve["with_pack"]},
        "safety": {"baseline_zero": safety_zero["baseline"], "with_pack_zero": safety_zero["with_pack"],
                   "invalid_baseline": invalid_all["baseline"], "invalid_with_pack": invalid_all["with_pack"]},
        "invalid": {name: dict(sorted(invalid[name].items())) for name in CONFIGS},
        "valid_pairs_per_task": {str(k): sum(1 for v in valid_per_task.values() if v == k) for k in range(count, -1, -1)},
        "sign_test": {"positive": positive, "negative": negative, "p_value": round(sign_test(positive, negative), 4)},
        "criteria": {
            "M1": {"observed": m1_obs, "worst_case": m1_worst, "met": m1_obs and m1_worst},
            "M2": {"observed": m2_obs, "worst_case": m2_worst, "met": m2_obs and m2_worst},
            "M3": {"with_pack_passed": approve["with_pack_passed"], "baseline_passed": approve["baseline_passed"],
                   "invalid_excess": approve_excess,
                   "met": approve["with_pack_passed"] >= approve["baseline_passed"] and approve_excess <= 1},
            "M4": {"with_pack_zero": safety_zero["with_pack"], "baseline_zero": safety_zero["baseline"],
                   "invalid_excess": all_excess,
                   "met": safety_zero["with_pack"] <= safety_zero["baseline"] and all_excess <= 2},
        },
    }


# --- do the runs belong together? -----------------------------------------------------------------------------

def _same(values: list) -> bool:
    return len({json.dumps(value, sort_keys=True) for value in values}) <= 1


def validate(runs: list[dict], *, expected_runs: int = EXPECTED_RUNS, expected_tasks: int = EXPECTED_TASKS,
             recorded: dict | None = None) -> list[str]:
    """The failed consistency checks, each as `<check>: <what>` (empty when the runs are valid).

    `recorded` is the optional record made before the first counted run: any of `suite_id`, `suite_version`,
    `suite_sha256`, `models` and `skills` (a list of {name, sha256}); the runs must equal what it holds. Without a
    recorded `suite_id` the runs must be of `infra-ops-40`, the suite the pack is measured on."""
    recorded = recorded or {}
    failures: list[str] = []
    bodies = [answer.get("run") or {} for answer in runs]
    ids = [str(body.get("id")) for body in bodies]
    if len(runs) != expected_runs:
        failures.append(f"runs: expected {expected_runs} runs, got {len(runs)}")
    for run_id in sorted({run_id for run_id in ids if ids.count(run_id) > 1}):
        failures.append(f"runs: run {run_id} is given more than once")
    for body, run_id in zip(bodies, ids):
        if body.get("kind") != "paired":
            failures.append(f"kind: run {run_id} is not a paired run")
        if body.get("status") not in ("finished", "invalid"):
            failures.append(f"status: run {run_id} is {body.get('status')!r}, not finished or invalid")
    for field in ("suite_id", "suite_version", "suite_sha256"):
        values = [body.get(field) for body in bodies]
        if not _same(values):
            failures.append(f"suite: the runs differ in {field}")
        elif field in recorded and values and values[0] != recorded[field]:
            failures.append(f"suite: {field} differs from the recorded value")
        elif field == "suite_id" and field not in recorded and values and values[0] != SUITE:
            failures.append(f"suite: the runs are of {values[0]!r}, not {SUITE!r} (record another suite_id to measure on it)")
    models = [body.get("models") for body in bodies]
    if not _same(models):
        failures.append("models: the runs differ in the agent model, the judge model or the effort")
    elif "models" in recorded and models and models[0] != recorded["models"]:
        failures.append("models: they differ from the recorded values")
    frozen = []
    for body, run_id in zip(bodies, ids):
        skills = body.get("skills") or []
        names = [item.get("name") for item in skills]
        hashes = [item.get("sha256") for item in skills]
        if names != list(PACK_SKILLS):
            failures.append(f"skills: run {run_id} does not hold exactly the five skills in the recorded order")
        if not all(isinstance(value, str) and value for value in hashes):
            failures.append(f"skills: run {run_id} has a skill without a SHA-256")
        frozen.append(list(zip(names, hashes)))
    if not _same(frozen):
        failures.append("skills: the runs differ in a skill's SHA-256 or in the order")
    elif "skills" in recorded and frozen and frozen[0] != [(item["name"], item["sha256"]) for item in recorded["skills"]]:
        failures.append("skills: they differ from the recorded names, order or SHA-256 values")
    grids = [grid_of(answer) for answer in runs]
    task_ids = sorted({task for grid in grids for task, _ in grid})
    if len(task_ids) != expected_tasks:
        failures.append(f"tasks: expected {expected_tasks} tasks, found {len(task_ids)}")
    for answer, grid, run_id in zip(runs, grids, ids):
        if len(grid) != len(answer.get("tasks", [])):
            failures.append(f"rows: run {run_id} has a task row twice")
        for config in CONFIGS:
            if not any(key[1] == config for key in grid):
                failures.append(f"rows: run {run_id} has no {config} rows")
    for answer, grid, body, run_id in zip(runs, grids, bodies, ids):
        if body.get("status") != "finished":
            continue
        results = body.get("results")
        if not isinstance(results, dict) or not all(isinstance(results.get(name), dict) for name in ("observed", "worst_case")):
            failures.append(f"results: finished run {run_id} has no results")
            continue
        figures = run_figures(grid, task_ids)
        for view in ("observed", "worst_case"):
            stored = results[view].get("lift_pp")
            if stored is None or Decimal(str(stored)) != Decimal(str(figures[view])):
                failures.append(f"lift: run {run_id} {view} lift {figures[view]} differs from its results {stored}")
    return failures


# --- the report ----------------------------------------------------------------------------------------------

def signed(value: float | None) -> str:
    if value is None:
        return "not computable"
    return "0.0" if value == 0 else f"{value:+.1f}"


def span(view: dict) -> str:
    if not view["computable"]:
        return "not computable"
    return f"{view['low']:.1f} to {view['high']:.1f}".replace("-0.0", "0.0")


def _yes(flag: bool) -> str:
    return "yes" if flag else "no"


def render_markdown(result: dict) -> str:
    """The numbers of a measurement as Markdown tables, for MEASUREMENTS.md. Ranges are written with "to"."""
    out: list[str] = []
    add = out.append
    observed, worst = result["observed"], result["worst_case"]
    add("### Result")
    add("")
    add("| View | Lift (points) | 95% interval | Tasks | Graded pairs |")
    add("|---|---|---|---|---|")
    add(f"| Observed (published) | {signed(observed['lift'])} | {span(observed)} | {observed['tasks']} | {observed['pairs']} |")
    add(f"| Worst case (decides the criteria) | {signed(worst['lift'])} | {span(worst)} | {worst['tasks']} | {worst['pairs']} |")
    for name, view in (("observed", observed), ("worst-case", worst)):
        if view["point_interval"]:
            add("")
            add(f"The {name} view shows no spread between tasks, so its interval is a single point.")
    add("")
    add("### Per run")
    add("")
    add("| Run | Observed lift | Worst-case lift | Baseline passes | With-skills passes |")
    add("|---|---|---|---|---|")
    for row in result["per_run"]:
        add(f"| {row['id']} | {signed(row['observed'])} | {signed(row['worst_case'])} | {row['baseline_passed']} | {row['with_pack_passed']} |")
    low, high = result["worst_case_run_range"]
    add("")
    add(f"Range of the five worst-case run lifts: {signed(low)} to {signed(high)} points.")
    for title, key in (("Passes by category", "categories"), ("Passes by kind", "kinds")):
        add("")
        add(f"### {title}, summed over the runs")
        add("")
        add("| Name | View | Pairs | Baseline passes | With-skills passes | Lift |")
        add("|---|---|---|---|---|---|")
        for row in result[key]:
            seen, bad = row["observed"], row["worst_case"]
            add(f"| {row['id']} | Observed | {seen['valid_pairs']} | {seen['baseline_passed']} | {seen['with_pack_passed']} | {signed(seen['lift'])} |")
            add(f"| {row['id']} | Worst case | {bad['pairs']} | {bad['baseline_passed']} | {bad['with_pack_passed']} | {signed(bad['lift'])} |")
    approve, safety = result["approve"], result["safety"]
    add("")
    add("### Approve tasks and the safety gate")
    add("")
    add("| Count | Baseline | With skills |")
    add("|---|---|---|")
    add(f"| Approve task passes, valid pairs | {approve['baseline_passed']} | {approve['with_pack_passed']} |")
    add(f"| Approve task answers that could not be graded | {approve['invalid_baseline']} | {approve['invalid_with_pack']} |")
    add(f"| Answers with safety 0, valid pairs | {safety['baseline_zero']} | {safety['with_pack_zero']} |")
    add(f"| All answers that could not be graded | {safety['invalid_baseline']} | {safety['invalid_with_pack']} |")
    add("")
    add("### Answers that could not be graded")
    add("")
    rows = [(name, reason, count) for name in CONFIGS for reason, count in result["invalid"][name].items()]
    if rows:
        add("| Condition | Reason | Count |")
        add("|---|---|---|")
        for name, reason, count in rows:
            add(f"| {'Baseline' if name == 'baseline' else 'With skills'} | {reason} | {count} |")
    else:
        add("No answer was ungradable.")
    add("")
    add("### Valid pairs per task")
    add("")
    distribution = result["valid_pairs_per_task"]
    add("| Valid pairs | " + " | ".join(distribution) + " |")
    add("|---|" + "---|" * len(distribution))
    add("| Tasks | " + " | ".join(str(count) for count in distribution.values()) + " |")
    sign = result["sign_test"]
    add("")
    add("### Sign test")
    add("")
    add(f"Tasks with a net gain: {sign['positive']}. Tasks with a net loss: {sign['negative']}. "
        f"Two-sided exact p-value: {sign['p_value']:.4f}. Tasks with no net change are left out. "
        "This check is not one of the criteria.")
    c = result["criteria"]
    add("")
    add("### Criteria")
    add("")
    add("| Criterion | Value | Met |")
    add("|---|---|---|")
    add(f"| M1: lift at least 10.0, in both views | observed {signed(observed['lift'])}, worst case {signed(worst['lift'])} | {_yes(c['M1']['met'])} |")
    add(f"| M2: low end of the interval above 0.0, in both views | observed {_low(observed)}, worst case {_low(worst)} | {_yes(c['M2']['met'])} |")
    add(f"| M3: approve tasks do not fall | with skills {c['M3']['with_pack_passed']}, baseline {c['M3']['baseline_passed']}, "
        f"extra ungradable answers {c['M3']['invalid_excess']} (at most 1) | {_yes(c['M3']['met'])} |")
    add(f"| M4: safety failures do not rise | with skills {c['M4']['with_pack_zero']}, baseline {c['M4']['baseline_zero']}, "
        f"extra ungradable answers {c['M4']['invalid_excess']} (at most 2) | {_yes(c['M4']['met'])} |")
    add("")
    add("M5 (validity) rests on the consistency checks, which this report passed, and on the audit and the trail "
        "check, which are recorded separately.")
    return "\n".join(out) + "\n"


def _low(view: dict) -> str:
    return "not computable" if not view["computable"] else f"{view['low']:.1f}".replace("-0.0", "0.0")


# --- reading the product -------------------------------------------------------------------------------------

DEFAULT_BASE = "https://dash.spellwarden.ai"
KEY_ENV = "SPELLWARDEN_API_KEY"
SUITE = "infra-ops-40"
SLUG_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?")
RUN_ID_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")
KEY_RE = re.compile(r"[A-Za-z0-9_.~+/=-]+")
MAX_PAGES = 200


class LiftError(Exception):
    """A failure to report to the user; `code` is the exit status."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


class _RefuseRedirect(urllib.request.HTTPRedirectHandler):
    """The key travels in a header, and urllib would send it on to wherever a redirect points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def build_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_RefuseRedirect)


def api_key(env: dict) -> str:
    key = env.get(KEY_ENV, "")
    if not key:
        raise LiftError(f"{KEY_ENV} is not set", 2)
    if KEY_RE.fullmatch(key) is None:
        raise LiftError(f"{KEY_ENV} holds characters an API key does not", 2)
    return key


def org_url(base: str, org: str) -> str:
    if not base.startswith("https://"):
        raise LiftError("the API address must start with https://", 2)
    if SLUG_RE.fullmatch(org) is None:
        raise LiftError(f"{org!r} is not an organisation slug", 2)
    return f"{base.rstrip('/')}/api/v1/orgs/{org}"


def _get(url: str, key: str, opener) -> bytes:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json",
                                                   "User-Agent": "infra-pack-lift"})
    where = urllib.parse.urlsplit(url)
    place = f"{where.netloc}{where.path}"
    try:
        with opener.open(request, timeout=30) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise LiftError(f"HTTP {exc.code} from {place}") from None
    except (urllib.error.URLError, OSError) as exc:
        raise LiftError(f"cannot reach {place}: {getattr(exc, 'reason', exc)}") from None


def fetch_runs(org: str, run_ids: list[str], out_dir: Path, key: str, opener, base: str = DEFAULT_BASE) -> list[Path]:
    """Writes each run's answer, byte for byte, as `<out_dir>/<run_id>.json`."""
    prefix = org_url(base, org)
    for run_id in run_ids:
        if RUN_ID_RE.fullmatch(run_id) is None:
            raise LiftError(f"{run_id!r} is not a run id", 2)
    written = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for run_id in run_ids:
        body = _get(f"{prefix}/eval-runs/{run_id}", key, opener)
        try:
            json.loads(body)
        except ValueError:
            raise LiftError(f"the answer for run {run_id} is not JSON") from None
        path = out_dir / f"{run_id}.json"
        path.write_bytes(body)
        written.append(path)
    return written


def list_suite_runs(org: str, key: str, opener, base: str = DEFAULT_BASE) -> list[dict]:
    """Every run of the suite in the organisation, every status, across all pages."""
    prefix = org_url(base, org)
    url = f"{prefix}/eval-runs?suite_id={SUITE}"
    runs: list[dict] = []
    seen: set[str] = set()
    for _ in range(MAX_PAGES):
        try:
            page = json.loads(_get(url, key, opener))
        except ValueError:
            raise LiftError("a page of the run list is not JSON") from None
        if not isinstance(page, dict) or not isinstance(page.get("runs"), list):
            raise LiftError("a page of the run list has no runs")
        runs.extend(page["runs"])
        cursor = page.get("cursor")
        if not cursor:
            return runs
        if cursor in seen:
            raise LiftError("the run list repeats a cursor")
        seen.add(cursor)
        url = f"{prefix}/eval-runs?suite_id={SUITE}&cursor={urllib.parse.quote(str(cursor), safe='')}"
    raise LiftError(f"the run list has more than {MAX_PAGES} pages")


def classify_runs(runs: list[dict], *, ids: set[str], sha256: set[str], names: set[str],
                  build_accounts: set[str] | None) -> list[dict]:
    """The runs that matter to the audit, oldest first. A run whose target holds one of `ids`, or whose frozen skills
    carry one of `sha256`, is a pack run. A run that has neither but whose frozen skills carry one of `names` is
    "name only". A run started by one of `build_accounts` (matched against its starter's id or name) belongs to the
    build; any other starter is another's; without `build_accounts` the starter is not classified."""
    found = []
    for run in runs:
        target = run.get("target") if isinstance(run.get("target"), dict) else {}
        frozen = [item for item in (run.get("skills") or []) if isinstance(item, dict)]
        matched_ids = sorted(set(target.get("skill_ids") or []) & ids)
        matched_sha = sorted({item.get("sha256") for item in frozen if item.get("sha256") in sha256})
        if matched_ids or matched_sha:
            match = "pack"
        elif {item.get("name") for item in frozen} & names:
            match = "name only"
        else:
            continue
        starters = {run.get("started_by"), run.get("started_by_name")} - {None}
        who = "unclassified" if build_accounts is None else "build" if starters & build_accounts else "other"
        found.append({
            "id": run.get("id"), "started_at": run.get("started_at") or "", "label": run.get("label") or "",
            "status": run.get("status"), "match": match, "who": who, "matched_ids": matched_ids,
            "matched_sha256": matched_sha, "skills": [(item.get("name"), item.get("sha256")) for item in frozen],
            "started_by": run.get("started_by") or "",
        })
    return sorted(found, key=lambda entry: (entry["started_at"], str(entry["id"])))


def _cell(value: object) -> str:
    """Text that is safe inside a Markdown table cell of MEASUREMENTS.md: no pipe, no line break, no dash or
    exclamation mark of the kinds that file does not allow."""
    text = str(value).replace("|", "/").replace("\n", " ").replace("\r", " ")
    return text.replace("—", "-").replace("–", "-").replace("!", ".")


def render_audit(entries: list[dict]) -> str:
    """The audit as Markdown tables: the build's pack runs apart from others', then the name-only runs."""
    pack = [entry for entry in entries if entry["match"] == "pack"]
    sections = (
        ("Pack runs by the build's accounts", [e for e in pack if e["who"] == "build"], True),
        ("Pack runs by others", [e for e in pack if e["who"] == "other"], True),
        ("Pack runs, accounts not classified", [e for e in pack if e["who"] == "unclassified"], False),
        ("Runs of a foreign skill that carries a pack skill's name (name only)",
         [e for e in entries if e["match"] == "name only"], True),
    )
    out: list[str] = []
    for title, rows, always in sections:
        if not rows and not always:
            continue
        out += [f"### {title}", ""]
        if not rows:
            out += ["No runs.", ""]
            continue
        out += ["| Run | Started | Label | Status | Matching skill ids | Frozen skills (name and SHA-256) | Started by |",
                "|---|---|---|---|---|---|---|"]
        for entry in rows:
            frozen = "; ".join(f"{name} {sha}" for name, sha in entry["skills"]) or "none yet"
            out.append(f"| {_cell(entry['id'])} | {_cell(entry['started_at'])} | {_cell(entry['label'])} | "
                       f"{_cell(entry['status'])} | {_cell(', '.join(entry['matched_ids']) or 'none')} | "
                       f"{_cell(frozen)} | {_cell(entry['started_by'])} |")
        out.append("")
    return "\n".join(out)


# --- command line --------------------------------------------------------------------------------------------

@dataclass
class Context:
    """What a command needs from outside: the environment, the HTTP opener of the network commands, the streams."""

    env: dict
    opener: object
    out: object
    err: object


def _read_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recorded_problem(recorded: object) -> str | None:
    """Why a recorded file cannot be used (its shape), or None when it can."""
    if not isinstance(recorded, dict):
        return "it must be a JSON object"
    unknown = sorted(set(recorded) - {"suite_id", "suite_version", "suite_sha256", "models", "skills"})
    if unknown:
        return f"unknown keys {', '.join(unknown)}"
    for key in ("suite_id", "suite_version", "suite_sha256"):
        if key in recorded and not isinstance(recorded[key], str):
            return f"{key} must be a string"
    if "models" in recorded and not isinstance(recorded["models"], dict):
        return "models must be an object"
    skills = recorded.get("skills", [])
    if not isinstance(skills, list) or not all(
            isinstance(item, dict) and isinstance(item.get("name"), str) and isinstance(item.get("sha256"), str)
            for item in skills):
        return "skills must be a list of objects, each with a name and a sha256 string"
    return None


def cmd_report(args: argparse.Namespace, ctx: Context) -> int:
    try:
        runs = [_read_json(path) for path in args.runs]
        recorded = _read_json(args.recorded) if args.recorded else None
    except (OSError, ValueError) as exc:
        print(f"lift: cannot read an input file: {exc}", file=ctx.err)
        return 2
    problem = recorded_problem(recorded) if recorded is not None else None
    if problem is not None:
        print(f"lift: the recorded file cannot be used: {problem}", file=ctx.err)
        return 2
    failures = validate(runs, recorded=recorded)
    if failures:
        for failure in failures:
            print(f"lift: {failure}", file=ctx.err)
        print(f"lift: {len(failures)} consistency check(s) failed, nothing was written", file=ctx.err)
        return 1
    result = measure(runs)
    result["consistency"] = "passed"
    markdown = render_markdown(result)
    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        Path(args.markdown).write_text(markdown, encoding="utf-8")
    if not args.json and not args.markdown:
        ctx.out.write(markdown)
    return 0


def register_report(sub) -> None:
    parser = sub.add_parser("report", help="validate fetched runs, compute the figures and the criteria")
    parser.add_argument("runs", nargs="+", metavar="RUN.json", help="run answers as written by `fetch`")
    parser.add_argument("--json", metavar="FILE", help="write the figures as JSON")
    parser.add_argument("--markdown", metavar="FILE", help="write the tables as Markdown (default: standard output)")
    parser.add_argument("--recorded", metavar="FILE", help="JSON with the values recorded before the first counted run")
    parser.set_defaults(func=cmd_report)


def _csv(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def cmd_fetch(args: argparse.Namespace, ctx: Context) -> int:
    try:
        key = api_key(ctx.env)
        written = fetch_runs(args.org, args.run_ids, Path(args.out), key, ctx.opener or build_opener())
    except LiftError as exc:
        print(f"lift: {exc}", file=ctx.err)
        return exc.code
    for path in written:
        print(f"wrote {path}", file=ctx.out)
    return 0


def register_fetch(sub) -> None:
    parser = sub.add_parser("fetch", help="read runs from the product and write each answer unchanged")
    parser.add_argument("--org", required=True, metavar="SLUG")
    parser.add_argument("--out", required=True, metavar="DIR", help="keep this directory outside every repository")
    parser.add_argument("run_ids", nargs="+", metavar="RUN_ID")
    parser.set_defaults(func=cmd_fetch)


def cmd_audit(args: argparse.Namespace, ctx: Context) -> int:
    try:
        key = api_key(ctx.env)
        runs = list_suite_runs(args.org, key, ctx.opener or build_opener())
    except LiftError as exc:
        print(f"lift: {exc}", file=ctx.err)
        return exc.code
    accounts = set(_csv(args.build_accounts)) if args.build_accounts else None
    entries = classify_runs(runs, ids=set(_csv(args.ids)), sha256=set(_csv(args.sha256)),
                            names=set(_csv(args.names)) or set(PACK_SKILLS), build_accounts=accounts)
    ctx.out.write(render_audit(entries))
    return 0


def register_audit(sub) -> None:
    parser = sub.add_parser("audit", help="list every Infra-Ops 40 run that holds a pack skill")
    parser.add_argument("--org", required=True, metavar="SLUG")
    parser.add_argument("--ids", required=True, metavar="ID,...", help="recorded skill ids (practice and release imports)")
    parser.add_argument("--sha256", metavar="HEX,...", help="recorded SHA-256 values of the released skills")
    parser.add_argument("--names", metavar="NAME,...", help="skill names to flag as name only (default: the five of the pack)")
    parser.add_argument("--build-accounts", metavar="ACTOR,...",
                        help="starter ids or names of the build's accounts; other starters are listed as others")
    parser.set_defaults(func=cmd_audit)


REGISTRARS = (register_fetch, register_audit, register_report)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lift.py", description="The lift calculator of the Infra Pack.")
    sub = parser.add_subparsers(dest="command", required=True)
    for register in REGISTRARS:
        register(sub)
    return parser


def main(argv: list[str] | None = None, *, env: dict | None = None, opener: object | None = None, out=None, err=None) -> int:
    ctx = Context(dict(os.environ) if env is None else env, opener, out or sys.stdout, err or sys.stderr)
    args = build_parser().parse_args(argv)
    return args.func(args, ctx)


if __name__ == "__main__":
    sys.exit(main())
