"""Brique 22 : le numéro que l'humain lit et dicte — point 102.

Pourquoi la brique. `exemples/02_boutique.ml` déclarait `Order.reference: UUID`
— un champ que le CLIENT remplissait, et qui depuis le point 101 exige la forme
canonique d'un UUID. Or personne ne dicte `3f2504e0-4f89-41d3-9a0c-0305e82c3301`
au téléphone. Un carnet de commandes veut « CMD-2026-0001 », et ce numéro-là
n'est pas une donnée du client : c'est le vendeur qui l'attribue.

    rule Order.reference numbered "CMD-{YYYY}-{NNNN}"

Ce que la brique décide, et qui n'allait pas de soi :

* **le compteur vit dans une table SYSTÈME.** `MAX(...) + 1` sur la table métier
  redonnerait le numéro d'un enregistrement supprimé — deux factures avec la
  même référence — et se tromperait dès que deux créations se croisent.
  `test_le_numero_ne_recule_pas_apres_une_suppression` le prouve ;
* **l'attribution vit DANS la transaction de création.** Hors d'elle, une
  insertion refusée laisserait le compteur avancé ;
* **le mot-clé n'est pas `reference`.** Il se confondrait avec le nom du champ
  qu'on lui donne presque toujours : `rule Order.reference reference "…"` ne se
  lit pas ;
* **les enregistrements antérieurs restent SANS numéro.** Les numéroter au
  démarrage prétendrait un ordre d'arrivée que le serveur n'a pas observé — et
  sur un carnet de commandes, un numéro inventé finit sur une facture. C'est la
  leçon du point 89, mot pour mot.
"""
import json
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

SPEC = """app BancNumero

entity Commande
    reference: String
    libelle: String

actor Client selfRegister

relation Client hasMany Commande

rule Commande.Read ownedBy Client
rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Delete Commande
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation doit refuser
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    ast = _valide(SPEC)
    regle = ast["security"]["numbered_fields"][0]
    assert regle == {"entity": "Commande", "field": "reference",
                     "format": "CMD-{YYYY}-{NNNN}", "periode": "YYYY"}
    capsys.readouterr()


def test_un_champ_inexistant_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("Commande.reference numbered",
                             "Commande.fantome numbered"))
    assert "champ inexistant" in str(refus.value)
    capsys.readouterr()


def test_un_champ_non_texte_est_refuse(capsys):
    spec = SPEC.replace("    reference: String", "    reference: Integer")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "String" in str(refus.value)
    capsys.readouterr()


def test_un_champ_uuid_est_refuse_en_le_nommant(capsys):
    """POINT 101 : c'est le type qu'on est tenté de choisir pour une référence,
    et depuis ce point-là il vérifie sa forme — un numéro lisible n'y entrerait
    jamais. Le message doit le DIRE, sinon l'auteur essaie et ne comprend pas."""
    spec = SPEC.replace("    reference: String", "    reference: UUID")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "point 101" in str(refus.value)
    capsys.readouterr()


def test_un_champ_masque_est_refuse(capsys):
    spec = SPEC.replace("rule Commande.reference numbered",
                        "rule Commande.reference hidden\nrule Commande.reference numbered")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "hidden" in str(refus.value)
    capsys.readouterr()


def test_deux_regles_sur_le_meme_champ_sont_refusees(capsys):
    spec = SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"',
                        'rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n'
                        'rule Commande.reference numbered "AUTRE-{NNNN}"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "une seule autorisée" in str(refus.value)
    capsys.readouterr()


def test_un_gabarit_sans_sequence_est_refuse(capsys):
    """LE refus qui porte la brique : sans séquence, tous les enregistrements
    porteraient le même numéro — ce qui n'en est pas un (point 85)."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{YYYY}"'))
    assert "aucune séquence" in str(refus.value)
    capsys.readouterr()


def test_deux_sequences_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{NN}-{NNNN}"'))
    assert "laquelle s'incrémente" in str(refus.value)
    capsys.readouterr()


def test_un_jalon_inconnu_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{MOIS}-{NNNN}"'))
    assert "ne veut rien dire" in str(refus.value)
    capsys.readouterr()


def test_une_accolade_orpheline_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{YYYY-{NNNN}"'))
    assert "accolade orpheline" in str(refus.value)
    capsys.readouterr()


def test_un_mois_sans_annee_est_refuse(capsys):
    """'CMD-{MM}-{NNNN}' redonne 'CMD-03-0001' tous les mois de mars. L'index
    unique l'attraperait — un an plus tard, et en production."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('"CMD-{YYYY}-{NNNN}"', '"CMD-{MM}-{NNNN}"'))
    assert "sans '{YYYY}'" in str(refus.value)
    capsys.readouterr()


