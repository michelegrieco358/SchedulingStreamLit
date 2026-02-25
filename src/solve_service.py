from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd
from ortools.sat.python import cp_model

from .diagnostics import build_infeasibility_summary
from .objective_report import ObjectiveBreakdown, compute_objective_breakdown
from .solver import build_solver_from_sources
from .warm_start import WarmStartError, WarmStartStats, apply_slot_warm_start_hints


@dataclass(frozen=True)
class SolveResult:
    status_code: int
    status_name: str
    objective_value: float | None
    best_objective_bound: float | None
    assignments_df: pd.DataFrame
    coverage_under_role_df: pd.DataFrame
    coverage_under_group_df: pd.DataFrame
    objective_breakdown: ObjectiveBreakdown | None
    infeasibility_summary: dict[str, Any] | None
    warm_start_stats: WarmStartStats | None
    solver: cp_model.CpSolver
    model: cp_model.CpModel
    artifacts: Any
    context: Any
    bundle: Mapping[str, object]


def _build_assignments_df(
    solver: cp_model.CpSolver,
    artifacts: Any,
    bundle: Mapping[str, object],
) -> pd.DataFrame:
    x = artifacts.assign_vars
    emp_of = bundle.get("emp_of", {})
    slot_of = bundle.get("slot_of", {})
    slot_date = bundle.get("slot_date", {})
    slot_reparto = bundle.get("slot_reparto", {})
    slot_shiftcode = bundle.get("slot_shiftcode", {})

    rows: list[dict[str, object]] = []
    for (e_idx, s_idx), var in x.items():
        if solver.Value(var) != 1:
            continue
        slot_id = slot_of.get(s_idx, s_idx)
        rows.append(
            {
                "date": slot_date.get(slot_id),
                "reparto_id": slot_reparto.get(slot_id),
                "shift_code": slot_shiftcode.get(slot_id),
                "slot_id": slot_id,
                "employee_id": emp_of.get(e_idx, e_idx),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["date", "reparto_id", "shift_code", "slot_id", "employee_id"]
        )

    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    sort_cols = [
        col
        for col in ["date", "reparto_id", "shift_code", "employee_id"]
        if col in df.columns
    ]
    if sort_cols:
        df = df.sort_values(sort_cols)
    return df.reset_index(drop=True)


def _build_coverage_under_role_df(
    solver: cp_model.CpSolver,
    artifacts: Any,
    bundle: Mapping[str, object],
) -> pd.DataFrame:
    slot_of = bundle.get("slot_of", {})
    slot_date = bundle.get("slot_date", {})
    slot_reparto = bundle.get("slot_reparto", {})
    slot_shiftcode = bundle.get("slot_shiftcode", {})

    rows: list[dict[str, object]] = []
    for (slot_idx, role), var in artifacts.coverage_under_role.items():
        slot_id = slot_of.get(slot_idx, slot_idx)
        rows.append(
            {
                "slot_id": slot_id,
                "role": str(role),
                "under_staff": int(solver.Value(var)),
                "date": slot_date.get(slot_id),
                "reparto_id": slot_reparto.get(slot_id),
                "shift_code": slot_shiftcode.get(slot_id),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=[
                "slot_id",
                "role",
                "under_staff",
                "date",
                "reparto_id",
                "shift_code",
            ]
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.sort_values(["date", "slot_id", "role"]).reset_index(drop=True)


def _build_coverage_under_group_df(
    solver: cp_model.CpSolver,
    artifacts: Any,
    bundle: Mapping[str, object],
) -> pd.DataFrame:
    slot_of = bundle.get("slot_of", {})
    slot_date = bundle.get("slot_date", {})
    slot_reparto = bundle.get("slot_reparto", {})
    slot_shiftcode = bundle.get("slot_shiftcode", {})

    rows: list[dict[str, object]] = []
    for slot_idx, var in artifacts.coverage_under_group.items():
        slot_id = slot_of.get(slot_idx, slot_idx)
        rows.append(
            {
                "slot_id": slot_id,
                "under_staff": int(solver.Value(var)),
                "date": slot_date.get(slot_id),
                "reparto_id": slot_reparto.get(slot_id),
                "shift_code": slot_shiftcode.get(slot_id),
            }
        )

    if not rows:
        return pd.DataFrame(
            columns=["slot_id", "under_staff", "date", "reparto_id", "shift_code"]
        )
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df.sort_values(["date", "slot_id"]).reset_index(drop=True)


def solve_schedule(
    cfg_path: str,
    data_dir: str,
    *,
    selected_departments: Iterable[str] | None = None,
    stability_enabled: bool | None = None,
    max_time_s: float | None = 600.0,
    relative_gap_limit: float | None = None,
    seed: int | None = None,
    num_workers: int | None = None,
    log_search_progress: bool = False,
    log_to_stdout: bool | None = None,
    warm_start_df: pd.DataFrame | None = None,
    warm_start_strict: bool = False,
    solution_callback: cp_model.CpSolverSolutionCallback | None = None,
) -> SolveResult:
    model, artifacts, context, bundle = build_solver_from_sources(
        cfg_path,
        data_dir,
        selected_departments=selected_departments,
        stability_enabled=stability_enabled,
    )

    solver = cp_model.CpSolver()
    if max_time_s is not None and float(max_time_s) > 0:
        solver.parameters.max_time_in_seconds = float(max_time_s)
    if relative_gap_limit is not None and float(relative_gap_limit) > 0:
        solver.parameters.relative_gap_limit = float(relative_gap_limit)
    if seed is not None:
        solver.parameters.random_seed = int(seed)
    if num_workers is not None:
        solver.parameters.num_search_workers = int(num_workers)
    solver.parameters.log_search_progress = bool(log_search_progress)
    if log_to_stdout is not None:
        solver.parameters.log_to_stdout = bool(log_to_stdout)

    warm_stats: WarmStartStats | None = None
    if warm_start_df is not None and not warm_start_df.empty:
        warm_stats = apply_slot_warm_start_hints(
            model,
            artifacts.assign_vars,
            bundle,
            warm_start_df,
            strict=bool(warm_start_strict),
        )

    if solution_callback is not None and hasattr(solver, "SolveWithSolutionCallback"):
        status = solver.SolveWithSolutionCallback(model, solution_callback)
    elif solution_callback is not None:
        status = solver.Solve(model, solution_callback)
    else:
        status = solver.Solve(model)

    status_name = solver.StatusName(status)
    feasible = status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    objective_value = float(solver.ObjectiveValue()) if feasible else None
    best_bound = float(solver.BestObjectiveBound()) if feasible else None

    assignments_df = (
        _build_assignments_df(solver, artifacts, bundle)
        if feasible
        else pd.DataFrame(
            columns=["date", "reparto_id", "shift_code", "slot_id", "employee_id"]
        )
    )
    coverage_under_role_df = (
        _build_coverage_under_role_df(solver, artifacts, bundle)
        if feasible
        else pd.DataFrame(
            columns=[
                "slot_id",
                "role",
                "under_staff",
                "date",
                "reparto_id",
                "shift_code",
            ]
        )
    )
    coverage_under_group_df = (
        _build_coverage_under_group_df(solver, artifacts, bundle)
        if feasible
        else pd.DataFrame(
            columns=["slot_id", "under_staff", "date", "reparto_id", "shift_code"]
        )
    )

    objective_breakdown = (
        compute_objective_breakdown(solver, artifacts)
        if feasible
        else None
    )
    infeasibility_summary = (
        build_infeasibility_summary(context)
        if status == cp_model.INFEASIBLE
        else None
    )

    return SolveResult(
        status_code=int(status),
        status_name=str(status_name),
        objective_value=objective_value,
        best_objective_bound=best_bound,
        assignments_df=assignments_df,
        coverage_under_role_df=coverage_under_role_df,
        coverage_under_group_df=coverage_under_group_df,
        objective_breakdown=objective_breakdown,
        infeasibility_summary=infeasibility_summary,
        warm_start_stats=warm_stats,
        solver=solver,
        model=model,
        artifacts=artifacts,
        context=context,
        bundle=bundle,
    )


__all__ = [
    "SolveResult",
    "solve_schedule",
    "WarmStartError",
]
