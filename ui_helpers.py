"""Funzioni helper per la UI Streamlit — rendering griglia turni stile SkyPPM."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape

import pandas as pd


# ---------------------------------------------------------------------------
# Costanti — stati reali del sistema: M, P, N, G, SN, R, F
# ---------------------------------------------------------------------------

# Classe CSS per ogni stato (corrispondente al CSS in app.py)
STATE_CSS: dict[str, str] = {
    "M":  "st-M",
    "P":  "st-P",
    "N":  "st-N",
    "G":  "st-G",
    "F":  "st-F",
    "SN": "st-SN",
}

# Giorni settimana italiani (Monday=0)
DOW_IT: dict[int, str] = {
    0: "L", 1: "Ma", 2: "Me", 3: "G", 4: "V", 5: "S", 6: "D",
}


# ---------------------------------------------------------------------------
# Piano iniziale
# ---------------------------------------------------------------------------

def build_initial_plan(data: dict) -> pd.DataFrame:
    """Costruisce il piano iniziale: tutto R, con overlay assenze (F) e preassegnamenti."""
    cfg = data.get("cfg", {})
    horizon = cfg.get("horizon", {})
    start = pd.Timestamp(horizon["start_date"])
    end = pd.Timestamp(horizon["end_date"])
    dates = pd.date_range(start, end)

    employees_df = data.get("employees", data.get("employees_df", pd.DataFrame()))
    employees = employees_df["employee_id"].tolist()

    rows = []
    for emp in employees:
        for d in dates:
            rows.append({"employee_id": emp, "date": str(d.date()), "state": "R"})
    df = pd.DataFrame(rows)

    # Overlay assenze
    leaves_days = data.get("leaves_days", data.get("leaves_days_df"))
    if leaves_days is not None and not leaves_days.empty and "employee_id" in leaves_days.columns:
        if "data" in leaves_days.columns:
            leaves_days = leaves_days.copy()
            leaves_days["_date_str"] = pd.to_datetime(leaves_days["data"], errors="coerce").dt.date.astype(str)
        elif "data_dt" in leaves_days.columns:
            leaves_days = leaves_days.copy()
            leaves_days["_date_str"] = pd.to_datetime(leaves_days["data_dt"], errors="coerce").dt.date.astype(str)
        else:
            leaves_days = None

        if leaves_days is not None:
            leave_set = set(
                zip(leaves_days["employee_id"].astype(str), leaves_days["_date_str"])
            )
            mask = df.apply(lambda r: (r["employee_id"], r["date"]) in leave_set, axis=1)
            df.loc[mask, "state"] = "F"

    # Overlay preassegnamenti
    preassign = data.get("preassignments", data.get("preassignments_df"))
    if preassign is not None and not preassign.empty and "employee_id" in preassign.columns:
        pa = preassign.copy()
        if "data" in pa.columns:
            pa["_date_str"] = pd.to_datetime(pa["data"], errors="coerce").dt.date.astype(str)
        elif "date" in pa.columns:
            pa["_date_str"] = pd.to_datetime(pa["date"], errors="coerce").dt.date.astype(str)
        else:
            pa = None

        if pa is not None and "state_code" in pa.columns:
            pa_map = dict(
                zip(
                    zip(pa["employee_id"].astype(str), pa["_date_str"]),
                    pa["state_code"].astype(str).str.strip().str.upper(),
                )
            )
            for idx, row in df.iterrows():
                key = (row["employee_id"], row["date"])
                if key in pa_map and pa_map[key]:
                    df.at[idx, "state"] = pa_map[key]

    return df.sort_values(["employee_id", "date"]).reset_index(drop=True)


def pivot_state_grid(states_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot: righe = employee_id, colonne = date string, valori = state."""
    return states_df.pivot(index="employee_id", columns="date", values="state").fillna("R")


# ---------------------------------------------------------------------------
# Date orizzonte
# ---------------------------------------------------------------------------

def get_horizon_dates(cfg: dict) -> list[date]:
    """Ritorna la lista di date nell'orizzonte di pianificazione."""
    horizon = cfg.get("horizon", {})
    start = pd.Timestamp(horizon["start_date"]).date()
    end = pd.Timestamp(horizon["end_date"]).date()
    result: list[date] = []
    d = start
    while d <= end:
        result.append(d)
        d += timedelta(days=1)
    return result


def _weekend_class(d: date) -> str:
    """Ritorna la classe CSS weekend per un giorno."""
    if d.weekday() == 6:  # Domenica
        return " wk-sun"
    if d.weekday() == 5:  # Sabato
        return " wk-sat"
    return ""


