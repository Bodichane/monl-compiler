"""Brique 16 : la date de création, écrite par le serveur — point 89.

Pourquoi cette brique. Aucune table métier générée par monl ne portait de date.
Un carnet de commandes sans dates n'est pas un carnet : on ne sait ni ce qui
est récent, ni dans quel ordre honorer. Le back-office de `projets/SneakerLab`
l'a montré en une capture — trois commandes, aucun moyen de dire laquelle
attend depuis le plus longtemps.

Ce que la brique décide, et qui n'allait pas de soi :

* **le client ne peut pas fournir la date, ni à la création ni à la
  modification.** Une date qu'on se donne à soi-même n'atteste de rien ; c'est
  la même raison que `generated` (point 30) et `derivedFrom` (point 77), et
  l'exclure du SET de la route Update évite en prime le 500 du point 78 ;
* **`Date` est refusé, `DateTime` exigé.** Tronquer au jour perdrait une
  information que le serveur possède, et rendrait deux enregistrements du même
  jour impossibles à ordonner — c'est-à-dire l'usage même d'un horodatage ;
* **la milliseconde, pas la seconde.** Deux commandes passées coup sur coup
  portaient la même date à la seconde près : le tri annoncé par le contrat
  devenait faux au premier coup de feu. Vérifié plus bas ;
* **les anciens enregistrements restent VIDES, et le serveur le dit.** La
  migration additive (point 32) rattrape une colonne, jamais son contenu. Pour
  toute autre brique c'est sans importance ; pour une date de création c'est
  irréparable — l'instant est passé et personne ne l'a vu. La remplir à l'heure
  du démarrage daterait toutes les vieilles commandes d'aujourd'hui : une base
  qui MENT, ce qui est pire qu'une case vide.
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

SPEC = """app BancHorodatage

entity Commande
    reference: String
    placedAt: DateTime
    statut: String

entity Client
    nom: String

relation Client hasMany Commande
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Commande.Read ownedBy Client
rule Commande.Update ownedBy Client
rule Client.Read ownedBy Client
rule Commande.placedAt timestamp

workflow Acheter for Client
    Create Commande
    Read Commande
    Update Commande
    Create Client
    Read Client

workflow Superviser for Patron
    Read Commande
"""

# La même spec sans la règle : le témoin des « avec / sans » de génération.
SANS_REGLE = SPEC.replace("rule Commande.placedAt timestamp\n", "")

# Et sans le CHAMP : l'état d'un projet d'avant la brique, seul point de départ
# valable pour éprouver la migration. Retirer la règle en gardant le champ ne
# prouverait rien — la colonne existerait déjà, donc aucun ALTER TABLE. Pire :
# le champ redevient un attribut ordinaire, donc obligatoire dans le corps de
# requête, et les créations de la première phase partaient en 422.
SANS_CHAMP = SANS_REGLE.replace("    placedAt: DateTime\n", "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation doit refuser
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    """Le témoin des refus qui suivent."""
    ast = _valide(SPEC)
    assert ast["security"]["timestamp_fields"] == [
        {"entity": "Commande", "field": "placedAt"}]
    capsys.readouterr()


def test_un_champ_texte_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.placedAt timestamp",
                             "rule Commande.reference timestamp"))
    assert "DateTime" in str(refus.value)
    capsys.readouterr()


def test_un_champ_date_est_refuse_en_le_disant(capsys):
    """`Date` compile ailleurs : c'est un type légitime, écrit par le client.
    Le refus doit donc EXPLIQUER, pas juste constater un type inattendu."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("placedAt: DateTime", "placedAt: Date"))
    message = str(refus.value)
    assert "Date" in message
    assert "ordonnables" in message, "le refus doit dire POURQUOI, pas seulement non"
    capsys.readouterr()


def test_un_champ_inexistant_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.placedAt timestamp",
                             "rule Commande.fantome timestamp"))
    assert "champ inexistant" in str(refus.value)
    capsys.readouterr()


def test_une_entite_inexistante_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.placedAt timestamp",
                             "rule Fantome.placedAt timestamp"))
    assert "n'existe pas" in str(refus.value)
    capsys.readouterr()


