#!/usr/bin/env python3
"""Four local synthetic receipts; no network or real payment."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scqos_synthetic_payment_adapter import PaymentRequest, SyntheticPaymentAdapter, SyntheticPaymentStore

def main():
    now = datetime.now(timezone.utc)
    for scenario in ("valid", "unapproved", "expired", "stale_state"):
        store = SyntheticPaymentStore()
        adapter = SyntheticPaymentAdapter(store, lambda: now)
        request = PaymentRequest("payment-001", "Vendor X", 50_000)
        if scenario == "unapproved":
            approval = None
        elif scenario == "expired":
            approval = adapter.issue_approval(request, issued_at=now-timedelta(seconds=61), expires_at=now)
        else:
            approval = adapter.issue_approval(request)
        if scenario == "stale_state":
            store.competing_change(100)
        receipt = adapter.execute(request, approval)
        print(json.dumps(dict(scenario=scenario, receipt=receipt.to_dict()), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
