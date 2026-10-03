# SCQOS Domain Adapter SDK v1 — local prototype

The SDK orchestrates a domain adapter around the existing SCQOS database-action
decision path. The reference adapter pays a synthetic Vendor X $500 from a
$10,000 local balance under a $1,000 synthetic approval ceiling.

## Interfaces

| Interface | Responsibility |
| --- | --- |
| read_authoritative_state | Return an isolated snapshot of the domain store |
| normalize_proposal | Bind request, before state and expected after state |
| collect_authority | Obtain a typed authority object; never generate approval on execution |
| evaluate_domain_predicates | Validate exact request, source version, authority origin, scope and time |
| execute_consequence | Repeat predicates and consume authority atomically with the writer |
| verify_consequence | Compare independent store re-read to the bound expected state |

`execute_governed_transition` accepts an explicit trusted kernel callable.
The payment adapter's callable invokes `build_database_action_decision`, which
calls the existing `evaluate_transition_invariants`. It does not substitute a
parallel eight-invariant evaluator. The core, registry and installed boundary
are unchanged.

## Exact local commands

From the candidate checkout:

```bash
/home/jerry/grassrootsai-live-venv/bin/python -m pytest -q tests/test_scqos_domain_sdk.py tests/test_database_action_decision.py tests/test_scqos_transition_evaluator.py
/home/jerry/grassrootsai-live-venv/bin/python scripts/run_scqos_synthetic_payment_demo.py
```

The demo emits one JSON receipt per valid, unapproved, expired and stale-state
scenario. Valid execution debits 50,000 integer cents and records the payment;
the other scenarios leave the writer uninvoked. Currency arithmetic rejects
floating point amounts, booleans, zero and negative values.

## Evidence and decision semantics

A domain failure is recorded separately from kernel invariant failures. For
example, `domain_time` means the adapter rejected an expired synthetic approval;
it is not a claim that the kernel Time predicate implements approval expiry.
A domain failure before kernel invocation has a null kernel decision and empty
kernel results. The canonical executable eighth invariant is `consciousness`;
this SDK preserves it.

PERMIT records pre-write admission. It does not prove persistence or success.
Only a matching re-read yields VERIFIED_EFFECT. A nonmatching normal writer
return yields UNVERIFIED_EFFECT. An exception without a matching observation
yields UNKNOWN_OUTCOME. There is no automatic retry, and consumed approvals
cannot be replayed after a writer error. An observed matching effect after an
exception is recorded with the error rather than hiding it.

The store compares the entire aggregate and version, consumes an issued approval
ID and invokes its writer under one process-local lock. Pre-write competing
changes yield HOLD without invoking the writer. This is a prototype CAS contract;
a real adapter must implement the equivalent guarantee in its storage system.

## Limits

- Entirely synthetic, in-memory, process-local evidence and authority. No durable
  receipt store, human credential authentication, independent witness or bank API.
- Synthetic approvals are retained by the local store; caller-edited approval
  objects fail the origin check. This is lab integrity, not production signing.
- Uses the already installed database lab boundary by encoding a payment
  aggregate as its typed single-field mutation. It demonstrates reusable
  orchestration, not universal domain support or a new installed payment boundary.
- No AWS mutation, production runtime integration, real money or AFA integration.
- The writer is a trusted local adapter implementation. Python callers can bypass
  it; production protection requires an enforced exclusive writer boundary.
- A second unrelated adapter and provider-specific authority verification remain
  future work. These results cannot establish clinical or financial compliance.
