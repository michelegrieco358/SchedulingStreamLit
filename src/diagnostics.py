from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


@dataclass(frozen=True)
class InfeasibilityCause:
    code: str
    title: str
    severity: str
    score: int
    evidence: str
    hint: str


def _to_date(value: Any) -> date | None:
    dt = pd.to_datetime(value, errors="coerce")
    if pd.isna(dt):
        return None
    return dt.date()


def _slot_day_map(context) -> dict[int, date]:
    out: dict[int, date] = {}
    slots = getattr(context, "slots", pd.DataFrame())
    if slots is None or slots.empty or "slot_id" not in slots.columns:
        return out

    day_col = "date" if "date" in slots.columns else None
    if day_col is None:
        for candidate in ("start_dt", "start_datetime"):
            if candidate in slots.columns:
                day_col = candidate
                break
    if day_col is None:
        return out

    for row in slots.loc[:, ["slot_id", day_col]].itertuples(index=False):
        slot_id = int(getattr(row, "slot_id"))
        day = _to_date(getattr(row, day_col))
        if day is not None:
            out[slot_id] = day
    return out


def _slot_duration_map(context) -> dict[int, int]:
    out: dict[int, int] = {}
    slots = getattr(context, "slots", pd.DataFrame())
    if slots is None or slots.empty or "slot_id" not in slots.columns:
        return out
    if "duration_min" not in slots.columns:
        return out
    for row in slots.loc[:, ["slot_id", "duration_min"]].itertuples(index=False):
        try:
            slot_id = int(getattr(row, "slot_id"))
            duration = int(float(getattr(row, "duration_min")))
        except Exception:
            continue
        out[slot_id] = max(duration, 0)
    return out


def _week_key(day: date) -> str:
    iso_year, iso_week, _ = day.isocalendar()
    return f"{iso_year}-W{iso_week:02d}"


def _month_key(day: date) -> str:
    return f"{day.year}-{day.month:02d}"


def _extract_cap_minutes(row: pd.Series, column: str) -> int | None:
    if column not in row.index:
        return None
    raw = row[column]
    if raw is None or (isinstance(raw, str) and raw.strip() == ""):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return int(round(value * 60.0))


def _find_must_lock_day_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    if locks_must is None or locks_must.empty:
        return []
    if not {"employee_id", "slot_id"}.issubset(locks_must.columns):
        return []

    slot_day = _slot_day_map(context)
    if not slot_day:
        return []

    keys: list[tuple[str, date]] = []
    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        employee_id = str(getattr(row, "employee_id")).strip()
        try:
            slot_id = int(getattr(row, "slot_id"))
        except Exception:
            continue
        day = slot_day.get(slot_id)
        if not employee_id or day is None:
            continue
        keys.append((employee_id, day))

    if not keys:
        return []

    counts = Counter(keys)
    conflicts = [(eid, day, count) for (eid, day), count in counts.items() if count > 1]
    if not conflicts:
        return []

    conflicts.sort(key=lambda item: (-item[2], item[0], item[1]))
    preview = ", ".join(
        f"{eid}@{day.isoformat()} ({count})" for eid, day, count in conflicts[:3]
    )
    return [
        InfeasibilityCause(
            code="must_lock_same_day_conflict",
            title="Lock MUST multipli nello stesso giorno",
            severity="high",
            score=100,
            evidence=f"{len(conflicts)} conflitti; esempi: {preview}",
            hint=(
                "Ogni dipendente puo' avere al massimo un turno al giorno: "
                "rimuovere o spostare parte dei lock MUST."
            ),
        )
    ]


def _employee_leave_days(context) -> set[tuple[str, date]]:
    leaves = getattr(context, "leaves", pd.DataFrame())
    if leaves is None or leaves.empty or "employee_id" not in leaves.columns:
        return set()

    date_col = None
    for candidate in ("date", "data_dt", "data", "day"):
        if candidate in leaves.columns:
            date_col = candidate
            break
    if date_col is None:
        return set()

    pairs: set[tuple[str, date]] = set()
    for row in leaves.loc[:, ["employee_id", date_col]].itertuples(index=False, name=None):
        eid = str(row[0]).strip()
        day = _to_date(row[1])
        if eid and day is not None:
            pairs.add((eid, day))
    return pairs


