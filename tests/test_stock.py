"""Brique 14 : décompter ce que le client a demandé — point 86.

Pourquoi cette brique. `decrements` savait retirer une CONSTANTE (`by 3`), ce qui
convient à une réputation ou à un like. Une boutique a besoin de retirer *ce que
le client a commandé*, et `exemples/02_boutique.ml` encaissait pour de vrai
depuis le point 74 sans jamais toucher à son stock : on pouvait commander cinquante
paires sur douze, et payer.

Ce que la brique décide, et qui n'allait pas de soi :

* **le plancher n'est pas câblé.** Un décompte qui passe sous zéro est un stock
  qui MENT — la boutique afficherait « -3 disponibles » après avoir encaissé les
  huit qu'elle n'avait pas. Mais une réputation, elle, a le droit d'être
  négative. Ce qui distingue les deux n'est pas le nom du champ : c'est la
  DÉCLARATION `rule Product.stock min 0`, arrivée au point 85. La vérification
  s'arme donc toute seule, à partir de ce que la spec dit — et reste absente là
  où rien ne la demande ;
* **une seule instruction SQL.** Lire le stock puis l'écrire laisserait deux
  commandes simultanées lire le même chiffre et décompter chacune de son côté.
  La condition voyage DANS le `UPDATE`, et c'est `rowcount` qui dit si elle a
  tenu ;
* **la colonne visée est celle qui pointe vers l'entité décrémentée.** Tant
  qu'une entité déclenchante n'avait qu'une relation entrante, « la relation
  propriétaire » et « la cible du décompte » coïncidaient. `OrderLine` en a deux
  — le bug est décrit plus bas, il a été trouvé en lisant le SQL généré.
"""
import json
import socket
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string

