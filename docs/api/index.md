<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->
# {{ project }} {{ version }}

The Python API of korml. The `korml` package exports the functions that read
and write Korml text and the classes of the document model:

```python
import korml

stream = korml.loads("name: example\n")
assert stream.to_builtin() == [{"name": "example"}]
```

The [project documentation](projectdocs:) describes the package, and the
[Korml specification](https://ambhora.github.io/korml/) the language.
