# ------------------------------------------------------------------------------
# SPDX-License-Identifier: Apache-2.0
# Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
# ------------------------------------------------------------------------------

"""Every function in the package describes its inputs and its return value.

cpdocs only sees public names and only asks that they have some documentation.
This looks at the signature of every function, private ones and nested ones
included: a docstring with one @param per parameter, in order, and a @return
unless the function returns None. A @param for a parameter the function does
not have fails too, so the fields cannot go stale.

cpdocs splits a docstring on blank lines and reads a paragraph as one field, so
each field must be a paragraph of its own: two @param lines in one paragraph
render as a single parameter that swallows the other.
"""

import ast
import pathlib
import re

import pytest

_SOURCE_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "korml"
_PARAM_PATTERN = re.compile(r"@param\s+(\*{0,2}\w+)\s+\S")
_RETURN_PATTERN = re.compile(r"@returns?\s+\S")
_FIELD_PATTERN = re.compile(r"^\s*@(param|returns?)\b", re.MULTILINE)


def _walk(body: list[ast.stmt], prefix: str) -> list[tuple[str, ast.FunctionDef]]:
    """
    Return the functions under body, each with its dotted name.

    @param body The statements to walk.

    @param prefix The dotted name of what encloses them.

    @return The name and the node of each function.
    """
    found: list[tuple[str, ast.FunctionDef]] = []

    for node in body:
        if isinstance(node, ast.FunctionDef):
            found.append((prefix + node.name, node))
            found.extend(_walk(node.body, f"{prefix}{node.name}."))
        elif isinstance(node, ast.ClassDef):
            found.extend(_walk(node.body, f"{prefix}{node.name}."))

    return found


def _functions() -> list[tuple[str, ast.FunctionDef]]:
    """
    Return every function of the package.

    @return The name, with its file, and the node of each function.
    """
    found: list[tuple[str, ast.FunctionDef]] = []

    for path in sorted(_SOURCE_ROOT.rglob("*.py")):
        name = path.relative_to(_SOURCE_ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        found.extend((f"{name}:{qualified}", node) for qualified, node in _walk(tree.body, ""))

    return found


_FUNCTIONS = _functions()


def _parameters(node: ast.FunctionDef) -> list[str]:
    """
    Return the names of the inputs of a function.

    @param node The function.

    @return The names, without self and cls.
    """
    arguments = node.args
    named = arguments.posonlyargs + arguments.args + arguments.kwonlyargs
    names = [argument.arg for argument in named]
    names += [argument.arg for argument in (arguments.vararg, arguments.kwarg) if argument]
    return [name for name in names if name not in ("self", "cls")]


def _returns_a_value(node: ast.FunctionDef) -> bool:
    """
    Return whether a function returns something a caller can use.

    @param node The function.

    @return False for __init__ and for a function annotated as returning None.
    """
    if node.name == "__init__":
        return False

    returns = node.returns
    return not (isinstance(returns, ast.Constant) and returns.value is None)


def test_the_package_was_walked() -> None:
    assert len(_FUNCTIONS) > 250


@pytest.mark.parametrize(("name", "node"), _FUNCTIONS, ids=[name for name, _ in _FUNCTIONS])
def test_function_describes_its_inputs_and_return_value(name: str, node: ast.FunctionDef) -> None:
    docstring = ast.get_docstring(node)
    assert docstring, f"{name} has no docstring"

    # The paragraphs as cpdocs reads them.
    paragraphs = [" ".join(block.split()) for block in re.split(r"\n\s*\n", docstring)]
    fields = [paragraph for paragraph in paragraphs if paragraph.startswith("@")]
    params = [match.group(1) for field in fields if (match := _PARAM_PATTERN.match(field))]
    returns = [field for field in fields if _RETURN_PATTERN.match(field)]

    for block in re.split(r"\n\s*\n", docstring):
        count = len(_FIELD_PATTERN.findall(block))
        assert count <= 1, f"{name} has {count} fields in one paragraph"

    assert params == _parameters(node), f"{name} documents {params}, not {_parameters(node)}"
    assert len(returns) == int(_returns_a_value(node)), f"{name} return is not described right"
    assert not re.search(r"^(Args|Returns):$", docstring, re.MULTILINE), f"{name} is not @param"


def test_cpdocs_reads_one_field_per_paragraph() -> None:
    html = pytest.importorskip("cpdocs.rendering.html")

    separate = html._documentation_description("Text.\n\n@param a One.\n\n@param b Two.")
    together = html._documentation_description("Text.\n\n@param a One.\n@param b Two.")

    assert "<code>b</code>" in separate
    assert "<code>b</code>" not in together
