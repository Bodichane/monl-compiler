"""Measurement: do the plugin's interface skills improve the frontend?

Two arms, identical in everything but one point:
  - "avec" (with): Claude Code loads the plugin (``--plugin-dir plugin``);
  - "sans" (without): no monl plugin.
The plugins installed on the machine are disabled in BOTH arms
(``design@synced`` would otherwise bring its own design skills), and user
settings are not loaded. Check the isolation with ``--sonde`` before any
paid measurement.

The instruction is the same in both arms and names no skill: build the
frontend of an already compiled monl project.

The grade comes from no AI judge: monl measures it itself.
  - ``monl run --check``: consistency + real smoke test (jsdom), exit code;
  - coverage: contract routes really called by frontend/
    (``couverture._frontend_fetch_calls`` and ``_route_est_appelee``, the
    functions monl's own check already uses);
  - cost, turns and duration reported by ``claude -p --output-format json``.

Usage:
  python3 outils/mesure_competences.py --sonde
  python3 outils/mesure_competences.py --noter demo            # validates the grade
  python3 outils/mesure_competences.py --essais 2 --sortie /tmp/mesure \\
      exemples/02_boutique.ml exemples/04_kanban.ml

Each attempt is a complete frontend build by Claude, paid on the account of
whoever runs it: the number of attempts is announced before starting.
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

from monl.cli import coverage  # noqa: E402

PLUGIN = Path(os.environ.get("MONL_PLUGIN_MESURE", RACINE / "plugin"))
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
# `Skill` is allowed in BOTH arms: otherwise a loaded skill would be refused,
# and the "with" arm would measure the refusal, not the skill.
OUTILS = ("Read,Write,Edit,Glob,Grep,Skill,Bash(monl run:*),Bash(ls:*),Bash(cat:*),"
          "Bash(python3:*)")
MONL = [sys.executable, "-c", "import sys; from monl.cli import main; "
        "sys.argv[0] = 'monl'; main()"]


def _claude(dossier, avec_plugin, consigne, tours=60, delai=1800, outils=OUTILS):
    commande = ["claude", "-p", consigne, "--output-format", "stream-json", "--verbose",
                "--settings", REGLAGES, "--setting-sources", "project",
                "--permission-mode", "acceptEdits", "--allowedTools", outils,
                "--max-turns", str(tours)]
    if avec_plugin:
        commande += ["--plugin-dir", str(PLUGIN)]
    debut = time.monotonic()
    rendu = subprocess.run(commande, cwd=dossier, capture_output=True, text=True,
                           timeout=delai, stdin=subprocess.DEVNULL)
    resultat = _lire_flux(rendu.stdout)
    if resultat is None:
        resultat = {"is_error": True, "result": rendu.stdout[-2000:] + rendu.stderr[-2000:],
                    "outils": {}, "competences": []}
    resultat["duree_s"] = round(time.monotonic() - debut, 1)
    return resultat


def _lire_flux(texte):
    """Reads the stream-json flow: final result + every tool call.

    The result alone does not say whether a skill was loaded: the `Skill`
    calls themselves are needed, hence the full stream.
    """
    outils, competences, final = {}, [], None
    for ligne in texte.splitlines():
        try:
            evenement = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        if evenement.get("type") == "result":
            final = evenement
        if evenement.get("type") != "assistant":
            continue
        for bloc in evenement.get("message", {}).get("content", []):
            if bloc.get("type") != "tool_use":
                continue
            outils[bloc["name"]] = outils.get(bloc["name"], 0) + 1
            if bloc["name"] == "Skill":
                competences.append(bloc.get("input", {}).get("skill", "?"))
    if final is None:
        return None
    return {**final, "outils": outils, "competences": competences}


def sonde():
    """Lists the skills each arm sees: only monl's may differ."""
    question = ("List the names of every skill available to you via the Skill "
                "tool, one per line, nothing else.")
    vues = {}
    for bras, avec in (("sans", False), ("avec", True)):
        dossier = Path(os.environ.get("TMPDIR", "/tmp")) / f"sonde-{bras}"
        dossier.mkdir(parents=True, exist_ok=True)
        texte = _claude(dossier, avec, question, tours=3, delai=300).get("result", "")
        vues[bras] = {ligne.strip() for ligne in texte.splitlines() if ligne.strip()}
    difference = sorted(vues["avec"] ^ vues["sans"])
    print("Skills specific to a single arm:", *difference, sep="\n  ")
    hors_monl = [nom for nom in difference if not nom.startswith("monl-compiler:")]
    assert vues["sans"], "the \"sans\" arm listed no skill: silent probe"
    assert not hors_monl, f"isolation broken, differences outside monl: {hors_monl}"
    assert difference, "no difference: the plugin is not loaded in \"avec\""
    print("Isolation verified.")


