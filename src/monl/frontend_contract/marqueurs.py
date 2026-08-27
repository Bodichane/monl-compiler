"""Les marqueurs de section exigés du frontend livré.

Un marqueur NOMME une section, il ne prouve pas qu'elle contient quelque
chose : la matière se mesure ailleurs (point 143, section_substance.py)."""

from ..design_system import build_asset_manifest, infer_design_profile


def _marker_block_description(marker):
    """Décrit le bloc HTML qui porte un marqueur du manifeste."""
    if marker.startswith('data-monl-media="'):
        entity = marker.split('"', 2)[1]
        return f"la zone qui rend les images de l'entité `{entity}`"
    if not marker.startswith('data-monl-section="'):
        return "l'élément HTML du bloc visuel correspondant"
    section = marker.split('"', 2)[1]
    descriptions = {
        "hero": "le bloc hero / bandeau principal",
        "catalogue": "le bloc catalogue qui rend la liste des produits",
        "panier": "le bloc panier ou récapitulatif de commande",
        "workspace": "le bloc espace de travail du rôle concerné",
        "faq": "le bloc FAQ structuré",
        "editorial": "le bloc du récit éditorial",
        "trust": "le bloc de preuve ou de réassurance",
        "closing-cta": "le bloc d'appel à l'action final",
    }
    return descriptions.get(section, f"le bloc HTML de la section `{section}`")

def _required_markers_block(contract):
    """Rend dans le brief la carte exécutable des marqueurs obligatoires."""
    manifest = build_asset_manifest(contract, infer_design_profile(contract))
    markers = (manifest.get("required_markers") or {}).get("index.html") or []
    if not markers:
        return ""
    lines = "\n".join(
        f"- Fichier exact : `frontend/index.html` — marqueur exact : `{marker}` — "
        f"bloc exact : {_marker_block_description(marker)}."
        for marker in markers
    )
    return f"""
## Marqueurs visuels obligatoires — fichier et bloc exacts

Le manifeste exige les marqueurs suivants. Écris chacun dans le fichier et
sur le bloc indiqués ci-dessous ; le texte du marqueur doit être recopié
exactement, guillemets compris. Ne le remplace pas par une classe CSS ou par
un commentaire.

{lines}
"""
