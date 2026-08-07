"""La couche d'émission SQL typée (point 108), et le garde-fou de régression
du point 107.

Ce que ces tests exigent, et qu'une relecture ne prouve pas :
* une valeur n'entre dans une requête que liée (sql.bind → '?' + paramètre) ;
  il n'existe aucune API pour la coller dans le texte ;
* un identifiant portant un guillemet est refusé, pas échappé en silence ;
* le nombre de '?' d'une requête émise égale toujours le nombre de paramètres ;
* et — le cœur — le générateur ne produit PLUS jamais le motif du point 107,
  une valeur client collée dans le texte SQL d'un contrôle d'accès.
"""

import pytest

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator, sql
from monl.parser import parse_monl_string

# ---------------------------------------------------------------------------
# L'invariant de la couche : une valeur ne traverse jamais le texte
# ---------------------------------------------------------------------------

def test_bind_sort_un_placeholder_et_retient_l_expression():
    q = sql.bind("data.commande_id")
    assert q.text == "?"
    assert q.params == ("data.commande_id",)


def test_bind_refuse_une_expression_vide():
    with pytest.raises(ValueError):
        sql.bind("   ")


def test_ident_met_entre_guillemets():
    assert sql.ident("commande_id").text == '"commande_id"'
    assert sql.ident("commande_id").params == ()


def test_ident_refuse_un_guillemet_interne():
    # Une entité/colonne validée n'en porte jamais ; deviner l'échappement
    # masquerait une divergence en amont.
    with pytest.raises(ValueError):
        sql.ident('col"; DROP TABLE users; --')


def test_kw_refuse_un_placeholder():
    # Un '?' ne s'écrit qu'avec bind() — sinon une valeur pourrait se glisser
    # dans un fragment réputé « fixe ».
    with pytest.raises(ValueError):
        sql.kw("WHERE id = ?")


def test_cat_concatene_texte_et_params_dans_l_ordre():
    q = sql.cat(sql.kw("SELECT "), sql.ident("a"), sql.kw(" WHERE x = "),
                sql.bind("v1"), sql.kw(" AND y = "), sql.bind("v2"))
    assert q.text == 'SELECT "a" WHERE x = ? AND y = ?'
    assert q.params == ("v1", "v2")


def test_execute_args_rend_le_couple_texte_params():
    q = sql.cat(sql.kw("id = "), sql.bind("current_user_id"))
    lit, params = sql.execute_args(q, prefix="SELECT * FROM t WHERE ")
    assert lit == repr("SELECT * FROM t WHERE id = ?")
    assert params == "(current_user_id, )"


def test_params_tuple_vide_quand_aucun_parametre():
    assert sql.params_tuple(sql.kw("SELECT 1")) == "()"


def test_une_requete_desequilibree_est_refusee_a_l_emission():
    # On force la main pour simuler un builder mal écrit : deux '?' pour un
    # seul paramètre. L'émission doit refuser plutôt que produire un execute
    # qui planterait à l'exécution.
    faux = sql.Sql("? = ?", ("current_user_id",))
    with pytest.raises(ValueError):
        sql.params_tuple(faux)


# ---------------------------------------------------------------------------
# Le garde-fou de régression du point 107 : sur du code RÉELLEMENT généré
# ---------------------------------------------------------------------------

SPEC_PROFONDEUR = """app G

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
rule Bloc.Update ownedBy Commande
rule Bloc.Delete ownedBy Commande
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


@pytest.fixture(scope="module")
def app_source(tmp_path_factory):
    dossier = tmp_path_factory.mktemp("g")
    ast = MonlAST(parse_monl_string(SPEC_PROFONDEUR)).validate_and_audit()
    MonlSecureGenerator(ast, output_dir=str(dossier)).generate_all()
    return (dossier / "app.py").read_text(encoding="utf-8")


def test_aucune_valeur_client_n_est_collee_dans_le_texte_sql(app_source):
    """LE défaut du point 107, interdit à la source. Une clé étrangère fournie
    par le client (data.<fk>) ou lue sur la ligne (named_row.get) ne doit
    JAMAIS apparaître à l'intérieur d'une comparaison SQL : sa place est le
    tuple de paramètres."""
    for motif in ('id = (data.', 'id = data.',
                  'id = (named_row', 'id = named_row',
                  '= (data.', "WHERE id = (named_row"):
        assert motif not in app_source, (
            f"valeur client collée dans le texte SQL : {motif!r} (point 107)")


def test_les_controles_transitifs_lient_leur_valeur(app_source):
    """Contre-épreuve du test précédent : les valeurs SONT bien là, mais dans
    le tuple de paramètres de cursor.execute, en regard d'un '?'."""
    # Création : le parent désigné par le client, lié.
    assert "(?))', (data.commande_id, ))" in app_source or \
           "(?))', (data.bloc_id, ))" in app_source
    # Détail : le maillon lu sur la ligne, lié.
    assert "named_row.get('commande_id')" in app_source
    # Update/Delete : l'id de la ligne, lié.
    assert "= ?))))', (id, ))" in app_source or "= ?))', (id, ))" in app_source
