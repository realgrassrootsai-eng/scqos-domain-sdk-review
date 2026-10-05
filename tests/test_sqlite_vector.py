"""Tests for SQLite vector adapter."""
import json
import os
import sqlite3
import tempfile
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys
import pytest
import scqos_domain_sdk

# Load vector_transition module for reuse
VECTOR_TRANSITION_PATH = Path(__file__).parent.parent / "math-example" / "vector_transition.py"
spec = spec_from_file_location("vector_transition", VECTOR_TRANSITION_PATH)
vector_module = module_from_spec(spec)
sys.modules["vector_transition"] = vector_module
spec.loader.exec_module(vector_module)

Update = vector_module.Update
Approval = vector_module.Approval
contract_digest = vector_module.contract_digest
utc = vector_module.utc
ACTOR = vector_module.ACTOR

# Import the SQLite adapter
sys.path.insert(0, str(Path(__file__).parent.parent / "sqlite-example"))
from sqlite_vector import SQLiteVectorAdapter

NOW = datetime(2026, 10, 5, tzinfo=timezone.utc)

@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "test.db"

@pytest.fixture
def clock():
    return [NOW]

@pytest.fixture
def adapter(db_path, clock):
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    yield adapter
    adapter.close()

def test_installed_sdk():
    assert 'site-packages' in Path(scqos_domain_sdk.__file__).parts

def test_initial_state(adapter):
    state = adapter.read_authoritative_state()
    assert state == {'x': 6, 'y': 4, 'revision': 0}

def test_issue_approval(adapter):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request, approval_id='test-approval')
    assert approval.approval_id == 'test-approval'
    assert approval.request_digest == contract_digest({'transition_id': 'transition-1', 'k': 2, 'actor': ACTOR})
    assert approval.state_digest == contract_digest({'x': 6, 'y': 4, 'revision': 0})
    expected = adapter.expected(request, {'x': 6, 'y': 4, 'revision': 0})
    assert approval.expected_digest == contract_digest(expected)
    assert approval.actor == ACTOR
    assert approval.issued_at == utc(NOW)
    assert approval.expires_at == utc(NOW + timedelta(seconds=60))

    # Duplicate approval_id should raise
    with pytest.raises(ValueError, match='approval_id_already_issued'):
        adapter.issue_approval(request, approval_id='test-approval')

def test_valid_transition(adapter):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request)
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'PERMIT'
    assert receipt.writer_invoked is True
    assert receipt.effect_status == 'VERIFIED_EFFECT'
    state = adapter.read_authoritative_state()
    assert state == {'x': 4, 'y': 6, 'revision': 1}
    # Check ledger
    conn = adapter._get_conn()
    cur = conn.execute("SELECT * FROM transition_ledger WHERE transition_id = ?", ('transition-1',))
    row = cur.fetchone()
    assert row is not None
    assert json.loads(row['after_state']) == state
    # Check consumed
    cur = conn.execute("SELECT 1 FROM consumed_approvals WHERE approval_id = ?", (approval.approval_id,))
    assert cur.fetchone() is not None

def test_replay_after_reopen(db_path, clock):
    # First adapter writes
    adapter1 = SQLiteVectorAdapter(db_path, lambda: clock[0])
    request = Update('transition-1', 2)
    approval = adapter1.issue_approval(request)
    receipt = adapter1.execute(request, approval)
    assert receipt.effect_status == 'VERIFIED_EFFECT'
    adapter1.close()
    # Reopen new adapter
    adapter2 = SQLiteVectorAdapter(db_path, lambda: clock[0])
    # Replay same request and approval should hold
    receipt = adapter2.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert 'replay' in receipt.domain_admission_failures
    assert receipt.writer_invoked is False
    assert receipt.effect_status == 'NOT_INVOKED'
    state = adapter2.read_authoritative_state()
    assert state == {'x': 4, 'y': 6, 'revision': 1}
    adapter2.close()

def test_forged_approval(adapter):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request)
    forged = Approval('forged', '0'*64, approval.state_digest, approval.expected_digest,
                      approval.actor, approval.issued_at, approval.expires_at)
    receipt = adapter.execute(request, forged)
    assert receipt.decision == 'HOLD'
    assert 'unrecognized_authority' in receipt.domain_admission_failures
    assert adapter.read_authoritative_state() == {'x': 6, 'y': 4, 'revision': 0}

