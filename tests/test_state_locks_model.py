"""Tests per _apply_state_lock_constraints in src/model.py.

Verifica che i vincoli hard su variabili di stato (locks_state_pairs nel bundle)
vengano applicati correttamente al modello CP-SAT:
- MUST_DO (lock=1)  → state_var == 1
- FORBIDDEN (lock=-1) → state_var == 0
- state_code sconosciuto → ignorato silenziosamente (no crash)
- Più lock su stati diversi nello stesso giorno sono gestiti correttamente
"""
from __future__ import annotations

from datetime import date

import pandas as pd
from ortools.sat.python import cp_model

from src.model import ModelContext, build_model


# ── Helper ────────────────────────────────────────────────────────────────────


def _make_state_lock_context(
    locks_state_pairs: list[tuple[int, int, str, int]] | None = None,
) -> ModelContext:
    """Costruisce un ModelContext minimale con i lock di stato specificati.

    Un solo dipendente (E1), un solo slot M il 2025-01-01, un solo giorno.
    I lock di stato sono passati direttamente nel bundle come lista di tuple
    (emp_idx, day_idx, state_code, lock_value) per testare
    _apply_state_lock_constraints indipendentemente dal preprocessing.
    """
    employees = pd.DataFrame({"employee_id": ["E1"], "role": ["INFERMIERE"]})
    slots_df = pd.DataFrame(
        {
            "slot_id": [1],
            "shift_code": ["M"],
            "date": [date(2025, 1, 1)],
        }
    )
    calendar = pd.DataFrame({"data": [pd.Timestamp("2025-01-01")]})

    bundle = {
        "eid_of": {"E1": 0},
        "emp_of": {0: "E1"},
        "sid_of": {1: 0},
        "slot_of": {0: 1},
        "did_of": {date(2025, 1, 1): 0},
        "date_of": {0: date(2025, 1, 1)},
        "num_employees": 1,
        "num_slots": 1,
        "num_days": 1,
        "eligible_eids": {0: [0]},
        "slot_date2": {0: 0},
        "locks_state_pairs": locks_state_pairs or [],
    }

    empty = pd.DataFrame()
    return ModelContext(
        cfg={},
        employees=employees,
        slots=slots_df,
        coverage_roles=empty,
        coverage_totals=empty,
        slot_requirements=empty,
        availability=empty,
        leaves=empty,
        history=empty,
        locks_must=pd.DataFrame(columns=["employee_id", "slot_id"]),
        locks_forbid=pd.DataFrame(columns=["employee_id", "slot_id"]),
        locks_state_must=pd.DataFrame(),
        locks_state_forbid=pd.DataFrame(),
        gap_pairs=empty,
        calendars=calendar,
        preassignments=pd.DataFrame(columns=["employee_id", "data", "state_code"]),
        bundle=bundle,
    )


def _solve(model: cp_model.CpModel) -> tuple[cp_model.CpSolver, int]:
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    return solver, int(status)


# ── MUST_DO ───────────────────────────────────────────────────────────────────


