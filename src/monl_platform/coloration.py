"""Coloration syntaxique d'une spécification monl, côté SERVEUR.

Il n'y avait rien à colorier sur la page d'accueil, et ailleurs les `<span>`
étaient écrits À LA MAIN dans les chaînes — donc deux classes en tout, `.kw` et
`.cm`, et le même or pour tout mot-clé de toute spec, sur toutes les pages.
C'est ce qui faisait revenir la couleur d'accent partout.

**Aucun mot-clé n'est écrit ici.** Les trois tables sont DÉRIVÉES des terminaux
de la vraie grammaire (`monl.parser.grammaire.grammar`) : une brique qui ajoute
un mot-clé le voit coloré sans qu'on y pense, et un mot qui disparaît de la
grammaire cesse d'être coloré. Une liste recopiée aurait divergé au premier
point de journal — c'est le reproche du point 146, appliqué à la coloration.

Le rendu est fait au serveur, sans une ligne de JavaScript : une page qui
n'exécute rien montre déjà le code coloré, et la plateforme n'ajoute aucune
dépendance de coloration.
"""

from __future__ import annotations

import html
import re

from monl.parser.grammaire import grammar


def _terminal(nom: str) -> frozenset:
    """Les alternatives littérales d'un terminal de la grammaire.

    Échoue plutôt que de rendre un ensemble vide : un terminal renommé
    laisserait sinon toute une famille de mots sans couleur, en silence — et
    une coloration qui manque ne ressemble pas à une panne.
    """
    trouve = re.search(rf"^\s*{nom}:\s*(.+)$", grammar, re.M)
    if not trouve:
        raise RuntimeError(f"terminal {nom} introuvable dans la grammaire")
    alternatives = frozenset(re.findall(r'"([^"]+)"', trouve.group(1)))
    if not alternatives:
        raise RuntimeError(f"terminal {nom} sans alternative littérale")
    return alternatives


TYPES = _terminal("TYPE")
ACTIONS = _terminal("ACTION_TYPE") | {"Execute"}   # Execute vit hors du terminal
VALIDATIONS = _terminal("VALIDATION_TYPE")
RELATIONS = _terminal("RELATION_TYPE")

# Tout le reste des littéraux de la grammaire est un mot-clé. Prendre le
# complément plutôt qu'une liste garantit qu'aucun mot ne passe entre les
# mailles : un mot-clé neuf est coloré le jour où il entre dans la grammaire.
_LITTERAUX = frozenset(re.findall(r'"([a-zA-Z][a-zA-Z_]{1,24})"', grammar))
MOTS_CLES = _LITTERAUX - TYPES - ACTIONS

_MOTIF = re.compile(
    r"""(?P<commentaire>\#[^\n]*)
      | (?P<chaine>"[^"\n]*")
      | (?P<nombre>\b\d+(?:\.\d+)?\b)
      | (?P<mot>[A-Za-z_][A-Za-z0-9_]*)""",
    re.VERBOSE,
)

_CLASSES = {
    "commentaire": "s-cm",
    "chaine": "s-str",
    "nombre": "s-num",
}


def _classe_du_mot(mot: str) -> str | None:
    if mot in TYPES:
        return "s-type"
    if mot in ACTIONS:
        return "s-act"
    if mot in VALIDATIONS or mot in RELATIONS or mot in MOTS_CLES:
        return "s-kw"
    # Un identifiant capitalisé est un nom DÉCLARÉ (entité, acteur, workflow).
    # Le reste — noms de champs, valeurs libres — garde l'encre du bloc : tout
    # colorier ne distingue plus rien.
    if mot[:1].isupper():
        return "s-nom"
    return None


def coloriser(source: str) -> str:
    """Rend une spécification monl en HTML coloré, échappée.

    L'échappement se fait ICI et pas avant : le texte est parcouru brut, et
    chaque morceau est échappé au moment d'être écrit. Échapper d'abord ferait
    voir `&quot;` au motif de chaîne, qui ne reconnaîtrait plus rien.
    """
    morceaux, position = [], 0
    for trouve in _MOTIF.finditer(source):
        morceaux.append(html.escape(source[position:trouve.start()]))
        genre = trouve.lastgroup
        texte = trouve.group()
        classe = _CLASSES.get(genre) or _classe_du_mot(texte)
        morceaux.append(f'<span class="{classe}">{html.escape(texte)}</span>'
                        if classe else html.escape(texte))
        position = trouve.end()
    morceaux.append(html.escape(source[position:]))
    return "".join(morceaux)


def en_lignes(source: str) -> str:
    """Même coloration, rendue avec `<br>` plutôt que dans un `<pre>`.

    Le terminal du héros n'est pas un bloc préformaté : il portait sa PROPRE
    coloration, en `<b>` doré, donc un troisième endroit où l'or marquait tout
    mot-clé. Une fonction de plus vaut mieux qu'une convention de plus.
    """
    lignes = []
    for ligne in coloriser(source).split("\n"):
        # Toute la CREUSE de tête, quelle qu'elle soit : hors d'un `<pre>` les
        # espaces consécutives se réduisent à une seule, et l'indentation de la
        # spec disparaîtrait sans bruit.
        creux = len(ligne) - len(ligne.lstrip(" "))
        lignes.append("&nbsp;" * creux + ligne[creux:])
    return "<br>".join(lignes)


def bloc(source: str, classes: str = "codeblock") -> str:
    """Un `<pre>` complet, prêt à poser dans une page."""
    return f'<pre class="{classes}"><code>{coloriser(source)}</code></pre>'
