"""The guide and the examples, checked against what the compiler really does.

Documentation is not text: it is a PROMISE. It is checked the way the
frontend contract is checked against the decorators really written in
`app.py` (`tests/test_orchestrator.py`), and for the same reason — a lying
doc sends you writing a spec the compiler will refuse, and costs more than a
missing doc.

Four confrontations, each against a different source: the Lark grammar, the
routes mounted by FastAPI, the tools declared by the MCP server, and the
compiler itself for the example specifications.
"""

import re

from monl_platform import docs_page, examples, guide, guide_data
from monl_platform.app import create_app
from monl_platform.mcp_server import TOOLS
from monl_platform.service import CompilationService


def _grammar_types():
    """The types the parser really accepts, read from its grammar.

    The grammar is IMPORTED, no longer read through a file path. This test
    targeted `src/monl/parser.py` and broke the day the parser became a package —
    while the grammar itself had not changed by a character. Importing the
    constant targets what Lark REALLY parses, and depends on no tree: it is also
    narrower, since reading the file picked up the rest of the module on the way."""
    from monl.parser import grammar

    ligne = re.search(r'^\s*TYPE:\s*(.+)$', grammar, re.MULTILINE)
    assert ligne, "la règle TYPE a disparu de la grammaire"
    return set(re.findall(r'"([A-Za-z]+)"', ligne.group(1)))


def test_the_guide_documents_exactly_the_grammar_types():
    """In BOTH directions. A documented type that does not exist makes you write
    a refused spec; an existing undocumented type stays unfindable for anyone
    without the repository at hand."""
    # The DSL reference left /guide for /docs: the data is now read in
    # `guide_data`, its SOURCE, which both pages render. The guarantee is
    # unchanged — only the module read has moved.
    documentes = {nom for nom, _ in guide_data.TYPES}
    reels = _grammar_types()
    assert documentes == reels, (
        f"documentés en trop : {sorted(documentes - reels)} · "
        f"absents du guide : {sorted(reels - documentes)}"
    )


def test_the_guide_documents_the_really_mounted_routes(tmp_path):
    """The guide describes the platform API; FastAPI knows what it is."""
    app = create_app(workspace=tmp_path)
    montees = {
        (methode, route.path)
        for route in app.routes
        for methode in getattr(route, "methods", set())
        if methode in {"GET", "POST", "DELETE"}
    }
    for verbe, chemin, _ in guide.ROUTES_API:
        assert (verbe, chemin) in montees, f"le guide annonce {verbe} {chemin}, absent de l'app"

    publiques = {
        (methode, route.path)
        for route in app.routes
        for methode in getattr(route, "methods", set())
        if methode in {"GET", "POST", "DELETE"}
        and (route.path.startswith("/api/") or route.path in {
            "/auth/fournisseurs", "/mcp", "/health", "/ready"
        })
    }
    documentees = {(verbe, chemin) for verbe, chemin, _ in guide.ROUTES_API}
    assert publiques == documentees, (
        f"routes non documentées : {sorted(publiques - documentees)}"
    )


def test_the_guide_documents_the_tools_the_mcp_server_declares():
    documentes = {nom for nom, _ in guide.OUTILS_MCP}
    reels = {outil["name"] for outil in TOOLS}
    assert documentes == reels


def test_the_guide_promises_no_fake_mcp_keys():
    html = guide.guide_html()
    assert "Per-user keys" in html
    assert "Authorization: Bearer" in html
    assert "its fingerprint" in html
    assert "revoke it" in html


def test_the_documentation_orients_before_detailing_the_reference():
    """The docs page stays a front door: the reader must be able to start, look
    up syntax or check permissions before diving into the full tables."""
    html = docs_page.DOCS_HTML
    for texte in ("Choose your starting point", "First spec",
                  "Language reference", "Security and permissions",
                  'href="#premiere-spec"', 'href="#mots-cles"',
                  'href="#acces"'):
        assert texte in html


