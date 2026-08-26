"""La construction par ÉTAGES, et le budget de chacun."""

import json
import os
import re

from ..design_system import ASSET_MANIFEST_FILENAME, GENERATED_MARKER
from . import fondations, fournisseurs, redaction, reponse, squelette

CHUNKED_FRONTEND_FILES = ("index.html", "styles.css", "app.js")

def _planned_generated_asset_paths(project_dir):
    """Retourne les SVG texte d'un manifeste historique uniquement.

    Les images matricielles sont produites avant cette étape par le fournisseur
    d'images et ne doivent jamais devenir des cibles du modèle texte.
    """
    path = os.path.join(project_dir, ASSET_MANIFEST_FILENAME)
    if not os.path.exists(path):
        return []
    try:
        content = open(path, encoding="utf-8").read()
        if content.startswith(GENERATED_MARKER):
            content = "\n".join(content.splitlines()[1:])
        manifest = json.loads(content)
    except (OSError, json.JSONDecodeError):
        return []
    paths = []
    for item in manifest.get("generated_assets") or []:
        rel = item.get("path") if isinstance(item, dict) else item
        if (isinstance(rel, str) and rel.lower().endswith(".svg") and
                not rel.startswith("/") and ".." not in rel.split("/")):
            paths.append(rel.replace("\\", "/"))
    return list(dict.fromkeys(paths))

def _parse_model_routing(declarations):
    """Transforme les options ``CIBLE=MODELE`` en table de routage."""
    routes = {}
    for declaration in declarations or []:
        if not isinstance(declaration, str):
            raise fondations.FrontendAIError(
                "routage de modèle invalide : la forme attendue est CIBLE=MODELE.")
        target, separator, model = declaration.partition("=")
        target = target.strip().replace("\\", "/")
        model = model.strip()
        if not separator or not target or not model:
            raise fondations.FrontendAIError(
                f"routage de modèle invalide : {declaration!r} — "
                "la forme attendue est CIBLE=MODELE.")
        if target in routes:
            raise fondations.FrontendAIError(
                f"cible répétée dans le routage des modèles : {target!r}.")
        routes[target] = model
    return routes

def _validate_model_routing(project_dir, routes):
    """Refuse toute cible qui ne sera jamais une étape de génération."""
    if not routes:
        return
    known = set(CHUNKED_FRONTEND_FILES)
    known.update(_planned_generated_asset_paths(project_dir))
    unknown = sorted(set(routes) - known)
    if unknown:
        rendered = ", ".join(repr(target) for target in unknown)
        known_targets = ", ".join(sorted(known))
        raise fondations.FrontendAIError(
            f"cible inconnue dans le routage des modèles : {rendered}. "
            f"Cibles connues : {known_targets}.")

def _provider_for_chunk(provider, target, routes, provider_factory):
    """Retourne le provider global ou celui construit pour une cible."""
    model = routes.get(target)
    if model is None:
        return provider
    if provider_factory is None:
        raise fondations.FrontendAIError(
            f"routage déclaré pour frontend/{target}, mais aucun constructeur "
            "de provider n'est disponible.")
    return provider_factory(model)

def _chunk_context(files, target=None):
    """Rend le contexte structurel utile à la cible, jamais les fichiers entiers."""
    if target == "styles.css":
        useful_paths = ("index.html",)
    elif target == "app.js" or target is None:
        useful_paths = ("index.html", "styles.css")
    else:
        useful_paths = ()

    morceaux = []
    for path in useful_paths:
        if path not in files or path == target:
            continue
        if path == "index.html":
            content = squelette._html_selector_skeleton(files[path])
            label = "squelette HTML (structure, class, id et data-*)"
        else:
            # Le JS ne dépend pas des propriétés CSS : les sélecteurs déclarés
            # suffisent à conserver les mêmes points d'accroche sans repayer
            # les règles et leurs valeurs, souvent beaucoup plus longues.
            content = squelette._css_selector_skeleton(files[path])
            label = "sélecteurs CSS déclarés (sans les règles)"
        morceaux.append(f"### frontend/{path} — {label}\n```\n{content}\n```")

    # Le contenu d'un SVG ne sert ni aux sélecteurs CSS ni aux branchements JS.
    # Son chemin suffit pour que les morceaux suivants le référencent.
    for path in sorted(path for path in files if path.endswith(".svg")):
        morceaux.append(
            f"### frontend/{path}\n(fichier SVG déjà produit ; le nom suffit)"
        )
    return "\n\n".join(morceaux) or "(aucun fichier généré pour le moment)"

def _chunk_response_reached_limit(provider):
    """Indique si le fournisseur a consommé tout son plafond de sortie."""
    usage = getattr(provider, "last_usage", None) or {}
    output_tokens = usage.get("output_tokens")
    maximum = getattr(provider, "max_output_tokens", None)
    return (isinstance(output_tokens, int) and not isinstance(output_tokens, bool)
            and output_tokens >= maximum
            if isinstance(maximum, int) and not isinstance(maximum, bool)
            else False)

