# SCQOS Domain SDK — independent reproduction kit

Frozen local synthetic review prototype, version 0.1.0.

## Reproduce this snapshot

Requires Git and Python 3.11 or newer, including Python's venv/ensurepip support.

```bash
git clone https://github.com/realgrassrootsai-eng/scqos-domain-sdk-review.git
cd scqos-domain-sdk-review
git checkout --detach 483560b361f1113a276a22947e2a9888ea93060d
cd SCQOS-Domain-SDK-v0.1.0
python3 verify_installation.py .
```

On Windows, use `py -3.11 verify_installation.py .`.

Read the [bundle README](SCQOS-Domain-SDK-v0.1.0/README.md) first. The verifier checks every artifact listed in the manifest, installs the wheel into a fresh temporary environment without downloading dependencies, runs 14 conformance checks for each synthetic adapter, and runs the comparison example. Success exits 0 and prints JSON with `passed: true`, two passing adapters, and `demo_receipts: 8`.

## Independent report

Return the full output, exit code, OS, Python version, and repository commit (`git rev-parse HEAD`). Preserve failures as observed; do not silently repair the package. Separate any proposed fixes from the reproduction record.

This checks installation and synthetic behavior only. It is not proof of production payments, deployments, remote atomicity, AFA compatibility, or compliance. No AWS credentials or model keys are needed. Nikolai Nedovodin reported a successful clean-environment verifier reproduction of the original commit; see [the scoped record](reproduction/nikolai-483560b.md). This maintenance revision has not been independently reproduced.

## Provenance

The original commit contains the unchanged prepared ZIP contents. This maintenance revision corrects bundled test paths and documentation and refreshes the unsigned manifest. Runtime source, wheel, and source archive are unchanged. Source candidate: `2746e515fa658c946b3349fbf256c43a3c3a66e5`. The bundle contains source, wheel, source archive, selected tests, documentation, and an unsigned SHA-256 manifest.

Original ZIP SHA-256: `05705cbbf472bc5dcbc7929c78ae1fd4208f81d346721ebb47a37c29f8bf05b1`.

The original candidate recorded 320 scoped tests passing. The single-command verifier runs the installation/conformance/demo checks, not that entire regression suite.

Publication for inspection does not add an open-source license or grant third-party rights.

## Maintenance revision and bundled tests

The commands above intentionally reproduce the exact original externally tested commit, not the latest maintenance revision. To test a newer revision, substitute its full 40-character commit ID in the checkout command. Tags are convenient labels and can move.

On the corrected maintenance revision, from the bundle folder:

```bash
python3 -m venv .test-venv
.test-venv/bin/python -m pip install --no-index --no-deps scqos_domain_sdk_prototype-0.1.0-py3-none-any.whl
.test-venv/bin/python -m pip install pytest==9.1.1
.test-venv/bin/python -m pytest -q tests
```

Pytest is a test-only dependency; its installation requires network access unless supplied locally. On Windows replace `.test-venv/bin/python` with `.test-venv\Scripts\python.exe`. These are the bundled subset of tests, not the original 320-test regression closure.

The manifest is unsigned. It detects changed bytes relative to its recorded hashes; an attacker replacing both artifacts and manifest can defeat that check. A trusted, independently obtained commit ID or authenticated manifest is needed to anchor provenance.

## Licensing

No open-source license has been selected. Public inspection is the purpose of this repository; publication does not grant redistribution or commercial-use rights. Licensing remains a separate owner decision.
