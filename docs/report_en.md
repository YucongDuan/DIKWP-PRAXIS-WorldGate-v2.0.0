# DIKWP-PRAXIS-OS 2.0.0
## WORLDGATE
### Evidence-bound execution, outcome witnessing and governed adaptation
Yucong Duan
Engineering research and executable reference release · 8 September 2026

This edition connects task evidence, scoped authority, resource state, budgets, observations and compensation into an executable protocol. It does not assume that a sufficiently capable model deserves unrestricted tools. Every governed operation must satisfy its declared conditions at the moment of execution.

**Three distinctions**
Passing an evaluation is not permission to act. A committed action is not an observed postcondition. Compensation is not erasure of the original event.

| Measured item | Result |
|---|---|
| Automated tests | 106 new + 115 preserved; 221 passed |
| Runtime fault cases | 23/23 expected outcomes; 185 events |
| Concurrent quota race | 24 requests, 8 workers; 1 effect, 23 denials |
| Bounded repair | 8 policies × 36 development cases; 36 reserved cases after selection |
| Preserved baseline | 432 local executions with unchanged v1 semantics |

This is an AI-assisted engineering release, not independent certification. “Implemented” means the named bounded module, not a universal platform guarantee. All reference data, role identities and approvals are synthetic. No live model API, payment rail or production platform was contacted.

Reading map: sections 1–2 compare versions; 3–8 specify execution and trust; 9–12 report inference, repair and experiments; 13–16 cover operation, deployment and sources.

---

# 1　Dimension shift: from judgment to control
Version 1 already included task contracts, a scoped read broker, trace auditing, a local release registry and outcome-led reopening. The comparison retains those capabilities rather than inventing a weak baseline. The baseline is the recovered source and its tests, not a commercial product reimplementation. [B1]

| Dimension | Actual v1 baseline | WORLDGATE addition |
|---|---|---|
| Assessment/action | Evaluation and local registry | Governed mutation of real local inventory |
| Permission timing | Toy read broker plus trace audit | Recheck at prepare and commit |
| Approval credential | Shared-key HMAC | Separate Ed25519 role keys |
| Evidence freshness | Versioned eligibility | Expiry/revocation blocks future commit |
| Concurrency | Fresh evaluation state | Version and quota checked atomically |
| Retry | Failure record retention | ID bound to full request; receipt reuse |
| Rollback | Registry-state rollback | Conditional inverse inventory operation |
| Completion | Declared postconditions | Read-only signed snapshot checked against actual state |

The core shift is from evidence as a report to evidence as one necessary input to a bounded action authorization. Passing evidence still does not issue a grant, and a grant still does not bypass execution-time state checks.

Only `inventory.reserve` performs business-state changes in this release. General enforcement over filesystems, browsers, cloud platforms, payment systems and arbitrary databases is not implemented.

---

# 2　Dimension shift: executable connections
| Dimension | Retained foundation | New connection and limitation |
|---|---|---|
| Uncertain delivery | No remote-effect protocol | Two local databases exercise status reconciliation; not a real network |
| Authenticity | Hash chain and recomputation | Signed anchor, pinned public root, fresh-world replay; not truth certification |
| Continuous monitoring | Fixed-sample bootstrap/Wilson | Predeclared e-process; original analyses remain |
| Missing outcomes | Explicit missing evidence | Stop at unresolved ordered prefix |
| Repair | Quarantined failure proposals | Eight predefined policies; not general model training |
| Counterexamples | Failure categories | Budgeted deletion-minimal reducer, not global minimum |
| Risk/authority | Local lifecycle rollback | Report → unsigned proposal → operator approval → revocation |
| Compatibility | 115 original tests | 15 upstream Python files unchanged, plus a new package |

The complete 16-row comparison in `docs/comparison.csv` maps each change to an implementation and an explicit boundary. Compatibility is exposed by the `legacy` command; old HMAC approvals are not silently converted into public-key grants.

