"""Le rattachement fantôme — point 99.

Ce que le compilateur faisait. Une entité fille d'une table MÉTIER (une variante
et son produit) recevait, dans la colonne `produit_id`, l'identifiant du COMPTE
qui l'avait créée — et `schema.sql` la déclarait `REFERENCES _monl_users(id)`.
Le client n'avait aucun moyen de désigner le produit : la colonne portait le nom
du lien métier et contenait autre chose. Silencieux, à la compilation comme à
l'exécution.

Pourquoi personne ne l'avait vu. Aucun exemple du dépôt ne présente ce cas :
`Like` et `Report` y échappent parce qu'ils sont cibles d'un compteur (le client
désigne « CE post »), `Comment` parce qu'il déclare `ownedBy Member`, `OrderLine`
parce qu'il est possédé transitivement. Les cinq exemples compilent tous une
entité fille d'un ACTEUR. La sonde qui l'a révélé tenait en trois relations.

Ce que le point décide, et qui n'allait pas de soi :

* **« peuplée depuis l'identité » exige que le parent SOIT un compte.** La
  condition manquait : toute relation entrante faisait l'affaire. C'est le défaut
  du point 80 par l'autre bout — là on nommait une entité comme propriétaire et
  le rattachement était faux, ici on n'en nomme aucune et il l'est tout autant ;
* **le choix ne dépend plus de l'ordre de déclaration.** Seuls les parents
  acteurs sont candidats ; entre eux, `ownedBy` tranche ;
* **`payable` perd une sécurité ACCIDENTELLE, donc gagne un refus.** La route de
  règlement comparait la colonne de propriété à l'appelant. Elle n'était juste
  que parce que la colonne recevait `current_user_id` faute de mieux — c'est-à-dire
  à cause du bug. Le rattachement redevenu honnête, la comparaison deviendrait
  fausse : le refus doit être écrit.
"""
import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import _contract_signature, compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

# La relation MÉTIER (`Produit hasMany Variante`) est déclarée AVANT les autres,
# à dessein : l'ancienne implémentation retenait la première relation entrante
# venue, et un banc qui la déclarerait en dernier masquerait la moitié du défaut.
SPEC = """app BancRattachement

entity Produit
    nom: String

entity Variante
    taille: String
    stock: Integer

entity Commande
    statut: String

entity Ligne
    quantite: Integer

entity Client
    nom: String

relation Produit hasMany Variante
relation Client hasMany Commande
relation Commande hasMany Ligne
relation Variante hasMany Ligne
relation Client hasMany Client

actor Client selfRegister
actor Patron selfRegister

rule Produit.Read public
rule Variante.Read public
rule Variante.stock min 0
rule Ligne.quantite required
rule Ligne.quantite min 1
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Commande
rule Ligne.Create decrements Variante.stock by quantite

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Ligne
    Read Ligne
    Delete Ligne
    Create Client
    Read Client
    Read Produit
    Read Variante

workflow Gerer for Patron
    Create Produit
    Read Produit
    Create Variante
    Read Variante
    Update Variante

seed Produit
    nom: "Halo RS"
    nom: "Deck Low"
    nom: "Court Mid"
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


def _compile(tmp_path, spec=SPEC):
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    contrat = compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return contrat, (tmp_path / "app.py").read_text(encoding="utf-8"), \
        (tmp_path / "schema.sql").read_text(encoding="utf-8")


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(tmp_path, capsys):
    """Le témoin de tout ce qui suit."""
    contrat, _, _ = _compile(tmp_path)
    assert "Variante" in contrat["entities"]
    capsys.readouterr()


def test_le_parent_metier_reference_la_table_metier(tmp_path, capsys):
    """LE bug. `produit_id` se déclarait `REFERENCES _monl_users(id)` : la
    variante pointait vers le registre des comptes, jamais vers son produit."""
    _, _, schema = _compile(tmp_path)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"produit_id"' in li
              and "FOREIGN KEY" in li)
    assert 'REFERENCES "produit"(id)' in fk
    assert "_monl_users" not in fk


def test_le_parent_metier_est_designe_par_le_client(tmp_path, capsys):
    """L'autre moitié du même défaut : la colonne recevait `current_user_id`,
    donc AUCUN produit ne pouvait être désigné à la création."""
    _, genere, _ = _compile(tmp_path)
    capsys.readouterr()
    insertion = next(li for li in genere.splitlines()
                     if 'INSERT INTO "variante"' in li)
    assert '"produit_id"' in insertion
    valeurs = genere.splitlines()[genere.splitlines().index(insertion) + 2]
    assert "data.produit_id" in valeurs
    assert "current_user_id" not in valeurs


def test_le_parent_metier_entre_dans_le_schema_dentree(tmp_path, capsys):
    """Une colonne que le client doit fournir et qu'aucun schéma n'accepte
    donnerait un 422 imparable — c'est le défaut du point 57, rejoué."""
    _, genere, _ = _compile(tmp_path)
    capsys.readouterr()
    debut = genere.index("class VarianteSchema")
    assert "produit_id: int" in genere[debut:debut + 400]