SPEC = """app BancStock

entity Produit
    nom: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Client
    nom: String

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Produit.nom required
rule Produit.stock min 0
rule Ligne.quantite required
rule Ligne.quantite min 1
rule Produit.Read public
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Produit.stock by quantite

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    # POINT 91 : `Update Ligne` est ici pour éprouver le décompte au PUT. Sans
    # cette action, la brique n'avait aucune façon d'être prise en défaut — et
    # elle l'était : la quantité changeait, le stock non.
    Update Ligne
    # POINT 92 : `Delete Ligne` éprouve la RESTITUTION. Sans cette action, la
    # brique n'avait toujours aucune façon d'être prise en défaut — et elle
    # l'était : vider son panier faisait disparaître le stock pour de bon.
    Delete Ligne
    Create Client
    Read Client
    Read Produit

workflow Gerer for Patron
    Create Produit
    Read Produit
    Update Produit

seed Produit
    nom: "Halo RS", stock: 3
    nom: "Deck Low", stock: 0
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation doit refuser
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    """Le témoin des refus qui suivent."""
    ast = _valide(SPEC)
    regle = next(r for r in ast["security"]["reputation_rules"]
                 if r["target_field"] == "stock")
    assert regle["amount_field"] == "quantite"
    assert regle["amount"] is None
    capsys.readouterr()


def test_une_quantite_qui_nest_pas_un_champ_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("by quantite", "by fantome"))
    assert "champ inexistant" in str(refus.value)
    capsys.readouterr()


def test_une_quantite_non_entiere_est_refusee(capsys):
    spec = SPEC.replace("    quantite: Integer", "    quantite: Integer\n    note: String")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace("by quantite", "by note"))
    assert "Integer" in str(refus.value)
    capsys.readouterr()


def test_une_quantite_facultative_est_refusee(capsys):
    """Même exigence que le multiplicateur de `derivedFrom` (point 77), et pour
    la même raison : un champ que le client peut omettre ferait décompter sur
    du vide."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Ligne.quantite required\n", ""))
    assert "required" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def test_le_decompte_vise_la_bonne_cle_etrangere(tmp_path, capsys):
    """LE bug trouvé en lisant le SQL généré, pas en relisant le code.

    La quantité était retranchée `WHERE id = data.commande_id` : le stock du
    produit portant l'id de la COMMANDE. Invisible tant qu'une entité
    déclenchante n'avait qu'UNE relation entrante (Report -> Member,
    Like -> Post) ; `Ligne` en a deux. Le compilateur a déjà connu ce défaut
    (« un mécanisme de clé étrangère qui décrémentait le mauvais
    enregistrement ») : il est revenu par la porte de la deuxième relation."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if '"stock" - ?' in li)
    assert "data.produit_id" in ligne
    assert "data.commande_id" not in ligne


def test_sans_plancher_declare_le_decompte_reste_libre(tmp_path, capsys):
    """Une réputation a le droit de passer sous zéro. La vérification vient de
    `min`, pas d'une exception « stock » câblée dans le compilateur : retirer la
    déclaration doit retirer le garde-fou."""
    (tmp_path / "spec.ml").write_text(SPEC.replace("rule Produit.stock min 0\n", ""),
                                      encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "rowcount == 0" not in genere
    assert "insuffisant" not in genere


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _appel(url, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        brut = err.read()
        try:
            return err.code, json.loads(brut or b"{}")
        except ValueError:
            return err.code, {"brut": brut[:300].decode("utf-8", "replace")}


@pytest.fixture
def boutique(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if processus.poll() is not None:
                pytest.fail(processus.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                urllib.request.urlopen(base + "/docs", timeout=5).read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        jeton = jeton["access_token"]
        _appel(base + "/client", {"nom": "Zoe"}, jeton)
        # Trois commandes pour que l'id retenu DIVERGE de ceux des produits :
        # avec « commande 1 » et « produit 1 », une confusion de clé étrangère
        # passerait inaperçue — c'est la leçon de la sonde du point 81.
        for _ in range(3):
            _, commande = _appel(base + "/commande", {"statut": "panier"}, jeton)
        _, catalogue = _appel(base + "/produit?limit=20")
        produits = {p["nom"]: p for p in catalogue["data"]}
        yield base, jeton, commande["id"], produits, tmp_path
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()


def _stock(base, produit_id):
    _, reponse = _appel(f"{base}/produit/{produit_id}")
    return reponse["data"]["stock"]


def test_une_commande_decompte_le_stock(boutique):
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    assert _stock(base, halo) == 3

    code, _ = _appel(base + "/ligne", {"quantite": 2, "commande_id": commande,
                                       "produit_id": halo}, jeton)
    assert code == 200
    assert _stock(base, halo) == 1, "le décompte doit valoir la QUANTITÉ, pas 1"


def test_commander_plus_que_le_stock_est_refuse(boutique):
    """Le trou que la brique ferme : avant elle, la boutique encaissait cinquante
    paires sur douze."""
    base, jeton, commande, produits, dossier = boutique
    halo = produits["Halo RS"]["id"]

    code, reponse = _appel(base + "/ligne", {"quantite": 4, "commande_id": commande,
                                             "produit_id": halo}, jeton)
    assert code == 409
    assert "insuffisant" in reponse["detail"]
    assert _stock(base, halo) == 3, "un refus ne doit rien avoir décompté"
    # Et la ligne ne doit pas exister : le refus arrive DANS la transaction.
    with sqlite3.connect(dossier / "app.db") as base_donnees:
        assert base_donnees.execute("SELECT COUNT(*) FROM ligne").fetchone()[0] == 0


def test_un_produit_epuise_refuse_toute_ligne(boutique):
    base, jeton, commande, produits, _ = boutique
    deck = produits["Deck Low"]["id"]
    assert _stock(base, deck) == 0
    code, _ = _appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                                       "produit_id": deck}, jeton)
    assert code == 409


def test_le_stock_ne_passe_jamais_sous_zero_meme_en_plusieurs_fois(boutique):
    """Trois commandes de 1 sur un stock de 3 : les trois passent. La quatrième
    non. C'est le cumul qui compte, pas chaque requête prise seule."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    codes = [_appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                                      "produit_id": halo}, jeton)[0]
             for _ in range(4)]
    assert codes == [200, 200, 200, 409]
    assert _stock(base, halo) == 0


def test_le_decompte_vise_le_produit_demande_et_pas_un_autre(boutique):
    """La contre-épreuve du bug de clé étrangère : avec des identifiants
    volontairement DIVERGENTS, décompter la mauvaise ligne se verrait."""
    base, jeton, commande, produits, _ = boutique
    halo, deck = produits["Halo RS"]["id"], produits["Deck Low"]["id"]
    assert halo != commande, "identifiants confondus : le test ne prouve rien"

    _appel(base + "/ligne", {"quantite": 1, "commande_id": commande,
                             "produit_id": halo}, jeton)
    assert _stock(base, halo) == 2
    assert _stock(base, deck) == 0, "aucun autre produit ne doit avoir bougé"


# ---------------------------------------------------------------------------
# POINT 91 : le décompte au PUT. `decrements` ne s'armait qu'à la CRÉATION —
# créer une ligne à 1 puis la passer à 4 facturait quatre paires et n'en
# décomptait qu'une. C'est le défaut du point 78 déplacé de l'argent vers la
# marchandise, et il vivait dans la brique depuis le point 86.