“Disruptive” refers to changing the controlled object and decision granularity: from average release-time pass rates to evidence, permission, state, outcome and succession for each action. Transactions, digital signatures and the statistical foundations are established techniques. Their integration is the engineering contribution; the release does not claim to have invented those foundations. [S1–S4]

---

# 3　Six roles, distinct powers, one action chain
## Roles are not titles supplied by an agent
| Role | Signed object or responsibility |
|---|---|
| owner | Purpose, resources, floor invariant and per-action boundary |
| evaluator | Scoped evaluation evidence and validity interval |
| reviewer | Independent review signature over the proposed grant |
| operator | Identical execution approval; revocation and compensation |
| executor | Concrete action request, without review authority |
| observer | Actual poststate from a read-only database connection |

Reviewer, operator, executor and contract owner must be four distinct configured principals. A public key cannot be duplicated under aliases. This prevents simple credential aliasing; it does not establish that two private keys belong to two different natural persons. Identity enrolment and key custody remain organizational obligations. [S3]

```text
owner contract → evaluator evidence
                  ↓
reviewer + operator → finite grant
                  ↓
executor proposal → PREPARED
                  ↓  recheck under transaction
COMMITTED_PENDING_OBSERVATION
                  ↓  read-only observer
VERIFIED_LOCAL_EFFECT / RECONCILIATION_REQUIRED
```

Purpose definition, evidence judgment, action approval and outcome observation are separate powers. No arbitrary shell or network operation is exposed. The broker must sit at the resource permission boundary. Adding advisory prompts to an agent that still possesses administrator database credentials is not enforcement.

---

# 4　Compile a task into an unambiguous action contract
The contract fixes the operation, resource set, candidate hash, minimum remaining stock, per-action quantity and maximum lease duration. Evidence additionally binds the contract/candidate, evaluation scope, origin, case-group count, artifact hash and expiry. Reviewer and operator separately sign exactly the same grant body.

## Executable request shape
```json
{
  "kind": "action", "tenant": "local",
  "action_id": "request-001", "actor": "executor-person",
  "grant_id": "grant-001",
  "contract_hash": "<reviewed SHA-256>",
  "candidate_hash": "<reviewed SHA-256>",
  "operation": "inventory.reserve",
  "resource": "stock-a", "units": 3,
  "expected_revision": 0
}
```
The bracketed strings are explanatory placeholders, not valid hashes. The runtime rejects booleans masquerading as integers, fractional or negative quantities, extra instruction fields, unlisted operations, and tenant/candidate/contract/resource substitution. Signing an invalid payload does not make it eligible.

## Distinctions that remain mandatory
The candidate hash binds an approved assertion; this release does not attest which remote binary actually ran. The artifact hash references evaluation material; an evaluator signature does not make those facts true. An old order-summary evaluation cannot automatically authorize an inventory operation: mismatched operation contracts are rejected.

The real CLI derives time from the host. SDK test clocks and fault-injection parameters are trusted test-driver inputs, excluded from the signed action schema.

---

# 5　Atomic commit: checks and effects share one boundary
Prepare records the request and proposed before/after state. It does not consume stock or quota. Commit obtains a write transaction, then rechecks active authority, unrevoked evidence, lease freshness, resource revision, per-action/total quotas and the minimum-stock invariant. [S1–S2]

```text
BEGIN IMMEDIATE
  verify authority + evidence + time
  compare current state with prepared state
  verify quantity + remaining quota + floor
  update inventory and revision
  charge grant counters
  persist effect receipt and audit event
COMMIT
```

## Local invariants and proof sketch
Let stock be x, requested units u, floor m, consumed quota b and maximum B. Admission requires both x−u≥m and b+u≤B. The same trusted transaction serializes the checks and updates, so the next writer sees the new state, not an earlier balance.

Assuming transaction atomicity, trusted adapter code and trusted storage, induction over successful commits establishes: governed commits preserve the floor; counters do not exceed the grant; one tenant/request ID cannot produce a second inventory effect. This is not a proof covering arbitrary hardware failure, administrator tampering or cross-service transactions.

