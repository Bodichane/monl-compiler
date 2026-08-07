"""Le type `UUID` vérifie enfin sa forme — point 101.

Le point 91 avait posé le raisonnement pour `Email` : « un type qui nomme une
adresse et n'en vérifie aucune est exactement ce que le point 85 refuse, une
règle qui ne produit rien ». Son type FRÈRE est resté debout dix points de plus.

`UUID` ne fixait qu'une longueur de 255. `exemples/02_boutique.ml` déclare
`Order.reference: UUID`, et le serveur acceptait `CMD-1`, `smoke-reference`, ou
la chaîne vide, sous un nom qui promet un identifiant universellement unique —
deux commandes pouvaient donc porter la même « référence ».

Ce que le point décide :

* **la forme canonique, et rien de plus.** Ni chiffre de version, ni variante :
  les exiger rejetterait l'UUID nul et les versions à venir, alors qu'ils sont
  bien formés. monl vérifie la FORME, il ne juge pas la provenance ;
* **la contre-épreuve compte autant que le refus.** Un motif trop strict ferait
  passer les tests de rejet en cassant les vrais identifiants — c'est la leçon
  du point 91, reprise ici telle quelle ;
* **le vérificateur est un client comme un autre, TROISIÈME fois.** Le smoke
  test envoyait `smoke-reference` et aurait déclaré cassée une boutique saine,
  après `'smoke'` (point 95) et `'smoke-status'` (point 96).

Ce point ne convertit AUCUNE donnée existante : une base qui contient déjà des
références mal formées continue de les rendre. La règle ne vaut que pour les
écritures à venir, comme au point 95.
"""
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.cli import compile_project
from monl.smoke_test import _sample_value, run_smoke_test

SPEC = """app BancUUID

entity Commande
    reference: UUID
    libelle: String

actor Client selfRegister

rule Commande.Read ownedBy Client

relation Client hasMany Commande

workflow Acheter for Client
    Create Commande
    Read Commande
"""

MAL_FORMES = [
    "smoke-reference",                        # ce que le smoke test envoyait
    "CMD-1",                                  # une référence « métier »
    "3f2504e0-4f89-41d3-9a0c",                # tronqué
    "3f2504e04f8941d39a0c0305e82c3301",       # sans tirets
    "3f2504e0-4f89-41d3-9a0c-0305e82c330g",   # 'g' n'est pas hexadécimal
    "3f2504e0-4f89-41d3-9a0c-0305e82c33011",  # un caractère de trop
    "",
]

BIEN_FORMES = [
    "3f2504e0-4f89-41d3-9a0c-0305e82c3301",
    # L'UUID nul est bien FORMÉ : le refuser demanderait de juger la valeur, pas
    # sa forme — et monl ne fait que la forme.
    "00000000-0000-0000-0000-000000000000",
    # Majuscules : la casse hexadécimale est libre dans la forme canonique.
    "3F2504E0-4F89-41D3-9A0C-0305E82C3302",
]


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def test_le_motif_est_ecrit_pour_un_champ_uuid(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.strip().startswith("reference:"))
    assert "pattern=" in ligne
    assert "max_length=36" in ligne


def test_un_champ_texte_ordinaire_ne_gagne_aucun_motif(tmp_path, capsys):
    """Le témoin : sans lui, un motif posé sur tous les champs texte passerait
    le test précédent."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.strip().startswith("libelle:"))
    assert "pattern=" not in ligne


def test_la_sortie_differe_dun_champ_string(tmp_path, capsys):
    """POINT 85 : une règle qui ne produit rien est un mensonge. Déclarer un
    champ `UUID` plutôt que `String` doit donc changer le code produit."""
    (tmp_path / "a.ml").write_text(SPEC, encoding="utf-8")
    (tmp_path / "b.ml").write_text(SPEC.replace("reference: UUID",
                                                "reference: String"),
                                   encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "avec"))
    compile_project(str(tmp_path / "b.ml"), str(tmp_path / "sans"))
    capsys.readouterr()
    assert ((tmp_path / "avec" / "app.py").read_text(encoding="utf-8")
            != (tmp_path / "sans" / "app.py").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Le vérificateur, qui est un client comme un autre
# --------------------------------------------------------------------------

def test_la_valeur_du_smoke_test_est_un_uuid_valide():
    """TROISIÈME occurrence de la leçon des points 95 et 96, prise d'avance
    cette fois plutôt qu'après un faux diagnostic."""
    import re
    valeur = _sample_value("UUID", "reference")
    assert re.fullmatch(
        r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
        r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", valeur)


def test_le_smoke_test_passe_sur_une_spec_a_uuid(tmp_path, capsys):
    """La preuve de bout en bout : le vérificateur doit rendre VERT une
    application saine qui déclare un champ `UUID`."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    ok, erreurs, _avertissements = run_smoke_test(str(tmp_path), say=lambda *a, **k: None)
    capsys.readouterr()
    assert ok, erreurs
    assert erreurs == []


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _appel(url, corps=None, jeton=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {}


@pytest.fixture(scope="module")
def application(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("uuid")
    (dossier / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
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
        yield base, jeton["access_token"]
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()


@pytest.mark.parametrize("valeur", MAL_FORMES)
def test_une_reference_mal_formee_est_refusee(application, valeur):
    base, jeton = application
    code, _ = _appel(base + "/commande",
                     {"reference": valeur, "libelle": "essai"}, jeton)
    assert code == 422


@pytest.mark.parametrize("valeur", BIEN_FORMES)
def test_une_reference_bien_formee_reste_acceptee(application, valeur):
    """La contre-épreuve du refus : un motif trop strict ferait passer le test
    précédent en rejetant aussi les vrais identifiants."""
    base, jeton = application
    code, _ = _appel(base + "/commande",
                     {"reference": valeur, "libelle": "essai"}, jeton)
    assert code == 200