def _raise_chunk_output_limit(provider):
    """Augmente le plafond d'une reprise, sans dépasser la borne définie."""
    maximum = getattr(provider, "max_output_tokens", None)
    if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum <= 0:
        return False
    enlarged = max(maximum + 1, int(maximum * fournisseurs.CHUNK_RETRY_OUTPUT_TOKEN_FACTOR))
    enlarged = min(enlarged, fournisseurs.CHUNK_RETRY_MAX_OUTPUT_TOKENS)
    if enlarged <= maximum:
        return False
    provider.max_output_tokens = enlarged
    return True

def _generate_chunked_files(project_dir, provider, base_prompt, operation,
                            attempt, say, run_id=None, model_routes=None,
                            provider_factory=None):
    """Génère puis valide chaque fichier d'un frontend DeepSeek/Yandex."""
    model_routes = model_routes or {}
    _validate_model_routing(project_dir, model_routes)
    files = reponse._read_existing_frontend(project_dir)
    ampleur = redaction.ampleur_du_contrat(project_dir)
    targets = list(CHUNKED_FRONTEND_FILES) + _planned_generated_asset_paths(project_dir)
    for target in targets:
        stage_provider = _provider_for_chunk(
            provider, target, model_routes, provider_factory)
        initial_output_limit = getattr(stage_provider, "max_output_tokens", None)
        say(f" -> Génération de frontend/{target}…")
        try:
            for retry in range(fournisseurs.CHUNK_MAX_RETRIES + 1):
                if retry:
                    say(f" -> Reprise de frontend/{target} "
                        f"({retry}/{fournisseurs.CHUNK_MAX_RETRIES})…")
                chunk_prompt = _build_chunk_prompt(base_prompt, target, files,
                                                   ampleur)
                if retry:
                    chunk_prompt += (
                        "\n\n## Reprise de génération\n"
                        "La réponse précédente pour ce fichier était illisible. "
                        "Rends à nouveau le fichier complet dans un JSON fermé, "
                        "sans reprendre une réponse tronquée."
                    )
                # Un appel en erreur ne doit pas réutiliser le compteur d'un appel
                # précédent. Le fournisseur peut néanmoins renseigner last_usage
                # avant de lever, ce qui permet alors de mesurer l'échec.
                if hasattr(stage_provider, "last_usage"):
                    stage_provider.last_usage = None
                try:
                    raw = stage_provider(chunk_prompt)
                except fondations.FrontendAIError as exc:
                    error = exc
                    fournisseurs._record_provider_usage(
                        project_dir, stage_provider, operation, attempt,
                        stage=target, retry=retry, run_id=run_id)
                else:
                    fournisseurs._record_provider_usage(
                        project_dir, stage_provider, operation, attempt,
                        stage=target, retry=retry, run_id=run_id)
                    try:
                        payload = reponse.parse_single_file_payload(raw, target)
                    except fondations.FrontendAIError as exc:
                        error = exc
                    else:
                        files.update(payload)
                        break

                if _chunk_response_reached_limit(stage_provider):
                    enlarged = _raise_chunk_output_limit(stage_provider)
                    if not enlarged:
                        raise fondations._ChunkOutputLimitError(
                            f"frontend/{target} : le modèle tronque encore au plafond "
                            f"maximal de sortie "
                            f"({fournisseurs.CHUNK_RETRY_MAX_OUTPUT_TOKENS} jetons) ; "
                            "aucune seconde tentative complète ne sera lancée, car "
                            "elle rejouerait la même configuration condamnée. "
                            f"Dernière erreur : {error}") from error
                if retry == fournisseurs.CHUNK_MAX_RETRIES:
                    raise fondations._ChunkGenerationError(
                        f"frontend/{target} : échec après "
                        f"{fournisseurs.CHUNK_MAX_RETRIES} reprise(s) ; aucune seconde tentative "
                        "complète ne sera lancée. "
                        f"Dernière erreur : {error}") from error
        finally:
            # Une hausse accordée à un fichier tronqué ne doit pas augmenter le
            # coût de tous les fichiers suivants partageant le même fournisseur.
            if hasattr(stage_provider, "max_output_tokens"):
                stage_provider.max_output_tokens = initial_output_limit
    return files

#: Budget de sortie d'`app.js`, en jetons : un socle, puis ce que coûte
#: RÉELLEMENT une route (appel, état de chargement, erreur, formulaire).
#: Mesuré à l'envers sur les frontends complets du dépôt — 26 à 43 Ko pour une
#: quinzaine de routes, soit 7 000 à 11 000 jetons.
APPJS_SOCLE_TOKENS = 1_200

APPJS_TOKENS_PAR_ROUTE = 400

INDEX_SOCLE_TOKENS = 1_200

INDEX_TOKENS_PAR_ROUTE = 200

