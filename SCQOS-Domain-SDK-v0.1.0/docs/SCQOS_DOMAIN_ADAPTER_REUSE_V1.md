# Two-domain SDK reuse proof — local prototype

## Implemented

The payment adapter and an independent deployment-state adapter use the same
unchanged `execute_governed_transition`, prepared-transition contract and
receipt format. Both call the existing SCQOS database-action decision path and
real eight-invariant evaluator. No SDK, kernel, registry or payment-adapter edits
were needed for the second domain.

| Element | Payment | Deployment state |
| --- | --- | --- |
| Request | Payment ID, vendor, integer cents, actor | Deployment ID, service, environment, immutable image digest, actor |
| Before state | Balance, version, payment records | Service, environment, current image, generation |
| Expected consequence | Debit and recorded payment | Image replacement and generation increment |
| Scope checks | Exact vendor, actor and amount ceiling | Exact service, environment and actor |
| Freshness | Bound aggregate and version | Bound service state and generation |
| Atomic local writer | Store lock, approval consumption, state replacement | Store lock, approval consumption, state replacement |
| Post-write verification | Aggregate equality | Service-state equality |

Each adapter validates time and exact proposal/state binding before kernel
evaluation, after kernel evaluation and atomically before its writer. Changed
state or expired authority cannot invoke the writer. Duplicate concurrent
attempts can invoke it once. A failed or mismatching writer cannot manufacture
VERIFIED_EFFECT.

Domain failure labels remain distinct from kernel invariant results. The
current executable eighth invariant is `consciousness`; neither adapter
renames it. Synthetic approvals are issued and retained in each local store,
with no claim of human credential authentication or independent provenance.

## Run

From this candidate checkout:

```bash
/home/jerry/grassrootsai-live-venv/bin/python -m pytest -q tests/test_scqos_domain_sdk.py tests/test_scqos_domain_adapter_reuse.py tests/test_database_action_decision.py tests/test_scqos_transition_evaluator.py
/home/jerry/grassrootsai-live-venv/bin/python scripts/run_scqos_domain_reuse_demo.py
```

The CLI emits eight JSON receipts: valid, unapproved, expired and stale-state
for each domain. The valid payment debits $500 from $10,000; the valid deployment
replaces the simulated image digest and increments generation. All other
scenarios HOLD without writer invocation.

## What this establishes

Two different domain models implement the same orchestration interfaces without
changing the orchestration or SCQOS core. Shared tests exercise the same admission,
race, replay, failed-writer and observation rules in both models. The deployment
adapter imports independently of the payment adapter.

## Limits and next integration boundary

Both adapters encode their aggregate mutation using the already installed
synthetic database-write boundary. This establishes SDK reuse across two
domain workflows through one underlying consequence boundary. It does not
establish universal consequence-boundary support.

The deployment store is an in-memory simulation. No ECS update, image pull,
container launch, health check, AWS API or real rollout occurs. VERIFIED_EFFECT
means the simulated metadata matches, not that a service is healthy or running.

The kernel evidence construction repeats some database-lab binding boilerplate.
It can later move into a shared helper without changing these interfaces, but
that refactor was deliberately unnecessary for this reuse test.

A real deployment integration still needs an installed deployment boundary,
provider-verified authority, immutable artifact identity, authoritative state
reads, an enforced exclusive writer, durable replay prevention and appropriate
rollout verification. A process lock cannot make a remote AWS update atomic.
This candidate must not be represented as a live deployment controller.

## Verification recorded 2026-10-02

Scoped regression: **301 passed in 0.75s**, exit 0. This covers both domain
adapters plus transition, database-action and external-authority contracts;
it is not a whole-repository regression.

The eight-row comparison CLI passed. Git comparison against payment candidate
`df234620ff3d4d7466935292a70e03924a397ea4` confirmed no changes to
`scqos_domain_sdk.py`, `scqos_synthetic_payment_adapter.py`, the transition
contract/evaluator, runtime evidence, governed registry or database decision.
Only the deployment adapter, shared tests, comparison CLI and this document
were added. No push, deployment, AWS mutation or real payment occurred.
