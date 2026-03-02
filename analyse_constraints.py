from src.solver import build_solver_from_sources
model, artifacts, _, _ = build_solver_from_sources('config.yaml', 'data_fake_month')
proto = model.Proto()
count = 0
for i, ct in enumerate(proto.constraints):
    # Prefer oneof inspection for cross-version compatibility on protobuf objects.
    linear = None
    if hasattr(ct, "WhichOneof"):
        try:
            if ct.WhichOneof("constraint") == "linear":
                linear = ct.linear
        except Exception:
            linear = None
    if linear is None and hasattr(ct, "HasField"):
        try:
            if ct.HasField("linear"):
                linear = ct.linear
        except Exception:
            linear = None
    if linear is None:
        continue

    domain = list(linear.domain)
    if domain and domain[-1] == -1:
        print('idx', i, 'vars', list(linear.vars), 'coeffs', list(linear.coeffs), 'domain', domain)
        count += 1
        if count >= 5:
            break