def _budget(socle, par_route, ampleur, defaut):
    if not ampleur:
        return defaut
    return min(socle + par_route * ampleur["routes"],
               fournisseurs.DEFAULT_CHUNK_MAX_OUTPUT_TOKENS)

def _build_chunk_prompt(base_prompt, target, files, ampleur=None):
    """Demande une seule pièce complète du frontend.

    Le brief complet reste présent : le modèle conserve le contrat API et la
    direction produit. Le contexte des fichiers précédents garantit toutefois
    que le CSS et le JS s'accordent sur les mêmes classes et identifiants.
    """
    planned_assets = list(dict.fromkeys(re.findall(
        r"((?:assets|frontend)/[A-Za-z0-9._/-]+\.(?:jpg|jpeg|png|webp|svg))",
        base_prompt, re.IGNORECASE)))
    asset_rule = ""
    if planned_assets:
        asset_rule = (
            "\nAssets graphiques obligatoires de cette construction : "
            + ", ".join(planned_assets)
            + ". Ces images matricielles sont déjà écrites hors de frontend/. "
            "Référence exactement ces noms ; ne crée ni ne référence un autre "
            "fichier graphique local.\n"
        )
    index_tokens = _budget(INDEX_SOCLE_TOKENS, INDEX_TOKENS_PAR_ROUTE,
                           ampleur, 1_600)
    app_tokens = _budget(APPJS_SOCLE_TOKENS, APPJS_TOKENS_PAR_ROUTE,
                         ampleur, 1_500)
    # La limite dure suit le budget au lieu de le contredire : ~4 caractères
    # par jeton. Elle valait 12 000 caractères pour un fichier dont les
    # exemples réussis du dépôt pèsent 26 à 43 Ko — trois fois trop peu.
    plancher = ""
    if ampleur:
        plancher = (
            f" Ce contrat porte {ampleur['routes']} routes sur "
            f"{ampleur['entites']} entités : un fichier qui n'en appelle que "
            "deux ou trois sera REFUSÉ. Chaque parcours déclaré doit avoir son "
            "point d'entrée."
        )
    instructions = {
        "index.html": (
            "Produis maintenant uniquement frontend/index.html. Construis la "
            "structure complète de l'application et de son parcours principal, "
            "ses états vides/chargement/erreur, ses zones de formulaire, de "
            "contenu et de compte selon le contrat, puis charge styles.css et "
            "app.js avec des chemins locaux. Donne à chaque section obligatoire "
            "une vraie structure et un texte utile ; ne remplace pas le brief "
            f"par trois cartes génériques. Vise environ {index_tokens} tokens. "
            f"Limite dure : termine avant {index_tokens * 4} caractères."
            + asset_rule
        ),
        "styles.css": (
            "Produis maintenant uniquement frontend/styles.css. Donne un "
            "style complet, dense, responsive et accessible à la structure "
            "index.html ; ne remplace pas le CSS par une librairie externe. "
            "Vise environ 2 000 tokens et réutilise les "
            "sélecteurs plutôt que de dupliquer les règles. Limite dure : "
            "termine le JSON avant 16 000 caractères."
            + asset_rule
        ),
        "app.js": (
            "Produis maintenant uniquement frontend/app.js. Implémente les "
            "interactions et les appels aux routes autorisées du contrat, "
            "avec états de chargement, erreur, formulaires et authentification "
            "adaptés au type d'application ; n'invente aucune route. Implémente "
            "les états locaux et les messages près des champs, sans sacrifier "
            "les parcours principaux. Les valeurs de `dataset.*` sont des "
            "chaînes : convertir avec Number() avant de les comparer aux IDs "
            "numériques de l'API, puis vérifier mentalement les clics Créer, "
            f"Modifier et Supprimer.{plancher} Vise environ {app_tokens} tokens "
            f"et factorise le code. Limite dure : termine avant "
            f"{app_tokens * 4} caractères."
            + asset_rule
        ),
    }
    if target.endswith(".svg"):
        instructions[target] = (
            f"Produis maintenant uniquement frontend/{target}. Crée une "
            "illustration SVG originale, légère et autonome, cohérente avec "
            "le brief. Utilise un viewBox, des formes vectorielles lisibles "
            "et des couleurs définies dans le SVG ; aucun href externe, aucune "
            "image raster distante, aucun texte qui remplace l'illustration. "
            "Le fichier doit être un SVG valide et complet."
        )
    return (
        f"{base_prompt}\n\n"
        "## Génération séquentielle — une seule pièce à la fois\n"
        f"{instructions[target]}\n"
        f"Le fichier cible est exactement : {target}\n"
        "Réponds UNIQUEMENT avec un objet JSON de cette forme, sans Markdown :\n"
        f'{{"files": {{"{target}": "contenu complet du fichier"}}}}\n'
        "Ne rends aucun autre fichier, ne tronque pas le contenu et ne mets "
        "jamais de commentaire hors JSON.\n\n"
        "## Fichiers déjà générés — à respecter\n"
        f"{_chunk_context(files, target)}"
    )
