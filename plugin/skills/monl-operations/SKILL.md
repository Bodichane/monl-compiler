---
name: monl-operations
description: Build professional operational workspaces for Monl. Use for dashboards, inventory, finance, task management, moderation, community administration, reporting, approval queues, and other multi-entity role-based applications.
---

# Build a Monl operations workspace

Apply `$monl-showcase`, then organize the interface around decisions and work queues instead of database tables.

## Required journey

1. Derive a concise overview from real API data.
2. Group tools by user goal and role.
3. Provide search, filtering, or status segmentation when supported by contract fields.
4. Pair collection views with focused create, inspect, edit, and resolve flows.
5. Keep ownership and privileged actions visible and understandable.
6. Show actionable empty states and contextual errors.
7. Make dense data responsive through prioritization, not microscopic text.

Read [references/operations-gates.md](references/operations-gates.md) for acceptance criteria.

Do not expose a generic CRUD shell, raw identifiers without context, raw JSON as the primary result, or controls the active role cannot use.
