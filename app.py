"""SkyScheduler - Piano di programmazione mensile."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.load_data import load_all_data  # noqa: E402
from ui_helpers import (  # noqa: E402
    build_coverage_html,
    build_employee_detail_html,
    build_initial_plan,
    build_legend_html,
    build_month_plan_html,
    build_shift_grid_html,
    compute_coverage_from_plan,
    get_horizon_dates,
    pivot_state_grid,
)

_MESI = {
    1: "Gennaio", 2: "Febbraio", 3: "Marzo", 4: "Aprile",
    5: "Maggio", 6: "Giugno", 7: "Luglio", 8: "Agosto",
    9: "Settembre", 10: "Ottobre", 11: "Novembre", 12: "Dicembre",
}

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(page_title="SKYppm", layout="wide", initial_sidebar_state="expanded")

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
:root {
    --teal-dark: #093d41;
    --teal-medium: #15757b;
    --teal-light: #078891;
    --teal-pale: #0a9ba6;
    --teal-soft: #e0f4f5;
    --primary-gradient: linear-gradient(293deg, #093d41 0%, #15757b 46%, #078891 100%);
    --bg-color: #f0f7f8;
    --surface-color: #ffffff;
    --border-color: #c5e0e3;
    --text-primary: #093d41;
    --text-secondary: #3a6a6e;
    --font-family: 'Inter', system-ui, -apple-system, sans-serif;
    --cell-width: 42px;
    --cell-height: 32px;
    --name-col-width: 170px;
    --c-sunday: #FFFF00;
    --c-holiday: #FFFFE0;
    --c-default: #d4f1f4;
}

.block-container { padding-top: 0 !important; padding-bottom: 0 !important; }
header[data-testid="stHeader"] { display: none !important; }

section[data-testid="stSidebar"] {
    background: var(--primary-gradient);
}
section[data-testid="stSidebar"] * {
    color: rgba(255,255,255,0.9) !important;
}
section[data-testid="stSidebar"] .stSelectbox > div > div {
    background: rgba(255,255,255,0.12);
    border: 1px solid rgba(255,255,255,0.25);
    border-radius: 8px;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.12);
}

.sky-header {
    background: var(--primary-gradient);
    padding: 0 28px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 12px 12px 0 0;
    margin: 0 0 0 0;
}
.sky-header .brand {
    display: flex; align-items: center; gap: 16px;
}
.sky-header .brand .title {
    font-size: 1rem; font-weight: 500;
    color: rgba(255,255,255,0.9); letter-spacing: 0.3px;
    font-family: var(--font-family);
}

.sky-toolbar {
    background: var(--surface-color);
    padding: 10px 28px;
    border-bottom: 1px solid var(--border-color);
    display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
    font-family: var(--font-family);
}

.stButton button {
    font-weight: 500 !important;
    font-size: 0.82rem !important;
    padding: 7px 14px !important;
    border-radius: 8px !important;
}

/* Bottoni attivi (primary) grassetto */
.stButton > button[kind="primary"],
.stButton button[kind="primary"],
button[kind="primary"],
[data-testid="baseButton-primary"] {
    font-weight: 700 !important;
    background-color: var(--teal-soft) !important;
    border: 2px solid var(--teal-medium) !important;
    color: var(--teal-dark) !important;
}

/* Forza grassetto su tutti i primary button */
div[data-testid="column"] button[kind="primary"] {
    font-weight: 700 !important;
}

.sky-month-tabs {
    display: flex; background: var(--surface-color);
    border-bottom: 1px solid var(--border-color);
    padding: 0 28px; gap: 4px;
    font-family: var(--font-family);
}
.sky-month-tabs .tab {
    padding: 12px 22px; font-size: 0.875rem;
    color: var(--text-secondary); cursor: default;
    border-bottom: 3px solid transparent;
    font-weight: 500; border-radius: 8px 8px 0 0;
}
.sky-month-tabs .tab.active {
    color: var(--teal-dark);
    border-bottom-color: var(--teal-light);
    background: linear-gradient(180deg, var(--teal-soft) 0%, transparent 100%);
    font-weight: 600;
}

.grid-main {
    background: var(--bg-color);
    padding: 20px 28px;
}
.schedule-container {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    overflow: auto;
    box-shadow: 0 4px 16px rgba(9,61,65,0.1);
}

.sg {
    border-collapse: collapse;
    font-family: var(--font-family);
    font-size: 0.82rem;
}
.sg th, .sg td {
    border-right: 1px solid var(--border-color);
    border-bottom: 1px solid var(--border-color);
}

.sg .hdr-cell {
    width: var(--cell-width); min-width: var(--cell-width);
    text-align: center; padding: 4px 0;
    background: var(--bg-color); color: var(--text-secondary);
    font-size: 0.75rem;
}
.sg .hdr-cell .dnum {
    font-size: 0.9rem; font-weight: 600; color: var(--text-primary);
    display: block;
}
.sg .hdr-cell .dow {
    font-size: 0.65rem; color: var(--text-secondary); display: block;
}
.sg .hdr-cell.wk-sun { background: var(--c-sunday); }
.sg .hdr-cell.wk-sat { background: var(--c-holiday); }

.sg .name-col {
    width: var(--name-col-width); min-width: var(--name-col-width);
    max-width: var(--name-col-width);
    text-align: left; padding: 4px 10px;
    position: sticky; left: 0; z-index: 2;
    background: var(--surface-color);
    border-right: 2px solid #ccc;
    font-weight: 500; font-size: 0.82rem;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    color: var(--text-primary);
}
.sg .name-col-h {
    width: var(--name-col-width); min-width: var(--name-col-width);
    text-align: left; padding: 4px 10px;
    position: sticky; left: 0; z-index: 3;
    background: var(--bg-color); border-right: 2px solid #ccc;
    font-weight: 600; color: var(--text-primary);
}

.sg .day-cell {
    width: var(--cell-width); min-width: var(--cell-width);
    height: var(--cell-height);
    text-align: center; vertical-align: middle;
    padding: 0; font-weight: 700; font-size: 0.78rem;
}

.sg .day-cell.wk-sun { background: var(--c-sunday); }
.sg .day-cell.wk-sat { background: var(--c-holiday); }
.sg .day-cell.bg-default { background: var(--c-default); }

.sg .day-cell.st-M  { background: var(--c-default); color: var(--text-primary); }
.sg .day-cell.st-P  { background: var(--c-default); color: var(--text-primary); }
.sg .day-cell.st-N  { background: #3949AB; color: white; }
.sg .day-cell.st-G  { background: #00897B; color: white; }
.sg .day-cell.st-F  { background: #FF0000; color: white; }
.sg .day-cell.st-SN { background: #ADD8E6; color: black; }

.sg .dept-sep td { border-top: 2px solid var(--teal-medium); }

.cg {
    border-collapse: collapse;
    font-family: var(--font-family);
    font-size: 0.75rem;
    margin-top: 8px;
}
.cg th, .cg td {
    border: 1px solid var(--border-color);
}
.cg .cov-hdr {
    background: #e0e0e0; text-align: center; font-weight: 600;
    padding: 4px; font-size: 0.75rem;
}
.cg .cov-name {
    text-align: left; padding: 2px 8px; font-size: 0.72rem;
    background: #fdfdfd; white-space: nowrap;
    min-width: var(--name-col-width); max-width: var(--name-col-width);
    position: sticky; left: 0; z-index: 2;
    border-right: 2px solid #ccc;
}
.cg .cov-cell {
    width: var(--cell-width); min-width: var(--cell-width);
    text-align: center; font-weight: 700; padding: 2px 0;
    font-size: 0.72rem;
}
.cg .bg-cov-red { background: #ffcccc; color: red; font-weight: 700; border: 2px solid red; }
.cg .bg-cov-valid { background: white; color: black; }
.cg .cov-sep td { border-top: 2px solid #999; }

.legend-item {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 4px; font-size: 0.8rem;
}
.l-box {
    width: 22px; height: 22px; flex-shrink: 0;
    border: 1px solid #999; display: flex;
    align-items: center; justify-content: center;
    font-size: 0.7rem; font-weight: 700;
}

.filters-panel {
    background: var(--surface-color);
    border-bottom: 1px solid var(--border-color);
    padding: 12px 28px;
    display: flex; gap: 20px; align-items: end; flex-wrap: wrap;
    font-family: var(--font-family);
}
.filters-panel label {
    font-size: 0.75rem; color: var(--text-secondary); font-weight: 500;
    display: block; margin-bottom: 4px;
}
.filters-panel select {
    padding: 6px 10px; border: 1px solid var(--border-color);
    border-radius: 8px; font-size: 0.82rem; color: var(--text-primary);
    background: white; min-width: 160px;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Init session state
# ---------------------------------------------------------------------------
if "data_loaded" not in st.session_state:
    with st.spinner("Caricamento dati..."):
        data = load_all_data("config.yaml", "data/")
        st.session_state.data = data
        st.session_state.cfg = data["cfg"]
        st.session_state.employees_df = data.get("employees", data.get("employees_df"))
        st.session_state.current_states_df = build_initial_plan(data)
        st.session_state.current_grid = pivot_state_grid(st.session_state.current_states_df)
        try:
            st.session_state.coverage_roles_df = pd.read_csv(
                Path("data/coverage_roles.csv")
            )
        except FileNotFoundError:
            st.session_state.coverage_roles_df = pd.DataFrame()
        st.session_state.data_loaded = True

cfg = st.session_state.cfg
employees_df = st.session_state.employees_df
current_grid = st.session_state.current_grid
current_states_df = st.session_state.current_states_df
dates = get_horizon_dates(cfg)
departments = sorted(employees_df["reparto_id"].dropna().unique().tolist())

horizon = cfg["horizon"]
_raw = horizon["start_date"]
start_date = _raw if isinstance(_raw, date) else date.fromisoformat(str(_raw))

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
_end = horizon["end_date"]
end_date = _end if isinstance(_end, date) else date.fromisoformat(str(_end))
with st.sidebar:
    st.markdown(
        '<div style="text-align:center;padding:12px 0 6px">'
        '<span style="font-size:14px;font-weight:700;letter-spacing:1px">SKYppm</span>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.caption(f"{start_date.strftime('%d/%m/%Y')} - {end_date.strftime('%d/%m/%Y')}")
    st.caption(f"{len(employees_df)} dipendenti | {len(departments)} reparti")

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "show_filters" not in st.session_state:
    st.session_state.show_filters = False
if "show_coverage" not in st.session_state:
    st.session_state.show_coverage = False
if "show_legend" not in st.session_state:
    st.session_state.show_legend = False

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
hdr_left, hdr_right = st.columns([8, 1])
with hdr_left:
    st.markdown(
        '<div class="sky-header">'
        '<div class="brand">'
        '<div class="title">SKYppm - Piano di programmazione mensile</div>'
        '</div>'
        '</div>',
        unsafe_allow_html=True,
    )
with hdr_right:
    if st.button("Filtri", use_container_width=True):
        st.session_state.show_filters = not st.session_state.show_filters
        st.rerun()

# ---------------------------------------------------------------------------
# Filtri
# ---------------------------------------------------------------------------
if st.session_state.show_filters:
    fc1, fc2 = st.columns([2, 8])
    with fc1:
        dept_filter = st.selectbox("Reparto", ["Tutti"] + departments, index=0)
else:
    dept_filter = "Tutti"

# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------
tc = st.columns([1, 1, 1, 1, 1, 1, 1, 1])
with tc[0]:
    _cov_type = "primary" if st.session_state.show_coverage else "secondary"
    if st.button("Mostra copertura", use_container_width=True, type=_cov_type):
        st.session_state.show_coverage = not st.session_state.show_coverage
        st.rerun()
with tc[1]:
    st.button("Aggiorna", use_container_width=True)
with tc[2]:
    st.button("Ordinamento", use_container_width=True)
with tc[3]:
    _leg_type = "primary" if st.session_state.show_legend else "secondary"
    if st.button("Legenda", use_container_width=True, type=_leg_type):
        st.session_state.show_legend = not st.session_state.show_legend
        st.rerun()
with tc[4]:
    st.button("Stampa", use_container_width=True)
with tc[5]:
    st.button("Export", use_container_width=True)
with tc[6]:
    st.button("Presenze", use_container_width=True)
with tc[7]:
    st.button("Giustificativi", use_container_width=True)

show_coverage = st.session_state.show_coverage
show_legend = st.session_state.show_legend

# ---------------------------------------------------------------------------
# Month tabs
# ---------------------------------------------------------------------------
m = start_date.month
y = start_date.year
prev_m = m - 1 if m > 1 else 12
prev_y = y if m > 1 else y - 1
next_m = m + 1 if m < 12 else 1
next_y = y if m < 12 else y + 1

st.markdown(
    '<div class="sky-month-tabs">'
    f'<div class="tab">{_MESI[prev_m]} {prev_y}</div>'
    f'<div class="tab active">{_MESI[m]} {y}</div>'
    f'<div class="tab">{_MESI[next_m]} {next_y}</div>'
    '</div>',
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_plan, tab_month = st.tabs(["Pianificazione mensile", "Month Plan"])

with tab_plan:
    if show_legend:
        st.markdown(build_legend_html(), unsafe_allow_html=True)

    grid_html = build_shift_grid_html(current_grid, employees_df, dates, dept_filter)
    st.markdown(
        f'<div class="grid-main"><div class="schedule-container">{grid_html}</div></div>',
        unsafe_allow_html=True,
    )

    if show_coverage:
        coverage_roles_df = st.session_state.coverage_roles_df
        if coverage_roles_df is not None and not coverage_roles_df.empty:
            coverage_df = compute_coverage_from_plan(
                current_states_df, employees_df, coverage_roles_df, dates,
            )
            cov_html = build_coverage_html(coverage_df, dates)
            st.markdown(
                f'<div class="grid-main"><div class="schedule-container">{cov_html}</div></div>',
                unsafe_allow_html=True,
            )

    csv_bytes = current_states_df.to_csv(index=False).encode("utf-8")
    st.download_button("Scarica piano CSV", data=csv_bytes,
                       file_name="piano_turni.csv", mime="text/csv")

with tab_month:
    coverage_roles_df = st.session_state.coverage_roles_df
    month_html = build_month_plan_html(coverage_roles_df, dates)
    st.markdown(
        f'<div class="grid-main"><div class="schedule-container">{month_html}</div></div>',
        unsafe_allow_html=True,
    )
