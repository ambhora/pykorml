<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2025 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# korml - Kosha's Reduced Markup Language


korml is the Python implementation of [Korml](https://ambhora.github.io/korml/),
a small, indentation-based markup language for configuration-like documents.
Its v0 form is the JSON-shaped, single-document subset of YAML.

```python
import korml

assert korml.loads("name: example\n").to_builtin() == [{"name": "example"}]
```

Development uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync
uv run pytest
uv run ruff check
CPDOCS_CURRENT_BRANCH=main uv run --group docs properdocs build --strict
```
