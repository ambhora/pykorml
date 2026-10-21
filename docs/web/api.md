<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# Python API

cpdocs generates the reference of the Python API from the source of every
published version. The names most programs need are also exported by the
`korml` package itself, so `korml.loads` is `korml.api.loads`:

| Purpose | API |
| --- | --- |
| Read Korml text or a file | @apidocs::korml.api.loads, @apidocs::korml.api.load |
| Write Korml text or a file | @apidocs::korml.api.dumps, @apidocs::korml.api.dump |
| Change values and keep the layout | @apidocs::korml.api.edit |
| Work with the document model | @apidocs::korml.model.Stream, @apidocs::korml.model.Mapping, @apidocs::korml.model.Sequence, @apidocs::korml.model.Scalar |
| Catch failures | @apidocs::korml.error.KormlError and its subclasses |

## Versions

@apidocs-versions
