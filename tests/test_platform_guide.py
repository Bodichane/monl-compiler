"""Le guide et les exemples, confrontés à ce que le compilateur fait vraiment.

Une documentation n'est pas un texte : c'est une PROMESSE. Elle se vérifie
comme le contrat frontend se vérifie contre les décorateurs réellement écrits
dans `app.py` (`tests/test_orchestrator.py`), et pour la même raison — une
doc qui ment envoie écrire une spec que le compilateur refusera, et coûte
plus cher qu'une doc absente.

Quatre confrontations, chacune contre une source différente :
la grammaire Lark, les routes montées par FastAPI, les outils déclarés par le
serveur MCP, et le compilateur lui-même pour les spécifications d'exemple.
"""

import re

from monl_platform import docs_page, examples, guide, guide_data
from monl_platform.app import create_app
from monl_platform.mcp_server import TOOLS
from monl_platform.service import CompilationService


def _types_de_la_grammaire():
    """Les types que le parseur accepte réellement, lus dans sa grammaire.

    La grammaire est IMPORTÉE, plus lue par un chemin de fichier. Ce test
    visait `src/monl/parser.py` et s'est cassé le jour où le parseur est
    devenu un paquet — alors que la grammaire, elle, n'avait pas changé d'un
    caractère. Importer la constante vise ce que Lark analyse VRAIMENT, et ne
    dépend d'aucune arborescence : c'est aussi plus étroit, puisque la lecture
    du fichier ramassait le reste du module au passage."""
    from monl.parser import grammar

    ligne = re.search(r'^\s*TYPE:\s*(.+)$', grammar, re.MULTILINE)
    assert ligne, "la règle TYPE a disparu de la grammaire"
    return set(re.findall(r'"([A-Za-z]+)"', ligne.group(1)))


def test_le_guide_documente_exactement_les_types_de_la_grammaire():
    """Dans les DEUX sens. Un type documenté qui n'existe pas fait écrire une
    spec refusée ; un type existant non documenté reste introuvable pour qui
    n'a pas le dépôt sous les yeux."""
    # La référence DSL a quitté /guide pour /docs : la donnée se lit
    # désormais dans `guide_data`, sa SOURCE, que les deux pages
    # rendent. La garantie est inchangée — seul le module lu a bougé.
    documentes = {nom for nom, _ in guide_data.TYPES}
    reels = _types_de_la_grammaire()
    assert documentes == reels, (
        f"documentés en trop : {sorted(documentes - reels)} · "
        f"absents du guide : {sorted(reels - documentes)}"
    )


def test_le_guide_documente_les_routes_reellement_montees(tmp_path):
    """Le guide décrit l'API de la plateforme ; FastAPI sait ce qu'elle est."""
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


def test_le_guide_documente_les_outils_que_le_serveur_mcp_declare():
    documentes = {nom for nom, _ in guide.OUTILS_MCP}
    reels = {outil["name"] for outil in TOOLS}
    assert documentes == reels


def test_le_guide_ne_promet_pas_de_fausses_cles_mcp():
    html = guide.guide_html()
    assert "Clés par utilisateur" in html
    assert "Authorization: Bearer" in html
    assert "l'empreinte" in html
    assert "révocation" in html


def test_la_documentation_oriente_avant_de_detailler_la_reference():
    """La page de docs reste une porte d'entrée : le lecteur doit pouvoir
    commencer, chercher la syntaxe ou vérifier les droits avant de plonger
    dans les tableaux complets."""
    html = docs_page.DOCS_HTML
    for texte in ("Choisissez votre point de départ", "Première spec",
                  "Référence du langage", "Sécurité et droits",
                  'href="#premiere-spec"', 'href="#mots-cles"',
                  'href="#acces"'):
        assert texte in html


def test_chaque_exemple_compile_vraiment(tmp_path):
    """Le verrou de ce fichier. Un exemple qui ne compile plus est un
    exemple qui apprend une syntaxe morte : le catalogue serait pire que vide.
    On compile pour de bon — valider ne prouve que la moitié du chemin."""
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
        # Le décompte reste à 16, et c'est une COÏNCIDENCE qu'il faut dire :
        # `sandbox_ai.py` est parti (aucun exemple n'a de bloc `custom`) et
        # `README.md` est arrivé. Un décompte inchangé aurait laissé croire
        # qu'aucun des deux n'avait bougé — on nomme donc les deux, et on
        # vérifie le RANGEMENT plutôt que le seul total.
        assert "sandbox_ai.py" not in fichiers, exemple["id"]
        assert {"README.md", "AGENTS.md", "docs/FRONTEND_PROMPT.md",
                "docs/DESIGN_SYSTEM.md", "docs/DESIGN_SPEC.md",
                "docs/ASSET_MANIFEST.json"} <= fichiers, exemple["id"]
        assert "CLAUDE.md" not in fichiers, exemple["id"]


def test_aucun_exemple_ne_declare_dasset(tmp_path):
    """La plateforme n'offre aucun téléversement : un exemple qui déclarerait
    une image serait refusé sous les yeux du visiteur, à la première touche.
    C'est la limite que le guide ÉNONCE — ce test la rend vraie."""
    for exemple in examples.EXAMPLES:
        assert "\nassets" not in exemple["spec"], exemple["id"]
        assert ": Image" not in exemple["spec"], exemple["id"]


def test_le_catalogue_ne_livre_pas_les_specs_et_les_ids_sont_uniques():
    catalogue = examples.catalogue()
    assert len(catalogue) == len(examples.EXAMPLES)
    assert all("spec" not in entree for entree in catalogue), "galerie inutilement lourde"
    identifiants = [entree["id"] for entree in catalogue]
    assert len(set(identifiants)) == len(identifiants)
    for entree in catalogue:
        assert entree["name"] and entree["summary"] and entree["teaches"]


def test_les_regles_citees_par_le_guide_portent_toutes_un_mot_cle_connu():
    """Garde-fou contre la règle inventée. Chaque ligne d'exemple du guide
    doit employer un mot-clé que le validateur connaît — la liste vient de
    `ast_validator`, pas d'une copie faite à la main ici."""
    import pathlib

    # Le validateur est un PAQUET depuis son découpage : la source à fouiller
    # est l'union de ses modules. La forme fichier reste acceptée — ce test dit
    # « le mot-clé existe chez le validateur », pas « il vit dans tel fichier ».
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
