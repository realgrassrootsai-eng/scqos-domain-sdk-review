#!/usr/bin/env python3
"""Eight receipts across payment and deployment using one unchanged SDK."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scqos_synthetic_payment_adapter import PaymentRequest, SyntheticPaymentAdapter, SyntheticPaymentStore
from scqos_synthetic_deployment_adapter import (DeploymentRequest, SyntheticDeploymentAdapter,
    SyntheticDeploymentStore, TARGET_IMAGE)

def main():
    now = datetime.now(timezone.utc)
    for domain in ("payment", "deployment"):
        for scenario in ("valid", "unapproved", "expired", "stale_state"):
            if domain == "payment":
                store = SyntheticPaymentStore()
                adapter = SyntheticPaymentAdapter(store, lambda: now)
                request = PaymentRequest("payment-001", "Vendor X", 50_000)
            else:
                store = SyntheticDeploymentStore()
                adapter = SyntheticDeploymentAdapter(store, lambda: now)
                request = DeploymentRequest("deploy-001", "service-ABC", "production", TARGET_IMAGE)
            if scenario == "unapproved":
                approval = None
            elif scenario == "expired":
                approval = adapter.issue_approval(request, issued_at=now-timedelta(seconds=61), expires_at=now)
            else:
                approval = adapter.issue_approval(request)
            if scenario == "stale_state":
                store.competing_change()
            receipt = adapter.execute(request, approval)
            print(json.dumps(dict(domain=domain, scenario=scenario, receipt=receipt.to_dict()), sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
