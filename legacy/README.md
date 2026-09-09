# DIKWP-PRAXIS-OS 1.0.0

**Evidence-to-Outcome Agent Assurance**

A local-first, executable reference system that connects agent evaluation to task contracts, authority, provenance, uncertainty, controlled release review and outcome-led reopening. It extends the *Agent Evaluation Guide* supplied by the project requester; it does **not** claim measured superiority over Langfuse, MLflow, commercial carriers or frontier models.

## Start in one command

Python 3.10+; no third-party runtime dependencies.

```bash
python dist/praxis.pyz demo --out my-first-run
python dist/praxis.pyz replay my-first-run/experiment
```

Open `web/praxis.html` to inspect the bundled demonstration, or import the generated `dashboard.json`. The HTML is an offline **viewer**, not a replacement execution engine. It makes no network requests and uses no persistent browser storage.

## What actually runs

Two independent local implementations (Python iteration and SQLite queries) execute an active-order summary task. A third deliberately unsafe fixture returns the right answer while recording a forbidden side effect in its **in-memory synthetic environment**. The harness pairs ON/OFF runs by case and trial, starts each run with fresh local state and records every completed/failed attempt. No actual customer orders, money, commercial model or external service is involved.

Default demo: 24 declared case groups × 3 repeats × 2 arms × 3 carriers = 432 executions. The group labels are a synthetic design, not evidence of population independence. Case-group bootstrap results demonstrate computation, not market or frontier-model performance.

## Capabilities

- Strict JSON, versioned contracts, declarative output assertions and frozen dataset manifests.
- Exact cross-split duplicate and declared-group leakage checks.
- Observable trace DAG validation; scoped tools, expiry, call budgets and memory lineage.
- Separate output quality, authority, memory, privacy, resource and outcome verdicts.
- Paired provenance-group bootstrap and Wilson intervals, with explicit estimands and limitations.
- Imported judge calibration: confusion, abstention, error intervals, Brier, visible panel disagreement.
- Sampling audit: unweighted result vs an inverse-inclusion-probability ratio; no invented population CI.
- Metadata-minimal OTLP/JSON subset importer; hidden chain-of-thought and raw prompt capture are excluded from trace attributes.
- Opt-in trusted subprocess JSON bridge with wall-clock timeout and output caps. **Not a security sandbox.**
- Source correction propagation and quarantined badcase proposals; no automatic test-label rewriting.
- SQLite local registry with artifact-bound HMAC approvals, role separation, expiry, replay protection and outcome-led rollback of **local registry state**.
- Recorded-observation recomputation, hash-chain verification and a bilingual comparison report.

## CLI

```bash
python dist/praxis.pyz inspect
python dist/praxis.pyz init --out my-project
python dist/praxis.pyz run my-project/project.json --out run-001
python dist/praxis.pyz audit project.json runs.jsonl --out imported-run
python dist/praxis.pyz judge examples/judge.json --out judge-report.json
python dist/praxis.pyz import-otel examples/otlp.json --out trace-import.json
python dist/praxis.pyz sampling sampling-rows.json --out sampling-report.json
python dist/praxis.pyz correct graph.json correction.json --out successor.json
```

Outputs are not silently overwritten. Use a fresh directory for every run. `project.json` is the executable source of truth; generated `skill.md`, `contract.json`, `cases.jsonl` and `eval.json` are starter views and are not silently synchronized.

## Real worker integration

Prepare a reviewed local program that reads one JSON request on stdin and returns one JSON response on stdout. The request contains case inputs and task authority, **not expected answers**. Configure absolute argv and opt in explicitly:

```bash
python tools/make_worker_config.py --out worker.json
python dist/praxis.pyz run examples/worker_project.json --worker worker.json --trust-worker --out worker-run
```

The example worker only executes the toy task. Replace it with your own authorized agent integration. PRAXIS does not contact OpenAI/Anthropic or any other model API. Remote model IDs, API permissions, terms, data handling, cost and isolation remain the integrator's responsibility. Never run untrusted generated code through this bridge on a privileged host.

## Controlled release registry

See `docs/DEPLOYMENT.md`. Registration from the CLI first recomputes an assessment bundle. A high evaluation score never authorizes external deployment. Shared-key holders are the local trust root; the HMAC does not prove a natural person's identity or institutional approval. Source bodies and local fixtures are plaintext unless the operator adds encrypted storage.

## Tests and replay

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
python dist/praxis.pyz replay outputs/reference/experiment
```

A fresh run's latency is measured and may differ. Replay recomputes decisions over **recorded** observations under the same implementation/environment fingerprint; it is not a new external experiment.

## Boundaries

Not implemented: distributed scheduling, live LLM judges or prompt optimization, production collectors, semantic near-duplicate detection, signed external attestations, provider integrations, hardware energy measurement, real rollouts or global safety certification. The `unsafe` fixture is intentionally unsafe only inside an in-memory demonstration. Never interpret its correct answer as authorization.

The comparison matrix distinguishes implemented modules, partial integrations and source gaps. The source's unsupported survey statistics, vendor rankings and fixed sample-count advice are not runtime parameters. Its missing six-layer figure has not been reconstructed by guesswork.

Original code and documentation: Apache-2.0. Third-party materials retain their original rights. Prepared for Yucong Duan with AI-assisted engineering; no endorsement from the attachment's speakers or vendors.