## Executed race
Twenty-four different requests prepare first, then eight workers contend for a one-call quota. Exactly one reaches COMMITTED_PENDING_OBSERVATION; 23 return GRANT_BUDGET_EXHAUSTED. Stock changes from 100 to 97. The system does not issue 24 passing labels and discover the budget race afterward.

---

# 6　Outcome witnessing: a success response is not the end
The effect receipt includes the request hash, candidate/evidence references, previous state, expected poststate and commit time. The state remains COMMITTED_PENDING_OBSERVATION. An observer reads actual state through a read-only connection and signs a record bound to the request and receipt; the broker then checks that snapshot against the current database.

| Observation | Outcome |
|---|---|
| Actual state matches the committed poststate | VERIFIED_LOCAL_EFFECT |
| A later write changed the state | RECONCILIATION_REQUIRED; suspend the grant |
| State changed after observation but before ingest | OBSERVER_SNAPSHOT_NOT_CURRENT |
| Executor signs its own success using the executor key | Observer-role verification rejects it |

The tests actually launch a separate CLI process using the observer key and a read-only database connection, then verify the result in the main process. This is stronger than trusting an agent's `success=true`, but it is not independent institutional, hardware or sensor certification.

## Do not confuse concurrency with malice
Stock first changes from 100 to 97; another valid action then changes it to 92. An observation for the first action no longer sees 97. The system requires reconciliation of the history and concurrency relation. It neither labels the first actor a liar nor overwrites the second action.

Signatures use a maintained cryptographic library, not a home-built algorithm. They identify a configured private-key holder; they do not establish that the observer is truthful. [S3]

---

# 7　Failure, unknown outcome and compensation differ
## Fault timing matters
An injected pre-commit fault rolls back stock, quota and receipt together. A lost response after commit leaves a real effect. Retrying the same request returns the stored receipt without another decrement. The demonstrations reopen the database and test both paths.

## Atomicity does not automatically cross a service boundary
A separate lab uses two real local SQLite databases as caller and provider. It is not a network connector, but deliberately preserves the gap between two commit boundaries.

| Scenario | Provider effect | Caller response |
|---|---|---|
| Response lost after reserving 7 | One durable effect | UNKNOWN; no blind retry; status query confirms |
| Success acknowledgment without execution | No effect record | No completion certificate; retry needs authorization review |
| Process stops before send | No effect record | Reconcile, then RETRY_AUTHORIZATION_REQUIRED |
| Status source unavailable | Unknown | Keep UNKNOWN rather than call it a failure |

Only one provider effect occurs in the reference run; stock goes from 100 to 93. HTTP 200 or similar acknowledgment text is not treated as an outcome witness.

## Compensation preserves later writers
Compensation executes only when the current complete state matches the original recorded poststate. It restores the quantity but increments the revision and preserves the old receipt. A later write produces COMPENSATION_CONFLICT. Quota is not refunded, preventing repeated undo from refreshing the call budget. No compensability guarantee is made for remote services, physical actions or irreversible operations.

---

# 8　Signatures, trust roots, replay and DIKWP responsibility
## What must be retained outside the imported package
An export includes a public-key registry and signed anchor, but a package carrying its own keys does not establish external origin. `replay --trust` accepts an independently retained root. Without it, the result reports self-contained signature integrity, not authenticated origin. Even with a pinned root, rollback of the whole database together with an old valid anchor needs an externally retained latest anchor to be detected.

## More than rehashing
Replay initializes a new temporary database from the initial resources and re-executes successful signed contracts, evidence registrations, grants, prepare/commit commands, observations, compensation and revocation. It compares each result hash and the final inventory, actions, quotas and evidence states. Truncating signed history and editing only final stock are both detected in the experiments.

Denial records retain only the input hash to reduce content exposure. The replay therefore does not claim to re-execute the denied original inputs. Nor does it rerun the original agent or observe the physical world again.

