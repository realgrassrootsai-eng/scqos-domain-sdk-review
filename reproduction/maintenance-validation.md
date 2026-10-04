# Maintainer validation — packaging correction

2026-10-04, RINZLER WSL. This is maintainer validation, not independent reproduction.

Fresh test venv, bundled wheel installed with --no-index --no-deps, pytest 9.1.1:

- Bundled tests: 97 passed.
- Fresh-install verifier: passed.
- Payment and deployment conformance: 14 checks passed each.
- Comparison demo: eight receipts.

Runtime modules, wheel, and source archive match the original reproduced commit. Test path corrections and documentation changes are covered by the refreshed unsigned manifest. Original commit/tag retained. No new license grant made.
