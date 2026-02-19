"""Esegue il caricamento dei dati e risolve il modello CP-SAT con logging del gap."""

from __future__ import annotations

import argparse
from pathlib import Path
import warnings
from typing import Optional

from ortools.sat.python import cp_model

from src.objective_report import (
    compute_objective_breakdown,
    write_objective_breakdown_report,
)
from src.solver import build_solver_from_sources


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

    model, artifacts, context, bundle = build_solver_from_sources(
        args.config,
        args.data_dir,
        selected_departments=selected_departments or None,
    )

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.max_time
    if args.seed is not None:
        solver.parameters.random_seed = int(args.seed)
    if args.num_workers is not None:
        solver.parameters.num_search_workers = int(args.num_workers)
    callback = GapLoggingCallback()

    status = solver.SolveWithSolutionCallback(model, callback)

    print("Solver status:", solver.StatusName(status))
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