## Operational DIKWP mapping
D registers inputs, evidence and observations; I preserves denials, conflicts and revocation; K holds scoped effect receipts; W makes approved resource, budget and floor constraints change admission; P registers purposes and concrete actions. Edges contain actual source, target and generated content.

Twenty-five directed role routes are permitted, but only routes actually present in the reference events are claimed. Reverse execution establishes local state correspondence, not universal semantic, cognitive or empirical closure.

---

# 9　Continuous risk without post-hoc threshold shopping
The fixed-sample v1 analyses remain. The new monitor adds a scoped sequential procedure. Let group failures be Xg∈{0,1}. The null is that, conditional on the observed past, the next failure probability is at most p0. For predeclared q>p0:

```text
L_t(q) = product_g (q/p0)^Xg × ((1-q)/(1-p0))^(1-Xg)
E_t    = mean over the fixed alternative set of L_t(q)
alarm  = first t with E_t >= 1 / alpha_stream
alpha_stream = family_alpha / predeclared_family_size
```

If the true conditional probability pt≤p0, the one-step multiplier has conditional expectation 1+(pt−p0)(q−p0)/(p0(1−p0))≤1. Hence L and its fixed mixture E are nonnegative test supermartingales. Under those assumptions, Ville's bound controls threshold crossing at arbitrary stopping times. Predeclared streams receive an error-budget allocation and union-bound control. This is an application of established safe anytime-valid inference, not a newly invented statistical theorem. [S4]

The synthetic settings are p0=.05, q=[.1,.2,.4,.7], family_alpha=.05 and family_size=2, giving threshold 40. A stream with ten nonfailures followed by fifteen failures first alarms at group 15. An all-nonfailure stream yields only non-rejection, not a safety certificate.

If group 6 is unresolved, only groups 1–5 are processed; later fast outcomes cannot jump the gap. Configuration, ordering, groups, alternatives and family must be fixed before outcomes. Group labels do not establish population representativeness. A critical individual incident need not wait for statistical significance before suspension.

---

# 10　Governed repair without rewriting the exam
The release implements reproducible finite rule search, not a claim of autonomous model evolution. The inventory proposer has three Boolean rules: require strict integers, respect the stock floor, and ignore instructions embedded in source text. These produce eight candidate policies, each actually executed on 36 development cases.

The all-off baseline is correct on 15/36 development cases. The procedure first selects a policy satisfying all declared development assertions with the fewest enabled rules, persists that candidate hash in a one-use holdout ledger, and only then evaluates 36 cases generated with a different seed. The selected all-on policy is correct on 36/36 reserved cases in this run.

| Control | Executed behavior |
|---|---|
| Candidate generation | Eight preimplemented combinations, no arbitrary code |
| Selection | Development data only |
| Holdout consumption | Candidate and data hashes persisted before evaluation |
| Another attempt | Same repair family is rejected on reuse |
| Deployment | No grant issuance or production policy replacement |

The holdout remains public synthetic data. A local ledger cannot prevent an administrator copying or deleting its database. It prevents silent reuse in the governed workflow; it is not a secret-exam system against a malicious administrator.

## Reduce a large failure to a useful counterexample
A second module deletes input items within a query budget while preserving failure. Four orders reduce to one cancelled order of amount 11, sufficient to falsify a summation rule that ignores cancellation. This is deletion-minimal under the given predicate, not the globally smallest counterexample across every representation.

---

# 11　Measured results, not an invented frontier leaderboard
| Experiment | Executed result |
|---|---|
| New regression tests | 106/106 passed |
| Preserved tests | 115/115 passed; 15 upstream source files unchanged |
| v1 reference | 24 groups × 3 repeats × 2 arms × 3 carriers = 432 runs |
| Runtime fault suite | 23 expected outcomes, 185 events |
| Quota concurrency | 1 inventory effect + 23 quota denials |
| Separate observation | Read-only function and separately launched CLI tested |
| Delivery ambiguity | 3 jobs; only 1 actual provider effect |
| Repair search | 288 development + 36 reserved-case executions |
| Sequential monitoring | 3 explicitly synthetic input streams |

