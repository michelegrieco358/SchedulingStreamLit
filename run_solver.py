"""Esegue il caricamento dei dati e risolve il modello CP-SAT con logging del gap."""

from __future__ import annotations

import argparse
from pathlib import Path
import warnings
from typing import Optional

from ortools.sat.python import cp_model

from src.diagnostics import write_infeasibility_summary_report
from src.objective_report import write_objective_breakdown_report
from src.solve_service import solve_schedule
from src.warm_start import WarmStartError, load_slot_warm_start


class GapLoggingCallback(cp_model.CpSolverSolutionCallback):
    """Stampa il gap corrente solo quando viene trovata una nuova soluzione."""

    def __init__(self) -> None:
        super().__init__()
        self._last_objective: Optional[float] = None

    def OnSolutionCallback(self) -> None:  # pragma: no cover - runtime callback
        objective = self.ObjectiveValue()
        bound = self.BestObjectiveBound()

        if self._last_objective is not None and abs(objective - self._last_objective) < 1e-9:
            return

        self._last_objective = objective
        denom = max(1.0, abs(objective))
        gap = abs(objective - bound) / denom

        print(
            f"Nuova soluzione: objective={objective:.6g}  bound={bound:.6g}  gap={gap:.4%}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Risolvi il modello CP-SAT caricando dati e config specificati."
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Percorso al file di configurazione YAML (default: config.yaml).",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory dei CSV di input (default: data).",
    )
    parser.add_argument(
        "--max-time",
        type=float,
        default=600,
        help="Tempo massimo in secondi per il solver CP-SAT (default: 600).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Seed random per CP-SAT (default: non impostato).",
    )
    parser.add_argument(
        "--num-workers",
        type=int,
        default=None,
        help="Numero di worker CP-SAT (default: comportamento OR-Tools).",
    )
    parser.add_argument(
        "--departments",
        default="",
        help="Lista reparti separati da virgola da includere nella schedulazione (default: tutti).",
    )
    parser.add_argument(
        "--warm-start-file",
        default="",
        help="CSV opzionale con colonne employee_id,slot_id da usare come warm start.",
    )
    parser.add_argument(
        "--warm-start-strict",
        action="store_true",
        help="Se attivo, fallisce quando il warm start contiene record invalidi.",
    )
    parser.add_argument(
        "--stability",
        choices=("auto", "on", "off"),
        default="auto",
        help=(
            "Controllo stabilita' preassegnazioni: "
            "'auto' usa config, 'on' forza attivo, 'off' forza disattivo."
        ),
    )
    args = parser.parse_args()

    # Ignora l'avviso informativo sui locks mancanti, utile in ambiente POC.
    warnings.filterwarnings(
        "ignore",
        message=r"locks\.csv non trovato: caricati 0 record da locks\.csv",
        category=UserWarning,
    )
    warnings.filterwarnings(
        "ignore",
        message=r"locks\.csv: caricati \d+ record",
        category=UserWarning,
    )

    selected_departments = [
        part.strip() for part in str(args.departments).split(",") if part.strip()
    ]

    stability_override: bool | None
    if args.stability == "on":
        stability_override = True
    elif args.stability == "off":
        stability_override = False
    else:
        stability_override = None

    warm_df = None
    if str(args.warm_start_file).strip():
        try:
            warm_df = load_slot_warm_start(args.warm_start_file)
        except WarmStartError as exc:
            raise SystemExit(f"Errore warm start: {exc}") from exc

    callback = GapLoggingCallback()
    result = solve_schedule(
        args.config,
        args.data_dir,
        selected_departments=selected_departments or None,
        stability_enabled=stability_override,
        max_time_s=args.max_time,
        seed=args.seed,
        num_workers=args.num_workers,
        warm_start_df=warm_df,
        warm_start_strict=bool(args.warm_start_strict),
        solution_callback=callback,
    )

    if result.warm_start_stats is not None:
        stats = result.warm_start_stats
        print(
            "Warm start hints: "
            f"read={stats.rows_read} "
            f"clean={stats.rows_after_cleanup} "
            f"applied={stats.hints_applied} "
            f"unknown_employee={stats.unknown_employees} "
            f"unknown_slot={stats.unknown_slots} "
            f"ineligible_pair={stats.ineligible_pairs} "
            f"duplicates={stats.duplicate_pairs}"
        )

    print("Solver status:", result.status_name)
    if result.status_code == cp_model.INFEASIBLE:
        summary = result.infeasibility_summary or {"top_causes": []}
        print("Diagnosi infeasibilita':")
        for idx, cause in enumerate(summary.get("top_causes", []), start=1):
            title = str(cause.get("title", "")).strip()
            evidence = str(cause.get("evidence", "")).strip()
            hint = str(cause.get("hint", "")).strip()
            print(f"  {idx}. {title}")
            if evidence:
                print(f"     Evidenza: {evidence}")
            if hint:
                print(f"     Suggerimento: {hint}")
        diagnostics_path = Path("infeasibility_diagnostics.txt")
        write_infeasibility_summary_report(summary, diagnostics_path)
        print(f"Report diagnosi infeasibilita' salvato in: {diagnostics_path}")
    if result.status_code not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return

    print("Objective value:", result.objective_value)
    print("Assegnazioni candidate:", len(result.artifacts.assign_vars))
    print("Dipendenti considerati:", len(result.context.employees))

    if result.objective_breakdown is None:
        return
    report_path = Path("objective_breakdown.txt")
    write_objective_breakdown_report(result.objective_breakdown, report_path)
    print(f"Report funzione obiettivo salvato in: {report_path}")


if __name__ == "__main__":
    main()
