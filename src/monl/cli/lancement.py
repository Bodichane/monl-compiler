"""`monl run` : monter le site sur /site du serveur qui porte déjà l'API."""

import os
import subprocess
import sys

from ..serving import rendre_wrapper
from . import coherence, emplacement


def cmd_run(project_dir, check_only=False, port=8000, skip_smoke=False):
    ok, errors, warnings = coherence.check_coherence(project_dir)
    for w in warnings:
        print(f" ⚠️  {w}")
    if not ok:
        for e in errors:
            print(f" ❌ {e}")
        sys.exit(1)
    print(" ✅ Cohérence statique vérifiée (spec ↔ backend ↔ contrat ↔ frontend).")

    # Point 1 du pivot : la cohérence statique ne garantit pas que ça
    # FONCTIONNE. Smoke test comportemental sur serveur éphémère (base
    # neuve, données réelles intouchées) : routes du contrat éprouvées en
    # HTTP réel, frontend exécuté dans jsdom si Node est disponible.
    if not skip_smoke:
        from ..smoke_test import run_smoke_test
        print(" -> Smoke test comportemental (serveur éphémère, base neuve)…")
        smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir)
        for w in smoke_warnings:
            print(f" ⚠️  {w}")
        if not smoke_ok:
            for e in smoke_errors:
                print(f" ❌ {e}")
            print(" ❌ Smoke test échoué — l'application ne sera pas lancée "
                  "(contourner en connaissance de cause : --skip-smoke).")
            sys.exit(1)
        print(" ✅ Smoke test réussi : l'API répond conformément au contrat"
              + (" et le frontend s'exécute sans erreur." if os.path.isdir(
                  os.path.join(os.path.abspath(project_dir), "frontend")) else "."))
    if check_only:
        return

    project_dir = os.path.abspath(project_dir)
    has_frontend = os.path.isdir(os.path.join(project_dir, "frontend"))
    assets_dir = emplacement._assets_dir_du_projet(project_dir)
    # POINT 133 : TOUJOURS `serve:app`, avec ou sans frontend. Le wrapper sait
    # désormais démarrer sans lui — et lancer `app:app` ici pendant que l'image
    # Docker lance `serve:app` ferait deux comportements pour un seul projet,
    # dont un seul serait éprouvé.
    #
    # POINT 134 : mais il n'est PLUS réécrit à chaque lancement. Il l'était,
    # et depuis qu'il est scellé cette réécriture retournait contre le projet :
    # qu'une version ultérieure de monl change le rendu du wrapper, et 'monl
    # run' écrivait un texte que `monl.json` ne reconnaît pas — le lancement
    # SUIVANT refusait de démarrer en accusant à tort une « modification à la
    # main ». Une commande qui invalide l'état qu'elle vient de vérifier.
    #
    # Il n'est donc écrit que s'il MANQUE, ou si l'état ne le scelle pas —
    # c'est-à-dire pour un projet compilé par un monl antérieur, qui n'a rien
    # à contredire. Un wrapper scellé vient d'être vérifié à l'octet par la
    # cohérence : le réécrire n'apporterait rien. Le rafraîchir reste le
    # travail de 'monl update', qui recompile ET réenregistre l'empreinte.
    wrapper = os.path.join(project_dir, "serve.py")
    etat = emplacement._load_state(project_dir) or {}
    scelle = "serve.py" in (etat.get("backend_sha256") or {})
    if not os.path.exists(wrapper) or not scelle:
        with open(wrapper, "w", encoding="utf-8") as fh:
            fh.write(rendre_wrapper(assets_dir))
    module = "serve:app"
    if has_frontend:
        print(f" -> Frontend monté sur http://127.0.0.1:{port}/site")
        if assets_dir and os.path.isdir(os.path.join(project_dir, assets_dir)):
            print(f" -> Assets ({assets_dir}/) montés sur "
                  f"http://127.0.0.1:{port}/site/{assets_dir}/")
    else:
        print(" -> Aucun frontend : l'API répond, /site renverra 404 "
              "(construire l'interface avec 'monl frontend').")
    print(f" -> Lancement : uvicorn {module} (port {port})")
    subprocess.run([sys.executable, "-m", "uvicorn", module,
                    "--host", "127.0.0.1", "--port", str(port)], cwd=project_dir)
