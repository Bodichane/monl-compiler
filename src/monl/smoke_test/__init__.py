"""Le vérificateur : un serveur ÉPHÉMÈRE, de vrais appels, un vrai jsdom.

Il démarre dans un dossier temporaire et ne touche JAMAIS l'app.db du
projet. Un test qui saute ne dit pas « rien à vérifier ici », il dit « je
n'ai pas vérifié » (point 140)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

from ..frontend_contract import CONTRACT_FILENAME
from ..serving import rendre_wrapper
from . import etapes, fondations
from .fondations import _identifiant_smoke
from .sondes import _sample_value


def run_smoke_test(project_dir, say=print):
    """Retourne (ok, erreurs, avertissements). Lève seulement sur bug interne."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)
    with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
        contract = json.load(fh)

    workdir = tempfile.mkdtemp(prefix="monl_smoke_")
    try:
        # Copie des artefacts : base neuve, données réelles intouchées.
        for name in ("app.py", "schema.sql", "sandbox_ai.py", ".jwt_secret"):
            src = os.path.join(project_dir, name)
            if os.path.exists(src):
                shutil.copy2(src, workdir)
        frontend_src = os.path.join(project_dir, "frontend")
        has_frontend = os.path.isdir(frontend_src)
        if has_frontend:
            shutil.copytree(frontend_src, os.path.join(workdir, "frontend"))
        # AJOUT (brique 13, point 83) : les assets déclarés sont copiés et
        # SERVIS, via le même wrapper que 'monl run'. Jusqu'ici le smoke test
        # lançait `app:app` : ni /site ni les assets ne passaient par HTTP,
        # donc « servi » n'était vérifié nulle part — seul l'œil, sur la page,
        # aurait vu un montage mal placé.
        assets_dir = (contract.get("assets") or {}).get("dir")
        assets_src = os.path.join(project_dir, assets_dir) if assets_dir else None
        has_assets = bool(assets_src and os.path.isdir(assets_src))
        if has_assets:
            shutil.copytree(assets_src, os.path.join(workdir, assets_dir))
        module = "app:app"
        if has_frontend:
            with open(os.path.join(workdir, "serve.py"), "w", encoding="utf-8") as fh:
                fh.write(rendre_wrapper(assets_dir if has_assets else None))
            module = "serve:app"

        port = fondations._free_port()
        base = f"http://127.0.0.1:{port}"
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", module, "--host", "127.0.0.1",
             "--port", str(port), "--log-level", "warning"],
            cwd=workdir, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(50):
                status, _b = fondations._http("GET", base + "/docs")
                if status == 200:
                    break
                if server.poll() is not None:
                    raise fondations.SmokeFailure("le serveur éphémère s'est arrêté au démarrage : "
                                       + server.stderr.read().decode(errors="replace")[-400:])
                time.sleep(0.2)
            else:
                raise fondations.SmokeFailure("le serveur éphémère n'a jamais répondu sur /docs")

            actor, token = etapes._compte_de_test(base, contract, errors, warnings)

            etapes._eprouver_les_routes(actor, base, contract, errors, token)

            etapes._eprouver_une_creation(actor, base, contract, errors, token, warnings)

            etapes._assets_reellement_servis(assets_dir, assets_src, base, contract, errors, has_assets)

            etapes._fichiers_reclames_servis(base, errors, has_frontend, workdir)

            etapes._frontend_dans_jsdom(base, contract, errors, has_frontend, say, warnings, workdir)
        finally:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
            # `stderr=PIPE` ouvre un descripteur que ni terminate() ni wait()
            # ne referment. Sans ce close, chaque smoke test en laisse un
            # derrière lui — et le smoke test tourne à chaque `monl run`.
            if server.stderr:
                server.stderr.close()
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    return (not errors), errors, warnings

__all__ = [
    "_identifiant_smoke",
    "_sample_value",
    "run_smoke_test",
]
