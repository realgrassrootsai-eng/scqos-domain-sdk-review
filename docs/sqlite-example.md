# SQLite Vector Adapter Example

This example implements a local persistent SQLite adapter for the vector transition domain, reusing the existing `vector_transition.py` logic. It stores authoritative state, issued approvals, consumed approvals, and a transition ledger in a SQLite database, providing atomic writes and recovery queries.

## Overview

The adapter (`sqlite_vector.py`) uses SQLite with `BEGIN IMMEDIATE` transactions to ensure atomicity under single-process assumptions. All domain predicates, authority checks, and replay guards are re-evaluated under the transaction before mutating state. The adapter is designed for local trusted hosts where all writers go through this adapter.

## Files

- `sqlite-example/sqlite_vector.py`: The SQLite adapter implementation.
- `tests/test_sqlite_vector.py`: Pytest tests for the adapter.
- `math-example/vector_transition.py`: Reused domain logic (unchanged).

## Installation

Create an isolated virtual environment and install the SCQOS SDK wheel. No additional dependencies are required beyond Python's standard library (`sqlite3`).

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install scqos_domain_sdk-0.1.0-py3-none-any.whl
```

## Running Tests

Run the tests with pytest:

```bash
cd /path/to/workbench
python -m pytest tests/test_sqlite_vector.py -v
```

All tests use temporary databases; they do not modify any developer database.

## Demo

A runnable demo script is provided below. It creates a temporary database, issues an approval, executes a transition, and demonstrates recovery.

```python
import tempfile
from pathlib import Path
from datetime import datetime, timezone
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from sqlite_example.sqlite_vector import SQLiteVectorAdapter
from math_example.vector_transition import Update

def demo():
    with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
        db_path = Path(f.name)
    try:
        clock = lambda: datetime(2026, 10, 5, tzinfo=timezone.utc)
        adapter = SQLiteVectorAdapter(db_path, clock)
        print("Initial state:", adapter.read_authoritative_state())
        request = Update('demo-transition', 2)
        approval = adapter.issue_approval(request, approval_id='demo-approval')
        print("Issued approval:", approval.approval_id)
        receipt = adapter.execute(request, approval)
        print("Receipt decision:", receipt.decision)
        print("Writer invoked:", receipt.writer_invoked)
        print("Effect status:", receipt.effect_status)
        print("New state:", adapter.read_authoritative_state())
        status, info = adapter.recovery_query('demo-transition')
        print("Recovery query:", status)
        if info:
            print("Committed at:", info['committed_at'])
        adapter.close()
    finally:
        db_path.unlink()

if __name__ == '__main__':
    demo()
```

## Adapter Details

### Atomic Write Protocol

1. `BEGIN IMMEDIATE` transaction.
2. Re-read current state.
3. Re-evaluate all domain predicates and guards (expiry, replay, authority recognition, etc.).
4. If any guard fails, rollback and return `HOLD`.
5. Insert into `consumed_approvals` and `transition_ledger`.
6. Update `vector_state`.
7. `COMMIT`.

### Crash Recovery

The adapter provides a `recovery_query(transition_id)` method that returns:
- `"COMMITTED"` with bound expected state if the transition is recorded in the ledger.
- `"NOT_COMMITTED"` otherwise (under local assumptions, no distributed database guarantees).

Crash hooks (`before_atomic_write` and `after_commit`) are available for testing partial commits. The `before_atomic_write` hook is called after `BEGIN IMMEDIATE` but before any mutations, allowing simulation of a crash that rolls back the transaction. The `after_commit` hook is called after commit but before returning, allowing simulation of a crash after the commit is durable.

### Multi-Process Considerations

The adapter uses a single SQLite connection per instance. For multi-process tests, each process must open its own connection. The tests use `multiprocessing` with `spawn` context and barriers for deterministic synchronization. The adapter does not guarantee atomicity across multiple processes unless all writers go through the same adapter instance; under local trusted-host assumptions, SQLite's `BEGIN IMMEDIATE` provides serialization.

### SQLite Configuration

- `journal_mode=WAL`
- `synchronous=FULL`
- `busy_timeout=5000` (5 seconds)

These settings provide durability under local assumptions but do not guarantee power-loss safety.

## Testing Scenarios Covered

1. Valid transition.
2. Replay after database reopen.
3. Forged approval.
4. Stale state (competing change).
5. Expired authority.
6. Math predicate failure (step out of bounds).
7. Race condition: two processes with same approved request (exactly one commits).
8. Distinct approvals for same starting state (at most one commits).
9. Crash before commit (no partial state).
10. Crash after commit (full commit recoverable, replay blocked).

All tests use `tmp_path` and do not modify external files.
