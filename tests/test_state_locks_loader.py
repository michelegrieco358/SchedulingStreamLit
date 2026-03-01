"""Tests per la nuova semantica state lock in loader/locks.py.

Copertura:
- load_locks(): classificazione slot lock vs state lock
  - Domanda + reparto → slot lock
  - Domanda + no reparto → state lock
  - Non-domanda + reparto → state lock (reparto ignorato)
  - Non-domanda + no reparto → state lock
  - Regression: N classificato come slot lock anche se assente da shift_slots
    (fix: classificazione usa TURNI_DOMANDA, non shift_slots)
- validate_state_locks(): validazione employee_id, state_code, conflitti
- split_state_locks(): separazione MUST_DO / FORBIDDEN
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from loader.locks import load_locks, split_state_locks, validate_state_locks


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_locks_csv(tmp_path, rows: list[dict]) -> str:
    """Scrive un locks.csv simbolico e restituisce il path."""
    cols = ["employee_id", "date", "reparto_id", "shift_code", "lock_type"]
    df = pd.DataFrame(rows, columns=cols)
    path = tmp_path / "locks.csv"
    df.to_csv(path, index=False)
    return str(path)


def _base_shift_slots(shift_code: str = "M", reparto: str = "DEG") -> pd.DataFrame:
    """Shift slots minimali con una riga per il test."""
    return pd.DataFrame(
        {
            "slot_id": [1],
            "reparto_id": [reparto],
            "shift_code": [shift_code],
            "start_dt": [pd.Timestamp("2025-11-01 07:00:00")],
        }
    )


# ── Classificazione: slot lock vs state lock ──────────────────────────────────


def test_demand_with_reparto_creates_slot_lock(tmp_path) -> None:
    """Codice di domanda M + reparto → classificato come slot lock."""
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "M", "lock_type": "MUST_DO"}],
    )
    shift_slots = _base_shift_slots("M", "DEG")

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path, shift_slots=shift_slots)

    assert len(slot_locks) == 1
    assert slot_locks.iloc[0]["slot_id"] == 1
    assert slot_locks.iloc[0]["lock"] == 1
    assert state_locks.empty


def test_demand_without_reparto_creates_state_lock(tmp_path) -> None:
    """Codice di domanda M senza reparto → classificato come state lock."""
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "",
          "shift_code": "M", "lock_type": "MUST_DO"}],
    )

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path)

    assert slot_locks.empty
    assert len(state_locks) == 1
    assert state_locks.iloc[0]["state_code"] == "M"
    assert state_locks.iloc[0]["lock"] == 1


def test_non_demand_with_reparto_creates_state_lock(tmp_path) -> None:
    """Codice non-domanda R con reparto → state lock (reparto ignorato)."""
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "R", "lock_type": "FORBIDDEN"}],
    )

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path)

    assert slot_locks.empty
    assert len(state_locks) == 1
    assert state_locks.iloc[0]["state_code"] == "R"
    assert state_locks.iloc[0]["lock"] == -1


def test_non_demand_without_reparto_creates_state_lock(tmp_path) -> None:
    """Codice non-domanda F senza reparto → state lock."""
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "",
          "shift_code": "F", "lock_type": "MUST_DO"}],
    )

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path)

    assert slot_locks.empty
    assert len(state_locks) == 1
    assert state_locks.iloc[0]["state_code"] == "F"


def test_sn_code_creates_state_lock(tmp_path) -> None:
    """Codice SN (non-domanda) → state lock indipendentemente dal reparto."""
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "SN", "lock_type": "FORBIDDEN"}],
    )

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path)

    assert slot_locks.empty
    assert len(state_locks) == 1
    assert state_locks.iloc[0]["state_code"] == "SN"


def test_classification_uses_turni_domanda_not_shift_slots(tmp_path) -> None:
    """Regression: N deve diventare slot lock anche se shift_slots non contiene N.

    Prima del fix, demand_codes era derivato da shift_slots["shift_code"].unique():
    se N non era presente, il lock N+reparto diventava erroneamente state lock.
    Dopo il fix, si usa TURNI_DOMANDA (costante), quindi N è sempre slot lock
    quando ha reparto → viene tentato il match sullo slot, che fallisce con
    warning "slot non trovato" invece di diventare silenziosamente state lock.
    """
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "N", "lock_type": "MUST_DO"}],
    )
    # shift_slots ha solo M, non N: scenario che causava il bug
    shift_slots = _base_shift_slots("M", "DEG")

    with pytest.warns(UserWarning) as wlist:
        slot_locks, state_locks = load_locks(path, shift_slots=shift_slots)

    # N è in TURNI_DOMANDA → tenta slot lock → slot non trovato → warning
    warning_messages = [str(w.message) for w in wlist]
    assert any("slot non trovato" in m for m in warning_messages), (
        f"Atteso warning 'slot non trovato', ricevuti: {warning_messages}"
    )
    # Non viene creato state lock (non è non-domanda, non è domanda senza reparto)
    assert state_locks.empty, (
        "N con reparto non deve essere classificato come state lock (regressione TURNI_DOMANDA)"
    )
    # Il slot lock non viene creato perché lo slot non esiste (solo scartato)
    assert slot_locks.empty


def test_must_do_with_multiple_slots_warns_and_deduplicates(tmp_path) -> None:
    """Regression: MUST_DO su (data, reparto, shift) con N>1 slot non deve
    sollevare MergeError ma emettere un warning e tenere solo il primo slot_id.

    Scenario: due coverage_code diversi producono slot 1 e slot 2 entrambi
    per M/DEG/2025-11-01. Il lock MUST_DO deve applicarsi a un solo slot.
    """
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "M", "lock_type": "MUST_DO"}],
    )
    # Due slot per la stessa (data, reparto, shift_code)
    shift_slots = pd.DataFrame(
        {
            "slot_id": [1, 2],
            "reparto_id": ["DEG", "DEG"],
            "shift_code": ["M", "M"],
            "start_dt": [
                pd.Timestamp("2025-11-01 07:00:00"),
                pd.Timestamp("2025-11-01 07:00:00"),
            ],
        }
    )

    with pytest.warns(UserWarning) as wlist:
        slot_locks, state_locks = load_locks(path, shift_slots=shift_slots)

    warning_messages = [str(w.message) for w in wlist]
    assert any("più slot" in m for m in warning_messages), (
        f"Atteso warning 'più slot', ricevuti: {warning_messages}"
    )
    # Un solo slot lock deve essere prodotto (non due)
    assert len(slot_locks) == 1
    assert slot_locks.iloc[0]["slot_id"] == 1  # primo slot_id (ordinato)
    assert slot_locks.iloc[0]["lock"] == 1
    assert state_locks.empty


def test_forbidden_with_multiple_slots_locks_all(tmp_path) -> None:
    """FORBIDDEN su (data, reparto, shift) con N>1 slot deve bloccare tutti gli slot.

    Semantica: 'il dipendente non può fare quel turno' → nessuno dei slot
    matching deve essere assegnabile.
    """
    path = _make_locks_csv(
        tmp_path,
        [{"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
          "shift_code": "M", "lock_type": "FORBIDDEN"}],
    )
    shift_slots = pd.DataFrame(
        {
            "slot_id": [1, 2],
            "reparto_id": ["DEG", "DEG"],
            "shift_code": ["M", "M"],
            "start_dt": [
                pd.Timestamp("2025-11-01 07:00:00"),
                pd.Timestamp("2025-11-01 07:00:00"),
            ],
        }
    )

    with pytest.warns(UserWarning) as wlist:
        slot_locks, state_locks = load_locks(path, shift_slots=shift_slots)

    # Nessun warning "più slot" per FORBIDDEN (nessuna disambiguazione necessaria)
    warning_messages = [str(w.message) for w in wlist]
    assert not any("più slot" in m for m in warning_messages), (
        "FORBIDDEN multi-slot non deve emettere warning di disambiguazione"
    )
    # Entrambi i slot devono essere bloccati
    assert len(slot_locks) == 2
    assert set(slot_locks["slot_id"].tolist()) == {1, 2}
    assert all(slot_locks["lock"] == -1)
    assert state_locks.empty


def test_mixed_rows_classified_correctly(tmp_path) -> None:
    """Righe miste: alcune slot lock, alcune state lock."""
    path = _make_locks_csv(
        tmp_path,
        [
            {"employee_id": "E1", "date": "2025-11-01", "reparto_id": "DEG",
             "shift_code": "M", "lock_type": "MUST_DO"},   # slot lock
            {"employee_id": "E1", "date": "2025-11-02", "reparto_id": "",
             "shift_code": "P", "lock_type": "FORBIDDEN"},  # state lock (no reparto)
            {"employee_id": "E2", "date": "2025-11-01", "reparto_id": "DEG",
             "shift_code": "R", "lock_type": "FORBIDDEN"},  # state lock (non-domanda)
        ],
    )
    shift_slots = pd.DataFrame(
        {
            "slot_id": [1],
            "reparto_id": ["DEG"],
            "shift_code": ["M"],
            "start_dt": [pd.Timestamp("2025-11-01 07:00:00")],
        }
    )

    with pytest.warns(UserWarning):
        slot_locks, state_locks = load_locks(path, shift_slots=shift_slots)

    assert len(slot_locks) == 1
    assert slot_locks.iloc[0]["slot_id"] == 1
    assert len(state_locks) == 2
    state_codes_found = set(state_locks["state_code"].tolist())
    assert state_codes_found == {"P", "R"}


# ── validate_state_locks ──────────────────────────────────────────────────────


def _employees_df(eids: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"employee_id": eids, "role": ["INFERMIERE"] * len(eids)})


def _state_locks_df(rows: list[dict]) -> pd.DataFrame:
    """Costruisce un DataFrame di state lock nel formato atteso."""
    cols = ["employee_id", "date", "state_code", "lock", "note"]
    data = []
    for r in rows:
        data.append(
            {
                "employee_id": r["employee_id"],
                "date": r.get("date", date(2025, 11, 1)),
                "state_code": r["state_code"],
                "lock": r["lock"],
                "note": r.get("note", ""),
            }
        )
    return pd.DataFrame(data, columns=cols)


def test_validate_state_locks_passes_valid_data() -> None:
    """Dati validi superano la validazione senza errori."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": 1},
        {"employee_id": "E1", "state_code": "F", "lock": -1, "date": date(2025, 11, 2)},
    ])
    employees = _employees_df(["E1"])
    result = validate_state_locks(df, employees, state_codes=("M", "P", "N", "G", "SN", "R", "F"))
    assert len(result) == 2


