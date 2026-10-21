# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""How errors describe where they are."""

import pytest

import korml


def test_lex_error_quotes_the_whole_line_with_the_caret_under_the_error() -> None:
    with pytest.raises(korml.LexError) as exc_info:
        korml.loads('a: "x\n', filename="app.korml")

    lines = str(exc_info.value).splitlines()

    assert lines[1] == "  --> app.korml:1:4"
    assert lines[3] == '1 | a: "x'
    assert lines[4] == "  |    ^"