def test_chaque_exemple_compile_vraiment(tmp_path):
    """This file's lock. An example that no longer compiles is an example
    teaching a dead syntax: the catalog would be worse than empty. We compile for
    real — validating only proves half the way."""
    service = CompilationService(tmp_path)
    for exemple in examples.EXAMPLES:
        manifeste = service.compile(exemple["spec"])
        assert manifeste["summary"]["counts"]["routes"] > 0, exemple["id"]
        attendu = exemple["result"]
        assert manifeste["summary"]["counts"]["entities"] == attendu["entities"]
        assert manifeste["summary"]["counts"]["routes"] == attendu["routes"]
        assert len(manifeste["files"]) == attendu["files"]
        fichiers = set(manifeste["files"])
        assert {"app.py", "schema.sql", "frontend_contract.json"} <= fichiers, exemple["id"]
        assert ".jwt_secret" not in fichiers, exemple["id"]
        # The count stays at 16, and it is a COINCIDENCE that must be said:
        # `sandbox_ai.py` left (no example has a `custom` block) and
        # `README.md` arrived. An unchanged count would have suggested neither
        # had moved — so both are named, and the LAYOUT is checked rather than
        # the total alone.
        assert "sandbox_ai.py" not in fichiers, exemple["id"]
        assert {"README.md", "AGENTS.md", "docs/FRONTEND_PROMPT.md",
                "docs/DESIGN_SYSTEM.md", "docs/DESIGN_SPEC.md",
                "docs/ASSET_MANIFEST.json"} <= fichiers, exemple["id"]
        assert "CLAUDE.md" not in fichiers, exemple["id"]


def test_no_example_declares_an_asset(tmp_path):
    """The platform offers no upload: an example declaring an image would be
    refused in front of the visitor, at the first keystroke. It is the limit the
    guide STATES — this test makes it true."""
    for exemple in examples.EXAMPLES:
        assert "\nassets" not in exemple["spec"], exemple["id"]
        assert ": Image" not in exemple["spec"], exemple["id"]


def test_the_catalog_does_not_ship_the_specs_and_ids_are_unique():
    catalogue = examples.catalogue()
    assert len(catalogue) == len(examples.EXAMPLES)
    assert all("spec" not in entree for entree in catalogue), "galerie inutilement lourde"
    identifiants = [entree["id"] for entree in catalogue]
    assert len(set(identifiants)) == len(identifiants)
    for entree in catalogue:
        assert entree["name"] and entree["summary"] and entree["teaches"]


def test_the_rules_cited_by_the_guide_all_carry_a_known_keyword():
    """Safeguard against invented rules. Each example line of the guide must use
    a keyword the validator knows — the list comes from `ast_validator`, not
    from a hand-made copy here."""
    import pathlib

    # The validator has been a PACKAGE since its split: the source to search is
    # the union of its modules. The file form stays accepted — this test says
    # "the keyword exists in the validator", not "it lives in this file".
    racine = pathlib.Path(__file__).parent.parent / "src/monl"
    paquet = racine / "ast_validator"
    fichiers = (sorted(paquet.glob("*.py")) if paquet.is_dir()
                else [racine / "ast_validator.py"])
    assert fichiers, "source du validateur introuvable"
    validateur = "\n".join(f.read_text(encoding="utf-8") for f in fichiers)
    tableaux = (guide_data.REGLES_ACCES + guide_data.REGLES_CHAMPS
                + guide_data.REGLES_SERVEUR + guide_data.REGLES_COMMERCE)
    for regle, _ in tableaux:
        mots = re.findall(r"\b(ownedBy|accessibleBy|public|publicWhen|sharedBy|oncePer|"
                          r"requiresOwn|min|max|unique|required|oneOf|generated|timestamp|"
                          r"numbered|derivedFrom|sumOf|hidden|categorized|decrements|"
                          r"increments|payable|releases|writableAfterPayment)\b", regle)
        assert mots, f"règle sans mot-clé identifiable : {regle}"
        for mot in mots:
            assert f'"{mot}"' in validateur or f"'{mot}'" in validateur, (
                f"le guide cite `{mot}`, que le validateur ne connaît pas")
