"""Synthetic evaluation runs for the tests of lift.py: task ids T-01 to T-40, never real data.

A plan maps a task id to the outcome of its two answers, (baseline, with_pack), each one of
"pass", "fail", "unsafe" (a failure with safety 0), "invalid" or "missing" (no row at all)."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

import support  # noqa: F401  (puts tools/ on sys.path)

from pack_common import SKILL_NAMES

TASK_IDS = [f"T-{number:02d}" for number in range(1, 41)]
CATEGORIES = ("category-a", "category-b", "category-c", "category-d")
KIND = {task: ("approve" if number <= 9 else "insufficient_evidence" if number <= 14 else "trap")
        for number, task in enumerate(TASK_IDS, 1)}
CATEGORY = {task: CATEGORIES[(number - 1) // 10] for number, task in enumerate(TASK_IDS, 1)}
SKILL_SHA = {name: f"{index:064x}" for index, name in enumerate(SKILL_NAMES, 1)}
SUITE_SHA = "ab" * 32
MODELS = {"agent": "agent-model", "judge": "judge-model", "effort": "high"}


def run_id(index: int) -> str:
    return f"{index:032x}"


def task_row(task_id: str, config: str, code: str) -> dict | None:
    if code == "missing":
        return None
    base = {"task_id": task_id, "config": config, "category": CATEGORY[task_id], "kind": KIND[task_id]}
    if code == "invalid":
        return {**base, "stage": "invalid", "invalid_reason": "unparseable", "scores": None, "weighted": None, "passed": None}
    passed = code == "pass"
    scores = {"correctness": 1.0 if passed else 0.5, "safety": 0.0 if code == "unsafe" else 1.0, "evidence": 1.0,
              "efficiency": 1.0}
    return {**base, "stage": "done", "scores": scores, "weighted": 0.9 if passed else 0.4, "passed": passed}


def _own_lift(plan: dict[str, tuple[str, str]]) -> dict:
    """What the product would store in `results`, computed here by a separate, plain implementation."""
    gained = lost = valid = worst_base = worst_with = 0
    for task in TASK_IDS:
        base, with_pack = plan[task]
        graded = base in ("pass", "fail", "unsafe") and with_pack in ("pass", "fail", "unsafe")
        if graded:
            valid += 1
            gained += int(with_pack == "pass" and base != "pass")
            lost += int(base == "pass" and with_pack != "pass")
        worst_base += int(base == "pass" or base in ("invalid", "missing"))
        worst_with += int(with_pack == "pass")

    def pp(difference: int, n: int) -> float:
        if n == 0:
            return 0.0
        return float((Decimal(difference) * 100 / Decimal(n)).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))

    return {"observed": {"lift_pp": pp(gained - lost, valid), "valid_pairs": valid},
            "worst_case": {"lift_pp": pp(worst_with - worst_base, len(TASK_IDS))}}


def make_run(index: int, plan: dict[str, tuple[str, str]] | None = None, *, default: tuple[str, str] = ("fail", "fail"),
             status: str = "finished", drop_config: str | None = None, results: dict | None = None,
             run: dict | None = None) -> dict:
    """A fetched run answer: {"run": ..., "tasks": [...], "progress": ...}. `run` overrides fields of the run."""
    full = {task: (plan or {}).get(task, default) for task in TASK_IDS}
    rows = []
    for task in TASK_IDS:
        for config, code in zip(("baseline", "with_pack"), full[task]):
            if config != drop_config:
                row = task_row(task, config, code)
                if row is not None:
                    rows.append(row)
    frozen = [{"skill_id": f"skill-{number}", "name": name, "sha256": SKILL_SHA[name]}
              for number, name in enumerate(SKILL_NAMES, 1)]
    body = {
        "id": run_id(index), "kind": "paired", "suite_id": "infra-ops-40", "suite_version": "1.0.0",
        "suite_sha256": SUITE_SHA, "status": status, "label": f"Placeholder counted {index} of 5",
        "started_at": f"2026-11-0{index}T10:00:00Z", "started_by": "user:builder", "started_by_name": "Build Account",
        "target": {"skill_ids": [item["skill_id"] for item in frozen]}, "skills": frozen, "models": dict(MODELS),
        "results": (results if results is not None else _own_lift(full)) if status == "finished" else None,
    }
    body.update(run or {})
    return {"run": body, "tasks": rows, "progress": {"done": len(rows), "total": len(rows)}}


def make_runs(plan: dict[str, tuple[str, str]] | None = None, count: int = 5, **kwargs) -> list[dict]:
    """`count` identical runs."""
    return [make_run(index, plan, **kwargs) for index in range(1, count + 1)]


def gains_and_losses(gained: int, lost: int, extra: dict[str, tuple[str, str]] | None = None) -> dict[str, tuple[str, str]]:
    """A plan where `gained` trap tasks pass only with skills and the next `lost` trap tasks pass only without."""
    plan: dict[str, tuple[str, str]] = {}
    traps = [task for task in TASK_IDS if KIND[task] == "trap"]
    for task in traps[:gained]:
        plan[task] = ("fail", "pass")
    for task in traps[gained:gained + lost]:
        plan[task] = ("pass", "fail")
    plan.update(extra or {})
    return plan
