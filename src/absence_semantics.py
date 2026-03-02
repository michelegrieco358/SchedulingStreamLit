from __future__ import annotations

import re
from typing import Iterable

import pandas as pd


_FULL_DAY_TOKENS = {"full_day", "full-day", "full"}
_TRUE_VALUES = {"1", "true", "t", "yes", "y", "si", "sì"}


def _tokenize(value: object) -> list[str]:
    if value is None or pd.isna(value):
        return []
    text = str(value).strip().lower()
    if text in {"", "nan", "<na>", "none"}:
        return []
    return [tok for tok in re.split(r"[|,;]", text) if tok]


def _is_full_day_value(value: object) -> bool:
    tokens = _tokenize(value)
    return any(token in _FULL_DAY_TOKENS for token in tokens)


def _coerce_bool_series(series: pd.Series) -> pd.Series:
    def _coerce(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and not pd.isna(value):
            return bool(int(value))
        text = str(value).strip().lower()
        return text in _TRUE_VALUES

    return series.map(_coerce).astype(bool)


def build_full_day_absence_mask(df: pd.DataFrame) -> pd.Series:
    """Return mask for rows representing full-day absences.

    Rule:
    - if a type column exists (kind/tipo/tipo_set/type), use only that semantic;
    - fallback to ``is_absent`` only when no type column exists;
    - if neither exists, keep backward-compatible behavior (all rows True).
    """
    if df is None or df.empty:
        return pd.Series(dtype=bool, index=df.index if df is not None else None)

    type_columns: list[str] = [
        col for col in ("kind", "tipo", "tipo_set", "type") if col in df.columns
    ]
    if type_columns:
        mask = pd.Series(False, index=df.index)
        for col in type_columns:
            mask |= df[col].map(_is_full_day_value)
        return mask.astype(bool)

    if "is_absent" in df.columns:
        return _coerce_bool_series(df["is_absent"])

    return pd.Series(True, index=df.index, dtype=bool)

