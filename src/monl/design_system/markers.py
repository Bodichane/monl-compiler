"""The REQUIRED sections, and the substance they must carry.

Point 143: a marker NAMES a section, it does not prove that it contains
anything. The thresholds travel in `ASSET_MANIFEST.json`."""

from ..section_substance import rule_for
from .profile import _entity_media, _slug


def _required_markers(contract: dict, profile: dict) -> list[str]:
    # A purely API spec did not ask for an editorial site. It does receive a
    # design system for the day a frontend is added, but Monl must not impose
    # on it landing sections it never declared (compatibility with historical
    # projects and backends without an interface).
    if not (contract.get("brief") or contract.get("sections") or contract.get("faq")):
        return []
    markers = [pattern["marker"] for pattern in profile.get("ui_patterns", [])]
    markers.extend(
        f'data-monl-media="{_slug(name)}"'
        for name, spec in (contract.get("entities") or {}).items()
        if _entity_media(spec)
    )
    if profile["kind"] == "commerce":
        markers.extend(['data-monl-section="catalogue"', 'data-monl-section="panier"'])
    if profile["kind"] == "operations":
        markers.append('data-monl-section="workspace"')
    # A marker identifies the element that carries the section, it never
    # requires a separate block. When the `editorial` pattern is present, this
    # element lives inside the editorial block: a single element, a single
    # marker, a single rendering. The "every declared section is rendered"
    # guarantee therefore stays active without pushing the AI to duplicate
    # "About".
    markers.extend(_declared_section_markers(contract))
    if contract.get("faq"):
        markers.append('data-monl-section="faq"')
    # BRICK 30: the footer is the last place where a produced site gives itself
    # away as a mockup — two gray words, no link, no notice. It was required
    # NOWHERE: point 143's floor counted four sections and stopped above it.
    markers.append('data-monl-section="footer"')
    return list(dict.fromkeys(markers))

def _declared_section_markers(contract: dict) -> list[str]:
    """Returns a distinct marker for each section, in declared order."""
    used_slugs = set()
    next_rank_by_slug = {}
    markers = []
    for section in contract.get("sections") or []:
        base_slug = _slug(section.get("title", "section"))
        rank = next_rank_by_slug.get(base_slug, 1)
        section_slug = base_slug if rank == 1 else f"{base_slug}-{rank}"
        while section_slug in used_slugs:
            rank += 1
            section_slug = f"{base_slug}-{rank}"
        next_rank_by_slug[base_slug] = rank + 1
        used_slugs.add(section_slug)
        markers.append(f'data-monl-section="{section_slug}"')
    return markers

def _section_substance(contract: dict, profile: dict) -> dict[str, dict]:
    """Pairs each mandatory section with what it must CONTAIN.

    A section written by the author is judged on what they declared
    themselves: requiring a hundred characters of a section that has fifty
    would make an honest spec fail. The threshold is therefore capped by the
    body's length, never guessed."""
    longueurs = {}
    for section, marker in zip(contract.get("sections") or [],
                               _declared_section_markers(contract), strict=False):
        corps = " ".join((section.get("body") or "").split())
        titre = " ".join((section.get("title") or "").split())
        longueurs[marker] = len(titre) + len(corps)
    regles = {}
    for marker in _required_markers(contract, profile):
        if not marker.startswith('data-monl-section="'):
            continue
        slug = marker.partition("=")[2].strip('"')
        regles[marker] = rule_for(slug, longueurs.get(marker))
    return regles

# Both languages: a manifest written before the English migration still carries
# the French role, and must keep placing its image.
ROLE_BANDEAU = ("main banner", "bandeau principal")
ROLE_VIGNETTE = ("secondary thumbnail", "vignette secondaire")


def _role_est(role, formes):
    return any(forme in role for forme in formes)


def _generated_image_block_markers(contract: dict, profile: dict,
                                   generated: list[dict]) -> list[str | None]:
    """Returns a section hint, when the role can receive one.

    The manifest's role is the mandatory pairing. A marker only serves to
    specify where to place the visual when the contract already offers a
    matching block; its absence must therefore never remove the instruction.
    The roles, not the position in the list, choose the candidates."""
    required = _required_markers(contract, profile)
    required_set = set(required)
    hero_marker = 'data-monl-section="hero"'
    declared_sections = [
        marker for marker in _declared_section_markers(contract)
        if marker != hero_marker
    ]
    fallback_sections = [
        f'data-monl-section="{name}"'
        for name in ("editorial", "trust", "closing-cta")
    ]
    placements = []
    used = set()
    for item in generated:
        role = str(item.get("role") or "").casefold()
        if _role_est(role, ROLE_BANDEAU):
            candidates = [hero_marker]
        elif _role_est(role, ROLE_VIGNETTE):
            candidates = declared_sections + fallback_sections + [
                marker for marker in required
                if marker.startswith('data-monl-section="')
                and marker != hero_marker
                and marker not in fallback_sections
                and marker not in declared_sections
            ]
        else:
            candidates = []
        marker = next((candidate for candidate in candidates
                       if candidate in required_set and candidate not in used), None)
        placements.append(marker)
        if marker:
            used.add(marker)
    return placements
