"""Verify the review wheel in a fresh environment outside the source checkout."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import venv

def main():
    bundle = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    manifest = json.loads((bundle/"MANIFEST.json").read_text())
    for relative, digest in manifest["artifact_sha256"].items():
        target = (bundle/relative).resolve()
        target.relative_to(bundle)
        if hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            raise ValueError("bundle_artifact_digest_mismatch")
    wheel_name = manifest["wheel"]
    if Path(wheel_name).name != wheel_name:
        raise ValueError("wheel_name_invalid")
    wheel = bundle/wheel_name
    expected = manifest["artifact_sha256"][wheel_name]
    if hashlib.sha256(wheel.read_bytes()).hexdigest() != expected:
        raise ValueError("wheel_digest_mismatch")
    with tempfile.TemporaryDirectory(prefix="scqos-install-check-") as temporary:
        root = Path(temporary)
        environment = root/"venv"
        venv.EnvBuilder(with_pip=True).create(environment)
        executable = environment/("Scripts/python.exe" if os.name == "nt" else "bin/python")
        clean = os.environ.copy()
        clean.pop("PYTHONPATH", None)
        clean.pop("PYTHONHOME", None)
        def run(arguments):
            return subprocess.run([str(executable), *arguments], cwd=root, env=clean,
                                  check=True, text=True, capture_output=True, timeout=120)
        run(["-m", "pip", "install", "--no-index", "--no-deps", str(wheel)])
        reports = []
        for name in ("builtin-payment", "builtin-deployment"):
            report = json.loads(run(["-m", "scqos_adapter_conformance", "--factory", name]).stdout)
            if report["passed"] is not True:
                raise RuntimeError("conformance_failed")
            reports.append(dict(adapter=name, passed=True, checks=len(report["checks"])))
        run(["-c", "import sys; import scqos_domain_sdk; assert sys.prefix != sys.base_prefix; "
                       "assert 'site-packages' in scqos_domain_sdk.__file__; "
                       "import scqos_synthetic_deployment_adapter; "
                       "assert 'boto3' not in sys.modules; assert 'web_chat' not in sys.modules"])
        rows = [json.loads(line) for line in run([str(bundle/"examples/run_scqos_domain_reuse_demo.py")]).stdout.splitlines()]
        if len(rows) != 8 or sum(r["receipt"]["writer_invoked"] for r in rows) != 2:
            raise RuntimeError("comparison_demo_failed")
    print(json.dumps(dict(passed=True, fresh_environment=True, network_dependencies=False,
                          source_checkout_required=False, conformance=reports, demo_receipts=len(rows)),
                     sort_keys=True))
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps(dict(passed=False, error=type(exc).__name__), sort_keys=True))
        raise SystemExit(1)
