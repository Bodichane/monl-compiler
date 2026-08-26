"""Aides partagées entre fichiers de tests.

Deux choses y vivent : la fabrication de sections qui portent leur MATIÈRE
(point 143), et la définition de ce qu'est une ressource distante — celle-ci
était écrite deux fois, dans le test de l'accueil et dans celui de la
console, et les deux ont divergé au premier élargissement.
"""

import re

#: Une page servie en local doit fonctionner sans réseau. Mais « charger une
#: ressource » et « pointer ailleurs » sont deux choses différentes, et la
#: première version les confondait : elle interdisait TOUTE URL, donc aussi
#: le lien vers le dépôt dans le pied de page. Un `<a href>` ne télécharge
#: rien — la page reste entière hors ligne, seul le clic échoue, ce qui est
#: le comportement attendu d'un lien sortant. Ce qui reste interdit, c'est ce
#: que le NAVIGATEUR va chercher tout seul.
RESSOURCE_DISTANTE = re.compile(
    r"<link\b"                        # feuille de style, favicon, préchargement
    r"|<script[^>]+\bsrc="            # script tiers
    r"|@import"                       # CSS importée
    r"|\bsrc\s*=\s*['\"]https?://"   # image, iframe, média distants
    r"|\burl\(\s*['\"]?https?://",    # police ou fond distants
    re.IGNORECASE,
)


def section_avec_matiere(marker, regle=None):
    """Une section de test qui porte sa MATIÈRE, pas seulement son nom.

    Depuis le point 143, une section marquée mais vide fait échouer la
    vérification — c'est tout l'objet de la brique. Les fixtures qui
    fabriquent un faux frontend doivent donc livrer ce qu'un vrai frontend
    doit livrer : titre, texte lisible, action, et formulaire là où le
    contrat en attend un. Écrit UNE fois ici plutôt que recopié dans chaque
    fichier de tests : trois copies finiraient par diverger, et une fixture
    trop généreuse rendrait la barrière intestable.
    """
    corps = [
        "<h2>Titre de la section</h2>",
        "<p>" + "Un texte réellement lisible, tel qu'un visiteur en lirait "
                "sur cette page du site. " * 4 + "</p>",
        '<a href="#suite">Continuer</a>',
    ]
    if (regle or {}).get("form"):
        corps.append("<form><label>Message<input></label>"
                     "<button>Envoyer</button></form>")
    return f"<section {marker}>" + "".join(corps) + "</section>"


def sections_du_manifeste(manifest, fichier="index.html"):
    """Rend toutes les sections obligatoires d'un manifeste, avec leur matière."""
    regles = (manifest.get("section_substance") or {}).get(fichier, {})
    return "\n".join(
        section_avec_matiere(marker, regles.get(marker))
        for marker in manifest["required_markers"][fichier]
    )
