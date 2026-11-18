"""The verifier: an EPHEMERAL server, real calls, a real jsdom.

It starts in a temporary folder and NEVER touches the project's app.db. A
skipped test does not say "nothing to check here", it says "I did not
check" (point 140)."""

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


def _wrapper_necessaire(has_frontend, has_assets):
    """The smoke test mounts the project the way `monl run` will (point 83).

    Declared assets without a frontend — the normal state just after
    `monl compile`, before any `monl frontend` — also require the wrapper:
    served by bare `app:app`, they answered 404 and `monl run --check` refused
    a healthy application (found while fixing issue #82)."""
    return has_frontend or has_assets


def run_smoke_test(project_dir, say=print):
    """Returns (ok, errors, warnings). Raises only on an internal bug."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)
    with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
        contract = json.load(fh)

    workdir = tempfile.mkdtemp(prefix="monl_smoke_")
    try:
        # Copy of the artifacts: fresh database, real data untouched.
        for name in ("app.py", "schema.sql", "sandbox_ai.py", ".jwt_secret"):
            src = os.path.join(project_dir, name)
            if os.path.exists(src):
                shutil.copy2(src, workdir)
        frontend_src = os.path.join(project_dir, "frontend")
        has_frontend = os.path.isdir(frontend_src)
        if has_frontend:
            shutil.copytree(frontend_src, os.path.join(workdir, "frontend"))
        # ADDED (brick 13, point 83): the declared assets are copied and
        # SERVED, through the same wrapper as 'monl run'. Until then the smoke
        # test ran `app:app`: neither /site nor the assets went through HTTP,
        # so "served" was checked nowhere — only the eye, on the page, would
        # have seen a misplaced mount.
        assets_dir = (contract.get("assets") or {}).get("dir")
        assets_src = os.path.join(project_dir, assets_dir) if assets_dir else None
        has_assets = bool(assets_src and os.path.isdir(assets_src))
        if has_assets:
            shutil.copytree(assets_src, os.path.join(workdir, assets_dir))
        module = "app:app"
        if _wrapper_necessaire(has_frontend, has_assets):
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
                    raise fondations.SmokeFailure("the temporary server stopped during startup: "
                                       + server.stderr.read().decode(errors="replace")[-400:])
                time.sleep(0.2)
            else:
                raise fondations.SmokeFailure("the temporary server never responded on /docs")

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
            # `stderr=PIPE` opens a descriptor that neither terminate() nor
            # wait() closes. Without this close, every smoke test leaves one
            # behind — and the smoke test runs on every `monl run`.
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