def test_le_parent_acteur_na_pas_bouge(tmp_path, capsys):
    """La non-régression qui compte : le cas CORRECT — une entité fille d'un
    acteur — doit continuer de se peupler depuis le jeton. Une correction qui
    rendrait toutes les clés étrangères clientes ouvrirait un trou bien plus
    large que celui qu'elle ferme."""
    _, genere, schema = _compile(tmp_path)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"client_id"' in li
              and "FOREIGN KEY" in li and "commande" not in li.lower())
    assert "_monl_users" in fk
    insertion = next(li for li in genere.splitlines()
                     if 'INSERT INTO "commande"' in li)
    assert '"client_id"' in insertion
    debut = genere.index("class CommandeSchema")
    assert "client_id" not in genere[debut:debut + 300], \
        "la colonne du propriétaire ne doit JAMAIS entrer dans le corps de requête"


def test_la_cible_dun_compteur_reste_designee_par_le_client(tmp_path, capsys):
    """Non-régression de la brique 3 : « je signale CE membre » est un choix du
    client, pas une propriété déduite. Ce cas passait déjà — il doit continuer,
    et par le même chemin qu'avant."""
    spec = SPEC.replace("relation Variante hasMany Ligne",
                        "relation Variante hasMany Ligne\nrelation Produit hasMany Avis")
    spec = spec.replace("entity Client\n    nom: String",
                        "entity Client\n    nom: String\n\nentity Avis\n    note: Integer")
    spec = spec.replace("rule Ligne.Create decrements Variante.stock by quantite",
                        "rule Ligne.Create decrements Variante.stock by quantite\n"
                        "rule Avis.Create increments Produit.avis by 1")
    spec = spec.replace("entity Produit\n    nom: String",
                        "entity Produit\n    nom: String\n    avis: Integer")
    spec = spec.replace("    Read Variante\n\nworkflow Gerer",
                        "    Read Variante\n    Create Avis\n    Read Avis\n\nworkflow Gerer")
    _, genere, schema = _compile(tmp_path, spec)
    capsys.readouterr()
    fk = next(li for li in schema.splitlines() if '"produit_id"' in li
              and "FOREIGN KEY" in li)
    assert 'REFERENCES "produit"(id)' in fk
    assert "data.produit_id" in genere


def test_le_choix_ne_depend_pas_de_lordre_des_relations(tmp_path, capsys):
    """L'ancienne implémentation retenait `placements[0]` : deux parents, et le
    propriétaire se décidait à l'ordre d'écriture de la spec. Un parent métier
    déclaré en premier volait la place de l'acteur."""
    base = SPEC.replace("entity Client\n    nom: String",
                        "entity Client\n    nom: String\n\nentity Avis\n    note: Integer")
    base = base.replace("    Read Variante\n\nworkflow Gerer",
                        "    Read Variante\n    Create Avis\n    Read Avis\n\nworkflow Gerer")
    metier_dabord = base.replace(
        "relation Client hasMany Client",
        "relation Produit hasMany Avis\nrelation Client hasMany Avis\n"
        "relation Client hasMany Client")
    acteur_dabord = base.replace(
        "relation Client hasMany Client",
        "relation Client hasMany Avis\nrelation Produit hasMany Avis\n"
        "relation Client hasMany Client")
    _, _, schema_a = _compile(tmp_path, metier_dabord)
    _, _, schema_b = _compile(tmp_path, acteur_dabord)
    capsys.readouterr()

    def liens_avis(schema):
        bloc = schema[schema.index('CREATE TABLE IF NOT EXISTS "avis"'):]
        # La virgule finale dépend du RANG de la ligne dans le bloc, pas de son
        # sens : la retirer, sinon le test compare une mise en forme.
        return {li.strip().rstrip(",") for li in bloc.splitlines()
                if "FOREIGN KEY" in li}

    assert liens_avis(schema_a) == liens_avis(schema_b)
    assert any('"client_id"' in li and "_monl_users" in li
               for li in liens_avis(schema_a))
    assert any('"produit_id"' in li and '"produit"(id)' in li
               for li in liens_avis(schema_a))


