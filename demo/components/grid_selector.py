"""Interactive grid component with cell selection support."""
from __future__ import annotations

from pathlib import Path

import streamlit.components.v1 as components

_COMP_DIR = Path(__file__).parent / "grid_selector_frontend"
_component_func = components.declare_component("grid_selector", path=str(_COMP_DIR))


def grid_selector(
    grid_html: str,
    grid_css: str,
    selected: dict | None = None,
    key: str = "grid",
) -> dict | None:
    """Render the schedule grid with clickable cells.

    Returns a dict ``{sel_type, sel_id, sel_date}`` when a cell is clicked,
    or *None* when nothing has been selected yet.
    """
    return _component_func(
        grid_html=grid_html,
        grid_css=grid_css,
        selected=selected if selected else {},
        key=key,
        default=None,
    )
