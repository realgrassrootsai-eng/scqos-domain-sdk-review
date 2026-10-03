"""Conformance detects broken adapters, rejects bad factories and reports CLI failure."""
from dataclasses import replace
from pathlib import Path
import json
import subprocess
import sys
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scqos_adapter_conformance import (PROBES, builtin_case, payment_case, deployment_case,
    resolve_factory, run_conformance)

@pytest.mark.parametrize("factory", [payment_case, deployment_case])
def test_complete_factory(factory):
    report = run_conformance(factory)
    assert report["passed"] is True and report["certification"] is False
    assert [r["check"] for r in report["checks"]] == list(PROBES)
    assert len(report["checks"]) == 14

def test_broken_writer_detected():
    def factory():
        case = payment_case()
        case.set_writer(lambda expected: None)
        return case
    report = run_conformance(factory)
    assert report["passed"] is False
    valid = next(r for r in report["checks"] if r["check"] == "valid_effect")
    assert valid["passed"] is False and valid["reason"] == "valid_effect_unverified"

def test_broken_approval_fixture_detected():
    def factory():
        case = deployment_case()
        case.authority = replace(case.authority, allowed_environment="wrong")
        return case
    assert run_conformance(factory)["passed"] is False

def test_factory_failure_opaque_and_all_checks_reported():
    def factory():
        raise RuntimeError("SECRET MUST NOT APPEAR")
    report = run_conformance(factory)
    assert not report["passed"] and len(report["checks"]) == 14
    assert "SECRET" not in json.dumps(report)
    assert all(r["reason"] == "RuntimeError" for r in report["checks"])

def test_factory_wrong_type_detected():
    report = run_conformance(lambda: object())
    assert not report["passed"]
    assert all(row["reason"] == "TypeError" for row in report["checks"])

@pytest.mark.parametrize("value", ["", "missing-colon", ":factory", "module:", "module:function.attr"])
def test_bad_factory_reference(value):
    with pytest.raises(ValueError):
        resolve_factory(value)

def test_external_factory_resolution():
    assert resolve_factory("scqos_adapter_conformance:payment_case") is payment_case

@pytest.mark.parametrize("factory", ["builtin-payment", "builtin-deployment"])
def test_cli_success(factory):
    result = subprocess.run([sys.executable, "-m", "scqos_adapter_conformance",
                             "--factory", factory], capture_output=True,text=True,check=True)
    assert json.loads(result.stdout)["passed"] is True

def test_cli_factory_error():
    result = subprocess.run([sys.executable, "-m", "scqos_adapter_conformance",
                             "--factory", "missing-colon"], capture_output=True,text=True)
    assert result.returncode == 2 and json.loads(result.stdout)["passed"] is False

def test_cli_behavior_failure(tmp_path):
    import os
    fixture = tmp_path/"broken_scqos_case.py"
    fixture.write_text("from scqos_adapter_conformance import payment_case\n"
        "def make_case():\n"
        "    case = payment_case()\n"
        "    case.set_writer(lambda value: None)\n"
        "    return case\n")
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(tmp_path) + os.pathsep + str(Path(__file__).resolve().parents[1])
    result = subprocess.run([sys.executable, "-m", "scqos_adapter_conformance",
        "--factory", "broken_scqos_case:make_case"], capture_output=True,text=True,env=environment)
    assert result.returncode == 1
    assert json.loads(result.stdout)["passed"] is False

@pytest.mark.parametrize("bad_path", ["../outside.whl", "/nonexistent/outside.whl"])
def test_install_verifier_rejects_manifest_path_escape(tmp_path, bad_path):
    manifest = dict(artifact_sha256={bad_path:"0"*64})
    (tmp_path/"MANIFEST.json").write_text(json.dumps(manifest))
    verifier = Path(__file__).resolve().parents[1]/"packages/scqos-domain-sdk/verify_installation.py"
    result = subprocess.run([sys.executable,str(verifier),str(tmp_path)],capture_output=True,text=True)
    assert result.returncode == 1 and json.loads(result.stdout)["error"] == "ValueError"

def test_install_verifier_rejects_modified_artifact(tmp_path):
    (tmp_path/"modified.whl").write_text("changed")
    (tmp_path/"MANIFEST.json").write_text(json.dumps(dict(artifact_sha256={"modified.whl":"0"*64})))
    verifier = Path(__file__).resolve().parents[1]/"packages/scqos-domain-sdk/verify_installation.py"
    result = subprocess.run([sys.executable,str(verifier),str(tmp_path)],capture_output=True,text=True)
    assert result.returncode == 1 and json.loads(result.stdout)["error"] == "ValueError"