def _find_must_lock_leave_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    if locks_must is None or locks_must.empty:
        return []
    if not {"employee_id", "slot_id"}.issubset(locks_must.columns):
        return []

    slot_day = _slot_day_map(context)
    if not slot_day:
        return []
    leave_days = _employee_leave_days(context)
    if not leave_days:
        return []

    conflicts: list[tuple[str, date, int]] = []
    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        eid = str(getattr(row, "employee_id")).strip()
        try:
            sid = int(getattr(row, "slot_id"))
        except Exception:
            continue
        day = slot_day.get(sid)
        if not eid or day is None:
            continue
        if (eid, day) in leave_days:
            conflicts.append((eid, day, sid))

    if not conflicts:
        return []

    preview = ", ".join(f"{eid}@{day.isoformat()}(slot {sid})" for eid, day, sid in conflicts[:5])
    return [
        InfeasibilityCause(
            code="must_lock_leave_conflict",
            title="Lock MUST in giornata di assenza",
            severity="high",
            score=95,
            evidence=f"{len(conflicts)} conflitti; esempi: {preview}",
            hint="Rimuovere i lock MUST in conflitto con ferie/assenze o aggiornare le assenze.",
        )
    ]


def _find_must_forbid_pair_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    locks_forbid = getattr(context, "locks_forbid", pd.DataFrame())
    if locks_must is None or locks_must.empty or locks_forbid is None or locks_forbid.empty:
        return []
    required = {"employee_id", "slot_id"}
    if not required.issubset(locks_must.columns) or not required.issubset(locks_forbid.columns):
        return []

    must_pairs: set[tuple[str, int]] = set()
    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        eid = str(getattr(row, "employee_id")).strip()
        try:
            sid = int(getattr(row, "slot_id"))
        except Exception:
            continue
        if eid:
            must_pairs.add((eid, sid))

    forbid_pairs: set[tuple[str, int]] = set()
    for row in locks_forbid.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        eid = str(getattr(row, "employee_id")).strip()
        try:
            sid = int(getattr(row, "slot_id"))
        except Exception:
            continue
        if eid:
            forbid_pairs.add((eid, sid))

    conflicts = sorted(must_pairs.intersection(forbid_pairs))
    if not conflicts:
        return []

    preview = ", ".join(f"{eid}:{sid}" for eid, sid in conflicts[:5])
    return [
        InfeasibilityCause(
            code="must_forbid_same_pair_conflict",
            title="Conflitto lock MUST/FORBID sulla stessa coppia",
            severity="high",
            score=110,
            evidence=f"{len(conflicts)} coppie in conflitto; esempi: {preview}",
            hint="Rimuovere la doppia imposizione sulla stessa coppia dipendente-slot.",
        )
    ]