The two safe v1 carriers retain 100% ON output correctness; the unsafe carrier also has 100% but is blocked by authority checks. These results are retained, not relabelled as a performance improvement over GPT, Claude or a commercial evaluation platform.

## How a finding affects future authority
In an additional feedback demonstration, a risk-monitor result creates an unsigned revocation proposal. A separate synthetic operator role signs it. The kernel revokes the target evidence and derived grant, and the next inventory request is denied. Local authority actually changes, but no natural-person approval or real production incident is implied.

This feedback demonstration is separate from the 23 runtime cases. Reusing synthetic monitoring inputs is not additional independent statistical sampling. Results are locatable under `outputs/reference/`. Multiple assertions inside a test are not counted as multiple test cases.

---

# 12　Fault catalogue and falsification conditions
The 23 cases are regression tests for declared controls, not an estimate of coverage against every possible attack.

| Fault class | Observed boundary and falsifier |
|---|---|
| Signed payload altered | BAD_SIGNATURE; acceptance would falsify the check |
| Tenant/candidate/resource substituted | Reject; cross-scope effect would be a failure |
| Negative, Boolean, fractional or instruction-bearing input | Type/field rejection; silent coercion would fail |
| Expiry/revocation after prepare | Commit rejects; stale authority must not execute |
| State changes between read and write | WORLD_CHANGED; overwriting the newer state would fail |
| Crash before commit | Full rollback; partial stock/quota change would fail |
| Reply lost after commit | Reuse receipt; a second effect would fail |
| Compensation after a later write | Stop on conflict; do not overwrite the later actor |
| Concurrent one-call quota | At most one governed effect |
| Truncated signed history or edited final stock | Verification or replay fails |

## Counterexamples not excluded by this release
An untrusted agent retaining direct DB or administrator privileges can bypass the broker. A false evaluator statement remains false after signing. An observer reading a jointly corrupted data source does not become an independent reality witness merely by using a separate key. A wholesale rollback to an older valid database and signed anchor cannot be recognized without an externally retained newer anchor.

These are deployment admission conditions, not disclaimers followed by a claim of complete safety. When a critical assumption fails, the operator must narrow scope or stop live integration.

---

# 13　From download to the first real local run
## Shortest path
```bash
python -m pip install -r requirements.txt
python dist/praxis_v2.pyz demo --out first-run
python tools/check.py
```
The new kernel requires `cryptography`. This build was actually tested on Python 3.13.5, SQLite 3.46.1 and cryptography 46.0.4. Python 3.10+ is the declared support range; a CI matrix is supplied, but remote CI and the other Python versions were not executed in this session.

## Check a recorded world
```bash
python dist/praxis_v2.pyz replay   first-run/runtime/verified-and-compensated/world.json   --anchor first-run/runtime/verified-and-compensated/anchor.json   --trust first-run/runtime/verified-and-compensated/trust.json
```
The demo distributes its public root with the transcript to support reproduction. Real origin verification must use a root and latest anchor retained independently beforehand, not merely the claims in a newly downloaded package.

## Minimal SDK in a trusted service
```python
from praxis_gate.common import load
from praxis_gate.kernel import WorldGate

gate = WorldGate("world.sqlite")
request = load("signed_request.json")
proposal = gate.apply("prepare", request)
receipt = gate.apply("commit", request)
```
The observer then runs `observe`, and the service ingests it with `attest`. The browser viewer is not the enforcement kernel and does not create signatures. `init` creates a local sandbox, six key pairs and a template; it issues no grant.

---

# 14　Deployment: control one resource before adding adapters
## Stage A: reproduce locally
Run the tests and references, check source lineage, and deliberately alter requests, evidence, permissions, state and receipts. Confirm that failures cannot disappear behind retries or averages. Use only synthetic or authorized nonsensitive inputs.

## Stage B: a team-owned noncritical resource
Choose one resource actually controlled by the team and one compensable operation. Run the broker, keys and database under a service account unavailable to the agent. Establish real identity and custody procedures for owner, reviewer, operator and observer. Define trusted time, retention, privacy, alerts and responsibility for reconciliation.

