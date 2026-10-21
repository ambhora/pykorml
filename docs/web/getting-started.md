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

## Errors

Every error korml raises for invalid input is a `korml.KormlError`. Lexer
errors name the source and the position:

```python
try:
    korml.loads('a: "x\n', filename="app.korml")
except korml.KormlError as error:
    print(error)
```

```text
LexError: unterminated double-quoted scalar
  --> app.korml:1:4
```

## The command line

`korml lex` prints the tokens of a source, as JSON or as text:

```bash
korml lex --input app.korml --output-format text
```
