"""Le système de design : ce que monl DÉCRIT du site sans rien en décider.

Point 72 : le compilateur ne choisit ni palette, ni typographie, ni
rayon. Il déduit un PROFIL de la spec, exige des marqueurs de section,
et rend un document que l'IA d'interface doit suivre.

La surface publique n'a pas bougé en devenant un paquet."""

from .manifeste import activate_asset_manifest, build_asset_manifest
from .marqueurs import _declared_section_markers, _section_substance
from .noms import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    GENERATED_MARKER,
)
from .profil import infer_design_profile
from .rendu import ensure_design_artifacts, plan_generated_images

# POINT 139 : il n'y a PLUS de palette ici, et il ne doit pas y en avoir.
# Cinq palettes indexées sur le type d'activité vivaient à cet endroit. Le
# point 72 l'interdit — « le compilateur ne décide RIEN du visuel : ni palette,
# ni typographie, ni rayon » — et trois faits l'ont tranché plutôt qu'un
# argument : les cinq couleurs `:root` de projets/AtelierNaya sont identiques à
# l'octet à la palette « service », écrite quarante minutes plus tôt ; le
# garde-fou ne regardait que le contrat, pendant que la palette voyageait par
# DESIGN_SYSTEM.md ; et cette palette échouait au contraste qu'elle promettait
# elle-même dans le même document (blanc sur #D07A4B : 3,20:1 pour un seuil
# annoncé de 4,5:1, mesuré sur le bouton « Réserver »).
#
# La ligne retenue est plus fine que « méthode contre goût » : une échelle, un
# rythme, une durée ou une rupture deviennent du GOÛT dès que le compilateur en
# choisit les VALEURS. Ce fichier peut donc exiger qu'une échelle existe et
# qu'elle soit suivie ; il ne peut pas dire laquelle.

__all__ = [
    "ASSET_MANIFEST_FILENAME",
    "DESIGN_SPEC_FILENAME",
    "DESIGN_SYSTEM_FILENAME",
    "GENERATED_MARKER",
    "_declared_section_markers",
    "_section_substance",
    "activate_asset_manifest",
    "build_asset_manifest",
    "ensure_design_artifacts",
    "infer_design_profile",
    "plan_generated_images",
]
