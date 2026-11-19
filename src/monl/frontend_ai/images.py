"""Generated images: their brief, their call, their optimization."""

import inspect
import json
import os
import re

from ..design_system import plan_generated_images
from ..image_ai import ImageProviderError, optimize_image_bytes, record_image_usage
from . import foundations


def _clean_image_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def _image_brief_material(brief):
    """Separates the visual material from the instructions meant for the text
    model."""
    text = _clean_image_text(brief)
    topic_match = re.search(
        r"(?:Les illustrations doivent évoquer|The illustrations should evoke)"
        r"\s*:\s*(.+?)(?:[.!?](?:\s|$)|$)",
        text, re.IGNORECASE)
    topic = _clean_image_text(topic_match.group(1)) if topic_match else ""
    if topic_match:
        text = text[:topic_match.start()].rstrip(" .")

    text = re.split(r"\b(?:mode express|express mode)\s*:", text, maxsplit=1,
                    flags=re.IGNORECASE)[0].rstrip(" ;,.")
    text = re.sub(r"\b(?:sans inventer|without inventing)\b.*$", "", text,
                  flags=re.IGNORECASE).rstrip(" ;,.")

    subject = text.split(" — ", 1)[0].strip(" ;,.")
    subject = re.split(
        r"\s*,\s*(?=(?:ton|registre|les images|le visiteur"
        r"|tone|the images|the visitor)\b)",
        subject, maxsplit=1, flags=re.IGNORECASE)[0].strip(" ;,.")
    if not subject:
        subject = text or "material declared by the project"

    register = []
    # Two grammars: French opens the clause with « registre … » or « les images
    # portent … » (specs written before the English migration), English puts
    # the word after the adjectives ("bold, graphic register: …") — the whole
    # clause containing it is then kept.
    for match in re.finditer(
            r"\b(?:ton|registre|les images portent)\b.+?(?=;| — |$)"
            r"|[^;—]*\b(?:register|tone)\b[^;—]*"
            r"|\bthe images carry\b.+?(?=;| — |$)",
            text, re.IGNORECASE):
        clause = _clean_image_text(match.group(0))
        if clause and clause.lower() not in {item.lower() for item in register}:
            register.append(clause)
    return subject, " ; ".join(register), topic

def _image_text_chunks(value):
    """Returns pieces that can be removed without breaking a declared sentence."""
    chunks = re.split(r"(?<=[.!?])\s+|;\s+|,\s+", _clean_image_text(value))
    return [chunk.strip(" ;") for chunk in chunks if chunk.strip(" ;")]

def _compact_image_value(value, limit):
    """Shrinks a field by removing whole sentences or clauses."""
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
    """Assembles a bounded prompt without truncating a token or a sentence."""
    parts = [list(part) for part in parts if part[1]]

    def render():
        return "\n".join(f"{label}: {value}" for label, value, _required in parts)

    # The sections are useful, but the subject, role, register and prohibitions
    # take priority for an image. Whole sections are therefore removed before
    # the visual material itself is shrunk.
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
                # This case should only concern an unrealistic provider limit;
                # the message stays an actionable monl error.
                raise foundations.FrontendAIError(
                    f"image prompt cannot be composed under {max_chars} characters")
            parts.pop(index)
            continue
        parts[index] = [label, shortened, required]

    prompt = render()
    if len(prompt) > max_chars:
        raise foundations.FrontendAIError(
            f"image prompt too long after composition ({len(prompt)} characters, "
            f"maximum {max_chars})")
    return prompt

def _image_prompt(project_dir, item, max_chars=None):
    """Builds the image prompt from the material declared by the project."""
    contract_path = os.path.join(project_dir, "frontend_contract.json")
    try:
        with open(contract_path, encoding="utf-8") as fh:
            contract = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise foundations.FrontendAIError(
            f"frontend contract unreadable before image generation: {exc}"
        ) from exc

    subject, register, topic = _image_brief_material(contract.get("brief"))
    subject = _clean_image_text(subject)
    if topic:
        subject = f"{subject} ; {topic}"
    parts = [
        ["Subject", subject, True],
        ["Role", _clean_image_text(item.get("role") or "project visual"), True],
        ["Visual register", register, True],
        ["Medium", "raster image", True],
    ]
    for section in contract.get("sections") or []:
        title = _clean_image_text(section.get("title") or "Section")
        body = _clean_image_text(section.get("body"))
        parts.append(["Material", f"{title} — {body}" if body else title, False])
    parts.append(["Forbidden", "no readable text, logo or brand", True])
    if max_chars is None:
        return "\n".join(f"{label}: {value}" for label, value, _required in parts if value)
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
    # The historical injectable providers stay prompt -> bytes. The YandexART
    # provider, however, explicitly accepts the optional report.
    limit = _image_provider_prompt_limit(provider)
    if limit is not None and len(prompt) > limit:
        raise foundations.FrontendAIError(
            f"monl: image prompt too long for the provider "
            f"({len(prompt)} characters, maximum {limit})")
    if aspect_ratio is None or not _image_provider_accepts_aspect_ratio(provider):
        return provider(prompt)
    return provider(prompt, aspect_ratio=aspect_ratio)

def _generate_planned_images(project_dir, image_provider, operation, attempt, run_id,
                             say=print):
    """Writes the planned images and reports failures without interrupting the
    AI."""
    generated = plan_generated_images(project_dir)
    if not generated:
        raise foundations.FrontendAIError(
            "image generation is enabled but the manifest cannot be "
            "planned")
    failures = []
    for item in generated:
        path = item.get("path")
        if not isinstance(path, str) or path.startswith("/") or ".." in path.split("/"):
            raise foundations.FrontendAIError(f"generated image path refused: {path}")
        destination = os.path.join(project_dir, path)
        if os.path.isfile(destination):
            continue
        prompt = _image_prompt(
            project_dir, item,
            max_chars=_image_provider_prompt_limit(image_provider))
        if hasattr(image_provider, "last_usage"):
            image_provider.last_usage = None
        say(f" -> Generating the image {path}…")
        try:
            image = _call_image_provider(image_provider, prompt, item.get("aspect_ratio"))
        except ImageProviderError as exc:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path}: {exc}"
            failures.append(failure)
            say(f" ⚠️ Image not generated — {failure}. The manifest check will "
                "decide after the frontend is built.")
            continue
        except Exception as exc:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path}: image provider error: {exc}"
            failures.append(failure)
            say(f" ⚠️ Image not generated — {failure}. The manifest check will "
                "decide after the frontend is built.")
            continue
        if not isinstance(image, (bytes, bytearray, memoryview)) or not image:
            record_image_usage(project_dir, image_provider, operation, attempt,
                               run_id=run_id, stage="image", path=path,
                               status="error")
            failure = f"{path}: the image provider returned no bytes"
            failures.append(failure)
            say(f" ⚠️ Image not generated — {failure}. The manifest check will "
                "decide after the frontend is built.")
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
