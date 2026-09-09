# Deployment and migration

## Stage A: reproducible local lab

Install Python plus cryptography, run tools/check.py, run the full demo, replay a world against a separately retained public root, and inspect the logs. Import only synthetic/non-sensitive data. Verify the preserved legacy source hashes. Do not overwrite v1 artifacts or import its HMAC authorizations as WorldGate grants.

## Stage B: team-owned noncritical resource

Define one real resource and one reversible operation. Put the broker and DB in a service account inaccessible to the agent. Separate reviewer, operator and observer keys. Define real owner/evaluator identity enrolment, secret custody, clock controls, backup, retention, rate limits and incident reporting. No such external identity infrastructure is provisioned by this ZIP. Begin with dry proposals, not general shell or API access.

## Stage C: explicitly authorized small canary

Only after an operator approves the contract and evidence may a narrow live action be enabled by a new reviewed adapter. Predeclare scope, quotas, floor invariants, deadline, observation source, stop signals, status lookup and compensation. Exercise timeout-before-effect, response-lost-after-effect, concurrent writes, signer compromise, key revocation, stale evidence and unknown outcome cases. Archive an independent witness/anchor. Measure harm and error types separately from task success.

## Acceptance gates

All applicable local tests pass; unsupported operations reject; private keys are outside the agent; no customer data in public artifacts; resource action idempotency/status semantics are verified; independent rollback/compensation behavior is tested; disagreement and missing evidence have an owner; monitor family and holdout budget are fixed before looking at results; operators can revoke authority; actual negative results are retained.

## Explicitly absent

No production API, LLM vendor, browser automation, HSM, identity provider, general sandbox, OTel collector, distributed scheduler, real payment rail, automatic live rollout, hardware energy meter or universal policy solver. None is implied by `VERIFIED_LOCAL_EFFECT`.