# --------------------------------------------------------------------------
# Ce que le contrat doit dire
# --------------------------------------------------------------------------

def test_le_contrat_dit_ce_que_la_colonne_contient(tmp_path, capsys):
    """POINT 88 : une jointure faite sur la mauvaise des deux natures marche À
    MOITIÉ. Le contrat annonçait `references_account` sur une colonne qui porte
    l'id d'un produit."""
    contrat, _, _ = _compile(tmp_path)
    capsys.readouterr()
    lien = next(li for li in contrat["entities"]["Variante"]["foreign_keys"]
                if li["column"] == "produit_id")
    assert lien["references_account"] is False
    assert lien["references"] == "Produit"
    assert "produit_id" in contrat["entities"]["Variante"]["client_foreign_keys"]


def test_le_contrat_reclame_le_parent_dans_le_corps(tmp_path, capsys):
    """Sans ça, une IA d'interface fidèle au contrat bâtit un formulaire sans
    choix du produit et récolte un 422 à chaque création."""
    contrat, _, _ = _compile(tmp_path)
    capsys.readouterr()
    route = next(r for r in contrat["routes"]
                 if r["path"] == "/variante" and r["method"] == "POST")
    assert "produit_id" in route["request_fields"]


def test_le_delta_voit_le_changement_de_nature(tmp_path, capsys):
    """La question que CLAUDE.md impose de poser AVANT d'écrire : est-ce que
    `_contract_signature` le voit ? Une clé étrangère ne vit pas dans `fields` —
    la réponse était non, pour la sixième fois."""
    contrat_metier, _, _ = _compile(tmp_path)
    acteur = SPEC.replace("relation Produit hasMany Variante",
                          "relation Client hasMany Variante")
    contrat_acteur, _, _ = _compile(tmp_path, acteur)
    capsys.readouterr()
    liens_metier = _contract_signature(contrat_metier)[7]
    liens_acteur = _contract_signature(contrat_acteur)[7]
    assert liens_metier != liens_acteur
    assert any("produit_id" in li and "à envoyer par le client" in li
               for li in liens_metier)
    assert any("client_id" in li and "identifiant de compte" in li
               and "renseigné par le serveur" in li for li in liens_acteur)


# --------------------------------------------------------------------------
# Le refus que la correction rend nécessaire
# --------------------------------------------------------------------------


# Le montant des lignes est CALCULÉ (point 77) : sans quoi le recoupement du
# point 82 refuserait la spec avant d'arriver au contrôle qu'on veut éprouver —
# sommer un montant que le client écrit est déjà interdit.
SPEC_PAIEMENT = """app BancEncaissement

entity Produit
    nom: String
    prix: Money

entity Facture
    total: Money

entity Ligne
    quantite: Integer
    montant: Money

relation Produit hasMany Facture
relation Facture hasMany Ligne
relation Client hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Ligne.Read ownedBy Client
rule Ligne.quantite required
rule Ligne.montant derivedFrom Produit.prix by quantite
rule Facture.total sumOf Ligne.montant
rule Facture.total payable

workflow Acheter for Client
    Create Facture
    Read Facture
    Create Ligne
    Read Ligne
"""

