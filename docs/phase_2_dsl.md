# 🟡 Phase 2 — DSL Design

> **Historical document.** This page describes a design stage; it does not
> replace the current architecture. See `README.md` and `CODEBASE_AUDIT.md`.

## Syntax Principles
- **Declarative & Readable**: Immediately understandable without technical explanation.
- **Clean indentation**: Strict use of 4 spaces for hierarchy.
- **Lean**: No braces `{}`, no semicolons `;`, one instruction per line.

## Naming Conventions
- **PascalCase**: Entities (`User`), Actors (`ShopManager`), Workflows (`ManageTodo`), primitive types (`String`).
- **camelCase**: Attributes (`publishedAt`, `totalAmount`).

## Supported Primitive Types
- `String`, `Text`, `Integer`, `Float`, `Boolean`
- `Date`, `DateTime`, `Email`, `UUID`, `Money`
