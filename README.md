# SCQOS Domain SDK — independent reproduction kit

Frozen local synthetic review prototype, version 0.1.0.

## Reproduce this snapshot

Requires Git and Python 3.11 or newer, including Python's venv/ensurepip support.

```bash
git clone --branch v0.1.0 --single-branch https://github.com/realgrassrootsai-eng/scqos-domain-sdk-review.git
cd scqos-domain-sdk-review/SCQOS-Domain-SDK-v0.1.0
python3 verify_installation.py .
```

On Windows, use `py -3.11 verify_installation.py .`.

Read the [bundle README](SCQOS-Domain-SDK-v0.1.0/README.md) first. The verifier checks every artifact listed in the manifest, installs the wheel into a fresh temporary environment without downloading dependencies, runs 14 conformance checks for each synthetic adapter, and runs the comparison example. Success exits 0 and prints JSON with `passed: true`, two passing adapters, and `demo_receipts: 8`.

## Independent report

Return the full output, exit code, OS, Python version, and repository commit (`git rev-parse HEAD`). Preserve failures as observed; do not silently repair the package. Separate any proposed fixes from the reproduction record.

This checks installation and synthetic behavior only. It is not proof of production payments, deployments, remote atomicity, AFA compatibility, or compliance. No AWS credentials or model keys are needed. No independent reproduction has yet been claimed for this snapshot.

## Provenance

The nested review bundle is byte-for-byte identical to the prepared ZIP contents. Source candidate: `2746e515fa658c946b3349fbf256c43a3c3a66e5`. The bundle contains source, wheel, source archive, selected tests, documentation, and an unsigned SHA-256 manifest.

Original ZIP SHA-256: `05705cbbf472bc5dcbc7929c78ae1fd4208f81d346721ebb47a37c29f8bf05b1`.

The original candidate recorded 320 scoped tests passing. The single-command verifier runs the installation/conformance/demo checks, not that entire regression suite.

Publication for inspection does not add an open-source license or grant third-party rights.
