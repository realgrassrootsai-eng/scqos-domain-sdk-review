# Build a domain adapter

Copy `adapter_starter.py` and implement its six methods for your application. The starter deliberately raises NotImplementedError. Passed through the SDK it returns HOLD without invoking the kernel or writer; it is not a functioning adapter yet.

## Six operations

| Operation | Your implementation must supply |
|---|---|
| read_authoritative_state | A fresh authoritative snapshot, including a revision/version marker; return a copy. |
| normalize_proposal | Validate exact request types, calculate expected state, construct PreparedTransition and the exact kernel proposal; preserve the bound state objects. |
| collect_authority | Resolve authority against your trusted issuer/registry; caller-provided fields alone do not establish permission. |
| evaluate_domain_predicates | Return failure codes for scope, expiry, replay, proposal/state mismatch and application constraints; empty tuple only when all checks pass. |
| execute_consequence | Atomically repeat those checks against current state, consume approval and perform the mutation; reject with False before writer invocation if guards fail. |
| verify_consequence | Compare an independently observed result against the bound expected result. |

Bind approval to the exact normalized request, actor and scope, authoritative starting state/version, expected outcome, validity interval and unique approval identifier. Reject changed or unknown approval records. Track both consumed approvals and executed transition IDs where appropriate. Retain a revision even if state values return to earlier values.

## Execution boundary

The SDK calls your adapter through `execute_governed_transition(adapter, request, authority, kernel=trusted_kernel)`. The supplied kernel must return a TransitionReceipt for exactly `prepared.kernel_proposal` with the complete invariant chain. Never use a default-PERMIT kernel. Kernel evaluation precedes the attempted write; the adapter verifies its observed effect afterward.

Repeat freshness, authority, scope, expiry and replay guards within the same lock or database transaction as approval consumption and mutation. Call `mark_invoked()` immediately before invoking the actual writer, after guards pass. Return True for a normal write attempt and let observation establish the effect; do not claim successful persistence from the return value alone. A writer exception can leave an unknown outcome: preserve evidence and do not blindly retry.

Your integration must enforce an exclusive writer boundary: every relevant mutation must pass its checks. This Python interface does not enforce that boundary or prevent direct writes. The mathematical example's RLock covers one process only. Distributed/persistent enforcement needs a separate design and verification.

## Local setup and tests

Use Python 3.11 or newer with venv support. From this repository root, at the full commit you intend to assess:

```bash
python3 -m venv .adapter-venv
.adapter-venv/bin/python -m pip install --no-index --no-deps SCQOS-Domain-SDK-v0.1.0/scqos_domain_sdk_prototype-0.1.0-py3-none-any.whl
.adapter-venv/bin/python -m pip install pytest==9.1.1
.adapter-venv/bin/python -m pytest -q tests/test_domain_extensions.py
```

On Windows use `.adapter-venv\Scripts\python.exe` instead. Installing pytest needs network access unless dependencies are supplied locally. The installed SDK wheel has no runtime third-party dependency. No AWS credentials are needed for these tests. Tests also work from another current directory when given the absolute test-file path.

The tests cover all 154 combinations x=0..10, y=10-x and k=-1..12 against an independent arithmetic acceptance rule; approval tampering; missing authority; issuance and expiry endpoints; changed requests; replay; same values with a changed revision; state/expiry changes after kernel PERMIT; concurrent duplicate submission; invalid, HOLD and wrong-proposal kernel responses; and the unimplemented starter. Direct store assignments are test-fixture setup only.

These are maintainer tests, not independent certification. Mathematical predicates are adapter checks, distinct from kernel invariant results. The original wheel and source remain unchanged, and Nikolai's earlier reproduction does not cover these additions. After implementing a new adapter, exercise it with the reusable conformance runner described in the bundle README and add domain-specific tests.
