from __future__ import annotations

import pandas as pd
import pytest

from src.warm_start import (
    WarmStartError,
    apply_slot_warm_start_hints,
    load_slot_warm_start,
)


class _DummyModel:
    def __init__(self) -> None:
        self.hints: list[tuple[str, int]] = []

    def AddHint(self, var, value: int) -> None:  # noqa: N802 - API compatibility
        self.hints.append((str(var), int(value)))


def test_load_slot_warm_start_requires_columns(tmp_path) -> None:
    path = tmp_path / "warm.csv"
    pd.DataFrame({"employee": ["E1"], "slot_id": [1]}).to_csv(path, index=False)

    with pytest.raises(WarmStartError):
        load_slot_warm_start(path)


def test_load_slot_warm_start_normalizes_rows(tmp_path) -> None:
    path = tmp_path / "warm.csv"
    pd.DataFrame(
        {
            "employee_id": [" E1 ", "", "E2"],
            "slot_id": ["1", "2", "x"],
        }
    ).to_csv(path, index=False)

    loaded = load_slot_warm_start(path)

    assert loaded.to_dict(orient="records") == [
        {"employee_id": "E1", "slot_id": 1}
    ]


def test_apply_slot_warm_start_hints_best_effort() -> None:
    model = _DummyModel()
    assign_vars = {(0, 0): "x00", (0, 1): "x01"}
    bundle = {"eid_of": {"E1": 0}, "sid_of": {101: 0, 102: 1}}
    warm_df = pd.DataFrame(
        {
            "employee_id": ["E1", "E1", "E2", "E1", "E1"],
            "slot_id": [101, 101, 101, 999, 102],
        }
    )

    stats = apply_slot_warm_start_hints(
        model,
        assign_vars,
        bundle,
        warm_df,
        strict=False,
    )

    assert model.hints == [("x00", 1), ("x01", 1)]
    assert stats.rows_read == 5
    assert stats.rows_after_cleanup == 4
    assert stats.hints_applied == 2
    assert stats.duplicate_pairs == 1
    assert stats.unknown_employees == 1
    assert stats.unknown_slots == 1
    assert stats.ineligible_pairs == 0


def test_apply_slot_warm_start_hints_strict_raises() -> None:
    model = _DummyModel()
    assign_vars = {(0, 0): "x00"}
    bundle = {"eid_of": {"E1": 0}, "sid_of": {101: 0}}
    warm_df = pd.DataFrame({"employee_id": ["E1"], "slot_id": [999]})

    with pytest.raises(WarmStartError):
        apply_slot_warm_start_hints(
            model,
            assign_vars,
            bundle,
            warm_df,
            strict=True,
        )
