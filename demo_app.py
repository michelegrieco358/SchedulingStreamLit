"""
SKYScheduler DEMO — Piano di Programmazione Mensile
Replica dell'interfaccia SKYppm HTML.
"""
from __future__ import annotations

import base64
from datetime import date, timedelta
from pathlib import Path
import sys

import pandas as pd
import yaml
import streamlit as st
from st_click_detector import click_detector

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


def _is_holiday(d: date) -> bool:
    return (d.day, d.month) in FIXED_HOLIDAYS


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
        # formato slot_id (employee_id, slot_id, lock): richiede risoluzione non
        # disponibile nella demo → ignorato, i lock si gestiscono via UI

    return {
        "cfg": cfg,
        "employees": employees,
        "shifts": shifts,
        "preassignments": preassignments,
        "locks": locks,
        "month_plan": month_plan,
        "coverage_groups": coverage_groups,
        "coverage_roles": coverage_roles,
        "folder": str(folder),
    }


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

def render_grid(dates: list[date], rows: list[dict]) -> str:
    """Build grid HTML. Highlight is handled client-side via JS so the HTML
    stays identical across clicks and the iframe is never re-created."""
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
</style>""",
        '<div class="sched-container"><table class="sky-grid"><thead><tr>',
        '<th class="nhdr">Nominativo</th>',
    ]

    for d in dates:
        css = _hdr_class(d)
        dl = DAY_LETTERS[d.weekday()]
        parts.append(f'<th class="{css}"><span class="dn">{d.day}</span><span class="dl">{dl}</span></th>')
    parts.append("</tr></thead><tbody>")

    for row in rows:
        eid = row["eid"]
        name = row["name"]
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
            parts.append(
                f'<td class="{css} dc-cell{extra_cls}">'
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


def _parse_click_id(click_id: str) -> dict | None:
    """Parse 'emp-42' or 'day-42-2024-07-15' into a selection dict."""
    if not click_id:
        return None
    if click_id.startswith("emp-"):
        return {"sel_type": "emp", "sel_id": click_id[4:], "sel_date": ""}
    if click_id.startswith("day-"):
        # day-{eid}-{YYYY-MM-DD}  →  split on first two dashes after 'day-'
        rest = click_id[4:]  # e.g. "42-2024-07-15"
        dash = rest.index("-")
        eid = rest[:dash]
        dt = rest[dash + 1:]
        return {"sel_type": "day", "sel_id": eid, "sel_date": dt}
    return None


# ── Detail panels ────────────────────────────────────────────────────────────

def _render_detail_item(label: str, value: str) -> str:
    return (
        f'<div class="dp-item">'
        f'<div class="dp-label">{label}</div>'
        f'<div class="dp-value">{value}</div>'
        f'</div>'
    )


def show_employee_detail(eid: str, emp_df: pd.DataFrame) -> None:
    matches = emp_df[emp_df["employee_id"].astype(str) == eid]
    if matches.empty:
        st.warning("Dipendente non trovato.")
        return
    emp = matches.iloc[0]
    items = "".join([
        _render_detail_item("Nome", str(emp.get("nome", eid))),
        _render_detail_item("Ruolo", str(emp.get("role", "--"))),
        _render_detail_item("Reparto", str(emp.get("reparto_id", "--"))),
    ])
    st.markdown(
        f'<div class="detail-panel"><div class="dp-grid">{items}</div></div>',
        unsafe_allow_html=True,
    )


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

    if st.button("Carica", type="primary", use_container_width=True):
        if dataset_folder and dataset_folder.exists():
            try:
                st.session_state["data"] = load_dataset(dataset_folder)
                st.session_state["loaded"] = True
                st.session_state.pop("grid_selection", None)
            except Exception as e:
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

        st.markdown("---")

        calc_time = st.radio("Tempo calcolo", list(TIME_PRESETS.keys()), index=1)

        st.markdown("---")

        st.button("ESEGUI OTTIMIZZAZIONE", type="primary", use_container_width=True)

        st.session_state["calc_params"] = {
            "reparti": calc_reparti,
            "start": calc_start,
            "end": calc_end,
            "cross": calc_cross,
            "time_s": TIME_PRESETS[calc_time],
            "stability": calc_stability,
        }


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

def compute_coverage_preview(data: dict, all_rows: list[dict]) -> dict:
    """Calcola per ogni (reparto, data) se il fabbisogno è soddisfatto.

    Ritorna dict {(reparto_id, date_str): {"status": "S"|"N", "details": [...]}}.
    Celle senza fabbisogno non compaiono nel dict.
    La presenza è costruita da all_rows (piano effettivo da build_schedule,
    che include gli override MUST_DO lock).
    """
    mp_df = data.get("month_plan", pd.DataFrame())
    cg_df = data.get("coverage_groups", pd.DataFrame())
    cr_df = data.get("coverage_roles", pd.DataFrame())

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
    # Costruita dal piano effettivo — include override MUST_DO rispetto ai preassignment raw
    presence: dict[tuple, dict] = {}
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
    show_shift_detail(eid, date_str, app_data)
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
    _locks_early = app_data.get("locks", pd.DataFrame())
    _forbidden_for_pa: set[str] = set()
    if not _locks_early.empty and "lock_type" in _locks_early.columns:
        _fm = (
            (_locks_early["employee_id"].astype(str) == eid)
            & (_locks_early["date"] == date_str)
            & (_locks_early["lock_type"] == "FORBIDDEN")
        )
        _forbidden_for_pa = set(_locks_early[_fm]["shift_code"].astype(str).tolist())
    # Preassignment options: demand shifts from CSV + non-demand state codes (SN, R…), minus forbidden
    _shift_csv_ids = list(shifts_df["shift_id"].astype(str).unique())
    _extra_sc = [s for s in _all_sc if s not in set(_shift_csv_ids)]
    shift_options = ["--"] + [
        s for s in _shift_csv_ids + _extra_sc if s not in _forbidden_for_pa
    ]
    pa_df = app_data["preassignments"]
    current = "--"
    _pa_code_col = next((c for c in ("state_code", "shift_code", "turno") if c in pa_df.columns), None)
    if not pa_df.empty and "employee_id" in pa_df.columns and "data" in pa_df.columns and _pa_code_col:
        mask = (pa_df["employee_id"].astype(str) == eid) & (pa_df["data"] == date_str)
        if mask.any():
            current = str(pa_df.loc[mask, _pa_code_col].iloc[0])
    # If current preassignment is now forbidden, reset to "--"
    if current in _forbidden_for_pa:
        current = "--"
    idx = shift_options.index(current) if current in shift_options else 0
    selected = st.selectbox("Modifica turno", shift_options, index=idx)
    if st.button("Salva", type="primary"):
        df = app_data["preassignments"].copy()
        if not df.empty and "employee_id" in df.columns and "data" in df.columns:
            mask = (df["employee_id"].astype(str) == eid) & (df["data"] == date_str)
            df = df[~mask].reset_index(drop=True)
        if selected != "--":
            new_row = pd.DataFrame([{"employee_id": eid, "data": date_str, "state_code": selected}])
            df = pd.concat([df, new_row], ignore_index=True)
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

    # Leggi lock attuali per questo dipendente+data
    locks_df = app_data.get("locks", pd.DataFrame())
    must_shift: str | None = None
    forbidden_shifts: list[str] = []
    must_reparto: str = ""
    if not locks_df.empty and "lock_type" in locks_df.columns:
        lmask = (locks_df["employee_id"].astype(str) == eid) & (locks_df["date"] == date_str)
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
    )

    must_options = ["-- nessuno --"] + all_lock_codes
    must_idx = must_options.index(must_shift) if must_shift in must_options else 0
    must_sel = st.selectbox("Forza turno (MUST_DO)", must_options, index=must_idx, key="dlg_lock_must")

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
    )

    if st.button("Salva lock", key="dlg_lock_save"):
        # reparto_id vuoto → state lock; valorizzato → slot lock (se domanda)
        reparto_id_val = "" if reparto_sel == "-- qualsiasi --" else reparto_sel
        ldf = locks_df.copy() if not locks_df.empty else pd.DataFrame(
            columns=["employee_id", "date", "reparto_id", "shift_code", "lock_type"]
        )
        # Rimuovi lock precedenti per questo dipendente+data
        if not ldf.empty and "employee_id" in ldf.columns:
            lmask2 = (ldf["employee_id"].astype(str) == eid) & (ldf["date"] == date_str)
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
        st.session_state["data"]["locks"] = ldf
        # Se un turno vietato coincide con la preassegnazione attiva → svuota
        if forbidden_sel:
            pa = st.session_state["data"]["preassignments"].copy()
            if not pa.empty and "employee_id" in pa.columns and "data" in pa.columns:
                code_col = next((c for c in ("state_code", "shift_code", "turno") if c in pa.columns), None)
                if code_col:
                    pmask = (
                        (pa["employee_id"].astype(str) == eid)
                        & (pa["data"] == date_str)
                        & (pa[code_col].astype(str).isin(forbidden_sel))
                    )
                    if pmask.any():
                        pa = pa[~pmask].reset_index(drop=True)
                        st.session_state["data"]["preassignments"] = pa
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
    for shift, groups in by_shift.items():
        st.markdown(f"**Turno {shift}**")
        for grp in groups:
            icon = "✓" if grp["total_ok"] else "✗"
            color = "#155724" if grp["total_ok"] else "#721c24"
            st.markdown(
                f'<div style="margin-left:10px;color:{color};font-size:0.9rem;">'
                f'{icon} Totale &nbsp; {grp["total_present"]} / {grp["total_required"]}'
                f'</div>',
                unsafe_allow_html=True,
            )
            for rd in grp["roles"]:
                if rd["min_required"] == 0:
                    continue
                ri = "✓" if rd["ok"] else "✗"
                rc = "#155724" if rd["ok"] else "#721c24"
                st.markdown(
                    f'<div style="margin-left:24px;color:{rc};font-size:0.85rem;">'
                    f'{ri} {rd["role"]} &nbsp; {rd["present"]} / {rd["min_required"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )


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
        pa = st.session_state["data"]["preassignments"]
        st.session_state["data"]["preassignments"] = pa.iloc[0:0].copy()
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
    dates, all_rows = build_schedule(data)
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

    # ── 6. Toolbar ───────────────────────────────────────────────────────────
    if sel_now and sel_now.get("sel_type") == "emp":
        det_label, det_cls = "Dettaglio dipendente", "btn"
    elif sel_now and sel_now.get("sel_type") == "day":
        det_label, det_cls = "Dettaglio stato", "btn"
    else:
        det_label, det_cls = "Dettaglio", "btn off"

    filtri_cls   = "btn btn-active" if show_filters  else "btn"
    show_cov_cls = "btn btn-active" if show_coverage else "btn"

    toolbar_html = (
        _TB_CSS +
        f'<div class="tb">'
        f'<a id="{det_id}" href="#" class="{det_cls}">{det_label}</a>'
        '<span class="sep"></span>'
        f'<a id="{clear_id}" href="#" class="btn">&#128465; Svuota preassegnazioni</a>'
        '<span class="sep"></span>'
        '<span class="btn">&Sigma; Mostra accum.</span>'
        f'<a id="{show_cov_id}" href="#" class="{show_cov_cls}">&#128202; Mostra copertura</a>'
        '<span class="sep"></span>'
        '<span class="btn">&#128260; Aggiorna</span>'
        '<span class="sep"></span>'
        '<span class="btn">&#128424; Stampa</span>'
        '<span class="btn">&#128203; Export</span>'
        '<span class="sep"></span>'
        f'<a id="{filtri_id}" href="#" class="{filtri_cls}">&#9776; Filtri</a>'
        f'<span class="info">{n_emp} dipendenti &middot; {n_days} giorni &middot; {month_label}</span>'
        '</div>'
    )
    click_detector(toolbar_html, key="toolbar")

    # ── 7. Filtri (se visibili) ─────────────────────────────────────────────
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

    # ── 8. Griglia principale ────────────────────────────────────────────────
    grid_html = render_grid(dates, filtered_rows)
    click_detector(grid_html, key="grid")

    # ── 9. Tabella copertura ──────────────────────────────────────────────────
    # Sempre click_detector: quando il dialog copertura è aperto via pulsante,
    # l'HTML non cambia (il pulsante non modifica contatore né selezione) →
    # click_detector non re-emette "" → nessun re-run spurio → dialog stabile.
    cov_data: dict = {}
    if show_coverage:
        st.markdown("**Copertura del fabbisogno**")
        cov_data = compute_coverage_preview(data, all_rows)
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

    # ── 10. Apri dialog (SEMPRE per ultimo, una funzione per tipo) ──────────
    # Funzioni diverse = componenti React indipendenti = no content bleed
    if _dialog_kind == "emp":
        _show_emp_dialog({"eid": _early_sel["sel_id"]}, data)
    elif _dialog_kind == "day":
        _show_day_dialog({"eid": _early_sel["sel_id"], "date": _early_sel.get("sel_date", "")}, data)
    elif _dialog_kind == "cov":
        _cov_rep, _cov_ds = open_cov_dialog
        _cov_d = cov_data if cov_data else compute_coverage_preview(data, all_rows)
        _show_cov_dialog({"reparto": _cov_rep, "date": _cov_ds, "cov_data": _cov_d}, data)

_grid_section()
