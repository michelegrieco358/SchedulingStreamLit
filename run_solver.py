"""Esegue il caricamento dei dati e risolve il modello CP-SAT con logging del gap."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
import warnings
from typing import Optional

logging.getLogger("loader").setLevel(logging.ERROR)

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

    model, artifacts, context, bundle = build_solver_from_sources(
        args.config,
        args.data_dir,
    )

    # Diagnostica dimensione modello
    proto = model.Proto()
    print(f"--- Model stats ---")
    print(f"  Variables:    {len(proto.variables)}")
    print(f"  Constraints:  {len(proto.constraints)}")
    print(f"  assign_vars:  {len(artifacts.assign_vars)}")
    print(f"  gap_pairs:    {len(context.gap_pairs) if context.gap_pairs is not None else 0}")
    print(f"  employees:    {len(context.employees)}")
    print(f"  slots:        {len(context.slots)}")
    print(f"-------------------")

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = args.max_time
    solver.parameters.num_workers = 1
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
