"""Mesure : les compétences d'interface du plugin améliorent-elles le frontend ?

Deux bras, identiques en tout sauf un point :
  - « avec » : Claude Code charge le plugin (``--plugin-dir plugin``) ;
  - « sans » : aucun plugin monl.
Les plugins installés sur la machine sont désactivés dans les DEUX bras
(``design@synced`` apporterait sinon ses propres compétences de design), et
les réglages utilisateur ne sont pas chargés. Vérifier l'isolation avec
``--sonde`` avant toute mesure payante.

La consigne est la même dans les deux bras et ne nomme aucune compétence :
construire le frontend d'un projet monl déjà compilé.

La note ne vient d'aucun juge IA : elle est mesurée par monl lui-même.
  - ``monl run --check`` : cohérence + smoke test réel (jsdom), code de sortie ;
  - couverture : routes du contrat réellement appelées par frontend/
    (``couverture._frontend_fetch_calls`` et ``_route_est_appelee``, les
    fonctions que la vérification de monl utilise déjà) ;
  - coût, tours et durée rapportés par ``claude -p --output-format json``.

Usage :
  python3 outils/mesure_competences.py --sonde
  python3 outils/mesure_competences.py --noter demo            # valide la note
  python3 outils/mesure_competences.py --essais 2 --sortie /tmp/mesure \\
      exemples/02_boutique.ml exemples/04_kanban.ml

Chaque essai est une construction complète de frontend par Claude, payée sur
le compte de celui qui lance : le nombre d'essais est annoncé avant de partir.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE / "src"))

from monl.cli import couverture  # noqa: E402

PLUGIN = RACINE / "plugin"
REGLAGES = json.dumps({"enabledPlugins": {
    "design@synced": False,
    "ui-ux-pro-max@ui-ux-pro-max-skill": False,
}})
CONSIGNE = (
    "Build the web frontend for the monl project in the current directory. "
    "Read docs/FRONTEND_PROMPT.md and frontend_contract.json first; the contract is "
    "the source of truth. Write files only in frontend/. When you are done, run "
    "`monl run . --check` and fix every failure it reports, then stop."
)
OUTILS = "Read,Write,Edit,Glob,Grep,Bash(monl run:*),Bash(ls:*),Bash(cat:*)"
MONL = [sys.executable, "-c", "import sys; from monl.cli import main; "
        "sys.argv[0] = 'monl'; main()"]


def _claude(dossier, avec_plugin, consigne, tours=60, delai=1800):
    commande = ["claude", "-p", consigne, "--output-format", "json",
                "--settings", REGLAGES, "--setting-sources", "project",
                "--permission-mode", "acceptEdits", "--allowedTools", OUTILS,
                "--max-turns", str(tours)]
    if avec_plugin:
        commande += ["--plugin-dir", str(PLUGIN)]
    debut = time.monotonic()
    rendu = subprocess.run(commande, cwd=dossier, capture_output=True, text=True,
                           timeout=delai, stdin=subprocess.DEVNULL)
    duree = time.monotonic() - debut
    try:
        resultat = json.loads(rendu.stdout)
    except json.JSONDecodeError:
        resultat = {"is_error": True, "result": rendu.stdout[-2000:] + rendu.stderr[-2000:]}
    resultat["duree_s"] = round(duree, 1)
    return resultat


def sonde():
    """Liste les compétences vues par chaque bras : seule celles de monl diffèrent."""
    question = ("List the names of every skill available to you via the Skill "
                "tool, one per line, nothing else.")
    vues = {}
    for bras, avec in (("sans", False), ("avec", True)):
        dossier = Path(os.environ.get("TMPDIR", "/tmp")) / f"sonde-{bras}"
        dossier.mkdir(parents=True, exist_ok=True)
        texte = _claude(dossier, avec, question, tours=3, delai=300).get("result", "")
        vues[bras] = {ligne.strip() for ligne in texte.splitlines() if ligne.strip()}
    difference = sorted(vues["avec"] ^ vues["sans"])
    print("Compétences propres à un seul bras :", *difference, sep="\n  ")
    hors_monl = [nom for nom in difference if not nom.startswith("monl-compiler:")]
    assert vues["sans"], "le bras « sans » n'a listé aucune compétence : sonde muette"
    assert not hors_monl, f"isolation rompue, différences hors monl : {hors_monl}"
    assert difference, "aucune différence : le plugin n'est pas chargé dans « avec »"
    print("Isolation vérifiée.")


def noter(dossier):
    """Note un projet compilé muni d'un frontend, par les mesures de monl."""
    dossier = Path(dossier)
    contrat = json.loads((dossier / "frontend_contract.json").read_text(encoding="utf-8"))
    routes = [r for r in contrat.get("routes", []) if r["path"] != "/paiement/webhook"]
    appels = couverture._frontend_fetch_calls(str(dossier / "frontend"))
    couvertes = sum(1 for route in routes if couverture._route_est_appelee(route, appels))
    verif = subprocess.run(MONL + ["run", str(dossier), "--check"], capture_output=True,
                           text=True, timeout=600, stdin=subprocess.DEVNULL)
    sortie = verif.stdout + verif.stderr
    fichiers = [f for f in (dossier / "frontend").rglob("*") if f.is_file()] \
        if (dossier / "frontend").is_dir() else []
    present = (dossier / "frontend" / "index.html").is_file()
    return {
        # Sans frontend, `monl run --check` passe (l'API seule est servie) :
        # un frontend absent est un ÉCHEC de la construction, jamais une réussite.
        "check_ok": present and verif.returncode == 0,
        "frontend_present": present,
        "routes_couvertes": couvertes,
        "routes_total": len(routes),
        "couverture": round(couvertes / len(routes), 3) if routes else None,
        "frontend_octets": sum(f.stat().st_size for f in fichiers),
        "check_extrait": sortie[-1500:],
    }


