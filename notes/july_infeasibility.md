# July solver infeasibility analysis

- The July configuration enforces a hard monthly balance band of ±36 hours around each employee’s contract hours (`max_balance_delta_month_h`).【F:July/config.yaml†L35-L58】【F:src/model.py†L1888-L1903】
- Coverage for July defines demands only for roles IP and OSS; no other roles appear in the coverage tables, so those employees get zero schedulable shifts.【F:July/coverage_roles.csv†L1-L8】
- Employees in roles outside IP/OSS still carry about 16 379.26 contract hours for July, which the balance constraint forces to be scheduled even though there are no corresponding coverage slots.【d3878c†L1-L2】

Because those non-IP/OSS employees cannot be assigned to any coverage slot, the balance constraint alone makes the model infeasible even after expanding the IP/OSS workforce.
