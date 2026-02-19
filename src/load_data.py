from __future__ import annotations

import contextlib
import os
import tempfile
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from loader import LoadedData, LoaderError as _CoreLoaderError, load_all as _core_load_all
from loader.config import load_config as _core_load_config

from .model import ModelContext, build_context_from_data
from .preprocessing import build_all as _build_bundle


class LoaderError(Exception):
    """High-level loader wrapper error."""


def load_config(path: str | Path) -> dict[str, Any]:
    """Load and validate the YAML config using the original loader."""
    config_path = Path(path)
    try:
        return _core_load_config(str(config_path))
    except _CoreLoaderError as exc:  # pragma: no cover - delegated
        raise LoaderError(str(exc)) from exc


_ALIAS_MAP = {
    "employees": "employees_df",
    "shift_slots": "shift_slots_df",
    "shift_role_eligibility": "eligibility_df",
    "role_dept_pools": "role_dept_pools_df",
    "locks": "locks_df",
    "availability": "availability_df",
    "slot_requirements": "slot_requirements_df",
    "month_plan": "month_plan_df",
    "history": "history_df",
    "leaves": "leaves_df",
    "leaves_days": "leaves_days_df",
    "gaps": "gap_pairs_df",
    "preassignments": "preassignments_df",
}


@contextlib.contextmanager
def _temporary_config(cfg: Mapping[str, Any]) -> Path:
    tmp_file = tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".yaml", delete=False)
    try:
        yaml.safe_dump(dict(cfg), tmp_file, allow_unicode=True, sort_keys=False)
        tmp_file.flush()
        tmp_path = Path(tmp_file.name)
    finally:
        tmp_file.close()
    try:
        yield tmp_path
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.remove(tmp_path)


def _call_core_loader(config_path: Path, data_dir: Path) -> LoadedData:
    try:
        return _core_load_all(str(config_path), str(data_dir))
    except _CoreLoaderError as exc:  # pragma: no cover - delegated
        raise LoaderError(str(exc)) from exc


def _to_dataframe_dict(loaded: LoadedData | Mapping[str, Any]) -> dict[str, Any]:
    if is_dataclass(loaded):
        data = {field.name: getattr(loaded, field.name) for field in fields(loaded)}
    elif isinstance(loaded, Mapping):
        data = dict(loaded)
    else:  # pragma: no cover - defensive guard
        raise LoaderError("Unexpected structure returned by load_all")

    for alias, target in _ALIAS_MAP.items():
        if alias not in data and target in data:
            data[alias] = data[target]

    if "absences" not in data:
        abs_alias = _build_absences_alias(data)
        if abs_alias is not None:
            data["absences"] = abs_alias

    return data


def _build_absences_alias(data: Mapping[str, Any]):
    for key in ("absences", "leaves_df", "leaves_days_df"):
        frame = data.get(key)
        if frame is None or getattr(frame, "empty", False):
            continue
        if {"employee_id", "date"}.issubset(frame.columns):
            alias = frame.loc[:, [col for col in frame.columns if col in {"employee_id", "date", "kind", "tipo", "tipo_set"}]].copy()
            alias = alias.rename(columns={"tipo": "kind", "tipo_set": "kind"})
            if "kind" not in alias.columns:
                alias["kind"] = "full_day"
            return alias.drop_duplicates().reset_index(drop=True)
    return None


def load_all_data(
    cfg: Mapping[str, Any] | str | Path,
    data_dir: str | Path,
    *,
    as_dict: bool = True,
) -> dict[str, Any] | LoadedData:
    """Load all scheduling dataframes using the core loader."""

    data_path = Path(data_dir)
    if isinstance(cfg, Mapping):
        with _temporary_config(cfg) as tmp_cfg:
            loaded = _call_core_loader(tmp_cfg, data_path)
    else:
        loaded = _call_core_loader(Path(cfg), data_path)

    if as_dict:
        return _to_dataframe_dict(loaded)
    return loaded


def _normalize_departments(values: Iterable[Any] | None) -> list[str]:
    if values is None:
        return []
    normalized: list[str] = []
    for value in values:
        dept = str(value).strip().upper()
        if dept and dept not in normalized:
            normalized.append(dept)
    return normalized


