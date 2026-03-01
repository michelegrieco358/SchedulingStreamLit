from __future__ import annotations

from datetime import date

import pandas as pd

from src.load_data import _filter_loaded_data_for_departments


def test_filter_loaded_data_for_departments_filters_employees_slots_and_pools() -> None:
    data = {
        "employees": pd.DataFrame(
            {
                "employee_id": ["E_A", "E_B"],
                "reparto_id": ["A", "B"],
                "role": ["INF", "INF"],
                "pool_id": ["P1", "P1"],
            }
        ),
        "month_plan": pd.DataFrame(
            {
                "reparto_id": ["A", "B"],
                "data": ["2025-11-01", "2025-11-01"],
                "shift_code": ["M", "M"],
            }
        ),
        "shift_slots": pd.DataFrame(
            {
                "slot_id": [1, 2],
                "reparto_id": ["A", "B"],
                "shift_code": ["M", "M"],
            }
        ),
        "slot_requirements": pd.DataFrame(
            {
                "slot_id": [1, 2],
                "role": ["INF", "INF"],
                "required_count": [1, 1],
            }
        ),
        "role_dept_pools": pd.DataFrame(
            {
                "role": ["INF", "INF"],
                "pool_id": ["P1", "P1"],
                "reparto_id": ["A", "B"],
            }
        ),
        "availability": pd.DataFrame(
            {
                "employee_id": ["E_A", "E_B"],
                "data": ["2025-11-01", "2025-11-01"],
                "turno": ["M", "M"],
            }
        ),
    }

    data["employees_df"] = data["employees"]
    data["month_plan_df"] = data["month_plan"]
    data["shift_slots_df"] = data["shift_slots"]
    data["slot_requirements_df"] = data["slot_requirements"]
    data["role_dept_pools_df"] = data["role_dept_pools"]
    data["availability_df"] = data["availability"]

    filtered = _filter_loaded_data_for_departments(data, ["A"])

    assert filtered["employees"]["employee_id"].tolist() == ["E_A"]
    assert filtered["shift_slots"]["slot_id"].tolist() == [1]
    assert filtered["slot_requirements"]["slot_id"].tolist() == [1]
    assert filtered["month_plan"]["reparto_id"].tolist() == ["A"]
    assert filtered["role_dept_pools"]["reparto_id"].tolist() == ["A"]
    assert filtered["availability"]["employee_id"].tolist() == ["E_A"]


def test_filter_loaded_data_for_departments_filters_state_locks() -> None:
    """I lock su stato giornaliero (locks_state_*) vengono filtrati per employee_id.

    Garantisce che lock di dipendenti appartenenti a reparti esclusi non
    vengano trasmessi al preprocessing/solver per i reparti selezionati.
    """
    employees = pd.DataFrame(
        {
            "employee_id": ["E_A", "E_B"],
            "reparto_id": ["A", "B"],
            "role": ["INF", "INF"],
        }
    )
    # Entrambi i dipendenti hanno lock di stato
    locks_state = pd.DataFrame(
        {
            "employee_id": ["E_A", "E_B"],
            "date": [date(2025, 11, 1), date(2025, 11, 1)],
            "state_code": ["R", "R"],
            "lock": [1, 1],
            "note": ["", ""],
        }
    )
    locks_state_must = pd.DataFrame(
        {
            "employee_id": ["E_A", "E_B"],
            "date": [date(2025, 11, 1), date(2025, 11, 1)],
            "state_code": ["R", "R"],
        }
    )
    locks_state_forbid = pd.DataFrame(
        {
            "employee_id": ["E_A", "E_B"],
            "date": [date(2025, 11, 1), date(2025, 11, 1)],
            "state_code": ["F", "F"],
        }
    )
    # shift_slots minimale per poter calcolare employee_ids
    shift_slots = pd.DataFrame(
        {"slot_id": [1, 2], "reparto_id": ["A", "B"], "shift_code": ["M", "M"]}
    )

    data = {
        "employees": employees,
        "employees_df": employees,
        "shift_slots": shift_slots,
        "shift_slots_df": shift_slots,
        "locks_state_df": locks_state,
        "locks_state_must_df": locks_state_must,
        "locks_state_forbid_df": locks_state_forbid,
        # alias senza suffisso
        "locks_state": locks_state.copy(),
        "locks_state_must": locks_state_must.copy(),
        "locks_state_forbid": locks_state_forbid.copy(),
    }

    filtered = _filter_loaded_data_for_departments(data, ["A"])

    # Solo E_A appartiene al reparto A
    for key in (
        "locks_state_df",
        "locks_state_must_df",
        "locks_state_forbid_df",
        "locks_state",
        "locks_state_must",
        "locks_state_forbid",
    ):
        result_eids = filtered[key]["employee_id"].tolist()
        assert result_eids == ["E_A"], (
            f"{key}: atteso ['E_A'], trovato {result_eids}"
        )
