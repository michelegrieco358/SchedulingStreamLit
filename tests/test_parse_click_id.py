"""Test per parse_click_id — parsing robusto dei click sulla griglia."""
from __future__ import annotations

from demo.parsing import parse_click_id


# ── emp- ────────────────────────────────────────────────────────────────────

def test_emp_numeric_id():
    assert parse_click_id("emp-42") == {
        "sel_type": "emp", "sel_id": "42", "sel_date": "",
    }


def test_emp_string_id():
    assert parse_click_id("emp-ABC") == {
        "sel_type": "emp", "sel_id": "ABC", "sel_date": "",
    }


# ── day- (eid numerico) ────────────────────────────────────────────────────

def test_day_numeric_eid():
    result = parse_click_id("day-42-2024-07-15")
    assert result == {
        "sel_type": "day", "sel_id": "42", "sel_date": "2024-07-15",
    }


def test_day_long_numeric_eid():
    result = parse_click_id("day-12345-2024-01-01")
    assert result == {
        "sel_type": "day", "sel_id": "12345", "sel_date": "2024-01-01",
    }


# ── day- (eid con trattini) ────────────────────────────────────────────────

def test_day_eid_with_dashes():
    result = parse_click_id("day-E-001-2024-07-15")
    assert result == {
        "sel_type": "day", "sel_id": "E-001", "sel_date": "2024-07-15",
    }


def test_day_eid_with_multiple_dashes():
    result = parse_click_id("day-A-B-C-2025-12-31")
    assert result == {
        "sel_type": "day", "sel_id": "A-B-C", "sel_date": "2025-12-31",
    }


# ── input malformati → None ────────────────────────────────────────────────

def test_empty_string():
    assert parse_click_id("") is None


def test_unknown_prefix():
    assert parse_click_id("foo-42") is None


def test_day_too_short():
    """'day-' senza abbastanza caratteri per eid + data."""
    assert parse_click_id("day-") is None


def test_day_missing_eid():
    """Solo la data, senza eid (manca il separatore)."""
    assert parse_click_id("day-2024-07-15") is None


def test_day_incomplete_date():
    assert parse_click_id("day-42-2024-07") is None
