"""Les constantes du contrat, et les deux outils que tout le paquet emprunte.

`paragraphes()` retraduit le séparateur `¶` (point 64) : la grammaire
interdit le saut de ligne dans un STRING_LITERAL, et c'est ainsi qu'une
`section` porte plusieurs paragraphes sans brique nouvelle."""

from ..artifacts import DOCS_DIR
from ..ir import CompilationPlans

CONTRACT_VERSION = 9  # 2 : base_url même origine (51) · 3 : rôles + archétypes (54)
#                     # 4 : champs de suivi du paiement déclarés (76)
#                     # 5 : assets déclarés — logo, favicon, dossier (83)
#                     # 6 : route d'écriture après paiement déclarée (113)
#                     # 7 : indicatif téléphone transmis au frontend (95)
#                     # 8 : design skills de densité sélectionnés
#                     # 9 : règles métier — publicWhen et oncePer (116)
# Les numéros entre parenthèses renvoient à docs/design_decisions.md. Ceux des
# versions 6 et 7 désignaient les points 107-109, qui parlent d'autre chose
# (émission SQL typée, contrôle d'accès, spike Rust) : corrigés ici plutôt que
# laissés induire en erreur — ce fichier cite ces numéros pour qu'on les suive.

# RÔLES DE CHAMPS ET ARCHÉTYPES (point 54) — restauration, dans le CONTRAT,
# de ce que le point 35 dérivait pour le frontend que monl générait lui-même,
# et que le pivot (point 41) a supprimé sans le transposer. Sans ces rôles,
# un champ n'est qu'un `{nom, type}` : l'IA UI doit redeviner depuis les noms
# lequel est le titre, lequel est l'image de couverture, alors que monl sait
# le déduire de façon déterministe. Même philosophie qu'aux thèmes : dérivé
# de la spec, jamais déclaré dans le DSL métier.
MEDIA_HINTS = ("image", "photo", "cover", "couverture", "avatar", "picture",
               "thumbnail", "vignette", "banner", "banniere", "illustration",
               "visuel", "url")

CATEGORY_HINTS = ("category", "categorie", "genre", "kind", "tag", "rubrique",
                  "status", "statut", "etat", "type")

# La disponibilité est un essentiel de fiche produit, au même rang que le prix
# (point 60) : la reléguer en « méta » la faisait traiter comme un détail.
STOCK_HINTS = ("stock", "quantity", "quantite", "inventaire", "disponib",
               "available", "restant")

CONTRACT_FILENAME = "frontend_contract.json"

#: Le brief se LIT : il part dans `docs/`. Le contrat, lui, reste à la racine —
#: c'est l'interface MACHINE du projet, celle qu'un outil ouvre sans rien
#: connaître de l'arborescence.
PROMPT_FILENAME = f"{DOCS_DIR}/FRONTEND_PROMPT.md"

#: La mémoire du projet s'appelle AGENTS.md et non CLAUDE.md : le frontend peut
#: être écrit par claude-code, codex ou gemini (point 69), et nommer le fichier
#: d'après un seul d'entre eux en fait un fichier que les autres ne lisent pas.
AGENTS_FILENAME = "AGENTS.md"

README_FILENAME = "README.md"

FRONTEND_ARTIFACTS = (CONTRACT_FILENAME, PROMPT_FILENAME,
                      AGENTS_FILENAME, README_FILENAME)

def paragraphes(texte):
    """Retraduit le séparateur de paragraphes de la spec en vrais sauts
    (point 64). La grammaire interdit le retour à la ligne dans un
    STRING_LITERAL : un « à propos » de trois paragraphes voyage donc en une
    seule ligne, marquée. Le contrat est le premier endroit où cette
    contrainte d'écriture cesse d'exister — et l'IA d'interface reçoit du
    texte structuré au lieu d'un bloc sans césure.

    Sans marqueur, le texte ressort tel quel : un contrat écrit avant le
    point 64, ou une spec rédigée à la main, se lit exactement comme avant.
    """
    return "\n\n".join(p.strip() for p in texte.split("¶") if p.strip())

def _coerce_plans(source) -> CompilationPlans:
    """Compatibilité de bibliothèque pour les anciens appels avec générateur."""
    if isinstance(source, CompilationPlans):
        return source
    return source.build_compilation_plans()
