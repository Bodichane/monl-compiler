# 🟢 Phase 3 — The Syntax Parser

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Goal
The goal of this phase is to design a parser that can read a raw file written in the monl DSL (extension `.ml` — historically `.yaml`, before the project adopted its own extension) and convert it to a raw computer data structure in JSON format.

## Technical Choices
- **Language**: Python 3.10+
- **Library**: `lark` (LALR parser)
- **Indentation handling**: Adapt the native `PythonIndenter` module for monl (`MonlIndenter`) to cleanly capture logical blocks of 4 spaces without braces.

## Implementation (`src/parser.py`)
The parser uses a formal grammar that strictly defines the language keywords (`app`, `entity`, `relation`, `actor`, `rule`, `workflow`) and relies on the `Transformer` class to extract tokens.

## Validation and Test Criteria
The validation test ran successfully on the input file `exemples/01_todo_list.ml`.
The parser produces a stable dictionary of this kind:
- Correct extraction of entities (`User`, `Todo`) and their semantic primitive types.
- Capture of relation links (`hasMany`).
- Isolation of workflows and their associated CRUD action lists.

The result is fully predictable: the same source file always produces the same JSON dictionary.
