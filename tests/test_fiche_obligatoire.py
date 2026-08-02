"""Brique 17 : « on ne commande pas sans être identifié » — point 90.

Pourquoi cette brique. Sur `projets/SneakerLab`, deux commandes réelles
portaient un compte SANS aucune fiche client :

    commande 10  compte 7  login=sondeur  fiche=— AUCUNE —
    commande 11  compte 7  login=sondeur  fiche=— AUCUNE —

Rien n'obligeait à créer une fiche avant de commander, et le registre des
comptes (`_monl_users`) n'est exposé par aucune route — délibérément, il porte
les empreintes de mots de passe. L'administrateur voyait donc une commande qu'il
ne pouvait attribuer à personne : ni nom, ni adresse, ni moyen d'en obtenir.
Pour une boutique, ce n'est pas un défaut d'affichage, c'est une **commande
inexpédiable**.

Deux voies existaient. Exposer l'identité du compte aux rôles autorisés aurait
donné le login — mais un login ne s'expédie pas, et ça entamait la promesse du
pseudonyme `generated` (brique 7). Garantir la fiche règle le fond sans toucher
à l'authentification : c'est la voie retenue.

Ce que la brique décide, et qui n'allait pas de soi :

* **la vérification vient EN PREMIER**, avant le contrôle du parent et avant
  tout calcul. Un appelant sans fiche n'a pas à apprendre si tel produit existe,
  ni à consommer du stock au passage ;
* **409, pas 403.** Ce n'est pas un droit qui manque — c'est un état à corriger,
  et le message dit lequel. Un 403 inviterait à croire que le compte est mal
  provisionné ;
* **la fiche est cherchée par identifiant de COMPTE**, via
  `_identity_fk_columns` — la source unique du point 88. La retrouver autrement,
  ce serait réécrire la moitié du bug que ce point-là a corrigé ;
* **seule `Create` peut l'exiger.** Sur une lecture ou une modification,
  l'enregistrement existe déjà : exiger une fiche a posteriori rendrait
  inaccessibles des données qu'on possède.
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

SPEC = """app BancFiche

entity Commande
    statut: String

entity Client
    nom: String

relation Client hasMany Commande
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Commande.statut required
rule Client.nom required
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Client.Delete ownedBy Client
rule Commande.Create requiresOwn Client

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Client
    Read Client
    # POINT 96 : `Delete Client` éprouve le PENDANT de la règle. Sans cette
    # action, la brique n'avait aucune façon d'être prise en défaut — et elle
    # l'était : `requiresOwn` gardait la création, et rien n'empêchait ensuite
    # de supprimer sa fiche en laissant la commande sans destinataire.
    Delete Client

workflow Gerer for Patron
    Read Commande
    Read Client
"""

SANS_REGLE = SPEC.replace("rule Commande.Create requiresOwn Client\n", "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation doit refuser
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    """Le témoin des refus qui suivent."""
    ast = _valide(SPEC)
    assert ast["security"]["required_profiles"] == {"Commande": "Client"}
    capsys.readouterr()


def test_une_reference_sans_action_est_refusee(capsys):
    """Refusé par la GRAMMAIRE, pas par le validateur : le jeton `REFERENCE`
    exige le point. Le validateur porte quand même la garde, comme ses huit
    règles sœurs — écrit ici pour que le jour où la grammaire s'assouplirait,
    la couche qui tranche soit choisie et non découverte."""
    from monl.parser import MonlSyntaxError

    with pytest.raises(MonlSyntaxError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Commande requiresOwn Client"))
    assert "Entite.champ ou Entite.Action" in str(refus.value)
    capsys.readouterr()


def test_une_entite_inexistante_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Fantome.Create requiresOwn Client"))
    assert "n'existe pas" in str(refus.value)
    capsys.readouterr()


def test_une_action_autre_que_create_est_refusee(capsys):
    """Sur Read/Update/Delete, l'enregistrement existe déjà : la fiche ne peut
    plus rien empêcher, elle ne ferait que rendre inaccessible ce qu'on possède."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Commande.Update requiresOwn Client"))
    assert "Create" in str(refus.value)
    capsys.readouterr()


def test_exiger_une_entite_inexistante_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("requiresOwn Client", "requiresOwn Fantome"))
    assert "pas une entité déclarée" in str(refus.value)
    capsys.readouterr()


