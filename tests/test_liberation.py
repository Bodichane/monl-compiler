"""Brique 20 : atteindre une valeur DÉFAIT un effet — point 98.

Le dernier bug vivant qu'avait laissé la comparaison à une boutique classique
(point 96) : annuler une commande la passait en « annulée » et gardait ses
lignes, donc le stock restait consommé. Supprimer les lignes le rendait
(point 92) mais effaçait l'historique — un marchand veut les deux.

`oneOf` (point 96) était le préalable : il fallait pouvoir désigner un état.

Ce que la brique décide :

* **ne rendre QU'UNE FOIS.** L'état est lu avant l'écriture et la libération
  n'a lieu qu'à la TRANSITION. Deux PUT successifs à « annulée » rendraient
  sinon le stock deux fois, et la boutique s'inventerait des paires ;
* **l'état libéré est TERMINAL.** Réactiver après avoir rendu laisserait une
  commande vivante sans rien avoir consommé — du stock gratuit, même famille
  que les exploits du point 77. Le reprendre au retour supposerait qu'il soit
  encore disponible, ce que rien ne garantit ;
* **aucun plancher sur la restitution**, comme au point 92 : on rend un état
  qui a existé et qui était valide.
"""
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

SPEC = """app BancLiberation

entity Produit
    nom: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Produit.stock min 0
rule Ligne.quantite required
rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Produit.stock by quantite
rule Commande.statut oneOf "panier", "en préparation", "annulée"
rule Commande.statut "annulée" releases Ligne

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Ligne
    Read Ligne
    Read Produit

seed Produit
    nom: "Halo RS", stock: 10
"""

SANS_REGLE = SPEC.replace('rule Commande.statut "annulée" releases Ligne\n', "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation refuse
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    ast = _valide(SPEC)
    assert ast["security"]["release_rules"] == [
        {"entity": "Commande", "field": "statut", "value": "annulée",
         "releases": "Ligne"}]
    capsys.readouterr()


def test_sans_oneOf_la_regle_est_refusee(capsys):
    """LE refus qui porte la brique : sans liste de valeurs, une faute de frappe
    donnerait une règle qui ne se déclenche JAMAIS — et rien ne le dirait. C'est
    exactement ce que le point 85 refuse."""
    spec = SPEC.replace(
        'rule Commande.statut oneOf "panier", "en préparation", "annulée"\n', "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "oneOf" in str(refus.value)
    capsys.readouterr()


def test_une_valeur_hors_de_la_liste_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"annulée" releases', '"remboursée" releases'))
    assert "jamais" in str(refus.value)
    capsys.readouterr()


def test_liberer_une_entite_sans_decompte_est_refuse(capsys):
    """« Rendre » suppose que quelque chose ait été pris."""
    spec = SPEC.replace("rule Ligne.Create decrements Produit.stock by quantite\n", "")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "decrements" in str(refus.value)
    capsys.readouterr()


def test_liberer_sans_relation_est_refuse(capsys):
    """Sans relation, rien ne dit QUELLES lignes dépendent de cette commande."""
    spec = SPEC.replace("relation Commande hasMany Ligne\n",
                        "relation Client hasMany Ligne\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "relation" in str(refus.value)
    capsys.readouterr()


def test_une_entite_inconnue_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("releases Ligne", "releases Fantome"))
    assert "Fantome" in str(refus.value)
    capsys.readouterr()


def test_deux_regles_sur_le_meme_champ_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + 'rule Commande.statut "panier" releases Ligne\n')
    assert "deuxième fois" in str(refus.value)
    capsys.readouterr()


def test_la_regle_change_vraiment_la_sortie(tmp_path, capsys):
    """Le test qui interdit une règle décorative (point 85)."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    avec = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert avec != sans
    assert "_bascule" in avec and "_bascule" not in sans


def test_le_contrat_annonce_la_liberation_et_laller_sans_retour(tmp_path, capsys):
    """Sans cette note, une interface propose « repasser en préparation » sur
    une commande annulée et découvre un 409 au clic."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    route = next(r for r in contrat["routes"]
                 if r["method"] == "PUT" and r["path"] == "/commande/{id}")
    assert route["releases_on"] == {"field": "statut", "value": "annulée",
                                    "releases": "Ligne", "terminal": True}
    assert "LIBÉRATION" in route["note"]
    assert "SANS retour" in route["note"]


