# 🟢 Phase 4 — Abstract Syntax Tree (AST) & Static Security Audit

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Goal
The Abstract Syntax Tree (AST) normalizes the raw dictionary produced by the Parser (Phase 3). This phase implements the **Static Security Analysis** engine (axis: “Secure and audited”), designed to intercept architectural vulnerabilities during compilation, before infrastructure files are generated.

## Structural Consistency Checks (`src/ast_validator.py`)
The validator resolves logical dependencies and catches specification inconsistencies:
1. **Actor declarations**: Strictly check that every actor profile attached to a workflow was previously listed in the global `actor` block.
2. **Dotted notation resolution**: Precisely support nested field targets (e.g. `Order.status`). The analyzer dynamically isolates the master entity (`Order`) to validate its existence in the data schema before validating the attribute, avoiding compilation crashes on complex applications.

## Static Security Audit Algorithm
The static analyzer actively tracks two major architectural vulnerabilities:

### 1. Detecting Unprotected Destructive Privileges (Orphan Delete)
The engine scans all workflows. If it detects a `Delete` action on an entity while the workflow is attached to a generic actor other than the administrator (`Admin`), the compiler emits a critical `[CRITICAL_WARNING]` alert so the technical team must review this specification vulnerability.

### 2. Auditing AI Block Isolation & Dynamic Actor Resolution
To secure data use inside the AI escape hatch (`custom` blocks), the compiler applies a call-graph algorithm:
- **Problem addressed**: `custom` blocks do not natively have an assigned actor. The analyzer maps the dependency tree and identifies every workflow that invokes the AI function through an `Execute` instruction.
- **Leak analysis**: If an AI block receives as an `input` a field protected by a strict confidentiality constraint (`restrictedTo`), the engine compares that restriction against all actors allowed to execute this block.
- **Alert**: If an unauthorized actor can indirectly trigger the AI block, a `[SECURITY_AUDIT]` security log is generated. The compiler then directs automatic anonymization filters to be injected at the Sandbox level to protect the data.

## Structure of the Normalized, Secured AST
Once the audit passes, the AST produces a structured object with four sealed pillars, ready for the deterministic generator:
- `meta`: Metadata and history of security audit logs.
- `schema`: Pure relational data structure (Entities, Attributes, Relations).
- `security`: Actor profiles, field filtering rules, and CRUD access rights.
- `sandbox_ai`: I/O signatures and isolation instructions for automated LLM completion.
