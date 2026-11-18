"""The document handed to the interface AI, and the image plan.

`plan_generated_images` lives HERE and not with the manifest: it calls the
rendering, which calls the manifest. Placing it there would make a cycle."""

import json
import shutil
from pathlib import Path

from ..ui_patterns import render_pattern_block
from .manifeste import _generated_image_plan, build_asset_manifest
from .marqueurs import _generated_image_block_markers, _required_markers, _section_substance
from .noms import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    GENERATED_MARKER,
)
from .profil import _guarantees, infer_design_profile


def _lignes_de_substance(contract, profile):
    """The "what each section must carry" list. Extracted from
    `render_design_system` (complexity ceiling); text byte-identical."""
    return "\n".join(
        "- `{}`: {}".format(
            marker.partition("=")[2].strip('"'),
            ", ".join(
                part for part in (
                    "a heading" if regle.get("heading") else "",
                    "a form" if regle.get("form") else "",
                    "an action button or link" if regle.get("action") else "",
                    (f"at least {regle['text']} characters of readable text"
                     if regle.get("text") else ""),
                ) if part
            ),
        )
        for marker, regle in _section_substance(contract, profile).items()
    ) or "- No required section for this project."


def render_design_system(contract: dict, generate_images=False) -> str:
    profile = infer_design_profile(contract)
    pages = "\n".join(f"- {page}" for page in profile["pages"])
    patterns = render_pattern_block(profile["ui_patterns"])
    media = "\n".join(
        f"- `{item['entity']}`: {', '.join(item['fields'])}"
        for item in profile["media_entities"]
    ) or "- No structured media detected; do not invent remote photos."
    generated = build_asset_manifest(
        contract, profile, generate_images=generate_images).get("generated_assets") or []
    block_markers = _generated_image_block_markers(contract, profile, generated)
    generated_block = "\n".join(
        f"- `{item['path']}` — role: {item['role']} — single use "
        "required: render this file only once"
        + (f" — detail: exact HTML block: `{marker}`" if marker else "")
        for item, marker in zip(generated, block_markers, strict=True)
    ) or "- No additional graphic file planned; do not invent an image path."
    anti_patterns = {
        "commerce": "catalog reduced to three cards, price pushed aside, fake stock, fake successful payment, hero without a product",
        "operations": "decorative dashboard with no decision, repeated cards, table unreadable on mobile, privileged action hidden",
        "editorial": "sections reduced to paragraphs with no rhythm, generic hero, remote images, FAQ flattened into text",
        "service": "form without reassurance, unproven promise, fictional calendar, silent error states",
        "generic": "empty screen after the hero, uniform grid, fake content, navigation with no clear way out",
    }[profile["kind"]]
    markers = "\n".join(f"- `{marker}`" for marker in _required_markers(contract, profile))
    liens = "\n".join(
        f"- **{lien['label']}** → `{lien['url']}`"
        for lien in (contract.get("links") or [])
    ) or ("- No link declared. Do not invent any: a guessed social network "
          "address leads to someone else.")
    garanties = "\n".join(f"- {phrase}" for phrase in _guarantees(contract)) or (
        "- No guarantee derivable from the contract: claim nothing rather "
        "than invent a proof.")
    substance = _lignes_de_substance(contract, profile)
    return f"""{GENERATED_MARKER}
# {contract.get('app', 'Monl')} — initial design system

This document is produced by Monl before the frontend is generated. It gives
the AI a consistent, revisable composition decision. It replaces neither the
business spec nor a `DESIGN_SPEC.md` written by the author: if the latter
exists, it takes precedence.

## Main decision

- **Detected type:** {profile['kind']}
- **Pattern:** {profile['pattern']}

## Expected method — the values are YOURS

This document contains no color, no font and no radius, and that is
deliberate: the identity comes from the brief and the dialogue, never from
the compiler. What is required here is RIGOR, not taste.

- **Tokens**: define your colors, spacings and radii as named CSS variables,
  at the top of the sheet, and write no hard-coded value anywhere else. A
  touch-up must be able to change the identity in one place.
- **Type scale**: choose a progression and stick to it. Each size must have a
  named ROLE; a size that belongs to no role is one size too many. The
  hierarchy must stay readable on a small screen — a main heading that drops
  to the size of the subheadings erases it.
- **Line length**: bound it for running text blocks.
- **Spacing rhythm**: a scale, not case-by-case numbers. A section's vertical
  rhythm must reflect its importance, and tighten on a small screen rather
  than stay identical.
- **States**: each interactive control must cover rest, hover when it makes
  sense, keyboard-visible focus, active, disabled, waiting and error. An error
  goes NEXT TO the field concerned, not only in a global message. An action
  in progress prevents double submission.
- **Motion**: bound the durations and give them a reason.
  `prefers-reduced-motion` is respected.
- **Contrast**: 4.5:1 minimum for body text, 3:1 for large headings — check
  it on BUTTON text, that is where it is most often missing.
- **Depth**: if you use shadows, make them form a model with several levels;
  a single shadow spread everywhere establishes no hierarchy.

## Pages and blocks to render

{pages}

The editorial sections and the FAQ declared in the contract must be visible
on the home page, not only hidden behind the navigation.

{patterns}

## Content ownership — avoiding repetition

Each declared section must appear **only once** on the home page, on its own
HTML element carrying `data-monl-section="<slug>"`. When an `editorial`
pattern is present, the editorial block carries these elements inside it:
merge "About", "Opening hours", etc. into that story instead of adding a
second block afterwards. One element, one marker, one rendering. Likewise,
each generated image has a single role: the exact block it is paired with is
given in "Graphic assets produced by the build" below. Render each file only
once in that block and never reuse its path in another block; do not swap
the two pairings.

## Assets

{media}

### Graphic assets produced by the build

{generated_block}

Every asset must be local and served from the folder declared by the
specification, mounted under `/site/<assets_dir>/`. No CDN, no remote URL and
no silent placeholder on a declared path. The associated manifest is
`ASSET_MANIFEST.json`. For each media entity, mark the area that renders its
images with `data-monl-media="entity-name"`: this marker lets Monl check that
an image has not disappeared behind an empty card or a fake placeholder.

## Anti-patterns to avoid

- {anti_patterns}
- Generic purple/pink gradients, emojis used as icons and insufficiently contrasted gray text.
- Global loading states that hide the whole page; prefer a state local to the area concerned.
- A desktop interface simply shrunk on mobile, horizontal overflow or buttons with no focus state.

## Delivery checklist

- [ ] Each main flow of the contract has a visible entry.
- [ ] Loading, empty, success, error, refusal and unavailability are handled when they exist.
- [ ] Images have a useful `alt` and a controlled local fallback.
- [ ] Buttons and links are distinguishable, keyboard-reachable and visible on focus.
- [ ] `prefers-reduced-motion` is respected.
- [ ] Widths of 375 px, 768 px, 1024 px and 1440 px stay usable.
- [ ] `monl run . --check` passes after the manifest is activated.

## Expected structural markers

{markers}

## Minimum substance of each section — refused at check time

A marker names a section, it does not fill it. A section that is marked but
empty **makes the build fail**: it is not a warning. What is required,
section by section:

{substance}

The text counted is the text a human reads: the content of a `<script>` does
not count, and a section cannot borrow its neighbor's text. These thresholds
are FLOORS, not targets — reaching them with filler would miss the point.
What is missing must be taken from the contract and the declared content,
never invented.

A collection section (`catalogue`, `workspace`) does NOT have to contain
hard-coded data: its rows come from the API at runtime. What it must carry is
its heading, its rendering area and its empty state.

## Footer — required, and checked

The footer carries `data-monl-section="footer"`. It is the last place where
a site gives itself away as a mockup: two gray words, no link, no notice. It
must carry, at least:

- **all the links declared below, with their exact address** — their absence
  makes the build fail;
- a **navigation** to the page's sections (the same anchors as the main
  menu);
- the **identity** of who publishes the site and the current year;
- the **contact** if a declared address or phone number exists.

NEVER invent: no undeclared social network, no fictional legal notice, no
"© 2026 All rights reserved" on a made-up company name. What is not declared
does not exist.

### Declared links — to render as is

{liens}

## Genuinely verifiable guarantees — material for the reassurance section

These sentences describe what the backend really does. The `trust` section
must be built from them, reworded in the site's register. Any other claim —
customer review, partner logo, number of users, award, undeclared delay — is
**forbidden**: monl cannot verify it, so the site cannot promise it.

{garanties}
"""

