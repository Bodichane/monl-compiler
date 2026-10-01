# 🟢 Phase 6 — Complete System (Closed Loop)

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Goal
The goal of this phase is to bring together all software components developed earlier (`parser.py`, `ast_validator.py`, `generator.py`) in a single central orchestrator. Validation is based on the compiler's ability to instantly reconfigure the entire target software infrastructure whenever the DSL source file changes.

## Orchestrator Implementation (`src/main.py`)
A centralized entry point in the form of a Python command-line interface (CLI) was developed. It automates the sequential flow:
1. Read and validate raw syntax through Lark.
2. Validate AST business and semantic rules (security, actors, references).
3. Generate physical technical artifacts (`schema.sql` and `app.py`).

## Closed-Loop Test
Validation was exercised by switching compilation from one use case to another:
- `python3 src/main.py` -> Instantly generates the full architecture for `TodoList`.
- `python3 src/main.py exemples/02_blog.ml` -> Immediately overwrites and reconfigures the database and FastAPI API for the `TechBlog` business domain.

The pipeline is smooth, synchronous, and has no side effects.
