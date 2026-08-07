"""Brique 21 : un jeu de démonstration peut rattacher un enfant — point 100.

Pourquoi la brique. Le point 99 a rendu honnête la clé étrangère d'une entité
fille d'une table métier. Restait qu'une telle entité ne pouvait pas figurer
dans les données de démonstration : un `seed` n'accepte que des champs DÉCLARÉS,
et une colonne de rattachement n'en est pas un. Une boutique à variantes
s'ouvrait donc sur un catalogue dont rien n'était commandable — la couverture de
compilation sans le comportement, exactement ce que le point 95 dénonce.

    seed Variant for Product.name "Chaise Ligne"
        finish: "Chêne naturel", price: 249.90, stock: 12

Ce que la brique décide, et qui n'allait pas de soi :

* **désigner par une VALEUR, jamais par un rang.** Un numéro de ligne ne se lit
  pas et se décale dès qu'on insère une ligne au milieu. C'est déjà le choix de
  `monl assets add --for "Halo RS"` (point 84), et pour la même raison : c'est
  ce que l'humain a sous les yeux ;
* **une désignation ambiguë est REFUSÉE.** Deux lignes portant la valeur
  désignée donneraient une vitrine différente d'une compilation à l'autre, et
  personne ne le verrait avant de regarder l'écran ;
* **le rattachement se résout au DÉMARRAGE, par une lecture.** Un rang calculé à
  la compilation aurait supposé que le parent vient d'être semé. Or le socle ne
  sème une table que si elle est VIDE : sur une base où les produits existent
  déjà, le rang aurait désigné la mauvaise ligne. Le test qui le prouve est
  `test_le_rattachement_suit_lid_reel_pas_le_rang`.
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

SPEC = """app BancSemis

entity Produit
    nom: String
    categorie: String

entity Variante
    finition: String
    prix: Money
    stock: Integer

actor Patron selfRegister

relation Produit hasMany Variante

rule Produit.Read public
rule Variante.Read public
rule Variante.stock min 0

workflow Gerer for Patron
    Create Produit
    Read Produit
    Create Variante
    Read Variante

seed Produit
    nom: "Chaise Ligne", categorie: "Assises"
    nom: "Lampe Arc", categorie: "Luminaires"
    nom: "Table Onde", categorie: "Tables"

# Le parent visé est le TROISIÈME : si le rattachement se calculait par un rang
# dans le bloc enfant, il tomberait sur le premier produit et le test passerait
# pour de mauvaises raisons.
seed Variante for Produit.nom "Table Onde"
    finition: "Frêne ondé", prix: 1200.00, stock: 2
    finition: "Noyer massif", prix: 1450.00, stock: 1

seed Variante for Produit.nom "Chaise Ligne"
    finition: "Chêne naturel", prix: 249.90, stock: 12
"""


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation doit refuser
# --------------------------------------------------------------------------

def test_la_spec_du_banc_compile(capsys):
    """Le témoin des sept refus qui suivent."""
    ast = _valide(SPEC)
    blocs = [s for s in ast["seeds"] if s["entity"] == "Variante"]
    assert len(blocs) == 2
    assert blocs[0]["parent"] == {"entity": "Produit", "field": "nom",
                                 "value": "Table Onde"}
    capsys.readouterr()


def test_un_parent_qui_nest_pas_une_entite_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Fantome.nom "Table Onde"'))
    assert "n'est pas une entité déclarée" in str(refus.value)
    capsys.readouterr()


def test_un_parent_sans_relation_est_refuse(capsys):
    """Sans relation, aucune colonne ne porte le rattachement : l'écrire n'aurait
    nulle part où aller."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("relation Produit hasMany Variante\n", ""))
    assert "aucune relation ne les lie" in str(refus.value)
    capsys.readouterr()