def _find_must_lock_hour_cap_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    employees = getattr(context, "employees", pd.DataFrame())
    if locks_must is None or locks_must.empty:
        return []
    if employees is None or employees.empty:
        return []
    if not {"employee_id", "slot_id"}.issubset(locks_must.columns):
        return []
    if "employee_id" not in employees.columns:
        return []

    slot_day = _slot_day_map(context)
    slot_duration = _slot_duration_map(context)
    if not slot_day or not slot_duration:
        return []

    week_minutes: dict[tuple[str, str], int] = defaultdict(int)
    month_minutes: dict[tuple[str, str], int] = defaultdict(int)

    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        employee_id = str(getattr(row, "employee_id")).strip()
        try:
            slot_id = int(getattr(row, "slot_id"))
        except Exception:
            continue
        day = slot_day.get(slot_id)
        duration = slot_duration.get(slot_id)
        if not employee_id or day is None or duration is None:
            continue
        week_minutes[(employee_id, _week_key(day))] += duration
        month_minutes[(employee_id, _month_key(day))] += duration

    week_conflicts: list[str] = []
    month_conflicts: list[str] = []
    for _, emp in employees.iterrows():
        employee_id = str(emp.get("employee_id", "")).strip()
        if not employee_id:
            continue

        week_cap = _extract_cap_minutes(emp, "max_week_hours_h")
        month_cap = _extract_cap_minutes(emp, "max_month_hours_h")

        if week_cap is not None:
            for (eid, week_id), minutes in week_minutes.items():
                if eid != employee_id:
                    continue
                if minutes > week_cap:
                    week_conflicts.append(
                        f"{eid}@{week_id}: {minutes/60:.1f}h > {week_cap/60:.1f}h"
                    )
        if month_cap is not None:
            for (eid, month_id), minutes in month_minutes.items():
                if eid != employee_id:
                    continue
                if minutes > month_cap:
                    month_conflicts.append(
                        f"{eid}@{month_id}: {minutes/60:.1f}h > {month_cap/60:.1f}h"
                    )

    causes: list[InfeasibilityCause] = []
    if week_conflicts:
        preview = ", ".join(week_conflicts[:3])
        causes.append(
            InfeasibilityCause(
                code="must_lock_week_cap_conflict",
                title="Lock MUST oltre cap ore settimanale",
                severity="high",
                score=90,
                evidence=f"{len(week_conflicts)} superamenti; esempi: {preview}",
                hint=(
                    "Ridurre lock MUST nelle settimane critiche o aumentare "
                    "max_week_hours_h per i dipendenti coinvolti."
                ),
            )
        )
    if month_conflicts:
        preview = ", ".join(month_conflicts[:3])
        causes.append(
            InfeasibilityCause(
                code="must_lock_month_cap_conflict",
                title="Lock MUST oltre cap ore mensile",
                severity="high",
                score=85,
                evidence=f"{len(month_conflicts)} superamenti; esempi: {preview}",
                hint=(
                    "Ridurre lock MUST nel mese o aumentare max_month_hours_h "
                    "per i dipendenti coinvolti."
                ),
            )
        )
    return causes


def _find_must_lock_night_eligibility_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    employees = getattr(context, "employees", pd.DataFrame())
    slots = getattr(context, "slots", pd.DataFrame())
    if locks_must is None or locks_must.empty:
        return []
    if employees is None or employees.empty or slots is None or slots.empty:
        return []
    if not {"employee_id", "slot_id"}.issubset(locks_must.columns):
        return []
    if "employee_id" not in employees.columns or "slot_id" not in slots.columns:
        return []

    cfg = getattr(context, "cfg", {})
    night_codes = _resolve_night_codes_from_cfg(cfg if isinstance(cfg, Mapping) else None)

    can_work_night: dict[str, bool] = {}
    if "can_work_night" in employees.columns:
        for row in employees.loc[:, ["employee_id", "can_work_night"]].itertuples(index=False):
            eid = str(getattr(row, "employee_id")).strip()
            raw = getattr(row, "can_work_night")
            can = True
            if isinstance(raw, bool):
                can = raw
            elif raw is None:
                can = True
            else:
                text = str(raw).strip().lower()
                if text in {"false", "0", "no", "n"}:
                    can = False
            if eid:
                can_work_night[eid] = can

    slot_night: dict[int, bool] = {}
    if "is_night" in slots.columns:
        for row in slots.loc[:, ["slot_id", "is_night"]].itertuples(index=False):
            try:
                sid = int(getattr(row, "slot_id"))
            except Exception:
                continue
            slot_night[sid] = bool(getattr(row, "is_night"))
    if "shift_code" in slots.columns:
        for row in slots.loc[:, ["slot_id", "shift_code"]].itertuples(index=False):
            try:
                sid = int(getattr(row, "slot_id"))
            except Exception:
                continue
            slot_night.setdefault(sid, str(getattr(row, "shift_code")).strip().upper() in night_codes)

    conflicts: list[tuple[str, int]] = []
    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        eid = str(getattr(row, "employee_id")).strip()
        try:
            sid = int(getattr(row, "slot_id"))
        except Exception:
            continue
        if not eid:
            continue
        if not slot_night.get(sid, False):
            continue
        if can_work_night.get(eid, True) is False:
            conflicts.append((eid, sid))

    if not conflicts:
        return []

    preview = ", ".join(f"{eid}:{sid}" for eid, sid in conflicts[:5])
    return [
        InfeasibilityCause(
            code="must_lock_night_eligibility_conflict",
            title="Lock MUST notturni su personale non idoneo",
            severity="high",
            score=92,
            evidence=f"{len(conflicts)} conflitti; esempi: {preview}",
            hint="Rimuovere lock MUST notturni su personale con can_work_night=false.",
        )
    ]


