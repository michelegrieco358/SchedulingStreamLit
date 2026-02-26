from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

import pandas as pd
from ortools.sat.python import cp_model

from .diagnostics import build_infeasibility_summary
from .load_data import (
    LoaderError,
    _filter_loaded_data_for_departments,
    _normalize_departments,
    load_all_data,
)
from .model import (
    ModelArtifacts,
    ModelContext,
    add_coverage_constraints,
    build_context_from_data,
    build_model,
)
from .objective_report import ObjectiveBreakdown, compute_objective_breakdown
from .preprocessing import build_all as _build_bundle
from .solver import build_solver_from_sources
from .warm_start import WarmStartError, WarmStartStats, apply_slot_warm_start_hints


@dataclass(frozen=True)
class SolveResult:
    status_code: int
    status_name: str
    objective_value: float | None
    best_objective_bound: float | None
    assignments_df: pd.DataFrame
    states_df: pd.DataFrame
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


def _build_state_table(
    solver: cp_model.CpSolver,
    artifacts: Any,
    bundle: Mapping[str, object],
) -> pd.DataFrame:
    """Estrae la matrice stati (employee_id, date, state) dalla soluzione."""
    emp_of: Mapping[int, str] = bundle.get("emp_of", {})
    date_of: Mapping[int, object] = bundle.get("date_of", {})

    if not emp_of or not date_of:
        return pd.DataFrame(columns=["employee_id", "date", "state"])

    state_codes: Iterable[str] = artifacts.state_codes

    rows: list[dict[str, object]] = []
    for emp_idx in sorted(emp_of.keys()):
        employee_id = emp_of[emp_idx]
        for day_idx in sorted(date_of.keys()):
            day = date_of[day_idx]
            state_value = ""
            for code in state_codes:
                var = artifacts.state_vars.get((emp_idx, day_idx, code))
                if var is None:
                    continue
                if solver.Value(var):
                    state_value = code
                    break
            rows.append(
                {
                    "employee_id": employee_id,
                    "date": str(day),
                    "state": state_value,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["employee_id", "date", "state"])
    return df.sort_values(["date", "employee_id"]).reset_index(drop=True)


def pivot_state_grid(states_df: pd.DataFrame) -> pd.DataFrame:
    """Pivota states_df in griglia (righe=employee_id, colonne=date, valori=state)."""
    if states_df.empty:
        return pd.DataFrame()
    return states_df.pivot(
        index="employee_id", columns="date", values="state"
    ).fillna("")


def solution_to_preassignments(states_df: pd.DataFrame) -> pd.DataFrame:
    """Converte states_df nel formato preassegnamenti (employee_id, data, state_code)."""
    if states_df.empty:
        return pd.DataFrame(columns=["employee_id", "data", "state_code"])
    result = states_df.rename(columns={"date": "data", "state": "state_code"}).copy()
    return result[["employee_id", "data", "state_code"]].reset_index(drop=True)


def resolve_lock(
    date: Any,
    shift_code: str,
    reparto_id: str,
    shift_slots_df: pd.DataFrame,
) -> int | None:
    """Traduce coordinate utente (data, turno, reparto) in slot_id.

    Restituisce lo slot_id corrispondente, o None se non trovato.
    """
    mask = (
        (shift_slots_df["data_dt"] == pd.Timestamp(date))
        & (shift_slots_df["shift_code"] == shift_code)
        & (shift_slots_df["reparto_id"].str.strip().str.upper() == str(reparto_id).strip().upper())
    )
    matches = shift_slots_df.loc[mask, "slot_id"]
    if matches.empty:
        return None
    return int(matches.iloc[0])


def _build_context_from_dict(
    data: dict[str, Any],
    cfg: dict[str, Any],
    *,
    selected_departments: Iterable[str] | None = None,
) -> tuple[ModelContext, dict[str, Any], Mapping[str, object]]:
    """Costruisce context e bundle da un dict di DataFrame già caricato."""
    cfg_dict = cfg if cfg is not None else data.get("cfg", {})

    explicit_selection = _normalize_departments(selected_departments)
    cfg_selection = _normalize_departments(
        cfg_dict.get("scheduling", {}).get("selected_departments")
        if isinstance(cfg_dict.get("scheduling"), Mapping)
        else None
    )
    active_selection = explicit_selection or cfg_selection

    working_data = dict(data)
    working_cfg = dict(cfg_dict)

    if active_selection:
        allowed = _normalize_departments(
            working_cfg.get("defaults", {}).get("departments")
            if isinstance(working_cfg.get("defaults"), Mapping)
            else None
        )
        unknown = sorted(set(active_selection) - set(allowed))
        if unknown:
            raise LoaderError(
                "Reparti selezionati non presenti in defaults.departments: "
                + ", ".join(unknown)
            )

        working_data = _filter_loaded_data_for_departments(working_data, active_selection)
        scheduling_cfg = working_cfg.get("scheduling")
        if not isinstance(scheduling_cfg, Mapping):
            scheduling_cfg = {}
        scheduling_cfg = dict(scheduling_cfg)
        scheduling_cfg["selected_departments"] = active_selection
        working_cfg["scheduling"] = scheduling_cfg
        working_data["cfg"] = working_cfg

    if "cfg" not in working_data:
        working_data["cfg"] = working_cfg

    bundle = _build_bundle(working_data, working_cfg)
    context = build_context_from_data(working_data, bundle)
    return context, working_data, bundle


def _run_solver(
    model_cp: cp_model.CpModel,
    artifacts: ModelArtifacts,
    context: ModelContext,
    bundle: Mapping[str, object],
    *,
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
    """Configura, esegue il solver e assembla SolveResult."""
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
            model_cp,
            artifacts.assign_vars,
            bundle,
            warm_start_df,
            strict=bool(warm_start_strict),
        )

    if solution_callback is not None and hasattr(solver, "SolveWithSolutionCallback"):
        status = solver.SolveWithSolutionCallback(model_cp, solution_callback)
    elif solution_callback is not None:
        status = solver.Solve(model_cp, solution_callback)
    else:
        status = solver.Solve(model_cp)

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
    states_df = (
        _build_state_table(solver, artifacts, bundle)
        if feasible
        else pd.DataFrame(columns=["employee_id", "date", "state"])
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
        states_df=states_df,
        coverage_under_role_df=coverage_under_role_df,
        coverage_under_group_df=coverage_under_group_df,
        objective_breakdown=objective_breakdown,
        infeasibility_summary=infeasibility_summary,
        warm_start_stats=warm_stats,
        solver=solver,
        model=model_cp,
        artifacts=artifacts,
        context=context,
        bundle=bundle,
    )


def solve_schedule_from_data(
    data: dict[str, Any],
    cfg: dict[str, Any],
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
    """Risolve il problema di scheduling a partire da un dict di DataFrame in memoria.

    Questo entry point evita l'I/O su disco: utile quando la UI modifica
    i dati (lock, copertura, preassegnamenti) e vuole ri-lanciare il solver
    senza riscrivere i CSV.
    """
    context, working_data, bundle = _build_context_from_dict(
        data, cfg, selected_departments=selected_departments,
    )
    artifacts = build_model(context, stability_enabled=stability_enabled)
    add_coverage_constraints(context, artifacts)

    return _run_solver(
        artifacts.model,
        artifacts,
        context,
        bundle,
        max_time_s=max_time_s,
        relative_gap_limit=relative_gap_limit,
        seed=seed,
        num_workers=num_workers,
        log_search_progress=log_search_progress,
        log_to_stdout=log_to_stdout,
        warm_start_df=warm_start_df,
        warm_start_strict=warm_start_strict,
        solution_callback=solution_callback,
    )


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
    """Risolve il problema di scheduling caricando dati da file."""
    model_cp, artifacts, context, bundle = build_solver_from_sources(
        cfg_path,
        data_dir,
        selected_departments=selected_departments,
        stability_enabled=stability_enabled,
    )

    return _run_solver(
        model_cp,
        artifacts,
        context,
        bundle,
        max_time_s=max_time_s,
        relative_gap_limit=relative_gap_limit,
        seed=seed,
        num_workers=num_workers,
        log_search_progress=log_search_progress,
        log_to_stdout=log_to_stdout,
        warm_start_df=warm_start_df,
        warm_start_strict=warm_start_strict,
        solution_callback=solution_callback,
    )


__all__ = [
    "SolveResult",
    "pivot_state_grid",
    "resolve_lock",
    "solution_to_preassignments",
    "solve_schedule",
    "solve_schedule_from_data",
    "WarmStartError",
]
