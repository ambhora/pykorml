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
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


class DiagnosticExitCode(enum.IntEnum):
    # sysexits.h: an internal software error. argparse uses 2 for invalid
    # usage, so an internal error needs another status.
    INTERNAL_ERROR = 70


@dataclasses.dataclass(frozen=True)
class ColorPolicy:
    enabled: bool

    @classmethod
    def from_stream(cls, stream: typing.Any) -> "ColorPolicy":
        enabled = hasattr(stream, "isatty") and stream.isatty()
        return cls(enabled=enabled)


@dataclasses.dataclass(frozen=True)
class TextStyler:
    color_policy: ColorPolicy

    def style(self, text: str, *styles: AnsiCode) -> str:
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
    url: str | None = dataclasses.field(default_factory=issues_url)


@dataclasses.dataclass(frozen=True)
class InternalFailureReport:
    exc: Exception
    styler: TextStyler
    config: BugReportConfig = dataclasses.field(default_factory=BugReportConfig)

    def _where_to_report(self) -> str:
        if self.config.url is not None:
            return f"If you would like to report this, please open an issue at: {self.config.url}"

        return (
            "If you would like to report this, please open an issue in the korml issue "
            "tracker, named by the Issues entry of [project.urls] in the pyproject.toml "
            "of korml and in the metadata of the installed package."
        )

    def render(self) -> str:
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
    color_policy = ColorPolicy.from_stream(stream)
    styler = TextStyler(color_policy=color_policy)
    report = InternalFailureReport(exc=exc, styler=styler)
    return report.render()
