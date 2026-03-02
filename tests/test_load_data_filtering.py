from __future__ import annotations

from datetime import date
import warnings

import pandas as pd

import src.load_data as load_data_mod
from src.load_data import (
    _build_absences_alias,
    _filter_loaded_data_for_departments,
    load_context,
)


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


def test_build_absences_alias_normalizes_single_kind_column_with_priority() -> None:
    frame = pd.DataFrame(
        {
            "employee_id": ["E1", "E2", "E3", "E4"],
            "date": ["2025-11-01", "2025-11-02", "2025-11-03", "2025-11-04"],
            "kind": ["", "full_day", "", ""],
            "tipo": ["half_day", "", "full-day", ""],
            "tipo_set": ["legacy", "legacy2", "", "legacy4"],
        }
    )

    alias = _build_absences_alias({"leaves_days_df": frame})

    assert alias is not None
    assert list(alias.columns) == ["employee_id", "date", "kind"]
    assert alias.loc[alias["employee_id"] == "E1", "kind"].iloc[0] == "half_day"
    assert alias.loc[alias["employee_id"] == "E2", "kind"].iloc[0] == "full_day"
    assert alias.loc[alias["employee_id"] == "E3", "kind"].iloc[0] == "full-day"
    assert alias.loc[alias["employee_id"] == "E4", "kind"].iloc[0] == "legacy4"


def test_build_absences_alias_treats_pd_na_as_missing() -> None:
    frame = pd.DataFrame(
        {
            "employee_id": ["E1"],
            "date": ["2025-11-01"],
            "kind": [pd.NA],
        }
    )

    alias = _build_absences_alias({"leaves_days_df": frame})

    assert alias is not None
    assert alias.loc[0, "kind"] == "full_day"


def test_build_absences_alias_uses_is_absent_fallback_when_type_missing() -> None:
    frame = pd.DataFrame(
        {
            "employee_id": ["E1", "E2"],
            "date": ["2025-11-01", "2025-11-01"],
            "is_absent": [True, False],
        }
    )

    alias = _build_absences_alias({"leaves_days_df": frame})

    assert alias is not None
    e1 = alias.loc[alias["employee_id"] == "E1", "kind"].iloc[0]
    e2 = alias.loc[alias["employee_id"] == "E2", "kind"].iloc[0]
    assert e1 == "full_day"
    assert pd.isna(e2)


def test_load_context_selected_departments_fallbacks_to_observed_data(monkeypatch) -> None:
    data = {
        "cfg": {"defaults": {}, "scheduling": {}},
        "employees": pd.DataFrame({"employee_id": ["E1"], "reparto_id": ["REP_A"]}),
        "employees_df": pd.DataFrame({"employee_id": ["E1"], "reparto_id": ["REP_A"]}),
        "month_plan": pd.DataFrame({"reparto_id": ["REP_A"]}),
        "month_plan_df": pd.DataFrame({"reparto_id": ["REP_A"]}),
    }

    monkeypatch.setattr(load_data_mod, "load_all_data", lambda *a, **k: data)
    monkeypatch.setattr(load_data_mod, "_build_bundle", lambda d, c: {"ok": True})
    monkeypatch.setattr(load_data_mod, "build_context_from_data", lambda d, b: object())

    context, filtered_data, _bundle = load_context("dummy_cfg", "dummy_data", selected_departments=["REP_A"])
    assert context is not None
    assert filtered_data["cfg"]["scheduling"]["selected_departments"] == ["REP_A"]


def test_load_context_warns_when_defaults_missing_but_dataset_contains_department(monkeypatch) -> None:
    data = {
        "cfg": {"defaults": {"departments": ["REP_X"]}, "scheduling": {}},
        "employees": pd.DataFrame({"employee_id": ["E1"], "reparto_id": ["REP_A"]}),
        "employees_df": pd.DataFrame({"employee_id": ["E1"], "reparto_id": ["REP_A"]}),
        "month_plan": pd.DataFrame({"reparto_id": ["REP_A"]}),
        "month_plan_df": pd.DataFrame({"reparto_id": ["REP_A"]}),
    }

    monkeypatch.setattr(load_data_mod, "load_all_data", lambda *a, **k: data)
    monkeypatch.setattr(load_data_mod, "_build_bundle", lambda d, c: {"ok": True})
    monkeypatch.setattr(load_data_mod, "build_context_from_data", lambda d, b: object())

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        load_context("dummy_cfg", "dummy_data", selected_departments=["REP_A"])

    assert any("osservati nel dataset" in str(w.message) for w in captured)
