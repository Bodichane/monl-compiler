# 🟢 Phase 0 — Scope, Vision, and Secure Positioning

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Starting observation
Many beginners or intermediate developers use AI (iterative prompts, “vibe coding”) to create applications. They quickly end up with a critical mass of code they do not understand and therefore cannot maintain, extend, or secure properly.

## monl's positioning
monl is not another application generator or a consumer no-code tool. It is a structured language designed specifically to make “vibe coding” traceable and secure. The user expresses a need through a clear declarative specification rather than an unstructured free-form prompt. This gives AI a verifiable direction, limiting its role to narrowly scoped, local interpretation.

## Target Architecture: Deterministic Foundation + Bounded AI Escape Hatch
The compilation pipeline strictly separates infrastructure from arbitrary business logic:

1. **The Foundation (conventional compiler)**: Generates everything standard, repetitive, and predictable (database schema, API routes, authentication, role-based access control, and workflows).
   - **Deterministic**: The same specification always produces the same code, bit for bit.
   - **Secure by default**: Parameterized queries, strict validation, and systematic access control are applied by construction.
   - **Traceable**: Every generated line of code corresponds to a fixed rule and an identifiable portion of the specification.

2. **The AI Escape Hatch (`custom` blocks)**: Used only for business logic that the DSL cannot express natively. AI then generates an isolated, sealed function, called by deterministic code without ever mixing into it. This makes it easier to perform a strengthened security review (audit) of that specific code before integration.

## Long-Term Goal
Make generated code (Python, SQL, etc.) as secondary to the end user as assembly language is to a high-level developer today, ensuring that no abstraction leak contaminates the domain covered by monl.
