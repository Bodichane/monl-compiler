"""Brique 19 : une valeur parmi une liste — point 96.

Nommée « la prochaine brique évidente » aux points 91 et 92, et pour cause : sur
une commande NON réglée, le client posait `status: "livrée"` et le serveur
l'acceptait. Un statut n'est pas du texte, c'est un état parmi quelques-uns.

Ce que la brique décide :

* **`Literal` plutôt qu'un motif.** Le refus tombe à la validation Pydantic —
  un 422 AVANT tout INSERT, même place que les bornes du point 85 — et la liste
  sort telle quelle dans le schéma OpenAPI, donc dans `/docs`, sans qu'on ait à
  la recopier ;
* **types TEXTE seulement.** Pour un nombre, `min`/`max` (point 85) et
  `categorized` (brique 5) disent déjà cela ; une troisième façon d'exprimer la
  même contrainte finirait par en contredire une autre ;
* **le contrat porte la liste.** Sans elle l'IA dessine un champ texte, et
  l'utilisateur invente une valeur qui récolte un 422 — alors que la liste tient
  dans un menu déroulant.
"""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string

SPEC = """app BancChoix

entity Commande
    statut: String
    note: String

relation Client hasMany Commande

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Commande.statut oneOf "panier", "en préparation", "expédiée", "livrée"

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
"""

SANS_REGLE = SPEC.replace(
    'rule Commande.statut oneOf "panier", "en préparation", "expédiée", "livrée"\n', "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation refuse
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    ast = _valide(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"] == [
        "panier", "en préparation", "expédiée", "livrée"]
    capsys.readouterr()


def test_lordre_declare_est_conserve(capsys):
    """Sur un statut, l'ordre est celui du cycle de vie — il porte du sens, et
    c'est celui qu'un menu déroulant doit présenter."""
    ast = _valide(SPEC)
    assert ast["security"]["enumerated_fields"]["Commande"]["statut"][0] == "panier"
    capsys.readouterr()


def test_un_champ_inexistant_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("Commande.statut oneOf", "Commande.fantome oneOf"))
    assert "champ inexistant" in str(refus.value)
    capsys.readouterr()


def test_un_champ_numerique_est_refuse(capsys):
    """Trois façons d'exprimer la même contrainte finiraient par se
    contredire : pour un nombre, 'min'/'max' et 'categorized' existent déjà."""
    spec = SPEC.replace("    note: String", "    montant: Integer")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace("Commande.statut oneOf", "Commande.montant oneOf"))
    assert "String ou Text" in str(refus.value)
    capsys.readouterr()