def test_le_delta_signale_une_liberation_ajoutee(tmp_path, capsys):
    """POINT 98 : septième fois. Poser `releases` ne crée aucune route et ne
    change aucun champ — mais un bouton « réactiver » devient un 409."""
    from monl.cli import cmd_update

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "spec.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    capsys.readouterr()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")

    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "aucun changement d'interface" not in sortie, sortie
    assert "libération de PUT /commande/{id}" in sortie, sortie
    assert "route ajoutée" not in sortie, sortie


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

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
            return err.code, {"detail": brut.decode("utf-8", "replace")}


@pytest.fixture
def boutique(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
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
        yield base, jeton["access_token"]
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def _stock(base):
    _, r = _appel(f"{base}/produit/1")
    return r["data"]["stock"]


def _commande_de(base, jeton, quantite):
    _, cmd = _appel(base + "/commande", {"statut": "panier"}, jeton)
    _appel(base + "/ligne", {"quantite": quantite, "commande_id": cmd["id"],
                             "produit_id": 1}, jeton)
    return cmd["id"]


def test_annuler_rend_le_stock(boutique):
    """LE défaut, mesuré en comparant la boutique à une vraie : annuler gardait
    les lignes, donc le stock restait consommé."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    assert _stock(base) == depart - 3

    code, reponse = _appel(f"{base}/commande/{cmd}", {"statut": "annulée"},
                           jeton, methode="PUT")

    assert code == 200, reponse
    assert _stock(base) == depart


def test_annuler_GARDE_les_lignes(boutique):
    """Toute la raison d'être de la brique : supprimer les lignes rendait déjà
    le stock (point 92), mais effaçait l'historique. Un marchand veut les deux."""
    base, jeton = boutique
    cmd = _commande_de(base, jeton, 2)
    _appel(f"{base}/commande/{cmd}", {"statut": "annulée"}, jeton, methode="PUT")

    _, lignes = _appel(f"{base}/ligne", jeton=jeton)
    assert lignes["total"] == 1


def test_re_annuler_ne_rend_PAS_une_seconde_fois(boutique):
    """LE point de la brique, et ce que seul un vrai serveur montre : sans la
    garde de transition, deux PUT rendraient le stock deux fois et la boutique
    s'inventerait des paires."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    for _ in range(3):
        code, _ = _appel(f"{base}/commande/{cmd}", {"statut": "annulée"},
                         jeton, methode="PUT")
        assert code == 200

    assert _stock(base) == depart, "le stock a été rendu plusieurs fois"


def test_reactiver_apres_annulation_est_refuse(boutique):
    """Sans ce refus : annuler rend le stock, réactiver laisse la commande
    vivante sans rien avoir consommé — du stock gratuit, même famille que les
    exploits du point 77."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 3)
    _appel(f"{base}/commande/{cmd}", {"statut": "annulée"}, jeton, methode="PUT")

    code, reponse = _appel(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                           jeton, methode="PUT")

    assert code == 409, reponse
    assert _stock(base) == depart, "un refus ne doit rien avoir consommé"
    _, relue = _appel(f"{base}/commande/{cmd}", jeton=jeton)
    assert relue["data"]["statut"] == "annulée", "l'état a changé malgré le refus"


def test_un_autre_statut_ne_libere_rien(boutique):
    """Le témoin : c'est la VALEUR déclarée qui libère, pas n'importe quelle
    modification. Sans lui, une brique qui rendrait à chaque PUT passerait les
    tests précédents."""
    base, jeton = boutique
    depart = _stock(base)
    cmd = _commande_de(base, jeton, 2)

    code, _ = _appel(f"{base}/commande/{cmd}", {"statut": "en préparation"},
                     jeton, methode="PUT")

    assert code == 200
    assert _stock(base) == depart - 2, "un statut ordinaire a rendu du stock"


def test_annuler_ne_rend_que_SES_lignes(boutique):
    """Deux commandes ouvertes : annuler l'une ne doit pas rendre ce que
    l'autre a consommé. Le piège de la clé étrangère, une fois de plus."""
    base, jeton = boutique
    depart = _stock(base)
    premiere = _commande_de(base, jeton, 3)
    _commande_de(base, jeton, 2)
    assert _stock(base) == depart - 5

    _appel(f"{base}/commande/{premiere}", {"statut": "annulée"}, jeton, methode="PUT")

    assert _stock(base) == depart - 2, "la libération a débordé sur l'autre commande"
