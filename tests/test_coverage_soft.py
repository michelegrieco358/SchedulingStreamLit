from __future__ import annotations

from datetime import date

import pandas as pd
from ortools.sat.python import cp_model

from src.model import ModelContext, add_coverage_constraints, build_model


def _base_bundle() -> dict[str, object]:
    return {
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
    }


def test_coverage_constraints_are_soft_and_keep_model_feasible() -> None:
    employees = pd.DataFrame({"employee_id": ["E1"], "role": ["INFERMIERE"]})
    slots = pd.DataFrame(
        {
            "slot_id": [1],
            "shift_code": ["M"],
            "coverage_code": ["COV"],
            "reparto_id": ["REP1"],
            "date": [date(2025, 1, 1)],
        }
    )
    slot_requirements = pd.DataFrame(
        {
            "slot_id": [1],
            "role": ["INFERMIERE"],
            "demand": [2],
        }
    )
    coverage_totals = pd.DataFrame(
        {
            "coverage_code": ["COV"],
            "shift_code": ["M"],
            "reparto_id": ["REP1"],
            "total_staff": [2],
            "ruoli_totale": ["INFERMIERE"],
        }
    )
    calendar = pd.DataFrame({"data": [pd.Timestamp("2025-01-01")]})
    empty = pd.DataFrame()

    context = ModelContext(
        cfg={"weights": {"coverage_under_role": 1000.0, "coverage_under_group": 1200.0}},
        employees=employees,
        slots=slots,
        coverage_roles=empty,
        coverage_totals=coverage_totals,
        slot_requirements=slot_requirements,
        availability=empty,
        leaves=empty,
        history=empty,
        locks_must=empty,
        locks_forbid=empty,
        gap_pairs=empty,
        calendars=calendar,
        preassignments=empty,
        bundle=_base_bundle(),
    )

    artifacts = build_model(context)
    add_coverage_constraints(context, artifacts)

    solver = cp_model.CpSolver()
    status = solver.Solve(artifacts.model)
    assert status in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    assert solver.Value(artifacts.coverage_under_role[(0, "INFERMIERE")]) == 1
    assert solver.Value(artifacts.coverage_under_group[0]) == 1


def test_coverage_group_weight_is_strictly_greater_and_dominant() -> None:
    employees = pd.DataFrame({"employee_id": ["E1"], "role": ["INFERMIERE"]})
    slots = pd.DataFrame(
        {
            "slot_id": [1],
            "shift_code": ["M"],
            "coverage_code": ["COV"],
            "reparto_id": ["REP1"],
            "date": [date(2025, 1, 1)],
        }
    )
    slot_requirements = pd.DataFrame(
        {
            "slot_id": [1],
            "role": ["INFERMIERE"],
            "demand": [1],
        }
    )
    coverage_totals = pd.DataFrame(
        {
            "coverage_code": ["COV"],
            "shift_code": ["M"],
            "reparto_id": ["REP1"],
            "total_staff": [1],
            "ruoli_totale": ["INFERMIERE"],
        }
    )
    calendar = pd.DataFrame({"data": [pd.Timestamp("2025-01-01")]})
    empty = pd.DataFrame()

    context = ModelContext(
        cfg={
            "weights": {
                "rest11": 500.0,
                "weekly_rest": 200.0,
                "coverage_under_role": 10.0,
                "coverage_under_group": 11.0,
            }
        },
        employees=employees,
        slots=slots,
        coverage_roles=empty,
        coverage_totals=coverage_totals,
        slot_requirements=slot_requirements,
        availability=empty,
        leaves=empty,
        history=empty,
        locks_must=empty,
        locks_forbid=empty,
        gap_pairs=empty,
        calendars=calendar,
        preassignments=empty,
        bundle=_base_bundle(),
    )

    artifacts = build_model(context)
    add_coverage_constraints(context, artifacts)

    by_component = {}
    for item in artifacts.objective_terms:
        by_component.setdefault(item.component, []).append(item.coeff)

    role_coeff = min(by_component["copertura_ruolo_scopertura"])
    group_coeff = min(by_component["copertura_gruppo_scopertura"])

    # Must dominate all configured non-coverage weights and keep strict group > role.
    assert role_coeff > int(500.0 * 1000)
    assert group_coeff > role_coeff


def test_coverage_dominance_uses_effective_objective_coefficients() -> None:
    employees = pd.DataFrame({"employee_id": ["E1"], "role": ["INFERMIERE"]})
    slots = pd.DataFrame(
        {
            "slot_id": [1],
            "shift_code": ["M"],
            "coverage_code": ["COV"],
            "reparto_id": ["REP1"],
            "date": [date(2025, 1, 1)],
        }
    )
    slot_requirements = pd.DataFrame(
        {
            "slot_id": [1],
            "role": ["INFERMIERE"],
            "demand": [1],
        }
    )
    coverage_totals = pd.DataFrame(
        {
            "coverage_code": ["COV"],
            "shift_code": ["M"],
            "reparto_id": ["REP1"],
            "total_staff": [1],
            "ruoli_totale": ["INFERMIERE"],
        }
    )
    calendar = pd.DataFrame({"data": [pd.Timestamp("2025-01-01")]})
    empty = pd.DataFrame()

    # Keep configured coverage weights tiny: coefficients must still dominate
    # effective objective coefficients already present in build_model.
    context = ModelContext(
        cfg={
            "weights": {
                "due_hours_under": 10_000.0,
                "coverage_under_role": 1.0,
                "coverage_under_group": 2.0,
            }
        },
        employees=employees,
        slots=slots,
        coverage_roles=empty,
        coverage_totals=coverage_totals,
        slot_requirements=slot_requirements,
        availability=empty,
        leaves=empty,
        history=empty,
        locks_must=empty,
        locks_forbid=empty,
        gap_pairs=empty,
        calendars=calendar,
        preassignments=empty,
        bundle=_base_bundle(),
    )

    artifacts = build_model(context)
    pre_max_coeff = max((int(term.coeff) for term in artifacts.objective_terms), default=0)
    add_coverage_constraints(context, artifacts)

    by_component = {}
    for item in artifacts.objective_terms:
        by_component.setdefault(item.component, []).append(item.coeff)

    role_coeff = min(by_component["copertura_ruolo_scopertura"])
    group_coeff = min(by_component["copertura_gruppo_scopertura"])

    assert role_coeff > pre_max_coeff
    assert group_coeff > role_coeff