def _resolve_night_codes_from_cfg(cfg: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(cfg, Mapping):
        return {"N"}
    shift_types = cfg.get("shift_types")
    if isinstance(shift_types, Mapping):
        raw = shift_types.get("night_codes")
        values = [raw] if isinstance(raw, str) else (list(raw) if isinstance(raw, list | tuple | set) else [])
        normalized = {str(item).strip().upper() for item in values if str(item).strip()}
        if normalized:
            return normalized
    return {"N"}


def _extract_night_limit(
    row: pd.Series,
    *,
    candidates: tuple[str, ...],
    cfg: Mapping[str, Any] | None,
    cfg_keys: tuple[str, ...],
) -> int | None:
    for col in candidates:
        if col not in row.index:
            continue
        raw = row[col]
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            continue
        try:
            parsed = int(round(float(raw)))
        except (TypeError, ValueError):
            continue
        return max(parsed, 0)

    if isinstance(cfg, Mapping):
        defaults = cfg.get("defaults")
        if isinstance(defaults, Mapping):
            night_defaults = defaults.get("night")
            if isinstance(night_defaults, Mapping):
                for key in cfg_keys:
                    raw = night_defaults.get(key)
                    if raw is None:
                        continue
                    try:
                        parsed = int(round(float(raw)))
                    except (TypeError, ValueError):
                        continue
                    return max(parsed, 0)
        night_cfg = cfg.get("night")
        if isinstance(night_cfg, Mapping):
            for key in cfg_keys:
                raw = night_cfg.get(key)
                if raw is None:
                    continue
                try:
                    parsed = int(round(float(raw)))
                except (TypeError, ValueError):
                    continue
                return max(parsed, 0)
    return None


def _collect_history_night_counts(
    context,
    *,
    night_codes: set[str],
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], int]]:
    history = getattr(context, "history", pd.DataFrame())
    if history is None or history.empty:
        return {}, {}
    if "employee_id" not in history.columns:
        return {}, {}

    shift_col = None
    for candidate in ("turno", "shift_code", "state_code"):
        if candidate in history.columns:
            shift_col = candidate
            break
    if shift_col is None:
        return {}, {}

    date_col = None
    for candidate in ("data_dt", "date_dt", "data", "date"):
        if candidate in history.columns:
            date_col = candidate
            break
    if date_col is None:
        return {}, {}

    work = history.loc[:, ["employee_id", shift_col, date_col]].copy()
    work["employee_id"] = work["employee_id"].astype(str).str.strip()
    work["_shift"] = work[shift_col].astype(str).str.strip().str.upper()
    work["_day"] = pd.to_datetime(work[date_col], errors="coerce").dt.date
    work = work[work["employee_id"].ne("") & work["_day"].notna()]
    if work.empty:
        return {}, {}

    work = work[work["_shift"].isin(night_codes)]
    if work.empty:
        return {}, {}

    week_counts: dict[tuple[str, str], int] = defaultdict(int)
    month_counts: dict[tuple[str, str], int] = defaultdict(int)
    for employee_id, day in work.loc[:, ["employee_id", "_day"]].itertuples(index=False, name=None):
        eid = str(employee_id).strip()
        week_counts[(eid, _week_key(day))] += 1
        month_counts[(eid, _month_key(day))] += 1
    return dict(week_counts), dict(month_counts)