def _ligne_de(base, jeton, commande, produit, quantite):
    code, reponse = _appel(base + "/ligne", {"quantite": quantite,
                                             "commande_id": commande,
                                             "produit_id": produit}, jeton)
    assert code == 200, reponse
    return reponse["id"]


def test_augmenter_la_quantite_decompte_la_difference(boutique):
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _ligne_de(base, jeton, commande, halo, 1)
    assert _stock(base, halo) == 2

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 3, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 200, reponse
    # 3 au départ, 3 commandées : le DELTA de 2 s'ajoute au 1 déjà décompté.
    assert _stock(base, halo) == 0, "le PUT doit décompter la différence"


def test_reduire_la_quantite_rend_du_stock(boutique):
    """Le delta joue dans les deux sens, sans code séparé : `stock - (-2)`
    repasse au-dessus du plancher, donc la même instruction suffit."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _ligne_de(base, jeton, commande, halo, 3)
    assert _stock(base, halo) == 0

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 1, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 200, reponse
    assert _stock(base, halo) == 2


def test_une_quantite_qui_depasse_le_stock_est_refusee_au_put(boutique):
    """Le trou tel qu'il a été mesuré sur une boutique réelle : quatre paires
    facturées, une seule décomptée."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    ligne = _ligne_de(base, jeton, commande, halo, 1)

    code, reponse = _appel(f"{base}/ligne/{ligne}",
                           {"quantite": 9, "commande_id": commande,
                            "produit_id": halo}, jeton, methode="PUT")

    assert code == 409, reponse
    assert "insuffisant" in reponse["detail"]
    assert _stock(base, halo) == 2, "un refus ne doit rien avoir décompté"
    _, relue = _appel(f"{base}/ligne/{ligne}", jeton=jeton)
    assert relue["data"]["quantite"] == 1, (
        "la ligne ne doit pas être écrite quand le stock refuse")


# --------------------------------------------------------------------------
# POINT 92 : la restitution — le troisième branchement, celui qu'on oublie
# --------------------------------------------------------------------------

def test_supprimer_une_ligne_rend_le_stock(boutique):
    """LE défaut, mesuré sur `projets/SneakerLab` contre un vrai serveur :
    commander trois paires puis vider son panier laissait le stock à 9 sur 12.

    Le décompte s'armait à la création (point 86) puis à la modification
    (point 91), jamais à la suppression. Le total du parent, lui, redescendait
    bien à zéro depuis le point 82 — donc une base qui se contredisait
    elle-même, et un catalogue qui s'épuise sans qu'une paire soit vendue."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    ligne = _ligne_de(base, jeton, commande, halo, 2)
    assert _stock(base, halo) == depart - 2

    code, reponse = _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert code == 200, reponse
    assert _stock(base, halo) == depart, "la ligne supprimée n'a pas rendu son stock"


def test_la_restitution_rend_la_quantite_COURANTE_pas_celle_de_la_creation(boutique):
    """Créée à 1 puis passée à 3, la ligne a consommé 3 : c'est 3 qu'elle doit
    rendre. La quantité est relue EN BASE au moment de la suppression — la lire
    ailleurs rendrait la valeur d'origine et laisserait deux paires évaporées."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    ligne = _ligne_de(base, jeton, commande, halo, 1)
    _appel(f"{base}/ligne/{ligne}", {"quantite": 3, "commande_id": commande,
                                     "produit_id": halo}, jeton, methode="PUT")
    assert _stock(base, halo) == depart - 3

    _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert _stock(base, halo) == depart


def test_la_restitution_vise_le_produit_de_la_ligne_et_pas_un_autre(boutique):
    """Même piège qu'au point 86, sur l'autre branchement : `Ligne` a DEUX
    relations entrantes, et rendre le stock au produit portant l'id de la
    COMMANDE serait invisible tant que les deux id coïncident. Le banc fait
    diverger les identifiants exprès."""
    base, jeton, commande, produits, _ = boutique
    halo, deck = produits["Halo RS"]["id"], produits["Deck Low"]["id"]
    depart_halo, depart_deck = _stock(base, halo), _stock(base, deck)
    ligne = _ligne_de(base, jeton, commande, halo, 2)

    _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")

    assert _stock(base, halo) == depart_halo
    assert _stock(base, deck) == depart_deck, "le stock d'un autre produit a bougé"