def test_masque_et_horodate_est_refuse(capsys):
    """Le client ne peut pas l'écrire ; masqué, il ne pourrait pas le lire non
    plus. Le champ n'existerait alors nulle part."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.placedAt hidden\n")
    assert "hidden" in str(refus.value)
    capsys.readouterr()


def test_deux_horodatages_sur_la_meme_entite_sont_refuses(capsys):
    """Tous deux recevraient le MÊME instant. Ce refus attrape surtout quelqu'un
    qui attendait une date de MODIFICATION — ce serait une autre brique."""
    spec = SPEC.replace("    statut: String", "    statut: String\n    updatedAt: DateTime")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec + "rule Commande.updatedAt timestamp\n")
    assert "MÊME instant" in str(refus.value)
    capsys.readouterr()


def test_deux_regles_sur_le_meme_champ_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.placedAt timestamp\n")
    assert "une seule autorisée" in str(refus.value)
    capsys.readouterr()


def test_required_sur_un_champ_horodate_est_refuse(capsys):
    """Hérité du recoupement du point 85, sans une ligne de plus : le contrat
    dirait à la fois « à remplir » et « à ne pas envoyer »."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.placedAt required\n")
    assert "SERVEUR" in str(refus.value)
    capsys.readouterr()


def test_une_borne_sur_un_champ_horodate_est_refusee(capsys):
    """Refusé, mais PAS par le recoupement du point 85 : `DateTime` n'est ni
    bornable en longueur ni bornable en valeur, donc `_valider_contraintes_de_champ`
    tranche avant. Le recoupement ne sert qu'à `required`. Écrit ici pour que le
    jour où `DateTime` deviendrait bornable, l'ordre des deux refus soit revu et
    non découvert."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.placedAt max 10\n")
    assert "DateTime" in str(refus.value)
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
    """La leçon du point 85 : quatre règles anciennes ne produisaient RIEN, et
    rien ne l'avait jamais vérifié. Aucune brique ne repart sans ce test."""
    avec = _compile(tmp_path / "a", SPEC, capsys)
    sans = _compile(tmp_path / "b", SANS_REGLE, capsys)
    assert avec != sans


def test_le_champ_horodate_sort_du_schema_dentree(tmp_path, capsys):
    genere = _compile(tmp_path, SPEC, capsys)
    schema = genere.split("class CommandeSchema(BaseModel):")[1].split("class ")[0]
    assert "placedAt" not in schema
    assert "reference" in schema, "les autres champs restent, eux"


def test_le_serveur_ecrit_la_date_a_la_creation(tmp_path, capsys):
    genere = _compile(tmp_path, SPEC, capsys)
    creation = genere.split("def create_commande")[1].split("@app.")[0]
    assert "_horodatage()" in creation


def test_la_modification_ne_touche_pas_a_la_date(tmp_path, capsys):
    """Une date de création qui bouge n'est pas une date de création. La lire
    depuis `data` donnerait en plus 500 — le défaut du point 78."""
    genere = _compile(tmp_path, SPEC, capsys)
    modification = genere.split("def update_commande")[1].split("@app.")[0]
    ligne_set = next(li for li in modification.splitlines() if "UPDATE " in li)
    assert "placedAt" not in ligne_set
    assert "data.placedAt" not in modification


