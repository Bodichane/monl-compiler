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

relation Autre hasMany Note

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
    ("restrictedTo sur une entité absente", "rule Fantome.titre restrictedTo Admin",
     "'restrictedTo' cible l'entité 'Fantome'"),
    ("restrictedTo sur un champ absent", "rule Note.fantome restrictedTo Admin",
     "cible le champ 'Note.fantome'"),
    ("writableAfterPayment sur une entité absente",
     "rule Fantome.titre writableAfterPayment Admin",
     "'writableAfterPayment' cible l'entité 'Fantome'"),
    ("writableAfterPayment sur un champ absent",
     "rule Note.fantome writableAfterPayment Admin",
     "cible le champ 'Note.fantome'"),
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
    # `payable` ne figure PLUS ici : depuis le point 79 il exige un montant
    # calculé par le serveur, donc une entité source, une relation, une
    # quantité `required` et un propriétaire — une structure que le socle ne
    # porte pas, et qu'y ajouter romprait sa raison d'être (« la ligne fautive
    # est la seule différence entre un cas et son témoin »). Son témoin est
    # `test_un_seul_champ_payable_compile`, sur la spec dédiée plus bas.
], ids=["public", "hidden", "categorized", "generated"])
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

entity Article
    prix: Money

entity Commande
    quantite: Integer
    total: Money
    frais: Money

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

{regles}

workflow W for Client
    Create Commande
    Read Commande
"""

# Ce que le point 79 rend obligatoire à côté de tout `payable` : un montant
# que le client ne peut pas écrire. Les cas de refus ci-dessous ne l'incluent
# PAS quand leur propre refus se déclenche avant (deux champs `payable`,
# création `public`) — leur garde-fou vit dans la boucle `payable`, en amont du
# recoupement final.
DERIVE = "rule Commande.total derivedFrom Article.prix by quantite"


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
    toute règle `payable` passerait aussi bien. C'est aussi, depuis le point 79,
    le témoin de la forme COMPLÈTE qu'un encaissement exige — montant calculé
    par le serveur inclus."""
    assert _valide(SPEC_PAYABLE.format(
        regles=f"{DERIVE}\nrule Commande.total payable"))


def test_payable_refuse_un_montant_que_le_client_peut_ecrire():
    """Le refus du point 79, et la garantie que le point 74 ne tenait pas.

    `payable` promettait « le montant vient de la base, jamais du corps de
    requête ». C'était vrai de la ROUTE et faux du système : le créateur d'un
    enregistrement en devient le propriétaire (sa clé étrangère est peuplée avec
    `current_user_id`), et la route de règlement n'accepte que le propriétaire —
    donc le payeur écrivait lui-même ce qu'il payait. Deux exploits de trois
    requêtes suffisaient à encaisser un centime pour 945 euros.

    Le refus est CASSANT et c'est voulu : toute boutique compilée avant lui
    pouvait être volée."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PAYABLE.format(regles="rule Commande.total payable"))
    message = str(refus.value)
    assert "le client peut l'écrire" in message
    # Le message doit nommer la sortie, pas seulement le problème.
    assert "derivedFrom" in message


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


def test_restrictedto_sur_un_acteur_non_declare():
    """Point 112 : avant, rien ne vérifiait que l'acteur nommé par
    'restrictedTo' existe — une faute de frappe désactivait la restriction
    en silence, sans qu'aucun avertissement n'apparaisse."""
    with pytest.raises(ASTValidationError) as refus:
        _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
rule Note.titre restrictedTo Fantome
workflow W for Admin
    Read Note
""")
    assert "restrictedTo" in str(refus.value) and "Fantome" in str(refus.value)


def test_restrictedto_bien_forme_compile():
    """Le témoin : sans lui, un validateur qui refuserait tout 'restrictedTo'
    passerait aussi le test précédent."""
    assert _valide("""app T
entity Note
    titre: String
actor Admin selfRegister
rule Note.titre restrictedTo Admin
workflow W for Admin
    Read Note
""")


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


# ------------------------------- brique 10 : derivedFrom (point 77) ----------

# Socle dédié : une entité calculée qui a un propriétaire ET une source
# distincte, c'est-à-dire la forme minimale que la brique exige. Les cas
# ci-dessous n'en changent qu'une ligne à la fois.
SOCLE_DERIVE = """app D

entity Article
    nom: String
    prix: Money

entity Commande
    quantite: Integer
    total: Money

entity Client
    displayName: String

relation Client hasMany Commande
relation Article hasMany Commande

actor Client selfRegister

rule Commande.quantite required
rule Commande.Read ownedBy Client

{regles}

workflow Acheter for Client
    Create Commande
    Read Commande
"""