def test_une_borne_sur_un_champ_numerote_est_refusee(capsys):
    """Héritée du recoupement du point 85 sans une ligne de plus : le champ
    n'est pas dans le schéma d'entrée, une borne n'aurait nulle part où vivre."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.reference max 10\n")
    assert "reference" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def _compile(tmp_path, spec=SPEC, nom="p"):
    (tmp_path / f"{nom}.ml").write_text(spec, encoding="utf-8")
    contrat = compile_project(str(tmp_path / f"{nom}.ml"), str(tmp_path / nom))
    return contrat, (tmp_path / nom / "app.py").read_text(encoding="utf-8")


def test_le_champ_disparait_du_schema_dentree(tmp_path, capsys):
    _, genere = _compile(tmp_path)
    capsys.readouterr()
    debut = genere.index("class CommandeSchema")
    assert "reference" not in genere[debut:debut + 300]


def test_le_champ_disparait_du_set_de_modification(tmp_path, capsys):
    """Un numéro de commande qui change n'est plus une référence : le client
    l'a noté, le vendeur aussi."""
    _, genere = _compile(tmp_path)
    capsys.readouterr()
    ligne = next(li for li in genere.splitlines() if 'UPDATE "commande" SET' in li)
    assert '"reference"' not in ligne
    assert '"libelle"' in ligne


def test_un_index_unique_est_cree_sans_le_declarer(tmp_path, capsys):
    """Un numéro en double n'est pas un numéro. Exiger 'unique' dans la spec
    ferait dépendre la garantie d'une ligne qu'on peut oublier d'écrire."""
    _, genere = _compile(tmp_path)
    capsys.readouterr()
    assert "idx_unique_commande_reference" in genere


def test_la_sortie_differe_sans_la_regle(tmp_path, capsys):
    """POINT 85 : le test qui interdit une règle ne produisant rien."""
    _, avec = _compile(tmp_path, SPEC, "avec")
    _, sans = _compile(
        tmp_path, SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n', ""),
        "sans")
    capsys.readouterr()
    assert avec != sans


def test_le_contrat_annonce_un_champ_en_lecture_seule(tmp_path, capsys):
    contrat, _ = _compile(tmp_path)
    capsys.readouterr()
    champ = next(f for f in contrat["entities"]["Commande"]["fields"]
                 if f["name"] == "reference")
    assert champ["server_generated"] is True
    assert champ["numbered_as"] == "CMD-{YYYY}-{NNNN}"
    assert "Ne pas l'envoyer" in champ["note"]
    route = next(r for r in contrat["routes"]
                 if r["method"] == "POST" and r["path"] == "/commande")
    assert "reference" not in route["request_fields"]


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
        with urllib.request.urlopen(requete, timeout=20) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {}


def _demarrer(dossier, port):
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(dossier), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    for _ in range(120):
        if processus.poll() is not None:
            pytest.fail(processus.stdout.read().decode("utf-8", "replace")[-2000:])
        try:
            urllib.request.urlopen(base + "/docs", timeout=5).read()
            return processus, base
        except OSError:
            time.sleep(0.25)
    processus.kill()
    pytest.fail("le serveur n'a jamais répondu")


def _arreter(processus):
    processus.terminate()
    try:
        return processus.communicate(timeout=10)[0].decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        processus.kill()
        return ""


