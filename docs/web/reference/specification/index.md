# Specification


`korml` is an indentation-based markup language like YAML, and therefore, by default the  grammar of the
language needs a stateful grammar like PEG. However, PEG is quite complex and can be difficult to reason about. On the
other hand, inspired from Python, one could preprocess the input to generate a stream of pre-tokens that includes
`INDENT` and `DEDENT` tokens, and then can use a much simpler EBNF grammar to parse the token stream.


Building on the idea of a multi-pass parser, we divide our parsing process into three stages:

1. **Layout Specification**: Define the rules for how indentation determine the structure of the document.
2. **Lexer Specification**: Define how to tokenize the input text, including handling of indentation and special
characters.
3. **Parser Specification**: Define the grammar for how tokens can be combined to form valid documents.

One of the advantages of separating the lexer and parser specification is  the allowance in future of using stream-based
parsing, where the lexer can produce tokens on-the-fly as the parser consumes them, rather than needing to generate the
entire token stream upfront.

## Layout Grammar

The layout grammar defines how physical source lines are interpreted as a
hierarchical block structure. It is specified in terms of indentation levels and
the layout tokens `INDENT`, `DEDENT`, `BLANK`, and `UNLEXED`.

The layout grammar is not context-free over raw characters, because the meaning
of a line depends on the indentation stack established by previous non-blank
lines. Therefore, the grammar is specified operationally.

### Layout Tokens

| Token | Meaning |
|---|---|
| `INDENT` | Opens a nested layout block |
| `DEDENT` | Closes one nested layout block |
| `BLANK` | Preserved blank or whitespace-only physical line |
| `UNLEXED` | Non-blank physical line content, excluding leading indentation |

### Indentation Rules

1. Indentation is measured as the number of leading spaces.
2. Tabs are not valid indentation characters.
3. Blank lines produce `BLANK` but do not change the current indentation level.
4. The indentation width is inferred from the first indented non-blank line.
5. Each non-blank line indentation must be a multiple of the inferred width.
6. An increase in indentation opens a new layout block and emits `INDENT`.
7. A decrease in indentation closes layout blocks and emits one or more `DEDENT`.
8. A dedent is valid only if it returns to a previously established indentation level.
9. End-of-file closes all remaining open layout blocks.


## Lexer Specification

The lexer specification can be found at [lexer](lexer)
