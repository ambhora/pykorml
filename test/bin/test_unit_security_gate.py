# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------
"""The security gate script that the security-gate CI job runs."""

import json as _json
import pathlib as _pathlib
import subprocess as _subprocess
import sys as _sys

import pytest

_SCRIPT = _pathlib.Path(__file__).resolve().parents[2] / ".gitlab" / "scripts" / "security_gate.py"


def _report(*, path: _pathlib.Path, findings: list[dict]) -> None:
    path.write_text(_json.dumps({"vulnerabilities": findings}), encoding="utf-8")


def _finding(*, severity: str) -> dict:
    return {
        "severity": severity,
        "name": f"{severity} finding",
        "location": {"file": "src/example.py", "start_line": 7},
    }


def _run(*, directory: _pathlib.Path) -> _subprocess.CompletedProcess[str]:
    return _subprocess.run(
        [_sys.executable, str(_SCRIPT)],
        cwd=directory,
        text=True,
        capture_output=True,
        check=False,
    )


@pytest.mark.parametrize(
    ("secrets", "sast", "status"),
    [
        ([], [], 0),
        ([], [_finding(severity="Medium")], 0),
        ([], [_finding(severity="High")], 1),
        ([], [_finding(severity="Critical")], 1),
        ([_finding(severity="Info")], [], 1),
    ],
)
def test_exit_status_follows_the_blocking_findings(
    tmp_path: _pathlib.Path, secrets: list, sast: list, status: int
) -> None:
    _report(path=tmp_path / "gl-secret-detection-report.json", findings=secrets)
    _report(path=tmp_path / "gl-sast-report.json", findings=sast)

    result = _run(directory=tmp_path)

    assert result.returncode == status, result.stdout
    for finding in [*secrets, *sast]:
        assert f"src/example.py:7: {finding['name']}" in result.stdout


def test_missing_reports_pass(tmp_path: _pathlib.Path) -> None:
    result = _run(directory=tmp_path)
    assert result.returncode == 0
    assert "not produced in this pipeline" in result.stdout