def test_une_seule_valeur_est_refusee(capsys):
    """Un champ qui n'a qu'une valeur possible n'a pas besoin d'être saisi —
    et une règle qui ne produit rien est ce que le point 85 refuse."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace(
            'oneOf "panier", "en préparation", "expédiée", "livrée"', 'oneOf "panier"'))
    assert "une valeur" in str(refus.value)
    capsys.readouterr()


def test_une_valeur_vide_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"panier",', '"   ",'))
    assert "vide" in str(refus.value)
    capsys.readouterr()


def test_un_doublon_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"livrée"', '"panier"'))
    assert "répète" in str(refus.value)
    capsys.readouterr()


def test_deux_regles_sur_le_meme_champ_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + 'rule Commande.statut oneOf "a", "b"\n')
    assert "laquelle" in str(refus.value)
    capsys.readouterr()


def test_cumul_avec_generated_est_refuse(capsys):
    """Le serveur écrit le champ lui-même : la liste ne serait jamais lue, et
    l'écran proposerait un menu inerte."""
    spec = SPEC + "rule Commande.note generated\n"
    spec = spec.replace('rule Commande.statut oneOf "panier", "en préparation", '
                        '"expédiée", "livrée"',
                        'rule Commande.note oneOf "a", "b"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "generated" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération écrit
# --------------------------------------------------------------------------

def test_la_regle_change_vraiment_la_sortie(tmp_path, capsys):
    """Le test qui interdit une règle décorative (point 85) : compiler AVEC et
    SANS doit donner des sorties différentes."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SANS_REGLE, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "b"))
    capsys.readouterr()
    avec = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    sans = (tmp_path / "b" / "app.py").read_text(encoding="utf-8")
    assert avec != sans
    assert "Literal['panier'" in avec
    assert "Literal[" not in sans


def test_le_contrat_et_le_brief_portent_la_liste(tmp_path, capsys):
    """L'IA lit le brief, pas le JSON — les deux doivent la porter, sinon elle
    dessine un champ texte et l'utilisateur récolte un 422."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    champ = next(f for f in contrat["entities"]["Commande"]["fields"]
                 if f["name"] == "statut")
    assert champ["allowed_values"] == ["panier", "en préparation", "expédiée", "livrée"]
    brief = (tmp_path / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    assert "MENU DÉROULANT" in brief
    assert "« en préparation »" in brief


def test_sans_regle_aucune_liste_dans_le_contrat(tmp_path, capsys):
    """Le témoin : une règle absente ne doit laisser aucune trace."""
    (tmp_path / "spec.ml").write_text(SANS_REGLE, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    assert not any(f.get("allowed_values")
                   for f in contrat["entities"]["Commande"]["fields"])
    assert "MENU DÉROULANT" not in (
        tmp_path / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")


def test_le_delta_signale_une_liste_qui_change(tmp_path, capsys):
    """POINT 96 : sixième fois. Poser `oneOf` ne renomme rien, et la liste peut
    changer sans que le champ bouge — un champ texte devient un menu, et le menu
    gagne une entrée. Comparer les seuls noms serait l'erreur du point 89."""
    from monl.cli import cmd_update

    proj = tmp_path / "p"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    capsys.readouterr()
    (proj / "spec.ml").write_text(SPEC.replace('"livrée"', '"livrée", "annulée"'),
                                  encoding="utf-8")

    cmd_update(str(proj))
    sortie = capsys.readouterr().out

    assert "aucun changement d'interface" not in sortie, sortie
    assert "contenu réécrit : choix de Commande.statut" in sortie, sortie
    assert "champ ajouté" not in sortie, sortie


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
            return err.code, {"detail": brut.decode("utf-8", "replace")}


@pytest.fixture
def serveur(tmp_path):
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


@pytest.mark.parametrize("valide", ["panier", "en préparation", "expédiée", "livrée"])
def test_les_valeurs_declarees_sont_acceptees(serveur, valide):
    base, jeton = serveur
    code, reponse = _appel(base + "/commande", {"statut": valide, "note": "x"}, jeton)
    assert code == 200, reponse


@pytest.mark.parametrize("invalide", ["livrée par moi", "", "PANIER", "expediee"])
def test_toute_autre_valeur_est_refusee(serveur, invalide):
    """LE défaut mesuré sur la boutique réelle : le client se déclarait
    « livrée » tout seul, sur une commande non réglée."""
    base, jeton = serveur
    code, _ = _appel(base + "/commande", {"statut": invalide, "note": "x"}, jeton)
    assert code == 422


def test_le_refus_enumere_les_valeurs_permises(serveur):
    """Un 422 qui ne dit pas ce qu'il attend oblige à lire la documentation.
    La liste est dans le message, elle vient de `Literal`."""
    base, jeton = serveur
    _, reponse = _appel(base + "/commande", {"statut": "inventé", "note": "x"}, jeton)
    message = json.dumps(reponse, ensure_ascii=False)
    assert "panier" in message and "livrée" in message


def test_la_contrainte_tient_AUSSI_a_la_modification(serveur):
    """Le branchement qu'on oublie (points 91, 92) : le schéma Pydantic est
    unique par entité, donc le PUT est couvert — mais il faut le VÉRIFIER,
    pas le supposer."""
    base, jeton = serveur
    _, cree = _appel(base + "/commande", {"statut": "panier", "note": "x"}, jeton)

    code, _ = _appel(f"{base}/commande/{cree['id']}",
                     {"statut": "livrée par moi", "note": "x"}, jeton, methode="PUT")
    assert code == 422

    code, _ = _appel(f"{base}/commande/{cree['id']}",
                     {"statut": "expédiée", "note": "x"}, jeton, methode="PUT")
    assert code == 200
    _, relue = _appel(f"{base}/commande/{cree['id']}", jeton=jeton)
    assert relue["data"]["statut"] == "expédiée"


def test_un_refus_ne_laisse_rien_en_base(serveur):
    """422 avant tout INSERT : la garde vit dans la validation d'entrée, pas
    au milieu d'une écriture."""
    base, jeton = serveur
    _appel(base + "/commande", {"statut": "inventé", "note": "x"}, jeton)
    _, liste = _appel(base + "/commande", jeton=jeton)
    assert liste["total"] == 0