def test_vider_puis_recommander_ne_perd_aucune_unite(boutique):
    """La contre-épreuve du cycle complet : trois allers-retours ne doivent pas
    grignoter le catalogue. C'est la forme sous laquelle le défaut se voyait en
    production — un stock qui ne descend que dans un sens."""
    base, jeton, commande, produits, _ = boutique
    halo = produits["Halo RS"]["id"]
    depart = _stock(base, halo)
    for _ in range(3):
        ligne = _ligne_de(base, jeton, commande, halo, 3)
        _appel(f"{base}/ligne/{ligne}", jeton=jeton, methode="DELETE")
    assert _stock(base, halo) == depart


def test_la_restitution_ne_porte_pas_de_plancher(tmp_path, capsys):
    """Décision assumée : rendre ne se refuse pas. La restitution rétablit un
    état qui a existé et qui était valide — un `decrements` rendu ne fait que
    remonter. Un garde-fou ici interdirait d'annuler une commande, c'est-à-dire
    exactement ce que la brique répare."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    bloc = genere.split("def delete_ligne(")[1].split("\n@app.")[0]
    rendu = next(li for li in bloc.splitlines() if '"stock" + ?' in li)
    assert ">= ?" not in rendu, "la restitution ne doit porter aucune condition"
    # Et elle rend au produit de la ligne : la colonne est nommée dans la
    # lecture qui précède, la restitution en réutilise la valeur.
    assert 'SELECT "quantite", "produit_id"' in bloc


def test_la_restitution_lit_la_ligne_avant_de_la_supprimer(tmp_path, capsys):
    """Après le DELETE, la ligne n'existe plus et sa clé étrangère avec elle :
    plus rien ne dit quoi rendre ni à qui. Même leçon qu'au point 82 pour
    l'agrégation — l'ordre des deux instructions EST la brique."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    bloc = ((tmp_path / "app.py").read_text(encoding="utf-8")
            .split("def delete_ligne(")[1].split("\n@app.")[0])
    lecture = bloc.index('SELECT "quantite", "produit_id"')
    suppression = bloc.index('DELETE FROM "ligne"')
    assert lecture < suppression, "la quantité est lue après la suppression"


# --------------------------------------------------------------------------
# POINT 92 : la variable qui fuyait d'une branche à l'autre
# --------------------------------------------------------------------------

SPEC_SANS_CREATE = """app SansCreate

entity Fiche
    titre: String

relation Client hasMany Fiche

actor Client selfRegister

rule Fiche.Read ownedBy Client
rule Fiche.Update ownedBy Client

workflow Consulter for Client
    Read Fiche
    Update Fiche
"""


def test_un_update_sans_aucun_create_compile(tmp_path, capsys):
    """RÉGRESSION (point 91 → 92) : le décompte au PUT lisait
    `reputation_rules_here`, variable assignée dans la branche `Create`. Une
    spec qui n'a aucun `Create` faisait donc PLANTER le compilateur —
    « cannot access local variable ». Aucun exemple ni test n'exerçait ce
    chemin : toutes les specs du dépôt créent quelque chose."""
    (tmp_path / "spec.ml").write_text(SPEC_SANS_CREATE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    assert "def update_fiche(" in (tmp_path / "app.py").read_text(encoding="utf-8")


SPEC_FUITE = """app Fuite

entity Produit
    nom: String
    stock: Integer

entity Ligne
    quantite: Integer

entity Avis
    quantite: Integer
    texte: String

relation Client hasMany Ligne
relation Produit hasMany Ligne
relation Client hasMany Avis
relation Produit hasMany Avis

actor Client selfRegister

rule Produit.Read public
rule Produit.stock min 0
rule Ligne.quantite required
rule Avis.quantite required
rule Ligne.Create decrements Produit.stock by quantite

workflow Acheter for Client
    Read Produit
    Create Ligne
    Read Ligne
    Read Avis
    Update Avis
"""


def test_les_regles_de_decompte_ne_fuient_pas_dune_entite_a_lautre(tmp_path, capsys):
    """L'autre face de la même régression, et la plus sournoise : la branche
    `Update` héritait des règles de la DERNIÈRE entité créée. `Avis` ne porte
    aucun `decrements` — modifier un avis décomptait pourtant le stock d'un
    produit (vérifié dans le SQL généré avant correction).

    La coïncidence qui masquait le défaut : quand `Create X` précède
    immédiatement `Update X`, la variable contient les bonnes règles. Il suffit
    qu'une autre entité s'intercale pour que ce ne soit plus vrai."""
    (tmp_path / "spec.ml").write_text(SPEC_FUITE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    bloc = ((tmp_path / "app.py").read_text(encoding="utf-8")
            .split("def update_avis(")[1].split("\n@app.")[0])
    assert '"stock"' not in bloc, "l'Update d'Avis touche au stock d'un Produit"
    assert "_delta" not in bloc
