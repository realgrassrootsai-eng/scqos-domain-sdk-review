# Persistent SQLite domain adapter validation — 2026-10-05

Scope: local persistent SQLite realization of the vector-transition example. Runtime SDK wheel and prior mathematical example remain unchanged.

## Workbench provenance

DeepSeek v3.2 generated an initial candidate in an isolated detached worktree. Executed tests exposed frozen-dataclass initialization, spawn pickling/import defects, kernel binding, crash-hook placement, and race-fixture defects. The maintainer corrected those issues in the isolated mission. A final DeepSeek inspector review found no blocking issues; that review is generated analysis, not execution evidence.

## Executed maintainer checks

- SQLite mission suite: 16 passed.
- Combined persistent SQLite, expanded domain, original mathematical, and bundled SDK suites: 302 passed, 13 subtests passed.
- Tests run against the installed bundled SDK wheel from outside the repository.

Coverage includes persistent authoritative state, issued/consumed approvals, exact authority binding, replay, stale references, expiry, mathematical predicates, atomic consume+ledger+state write under BEGIN IMMEDIATE, two-process contention, precommit process death with rollback, postcommit process death with recovery, and explicit close/reopen persistence.

Claims remain local: trusted host, application writers routed through this adapter, SQLite process serialization. This does not establish distributed-database atomicity, OS-level exclusive write enforcement, or power-loss certification.
