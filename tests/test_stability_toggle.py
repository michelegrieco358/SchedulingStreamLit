from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from src.model import ModelContext, build_model


def _make_context(
    *,
    cfg: dict | None = None,
    preassignment_pairs: list[tuple[int, int, str]] | None = None,
) -> ModelContext:
    employees = pd.DataFrame({"employee_id": ["E1"], "role": ["INFERMIERE"]})
    slots = pd.DataFrame(
        {
            "slot_id": [1],
            "shift_code": ["M"],
            "date": [date(2025, 1, 1)],
        }
    )
    empty = pd.DataFrame()

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
        "preassignment_pairs": preassignment_pairs or [],
    }

    base_cfg = {
        "weights": {"preassignment_change": 5.0},
        "preassignments": {"stability_enabled": True},
    }
    if cfg:
        base_cfg.update(cfg)

    preassignments = pd.DataFrame(columns=["employee_id", "data", "state_code"])

    return ModelContext(
        cfg=base_cfg,
        employees=employees,
        slots=slots,
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
        preassignments=preassignments,
        bundle=bundle,
    )


def _has_preassignment_terms(context: ModelContext, *, stability_enabled: bool | None) -> bool:
    artifacts = build_model(context, stability_enabled=stability_enabled)
    return any(term.component == "preassegnazioni" for term in artifacts.objective_terms)


def test_runtime_off_disables_preassignment_terms() -> None:
    context = _make_context(preassignment_pairs=[(0, 0, "M")])
    assert _has_preassignment_terms(context, stability_enabled=False) is False


def test_runtime_on_enables_preassignment_terms() -> None:
    context = _make_context(preassignment_pairs=[(0, 0, "M")])
    assert _has_preassignment_terms(context, stability_enabled=True) is True


def test_config_default_true_enables_terms() -> None:
    context = _make_context(preassignment_pairs=[(0, 0, "M")])
    assert _has_preassignment_terms(context, stability_enabled=None) is True


def test_missing_preassignments_with_stability_on_is_non_blocking() -> None:
    context = _make_context(preassignment_pairs=[])
    with pytest.warns(
        UserWarning,
        match="Stabilita' attiva ma nessuna preassegnazione disponibile",
    ):
        artifacts = build_model(context, stability_enabled=True)

    assert isinstance(artifacts.objective_terms, tuple)
    assert not any(term.component == "preassegnazioni" for term in artifacts.objective_terms)
