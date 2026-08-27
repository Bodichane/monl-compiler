"""`monl run --check` : le site livré tient-il la promesse du contrat.

La détection d'artefacts périmés compare à une RÉGÉNÉRATION, jamais à un
numéro de version — `__version__` n'avait pas bougé pendant les points 74
à 81, un tampon n'aurait rien vu."""

import contextlib
import io
import json
import os
import re
import tempfile

from ..ast_validator import MonlAST
from ..frontend_contract import (
    CONTRACT_FILENAME,
    contract_sha256,
    generate_frontend_contract,
)
from ..generator import MonlSecureGenerator
from ..parser import parse_monl_file
from . import couverture, emplacement, nomenclature


# ------------------------------------------------------------ cohérence ----
def _empreintes_regenerees(spec_path):
    """Empreintes des artefacts qu'une recompilation produirait MAINTENANT,
    ou None si la spec ne compile plus (le contrôle ne doit pas devenir une
    panne : la spec modifiée est déjà signalée par son propre contrôle).

    La recompilation a lieu dans un dossier temporaire — le projet n'est jamais
    touché — et sa sortie est capturée : un contrôle de cohérence n'a pas à
    rejouer l'audit de sécurité à l'écran."""

    empreintes = {}
    with tempfile.TemporaryDirectory() as temporaire:
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                # base_dir = le dossier de la SPEC, pas le dossier temporaire :
                # c'est là que vivent les assets à vérifier (brique 13).
                normalized = MonlAST(
                    parse_monl_file(spec_path),
                    base_dir=os.path.dirname(os.path.abspath(spec_path)),
                ).validate_and_audit()
                generator = MonlSecureGenerator(normalized, output_dir=temporaire)
                generator.generate_all()
                generate_frontend_contract(normalized, generator, temporaire)
        except Exception:
            return None
        for nom in ("app.py", "schema.sql", "sandbox_ai.py", CONTRACT_FILENAME):
            chemin = os.path.join(temporaire, nom)
            if os.path.exists(chemin):
                empreintes[nom] = emplacement._sha256_file(chemin)
    return empreintes

