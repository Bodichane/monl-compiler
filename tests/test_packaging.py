"""Minimal packaging contracts of the monl package."""

import re
from pathlib import Path

from monl import __version__


def test_package_version_matches_pyproject():
    """The imported package and the published metadata must state the same version."""
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    contenu = pyproject.read_text(encoding="utf-8")
    trouvee = re.search(r'^version\s*=\s*"([^"]+)"\s*$', contenu, re.MULTILINE)

    assert trouvee, "version absente de pyproject.toml"
    assert __version__ == trouvee.group(1)
