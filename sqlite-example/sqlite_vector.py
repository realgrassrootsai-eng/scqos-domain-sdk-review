"""Local persistent SQLite vector adapter."""
import json
import sqlite3
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

from scqos_domain_sdk import PreparedTransition, execute_governed_transition

# Reuse vector_transition.py from math-example relative to this file
VECTOR_TRANSITION_PATH = Path(__file__).parent.parent / "math-example" / "vector_transition.py"
if not VECTOR_TRANSITION_PATH.exists():
    raise ImportError(f"Cannot find vector_transition.py at {VECTOR_TRANSITION_PATH}")
existing_vector_module = sys.modules.get("vector_transition")
if existing_vector_module is not None and Path(existing_vector_module.__file__).resolve() == VECTOR_TRANSITION_PATH.resolve():
    vector_module = existing_vector_module
else:
    spec = spec_from_file_location("vector_transition", VECTOR_TRANSITION_PATH)
    vector_module = module_from_spec(spec)
    sys.modules["vector_transition"] = vector_module
    spec.loader.exec_module(vector_module)

Update = vector_module.Update
Approval = vector_module.Approval
contract_digest = vector_module.contract_digest
canonical = vector_module.canonical
utc = vector_module.utc
ACTOR = vector_module.ACTOR

@dataclass
class SQLiteVectorAdapter:
    """Adapter storing state, approvals, consumed approvals, and transition ledger in SQLite."""
    kernel = vector_module.SyntheticDeploymentAdapter.kernel
    db_path: Path
    clock: callable
    before_atomic_write: callable = None
    after_commit: callable = None

    def __post_init__(self):
        self._conn = None
        self._ensure_tables()

    def _get_conn(self):
        if self._conn is None:
            conn = sqlite3.connect(self.db_path, timeout=10)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=FULL")
            conn.execute("PRAGMA busy_timeout=5000")
            conn.row_factory = sqlite3.Row
            self._conn = conn
        return self._conn

    def _ensure_tables(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS vector_state (
                key TEXT PRIMARY KEY,
                value INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS approvals (
                approval_id TEXT PRIMARY KEY,
                request_digest TEXT NOT NULL,
                state_digest TEXT NOT NULL,
                expected_digest TEXT NOT NULL,
                actor TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS consumed_approvals (
                approval_id TEXT PRIMARY KEY
            );
            CREATE TABLE IF NOT EXISTS transition_ledger (
                transition_id TEXT PRIMARY KEY,
                approval_id TEXT NOT NULL,
                before_state TEXT NOT NULL,
                after_state TEXT NOT NULL,
                committed_at TEXT NOT NULL
            );
        """)
        conn.commit()
        # Initialize state if not present
        cur = conn.execute("SELECT COUNT(*) FROM vector_state")
        if cur.fetchone()[0] == 0:
            conn.executescript("""
                INSERT INTO vector_state (key, value) VALUES ('x', 6);
                INSERT INTO vector_state (key, value) VALUES ('y', 4);
                INSERT INTO vector_state (key, value) VALUES ('revision', 0);
            """)
            conn.commit()

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def read_authoritative_state(self):
        conn = self._get_conn()
        cur = conn.execute("SELECT key, value FROM vector_state")
        return {row["key"]: row["value"] for row in cur}

    def collect_authority(self, authority):
        if authority is not None and type(authority) is not Approval:
            raise ValueError('exact_approval_required')
        return authority

    def expected(self, request, before):
        return dict(x=before['x']-request.k, y=before['y']+request.k,
                    revision=before['revision']+1)

    def issue_approval(self, request, approval_id='approval-1', lifetime_seconds=60):
        vector_module.text(approval_id)
        if type(request) is not Update:
            raise ValueError('exact_update_required')
        now = utc(self.clock())
        if type(lifetime_seconds) is not int or lifetime_seconds <= 0:
            raise ValueError('positive_lifetime_required')
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Check for duplicate approval_id
            cur = conn.execute("SELECT 1 FROM approvals WHERE approval_id = ?", (approval_id,))
            if cur.fetchone():
                raise ValueError('approval_id_already_issued')
            before = self.read_authoritative_state()
            a = Approval(approval_id, contract_digest(asdict(request)), contract_digest(before),
                contract_digest(self.expected(request, before)), request.actor, now,
                now+timedelta(seconds=lifetime_seconds))
            conn.execute("""
                INSERT INTO approvals (approval_id, request_digest, state_digest, expected_digest,
                                       actor, issued_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (a.approval_id, a.request_digest, a.state_digest, a.expected_digest,
                  a.actor, a.issued_at.isoformat(), a.expires_at.isoformat()))
            conn.commit()
            return a
        except Exception:
            conn.rollback()
            raise

    def normalize_proposal(self, request, before, authority):
        if type(request) is not Update:
            raise ValueError('exact_update_required')
        expected = self.expected(request, before)
        # Reuse the synthetic kernel builder from vector_transition
        action = vector_module.DatabaseWriteActionV1(
            transition_id='vector:'+request.transition_id,
            actor_id=request.actor,
            operation=vector_module.DatabaseWriteOperation.SET_FIELD,
            table_name=vector_module.DATABASE_ACTION_LAB_TABLE,
            record_key='vector-example',
            field_name='synthetic_vector_state',
            old_value=canonical(before),
            proposed_value=canonical(expected),
            evidence_refs=('synthetic-vector-state:'+contract_digest(before),)
        )
        lab = None
        if authority is not None:
            lab = vector_module.build_database_action_approval(
                action, approval_id=authority.approval_id,
                approver_id='synthetic-lab-operator'
            )
            action = vector_module.attach_database_action_approval(action, lab)
        binding = vector_module.build_database_action_transition_binding(
            action, request_id=action.transition_id,
            session_id='action-lab',
            inherited_state_ref='synthetic-state:'+contract_digest(before)
        )
        return PreparedTransition(
            contract_digest(dict(request=asdict(request), before=before,
                                 expected_after=expected)),
            deepcopy(before), expected,
            dict(action=action, approval=lab),
            binding.proposal
        )

    def evaluate_domain_predicates(self, request, prepared, authority, current):
        failures = []
        after = prepared.expected_after
        if current['x']+current['y'] != 10 or after['x']+after['y'] != 10:
            failures.append('conservation')
        if min(current['x'], current['y'], after['x'], after['y']) < 0:
            failures.append('nonnegative')
        if not 1 <= request.k <= 3:
            failures.append('step_bound')
        if authority is None:
            return tuple(failures+['approval_missing'])
        if not utc(authority.issued_at) <= utc(self.clock()) < utc(authority.expires_at):
            failures.append('expired_authority')
        conn = self._get_conn()
        # Check approval exists and matches
        cur = conn.execute("""
            SELECT request_digest, state_digest, expected_digest, actor, issued_at, expires_at
            FROM approvals WHERE approval_id = ?
        """, (authority.approval_id,))
        row = cur.fetchone()
        if row is None:
            failures.append('unrecognized_authority')
        else:
            expected_approval = Approval(
                authority.approval_id, row["request_digest"], row["state_digest"],
                row["expected_digest"], row["actor"],
                datetime.fromisoformat(row["issued_at"]),
                datetime.fromisoformat(row["expires_at"])
            )
            if expected_approval != authority:
                failures.append('unrecognized_authority')
        # Check consumed and ledger
        cur = conn.execute("SELECT 1 FROM consumed_approvals WHERE approval_id = ?",
                           (authority.approval_id,))
        if cur.fetchone():
            failures.append('replay')
        cur = conn.execute("SELECT 1 FROM transition_ledger WHERE transition_id = ?",
                           (request.transition_id,))
        if cur.fetchone():
            failures.append('replay')
        if request.actor != ACTOR or request.actor != authority.actor:
            failures.append('actor_scope')
        if contract_digest(asdict(request)) != authority.request_digest:
            failures.append('changed_proposal')
        if contract_digest(current) != authority.state_digest or current != prepared.before:
            failures.append('stale_reference')
        if contract_digest(after) != authority.expected_digest:
            failures.append('changed_expected_state')
        return tuple(failures)

    def execute_consequence(self, request, prepared, authority, mark_invoked):
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            # Recheck all guards under the same transaction that performs the write.
            current = self.read_authoritative_state()
            failures = self.evaluate_domain_predicates(request, prepared, authority, current)
            if failures:
                conn.rollback()
                return False
            # Consequence starts here: from this point an exception is an observed-outcome problem.
            mark_invoked()
            conn.execute("INSERT INTO consumed_approvals (approval_id) VALUES (?)",
                         (authority.approval_id,))
            conn.execute("""
                INSERT INTO transition_ledger (transition_id, approval_id, before_state,
                                               after_state, committed_at)
                VALUES (?, ?, ?, ?, ?)
            """, (request.transition_id, authority.approval_id,
                  json.dumps(current), json.dumps(prepared.expected_after),
                  utc(self.clock()).isoformat()))
            # Update vector_state
            after = prepared.expected_after
            for key, value in after.items():
                conn.execute("UPDATE vector_state SET value = ? WHERE key = ?", (value, key))
            if self.before_atomic_write:
                self.before_atomic_write()
            conn.commit()
            if self.after_commit:
                self.after_commit()
            return True
        except Exception:
            conn.rollback()
            raise

    def verify_consequence(self, prepared, observed):
        return observed == prepared.expected_after

    def execute(self, request, authority=None, kernel=None):
        return execute_governed_transition(
            self, request, authority, kernel=kernel or self.kernel
        )

    def recovery_query(self, transition_id):
        """Return COMMITTED with bound expected state if ledger exists, NOT_COMMITTED otherwise."""
        conn = self._get_conn()
        cur = conn.execute("""
            SELECT approval_id, before_state, after_state, committed_at
            FROM transition_ledger WHERE transition_id = ?
        """, (transition_id,))
        row = cur.fetchone()
        if row:
            return "COMMITTED", {
                "approval_id": row["approval_id"],
                "before_state": json.loads(row["before_state"]),
                "after_state": json.loads(row["after_state"]),
                "committed_at": row["committed_at"]
            }
        else:
            return "NOT_COMMITTED", None

    @contextmanager
    def competing_change(self):
        """Helper for tests: make a competing change outside adapter."""
        conn = self._get_conn()
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute("SELECT value FROM vector_state WHERE key = 'revision'")
            rev = cur.fetchone()[0]
            conn.execute("UPDATE vector_state SET value = ? WHERE key = 'x'", (5,))
            conn.execute("UPDATE vector_state SET value = ? WHERE key = 'y'", (5,))
            conn.execute("UPDATE vector_state SET value = ? WHERE key = 'revision'", (rev + 1,))
            conn.commit()
        except sqlite3.Error:
            conn.rollback()
            raise
