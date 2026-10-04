# Mathematical transition example — exact integer vector

An executable discussion example for James and Jimmy. This example is maintainer-tested, not independently reproduced. It makes no claim about their ISS application, spacecraft control, AFA integration, or safety certification.

## State and transition

Let s = (x, y, r), with x and y nonnegative integers and r an integer revision counter. The initial state is (6, 4, 0). A proposed integer step k produces:

T_k(s) = (x - k, y + k, r + 1).

Domain predicates are:

- Conservation: x + y = 10 before and after.
- Nonnegativity: x >= 0, y >= 0, x - k >= 0, y + k >= 0.
- Step bound: 1 <= k <= 3.

Numbers instantiate this example; the conserved quantity and step limit would come from an actual application specification.

### Elementary mathematical argument

For this defined transition, (x - k) + (y + k) = x + y, so conservation follows algebraically. Nonnegativity follows when k <= x and y + k >= 0. The step predicate is an additional policy choice, not a consequence of conservation. Exact integers avoid floating-point tolerances in this example.

This establishes those limited properties of T under the stated assumptions. Executable tests are not a proof of universal correctness of the adapter, SDK, kernel, or host environment.

## Admission and execution

A candidate must satisfy the domain predicates and carry recognized, unexpired authority bound to the exact request, actor, starting state (including revision), and expected result. Its permit must not have been consumed.

The SDK then evaluates the existing synthetic database-write kernel boundary. The adapter reuses the existing kernel evidence builder unchanged; the mathematical predicates above remain separate domain admission checks. A failed domain predicate can skip kernel evaluation, so kernel_decision is null in those receipts. These failures are not presented as failed SCQOS kernel invariants.

After kernel PERMIT, the SDK checks current state again. The adapter repeats the guards under one process lock, consumes approval, records the transition ID, and writes the state. The observed state must match the expected result for VERIFIED_EFFECT.

Kernel PERMIT alone is not a guarantee that the eventual write will occur. The atomic competing-change case deliberately exercises this distinction.

## Run from a fresh checkout

Requires Python 3.11 or newer with venv support. From the repository root:

```bash
python3 -m venv .math-venv
.math-venv/bin/python -m pip install --no-index --no-deps SCQOS-Domain-SDK-v0.1.0/scqos_domain_sdk_prototype-0.1.0-py3-none-any.whl
cd math-example
../.math-venv/bin/python -m unittest -v
../.math-venv/bin/python vector_transition.py
```

On Windows use the corresponding `.math-venv\Scripts\python.exe` paths. Pin a full repository commit before running, and record `git rev-parse HEAD`. The example uses the bundled unchanged wheel. Tests use the Python standard library; no cloud account, pytest, database server, or model is needed.

## Cases and expected observations

| Case | Decision | Writer calls in attempt | Explanation |
|---|---|---:|---|
| valid, k=2 | PERMIT | 1 | State becomes (4,6,1); effect verified |
| step_bound, k=4 | HOLD | 0 | Result is nonnegative and conserved but violates step limit |
| nonnegative, k=7 | HOLD | 0 | Negative resulting x; also violates step limit |
| stale_reference | HOLD | 0 | Approval binds (6,4,0); current state is (5,5,1) |
| missing_authority | HOLD | 0 | No approval supplied |
| expired | HOLD | 0 | Clock advanced beyond approval validity |
| changed_proposal | HOLD | 0 | Approval binds k=2; request changed to k=3 |
| atomic_competing_change | HOLD | 0 | Kernel permits, then another update occurs; atomic guard rejects our write |
| replay | HOLD | 0 | Prior authorized update remains; repeated request has no additional effect |

The duplicate-race test coordinates two kernel evaluations of the same proposal and asserts exactly one write. The integer-domain test rejects booleans, floats, NaN, and strings. The scenario test checks all nine cases, writer observations, and expected state.

`receipts.jsonl` records a maintainer run. In the competing-change case the observed state changes because of the injected other writer, not this rejected request. In replay, the earlier successful effect remains. HOLD does not undo another or an earlier valid effect.

## Assumptions and limits

The trusted components are the local process, clock, approval registry, state reader, synthetic kernel evidence builder, and exclusive adapter writer path. The lock applies only within this process. Direct access to the store can bypass the adapter; this is not an OS-enforced boundary. Approvals are local records, not cryptographically signed external authority. Revision increments address this example's stale-state reuse but do not model distributed consistency. Receipts are unsigned local observations, not independently witnessed physical outcomes.

## What James would supply next

One actual state representation, a transition equation or algorithm, the acceptance predicates, units/tolerances if numerical, and the authoritative source/version of the starting state. Then we can replace this invented problem with his bounded problem and ask whether the required constraints can be evaluated before committing its result.

Maintainer validation: three unittest methods passed, covering nine scenarios, duplicate concurrency, and invalid numeric types. Existing runtime modules and wheel remain unchanged. Nikolai's reproduction applies to the earlier verifier snapshot, not this new example.
