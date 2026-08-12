"""Les quatre règles qui ne faisaient rien : required, unique, min, max — point 85.

Pourquoi ce fichier existe. `required`, `unique`, `min` et `max` sont les plus
ANCIENNES règles du compilateur, présentes avant toutes les briques. Elles
étaient acceptées par la grammaire, et **c'est tout**. Deux constats, tous deux
obtenus par exécution :

* une référence fantôme passait en silence. `rule Colis.champFantome required`
  compilait ; `rule Fantome.reference required` aussi. Toutes les briques
  ajoutées depuis (`hidden`, `generated`, `categorized`, `payable`,
  `derivedFrom`, `sumOf`) validaient leur référence — les quatre d'origine,
  jamais ;
* **la sortie était identique à l'octet** avec ou sans elles. Compilé deux fois
  le même projet, une fois avec `rule X.f required` et `rule X.g unique`, une
  fois sans : `diff` muet sur `app.py` ET sur `schema.sql`.

Le premier dépôt à en souffrir était le dépôt lui-même. `exemples/02_boutique.ml`
déclare `rule Product.price min 0` et `rule Product.stock min 0` ; le serveur
acceptait `price: -99, stock: -5` et les écrivait en base. Dans une boutique où
le prix se multiplie en sous-total (`derivedFrom`), se somme en total (`sumOf`)
et part chez le prestataire (`payable`), cette borne était la dernière chose
entre le catalogue et un montant négatif encaissé.

Ce que ce fichier garde, et dans cet ordre : les refus de référence (la moitié
« on ne promet pas ce qu'on n'applique pas »), puis le comportement contre un
vrai serveur (la moitié « on applique ce qu'on promet »). La couverture de
compilation seule n'aurait rien vu : elle n'a rien vu pendant toute la vie du
projet.
"""
import json
import os
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
from tests.support.server import free_port as _port_libre

SPEC = """app BancContraintes

entity Membre
    pseudo: String
    courriel: Email
    age: Integer

actor Visiteur selfRegister

rule Membre.pseudo unique
rule Membre.pseudo min 3
rule Membre.age min 18
rule Membre.age max 120
rule Membre.Read public

workflow Gerer for Visiteur
    Create Membre
    Read Membre
    Update Membre
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


def _sans_contraintes(spec):
    """La même spec, privée de ses quatre règles de contrainte."""
    return "\n".join(li for li in spec.splitlines()
                     if not any(li.strip().endswith(f" {mot}")
                                or f" {mot} " in li for mot in
                                ("unique", "required", "min", "max"))) + "\n"


# --------------------------------------------------------------------------
# Ce qui ne doit plus compiler : une contrainte qui ne s'applique à rien
# --------------------------------------------------------------------------

def test_une_spec_bien_formee_compile(capsys):
    """Le témoin de tous les refus : sans lui, un validateur qui refuserait
    TOUTE contrainte les passerait tous."""
    ast = _valide(SPEC)
    contraintes = ast["security"]["field_constraints"]
    assert contraintes[("Membre", "pseudo")]["unique"] is True
    assert contraintes[("Membre", "pseudo")]["min"] == {"portee": "longueur", "valeur": 3}
    assert contraintes[("Membre", "age")]["min"] == {"portee": "valeur", "valeur": 18}
    capsys.readouterr()


@pytest.mark.parametrize("regle", [
    "rule Membre.champFantome required",
    "rule Membre.champFantome unique",
    "rule Membre.champFantome min 2",
    "rule Membre.champFantome max 9",
])
def test_un_champ_inexistant_est_refuse(regle, capsys):
    """LE défaut du point 85 : ces quatre lignes compilaient sans un mot.
    L'auteur croit tenir une contrainte, il n'en a aucune, et rien ne le dit."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + regle + "\n")
    message = str(refus.value)
    assert "champFantome" in message
    assert "ne déclare pas" in message
    # Le message doit dire POURQUOI le refus est là, pas seulement refuser.
    assert "ne s'applique à rien" in message
    capsys.readouterr()