def test_state_must_lock_forces_state_to_one() -> None:
    """Lock MUST_DO su stato R → state_vars[(0,0,'R')] == 1."""
    context = _make_state_lock_context(locks_state_pairs=[(0, 0, "R", 1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")

    r_var = artifacts.state_vars[(0, 0, "R")]
    assert solver.Value(r_var) == 1, "MUST_DO deve forzare stato R a 1"

    # Aggiungere il contrario rende il modello infattibile
    artifacts.model.Add(r_var == 0)
    solver2 = cp_model.CpSolver()
    assert solver2.Solve(artifacts.model) == cp_model.INFEASIBLE


def test_state_must_lock_on_demand_shift_forces_slot_assignment() -> None:
    """Lock MUST_DO su stato M (domanda) → anche l'assegnazione slot è forzata.

    Il vincolo di accoppiamento stato↔slot propaga automaticamente:
    state_var[M] == 1  ⟹  sum(assign_vars per M in quel giorno) >= 1.
    """
    context = _make_state_lock_context(locks_state_pairs=[(0, 0, "M", 1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")

    m_state_var = artifacts.state_vars[(0, 0, "M")]
    slot_var = artifacts.assign_vars[(0, 0)]  # unico slot (idx=0)

    assert solver.Value(m_state_var) == 1
    assert solver.Value(slot_var) == 1, (
        "MUST_DO su stato M deve forzare l'assegnazione dello slot M"
    )


# ── FORBIDDEN ─────────────────────────────────────────────────────────────────


def test_state_forbid_lock_blocks_state() -> None:
    """Lock FORBIDDEN su stato R → state_vars[(0,0,'R')] == 0."""
    context = _make_state_lock_context(locks_state_pairs=[(0, 0, "R", -1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")

    r_var = artifacts.state_vars[(0, 0, "R")]
    assert solver.Value(r_var) == 0, "FORBIDDEN deve forzare stato R a 0"

    # Aggiungere il contrario rende il modello infattibile
    artifacts.model.Add(r_var == 1)
    solver2 = cp_model.CpSolver()
    assert solver2.Solve(artifacts.model) == cp_model.INFEASIBLE


def test_state_forbid_lock_on_demand_shift_blocks_slot_assignment() -> None:
    """Lock FORBIDDEN su stato M → il dipendente non può lavorare turno M quel giorno.

    Il vincolo di accoppiamento propaga: state_var[M] == 0  ⟹  assign_vars[slot_M] == 0.
    """
    context = _make_state_lock_context(locks_state_pairs=[(0, 0, "M", -1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")

    m_state_var = artifacts.state_vars[(0, 0, "M")]
    slot_var = artifacts.assign_vars[(0, 0)]

    assert solver.Value(m_state_var) == 0
    assert solver.Value(slot_var) == 0, (
        "FORBIDDEN su stato M deve bloccare l'assegnazione dello slot M"
    )


# ── Robustezza ────────────────────────────────────────────────────────────────


def test_state_lock_unknown_state_code_is_ignored() -> None:
    """state_code non creato nel modello (es. 'XYZZY') → ignorato, nessun crash."""
    context = _make_state_lock_context(locks_state_pairs=[(0, 0, "XYZZY", 1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    # Il modello deve rimanere fattibile nonostante il lock ignoto
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")


def test_state_lock_out_of_range_employee_idx_is_ignored() -> None:
    """emp_idx fuori range (non esiste in state_vars) → ignorato, nessun crash."""
    context = _make_state_lock_context(locks_state_pairs=[(99, 0, "R", 1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")


def test_state_lock_out_of_range_day_idx_is_ignored() -> None:
    """day_idx fuori range → ignorato, nessun crash."""
    context = _make_state_lock_context(locks_state_pairs=[(0, 99, "R", 1)])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")


def test_no_state_locks_model_is_feasible() -> None:
    """Bundle senza locks_state_pairs → modello fattibile senza modifiche."""
    context = _make_state_lock_context(locks_state_pairs=[])
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")


def test_multiple_forbid_on_different_states_still_feasible() -> None:
    """Più FORBIDDEN su stati diversi nello stesso giorno → rimane fattibile
    finché almeno uno stato è disponibile (il modello ha 7 stati di default)."""
    # Vieta 5 stati su 7: deve comunque trovare una soluzione
    pairs = [
        (0, 0, "M", -1),
        (0, 0, "P", -1),
        (0, 0, "N", -1),
        (0, 0, "G", -1),
        (0, 0, "SN", -1),
    ]
    context = _make_state_lock_context(locks_state_pairs=pairs)
    artifacts = build_model(context)

    solver, status = _solve(artifacts.model)
    assert solver.StatusName(status) in ("OPTIMAL", "FEASIBLE")

    # Il dipendente deve essere in R o F
    r_var = artifacts.state_vars[(0, 0, "R")]
    f_var = artifacts.state_vars[(0, 0, "F")]
    assert solver.Value(r_var) + solver.Value(f_var) == 1