def test_validate_state_locks_unknown_employee() -> None:
    """employee_id non presente in employees → ValueError."""
    df = _state_locks_df([{"employee_id": "GHOST", "state_code": "R", "lock": 1}])
    employees = _employees_df(["E1"])
    with pytest.raises(ValueError, match="employee_id inesistente"):
        validate_state_locks(df, employees, state_codes=("R",))


def test_validate_state_locks_unknown_state_code() -> None:
    """state_code non in state_codes config → ValueError."""
    df = _state_locks_df([{"employee_id": "E1", "state_code": "XYZ", "lock": 1}])
    employees = _employees_df(["E1"])
    with pytest.raises(ValueError, match="state_code non riconosciuto"):
        validate_state_locks(df, employees, state_codes=("M", "P", "N", "G", "R", "F"))


def test_validate_state_locks_must_forbidden_conflict() -> None:
    """MUST_DO e FORBIDDEN sulla stessa (employee, date, state_code) → ValueError."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": 1},
        {"employee_id": "E1", "state_code": "R", "lock": -1},
    ])
    employees = _employees_df(["E1"])
    with pytest.raises(ValueError, match="lock contrastanti"):
        validate_state_locks(df, employees, state_codes=("R",))


def test_validate_state_locks_two_must_different_states_same_day() -> None:
    """Due MUST_DO su stati diversi nello stesso giorno → ValueError."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": 1},
        {"employee_id": "E1", "state_code": "M", "lock": 1},
    ])
    employees = _employees_df(["E1"])
    with pytest.raises(ValueError, match="due o più MUST_DO"):
        validate_state_locks(df, employees, state_codes=("M", "R"))