def test_stale_state(adapter):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request)
    # Make competing change
    adapter.competing_change()
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert 'stale_reference' in receipt.domain_admission_failures
    state = adapter.read_authoritative_state()
    assert state == {'x': 5, 'y': 5, 'revision': 1}

def test_expired_authority(adapter, clock):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request, lifetime_seconds=10)
    clock[0] = NOW + timedelta(seconds=11)
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert 'expired_authority' in receipt.domain_admission_failures
    assert adapter.read_authoritative_state() == {'x': 6, 'y': 4, 'revision': 0}

def test_math_predicate_failure(adapter):
    request = Update('transition-1', 5)  # k > 3
    approval = adapter.issue_approval(request)
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert 'step_bound' in receipt.domain_admission_failures
    assert adapter.read_authoritative_state() == {'x': 6, 'y': 4, 'revision': 0}

def _worker_adapter_and_approval(db_path_str, clock_iso, approval_id):
    """Open the child-process adapter and reconstruct the stored approval exactly."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent / "sqlite-example"))
    import sqlite_vector as sv
    adapter = sv.SQLiteVectorAdapter(Path(db_path_str), lambda: datetime.fromisoformat(clock_iso))
    row = adapter._get_conn().execute(
        """SELECT request_digest, state_digest, expected_digest, actor, issued_at, expires_at
           FROM approvals WHERE approval_id = ?""",
        (approval_id,),
    ).fetchone()
    if row is None:
        raise AssertionError("stored approval missing")
    approval = sv.Approval(
        approval_id,
        row["request_digest"],
        row["state_digest"],
        row["expected_digest"],
        row["actor"],
        datetime.fromisoformat(row["issued_at"]),
        datetime.fromisoformat(row["expires_at"]),
    )
    return sv, adapter, approval

def _race_worker(db_path_str, clock_iso, approval_id, transition_id, barrier, result_queue):
    sv, adapter, approval = _worker_adapter_and_approval(db_path_str, clock_iso, approval_id)
    request = sv.Update(transition_id, 2)
    def synchronized_kernel(prepared):
        barrier.wait(timeout=5)
        return adapter.kernel(prepared)
    try:
        receipt = adapter.execute(request, approval, kernel=synchronized_kernel)
        result_queue.put((receipt.decision, receipt.writer_invoked))
    finally:
        adapter.close()

def _crash_worker(db_path_str, clock_iso, approval_id, transition_id, crash_point):
    import os
    sv, adapter, approval = _worker_adapter_and_approval(db_path_str, clock_iso, approval_id)
    request = sv.Update(transition_id, 2)
    def crash_now():
        os._exit(73 if crash_point == "precommit" else 74)
    if crash_point == "precommit":
        adapter.before_atomic_write = crash_now
    else:
        adapter.after_commit = crash_now
    adapter.execute(request, approval)

def _run_two_process_race(ctx, target, args1, args2):
    barrier = ctx.Barrier(2)
    result_queue = ctx.Queue()
    p1 = ctx.Process(target=target, args=(*args1, barrier, result_queue))
    p2 = ctx.Process(target=target, args=(*args2, barrier, result_queue))
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)
    for p in (p1, p2):
        if p.is_alive():
            p.terminate()
            p.join(timeout=2)
            raise AssertionError("worker did not finish")
        assert p.exitcode == 0
    return [result_queue.get(timeout=2), result_queue.get(timeout=2)]

def test_race_two_processes_same_approved_request(db_path, clock):
    """One stored approval raced twice: exactly one consequence commits."""
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    request = Update('race-transition', 2)
    adapter.issue_approval(request, approval_id='race-approval')
    adapter.close()
    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    args = (str(db_path), NOW.isoformat(), 'race-approval', 'race-transition')
    results = _run_two_process_race(ctx, _race_worker, args, args)
    assert sorted(r[0] for r in results) == ['HOLD', 'PERMIT']
    assert sum(r[1] for r in results) == 1
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    assert adapter.read_authoritative_state() == {'x': 4, 'y': 6, 'revision': 1}
    adapter.close()

def test_distinct_approvals_same_starting_state(db_path, clock):
    """Two approvals bound to one starting state: at most one can commit."""
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    request = Update('transition-1', 2)
    adapter.issue_approval(request, approval_id='approval-1')
    adapter.issue_approval(request, approval_id='approval-2')
    adapter.close()
    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    a1 = (str(db_path), NOW.isoformat(), 'approval-1', 'transition-1')
    a2 = (str(db_path), NOW.isoformat(), 'approval-2', 'transition-1')
    results = _run_two_process_race(ctx, _race_worker, a1, a2)
    assert sorted(r[0] for r in results) == ['HOLD', 'PERMIT']
    assert sum(r[1] for r in results) == 1
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    assert adapter.read_authoritative_state() == {'x': 4, 'y': 6, 'revision': 1}
    adapter.close()

def test_crash_hook_before_commit(db_path, clock):
    """Child exits after SQL mutations but before COMMIT; SQLite rolls all of them back."""
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    request = Update('crash-transition', 2)
    approval = adapter.issue_approval(request)
    adapter.close()
    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    p = ctx.Process(
        target=_crash_worker,
        args=(str(db_path), NOW.isoformat(), approval.approval_id, request.transition_id, 'precommit'),
    )
    p.start()
    p.join(timeout=10)
    if p.is_alive():
        p.terminate()
        p.join(timeout=2)
        raise AssertionError("precommit crash worker did not finish")
    assert p.exitcode == 73
    adapter2 = SQLiteVectorAdapter(db_path, lambda: clock[0])
    assert adapter2.read_authoritative_state() == {'x': 6, 'y': 4, 'revision': 0}
    conn = adapter2._get_conn()
    assert conn.execute("SELECT 1 FROM transition_ledger WHERE transition_id = ?", ('crash-transition',)).fetchone() is None
    assert conn.execute("SELECT 1 FROM consumed_approvals WHERE approval_id = ?", (approval.approval_id,)).fetchone() is None
    adapter2.close()

def test_crash_hook_after_commit(db_path, clock):
    """Child exits after COMMIT but before return; recovery sees the whole consequence."""
    adapter = SQLiteVectorAdapter(db_path, lambda: clock[0])
    request = Update('crash-after-transition', 2)
    approval = adapter.issue_approval(request)
    adapter.close()
    import multiprocessing
    ctx = multiprocessing.get_context('spawn')
    p = ctx.Process(
        target=_crash_worker,
        args=(str(db_path), NOW.isoformat(), approval.approval_id, request.transition_id, 'postcommit'),
    )
    p.start()
    p.join(timeout=10)
    if p.is_alive():
        p.terminate()
        p.join(timeout=2)
        raise AssertionError("postcommit crash worker did not finish")
    assert p.exitcode == 74
    adapter2 = SQLiteVectorAdapter(db_path, lambda: clock[0])
    assert adapter2.read_authoritative_state() == {'x': 4, 'y': 6, 'revision': 1}
    status, info = adapter2.recovery_query('crash-after-transition')
    assert status == 'COMMITTED'
    assert info['after_state'] == {'x': 4, 'y': 6, 'revision': 1}
    assert adapter2._get_conn().execute(
        "SELECT 1 FROM consumed_approvals WHERE approval_id = ?",
        (approval.approval_id,),
    ).fetchone() is not None
    receipt = adapter2.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert receipt.writer_invoked is False
    adapter2.close()

def test_recovery_query(adapter):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request)
    status, info = adapter.recovery_query('transition-1')
    assert status == 'NOT_COMMITTED'
    assert info is None
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'PERMIT'
    status, info = adapter.recovery_query('transition-1')
    assert status == 'COMMITTED'
    assert info['approval_id'] == approval.approval_id
    assert info['after_state'] == {'x': 4, 'y': 6, 'revision': 1}

def test_clock_injection_for_expiry(adapter, clock):
    request = Update('transition-1', 2)
    approval = adapter.issue_approval(request, lifetime_seconds=10)
    clock[0] = NOW + timedelta(seconds=5)
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'PERMIT'
    clock[0] = NOW + timedelta(seconds=15)
    # Same approval is now expired
    receipt = adapter.execute(request, approval)
    assert receipt.decision == 'HOLD'
    assert 'expired_authority' in receipt.domain_admission_failures
    # State unchanged because approval expired
    assert adapter.read_authoritative_state() == {'x': 4, 'y': 6, 'revision': 1}

def test_public_helpers_implemented(adapter):
    # Ensure all public methods exist and are callable
    assert callable(adapter.read_authoritative_state)
    assert callable(adapter.collect_authority)
    assert callable(adapter.expected)
    assert callable(adapter.issue_approval)
    assert callable(adapter.normalize_proposal)
    assert callable(adapter.evaluate_domain_predicates)
    assert callable(adapter.execute_consequence)
    assert callable(adapter.verify_consequence)
    assert callable(adapter.execute)
    assert callable(adapter.recovery_query)
    assert callable(adapter.competing_change)
    assert callable(adapter.close)