def test_une_entite_inexistante_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Fantome.pseudo required\n")
    assert "'Fantome'" in str(refus.value) and "n'existe pas" in str(refus.value)
    capsys.readouterr()


def test_une_faute_de_casse_est_suggeree(capsys):
    """La faute la plus probable est une faute de frappe : le refus doit
    proposer le champ voisin plutôt que laisser chercher."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.Pseudo required\n")
    assert "Peut-être 'pseudo'" in str(refus.value)
    capsys.readouterr()


def test_une_borne_sur_un_type_qui_ne_se_borne_pas_est_refusee(capsys):
    spec = SPEC.replace("    age: Integer", "    age: Integer\n    actif: Boolean")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec + "rule Membre.actif min 1\n")
    assert "Boolean" in str(refus.value)
    capsys.readouterr()


def test_un_max_au_dela_de_la_colonne_est_refuse(capsys):
    """La contrainte promettrait une donnée que la base ne peut pas tenir :
    String est une colonne VARCHAR(255)."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.pseudo max 400\n")
    assert "255" in str(refus.value)
    capsys.readouterr()


def test_des_bornes_contradictoires_sont_refusees(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.courriel min 40\nrule Membre.courriel max 10\n")
    assert "aucune valeur ne satisfait" in str(refus.value)
    capsys.readouterr()


def test_une_borne_sur_un_champ_calcule_par_le_serveur_est_refusee(capsys):
    """Une borne vit dans le schéma Pydantic, donc dans le corps de requête. Sur
    un champ que le serveur peuple, ce champ n'y est PAS : la borne ne
    s'appliquerait à rien — c'est-à-dire la faute même que le point 85 corrige."""
    spec = """app BancSomme

entity Ligne
    quantite: Integer

entity Panier
    total: Integer

entity Client
    nom: String

relation Client hasMany Panier
relation Panier hasMany Ligne
# Porte la colonne de propriété de la fiche client elle-même : sans elle,
# 'Client.Read ownedBy Client' est refusé AVANT la borne qu'on veut éprouver.
relation Client hasMany Client

# Acteur HOMONYME de l'entité propriétaire : 'ownedBy Client' doit remonter à un
# compte. Nommer l'acteur autrement fait tomber sur le refus de chaîne du
# point 81, et le test n'éprouverait plus ce qu'il annonce.
actor Client selfRegister

rule Ligne.quantite required
rule Panier.Read ownedBy Client
rule Panier.Update ownedBy Client
rule Client.Read ownedBy Client
rule Ligne.Read ownedBy Panier
rule Panier.total sumOf Ligne.quantite
rule Panier.total min 0

workflow Acheter for Client
    Create Panier
    Read Panier
    Update Panier
    Create Ligne
    Read Ligne
    Create Client
    Read Client
"""
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "le SERVEUR calcule ce champ" in str(refus.value)
    capsys.readouterr()


def test_la_meme_contrainte_deux_fois_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Membre.pseudo unique\n")
    assert "deux fois" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération doit produire — et ne produisait pas
# --------------------------------------------------------------------------

def test_les_contraintes_changent_la_sortie(tmp_path, capsys):
    """Le constat qui a ouvert le point 85, retourné en garde : compiler avec
    et sans les quatre règles donnait un `diff` MUET sur app.py et schema.sql.
    Ce test échoue le jour où l'une d'elles redevient décorative."""
    avec, sans = tmp_path / "avec", tmp_path / "sans"
    for dossier, spec in ((avec, SPEC), (sans, _sans_contraintes(SPEC))):
        dossier.mkdir()
        (dossier / "spec.ml").write_text(spec, encoding="utf-8")
        compile_project(str(dossier / "spec.ml"), str(dossier))
    capsys.readouterr()

    app_avec = (avec / "app.py").read_text(encoding="utf-8")
    app_sans = (sans / "app.py").read_text(encoding="utf-8")
    assert app_avec != app_sans
    assert "min_length=3" in app_avec and "min_length=3" not in app_sans
    assert "ge=18" in app_avec and "le=120" in app_avec
    assert "idx_unique_membre_pseudo" in app_avec
    assert "idx_unique_membre_pseudo" not in app_sans


def test_le_contrat_annonce_les_contraintes(tmp_path, capsys):
    """Une interface qui ignore les bornes laisse remplir un formulaire pour se
    faire refuser au bout, alors qu'elle pouvait le dire tout de suite. Même
    raison que pour `server_generated` au point 79 : le contrat décrit ce que le
    backend fait vraiment, y compris ce qu'il REFUSE."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    contrat = json.loads((tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    champs = {f["name"]: f for f in contrat["entities"]["Membre"]["fields"]}
    assert champs["pseudo"]["min_length"] == 3
    assert champs["pseudo"]["unique"] is True
    assert "409" in champs["pseudo"]["unique_note"]
    assert champs["age"]["min_value"] == 18
    assert champs["age"]["max_value"] == 120


def test_les_blocs_custom_nappellent_plus_une_methode_depreciee(tmp_path, capsys):
    """`payload.dict()` est déprécié en Pydantic v2 et RETIRÉ en v3 : tout
    backend portant un bloc 'custom' aurait cessé de fonctionner à la première
    installation sur Pydantic 3. Aucun exemple, aucun test n'exerçait ce
    chemin — c'est le trou de couverture de schemas.py qui l'a fait trouver."""
    spec = """app BancCustom

entity Colis
    reference: String

actor Client selfRegister

rule Colis.Read public

custom Estimer
    description: "Estime un délai"
    input: poids: Float, destination: String
    output: jours: Integer

workflow Suivre for Client
    Read Colis
    Execute Estimer
"""
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    assert "payload.model_dump()" in genere
    assert ".dict()" not in genere


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
        try:
            brut = err.read()
            return err.code, json.loads(brut or b"{}")
        except ValueError:
            return err.code, {"brut": brut[:200].decode("utf-8", "replace")}
        finally:
            err.close()


@pytest.fixture
def serveur(tmp_path):
    """Un vrai serveur éphémère sur la spec du banc."""
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
                sortie = processus.stdout.read().decode("utf-8", "replace")
                pytest.fail(f"le serveur s'est arrêté :\n{sortie[-2000:]}")
            try:
                # /docs renvoie du HTML : sonder avec _appel (qui décode du
                # JSON) ferait passer un serveur PRÊT pour un serveur muet.
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        _appel(base + "/register", {"username": "v", "password": "motdepasse1",
                                    "actor": "Visiteur"})
        _, corps = _appel(base + "/login", {"username": "v",
                                            "password": "motdepasse1"})
        yield base, corps["access_token"], tmp_path
    finally:
        processus.terminate()
        try:
            processus.wait(timeout=10)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait(timeout=5)
        if processus.stdout is not None:
            processus.stdout.close()


def test_unique_refuse_un_doublon_a_la_creation(serveur):
    """Avant le point 85 : les deux POST répondaient 200 et la base portait
    deux lignes. Vérifié, pas supposé."""
    base, jeton, dossier = serveur
    membre = {"pseudo": "zoe", "courriel": "z@x.fr", "age": 30}
    code1, _ = _appel(base + "/membre", membre, jeton)
    code2, corps2 = _appel(base + "/membre", membre, jeton)
    assert code1 == 200
    assert code2 == 409
    # Le message doit nommer la CAUSE : le même 409 servait déjà aux clés
    # étrangères, et « référence invalide » enverrait chercher ailleurs.
    assert "unique" in corps2["detail"] and "pseudo" in corps2["detail"]

    base_donnees = sqlite3.connect(dossier / "app.db")
    try:
        lignes = base_donnees.execute(
            "SELECT COUNT(*) FROM membre WHERE pseudo = 'zoe'").fetchone()[0]
    finally:
        base_donnees.close()
    assert lignes == 1, "l'unicité doit tenir EN BASE, pas seulement dans la réponse"


def test_unique_refuse_un_doublon_a_la_modification(serveur):
    """La route Update n'écrivait aucune clé étrangère, donc elle n'avait aucune
    garde : le premier essai de cette brique donnait 500 et laissait la
    connexion ouverte. SQLite lève à l'`execute`, pas au `commit`."""
    base, jeton, _ = serveur
    _appel(base + "/membre", {"pseudo": "zoe", "courriel": "z@x.fr", "age": 30}, jeton)
    _appel(base + "/membre", {"pseudo": "autre", "courriel": "b@x.fr", "age": 40}, jeton)

    code, corps = _appel(base + "/membre/1",
                         {"pseudo": "autre", "courriel": "z@x.fr", "age": 30},
                         jeton, methode="PUT")
    assert code == 409, f"500 = la garde manque ou entoure le mauvais appel ({corps})"
    # Témoin : une modification légitime passe toujours.
    code_ok, _ = _appel(base + "/membre/1",
                        {"pseudo": "zoe2", "courriel": "z@x.fr", "age": 31},
                        jeton, methode="PUT")
    assert code_ok == 200


@pytest.mark.parametrize("corps, champ", [
    ({"pseudo": "ab", "courriel": "a@x.fr", "age": 30}, "pseudo"),   # min 3
    ({"pseudo": "abc", "courriel": "a@x.fr", "age": 17}, "age"),     # min 18
    ({"pseudo": "abd", "courriel": "a@x.fr", "age": 130}, "age"),    # max 120
])
def test_les_bornes_donnent_un_422_avant_tout_insert(serveur, corps, champ):
    base, jeton, dossier = serveur
    code, reponse = _appel(base + "/membre", corps, jeton)
    assert code == 422
    assert any(champ in str(e.get("loc", "")) for e in reponse["detail"])
    base_donnees = sqlite3.connect(dossier / "app.db")
    try:
        assert base_donnees.execute("SELECT COUNT(*) FROM membre").fetchone()[0] == 0
    finally:
        base_donnees.close()


def test_une_valeur_dans_les_bornes_passe(serveur):
    """Le témoin des trois refus ci-dessus."""
    base, jeton, _ = serveur
    code, _ = _appel(base + "/membre",
                     {"pseudo": "zoe", "courriel": "z@x.fr", "age": 18}, jeton)
    assert code == 200


def test_une_base_avec_doublons_le_dit_au_lieu_de_le_taire(tmp_path, capsys):
    """Un index unique ne peut PAS naître sur des données déjà en doublon. C'est
    un changement non automatisable (docs/MIGRATIONS.md) : le serveur doit le
    NOMMER au démarrage, et continuer de tourner — pas avaler l'erreur dans le
    « ℹ️ DB déjà initialisée » qui masquerait tout le reste du script."""
    (tmp_path / "spec.ml").write_text(_sans_contraintes(SPEC), encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    # Une base peuplée AVANT que 'unique' n'existe dans la spec.
    base_donnees = sqlite3.connect(tmp_path / "app.db")
    try:
        with base_donnees:
            base_donnees.executescript(
                (tmp_path / "schema.sql").read_text(encoding="utf-8"))
            base_donnees.executemany(
                'INSERT INTO membre ("pseudo", "courriel", "age") VALUES (?, ?, ?)',
                [("zoe", "a@x.fr", 30), ("zoe", "b@x.fr", 40)])
    finally:
        base_donnees.close()

    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    sortie = subprocess.run(
        [sys.executable, "-c", "import app; app.init_db()"],
        cwd=str(tmp_path), capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(tmp_path)}, timeout=60)
    trace = sortie.stdout + sortie.stderr
    assert "pseudo" in trace and "double" in trace, trace[-1500:]
    assert sortie.returncode == 0, "le serveur doit continuer de démarrer"
