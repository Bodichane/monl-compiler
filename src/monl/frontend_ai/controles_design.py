"""Ce que le site livré doit CONTENIR : sections, matière, images."""

import json
import os
import re
from html import unescape

from ..design_system import GENERATED_MARKER
from ..section_substance import substance_errors
from . import controles_fichiers


def _design_completeness_errors(project_dir):
    """Contrôles de complétude visuelle propres aux projets qui les déclarent.

    Le contrat Monl vérifie l'API et le fonctionnement. Ce contrôle séparé
    vérifie qu'un projet doté d'un design spec a aussi livré ses assets et ses
    sections obligatoires ; les projets historiques sans manifeste restent
    compatibles.
    """
    manifest_path = os.path.join(project_dir, "ASSET_MANIFEST.json")
    if not os.path.exists(manifest_path):
        return []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            raw = fh.read()
            if raw.startswith(GENERATED_MARKER):
                raw = "\n".join(raw.splitlines()[1:])
            manifest = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return [f"ASSET_MANIFEST.json illisible : {exc}"]

    # Le compilateur peut préparer le plan avant que le frontend n'existe.
    # Tant que l'orchestrateur n'a pas reçu une construction/importation, ce
    # plan informe l'IA mais ne bloque pas un projet qui possède déjà une
    # interface historique. La transition vers ``active`` est faite après
    # l'écriture du frontend, hors du périmètre de l'agent.
    if manifest.get("generated_by") == "monl" and manifest.get("status") == "planned":
        return []

    errors = []
    frontend_dir = os.path.join(project_dir, "frontend")
    assets_dir = "assets"
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if os.path.exists(contract_path):
        try:
            with open(contract_path, encoding="utf-8") as fh:
                assets_dir = ((json.load(fh).get("assets") or {}).get("dir")
                              or "assets").strip("/")
        except (OSError, json.JSONDecodeError):
            assets_dir = "assets"

    def asset_disk_path(rel):
        """Résout les nouveaux assets hors frontend, avec repli historique."""
        if rel == assets_dir or rel.startswith(assets_dir + "/"):
            return os.path.join(project_dir, rel)
        return os.path.join(frontend_dir, rel)

    asset_paths = []
    for group in ("products", "editorial"):
        values = manifest.get(group, {})
        if not isinstance(values, dict):
            errors.append(f"ASSET_MANIFEST.json : section '{group}' invalide")
            continue
        asset_paths.extend(values.values())
    for rel in asset_paths:
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            errors.append(f"asset refusé dans le manifeste : {rel}")
            continue
        if not os.path.isfile(asset_disk_path(rel)):
            errors.append(f"asset manquant : {rel}")

    # Les visuels produits par l'IA ne sont pas des assets métier déclarés par
    # l'auteur : ils ont néanmoins un chemin déterministe dans le manifeste.
    # Sans cette vérification, le modèle pouvait référencer un fichier image
    # absent, recevoir un succès du smoke test (qui n'interprète pas les
    # images), puis livrer une page blanche à l'endroit le plus visible.
    generated_assets = manifest.get("generated_assets") or []
    frontend_sources = []
    if os.path.isdir(frontend_dir):
        for root, _dirs, names in os.walk(frontend_dir):
            for name in names:
                if name.endswith((".html", ".css", ".js")):
                    try:
                        frontend_sources.append(
                            open(os.path.join(root, name), encoding="utf-8",
                                 errors="ignore").read())
                    except OSError:
                        pass
    rendered_source = "\n".join(frontend_sources)
    for item in generated_assets:
        rel = item.get("path") if isinstance(item, dict) else item
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            errors.append(f"asset généré refusé dans le manifeste : {rel}")
            continue
        if not os.path.isfile(asset_disk_path(rel)):
            errors.append(f"asset généré manquant : {rel}")
        elif rel not in rendered_source:
            errors.append(f"asset généré non utilisé : {rel}")

    errors.extend(_generated_asset_reuse_errors(frontend_dir, generated_assets))
    errors.extend(_editorial_content_errors(project_dir, rendered_source))
    errors.extend(controles_fichiers._declared_link_errors(project_dir, rendered_source))

    errors.extend(controles_fichiers._frontend_local_reference_errors(project_dir))
    errors.extend(controles_fichiers._frontend_behavioral_quality_errors(project_dir))

    for filename, markers in (manifest.get("required_markers") or {}).items():
        path = os.path.join(frontend_dir, filename)
        if not os.path.isfile(path):
            errors.append(f"fichier visuel obligatoire absent : frontend/{filename}")
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        unique_markers = set(
            (manifest.get("unique_section_markers") or {}).get(filename, [])
        )
        for marker in markers:
            count = content.count(marker)
            if marker in unique_markers and count != 1:
                if count == 0:
                    errors.append(f"section visuelle obligatoire absente : {marker}")
                else:
                    errors.append(
                        f"section visuelle obligatoire présente {count} fois : {marker}"
                    )
            elif marker not in unique_markers and count == 0:
                errors.append(f"section visuelle obligatoire absente : {marker}")
        # Le contrôle ci-dessus prouve qu'une section est NOMMÉE. Il ne dit
        # rien de ce qu'elle contient : `<section data-monl-section="hero">
        # </section>` le franchissait, et un site de huit balises vides
        # passait pour complet. La substance se mesure sur ce qui a été
        # réellement écrit, section par section.
        regles = (manifest.get("section_substance") or {}).get(filename) or {}
        errors.extend(substance_errors(content, {
            marker: regle for marker, regle in regles.items()
            if content.count(marker)
        }))
    return errors

def _generated_asset_reuse_errors(frontend_dir, generated_assets):
    """Refuse qu'une illustration dédiée soit copiée dans plusieurs images."""
    html_sources = []
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith(".html"):
                continue
            try:
                html_sources.append(open(os.path.join(root, name), encoding="utf-8",
                                         errors="ignore").read())
            except OSError:
                pass
    refs = re.findall(
        r"<img\b[^>]*\bsrc=['\"]([^'\"]+)['\"]",
        "\n".join(html_sources), re.IGNORECASE | re.DOTALL)
    refs = [os.path.normpath(ref.split("#", 1)[0].split("?", 1)[0])
            for ref in refs]
    errors = []
    for item in generated_assets:
        rel = item.get("path") if isinstance(item, dict) else item
        if not isinstance(rel, str):
            continue
        count = refs.count(os.path.normpath(rel))
        if count > 1:
            errors.append(
                f"asset généré réutilisé {count} fois : frontend/{rel} — "
                "chaque illustration doit avoir un rôle visuel unique.")
    return errors

def _editorial_content_errors(project_dir, rendered_source):
    """Détecte la répétition exacte d'un texte éditorial déclaré."""
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if not os.path.exists(contract_path):
        return []
    try:
        with open(contract_path, encoding="utf-8") as fh:
            sections = json.load(fh).get("sections") or []
    except (OSError, json.JSONDecodeError):
        return []
    source = " ".join(unescape(rendered_source).split())
    errors = []
    for section in sections:
        body = " ".join(unescape(section.get("body") or "").split())
        if len(body) < 40:
            continue
        count = source.count(body)
        if count > 1:
            title = section.get("title") or "section sans titre"
            errors.append(
                f"contenu éditorial répété {count} fois : « {title} » — "
                "chaque section déclarée doit être rendue une seule fois.")
    return errors
