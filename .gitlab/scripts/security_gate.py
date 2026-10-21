# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------
"""Fail the pipeline on findings in GitLab's security reports.

Without GitLab Ultimate, scanner findings appear only in the report artifacts
and never fail a pipeline. This script fails on any detected secret and on
Critical or High SAST findings, and lists every finding. A report is missing
only when its scanner did not run in this pipeline, as in tag pipelines.

Run it in the directory that holds the downloaded reports.
"""

import json as _json
import pathlib as _pathlib
import sys as _sys


def describe(*, finding: dict) -> str:
    """Return one line naming the severity, location and title of a finding."""
    severity = finding.get("severity", "Unknown")
    location = finding.get("location", {})
    where = f"{location.get('file')}:{location.get('start_line')}"
    title = finding.get("name") or finding.get("message")
    return f"{severity}: {where}: {title}"


def check(*, path: _pathlib.Path, blocking: set[str] | None) -> bool:
    """Print the findings of one report; return whether any of them blocks.

    With blocking None, every finding blocks.
    """
    if not path.exists():
        print(f"{path.name}: not produced in this pipeline")
        return False
    findings = _json.loads(path.read_text(encoding="utf-8"))["vulnerabilities"]
    print(f"{path.name}: {len(findings)} finding(s)")
    failed = False
    for finding in findings:
        print(f"  {describe(finding=finding)}")
        if blocking is None or finding.get("severity") in blocking:
            failed = True
    return failed


def main() -> int:
    """Check every report in the working directory; return the exit status."""
    secrets = check(path=_pathlib.Path("gl-secret-detection-report.json"), blocking=None)
    sast = check(path=_pathlib.Path("gl-sast-report.json"), blocking={"Critical", "High"})
    return 1 if secrets or sast else 0


if __name__ == "__main__":
    _sys.exit(main())
