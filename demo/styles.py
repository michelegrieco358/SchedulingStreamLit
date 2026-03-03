"""CSS styling — pixel-accurate replica of SKYppm HTML interface."""

# ── Grid CSS (injected into the custom component iframe) ─────────────────────
GRID_CSS = r"""
/* ===== GOOGLE FONT ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ===== ROOT VARIABLES ===== */
:root {
    --teal-dark: #093d41;
    --teal-medium: #15757b;
    --teal-light: #078891;
    --teal-pale: #0a9ba6;
    --teal-soft: #e0f4f5;
    --bg-color: #f0f7f8;
    --surface-color: #ffffff;
    --border-color: #c5e0e3;
    --text-primary: #093d41;
    --text-secondary: #3a6a6e;
    --cell-w: 45px;
    --cell-h: 55px;
    --name-w: 210px;
    --font: 'Inter', system-ui, -apple-system, sans-serif;
}

html, body { font-family: var(--font); margin: 0; padding: 0; }

/* ===== SCHEDULE CONTAINER ===== */
.sched-container {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(9,61,65,0.10);
    overflow: auto;
    max-height: 78vh;
}

/* ===== GRID TABLE ===== */
table.sky-grid {
    border-collapse: collapse;
    font-family: var(--font);
    font-size: 0.85rem;
    width: max-content;
    min-width: 100%;
}
table.sky-grid thead { position: sticky; top: 0; z-index: 12; }
table.sky-grid thead th {
    background: var(--bg-color);
    color: var(--text-secondary);
    font-weight: 600; font-size: 0.75rem;
    text-align: center; padding: 4px 0;
    border: 1px solid var(--border-color);
    border-bottom: 2px solid var(--border-color);
    width: var(--cell-w); min-width: var(--cell-w); max-width: var(--cell-w);
    height: var(--cell-h); vertical-align: middle; line-height: 1.15;
}
table.sky-grid thead th .dn { display: block; font-size: 0.9rem; font-weight: 600; color: var(--text-primary); }
table.sky-grid thead th .dl { display: block; font-size: 0.7rem; color: var(--text-secondary); }
table.sky-grid thead th.nhdr {
    position: sticky; left: 0; z-index: 20;
    min-width: var(--name-w); max-width: var(--name-w); width: var(--name-w);
    text-align: left; padding-left: 10px;
    background: #d2ecee; border-right: 2px solid #ccc;
}

/* --- BODY --- */
table.sky-grid tbody td {
    text-align: center; border: 1px solid var(--border-color);
    width: var(--cell-w); min-width: var(--cell-w); max-width: var(--cell-w);
    height: var(--cell-h); padding: 0;
    vertical-align: top; cursor: default; user-select: none;
}
table.sky-grid tbody tr:hover td { filter: brightness(0.97); }
table.sky-grid tbody tr:hover td.ncell { background: #f0f9fa !important; }

/* Name cell */
table.sky-grid tbody td.ncell {
    position: sticky; left: 0; z-index: 5; background: #fff;
    text-align: left; padding: 0 0 0 10px;
    min-width: var(--name-w); max-width: var(--name-w); width: var(--name-w);
    border-right: 2px solid #ccc; font-size: 0.78rem; font-weight: 500;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    vertical-align: middle; cursor: pointer;
}

/* --- Day cell (3 lines) --- */
.dc { display: flex; flex-direction: column; justify-content: center; align-items: center; height: 100%; padding: 2px 0; line-height: 1; gap: 1px; }
.dc .l1 { font-weight: 700; display: flex; align-items: center; justify-content: center; font-size: 0.85rem; }
.dc .l2 { font-size: 0.65rem; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }
.dc .l3 { font-size: 0.65rem; display: flex; align-items: center; justify-content: center; color: var(--text-secondary); }

/* --- Day background colours --- */
.bg-sun   { background-color: #FFFF00 !important; }
.bg-hol   { background-color: #FFFFE0 !important; }
.bg-def   { background-color: #d4f1f4 !important; }
.bg-today { background-color: #15757b !important; color: #fff !important; }
.bg-today .l1, .bg-today .l2, .bg-today .l3 { color: #fff !important; }
.bg-black { background-color: #000000 !important; color: #444 !important; }
.bg-orange{ background-color: #FFA500 !important; }
.bg-green { background-color: #90EE90 !important; }
.bg-abs   { background-color: #FF0000 !important; color: #fff !important; }
.bg-abs .l1, .bg-abs .l2, .bg-abs .l3 { color: #fff !important; }
.bg-sw    { background-color: #ADD8E6 !important; }
.bg-rest  { background-color: #f0f0f0 !important; }
.bg-rest .l1 { color: #999; font-weight: 400; }
.bg-night { background-color: #3a3a6e !important; color: #fff !important; }
.bg-night .l1, .bg-night .l2, .bg-night .l3 { color: #fff !important; }
.bg-sn    { background-color: #b8a9d4 !important; color: #2d1f4e !important; }
.bg-sn .l1 { font-weight: 500; }

/* --- Scrollbar --- */
.sched-container::-webkit-scrollbar { width: 8px; height: 8px; }
.sched-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
.sched-container::-webkit-scrollbar-thumb { background: var(--teal-medium); border-radius: 4px; }
.sched-container::-webkit-scrollbar-thumb:hover { background: var(--teal-dark); }
"""

