<!--
- SPDX-License-Identifier: Apache-2.0
- Copyright (C) 2026 Jayesh Badwaik <j.badwaik@fz-juelich.de>
-->

# Compiler Design


The main objective of the `korml` language is to be able to provide a round-trippable YAML-like
language which has instrumentable syntax so that it is easy for tools to indicate line and column
information for error reporting and debugging, while at the same time being able to validate the
documents in the language against a schema.

At an implementation level, the goal is to keep parsers and emitters as formal as possible, while
still allowing the language to be specified using a simple, EBNF-like notation. Such a specification
is easier to reason about, maintain, and evolve over time. Indentation-based languages, however, do
not map directly to EBNF grammars, since indentation introduces context sensitivity that is not
naturally expressible in standard context-free formalisms.

A practical approach is to decompose the compiler into multiple stages. An initial preprocessing
stage resolves indentation into an explicit token stream, after which a conventional EBNF-style
grammar can be applied. The specification follows this design, as described in
[Specification](../../reference/specification/index.md).

The compiler is therefore structured as a three-stage pipeline:

1. **Indentation Processor**
   Processes the raw input document and converts indentation into an explicit structural
   representation (e.g., INDENT/DEDENT tokens). The output is a normalized token stream suitable for
   further processing.

2. **Lexer**
   Consumes the indentation-annotated stream and produces lexical tokens. Tokens are annotated with
   precise source locations (line and column) to support error reporting and diagnostics.

3. **Parser**
   Consumes the token stream and constructs a **Concrete Syntax Tree (CST)** representing the full
   syntactic structure of the document. Source location metadata from the lexer is attached to CST
   nodes to enable accurate debugging and validation. The parser also enforces syntactic correctness
   with respect to the language specification.

For round-tripping, an **emitter** is provided. It takes a CST as input and produces a `korml`
document. The emitter preserves semantic equivalence while handling formatting concerns, enabling
lossless or near-lossless reconstruction of the original input.

In many use cases, the full CST is not required beyond debugging or tooling. Programs typically
operate on an **Abstract Syntax Tree (AST)**, which captures the semantic structure without
retaining concrete syntax details such as formatting or layout. Given the prevalence of data-centric
workflows (e.g., Python dictionaries, JSON, YAML), a dictionary-like representation often serves as
a practical AST form for downstream consumers.

To bridge these needs, the system provides parsers and emitters for dictionary-based
representations, as well as an AST-like view over the CST. The dictionary form offers a convenient,
data-oriented interface but does not preserve enough information for round-tripping, as formatting
and other concrete syntax details are lost. In contrast, the AST-like view wraps CST nodes and
exposes a simplified, semantic interface without discarding information. Consumers can work with the
structure as if it were an AST, while the underlying CST—and thus full fidelity, including trivia
and source locations—remains accessible when needed. We now describe the different stages of the
compiler:

## Indentation Processor

The indentation processor is responsible for  taking in the raw input document and producing a token
stream that explicitly


## Lexer

## Parser

## AST Emitter

## AST Parser

## Emitter

## Writer

## Indentation Inserter