# ---------------------------------------------------------------------------
# Griglia turni HTML — struttura SkyPPM
# ---------------------------------------------------------------------------

def build_shift_grid_html(
    grid_df: pd.DataFrame,
    employees_df: pd.DataFrame,
    dates: list[date],
    dept_filter: str = "Tutti",
    selected_employee: str = "",
) -> str:
    """Genera la tabella HTML griglia turni con classi CSS SkyPPM."""

    if dept_filter != "Tutti":
        dept_emps = set(
            employees_df.loc[
                employees_df["reparto_id"] == dept_filter, "employee_id"
            ].tolist()
        )
        filtered = grid_df.loc[grid_df.index.isin(dept_emps)]
    else:
        filtered = grid_df

    if filtered.empty:
        return "<p>Nessun dipendente per il filtro selezionato.</p>"

    emp_info = employees_df.set_index("employee_id")[
        ["nome", "reparto_id", "role"]
    ].to_dict("index")

    emp_order = sorted(
        filtered.index,
        key=lambda eid: (
            emp_info.get(eid, {}).get("reparto_id", ""),
            emp_info.get(eid, {}).get("role", ""),
            emp_info.get(eid, {}).get("nome", eid),
        ),
    )

    p = ['<table class="sg">']

    # --- Header: una riga con numero giorno + DOW dentro lo stesso th ---
    p.append("<thead><tr>")
    p.append('<th class="name-col-h">Nominativo</th>')
    for d in dates:
        wk = _weekend_class(d)
        p.append(
            f'<th class="hdr-cell{wk}">'
            f'<span class="dnum">{d.day}</span>'
            f'<span class="dow">{DOW_IT[d.weekday()]}</span>'
            f"</th>"
        )
    p.append("</tr></thead>")

    # --- Body ---
    p.append("<tbody>")
    prev_dept: str | None = None
    for eid in emp_order:
        info = emp_info.get(eid, {})
        nome = escape(info.get("nome", eid))
        dept = info.get("reparto_id", "")

        classes = []
        if prev_dept is not None and dept != prev_dept:
            classes.append("dept-sep")
        if eid == selected_employee:
            classes.append("emp-selected")
        prev_dept = dept

        tr_cls = f' class="{" ".join(classes)}"' if classes else ""
        p.append(f"<tr{tr_cls}>")
        p.append(
            f'<td class="name-col" data-eid="{escape(eid)}"'
            f' onclick="selectEmp(this)">{nome}</td>'
        )

        for d in dates:
            d_str = str(d)
            state = ""
            if d_str in filtered.columns and eid in filtered.index:
                val = filtered.at[eid, d_str]
                state = str(val).strip() if pd.notna(val) else ""

            wk = _weekend_class(d)

            if state and state != "R" and state in STATE_CSS:
                css = STATE_CSS[state]
                p.append(f'<td class="day-cell {css}">{state}</td>')
            else:
                # R: mostra "R" con sfondo weekend o default
                bg = wk.strip() if wk else "bg-default"
                label = "R" if state == "R" else ""
                p.append(f'<td class="day-cell {bg}">{label}</td>')

        p.append("</tr>")

    p.append("</tbody></table>")
    return "".join(p)


# ---------------------------------------------------------------------------
# Copertura
# ---------------------------------------------------------------------------

def compute_coverage_from_plan(
    current_states_df: pd.DataFrame,
    employees_df: pd.DataFrame,
    coverage_roles_df: pd.DataFrame,
    dates: list[date],
) -> pd.DataFrame:
    """Calcola la copertura attuale dal piano corrente, confronta con il fabbisogno."""

    emp_info = employees_df[["employee_id", "reparto_id", "role"]].copy()
    emp_info["role"] = emp_info["role"].str.strip().str.upper()

    merged = current_states_df.merge(emp_info, on="employee_id", how="left")

    working = merged[merged["state"].isin(["M", "P"])].copy()
    if working.empty:
        actual = pd.DataFrame(columns=["date", "reparto_id", "state", "role", "assigned"])
    else:
        actual = (
            working.groupby(["date", "reparto_id", "state", "role"])
            .size()
            .reset_index(name="assigned")
        )

    cov = coverage_roles_df.copy()
    role_col = "role" if "role" in cov.columns else "gruppo"
    cov["_role"] = cov[role_col].str.strip().str.upper()

    results = []
    for d in dates:
        d_str = str(d)
        for _, req in cov.iterrows():
            reparto = req.get("reparto_id", "")
            shift = req.get("shift_code", "")
            role = req["_role"]
            min_required = int(req.get("min_ruolo", 0))

            match = actual[
                (actual["date"] == d_str)
                & (actual["reparto_id"] == reparto)
                & (actual["state"] == shift)
                & (actual["role"] == role)
            ]
            assigned = int(match["assigned"].sum()) if not match.empty else 0
            delta = assigned - min_required

            results.append({
                "date": d_str, "day": d.day,
                "reparto_id": reparto, "shift_code": shift, "role": role,
                "required": min_required, "assigned": assigned, "delta": delta,
            })

    return pd.DataFrame(results)


