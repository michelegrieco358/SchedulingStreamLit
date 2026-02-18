from __future__ import annotations

import pandas as pd

from loader.gap_pairs import build_gap_pairs



def _make_slots() -> pd.DataFrame:
    tz = "Europe/Rome"
    return pd.DataFrame(
        {
            "slot_id": [1, 2, 3],
            "reparto_id": ["A", "B", "A"],
            "start_dt": pd.to_datetime(
                [
                    "2025-11-01 07:00:00",
                    "2025-11-01 15:00:00",
                    "2025-11-02 07:00:00",
                ]
            ).tz_localize(tz),
            "end_dt": pd.to_datetime(
                [
                    "2025-11-01 14:00:00",
                    "2025-11-01 22:00:00",
                    "2025-11-02 14:00:00",
                ]
            ).tz_localize(tz),
        }
    )


def test_build_gap_pairs_default_excludes_cross_department() -> None:
    slots = _make_slots()

    result = build_gap_pairs(slots, max_check_window_h=12, add_debug=False)

    pairs = {(int(r.s1_id), int(r.s2_id)) for r in result.itertuples(index=False)}
    assert (1, 2) not in pairs


def test_build_gap_pairs_can_include_cross_department() -> None:
    slots = _make_slots()

    result = build_gap_pairs(
        slots,
        max_check_window_h=12,
        include_cross_department=True,
        add_debug=False,
    )

    pairs = {(int(r.s1_id), int(r.s2_id)) for r in result.itertuples(index=False)}
    assert (1, 2) in pairs
