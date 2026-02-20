from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


class WarmStartError(Exception):
    """Errore durante il caricamento o l'applicazione dei warm-start hints."""


@dataclass(frozen=True)
class WarmStartStats:
    rows_read: int = 0
    rows_after_cleanup: int = 0
    hints_applied: int = 0
    unknown_employees: int = 0
    unknown_slots: int = 0
    ineligible_pairs: int = 0
    duplicate_pairs: int = 0


def load_slot_warm_start(path: str | Path) -> pd.DataFrame:
    """Load a slot-based warm-start file with required columns employee_id, slot_id."""

    warm_path = Path(path)
    if not warm_path.exists():
        raise WarmStartError(f"File warm start non trovato: {warm_path}")

    try:
        df = pd.read_csv(warm_path, dtype=str).fillna("")
    except Exception as exc:  # pragma: no cover - dipende da parser pandas
        raise WarmStartError(f"Impossibile leggere il file warm start: {warm_path}") from exc

    required = {"employee_id", "slot_id"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise WarmStartError(
            "Warm start CSV non valido: colonne mancanti "
            + ", ".join(missing)
            + ". Richieste: employee_id, slot_id"
        )

    work = df.loc[:, ["employee_id", "slot_id"]].copy()
    work["employee_id"] = work["employee_id"].astype(str).str.strip()
    work["slot_id"] = pd.to_numeric(work["slot_id"].astype(str).str.strip(), errors="coerce")
    work = work.dropna(subset=["employee_id", "slot_id"]).copy()
    work = work.loc[work["employee_id"].ne("")]
    if work.empty:
        return pd.DataFrame(columns=["employee_id", "slot_id"])

    work["slot_id"] = work["slot_id"].astype(int)
    return work.reset_index(drop=True)


def apply_slot_warm_start_hints(
    model: Any,
    assign_vars: Mapping[tuple[int, int], Any],
    bundle: Mapping[str, object],
    warm_start_df: pd.DataFrame,
    *,
    strict: bool = False,
) -> WarmStartStats:
    """Apply slot-based warm-start hints onto assignment variables."""

    if warm_start_df is None or warm_start_df.empty:
        return WarmStartStats(rows_read=0)

    eid_of: Mapping[str, int] = bundle.get("eid_of", {})  # type: ignore[assignment]
    sid_of: Mapping[int, int] = bundle.get("sid_of", {})  # type: ignore[assignment]

    rows_read = int(len(warm_start_df))
    work = warm_start_df.loc[:, ["employee_id", "slot_id"]].copy()
    work["employee_id"] = work["employee_id"].astype(str).str.strip()
    work["slot_id"] = pd.to_numeric(work["slot_id"], errors="coerce")
    work = work.dropna(subset=["employee_id", "slot_id"])
    work = work.loc[work["employee_id"].ne("")]
    if work.empty:
        return WarmStartStats(rows_read=rows_read)

    work["slot_id"] = work["slot_id"].astype(int)

    duplicate_count = int(work.duplicated(subset=["employee_id", "slot_id"]).sum())
    work = work.drop_duplicates(subset=["employee_id", "slot_id"], keep="first")

    unknown_employees = 0
    unknown_slots = 0
    ineligible_pairs = 0
    hints_applied = 0

    for employee_id, slot_id in work.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        emp_idx = eid_of.get(employee_id)
        if emp_idx is None:
            unknown_employees += 1
            if strict:
                raise WarmStartError(
                    f"Warm start contiene employee_id sconosciuto: {employee_id}"
                )
            continue

        slot_idx = sid_of.get(int(slot_id))
        if slot_idx is None:
            unknown_slots += 1
            if strict:
                raise WarmStartError(
                    f"Warm start contiene slot_id sconosciuto: {slot_id}"
                )
            continue

        var = assign_vars.get((emp_idx, slot_idx))
        if var is None:
            ineligible_pairs += 1
            if strict:
                raise WarmStartError(
                    "Warm start contiene coppia non candidabile "
                    f"(employee_id={employee_id}, slot_id={slot_id})"
                )
            continue

        model.AddHint(var, 1)
        hints_applied += 1

    return WarmStartStats(
        rows_read=rows_read,
        rows_after_cleanup=int(len(work)),
        hints_applied=hints_applied,
        unknown_employees=unknown_employees,
        unknown_slots=unknown_slots,
        ineligible_pairs=ineligible_pairs,
        duplicate_pairs=duplicate_count,
    )


__all__ = [
    "WarmStartError",
    "WarmStartStats",
    "apply_slot_warm_start_hints",
    "load_slot_warm_start",
]
