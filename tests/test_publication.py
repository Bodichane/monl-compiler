"""Publishing is secretless and its witnesses really bite."""

import os
import re
from pathlib import Path

import pytest
import yaml

from scripts.check_publication_version import PublicationVersionError, validate_tag_version
from tests.support.cases import check_each_case


def _racine():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _guide():
    with open(os.path.join(_racine(), "docs", "PUBLICATION.md"), encoding="utf-8") as fichier:
        return fichier.read()


def _workflow(nom="publication.yml"):
    chemin = Path(_racine()) / ".github" / "workflows" / nom
    with chemin.open(encoding="utf-8") as fichier:
        return yaml.safe_load(fichier)


def _extras_installes(job):
    """The extras the job passes to `pip install -e ".[…]"`.

    A job installing the package through no command of this form raises:
    returning an empty set would make equality pass between two silent jobs.
    """
    commandes = "\n".join(etape.get("run", "") for etape in job["steps"])
    trouves = re.findall(r'pip install -e "\.\[([^\]]*)\]"', commandes)
    assert len(trouves) == 1, f"package installation not found or multiple: {trouves}"
    return {extra.strip() for extra in trouves[0].split(",")}


def _project():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    with open(os.path.join(_racine(), "pyproject.toml"), "rb") as fichier:
        return tomllib.load(fichier)["project"]


def test_the_guide_publishes_the_same_version_in_the_right_order():
    guide = _guide()
    project = _project()

    assert project["name"] in guide
    assert project["version"] in guide
    commandes = (
        "python -m build",
        "python -m twine check dist/*",
        "python -m twine upload --repository testpypi dist/*",
        "python -m twine upload dist/*",
    )
    positions = [guide.index(commande) for commande in commandes]
    assert positions == sorted(positions)
    assert "https://test.pypi.org/simple/" in guide
    assert "https://pypi.org/simple/" in guide
    assert "https://test.pypi.org/legacy/" in guide
    assert "https://upload.pypi.org/legacy/" in guide


def test_the_guide_isolates_repository_and_command_identifiers():
    guide = _guide()

    assert "~/.pypirc" in guide
    assert "TWINE_PASSWORD" in guide
    assert "--password" in guide
    assert "never in this repository" in " ".join(guide.split())
    assert "Do not rebuild between the two uploads" in guide


def test_the_guide_empties_dist_before_building():
    """`dist/` survives from one build to the next, and `twine upload dist/*`
    sends EVERYTHING it finds there.

    The folder is ignored by git, so absent from a freshly cloned repository —
    but present on the publishing machine, which is precisely the one that has
    already built. Measured when writing this witness: `dist/` carried
    `monl_compiler-0.9.0b7` while the version to publish was `0.9.0b8`. Without
    cleaning, both go, and **a version number sent to PyPI can never be reused,
    even after deletion**: the mistake is final.

    The witness requires cleaning BEFORE `python -m build` — the order IS the
    guarantee, an `rm -rf dist/` written after would protect from nothing.
    """
    guide = _guide()

    assert "rm -rf dist/" in guide, (
        "the guide builds without emptying dist/: a stale version already "
        "present would be published with the new one")
    assert guide.index("rm -rf dist/") < guide.index("python -m build"), (
        "cleaning is written AFTER building: it protects from nothing")
    # The consequence must be written, otherwise the command looks like a fad
    # and the first person publishing under pressure skips it.
    assert "cannot be reused" in guide or "does not allow republishing" in guide, (
        "the guide does not say an uploaded version number is final")


def test_the_matching_tag_is_accepted():
    validate_tag_version("v0.9.0-beta.8", "0.9.0-beta.8")


def test_the_diverging_tag_is_refused_and_names_both_values():
    with pytest.raises(PublicationVersionError, match=r"v0\.9\.0b9.*0\.9\.0-beta\.8"):
        validate_tag_version("v0.9.0b9", "0.9.0-beta.8")


def test_both_spellings_of_one_version_are_accepted():
    table = [
        ("v0.9.0b8", "0.9.0-beta.8"),
        ("v0.9.0-beta.8", "0.9.0b8"),
    ]

    def cas(tag, declared_version):
        validate_tag_version(tag, declared_version)

    check_each_case(table, cas)


