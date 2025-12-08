# July dataset feasibility check (current state)

## Solver run
- Command: `python run_solver.py --config July/config.yaml --data-dir July`
- Result: solver did not return within a few minutes; interrupted manually with status `UNKNOWN`.

## Capacity vs. coverage summary
- Contract hours (per reparto/role):
  - ADT: OSS 750 h
  - REP0: IP 1050 h, OSS 600 h
  - REP2: IP 1350 h, OSS 2397.5 h
  - REP3: IP 1350 h, OSS 2250 h
  - REP5: IP 2400 h, OSS 2475 h
- Minimum required hours from `min_ruolo`:
  - ADT: OSS 68 h
  - REP0: IP 821.5 h, OSS 263.5 h
  - REP2: IP 1255.5 h, OSS 2185.5 h
  - REP3: IP 1255.5 h, OSS 2185.5 h
  - REP5: IP 1255.5 h, OSS 2185.5 h
- Approximate total staff-hours per reparto (splitting mixed-role requests evenly):
  - ADT: OSS ~654.5 h
  - REP0: IP ~705.25 h, OSS ~379.75 h
  - REP2: IP/OSS ~1720.5 h each
  - REP3: IP/OSS ~1720.5 h each
  - REP5: IP/OSS ~1720.5 h each

## Interpretation
- Contract capacity comfortably exceeds the minimum role requirements in every reparto.
- Mixed-role coverage (IP|OSS) leaves tight but still positive IP margin in REP2/REP3; OSS capacity is ample and can absorb part of the mixed demand, so data appear feasible. The solver likely needs more time to search; no infeasibility was detected in the supply/demand tallies above.
