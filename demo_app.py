"""
SKYScheduler DEMO — Piano di Programmazione Mensile
Replica dell'interfaccia SKYppm HTML.
"""
from __future__ import annotations

import base64
import copy
from datetime import date, datetime, timedelta
import html as _html
import io
import inspect
import logging
import math
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

import pandas as pd
import yaml
import streamlit as st
from st_click_detector import click_detector

LOGGER = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# ── Logo (base64 for embedding in HTML) ──────────────────────────────────────
_logo_path = PROJECT_ROOT / "Immagine1.png"
_LOGO_B64 = base64.b64encode(_logo_path.read_bytes()).decode() if _logo_path.exists() else ""
_LOGO_IMG = (
    f'<div style="background:white;border-radius:8px;padding:5px 12px;'
    f'display:flex;align-items:center;box-shadow:0 1px 4px rgba(0,0,0,0.15);">'
    f'<img src="data:image/png;base64,{_LOGO_B64}" style="height:30px;object-fit:contain;">'
    f'</div>'
    if _LOGO_B64 else ""
)

from demo.styles import inject_css, GRID_CSS

# Solver opzionale: disponibile solo se le dipendenze (ortools ecc.) sono installate
try:
    from src.load_data import load_all_data as _load_all_data
    from src.solve_service import solve_schedule_from_data as _solve
    _SOLVER_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _SOLVER_AVAILABLE = False

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="SKYppm - Piano Programmazione Mensile",
    page_icon="\U0001f4c5",
    layout="wide",
    initial_sidebar_state="expanded",
)
inject_css()

# ── Constants ────────────────────────────────────────────────────────────────
DAY_LETTERS = {0: "L", 1: "M", 2: "M", 3: "G", 4: "V", 5: "S", 6: "D"}
MONTH_NAMES = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}
FIXED_HOLIDAYS = {
    (1, 1), (6, 1), (25, 4), (1, 5), (2, 6),
    (15, 8), (1, 11), (8, 12), (25, 12), (26, 12),
}
TIME_PRESETS = {"Veloce (30s)": 30, "Standard (60s)": 60, "Avanzata (300s)": 300}

_DATASET_RESET_KEYS: tuple[str, ...] = (
    "draft",
    "view_draft",
    "draft_view_radio",
    "grid_selection",
    "_ottimizza_req",
    "_cov_dlg_req",
    "calc_params",
    "show_coverage",
    "show_filters",
    "view_reparto",
    "view_role",
    "view_employee",
    "cov_selection",
    "_cov_click_counter",
    "_show_cov_counter",
    "_filtri_counter",
    "_det_counter",
    "_clear_counter",
)

_DRAFT_ONLY_KEYS: tuple[str, ...] = (
    "draft",
    "view_draft",
    "draft_view_radio",
)


def _clear_session_keys(keys: tuple[str, ...]) -> None:
    for key in keys:
        st.session_state.pop(key, None)


def _drop_draft_state() -> None:
    _clear_session_keys(_DRAFT_ONLY_KEYS)


def _queue_warm_start_from_calc_params() -> bool:
    calc_params = st.session_state.get("calc_params")
    if not _has_valid_calc_params(calc_params):
        return False
    next_req = dict(calc_params)
    next_req["use_warm_start"] = True
    st.session_state["_ottimizza_req"] = next_req
    return True


def _has_valid_calc_params(calc_params: object) -> bool:
    required = {"start", "end", "cross", "time_s", "reparti", "stability"}
    return bool(isinstance(calc_params, dict) and required.issubset(calc_params))


def _queue_normal_run_from_calc_params() -> bool:
    calc_params = st.session_state.get("calc_params")
    if not _has_valid_calc_params(calc_params):
        return False
    next_req = dict(calc_params)
    next_req["use_warm_start"] = False
    st.session_state["_ottimizza_req"] = next_req
    return True


def _promote_draft_to_current(draft: dict) -> None:
    """Promuove la bozza (base2) a piano corrente ufficiale (base1)."""
    save_start = draft.get("calc_start")
    save_end = draft.get("calc_end")
    base2_pa = draft.get("base_preassignments", pd.DataFrame())
    if save_start and save_end:
        final_pa = _merge_draft_pa(
            draft["preassignments"],
            base2_pa,
            save_start,
            save_end,
        )
    else:
        final_pa = draft["preassignments"].copy()
    st.session_state["data"]["preassignments"] = final_pa

    base2_locks = draft.get("base_locks")
    if base2_locks is not None:
        st.session_state["data"]["locks"] = base2_locks.copy()
    st.session_state["data"]["demand_overrides"] = _normalize_demand_overrides(
        draft.get("demand_overrides", pd.DataFrame())
    )

    # assignments_df solver non è affidabile dopo edit manuali.
    if draft.get("manual_edits", False):
        st.session_state["data"].pop("assignments_df", None)
    else:
        save_adf = draft.get("assignments_df", pd.DataFrame())
        if not save_adf.empty:
            st.session_state["data"]["assignments_df"] = save_adf.copy()
        else:
            st.session_state["data"].pop("assignments_df", None)

    _drop_draft_state()


def _is_holiday(d: date) -> bool:
    return (d.day, d.month) in FIXED_HOLIDAYS


def _supports_kwarg(fn, arg: str) -> bool:
    try:
        return arg in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def _button(label: str, *, width: str | None = None, **kwargs):
    if width is not None and _supports_kwarg(st.button, "width"):
        kwargs["width"] = width
    elif width is not None and _supports_kwarg(st.button, "use_container_width"):
        kwargs["use_container_width"] = (width == "stretch")
    return st.button(label, **kwargs)


def _download_button(label: str, *, width: str | None = None, **kwargs):
    if width is not None and _supports_kwarg(st.download_button, "width"):
        kwargs["width"] = width
    elif width is not None and _supports_kwarg(st.download_button, "use_container_width"):
        kwargs["use_container_width"] = (width == "stretch")
    return st.download_button(label, **kwargs)


def _dataframe(data, *, width: str | None = None, **kwargs):
    if width is not None and _supports_kwarg(st.dataframe, "use_container_width"):
        kwargs["use_container_width"] = (width == "stretch")
    elif isinstance(width, int) and _supports_kwarg(st.dataframe, "width"):
        kwargs["width"] = width
    return st.dataframe(data, **kwargs)


def _hdr_class(d: date) -> str:
    if d.weekday() == 6:
        return "bg-sun"
    if _is_holiday(d):
        return "bg-hol"
    return ""


def _cell_class(code: str, d: date) -> str:
    c = code.strip().upper() if isinstance(code, str) else ""
    if c == "F":
        return "bg-abs"
    if c == "N":
        return "bg-night"
    if c == "SN":
        return "bg-sn"
    if c in ("SW", "S"):
        return "bg-sw"
    if c == "R":
        return "bg-rest"
    if d.weekday() == 6:
        return "bg-sun"
    if _is_holiday(d):
        return "bg-hol"
    return "bg-def"


# ── Data loading ─────────────────────────────────────────────────────────────

def load_dataset(folder: Path) -> dict:
    cfg_path = folder / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"config.yaml non trovato in {folder}")
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    employees = pd.read_csv(folder / "employees.csv")
    shifts = pd.read_csv(folder / "shifts.csv")

    preassignments = pd.DataFrame()
    pa_path = folder / "preassignments.csv"
    if pa_path.exists():
        preassignments = pd.read_csv(pa_path)
        # Normalizza il nome colonna turno a "state_code" per coerenza con il salvataggio
        for _alt in ("shift_code", "turno"):
            if _alt in preassignments.columns and "state_code" not in preassignments.columns:
                preassignments = preassignments.rename(columns={_alt: "state_code"})

    month_plan = pd.DataFrame()
    mp_path = folder / "month_plan.csv"
    if mp_path.exists():
        month_plan = pd.read_csv(mp_path, dtype=str).fillna("")

    coverage_groups = pd.DataFrame()
    cg_path = folder / "coverage_groups.csv"
    if cg_path.exists():
        coverage_groups = pd.read_csv(cg_path, dtype=str).fillna("")

    coverage_roles = pd.DataFrame()
    cr_path = folder / "coverage_roles.csv"
    if cr_path.exists():
        coverage_roles = pd.read_csv(cr_path, dtype=str).fillna("")

    _LOCK_COLS = ["employee_id", "date", "reparto_id", "shift_code", "lock_type"]
    locks = pd.DataFrame(columns=_LOCK_COLS)
    locks_path = folder / "locks.csv"
    if locks_path.exists():
        raw_locks = pd.read_csv(locks_path, dtype=str).fillna("")
        if {"employee_id", "date", "reparto_id", "shift_code", "lock_type"}.issubset(raw_locks.columns):
            locks = raw_locks[_LOCK_COLS].copy()
            locks["lock_type"] = locks["lock_type"].str.strip().str.upper()
        elif (
            {"employee_id", "slot_id", "lock"}.issubset(raw_locks.columns)
            and not raw_locks.empty
            and not month_plan.empty
            and {"data", "reparto_id", "shift_code"}.issubset(month_plan.columns)
        ):
            # Formato slot_id: risolvi slot_id → (date, reparto_id, shift_code)
            # replicando la logica di build_shift_slots (sort + indice 1-based).
            _mp = month_plan.copy()
            _mp["_data_dt"] = pd.to_datetime(_mp["data"], errors="coerce")
            _h = cfg.get("horizon", {})
            _hs, _he = _h.get("start_date"), _h.get("end_date")
            if _hs and _he:
                _hs_t, _he_t = pd.Timestamp(_hs), pd.Timestamp(_he)
                _mp = _mp[(_mp["_data_dt"] >= _hs_t) & (_mp["_data_dt"] <= _he_t)]
            _sort = ["_data_dt", "reparto_id", "shift_code"]
            if "coverage_code" in _mp.columns:
                _sort.append("coverage_code")
            _mp = _mp.sort_values(_sort).reset_index(drop=True)
            _slot_map: dict[str, dict] = {}
            for _i, _r in _mp.iterrows():
                _slot_map[str(_i + 1)] = {
                    "date": str(pd.Timestamp(_r["_data_dt"]).date()),
                    "reparto_id": str(_r["reparto_id"]).strip(),
                    "shift_code": str(_r["shift_code"]).strip(),
                }
            _LOCK_VAL = {"-1": "FORBIDDEN", "1": "MUST_DO"}
            _resolved: list[dict] = []
            for _, _lr in raw_locks.iterrows():
                try:
                    _sid = str(int(float(_lr["slot_id"])))
                except (ValueError, TypeError):
                    continue
                _lt = _LOCK_VAL.get(str(_lr["lock"]).strip())
                if _lt and _sid in _slot_map:
                    _si = _slot_map[_sid]
                    _resolved.append({
                        "employee_id": str(_lr["employee_id"]).strip(),
                        "date": _si["date"],
                        "reparto_id": _si["reparto_id"],
                        "shift_code": _si["shift_code"],
                        "lock_type": _lt,
                    })
            if _resolved:
                locks = pd.DataFrame(_resolved, columns=_LOCK_COLS)

    return {
        "cfg": cfg,
        "employees": employees,
        "shifts": shifts,
        "preassignments": preassignments,
        "locks": locks,
        "month_plan": month_plan,
        "coverage_groups": coverage_groups,
        "coverage_roles": coverage_roles,
        "demand_overrides": pd.DataFrame(
            columns=[
                "data",
                "reparto_id",
                "shift_code",
                "coverage_code",
                "gruppo",
                "total_required",
                "role",
                "min_required",
            ]
        ),
        "folder": str(folder),
    }


def _normalize_preassignments(pa_df: pd.DataFrame) -> pd.DataFrame:
    """Normalizza il DataFrame preassegnazioni al formato atteso dal loader.

    Colonne output: employee_id | data (YYYY-MM-DD) | state_code
    Gestisce varianti di nomi colonna provenienti da CSV eterogenei.
    """
    if pa_df is None or pa_df.empty:
        return pd.DataFrame(columns=["employee_id", "data", "state_code"])

    out = pa_df.copy()

    # Normalizza colonna data: accetta "data", "date", "day"
    if "data" not in out.columns:
        for alt in ("date", "day"):
            if alt in out.columns:
                out = out.rename(columns={alt: "data"})
                break

    # Normalizza colonna stato: accetta "state_code", "state", "turno", "shift_code"
    if "state_code" not in out.columns:
        for alt in ("state", "turno", "shift_code"):
            if alt in out.columns:
                out = out.rename(columns={alt: "state_code"})
                break

    # Tieni solo le colonne necessarie (ignora eventuali colonne extra)
    keep = [c for c in ("employee_id", "data", "state_code") if c in out.columns]
    out = out[keep].copy()

    # Rimuovi righe senza stato assegnato (stato vuoto o "--")
    if "state_code" in out.columns:
        out = out[out["state_code"].notna() & (out["state_code"].astype(str).str.strip() != "")
                  & (out["state_code"].astype(str).str.strip() != "--")]

    return out.reset_index(drop=True)


def _normalize_locks(locks_df: pd.DataFrame | None) -> pd.DataFrame:
    cols = ["employee_id", "date", "reparto_id", "shift_code", "lock_type"]
    if locks_df is None or locks_df.empty:
        return pd.DataFrame(columns=cols)
    out = locks_df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = ""
    out = out[cols].copy()
    out["lock_type"] = out["lock_type"].astype(str).str.strip().str.upper()
    out = out[out["lock_type"].isin(["MUST_DO", "FORBIDDEN"])].reset_index(drop=True)
    return out


