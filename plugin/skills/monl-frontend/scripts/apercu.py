#!/usr/bin/env python3
"""Capture le frontend monl sans modifier le projet source."""

import argparse
import glob
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def navigateur():
    impose = os.environ.get("MONL_BROWSER")
    if impose is not None:
        candidats = [impose]
    else:
        candidats = sorted(glob.glob(os.path.expanduser(
            "~/.cache/ms-playwright/chromium_headless_shell-*/"
            "chrome-headless-shell-linux64/chrome-headless-shell"
        ))) + ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]
    for candidat in candidats:
        trouve = shutil.which(candidat)
        if trouve:
            return trouve
    return None


def arreter(processus):
    """Récolte le processus et arrête aussi ses éventuels descendants."""
    try:
        os.killpg(processus.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        processus.wait(timeout=5)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(processus.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    processus.wait()


def capturer(browser, url, destination, dimensions, profil, journal):
    for tentative in range(2):
        destination.unlink(missing_ok=True)
        commande = [browser]
        if "headless-shell" not in Path(browser).name:
            commande.append("--headless=new")
        commande += [
            "--no-sandbox", "--hide-scrollbars", "--virtual-time-budget=6000",
            f"--window-size={dimensions}", f"--screenshot={destination}",
            f"--user-data-dir={profil}", url,
        ]
        processus = subprocess.Popen(
            commande, stdout=journal, stderr=subprocess.STDOUT, start_new_session=True
        )
        bloque = False
        try:
            code = processus.wait(timeout=90)
        except subprocess.TimeoutExpired:
            bloque = True
        finally:
            arreter(processus)
        if bloque:
            if tentative == 0:
                print("Screenshot stalled: retrying.", file=sys.stderr)
                continue
            raise RuntimeError(f"Screenshot stalled twice: {destination.name}")
        if code != 0 or not destination.is_file() or destination.stat().st_size < 5000:
            raise RuntimeError(f"Screenshot missing, too small or failed: {destination.name}")
        return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("projet", nargs="?", default=".")
    parser.add_argument("--sortie")
    args = parser.parse_args()
    projet = Path(args.projet).resolve()
    for requis in ("serve.py", "frontend/index.html"):
        if not (projet / requis).is_file():
            print(f"Not a compiled monl project with a frontend: missing {projet / requis}", file=sys.stderr)
            return 2
    browser = navigateur()
    if not browser:
        print("No browser found. Set MONL_BROWSER to a Chrome or Chromium executable, "
              "or install Chromium.", file=sys.stderr)
        return 3
    sortie = Path(args.sortie).resolve() if args.sortie else None
    if sortie is not None and sortie.is_relative_to(projet):
        print("The output directory must be outside the project.", file=sys.stderr)
        return 2
    serveur = None
    try:
        if sortie is None:
            sortie = Path(tempfile.mkdtemp(prefix=f"monl-apercu-{projet.name}-")).resolve()
            if sortie.is_relative_to(projet):
                sortie.rmdir()
                raise RuntimeError("The temporary output directory is inside the project.")
        sortie.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="monl-copie-") as temporaire:
            racine = Path(temporaire)
            copie = racine / "projet"
            shutil.copytree(projet, copie, ignore=shutil.ignore_patterns("*.db"))
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            url = f"http://127.0.0.1:{port}/site/"
            with tempfile.TemporaryFile() as journal:
                try:
                    serveur = subprocess.Popen(
                        [sys.executable, "-m", "uvicorn", "serve:app", "--host",
                         "127.0.0.1", "--port", str(port)],
                        cwd=copie, stdout=journal, stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    limite = time.monotonic() + 30
                    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    while time.monotonic() < limite:
                        if serveur.poll() is not None:
                            break
                        try:
                            with client.open(url, timeout=min(1, limite - time.monotonic())) as reponse:
                                if reponse.status == 200:
                                    break
                        except (urllib.error.URLError, TimeoutError, OSError):
                            pass
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("The server did not answer 200 on /site/ within 30 s.")
                    if serveur.poll() is not None:
                        raise RuntimeError("The server stopped before answering on /site/.")
                    for nom, dimensions in (("bureau", "1280,2400"), ("mobile", "390,1800")):
                        capturer(browser, url, sortie / f"{nom}.png", dimensions,
                                 racine / f"profil-{nom}", journal)
                except (OSError, RuntimeError) as erreur:
                    print(f"Failed: {erreur}", file=sys.stderr)
                    journal.seek(0, os.SEEK_END)
                    journal.seek(max(0, journal.tell() - 8000))
                    print(journal.read().decode(errors="replace"), file=sys.stderr)
                    return 4
                finally:
                    if serveur is not None:
                        arreter(serveur)
    except OSError as erreur:
        print(f"Failed: {erreur}", file=sys.stderr)
        return 4
    print(sortie / "bureau.png")
    print(sortie / "mobile.png")
    print("Open both images with your image-reading tool and fix what you see.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
