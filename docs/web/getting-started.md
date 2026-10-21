<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# Getting started

korml needs Python 3.11 or later and nothing else. Install it from a
checkout of its repository:

```bash
uv pip install .
```

## Reading Korml

`korml.loads` reads Korml text and `korml.load` reads a file. Both detect
the version from the source and return a stream of documents; a v0 source
gives a stream with one document:

```python
import korml

stream = korml.loads("name: example  # the project name\n")
assert stream.version is korml.Version.v0
assert stream.to_builtin() == [{"name": "example"}]
```

`to_builtin` turns the stream into a list with one Python value per
document: a mapping becomes a `dict`, a sequence a `list`, and every scalar
a `str`. Korml has no implicit typing, so a `3` in the source is the string
`"3"`.

A v1 source holds one or more documents, each opened by `---` and closed by
`...`:

```python
source = "%!korml version 1.0\n---\na: 1\n...\n---\nb: [x, y]\n...\n"
assert korml.loads(source).to_builtin() == [{"a": "1"}, {"b": ["x", "y"]}]
```

## The document model

The values of a stream are `korml.Mapping`, `korml.Sequence` and
`korml.Scalar` objects. They behave like the Python containers, and each
keeps the tokens it was read from, so a tool can report where a value
appears in the source:

```python
mapping = korml.loads("name: example\n")[0]
scalar = mapping["name"]
print(scalar.value, scalar.span.start.line)
```

## Writing Korml

`korml.dumps` turns a Python value or a stream into Korml text, and
`korml.dump` writes it to a file. Mappings need string keys, and every
scalar must be a string. The default is v1:

```python
text = korml.dumps({"name": "example"}, version=korml.Version.v0)
assert text == '"name": "example"\n'
```

## Editing without reformatting

`dumps` writes a new document. To change some values of an existing source
and keep everything else, comments and layout included, pass values of the
parsed stream to `korml.edit` with the strings they become:

```python
source = "# the project\nname: example  # shown in the title\n"
stream = korml.loads(source)

edited = korml.edit(stream=stream, replacements=[(stream[0]["name"], "demo")])
assert edited == '# the project\nname: "demo"  # shown in the title\n'
```

A replacement is always written as a double-quoted scalar, so no string can
turn into structure. `edit` parses its result again and raises an error
unless it reads back as the original with the replacements applied.

## Errors

Every error korml raises for invalid input is a `korml.KormlError`, and
names the source and the position:

```python
try:
    korml.loads('a: "x\n', filename="app.korml")
except korml.KormlError as error:
    print(error)
```

```text
LexError: unterminated double-quoted scalar
  --> app.korml:1:4
  |
1 | a: "x
  |    ^
  = code: UNEXPECTED_CHARACTER
```

A program that must not print what it read, such as one reading secrets,
uses `error.describe(quote_source=False)`, which gives the message and the
position without the source line.

## The command line

`korml lex` prints the tokens of a source, as JSON or as text:

```bash
korml lex --input app.korml --output-format text
```

## Processing untrusted input

`load` and `loads` enforce default limits of 8 MiB of UTF-8 input, 100,000
lexer tokens, 128 levels of nesting, and one million cumulative parse-token
visits. Inputs exceeding these limits raise a `KormlError` with a diagnostic
code. The CLI `lex` command applies the byte and token limits as well.

For a trusted application that intentionally processes larger documents,
adjust the byte, token and work limits independently:

```python
stream = korml.load(
    "large.korml",
    max_input_bytes=32 * 1024 * 1024,
    max_tokens=250_000,
    max_parse_work=5_000_000,
)
```

Passing `None` disables a particular limit; the fixed nesting guard remains
in place. Do not disable limits for documents supplied by untrusted users.

Both `korml.dump` and the CLI's file output atomically replace their target
once rendering succeeds. Output symlinks are replaced, not followed. Files
in symlinked directories are supported. An existing regular file's mode is
preserved on POSIX systems; creating a new file uses restricted permissions.