def _socle_derive(regles=""):
    return SOCLE_DERIVE.format(regles=regles)


REGLE_VALIDE = "rule Commande.total derivedFrom Article.prix by quantite"


def test_une_derivation_bien_formee_compile():
    """Témoin des refus ci-dessous : sans lui, un validateur qui refuserait
    TOUTE dérivation les ferait tous passer."""
    normalise = _valide(_socle_derive(REGLE_VALIDE))
    assert normalise["security"]["derived_fields"] == [{
        "entity": "Commande", "field": "total",
        "source_entity": "Article", "source_field": "prix",
        "factor": "quantite",
    }]


@pytest.mark.parametrize("regles,fragment", [
    ("rule Fantome.total derivedFrom Article.prix by quantite",
     "cible l'entité 'Fantome'"),
    ("rule Commande.total derivedFrom Fantome.prix by quantite",
     "lit l'entité 'Fantome'"),
    ("rule Commande.fantome derivedFrom Article.prix by quantite",
     "champ inexistant"),
    ("rule Commande.total derivedFrom Article.nom by quantite",
     "lit 'Article.nom'"),
    (REGLE_VALIDE + "\nrule Commande.total derivedFrom Article.prix by quantite",
     "plusieurs règles 'derivedFrom'"),
    # `quantite` est Integer, donc recevable à la fois comme champ calculé et
    # comme multiplicateur : c'est le seul montage qui ATTEINT ce refus. Avec
    # `total` (Money), c'est le contrôle de type du multiplicateur qui refuse
    # avant — juste, mais pas le garde-fou qu'on prétend éprouver.
    ("rule Commande.quantite derivedFrom Article.prix by quantite",
     "son propre multiplicateur"),
    ("rule Commande.total derivedFrom Article.prix by nom",
     "champ inexistant"),
    (REGLE_VALIDE + "\nrule Commande.total hidden",
     "à la fois 'hidden' et 'derivedFrom'"),
], ids=["entité-calculée-absente", "entité-source-absente", "champ-absent",
        "source-non-numérique", "deux-règles", "auto-multiplicateur",
        "multiplicateur-absent", "cumul-hidden"])
def test_les_derivations_mal_formees_sont_refusees(regles, fragment):
    """Un calcul mal déclaré doit échouer à la COMPILATION : c'est un montant
    à encaisser, l'échec au runtime coûterait de l'argent."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(_socle_derive(regles))
    assert fragment in str(refus.value)


def test_le_multiplicateur_doit_etre_declare_required():
    """Sans `required`, un client qui omet la quantité ferait calculer sur du
    vide — et le montant à encaisser serait nul ou faux."""
    spec = _socle_derive(REGLE_VALIDE).replace(
        "rule Commande.quantite required\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "required" in str(refus.value)


def test_la_source_ne_peut_pas_etre_le_proprietaire():
    """La clé étrangère du propriétaire est peuplée depuis le JETON, jamais
    choisie par le client : si la source possédait l'entité, aucune ligne ne
    pourrait être désignée à la création."""
    spec = _socle_derive("rule Commande.total derivedFrom Client.remise by quantite")
    spec = spec.replace("entity Client\n    displayName: String",
                        "entity Client\n    displayName: String\n    remise: Float")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "propriétaire" in str(refus.value)


def test_une_entite_sans_proprietaire_ne_peut_pas_deriver():
    """C'est le propriétaire qui distingue la clé étrangère peuplée par le
    serveur de celle que le client fournit pour désigner la ligne à lire."""
    spec = _socle_derive(REGLE_VALIDE).replace(
        "rule Commande.Read ownedBy Client\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "propriétaire" in str(refus.value)


def test_une_source_sans_relation_est_refusee():
    """Sans relation, rien ne dit QUELLE ligne de la source lire — même
    exigence que pour 'increments' (point 27)."""
    spec = _socle_derive(REGLE_VALIDE).replace(
        "relation Article hasMany Commande\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "exige une relation" in str(refus.value)


# ------------------------- propriété : la chaîne doit remonter à un COMPTE ---
#
# Point 80 puis 81. `ownedBy <Entité>` compilait à l'origine en silence, en
# produisant du code incohérent : clé étrangère annoncée vers la table des
# comptes, identifiant de l'appelant écrit à la place du rattachement demandé,
# filtre de lecture comparant un id d'enregistrement à un id de compte. Le
# point 80 l'a refusé ; le point 81 en a fait une brique (propriété
# TRANSITIVE), à une condition : la chaîne doit aboutir à un acteur. Ce qui
# suit vérifie les cas où elle n'aboutit pas.

SPEC_PROPRIETE = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne

actor Client selfRegister

{regles}

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""

CHAINE_COMPLETE = "rule Commande.Read ownedBy Client"


def test_une_chaine_de_propriete_qui_remonte_a_un_acteur_compile():
    """La brique elle-même (point 81) : « une ligne appartient à qui possède sa
    commande ». Le témoin de tous les refus ci-dessous — sans lui, un validateur
    qui refuserait toute chaîne les passerait tous."""
    assert _valide(SPEC_PROPRIETE.format(
        regles=CHAINE_COMPLETE + "\nrule Ligne.Read ownedBy Commande"))


def test_un_intermediaire_sans_proprietaire_ne_mene_a_aucun_compte():
    """Sans `ownedBy` sur l'intermédiaire, rien ne relie la ligne à un compte :
    le serveur n'aurait aucune colonne à comparer. C'est le cas exact que le
    point 80 avait trouvé en train de compiler."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PROPRIETE.format(regles="rule Ligne.Read ownedBy Commande"))
    message = str(refus.value)
    assert "ne remonte à AUCUN acteur" in message
    # Le message doit dire ce qui manque, pas seulement ce qui cloche.
    assert "ownedBy" in message