def test_une_entite_ne_peut_pas_sexiger_elle_meme(capsys):
    """Le premier enregistrement ne pourrait jamais être créé."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Client.Create requiresOwn Client"))
    assert "elle-même" in str(refus.value)
    capsys.readouterr()


def test_exiger_une_entite_que_personne_ne_possede_est_refuse(capsys):
    """« En posséder un » n'a de sens que si la propriété se déduit du jeton.
    Sans règle 'ownedBy' menant à un acteur, la question n'a pas de réponse."""
    # Les DEUX règles de propriété doivent tomber : depuis le point 96 le banc
    # porte aussi 'Client.Delete ownedBy Client', et il suffit d'une seule pour
    # que la propriété se déduise du jeton.
    sans_propriete = (SPEC.replace("rule Client.Read ownedBy Client\n", "")
                          .replace("rule Client.Delete ownedBy Client\n", ""))
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans_propriete)
    assert "possédé par aucun acteur" in str(refus.value)
    capsys.readouterr()


def test_une_creation_publique_est_refusee(capsys):
    """Sans appelant identifié, aucune fiche ne peut être cherchée. Même refus
    que 'generated' et 'payable', même raison."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.Create public\n")
    assert "public" in str(refus.value)
    capsys.readouterr()


def test_deux_regles_sur_la_meme_entite_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.Create requiresOwn Client\n")
    assert "une seule autorisée" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def _compile(dossier, spec, capsys):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))
    capsys.readouterr()
    return (dossier / "app.py").read_text(encoding="utf-8")


def test_la_regle_change_vraiment_la_sortie(tmp_path, capsys):
    """Discipline du point 85 : aucune brique ne repart sans ce test."""
    assert _compile(tmp_path / "a", SPEC, capsys) != _compile(tmp_path / "b",
                                                             SANS_REGLE, capsys)


def test_la_verification_est_la_toute_premiere_requete(tmp_path, capsys):
    """Ce qui décide de l'ordre : un appelant sans fiche ne doit rien apprendre
    du catalogue, et surtout ne rien consommer. Placée après le contrôle du
    parent ou après un calcul 'derivedFrom', elle laisserait fuiter l'existence
    d'un enregistrement lié — et, sur une entité qui décompte du stock, elle
    laisserait le décompte se produire avant le refus."""
    genere = _compile(tmp_path, SPEC, capsys)
    creation = genere.split("def create_commande")[1].split("@app.")[0]
    premiere = next(li for li in creation.splitlines() if "cursor.execute(" in li)
    assert 'SELECT 1 FROM "client"' in premiere, creation


def test_la_fiche_est_cherchee_par_identifiant_de_compte(tmp_path, capsys):
    """POINT 88 : la colonne de propriété d'une entité créée par son titulaire
    porte un id de COMPTE, pas l'`id` de la ligne. Chercher `WHERE id = ?`
    trouverait la fiche de quelqu'un d'autre dès que les deux divergent."""
    genere = _compile(tmp_path, SPEC, capsys)
    creation = genere.split("def create_commande")[1].split("@app.")[0]
    ligne = next(li for li in creation.splitlines() if 'SELECT 1 FROM "client"' in li)
    assert '"client_id" = ?' in ligne
    assert "current_user_id" in ligne


def test_le_contrat_annonce_le_prealable(tmp_path, capsys):
    """Sans cette note, une IA d'interface bâtit un tunnel d'achat qui bute en
    409 au dernier écran — le seul endroit où l'utilisateur a déjà tout rempli."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    contrat = json.loads((tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    route = next(r for r in contrat["routes"]
                 if r["method"] == "POST" and r["path"] == "/commande")
    assert route["requires_own"] == "Client"
    assert "PRÉALABLE" in route["note"]
    assert "AVANT" in route["note"], "le contrat doit dire QUAND, pas seulement quoi"


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


def _compte(base, nom):
    _appel(base + "/register", {"username": nom, "password": "motdepasse1",
                                "actor": "Client"})
    _, jeton = _appel(base + "/login", {"username": nom, "password": "motdepasse1"})
    return jeton["access_token"]


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
        yield base, tmp_path
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()


def test_commander_sans_fiche_est_refuse_et_ne_cree_rien(boutique):
    base, _ = boutique
    jeton = _compte(base, "zoe")

    code, reponse = _appel(base + "/commande", {"statut": "panier"}, jeton)
    assert code == 409
    assert "fiche Client" in reponse["detail"]

    _, liste = _appel(base + "/commande", jeton=jeton)
    assert liste["total"] == 0, "un refus ne doit rien avoir créé"


def test_la_fiche_creee_ouvre_la_commande(boutique):
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _appel(base + "/client", {"nom": "Zoé Martin"}, jeton)

    code, _ = _appel(base + "/commande", {"statut": "panier"}, jeton)
    assert code == 200