def test_le_contrat_annonce_le_champ_comme_peuple_par_le_serveur(tmp_path, capsys):
    """POINT 76, quatrième récidive évitée : le contrat doit décrire ce que le
    backend fait VRAIMENT. Sans cela une IA d'interface bâtit un sélecteur de
    date que le serveur ignore."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    contrat = json.loads((tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    champ = next(f for f in contrat["entities"]["Commande"]["fields"]
                 if f["name"] == "placedAt")
    assert champ["server_generated"] is True
    assert champ["created_at"] is True
    # Le contrat doit AUSSI avertir du vide possible : c'est le seul cas du
    # compilateur où une colonne ajoutée ne peut pas être rattrapée.
    assert "VIDE" in champ["note"]


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


class _Serveur:
    """Un serveur éphémère qu'on peut arrêter puis RELANCER sur la même base —
    ce que la preuve de migration exige."""

    def __init__(self, dossier):
        self.dossier = dossier
        self.processus = None
        self.base = None
        self.journal = ""

    def demarrer(self):
        port = _port_libre()
        self.processus = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
             "--port", str(port)],
            cwd=str(self.dossier), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.base = f"http://127.0.0.1:{port}"
        for _ in range(120):
            if self.processus.poll() is not None:
                pytest.fail(self.processus.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                urllib.request.urlopen(self.base + "/docs", timeout=5).read()
                return self.base
            except OSError:
                time.sleep(0.25)
        pytest.fail("le serveur n'a jamais répondu")

    def arreter(self):
        if self.processus is None:
            return
        self.processus.terminate()
        try:
            sortie, _ = self.processus.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            self.processus.kill()
            sortie, _ = self.processus.communicate()
        self.journal += (sortie or b"").decode("utf-8", "replace")
        self.processus = None


@pytest.fixture
def carnet(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    serveur = _Serveur(tmp_path)
    base = serveur.demarrer()
    try:
        _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                    "actor": "Client"})
        _, jeton = _appel(base + "/login", {"username": "zoe",
                                            "password": "motdepasse1"})
        yield base, jeton["access_token"]
    finally:
        serveur.arreter()


def test_la_date_est_ecrite_sans_que_le_client_la_donne(carnet):
    base, jeton = carnet
    code, _ = _appel(base + "/commande", {"reference": "CMD-1", "statut": "panier"}, jeton)
    assert code == 200
    _, lu = _appel(base + "/commande/1", jeton=jeton)
    assert lu["data"]["placedAt"], "aucune date écrite"
    assert lu["data"]["placedAt"].endswith("+00:00"), "UTC explicite attendu"


def test_une_date_imposee_par_le_client_est_ignoree(carnet):
    """Le cœur de la brique. Sans elle, n'importe qui antidate sa commande —
    et personne ne peut plus rien prouver sur l'ordre d'arrivée."""
    base, jeton = carnet
    _appel(base + "/commande", {"reference": "CMD-1", "statut": "panier",
                                "placedAt": "2019-01-01T00:00:00+00:00"}, jeton)
    _, lu = _appel(base + "/commande/1", jeton=jeton)
    assert not lu["data"]["placedAt"].startswith("2019")


def test_la_modification_laisse_la_date_intacte(carnet):
    base, jeton = carnet
    _appel(base + "/commande", {"reference": "CMD-1", "statut": "panier"}, jeton)
    _, avant = _appel(base + "/commande/1", jeton=jeton)

    code, _ = _appel(base + "/commande/1",
                     {"reference": "CMD-1", "statut": "expediee",
                      "placedAt": "2019-01-01T00:00:00+00:00"}, jeton, methode="PUT")
    assert code == 200, "la brique ne doit pas casser la modification"
    _, apres = _appel(base + "/commande/1", jeton=jeton)
    assert apres["data"]["statut"] == "expediee", "le reste doit bien changer"
    assert apres["data"]["placedAt"] == avant["data"]["placedAt"]


def test_deux_commandes_coup_sur_coup_restent_ordonnables(carnet):
    """La raison de la milliseconde. À la seconde près, ces deux dates étaient
    IDENTIQUES — et le tri annoncé par le contrat devenait faux au premier coup
    de feu, c'est-à-dire exactement quand un carnet en a besoin."""
    base, jeton = carnet
    for i in range(2):
        _appel(base + "/commande", {"reference": f"CMD-{i}", "statut": "panier"}, jeton)
    _, liste = _appel(base + "/commande", jeton=jeton)
    dates = [c["placedAt"] for c in liste["data"]]
    assert dates[0] != dates[1], "deux créations rapprochées doivent se distinguer"
    # Trié comme du TEXTE : c'est la propriété que le contrat annonce, et elle
    # tient parce que le décalage est toujours '+00:00' et le format de largeur
    # fixe. Aucune conversion nécessaire côté navigateur.
    assert sorted(dates) == dates


def test_les_enregistrements_anterieurs_restent_sans_date_et_le_serveur_le_dit(tmp_path):
    """Le seul cas du compilateur où une colonne ajoutée ne peut pas être
    rattrapée. On compte, on nomme, on laisse à NULL — plutôt que de dater
    d'aujourd'hui des commandes d'avant-hier."""
    (tmp_path / "spec.ml").write_text(SANS_CHAMP, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    serveur = _Serveur(tmp_path)
    base = serveur.demarrer()
    _appel(base + "/register", {"username": "zoe", "password": "motdepasse1",
                                "actor": "Client"})
    _, jeton = _appel(base + "/login", {"username": "zoe", "password": "motdepasse1"})
    jeton = jeton["access_token"]
    for i in range(3):
        _appel(base + "/commande", {"reference": f"VIEILLE-{i}", "statut": "livree"}, jeton)
    serveur.arreter()

    # La règle arrive sur une base DÉJÀ peuplée.
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    serveur = _Serveur(tmp_path)
    base = serveur.demarrer()
    try:
        _, jeton = _appel(base + "/login", {"username": "zoe", "password": "motdepasse1"})
        jeton = jeton["access_token"]
        _appel(base + "/commande", {"reference": "NEUVE", "statut": "panier"}, jeton)
        _, liste = _appel(base + "/commande", jeton=jeton)
        par_reference = {c["reference"]: c["placedAt"] for c in liste["data"]}
    finally:
        serveur.arreter()

    assert par_reference["NEUVE"], "les nouvelles commandes sont datées"
    for i in range(3):
        assert par_reference[f"VIEILLE-{i}"] is None, (
            "une date inventée après coup serait fausse : le vide est la seule "
            "réponse honnête")
    assert "3 enregistrement(s)" in serveur.journal, (
        "le serveur doit NOMMER les enregistrements qui n'auront jamais de date")
