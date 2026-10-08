---
name: monl-frontend
description: Build, fix or improve the web frontend of a compiled monl project — the folder that holds frontend_contract.json and docs/FRONTEND_PROMPT.md. Use for any work in its frontend/ directory, from a first build to a visual touch-up, before declaring it finished.
---

# Build a monl frontend and look at it

monl already wrote everything this site must do and how it should be composed.
Do not look for that here: read it from the project, it is authoritative.

1. Read `docs/FRONTEND_PROMPT.md`, `frontend_contract.json`,
   `docs/DESIGN_SYSTEM.md`, `docs/DESIGN_SPEC.md` and `docs/ASSET_MANIFEST.json`.
2. Write only in `frontend/`. Local HTML, CSS, JS and SVG, no CDN.
3. Run `monl run . --check` and fix every failure until it passes.

`monl run --check` proves the site WORKS: routes, markers, smoke test. It
cannot see what a visitor sees. Measured on real builds, a site that passes it
still shipped clipped text, misaligned grids and a cramped mobile header. So
the job is not finished until you have looked at it:

4. Run `python3 ${CLAUDE_PLUGIN_ROOT}/skills/monl-frontend/scripts/apercu.py .`
   from the project.
   It serves the site and writes `bureau.png` (1280 px) and `mobile.png`
   (390 px), then prints their paths.
5. Open both images with your image-reading tool and list what a visitor would
   notice. Fix it in `frontend/`, capture again, and stop after three rounds.
6. Run `monl run . --check` one last time: a visual fix must not break a route.

## What to look for in the screenshots

- Text cut off, overlapping or overflowing its box, on desktop or mobile.
- Grid items, captions or prices that do not line up.
- A mobile header or menu that wraps badly, or controls that are too small to tap.
- Empty boxes, broken images, placeholder words, raw identifiers or raw JSON.
- Spacing that changes from one section to the next for no reason.
- Low-contrast text over images or tinted backgrounds.

These CSS habits prevent most of them: `min-width: 0` on grid and flex
children, `overflow-wrap: anywhere` on titles and long values, no fixed height
on a box that holds text, and a header that is designed for 390 px rather than
shrunk from desktop.

If `apercu.py` finds no browser, say so in your final answer instead of
claiming a visual review you did not do.
