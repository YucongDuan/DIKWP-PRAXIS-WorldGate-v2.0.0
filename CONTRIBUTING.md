# Contributing

Submit focused changes with an explicit threat model, allowed operation, deterministic unit tests and new negative fixtures. Never change test labels merely to pass a candidate. Preserve failures, uncertainty and source lineage. Proposed new adapters need observation, idempotency, compensation and trusted-clock contracts. Do not include real secrets or customer records. Keep the legacy package unchanged unless a separately reviewed migration is explicitly documented. Benchmarks must identify synthetic data, grouping, missingness and the true comparison baseline.
