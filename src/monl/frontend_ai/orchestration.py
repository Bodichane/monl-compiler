"""Construire, vérifier, importer — la boucle complète."""

import os
import shutil
import tempfile
import uuid
import zipfile

from ..design_system import activate_asset_manifest
from . import etages, fondations, fournisseurs, images, redaction, reponse

# ─────────────────────────────────────────────────────────────────────
# IMPORT MANUEL — la voie SANS clé API (point 42 du journal). Le cas le
# plus courant : l'utilisateur a un abonnement Claude (claude.ai) mais pas
# de clé. Le flux devient :
#   1. copier FRONTEND_PROMPT.md dans la conversation Claude
#   2. télécharger ce que Claude produit (zip, index.html, ou dossier)
#   3. 'monl import <téléchargement> [projet]' — installation dans
#      frontend/ avec les MÊMES garde-fous que la voie API (extensions en
#      liste blanche, confinement, index.html obligatoire, taille
#      plafonnée), puis la MÊME re-vérification (cohérence + smoke test).
# Pas d'auto-correction ici : l'humain est déjà dans la boucle — en cas
# d'échec, les erreurs sont affichées, prêtes à être recollées dans la
# conversation Claude pour obtenir un correctif, puis réimporter.
# ─────────────────────────────────────────────────────────────────────

