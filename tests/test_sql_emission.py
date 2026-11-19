"""The typed SQL emission layer (point 108), and the point 107 regression
safeguard.

What these tests require, and what a review does not prove:
* a value only enters a query bound (sql.bind → '?' + parameter); there is
  no API to paste it into the text;
* an identifier carrying a quote is refused, not silently escaped;
* the number of '?' of an emitted query always equals the number of
  parameters;
* and — the heart — the generator NEVER again produces point 107's pattern, a
  client value pasted into the SQL text of an access check.
"""

import pytest

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator, sql
from monl.parser import parse_monl_string

# -----------------------------------------------------------------------------
# The layer's invariant: a value never crosses the text
# -----------------------------------------------------------------------------

def test_bind_sort_un_placeholder_et_retient_l_expression():
    q = sql.bind("data.commande_id")
    assert q.text == "?"
    assert q.params == ("data.commande_id",)


def test_bind_refuses_an_empty_expression():
    with pytest.raises(ValueError):
        sql.bind("   ")


def test_ident_met_entre_guillemets():
    assert sql.ident("commande_id").text == '"commande_id"'
    assert sql.ident("commande_id").params == ()


def test_ident_refuse_un_guillemet_interne():
    # A validated entity/column never carries one; guessing the escaping would
    # hide a divergence upstream.
    with pytest.raises(ValueError):
        sql.ident('col"; DROP TABLE users; --')


def test_kw_refuse_un_placeholder():
    # A '?' is only written with bind() — otherwise a value could slip into a
    # fragment deemed "fixed".
    with pytest.raises(ValueError):
        sql.kw("WHERE id = ?")


def test_cat_concatenates_text_and_params_in_order():
    q = sql.cat(sql.kw("SELECT "), sql.ident("a"), sql.kw(" WHERE x = "),
                sql.bind("v1"), sql.kw(" AND y = "), sql.bind("v2"))
    assert q.text == 'SELECT "a" WHERE x = ? AND y = ?'
    assert q.params == ("v1", "v2")


def test_execute_args_returns_the_text_params_pair():
    q = sql.cat(sql.kw("id = "), sql.bind("current_user_id"))
    lit, params = sql.execute_args(q, prefix="SELECT * FROM t WHERE ")
    assert lit == repr("SELECT * FROM t WHERE id = ?")
    assert params == "(current_user_id, )"


def test_params_empty_tuple_when_no_parameter():
    assert sql.params_tuple(sql.kw("SELECT 1")) == "()"


def test_an_unbalanced_query_is_refused_at_emission():
    # We force the issue to simulate a badly written builder: two '?' for a
    # single parameter. Emission must refuse rather than produce an execute
    # that would crash at runtime.
    faux = sql.Sql("? = ?", ("current_user_id",))
    with pytest.raises(ValueError):
        sql.params_tuple(faux)


# -----------------------------------------------------------------------------
# The point 107 regression safeguard: on REALLY generated code
# -----------------------------------------------------------------------------

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


def test_no_client_value_is_pasted_into_sql_text(app_source):
    """THE point 107 defect, forbidden at the source. A foreign key provided by
    the client (data.<fk>) or read from the row (named_row.get) must NEVER appear
    inside a SQL comparison: its place is the parameter tuple."""
    for motif in ('id = (data.', 'id = data.',
                  'id = (named_row', 'id = named_row',
                  '= (data.', "WHERE id = (named_row"):
        assert motif not in app_source, (
            f"valeur client collée dans le texte SQL : {motif!r} (point 107)")


def test_transitive_checks_bind_their_value(app_source):
    """Counter-proof of the previous test: the values ARE there, but in
    cursor.execute's parameter tuple, facing a '?'."""
    # Creation: the parent designated by the client, bound.
    assert "(?))', (data.commande_id, ))" in app_source or \
           "(?))', (data.bloc_id, ))" in app_source
    # Detail: the link read from the row, bound.
    assert "named_row.get('commande_id')" in app_source
    # Update/Delete: the row id, bound.
    assert "= ?))))', (id, ))" in app_source or "= ?))', (id, ))" in app_source
