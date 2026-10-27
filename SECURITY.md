<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# Security Policy

## Reporting a Vulnerability

Please report security vulnerabilities privately, not in a public issue,
merge request or pull request. Use either:

- GitHub private vulnerability reporting: open the repository's **Security**
  tab and choose **Report a vulnerability**; or
- email to [j.badwaik@fz-juelich.de](mailto:j.badwaik@fz-juelich.de).

Include the korml version, the smallest input or program that shows the
problem, and what an attacker gains from it. Please keep the report
confidential until a fix is released or a disclosure date is agreed with
the maintainer.

## Supported Versions

Security fixes go into the latest release only.

## Scope

korml parses untrusted text. Reports are welcome in particular for inputs
that make `korml.loads` or `korml.load` raise anything other than a
`korml.KormlError`, use unbounded time or memory despite the default
limits, or read a document differently from the Korml rules; and for
values that make `korml.dumps` write a document that reads back
differently.
