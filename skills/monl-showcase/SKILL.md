---
name: monl-showcase
description: Build or refine dense, distinctive, demo-grade Monl web interfaces. Use for every public-facing Monl frontend, showcase project, design upgrade, or frontend quality review that must preserve the generated API contract while reaching production-level polish.
---

# Build a Monl showcase

Read `FRONTEND_PROMPT.md` and `frontend_contract.json` before editing. Treat the contract as the source of truth for routes, roles, fields, ownership, and authentication.

## Workflow

1. Inventory every user-visible workflow and map it to an interface entry point.
2. Choose a visual direction from the author's brief; never infer a palette from the business category.
3. Build a dense home or workspace with clear hierarchy, real demo data, and purposeful sections.
4. Implement loading, empty, success, validation, authorization, conflict, and service-unavailable states where relevant.
5. Exercise each role's primary journey from entry to completion.
6. Verify mobile, keyboard, reduced-motion, contrast, and responsive overflow behavior.
7. Run `monl run . --check` and fix all failures.

Read [references/quality-gates.md](references/quality-gates.md) when planning or auditing the interface.

## Guardrails

- Keep all frontend resources local and write only in `frontend/`.
- Expose business operations through humane controls, not raw JSON or API consoles.
- Avoid generic dashboard/card repetition; vary hierarchy according to content importance.
- Never invent routes, permissions, records, payment outcomes, or backend behavior.
- Preserve a distinct identity across projects while maintaining equivalent depth.
