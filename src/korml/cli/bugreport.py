# --------------------------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# --------------------------------------------------------------------------------------------------

import dataclasses
import enum
import traceback
import typing


class AnsiCode(enum.Enum):
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[31m"
    YELLOW = "\033[33m"
    CYAN = "\033[36m"


class DiagnosticExitCode(enum.IntEnum):
    INTERNAL_ERROR = 2


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


@dataclasses.dataclass(frozen=True)
class BugReportConfig:
    url: str = "https://github.com/korml/pykorml/issues"


@dataclasses.dataclass(frozen=True)
class InternalFailureReport:
    exc: Exception
    styler: TextStyler
    config: BugReportConfig = dataclasses.field(default_factory=BugReportConfig)

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
                self.styler.style(
                    f"If you would like to report this, please open an issue at: {self.config.url}",
                    AnsiCode.YELLOW,
                ),
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
                f"- Exception message: {self.exc}",
                "",
                self.styler.style("## Traceback", AnsiCode.CYAN, AnsiCode.BOLD),
                "```text",
                traceback.format_exc().rstrip(),
                "```",
                self.styler.style("----- END KORML BUG REPORT -----", AnsiCode.CYAN, AnsiCode.BOLD),
            ]
        )


def render_internal_failure_report(exc: Exception, stream: typing.Any) -> str:
    color_policy = ColorPolicy.from_stream(stream)
    styler = TextStyler(color_policy=color_policy)
    report = InternalFailureReport(exc=exc, styler=styler)
    return report.render()
