"""Blind design judgment of the frontends produced by mesure_competences.

monl's grade says whether a frontend WORKS (check, routes); it says nothing of
its visual quality — what the interface skills claim to improve. This module
judges it, with three precautions:
  - the judge only sees screenshots named A and B, in a neutral folder: no
    path, no arm name, no code;
  - each pair is judged IN BOTH ORDERS: a judge who always prefers the first
    image contradicts itself, and its preference cancels out instead of
    passing for a result;
  - every sans-i × avec-j pair of a project is judged, never a single one.

Usage:
  python3 outils/juge_design.py ~/mesure-competences-portfolio
"""

from __future__ import annotations

import itertools
import json
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import mesure_competences as mesure

NAVIGATEUR = next(iter(sorted(Path.home().glob(
    ".cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-linux64/"
    "chrome-headless-shell"))), None)
FORMATS = {"bureau": "1280,2400", "mobile": "390,1800"}
CONSIGNE_JUGE = (
    "You are a senior product designer. In this directory there are screenshots of two "
    "websites built from the same specification: A_bureau.png and A_mobile.png, "
    "B_bureau.png and B_mobile.png (bureau = desktop, mobile = phone). Read all four "
    "images. Compare ONLY visual design quality: hierarchy, typography, spacing and "
    "rhythm, color, consistency, polish, how distinctive and professional it looks, and "
    "the mobile layout. Ignore which content is shown. End your answer with one line of "
    'JSON exactly like {"winner": "A"} or {"winner": "B"} or {"winner": "tie"}.'
)


def _port_libre():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def capturer(projet, cible):
    """Serves the project through its own serve.py and screenshots /site/."""
    if NAVIGATEUR is None:
        raise SystemExit("chrome-headless-shell not found in ~/.cache/ms-playwright")
    copie = Path(tempfile.mkdtemp(prefix="juge-"))
    shutil.copytree(projet, copie / "p", ignore=shutil.ignore_patterns("*.db", "_claude.json"))
    port = _port_libre()
    serveur = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "serve:app", "--host", "127.0.0.1",
         "--port", str(port)], cwd=copie / "p", stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL)
    adresse = f"http://127.0.0.1:{port}/site/"
    try:
        for _ in range(60):
            try:
                if urllib.request.urlopen(adresse, timeout=2).status == 200:
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise SystemExit(f"{projet}: /site/ does not answer")
        for nom, taille in FORMATS.items():
            image = cible / f"{nom}.png"
            image.unlink(missing_ok=True)
            for _ in range(2):
                # The headless browser sometimes hangs on a page that was
                # nonetheless captured on the previous pass: retry once.
                try:
                    subprocess.run([str(NAVIGATEUR), "--no-sandbox", "--hide-scrollbars",
                                    f"--window-size={taille}", "--virtual-time-budget=6000",
                                    f"--screenshot={image}", adresse],
                                   capture_output=True, timeout=90, check=False)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if not image.is_file() or image.stat().st_size < 5000:
                # Judging an empty capture would invent a grade: stop.
                raise SystemExit(f"screenshot {nom} of {projet} empty or missing")
    finally:
        serveur.terminate()
        serveur.wait(timeout=10)
        shutil.rmtree(copie, ignore_errors=True)


def _verdict(texte):
    """The LAST {"winner": …} of the answer, wherever it is written."""
    trouves = re.findall(r'\{\s*"winner"\s*:\s*"(A|B|tie)"\s*\}', texte)
    return trouves[-1] if trouves else None


def juger_paire(captures_a, captures_b, journal):
    """One comparison: 'A', 'B', 'tie' or None, and its cost.

    An unreadable verdict (turns exhausted before the conclusion) is retried
    once; the raw answer is kept in `journal` so it can be reread.
    """
    neutre = Path(tempfile.mkdtemp(prefix="paire-"))
    cout, gagnant = 0.0, None
    try:
        for lettre, source in (("A", captures_a), ("B", captures_b)):
            for nom in FORMATS:
                shutil.copy(source / f"{nom}.png", neutre / f"{lettre}_{nom}.png")
        for _ in range(2):
            rendu = mesure._claude(neutre, False, CONSIGNE_JUGE, tours=15, delai=600,
                                   outils="Read")
            cout += rendu.get("total_cost_usd") or 0
            texte = str(rendu.get("result", ""))
            with journal.open("a", encoding="utf-8") as f:
                f.write(f"## {captures_a.name} (A) vs {captures_b.name} (B) — "
                        f"{rendu.get('subtype')}\n{texte}\n\n")
            gagnant = _verdict(texte)
            if gagnant:
                break
    finally:
        shutil.rmtree(neutre, ignore_errors=True)
    return gagnant, cout


def juger(racine):
    racine = Path(racine).resolve()
    # Only the attempts whose `monl run --check` passed are judged: the beauty
    # of a broken (or interrupted) frontend says nothing about a skill.
    lignes = json.loads((racine / "resultats.json").read_text(encoding="utf-8"))
    retenus = {}
    for ligne in lignes:
        if ligne["check_ok"]:
            nom = f"{ligne['bras']}-{ligne['essai']}"
            retenus.setdefault(ligne["projet"], {})[nom] = racine / ligne["projet"] / nom
    if not retenus:
        raise SystemExit(f"no successful attempt to judge under {racine}")
    bilan, cout = {}, 0.0
    for projet, essais in sorted(retenus.items()):
        captures = racine / "_captures" / projet
        for nom, dossier in essais.items():
            (captures / nom).mkdir(parents=True, exist_ok=True)
            capturer(dossier, captures / nom)
        sans = [n for n in essais if n.startswith("sans")]
        avec = [n for n in essais if n.startswith("avec")]
        compte = {"avec": 0, "sans": 0, "egal": 0, "illisible": 0}
        for s, a in itertools.product(sans, avec):
            # Both orders: a position bias cancels out instead of counting.
            for premier, second in ((s, a), (a, s)):
                gagnant, prix = juger_paire(captures / premier, captures / second,
                                            captures / "verdicts.md")
                cout += prix
                choisi = {"A": premier, "B": second}.get(gagnant)
                cle = ("illisible" if gagnant is None else "egal" if gagnant == "tie"
                       else choisi.split("-")[0])
                compte[cle] += 1
                print(f"{projet} {premier} vs {second} → {gagnant} ({cle})", flush=True)
        bilan[projet] = compte
    (racine / "jugement.json").write_text(json.dumps(bilan, indent=2), encoding="utf-8")
    print("\nproject       avec  sans  tie   unreadable")
    for projet, c in bilan.items():
        print(f"{projet:13} {c['avec']:>4}  {c['sans']:>4}  {c['egal']:>4}  {c['illisible']:>9}")
    print(f"judging cost: {cout:.2f} $")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    juger(sys.argv[1])