## Stage C: a bounded canary
Begin with proposals that have no business side effects, then obtain named operator approval for a small quota. A new adapter must define idempotency keys, status lookup, scope, observation source, transaction boundary, compensation preconditions, timeout states, data handling and stopping. An API is not sufficient evidence that safe integration is available.

## Initial team use cases
Internal stock/quota reservation; test-environment configuration changes; publication of explicitly versioned document indexes; auditable data corrections. Only stock reservation is implemented here. The other three are adapter design directions, not shipped integrations.

## Admission evidence
Operators can revoke future authority; executors cannot rewrite approvals; observers do not use the executor's success prose as sole evidence; duplicates do not repeat effects; compensation does not overwrite later writers; failures and unmeasured outcomes have an actual owner. Beyond every positive score, retain an executable path that can say no.

---

# 15　Remaining boundaries and version responsibility
| Topic | Actual status |
|---|---|
| Business effect | Local SQLite reservation and conditional compensation |
| Cryptography | Maintained Ed25519 library; no homemade fallback |
| Human identity, HSM, key rotation | External governance or future integration |
| Untrusted-code sandbox | Not supplied; the legacy trusted-process bridge is not a sandbox |
| Live model/Judge APIs | Not called; imported v1 judge audits remain |
| Production network, payments, distributed scheduling | Not implemented |
| Unlimited self-learning or arbitrary prompt rewriting | Not implemented; only finite policy search |
| Hardware energy and population risk | Not measured |
| Universal correctness, safety or consciousness | Not established by this release |

Local data and keys generated by `init` are plaintext. POSIX file permissions are not full key management; other systems require suitable ACLs. Hash/signature checks do not replace confidentiality, rate limiting, backups or identity enrolment. SQLite transaction and connection-close semantics follow its documented interface, while the host, filesystem and DB remain trusted. [S5]

Source, tests, reports, observations and verification manifests jointly define the release. Changes to adapters, permissions, inference settings or evidence interpretation require a successor version and fresh tests, not merely a new README version label.

GitHub workflow files are supplied but were not executed remotely; no account publication occurred. Code and original documentation use Apache-2.0. Underlying third-party research retains its attribution. This report is not endorsement by the source article's authors, SQLite, PyCA or the statistical paper's authors.

---

# 16　Sources, verification and artifact index
[B1] DIKWP-PRAXIS-OS 1.0.0 source archive supplied in this conversation. Original archive SHA-256:
9bcbb748b3ca27a1a62128c8107f0593a7a8f272fab32a71811469edf3d26abd
Per-file inheritance is recorded in verification/upstream_lineage.json.

[S1] SQLite. Transaction.
https://www.sqlite.org/lang_transaction.html

[S2] SQLite. Isolation.
https://www.sqlite.org/isolation.html

[S3] PyCA cryptography. Ed25519 signing.
https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/

[S4] Ramdas, A., Grünwald, P., Vovk, V., Shafer, G. Game-theoretic statistics and safe anytime-valid inference. Statistical Science, 38(4), 576–601, 2023. DOI: 10.1214/23-STS894.
https://arxiv.org/abs/2210.01948

[S5] Python documentation. sqlite3.
https://docs.python.org/3/library/sqlite3.html

Web sources checked on 8 September 2026. They support specific technical foundations, not compliance or safety certification. The supplied background article remains a problem source; its missing diagram was not reconstructed as if it were the authors' actual architecture.

## Artifact index
README.md / README_CN.md: start and boundaries. docs/comparison.csv: 16-row comparison. docs/PROTOCOL.md: protocol and SDK. docs/SECURITY_MODEL.md: trusted base. docs/STATISTICS.md: monitoring assumptions. outputs/reference/: executed results and public-key transcripts. verification/: tests, source lineage and release checks.

Check three different things: whether the code runs, whether evidence supports the conclusion, and whether the conclusion stays within its authorized scope. None substitutes for the others.
