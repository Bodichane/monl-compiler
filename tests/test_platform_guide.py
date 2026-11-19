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

    line = re.search(r'^\s*TYPE:\s*(.+)$', grammar, re.MULTILINE)
    assert line, "the TYPE rule disappeared from the grammar"
    return set(re.findall(r'"([A-Za-z]+)"', line.group(1)))


def test_the_guide_documents_exactly_the_grammar_types():
    """In BOTH directions. A documented type that does not exist makes you write
    a refused spec; an existing undocumented type stays unfindable for anyone
    without the repository at hand."""
    # The DSL reference left /guide for /docs: the data is now read in
    # `guide_data`, its SOURCE, which both pages render. The guarantee is
    # unchanged — only the module read has moved.
    documented = {name for name, _ in guide_data.TYPES}
    reels = _grammar_types()
    assert documented == reels, (
        f"documented in excess: {sorted(documented - reels)} · "
        f"missing from the guide: {sorted(reels - documented)}"
    )


def test_the_guide_documents_the_really_mounted_routes(tmp_path):
    """The guide describes the platform API; FastAPI knows what it is."""
    app = create_app(workspace=tmp_path)
    mounted = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in {"GET", "POST", "DELETE"}
    }
    for verb, path, _ in guide.ROUTES_API:
        assert (verb, path) in mounted, f"the guide announces {verb} {path}, missing from the app"

    public = {
        (method, route.path)
        for route in app.routes
        for method in getattr(route, "methods", set())
        if method in {"GET", "POST", "DELETE"}
        and (route.path.startswith("/api/") or route.path in {
            "/auth/fournisseurs", "/mcp", "/health", "/ready"
        })
    }
    documented = {(verb, path) for verb, path, _ in guide.ROUTES_API}
    assert public == documented, (
        f"undocumented routes: {sorted(public - documented)}"
    )


def test_the_guide_documents_the_tools_the_mcp_server_declares():
    documented = {name for name, _ in guide.TOOLS_MCP}
    reels = {tool["name"] for tool in TOOLS}
    assert documented == reels


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
    for text in ("Choose your starting point", "First spec",
                  "Language reference", "Security and permissions",
                  'href="#premiere-spec"', 'href="#mots-cles"',
                  'href="#acces"'):
        assert text in html


def test_each_example_really_compiles(tmp_path):
    """This file's lock. An example that no longer compiles is an example
    teaching a dead syntax: the catalog would be worse than empty. We compile for
    real — validating only proves half the way."""
    service = CompilationService(tmp_path)
    for example in examples.EXAMPLES:
        manifest = service.compile(example["spec"])
        assert manifest["summary"]["counts"]["routes"] > 0, example["id"]
        expected = example["result"]
        assert manifest["summary"]["counts"]["entities"] == expected["entities"]
        assert manifest["summary"]["counts"]["routes"] == expected["routes"]
        assert len(manifest["files"]) == expected["files"]
        files = set(manifest["files"])
        assert {"app.py", "schema.sql", "frontend_contract.json"} <= files, example["id"]
        assert ".jwt_secret" not in files, example["id"]
        # The count stays at 16, and it is a COINCIDENCE that must be said:
        # `sandbox_ai.py` left (no example has a `custom` block) and
        # `README.md` arrived. An unchanged count would have suggested neither
        # had moved — so both are named, and the LAYOUT is checked rather than
        # the total alone.
        assert "sandbox_ai.py" not in files, example["id"]
        assert {"README.md", "AGENTS.md", "docs/FRONTEND_PROMPT.md",
                "docs/DESIGN_SYSTEM.md", "docs/DESIGN_SPEC.md",
                "docs/ASSET_MANIFEST.json"} <= files, example["id"]
        assert "CLAUDE.md" not in files, example["id"]


def test_no_example_declares_an_asset(tmp_path):
    """The platform offers no upload: an example declaring an image would be
    refused in front of the visitor, at the first keystroke. It is the limit the
    guide STATES — this test makes it true."""
    for example in examples.EXAMPLES:
        assert "\nassets" not in example["spec"], example["id"]
        assert ": Image" not in example["spec"], example["id"]


def test_the_catalog_does_not_ship_the_specs_and_ids_are_unique():
    catalogue = examples.catalogue()
    assert len(catalogue) == len(examples.EXAMPLES)
    assert all("spec" not in entry for entry in catalogue), "galerie inutilement lourde"
    identifiers = [entry["id"] for entry in catalogue]
    assert len(set(identifiers)) == len(identifiers)
    for entry in catalogue:
        assert entry["name"] and entry["summary"] and entry["teaches"]


def test_the_rules_cited_by_the_guide_all_carry_a_known_keyword():
    """Safeguard against invented rules. Each example line of the guide must use
    a keyword the validator knows — the list comes from `ast_validator`, not
    from a hand-made copy here."""
    import pathlib

    # The validator has been a PACKAGE since its split: the source to search is
    # the union of its modules. The file form stays accepted — this test says
    # "the keyword exists in the validator", not "it lives in this file".
    racine = pathlib.Path(__file__).parent.parent / "src/monl"
    package = racine / "ast_validator"
    files = (sorted(package.glob("*.py")) if package.is_dir()
                else [racine / "ast_validator.py"])
    assert files, "validator source not found"
    validator = "\n".join(f.read_text(encoding="utf-8") for f in files)
    tableaux = (guide_data.RULES_ACCESS + guide_data.RULES_FIELDS
                + guide_data.RULES_SERVER + guide_data.RULES_COMMERCE)
    for rule, _ in tableaux:
        words = re.findall(r"\b(ownedBy|accessibleBy|public|publicWhen|sharedBy|oncePer|"
                          r"requiresOwn|min|max|unique|required|oneOf|generated|timestamp|"
                          r"numbered|derivedFrom|sumOf|hidden|categorized|decrements|"
                          r"increments|payable|releases|writableAfterPayment)\b", rule)
        assert words, f"rule without identifiable keyword: {rule}"
        for word in words:
            assert f'"{word}"' in validator or f"'{word}'" in validator, (
                f"the guide cites `{word}`, which the validator does not know")
