---
name: monl-design-system
description: Turn a validated Monl contract into a concrete design system before frontend implementation, with page patterns, tokens, asset planning, anti-patterns, accessibility and delivery gates.
---

# Build from the Monl design system

Read `DESIGN_SYSTEM.md`, `DESIGN_SPEC.md`, `ASSET_MANIFEST.json`,
`FRONTEND_PROMPT.md` and `frontend_contract.json` before editing. The design
system decides composition; the contract decides what the application is
allowed to do.

## Workflow

1. Confirm the page pattern and the primary user action.
2. Apply the supplied tokens consistently before adding decorative details.
3. Map each contract entity and route to a visible interface entry point.
4. Create or reuse local assets described by the manifest; never hide a missing
   asset behind a remote URL or a generic empty box.
5. Treat the anti-pattern list as a blocking review, not as optional advice.
6. Verify focus states, contrast, reduced motion, responsive widths and all
   loading/empty/error/refusal states.
7. Run `monl run . --check` and fix every reported marker or asset failure.

## Guardrails

- Do not infer a new business route from a visual pattern.
- Do not replace the author's `DESIGN_SPEC.md` or the generated manifest.
- Keep the frontend autonomous: local HTML/CSS/JS/SVG only.
- A design system can improve consistency and hierarchy; it cannot prove that
  a layout is beautiful. The final site still needs a human visual review.
