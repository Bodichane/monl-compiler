"""Issue #83 : ce que `monl run --check` annonce d'un projet SANS frontend doit
être ce qu'un vrai serveur sert.

L'avertissement promettait « ses seules pages générées (landing, /app, /docs) »
alors que le frontend généré par monl a disparu au point 41 : `/` répondait
307 vers /docs et `/app` un 404 JSON, que l'usager prenait pour une panne. Le
témoin ne compare pas le message à une phrase attendue — il DEMANDE au serveur
chaque chemin que le message cite, et confronte la réponse à ce qui est dit.
"""

import re
import urllib.error
import urllib.request

from monl.cli import check_coherence, compile_project
from tests.support.server import uvicorn_server


class _SansRedirection(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


_OUVREUR = urllib.request.build_opener(_SansRedirection)


def _statut(url):
    try:
        with _OUVREUR.open(url, timeout=5) as r:
            return r.status, r.headers.get("Location")
    except urllib.error.HTTPError as e:
        with e:
            return e.code, e.headers.get("Location")


def _avertissement_sans_frontend(projet):
    ok, erreurs, avertissements = check_coherence(str(projet))
    assert ok, erreurs
    trouves = [a for a in avertissements if "frontend/" in a]
    assert len(trouves) == 1, avertissements
    return trouves[0]


def _chemins_cites(message):
    """Les chemins d'URL que le message nomme (`/`, `/docs`, `/site/`…).

    Un chemin est une barre oblique en début de mot ; `frontend/` n'en est pas
    un (la barre est en fin de mot), et c'est la raison de l'ancre."""
    return sorted(set(re.findall(r"(?<![\w.])/[a-z_]*/?", message)))


def test_chaque_chemin_annonce_sans_frontend_repond_comme_annonce(tmp_path, capsys):
    compile_project("exemples/02_boutique.ml", str(tmp_path))
    capsys.readouterr()
    assert not (tmp_path / "frontend").exists()

    message = _avertissement_sans_frontend(tmp_path)
    chemins = _chemins_cites(message)
    # Non-vacuité : sans chemin extrait, la boucle ci-dessous ne vérifierait
    # rien et rendrait du vert (point 161). On n'exige PAS une liste précise :
    # c'est le serveur, pas une phrase recopiée ici, qui juge chaque chemin.
    assert chemins, message

    with uvicorn_server(str(tmp_path), module="serve:app") as base:
        for chemin in chemins:
            statut, destination = _statut(base + chemin)
            if chemin == "/site/":
                # Le message dit que /site/ répond 404 sans interface : il
                # faut que ce soit VRAI, sinon il promet une panne qui n'a pas
                # lieu.
                assert statut == 404, (chemin, statut)
            elif chemin == "/":
                assert statut in (302, 307) and destination == "/docs", (
                    chemin, statut, destination)
            else:
                assert statut == 200, (
                    f"l'avertissement cite {chemin}, qui répond {statut} : "
                    f"un usager qui l'ouvre croit son déploiement cassé")


def test_un_frontend_qui_appelle_app_est_signale(tmp_path, capsys):
    """`/app` figurait parmi les préfixes « connus » de la cohérence, reliquat
    du frontend retiré au point 41 : un frontend qui l'appelait n'était pas
    signalé, alors que le serveur y répond 404."""
    compile_project("exemples/02_boutique.ml", str(tmp_path))
    capsys.readouterr()
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "index.html").write_text(
        "<!doctype html><title>t</title>"
        "<script>fetch('/app/tableau').then(r => r.json())</script>",
        encoding="utf-8")

    _ok, _erreurs, avertissements = check_coherence(str(tmp_path))
    absents = [a for a in avertissements if "absents du contrat" in a]
    assert absents and "/app" in absents[0], avertissements
