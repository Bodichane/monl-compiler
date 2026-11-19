"""Performance invariant on the generated read filters.

Every spec of the repository is compiled then probed on the produced Python
code. List queries often build their ``WHERE`` in a fragment separate from
the ``FROM``; the witness therefore collects SQL literals per fragment, in
the relevant route function, instead of looking for a complete query in a
single string.

The column scope is derived from ``_EXPECTED_COLUMNS`` produced by
compilation. It only holds business tables and so excludes ``id`` without a
hand-written exception list. The covered indexes are also read from the
generated runtime's constants, so that the witness really checks the
contract between the queries and the indexes startup will create.
"""

import ast
import contextlib
import glob
import io
import os
import re
import tempfile

import pytest

from monl.ast_validator import MonlAST
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file
from tests.support.cas import verifier_chaque_cas

EXEMPLES_DIR = os.path.join(os.path.dirname(__file__), "../exemples")
PROJETS_DIR = os.path.join(os.path.dirname(__file__), "../projets")
SPEC_FILES = sorted(
    glob.glob(os.path.join(EXEMPLES_DIR, "*.ml"))
    + glob.glob(os.path.join(PROJETS_DIR, "*/spec.ml"))
)

_SQL_TABLE = re.compile(r'\bFROM\s+["`]?([A-Za-z_]\w*)["`]?', re.IGNORECASE)
_LIST_TABLE = re.compile(
    r'\bSELECT\s+(?:COUNT\(\*\)|\*)\s+FROM\s+["`]?([A-Za-z_]\w*)',
    re.IGNORECASE)
_SQL_WHERE = re.compile(r'\bWHERE\b', re.IGNORECASE)
_SQL_CONDITION = re.compile(
    r'(?P<column>["`]?[A-Za-z_]\w*["`]?)\s*'
    r'(?:=|<>|!=|<=|>=|<|>|IS\b|IN\b)')

# The social network must provide a real witness: status, member_id and both
# parties of PrivateMessage are all present in its list fragments.
SPEC_TEMOIN = os.path.join(EXEMPLES_DIR, "03_reseau_social.ml")
MIN_COLONNES_TEMOIN = 4


def _condition_column(match):
    return match.group("column").strip('"`')


def _literal_assignments(source):
    tree = ast.parse(source)
    wanted = {
        "_EXPECTED_COLUMNS", "_LOOKUP_INDEXES", "_UNIQUE_INDEXES",
        "_ONCE_PER_INDEXES",
    }
    assignments = {}
    for node in tree.body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id in wanted):
            assignments[node.targets[0].id] = ast.literal_eval(node.value)
    missing = wanted - assignments.keys()
    assert not missing, f"constantes d'index absentes du code généré : {sorted(missing)}"
    return assignments, tree


def _route_sql_fragments(function):
    """Returns the literals that make up this list route's SQL."""
    return [
        node.value
        for node in ast.walk(function)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and ("WHERE" in node.value.upper()
             or " AND " in node.value.upper()
             or " OR " in node.value.upper()
             or _SQL_CONDITION.search(node.value))
    ]


def _columns_in_fragment(fragment, default_table):
    """Extracts table/column pairs from WHERE/AND/OR fragments.

    A transitive ownership fragment can contain a nested ``FROM``. The last
    ``FROM`` before each ``WHERE`` then gives the subquery's table; without a
    ``FROM`` the fragment belongs to the list route's table.
    """
    table_markers = list(_SQL_TABLE.finditer(fragment))
    where_markers = list(_SQL_WHERE.finditer(fragment))
    if where_markers:
        columns = []
        for index, where in enumerate(where_markers):
            previous_tables = [marker for marker in table_markers
                               if marker.start() < where.start()]
            table = (previous_tables[-1].group(1).lower()
                     if previous_tables else default_table)
            end = (where_markers[index + 1].start()
                   if index + 1 < len(where_markers) else len(fragment))
            columns.extend((table, _condition_column(match))
                           for match in _SQL_CONDITION.finditer(
                               fragment[where.end():end]))
        return columns
    return [
        (default_table, _condition_column(match))
        for match in _SQL_CONDITION.finditer(fragment)
    ]