def _find_must_lock_night_limit_conflicts(context) -> list[InfeasibilityCause]:
    locks_must = getattr(context, "locks_must", pd.DataFrame())
    employees = getattr(context, "employees", pd.DataFrame())
    slots = getattr(context, "slots", pd.DataFrame())
    if locks_must is None or locks_must.empty:
        return []
    if employees is None or employees.empty or slots is None or slots.empty:
        return []
    if not {"employee_id", "slot_id"}.issubset(locks_must.columns):
        return []
    if "employee_id" not in employees.columns or "slot_id" not in slots.columns:
        return []

    cfg = getattr(context, "cfg", {})
    night_codes = _resolve_night_codes_from_cfg(cfg if isinstance(cfg, Mapping) else None)

    slot_night: dict[int, bool] = {}
    shift_map: dict[int, str] = {}
    if "shift_code" in slots.columns:
        for row in slots.loc[:, ["slot_id", "shift_code"]].itertuples(index=False):
            try:
                sid = int(getattr(row, "slot_id"))
            except Exception:
                continue
            shift_map[sid] = str(getattr(row, "shift_code")).strip().upper()
    if "is_night" in slots.columns:
        for row in slots.loc[:, ["slot_id", "is_night"]].itertuples(index=False):
            try:
                sid = int(getattr(row, "slot_id"))
            except Exception:
                continue
            slot_night[sid] = bool(getattr(row, "is_night"))
    for sid, shift_code in shift_map.items():
        slot_night.setdefault(sid, shift_code in night_codes)

    slot_day = _slot_day_map(context)
    if not slot_day:
        return []

    must_night_days_by_emp: dict[str, list[date]] = defaultdict(list)
    for row in locks_must.loc[:, ["employee_id", "slot_id"]].itertuples(index=False):
        eid = str(getattr(row, "employee_id")).strip()
        try:
            sid = int(getattr(row, "slot_id"))
        except Exception:
            continue
        if not eid:
            continue
        if not slot_night.get(sid, False):
            continue
        day = slot_day.get(sid)
        if day is not None:
            must_night_days_by_emp[eid].append(day)

    if not must_night_days_by_emp:
        return []

    hist_week, hist_month = _collect_history_night_counts(context, night_codes=night_codes)

    week_conflicts: list[str] = []
    month_conflicts: list[str] = []
    consecutive_conflicts: list[str] = []

    for _, emp in employees.iterrows():
        eid = str(emp.get("employee_id", "")).strip()
        if not eid:
            continue
        days = sorted(must_night_days_by_emp.get(eid, []))
        if not days:
            continue

        week_limit = _extract_night_limit(
            emp,
            candidates=("max_nights_week", "max_week_nights"),
            cfg=cfg if isinstance(cfg, Mapping) else None,
            cfg_keys=("max_per_week", "max_week_nights", "max_nights_week"),
        )
        month_limit = _extract_night_limit(
            emp,
            candidates=("max_nights_month", "max_month_nights"),
            cfg=cfg if isinstance(cfg, Mapping) else None,
            cfg_keys=("max_per_month", "max_month_nights", "max_nights_month"),
        )
        consecutive_limit = _extract_night_limit(
            emp,
            candidates=("max_consecutive_nights", "max_nights_consecutive"),
            cfg=cfg if isinstance(cfg, Mapping) else None,
            cfg_keys=("max_consecutive_nights", "max_nights_consecutive"),
        )

        if week_limit is not None:
            counts = Counter(_week_key(day) for day in days)
            for week_id, must_count in counts.items():
                total = must_count + hist_week.get((eid, week_id), 0)
                if total > week_limit:
                    week_conflicts.append(f"{eid}@{week_id}: {total}>{week_limit}")

        if month_limit is not None:
            counts = Counter(_month_key(day) for day in days)
            for month_id, must_count in counts.items():
                total = must_count + hist_month.get((eid, month_id), 0)
                if total > month_limit:
                    month_conflicts.append(f"{eid}@{month_id}: {total}>{month_limit}")

        if consecutive_limit is not None and consecutive_limit >= 0:
            streak = 1
            max_streak = 1
            for idx in range(1, len(days)):
                if (days[idx] - days[idx - 1]).days == 1:
                    streak += 1
                else:
                    streak = 1
                max_streak = max(max_streak, streak)
            if max_streak > consecutive_limit:
                consecutive_conflicts.append(f"{eid}: streak={max_streak}>{consecutive_limit}")

    causes: list[InfeasibilityCause] = []
    if week_conflicts:
        causes.append(
            InfeasibilityCause(
                code="must_lock_night_week_cap_conflict",
                title="Lock MUST notturni oltre limite settimanale",
                severity="high",
                score=88,
                evidence=f"{len(week_conflicts)} superamenti; esempi: {', '.join(week_conflicts[:3])}",
                hint="Ridurre lock notturni o alzare max_nights_week nelle settimane coinvolte.",
            )
        )
    if month_conflicts:
        causes.append(
            InfeasibilityCause(
                code="must_lock_night_month_cap_conflict",
                title="Lock MUST notturni oltre limite mensile",
                severity="high",
                score=84,
                evidence=f"{len(month_conflicts)} superamenti; esempi: {', '.join(month_conflicts[:3])}",
                hint="Ridurre lock notturni o alzare max_nights_month nel mese coinvolto.",
            )
        )
    if consecutive_conflicts:
        causes.append(
            InfeasibilityCause(
                code="must_lock_night_consecutive_conflict",
                title="Lock MUST notturni oltre limite di consecutivita'",
                severity="high",
                score=86,
                evidence=(
                    f"{len(consecutive_conflicts)} superamenti; esempi: "
                    f"{', '.join(consecutive_conflicts[:3])}"
                ),
                hint="Spezzare le sequenze di notti consecutive o alzare max_consecutive_nights.",
            )
        )
    return causes


