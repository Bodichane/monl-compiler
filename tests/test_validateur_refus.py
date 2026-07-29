"""Ce que le compilateur REFUSE — les branches de garde d'ast_validator.py.

Le README l'affiche comme la différence de fond avec un générateur d'IA : « une
règle sans effet est refusée à la compilation plutôt qu'ignorée en silence ».
`tests/test_parser_errors.py` couvrait les erreurs de SYNTAXE (Lark), et
`tests/test_exploit*.py` les attaques au runtime. Entre les deux, les quelque
cinquante refus du validateur — l'endroit exact où cette promesse se tient —
n'étaient exercés par presque rien : `ast_validator.py` plafonnait à 76 %, et
ses lignes manquantes étaient très majoritairement des `raise`.

Un garde-fou muet est pire qu'un garde-fou absent : il rassure. Un `raise` que
personne n'atteint est un garde-fou dont on ne sait pas s'il fonctionne encore.

**Les témoins font partie du test.** Un validateur cassé qui refuserait TOUTE
spec passerait une suite composée uniquement de refus. Chaque famille de refus
est donc accompagnée de la spec valide la plus proche possible — celle qui ne
diffère que par ce qui est fautif — et cette spec doit compiler.
"""
import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.parser import MonlSyntaxError, parse_monl_string


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# Socle commun : deux entités, un acteur, un workflow. Les cas ci-dessous n'y
# insèrent que les règles à éprouver, pour que la ligne fautive soit la seule
# différence entre un cas et son témoin.
SOCLE = """app T

entity Note
    titre: String
    score: Integer

entity Autre
    nom: String

actor Admin selfRegister

{regles}

workflow W for Admin
    Create Note
    Read Note
"""


def _socle(regles):
    return SOCLE.format(regles=regles)


CIBLES_INEXISTANTES = [
    ("ownedBy sur une entité absente", "rule Fantome.Update ownedBy Admin",
     "'ownedBy' cible l'entité 'Fantome'"),
    ("ownedBy sur une action inventée", "rule Note.Manger ownedBy Admin",
     "action 'Manger' invalide"),
    ("public sur une entité absente", "rule Fantome.Read public",
     "'public' cible l'entité 'Fantome'"),
    ("hidden sur une entité absente", "rule Fantome.titre hidden",
     "'hidden' cible l'entité 'Fantome'"),
    ("hidden sur un champ absent", "rule Note.fantome hidden",
     "référence le champ 'fantome'"),
    ("increments vers une entité absente",
     "rule Note.Create increments Fantome.score by 1",
     "référence l'entité 'Fantome'"),
    ("increments vers un champ absent",
     "rule Note.Create increments Autre.fantome by 1",
     "cible le champ 'Autre.fantome'"),
    ("payable sur une entité absente", "rule Fantome.score payable",
     "'payable' cible l'entité 'Fantome'"),
    ("payable sur un champ absent", "rule Note.fantome payable",
     "champ inexistant"),
]

TYPES_INCOMPATIBLES = [
    ("categorized sur un champ texte",
     'rule Note.titre categorized: "bas" below 5, "haut" otherwise',
     "Integer ou Float"),
    ("generated sur un champ numérique", "rule Note.score generated",
     "doit être un attribut String"),
    ("increments sur un champ texte",
     "rule Note.Create increments Autre.nom by 1",
     "Integer ou Float"),
    # On n'encaisse pas du texte : la seule façon d'en tirer un montant serait
    # de le convertir, donc de deviner.
    ("payable sur un champ texte", "rule Note.titre payable",
     "Money, Float ou Integer"),
]

PALIERS_MAL_FORMES = [
    ("categorized sans palier de secours",
     'rule Note.score categorized: "bas" below 5, "haut" below 10',
     "'otherwise'"),
    ("categorized à seuils décroissants",
     'rule Note.score categorized: "a" below 10, "b" below 5, "c" otherwise',
     "strictement croissants"),
]

REGLES_QUI_SE_CONTREDISENT = [
    ("hidden et categorized sur le même champ",
     'rule Note.score hidden\nrule Note.score categorized: "bas" below 5, "haut" otherwise',
     "à la fois 'hidden' et 'categorized'"),
    ("hidden et generated sur le même champ",
     "rule Note.titre generated\nrule Note.titre hidden",
     "à la fois 'hidden' et 'generated'"),
    # Un montant qu'on ne peut pas lire ne peut pas être vérifié par celui
    # qui le règle : il paierait un chiffre qu'on refuse de lui montrer.
    ("hidden et payable sur le même champ",
     "rule Note.score hidden\nrule Note.score payable",
     "à la fois 'hidden' et 'payable'"),
]

TOUS_LES_CAS = (CIBLES_INEXISTANTES + TYPES_INCOMPATIBLES
                + PALIERS_MAL_FORMES + REGLES_QUI_SE_CONTREDISENT)