def test_validate_state_locks_must_on_absence_day() -> None:
    """MUST_DO su giorno di assenza → ValueError."""
    df = _state_locks_df([{"employee_id": "E1", "state_code": "M", "lock": 1}])
    employees = _employees_df(["E1"])
    absences = pd.DataFrame(
        {"employee_id": ["E1"], "date": [date(2025, 11, 1)], "is_absent": [True]}
    )
    with pytest.raises(ValueError, match="MUST_DO su giorni di assenza"):
        validate_state_locks(df, employees, state_codes=("M",), absences_by_day=absences)


def test_validate_state_locks_forbidden_on_absence_day_is_ok() -> None:
    """FORBIDDEN su giorno di assenza è ammesso (non è una contraddizione)."""
    df = _state_locks_df([{"employee_id": "E1", "state_code": "M", "lock": -1}])
    employees = _employees_df(["E1"])
    absences = pd.DataFrame(
        {"employee_id": ["E1"], "date": [date(2025, 11, 1)], "is_absent": [True]}
    )
    # Non deve sollevare eccezioni
    result = validate_state_locks(df, employees, state_codes=("M",), absences_by_day=absences)
    assert len(result) == 1


def test_validate_state_locks_empty_df_returns_empty() -> None:
    """DataFrame vuoto → restituisce DataFrame vuoto senza errori."""
    empty = pd.DataFrame(columns=["employee_id", "date", "state_code", "lock", "note"])
    employees = _employees_df(["E1"])
    result = validate_state_locks(empty, employees, state_codes=("M", "R"))
    assert result.empty


