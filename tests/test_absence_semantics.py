from __future__ import annotations

from datetime import date

import pandas as pd

from src.model import _collect_absence_pairs
from src.preprocessing import _build_absence_index, _build_absence_pairs


def test_collect_absence_pairs_ignores_partial_kind() -> None:
    leaves = pd.DataFrame(
        {
            "employee_id": ["E1"],
            "date": ["2025-01-01"],
            "kind": ["partial"],
            "is_absent": [True],
        }
    )
    eid_of = {"E1": 0}
    did_of = {date(2025, 1, 1): 0}

    pairs = _collect_absence_pairs(leaves, eid_of, did_of)
    assert pairs == set()


def test_collect_absence_pairs_accepts_full_day_kind() -> None:
    leaves = pd.DataFrame(
        {
            "employee_id": ["E1"],
            "date": ["2025-01-01"],
            "kind": ["full_day"],
        }
    )
    eid_of = {"E1": 0}
    did_of = {date(2025, 1, 1): 0}

    pairs = _collect_absence_pairs(leaves, eid_of, did_of)
    assert pairs == {(0, 0)}


def test_preprocessing_and_model_share_full_day_semantics() -> None:
    leaves = pd.DataFrame(
        {
            "employee_id": ["E1", "E1", "E2"],
            "date": ["2025-01-01", "2025-01-02", "2025-01-01"],
            "kind": ["full_day", "partial", "full-day"],
        }
    )
    eid_of = {"E1": 0, "E2": 1}
    did_of = {date(2025, 1, 1): 0, date(2025, 1, 2): 1}

    absence_tbl = _build_absence_index(leaves)
    pre_pairs = set(_build_absence_pairs(absence_tbl, eid_of, did_of))
    model_pairs = _collect_absence_pairs(leaves, eid_of, did_of)

    assert pre_pairs == model_pairs
    assert pre_pairs == {(0, 0), (1, 0)}


def test_collect_absence_pairs_date_range_skips_non_full_day_records() -> None:
    leaves = pd.DataFrame(
        {
            "employee_id": ["E1", "E2"],
            "date_from": ["2025-01-01", "2025-01-01"],
            "date_to": ["2025-01-02", "2025-01-02"],
            "kind": ["hourly", "full"],
        }
    )
    eid_of = {"E1": 0, "E2": 1}
    did_of = {date(2025, 1, 1): 0, date(2025, 1, 2): 1}

    pairs = _collect_absence_pairs(leaves, eid_of, did_of)
    assert pairs == {(1, 0), (1, 1)}