@pytest.mark.parametrize("regles,fragment",
                         [(r, f) for _n, r, f in TOUS_LES_CAS],
                         ids=[n for n, _r, _f in TOUS_LES_CAS])
def test_une_regle_fautive_est_refusee_en_nommant_sa_cause(regles, fragment):
    """Refuser ne suffit pas : le message doit nommer ce qui cloche. Un
    validateur qui lèverait une erreur générique laisserait l'auteur de la spec
    chercher lui-même, ce qui est la moitié du travail que le compilateur
    existe pour éviter."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(_socle(regles))
    assert fragment in str(refus.value), str(refus.value)


@pytest.mark.parametrize("regles", [
    "rule Note.Read public",
    "rule Note.titre hidden",
    'rule Note.score categorized: "bas" below 5, "haut" otherwise',
    "rule Note.titre generated",
    "rule Note.score payable",
], ids=["public", "hidden", "categorized", "generated", "payable"])
def test_la_meme_regle_bien_formee_compile(regles):
    """Le témoin. Sans lui, un validateur qui refuserait tout passerait les
    tests ci-dessus sans qu'on s'en aperçoive."""
    assert _valide(_socle(regles))


# Les compteurs ont leur propre témoin : ils exigent une relation entre
# l'entité déclencheuse et l'entité cible, que le socle ci-dessus ne porte pas.
SPEC_COMPTEUR = """app T

entity Post
    contenu: Text
    likes: Integer

entity Like
    note: String

relation Post hasMany Like

actor Membre selfRegister

{regles}

workflow W for Membre
    Create Post
    Create Like
"""


def test_un_compteur_bien_forme_compile():
    """Témoin des trois cas `increments` ci-dessus."""
    assert _valide(SPEC_COMPTEUR.format(
        regles="rule Like.Create increments Post.likes by 1"))


def test_un_compteur_sans_relation_entre_les_deux_entites_est_refuse():
    """Trouvé en construisant le témoin, pas en lisant le validateur : sans
    relation, il n'existe aucune clé étrangère d'où tirer QUEL enregistrement
    incrémenter. La règle ne serait pas seulement inefficace — elle serait
    ambiguë."""
    sans_relation = SPEC_COMPTEUR.replace("relation Post hasMany Like\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans_relation.format(
            regles="rule Like.Create increments Post.likes by 1"))
    assert "exige une relation" in str(refus.value)


def test_un_compteur_hors_creation_est_refuse():
    """`increments` n'est pris en charge que sur `Create` : le brancher sur
    `Update` laisserait croire à un compteur qui suit les modifications."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_COMPTEUR.format(
            regles="rule Like.Update increments Post.likes by 1"))
    assert "'Create'" in str(refus.value)


# ------------------------------------- incompatibilités entre deux mécanismes --
def test_generated_exige_un_appelant_identifie(spec=None):
    """Point 30 : pas d'identité fiable, pas de pseudonyme dérivable. Une
    création `public` et un champ `generated` sur la même entité ne peuvent pas
    coexister — et ce refus ne peut se voir qu'en croisant deux règles que rien
    ne relie syntaxiquement."""
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Post
    author: String
actor Membre selfRegister
rule Post.Create public
rule Post.author generated
workflow W for Membre
    Create Post
""")
    assert "'generated'" in str(refus.value) and "'public'" in str(refus.value)


# ----------------------------------------- paiement (point 74) : les deux --
# refus qui exigent leur propre spec, le socle ne pouvant pas les porter.
SPEC_PAYABLE = """app T

entity Commande
    total: Money
    frais: Money

actor Client selfRegister

{regles}

workflow W for Client
    Create Commande
    Read Commande
"""


def test_un_seul_champ_payable_par_entite():
    """Deux montants sur la même entité, et plus rien ne dit lequel encaisser.
    Le compilateur ne peut pas trancher à la place de l'auteur — additionner
    serait une invention, prendre le premier un tirage au sort. Témoin ci-
    dessous : la même spec avec un seul `payable` compile."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PAYABLE.format(
            regles="rule Commande.total payable\nrule Commande.frais payable"))
    assert "plusieurs champs 'payable'" in str(refus.value)


def test_un_seul_champ_payable_compile():
    """Le témoin du test précédent : sans lui, un validateur qui refuserait
    toute règle `payable` passerait aussi bien."""
    assert _valide(SPEC_PAYABLE.format(regles="rule Commande.total payable"))


