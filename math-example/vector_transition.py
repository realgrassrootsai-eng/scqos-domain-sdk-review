"""Exact-integer local vector adapter; no physical system or network access."""
from copy import deepcopy
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from threading import RLock
import json

from database_action_approval import attach_database_action_approval, build_database_action_approval
from database_action_contracts import DatabaseWriteActionV1, DatabaseWriteOperation
from database_action_governance import DATABASE_ACTION_LAB_TABLE, build_database_action_transition_binding
from scqos_contract_digest import contract_digest
from scqos_domain_sdk import PreparedTransition, execute_governed_transition
from scqos_synthetic_deployment_adapter import SyntheticDeploymentAdapter, ACTOR, canonical, utc, text

@dataclass(frozen=True)
class Update:
    transition_id: str
    k: int
    actor: str = ACTOR
    def __post_init__(self):
        text(self.transition_id)
        text(self.actor)
        if type(self.k) is not int:
            raise ValueError('exact_integer_step_required')

@dataclass(frozen=True)
class Approval:
    approval_id: str
    request_digest: str
    state_digest: str
    expected_digest: str
    actor: str
    issued_at: datetime
    expires_at: datetime

class Store:
    def __init__(self):
        self.lock = RLock()
        self._state = dict(x=6, y=4, revision=0)
        self.issued = {}
        self.used = set()
        self.executed = set()
        self.writer_count = 0
    def read(self):
        with self.lock:
            return deepcopy(self._state)
    def competing_change(self):
        with self.lock:
            self._state = dict(x=5, y=5, revision=self._state['revision']+1)

class VectorAdapter:
    # Reuse the existing synthetic database-boundary kernel builder unchanged.
    # Domain mathematics is evaluated separately below, not by this builder.
    kernel = SyntheticDeploymentAdapter.kernel
    def __init__(self, store, clock=None):
        self.store = store
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.before_atomic_write = None
    def read_authoritative_state(self):
        return self.store.read()
    def collect_authority(self, authority):
        if authority is not None and type(authority) is not Approval:
            raise ValueError('exact_approval_required')
        return authority
    def expected(self, request, before):
        return dict(x=before['x']-request.k, y=before['y']+request.k,
                    revision=before['revision']+1)
    def issue_approval(self, request, approval_id='approval-1', lifetime_seconds=60):
        text(approval_id)
        if type(request) is not Update:
            raise ValueError('exact_update_required')
        now = utc(self.clock())
        if type(lifetime_seconds) is not int or lifetime_seconds <= 0:
            raise ValueError('positive_lifetime_required')
        with self.store.lock:
            if approval_id in self.store.issued:
                raise ValueError('approval_id_already_issued')
            before = self.store.read()
            a = Approval(approval_id, contract_digest(asdict(request)), contract_digest(before),
                contract_digest(self.expected(request, before)), request.actor, now,
                now+timedelta(seconds=lifetime_seconds))
            self.store.issued[approval_id] = a
            return a
    def normalize_proposal(self, request, before, authority):
        if type(request) is not Update:
            raise ValueError('exact_update_required')
        expected = self.expected(request, before)
        action = DatabaseWriteActionV1(transition_id='vector:'+request.transition_id,
            actor_id=request.actor, operation=DatabaseWriteOperation.SET_FIELD,
            table_name=DATABASE_ACTION_LAB_TABLE, record_key='vector-example',
            field_name='synthetic_vector_state', old_value=canonical(before),
            proposed_value=canonical(expected),
            evidence_refs=('synthetic-vector-state:'+contract_digest(before),))
        lab = None
        if authority is not None:
            lab = build_database_action_approval(action, approval_id=authority.approval_id,
                                                approver_id='synthetic-lab-operator')
            action = attach_database_action_approval(action, lab)
        binding = build_database_action_transition_binding(action, request_id=action.transition_id,
            session_id='action-lab', inherited_state_ref='synthetic-state:'+contract_digest(before))
        return PreparedTransition(contract_digest(dict(request=asdict(request), before=before,
            expected_after=expected)), deepcopy(before), expected,
            dict(action=action, approval=lab), binding.proposal)
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
        with self.store.lock:
            if self.store.issued.get(authority.approval_id) != authority:
                failures.append('unrecognized_authority')
            if authority.approval_id in self.store.used or request.transition_id in self.store.executed:
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
        if self.before_atomic_write:
            self.before_atomic_write()
        with self.store.lock:
            if self.evaluate_domain_predicates(request, prepared, authority, self.store.read()):
                return False
            self.store.used.add(authority.approval_id)
            self.store.executed.add(request.transition_id)
            self.store.writer_count += 1
            mark_invoked()
            self.store._state = deepcopy(prepared.expected_after)
            return True
    def verify_consequence(self, prepared, observed):
        return observed == prepared.expected_after
    def execute(self, request, authority=None, kernel=None):
        return execute_governed_transition(self, request, authority, kernel=kernel or self.kernel)

def scenarios():
    now = datetime(2026, 10, 4, tzinfo=timezone.utc)
    for name, k in [('valid',2), ('step_bound',4), ('nonnegative',7),
                    ('stale_reference',2), ('missing_authority',2), ('expired',2),
                    ('changed_proposal',2), ('atomic_competing_change',2), ('replay',2)]:
        store = Store()
        clock = [now]
        adapter = VectorAdapter(store, lambda: clock[0])
        request = Update('transition-1', k)
        approval = adapter.issue_approval(request)
        if name == 'stale_reference': store.competing_change()
        if name == 'missing_authority': approval = None
        if name == 'expired': clock[0] += timedelta(seconds=61)
        if name == 'changed_proposal': request = Update('transition-1',3)
        if name == 'atomic_competing_change': adapter.before_atomic_write = store.competing_change
        if name == 'replay': adapter.execute(request, approval)
        before = store.read()
        count = store.writer_count
        receipt = adapter.execute(request, approval)
        yield dict(scenario=name, state_before_attempt=before,
            writer_calls_this_attempt=store.writer_count-count, receipt=receipt.to_dict())

if __name__ == '__main__':
    for row in scenarios():
        print(json.dumps(row,sort_keys=True))
