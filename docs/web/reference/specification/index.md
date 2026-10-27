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
hierarchical block structure. It is applied to each document body separately
(v0: the whole source; v1: the lines between `---` and `...`) and adds the layout
tokens `INDENT`, `DEDENT` and `NEWLINE` to the token stream.

The layout grammar is not context-free over raw characters, because the meaning
of a line depends on the indentation stack established by previous lines.
Therefore, the grammar is specified operationally.

### Layout Tokens

| Token | Meaning |
|---|---|
| `INDENT` | Opens a nested layout level |
| `DEDENT` | Closes one nested layout level |
| `NEWLINE` | Ends a content line |

### Lines That Take Part

Blank lines (empty, whitespace only, or whitespace and a comment), the content
lines of a block scalar, and the continuation lines of a flow collection take no
part in layout. Every other line is a *content line*. Its indentation `c` is its
number of leading spaces; a tab in the leading whitespace of a content line is an
error.

### Indentation Rules

The state is a stack `S` of columns, initially `[0]`, and the indentation width
`w`, initially unknown. For each content line, before its tokens:

1. If `c > top(S)`: if `w` is unknown, set `w = c - top(S)`. Then `c` must equal
   `top(S) + w`. Push `c` and emit `INDENT`.
2. If `c < top(S)`: pop and emit `DEDENT` while `top(S) > c`. Then `top(S)` must
   equal `c`: a dedent returns only to an open level.
3. Otherwise nothing.

The width `w` is inferred once per document, from its first indented content
line (or from the first content line of a block scalar, if that comes first), and
is any positive integer. Every level of the document then indents by exactly `w`.
The root node starts at column 0.

Within a line, a sequence dash is followed by exactly one space, a line break, a
comment (after whitespace) or the end of input. When one space and further content
follow the dash on the same line (a *compact entry*, such as `- key: value` or
`- - a`), that content starts at column `d + 2`, where `d` is the column of the
dash: push `d + 2` and emit `INDENT` right after the dash. Compact entries nest,
and a compact level does not set `w`. A compact mapping continues on the next
lines at column `d + 2`:

```yaml
- key: value
  other: value
- - a
  - b
```

At the end of each content line emit `NEWLINE`, also at the end of input if the
last content line has no line break. At the end of the document body, pop every
level above 0, emitting one `DEDENT` each.

A sequence that is the value of a key is indented by exactly `w`, like any other
block value; a sequence at the column of its key is an error:

```yaml
key:
  - a     # valid
other:
- a       # error
```


## Lexer Specification

The lexer specification can be found at [lexer](lexer.md)
