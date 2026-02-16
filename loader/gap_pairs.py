"""Utility per la generazione delle coppie di turni incompatibili per riposo."""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS: set[str] = {
    "slot_id",
    "reparto_id",
    "start_dt",
    "end_dt",
}


def _ensure_required_columns(df: pd.DataFrame, columns: Iterable[str]) -> None:
    """Verifica che il DataFrame contenga tutte le colonne richieste."""

    missing = set(columns) - set(df.columns)
    if missing:
        missing_str = ", ".join(sorted(missing))
        raise ValueError(f"Colonne mancanti in shift_slots: {missing_str}")


def _to_naive_utc(series: pd.Series) -> pd.Series:
    """Converte una serie datetime tz-aware in naive su UTC."""

    if not isinstance(series.dtype, pd.DatetimeTZDtype):
        raise TypeError("Le colonne start_dt e end_dt devono essere datetime tz-aware")
    return series.dt.tz_convert("UTC").dt.tz_localize(None)


def _iso_year_week_of(ts: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Restituisce (iso_year, iso_week) da una Series datetime tz-aware."""

    if not isinstance(ts.dtype, pd.DatetimeTZDtype):
        raise TypeError("La serie deve contenere datetime tz-aware")

    iso = ts.dt.isocalendar()
    return iso["year"], iso["week"]


def build_gap_pairs(
    shift_slots: pd.DataFrame,
    max_check_window_h: int = 15,
    handover_minutes: int = 0,
    *,
    include_cross_reparto_pairs: bool = False,
    add_debug: bool = True,
) -> pd.DataFrame:
    """Costruisce la tabella delle coppie di slot incompatibili per riposo."""

    if max_check_window_h <= 0:
        raise ValueError("max_check_window_h deve essere positivo")
    if handover_minutes < 0:
        raise ValueError("handover_minutes deve essere >= 0")
    if not isinstance(include_cross_reparto_pairs, bool):
        raise TypeError("include_cross_reparto_pairs deve essere booleano")

    _ensure_required_columns(shift_slots, REQUIRED_COLUMNS)

    has_shift_code = "shift_code" in shift_slots.columns
    has_in_scope = "in_scope" in shift_slots.columns

    reparto_dtype = shift_slots["reparto_id"].dtype if "reparto_id" in shift_slots else "object"
    slot_dtype = shift_slots["slot_id"].dtype if "slot_id" in shift_slots else "int64"

    base_columns = {
        "reparto_id": pd.Series(dtype=reparto_dtype),
        "s1_id": pd.Series(dtype=slot_dtype),
        "s2_id": pd.Series(dtype=slot_dtype),
        "gap_hours": pd.Series(dtype="float64"),
    }

    if add_debug:
        tz_dtype = pd.DatetimeTZDtype(tz="Europe/Rome")
        debug_columns: dict[str, pd.Series] = {
            "s1_end_dt": pd.Series(dtype=tz_dtype),
            "s2_start_dt": pd.Series(dtype=tz_dtype),
            "s1_end_date": pd.Series(dtype="object"),
            "s2_start_date": pd.Series(dtype="object"),
            "s1_iso_year": pd.Series(dtype=pd.UInt32Dtype()),
            "s1_iso_week": pd.Series(dtype=pd.UInt32Dtype()),
            "s2_iso_year": pd.Series(dtype=pd.UInt32Dtype()),
            "s2_iso_week": pd.Series(dtype=pd.UInt32Dtype()),
        }
        if has_shift_code:
            shift_dtype = shift_slots["shift_code"].dtype
            debug_columns["s1_shift_code"] = pd.Series(dtype=shift_dtype)
            debug_columns["s2_shift_code"] = pd.Series(dtype=shift_dtype)
        if has_in_scope:
            scope_dtype = shift_slots["in_scope"].dtype
            debug_columns["s1_in_scope"] = pd.Series(dtype=scope_dtype)
            debug_columns["s2_in_scope"] = pd.Series(dtype=scope_dtype)
            debug_columns["pair_crosses_scope"] = pd.Series(dtype="bool")
        base_columns.update(debug_columns)

    if shift_slots.empty:
        return pd.DataFrame(base_columns)

    result_frames: list[pd.DataFrame] = []

    if include_cross_reparto_pairs:
        grouped = [(None, shift_slots)]
    else:
        grouped = shift_slots.groupby("reparto_id", sort=False, dropna=False)

    for _group_reparto_id, group in grouped:
        group_sorted = group.sort_values("start_dt").reset_index(drop=True)

        start_naive = _to_naive_utc(group_sorted["start_dt"])  # naive per searchsorted
        end_naive = _to_naive_utc(group_sorted["end_dt"])

        start_values = start_naive.to_numpy(dtype="datetime64[ns]")
        end_values = end_naive.to_numpy(dtype="datetime64[ns]")

        window_delta = np.timedelta64(max_check_window_h, "h")

        left_idx = np.searchsorted(start_values, end_values, side="right")
        right_idx = np.searchsorted(start_values, end_values + window_delta, side="right")

        counts = right_idx - left_idx
        total_pairs = int(counts.sum())
        if total_pairs == 0:
            continue

        s1_idx = np.repeat(np.arange(len(group_sorted), dtype=int), counts)

        s2_idx = np.empty(total_pairs, dtype=int)
        cursor = 0
        for l_idx, r_idx in zip(left_idx, right_idx):
            span = r_idx - l_idx
            if span <= 0:
                continue
            s2_idx[cursor : cursor + span] = np.arange(l_idx, r_idx)
            cursor += span

        s1_end = group_sorted["end_dt"].iloc[s1_idx].reset_index(drop=True)
        s2_start = group_sorted["start_dt"].iloc[s2_idx].reset_index(drop=True)

        gap_delta = s2_start - s1_end
        gap_hours = gap_delta.dt.total_seconds().to_numpy() / 3600.0

        handover_hours = handover_minutes / 60.0
        gap_hours_eff = np.maximum(gap_hours - handover_hours, 0.0)

        valid_mask = (gap_hours_eff > 0) & (gap_hours_eff <= float(max_check_window_h))

        if not np.any(valid_mask):
            continue

        s1_valid = s1_idx[valid_mask]
        s2_valid = s2_idx[valid_mask]

        gap_valid = gap_hours_eff[valid_mask]

        s1_reparto = group_sorted["reparto_id"].iloc[s1_valid].to_numpy()

        pairs_df = pd.DataFrame(
            {
                "reparto_id": s1_reparto,
                "s1_id": group_sorted["slot_id"].iloc[s1_valid].to_numpy(),
                "s2_id": group_sorted["slot_id"].iloc[s2_valid].to_numpy(),
                "gap_hours": gap_valid,
            }
        )

        if add_debug:
            s1_end_valid = s1_end.iloc[valid_mask].reset_index(drop=True)
            s2_start_valid = s2_start.iloc[valid_mask].reset_index(drop=True)

            pairs_df["s1_end_dt"] = s1_end_valid
            pairs_df["s2_start_dt"] = s2_start_valid
            pairs_df["s1_end_date"] = s1_end_valid.dt.date
            pairs_df["s2_start_date"] = s2_start_valid.dt.date

            s1_iso_year, s1_iso_week = _iso_year_week_of(s1_end_valid)
            s2_iso_year, s2_iso_week = _iso_year_week_of(s2_start_valid)
            pairs_df["s1_iso_year"] = s1_iso_year.reset_index(drop=True)
            pairs_df["s1_iso_week"] = s1_iso_week.reset_index(drop=True)
            pairs_df["s2_iso_year"] = s2_iso_year.reset_index(drop=True)
            pairs_df["s2_iso_week"] = s2_iso_week.reset_index(drop=True)

            if has_shift_code:
                s1_shift = group_sorted["shift_code"].iloc[s1_valid].reset_index(drop=True)
                s2_shift = group_sorted["shift_code"].iloc[s2_valid].reset_index(drop=True)
                pairs_df["s1_shift_code"] = s1_shift
                pairs_df["s2_shift_code"] = s2_shift

            if has_in_scope:
                s1_scope = group_sorted["in_scope"].iloc[s1_valid].reset_index(drop=True)
                s2_scope = group_sorted["in_scope"].iloc[s2_valid].reset_index(drop=True)
                pairs_df["s1_in_scope"] = s1_scope
                pairs_df["s2_in_scope"] = s2_scope
                pairs_df["pair_crosses_scope"] = (~s1_scope.fillna(False)) & s2_scope.fillna(False)

        result_frames.append(pairs_df.reset_index(drop=True))

    if not result_frames:
        return pd.DataFrame(base_columns)

    result_df = pd.concat(result_frames, ignore_index=True)
    result_df = result_df.drop_duplicates(subset=["s1_id", "s2_id"])
    result_df = result_df.sort_values(["s1_id", "s2_id"]).reset_index(drop=True)

    return result_df


def build_overlap_pairs(shift_slots: pd.DataFrame) -> pd.DataFrame:
    """Costruisce la tabella delle coppie di slot con stesso shift_code che si sovrappongono nel tempo.

    Restituisce un DataFrame con colonne ["s1_id", "s2_id"] dove s1_id < s2_id.
    Usato dal modello per aggiungere vincoli hard assign1 + assign2 <= 1.
    """
    required = {"slot_id", "shift_code", "start_dt", "end_dt"}
    missing = required - set(shift_slots.columns)
    if missing:
        raise ValueError(f"Colonne mancanti in shift_slots: {', '.join(sorted(missing))}")

    empty = pd.DataFrame({"s1_id": pd.Series(dtype="int64"),
                          "s2_id": pd.Series(dtype="int64")})

    df = shift_slots.copy()

    # Filtra solo slot con orario reale (R, SN, F hanno duration_min=0 e nessun orario)
    if "duration_min" in df.columns:
        df = df.loc[df["duration_min"].fillna(0).astype(float) > 0]

    if df.empty:
        return empty

    # Ricava la data di calendario per raggruppamento efficiente
    if "data_dt" in df.columns:
        df["_cal_date"] = pd.to_datetime(df["data_dt"], errors="coerce").dt.date
    else:
        df["_cal_date"] = pd.to_datetime(df["start_dt"], errors="coerce").dt.date

    keep = ["slot_id", "shift_code", "start_dt", "end_dt", "_cal_date"]
    df = df.loc[:, [c for c in keep if c in df.columns]].copy()
    df["start_dt"] = pd.to_datetime(df["start_dt"], utc=True, errors="coerce")
    df["end_dt"] = pd.to_datetime(df["end_dt"], utc=True, errors="coerce")
    df = df.dropna(subset=["start_dt", "end_dt"])

    if df.empty:
        return empty

    result_frames: list[pd.DataFrame] = []

    # Raggruppa per (shift_code, data di calendario):
    # solo slot dello stesso tipo nella stessa data possono sovrapporsi.
    for (_shift_code, _cal_date), group in df.groupby(
        ["shift_code", "_cal_date"], sort=False, dropna=False
    ):
        if len(group) < 2:
            continue

        left = group.rename(columns={"slot_id": "s1_id", "start_dt": "s1_start", "end_dt": "s1_end"})
        right = group.rename(columns={"slot_id": "s2_id", "start_dt": "s2_start", "end_dt": "s2_end"})

        merged = left.loc[:, ["s1_id", "s1_start", "s1_end"]].merge(
            right.loc[:, ["s2_id", "s2_start", "s2_end"]],
            how="cross",
        )

        # Tieni solo s1_id < s2_id per evitare duplicati e auto-coppie
        merged = merged.loc[merged["s1_id"] < merged["s2_id"]]

        if merged.empty:
            continue

        # Maschera di overlap: s1_start < s2_end AND s2_start < s1_end
        overlap_mask = (merged["s1_start"] < merged["s2_end"]) & (merged["s2_start"] < merged["s1_end"])
        overlaps = merged.loc[overlap_mask, ["s1_id", "s2_id"]]

        if not overlaps.empty:
            result_frames.append(overlaps)

    if not result_frames:
        return empty

    result = pd.concat(result_frames, ignore_index=True)
    return result.drop_duplicates().reset_index(drop=True)


__all__ = ["build_gap_pairs", "build_overlap_pairs", "_iso_year_week_of"]