def build_coverage_html(coverage_df: pd.DataFrame, dates: list[date]) -> str:
    """Genera la tabella HTML copertura con classi CSS SkyPPM."""
    if coverage_df.empty:
        return "<p>Nessun dato di copertura disponibile.</p>"

    groups = list(coverage_df.groupby(["reparto_id", "shift_code", "role"]))

    p: list[str] = ['<table class="cg">']

    # Header
    p.append("<thead><tr>")
    p.append('<th class="cov-hdr" style="min-width:170px;text-align:left;padding-left:8px">Dettaglio copertura</th>')
    for d in dates:
        p.append(f'<th class="cov-hdr">{d.day}</th>')
    p.append("</tr></thead><tbody>")

    for (reparto, shift, role), group in groups:
        label = escape(f"{shift} min {role}")
        p.append(f'<tr><td class="cov-name">{label}</td>')
        for d in dates:
            d_str = str(d)
            row_data = group[group["date"] == d_str]
            if row_data.empty:
                p.append('<td class="cov-cell"></td>')
            else:
                assigned = int(row_data.iloc[0]["assigned"])
                delta = int(row_data.iloc[0]["delta"])
                cls = "bg-cov-red" if delta < 0 else "bg-cov-valid"
                p.append(f'<td class="cov-cell {cls}">{assigned}</td>')
        p.append("</tr>")

    # Riga riepilogo
    p.append('<tr class="cov-sep"><td class="cov-name"><b>Copertura</b></td>')
    for d in dates:
        d_str = str(d)
        day_data = coverage_df[coverage_df["date"] == d_str]
        total_delta = int(day_data["delta"].sum()) if not day_data.empty else 0
        if total_delta < 0:
            p.append(f'<td class="cov-cell bg-cov-red">{total_delta}</td>')
        else:
            p.append('<td class="cov-cell bg-cov-valid">OK</td>')
    p.append("</tr>")

    p.append("</tbody></table>")
    return "".join(p)


# ---------------------------------------------------------------------------
# Legenda — struttura SkyPPM (fieldset + legend)
# ---------------------------------------------------------------------------

def build_month_plan_html(
    coverage_roles_df: pd.DataFrame,
    dates: list[date],
) -> str:
    """Genera la tabella HTML del Month Plan (fabbisogno per reparto/turno/ruolo)."""
    if coverage_roles_df is None or coverage_roles_df.empty:
        return "<p>Nessun dato di copertura configurato.</p>"

    cov = coverage_roles_df.copy()
    role_col = "role" if "role" in cov.columns else "gruppo"

    p: list[str] = ['<table class="sg">']

    # Header con giorni
    p.append("<thead><tr>")
    p.append('<th class="name-col-h">Fabbisogno</th>')
    for d in dates:
        wk = _weekend_class(d)
        p.append(
            f'<th class="hdr-cell{wk}">'
            f'<span class="dnum">{d.day}</span>'
            f'<span class="dow">{DOW_IT[d.weekday()]}</span>'
            f"</th>"
        )
    p.append("</tr></thead><tbody>")

    prev_reparto: str | None = None
    for _, row in cov.iterrows():
        reparto = str(row.get("reparto_id", ""))
        shift = str(row.get("shift_code", ""))
        role = str(row.get(role_col, ""))
        min_r = int(row.get("min_ruolo", 0))
        cov_code = str(row.get("coverage_code", ""))

        tr_cls = ' class="dept-sep"' if prev_reparto is not None and reparto != prev_reparto else ""
        prev_reparto = reparto

        label = escape(f"{shift} {role} (min {min_r})")
        p.append(f"<tr{tr_cls}>")
        p.append(f'<td class="name-col">{label}</td>')

        for d in dates:
            wk = _weekend_class(d)
            bg = wk.strip() if wk else "bg-default"
            p.append(f'<td class="day-cell {bg}">{escape(cov_code)}</td>')

        p.append("</tr>")

    p.append("</tbody></table>")
    return "".join(p)