def _compiler(spec, cible):
    cible.mkdir(parents=True, exist_ok=True)
    shutil.copy(spec, cible / spec.name)
    assets = spec.parent / "assets"
    if assets.is_dir():
        shutil.copytree(assets, cible / "assets", dirs_exist_ok=True)
    rendu = subprocess.run(MONL + ["compile", spec.name, "--output", "projet"], cwd=cible,
                           capture_output=True, text=True, timeout=300,
                           stdin=subprocess.DEVNULL)
    if rendu.returncode != 0:
        raise SystemExit(f"compilation de {spec} impossible :\n{rendu.stdout[-2000:]}")
    return cible / "projet"


def mesurer(specs, essais, sortie):
    sortie = Path(sortie).resolve()
    if (Path.home() / ".claude") in (sortie, *sortie.parents):
        raise SystemExit("la sortie ne peut pas être sous ~/.claude/ : Claude Code y refuse "
                         "toute écriture, et chaque essai rendrait un frontend vide")
    total = len(specs) * 2 * essais
    print(f"{total} constructions de frontend vont être lancées "
          f"({len(specs)} projet(s) × 2 bras × {essais} essai(s)).")
    lignes = []
    for spec in map(Path, specs):
        base = _compiler(spec, sortie / spec.stem / "base")
        for essai in range(1, essais + 1):
            for bras, avec in (("sans", False), ("avec", True)):
                dossier = sortie / spec.stem / f"{bras}-{essai}"
                shutil.rmtree(dossier, ignore_errors=True)
                shutil.copytree(base, dossier)
                print(f"→ {spec.stem} {bras} #{essai}…", flush=True)
                execution = _claude(dossier, avec, CONSIGNE)
                (dossier / "_claude.json").write_text(
                    json.dumps(execution, indent=2, ensure_ascii=False), encoding="utf-8")
                refus = execution.get("permission_denials") or []
                ecritures = [r for r in refus if r.get("tool_name") in ("Write", "Edit")]
                if ecritures:
                    # Une écriture refusée mesure le harnais, pas les compétences :
                    # mieux vaut s'arrêter que noter un frontend vide.
                    raise SystemExit(f"écriture refusée dans {dossier} : {ecritures[:2]}")
                if execution.get("is_error") and not execution.get("total_cost_usd"):
                    # Claude n'a rien fait (limite d'usage, panne) : ce n'est pas un
                    # essai raté, c'est un essai qui n'a pas eu lieu.
                    raise SystemExit(f"Claude n'a pas travaillé dans {dossier} : "
                                     f"{str(execution.get('result'))[:200]}")
                note = noter(dossier)
                ligne = {"projet": spec.stem, "bras": bras, "essai": essai, **note,
                         "cout_usd": execution.get("total_cost_usd"),
                         "tours": execution.get("num_turns"),
                         "duree_s": execution["duree_s"],
                         "refus_bash": len(refus),
                         "erreur_claude": execution.get("is_error", False)}
                lignes.append(ligne)
                (sortie / "resultats.json").write_text(
                    json.dumps(lignes, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"   check={'OK' if ligne['check_ok'] else 'ÉCHEC'} "
                      f"routes={ligne['routes_couvertes']}/{ligne['routes_total']} "
                      f"coût={ligne['cout_usd']} tours={ligne['tours']}", flush=True)
    _resumer(lignes)


def _resumer(lignes):
    print("\nprojet        bras  check  couverture  coût moyen  tours")
    for projet in sorted({ligne["projet"] for ligne in lignes}):
        for bras in ("sans", "avec"):
            groupe = [ligne for ligne in lignes
                      if ligne["projet"] == projet and ligne["bras"] == bras]
            if not groupe:
                continue
            check = sum(ligne["check_ok"] for ligne in groupe)
            couv = statistics.mean(ligne["couverture"] or 0 for ligne in groupe)
            couts = [ligne["cout_usd"] for ligne in groupe if ligne["cout_usd"] is not None]
            tours = [ligne["tours"] for ligne in groupe if ligne["tours"] is not None]
            print(f"{projet:13} {bras:5} {check}/{len(groupe):<4} {couv:>9.0%}  "
                  f"{statistics.mean(couts) if couts else float('nan'):>9.2f}  "
                  f"{statistics.mean(tours) if tours else float('nan'):>5.0f}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("specs", nargs="*", help="specs .ml à mesurer")
    parser.add_argument("--essais", type=int, default=2)
    parser.add_argument("--sortie", default=str(Path.home() / "mesure-competences"),
                        help="hors de ~/.claude/, où Claude Code refuse d'écrire")
    parser.add_argument("--sonde", action="store_true", help="vérifier l'isolation des bras")
    parser.add_argument("--noter", metavar="DOSSIER", help="noter un projet existant")
    args = parser.parse_args()
    if args.sonde:
        return sonde()
    if args.noter:
        return print(json.dumps(noter(args.noter), indent=2, ensure_ascii=False))
    if not args.specs:
        parser.error("donner au moins une spec, ou --sonde / --noter")
    return mesurer(args.specs, args.essais, args.sortie)


if __name__ == "__main__":
    main()
