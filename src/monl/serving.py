"""Le wrapper de service, partagé par 'monl run' et le smoke test.

POURQUOI CE MODULE EXISTE (brique 13, point 83). Le wrapper vivait dans cli.py,
et le smoke test lançait `app:app` — donc il n'exerçait NI le montage de
frontend/ sur /site, NI celui des assets. « Servi » n'était vérifié nulle part :
seul l'œil, sur la page, aurait vu un montage mal placé.

Le faire vérifier par le smoke test demandait que les deux couches partagent le
même texte. Le dupliquer aurait créé deux wrappers à faire dériver — exactement
ce que le projet refuse ailleurs (PAYMENT_*_COLUMN, _compute_route_map). Mais
smoke_test est importé par cli, donc l'inverse ferait un cycle : d'où ce module,
FEUILLE volontaire qui n'importe rien du projet.
"""

SERVE_WRAPPER = '''"""Wrapper généré par 'monl run' — ne pas éditer.
Monte le frontend produit par l'IA (frontend/) sur /site, sans modifier
app.py (le backend reste un artefact scellé du compilateur)."""
import os

from fastapi.staticfiles import StaticFiles
from app import app

# BRIQUE 13 (point 83) : les assets fournis par l'HUMAIN vivent hors de
# frontend/, parce que ce dossier-là est renommé à chaque construction par
# 'monl frontend' et que sa liste blanche n'accepte pas les .jpg — les photos
# qu'on y déposait finissaient dans frontend.precedent/ sans un mot.
#
# Le montage doit venir AVANT celui de /site : Starlette teste les routes dans
# l'ordre d'enregistrement, et '/site' monté en premier absorberait
# '/site/<dossier>/…' pour aller le chercher dans frontend/, où il n'est pas.
_ASSETS_DIR = {assets_dir!r}
if _ASSETS_DIR and os.path.isdir(_ASSETS_DIR):
    app.mount("/site/" + _ASSETS_DIR,
              StaticFiles(directory=_ASSETS_DIR), name="assets")

app.mount("/site", StaticFiles(directory="frontend", html=True), name="site")
'''


def rendre_wrapper(assets_dir=None):
    """Le texte du serve.py à écrire dans un projet.

    'assets_dir' est le dossier déclaré par la spec, ou None : dans ce cas le
    wrapper ne monte que frontend/, exactement comme avant la brique 13."""
    return SERVE_WRAPPER.format(assets_dir=assets_dir)