# Le même encaissement, mais la facture est possédée À TRAVERS la commande :
# la jointure du point 87 rend un id de COMPTE, donc le refus ne doit pas
# s'appliquer. Écrit en entier plutôt que dérivé par substitution — une chaîne
# de propriété se lit mal en `.replace()`.
SPEC_PAIEMENT_TRANSITIF = """app BancEncaissementTransitif

entity Produit
    nom: String
    prix: Money

entity Commande
    statut: String

entity Facture
    total: Money

entity Ligne
    quantite: Integer
    montant: Money

relation Client hasMany Commande
relation Commande hasMany Facture
relation Facture hasMany Ligne
relation Client hasMany Ligne
relation Produit hasMany Ligne

actor Client selfRegister

rule Produit.Read public
rule Commande.Read ownedBy Client
rule Facture.Read ownedBy Commande
rule Ligne.Read ownedBy Client
rule Ligne.quantite required
rule Ligne.montant derivedFrom Produit.prix by quantite
rule Facture.total sumOf Ligne.montant
rule Facture.total payable

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Facture
    Read Facture
    Create Ligne
    Read Ligne
"""


def test_encaisser_sans_proprietaire_acteur_est_refuse(capsys):
    """La sécurité ACCIDENTELLE que la correction retire. Cette spec compilait :
    la route de règlement comparait `produit_id` à l'id du compte appelant, et
    la comparaison était juste uniquement parce que la colonne recevait
    `current_user_id` — c'est-à-dire à cause du bug. Sans ce refus, le
    propriétaire ne pourrait plus payer, et un inconnu le pourrait dès que les
    deux identifiants coïncident."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC_PAIEMENT)
    assert "ACTEUR" in str(refus.value)
    assert "Facture" in str(refus.value)
    capsys.readouterr()


def test_le_temoin_du_refus(capsys):
    """La même spec avec un parent acteur doit compiler — sans quoi le refus
    ci-dessus interdirait la brique au lieu d'interdire la faute."""
    ast = _valide(SPEC_PAIEMENT.replace(
        "relation Produit hasMany Facture",
        "relation Produit hasMany Facture\nrelation Client hasMany Facture"))
    assert ast["security"]["payable_fields"]
    capsys.readouterr()


def test_le_refus_laisse_passer_la_propriete_transitive(capsys):
    """POINT 87 : sous chaîne, la jointure rend un id de COMPTE. Le nouveau
    refus ne doit pas rouvrir le verrou que ce point-là avait levé."""
    ast = _valide(SPEC_PAIEMENT_TRANSITIF)
    assert ast["security"]["payable_fields"]
    capsys.readouterr()


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
        # Le vendeur est inscrit en DERNIER, après trois autres comptes : son
        # identifiant (4) ne coïncide alors avec celui d'AUCUN des trois
        # produits. Sans cette divergence, « id du compte » et « id du produit »
        # se valent et le rattachement fautif passerait le test — c'est la leçon
        # de la sonde du point 81, et elle vaut ici mot pour mot.
        for figurant in ("zoe", "ines", "malik"):
            _appel(base + "/register", {"username": figurant,
                                        "password": "motdepasse1",
                                        "actor": "Client"})
        _appel(base + "/register", {"username": "victor", "password": "motdepasse1",
                                    "actor": "Patron"})
        _, jeton_client = _appel(base + "/login", {"username": "zoe",
                                                   "password": "motdepasse1"})
        _, jeton_patron = _appel(base + "/login", {"username": "victor",
                                                   "password": "motdepasse1"})
        yield (base, jeton_client["access_token"], jeton_patron["access_token"],
               tmp_path)
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()


def _en_base(tmp_path, requete, params=()):
    connexion = sqlite3.connect(str(tmp_path / "app.db"))
    try:
        return connexion.execute(requete, params).fetchall()
    finally:
        connexion.close()


def test_la_variante_se_rattache_a_son_produit(boutique):
    """Le comportement que tout le reste sert. Lu en BASE, pas dans la réponse :
    la route de lecture ferait un `SELECT *` et rendrait la même chose quelle
    que soit la valeur écrite."""
    base, _, patron, tmp_path = boutique
    _, catalogue = _appel(base + "/produit?limit=20")
    deck = next(p for p in catalogue["data"] if p["nom"] == "Deck Low")

    comptes = _en_base(tmp_path, "SELECT id FROM _monl_users WHERE username = 'victor'")
    id_compte = comptes[0][0]
    assert id_compte != deck["id"], \
        "les deux identifiants doivent DIVERGER, sinon le test ne prouve rien"

    code, variante = _appel(base + "/variante",
                            {"taille": "42", "stock": 5, "produit_id": deck["id"]},
                            patron)
    assert code == 200
    rattachement = _en_base(tmp_path, 'SELECT "produit_id" FROM "variante" WHERE id = ?',
                            (variante["id"],))[0][0]
    assert rattachement == deck["id"]
    assert rattachement != id_compte, \
        "la colonne portait l'id du COMPTE créateur, jamais celui du produit"