def noter(dossier):
    """Grades a compiled project that has a frontend, with monl's measurements."""
    dossier = Path(dossier)
    contrat = json.loads((dossier / "frontend_contract.json").read_text(encoding="utf-8"))
    routes = [r for r in contrat.get("routes", []) if r["path"] != "/paiement/webhook"]
    appels = coverage._frontend_fetch_calls(str(dossier / "frontend"))
    couvertes = sum(1 for route in routes if coverage._route_est_appelee(route, appels))
    verif = subprocess.run(MONL + ["run", str(dossier), "--check"], capture_output=True,
                           text=True, timeout=600, stdin=subprocess.DEVNULL)
    sortie = verif.stdout + verif.stderr
    fichiers = [f for f in (dossier / "frontend").rglob("*") if f.is_file()] \
        if (dossier / "frontend").is_dir() else []
    present = (dossier / "frontend" / "index.html").is_file()
    return {
        # Without a frontend, `monl run --check` passes (only the API is
        # served): a missing frontend is a FAILED build, never a success.
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
        raise SystemExit(f"cannot compile {spec}:\n{rendu.stdout[-2000:]}")
    return cible / "projet"


def mesurer(specs, essais, sortie):
    sortie = Path(sortie).resolve()
    if (Path.home() / ".claude") in (sortie, *sortie.parents):
        raise SystemExit("the output cannot be under ~/.claude/: Claude Code refuses "
                         "every write there, and each attempt would return an empty frontend")
    total = len(specs) * 2 * essais
    print(f"{total} frontend builds are about to start "
          f"({len(specs)} project(s) × 2 arms × {essais} attempt(s)).")
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
                    # A refused write measures the harness, not the skills:
                    # better to stop than to grade an empty frontend.
                    raise SystemExit(f"write refused in {dossier}: {ecritures[:2]}")
                coupe = "session limit" in str(execution.get("result", "")).lower()
                if execution.get("is_error") and (coupe or not execution.get("total_cost_usd")):
                    # Claude did nothing, or was CUT OFF on the way by the
                    # usage limit: it is not a failed attempt, it is an attempt
                    # that did not happen — even if it already cost a few
                    # turns.
                    raise SystemExit(f"Claude did not work in {dossier}: "
                                     f"{str(execution.get('result'))[:200]}")
                note = noter(dossier)
                ligne = {"projet": spec.stem, "bras": bras, "essai": essai, **note,
                         "cout_usd": execution.get("total_cost_usd"),
                         "tours": execution.get("num_turns"),
                         "duree_s": execution["duree_s"],
                         "refus_bash": len(refus),
                         "competences": execution.get("competences", []),
                         "erreur_claude": execution.get("is_error", False)}
                lignes.append(ligne)
                (sortie / "resultats.json").write_text(
                    json.dumps(lignes, indent=2, ensure_ascii=False), encoding="utf-8")
                print(f"   check={'OK' if ligne['check_ok'] else 'FAILED'} "
                      f"routes={ligne['routes_couvertes']}/{ligne['routes_total']} "
                      f"cost={ligne['cout_usd']} turns={ligne['tours']}", flush=True)
    _resumer(lignes)


def _resumer(lignes):
    print("\nproject       arm   check  coverage    mean cost  turns")
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
    parser.add_argument("specs", nargs="*", help=".ml specs to measure")
    parser.add_argument("--essais", type=int, default=2)
    parser.add_argument("--sortie", default=str(Path.home() / "mesure-competences"),
                        help="outside ~/.claude/, where Claude Code refuses to write")
    parser.add_argument("--sonde", action="store_true", help="check the arms' isolation")
    parser.add_argument("--noter", metavar="DOSSIER", help="grade an existing project")
    args = parser.parse_args()
    if args.sonde:
        return sonde()
    if args.noter:
        return print(json.dumps(noter(args.noter), indent=2, ensure_ascii=False))
    if not args.specs:
        parser.error("give at least one spec, or --sonde / --noter")
    return mesurer(args.specs, args.essais, args.sortie)


if __name__ == "__main__":
    main()
