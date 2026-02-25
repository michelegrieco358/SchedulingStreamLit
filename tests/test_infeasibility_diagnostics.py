from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from src.diagnostics import (
    build_infeasibility_summary,
    write_infeasibility_summary_report,
)
from src.model import ModelContext


def _make_context(
    *,
    locks_must: pd.DataFrame | None = None,
    locks_forbid: pd.DataFrame | None = None,
    employees: pd.DataFrame | None = None,
    slots: pd.DataFrame | None = None,
    history: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> ModelContext:
    employees_df = (
        employees
        if employees is not None
        else pd.DataFrame(
            {"employee_id": ["E1"], "role": ["INFERMIERE"], "max_week_hours_h": [40.0]}
        )
    )
    slots_df = (
        slots
        if slots is not None
        else pd.DataFrame(
            {
                "slot_id": [1],
                "shift_code": ["M"],
                "date": [date(2025, 1, 1)],
                "duration_min": [480],
            }
        )
    )
    locks_must_df = (
        locks_must.copy()
        if locks_must is not None
        else pd.DataFrame(columns=["employee_id", "slot_id"])
    )
    locks_forbid_df = (
        locks_forbid.copy()
        if locks_forbid is not None
        else pd.DataFrame(columns=["employee_id", "slot_id"])
    )
    history_df = (
        history.copy()
        if history is not None
        else pd.DataFrame(columns=["data", "employee_id", "turno"])
    )

    empty = pd.DataFrame()
    bundle = {
        "eid_of": {"E1": 0},
        "emp_of": {0: "E1"},
        "sid_of": {int(slot_id): idx for idx, slot_id in enumerate(slots_df["slot_id"])},
        "slot_of": {idx: int(slot_id) for idx, slot_id in enumerate(slots_df["slot_id"])},
        "did_of": {date(2025, 1, 1): 0},
        "date_of": {0: date(2025, 1, 1)},
        "num_employees": len(employees_df),
        "num_slots": len(slots_df),
        "num_days": 1,
        "eligible_eids": {idx: [0] for idx in range(len(slots_df))},
        "slot_date2": {idx: 0 for idx in range(len(slots_df))},
    }

    return ModelContext(
        cfg=cfg or {},
        employees=employees_df,
        slots=slots_df,
        coverage_roles=empty,
        coverage_totals=empty,
        slot_requirements=empty,
        availability=empty,
        leaves=empty,
        history=history_df,
        locks_must=locks_must_df,
        locks_forbid=locks_forbid_df,
        gap_pairs=empty,
        calendars=empty,
        preassignments=empty,
        bundle=bundle,
    )


def test_detects_must_lock_same_day_conflict() -> None:
    context = _make_context(
        locks_must=pd.DataFrame(
            {"employee_id": ["E1", "E1"], "slot_id": [1, 2]}
        ),
        slots=pd.DataFrame(
            {
                "slot_id": [1, 2],
                "shift_code": ["M", "P"],
                "date": [date(2025, 1, 1), date(2025, 1, 1)],
                "duration_min": [480, 480],
            }
        ),
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_same_day_conflict" in codes


def test_detects_must_lock_week_hour_cap_conflict() -> None:
    context = _make_context(
        employees=pd.DataFrame(
            {"employee_id": ["E1"], "role": ["INFERMIERE"], "max_week_hours_h": [8.0]}
        ),
        slots=pd.DataFrame(
            {
                "slot_id": [1, 2],
                "shift_code": ["M", "M"],
                "date": [date(2025, 1, 1), date(2025, 1, 2)],
                "duration_min": [480, 480],
            }
        ),
        locks_must=pd.DataFrame({"employee_id": ["E1", "E1"], "slot_id": [1, 2]}),
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_week_cap_conflict" in codes


def test_detects_must_forbid_same_pair_conflict() -> None:
    context = _make_context(
        locks_must=pd.DataFrame({"employee_id": ["E1"], "slot_id": [1]}),
        locks_forbid=pd.DataFrame({"employee_id": ["E1"], "slot_id": [1]}),
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_forbid_same_pair_conflict" in codes


def test_detects_must_lock_night_consecutive_conflict() -> None:
    context = _make_context(
        cfg={
            "shift_types": {"night_codes": ["N"]},
            "defaults": {"night": {"max_consecutive_nights": 2}},
        },
        slots=pd.DataFrame(
            {
                "slot_id": [1, 2, 3],
                "shift_code": ["N", "N", "N"],
                "date": [date(2025, 1, 1), date(2025, 1, 2), date(2025, 1, 3)],
                "duration_min": [480, 480, 480],
                "is_night": [True, True, True],
            }
        ),
        locks_must=pd.DataFrame({"employee_id": ["E1", "E1", "E1"], "slot_id": [1, 2, 3]}),
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_night_consecutive_conflict" in codes


def test_detects_must_lock_night_week_cap_with_history() -> None:
    context = _make_context(
        cfg={
            "shift_types": {"night_codes": ["N"]},
            "defaults": {"night": {"max_per_week": 2}},
        },
        slots=pd.DataFrame(
            {
                "slot_id": [1],
                "shift_code": ["N"],
                "date": [date(2025, 1, 8)],
                "duration_min": [480],
                "is_night": [True],
            }
        ),
        locks_must=pd.DataFrame({"employee_id": ["E1"], "slot_id": [1]}),
        history=pd.DataFrame(
            {
                "data": ["2025-01-06", "2025-01-07"],
                "employee_id": ["E1", "E1"],
                "turno": ["N", "N"],
            }
        ),
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_night_week_cap_conflict" in codes


def test_detects_must_lock_leave_conflict() -> None:
    context = _make_context(
        slots=pd.DataFrame(
            {
                "slot_id": [1],
                "shift_code": ["M"],
                "date": [date(2025, 1, 10)],
                "duration_min": [480],
            }
        ),
        locks_must=pd.DataFrame({"employee_id": ["E1"], "slot_id": [1]}),
    )
    context = ModelContext(
        cfg=context.cfg,
        employees=context.employees,
        slots=context.slots,
        coverage_roles=context.coverage_roles,
        coverage_totals=context.coverage_totals,
        slot_requirements=context.slot_requirements,
        availability=context.availability,
        leaves=pd.DataFrame({"employee_id": ["E1"], "date": [date(2025, 1, 10)]}),
        history=context.history,
        locks_must=context.locks_must,
        locks_forbid=context.locks_forbid,
        gap_pairs=context.gap_pairs,
        calendars=context.calendars,
        preassignments=context.preassignments,
        bundle=context.bundle,
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_leave_conflict" in codes


def test_detects_must_lock_night_eligibility_conflict() -> None:
    context = _make_context(
        employees=pd.DataFrame(
            {
                "employee_id": ["E1"],
                "role": ["INFERMIERE"],
                "can_work_night": [False],
            }
        ),
        slots=pd.DataFrame(
            {
                "slot_id": [1],
                "shift_code": ["N"],
                "date": [date(2025, 1, 11)],
                "duration_min": [480],
                "is_night": [True],
            }
        ),
        locks_must=pd.DataFrame({"employee_id": ["E1"], "slot_id": [1]}),
        cfg={"shift_types": {"night_codes": ["N"]}},
    )

    summary = build_infeasibility_summary(context)
    codes = [entry["code"] for entry in summary["top_causes"]]
    assert "must_lock_night_eligibility_conflict" in codes


def test_writes_infeasibility_report(tmp_path: Path) -> None:
    context = _make_context()
    summary = build_infeasibility_summary(context)
    report_path = tmp_path / "diag.txt"

    written = write_infeasibility_summary_report(summary, report_path)
    assert written == report_path
    text = report_path.read_text(encoding="utf-8")
    assert "Diagnosi infeasibilita'" in text
    assert "Top cause:" in text


def test_returns_fallback_when_no_static_conflicts_found() -> None:
    context = _make_context()
    summary = build_infeasibility_summary(context)
    assert summary["status"] == "INFEASIBLE"
    assert summary["top_causes"][0]["code"] == "no_static_conflict_detected"
