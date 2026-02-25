"""Esegue il caricamento dei dati e risolve il modello CP-SAT con logging del gap."""

from __future__ import annotations

import argparse
from pathlib import Path
import warnings
from typing import Optional

from ortools.sat.python import cp_model

from src.diagnostics import (
    build_infeasibility_summary,
    write_infeasibility_summary_report,
)
from src.objective_report import (
    compute_objective_breakdown,
    write_objective_breakdown_report,
)
from src.solver import build_solver_from_sources
from src.warm_start import (
    WarmStartError,
    apply_slot_warm_start_hints,
    load_slot_warm_start,
)


class GapLoggingCallback(cp_model.CpSolverSolutionCallback):
    """Stampa il gap corrente solo quando viene trovata una nuova soluzione."""

    def __init__(self) -> None:
        super().__init__()
        self._last_objective: Optional[float] = None

    def OnSolutionCallback(self) -> None:  # pragma: no cover - runtime callback
        objective = self.ObjectiveValue()
        bound = self.BestObjectiveBound()

        if self._last_objective is not None and objective == self._last_objective:
            return

        self._last_objective = objective
        if objective == bound:
            gap = 0.0
        elif objective != 0:
            gap = abs(objective - bound) / abs(objective)
        else:
            gap = float("inf")

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

    model, artifacts, context, bundle = build_solver_from_sources(
        args.config,
        args.data_dir,
        selected_departments=selected_departments or None,
        stability_enabled=stability_override,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.max_time
    if args.seed is not None:
        solver.parameters.random_seed = int(args.seed)
    if args.num_workers is not None:
        solver.parameters.num_search_workers = int(args.num_workers)

    if str(args.warm_start_file).strip():
        try:
            warm_df = load_slot_warm_start(args.warm_start_file)
            stats = apply_slot_warm_start_hints(
                model,
                artifacts.assign_vars,
                bundle,
                warm_df,
                strict=bool(args.warm_start_strict),
            )
        except WarmStartError as exc:
            raise SystemExit(f"Errore warm start: {exc}") from exc

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

    callback = GapLoggingCallback()
    if hasattr(solver, "SolveWithSolutionCallback"):
        status = solver.SolveWithSolutionCallback(model, callback)
    else:  # compatibilità con versioni OR-Tools più vecchie
        status = solver.Solve(model, callback)

    print("Solver status:", solver.StatusName(status))
    if status == cp_model.INFEASIBLE:
        summary = build_infeasibility_summary(context)
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
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return

    print("Objective value:", solver.ObjectiveValue())
    print("Assegnazioni candidate:", len(artifacts.assign_vars))
    print("Dipendenti considerati:", len(context.employees))

    breakdown = compute_objective_breakdown(solver, artifacts)
    report_path = Path("objective_breakdown.txt")
    write_objective_breakdown_report(breakdown, report_path)
    print(f"Report funzione obiettivo salvato in: {report_path}")


if __name__ == "__main__":
    main()
