# Message protocol and SDK

Canonical encoding is the project JSON encoding (sorted keys, compact separators, UTF-8, no NaN, no duplicate keys), not a claimed RFC 8785 implementation. Ed25519 signs `DOMAIN || canonical({key_id,payload})`. The receiver loads public keys from its trust registry, not from the request.

Roles: owner signs the immutable contract; evaluator signs scoped evidence; reviewer and operator sign identical grant bodies; executor signs an action; observer signs an actual read-only snapshot. Reviewer, operator, executor and owner must be distinct configured principals. Public keys cannot be duplicated under aliases.

## State transition

`PREPARED -> COMMITTED_PENDING_OBSERVATION -> VERIFIED_LOCAL_EFFECT`

A changed snapshot produces `RECONCILIATION_REQUIRED`. A compensating inverse is allowed only from the exact recorded poststate; otherwise `COMPENSATION_CONFLICT`. Compensation retains history and increments revision. Revocation stops future actions; a retry of a completed action only returns its stored receipt.

## SDK

```python
from praxis_gate.common import load
from praxis_gate.kernel import WorldGate

gate = WorldGate('world.sqlite')  # trusted service process only
request = load('signed_request.json')
proposal = gate.apply('prepare', request)
receipt = gate.apply('commit', request)  # host clock supplied internally
assert receipt['state'] == 'COMMITTED_PENDING_OBSERVATION'
```

Run the `observe` CLI under a separate custodian with read-only access, then submit its signed result through `attest`. A true natural-person/organizational approval requires an external identity and custody process; the code alone does not create it.

## Evidence semantics

`case_groups` and `artifact_hash` describe an evaluator's assertion. They are not evidence that a random representative sample was obtained. The demonstration actually executes a 36-case local policy preflight and signs its digest; that finite result is not a population guarantee. Old order-summary evaluation must not authorize a new inventory reservation operation: mismatched operation contracts are rejected.

## Idempotency and atomicity

The key is `(tenant, action_id)`, bound to the entire request payload hash. Different content cannot reuse the ID. Effect, counters, receipt and event append commit in the same SQLite transaction. A crash injected before commit rolls them all back; after commit it loses only the response. These tests do not prove crash recovery under every hardware/filesystem failure. The separate delivery lab shows why this guarantee does not extend automatically to two services.

## Return and error handling

CLI writes structured JSON, uses exit code 2 on validation/authorization errors, and refuses existing output paths. Callers must not convert an error or UNKNOWN into a success. The Python `_fault` and `now` parameters exist for trusted deterministic tests only and are not accepted by the remote request schema or CLI.