# ── split_state_locks ─────────────────────────────────────────────────────────


def test_split_state_locks_separates_must_and_forbid() -> None:
    """split_state_locks separa correttamente MUST_DO (lock=1) da FORBIDDEN (lock=-1)."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": 1},
        {"employee_id": "E1", "state_code": "M", "lock": -1, "date": date(2025, 11, 2)},
        {"employee_id": "E2", "state_code": "F", "lock": -1},
    ])
    must_df, forbid_df = split_state_locks(df)

    assert list(must_df.columns) == ["employee_id", "date", "state_code"]
    assert list(forbid_df.columns) == ["employee_id", "date", "state_code"]
    assert len(must_df) == 1
    assert must_df.iloc[0]["state_code"] == "R"
    assert len(forbid_df) == 2
    assert set(forbid_df["state_code"].tolist()) == {"M", "F"}


def test_split_state_locks_all_must() -> None:
    """Tutti MUST_DO → forbid vuoto."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": 1},
    ])
    must_df, forbid_df = split_state_locks(df)
    assert len(must_df) == 1
    assert forbid_df.empty


def test_split_state_locks_all_forbid() -> None:
    """Tutti FORBIDDEN → must vuoto."""
    df = _state_locks_df([
        {"employee_id": "E1", "state_code": "R", "lock": -1},
    ])
    must_df, forbid_df = split_state_locks(df)
    assert must_df.empty
    assert len(forbid_df) == 1


def test_split_state_locks_empty() -> None:
    """DataFrame vuoto → entrambi i DataFrame vuoti."""
    empty = pd.DataFrame(columns=["employee_id", "date", "state_code", "lock", "note"])
    must_df, forbid_df = split_state_locks(empty)
    assert must_df.empty
    assert forbid_df.empty