def test_le_produit_designe_est_celui_quon_demande(boutique):
    """Deux produits, deux variantes : le rattachement doit SUIVRE la demande,
    pas une constante qui se trouverait juste une fois sur deux."""
    base, _, patron, tmp_path = boutique
    _, catalogue = _appel(base + "/produit?limit=20")
    produits = {p["nom"]: p["id"] for p in catalogue["data"]}
    poses = {}
    for nom, taille in (("Halo RS", "41"), ("Court Mid", "44")):
        _, variante = _appel(base + "/variante",
                             {"taille": taille, "stock": 2,
                              "produit_id": produits[nom]}, patron)
        poses[nom] = variante["id"]
    for nom, variante_id in poses.items():
        assert _en_base(tmp_path, 'SELECT "produit_id" FROM "variante" WHERE id = ?',
                        (variante_id,))[0][0] == produits[nom]


def test_le_stock_se_decompte_par_variante(boutique):
    """La chaîne entière, bout à bout : c'est le modèle « stock par taille »
    qu'un marchand tient, et il ne tenait pas debout tant que la variante ne
    savait pas à quel produit elle appartenait."""
    base, client, patron, _ = boutique
    _, catalogue = _appel(base + "/produit?limit=20")
    halo = next(p["id"] for p in catalogue["data"] if p["nom"] == "Halo RS")
    _, quarante_deux = _appel(base + "/variante",
                              {"taille": "42", "stock": 4, "produit_id": halo}, patron)
    _, quarante_trois = _appel(base + "/variante",
                               {"taille": "43", "stock": 4, "produit_id": halo}, patron)

    _appel(base + "/client", {"nom": "Zoe"}, client)
    _, commande = _appel(base + "/commande", {"statut": "panier"}, client)
    code, _ = _appel(base + "/ligne",
                     {"quantite": 3, "commande_id": commande["id"],
                      "variante_id": quarante_deux["id"]}, client)
    assert code == 200

    _, apres_42 = _appel(f"{base}/variante/{quarante_deux['id']}")
    _, apres_43 = _appel(f"{base}/variante/{quarante_trois['id']}")
    assert apres_42["data"]["stock"] == 1
    assert apres_43["data"]["stock"] == 4, \
        "deux tailles du même produit ont des stocks INDÉPENDANTS"


def test_le_plancher_tient_par_variante(boutique):
    """Le témoin du précédent : sans plancher effectif, « stock par taille »
    afficherait des paires qui n'existent pas."""
    base, client, patron, _ = boutique
    _, catalogue = _appel(base + "/produit?limit=20")
    halo = next(p["id"] for p in catalogue["data"] if p["nom"] == "Halo RS")
    _, variante = _appel(base + "/variante",
                         {"taille": "45", "stock": 2, "produit_id": halo}, patron)
    _appel(base + "/client", {"nom": "Zoe"}, client)
    _, commande = _appel(base + "/commande", {"statut": "panier"}, client)
    code, reponse = _appel(base + "/ligne",
                           {"quantite": 3, "commande_id": commande["id"],
                            "variante_id": variante["id"]}, client)
    assert code == 409
    assert "insuffisant" in json.dumps(reponse)
    _, apres = _appel(f"{base}/variante/{variante['id']}")
    assert apres["data"]["stock"] == 2, "un refus ne doit rien avoir consommé"


def test_un_produit_inexistant_ne_cree_pas_de_variante_orpheline(boutique):
    """La contrepartie de « le client fournit la clé » : elle doit être VÉRIFIÉE
    à l'écriture. Ici c'est la contrainte de clé étrangère qui s'en charge —
    règle de conception du point 81, appliquée à l'autre famille de colonnes."""
    base, _, patron, tmp_path = boutique
    avant = _en_base(tmp_path, 'SELECT COUNT(*) FROM "variante"')[0][0]
    code, _ = _appel(base + "/variante",
                     {"taille": "42", "stock": 1, "produit_id": 99999}, patron)
    assert code == 409
    assert _en_base(tmp_path, 'SELECT COUNT(*) FROM "variante"')[0][0] == avant
