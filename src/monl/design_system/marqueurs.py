"""Les sections EXIGÉES, et la matière qu'elles doivent porter.

Point 143 : un marqueur NOMME une section, il ne prouve pas qu'elle
contient quelque chose. Les seuils voyagent dans `ASSET_MANIFEST.json`."""

from ..section_substance import rule_for
from .profil import _entity_media, _slug


def _required_markers(contract: dict, profile: dict) -> list[str]:
    # Une spec purement API n'a pas demandé de site éditorial. Elle reçoit
    # bien un design system pour le jour où un frontend sera ajouté, mais
    # Monl ne doit pas lui imposer des sections de landing qu'elle n'a jamais
    # déclarées (compatibilité avec les projets historiques et les backends
    # sans interface).
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
    # Un marqueur identifie l'élément qui porte la section, il n'exige jamais
    # un bloc séparé. Quand le pattern `editorial` est présent, cet élément vit
    # à l'intérieur du bloc éditorial : un seul élément, un seul marqueur, un
    # seul rendu. La garantie « chaque section déclarée est rendue » reste donc
    # active sans pousser l'IA à dupliquer « À propos ».
    markers.extend(_declared_section_markers(contract))
    if contract.get("faq"):
        markers.append('data-monl-section="faq"')
    # BRIQUE 30 : le pied de page est le dernier endroit où un site produit se
    # dénonce comme une maquette — deux mots gris, aucun lien, aucune mention.
    # Il était exigé NULLE PART : le plancher du point 143 comptait quatre
    # sections et s'arrêtait au-dessus de lui.
    markers.append('data-monl-section="footer"')
    return list(dict.fromkeys(markers))

def _declared_section_markers(contract: dict) -> list[str]:
    """Retourne un marqueur distinct pour chaque section, dans l'ordre déclaré."""
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
    """Apparie chaque section obligatoire à ce qu'elle doit CONTENIR.

    Une section écrite par l'auteur est jugée sur ce qu'il a lui-même
    déclaré : réclamer cent caractères à une rubrique qui en compte
    cinquante ferait échouer une spec honnête. Le seuil est donc plafonné par
    la longueur du corps, jamais deviné.
    """
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

def _generated_image_block_markers(contract: dict, profile: dict,
                                   generated: list[dict]) -> list[str | None]:
    """Retourne une précision de section, quand le rôle peut en recevoir une.

    Le rôle du manifeste est l'appariement obligatoire. Un marqueur ne sert
    qu'à préciser où placer le visuel lorsque le contrat offre déjà un bloc
    correspondant ; son absence ne doit donc jamais supprimer la consigne.
    Les rôles, et non la position dans la liste, choisissent les candidats.
    """
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
        if "bandeau principal" in role:
            candidates = [hero_marker]
        elif "vignette secondaire" in role:
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
