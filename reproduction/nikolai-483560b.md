# Reported independent reproduction — original snapshot

Reporter: Nikolai Nedovodin. Source: message supplied by Jerry; this record transcribes the supplied result and does not independently authenticate the reporter or environment.

- Commit: `483560b361f1113a276a22947e2a9888ea93060d`
- OS as reported: Linux 7.0.0-34-generic x86_64 (Debian bookworm container)
- Python: 3.12.14
- Exit code: 0
- Command: `python3 verify_installation.py`
- Reporter states nothing was modified or repaired.

Complete reported output:

```json
{"conformance": [{"adapter": "builtin-payment", "checks": 14, "passed": true}, {"adapter": "builtin-deployment", "checks": 14, "passed": true}], "demo_receipts": 8, "fresh_environment": true, "network_dependencies": false, "passed": true, "source_checkout_required": false}
```

Scope stated by reporter: clean-environment reproduction of the verifier at that commit only; not a review or endorsement of the SDK design or claims.

Reading observations: bundled test paths did not match examples/verifier locations; tags can move; manifest is unsigned; no license file; original Git author and committer email was the placeholder `YOUR_GITHUB_EMAIL`.

The original commit and v0.1.0 tag are preserved. Corrections are separate commits. This report does not apply to later revisions.