def generate_and_verify(project_dir, provider, update_mode=False, say=print,
                        retouche_mode=False, model_routes=None,
                        provider_factory=None, generate_images=False,
                        image_provider=None):
    """La boucle complète du point 4 : générer → écrire → RE-VÉRIFIER
    (cohérence + smoke test) → si échec, renvoyer les erreurs au modèle une
    seule fois → re-vérifier. Retourne (ok, erreurs)."""
    from ..cli import check_coherence
    from ..smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    model_routes = model_routes or {}
    etages._validate_model_routing(project_dir, model_routes)
    if generate_images and image_provider is None:
        raise fondations.FrontendAIError(
            "--generate-images requires an injectable image provider.")
    if model_routes and not getattr(provider, "chunked_generation", False):
        declared = ", ".join(
            f"{target}={model}" for target, model in sorted(model_routes.items()))
        say(" -> Per-stage routing not applied: the monolithic path makes only "
            f"one call (declared mappings: {declared}).")
    run_id = uuid.uuid4().hex
    operation = ("retouche" if retouche_mode else
                 ("update" if update_mode else "construction"))
    image_failures = []
    if generate_images:
        _generated, image_failures = images._generate_planned_images(
            project_dir, image_provider, operation, 1, run_id, say=say)
    prompt = redaction.build_generation_prompt(project_dir, update_mode, retouche_mode)

    last_errors = []
    # La correction automatique peut RÉGRESSER : mesuré sur une construction
    # réelle, une passe chargée de réparer deux lignes a réécrit le site
    # entier et perdu quatorze routes sur quinze. monl gardait la DERNIÈRE
    # tentative ; il garde désormais la MEILLEURE.
    meilleure = None
    for attempt in (1, 2):
        if attempt == 2:
            say(" -> Automatic correction: errors sent back to the model (once only)…")
            prompt = (prompt + "\n\n## CHECK FAILED — TO FIX\n"
                      "Your previous response failed the monl check:\n"
                      + "\n".join(f"- {e}" for e in last_errors)
                      + "\nReturn a corrected version, same response format.")
        say(f" -> Frontend generation by the AI (attempt {attempt}/2)…")
        try:
            if getattr(provider, "chunked_generation", False):
                files = etages._generate_chunked_files(
                    project_dir, provider, prompt, operation, attempt, say,
                    run_id=run_id, model_routes=model_routes,
                    provider_factory=provider_factory)
            else:
                if hasattr(provider, "last_usage"):
                    provider.last_usage = None
                try:
                    raw = provider(prompt)
                except fondations.FrontendAIError:
                    fournisseurs._record_provider_usage(project_dir, provider, operation, attempt,
                                           run_id=run_id)
                    raise
                fournisseurs._record_provider_usage(project_dir, provider, operation, attempt,
                                       run_id=run_id)
                files = reponse.parse_files_payload(raw)
        except fondations._ChunkOutputLimitError as exc:
            last_errors = [f"generation failed: {exc}"]
            say(f" ❌ {last_errors[0]}")
            return False, last_errors
        except fondations._ChunkGenerationError as exc:
            last_errors = [f"generation failed: {exc}"]
            say(f" ❌ {last_errors[0]}")
            return False, last_errors
        except fondations.FrontendAIError as exc:
            last_errors = [f"generation failed: {exc}"]
            say(f" ❌ {last_errors[0]}")
            continue
        reponse._write_files(project_dir, files)
        # Un manifeste généré par Monl est seulement un plan tant que le
        # frontend n'existe pas. Après la réponse de l'IA, il devient une
        # obligation vérifiable : les assets et marqueurs attendus entrent
        # ainsi dans la correction automatique avec les erreurs d'API.
        activate_asset_manifest(project_dir)
        say(f" -> {len(files)} file(s) written in frontend/ "
            f"({', '.join(sorted(files))})")

        say(" -> Automatic recheck (consistency + smoke test)…")
        ok, errors, warnings = check_coherence(project_dir)
        if ok:
            smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
            errors, warnings = smoke_errors, warnings + smoke_warnings
            ok = smoke_ok
        # check_coherence() collecte déjà ces erreurs de complétude quand le
        # frontend existe ; les récolter ici une seconde fois dupliquerait
        # chaque refus d'asset dans la correction et dans le rapport.
        for w in warnings:
            say(f" ⚠️  {w}")
        if ok:
            say(" ✅ Frontend generated and verified: everything is consistent and works.")
            return True, []
        last_errors = errors
        for e in errors:
            say(f" ❌ {e}")
        # Le classement est (erreurs, avertissements), dans cet ordre et sans
        # pondération : une gravité inventée serait une opinion déguisée en
        # mesure. Il départage le cas qui l'a fait naître — même nombre
        # d'erreurs, mais deux parcours entiers signalés en plus.
        score = (len(errors), len(warnings))
        if meilleure is None or score < meilleure[0]:
            meilleure = (score, reponse._read_existing_frontend(project_dir), attempt,
                         list(errors))
        if image_failures:
            say(" ❌ Delivery refused: the manifest remains the authority for the "
                "planned images; run again once the provider is available.")
            return False, last_errors

    if meilleure is not None and meilleure[2] != attempt:
        reponse._restaurer_frontend(project_dir, meilleure[1])
        # Les erreurs rapportées doivent être celles des fichiers CONSERVÉS :
        # rapporter celles de la tentative écartée décrirait un frontend qui
        # n'est plus sur le disque.
        last_errors = meilleure[3]
        say(f" ↩  Attempt {meilleure[2]} restored: the correction produced a "
            f"more degraded frontend ({score[0]} error(s) and {score[1]} "
            f"warning(s), against {meilleure[0][0]} and {meilleure[0][1]}). "
            "What is kept is the less bad of the two, not the last one.")
        for e in last_errors:
            say(f" ❌ {e}")
    say(" ❌ The generated frontend still fails after correction — the files "
        "are kept in frontend/ for inspection, but 'monl run' "
        "will refuse to start while the smoke test fails.")
    return False, last_errors

def _collect_from_directory(root):
    """Ramène un dossier au format {chemin relatif: contenu}, filtré par la
    liste blanche d'extensions. Racine intelligente : si index.html vit dans
    un sous-dossier (zip Claude du type 'mon-app/index.html'), c'est CE
    sous-dossier qui devient la racine — le moins profond gagne."""
    index_candidates = []
    for dirpath, _dirs, names in os.walk(root):
        if "index.html" in names:
            index_candidates.append(dirpath)
    if not index_candidates:
        raise fondations.FrontendAIError("no 'index.html' found in the source — "
                              "it is the entry point the contract requires.")
    base = min(index_candidates, key=lambda p: len(os.path.relpath(p, root).split(os.sep)))

    files, skipped = {}, []
    for dirpath, _dirs, names in os.walk(base):
        for name in names:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, base).replace(os.sep, "/")
            if not rel.endswith(fondations.ALLOWED_EXTENSIONS):
                skipped.append(rel)
                continue
            with open(full, encoding="utf-8", errors="replace") as fh:
                files[rel] = fh.read()
    return files, skipped