def _write_generated(path: Path, content: str, marker: str = GENERATED_MARKER) -> bool:
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if marker not in current:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True

def ensure_design_artifacts(project_dir: str, staging_dir: str, contract: dict,
                            generate_images=False) -> dict:
    """Emits the generated visual artifacts, without overwriting human work."""
    project = Path(project_dir)
    staging = Path(staging_dir)
    design_system = _write_generated(
        staging / DESIGN_SYSTEM_FILENAME,
        render_design_system(contract, generate_images=generate_images))

    design_spec = f"""{GENERATED_MARKER}
# {contract.get('app', 'Monl')} — initial visual brief

The complete design system is in `DESIGN_SYSTEM.md`. This summary is produced
from the frontend contract and can be replaced by a specific brief written by
the author.

## Intent

{contract.get('brief') or 'Build a clear, complete interface suited to the contract flows.'}

## Required content

{chr(10).join(f"- {section.get('title', 'Section')}: {section.get('body', '')}" for section in contract.get('sections') or []) or '- Render the contract flows and entities with an explicit hierarchy.'}

## Quality rules

- The main flows, error states and empty states are visible and understandable.
- The declared editorial sections stay present on the home page.
- The visuals are local, consistent with the design system and actually referenced.
- The accessibility and responsive details of `DESIGN_SYSTEM.md` are mandatory.
"""
    design_spec_written = _write_generated(staging / DESIGN_SPEC_FILENAME, design_spec)

    manifest = build_asset_manifest(
        contract, infer_design_profile(contract), generate_images=generate_images)
    manifest_text = GENERATED_MARKER + "\n" + json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    manifest_written = _write_generated(staging / ASSET_MANIFEST_FILENAME, manifest_text)

    # ``copy_preserved_files`` already handles the human briefs. This fallback
    # makes the function safe when called independently of the pipeline.
    for name, written in ((DESIGN_SPEC_FILENAME, design_spec_written),
                          (ASSET_MANIFEST_FILENAME, manifest_written)):
        if not written and not (staging / name).exists() and (project / name).exists():
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / name, staging / name)
    return {
        DESIGN_SYSTEM_FILENAME: design_system,
        DESIGN_SPEC_FILENAME: design_spec_written,
        ASSET_MANIFEST_FILENAME: manifest_written,
    }

