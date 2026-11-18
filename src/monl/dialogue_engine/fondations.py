"""Ce que tout le dialogue lit, et qui ne lit rien en retour.

`adresse_de_lien` est la SOURCE UNIQUE de la complétion d'adresse côté
Python (point 146). La console web en a nécessairement une copie
JavaScript, et l'accord des deux est VÉRIFIÉ par un test : deux mises en
oeuvre d'une même règle divergent toujours."""

import re

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

# Indicatif téléphonique international : '+' puis 1 à 4 chiffres (+229 Bénin,
# +33 France, +7 Russie). Vérifié ici plutôt que laissé au compilateur, pour
# que la faute se voie pendant le dialogue et non trois écrans plus loin.
PHONE_PREFIX_RE = re.compile(r"^\+\d{1,4}$")

# Types proposés dans le menu — sous-ensemble sûr des types de la grammaire
# (Date/UUID exclus du menu v1 : peu utiles sans widget de saisie dédié).
FIELD_TYPES = ["String", "Text", "Integer", "Float", "Money", "Boolean", "Email", "DateTime"]

# Types qu'on sait seeder de façon déterministe (la grammaire 'seed' n'accepte
# que STRING_LITERAL et SIGNED_NUMBER — pas de booléen ni de date).
SEEDABLE_TYPES = {"String", "Text", "Integer", "Float", "Money", "Email"}

RELATION_TYPES = ["hasMany", "hasOne", "belongsTo"]

# POINT 64 : séparateur de paragraphes dans un texte éditorial. La grammaire
# n'accepte pas de retour à la ligne dans un STRING_LITERAL ; ce caractère
# tient sa place dans la spec et n'existe QUE là — le contrat frontend le
# retraduit en saut de paragraphe (frontend_contract.paragraphes). Choisi
# parce qu'il ne se tape pas par accident dans de la prose française.
PARAGRAPH_SEP = " ¶ "

# AJOUT (point 53) : intention visuelle. Le brief transmis à l'IA UI se
# résumait à la phrase de description — souvent trois mots — face à un contrat
# qui décrit les routes au champ près. L'IA recevait donc toute la structure et
# presque aucune intention, et rendait le dénominateur commun. Ces deux menus
# captent ce qu'aucune spec ne peut déduire : le registre voulu et la place des
# images. Menus FERMÉS (le dialogue reste déterministe et sans IA) ; chaque
# entrée porte un libellé court pour l'écran et une phrase pour le brief.
DESIGN_REGISTERS = [
    ("Formal and institutional",
     "restrained, institutional register: readability and trust above all, "
     "few effects, a clear typographic hierarchy"),
    ("Warm and editorial",
     "warm, editorial register: long stretches of text, generous breathing "
     "room, texture and nuance rather than harsh contrasts"),
    ("Dense and functional",
     "dense, functional register: the tool comes before the showcase, "
     "compact information, the user moves fast and comes back often"),
    ("Bold and graphic",
     "bold, graphic register: large typographic scales, strong contrasts, "
     "an assertive visual stance"),
]

DESIGN_IMAGERY = [
    ("Images define the site",
     "the images carry the site (photo, artwork, product): they take up "
     "large areas and drive the layout"),
    ("Text first, supporting images",
     "the text carries the site, images play a supporting role and stay "
     "secondary in the layout"),
    ("No images",
     "no images: everything rests on typography, spacing and "
     "color"),
]

class DialogueError(Exception):
    """Réponse invalide répétée ou incohérence — le moteur ne devine jamais."""

def adresse_de_lien(saisie):
    """Rend l'adresse telle qu'un navigateur saura l'ouvrir, ou None.

    SOURCE UNIQUE, partagée par le dialogue guidé et par la console web de
    la plateforme : deux règles de complétion finiraient par diverger, et
    c'est celle qui décide si un lien de pied de page mène quelque part.

    Personne ne tape « mailto: » ni « https:// » spontanément, et une adresse
    sans schéma est lue comme un chemin RELATIF : le lien mène alors à une
    page inexistante du site lui-même. Compléter n'est pas deviner tant qu'il
    n'existe qu'UNE lecture — et l'appelant DIT ce qu'il a complété, ce qui
    est toute la différence avec le fait de corriger d'office (point 105).
    """
    saisie = saisie.strip()
    if not saisie:
        return None
    if saisie.lower().startswith(("https://", "http://", "mailto:", "tel:")):
        return saisie
    # Le téléphone AVANT le refus des espaces : « +33 6 12 34 56 78 » est
    # la façon dont tout le monde écrit un numéro, et c'est la seule
    # valeur de cette liste qui en contienne légitimement.
    compact = saisie.replace(" ", "")
    if re.fullmatch(r"\+?[0-9.\-]{6,20}", compact):
        return "tel:" + compact
    if " " in saisie:
        return None
    if "@" in saisie and "." in saisie.split("@")[-1]:
        return "mailto:" + saisie
    domaine = saisie.split("/")[0]
    if "." in domaine and not domaine.startswith("."):
        return "https://" + saisie
    return None
