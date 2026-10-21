# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------
"""Enforce blocking findings and the presence of every required scanner report.

GitLab security templates upload scanner findings even on editions without the
vulnerability approval features. A missing or malformed report cannot be treated
as a clean scan. Scanners intentionally disabled for a pipeline must be managed
explicitly in CI configuration, not silently skipped here.
"""

import json as _json
import pathlib as _pathlib
import sys as _sys


class ReportError(Exception):
    """The security report is absent or malformed."""


def describe(*, finding: dict) -> str:
    """Return one line naming the severity, location and title of a finding."""
    severity = finding.get("severity", "Unknown")
    location = finding.get("location") or {}
    where = f"{location.get('file')}:{location.get('start_line')}"
    title = finding.get("name") or finding.get("message")
    return f"{severity}: {where}: {title}"


def check(*, path: _pathlib.Path, blocking: set[str] | None) -> bool:
    """Show the findings in a valid report and return whether any is blocking."""
    if not path.is_file():
        raise ReportError(f"{path.name}: required scanner report is missing")
    try:
        report = _json.loads(path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, UnicodeError, OSError) as exc:
        raise ReportError(f"{path.name}: invalid or unreadable report: {exc}") from exc

    if not isinstance(report, dict) or not isinstance(report.get("vulnerabilities"), list):
        raise ReportError(f"{path.name}: report must contain a vulnerabilities list")

    findings = report["vulnerabilities"]
    print(f"{path.name}: {len(findings)} finding(s)")
    failed = False
    for finding in findings:
        if not isinstance(finding, dict) or not isinstance(finding.get("severity"), str):
            raise ReportError(f"{path.name}: vulnerability has no valid severity")
        print(f"  {describe(finding=finding)}")
        if blocking is None or finding["severity"] in blocking:
            failed = True
    return failed


def main() -> int:
    """Check SAST, IaC SAST and secret detection; fail closed."""
    failed = False
    report_rules = (
        ("gl-secret-detection-report.json", None),
        ("gl-sast-report.json", {"Critical", "High"}),
        ("gl-iac-sast-report.json", {"Critical", "High"}),
    )
    for filename, blocking in report_rules:
        try:
            failed = check(path=_pathlib.Path(filename), blocking=blocking) or failed
        except ReportError as exc:
            print(f"error: {exc}", file=_sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    _sys.exit(main())