def _filtered_columns(source):
    """Returns the columns filtered by the list routes of ``source``."""
    assignments, tree = _literal_assignments(source)
    business_columns = {
        table: {column for column, _sql_type in columns}
        for table, columns in assignments["_EXPECTED_COLUMNS"].items()
    }
    found = set()
    list_routes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("list_")
    ]
    assert list_routes, "aucune route de liste trouvée dans le code généré"
    for function in list_routes:
        tables = {
            match.group(1).lower()
            for fragment in (
                node.value
                for node in ast.walk(function)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
            )
            for match in _LIST_TABLE.finditer(fragment)
        }
        route_tables = tables & business_columns.keys()
        if not route_tables:
            continue
        assert len(route_tables) == 1, (
            f"plusieurs tables métier dans la route {function.name}: "
            f"{sorted(route_tables)}")
        table = next(iter(route_tables))
        for fragment in _route_sql_fragments(function):
            for fragment_table, column in _columns_in_fragment(fragment, table):
                if column in business_columns.get(fragment_table, set()):
                    found.add((fragment_table, column))
    return found, assignments


def _indexed_columns(assignments):
    indexed = set()
    indexed.update(
        (table, column)
        for table, column, _index in assignments["_LOOKUP_INDEXES"]
    )
    indexed.update(
        (table, column)
        for table, column, _index in assignments["_UNIQUE_INDEXES"]
    )
    indexed.update(
        (table, column)
        for table, columns, _index in assignments["_ONCE_PER_INDEXES"]
        for column in columns
    )
    return indexed


def _compile_source(path):
    raw = parse_monl_file(path)
    ast_manager = MonlAST(raw, base_dir=os.path.dirname(path))
    with tempfile.TemporaryDirectory() as output:
        # Audit messages are not part of the proof; compiling them all into
        # throwaway folders keeps the test deterministic and clean.
        with contextlib.redirect_stdout(io.StringIO()):
            normalized = ast_manager.validate_and_audit()
            MonlSecureGenerator(normalized, output_dir=output).generate_all()
        with open(os.path.join(output, "app.py"), encoding="utf-8") as app:
            return app.read()


def _assert_performance_invariant(path, *, minimum_witness=None):
    source = _compile_source(path)
    found, assignments = _filtered_columns(source)
    if minimum_witness is not None:
        assert found, (
            f"aucune colonne filtrée trouvée dans {os.path.basename(path)}")
        assert len(found) >= minimum_witness, (
            f"le témoin ne voit que {len(found)} colonne(s) filtrée(s) dans "
            f"{os.path.basename(path)} ; minimum attendu : {minimum_witness}")
    missing = sorted(found - _indexed_columns(assignments))
    assert not missing, (
        f"{os.path.basename(path)} : colonnes métier filtrées sans index : "
        f"{missing}")
    return found


def test_every_business_column_filtering_a_list_is_indexed():
    table = SPEC_FILES
    noms = [os.path.relpath(path) for path in SPEC_FILES]

    def cas(path):
        minimum = MIN_COLONNES_TEMOIN if path == SPEC_TEMOIN else None
        _assert_performance_invariant(path, minimum_witness=minimum)

    verifier_chaque_cas([(valeur,) for valeur in table], cas, ids=noms)


def test_the_witness_sees_the_four_social_network_filters():
    found = _assert_performance_invariant(
        SPEC_TEMOIN, minimum_witness=MIN_COLONNES_TEMOIN)
    assert {("post", "status"), ("post", "member_id"),
            ("privatemessage", "member_id"),
            ("privatemessage", "recipient_id")} <= found


def _without_source(*, access=False, public=False):
    original = MonlSecureGenerator._compute_lookup_indexes

    def compute(current):
        indexes = original(current)
        access_columns = {
            (reference.split(".", 1)[0].lower(), column)
            for reference, columns in current.access_parties.items()
            for column in columns
        }
        public_columns = {
            (entity.lower(), condition["field"])
            for (entity, _action), condition in current.public_conditions.items()
        }
        if access:
            indexes = [item for item in indexes
                       if item[:2] not in access_columns]
        if public:
            indexes = [item for item in indexes
                       if item[:2] not in public_columns]
        return indexes

    return compute


def test_counterproof_accessible_by_turns_the_invariant_red(monkeypatch):
    monkeypatch.setattr(
        MonlSecureGenerator, "_compute_lookup_indexes",
        _without_source(access=True),
    )
    with pytest.raises(AssertionError, match="recipient_id"):
        _assert_performance_invariant(SPEC_TEMOIN, minimum_witness=MIN_COLONNES_TEMOIN)


def test_counterproof_public_when_turns_the_invariant_red(monkeypatch):
    monkeypatch.setattr(
        MonlSecureGenerator, "_compute_lookup_indexes",
        _without_source(public=True),
    )
    with pytest.raises(AssertionError, match="status"):
        _assert_performance_invariant(SPEC_TEMOIN, minimum_witness=MIN_COLONNES_TEMOIN)