# ── Page CSS (injected into the Streamlit main page) ─────────────────────────
PAGE_CSS = r"""
<style>
/* ===== GOOGLE FONT ===== */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ===== ROOT VARIABLES (from SKYppm) ===== */
:root {
    --teal-dark: #093d41;
    --teal-medium: #15757b;
    --teal-light: #078891;
    --teal-pale: #0a9ba6;
    --teal-soft: #e0f4f5;
    --teal-hover: #0b5a5f;

    --primary-gradient: linear-gradient(293deg, #093d41 0%, #15757b 46%, #078891 100%);
    --bg-color: #f0f7f8;
    --surface-color: #ffffff;
    --border-color: #c5e0e3;
    --text-primary: #093d41;
    --text-secondary: #3a6a6e;

    --cell-w: 45px;
    --cell-h: 55px;
    --name-w: 210px;
    --hdr-h: 70px;
    --font: 'Inter', system-ui, -apple-system, sans-serif;
}

/* ===== GLOBAL ===== */
html, body, [data-testid="stAppViewContainer"] {
    font-family: var(--font) !important;
}
.main {
    background: linear-gradient(135deg, #e8f4f5 0%, #d0e8ea 50%, #c5dfe2 100%) !important;
}
.block-container { padding-top: 1rem !important; max-width: 100% !important; }

/* ===== SIDEBAR (ottanio gradient) ===== */
section[data-testid="stSidebar"] > div:first-child {
    background: var(--primary-gradient) !important;
    color: white !important;
}
section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3,
section[data-testid="stSidebar"] label,
section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] .stMarkdown {
    color: white !important;
}
section[data-testid="stSidebar"] hr {
    border-color: rgba(255,255,255,0.15) !important;
}
section[data-testid="stSidebar"] .stRadio > div {
    background: rgba(255,255,255,0.08);
    border-radius: 8px;
    padding: 6px;
}
section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label {
    font-size: 0.75rem !important;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600 !important;
}

/* ===== HEADER BAR ===== */
.sky-header {
    background: var(--primary-gradient);
    color: white;
    padding: 0 28px;
    height: var(--hdr-h);
    display: flex;
    align-items: center;
    justify-content: space-between;
    border-radius: 16px 16px 0 0;
    box-shadow: 0 4px 16px rgba(9,61,65,0.15);
}
.sky-header .hdr-title {
    font-size: 1rem;
    font-weight: 500;
    color: rgba(255,255,255,0.9);
    letter-spacing: 0.3px;
}
.sky-header .hdr-sub {
    font-size: 0.8rem;
    color: rgba(255,255,255,0.7);
    margin-top: 2px;
}

/* ===== TOOLBAR ===== */
.sky-toolbar {
    background: var(--surface-color);
    padding: 12px 28px;
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    min-height: 56px;
    font-family: var(--font);
}
.tb-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border: 1px solid var(--border-color);
    background: white;
    border-radius: 8px;
    cursor: pointer;
    font-size: 0.85rem;
    color: var(--text-primary);
    font-weight: 500;
    text-decoration: none;
}
.tb-btn:hover {
    background: var(--teal-soft);
    border-color: var(--teal-medium);
    color: var(--text-primary);
}
/* ===== DETTAGLIO BUTTON (matches tb-btn style) ===== */
.stMainBlockContainer .stButton > button {
    background: white !important;
    border: 1px solid #c5e0e3 !important;
    color: #093d41 !important;
    font-weight: 500 !important;
    border-radius: 8px !important;
    font-size: 0.85rem !important;
    box-shadow: none !important;
}
.stMainBlockContainer .stButton > button:hover:not(:disabled) {
    background: #e0f4f5 !important;
    border-color: #15757b !important;
    color: #093d41 !important;
}
.stMainBlockContainer .stButton > button:disabled {
    opacity: 0.45 !important;
    background: white !important;
    border-color: #c5e0e3 !important;
    color: #093d41 !important;
}

.tb-sep {
    width: 1px;
    height: 28px;
    background: var(--border-color);
    margin: 0 6px;
}
.tb-info {
    margin-left: auto;
    font-size: 0.78rem;
    color: var(--text-secondary);
}

/* ===== SCHEDULE CONTAINER ===== */
.sched-main {
    background: var(--bg-color);
    padding: 24px 28px;
    border-radius: 0 0 16px 16px;
}
.sched-container {
    background: var(--surface-color);
    border: 1px solid var(--border-color);
    border-radius: 12px;
    box-shadow: 0 4px 16px rgba(9,61,65,0.10);
    overflow: auto;
    max-height: 78vh;
}

/* ===== GRID TABLE ===== */
table.sky-grid {
    border-collapse: collapse;
    font-family: var(--font);
    font-size: 0.85rem;
    width: max-content;
    min-width: 100%;
}

/* --- HEADER --- */
table.sky-grid thead {
    position: sticky;
    top: 0;
    z-index: 12;
}
table.sky-grid thead th {
    background: var(--bg-color);
    color: var(--text-secondary);
    font-weight: 600;
    font-size: 0.75rem;
    text-align: center;
    padding: 4px 0;
    border: 1px solid var(--border-color);
    border-bottom: 2px solid var(--border-color);
    width: var(--cell-w);
    min-width: var(--cell-w);
    max-width: var(--cell-w);
    height: var(--cell-h);
    vertical-align: middle;
    line-height: 1.15;
}
table.sky-grid thead th .dn {
    display: block;
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-primary);
}
table.sky-grid thead th .dl {
    display: block;
    font-size: 0.7rem;
    color: var(--text-secondary);
}

/* Name header */
table.sky-grid thead th.nhdr {
    position: sticky;
    left: 0;
    z-index: 20;
    min-width: var(--name-w);
    max-width: var(--name-w);
    width: var(--name-w);
    text-align: left;
    padding-left: 10px;
    background: #d2ecee;
    border-right: 2px solid #ccc;
}

/* --- BODY --- */
table.sky-grid tbody td {
    text-align: center;
    border: 1px solid var(--border-color);
    width: var(--cell-w);
    min-width: var(--cell-w);
    max-width: var(--cell-w);
    height: var(--cell-h);
    padding: 0;
    vertical-align: top;
    cursor: default;
    user-select: none;
}
table.sky-grid tbody tr:hover td { filter: brightness(0.97); }
table.sky-grid tbody tr:hover td.ncell { background: #f0f9fa !important; }

/* Name cell */
table.sky-grid tbody td.ncell {
    position: sticky;
    left: 0;
    z-index: 5;
    background: #fff;
    text-align: left;
    padding: 0 0 0 10px;
    min-width: var(--name-w);
    max-width: var(--name-w);
    width: var(--name-w);
    border-right: 2px solid #ccc;
    font-size: 0.78rem;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    vertical-align: middle;
    cursor: pointer;
}

/* --- Day cell (3 lines) --- */
.dc {
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100%;
    padding: 2px 0;
    line-height: 1;
    gap: 1px;
}
.dc .l1 {
    font-weight: 700;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.85rem;
}
.dc .l2 {
    font-size: 0.65rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
}
.dc .l3 {
    font-size: 0.65rem;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-secondary);
}

/* --- Day background colours --- */
.bg-sun   { background-color: #FFFF00 !important; }
.bg-hol   { background-color: #FFFFE0 !important; }
.bg-def   { background-color: #d4f1f4 !important; }
.bg-today { background-color: #15757b !important; color: #fff !important; }
.bg-today .l1, .bg-today .l2, .bg-today .l3 { color: #fff !important; }
.bg-black { background-color: #000000 !important; color: #444 !important; }
.bg-orange{ background-color: #FFA500 !important; }
.bg-green { background-color: #90EE90 !important; }
.bg-abs   { background-color: #FF0000 !important; color: #fff !important; }
.bg-abs .l1, .bg-abs .l2, .bg-abs .l3 { color: #fff !important; }
.bg-sw    { background-color: #ADD8E6 !important; }
.bg-rest  { background-color: #f0f0f0 !important; }
.bg-rest .l1 { color: #999; font-weight: 400; }

/* Night shift special */
.bg-night { background-color: #3a3a6e !important; color: #fff !important; }
.bg-night .l1, .bg-night .l2, .bg-night .l3 { color: #fff !important; }
.bg-sn    { background-color: #b8a9d4 !important; color: #2d1f4e !important; }
.bg-sn .l1 { font-weight: 500; }

/* ===== SCROLLBAR ===== */
.sched-container::-webkit-scrollbar { width: 8px; height: 8px; }
.sched-container::-webkit-scrollbar-track { background: #f1f1f1; border-radius: 4px; }
.sched-container::-webkit-scrollbar-thumb { background: var(--teal-medium); border-radius: 4px; }
.sched-container::-webkit-scrollbar-thumb:hover { background: var(--teal-dark); }

/* ===== FILTER BAR (above grid, ottanio gradient) ===== */
.sky-filters {
    background: linear-gradient(180deg, #15757b 0%, #093d41 100%);
    padding: 14px 28px;
    display: flex;
    gap: 24px;
    align-items: center;
    flex-wrap: wrap;
}
.sky-filters .flt-group {
    display: flex;
    align-items: center;
    gap: 10px;
}
.sky-filters .flt-label {
    font-size: 0.72rem;
    color: #fff;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600;
    text-shadow: 0 1px 2px rgba(0,0,0,0.2);
    white-space: nowrap;
}
.sky-filters select {
    padding: 6px 12px;
    border: 2px solid #0a9ba6;
    border-radius: 6px;
    font-size: 0.82rem;
    background: #fff;
    color: #093d41;
    min-width: 140px;
    font-weight: 500;
    cursor: pointer;
    font-family: var(--font);
}
.sky-filters select:hover {
    background: var(--teal-soft);
    border-color: #093d41;
}
.sky-filters select:focus {
    outline: none;
    border-color: #fff;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.4);
}

/* Style the native Streamlit selectboxes inside the filter row */
div[data-testid="stHorizontalBlock"].filter-row .stSelectbox {
    min-width: 160px;
}
div[data-testid="stHorizontalBlock"].filter-row .stSelectbox label {
    font-size: 0.72rem !important;
    color: var(--teal-dark) !important;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    font-weight: 600 !important;
}

/* ===== SIDEBAR SECTIONS ===== */
.sidebar-section-title {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.7;
    margin-bottom: 4px;
    border-bottom: 1px solid rgba(255,255,255,0.15);
    padding-bottom: 6px;
}

/* ===== SIDEBAR EXPANDER (Impostazioni avanzate) ===== */
/* Summary/header: semi-transparent bg, white text preserved */
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary {
    background: rgba(255,255,255,0.12) !important;
    border-radius: 8px !important;
    padding: 10px 14px !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary:hover,
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary:focus,
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary:active {
    background: rgba(255,255,255,0.22) !important;
}
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary p,
section[data-testid="stSidebar"] details[data-testid="stExpander"] > summary span {
    color: white !important;
}

/* Content area: trasparente (eredita gradiente sidebar), testo bianco ok */
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] {
    background: transparent !important;
    padding: 12px 4px 4px 4px !important;
}
/* Input fields: sfondo bianco con testo scuro */
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] input,
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] select {
    color: #093d41 !important;
    background: white !important;
}

/* "Applica configurazione" button inside expander */
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] .stButton > button {
    background: #0a9ba6 !important;
    color: white !important;
    border: none !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    box-shadow: none !important;
}
section[data-testid="stSidebar"] [data-testid="stExpanderDetails"] .stButton > button:hover {
    background: #088590 !important;
    color: white !important;
}

/* ===== DETAIL PANEL (below grid) ===== */
.detail-panel {
    background: #fff;
    border: 2px solid #0a9ba6;
    border-radius: 12px;
    padding: 20px 28px;
    margin-top: 16px;
    box-shadow: 0 4px 16px rgba(9,61,65,0.10);
    font-family: 'Inter', system-ui, sans-serif;
}
.detail-panel .dp-header {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: #15757b;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid #c5e0e3;
}
.detail-panel .dp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 12px 24px;
}
.detail-panel .dp-item .dp-label {
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: #3a6a6e;
    font-weight: 600;
    margin-bottom: 2px;
}
.detail-panel .dp-item .dp-value {
    font-size: 0.95rem;
    font-weight: 500;
    color: #093d41;
}

/* ===== CELL SELECTION (clickable anchor links in grid) ===== */
td.ncell a.cell-link, td.dc-cell a.cell-link {
    color: inherit !important;
    text-decoration: none !important;
    display: block;
    width: 100%;
    height: 100%;
}
td.ncell a.cell-link { line-height: var(--cell-h); }
.cell-selected {
    outline: 3px solid #0a9ba6 !important;
    outline-offset: -3px;
    box-shadow: inset 0 0 0 2px rgba(10,155,166,0.35) !important;
    position: relative;
    z-index: 2;
}
td.ncell:hover, td.dc-cell:hover { filter: brightness(0.90); cursor: pointer; }

/* ===== HIDE default Streamlit chrome (keep sidebar toggle visible) ===== */
header[data-testid="stHeader"] {
    background: transparent !important;
    border-bottom: none !important;
}
#MainMenu { display: none !important; }
footer { display: none !important; }
</style>
"""


def inject_css():
    """Inject custom CSS into Streamlit page."""
    import streamlit as st
    st.markdown(PAGE_CSS, unsafe_allow_html=True)
