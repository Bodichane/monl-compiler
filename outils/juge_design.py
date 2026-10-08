"""Jugement du design, à l'aveugle, des frontends produits par mesure_competences.

La note de monl dit si un frontend MARCHE (check, routes) ; elle ne dit rien de
sa qualité visuelle — ce que les compétences d'interface prétendent améliorer.
Ce module la juge, avec trois précautions :
  - le juge ne voit que des captures nommées A et B, dans un dossier neutre :
    ni chemin, ni nom de bras, ni code ;
  - chaque paire est jugée DANS LES DEUX ORDRES : un juge qui préfère toujours
    la première image se contredit, et sa préférence s'annule au lieu de
    passer pour un résultat ;
  - toutes les paires sans-i × avec-j d'un projet sont jugées, jamais une seule.

Usage :
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
    """Sert le projet par son propre serve.py et photographie /site/."""
    if NAVIGATEUR is None:
        raise SystemExit("chrome-headless-shell introuvable dans ~/.cache/ms-playwright")
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
            raise SystemExit(f"{projet} : /site/ ne répond pas")
        for nom, taille in FORMATS.items():
            image = cible / f"{nom}.png"
            image.unlink(missing_ok=True)
            for _ in range(2):
                # Le navigateur headless se bloque parfois sur une page qui a
                # pourtant été capturée au passage précédent : on retente une fois.
                try:
                    subprocess.run([str(NAVIGATEUR), "--no-sandbox", "--hide-scrollbars",
                                    f"--window-size={taille}", "--virtual-time-budget=6000",
                                    f"--screenshot={image}", adresse],
                                   capture_output=True, timeout=90, check=False)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if not image.is_file() or image.stat().st_size < 5000:
                # Une capture vide jugée serait une note inventée : on s'arrête.
                raise SystemExit(f"capture {nom} de {projet} vide ou absente")
    finally:
        serveur.terminate()
        serveur.wait(timeout=10)
        shutil.rmtree(copie, ignore_errors=True)


def _verdict(texte):
    """Le DERNIER {"winner": …} de la réponse, où qu'il soit écrit."""
    trouves = re.findall(r'\{\s*"winner"\s*:\s*"(A|B|tie)"\s*\}', texte)
    return trouves[-1] if trouves else None


def juger_paire(captures_a, captures_b, journal):
    """Une comparaison : 'A', 'B', 'tie' ou None, et son coût.

    Un verdict illisible (tours épuisés avant la conclusion) est retenté une
    fois ; la réponse brute est gardée dans `journal` pour pouvoir le relire.
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
    # Seuls les essais dont `monl run --check` est passé sont jugés : la beauté
    # d'un frontend cassé (ou interrompu) ne dit rien d'une compétence.
    lignes = json.loads((racine / "resultats.json").read_text(encoding="utf-8"))
    retenus = {}
    for ligne in lignes:
        if ligne["check_ok"]:
            nom = f"{ligne['bras']}-{ligne['essai']}"
            retenus.setdefault(ligne["projet"], {})[nom] = racine / ligne["projet"] / nom
    if not retenus:
        raise SystemExit(f"aucun essai réussi à juger sous {racine}")
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
            # Les deux ordres : un biais de position s'annule au lieu de compter.
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
    print("\nprojet        avec  sans  égal  illisible")
    for projet, c in bilan.items():
        print(f"{projet:13} {c['avec']:>4}  {c['sans']:>4}  {c['egal']:>4}  {c['illisible']:>9}")
    print(f"coût du jugement : {cout:.2f} $")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    juger(sys.argv[1])