def _normalize_demand_overrides(df: pd.DataFrame | None) -> pd.DataFrame:
    cols = [
        "data",
        "reparto_id",
        "shift_code",
        "coverage_code",
        "gruppo",
        "total_required",
        "role",
        "min_required",
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    out = df.copy()
    for c in cols:
        if c not in out.columns:
            out[c] = pd.NA
    out = out[cols].copy()
    _dt = pd.to_datetime(out["data"], errors="coerce")
    out = out[_dt.notna()].copy()
    out["data"] = _dt[_dt.notna()].dt.date.astype(str)
    out["reparto_id"] = out["reparto_id"].astype(str).str.strip().str.upper()
    out["shift_code"] = out["shift_code"].astype(str).str.strip().str.upper()
    out["coverage_code"] = out["coverage_code"].astype(str).str.strip().str.upper().replace({"<NA>": "", "NAN": ""})
    # Retrocompatibilità: eventuali override salvati con coverage sintetico OVR_*.
    out.loc[out["coverage_code"].str.startswith("OVR_", na=False), "coverage_code"] = ""
    out["gruppo"] = out["gruppo"].astype(str).str.strip().str.upper().replace({"<NA>": "", "NAN": ""})
    out["role"] = out["role"].astype(str).str.strip().str.upper().replace({"<NA>": "", "NAN": ""})
    out["total_required"] = pd.to_numeric(out["total_required"], errors="coerce")
    out["min_required"] = pd.to_numeric(out["min_required"], errors="coerce")
    out = out[out["data"].notna() & (out["reparto_id"] != "") & (out["shift_code"] != "")]
    group_mask = out["total_required"].notna()
    role_mask = out["min_required"].notna()
    group_rows = out[group_mask].copy()
    role_rows = out[role_mask].copy()
    if not group_rows.empty:
        group_rows["total_required"] = group_rows["total_required"].fillna(0).astype(int).clip(lower=0)
        group_rows["min_required"] = pd.NA
        group_rows["role"] = ""
        group_rows = group_rows.drop_duplicates(
            subset=["data", "reparto_id", "shift_code", "coverage_code", "gruppo"],
            keep="last",
        )
    if not role_rows.empty:
        role_rows["min_required"] = role_rows["min_required"].fillna(0).astype(int).clip(lower=0)
        role_rows["total_required"] = pd.NA
        role_rows = role_rows[role_rows["role"] != ""]
        role_rows = role_rows.drop_duplicates(
            subset=["data", "reparto_id", "shift_code", "coverage_code", "gruppo", "role"],
            keep="last",
        )
    out = pd.concat([group_rows, role_rows], ignore_index=True)
    return out.reset_index(drop=True)


def _get_demand_overrides_target() -> tuple[str, pd.DataFrame]:
    draft = st.session_state.get("draft")
    if st.session_state.get("view_draft", False) and isinstance(draft, dict):
        return "draft", _normalize_demand_overrides(draft.get("demand_overrides", pd.DataFrame()))
    data = st.session_state.get("data", {})
    return "data", _normalize_demand_overrides(data.get("demand_overrides", pd.DataFrame()))


def _set_demand_overrides_target(target: str, overrides_df: pd.DataFrame) -> None:
    normalized = _normalize_demand_overrides(overrides_df)
    if target == "draft":
        st.session_state["draft"]["demand_overrides"] = normalized
        st.session_state["draft"]["manual_edits"] = True
    else:
        st.session_state["data"]["demand_overrides"] = normalized


def _upsert_group_override(
    overrides_df: pd.DataFrame,
    *,
    data_s: str,
    reparto_id: str,
    shift_code: str,
    coverage_code: str,
    gruppo: str,
    total_required: int,
) -> pd.DataFrame:
    out = _normalize_demand_overrides(overrides_df)
    cov_opts = [coverage_code, ""]
    mask = (
        (out["data"] == data_s)
        & (out["reparto_id"] == reparto_id)
        & (out["shift_code"] == shift_code)
        & (out["coverage_code"].isin(cov_opts))
        & (out["gruppo"] == gruppo)
        & (out["total_required"].notna())
    )
    out = out[~mask].reset_index(drop=True)
    row = {
        "data": data_s,
        "reparto_id": reparto_id,
        "shift_code": shift_code,
        "coverage_code": coverage_code,
        "gruppo": gruppo,
        "total_required": int(total_required),
        "role": "",
        "min_required": pd.NA,
    }
    return _normalize_demand_overrides(pd.concat([out, pd.DataFrame([row])], ignore_index=True))


def _clear_group_override(
    overrides_df: pd.DataFrame,
    *,
    data_s: str,
    reparto_id: str,
    shift_code: str,
    coverage_code: str,
    gruppo: str,
) -> pd.DataFrame:
    out = _normalize_demand_overrides(overrides_df)
    cov_opts = [coverage_code, ""]
    mask = (
        (out["data"] == data_s)
        & (out["reparto_id"] == reparto_id)
        & (out["shift_code"] == shift_code)
        & (out["coverage_code"].isin(cov_opts))
        & (out["gruppo"] == gruppo)
        & (out["total_required"].notna())
    )
    return out[~mask].reset_index(drop=True)


def _upsert_role_override(
    overrides_df: pd.DataFrame,
    *,
    data_s: str,
    reparto_id: str,
    shift_code: str,
    coverage_code: str,
    gruppo: str,
    role: str,
    min_required: int,
) -> pd.DataFrame:
    out = _normalize_demand_overrides(overrides_df)
    cov_opts = [coverage_code, ""]
    mask = (
        (out["data"] == data_s)
        & (out["reparto_id"] == reparto_id)
        & (out["shift_code"] == shift_code)
        & (out["coverage_code"].isin(cov_opts))
        & (out["gruppo"] == gruppo)
        & (out["role"] == role)
        & (out["min_required"].notna())
    )
    out = out[~mask].reset_index(drop=True)
    row = {
        "data": data_s,
        "reparto_id": reparto_id,
        "shift_code": shift_code,
        "coverage_code": coverage_code,
        "gruppo": gruppo,
        "total_required": pd.NA,
        "role": role,
        "min_required": int(min_required),
    }
    return _normalize_demand_overrides(pd.concat([out, pd.DataFrame([row])], ignore_index=True))


def _clear_role_override(
    overrides_df: pd.DataFrame,
    *,
    data_s: str,
    reparto_id: str,
    shift_code: str,
    coverage_code: str,
    gruppo: str,
    role: str,
) -> pd.DataFrame:
    out = _normalize_demand_overrides(overrides_df)
    cov_opts = [coverage_code, ""]
    mask = (
        (out["data"] == data_s)
        & (out["reparto_id"] == reparto_id)
        & (out["shift_code"] == shift_code)
        & (out["coverage_code"].isin(cov_opts))
        & (out["gruppo"] == gruppo)
        & (out["role"] == role)
        & (out["min_required"].notna())
    )
    return out[~mask].reset_index(drop=True)


def _distribute_total(original: list[int], target: int) -> list[int]:
    if not original:
        return []
    target = max(0, int(target))
    if len(original) == 1:
        return [target]
    base_sum = sum(max(0, int(v)) for v in original)
    if base_sum <= 0:
        out = [0] * len(original)
        out[0] = target
        return out
    raw = [max(0.0, float(v)) * target / base_sum for v in original]
    floor = [int(x) for x in raw]
    remainder = target - sum(floor)
    frac_idx = sorted(
        range(len(raw)),
        key=lambda i: (raw[i] - floor[i]),
        reverse=True,
    )
    for i in frac_idx[:max(0, remainder)]:
        floor[i] += 1
    return floor


def _apply_demand_overrides_tables(
    month_plan: pd.DataFrame,
    coverage_groups: pd.DataFrame,
    coverage_roles: pd.DataFrame,
    overrides_df: pd.DataFrame | None,
    *,
    include_base_coverage: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[str]]:
    overrides = _normalize_demand_overrides(overrides_df)
    if overrides.empty or month_plan.empty or coverage_groups.empty:
        return month_plan, coverage_groups, coverage_roles, []

    mp = month_plan.copy()
    cg = coverage_groups.copy()
    cr = coverage_roles.copy()
    warnings_list: list[str] = []

    # Normalize lookup columns.
    for df, cols in (
        (mp, ["data", "reparto_id", "shift_code", "coverage_code"]),
        (cg, ["coverage_code", "reparto_id", "shift_code", "gruppo"]),
        (cr, ["coverage_code", "reparto_id", "shift_code", "gruppo"]),
    ):
        for col in cols:
            if col in df.columns:
                df[col] = df[col].astype(str).str.strip().str.upper()
    if "data" in mp.columns:
        mp["data"] = pd.to_datetime(mp["data"], errors="coerce").dt.date.astype(str)
    if include_base_coverage:
        mp["base_coverage_code"] = mp["coverage_code"].astype(str).str.strip().str.upper()

    cg["total_staff"] = pd.to_numeric(cg.get("total_staff"), errors="coerce").fillna(0).astype(int)
    if "min_ruolo" in cr.columns:
        cr["min_ruolo"] = pd.to_numeric(cr["min_ruolo"], errors="coerce").fillna(0).astype(int)
    role_col = "role" if "role" in cr.columns else ("ruolo" if "ruolo" in cr.columns else None)
    if role_col:
        cr["_role_norm"] = cr[role_col].astype(str).str.strip().str.upper()

    new_cg_rows: list[dict] = []
    new_cr_rows: list[dict] = []

    by_cell = overrides.groupby(["data", "reparto_id", "shift_code"], dropna=False)
    for (ds, rep, sh), ovr_cell in by_cell:
        ds = str(ds).upper()
        rep = str(rep).upper()
        sh = str(sh).upper()
        mp_mask = (mp["data"] == ds) & (mp["reparto_id"] == rep) & (mp["shift_code"] == sh)
        if not mp_mask.any():
            warnings_list.append(f"Override ignorato: nessun month_plan per {ds} {rep} {sh}.")
            continue

        cell_groups = ovr_cell[ovr_cell["total_required"].notna()].copy()
        cell_roles = ovr_cell[ovr_cell["min_required"].notna()].copy()
        per_group_total: dict[str, int] = {}
        if not cell_groups.empty:
            for _, g in cell_groups.iterrows():
                gr = str(g.get("gruppo", "")).strip().upper()
                cov = str(g.get("coverage_code", "")).strip().upper()
                per_group_total[(cov, gr)] = int(g["total_required"])
        per_role_min: dict[tuple[str, str], int] = {}
        if not cell_roles.empty:
            for _, r in cell_roles.iterrows():
                gr = str(r.get("gruppo", "")).strip().upper()
                rl = str(r.get("role", "")).strip().upper()
                if not rl:
                    continue
                cov = str(r.get("coverage_code", "")).strip().upper()
                per_role_min[(cov, gr, rl)] = int(r["min_required"])

        for mp_idx in mp.index[mp_mask]:
            old_cov = str(mp.at[mp_idx, "coverage_code"])
            base_cov = (
                str(mp.at[mp_idx, "base_coverage_code"])
                if include_base_coverage and "base_coverage_code" in mp.columns
                else old_cov
            )
            gmask = (
                (cg["coverage_code"] == base_cov)
                & (cg["reparto_id"] == rep)
                & (cg["shift_code"] == sh)
            )
            grows = cg[gmask].copy()
            if grows.empty:
                warnings_list.append(
                    f"Override ignorato: nessun coverage_group per {ds} {rep} {sh} ({base_cov})."
                )
                continue

            new_cov = f"OVR_{ds.replace('-', '')}_{rep}_{sh}_{mp_idx}".upper()

            if per_group_total:
                for gidx in grows.index:
                    gr = str(grows.at[gidx, "gruppo"]).strip().upper()
                    key_exact = (base_cov, gr)
                    key_wild = ("", gr)
                    if key_exact in per_group_total:
                        grows.at[gidx, "total_staff"] = int(per_group_total[key_exact])
                    elif key_wild in per_group_total:
                        grows.at[gidx, "total_staff"] = int(per_group_total[key_wild])

            for _, grow in grows.iterrows():
                ng = grow.to_dict()
                ng["coverage_code"] = new_cov
                ng["total_staff"] = int(ng["total_staff"])
                new_cg_rows.append(ng)

            if cr.empty:
                mp.at[mp_idx, "coverage_code"] = new_cov
                continue

            for _, grow in grows.iterrows():
                gruppo = str(grow.get("gruppo", "")).strip().upper()
                gtot = int(grow.get("total_staff", 0))
                rmask = (
                    (cr["coverage_code"] == base_cov)
                    & (cr["reparto_id"] == rep)
                    & (cr["shift_code"] == sh)
                )
                if "gruppo" in cr.columns:
                    rmask = rmask & (cr["gruppo"].astype(str).str.strip().str.upper() == gruppo)
                rrows = cr[rmask].copy()
                if rrows.empty:
                    continue

                role_override_pairs = {
                    (cov, g, r)
                    for (cov, g, r) in per_role_min
                    if g == gruppo and cov in ("", base_cov)
                }
                if role_override_pairs and role_col:
                    for ridx in rrows.index:
                        role_norm = str(rrows.at[ridx, "_role_norm"]).strip().upper()
                        key_exact = (base_cov, gruppo, role_norm)
                        key_wild = ("", gruppo, role_norm)
                        if key_exact in per_role_min:
                            rrows.at[ridx, "min_ruolo"] = int(per_role_min[key_exact])
                        elif key_wild in per_role_min:
                            rrows.at[ridx, "min_ruolo"] = int(per_role_min[key_wild])

                for _, rrow in rrows.iterrows():
                    nr = rrow.to_dict()
                    nr["coverage_code"] = new_cov
                    if "min_ruolo" in nr:
                        nr["min_ruolo"] = int(nr["min_ruolo"])
                    nr.pop("_role_norm", None)
                    new_cr_rows.append(nr)

            mp.at[mp_idx, "coverage_code"] = new_cov

    if new_cg_rows:
        cg = pd.concat(
            [
                cg[~cg["coverage_code"].str.startswith("OVR_", na=False)],
                pd.DataFrame(new_cg_rows),
            ],
            ignore_index=True,
        )
    if new_cr_rows:
        cr = pd.concat(
            [
                cr[~cr["coverage_code"].str.startswith("OVR_", na=False)],
                pd.DataFrame(new_cr_rows),
            ],
            ignore_index=True,
        )
    if "_role_norm" in cr.columns:
        cr = cr.drop(columns=["_role_norm"])

    return mp, cg, cr, warnings_list


def _build_export_zip_bytes(
    *,
    preassignments_df: pd.DataFrame,
    locks_df: pd.DataFrame,
    assignments_df: pd.DataFrame | None,
    demand_overrides_df: pd.DataFrame | None,
    kind: str,
) -> bytes:
    pa_out = _normalize_preassignments(preassignments_df)
    locks_out = _normalize_locks(locks_df)
    over_out = _normalize_demand_overrides(demand_overrides_df)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("preassignments.csv", pa_out.to_csv(index=False))
        zf.writestr("locks.csv", locks_out.to_csv(index=False))
        zf.writestr("demand_overrides.csv", over_out.to_csv(index=False))
        if assignments_df is not None and not assignments_df.empty:
            zf.writestr("assignments_df.csv", assignments_df.to_csv(index=False))
        zf.writestr(
            "README.txt",
            (
                f"Export type: {kind}\n"
                f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            ),
        )
    return buf.getvalue()


def _build_current_export_zip(data: dict) -> bytes:
    return _build_export_zip_bytes(
        preassignments_df=data.get("preassignments", pd.DataFrame()),
        locks_df=data.get("locks", pd.DataFrame()),
        assignments_df=data.get("assignments_df", pd.DataFrame()),
        demand_overrides_df=data.get("demand_overrides", pd.DataFrame()),
        kind="current",
    )


def _build_draft_export_zip(draft: dict) -> bytes:
    save_start = draft.get("calc_start")
    save_end = draft.get("calc_end")
    base2_pa = draft.get("base_preassignments", pd.DataFrame())
    if save_start and save_end:
        final_pa = _merge_draft_pa(
            draft.get("preassignments", pd.DataFrame()),
            base2_pa,
            save_start,
            save_end,
        )
    else:
        final_pa = draft.get("preassignments", pd.DataFrame()).copy()

    assignments_df = None
    if not draft.get("manual_edits", False):
        assignments_df = draft.get("assignments_df", pd.DataFrame())

    return _build_export_zip_bytes(
        preassignments_df=final_pa,
        locks_df=draft.get("base_locks", pd.DataFrame()),
        assignments_df=assignments_df,
        demand_overrides_df=draft.get("demand_overrides", pd.DataFrame()),
        kind="draft",
    )


def _merge_draft_pa(
    draft_pa: pd.DataFrame,
    current_pa: pd.DataFrame,
    win_start: str,
    win_end: str,
) -> pd.DataFrame:
    """Unisce le preassegnazioni della bozza (giorni nella finestra di calcolo)
    con quelle correnti (giorni fuori dalla finestra), preservando i dati
    esistenti quando si ottimizza solo un periodo parziale.

    Args:
        draft_pa:   PA prodotte dal solver (colonne: employee_id, data, state_code)
        current_pa: PA correnti in sessione (possibili varianti di colonne)
        win_start:  primo giorno della finestra, es. "2025-07-01"
        win_end:    ultimo giorno della finestra, es. "2025-07-15"
    Returns:
        DataFrame con colonne employee_id | data | state_code
    """
    _s = pd.Timestamp(win_start).date()
    _e = pd.Timestamp(win_end).date()
    win_dates: set[str] = {
        str(_s + timedelta(days=i))
        for i in range((_e - _s).days + 1)
    }
    norm_curr = _normalize_preassignments(current_pa)
    if not norm_curr.empty and "data" in norm_curr.columns:
        outside = norm_curr[~norm_curr["data"].astype(str).isin(win_dates)]
    else:
        outside = pd.DataFrame(columns=["employee_id", "data", "state_code"])
    return pd.concat([draft_pa, outside], ignore_index=True)


def _build_state_lookup(pa_df: pd.DataFrame) -> dict[tuple[str, str], str]:
    norm = _normalize_preassignments(pa_df)
    if norm.empty:
        return {}
    return {
        (str(r["employee_id"]), str(pd.Timestamp(r["data"]).date())): str(r["state_code"]).strip().upper()
        for _, r in norm.iterrows()
    }


def _compute_schedule_diff(
    baseline_pa: pd.DataFrame,
    draft_pa: pd.DataFrame,
) -> pd.DataFrame:
    base_lu = _build_state_lookup(baseline_pa)
    draft_lu = _build_state_lookup(draft_pa)
    keys = sorted(set(base_lu.keys()) | set(draft_lu.keys()))
    rows: list[dict] = []
    for eid, ds in keys:
        old = base_lu.get((eid, ds), "--")
        new = draft_lu.get((eid, ds), "--")
        if old != new:
            rows.append({"employee_id": eid, "data": ds, "from_state": old, "to_state": new})
    return pd.DataFrame(rows, columns=["employee_id", "data", "from_state", "to_state"])


def _coverage_shortage_summary(cov_data: dict) -> dict[str, int]:
    uncovered_cells = 0
    total_shortage = 0
    for _, cell in cov_data.items():
        if cell.get("status") == "N":
            uncovered_cells += 1
        for d in cell.get("details", []):
            req = int(d.get("total_required", 0))
            pres = int(d.get("total_present", 0))
            total_shortage += max(0, req - pres)
    return {"uncovered_cells": uncovered_cells, "total_shortage": total_shortage}


def _build_draft_kpi_data(result) -> dict:
    """Estrae le metriche KPI da un SolveResult per la tab Analisi.

    Restituisce un dizionario flat pronto per _render_kpi_tab.
    Tollerante agli errori: se un campo non è disponibile viene omesso.
    """
    kpi: dict = {}

    # ── Coverage under (ruolo e gruppo separati — semantica diversa) ─────
    under_role = 0
    if result.coverage_under_role_df is not None and not result.coverage_under_role_df.empty:
        under_role = int(result.coverage_under_role_df["under_staff"].sum())
    under_group = 0
    if result.coverage_under_group_df is not None and not result.coverage_under_group_df.empty:
        under_group = int(result.coverage_under_group_df["under_staff"].sum())
    kpi["coverage_under_role"]  = under_role
    kpi["coverage_under_group"] = under_group

    # ── Obiettivo e gap dall'ottimo ───────────────────────────────────────
    obj = result.objective_value
    bound = result.best_objective_bound
    kpi["objective_value"] = obj
    kpi["best_bound"] = bound
    if obj is not None and bound is not None and obj > 0:
        kpi["gap_pct"] = max(0.0, (obj - bound) / obj * 100.0)
    else:
        kpi["gap_pct"] = None

    # ── Breakdown per componente ──────────────────────────────────────────
    bd = result.objective_breakdown
    if bd is not None:
        bd_map = {r.component: r for r in bd.rows}
        r11  = bd_map.get("riposo_11h")
        rw   = bd_map.get("riposo_settimanale")
        rpa  = bd_map.get("preassegnazioni")
        rcr  = bd_map.get("assegnazioni_cross")
        kpi["violations_rest11"]      = int(r11.violations)  if r11  else 0
        kpi["violations_rest_weekly"] = int(rw.violations)   if rw   else 0
        kpi["violations_preass"]      = int(rpa.violations)  if rpa  else 0
        kpi["n_cross_dept"]           = int(rcr.violations)  if rcr  else 0
    else:
        kpi["violations_rest11"]      = 0
        kpi["violations_rest_weekly"] = 0
        kpi["violations_preass"]      = 0
        kpi["n_cross_dept"]           = 0

    # ── Dipendenti pianificati ────────────────────────────────────────────
    adf = result.assignments_df
    if adf is not None and not adf.empty and "employee_id" in adf.columns:
        kpi["n_employees_planned"] = int(adf["employee_id"].nunique())
    else:
        kpi["n_employees_planned"] = 0

    # ── Saldo ore finale per dipendente (minuti → ore) ────────────────────
    try:
        balance_vars = getattr(result.artifacts, "final_hour_balance", {})
        solver = result.solver
        emp_of: dict = dict(result.bundle.get("emp_of", {}))
        final_balance: dict[str, float] = {}
        for (emp_idx, _), var in balance_vars.items():
            eid = emp_of.get(emp_idx, str(emp_idx))
            final_balance[str(eid)] = solver.Value(var) / 60.0
        kpi["final_balance_by_emp"] = final_balance
    except (AttributeError, KeyError, TypeError, ValueError):
        kpi["final_balance_by_emp"] = {}

    return kpi


def _store_new_draft(
    *,
    draft_pa: pd.DataFrame,
    result,
    ottimizza_req: dict,
    base2_pa: pd.DataFrame,
    base2_locks: pd.DataFrame,
    demand_overrides: pd.DataFrame,
) -> None:
    st.session_state["draft"] = {
        "preassignments": draft_pa,
        "status_name": result.status_name,
        "objective_value": result.objective_value,
        "calc_start": ottimizza_req["start"],
        "calc_end": ottimizza_req["end"],
        "assignments_df": result.assignments_df.copy(),
        "kpi": _build_draft_kpi_data(result),
        "infeasibility_summary": result.infeasibility_summary,
        "base_preassignments": base2_pa,
        "base_locks": base2_locks,
        "demand_overrides": _normalize_demand_overrides(demand_overrides),
        "manual_edits": False,
        "edited_cells": {},
    }
    st.session_state["view_draft"] = True


def prepare_run_folder(data: dict) -> Path:
    """Crea una cartella temporanea con tutti i CSV/YAML pronti per il loader.

    Copia i file statici dalla cartella originale del dataset e sovrascrive
    quelli che la UI può aver modificato in memoria:
      - employees.csv      ← data["employees"]
      - month_plan.csv     ← data["month_plan"] (runtime, include override domanda)
      - coverage_groups.csv← data["coverage_groups"] (runtime, include override domanda)
      - coverage_roles.csv ← data["coverage_roles"] (runtime, include override domanda)
      - preassignments.csv ← data["preassignments"] (normalizzato)
      - locks.csv          ← data["locks"] (se non vuoto)
    Nota: config.yaml NON viene scritto qui — load_all_data riceve data["cfg"]
    come dict in memoria e lo gestisce internamente.

    Crea holidays.csv vuoto se non presente nella cartella originale
    (il loader lo usa per la classificazione dei giorni festivi).

    Returns:
        Path alla cartella temporanea.
        Il chiamante è responsabile di cancellarla dopo l'uso
        (tipicamente con shutil.rmtree in un blocco finally).

    Raises:
        ValueError: se data["folder"] non è impostato o la cartella non esiste.
        IOError: se la creazione del file temporaneo fallisce.
    """
    src = Path(data.get("folder", ""))
    if not src.is_dir():
        raise ValueError(f"Cartella dataset non valida: {src!r}")

    tmp_dir = Path(tempfile.mkdtemp(prefix="sky_run_"))
    try:
        # ── 1. Copia tutti i file statici dalla cartella originale ────────────
        for f in src.iterdir():
            if f.is_file():
                shutil.copy2(f, tmp_dir / f.name)

        # ── 2. employees.csv — sovrascrive con la working copy della UI ───────
        # Nota: config.yaml NON viene scritto qui. load_all_data riceve data["cfg"]
        # come dict in memoria e crea internamente il proprio file yaml temporaneo.
        # Scrivere config.yaml nella run folder sarebbe una seconda fonte di config
        # che il loader non legge mai, causando solo ambiguità in debug.
        emp_df = data["employees"].copy()
        emp_df.to_csv(tmp_dir / "employees.csv", index=False)

        # ── 3. month/coverage tables — sovrascrive working copy runtime ──────
        for key, fname in (
            ("month_plan", "month_plan.csv"),
            ("coverage_groups", "coverage_groups.csv"),
            ("coverage_roles", "coverage_roles.csv"),
        ):
            df = data.get(key, pd.DataFrame())
            if isinstance(df, pd.DataFrame) and not df.empty:
                df.to_csv(tmp_dir / fname, index=False)

        # ── 4. preassignments.csv — normalizzato e scritto sempre ─────────────
        #    Se vuoto il loader lo ignora; scrivere il file garantisce che
        #    eventuali preassegnazioni della sessione precedente non persistano.
        pa_out = _normalize_preassignments(data.get("preassignments"))
        pa_out.to_csv(tmp_dir / "preassignments.csv", index=False)

        # ── 5. locks.csv — sovrascrive solo se ci sono lock attivi ───────────
        locks_df = data.get("locks", pd.DataFrame())
        if not locks_df.empty and "lock_type" in locks_df.columns:
            # Formato state-based: employee_id, date, reparto_id, shift_code, lock_type
            # Compatibile con il loader (formato simbolico)
            locks_df.to_csv(tmp_dir / "locks.csv", index=False)
        else:
            # Nessun lock attivo: se esiste un lock.csv dalla copia, lo rimuoviamo
            # per evitare di passare lock obsoleti al solver
            stale = tmp_dir / "locks.csv"
            if stale.exists():
                stale.unlink()

        # ── 6. holidays.csv — crea file vuoto se assente ─────────────────────
        #    Il loader classifica i giorni festivi da questo file; se mancante
        #    in alcuni dataset (July/August), lo creiamo vuoto con l'header.
        hol_path = tmp_dir / "holidays.csv"
        if not hol_path.exists():
            pd.DataFrame(columns=["data", "descrizione"]).to_csv(hol_path, index=False)

    except (
        OSError,
        IOError,
        ValueError,
        TypeError,
        KeyError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        yaml.YAMLError,
        RuntimeError,
    ):
        shutil.rmtree(tmp_dir, ignore_errors=True)
        raise

    return tmp_dir


def build_schedule(data: dict) -> tuple[list[date], list[dict]]:
    cfg = data["cfg"]
    horizon = cfg.get("horizon", {})
    start = pd.Timestamp(horizon["start_date"]).date()
    end = pd.Timestamp(horizon["end_date"]).date()
    dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    date_strs = [str(d) for d in dates]

    emp_df = data["employees"]
    pa_df = data["preassignments"]

    pa_lookup: dict[tuple[str, str], str] = {}
    if not pa_df.empty:
        code_col = next((c for c in ("state_code", "shift_code", "turno") if c in pa_df.columns), None)
        date_col = next((c for c in ("data", "date") if c in pa_df.columns), None)
        if code_col and date_col:
            for _, r in pa_df.iterrows():
                pa_lookup[(str(r["employee_id"]), str(pd.Timestamp(r[date_col]).date()))] = (
                    str(r[code_col]).strip().upper()
                )

    # MUST_DO lock: priorità su preassignment, rende la cella bold
    locks_df = data.get("locks", pd.DataFrame())
    must_lookup: dict[tuple[str, str], str] = {}
    locked_days_by_emp: dict[str, set[str]] = {}
    if not locks_df.empty and "lock_type" in locks_df.columns:
        for _, r in locks_df[locks_df["lock_type"] == "MUST_DO"].iterrows():
            key = (str(r["employee_id"]), str(r["date"]))
            must_lookup[key] = str(r["shift_code"]).strip().upper()
            locked_days_by_emp.setdefault(str(r["employee_id"]), set()).add(str(r["date"]))

    rows: list[dict] = []
    for _, emp in emp_df.iterrows():
        eid = str(emp["employee_id"])
        name = str(emp.get("nome", eid))
        reparto = str(emp.get("reparto_id", ""))
        role = str(emp.get("role", ""))
        days = {}
        pa_days: set[str] = set()
        for ds in date_strs:
            if (eid, ds) in must_lookup:
                days[ds] = must_lookup[(eid, ds)]
            else:
                val = pa_lookup.get((eid, ds), "")
                days[ds] = val
                if val:
                    pa_days.add(ds)
        rows.append({
            "eid": eid, "name": name, "reparto": reparto, "role": role,
            "days": days,
            "locked_days": locked_days_by_emp.get(eid, set()),
            "pa_days": pa_days,
        })
    return dates, rows


# ── HTML grid with <a id> links for click_detector ───────────────────────────

def render_grid(
    dates: list[date],
    rows: list[dict],
    consolidated_before: date | None = None,
) -> str:
    """Build grid HTML. Highlight is handled client-side via JS so the HTML
    stays identical across clicks and the iframe is never re-created.

    Args:
        dates:               Lista di date da visualizzare.
        rows:                Righe dello schedule (output di build_schedule).
        consolidated_before: Prima data della finestra di ottimizzazione.
                             I giorni strettamente precedenti vengono marcati
                             come "consolidati" (visivamente attenuati).
    """
    # Pre-calcola l'insieme di date string consolidate per lookup O(1)
    consolidated_ds: set[str] = set()
    if consolidated_before is not None:
        consolidated_ds = {str(d) for d in dates if d < consolidated_before}

    parts: list[str] = [
        f"<style>{GRID_CSS}",
        """
.cell-selected {
    outline: 3px solid #0a9ba6 !important;
    outline-offset: -3px;
    box-shadow: inset 0 0 0 2px rgba(10,155,166,0.35) !important;
    position: relative; z-index: 2;
}
td.ncell a, td.dc-cell a {
    color: inherit !important; text-decoration: none !important;
    display: block; width: 100%; height: 100%;
}
td.ncell a { line-height: var(--cell-h); }
td.ncell:hover, td.dc-cell:hover { filter: brightness(0.90); cursor: pointer; }
.sched-container { max-height: 700px; }
td.dc-cell.cell-locked .l1 { font-weight: 700; letter-spacing: 0.04em; }
td.dc-cell.cell-locked { outline: 2px solid currentColor; outline-offset: -2px; }
td.dc-cell.cell-pa .l1 { font-style: italic; opacity: 0.85; }
th.col-consolidated { background-color: #dde8ea !important; opacity: 0.65; }
td.dc-cell.col-consolidated { opacity: 0.50; }
</style>""",
        '<div class="sched-container"><table class="sky-grid"><thead><tr>',
        '<th class="nhdr">Nominativo</th>',
    ]

    for d in dates:
        css = _hdr_class(d)
        cons_cls = " col-consolidated" if str(d) in consolidated_ds else ""
        dl = DAY_LETTERS[d.weekday()]
        parts.append(f'<th class="{css}{cons_cls}"><span class="dn">{d.day}</span><span class="dl">{dl}</span></th>')
    parts.append("</tr></thead><tbody>")

    for row in rows:
        eid = row["eid"]
        name = _html.escape(row["name"])
        parts.append(
            f'<tr><td class="ncell" title="{name}">'
            f'<a href="#" id="emp-{eid}">{name}</a></td>'
        )
        locked_days = row.get("locked_days", set())
        pa_days = row.get("pa_days", set())
        for d in dates:
            code = row["days"].get(str(d), "R")
            css = _cell_class(code, d)
            ds = str(d)
            if ds in locked_days:
                extra_cls = " cell-locked"
            elif ds in pa_days:
                extra_cls = " cell-pa"
            else:
                extra_cls = ""
            cons_cls = " col-consolidated" if ds in consolidated_ds else ""
            parts.append(
                f'<td class="{css} dc-cell{extra_cls}{cons_cls}">'
                f'<a href="#" id="day-{eid}-{d}">'
                f'<div class="dc"><div class="l1">{code}</div>'
                f'<div class="l2"></div><div class="l3"></div></div></a></td>'
            )
        parts.append("</tr>")

    parts.append("</tbody></table></div>")

    # Client-side highlight: <img onerror> trick to run JS inside innerHTML.
    # Adds a click listener (once) that toggles .cell-selected on the clicked <td>.
    highlight_js = (
        "if(!document._hlReady){"
        "document._hlReady=true;"
        'document.addEventListener("click",function(e){'
        'var a=e.target.closest("a");if(!a)return;'
        'var td=a.closest("td");if(!td)return;'
        'if(td.className.indexOf("ncell")<0'
        '&&td.className.indexOf("dc-cell")<0)return;'
        'var p=document.querySelectorAll(".cell-selected");'
        'for(var i=0;i<p.length;i++)p[i].classList.remove("cell-selected");'
        'td.classList.add("cell-selected");'
        "});}"
        "this.remove();"
    )
    parts.append(f"<img src='' onerror='{highlight_js}' style='display:none'>")

    return "".join(parts)


from demo.parsing import parse_click_id as _parse_click_id  # noqa: E402


# ── Detail panels ────────────────────────────────────────────────────────────

def _render_detail_item(label: str, value: str) -> str:
    return (
        f'<div class="dp-item">'
        f'<div class="dp-label">{_html.escape(str(label))}</div>'
        f'<div class="dp-value">{_html.escape(str(value))}</div>'
        f'</div>'
    )


# (colonna_csv, etichetta_italiana, tipo)  — pool_id escluso (nascosto)
_EMP_ADVANCED_FIELDS: list[tuple[str, str, str]] = [
    ("ore_dovute_mese_h",                  "Ore dovute al mese (h)",              "float"),
    ("saldo_prog_iniziale_h",              "Saldo progressivo iniziale (h)",       "float"),
    ("max_month_hours_h",                  "Max ore mensili (h)",                  "float"),
    ("max_week_hours_h",                   "Max ore settimanali (h)",              "float"),
    ("can_work_night",                     "Può lavorare di notte",               "bool"),
    ("max_nights_week",                    "Max notti settimanali",                "int"),
    ("max_nights_month",                   "Max notti mensili",                    "int"),
    ("max_consecutive_nights",             "Max notti consecutive",               "int"),
    ("saturday_count_ytd",                 "Sabati lavorati (anno in corso)",      "int"),
    ("sunday_count_ytd",                   "Domeniche lavorate (anno in corso)",   "int"),
    ("holiday_count_ytd",                  "Festività lavorate (anno in corso)",   "int"),
    ("rest11h_max_monthly_exceptions",     "Max eccezioni riposo 11h mensili",     "int"),
    ("rest11h_max_consecutive_exceptions", "Max eccezioni riposo 11h consecutive", "int"),
    ("cross_max_shifts_month",             "Max turni cross-reparto mensili",      "int"),
]


def _is_empty_val(raw) -> bool:
    """True se il valore è assente / NaN / stringa vuota."""
    return (
        raw is None
        or (isinstance(raw, float) and math.isnan(raw))
        or str(raw).strip() in ("", "nan", "None")
    )


def show_employee_detail(eid: str, emp_df: pd.DataFrame) -> None:
    matches = emp_df[emp_df["employee_id"].astype(str) == eid]
    if matches.empty:
        st.warning("Dipendente non trovato.")
        return
    emp = matches.iloc[0]

    # ── Dati anagrafici (sola lettura) ────────────────────────────────────────
    items = "".join([
        _render_detail_item("Nome", str(emp.get("nome", eid))),
        _render_detail_item("Ruolo", str(emp.get("role", "--"))),
        _render_detail_item("Reparto", str(emp.get("reparto_id", "--"))),
    ])
    st.markdown(
        f'<div class="detail-panel"><div class="dp-grid">{items}</div></div>',
        unsafe_allow_html=True,
    )

    # ── Impostazioni avanzate (modificabili) ──────────────────────────────────
    available = [
        (col, label, ftype)
        for col, label, ftype in _EMP_ADVANCED_FIELDS
        if col in emp_df.columns
    ]
    if not available:
        return

    with st.expander("Impostazioni avanzate"):
        st.caption("Lascia i campi vuoti per usare il valore di default del solver.")
        col_l, col_r = st.columns(2)
        for i, (col, label, ftype) in enumerate(available):
            raw = emp.get(col)
            target = col_l if i % 2 == 0 else col_r
            with target:
                if ftype == "bool":
                    if _is_empty_val(raw):
                        idx = 0
                    elif str(raw).lower() in ("true", "1"):
                        idx = 1
                    else:
                        idx = 2
                    st.selectbox(
                        label,
                        options=["(default)", "Sì", "No"],
                        index=idx,
                        key=f"emp_adv_{eid}_{col}",
                    )
                else:
                    current = "" if _is_empty_val(raw) else str(raw)
                    st.text_input(
                        label,
                        value=current,
                        placeholder="default",
                        key=f"emp_adv_{eid}_{col}",
                    )

        st.divider()
        if st.button("Salva modifiche", key=f"emp_adv_{eid}_save", type="primary"):
            df = st.session_state["data"]["employees"].copy()
            mask = df["employee_id"].astype(str) == eid
            errors: list[str] = []
            for col, label, ftype in available:
                widget_key = f"emp_adv_{eid}_{col}"
                raw_val = st.session_state.get(widget_key, "")
                if ftype == "bool":
                    if raw_val == "Sì":
                        parsed: object = True
                    elif raw_val == "No":
                        parsed = False
                    else:
                        parsed = float("nan")
                else:
                    raw_str = str(raw_val).strip()
                    if raw_str == "":
                        parsed = float("nan")
                    else:
                        try:
                            parsed = int(raw_str) if ftype == "int" else float(raw_str)
                        except ValueError:
                            errors.append(f"'{label}': valore non valido '{raw_str}'")
                            continue
                df.loc[mask, col] = parsed
            if errors:
                st.error("Errori di formato:\n" + "\n".join(f"• {e}" for e in errors))
            else:
                st.session_state["data"]["employees"] = df
                st.rerun()


def show_shift_detail(eid: str, date_str: str, data: dict) -> None:
    emp_df = data["employees"]
    shifts_df = data["shifts"]

    matches = emp_df[emp_df["employee_id"].astype(str) == eid]
    if matches.empty:
        st.warning("Dipendente non trovato.")
        return
    emp = matches.iloc[0]
    emp_name = str(emp.get("nome", eid))
    emp_reparto = str(emp.get("reparto_id", "--"))

    _, all_rows = build_schedule(data)
    code = "R"
    for row in all_rows:
        if row["eid"] == eid:
            code = row["days"].get(date_str, "R")
            break

    shift_name = "--"
    shift_start = "--"
    shift_end = "--"
    if code:
        shift_matches = shifts_df[shifts_df["shift_id"].astype(str) == code]
        if not shift_matches.empty:
            s = shift_matches.iloc[0]
            shift_name = f'{code} ({s.get("nome", "")})'
            shift_start = str(s.get("start", "--"))
            shift_end = str(s.get("end", "--"))
        else:
            shift_name = code

    items = "".join([
        _render_detail_item("Dipendente", emp_name),
        _render_detail_item("Data", date_str),
        _render_detail_item("Turno", shift_name),
        _render_detail_item("Orario inizio", shift_start),
        _render_detail_item("Orario fine", shift_end),
    ])
    st.markdown(
        f'<div class="detail-panel"><div class="dp-grid">{items}</div></div>',
        unsafe_allow_html=True,
    )


# ══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ══════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown('<div class="sidebar-section-title">Caricamento Dati</div>', unsafe_allow_html=True)

    data_source = st.radio(
        "Sorgente dati",
        ["July (dataset demo)", "Seleziona cartella"],
        index=0,
        label_visibility="collapsed",
    )

    dataset_folder: Path | None = None
    if data_source == "July (dataset demo)":
        dataset_folder = PROJECT_ROOT / "July"
    else:
        custom_path = st.text_input("Percorso cartella", str(PROJECT_ROOT / "July"))
        if custom_path:
            dataset_folder = Path(custom_path)

    if _button("Carica", type="primary", width="stretch"):
        if dataset_folder and dataset_folder.exists():
            try:
                st.session_state["data"] = load_dataset(dataset_folder)
                st.session_state["loaded"] = True
                # Pulisci stato sessione del dataset precedente.
                _clear_session_keys(_DATASET_RESET_KEYS)
            except (
                OSError,
                IOError,
                ValueError,
                TypeError,
                KeyError,
                pd.errors.ParserError,
                pd.errors.EmptyDataError,
                yaml.YAMLError,
                RuntimeError,
            ) as e:
                LOGGER.exception("Errore durante il caricamento dataset: %s", dataset_folder)
                st.error(str(e))
        else:
            st.error("Cartella non trovata")

    st.markdown("---")

    if st.session_state.get("loaded"):
        st.markdown(
            '<div class="sidebar-section-title">Parametri Calcolo</div>',
            unsafe_allow_html=True,
        )

        data = st.session_state["data"]
        cfg = data["cfg"]
        emp_df = data["employees"]
        all_reparti = sorted(emp_df["reparto_id"].dropna().unique().tolist())

        calc_reparti = st.multiselect(
            "Reparti da ottimizzare",
            options=all_reparti,
            default=all_reparti,
            help="Seleziona i reparti da includere nel calcolo della programmazione",
        )

        horizon = cfg.get("horizon", {})
        h_start = pd.Timestamp(horizon.get("start_date", "2024-07-01")).date()
        h_end = pd.Timestamp(horizon.get("end_date", "2024-07-31")).date()

        col_s, col_e = st.columns(2)
        with col_s:
            calc_start = st.date_input("Inizio", value=h_start)
        with col_e:
            calc_end = st.date_input("Fine", value=h_end)

        cross_default = cfg.get("cross", {}).get("allow_cross", False)
        calc_cross = st.checkbox(
            "Permetti cross-reparto",
            value=bool(cross_default),
            help="Consenti assegnazione di dipendenti a reparti diversi dal proprio",
        )
        calc_stability = st.checkbox(
            "Stabilita orario",
            value=True,
            help="Minimizza le modifiche rispetto alla programmazione esistente",
        )

        # ── Impostazioni avanzate ─────────────────────────────────────────────
        with st.expander("Impostazioni avanzate"):
            _d    = cfg.get("defaults", {})
            _rr   = cfg.get("rest_rules", {})
            _n    = _d.get("night", {})
            _r11  = _d.get("rest11h", {})
            _ov   = _d.get("overstaffing", {})
            _bal  = _d.get("balance", {})
            _cr   = cfg.get("cross", {})
            _rl   = cfg.get("roles", {})

            # ── Vincoli di riposo ─────────────────────────────────────────────
            st.markdown("**Vincoli di riposo**")
            st.number_input(
                "Riposo minimo tra turni (h)",
                min_value=0.0, step=0.5,
                value=float(_rr.get("min_between_shifts_h", 11)),
                key="cfg_rest_min_between_h",
            )
            _ca, _cb = st.columns(2)
            with _ca:
                st.number_input(
                    "Min gg riposo settimanale",
                    min_value=0, step=1,
                    value=int(_d.get("weekly_rest_min_days", 1)),
                    key="cfg_weekly_rest_min_days",
                )
                st.number_input(
                    "Max eccezioni 11h mensili",
                    min_value=0, step=1,
                    value=int(_r11.get("max_monthly_exceptions", 2)),
                    key="cfg_rest11h_max_monthly",
                )
            with _cb:
                st.number_input(
                    "Min gg riposo bisettimanale",
                    min_value=0, step=1,
                    value=int(_d.get("biweekly_rest_min_days", 2)),
                    key="cfg_biweekly_rest_min_days",
                )
                st.number_input(
                    "Max eccezioni 11h consecutive",
                    min_value=0, step=1,
                    value=int(_r11.get("max_consecutive_exceptions", 1)),
                    key="cfg_rest11h_max_consec",
                )

            # ── Notti ─────────────────────────────────────────────────────────
            st.markdown("**Notti**")
            _ca, _cb = st.columns(2)
            with _ca:
                st.number_input(
                    "Max consecutive",
                    min_value=0, step=1,
                    value=int(_n.get("max_consecutive_nights", 3)),
                    key="cfg_night_max_consec",
                )
                st.number_input(
                    "Max/settimana",
                    min_value=0, step=1,
                    value=int(_n.get("max_per_week", 2)),
                    key="cfg_night_max_week",
                )
            with _cb:
                st.number_input(
                    "Max/mese",
                    min_value=0, step=1,
                    value=int(_n.get("max_per_month", 8)),
                    key="cfg_night_max_month",
                )
                st.checkbox(
                    "Abilitate (default)",
                    value=bool(_n.get("can_work_night", True)),
                    key="cfg_night_can_work",
                )
            _ca, _cb = st.columns(2)
            with _ca:
                st.checkbox(
                    "IP — notti abilitate",
                    value=bool(_rl.get("IP", {}).get("can_work_night", True)),
                    key="cfg_roles_IP_night",
                )
            with _cb:
                st.checkbox(
                    "OSS — notti abilitate",
                    value=bool(_rl.get("OSS", {}).get("can_work_night", True)),
                    key="cfg_roles_OSS_night",
                )

            # ── Bilancio ──────────────────────────────────────────────────────
            st.markdown("**Bilancio**")
            st.number_input(
                "Max delta bilancio mensile (h)",
                min_value=0.0, step=1.0,
                value=float(_bal.get("max_balance_delta_month_h", 36)),
                key="cfg_balance_max_delta",
            )

            # ── Overstaffing ──────────────────────────────────────────────────
            st.markdown("**Overstaffing**")
            _ca, _cb = st.columns(2)
            with _ca:
                st.checkbox(
                    "Abilitato",
                    value=bool(_ov.get("enabled", True)),
                    key="cfg_overst_enabled",
                )
            with _cb:
                st.number_input(
                    "Cap per gruppo",
                    min_value=0, step=1,
                    value=int(_ov.get("group_cap_default", 1)),
                    key="cfg_overst_cap",
                )

            # ── Cross-reparto ─────────────────────────────────────────────────
            st.markdown("**Cross-reparto**")
            st.number_input(
                "Max turni cross-reparto/mese",
                min_value=0, step=1,
                value=int(_cr.get("max_shifts_month", 6)),
                key="cfg_cross_max_shifts",
            )

            # ── Applica ───────────────────────────────────────────────────────
            st.divider()
            if _button("Applica configurazione", key="cfg_adv_apply",
                       width="stretch"):
                _c = copy.deepcopy(st.session_state["data"]["cfg"])
                _c.setdefault("rest_rules", {})["min_between_shifts_h"] = (
                    st.session_state["cfg_rest_min_between_h"]
                )
                _dd = _c.setdefault("defaults", {})
                _dd["weekly_rest_min_days"]   = st.session_state["cfg_weekly_rest_min_days"]
                _dd["biweekly_rest_min_days"] = st.session_state["cfg_biweekly_rest_min_days"]
                _dd.setdefault("rest11h", {}).update({
                    "max_monthly_exceptions":     st.session_state["cfg_rest11h_max_monthly"],
                    "max_consecutive_exceptions": st.session_state["cfg_rest11h_max_consec"],
                })
                _dd.setdefault("night", {}).update({
                    "max_consecutive_nights": st.session_state["cfg_night_max_consec"],
                    "max_per_week":           st.session_state["cfg_night_max_week"],
                    "max_per_month":          st.session_state["cfg_night_max_month"],
                    "can_work_night":         st.session_state["cfg_night_can_work"],
                })
                _dd.setdefault("balance", {})["max_balance_delta_month_h"] = (
                    st.session_state["cfg_balance_max_delta"]
                )
                _dd.setdefault("overstaffing", {}).update({
                    "enabled":           st.session_state["cfg_overst_enabled"],
                    "group_cap_default": st.session_state["cfg_overst_cap"],
                })
                _c.setdefault("cross", {})["max_shifts_month"] = (
                    st.session_state["cfg_cross_max_shifts"]
                )
                _c.setdefault("roles", {}).setdefault("IP", {})["can_work_night"] = (
                    st.session_state["cfg_roles_IP_night"]
                )
                _c.setdefault("roles", {}).setdefault("OSS", {})["can_work_night"] = (
                    st.session_state["cfg_roles_OSS_night"]
                )
                st.session_state["data"]["cfg"] = _c
                st.success("Configurazione aggiornata.")

        st.markdown("---")

        calc_time = st.radio("Tempo calcolo", list(TIME_PRESETS.keys()), index=1)

        # Salva parametri nel session state (disponibili anche al prossimo run)
        st.session_state["calc_params"] = {
            "reparti": calc_reparti,
            "start": str(calc_start),
            "end": str(calc_end),
            "cross": calc_cross,
            "time_s": TIME_PRESETS[calc_time],
            "stability": calc_stability,
        }

        st.markdown("---")

        # Validazione date prima di abilitare il pulsante
        _date_error: str | None = None
        if calc_start > calc_end:
            _date_error = "La data di inizio è successiva alla data di fine."
        elif calc_start < h_start or calc_end > h_end:
            _date_error = (
                f"Le date devono essere comprese nell'orizzonte del dataset "
                f"({h_start} – {h_end})."
            )

        if _date_error:
            st.caption(f"⚠️ {_date_error}")

        if not _SOLVER_AVAILABLE:
            _button(
                "ESEGUI OTTIMIZZAZIONE",
                type="primary",
                width="stretch",
                disabled=True,
            )
            st.caption("⚠️ Modulo solver non disponibile (dipendenze mancanti).")
        elif _button(
            "ESEGUI OTTIMIZZAZIONE",
            type="primary",
            width="stretch",
            disabled=bool(_date_error),
        ):
            # Pattern "request": imposta il flag e lascia che il main area
            # processi il run con lo spinner centrato nella pagina principale.
            if not _queue_normal_run_from_calc_params():
                st.error("Parametri di calcolo non validi.")


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN AREA
# ══════════════════════════════════════════════════════════════════════════════

if not st.session_state.get("loaded"):
    st.markdown(
        '<div class="sky-header">'
        '<div><div class="hdr-title">SKYppm &mdash; Piano di programmazione mensile</div>'
        '<div class="hdr-sub">Carica un dataset dalla sidebar per iniziare</div></div>'
        f'{_LOGO_IMG}'
        '</div>',
        unsafe_allow_html=True,
    )
    st.stop()

data = st.session_state["data"]
cfg = data["cfg"]
start_date = pd.Timestamp(cfg["horizon"]["start_date"]).date()
month_label = f"{MONTH_NAMES.get(start_date.month, '')} {start_date.year}"

st.markdown(
    '<div class="sky-header">'
    f'{_LOGO_IMG}'
    f'<div><div class="hdr-title">SKYppm &mdash; Piano di programmazione mensile</div></div>'
    '</div>',
    unsafe_allow_html=True,
)


# ── Coverage preview ─────────────────────────────────────────────────────


def _build_assignments_df_preview(
    assignments_df: pd.DataFrame,
    edited_cells: dict,
    employees_df: pd.DataFrame,
) -> pd.DataFrame:
    """Costruisce un assignments_df con override delle celle editate manualmente.

    Per celle non editate, mantiene le assegnazioni solver originali.
    Per celle editate:
      - preassignment edit → reparto = home del dipendente
      - lock edit → reparto = reparto indicato nel lock (se disponibile), altrimenti home
      - shift_code = None → rimuove l'assegnazione (turno svuotato)
    """
    if assignments_df is None or assignments_df.empty:
        adf = pd.DataFrame(
            columns=["date", "reparto_id", "shift_code", "slot_id", "employee_id"]
        )
    else:
        adf = assignments_df.copy()

    if not edited_cells:
        return adf

    # Mappa employee_id → reparto home
    _home_rep: dict[str, str] = {}
    if not employees_df.empty and "employee_id" in employees_df.columns and "reparto_id" in employees_df.columns:
        _home_rep = dict(zip(
            employees_df["employee_id"].astype(str),
            employees_df["reparto_id"].astype(str),
        ))

    # Risolvi priorità: per ogni (eid, date), lock vince su preassignment.
    # Le chiavi di edited_cells sono (eid, date, edit_type).
    effective: dict[tuple[str, str], dict] = {}
    for key, info in edited_cells.items():
        if len(key) == 3:
            cell_eid, cell_date, edit_type = key
        else:
            # Backward compat: chiave vecchia (eid, date) senza tipo
            cell_eid, cell_date = key[:2]
            edit_type = info.get("edit_type", "preassignment")
        prev = effective.get((cell_eid, cell_date))
        # Lock ha sempre priorità su preassignment
        if prev is None or edit_type == "lock":
            effective[(cell_eid, cell_date)] = info

    for (cell_eid, cell_date), info in effective.items():
        # Rimuovi assegnazione solver per questa (employee, date)
        if not adf.empty and "employee_id" in adf.columns and "date" in adf.columns:
            rm = (
                (adf["employee_id"].astype(str) == cell_eid)
                & (adf["date"].apply(lambda x: str(pd.Timestamp(x).date())) == cell_date)
            )
            adf = adf[~rm].reset_index(drop=True)

        shift = info.get("shift_code")
        if shift is None:
            continue  # turno svuotato ("--"), niente da aggiungere

        # Determina reparto
        if info.get("edit_type") == "lock" and info.get("reparto_id"):
            rep = info["reparto_id"]
        else:
            rep = _home_rep.get(cell_eid, "")

        adf = pd.concat([adf, pd.DataFrame([{
            "date": pd.Timestamp(cell_date),
            "reparto_id": rep,
            "shift_code": shift,
            "slot_id": "",
            "employee_id": cell_eid,
        }])], ignore_index=True)

    return adf


def compute_coverage_preview(
    data: dict,
    all_rows: list[dict],
    assignments_df: pd.DataFrame | None = None,
) -> dict:
    """Calcola per ogni (reparto, data) se il fabbisogno è soddisfatto.

    Ritorna dict {(reparto_id, date_str): {"status": "S"|"N", "details": [...]}}.
    Celle senza fabbisogno non compaiono nel dict.

    Se assignments_df è fornito (output del solver con colonne date/reparto_id/
    shift_code/employee_id), la presenza viene costruita dal reparto effettivo
    di lavoro — gestendo correttamente le assegnazioni cross-reparto.
    Altrimenti si usa all_rows (reparto home dell'employee, fallback).
    """
    mp_df = data.get("month_plan", pd.DataFrame())
    cg_df = data.get("coverage_groups", pd.DataFrame())
    cr_df = data.get("coverage_roles", pd.DataFrame())

    mp_df, cg_df, cr_df, _ = _apply_demand_overrides_tables(
        mp_df,
        cg_df,
        cr_df,
        data.get("demand_overrides", pd.DataFrame()),
        include_base_coverage=True,
    )

    if mp_df.empty or cg_df.empty:
        return {}

    # Normalizza case
    def _norm(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
        df = df.copy()
        for c in cols:
            if c in df.columns:
                df[c] = df[c].astype(str).str.strip().str.upper()
        return df

    mp_df = _norm(mp_df, ["reparto_id", "shift_code", "coverage_code"])
    cg_df = _norm(cg_df, ["coverage_code", "shift_code", "reparto_id", "gruppo"])
    cr_df = _norm(cr_df, ["coverage_code", "shift_code", "reparto_id", "gruppo"])
    role_col = "role" if "role" in cr_df.columns else ("ruolo" if "ruolo" in cr_df.columns else None)

    cg_df["total_staff"] = pd.to_numeric(cg_df["total_staff"], errors="coerce").fillna(0).astype(int)
    if not cr_df.empty and role_col:
        cr_df["min_ruolo"] = pd.to_numeric(cr_df["min_ruolo"], errors="coerce").fillna(0).astype(int)
        cr_df["_role"] = cr_df[role_col].astype(str).str.strip().str.upper()

    # Presenza: {(date_str, reparto, shift): {role: count}}
    presence: dict[tuple, dict] = {}
    if assignments_df is not None and not assignments_df.empty:
        # Percorso preciso: usa il reparto effettivo di lavoro dal solver output.
        # Gestisce correttamente le assegnazioni cross-reparto.
        _emp_df = data.get("employees", pd.DataFrame())
        _emp_role: dict[str, str] = {}
        if not _emp_df.empty and "role" in _emp_df.columns:
            _emp_role = {
                str(r["employee_id"]): str(r["role"]).strip().upper()
                for _, r in _emp_df.iterrows()
            }
        for _, _ar in assignments_df.iterrows():
            _ds  = str(pd.Timestamp(_ar["date"]).date())
            _rep = str(_ar["reparto_id"]).strip().upper()
            _sh  = str(_ar["shift_code"]).strip().upper()
            _rol = _emp_role.get(str(_ar["employee_id"]), "")
            _key = (_ds, _rep, _sh)
            presence.setdefault(_key, {})
            if _rol:
                presence[_key][_rol] = presence[_key].get(_rol, 0) + 1
    else:
        # Fallback: piano da all_rows — usa reparto home (cross-dept non considerato)
        for row in all_rows:
            reparto = row["reparto"].upper()
            role = row["role"].upper()
            if not reparto:
                continue
            for ds, state in row["days"].items():
                if not state:
                    continue
                key = (ds, reparto, state.upper())
                presence.setdefault(key, {})
                presence[key][role] = presence[key].get(role, 0) + 1

    result: dict[tuple, dict] = {}

    for _, plan_row in mp_df.iterrows():
        ds = str(plan_row["data"])
        reparto = str(plan_row["reparto_id"])
        shift = str(plan_row["shift_code"])
        cov_code = str(plan_row["coverage_code"])

        cell_key = (reparto, ds)
        if cell_key not in result:
            result[cell_key] = {"status": "S", "details": []}

        grp_mask = (
            (cg_df["coverage_code"] == cov_code) &
            (cg_df["shift_code"] == shift) &
            (cg_df["reparto_id"] == reparto)
        )
        pres = presence.get((ds, reparto, shift), {})

        for _, grp_row in cg_df[grp_mask].iterrows():
            gruppo = str(grp_row["gruppo"])
            total_req = int(grp_row["total_staff"])
            ruoli_str = str(grp_row.get("ruoli_totale", ""))
            ruoli = [r.strip().upper() for r in ruoli_str.split("|") if r.strip()]

            group_present = sum(pres.get(r, 0) for r in ruoli)
            total_ok = group_present >= total_req
            if not total_ok:
                result[cell_key]["status"] = "N"

            role_details: list[dict] = []
            if not cr_df.empty and role_col:
                role_mask = (
                    (cr_df["coverage_code"] == cov_code) &
                    (cr_df["shift_code"] == shift) &
                    (cr_df["reparto_id"] == reparto) &
                    (cr_df["gruppo"] == gruppo)
                )
                for _, rr in cr_df[role_mask].iterrows():
                    role = str(rr["_role"])
                    min_req = int(rr["min_ruolo"])
                    present_n = pres.get(role, 0)
                    ok = present_n >= min_req
                    role_details.append({"role": role, "min_required": min_req, "present": present_n, "ok": ok})
                    if not ok and min_req > 0:
                        result[cell_key]["status"] = "N"

            result[cell_key]["details"].append({
                "shift_code": shift,
                "coverage_code": str(plan_row.get("base_coverage_code", cov_code)).strip().upper(),
                "gruppo": gruppo,
                "total_required": total_req,
                "total_present": group_present,
                "total_ok": total_ok,
                "roles": role_details,
            })

    return result


def _parse_cov_click_id(click_id: str, expected_counter: int) -> dict | None:
    """Parse 'cov-{counter}-{reparto}-{YYYY-MM-DD}' → {reparto, date}."""
    if not click_id or not click_id.startswith("cov-"):
        return None
    rest = click_id[4:]
    try:
        dash = rest.index("-")
        if int(rest[:dash]) != expected_counter:
            return None
        remainder = rest[dash + 1:]          # "{reparto}-YYYY-MM-DD"
        date_str = remainder[-10:]           # "YYYY-MM-DD"
        reparto = remainder[:-11]            # tutto prima di "-YYYY-MM-DD"
        if len(date_str) != 10:
            return None
        return {"reparto": reparto, "date": date_str}
    except (ValueError, IndexError):
        return None


_COV_CSS = """<style>
body{margin:0;font-family:'Inter',system-ui,sans-serif;}
.cov-tbl{border-collapse:collapse;font-size:0.78rem;min-width:max-content;}
.cov-tbl th,.cov-tbl td{border:1px solid #d0e8ea;padding:0;height:28px;text-align:center;min-width:32px;}
.cov-tbl .cnhdr{min-width:130px;max-width:130px;text-align:left;padding:0 8px;
    background:#f0f8f9;font-weight:600;color:#093d41;position:sticky;left:0;z-index:2;}
.cov-tbl .cdhdr{background:#f0f8f9;font-size:0.7rem;color:#555;}
.cov-tbl .cdhdr.sat{background:#fff3cd;}.cov-tbl .cdhdr.sun{background:#fde8e8;}
.cov-s{background:#d1f0da;}.cov-s a{color:#155724 !important;}
.cov-n{background:#fad7da;}.cov-n a{color:#721c24 !important;}
.cov-e{background:#f5f5f5;}
.cov-tbl td a{display:block;width:100%;height:100%;line-height:28px;
    color:inherit;text-decoration:none;font-weight:700;}
.cov-tbl td.cov-s:hover,.cov-tbl td.cov-n:hover{filter:brightness(0.9);cursor:pointer;}
.cov-tbl td.cov-sel{outline:3px solid #0a9ba6 !important;outline-offset:-3px;position:relative;z-index:2;}
</style>"""


def render_coverage_grid(dates: list[date], reparti: list[str], cov_data: dict, cov_counter: int, cov_selection=None) -> str:
    parts: list[str] = [_COV_CSS, '<div style="overflow-x:auto;max-height:260px;overflow-y:auto;">',
                        '<table class="cov-tbl"><thead><tr><th class="cnhdr">Reparto</th>']
    for d in dates:
        cls = "cdhdr"
        if d.weekday() == 5: cls += " sat"
        if d.weekday() == 6: cls += " sun"
        parts.append(f'<th class="{cls}">{d.day}<br><span style="font-size:0.62rem">{DAY_LETTERS[d.weekday()]}</span></th>')
    parts.append("</tr></thead><tbody>")

    for reparto in reparti:
        parts.append(f'<tr><td class="cnhdr">{reparto}</td>')
        for d in dates:
            ds = str(d)
            cell = cov_data.get((reparto, ds))
            sel_cls = " cov-sel" if cov_selection == (reparto, ds) else ""
            if cell is None:
                parts.append('<td class="cov-e"></td>')
            elif cell["status"] == "S":
                parts.append(f'<td class="cov-s{sel_cls}"><a href="#" id="cov-{cov_counter}-{reparto}-{ds}">S</a></td>')
            else:
                parts.append(f'<td class="cov-n{sel_cls}"><a href="#" id="cov-{cov_counter}-{reparto}-{ds}">N</a></td>')
        parts.append("</tr>")

    parts.append("</tbody></table></div>")
    return "".join(parts)


# ── Detail dialogs (modal overlay) ────────────────────────────────────────
# Tre funzioni separate con titoli diversi: ogni @st.dialog crea un componente
# React INDIPENDENTE nel frontend. Stessa funzione = stessa istanza React =
# content bleed tra chiamate successive con contenuto diverso.

@st.dialog("Dettaglio dipendente")
def _show_emp_dialog(payload: dict, app_data: dict) -> None:
    show_employee_detail(payload["eid"], app_data["employees"])


@st.dialog("Dettaglio stato")
def _show_day_dialog(payload: dict, app_data: dict) -> None:
    eid = payload["eid"]
    date_str = payload["date"]
    if not date_str:
        return

    # ── Rilevamento giorno consolidato (draft mode, data < calc_start) ────
    _is_consolidated = False
    _draft = st.session_state.get("draft")
    if st.session_state.get("view_draft") and _draft:
        _cs = _draft.get("calc_start")
        if _cs:
            try:
                _is_consolidated = pd.Timestamp(date_str).date() < pd.Timestamp(_cs).date()
            except (TypeError, ValueError):
                pass

    # ── Flag: siamo in vista draft (non consolidata)? ────────────────────
    _in_draft_view = (
        st.session_state.get("view_draft", False)
        and _draft is not None
        and not _is_consolidated
    )

    # In vista bozza, passa dati coerenti con la griglia:
    # PA = merge di draft solver (finestra) + base2 (fuori finestra), come fa la griglia.
    # Lock = base2.
    if _in_draft_view:
        _detail_data = dict(app_data)
        _base2_pa = _draft.get("base_preassignments", app_data["preassignments"])
        _win_s = _draft.get("calc_start")
        _win_e = _draft.get("calc_end")
        if _win_s and _win_e:
            _detail_data["preassignments"] = _merge_draft_pa(
                _draft["preassignments"], _base2_pa, _win_s, _win_e,
            )
        else:
            _detail_data["preassignments"] = _draft.get("preassignments", pd.DataFrame())
        _detail_data["locks"] = _draft.get("base_locks", app_data.get("locks", pd.DataFrame()))
        show_shift_detail(eid, date_str, _detail_data)
    else:
        show_shift_detail(eid, date_str, app_data)

    if _is_consolidated:
        st.info(
            "Giorno consolidato — fuori dalla finestra di ottimizzazione. "
            "Visualizzazione in sola lettura."
        )

    st.divider()
    shifts_df = app_data["shifts"]

    # ── Codici turno/stato ────────────────────────────────────────────────────
    demand_shift_ids = set(
        shifts_df.loc[
            shifts_df["duration_min"].fillna(0).astype(float) > 0,
            "shift_id",
        ].astype(str).unique()
    )
    _cfg = app_data.get("cfg", {})
    _raw_sc = _cfg.get("state_codes") if isinstance(_cfg, dict) else None
    _all_sc = (
        [str(s).strip().upper() for s in _raw_sc if str(s).strip()]
        if _raw_sc else ["M", "P", "N", "G", "SN", "R", "F"]
    )
    non_demand_codes = [s for s in _all_sc if s not in demand_shift_ids]

    # Collect FORBIDDEN shifts for this emp+date to exclude from preassignment options
    if _in_draft_view:
        _locks_early = _draft.get("base_locks", pd.DataFrame())
    else:
        _locks_early = app_data.get("locks", pd.DataFrame())
    _forbidden_for_pa: set[str] = set()
    if not _locks_early.empty and "lock_type" in _locks_early.columns:
        _fm = (
            (_locks_early["employee_id"].astype(str).str.strip() == eid)
            & (_locks_early["date"].astype(str).str.strip() == date_str)
            & (_locks_early["lock_type"] == "FORBIDDEN")
        )
        _forbidden_for_pa = set(_locks_early[_fm]["shift_code"].astype(str).tolist())
    # Preassignment options: demand shifts from CSV + non-demand state codes (SN, R…), minus forbidden
    _shift_csv_ids = list(shifts_df["shift_id"].astype(str).unique())
    _extra_sc = [s for s in _all_sc if s not in set(_shift_csv_ids)]
    shift_options = ["--"] + [
        s for s in _shift_csv_ids + _extra_sc if s not in _forbidden_for_pa
    ]
    # In vista draft leggi dalla PA merge (stessa della griglia), altrimenti dal piano corrente
    if _in_draft_view:
        _b2pa = _draft.get("base_preassignments", app_data["preassignments"])
        _ws = _draft.get("calc_start")
        _we = _draft.get("calc_end")
        _dpa = _draft.get("preassignments", pd.DataFrame())
        if _ws and _we:
            pa_df = _merge_draft_pa(_dpa, _b2pa, _ws, _we)
        else:
            pa_df = _dpa
    else:
        pa_df = app_data["preassignments"]
    current = "--"
    _pa_code_col = next((c for c in ("state_code", "shift_code", "turno") if c in pa_df.columns), None)
    if not pa_df.empty and "employee_id" in pa_df.columns and "data" in pa_df.columns and _pa_code_col:
        mask = (pa_df["employee_id"].astype(str) == eid) & (pa_df["data"].astype(str) == date_str)
        if mask.any():
            current = str(pa_df.loc[mask, _pa_code_col].iloc[0])
    # If current preassignment is now forbidden, reset to "--"
    if current in _forbidden_for_pa:
        current = "--"
    idx = shift_options.index(current) if current in shift_options else 0
    selected = st.selectbox("Modifica preassegnazione", shift_options, index=idx, disabled=_is_consolidated)

    if st.button("Salva", type="primary", disabled=_is_consolidated):
        if _in_draft_view:
            df = _draft["base_preassignments"].copy()
        else:
            df = app_data["preassignments"].copy()
        if not df.empty and "employee_id" in df.columns and "data" in df.columns:
            mask = (df["employee_id"].astype(str) == eid) & (df["data"].astype(str) == date_str)
            df = df[~mask].reset_index(drop=True)
        if selected != "--":
            df = pd.concat([df, pd.DataFrame([{
                "employee_id": eid, "data": date_str, "state_code": selected,
            }])], ignore_index=True)
        if _in_draft_view:
            st.session_state["draft"]["base_preassignments"] = df
            # Aggiorna anche il draft solver PA così la griglia bozza
            # mostra subito la modifica e "Salva bozza" la preserva.
            draft_pa = st.session_state["draft"]["preassignments"].copy()
            if not draft_pa.empty and "employee_id" in draft_pa.columns and "data" in draft_pa.columns:
                dm = (draft_pa["employee_id"].astype(str) == eid) & (draft_pa["data"].astype(str) == date_str)
                draft_pa = draft_pa[~dm].reset_index(drop=True)
            if selected != "--":
                draft_pa = pd.concat([draft_pa, pd.DataFrame([{
                    "employee_id": eid, "data": date_str, "state_code": selected,
                }])], ignore_index=True)
            st.session_state["draft"]["preassignments"] = draft_pa
            st.session_state["draft"]["manual_edits"] = True
            # Registra cella editata per copertura preview.
            # Anche "--" (svuota) va registrato con shift_code=None:
            # _build_assignments_df_preview lo interpreta come "rimuovi
            # l'assegnazione solver", allineando la copertura alla griglia.
            _ec = st.session_state["draft"].get("edited_cells", {})
            _pa_key = (str(eid), str(date_str), "preassignment")
            _ec[_pa_key] = {
                "edit_type": "preassignment",
                "shift_code": selected if selected != "--" else None,
                "reparto_id": None,
            }
            st.session_state["draft"]["edited_cells"] = _ec
        else:
            st.session_state["data"]["preassignments"] = df
        st.rerun()

    # ── Sezione Lock ─────────────────────────────────────────────────────────
    st.divider()
    st.markdown("⚠️ **Lock turno** *(vincolo hard — sovrascrive preassegnazione)*")

    # Lista completa per lock: prima domanda (solo quelli con slot), poi non-domanda
    all_lock_codes = (
        [s for s in shifts_df["shift_id"].astype(str).unique() if s in demand_shift_ids]
        + non_demand_codes
    )

    # Leggi lock attuali per questo dipendente+data (base2 in bozza, base1 altrimenti)
    if _in_draft_view:
        locks_df = _draft.get("base_locks", pd.DataFrame())
    else:
        locks_df = app_data.get("locks", pd.DataFrame())
    must_shift: str | None = None
    forbidden_shifts: list[str] = []
    must_reparto: str = ""
    if not locks_df.empty and "lock_type" in locks_df.columns:
        lmask = (locks_df["employee_id"].astype(str).str.strip() == eid) & (locks_df["date"].astype(str).str.strip() == date_str)
        emp_locks = locks_df[lmask]
        must_rows = emp_locks[emp_locks["lock_type"] == "MUST_DO"]
        if not must_rows.empty:
            must_shift = str(must_rows.iloc[0]["shift_code"])
            must_reparto = str(must_rows.iloc[0].get("reparto_id", ""))
        forbidden_shifts = emp_locks[emp_locks["lock_type"] == "FORBIDDEN"]["shift_code"].tolist()

    # Reparto: "-- qualsiasi --" → state lock; reparto specifico → slot lock (solo domanda)
    emp_df = app_data["employees"]
    emp_reparto = ""
    emp_match = emp_df[emp_df["employee_id"].astype(str) == eid]
    if not emp_match.empty:
        emp_reparto = str(emp_match.iloc[0].get("reparto_id", ""))
    all_reparti = sorted(emp_df["reparto_id"].dropna().unique().tolist())
    reparto_options = ["-- qualsiasi --"] + all_reparti
    # Default reparto: quello del lock esistente; "-- qualsiasi --" per non-domanda o assente
    if must_reparto and must_reparto in all_reparti:
        _def_rep = must_reparto
    elif must_shift and must_shift not in demand_shift_ids:
        _def_rep = "-- qualsiasi --"
    else:
        _def_rep = emp_reparto if emp_reparto in all_reparti else "-- qualsiasi --"
    reparto_sel = st.selectbox(
        "Reparto", reparto_options,
        index=reparto_options.index(_def_rep) if _def_rep in reparto_options else 0,
        key="dlg_lock_reparto",
        disabled=_is_consolidated,
    )

    must_options = ["-- nessuno --"] + all_lock_codes
    must_idx = must_options.index(must_shift) if must_shift in must_options else 0
    must_sel = st.selectbox("Forza turno (MUST_DO)", must_options, index=must_idx, key="dlg_lock_must", disabled=_is_consolidated)

    # Indicatore tipo di lock
    if must_sel != "-- nessuno --":
        if must_sel in demand_shift_ids and reparto_sel != "-- qualsiasi --":
            st.caption(f"→ lock su **slot** ({must_sel} · reparto {reparto_sel})")
        elif must_sel in demand_shift_ids:
            st.caption(f"→ lock su **stato giornaliero** (qualsiasi slot {must_sel})")
        else:
            st.caption(f"→ lock su **stato giornaliero** ({must_sel})")

    forbidden_choices = [s for s in all_lock_codes if s != must_sel]
    forbidden_default = [f for f in forbidden_shifts if f in forbidden_choices]
    forbidden_sel = st.multiselect(
        "Vieta turni (FORBIDDEN)", forbidden_choices, default=forbidden_default,
        key="dlg_lock_forbidden",
        disabled=_is_consolidated,
    )

    if st.button("Salva lock", key="dlg_lock_save", disabled=_is_consolidated):
        # reparto_id vuoto → state lock; valorizzato → slot lock (se domanda)
        reparto_id_val = "" if reparto_sel == "-- qualsiasi --" else reparto_sel
        ldf = locks_df.copy() if not locks_df.empty else pd.DataFrame(
            columns=["employee_id", "date", "reparto_id", "shift_code", "lock_type"]
        )
        # Rimuovi lock precedenti per questo dipendente+data
        if not ldf.empty and "employee_id" in ldf.columns:
            lmask2 = (ldf["employee_id"].astype(str).str.strip() == eid) & (ldf["date"].astype(str).str.strip() == date_str)
            ldf = ldf[~lmask2].reset_index(drop=True)
        # Aggiungi MUST_DO se selezionato
        if must_sel != "-- nessuno --":
            ldf = pd.concat([ldf, pd.DataFrame([{
                "employee_id": eid, "date": date_str,
                "reparto_id": reparto_id_val if must_sel in demand_shift_ids else "",
                "shift_code": must_sel, "lock_type": "MUST_DO",
            }])], ignore_index=True)
        # Aggiungi FORBIDDEN
        for fs in forbidden_sel:
            ldf = pd.concat([ldf, pd.DataFrame([{
                "employee_id": eid, "date": date_str,
                "reparto_id": reparto_id_val if fs in demand_shift_ids else "",
                "shift_code": fs, "lock_type": "FORBIDDEN",
            }])], ignore_index=True)
        if _in_draft_view:
            st.session_state["draft"]["base_locks"] = ldf
        else:
            st.session_state["data"]["locks"] = ldf
        # Se MUST_DO selezionato, allinea PA allo stesso turno per evitare
        # penalità di stabilità artificiali (PA=M vs lock=N)
        if must_sel != "-- nessuno --":
            if _in_draft_view:
                _pa_must = st.session_state["draft"]["base_preassignments"].copy()
            else:
                _pa_must = st.session_state["data"]["preassignments"].copy()
            if not _pa_must.empty and "employee_id" in _pa_must.columns and "data" in _pa_must.columns:
                _pm = (
                    (_pa_must["employee_id"].astype(str) == eid)
                    & (_pa_must["data"].astype(str) == date_str)
                )
                _pa_must = _pa_must[~_pm].reset_index(drop=True)
            _pa_must = pd.concat([_pa_must, pd.DataFrame([{
                "employee_id": eid, "data": date_str, "state_code": must_sel,
            }])], ignore_index=True)
            if _in_draft_view:
                st.session_state["draft"]["base_preassignments"] = _pa_must
                # Allinea anche draft solver PA per coerenza griglia
                _dpa_must = st.session_state["draft"]["preassignments"].copy()
                if not _dpa_must.empty and "employee_id" in _dpa_must.columns and "data" in _dpa_must.columns:
                    _dpm = (
                        (_dpa_must["employee_id"].astype(str) == eid)
                        & (_dpa_must["data"].astype(str) == date_str)
                    )
                    _dpa_must = _dpa_must[~_dpm].reset_index(drop=True)
                _dpa_must = pd.concat([_dpa_must, pd.DataFrame([{
                    "employee_id": eid, "data": date_str, "state_code": must_sel,
                }])], ignore_index=True)
                st.session_state["draft"]["preassignments"] = _dpa_must
            else:
                st.session_state["data"]["preassignments"] = _pa_must
        # Se un turno vietato coincide con la preassegnazione attiva → svuota
        if forbidden_sel:
            if _in_draft_view:
                pa = st.session_state["draft"]["base_preassignments"].copy()
            else:
                pa = st.session_state["data"]["preassignments"].copy()
            if not pa.empty and "employee_id" in pa.columns and "data" in pa.columns:
                code_col = next((c for c in ("state_code", "shift_code", "turno") if c in pa.columns), None)
                if code_col:
                    pmask = (
                        (pa["employee_id"].astype(str) == eid)
                        & (pa["data"].astype(str) == date_str)
                        & (pa[code_col].astype(str).isin(forbidden_sel))
                    )
                    if pmask.any():
                        pa = pa[~pmask].reset_index(drop=True)
                        if _in_draft_view:
                            st.session_state["draft"]["base_preassignments"] = pa
                            # Pulisci anche draft solver PA per coerenza griglia
                            _dpa = st.session_state["draft"]["preassignments"].copy()
                            if not _dpa.empty and "employee_id" in _dpa.columns and "data" in _dpa.columns:
                                _dpa_code = next((c for c in ("state_code", "shift_code", "turno") if c in _dpa.columns), None)
                                if _dpa_code:
                                    _dpm = (
                                        (_dpa["employee_id"].astype(str) == eid)
                                        & (_dpa["data"].astype(str) == date_str)
                                        & (_dpa[_dpa_code].astype(str).isin(forbidden_sel))
                                    )
                                    if _dpm.any():
                                        _dpa = _dpa[~_dpm].reset_index(drop=True)
                                        st.session_state["draft"]["preassignments"] = _dpa
                        else:
                            st.session_state["data"]["preassignments"] = pa
        if _in_draft_view:
            st.session_state["draft"]["manual_edits"] = True
            _ec = st.session_state["draft"].get("edited_cells", {})
            _lock_key = (str(eid), str(date_str), "lock")
            _pa_key = (str(eid), str(date_str), "preassignment")
            if must_sel != "-- nessuno --":
                _ec[_lock_key] = {
                    "edit_type": "lock",
                    "shift_code": must_sel,
                    "reparto_id": reparto_id_val if reparto_id_val else None,
                }
            elif _pa_key in _ec:
                # MUST_DO rimosso ma c'è un override preassignment: basta
                # togliere il lock, la preassignment prende il sopravvento.
                _ec.pop(_lock_key, None)
            else:
                # MUST_DO rimosso e nessun override preassignment: serve un
                # override esplicito None per cancellare l'assegnazione solver
                # dalla preview copertura, coerente con la griglia che mostra
                # la cella svuotata.
                _ec.pop(_lock_key, None)
                _ec[_pa_key] = {
                    "edit_type": "preassignment",
                    "shift_code": None,
                    "reparto_id": None,
                }
            st.session_state["draft"]["edited_cells"] = _ec
        st.rerun()


@st.dialog("Dettaglio copertura")
def _show_cov_dialog(payload: dict, app_data: dict) -> None:
    from collections import defaultdict

    reparto = payload["reparto"]
    date_str = payload["date"]
    cov_d = payload["cov_data"]
    cell = cov_d.get((reparto, date_str))
    if not cell:
        st.info("Nessun fabbisogno per questo reparto in questa data.")
        return

    by_shift: dict[str, list] = defaultdict(list)
    for d in cell["details"]:
        by_shift[d["shift_code"]].append(d)

    target_name, overrides_df = _get_demand_overrides_target()
    ds = str(pd.Timestamp(date_str).date())
    rep = str(reparto).strip().upper()

    st.caption("Override puntuale su questa cella: totale gruppo e minimo ruolo.")
    if target_name == "draft":
        st.caption("Stai modificando la bozza corrente.")

    for shift, groups in by_shift.items():
        shift_norm = str(shift).strip().upper()
        st.markdown(f"**Turno {shift_norm}**")
        for grp in groups:
            icon = "S" if grp["total_ok"] else "N"
            color = "#155724" if grp["total_ok"] else "#721c24"
            st.markdown(
                f'<div style="margin-left:10px;color:{color};font-size:0.9rem;">'
                f'{icon} Totale &nbsp; {grp["total_present"]} / {grp["total_required"]}'
                f'</div>',
                unsafe_allow_html=True,
            )

            gruppo = str(grp.get("gruppo", "")).strip().upper()
            cov_code = str(grp.get("coverage_code", "")).strip().upper()
            key_base = (
                f"{rep}_{ds}_{shift_norm}_{cov_code}_{gruppo}"
                .replace("-", "_")
                .replace(" ", "_")
            )
            gmask = (
                (overrides_df["data"] == ds)
                & (overrides_df["reparto_id"] == rep)
                & (overrides_df["shift_code"] == shift_norm)
                & (overrides_df["coverage_code"] == cov_code)
                & (overrides_df["gruppo"] == gruppo)
                & (overrides_df["total_required"].notna())
            )
            if not gmask.any():
                gmask = (
                    (overrides_df["data"] == ds)
                    & (overrides_df["reparto_id"] == rep)
                    & (overrides_df["shift_code"] == shift_norm)
                    & (overrides_df["coverage_code"] == "")
                    & (overrides_df["gruppo"] == gruppo)
                    & (overrides_df["total_required"].notna())
                )
            gcur = int(grp["total_required"])
            if gmask.any():
                gcur = int(overrides_df.loc[gmask, "total_required"].iloc[-1])

            gcol1, gcol2, gcol3 = st.columns([2, 1, 1])
            with gcol1:
                gnew = st.number_input(
                    f"Totale gruppo {gruppo or '(default)'}",
                    min_value=0,
                    step=1,
                    value=int(gcur),
                    key=f"ovr_g_total_{key_base}",
                )
            with gcol2:
                if _button("Salva totale", key=f"ovr_g_save_{key_base}", width="stretch"):
                    out = _upsert_group_override(
                        overrides_df,
                        data_s=ds,
                        reparto_id=rep,
                        shift_code=shift_norm,
                        coverage_code=cov_code,
                        gruppo=gruppo,
                        total_required=int(gnew),
                    )
                    _set_demand_overrides_target(target_name, out)
                    st.rerun()
            with gcol3:
                if _button("Rimuovi", key=f"ovr_g_rm_{key_base}", width="stretch"):
                    out = _clear_group_override(
                        overrides_df,
                        data_s=ds,
                        reparto_id=rep,
                        shift_code=shift_norm,
                        coverage_code=cov_code,
                        gruppo=gruppo,
                    )
                    _set_demand_overrides_target(target_name, out)
                    st.rerun()

            for rd in grp["roles"]:
                role = str(rd["role"]).strip().upper()
                ri = "S" if rd["ok"] else "N"
                rc = "#155724" if rd["ok"] else "#721c24"
                st.markdown(
                    f'<div style="margin-left:24px;color:{rc};font-size:0.85rem;">'
                    f'{ri} {role} &nbsp; {rd["present"]} / {rd["min_required"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                rmask = (
                    (overrides_df["data"] == ds)
                    & (overrides_df["reparto_id"] == rep)
                    & (overrides_df["shift_code"] == shift_norm)
                    & (overrides_df["coverage_code"] == cov_code)
                    & (overrides_df["gruppo"] == gruppo)
                    & (overrides_df["role"] == role)
                    & (overrides_df["min_required"].notna())
                )
                if not rmask.any():
                    rmask = (
                        (overrides_df["data"] == ds)
                        & (overrides_df["reparto_id"] == rep)
                        & (overrides_df["shift_code"] == shift_norm)
                        & (overrides_df["coverage_code"] == "")
                        & (overrides_df["gruppo"] == gruppo)
                        & (overrides_df["role"] == role)
                        & (overrides_df["min_required"].notna())
                    )
                rcur = int(rd["min_required"])
                if rmask.any():
                    rcur = int(overrides_df.loc[rmask, "min_required"].iloc[-1])
                role_base = (
                    f"{key_base}_{role}"
                    .replace("-", "_")
                    .replace(" ", "_")
                )
                rcol1, rcol2, rcol3 = st.columns([2, 1, 1])
                with rcol1:
                    rnew = st.number_input(
                        f"Minimo ruolo {role}",
                        min_value=0,
                        step=1,
                        value=int(rcur),
                        key=f"ovr_r_min_{role_base}",
                    )
                with rcol2:
                    if _button("Salva minimo", key=f"ovr_r_save_{role_base}", width="stretch"):
                        out = _upsert_role_override(
                            overrides_df,
                            data_s=ds,
                            reparto_id=rep,
                            shift_code=shift_norm,
                            coverage_code=cov_code,
                            gruppo=gruppo,
                            role=role,
                            min_required=int(rnew),
                        )
                        _set_demand_overrides_target(target_name, out)
                        st.rerun()
                with rcol3:
                    if _button("Rimuovi", key=f"ovr_r_rm_{role_base}", width="stretch"):
                        out = _clear_role_override(
                            overrides_df,
                            data_s=ds,
                            reparto_id=rep,
                            shift_code=shift_norm,
                            coverage_code=cov_code,
                            gruppo=gruppo,
                            role=role,
                        )
                        _set_demand_overrides_target(target_name, out)
                        st.rerun()


# ── Toolbar + Grid (fragment: cell clicks only rerun this section) ────────

_TB_CSS = """<style>
body{margin:0;font-family:'Inter',system-ui,sans-serif;}
.tb{background:#fff;padding:6px 14px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;min-height:48px;border-bottom:1px solid #c5e0e3;}
.btn{display:inline-flex;align-items:center;padding:7px 13px;border:1px solid #c5e0e3;background:white;border-radius:8px;cursor:pointer;font-size:0.85rem;color:#093d41;font-weight:500;text-decoration:none;}
.btn:hover{background:#e0f4f5;border-color:#15757b;}
.btn.off{opacity:0.4;pointer-events:none;cursor:not-allowed;}
.btn.btn-active{background:#d0eef0;border-color:#0a9ba6;color:#093d41;}
.sep{width:1px;height:26px;background:#c5e0e3;margin:0 4px;}
.info{margin-left:auto;font-size:0.78rem;color:#3a6a6e;}
</style>"""

def _render_kpi_tab(draft: dict, data: dict) -> None:
    """Renderizza la tab Analisi con le metriche KPI del solver."""
    # ── Infeasibility: mostra diagnosi e interrompi ───────────────────────
    # Precede il check su kpi: anche se kpi fosse vuoto (draft vecchio,
    # errore di costruzione) le cause devono comunque essere visibili.
    infeas = draft.get("infeasibility_summary")
    if infeas:
        st.error(
            "Il solver non ha trovato nessuna soluzione ammissibile. "
            "Di seguito le cause più probabili individuate dall'analisi euristica."
        )
        _SEV_ICON = {"error": "🔴", "warning": "🟡", "info": "ℹ️"}
        causes = infeas.get("top_causes", [])
        for i, cause in enumerate(causes):
            icon  = _SEV_ICON.get(str(cause.get("severity", "info")), "ℹ️")
            title = str(cause.get("title", f"Causa {i + 1}")).strip()
            with st.expander(f"{icon} {title}", expanded=(i == 0)):
                evidence = str(cause.get("evidence", "")).strip()
                hint     = str(cause.get("hint", "")).strip()
                if evidence:
                    st.markdown(f"**Evidenza:** {evidence}")
                if hint:
                    st.markdown(f"**Suggerimento:** {hint}")
        return

    kpi = draft.get("kpi", {})
    if not kpi:
        st.info("Nessun dato KPI disponibile.")
        return

    emp_df = data.get("employees", pd.DataFrame())
    n_total = len(emp_df)
    base2_pa = draft.get("base_preassignments", pd.DataFrame())
    d_start = draft.get("calc_start")
    d_end = draft.get("calc_end")
    if d_start and d_end:
        draft_pa_full = _merge_draft_pa(
            draft.get("preassignments", pd.DataFrame()),
            base2_pa,
            d_start,
            d_end,
        )
    else:
        draft_pa_full = draft.get("preassignments", pd.DataFrame()).copy()
    diff_df = _compute_schedule_diff(base2_pa, draft_pa_full)

    base_cov_data = dict(data)
    base_cov_data["preassignments"] = _normalize_preassignments(base2_pa)
    base_cov_data["locks"] = draft.get("base_locks", data.get("locks", pd.DataFrame()))
    base_cov_data["demand_overrides"] = draft.get(
        "demand_overrides", data.get("demand_overrides", pd.DataFrame())
    )
    _, base_rows = build_schedule(base_cov_data)
    base_cov = compute_coverage_preview(base_cov_data, base_rows, assignments_df=data.get("assignments_df"))

    draft_cov_data = dict(base_cov_data)
    draft_cov_data["preassignments"] = draft_pa_full
    draft_cov = compute_coverage_preview(
        draft_cov_data,
        base_rows,
        assignments_df=draft.get("assignments_df"),
    )
    base_cov_sum = _coverage_shortage_summary(base_cov)
    draft_cov_sum = _coverage_shortage_summary(draft_cov)

    # ── Riga 1: copertura + ottimo ────────────────────────────────────────
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric(
            "Scoperture ruolo",
            kpi.get("coverage_under_role", 0),
            help="Persone-slot mancanti rispetto al fabbisogno per ruolo specifico",
        )
    with col2:
        st.metric(
            "Scoperture gruppo",
            kpi.get("coverage_under_group", 0),
            help="Persone-slot mancanti rispetto al fabbisogno per gruppo di ruoli",
        )
    with col3:
        gap = kpi.get("gap_pct")
        st.metric(
            "Gap dall'ottimo",
            f"{gap:.1f}%" if gap is not None else "—",
            help="(obiettivo − lower bound) / obiettivo × 100",
        )
    with col4:
        n_plan = kpi.get("n_employees_planned", 0)
        st.metric(
            "Dipendenti pianificati",
            f"{n_plan} / {n_total}",
            help="Dipendenti con almeno un turno assegnato nella finestra",
        )

    st.divider()

    d1, d2, d3 = st.columns(3)
    with d1:
        st.metric("Turni cambiati", len(diff_df))
    with d2:
        delta_cells = draft_cov_sum["uncovered_cells"] - base_cov_sum["uncovered_cells"]
        st.metric("Delta celle scoperte", delta_cells)
    with d3:
        delta_short = draft_cov_sum["total_shortage"] - base_cov_sum["total_shortage"]
        st.metric("Delta scopertura totale", delta_short)
    if not diff_df.empty:
        st.caption("Prime modifiche bozza vs baseline")
        _dataframe(diff_df.head(200), width="stretch", hide_index=True)
    else:
        st.caption("Nessuna differenza tra bozza e baseline.")

    st.divider()

    # ── Riga 2: violazioni ────────────────────────────────────────────────
    col5, col6, col7, col8 = st.columns(4)
    with col5:
        st.metric(
            "Riposo 11h violato",
            kpi.get("violations_rest11", 0),
            help="Coppie di turni consecutivi con meno di 11h di riposo (soft)",
        )
    with col6:
        st.metric(
            "Riposo sett. violato",
            kpi.get("violations_rest_weekly", 0),
            help="Periodi di 7 giorni senza almeno un giorno di riposo (soft)",
        )
    with col7:
        st.metric(
            "Preassegn. violate",
            kpi.get("violations_preass", 0),
            help="Preassegnazioni non rispettate dal solver (soft)",
        )
    with col8:
        st.metric(
            "Turni cross-dept",
            kpi.get("n_cross_dept", 0),
            help="Turni assegnati a dipendenti fuori dal loro reparto principale (soft)",
        )

    # ── Saldo ore finale per dipendente ───────────────────────────────────
    final_balance = kpi.get("final_balance_by_emp", {})
    if final_balance:
        st.divider()
        st.markdown("**Saldo ore progressive per dipendente** *(post-ottimizzazione)*")
        rows_disp = []
        sum_abs_pre = 0.0
        sum_abs_post = 0.0
        for eid, bal_h in sorted(final_balance.items(), key=lambda x: str(x[0])):
            name = eid
            init_h = 0.0
            if not emp_df.empty:
                mask = emp_df["employee_id"].astype(str) == str(eid)
                if mask.any():
                    for _name_col in ("nome", "name"):
                        if _name_col in emp_df.columns:
                            _val = emp_df.loc[mask, _name_col]
                            if not _val.empty and str(_val.iloc[0]).strip():
                                name = str(_val.iloc[0])
                                break
                    # Cerca saldo iniziale: prima in ore, poi in minuti
                    _init_col = next(
                        (c for c in ("saldo_prog_iniziale_h", "saldo_iniziale_h",
                                     "start_balance_h", "start_balance")
                         if c in emp_df.columns),
                        None,
                    )
                    _init_min_col = next(
                        (c for c in ("saldo_init_min", "start_balance_min")
                         if c in emp_df.columns),
                        None,
                    ) if _init_col is None else None
                    if _init_col:
                        init_series = emp_df.loc[mask, _init_col]
                        if not init_series.empty:
                            try:
                                init_h = float(init_series.iloc[0])
                            except (ValueError, TypeError):
                                init_h = 0.0
                    elif _init_min_col:
                        init_series = emp_df.loc[mask, _init_min_col]
                        if not init_series.empty:
                            try:
                                init_h = float(init_series.iloc[0]) / 60.0
                            except (ValueError, TypeError):
                                init_h = 0.0
            sum_abs_pre += abs(init_h)
            sum_abs_post += abs(bal_h)
            rows_disp.append({
                "Dipendente": name,
                "Saldo iniziale (h)": f"{init_h:+.1f}",
                "Saldo finale (h)": f"{bal_h:+.1f}",
                "Δ (h)": f"{bal_h - init_h:+.1f}",
            })

        # Totale Σ|saldo| pre e post
        _tc1, _tc2 = st.columns(2)
        with _tc1:
            st.metric(
                "Σ |saldo| iniziale",
                f"{sum_abs_pre:.1f} h",
                help="Somma dei valori assoluti del saldo progressivo iniziale di ogni dipendente",
            )
        with _tc2:
            delta_abs = sum_abs_post - sum_abs_pre
            st.metric(
                "Σ |saldo| finale",
                f"{sum_abs_post:.1f} h",
                delta=f"{delta_abs:+.1f} h",
                delta_color="inverse",
                help="Somma dei valori assoluti del saldo finale. Delta negativo = miglioramento",
            )

        if rows_disp:
            _dataframe(pd.DataFrame(rows_disp), width="stretch", hide_index=True)


@st.fragment
def _grid_section():
    data = st.session_state["data"]
    emp_df = data["employees"]
    all_reparti = sorted(emp_df["reparto_id"].dropna().unique().tolist())

    # ── 1. Leggi tutti i click PRIMA di qualsiasi rendering ──────────────────
    pending_click = st.session_state.get("grid", "")
    tb_raw        = st.session_state.get("toolbar", "")
    cov_raw       = st.session_state.get("coverage_grid", "")

    det_counter      = st.session_state.get("_det_counter", 0)
    clear_counter    = st.session_state.get("_clear_counter", 0)
    filtri_counter   = st.session_state.get("_filtri_counter", 0)
    show_cov_counter = st.session_state.get("_show_cov_counter", 0)
    cov_click_counter = st.session_state.get("_cov_click_counter", 0)
    # Request di apertura dialog copertura via pulsante (consumato una volta sola)
    cov_dlg_req: tuple | None = st.session_state.pop("_cov_dlg_req", None)

    det_id      = f"det-{det_counter}"
    clear_id    = f"clear-{clear_counter}"
    filtri_id   = f"filtri-{filtri_counter}"
    show_cov_id = f"showcov-{show_cov_counter}"

    # ── 2. Processa grid click → aggiorna selezione ──────────────────────────
    if pending_click:
        new_sel = _parse_click_id(pending_click)
        if new_sel:
            st.session_state["grid_selection"] = new_sel
    sel_now = st.session_state.get("grid_selection")

    # ── 3. Processa toolbar + coverage click (PRIMA del rendering, senza st.rerun) ──────
    open_dialog: tuple | None = None
    open_cov_dialog: tuple | None = None

    if tb_raw == det_id and sel_now:
        st.session_state["_det_counter"] = det_counter + 1
        open_dialog = ("det", sel_now)
    elif tb_raw == clear_id:
        st.session_state["_clear_counter"] = clear_counter + 1
        if not st.session_state.get("view_draft"):
            pa = st.session_state["data"]["preassignments"]
            st.session_state["data"]["preassignments"] = pa.iloc[0:0].copy()
            st.rerun()
    elif tb_raw == filtri_id:
        st.session_state["_filtri_counter"] = filtri_counter + 1
        st.session_state["show_filters"] = not st.session_state.get("show_filters", False)
    elif tb_raw == show_cov_id:
        st.session_state["_show_cov_counter"] = show_cov_counter + 1
        st.session_state["show_coverage"] = not st.session_state.get("show_coverage", False)

    cov_parsed = _parse_cov_click_id(cov_raw, cov_click_counter)
    if cov_parsed:
        st.session_state["_cov_click_counter"] = cov_click_counter + 1
        rep = cov_parsed["reparto"]
        ds  = cov_parsed["date"]
        if st.session_state.get("cov_selection") == (rep, ds):
            # secondo click sulla stessa cella → deseleziona
            st.session_state["cov_selection"] = None
        else:
            # primo click → seleziona (evidenzia)
            st.session_state["cov_selection"] = (rep, ds)
            # Apertura diretta dialog copertura su click cella.
            cov_dlg_req = (rep, ds)

    # ── 4. Leggi stato aggiornato (dopo aver processato i click) ─────────────
    show_filters  = st.session_state.get("show_filters", False)
    show_coverage = st.session_state.get("show_coverage", False)
    cov_selection = st.session_state.get("cov_selection")

    # ── 4b. Calcola dialog_kind PRIMA del rendering (evita bleed iframe/dialog) ──
    _early_sel = open_dialog[1] if open_dialog else None
    _dialog_kind: str | None = None
    if _early_sel is not None and _early_sel.get("sel_type") == "emp":
        _dialog_kind = "emp"
    elif _early_sel is not None and _early_sel.get("sel_type") == "day":
        _dialog_kind = "day"
    elif cov_dlg_req:
        # Apertura dialog copertura via pulsante "Dettaglio copertura"
        open_cov_dialog = cov_dlg_req
        _dialog_kind = "cov"

    # ── 5. Costruisci schedule (dopo eventuale clear) ────────────────────────
    # In vista bozza: per i giorni nella finestra di calcolo usiamo le PA del
    # solver; per i giorni fuori finestra integriamo con le PA correnti così
    # da non perdere i dati esistenti (ottimizzazione parziale).
    _view_draft = st.session_state.get("view_draft", False)
    _draft = st.session_state.get("draft")
    if _view_draft and _draft:
        _sched_data = dict(data)
        _win_start = _draft.get("calc_start")
        _win_end   = _draft.get("calc_end")
        # Per i giorni nella finestra usiamo le PA del solver;
        # per i giorni fuori finestra usiamo base2 (non base1).
        _base2_pa = _draft.get("base_preassignments", data["preassignments"])
        if _win_start and _win_end:
            _merged_pa = _merge_draft_pa(
                _draft["preassignments"],
                _base2_pa,
                _win_start,
                _win_end,
            )
        else:
            _merged_pa = _draft["preassignments"]
        _sched_data["preassignments"] = _merged_pa
        # Usa lock da base2
        _base2_locks = _draft.get("base_locks")
        if _base2_locks is not None:
            _sched_data["locks"] = _base2_locks
        dates, all_rows = build_schedule(_sched_data)
        _cov_input_data = dict(_sched_data)
        _cov_input_data["demand_overrides"] = _draft.get(
            "demand_overrides",
            data.get("demand_overrides", pd.DataFrame()),
        )
    else:
        dates, all_rows = build_schedule(data)
        _cov_input_data = data
    all_roles     = sorted(emp_df["role"].dropna().unique().tolist())
    view_reparto  = st.session_state.get("view_reparto", "Tutti")
    view_role     = st.session_state.get("view_role", "Tutti")
    view_employee = st.session_state.get("view_employee", "Tutti")
    filtered_rows = all_rows
    if view_reparto != "Tutti":
        filtered_rows = [r for r in filtered_rows if r["reparto"] == view_reparto]
    if view_role != "Tutti":
        filtered_rows = [r for r in filtered_rows if r["role"] == view_role]
    if view_employee != "Tutti":
        filtered_rows = [r for r in filtered_rows if r["name"] == view_employee]
    n_emp  = len(filtered_rows)
    n_days = len(dates)

    # ── 6-10. Piano / Analisi tabs ────────────────────────────────────────────
    # La tab Analisi compare quando la bozza ha metriche KPI oppure una diagnosi
    # di infeasibility: le due condizioni sono disgiunte per garantire che la
    # diagnostica sia sempre visibile anche se kpi fosse vuoto.
    _has_kpi = bool(
        _view_draft and _draft and (
            _draft.get("kpi") or _draft.get("infeasibility_summary")
        )
    )
    if _has_kpi:
        _tab_piano, _tab_analisi = st.tabs(["📅 Piano", "📊 Analisi"])
        _piano_ctx = _tab_piano
    else:
        _piano_ctx = st.container()

    with _piano_ctx:
        # ── 6. Toolbar ───────────────────────────────────────────────────────
        if sel_now and sel_now.get("sel_type") == "emp":
            det_label, det_cls = "Dettaglio dipendente", "btn"
        elif sel_now and sel_now.get("sel_type") == "day":
            det_label, det_cls = "Dettaglio stato", "btn"
        else:
            det_label, det_cls = "Dettaglio", "btn off"

        filtri_cls   = "btn btn-active" if show_filters  else "btn"
        show_cov_cls = "btn btn-active" if show_coverage else "btn"
        clear_cls    = "btn off" if _view_draft else "btn"

        toolbar_html = (
            _TB_CSS +
            f'<div class="tb">'
            f'<a id="{det_id}" href="#" class="{det_cls}">{det_label}</a>'
            '<span class="sep"></span>'
            f'<a id="{clear_id}" href="#" class="{clear_cls}">&#128465; Svuota preassegnazioni</a>'
            '<span class="sep"></span>'
            '<span class="btn off">&Sigma; Mostra accum.</span>'
            f'<a id="{show_cov_id}" href="#" class="{show_cov_cls}">&#128202; Mostra copertura</a>'
            '<span class="sep"></span>'
            '<span class="btn off">&#128260; Aggiorna</span>'
            '<span class="sep"></span>'
            '<span class="btn off">&#128424; Stampa</span>'
            '<span class="btn off">&#128203; Export</span>'
            '<span class="sep"></span>'
            f'<a id="{filtri_id}" href="#" class="{filtri_cls}">&#9776; Filtri</a>'
            f'<span class="info">{n_emp} dipendenti &middot; {n_days} giorni &middot; {month_label}</span>'
            '</div>'
        )
        click_detector(toolbar_html, key="toolbar")

        # ── 7. Filtri (se visibili) ───────────────────────────────────────────
        if show_filters:
            fcol1, fcol2, fcol3, _ = st.columns([1, 1, 1, 3])
            with fcol1:
                st.selectbox("Reparto", ["Tutti"] + all_reparti, key="view_reparto")
            with fcol2:
                st.selectbox("Ruolo", ["Tutti"] + all_roles, key="view_role")
            with fcol3:
                emp_names = sorted(set(
                    r["name"] for r in all_rows
                    if (view_reparto == "Tutti" or r["reparto"] == view_reparto)
                    and (view_role == "Tutti" or r["role"] == view_role)
                ))
                st.selectbox("Dipendente", ["Tutti"] + emp_names, key="view_employee")

        # ── 8. Griglia principale ─────────────────────────────────────────────
        # In draft mode, i giorni prima di calc_start sono "consolidati" e
        # vengono attenuati visivamente per distinguerli dalla finestra ottimizzata.
        _consolidated_before: date | None = None
        if _view_draft and _draft:
            _cs = _draft.get("calc_start")
            if _cs:
                try:
                    _consolidated_before = pd.Timestamp(_cs).date()
                except (TypeError, ValueError):
                    pass
        grid_html = render_grid(dates, filtered_rows, consolidated_before=_consolidated_before)
        click_detector(grid_html, key="grid")

        # ── 9. Tabella copertura ───────────────────────────────────────────────
        # Sempre click_detector: quando il dialog copertura è aperto via pulsante,
        # l'HTML non cambia (il pulsante non modifica contatore né selezione) →
        # click_detector non re-emette "" → nessun re-run spurio → dialog stabile.
        #
        # assignments_df: se disponibile, viene usato per calcolare la copertura con
        # il reparto effettivo di lavoro (gestisce cross-dept). In draft mode si
        # prende dal draft; in normal mode da data (persistito al momento del salvataggio).
        # In bozza: usa assignments_df preview (solver + override celle editate).
        # In piano corrente: usa assignments_df persistito (se presente).
        _cov_adf: pd.DataFrame | None = None
        if _view_draft and _draft:
            _base_adf = _draft.get("assignments_df")
            _edited = _draft.get("edited_cells", {})
            if _edited and _base_adf is not None:
                _cov_adf = _build_assignments_df_preview(
                    _base_adf, _edited, data.get("employees", pd.DataFrame())
                )
            else:
                _cov_adf = _base_adf
        else:
            _cov_adf = data.get("assignments_df")
        cov_data: dict = {}
        if show_coverage:
            st.markdown("**Copertura del fabbisogno**")
            cov_data = compute_coverage_preview(_cov_input_data, all_rows, assignments_df=_cov_adf)
            cov_html = render_coverage_grid(dates, all_reparti, cov_data, cov_click_counter, cov_selection)
            click_detector(cov_html, key="coverage_grid")
            # Pulsante contestuale: 1 clic seleziona la cella, pulsante apre il dialog
            if cov_selection and _dialog_kind != "cov":
                _cov_sel_rep, _cov_sel_ds = cov_selection
                if st.button(
                    f"Dettaglio copertura: {_cov_sel_rep} · {_cov_sel_ds}",
                    key="cov_detail_btn",
                    type="secondary",
                ):
                    st.session_state["_cov_dlg_req"] = cov_selection
                    st.rerun()

        # ── 10. Apri dialog (SEMPRE per ultimo, una funzione per tipo) ─────────
        # Funzioni diverse = componenti React indipendenti = no content bleed
        if _dialog_kind == "emp":
            _show_emp_dialog({"eid": _early_sel["sel_id"]}, data)
        elif _dialog_kind == "day":
            _show_day_dialog({"eid": _early_sel["sel_id"], "date": _early_sel.get("sel_date", "")}, data)
        elif _dialog_kind == "cov":
            _cov_rep, _cov_ds = open_cov_dialog
            _cov_d = (
                cov_data
                if cov_data
                else compute_coverage_preview(_cov_input_data, all_rows, assignments_df=_cov_adf)
            )
            _show_cov_dialog({"reparto": _cov_rep, "date": _cov_ds, "cov_data": _cov_d}, data)

    if _has_kpi:
        with _tab_analisi:
            _render_kpi_tab(_draft, data)

# ── Esecuzione solver (richiesta dal pulsante in sidebar) ────────────────────
_ottimizza_req = st.session_state.pop("_ottimizza_req", None)
if _ottimizza_req:
    _run_error: str | None = None
    _tmp_folder: Path | None = None
    try:
        # Copia profonda dei dati correnti per non toccare la sessione
        _run_data = copy.deepcopy(st.session_state["data"])

        # Applica le impostazioni della sidebar che non sono ancora nel cfg
        _run_data["cfg"].setdefault("horizon", {}).update({
            "start_date": _ottimizza_req["start"],
            "end_date":   _ottimizza_req["end"],
        })
        _run_data["cfg"].setdefault("cross", {})["allow_cross"] = _ottimizza_req["cross"]

        # ── Cerca meglio: usa base2 (preassign + lock con edits utente) ────
        if _ottimizza_req.get("use_warm_start"):
            _prev_draft = st.session_state.get("draft")
            if _prev_draft is not None:
                _b2_pa = _prev_draft.get("base_preassignments")
                if _b2_pa is not None:
                    _run_data["preassignments"] = _b2_pa.copy()
                _b2_locks = _prev_draft.get("base_locks")
                if _b2_locks is not None:
                    _run_data["locks"] = _b2_locks.copy()
                _b2_ovr = _prev_draft.get("demand_overrides")
                if _b2_ovr is not None:
                    _run_data["demand_overrides"] = _normalize_demand_overrides(_b2_ovr)

        # Applica override puntuali di fabbisogno (solo runtime, non tocca i CSV sorgente).
        # Deve avvenire dopo l'eventuale sostituzione base2 in "Cerca meglio".
        _mp2, _cg2, _cr2, _ovr_warn = _apply_demand_overrides_tables(
            _run_data.get("month_plan", pd.DataFrame()),
            _run_data.get("coverage_groups", pd.DataFrame()),
            _run_data.get("coverage_roles", pd.DataFrame()),
            _run_data.get("demand_overrides", pd.DataFrame()),
        )
        _run_data["month_plan"] = _mp2
        _run_data["coverage_groups"] = _cg2
        _run_data["coverage_roles"] = _cr2
        if _ovr_warn:
            st.warning("Override fabbisogno: " + " | ".join(_ovr_warn[:3]))

        with st.spinner("Preparazione cartella di lavoro…"):
            _tmp_folder = prepare_run_folder(_run_data)

        with st.spinner("Caricamento e validazione dati…"):
            _loaded = _load_all_data(_run_data["cfg"], _tmp_folder)

        _max_s = float(_ottimizza_req["time_s"])
        _preset_label = next(
            (k for k, v in TIME_PRESETS.items() if v == int(_max_s)), f"{int(_max_s)}s"
        )

        # ── Warm start: costruisci hint dalla bozza precedente ────────────
        _warm_df = None
        _warm_fallback = False
        if _ottimizza_req.get("use_warm_start"):
            _prev_draft = st.session_state.get("draft")
            if _prev_draft is not None:
                _prev_adf = _prev_draft.get("assignments_df", pd.DataFrame())
                if (
                    not _prev_adf.empty
                    and "employee_id" in _prev_adf.columns
                    and "slot_id" in _prev_adf.columns
                ):
                    _warm_df = _prev_adf[["employee_id", "slot_id"]].copy()
                    _warm_df["employee_id"] = _warm_df["employee_id"].astype(str)
                    _warm_df["slot_id"] = pd.to_numeric(
                        _warm_df["slot_id"], errors="coerce"
                    )
                    _warm_df = _warm_df.dropna(subset=["employee_id", "slot_id"])
                    _warm_df = _warm_df.drop_duplicates(subset=["employee_id", "slot_id"])
            if _warm_df is None or _warm_df.empty:
                _warm_df = None
                _warm_fallback = True

        _spinner_prefix = "Cerca meglio" if _warm_df is not None else "Ottimizzazione"
        with st.spinner(f"{_spinner_prefix} in corso… ({_preset_label})"):
            _result = _solve(
                _loaded,
                _run_data["cfg"],
                selected_departments=_ottimizza_req["reparti"] or None,
                stability_enabled=_ottimizza_req["stability"],
                max_time_s=_max_s,
                warm_start_df=_warm_df,
                warm_start_strict=False,
            )

        # Converti states_df → formato preassegnazioni (employee_id, data, state_code)
        if _result.states_df is not None and not _result.states_df.empty:
            _draft_pa = (
                _result.states_df
                .rename(columns={"date": "data", "state": "state_code"})
                [["employee_id", "data", "state_code"]]
                .copy()
            )
        else:
            _draft_pa = pd.DataFrame(columns=["employee_id", "data", "state_code"])

        # ── Base2: copia della base modificabile in vista bozza ─────────
        # Se "Cerca meglio", base2 viene dalla bozza precedente (già editata);
        # altrimenti parte dalla base1 corrente.
        if _ottimizza_req.get("use_warm_start"):
            _prev = st.session_state.get("draft")
            _base2_pa = (
                _prev["base_preassignments"].copy()
                if _prev and "base_preassignments" in _prev
                else _run_data["preassignments"].copy()
            )
            _base2_locks = (
                _prev["base_locks"].copy()
                if _prev and "base_locks" in _prev
                else _run_data.get("locks", pd.DataFrame()).copy()
            )
        else:
            _base2_pa = st.session_state["data"].get("preassignments", pd.DataFrame()).copy()
            _base2_locks = st.session_state["data"].get("locks", pd.DataFrame()).copy()

        _store_new_draft(
            draft_pa=_draft_pa,
            result=_result,
            ottimizza_req=_ottimizza_req,
            base2_pa=_base2_pa,
            base2_locks=_base2_locks,
            demand_overrides=_run_data.get("demand_overrides", pd.DataFrame()),
        )

        # ── Feedback warm start ───────────────────────────────────────────
        _used_ws = _warm_df is not None
        st.session_state["draft"]["used_warm_start"] = _used_ws
        _ws_note = ""
        if _warm_fallback:
            _ws_note = (
                "Warm start non disponibile: nessun hint valido dalla bozza. "
                "Eseguito run normale."
            )
        elif _used_ws and _result.warm_start_stats is not None:
            _ws = _result.warm_start_stats
            _ws_note = f"Warm start: applicati {_ws.hints_applied} hint"
            _ws_ignored = (
                _ws.unknown_slots + _ws.ineligible_pairs + _ws.unknown_employees
            )
            if _ws_ignored > 0:
                _ws_note += f" ({_ws_ignored} ignorati)"
        if _ws_note:
            st.session_state["draft"]["warm_start_note"] = _ws_note

    except (
        OSError,
        IOError,
        ValueError,
        TypeError,
        KeyError,
        RuntimeError,
        ArithmeticError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        yaml.YAMLError,
    ) as _exc:
        LOGGER.exception("Errore durante run solver demo")
        _run_error = str(_exc)
    finally:
        if _tmp_folder is not None and Path(_tmp_folder).exists():
            shutil.rmtree(_tmp_folder, ignore_errors=True)

    if _run_error:
        st.error(f"Errore durante l'ottimizzazione: {_run_error}")
    else:
        st.rerun()

# ── Banner bozza ──────────────────────────────────────────────────────────────
_draft = st.session_state.get("draft")
if _draft:
    _view_draft = st.session_state.get("view_draft", False)
    _feasible = _draft["status_name"] in ("OPTIMAL", "FEASIBLE")
    _can_refine = _feasible and _has_valid_calc_params(st.session_state.get("calc_params"))
    _status_icon = "✅" if _feasible else "⚠️"
    _obj_str = (
        f" · obiettivo {_draft['objective_value']:.1f}"
        if _draft["objective_value"] is not None else ""
    )

    _b1, _b2, _b3, _b4, _b5 = st.columns([3, 2, 1, 1, 1])
    with _b1:
        st.info(f"{_status_icon} **Bozza disponibile** — {_draft['status_name']}{_obj_str}")
        _ws_note = _draft.get("warm_start_note")
        if _ws_note:
            st.caption(_ws_note)
        if _draft.get("manual_edits", False):
            st.caption(
                "Bozza modificata manualmente: copertura e KPI possono essere "
                "approssimati. Per aggiornarli, usa Cerca meglio."
            )
    with _b2:
        _radio_val = st.radio(
            "Vista",
            ["Piano corrente", "Bozza"],
            index=1 if _view_draft else 0,
            horizontal=True,
            label_visibility="collapsed",
            key="draft_view_radio",
        )
        st.session_state["view_draft"] = (_radio_val == "Bozza")
    with _b3:
        if _button(
            "Salva bozza",
            type="primary",
            width="stretch",
            disabled=not _feasible,
            help=None if _feasible else "Non salvabile: il solver non ha trovato una soluzione.",
        ):
            _promote_draft_to_current(_draft)
            st.rerun()
    with _b4:
        if _button(
            "Cerca meglio",
            width="stretch",
            disabled=not _can_refine,
            help=(
                "Rilancia il solver usando la bozza come punto di partenza"
                if _can_refine
                else (
                    "Non disponibile: bozza non valida."
                    if not _feasible
                    else "Parametri di calcolo non disponibili. Configura dalla sidebar."
                )
            ),
        ):
            if _queue_warm_start_from_calc_params():
                st.rerun()
            else:
                st.error("Parametri di calcolo non disponibili. Configura dalla sidebar.")
    with _b5:
        if _button("Annulla", width="stretch"):
            _drop_draft_state()
            st.rerun()
    _ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    _e1, _e2 = st.columns(2)
    with _e1:
        _download_button(
            "Esporta piano corrente",
            data=_build_current_export_zip(st.session_state["data"]),
            file_name=f"export_current_{_ts}.zip",
            mime="application/zip",
            width="stretch",
        )
    with _e2:
        _download_button(
            "Esporta bozza",
            data=_build_draft_export_zip(_draft),
            file_name=f"export_draft_{_ts}.zip",
            mime="application/zip",
            width="stretch",
        )
_grid_section()