def test_the_workflow_parses_and_carries_the_secretless_chain():
    workflow = _workflow()
    jobs = workflow["jobs"]
    triggers = workflow.get("on", workflow.get(True))

    assert triggers == {"push": {"tags": ["v*"]}}
    assert set(jobs) == {
        "verify-tag",
        "tests",
        "build",
        "publish-testpypi",
        "publish-pypi",
    }
    assert jobs["build"]["needs"] == ["verify-tag", "tests"]
    assert jobs["publish-testpypi"]["needs"] == "build"
    assert jobs["publish-pypi"]["needs"] == "publish-testpypi"

    assert jobs["verify-tag"]["permissions"] == {"contents": "read"}
    assert jobs["tests"]["permissions"] == {"contents": "read"}
    assert jobs["build"]["permissions"] == {"contents": "read"}
    assert jobs["publish-testpypi"]["permissions"] == {"id-token": "write"}
    assert jobs["publish-pypi"]["permissions"] == {"id-token": "write"}
    assert jobs["publish-testpypi"]["environment"] == "testpypi"
    assert jobs["publish-pypi"]["environment"] == "pypi"

    contenu = (Path(_racine()) / ".github" / "workflows" / "publication.yml").read_text(
        encoding="utf-8"
    )
    assert "secrets." not in contenu
    assert contenu.count("python -m build") == 1
    assert "actions/upload-artifact@v4.6.2" in contenu
    assert contenu.count("actions/download-artifact@v4.3.0") == 2
    assert "pypa/gh-action-pypi-publish@v1.14.2" in contenu
    actions = re.findall(r"uses:\s+([^\s]+)", contenu)
    assert actions and all(re.search(r"@v\d+\.\d+\.\d+$", action) for action in actions)


def test_lint_and_tests_are_dependencies_of_the_build():
    workflow = _workflow()
    build = workflow["jobs"]["build"]
    tests_steps = workflow["jobs"]["tests"]["steps"]
    commandes = [etape.get("run", "") for etape in tests_steps]

    assert "ruff check src tests" in commandes
    assert any("pytest tests/" in commande for commande in commandes)
    assert set(build["needs"]) >= {"tests", "verify-tag"}


def test_the_guide_names_the_real_workflow_and_environments():
    guide = _guide()
    workflow = _workflow()
    environnements = {
        job["environment"]
        for job in workflow["jobs"].values()
        if "environment" in job
    }

    assert ".github/workflows/publication.yml" in guide
    assert "publication.yml" in guide
    assert "| Workflow | `publication.yml` |" in guide
    assert "| Environment | `pypi` |" in guide
    assert "| Environment | `testpypi` |" in guide
    assert {"testpypi", "pypi"} <= environnements
    for environnement in environnements:
        assert f"`{environnement}`" in guide


def test_the_trusted_publisher_table_names_the_real_repository():
    """A wrong field in this table produces `invalid-publisher`, nothing more.

    PyPI does not check the trusted publisher when it is declared: it checks it
    against the OIDC token at upload time. A mistake on the owner, the repository
    or the project name therefore only shows at publishing, as a refusal that
    does not say WHICH field is wrong — and the maintainer has no way to guess
    it from GitHub.

    The table is therefore checked against `[project.urls].Repository`, which is
    already pinned by `tests/test_package_metadata.py`. Two truths kept
    separately always end up contradicting each other: here one is published
    metadata, the other an instruction to copy by hand into a form.
    """
    import re

    project = _project()
    depot = project["urls"]["Repository"]
    correspondance = re.fullmatch(
        r"https://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?", depot)
    assert correspondance, f"unreadable repository URL: {depot!r}"
    proprietaire, nom_du_depot = correspondance.groups()

    guide = _guide()
    # Two tables: PyPI and TestPyPI. BOTH must carry the value — checking only
    # one would let the test instance diverge, and it is precisely the one
    # filled in first.
    for etiquette, valeur in (
        ("Project", project["name"]),
        ("Repository owner", proprietaire),
        ("Repository", nom_du_depot),
    ):
        ligne = f"| {etiquette} | `{valeur}` |"
        assert guide.count(ligne) == 2, (
            f"the guide should carry {ligne!r} twice (PyPI and TestPyPI), "
            f"it carries it {guide.count(ligne)} times — the trusted publisher "
            f"would refuse the upload without saying which field is wrong")


def test_publishing_tests_the_tag_in_the_ci_environment():
    """Same reason as the matrix, applied to what is INSTALLED and MOUNTED.

    The first real run of this chain, on tag v0.9.0-beta.9, failed on a single
    test: publishing installed `.[dev]` while CI installs `.[dev,postgres]`, and
    `psycopg` was missing. Nothing was published — the safeguard held — but the
    cause is a list kept by hand in two places. Worse than the red test: without
    the PostgreSQL service, sixteen tests would have SKIPPED here while running
    in CI, and the chain would have published a tag less tested than `main`'s
    commit.
    """
    ci = _workflow("ci.yml")["jobs"]["verifier"]
    publication = _workflow()["jobs"]["tests"]

    extras_ci = _extras_installes(ci)
    assert "postgres" in extras_ci, "premise: CI tests PostgreSQL"
    assert _extras_installes(publication) == extras_ci
    assert publication.get("services") == ci.get("services")
    assert publication.get("env") == ci.get("env")