def test_une_chaine_a_deux_niveaux_est_desormais_resolue():
    """BRIQUE 24 (point 107) : ce cas était REFUSÉ (« plus d'un niveau »), la
    jointure générée ne remontant qu'un maillon. La marche remonte désormais
    toute la profondeur jusqu'à un acteur, maillon par maillon. La classe de
    défaut du point 80 ne reparaît PAS pour autant : cycle, cul-de-sac et
    maillon ambigu restent refusés (tests dédiés dans
    tests/test_transitive_profondeur.py), et la profondeur 2 est éprouvée
    contre un vrai serveur dans le même fichier."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Detail
    note: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Ligne hasMany Detail

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Detail.Read ownedBy Ligne

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Create Detail
    Read Detail
"""
    ast = _valide(spec)
    transitif = ast["security"]["transitive_ownership"]
    assert transitif["Ligne"] == {"chain": ["Commande"], "actor": "Client"}
    assert transitif["Detail"] == {"chain": ["Ligne", "Commande"], "actor": "Client"}


def test_un_intermediaire_a_deux_proprietaires_rend_la_chaine_ambigue():
    """Deux propriétaires sur l'intermédiaire : le serveur ne saurait pas lequel
    vérifier. Choisir au hasard de l'ordre d'écriture de la spec est exactement
    ce que le correctif de la bêta 3 avait déjà refusé ailleurs."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Vendeur hasMany Commande
relation Commande hasMany Ligne

actor Client selfRegister
actor Vendeur

rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Vendeur
rule Ligne.Read ownedBy Commande

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne

workflow V for Vendeur
    Update Commande
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "ambiguë" in str(refus.value)


def test_melanger_propriete_directe_et_transitive_est_refuse():
    """La colonne de propriété serait à la fois peuplée depuis le jeton (pour
    une règle) et fournie par le client (pour l'autre) : deux traitements
    contradictoires sur une seule colonne."""
    spec = """app P

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Client hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Update ownedBy Client

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Update Ligne
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "un seul propriétaire" in str(refus.value)


def test_payable_sur_une_entite_possedee_transitivement_compile_desormais():
    """POINT 87 : ce cas était REFUSÉ (point 81), et le refus a été levé.

    Il ne protégeait pas d'une impossibilité mais d'une comparaison fausse : la
    route de règlement opposait `current_user_id` à une clé étrangère qui, sous
    chaîne transitive, porte un id d'enregistrement intermédiaire. La brique 11
    fournissait déjà la jointure qui rend l'id de COMPTE — la route l'emploie.

    Ce test garde donc l'inverse de ce qu'il gardait. Les trois refus qui
    rendent `payable` sûr sont vérifiés ailleurs et n'ont pas bougé : chaîne
    remontant à un acteur (point 81), montant incalculable par le client
    (point 79), relation entrante obligatoire (point 75)."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    statut: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Ligne.sousTotal payable

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    ast = _valide(spec)
    assert ast["security"]["payable_fields"] == [{"entity": "Ligne", "field": "sousTotal"}]
    assert ast["security"]["transitive_ownership"]["Ligne"] == {"chain": ["Commande"], "actor": "Client"}


def test_payable_transitif_exige_toujours_un_montant_incalculable_par_le_client():
    """Le témoin du test ci-dessus : lever le refus du point 81 ne lève PAS
    celui du point 79. Sans `derivedFrom`, le payeur écrirait encore ce qu'il
    règle — et la propriété transitive n'y change rien, puisque le créateur
    d'une ligne doit posséder la commande à laquelle il la rattache."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    statut: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal payable

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "le client peut l'écrire" in str(refus.value)


# ------------------------- agrégation : sommer un total (brique 12) ----------
#
# Point 82. `derivedFrom` ne lit qu'UNE ligne liée : une commande à plusieurs
# articles ne savait pas ce qu'elle coûtait. `sumOf` la somme. Le refus qui
# porte tout le reste est le dernier de cette section : sommer un montant que le
# client écrit rendrait au payeur la main sur ce qu'il règle — la faille du
# point 77, revenue par le panier, exactement comme le cadrage du point 80 le
# redoutait.

SPEC_PANIER = """app P

entity Article
    prix: Money

entity Commande
    total: Money
    libelle: String

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
{regles}

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""

SOMME = "rule Commande.total sumOf Ligne.sousTotal"


def test_une_somme_bien_formee_compile():
    """Le témoin de toute cette section : sans lui, un validateur qui refuserait
    toute règle `sumOf` passerait chacun des refus ci-dessous."""
    assert _valide(SPEC_PANIER.format(regles=SOMME))


def test_un_panier_somme_est_encaissable():
    """Point 82, et l'aboutissement des points 77 à 81 : jusqu'ici, `payable`
    n'acceptait qu'un champ `derivedFrom`, donc une commande à UN article. Un
    total sommé est calculé par le serveur, il satisfait donc le refus du
    point 79."""
    assert _valide(SPEC_PANIER.format(
        regles=SOMME + "\nrule Commande.total payable"))


# ---------------- écriture supervisée après paiement ------------------------

SPEC_APRES_PAIEMENT = SPEC_PANIER.replace(
    "    libelle: String", "    libelle: String\n    statut: String\n    creeLe: DateTime\n"
    "    reference: String\n    quantite: Integer\n    calcule: Money"
).replace(
    "relation Client hasMany Commande",
    "relation Client hasMany Commande\nrelation Article hasMany Commande"
).replace(
    "actor Client selfRegister", "actor Client selfRegister\nactor Superviseur"
)


def _apres_paiement(regles):
    base = (SOMME + "\nrule Commande.total payable"
            "\nrule Commande.quantite required")
    return SPEC_APRES_PAIEMENT.format(regles=base + "\n" + regles)


def test_writable_after_payment_sur_acteur_non_declare_est_refuse():
    with pytest.raises(ASTValidationError) as refus:
        _valide(_apres_paiement(
            "rule Commande.statut writableAfterPayment Fantome"))
    assert "writableAfterPayment" in str(refus.value)
    assert "Fantome" in str(refus.value)


def test_writable_after_payment_exige_une_entite_payable():
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PANIER.format(
            regles=SOMME
            + "\nrule Commande.libelle writableAfterPayment Client"))
    assert "ne vaut que sur une entité 'payable'" in str(refus.value)


@pytest.mark.parametrize("regle_serveur", [
    "rule Commande.statut generated",
    "rule Commande.calcule derivedFrom Article.prix by quantite",
    "rule Commande.creeLe timestamp",
    'rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"',
], ids=["generated", "derivedFrom", "timestamp", "numbered"])
def test_writable_after_payment_refuse_un_champ_ecrit_par_le_serveur(
        regle_serveur):
    cible = {
        "generated": "statut",
        "derivedFrom": "calcule",
        "timestamp": "creeLe",
        "numbered": "reference",
    }[regle_serveur.split()[2]]
    spec = _apres_paiement(
        regle_serveur
        + f"\nrule Commande.{cible} writableAfterPayment Superviseur")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "writableAfterPayment" in str(refus.value)
    assert regle_serveur.split()[2] in str(refus.value)


def test_writable_after_payment_refuse_un_champ_somme():
    """`sumOf` manquait à la liste des familles serveur ci-dessus : une entité
    'payable' dont le montant est 'sumOf' (le panier à plusieurs lignes,
    seule forme éprouvée depuis le point 82 pour un total encaissable)
    pouvait déclarer 'writableAfterPayment' sur CE MÊME champ. La route
    dédiée qui en résulte écrit le total en base sans recalcul ET sans le
    verrou de paiement — exactement la faille des points 77/82 rouverte par
    une combinaison de règles que rien ne signalait à la compilation."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(_apres_paiement(
            "rule Commande.total writableAfterPayment Superviseur"))
    assert "writableAfterPayment" in str(refus.value)
    assert "sumOf" in str(refus.value)


