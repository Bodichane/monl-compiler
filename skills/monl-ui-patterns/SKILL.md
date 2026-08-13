---
name: monl-ui-patterns
description: Compose Monl frontends from local, autonomous UI patterns inspired by component registries, without importing React, Tailwind, CDNs or invented business behavior.
---

# Compose with Monl UI patterns

Read `DESIGN_SYSTEM.md` and `ASSET_MANIFEST.json` first. The selected patterns
are structures, not a license to reproduce a generic template or invent data.

## Available pattern families

- `hero`: split editorial, centered conversion, workspace entry
- `catalogue`: featured rail, filter grid, dense list
- `editorial`: split story, proof bento, longform rail
- `trust`: value grid, process steps, evidence strip
- `faq`: accordion, two-column, definition list
- `contact`: form aside, contact card, closing form
- `closing-cta`: quiet band, image overlap, next step

## Workflow

1. Use the selected variant from `DESIGN_SYSTEM.md`.
2. Keep the structure compatible with the contract's routes and real data.
3. Add the required `data-monl-section` and `data-monl-media` markers.
4. Implement the pattern with local HTML/CSS/JS and accessible states.
5. Run `monl run . --check` before delivery.

Do not copy React/Tailwind source into a static Monl frontend. Translate the
composition and interaction into the project's autonomous stack.