# ---------------------------------------------------------------------------
# Dettaglio dipendente
# ---------------------------------------------------------------------------

def build_employee_detail_html(
    employees_df: pd.DataFrame,
    employee_id: str,
) -> str:
    """Genera HTML card con le informazioni del dipendente selezionato."""
    row = employees_df.loc[employees_df["employee_id"] == employee_id]
    if row.empty:
        return "<p>Dipendente non trovato.</p>"

    r = row.iloc[0]
    nome = escape(str(r.get("nome", employee_id)))
    role = escape(str(r.get("role", "")))
    reparto = escape(str(r.get("reparto_label", r.get("reparto_id", ""))))
    ore_dovute = r.get("ore_dovute_mese_h", "")
    saldo = r.get("saldo_prog_iniziale_h", "")
    max_month = r.get("max_month_hours_h", "")
    max_week = r.get("max_week_hours_h", "")
    max_delta = r.get("max_balance_delta_month_h", "")
    can_night = r.get("can_work_night", False)
    max_nights_m = r.get("max_nights_month", "")
    max_nights_w = r.get("max_nights_week", "")
    sat_ytd = r.get("saturday_count_ytd", 0)
    sun_ytd = r.get("sunday_count_ytd", 0)
    hol_ytd = r.get("holiday_count_ytd", 0)
    pool = escape(str(r.get("pool_id", "")))

    saldo_str = f"+{saldo}" if isinstance(saldo, (int, float)) and saldo > 0 else str(saldo)
    night_str = f"Sì ({max_nights_m}/m, {max_nights_w}/s)" if can_night else "No"

    def _cell(label: str, value: str) -> str:
        return (
            '<div style="flex:1;min-width:120px;padding:8px 12px;'
            'border-right:1px solid #e0e0e0">'
            f'<div style="font-size:0.7rem;color:#666;margin-bottom:2px">{escape(label)}</div>'
            f'<div style="font-size:0.95rem;font-weight:600;color:#093d41">{escape(str(value))}</div>'
            '</div>'
        )

    return (
        '<div style="border:1px solid #c5e0e3;border-radius:10px;background:white;'
        'margin:8px 28px;overflow:hidden;box-shadow:0 2px 8px rgba(9,61,65,0.08)">'
        # Intestazione
        '<div style="background:linear-gradient(293deg,#093d41 0%,#15757b 46%,#078891 100%);'
        'padding:10px 16px;color:white;font-size:0.9rem;font-weight:600">'
        f'{nome} &mdash; {role} &middot; {reparto}'
        '</div>'
        # Riga 1: ore
        '<div style="display:flex;flex-wrap:wrap;border-bottom:1px solid #eee">'
        + _cell("Ore dovute mese", f"{ore_dovute}h")
        + _cell("Saldo progressivo", f"{saldo_str}h")
        + _cell("Max ore mese", f"{max_month}h")
        + _cell("Max ore settimana", f"{max_week}h")
        + _cell("Max scostamento saldo", f"{max_delta}h")
        + '</div>'
        # Riga 2: notti e contatori
        '<div style="display:flex;flex-wrap:wrap">'
        + _cell("Notti", night_str)
        + _cell("Sabati YTD", str(sat_ytd))
        + _cell("Domeniche YTD", str(sun_ytd))
        + _cell("Festivi YTD", str(hol_ytd))
        + _cell("Pool", pool)
        + '</div>'
        '</div>'
    )


# ---------------------------------------------------------------------------
# Legenda
# ---------------------------------------------------------------------------

def build_legend_html() -> str:
    """Genera la legenda colori in formato orizzontale."""
    return """
    <div style="display:flex;flex-wrap:wrap;gap:16px;align-items:center;padding:8px 0;">
        <div class="legend-item">
            <div class="l-box" style="background:#d4f1f4;color:#093d41">M</div> Mattina
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#d4f1f4;color:#093d41">P</div> Pomeriggio
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#3949AB;color:white">N</div> Notte
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#00897B;color:white">G</div> Giorno
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#FF0000;color:white">F</div> Ferie / Assenza
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#ADD8E6;color:black">SN</div> Smonto notte
        </div>
        <span style="color:#999;margin:0 4px;">|</span>
        <div class="legend-item">
            <div class="l-box" style="background:#FFFFE0"></div> Sabato
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#FFFF00"></div> Domenica
        </div>
        <div class="legend-item">
            <div class="l-box" style="background:#d4f1f4"></div> Feriale
        </div>
    </div>
    """
