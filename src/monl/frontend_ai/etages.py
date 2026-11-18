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
        with open(path, encoding="utf-8") as fichier:
            content = fichier.read()
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
                "invalid model routing: the expected form is TARGET=MODEL.")
        target, separator, model = declaration.partition("=")
        target = target.strip().replace("\\", "/")
        model = model.strip()
        if not separator or not target or not model:
            raise fondations.FrontendAIError(
                f"invalid model routing: {declaration!r} — "
                "the expected form is TARGET=MODEL.")
        if target in routes:
            raise fondations.FrontendAIError(
                f"target repeated in the model routing: {target!r}.")
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
            f"unknown target in the model routing: {rendered}. "
            f"Known targets: {known_targets}.")

def _provider_for_chunk(provider, target, routes, provider_factory):
    """Retourne le provider global ou celui construit pour une cible."""
    model = routes.get(target)
    if model is None:
        return provider
    if provider_factory is None:
        raise fondations.FrontendAIError(
            f"routing declared for frontend/{target}, but no provider "
            "builder is available.")
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
            label = "HTML skeleton (structure, class, id and data-*)"
        else:
            # Le JS ne dépend pas des propriétés CSS : les sélecteurs déclarés
            # suffisent à conserver les mêmes points d'accroche sans repayer
            # les règles et leurs valeurs, souvent beaucoup plus longues.
            content = squelette._css_selector_skeleton(files[path])
            label = "declared CSS selectors (without the rules)"
        morceaux.append(f"### frontend/{path} — {label}\n```\n{content}\n```")

    # Le contenu d'un SVG ne sert ni aux sélecteurs CSS ni aux branchements JS.
    # Son chemin suffit pour que les morceaux suivants le référencent.
    for path in sorted(path for path in files if path.endswith(".svg")):
        morceaux.append(
            f"### frontend/{path}\n(SVG file already produced; the name is enough)"
        )
    return "\n\n".join(morceaux) or "(no file generated yet)"

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
        say(f" -> Generating frontend/{target}…")
        try:
            for retry in range(fournisseurs.CHUNK_MAX_RETRIES + 1):
                if retry:
                    say(f" -> Retrying frontend/{target} "
                        f"({retry}/{fournisseurs.CHUNK_MAX_RETRIES})…")
                chunk_prompt = _build_chunk_prompt(base_prompt, target, files,
                                                   ampleur)
                if retry:
                    chunk_prompt += (
                        "\n\n## Generation retry\n"
                        "The previous response for this file was unreadable. "
                        "Return the complete file again in a closed JSON, "
                        "without resuming a truncated response."
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
                            f"frontend/{target}: the model still truncates at the maximum "
                            f"output ceiling "
                            f"({fournisseurs.CHUNK_RETRY_MAX_OUTPUT_TOKENS} tokens); "
                            "no second complete attempt will be started, since "
                            "it would replay the same doomed configuration. "
                            f"Last error: {error}") from error
                if retry == fournisseurs.CHUNK_MAX_RETRIES:
                    raise fondations._ChunkGenerationError(
                        f"frontend/{target}: failed after "
                        f"{fournisseurs.CHUNK_MAX_RETRIES} retry(ies); no second complete "
                        "attempt will be started. "
                        f"Last error: {error}") from error
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
            "\nRequired graphic assets for this build: "
            + ", ".join(planned_assets)
            + ". These raster images are already written outside frontend/. "
            "Reference exactly these names; do not create or reference any "
            "other local graphic file.\n"
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
            f" This contract carries {ampleur['routes']} routes over "
            f"{ampleur['entites']} entities: a file that calls only two or "
            "three of them will be REFUSED. Each declared flow must have its "
            "entry point."
        )
    instructions = {
        "index.html": (
            "Now produce only frontend/index.html. Build the complete "
            "structure of the application and of its main flow, its "
            "empty/loading/error states, its form, content and account areas "
            "according to the contract, then load styles.css and app.js with "
            "local paths. Give each required section a real structure and "
            "useful text; do not replace the brief with three generic cards. "
            f"Aim for about {index_tokens} tokens. "
            f"Hard limit: finish before {index_tokens * 4} characters."
            + asset_rule
        ),
        "styles.css": (
            "Now produce only frontend/styles.css. Give the index.html "
            "structure a complete, dense, responsive and accessible style; "
            "do not replace the CSS with an external library. "
            "Aim for about 2,000 tokens and reuse "
            "selectors rather than duplicating rules. Hard limit: "
            "finish the JSON before 16,000 characters."
            + asset_rule
        ),
        "app.js": (
            "Now produce only frontend/app.js. Implement the interactions "
            "and the calls to the contract's allowed routes, with loading, "
            "error, form and authentication states suited to the type of "
            "application; invent no route. Implement local states and "
            "messages next to the fields, without sacrificing the main "
            "flows. `dataset.*` values are strings: convert them with "
            "Number() before comparing them with the API's numeric IDs, then "
            "mentally check the Create, Edit and Delete clicks."
            f"{plancher} Aim for about {app_tokens} tokens "
            f"and factor the code. Hard limit: finish before "
            f"{app_tokens * 4} characters."
            + asset_rule
        ),
    }
    if target.endswith(".svg"):
        instructions[target] = (
            f"Now produce only frontend/{target}. Create an original, light, "
            "self-contained SVG illustration consistent with the brief. Use "
            "a viewBox, readable vector shapes and colors defined in the SVG; "
            "no external href, no remote raster image, no text replacing the "
            "illustration. The file must be a valid, complete SVG."
        )
    return (
        f"{base_prompt}\n\n"
        "## Sequential generation — one piece at a time\n"
        f"{instructions[target]}\n"
        f"The target file is exactly: {target}\n"
        "Answer ONLY with a JSON object of this shape, without Markdown:\n"
        f'{{"files": {{"{target}": "complete file content"}}}}\n'
        "Return no other file, do not truncate the content and never put "
        "a comment outside the JSON.\n\n"
        "## Files already generated — to respect\n"
        f"{_chunk_context(files, target)}"
    )
