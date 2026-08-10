"""Contrats minimaux du packaging du paquet monl."""

import re
from pathlib import Path

from monl import __version__


def test_la_version_du_paquet_est_alignee_sur_pyproject():
    """Le paquet importé et la métadonnée publiée doivent parler de la même version."""
    pyproject = Path(__file__).parents[1] / "pyproject.toml"
    contenu = pyproject.read_text(encoding="utf-8")
    trouvee = re.search(r'^version\s*=\s*"([^"]+)"\s*$', contenu, re.MULTILINE)

    assert trouvee, "version absente de pyproject.toml"
    assert __version__ == trouvee.group(1)
