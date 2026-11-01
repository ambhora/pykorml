# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import dataclasses
import enum
import importlib.metadata
import traceback
import typing

import korml.error


class AnsiCode(enum.Enum):
    """The terminal escape sequences the report uses."""

    RESET = "\033[0m"
    """End every style."""
    BOLD = "\033[1m"
    """Bold text."""
    RED = "\033[31m"
    """Red text."""
    YELLOW = "\033[33m"
    """Yellow text."""
    CYAN = "\033[36m"
    """Cyan text."""


class DiagnosticExitCode(enum.IntEnum):
    """The exit statuses of the command line beyond success and user error."""

    # sysexits.h: an internal software error. argparse uses 2 for invalid
    # usage, so an internal error needs another status.
    INTERNAL_ERROR = 70
    """The status of an internal failure, a bug in korml."""


@dataclasses.dataclass(frozen=True)
class ColorPolicy:
    """Whether the report may use terminal escape sequences."""

    enabled: bool
    """Whether styles are applied."""

    @classmethod
    def from_stream(cls, stream: typing.Any) -> "ColorPolicy":
        """Return the policy for stream: colour only on a terminal."""
        enabled = hasattr(stream, "isatty") and stream.isatty()
        return cls(enabled=enabled)


@dataclasses.dataclass(frozen=True)
class TextStyler:
    """Applies terminal styles to text, as a color policy allows."""

    color_policy: ColorPolicy
    """The policy that decides whether styles are applied."""

    def style(self, text: str, *styles: AnsiCode) -> str:
        """Return text with styles applied, or unchanged if colour is off."""
        if not self.color_policy.enabled:
            return text

        prefix = "".join(style.value for style in styles)
        return prefix + text + AnsiCode.RESET.value


def issues_url() -> str | None:
    """
    Return the issue tracker named by the installed package metadata.

    That is the Project-URL entry labelled Issues, which comes from
    [project.urls] in pyproject.toml, so the bug report and the package
    metadata never disagree. Without installed metadata, as when korml runs
    from a source tree, or without an Issues entry, it is None: the report
    then says where to look rather than naming a URL that may be wrong.
    """
    try:
        metadata = importlib.metadata.metadata("korml")
    except importlib.metadata.PackageNotFoundError:
        return None

    for entry in metadata.get_all("Project-URL") or []:
        label, _, url = entry.partition(",")
        if label.strip().lower() == "issues" and url.strip() != "":
            return url.strip()

    return None


@dataclasses.dataclass(frozen=True)
class BugReportConfig:
    """What the report needs to know about the project."""

    url: str | None = dataclasses.field(default_factory=issues_url)
    """The issue tracker, or None if the package metadata names none."""


@dataclasses.dataclass(frozen=True)
class InternalFailureReport:
    """The report printed for an exception that korml did not expect."""

    exc: Exception
    """The exception being reported."""
    styler: TextStyler
    """The styles of the report."""
    config: BugReportConfig = dataclasses.field(default_factory=BugReportConfig)
    """What the report needs to know about the project."""

    def _where_to_report(self) -> str:
        if self.config.url is not None:
            return f"If you would like to report this, please open an issue at: {self.config.url}"

        return (
            "If you would like to report this, please open an issue in the korml issue "
            "tracker, named by the Issues entry of [project.urls] in the pyproject.toml "
            "of korml and in the metadata of the installed package."
        )

    def render(self) -> str:
        """Return the report as text, with untrusted text escaped."""
        return "\n".join(
            [
                self.styler.style(
                    "========================================", AnsiCode.RED, AnsiCode.BOLD
                ),
                self.styler.style("ERROR: KORML INTERNAL FAILURE", AnsiCode.RED, AnsiCode.BOLD),
                self.styler.style(
                    "========================================", AnsiCode.RED, AnsiCode.BOLD
                ),
                "",
                self.styler.style("KORML encountered an unexpected internal error.", AnsiCode.BOLD),
                "This usually indicates a bug in KORML rather than an error in your input.",
                "",
                self.styler.style(self._where_to_report(), AnsiCode.YELLOW),
                "",
                "A bug report is most helpful when it includes:",
                "",
                "  • a short issue title, for example:",
                "      [BUG] <short description>",
                "",
                "  • a minimal working example (MWE), including:",
                "      - the smallest input that reproduces the problem",
                "      - the exact command used to trigger it",
                "",
                "  • the diagnostic report below",
                "",
                "You may copy and paste the following section into the issue if useful.",
                "",
                self.styler.style(
                    "----- BEGIN KORML BUG REPORT -----", AnsiCode.CYAN, AnsiCode.BOLD
                ),
                self.styler.style("## Error Summary", AnsiCode.CYAN, AnsiCode.BOLD),
                f"- Exception type: {type(self.exc).__name__}",
                f"- Exception message: {_escape_lines(str(self.exc))}",
                "",
                self.styler.style("## Traceback", AnsiCode.CYAN, AnsiCode.BOLD),
                "```text",
                _escape_lines(traceback.format_exc().rstrip()),
                "```",
                self.styler.style("----- END KORML BUG REPORT -----", AnsiCode.CYAN, AnsiCode.BOLD),
            ]
        )


def _escape_lines(text: str) -> str:
    """
    Escape the unprintable characters of each line of text, keeping the line breaks.

    An exception message, and the traceback that repeats it, may quote the
    input that caused the failure, so they are untrusted text: a terminal
    control in them must not reach the terminal raw, as in every other
    diagnostic (see korml.error.escape_controls).
    """
    return "\n".join(korml.error.escape_controls(line) for line in text.split("\n"))


def render_internal_failure_report(exc: Exception, stream: typing.Any) -> str:
    """Return the report for exc, styled for the terminal stream if it is one."""
    color_policy = ColorPolicy.from_stream(stream)
    styler = TextStyler(color_policy=color_policy)
    report = InternalFailureReport(exc=exc, styler=styler)
    return report.render()
