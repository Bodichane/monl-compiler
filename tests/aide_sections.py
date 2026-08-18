"""Fabrique des sections de test qui portent leur MATIÈRE (point 140)."""


def section_avec_matiere(marker, regle=None):
    """Une section de test qui porte sa MATIÈRE, pas seulement son nom.

    Depuis le point 140, une section marquée mais vide fait échouer la
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
