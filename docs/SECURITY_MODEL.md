# Security model and explicit non-goals

## Trusted base

The enforcement process, SQLite database and OS permissions, trusted host clock, configured public-role registry, PyCA cryptography, reviewed adapter implementation and authorized key custodians. The observer may run as a separate process with read-only DB access. It still shares the host/data source in this release; it is not an independent institution or hardware witness.

## Adversaries covered within this base

Unsigned or tampered requests; role/tenant mismatch; resource/candidate/contract substitution; stale or revoked leases; quantity/type escalation; duplicate IDs; concurrent budget attempts; changed preconditions; lost replies; false success acknowledgments in the local provider fixture; stale observations; blind compensation; modified history relative to a pinned anchor; reuse of a governed local holdout.

## Not covered

An attacker with database or host administrator access; compromised signing keys; colluding custodians; a malicious evaluator signing false evidence; a compromised physical sensor; false identity enrolment; untrusted clock input; rollback of the entire DB plus an old valid signed anchor; unknown browser/LLM vulnerabilities; general DLP; denial-of-service; confidentiality of local plaintext; secure HSM or key rotation; production API authentication/TLS; arbitrary remote side effects.

## Mandatory integration rules

Keep the agent outside the resource trust boundary. Give it only a constrained request interface, not database credentials or private approval keys. The broker must derive the clock itself. Pin public trust outside the imported artifact. Keep a newer independent audit anchor. Never interpret HMAC or Ed25519 as identity proof. The signed candidate hash binds an assertion, not remote execution attestation. A signed evaluator report must remain scoped and auditable; this kernel cannot infer whether its source facts are true.

For a new adapter, define resource identifiers, atomicity boundary, observation source, idempotency scope, status lookup, conflict handling, compensation preconditions, privacy policy, quota and approval roles. Without reliable status lookup or idempotency, an ambiguous outcome must remain UNKNOWN and require reconciliation. Do not promise global exactly-once semantics.

## Demonstration keys

All reference WorldGate private keys are ephemeral and are discarded after producing public trust and signed transcripts. `init` writes plaintext local keys with exclusive creation and POSIX mode 0600 when supported. Windows requires appropriate ACLs. Its co-located keys are for setup, not an independent review organization. Do not use legacy v1 public HMAC fixture strings in deployment.

## Disclosure

No repository security inbox is configured by this release. Before public hosting, the maintainer must set a real reporting contact, supported-version policy, dependency update policy and incident process. Do not email raw secrets, full private conversations or customer payloads in a bug report.