def test_writable_after_payment_refuse_le_proprietaire():
    with pytest.raises(ASTValidationError) as refus:
        _valide(_apres_paiement(
            "rule Commande.statut writableAfterPayment Client"))
    assert "déjà propriétaire" in str(refus.value)


def test_writable_after_payment_refuse_deux_acteurs_par_entite():
    spec = _apres_paiement(
        "actor AutreSuperviseur\n"
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment AutreSuperviseur")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "Superviseur" in str(refus.value)
    assert "AutreSuperviseur" in str(refus.value)


def test_writable_after_payment_refuse_un_doublon_de_champ():
    regle = "rule Commande.statut writableAfterPayment Superviseur"
    with pytest.raises(ASTValidationError) as refus:
        _valide(_apres_paiement(regle + "\n" + regle))
    assert "plusieurs règles 'writableAfterPayment'" in str(refus.value)


def test_writable_after_payment_bien_forme_compile_et_normalise():
    ast = _valide(_apres_paiement(
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment Superviseur"))
    assert ast["security"]["writable_after_payment"] == {
        "Commande": {
            "actor": "Superviseur",
            "fields": ["statut", "libelle"],
        }
    }


def test_writable_after_payment_ne_casse_ni_create_ni_update(tmp_path):
    """Un champ absent du schéma générique ne doit jamais être lu sur `data`.

    Le checkout réel de CodexShop révélait sinon un AttributeError avant même
    l'insertion de la commande : les champs de suivi, réservés au superviseur,
    n'existent légitimement pas encore à la création.
    """
    from monl.generator import MonlSecureGenerator

    spec = _apres_paiement(
        "rule Commande.statut writableAfterPayment Superviseur\n"
        "rule Commande.libelle writableAfterPayment Superviseur")
    spec = spec.replace(
        "rule Commande.Read ownedBy Client",
        "rule Commande.Read ownedBy Client\nrule Commande.Update ownedBy Client",
    ).replace("    Read Commande\n", "    Read Commande\n    Update Commande\n")
    ast = _valide(spec)
    MonlSecureGenerator(ast, output_dir=str(tmp_path)).generate_all()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    creation = genere.split("def create_commande(", 1)[1].split("@app.", 1)[0]
    modification = genere.split("def update_commande(", 1)[1].split("@app.", 1)[0]

    assert "data.statut" not in creation
    assert "data.libelle" not in creation
    assert "data.statut" not in modification
    assert "data.libelle" not in modification


@pytest.mark.parametrize("regle, attendu", [
    ("rule Fantome.total sumOf Ligne.sousTotal", "n'existe pas"),
    ("rule Commande.total sumOf Fantome.sousTotal", "n'existe pas"),
    ("rule Commande.libelle sumOf Ligne.sousTotal", "Money, Float ou Integer"),
    ("rule Commande.absent sumOf Ligne.sousTotal", "champ inexistant"),
    ("rule Commande.total sumOf Ligne.quantiteAbsente", "champ inexistant"),
    # Une entité ne peut pas s'additionner elle-même.
    ("rule Commande.total sumOf Commande.total", "ne peut pas s'additionner"),
    # Sans relation parent-enfant, la somme porterait sur la table entière.
    ("rule Commande.total sumOf Article.prix", "relation parent-enfant"),
])
def test_refus_de_somme_mal_formee(regle, attendu):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PANIER.format(regles=regle))
    assert attendu in str(refus.value)


def test_une_somme_masquee_est_refusee():
    """Même raison que pour `payable` et `derivedFrom` : un total qu'on ne peut
    pas lire ne peut pas être vérifié par celui qui le règle."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PANIER.format(
            regles=SOMME + "\nrule Commande.total hidden"))
    assert "hidden" in str(refus.value) and "sumOf" in str(refus.value)


def test_deux_calculs_concurrents_sur_le_meme_champ_sont_refuses():
    """`derivedFrom` lit UNE ligne liée, `sumOf` additionne des enfants. Les
    deux sur le même champ, c'est deux écritures qui se contredisent.

    Spec dédiée : pour ATTEINDRE ce recoupement, la règle `derivedFrom` doit
    elle-même être valide (entité source liée, multiplicateur Integer `required`
    sur l'entité calculée). Mon premier essai la posait sur la spec commune, où
    `Commande` n'a pas de multiplicateur : c'est le contrôle du facteur qui
    répondait, et le test ne prouvait rien du recoupement."""
    spec = """app P

entity Article
    prix: Money

entity Commande
    total: Money
    quantite: Integer

entity Ligne
    quantite: Integer
    sousTotal: Money

relation Client hasMany Commande
relation Article hasMany Commande
relation Commande hasMany Ligne
relation Article hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Commande.quantite required
rule Ligne.Read ownedBy Commande
rule Ligne.quantite required
rule Ligne.sousTotal derivedFrom Article.prix by quantite
rule Commande.total derivedFrom Article.prix by quantite
rule Commande.total sumOf Ligne.sousTotal

workflow W for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    message = str(refus.value)
    assert "'derivedFrom' et 'sumOf'" in message
    assert "choisir lequel" in message


def test_deux_sommes_sur_le_meme_champ_sont_refusees():
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PANIER.format(regles=SOMME + "\n" + SOMME))
    assert "une seule somme" in str(refus.value)


def test_sommer_une_entite_sans_proprietaire_est_refuse():
    """Sans propriétaire déclaré sur la ligne, la colonne qui la relie à sa
    commande peut recevoir un id de COMPTE (voir _identity_fk_columns) et la
    somme se recalculerait sur le mauvais parent. Et une ligne sans
    propriétaire serait créable par n'importe qui : le total d'un tiers
    deviendrait déplaçable à volonté.

    La somme porte ici sur `Ligne.quantite`, un champ ORDINAIRE, et la spec perd
    aussi sa règle `derivedFrom` : sur `Ligne.sousTotal`, c'est l'exigence de
    propriétaire de `derivedFrom` (point 78) qui répondait d'abord, et le test
    validait la garde d'une autre brique."""
    spec = (SPEC_PANIER
            .replace("rule Ligne.Read ownedBy Commande\n", "")
            .replace("rule Ligne.sousTotal derivedFrom Article.prix by quantite\n", ""))
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.format(regles="rule Commande.total sumOf Ligne.quantite"))
    message = str(refus.value)
    assert "n'a pas de propriétaire" in message
    assert "ownedBy" in message


def test_encaisser_une_somme_de_montants_ecrits_par_le_client_est_refuse():
    """LE refus de la brique — la faille du point 77 fermée avant qu'elle ne
    revienne par le panier.

    Un champ `sumOf` est calculé par le serveur, donc il satisfait le refus du
    point 79. Mais additionner des lignes dont le montant vient du client ne
    produit pas un total sûr : il produit un total que le client contrôle, en
    une addition de plus. Le payeur reprend la main sur ce qu'il règle.

    Le refus vit dans le recoupement avec `payable`, et non dans la boucle
    `sumOf`, parce que sommer un champ client reste légitime hors paiement :
    `Commande.nbArticles sumOf Ligne.quantite` compte des articles, il n'encaisse
    rien. C'est le CUMUL qui est fautif, pas la somme."""
    spec = SPEC_PANIER.replace(
        "rule Ligne.sousTotal derivedFrom Article.prix by quantite\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.format(regles=SOMME + "\nrule Commande.total payable"))
    message = str(refus.value)
    assert "que le client peut écrire" in message
    # Le message doit nommer la ligne fautive et proposer le correctif.
    assert "Ligne.sousTotal" in message
    assert "derivedFrom" in message


def test_sommer_un_champ_client_reste_permis_hors_paiement():
    """Le témoin du refus ci-dessus : c'est le cumul avec `payable` qui est
    interdit, pas la somme d'un champ fourni par le client. Compter les articles
    d'un panier est légitime et n'encaisse rien."""
    spec = SPEC_PANIER.replace("entity Commande\n    total: Money",
                               "entity Commande\n    total: Money\n    nbArticles: Integer")
    assert _valide(spec.format(
        regles="rule Commande.nbArticles sumOf Ligne.quantite"))
