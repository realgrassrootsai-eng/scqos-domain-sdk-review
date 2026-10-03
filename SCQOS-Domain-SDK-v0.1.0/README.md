# SCQOS Domain SDK prototype — integration review kit

Version 0.1.0. Python 3.11 or newer. No runtime third-party dependencies.
The package contains the unchanged local SDK, existing kernel dependency closure,
two synthetic adapters and a reusable behavioral conformance runner.

## Install from the review bundle

Create a fresh environment. Do not install this prototype into Anabelle's
production environment: its existing top-level module names may collide.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --no-index --no-deps scqos_domain_sdk_prototype-0.1.0-py3-none-any.whl
.venv/bin/python -m scqos_adapter_conformance --factory builtin-payment
.venv/bin/python -m scqos_adapter_conformance --factory builtin-deployment
.venv/bin/python examples/run_scqos_domain_reuse_demo.py
```

Windows PowerShell uses `.venv\Scripts\python.exe` in place of
`.venv/bin/python`. There is no AWS login, model key or database credential.

Alternatively run `python3 verify_installation.py .` from the extracted bundle.
It checks the recorded wheel hash, installs that wheel into a fresh temporary
environment with no network dependencies, runs both conformance factories and
the comparison example from outside the source checkout. It outputs one JSON
summary and exits nonzero on failure.

## Adapter contract

Import `DomainAdapter`, `PreparedTransition` and
`execute_governed_transition` from `scqos_domain_sdk`.

Your adapter supplies six operations: read state, normalize proposal, collect
authority, evaluate domain predicates, execute a guarded consequence and verify
the observed consequence. Supply an explicit trusted kernel callable returning
a `TransitionReceipt` for exactly `PreparedTransition.kernel_proposal`.
Keep domain admission checks distinct from the actual kernel invariant results.

The writer must repeat freshness, scope, expiry and replay guards atomically with
approval consumption and mutation. It calls the supplied `mark_invoked` just
before invoking the writer. An atomic guard rejection returns False without
calling the writer. A normal write attempt returns True. The SDK re-reads state
after an attempt. The adapter must not mutate the bound expected state object.

A real adapter needs an enforced exclusive writer boundary. A Python protocol
does not prevent callers from bypassing it. The synthetic adapters offer only
one-process locks; these do not establish remote API atomicity.

## Reusable conformance factory

Provide a zero-argument function returning `AdapterConformanceCase` from
`scqos_adapter_conformance`. Every call must create a fresh disposable case
with valid initial approval. The case includes:

- adapter, request, authority and trusted kernel
- independent state-read and writer-count callbacks
- a changed-request callback and a clock-advance callback
- competing-change and before-write-hook callbacks
- writer injection and expected-state write callbacks

The clock starts within approval validity and advancing 61 seconds must expire
it. Hooks must affect the actual code path used by the adapter. Writer callbacks
simulate local failures and mismatches. The built-in factories are executable
examples of this contract.

```bash
.venv/bin/python -m scqos_adapter_conformance --factory my_adapter:make_case
```

An external factory is executable user-supplied Python. The runner deliberately
mutates its test store and injects writer failures. Use a disposable local
fixture. It does not sandbox arbitrary factory code or certify a live service.

Fourteen probes cover valid observed effect, missing/expired authority, changed
proposal, stale state, replay, atomic stale/expiry guards, no-effect writer,
writer exceptions before/after effect, unavailable/HOLD kernel and simultaneous
duplicate attempts. The JSON report identifies each failed probe and exits 1
for behavioral failure, 2 for factory resolution failure, 0 for all checks passed.

## Receipt definitions and evidence

`schema_version`: scqos_domain_receipt_v1.
`decision`: HOLD or PERMIT for the admission attempt.
`kernel_decision`: null if skipped, otherwise the actual kernel decision.
`kernel_invariant_results`: actual evaluated chain in executable order.
`domain_admission_failures`: separate adapter/guard/error reasons.
`writer_invoked`: whether the local writer was attempted.
`before`, `expected_after`, `observed_after`: state snapshots.
`effect_status`: NOT_INVOKED, VERIFIED_EFFECT, UNVERIFIED_EFFECT or UNKNOWN_OUTCOME.
`provenance`: synthetic_local_lab in these examples.

PERMIT does not prove execution success. VERIFIED_EFFECT requires a matching
store re-read. The executable eighth invariant remains `consciousness`.
This report format is not a signed receipt or an independently witnessed proof.

The bundle includes source/artifact SHA-256 hashes and a source commit. Hashes
detect byte changes relative to the included manifest; the manifest is unsigned.
The bundled source mirrors the installed wheel and supports inspection.

## Scope

Both examples simulate different domain workflows over the already installed
database-write boundary. No real payments, ECS deployment, production integration,
AFA compatibility, compliance certification or independent reproduction is claimed.
The package is a review prototype. No third-party license grant is implied.

Installation verification proves it works outside the original checkout on the
tested interpreter. An independent engineer's review is still needed.

## Recorded local verification — 2026-10-02

Scoped regression: 320 passed, covering SDK/adapters, conformance behavior and
CLI failures, manifest integrity checks, kernel and authority contracts.
The original SDK, both adapters, kernel and registry are byte-for-byte unchanged
from reuse candidate `cf36261e477e126de9fa5fa12fe0b4c5cdb77a37`.
This is scoped testing, not a whole-repository or independent review result.
