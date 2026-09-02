"""La démonstration de l'accueil : une spec qui compile POUR DE VRAI.

Avant ce module, la carte « PetiteBoutique » annonçait 3 entités, 17 routes et
12 fichiers, listait un `README.md`, et affirmait en toutes lettres que « les
métriques ci-dessous sont vérifiées en recompilant la spec dans les tests ».

Mesuré : aucun test ne compilait cette spec, `PetiteBoutique` n'existait nulle
part dans le code, le fragment affiché ne pouvait pas compiler (ni `app`, ni
`actor`, ni `workflow`), et sur les trois chiffres deux étaient faux — 14
routes et 15 fichiers. C'est le défaut du point 164, où la page `/mcp`
annonçait quatre outils inexistants parce que la liste était écrite à la main ;
en pire, puisque la page revendiquait ici une vérification qui n'existait pas.

La spec ci-dessous est donc la VRAIE : `tests/test_platform_landing.py` la
compile et confronte chaque chiffre et chaque nom de fichier de l'arborescence
au résultat. La page ne peut plus nommer un fichier que le compilateur ne
produit pas.

L'extrait montré à l'écran est DÉCOUPÉ dans cette spec, jamais recopié à côté :
deux textes à tenir d'accord divergent toujours.
"""

from __future__ import annotations

#: Elle compile. Le `required` sur le multiplicateur n'est pas décoratif : le
#: compilateur REFUSE `derivedFrom` sans lui (point 77), et l'écrire ici montre
#: précisément ce que la page promet — une règle incohérente est refusée.
SPEC_VITRINE = """app PetiteBoutique

entity Produit
    nom: String
    prix: Money
    stock: Integer

entity Commande
    total: Money
    passeeLe: DateTime

entity Ligne
    quantite: Integer
    montant: Money

actor Client selfRegister

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne

rule Produit.prix min 0
rule Produit.stock min 0
rule Produit.Read public
rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.montant derivedFrom Produit.prix by quantite
rule Commande.total sumOf Ligne.montant
rule Commande.passeeLe timestamp
rule Commande.total payable
rule Ligne.Create decrements Produit.stock by quantite

workflow Acheter for Client
    Create Commande
    Create Ligne
    Read Produit
    Read Commande
"""

#: L'extrait affiché : tout ce qui concerne UNE entité, découpé dans la spec
#: réelle. Le découpage se fait par ce que les lignes CONCERNENT et non par des
#: bornes de position — un numéro de ligne se décale à la première règle
#: ajoutée, en silence, et l'extrait montrerait alors autre chose.
ENTITE_MONTREE = "Produit"


def extrait_affiche() -> str:
    """Le bloc d'entité et ses règles, pris dans `SPEC_VITRINE`.

    ÉCHOUE plutôt que de rendre une chaîne vide : un extrait introuvable
    afficherait un cadre vide, ce qui ressemble à un défaut de style et non à
    une spec qui a changé de forme.
    """
    lignes = SPEC_VITRINE.splitlines()
    bloc, dans_entite = [], False
    for ligne in lignes:
        if ligne.startswith(f"entity {ENTITE_MONTREE}"):
            dans_entite = True
            bloc.append(ligne)
        elif dans_entite and ligne.startswith((" ", "\t")):
            bloc.append(ligne)
        elif dans_entite and not ligne.strip():
            dans_entite = False
        elif ligne.startswith(f"rule {ENTITE_MONTREE}."):
            bloc.append(ligne)
    regles = [ligne for ligne in bloc if ligne.startswith("rule ")]
    if not regles or len(bloc) == len(regles):
        raise AssertionError(
            f"extrait vide ou sans règle pour {ENTITE_MONTREE} : la spec a "
            "changé de forme, la carte afficherait un cadre creux")
    champs = [ligne for ligne in bloc if ligne not in regles]
    return "\n".join(champs) + "\n\n" + "\n".join(regles)


#: Les chiffres annoncés par la carte. Ils sont ici pour être CONFRONTÉS : le
#: témoin compile `SPEC_VITRINE` et exige l'égalité, donc les corriger à la
#: main sans recompiler fait rougir la suite.
ENTITES = 3
ROUTES = 14
FICHIERS = 15

#: L'arborescence montrée. Chaque nom doit exister dans l'archive produite —
#: c'est ce que le témoin vérifie, et c'est tout l'objet de ce module. La liste
#: reste un EXTRAIT lisible : on ne montre pas quinze lignes dans une carte.
ARBRE = (
    ("app.py", "API FastAPI"),
    ("schema.sql", "base de données"),
    ("frontend_contract.json", "droits et routes"),
    ("manage.py", "administration"),
    ("Dockerfile", "déploiement"),
)