def _filter_loaded_data_for_departments(
    data: Mapping[str, Any],
    selected_departments: Iterable[Any],
) -> dict[str, Any]:
    selected = set(_normalize_departments(selected_departments))
    if not selected:
        return dict(data)

    filtered = dict(data)

    employees = filtered.get("employees")
    if employees is not None and "reparto_id" in employees.columns:
        filtered_employees = employees[
            employees["reparto_id"].astype(str).str.strip().str.upper().isin(selected)
        ].copy()
        filtered["employees"] = filtered_employees
        filtered["employees_df"] = filtered_employees
    employee_ids = set(
        filtered.get("employees", employees).get("employee_id", []).astype(str).str.strip()
    ) if filtered.get("employees", employees) is not None else set()

    for key in ("month_plan", "month_plan_df", "shift_slots", "shift_slots_df"):
        frame = filtered.get(key)
        if frame is None or "reparto_id" not in frame.columns:
            continue
        filtered[key] = frame[
            frame["reparto_id"].astype(str).str.strip().str.upper().isin(selected)
        ].copy()

    slots = filtered.get("shift_slots", filtered.get("shift_slots_df"))
    slot_ids: set[int] = set()
    if slots is not None and "slot_id" in slots.columns:
        slot_ids = set(slots["slot_id"].tolist())

    for key in ("slot_requirements", "slot_requirements_df"):
        frame = filtered.get(key)
        if frame is None:
            continue
        if "slot_id" in frame.columns:
            filtered[key] = frame[frame["slot_id"].isin(slot_ids)].copy()
        elif "reparto_id" in frame.columns:
            filtered[key] = frame[
                frame["reparto_id"].astype(str).str.strip().str.upper().isin(selected)
            ].copy()

    for key in (
        "coverage_roles",
        "coverage_roles_df",
        "groups_role_min_expanded",
        "coverage_totals",
        "coverage_totals_df",
        "groups_total_expanded",
        "role_dept_pools",
        "role_dept_pools_df",
    ):
        frame = filtered.get(key)
        if frame is None or "reparto_id" not in frame.columns:
            continue
        filtered[key] = frame[
            frame["reparto_id"].astype(str).str.strip().str.upper().isin(selected)
        ].copy()

    for key in ("dept_compat", "dept_compat_df"):
        frame = filtered.get(key)
        if frame is None:
            continue
        output = frame
        if "reparto_home" in output.columns:
            output = output[
                output["reparto_home"].astype(str).str.strip().str.upper().isin(selected)
            ]
        if "reparto_target" in output.columns:
            output = output[
                output["reparto_target"].astype(str).str.strip().str.upper().isin(selected)
            ]
        filtered[key] = output.copy()

    for key in (
        "availability",
        "availability_df",
        "leaves",
        "leaves_df",
        "leaves_days",
        "leaves_days_df",
        "history",
        "history_df",
        "preassignments",
        "preassignments_df",
        "absences",
    ):
        frame = filtered.get(key)
        if frame is None or "employee_id" not in frame.columns:
            continue
        filtered[key] = frame[
            frame["employee_id"].astype(str).str.strip().isin(employee_ids)
        ].copy()

    for key in ("locks", "locks_df", "locks_must", "locks_must_df", "locks_forbid", "locks_forbid_df"):
        frame = filtered.get(key)
        if frame is None:
            continue
        output = frame
        if "employee_id" in output.columns:
            output = output[
                output["employee_id"].astype(str).str.strip().isin(employee_ids)
            ]
        if "slot_id" in output.columns:
            output = output[output["slot_id"].isin(slot_ids)]
        filtered[key] = output.copy()

    for key in ("gaps", "gap_pairs", "gap_pairs_df"):
        frame = filtered.get(key)
        if frame is None:
            continue
        output = frame
        if "s1_id" in output.columns:
            output = output[output["s1_id"].isin(slot_ids)]
        if "s2_id" in output.columns:
            output = output[output["s2_id"].isin(slot_ids)]
        filtered[key] = output.copy()

    return filtered


def load_context(
    cfg: Mapping[str, Any] | str | Path,
    data_dir: str | Path,
    *,
    selected_departments: Iterable[Any] | None = None,
) -> tuple[ModelContext, dict[str, Any], Mapping[str, object]]:
    """
    Carica tutti i dati, esegue il preprocessing e costruisce un ModelContext pronto per il solver.
    Restituisce (context, dataset_dict, bundle_preprocessing).
    """
    data = load_all_data(cfg, data_dir, as_dict=True)
    cfg_dict = data.get("cfg")
    if cfg_dict is None:
        raise LoaderError("Il caricamento dati non ha restituito la configurazione 'cfg'.")

    explicit_selection = _normalize_departments(selected_departments)
    cfg_selection = _normalize_departments(
        cfg_dict.get("scheduling", {}).get("selected_departments")
        if isinstance(cfg_dict.get("scheduling"), Mapping)
        else None
    )
    active_selection = explicit_selection or cfg_selection

    if active_selection:
        allowed = _normalize_departments(
            cfg_dict.get("defaults", {}).get("departments")
            if isinstance(cfg_dict.get("defaults"), Mapping)
            else None
        )
        unknown = sorted(set(active_selection) - set(allowed))
        if unknown:
            raise LoaderError(
                "Reparti selezionati non presenti in defaults.departments: "
                + ", ".join(unknown)
            )

        data = _filter_loaded_data_for_departments(data, active_selection)
        cfg_dict = dict(cfg_dict)
        scheduling_cfg = cfg_dict.get("scheduling")
        if not isinstance(scheduling_cfg, Mapping):
            scheduling_cfg = {}
        scheduling_cfg = dict(scheduling_cfg)
        scheduling_cfg["selected_departments"] = active_selection
        cfg_dict["scheduling"] = scheduling_cfg
        data["cfg"] = cfg_dict

    bundle = _build_bundle(data, cfg_dict)
    context = build_context_from_data(data, bundle)
    return context, data, bundle
