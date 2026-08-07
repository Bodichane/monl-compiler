"""Invariant de sécurité à l'échelle du projet : sur le code RÉELLEMENT généré,
aucune valeur client ou d'exécution ne vit dans le texte d'une requête SQL.

Le point 107 (brique 24) a livré un contrôle d'accès qui collait `data.<fk>`
dans le texte SQL — 500 à chaque création. Le point 108 a rendu le défaut
difficile à écrire (émission typée) ; ce test le rend inexpédiable, et pas
seulement sur l'exemple qui l'avait révélé : il compile CHAQUE spec du dépôt et
vérifie l'invariant sur chacune.

La méthode est en AST, pas en sous-chaîne : on ne regarde QUE les littéraux de
chaîne qui sont du SQL. Un `x = data.y` en Python n'est pas un littéral de
chaîne, donc jamais un faux positif — seul un `'... = data.y ...'` DANS une
requête est fautif. C'est exactement la forme du défaut du point 107.

Ce que le générateur doit toujours faire à la place : `... WHERE col = ?` avec
la valeur dans le tuple passé à `cursor.execute`. Une valeur liée ne laisse
aucune trace dans le texte.
"""

import ast
import glob
import os
import tempfile

import pytest

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file, parse_monl_string

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")

# Expressions Python (valeur client ou d'exécution) qui doivent TOUJOURS être
# liées en paramètre, donc ne jamais apparaître dans le texte d'une requête.
INTERDITS_EN_SQL = ("data.", "named_row", "current_user_id")

# Un littéral est « du SQL » dès qu'il porte un de ces jalons — assez pour
# attraper toute requête de lecture, d'écriture ou de contrôle d'accès.
JALONS_SQL = ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", " FROM ", " WHERE ")


def _litteraux_sql(source):
    """Tous les littéraux de chaîne du module qui sont du SQL, via l'AST."""
    arbre = ast.parse(source)
    for noeud in ast.walk(arbre):
        if isinstance(noeud, ast.Constant) and isinstance(noeud.value, str):
            texte = noeud.value
            if any(jalon in texte for jalon in JALONS_SQL):
                yield texte


def _app_source(spec_ou_chemin, depuis_fichier, base_dir):
    raw = (parse_monl_file(spec_ou_chemin) if depuis_fichier
           else parse_monl_string(spec_ou_chemin))
    ast_manager = MonlAST(raw, base_dir=base_dir)
    normalized = ast_manager.validate_and_audit()
    with tempfile.TemporaryDirectory() as sortie:
        MonlSecureGenerator(normalized, output_dir=sortie).generate_all()
        return open(os.path.join(sortie, "app.py"), encoding="utf-8").read()


# Une spec taillée pour exercer TOUTE la surface du contrôle d'accès transitif
# (profondeur 2 : liste, détail, création, Update, Delete), là où le point 107
# vivait. Les exemples couvrent la profondeur 1 (02_boutique) ; celle-ci garantit
# que la profondeur 2 est éprouvée par l'invariant elle aussi.
SPEC_PROFONDEUR = """app Inv

entity Commande
    libelle: String

entity Bloc
    note: String

entity Ligne
    quantite: Integer

relation Client hasMany Commande
relation Commande hasMany Bloc
relation Bloc hasMany Ligne

actor Client selfRegister

rule Commande.Read ownedBy Client
rule Bloc.Read ownedBy Commande
rule Ligne.Read ownedBy Bloc
rule Ligne.Update ownedBy Bloc
rule Ligne.Delete ownedBy Bloc

workflow W for Client
    Create Commande
    Read Commande
    Create Bloc
    Read Bloc
    Create Ligne
    Read Ligne
    Update Ligne
    Delete Ligne
"""

EXEMPLES = sorted(glob.glob(os.path.join(EXEMPLES_DIR, "*.ml")))


@pytest.mark.parametrize("chemin", EXEMPLES,
                         ids=[os.path.basename(p) for p in EXEMPLES])
def test_aucun_exemple_ne_colle_de_valeur_dans_le_sql(chemin):
    source = _app_source(chemin, depuis_fichier=True, base_dir=EXEMPLES_DIR)
    for requete in _litteraux_sql(source):
        for interdit in INTERDITS_EN_SQL:
            assert interdit not in requete, (
                f"{os.path.basename(chemin)} : valeur '{interdit}' collée dans "
                f"le texte SQL (point 107) — {requete!r}")


def test_la_profondeur_2_ne_colle_aucune_valeur_dans_le_sql():
    source = _app_source(SPEC_PROFONDEUR, depuis_fichier=False, base_dir=None)
    for requete in _litteraux_sql(source):
        for interdit in INTERDITS_EN_SQL:
            assert interdit not in requete, (
                f"profondeur 2 : valeur '{interdit}' collée dans le texte SQL "
                f"(point 107) — {requete!r}")


def test_l_invariant_voit_vraiment_du_controle_dacces():
    """Garde-fou du garde-fou : un invariant qui ne scrute aucune requête de
    contrôle d'accès passerait toujours, et ne dirait plus rien. La spec
    profondeur DOIT produire des requêtes de contrôle d'accès (jointure de
    propriété), et elles DOIVENT lier leurs valeurs (`= ?`)."""
    requetes = list(_litteraux_sql(
        _app_source(SPEC_PROFONDEUR, depuis_fichier=False, base_dir=None)))
    controle = [r for r in requetes if "IN (SELECT id FROM" in r or
                ('WHERE id = ' in r and "SELECT" in r)]
    assert controle, "aucune requête de contrôle d'accès générée — invariant aveugle"
    assert any("= ?" in r for r in controle), \
        "le contrôle d'accès ne lie aucune valeur — régression du point 107"