def build_infeasibility_summary(
    context,
    *,
    max_causes: int = 5,
) -> dict[str, Any]:
    causes: list[InfeasibilityCause] = []
    causes.extend(_find_must_forbid_pair_conflicts(context))
    causes.extend(_find_must_lock_day_conflicts(context))
    causes.extend(_find_must_lock_leave_conflicts(context))
    causes.extend(_find_must_lock_hour_cap_conflicts(context))
    causes.extend(_find_must_lock_night_eligibility_conflicts(context))
    causes.extend(_find_must_lock_night_limit_conflicts(context))

    if not causes:
        causes.append(
            InfeasibilityCause(
                code="no_static_conflict_detected",
                title="Nessun conflitto statico evidente",
                severity="info",
                score=0,
                evidence=(
                    "La diagnosi euristica non ha trovato conflitti diretti sui dati "
                    "di input; l'infeasibilita' potrebbe dipendere da interazioni "
                    "tra vincoli di pattern/riposo/notte."
                ),
                hint=(
                    "Provare a ridurre lock rigidi o ad allargare progressivamente "
                    "i vincoli hard piu' stringenti."
                ),
            )
        )

    causes = sorted(causes, key=lambda item: (-item.score, item.code))[: max(1, int(max_causes))]
    return {
        "status": "INFEASIBLE",
        "top_causes": [
            {
                "code": cause.code,
                "title": cause.title,
                "severity": cause.severity,
                "evidence": cause.evidence,
                "hint": cause.hint,
            }
            for cause in causes
        ],
    }


def write_infeasibility_summary_report(
    summary: Mapping[str, Any],
    path: str | Path,
) -> Path:
    target = Path(path)
    lines: list[str] = ["Diagnosi infeasibilita'"]
    status = str(summary.get("status", "INFEASIBLE")).strip() or "INFEASIBLE"
    lines.append(f"Status: {status}")
    lines.append("")
    lines.append("Top cause:")

    causes = summary.get("top_causes", [])
    if not isinstance(causes, list) or not causes:
        lines.append("- (nessuna causa disponibile)")
    else:
        for idx, cause in enumerate(causes, start=1):
            if not isinstance(cause, Mapping):
                continue
            title = str(cause.get("title", "")).strip()
            evidence = str(cause.get("evidence", "")).strip()
            hint = str(cause.get("hint", "")).strip()
            lines.append(f"{idx}. {title}")
            if evidence:
                lines.append(f"   Evidenza: {evidence}")
            if hint:
                lines.append(f"   Suggerimento: {hint}")

    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


__all__ = [
    "InfeasibilityCause",
    "build_infeasibility_summary",
    "write_infeasibility_summary_report",
]