@pytest.fixture
def carnet(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    processus, base = _demarrer(tmp_path, _port_libre())
    try:
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, jeton["access_token"], tmp_path
    finally:
        _arreter(processus)


def _numero(base, identifiant, jeton):
    _, reponse = _appel(f"{base}/commande/{identifiant}", jeton=jeton)
    return reponse["data"]["reference"]


def test_les_numeros_se_suivent(carnet):
    base, jeton, _ = carnet
    numeros = []
    for i in range(3):
        _, cree = _appel(base + "/commande", {"libelle": f"achat {i}"}, jeton)
        numeros.append(_numero(base, cree["id"], jeton))
    annee = time.gmtime().tm_year
    assert numeros == [f"CMD-{annee}-0001", f"CMD-{annee}-0002", f"CMD-{annee}-0003"]


def test_le_client_ne_peut_pas_choisir_son_numero(carnet):
    """Le champ n'est pas dans le schéma : l'envoyer ne fait rien. C'est le
    comportement de toute la famille des champs peuplés par le serveur."""
    base, jeton, _ = carnet
    _, cree = _appel(base + "/commande",
                     {"libelle": "triche", "reference": "CMD-1999-0001"}, jeton)
    assert _numero(base, cree["id"], jeton) != "CMD-1999-0001"


def test_le_numero_ne_bouge_pas_a_la_modification(carnet):
    base, jeton, _ = carnet
    _, cree = _appel(base + "/commande", {"libelle": "achat"}, jeton)
    avant = _numero(base, cree["id"], jeton)
    code, _ = _appel(f"{base}/commande/{cree['id']}",
                     {"libelle": "renommé", "reference": "CMD-1999-9999"},
                     jeton, methode="PUT")
    assert code == 200
    assert _numero(base, cree["id"], jeton) == avant


def test_le_numero_ne_recule_pas_apres_une_suppression(carnet):
    """LA raison d'être de la table système. Avec `MAX(...) + 1`, supprimer la
    dernière commande ferait RÉATTRIBUER son numéro — deux factures, une seule
    référence."""
    base, jeton, _ = carnet
    _, premiere = _appel(base + "/commande", {"libelle": "a"}, jeton)
    _, seconde = _appel(base + "/commande", {"libelle": "b"}, jeton)
    deuxieme_numero = _numero(base, seconde["id"], jeton)
    _appel(f"{base}/commande/{seconde['id']}", jeton=jeton, methode="DELETE")
    _, troisieme = _appel(base + "/commande", {"libelle": "c"}, jeton)
    assert _numero(base, troisieme["id"], jeton) != deuxieme_numero
    assert _numero(base, premiere["id"], jeton).endswith("0001")


def test_deux_creations_simultanees_ne_partagent_pas_un_numero(carnet):
    """Huit créations concurrentes : huit numéros distincts, et aucun échec.

    Ce que ce test prouve VRAIMENT, et pas plus : que la contention ne produit
    ni collision, ni « database is locked », ni 500. Il ne départage pas à lui
    seul un compteur atomique d'un `MAX(...) + 1` — SQLite sérialise les
    écritures, et cette sérialisation masquerait la différence sous une charge
    aussi modeste. C'est `test_le_numero_ne_recule_pas_apres_une_suppression`
    qui tranche entre les deux conceptions."""
    base, jeton, _ = carnet
    obtenus, verrou = [], threading.Lock()

    def commander(rang):
        code, cree = _appel(base + "/commande", {"libelle": f"lot {rang}"}, jeton)
        with verrou:
            obtenus.append((code, cree.get("id")))

    fils = [threading.Thread(target=commander, args=(i,)) for i in range(8)]
    for f in fils:
        f.start()
    for f in fils:
        f.join(timeout=30)

    assert all(code == 200 for code, _ in obtenus), obtenus
    numeros = [_numero(base, identifiant, jeton) for _, identifiant in obtenus]
    assert len(set(numeros)) == 8, numeros


def test_une_periode_anterieure_ne_decale_pas_la_sequence(carnet):
    """La séquence repart à 1 à chaque année : un compteur laissé par l'année
    passée ne doit pas être repris."""
    base, jeton, dossier = carnet
    connexion = sqlite3.connect(str(dossier / "app.db"))
    connexion.execute(
        "INSERT INTO _monl_sequences (entite, champ, periode, dernier) "
        "VALUES ('Commande', 'reference', '2019', 41)")
    connexion.commit()
    connexion.close()
    _, cree = _appel(base + "/commande", {"libelle": "cette année"}, jeton)
    assert _numero(base, cree["id"], jeton).endswith("0001")


def test_les_enregistrements_anterieurs_restent_sans_numero(tmp_path):
    """POINT 89, mot pour mot : la migration additive rattrape une colonne,
    jamais son contenu. Numéroter après coup inventerait un ordre d'arrivée."""
    sans = SPEC.replace('rule Commande.reference numbered "CMD-{YYYY}-{NNNN}"\n', "")
    (tmp_path / "spec.ml").write_text(sans, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    processus, base = _demarrer(tmp_path, _port_libre())
    _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                "actor": "Client"})
    _, jeton = _appel(base + "/login", {"username": "zoe", "password": "motdepasse1"})
    jeton = jeton["access_token"]
    _appel(base + "/commande", {"libelle": "avant la règle", "reference": ""}, jeton)
    _arreter(processus)

    # La règle arrive maintenant, sur la base déjà peuplée.
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    processus, base = _demarrer(tmp_path, _port_libre())
    _, nouvelle = _appel(base + "/commande", {"libelle": "après"}, jeton)
    journal = _arreter(processus)

    connexion = sqlite3.connect(str(tmp_path / "app.db"))
    try:
        refs = [r[0] for r in connexion.execute(
            'SELECT "reference" FROM "commande" ORDER BY id').fetchall()]
    finally:
        connexion.close()
    # L'ancienne garde ce qu'elle avait, la nouvelle repart de 1.
    assert refs[-1].endswith("0001")
    assert refs[0] != refs[-1]
    assert "sans numéro" in journal or refs[0] == ""