def test_un_parent_acteur_est_refuse(capsys):
    """POINT 99 : la colonne d'un parent ACTEUR porte un identifiant de COMPTE.
    Un jeu de démonstration s'insère au démarrage, quand aucun compte n'existe
    encore — il n'a personne à désigner.

    Le parent visé est ici une entité qui est AUSSI un acteur (`Client`, comme
    le `Customer` de `projets/SneakerLab`) : c'est le seul cas où le refus est
    atteignable, un acteur sans entité homonyme tombant d'abord sur « n'est pas
    une entité déclarée »."""
    spec = SPEC.replace(
        "entity Variante",
        "entity Client\n    nom: String\n\nentity Variante")
    spec = spec.replace("actor Patron selfRegister",
                        "actor Patron selfRegister\nactor Client selfRegister")
    spec = spec.replace("relation Produit hasMany Variante",
                        "relation Produit hasMany Variante\n"
                        "relation Client hasMany Variante")
    spec = spec.replace('seed Variante for Produit.nom "Table Onde"',
                        'seed Variante for Client.nom "Zoe"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "identifiant de COMPTE" in str(refus.value)
    capsys.readouterr()


def test_un_champ_de_designation_inexistant_est_refuse(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Produit.fantome "Table Onde"'))
    assert "n'est pas un champ déclaré" in str(refus.value)
    capsys.readouterr()


def test_designer_par_un_nombre_est_refuse(capsys):
    """Rapprocher deux flottants est déjà douteux ; surtout, un prix ne NOMME
    rien. La désignation doit se lire."""
    spec = SPEC.replace("entity Produit\n    nom: String",
                        "entity Produit\n    poids: Float\n    nom: String")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec.replace('for Produit.nom "Table Onde"',
                             'for Produit.poids "3"'))
    assert "qui la NOMME" in str(refus.value)
    capsys.readouterr()


def test_un_parent_seme_apres_lenfant_est_refuse(capsys):
    """Les données sont insérées dans l'ordre des blocs. Un parent déclaré après
    son enfant ne serait pas en base au moment de rattacher — et la ligne serait
    écartée au démarrage, sans que la spec ait rien dit de faux."""
    lignes = SPEC.split("seed Produit")
    inverse = ("app BancSemis" + lignes[0].split("app BancSemis")[1]
               + "seed Variante for Produit.nom \"Table Onde\"\n"
                 "    finition: \"Frêne ondé\", prix: 1200.00, stock: 2\n\n"
                 "seed Produit\n"
                 "    nom: \"Table Onde\", categorie: \"Tables\"\n")
    with pytest.raises(ASTValidationError) as refus:
        _valide(inverse)
    assert "AVANT" in str(refus.value)
    capsys.readouterr()


def test_une_valeur_que_personne_ne_porte_est_refusee(capsys):
    """LA coquille que la brique doit attraper : sans ce refus, la vitrine
    serait amputée d'une rubrique entière et rien ne le dirait."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace('for Produit.nom "Table Onde"',
                             'for Produit.nom "Table Ondée"'))
    assert "qu'aucune ligne de 'seed Produit' ne porte" in str(refus.value)
    capsys.readouterr()


def test_une_designation_ambigue_est_refusee(capsys):
    """Deux lignes portant la valeur désignée : rien ne dit à laquelle. Deviner
    donnerait une vitrine différente d'une compilation à l'autre."""
    spec = SPEC.replace('    nom: "Lampe Arc", categorie: "Luminaires"',
                        '    nom: "Table Onde", categorie: "Luminaires"')
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "2 lignes" in str(refus.value)
    assert "valeurs sont distinctes" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# Ce que la génération doit écrire
# --------------------------------------------------------------------------

def test_le_socle_porte_la_designation_pas_un_rang(tmp_path, capsys):
    """La décision de conception, vérifiée dans le code produit : ce qui voyage
    jusqu'au serveur est la VALEUR, pas un identifiant calculé."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.startswith("_SEED_DATA"))
    assert "'column': 'produit_id'" in ligne
    assert "'field': 'nom'" in ligne
    assert "'value': 'Table Onde'" in ligne


def test_une_spec_sans_rattachement_seme_comme_avant(tmp_path, capsys):
    """Non-régression : la forme des données de démonstration a changé (chaque
    entrée est un couple), mais une spec qui n'emploie pas la brique doit semer
    exactement ce qu'elle semait."""
    spec = SPEC.split("# Le parent visé")[0]
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    genere = (tmp_path / "app.py").read_text(encoding="utf-8")
    ligne = next(li for li in genere.splitlines() if li.startswith("_SEED_DATA"))
    assert "'parent': None" in ligne
    assert "'nom': 'Chaise Ligne'" in ligne


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _appel(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        return err.code, {}


def _demarrer(dossier, port):
    """Démarre le serveur et rend (processus, journal-de-démarrage)."""
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


def _variantes(chemin_db):
    connexion = sqlite3.connect(str(chemin_db))
    try:
        return connexion.execute(
            'SELECT v.finition, p.nom FROM "variante" v '
            'LEFT JOIN "produit" p ON p.id = v."produit_id" '
            'ORDER BY v.id').fetchall()
    finally:
        connexion.close()


@pytest.fixture
def compile_banc(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    return tmp_path


def test_les_variantes_semees_sont_rattachees_au_bon_produit(compile_banc):
    """Le comportement que tout le reste sert. Lu en BASE par une jointure : la
    route de lecture rendrait la même chose quelle que soit la valeur écrite."""
    processus, base = _demarrer(compile_banc, _port_libre())
    try:
        code, catalogue = _appel(base + "/variante?limit=10")
        assert code == 200
        assert len(catalogue["data"]) == 3
    finally:
        _arreter(processus)
    assert _variantes(compile_banc / "app.db") == [
        ("Frêne ondé", "Table Onde"),
        ("Noyer massif", "Table Onde"),
        ("Chêne naturel", "Chaise Ligne"),
    ]


def test_le_semis_reste_idempotent(compile_banc):
    """Le socle ne sème que dans une table VIDE. Un redémarrage ne doit pas
    empiler les variantes — la brique ne doit pas défaire cette garantie."""
    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)
    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)
    assert len(_variantes(compile_banc / "app.db")) == 3


def test_le_rattachement_suit_lid_reel_pas_le_rang(compile_banc):
    """LE test qui départage les deux conceptions possibles.

    On peuple la table des produits AVANT le premier démarrage, avec des id qui
    ne correspondent à aucun rang de bloc : le socle n'y sèmera donc rien
    (table non vide), et « Table Onde » porte l'id 41. Un rattachement calculé à
    la compilation aurait écrit 3 — le rang de la ligne dans `seed Produit` —
    et les variantes auraient atterri sur un produit inexistant."""
    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    connexion.executescript((compile_banc / "schema.sql").read_text(encoding="utf-8"))
    connexion.execute('INSERT INTO "produit" (id, nom, categorie) VALUES (?,?,?)',
                      (17, "Chaise Ligne", "Assises"))
    connexion.execute('INSERT INTO "produit" (id, nom, categorie) VALUES (?,?,?)',
                      (41, "Table Onde", "Tables"))
    connexion.commit()
    connexion.close()

    processus, _ = _demarrer(compile_banc, _port_libre())
    _arreter(processus)

    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    try:
        liens = connexion.execute(
            'SELECT finition, "produit_id" FROM "variante" ORDER BY id').fetchall()
    finally:
        connexion.close()
    assert liens == [("Frêne ondé", 41), ("Noyer massif", 41),
                     ("Chêne naturel", 17)]


def test_un_parent_introuvable_au_demarrage_est_nomme(compile_banc):
    """Le seul chemin où la résolution échoue : une base dont la table parente
    est déjà peuplée AUTREMENT. La ligne est écartée — mais jamais en silence,
    sinon on chercherait la panne dans le frontend."""
    connexion = sqlite3.connect(str(compile_banc / "app.db"))
    connexion.executescript((compile_banc / "schema.sql").read_text(encoding="utf-8"))
    connexion.execute('INSERT INTO "produit" (nom, categorie) VALUES (?,?)',
                      ("Tabouret Pli", "Assises"))
    connexion.commit()
    connexion.close()

    processus, _ = _demarrer(compile_banc, _port_libre())
    journal = _arreter(processus)

    assert "Table Onde" in journal
    assert "ignorée" in journal
    # « Chaise Ligne » non plus n'existe pas : les trois lignes sont écartées,
    # et le serveur tourne quand même.
    assert _variantes(compile_banc / "app.db") == []