def test_payable_exige_un_appelant_identifie():
    """Même raison qu'au point 30 pour `generated`, mais avec de l'argent au
    bout : une création `public` n'a aucune identité à rattacher au règlement
    — ni personne à qui rembourser. Ce refus ne se voit qu'en croisant deux
    règles que rien ne relie syntaxiquement."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PAYABLE.format(
            regles="rule Commande.Create public\nrule Commande.total payable"))
    assert "'payable'" in str(refus.value) and "'public'" in str(refus.value)


def test_ownedby_et_accessibleby_ne_peuvent_pas_regir_la_meme_action():
    """Point 31 : `accessibleBy` généralise `ownedBy`. Les cumuler laisserait
    deux contrôles d'accès concurrents sur une même route, dont l'ordre
    d'application déciderait du résultat."""
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Msg
    corps: Text
    dest_id: Integer
entity Membre
    nom: String
relation Membre hasMany Msg
actor Membre selfRegister
rule Msg.Read ownedBy Membre
rule Msg.Read accessibleBy membre_id, dest_id
workflow W for Membre
    Read Msg
""")
    assert "ownedBy" in str(refus.value) and "accessibleBy" in str(refus.value)


def test_ownedby_sans_relation_correspondante_est_refuse():
    """Une règle de propriété sans relation d'où tirer le propriétaire ne
    protégerait rien. C'est le cas type de la « règle sans effet » que le
    README promet de refuser plutôt que d'ignorer."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(_socle("rule Note.Update ownedBy Admin"))
    assert "aucune relation" in str(refus.value)


def test_deux_acteurs_sur_la_meme_ecriture_ne_compilent_pas():
    """Point 1, la règle fondatrice : un partage d'autorité doit être déclaré
    (`sharedBy`), jamais accidentel."""
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
actor Editeur selfRegister
workflow A for Admin
    Update Note
workflow B for Editeur
    Update Note
""")
    assert "CRITICAL_COLLISION" in str(refus.value)


# --------------------------------------------------- workflows et blocs annexes --
def test_un_workflow_ne_peut_pas_viser_un_acteur_non_declare():
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Inconnu
    Create Note
""")
    assert "'Inconnu'" in str(refus.value)


def test_un_workflow_ne_peut_pas_viser_une_entite_absente():
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Admin
    Create Fantome
""")
    assert "'Fantome'" in str(refus.value)


def test_execute_exige_que_le_bloc_custom_existe():
    """Sans ce refus, `Execute` sur un bloc absent produirait un app.py qui
    appelle une fonction que sandbox_ai.py ne contient pas — une ImportError
    au démarrage plutôt qu'une erreur de compilation."""
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
workflow W for Admin
    Execute CalculMagique
""")
    assert "CalculMagique" in str(refus.value)


@pytest.mark.parametrize("bloc,fragment", [
    ("ui Fantome\n    primary: titre", "cible une entité qui n'existe pas"),
    ("ui Note\n    primary: fantome", "primary: fantome"),
    ("ui Note\n    order: titre, fantome", "champs inconnus"),
    ("seed Fantome\n    titre: \"a\"", "cible l'entité 'Fantome'"),
    ("seed Note\n    titre: \"a\", fantome: \"b\"", "référence le champ 'fantome'"),
], ids=["ui-entité", "ui-primary", "ui-order", "seed-entité", "seed-champ"])
def test_les_blocs_annexes_sont_validés_comme_les_regles(bloc, fragment):
    """`ui` et `seed` ne portent aucune sécurité — mais une faute de frappe qui
    y passe inaperçue se paie au rendu ou au démarrage, loin de sa cause."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(_socle(bloc))
    assert fragment in str(refus.value)


def test_un_bloc_ui_bien_forme_compile():
    """Témoin des cinq cas ci-dessus."""
    assert _valide(_socle("ui Note\n    primary: titre\n    order: titre, score"))


def test_accessibleby_a_moins_de_deux_colonnes_est_arrete_par_la_grammaire():
    """Le garde-fou du point 31 (« au moins deux colonnes distinctes, sinon
    `ownedBy` ») n'est PAS dans le validateur : la grammaire exige la virgule,
    donc une colonne unique n'atteint jamais ast_validator.py. Le test le dit
    plutôt que de chercher un ASTValidationError qui ne viendra pas — savoir
    quelle couche tient un garde-fou est ce qui permet de ne pas le déplacer
    par mégarde."""
    with pytest.raises(MonlSyntaxError):
        _valide(_socle("rule Note.Read accessibleBy titre"))


def test_payable_sans_champ_est_arrete_par_la_grammaire():
    """Même situation que ci-dessus, et il faut le dire pour la même raison :
    `ast_validator.py` porte un refus pour une règle `payable` qui ne
    nommerait pas `Entite.champ`, mais le terminal REFERENCE de la grammaire
    EXIGE le point. Ce `raise` est donc inatteignable, et le garde-fou réel
    est dans `parser.py`. Le laisser croire au validateur, c'est risquer de
    l'y déplacer un jour en pensant le renforcer."""
    with pytest.raises(MonlSyntaxError):
        _valide(_socle("rule Note payable"))
