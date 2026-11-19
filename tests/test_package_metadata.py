"""The published package describes what it is, without inventing its identity."""

import os

from monl_platform import legal


def _project():
    try:
        import tomllib
    except ModuleNotFoundError:  # Python 3.10
        import tomli as tomllib

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(racine, "pyproject.toml"), "rb") as file:
        return tomllib.load(file)["project"]


def _workflow_versions(name):
    """Returns the Python versions a workflow really tests.

    Read from the file rather than copied: two version lists kept separately
    always end up diverging. A single reader for both workflows, for the same
    reason — writing a second would reproduce, at the measurement level, the
    defect the measurement tries to forbid.
    """
    import re

    racine = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(racine, ".github", "workflows", name)
    with open(path, encoding="utf-8") as file:
        content = file.read()
    line = re.search(r"python-version:\s*\[([^\]]*)\]", content)
    return re.findall(r"\d+\.\d+", line.group(1)) if line else []


def _ci_versions():
    return _workflow_versions("ci.yml")


def test_the_publishing_metadata_describe_the_project():
    project = _project()
    classifiers = set(project["classifiers"])

    assert {
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Topic :: Software Development :: Code Generators",
        "Topic :: Software Development :: Compilers",
    } <= classifiers
    # The versions are NOT written here: they are read from the CI matrix. A
    # hand-kept list silently drifts the day the matrix changes — the defect
    # point 164 found on the `/mcp` page, which announced four nonexistent
    # tools because its list was written by hand rather than checked against
    # `TOOLS`.
    #
    # The direction of the check matters: every TESTED version must be
    # announced, never the reverse. Announcing 3.11 without testing it would be
    # an unverifiable promise; testing it without announcing it deprives the
    # user of true information.
    testees = _ci_versions()
    assert testees, "unreadable CI matrix: this witness no longer guards anything"
    missing = [v for v in testees
                  if f"Programming Language :: Python :: {v}" not in classifiers]
    assert not missing, (
        f"versions tested by CI but not announced on the index: "
        f"{missing}")
    assert project["urls"] == {
        "Repository": "https://github.com/Bodichane/monl-compiler",
        "Documentation": "https://github.com/Bodichane/monl-compiler/tree/main/docs",
        "Issues": "https://github.com/Bodichane/monl-compiler/issues",
    }


def test_the_non_spdx_license_is_named_and_shipped_without_substitution():
    project = _project()

    # FSL-1.1-ALv2 is not in the SPDX catalog: LicenseRef honestly names this
    # custom license and the file stays its source of truth in every artifact.
    assert project["license"] == "LicenseRef-FSL-1.1-ALv2"
    assert project["license-files"] == ["LICENSE"]


def test_an_author_cannot_be_the_package_name():
    project = _project()
    auteurs = project.get("authors", [])

    assert auteurs, "no declared author: this witness would no longer guard anything"
    assert all(auteur["name"] != project["name"] for auteur in auteurs)


def test_the_distribution_author_is_the_legal_publisher():
    project = _project()

    assert project["authors"] == [{"name": legal.PUBLISHER}], (
        "the distribution's author must stay identical to legal.EDITEUR"
    )


def test_publishing_tests_the_tag_on_the_same_versions_as_ci():
    """Publishing on fewer versions than CI would make its own sentence false.

    `publication.yml` justifies in a comment that it replays tests and lint
    because "main's CI is not enough: it ran on a commit, not necessarily the one
    the tag designates". That reason only holds if the tag is tested on the SAME
    versions: replaying only one would let go, for good, a version two thirds of
    whose announced support was never checked on that commit.

    The direction of the check is equality, not inclusion. A version published
    without being announced would have no classifier (the witness above already
    refuses it); a version announced that publishing does not test is exactly the
    hole this witness closes.
    """
    ci = _workflow_versions("ci.yml")
    publication = _workflow_versions("publication.yml")

    assert ci, "unreadable ci.yml matrix: this witness no longer guards anything"
    assert publication, (
        "unreadable publication.yml matrix: this witness no longer guards anything")
    assert publication == ci, (
        f"publication tests {publication} while CI tests {ci}: "
        f"the tag would go out without having been replayed on every version "
        f"announced on the index")