def load_frontend_source(source):
    """Accepte les formes sous lesquelles un frontend revient d'une
    conversation Claude : un .zip téléchargé, un index.html seul, un dossier
    déjà décompressé, ou le JSON {"files": ...} (même format que l'API).
    Retourne ({chemin: contenu}, [fichiers ignorés])."""
    source = os.path.abspath(source)
    if not os.path.exists(source):
        raise fondations.FrontendAIError(f"source not found: {source}")

    if os.path.isdir(source):
        return _collect_from_directory(source)

    low = source.lower()
    if low.endswith(".zip"):
        tmp = tempfile.mkdtemp(prefix="monl_import_")
        try:
            with zipfile.ZipFile(source) as zf:
                for info in zf.infolist():
                    norm = info.filename.replace("\\", "/")
                    # Protection zip-slip : rien ne sort du dossier d'extraction.
                    if norm.startswith("/") or ".." in norm.split("/"):
                        raise fondations.FrontendAIError(f"archive refused: suspicious path '{info.filename}'")
                zf.extractall(tmp)
            return _collect_from_directory(tmp)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    if low.endswith((".html", ".htm")):
        with open(source, encoding="utf-8", errors="replace") as fh:
            return {"index.html": fh.read()}, []

    if low.endswith((".json", ".txt")):
        with open(source, encoding="utf-8", errors="replace") as fh:
            return reponse.parse_files_payload(fh.read()), []

    raise fondations.FrontendAIError(f"unrecognized format: {os.path.basename(source)} "
                          "(expected: .zip, .html, folder, or JSON {'files': ...})")

def import_and_verify(project_dir, source, say=print):
    """'monl import' : installer la source dans frontend/ puis re-vérifier
    exactement comme la voie API. Retourne (ok, erreurs)."""
    from ..cli import check_coherence
    from ..smoke_test import run_smoke_test

    project_dir = os.path.abspath(project_dir)
    files, skipped = load_frontend_source(source)

    # Mêmes garde-fous que la réponse d'un modèle : la source vient d'une
    # conversation, elle est traitée comme une entrée non fiable.
    total = sum(len(c.encode("utf-8")) for c in files.values())
    if total > fondations.MAX_TOTAL_BYTES:
        raise fondations.FrontendAIError(f"source too large ({total} bytes)")
    if "index.html" not in files:
        raise fondations.FrontendAIError("'index.html' missing after filtering — required entry point.")

    frontend_dir = os.path.join(project_dir, "frontend")
    if os.path.isdir(frontend_dir):
        backup = frontend_dir + ".precedent"
        shutil.rmtree(backup, ignore_errors=True)
        os.rename(frontend_dir, backup)
        say(" -> Existing frontend kept in frontend.precedent/ (nothing is lost).")
    reponse._write_files(project_dir, files)
    activate_asset_manifest(project_dir)
    say(f" -> {len(files)} file(s) installed in frontend/ ({', '.join(sorted(files))})")
    for rel in skipped:
        say(f" ⚠️  ignored (extension outside the .html/.css/.js/.svg/.json allowlist): {rel}")

    say(" -> Automatic recheck (consistency + smoke test)…")
    ok, errors, warnings = check_coherence(project_dir)
    if ok:
        smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir, say=say)
        errors, warnings = smoke_errors, warnings + smoke_warnings
        ok = smoke_ok
    for w in warnings:
        say(f" ⚠️  {w}")
    if ok:
        say(" ✅ Frontend imported and verified: 'monl run' is ready.")
        return True, []
    for e in errors:
        say(f" ❌ {e}")
    say(" ❌ Check failed. Paste the errors above back into your Claude "
        "conversation, ask for a fix, then import again "
        "(the files stay in frontend/ for inspection).")
    return False, errors
