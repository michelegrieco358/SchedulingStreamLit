from __future__ import annotations

import pandas as pd

from src.model import ModelContext, _extract_employee_hour_params


def test_extract_employee_hour_params_handles_non_consecutive_index() -> None:
    employees = pd.DataFrame(
        {
            "employee_id": ["E1"],
            "role": ["INFERMIERE"],
            "ore_dovute_mese_h": [pd.NA],
        },
        index=[10],
    )

    empty = pd.DataFrame()
    context = ModelContext(
        cfg={"defaults": {"contract_hours_by_role_h": {"INFERMIERE": 160}}},
        employees=employees,
        slots=empty,
        coverage_roles=empty,
        coverage_totals=empty,
        slot_requirements=empty,
        availability=empty,
        leaves=empty,
        history=empty,
        locks_must=empty,
        locks_forbid=empty,
        gap_pairs=empty,
        calendars=empty,
        preassignments=empty,
        bundle={"eid_of": {"E1": 0}},
    )

    params = _extract_employee_hour_params(context, context.bundle)

    assert params[0]["due_minutes"] == 160 * 60
