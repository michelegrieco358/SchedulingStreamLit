"""Esporta in CSV lo stato giornaliero assegnato a ogni dipendente."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ortools.sat.python import cp_model

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.solve_service import _build_state_table
from src.solver import build_solver_from_sources


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Risolvi il modello di scheduling e salva per ogni dipendente lo stato giornaliero "
            "(M, P, N, SN, R, F, ...)."
        )
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Percorso al file di configurazione YAML (default: config.yaml).",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="Directory che contiene i CSV di input (default: data).",
    )
    parser.add_argument(
        "--output",
        default="states.csv",
        help="Percorso del file CSV di output (default: states.csv).",
    )
    parser.add_argument(
        "--time-limit",
        type=float,
        default=None,
        help="Limite di tempo in secondi per CP-SAT (opzionale).",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    model, artifacts, _, bundle = build_solver_from_sources(
        args.config,
        args.data_dir,
    )

    solver = cp_model.CpSolver()
    if args.time_limit is not None and args.time_limit > 0:
        solver.parameters.max_time_in_seconds = args.time_limit

    status = solver.Solve(model)
    status_name = solver.StatusName(status)
    print(f"Solver status: {status_name}")

    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return 1

    df = _build_state_table(solver, artifacts, bundle)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)

    print(f"Stati esportati in: {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