def plan_generated_images(project_dir: str) -> list[dict]:
    """Activates the image plan after the explicit choice of the image AI.

    ``monl compile`` stays without images by default. This step is called by
    ``monl frontend --generate-images`` just before the build, so that the
    manifest and the text brief contain the names before the first HTML file
    is written."""
    project = Path(project_dir)
    contract_path = project / "frontend_contract.json"
    manifest_path = project / ASSET_MANIFEST_FILENAME
    if not contract_path.exists() or not manifest_path.exists():
        return []
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        content = manifest_path.read_text(encoding="utf-8")
        if not content.startswith(GENERATED_MARKER):
            return []
        manifest = json.loads("\n".join(content.splitlines()[1:]))
    except (OSError, json.JSONDecodeError):
        return []
    if manifest.get("generated_by") != "monl":
        return []
    generated = _generated_image_plan(contract, infer_design_profile(contract))
    manifest["generated_assets"] = generated
    manifest["status"] = "planned"
    manifest_path.write_text(
        GENERATED_MARKER + "\n" + json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    design_path = project / DESIGN_SYSTEM_FILENAME
    if design_path.exists():
        try:
            design = design_path.read_text(encoding="utf-8")
        except OSError:
            design = ""
        if GENERATED_MARKER in design:
            design_path.write_text(
                render_design_system(contract, generate_images=True), encoding="utf-8")
    return generated
