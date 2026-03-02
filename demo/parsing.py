"""Funzioni di parsing per gli ID click della griglia (senza dipendenze Streamlit)."""
from __future__ import annotations


def parse_click_id(click_id: str) -> dict | None:
    """Parse 'emp-42' or 'day-42-2024-07-15' into a selection dict.

    Returns a dict with keys ``sel_type``, ``sel_id``, ``sel_date``
    or ``None`` for unrecognised / malformed input.
    """
    if not click_id:
        return None
    if click_id.startswith("emp-"):
        return {"sel_type": "emp", "sel_id": click_id[4:], "sel_date": ""}
    if click_id.startswith("day-"):
        # day-{eid}-{YYYY-MM-DD}  →  la data è sempre gli ultimi 10 char
        rest = click_id[4:]  # e.g. "42-2024-07-15"
        # Il separatore tra eid e data è il trattino che precede YYYY-MM-DD
        # (10 caratteri). Splittiamo da destra per gestire eid con trattini.
        if len(rest) < 12:  # almeno 1 char eid + "-" + 10 char data
            return None
        dt = rest[-10:]     # "2024-07-15"
        eid = rest[:-11]    # tutto prima del trattino separatore
        if not eid or not dt:
            return None
        return {"sel_type": "day", "sel_id": eid, "sel_date": dt}
    return None
