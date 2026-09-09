# DIKWP-PRAXIS-OS 2.0.0 · WORLDGATE

Created by Yucong Duan (段玉聪). Licensed under Apache-2.0.

[中文说明](README_CN.md) · [Complete original delivery](release/praxis_v2.zip) · [Publication record](PUBLICATION.md)

**Evidence-bound execution, outcome witnessing and governed adaptation.**

An agent's correct answer does not grant authority. A successful API response does not prove a real effect. A compensating action does not erase history. WorldGate makes these distinctions executable for one local resource adapter: `inventory.reserve`.

## Quick start

Python 3.10+ is declared; this build is tested on Python 3.13.5. The new kernel has **one direct dependency**, PyCA `cryptography` (tested 46.0.4); transitive/platform dependencies are not bundled. The preserved v1 runtime remains standard-library-only.

```bash
python -m pip install -r requirements.txt
python dist/praxis_v2.pyz demo --out my-first-run
python dist/praxis_v2.pyz replay my-first-run/runtime/verified-and-compensated/world.json --anchor my-first-run/runtime/verified-and-compensated/anchor.json --trust my-first-run/runtime/verified-and-compensated/trust.json
```

Open `web/praxis_v2.html` for a bilingual offline viewer. Import `summary.json` from a new run. The page makes no network requests and holds no signing keys. It is a viewer and unsigned request-draft helper, not the Python enforcement engine.

## What runs

* Preserve all v1 code: paired evaluation, 432 local reference executions, group-level statistics, imported judge audits, OTLP subset, trusted process bridge and HMAC local lifecycle. Use `legacy` before the old CLI command.
* Validate owner contracts, evaluator evidence, and matching reviewer/operator Ed25519 grants. Enforce distinct configured principals and unique public keys.
* Stage a proposed action, then recheck evidence, expiry, resource version and budgets inside the actual SQLite commit transaction.
* Keep effect, budget charge, receipt and audit append atomic. Retry by the same request ID/hash returns the previous effect instead of repeating it.
* Verify postconditions with a separately invokable, read-only observer. Halt for reconciliation when the world changed.
* Compensate only when the recorded poststate still matches. A later writer is never overwritten to fabricate a successful rollback.
* Exercise two local databases for unknown delivery outcomes; no blind retries after a lost response.
* Run a fixed e-process risk monitor, a finite eight-policy repair search, one-use holdout accounting, counterexample reduction and signed revocation feedback.

## Operator CLI

```bash
python dist/praxis_v2.pyz init --out local-sandbox
python dist/praxis_v2.pyz sign payload.json --key reviewer.key --key-id reviewed-key-id --out signed.json
python dist/praxis_v2.pyz contract signed_contract.json --db world.sqlite
python dist/praxis_v2.pyz evidence signed_evidence.json --db world.sqlite
python dist/praxis_v2.pyz grant matching_approvals.json --db world.sqlite
python dist/praxis_v2.pyz prepare signed_request.json --db world.sqlite
python dist/praxis_v2.pyz commit signed_request.json --db world.sqlite
python dist/praxis_v2.pyz observe --db world.sqlite --tenant local --action request-1 --key observer.key --key-id observer-key-id --out observation.json
python dist/praxis_v2.pyz attest observation.json --db world.sqlite
python dist/praxis_v2.pyz compensate signed_compensation.json --db world.sqlite
python dist/praxis_v2.pyz revoke signed_revocation.json --db world.sqlite
```

`init` creates a **local sandbox** with co-located keys for six roles and no grant. It is not separation between real people. Split key custody and retain the latest trust root/anchor separately before a team trial. Templates need your actual reviewed hashes, resources and current timestamps. No untrusted request may choose the host clock.

`sign` does not make an action valid: receiver-side scope, identity, expiry, budget and state checks still apply. Never run an untrusted agent with direct database access, signing keys or host administrator privileges.

## Legacy compatibility

```bash
python dist/praxis_v2.pyz legacy demo --out v1-reference
python dist/praxis_v2.pyz legacy replay v1-reference/experiment
```

The v1 source package is byte-identical to the supplied release. Its HMAC demo key remains an explicitly public synthetic fixture; it is never used for WorldGate Ed25519 authorization.

## Tests and release evidence

```bash
python tools/check.py
python tools/build_zipapp.py
```

The release retains raw test logs and actual outputs. `verification/upstream_lineage.json` records the source lineage. `outputs/reference/` includes 23 fault cases, a 24-way concurrency test, three delivery fault jobs, the finite repair search, three monitoring sequences, a separately authorized revocation loop and the v1 baseline. No private Ed25519 key is in the release.

## Boundaries

This is a local reference implementation, not a universal agent sandbox, distributed transaction manager, real payment service, production deployment controller, or certified safety system. Signatures prove possession of configured keys, not human identity, factual truth or execution of a remote binary. Evidence is a signed evaluator assertion with explicit scope. Database/OS administrators and the host clock remain trusted. Data files are plaintext. Risk-monitor assumptions and holdout budgets require operational governance. Read `docs/SECURITY_MODEL.md` before integration.

Prepared for Yucong Duan with AI-assisted engineering. Apache-2.0. Not an endorsement by the source article's speakers, companies or standards organizations. The original delivery predates this GitHub publication.