def check_coherence(project_dir):
    """Vérifie que spec, backend, contrat et frontend forment un ensemble
    cohérent. Retourne (ok, erreurs, avertissements)."""
    errors, warnings = [], []
    project_dir = os.path.abspath(project_dir)

    souci = emplacement._erreur_de_chemin(project_dir)
    if souci:
        errors.append(souci.replace(" ❌ ", "").strip())
        return False, errors, warnings

    state = emplacement._load_state(project_dir)
    if state is None:
        errors.append(f"{nomenclature.STATE_FILENAME} introuvable — ce dossier n'est pas un projet "
                      "monl compilé (lancer 'monl' ou 'monl compile').")
        return False, errors, warnings

    spec_path = state["spec"] if os.path.isabs(state["spec"]) \
        else os.path.join(project_dir, state["spec"])
    if not os.path.exists(spec_path):
        errors.append(f"Spec introuvable : {spec_path}")
        return False, errors, warnings

    if emplacement._sha256_file(spec_path) != state["spec_sha256"]:
        errors.append("La spec a été modifiée depuis la dernière compilation — "
                      "lancer 'monl update' pour resynchroniser backend et contrat.")

    for artefact in ("app.py", "schema.sql", CONTRACT_FILENAME):
        if not os.path.exists(os.path.join(project_dir, artefact)):
            errors.append(f"Artefact manquant : {artefact}")
    if errors:
        return False, errors, warnings

    # Le backend est scellé (point 64) : il se régénère depuis la spec, il ne
    # se retouche pas. Un état antérieur à cette empreinte n'est pas une
    # erreur — il est simplement muet, et le dire vaut mieux que laisser
    # croire à une vérification qui n'a pas eu lieu.
    empreintes = state.get("backend_sha256")
    if not empreintes:
        warnings.append("État antérieur au scellé du backend : recompiler "
                        "('monl update') pour que app.py et schema.sql soient "
                        "réellement vérifiés.")
    else:
        for nom, attendu in sorted(empreintes.items()):
            chemin = os.path.join(project_dir, nom)
            # POINT 134 : un artefact ENREGISTRÉ mais ABSENT était ignoré. La
            # boucle ne disait donc rien d'un fichier disparu — et depuis le
            # point 133, 'monl run --check' pouvait certifier « cohérence
            # vérifiée » sur un projet dont le Dockerfile lance `serve:app`
            # alors que le module n'est plus là. Le trou existait aussi pour
            # manage.py et sandbox_ai.py ; il ne se voyait pas parce qu'aucun
            # artefact n'était encore désigné par le conteneur.
            if not os.path.exists(chemin):
                errors.append(
                    f"{nom} est enregistré dans {nomenclature.STATE_FILENAME} mais absent "
                    "du projet — il est généré depuis la spec : recompiler "
                    "('monl update').")
                continue
            if emplacement._sha256_file(chemin) != attendu:
                errors.append(
                    f"{nom} a été modifié à la main — le backend est généré "
                    "depuis la spec. Modifier la spec puis 'monl update' ; "
                    "toute retouche directe sera écrasée.")
        if errors:
            return False, errors, warnings

    if contract_sha256(project_dir) != state["contract_sha256"]:
        errors.append(f"{CONTRACT_FILENAME} a été modifié à la main — le contrat est "
                      "dérivé de la spec, il ne se modifie que via 'monl update'.")
        return False, errors, warnings

    # AJOUT (point 81) : les contrôles ci-dessus comparent aux empreintes
    # ENREGISTRÉES à la compilation. Ils détectent donc une retouche à la main
    # — leur but — et rien d'autre. Un projet dont les artefacts ont été
    # produits par un compilateur ANTÉRIEUR les passait tous, et 'monl run'
    # annonçait « cohérence vérifiée (spec ↔ backend ↔ contrat ↔ frontend) »
    # sur un backend que le compilateur courant n'écrirait plus — y compris
    # après qu'un correctif ait fermé un trou de sécurité.
    #
    # Pourquoi comparer à une RÉGÉNÉRATION plutôt qu'à un numéro de version :
    # `__version__` n'a pas bougé pendant les points 74 à 81, donc un tampon de
    # version n'aurait rien vu. La génération est déterministe (c'est ce sur
    # quoi reposent déjà les empreintes ci-dessus) : recompiler dans un dossier
    # temporaire et comparer dit exactement quels artefacts changeraient.
    #
    # Pourquoi un AVERTISSEMENT et non une erreur : précédent explicite quelques
    # lignes plus haut, pour l'état antérieur au scellé du backend — « il est
    # simplement muet, et le dire vaut mieux que laisser croire à une
    # vérification qui n'a pas eu lieu ». Une erreur bloquerait 'monl run' sur
    # tout projet après n'importe quelle évolution du compilateur, y compris
    # celles qui ne le concernent pas. L'avertissement NOMME les artefacts
    # concernés et la commande qui resynchronise : c'est actionnable en une
    # commande, sans immobiliser une application qui tourne.
    frais = _empreintes_regenerees(spec_path)
    if frais is None:
        warnings.append("Impossible de recompiler la spec pour comparer les artefacts "
                        "au compilateur courant — vérification non effectuée.")
    else:
        perimes = sorted(nom for nom, empreinte in frais.items()
                         if os.path.exists(os.path.join(project_dir, nom))
                         and emplacement._sha256_file(os.path.join(project_dir, nom)) != empreinte)
        if perimes:
            from .. import __version__
            construit_avec = state.get("compiler_version")
            depuis = (f" (construit avec monl {construit_avec}, courant "
                      f"{__version__})" if construit_avec else "")
            warnings.append(
                f"Artefacts produits par un compilateur antérieur : {', '.join(perimes)}"
                f"{depuis}. La spec n'a pas changé, monl si — lancer 'monl update' pour "
                f"resynchroniser (un correctif de sécurité n'atteint un projet "
                f"qu'après recompilation).")

    # Frontend (optionnel) : vérification best-effort que les chemins d'API
    # référencés existent dans le contrat. On ne bloque pas (un chemin peut
    # être construit dynamiquement) : on AVERTIT, nominalement.
    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        if not os.path.exists(os.path.join(frontend_dir, "index.html")):
            errors.append("frontend/ existe mais frontend/index.html est absent "
                          "(point d'entrée exigé par le contrat).")
            return False, errors, warnings
        # Un projet qui fournit un cahier visuel et un manifeste d'assets ne
        # doit pas pouvoir être déclaré « cohérent » avec des images ou des
        # sections obligatoires manquantes. Les projets historiques sans
        # manifeste conservent le contrôle best-effort ci-dessous.
        from ..frontend_ai import _design_completeness_errors
        design_errors = _design_completeness_errors(project_dir)
        if design_errors:
            errors.extend(design_errors)
            return False, errors, warnings
        with open(os.path.join(project_dir, CONTRACT_FILENAME), encoding="utf-8") as fh:
            contract = json.load(fh)
        known_prefixes = {r["path"].split("/")[1] for r in contract["routes"]}
        known_prefixes |= {"register", "login", "logout", "docs", "app", "site", "workflow"}
        referenced = set()
        # POINT 92 : les routes de NAVIGATION d'une application monopage
        # (`href="#/catalogue"`, `aller('/compte')`) ne sont pas des chemins
        # d'API, et l'avertissement les dénonçait toutes — quatre sur quatre sur
        # SneakerLab, dont aucune n'était un défaut. Un avertissement qui crie au
        # loup sur un site correct n'est pas prudent, il apprend à ne plus lire
        # les avertissements. La preuve est DANS le fichier : si `#/x` y figure,
        # `/x` est une route de navigation. Un vrai chemin d'API mal tapé, lui,
        # n'apparaît jamais derrière un dièse — il reste donc signalé.
        routes_client = set()
        for root, _dirs, files in os.walk(frontend_dir):
            for name in files:
                if not name.endswith((".html", ".js")):
                    continue
                with open(os.path.join(root, name), encoding="utf-8", errors="ignore") as fh:
                    contenu = fh.read()
                routes_client |= set(re.findall(r"#/([a-z_]+)", contenu))
                # Le littéral ENTIER est examiné, pas seulement son début
                # (point 57) : `'/edit">Modifier</a>'` est la fin d'une
                # route de navigation `#/article/<id>/edit` coupée par une
                # concaténation — du balisage, jamais une URL d'API. Toute
                # application monopage en produisait, et l'avertissement
                # criait au loup à chaque fois. Un chemin qui contient de
                # l'espace ou un chevron n'est pas un chemin.
                for match in re.finditer(r"""(['"`])(/[^'"`\n]*)\1""", contenu):
                    chemin = match.group(2)
                    if any(c in chemin for c in "<> "):
                        continue
                    segment = re.match(r"/([a-z_]+)(?:[/?#]|$)", chemin)
                    if segment:
                        referenced.add(segment.group(1))
        unknown = sorted(referenced - known_prefixes - routes_client)
        if unknown:
            warnings.append("Le frontend référence des chemins absents du contrat : "
                            + ", ".join(f"/{u}" for u in unknown))
        appels = couverture._frontend_fetch_calls(frontend_dir)
        errors.extend(couverture._frontend_fetch_contract_errors(contract, appels))
        couverture_errors, couverture_warnings = couverture._frontend_route_coverage(
            project_dir, spec_path, contract, appels=appels)
        errors.extend(couverture_errors)
        warnings.extend(couverture_warnings)
    else:
        warnings.append("Aucun dossier frontend/ — l'app sera servie avec ses seules "
                        "pages générées (landing, /app, /docs).")

    return not errors, errors, warnings