def test_la_fiche_dun_autre_ne_suffit_pas(boutique):
    """LE test de la brique. Une vérification écrite « existe-t-il au moins une
    fiche ? » passerait ici — et la première fiche créée sur la boutique
    ouvrirait la commande à tout le monde. La preuve exige donc DEUX comptes,
    dont un seul a sa fiche."""
    base, _ = boutique
    avec = _compte(base, "zoe")
    _appel(base + "/client", {"nom": "Zoé Martin"}, avec)
    sans = _compte(base, "bob")

    code, reponse = _appel(base + "/commande", {"statut": "panier"}, sans)
    assert code == 409, "la fiche de Zoé ne doit rien ouvrir à Bob"
    assert "fiche Client" in reponse["detail"]


def test_toute_commande_est_desormais_attribuable(boutique):
    """Le trou que la brique ferme, énoncé à l'endroit : après elle, il ne peut
    plus exister de commande dont on ignore le titulaire."""
    import sqlite3

    base, dossier = boutique
    for nom in ("zoe", "bob"):
        jeton = _compte(base, nom)
        _appel(base + "/client", {"nom": nom.title()}, jeton)
        _appel(base + "/commande", {"statut": "panier"}, jeton)

    conn = sqlite3.connect(dossier / "app.db")
    orphelines = conn.execute(
        'SELECT COUNT(*) FROM commande WHERE client_id NOT IN '
        '(SELECT client_id FROM client)').fetchone()[0]
    conn.close()
    assert orphelines == 0


# --------------------------------------------------------------------------
# POINT 96 : le pendant à la SUPPRESSION
# --------------------------------------------------------------------------

def test_supprimer_sa_derniere_fiche_avec_une_commande_est_refuse(boutique):
    """LE trou, mesuré sur `projets/SneakerLab` en comparant le parcours à
    celui d'une boutique classique : `DELETE /customer` répondait 200 et
    laissait 1 commande pour 0 fiche. `requiresOwn` gardait la CRÉATION depuis
    le point 90 ; le trou se rouvrait par l'autre bout, et l'état obtenu était
    exactement celui que ce point-là existe pour empêcher — une commande que
    l'administrateur ne peut attribuer à personne."""
    base, dossier = boutique
    jeton = _compte(base, "zoe")
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, jeton)
    _appel(base + "/commande", {"statut": "panier"}, jeton)

    code, reponse = _appel(f"{base}/client/{fiche['id']}", jeton=jeton, methode="DELETE")

    assert code == 409, reponse
    assert "Commande" in reponse["detail"]
    conn = sqlite3.connect(str(dossier / "app.db"))
    assert conn.execute("SELECT COUNT(*) FROM client").fetchone()[0] == 1
    conn.close()


def test_sans_commande_la_fiche_reste_supprimable(boutique):
    """LE témoin, et il compte autant : un garde qui refuserait toute
    suppression passerait le test précédent sans rien garantir, et rendrait le
    compte impossible à fermer."""
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, jeton)

    code, reponse = _appel(f"{base}/client/{fiche['id']}", jeton=jeton, methode="DELETE")

    assert code == 200, reponse


def test_lavant_derniere_fiche_reste_supprimable(boutique):
    """`requiresOwn` exige « au moins une » : tant qu'il en reste une, la
    commande reste rattachée. Refuser ici serait plus strict que la règle."""
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _, premiere = _appel(base + "/client", {"nom": "Zoé"}, jeton)
    _, seconde = _appel(base + "/client", {"nom": "Zoé pro"}, jeton)
    _appel(base + "/commande", {"statut": "panier"}, jeton)

    code, reponse = _appel(f"{base}/client/{seconde['id']}", jeton=jeton, methode="DELETE")
    assert code == 200, reponse
    # …mais la DERNIÈRE reste protégée.
    code, _ = _appel(f"{base}/client/{premiere['id']}", jeton=jeton, methode="DELETE")
    assert code == 409


def test_la_fiche_dun_AUTRE_compte_ne_protege_pas_la_mienne(boutique):
    """Le piège du test, encore : avec un seul compte, « existe-t-il une fiche
    quelque part ? » passerait. Le décompte doit porter sur MON compte."""
    base, _ = boutique
    zoe = _compte(base, "zoe")
    autre = _compte(base, "max")
    _appel(base + "/client", {"nom": "Max"}, autre)
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, zoe)
    _appel(base + "/commande", {"statut": "panier"}, zoe)

    code, _ = _appel(f"{base}/client/{fiche['id']}", jeton=zoe, methode="DELETE")

    assert code == 409, "la fiche d'un autre compte a été comptée comme la mienne"
