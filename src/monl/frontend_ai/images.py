"""Les images générées : leur brief, leur appel, leur optimisation."""

import inspect
import json
import os
import re

from ..design_system import plan_generated_images
from ..image_ai import ImageProviderError, optimize_image_bytes, record_image_usage
from . import fondations


def _clean_image_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _image_brief_material(brief):
    """Sépare la matière visuelle des consignes destinées au modèle texte."""
    text = _clean_image_text(brief)
    topic_match = re.search(
        r"Les illustrations doivent évoquer\s*:\s*(.+?)(?:[.!?](?:\s|$)|$)",
        text, re.IGNORECASE)
    topic = _clean_image_text(topic_match.group(1)) if topic_match else ""
    if topic_match:
        text = text[:topic_match.start()].rstrip(" .")

    text = re.split(r"\bmode express\s*:", text, maxsplit=1,
                    flags=re.IGNORECASE)[0].rstrip(" ;,.")
    text = re.sub(r"\bsans inventer\b.*$", "", text,
                  flags=re.IGNORECASE).rstrip(" ;,.")

    subject = text.split(" — ", 1)[0].strip(" ;,.")
    subject = re.split(
        r"\s*,\s*(?=(?:ton|registre|les images|le visiteur)\b)",
        subject, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ;,.")
    if not subject:
        subject = text or "matière déclarée par le projet"

    register = []
    for match in re.finditer(
            r"\b(?:ton|registre|les images portent)\b.+?(?=;| — |$)",
            text, re.IGNORECASE):
        clause = _clean_image_text(match.group(0))
        if clause and clause.lower() not in {item.lower() for item in register}:
            register.append(clause)
    return subject, " ; ".join(register), topic

def _image_text_chunks(value):
    """Retourne des morceaux supprimables sans casser une phrase déclarée."""
    chunks = re.split(r"(?<=[.!?])\s+|;\s+|,\s+", _clean_image_text(value))
    return [chunk.strip(" ;") for chunk in chunks if chunk.strip(" ;")]

def _compact_image_value(value, limit):
    """Réduit un champ en retirant des phrases ou clauses entières."""
    value = _clean_image_text(value)
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value

    chunks = _image_text_chunks(value)
    selected = []
    for chunk in chunks:
        candidate = "; ".join(selected + [chunk])
        if len(candidate) > limit:
            break
        selected.append(chunk)
    if selected:
        return "; ".join(selected)
    return ""

def _fit_image_prompt(parts, max_chars):
    """Assemble un prompt borné sans tronquer un token ni une phrase."""
    parts = [list(part) for part in parts if part[1]]

    def render():
        return "\n".join(f"{label} : {value}" for label, value, _required in parts)

    # Les sections sont utiles, mais le sujet, le rôle, le registre et les
    # interdits sont prioritaires pour une image. On retire donc les sections
    # entières avant de réduire la matière visuelle elle-même.
    while len(render()) > max_chars:
        optional = [index for index, (_label, _value, required) in enumerate(parts)
                    if not required]
        if optional:
            parts.pop(optional[-1])
            continue

        candidates = sorted(
            (index for index, (_label, value, _required) in enumerate(parts)
             if value),
            key=lambda index: len(parts[index][1]), reverse=True)
        if not candidates:
            break
        index = candidates[0]
        label, value, required = parts[index]
        excess = len(render()) - max_chars
        target = max(1, len(value) - excess - 1)
        shortened = _compact_image_value(value, target)
        if shortened == value:
            shortened = value.rsplit(" ", 1)[0] if " " in value else ""
        if not shortened:
            if required:
                # Ce cas ne devrait concerner qu'une limite fournisseur
                # irréaliste ; le message reste une erreur monl exploitable.
                raise fondations.FrontendAIError(
                    f"prompt image impossible à composer sous {max_chars} caractères")
            parts.pop(index)
            continue
        parts[index] = [label, shortened, required]

    prompt = render()
    if len(prompt) > max_chars:
        raise fondations.FrontendAIError(
            f"prompt image trop long après composition ({len(prompt)} caractères, "
            f"maximum {max_chars})")
    return prompt

def _image_prompt(project_dir, item, max_chars=None):
    """Construit le prompt image depuis la matière déclarée par le projet."""
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    try:
        with open(contract_path, encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise fondations.FrontendAIError(
            f"contrat frontend illisible avant la génération d'image : {exc}"
        ) from exc

    subject, register, topic = _image_brief_material(contract.get("brief"))
    subject = _clean_image_text(subject)
    if topic:
        subject = f"{subject} ; {topic}"
    parts = [
        ["Sujet", subject, True],
        ["Rôle", _clean_image_text(item.get("role") or "visuel du projet"), True],
        ["Registre visuel", register, True],
        ["Médium", "image matricielle", True],
    ]
    for section in contract.get("sections") or []:
        title = _clean_image_text(section.get("title") or "Section")
        body = _clean_image_text(section.get("body"))
        parts.append(["Matière", f"{title} — {body}" if body else title, False])
    parts.append(["Interdits", "pas de texte lisible, de logo ni de marque", True])
    if max_chars is None:
        return "\n".join(f"{label} : {value}" for label, value, _required in parts if value)
    return _fit_image_prompt(parts, max_chars)

def _image_provider_accepts_aspect_ratio(provider):
    try:
        parameters = inspect.signature(provider).parameters.values()
    except (TypeError, ValueError):
        return False
    return any(
        parameter.name == "aspect_ratio"
        or parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters
    )

def _image_provider_prompt_limit(provider):
    limit = getattr(provider, "max_prompt_chars", None)
    if (isinstance(limit, int) and not isinstance(limit, bool) and limit > 0):
        return limit
    return None

def _call_image_provider(provider, prompt, aspect_ratio):
    # Les fournisseurs injectables historiques restent prompt -> octets. Le
    # fournisseur YandexART, lui, accepte le rapport optionnel explicitement.
    limit = _image_provider_prompt_limit(provider)
    if limit is not None and len(prompt) > limit:
        raise fondations.FrontendAIError(
            f"monl : prompt image trop long pour le fournisseur "
            f"({len(prompt)} caractères, maximum {limit})")
    if aspect_ratio is None or not _image_provider_accepts_aspect_ratio(provider):
        return provider(prompt)
    return provider(prompt, aspect_ratio=aspect_ratio)

def _generate_planned_images(project_dir, image_provider, operation, attempt, run_id,
                             say=print):
    """Écrit les images planifiées et rapporte les échecs sans interrompre l'IA."""
    generated = plan_generated_images(project_dir)
    if not generated:
        raise fondations.FrontendAIError(
            "la génération d'images est activée mais le manifeste ne peut pas "
            "être planifié")
    failures = []
    for item in generated:
        path = item.get("path")
        if not isinstance(path, str) or path.startswith("/") or ".." in path.split("/"):
            raise fondations.FrontendAIError(f"chemin d'image générée refusé : {path}")
        destination = os.path.join(project_dir, path)
        if os.path.isfile(destination):
            continue
        prompt = _image_prompt(
            project_dir, item,
            max_chars=_image_provider_prompt_limit(image_provider))
        if hasattr(image_provider, "last_usage"):
            image_provider.last_usage = None
        say(f" -> Génération de l'image {path}…")
        try:
            image = _call_image_provider(image_provider, prompt, item.get("aspect_ratio"))
        except ImageProviderError as exc:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path} : {exc}"
            failures.append(failure)
            say(f" ⚠️ Image non générée — {failure}. La vérification du manifeste "
                "tranchera après la construction du frontend.")
            continue
        except Exception as exc:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path} : fournisseur d'image en erreur : {exc}"
            failures.append(failure)
            say(f" ⚠️ Image non générée — {failure}. La vérification du manifeste "
                "tranchera après la construction du frontend.")
            continue
        if not isinstance(image, (bytes, bytearray, memoryview)) or not image:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path} : le fournisseur d'image n'a pas rendu des octets"
            failures.append(failure)
            say(f" ⚠️ Image non générée — {failure}. La vérification du manifeste "
                "tranchera après la construction du frontend.")
            continue
        image, notice = optimize_image_bytes(bytes(image))
        if notice:
            say(f" ⚠️ {notice} ({path})")
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        with open(destination, "wb") as fh:
            fh.write(image)
        record_image_usage(project_dir, image_provider, operation, attempt,
                           run_id=run_id, stage="image", path=path)
    return generated, failures
