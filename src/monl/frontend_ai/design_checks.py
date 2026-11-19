"""What the delivered site must CONTAIN: sections, substance, images."""

import json
import os
import re
from html import unescape

from ..design_system import ASSET_MANIFEST_FILENAME, GENERATED_MARKER
from ..section_substance import substance_errors
from . import file_checks


def _design_completeness_errors(project_dir):
    """Visual completeness checks specific to the projects that declare them.

    The Monl contract checks the API and behavior. This separate check
    verifies that a project with a design spec has also delivered its assets
    and its mandatory sections; historical projects without a manifest stay
    compatible."""
    manifest, read_errors = _load_manifest(project_dir)
    if read_errors:
        return read_errors
    if manifest is None or _manifest_is_planned(manifest):
        return []

    frontend_dir = os.path.join(project_dir, "frontend")
    assets_dir = _manifest_assets_dir(project_dir)
    errors = _declared_asset_errors(manifest, project_dir, frontend_dir, assets_dir)
    generated_assets = manifest.get("generated_assets") or []
    rendered_source = _frontend_source(frontend_dir)
    errors.extend(_generated_asset_errors(
        generated_assets, project_dir, frontend_dir, assets_dir, rendered_source,
    ))
    errors.extend(_generated_asset_reuse_errors(frontend_dir, generated_assets))
    errors.extend(_editorial_content_errors(project_dir, rendered_source))
    errors.extend(file_checks._declared_link_errors(project_dir, rendered_source))
    errors.extend(file_checks._frontend_local_reference_errors(project_dir))
    errors.extend(file_checks._frontend_behavioral_quality_errors(project_dir))

    errors.extend(_required_marker_errors(manifest, frontend_dir))
    return errors


def _load_manifest(project_dir):
    manifest_path = os.path.join(project_dir, ASSET_MANIFEST_FILENAME)
    if not os.path.exists(manifest_path):
        return None, []
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            raw = fh.read()
            if raw.startswith(GENERATED_MARKER):
                raw = "\n".join(raw.splitlines()[1:])
            return json.loads(raw), []
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"ASSET_MANIFEST.json illisible : {exc}"]


def _manifest_is_planned(manifest):
    """The preparatory plan informs the AI without blocking the existing
    interface."""
    return manifest.get("generated_by") == "monl" and manifest.get("status") == "planned"


def _manifest_assets_dir(project_dir):
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    if not os.path.exists(contract_path):
        return "assets"
    try:
        with open(contract_path, encoding="utf-8") as fh:
            return ((json.load(fh).get("assets") or {}).get("dir")
                    or "assets").strip("/")
    except (OSError, json.JSONDecodeError):
        return "assets"


def _asset_disk_path(project_dir, frontend_dir, assets_dir, rel):
    """Resolves the new assets outside frontend, with a historical fallback."""
    if rel == assets_dir or rel.startswith(assets_dir + "/"):
        return os.path.join(project_dir, rel)
    return os.path.join(frontend_dir, rel)


def _declared_asset_errors(manifest, project_dir, frontend_dir, assets_dir):
    errors = []
    for group in ("products", "editorial"):
        values = manifest.get(group, {})
        if not isinstance(values, dict):
            errors.append(f"ASSET_MANIFEST.json: invalid section '{group}'")
            continue
        for rel in values.values():
            if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
                errors.append(f"asset refused in the manifest: {rel}")
            elif not os.path.isfile(_asset_disk_path(
                    project_dir, frontend_dir, assets_dir, rel)):
                errors.append(f"asset manquant : {rel}")
    return errors


def _frontend_source(frontend_dir):
    sources = []
    if not os.path.isdir(frontend_dir):
        return ""
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith((".html", ".css", ".js")):
                continue
            try:
                with open(os.path.join(root, name), encoding="utf-8",
                          errors="ignore") as fichier:
                    sources.append(fichier.read())
            except OSError:
                pass
    return "\n".join(sources)


def _generated_asset_errors(generated_assets, project_dir, frontend_dir,
                            assets_dir, rendered_source):
    """Checks the presence and use of the visuals produced by the AI."""
    errors = []
    for item in generated_assets:
        rel = item.get("path") if isinstance(item, dict) else item
        if not isinstance(rel, str) or rel.startswith("/") or ".." in rel.split("/"):
            errors.append(f"generated asset refused in the manifest: {rel}")
            continue
        if not os.path.isfile(_asset_disk_path(
                project_dir, frontend_dir, assets_dir, rel)):
            errors.append(f"generated asset missing: {rel}")
        elif rel not in rendered_source:
            errors.append(f"generated asset unused: {rel}")
    return errors


def _required_marker_errors(manifest, frontend_dir):
    errors = []
    unique_markers_by_file = manifest.get("unique_section_markers") or {}
    for filename, markers in (manifest.get("required_markers") or {}).items():
        path = os.path.join(frontend_dir, filename)
        if not os.path.isfile(path):
            errors.append(f"required visual file missing: frontend/{filename}")
            continue
        with open(path, encoding="utf-8", errors="ignore") as fh:
            content = fh.read()
        unique_markers = set(unique_markers_by_file.get(filename, []))
        errors.extend(_marker_errors(content, markers, unique_markers))
        regles = (manifest.get("section_substance") or {}).get(filename) or {}
        errors.extend(substance_errors(content, {
            marker: regle for marker, regle in regles.items()
            if content.count(marker)
        }))
    return errors


def _marker_errors(content, markers, unique_markers):
    errors = []
    for marker in markers:
        count = content.count(marker)
        if marker in unique_markers and count != 1:
            if count == 0:
                errors.append(f"required visual section missing: {marker}")
            else:
                errors.append(
                    f"required visual section present {count} times: {marker}"
                )
        elif marker not in unique_markers and count == 0:
            errors.append(f"required visual section missing: {marker}")
    return errors

def _generated_asset_reuse_errors(frontend_dir, generated_assets):
    """Refuses a dedicated illustration copied into several images."""
    html_sources = []
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            if not name.endswith(".html"):
                continue
            try:
                with open(os.path.join(root, name), encoding="utf-8",
                          errors="ignore") as fichier:
                    html_sources.append(fichier.read())
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
                f"generated asset reused {count} times: frontend/{rel} — "
                "each illustration must have a single visual role.")
    return errors

def _editorial_content_errors(project_dir, rendered_source):
    """Detects the exact repetition of a declared editorial text."""
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
            title = section.get("title") or "untitled section"
            errors.append(
                f"editorial content repeated {count} times: “{title}” — "
                "each declared section must be rendered only once.")
    return errors
