<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# korml

korml is the Python implementation of Korml, Kosha's reduced markup
language: a small, indentation-based language for configuration-like
documents. The language itself is specified separately, in the
[Korml specification](https://ambhora.github.io/korml/).

Korml comes in two versions. A v0 source is a single implicit document and
looks like small, JSON-shaped YAML:

```yaml
name: example
tags: [small, portable]
limits:
  ranks: 4
  threads: 8
```

A v1 source starts with a version directive and holds one or more explicit
documents:

```text
%!korml version 1.0
---
name: example
...
```

Korml leaves out the parts of YAML that make it hard to parse and edit:
anchors and aliases, tags, complex keys, merge keys and implicit typing.
Every scalar is text; deciding that `3` is a number is up to the
application or a schema.

The package reads and writes Korml, keeps the tokens of what it read so
that every value knows its position in the source, and validates documents
against a schema. It has no dependencies outside the Python standard
library.

[Getting started](getting-started.md) shows how to use it, and the
[Python API](api.md) lists the functions and classes.
