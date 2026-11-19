"""Read the model's response, and write it to disk."""

import json
import os
import re
from xml.etree import ElementTree

from ..design_system import ASSET_MANIFEST_FILENAME, DESIGN_SPEC_FILENAME, DESIGN_SYSTEM_FILENAME
from . import foundations

# ------------------------------------------------------ parsing + guards --
# Tab, line feed and carriage return are the only legitimate control characters
# in a delivered text file.
_CONTROLES_AUTORISES = {"\t", "\n", "\r"}

def _refuser_caracteres_de_controle(path, content):
    """Refuses a file carrying control characters, NUL first and foremost.

    A model that writes its accents as Unicode escapes can produce `\\u0000`
    where it aimed at `\\u00e8`: `json.loads` then returns a NUL byte, the file
    stays PERFECTLY VALID UTF-8, and nothing downstream notices anymore.
    Measured on a really built site — « Animalière » delivered as « Animali
    re », thirty-one NUL bytes in an index.html declared successful. Refusing
    here rather than further on gives the model its targeted retry, instead
    of publishing a mutilated French text."""
    fautifs = {
        caractere for caractere in content
        if ord(caractere) < 32 and caractere not in _CONTROLES_AUTORISES
    }
    if not fautifs:
        return
    nombre = sum(content.count(caractere) for caractere in fautifs)
    noms = ", ".join(f"U+{ord(c):04X}" for c in sorted(fautifs))
    raise foundations.FrontendAIError(
        f"forbidden control character in {path}: {noms} "
        f"({nombre} occurrence(s)) — a badly escaped accent produces this defect, "
        "and the file is still valid UTF-8.")

def _validate_files(files, require_index=True):
    """Validates a file map without imposing its transport format."""
    if not isinstance(files, dict) or not files:
        raise foundations.FrontendAIError("model response without a usable 'files' key")
    if require_index and "index.html" not in files:
        raise foundations.FrontendAIError("'index.html' missing from the response (required)")

    total = 0
    for path, content in files.items():
        norm = path.replace("\\", "/")
        if norm.startswith("/") or ".." in norm.split("/"):
            raise foundations.FrontendAIError(f"path refused (must stay inside frontend/): {path}")
        if not norm.endswith(foundations.ALLOWED_EXTENSIONS):
            raise foundations.FrontendAIError(f"extension refused: {path}")
        if not isinstance(content, str):
            raise foundations.FrontendAIError(f"non-text content for: {path}")
        _refuser_caracteres_de_controle(path, content)
        if norm.lower().endswith(".svg"):
            try:
                root = ElementTree.fromstring(content)
            except ElementTree.ParseError as exc:
                raise foundations.FrontendAIError(f"invalid or incomplete SVG: {path}") from exc
            if root.tag.rsplit("}", 1)[-1].lower() != "svg":
                raise foundations.FrontendAIError(f"invalid or incomplete SVG: {path}")
            # The standard XML namespace `xmlns="http://www.w3.org/2000/svg"`
            # is mandatory and downloads nothing. Do not confuse it with a real
            # remote resource in href/src/url().
            if re.search(
                    r"(?:\b(?:href|src|xlink:href)\s*=\s*['\"]"
                    r"(?:https?:|//)|\burl\(\s*['\"]?(?:https?:|//))",
                    content, re.IGNORECASE):
                raise foundations.FrontendAIError(
                    f"non-self-contained SVG (external resource): {path}")
        total += len(content.encode("utf-8"))
    if total > foundations.MAX_TOTAL_BYTES:
        raise foundations.FrontendAIError(f"response too large ({total} bytes)")
    return files

def _json_payload(raw_text):
    """Decodes a JSON response, tolerating Markdown fences."""
    text = raw_text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise foundations.FrontendAIError(f"unreadable model response (JSON expected): {e}") from e

def parse_files_payload(raw_text):
    """Extracts {path: content} from the model's response, with the same
    safeguards as for any untrusted input."""
    payload = _json_payload(raw_text)
    return _validate_files(payload.get("files"), require_index=True)

#: A fenced Markdown block, with or without a language name. The content is
#: captured as is: it is a FILE, not JSON.
_BLOC_CLOTURE = re.compile(r"```[a-zA-Z0-9_+-]*\s*\n(.*?)\n?```", re.DOTALL)

def _fichier_depuis_un_bloc(raw_text, expected_path):
    """Fallback: the model returned the FILE, not a JSON that contains it.

    A sequential step has to wrap a whole JavaScript file in a JSON string —
    every line break escaped, every quote doubled. That is where cheap models
    break, and the price is heavy: measured on a real build, `app.js` failed
    twice then returned 834 tokens — a tiny but PARSABLE file. The retry loop
    optimizes for readability, never completeness, and a quarter of the budget
    went there.

    The JSON envelope brings nothing here anyway: the step KNOWS which file it
    expects. The JSON contract stays the normal path — this is only a net, and
    it goes through the SAME safeguards (`_validate_files`): extension,
    confinement, size, control characters. No path bypasses them."""
    # A TRUNCATED response must never come through here. An ODD number of
    # fences says a block was left open: the response was cut. Without this
    # check, a model that illustrates with a small closed excerpt then gets cut
    # in the middle of the real file would have its EXCERPT written into app.js
    # — and the ceiling enlargement ladder, which exists precisely for this
    # case, would never be reached.
    if raw_text.count("```") % 2:
        return None
    blocs = [bloc for bloc in _BLOC_CLOTURE.findall(raw_text) if bloc.strip()]
    if not blocs:
        return None
    # The BIGGEST block: a chatty model comments on its response with small
    # excerpts before returning the file.
    contenu = max(blocs, key=len)
    # A block that IS the expected JSON is not a file: writing it as is would
    # drop `{"files": …}` into app.js, which parses and does not work.
    if contenu.lstrip().startswith("{"):
        return None
    # The fence swallows the last line break: a source file ends with a line
    # break, it is restored rather than delivering a last line stuck to
    # nothing.
    contenu = contenu.rstrip("\n") + "\n"
    return _validate_files({expected_path: contenu}, require_index=False)

def parse_single_file_payload(raw_text, expected_path):
    """Decodes the response of a sequential generation step.

    The normal transport stays ``{"files": {…}}`` — the same JSON contract as
    the monolithic path. When it is unreadable, we fall back on the file
    returned in a fenced block rather than burning a retry (see
    ``_fichier_depuis_un_bloc``)."""
    try:
        payload = _json_payload(raw_text)
        files = _validate_files(payload.get("files"), require_index=False)
    except foundations.FrontendAIError:
        secours = _fichier_depuis_un_bloc(raw_text, expected_path)
        if secours is None:
            raise
        return secours
    if set(files) != {expected_path}:
        rendus = ", ".join(sorted(files))
        raise foundations.FrontendAIError(
            f"the stage was to return only {expected_path}, received: {rendus}")
    return files

def _write_files(project_dir, files):
    frontend_dir = os.path.join(project_dir, "frontend")
    os.makedirs(frontend_dir, exist_ok=True)
    for path, content in files.items():
        dest = os.path.join(frontend_dir, path.replace("\\", "/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w", encoding="utf-8") as fh:
            fh.write(content)
    return frontend_dir

def _restaurer_frontend(project_dir, instantane):
    """Puts the frontend back in the exact state of a snapshot.

    Targeted on purpose: only the ALLOWLISTED files are touched. Wiping the
    folder would take away the generated images, which are not subject to it
    and which nobody would replay without paying again."""
    frontend_dir = os.path.join(project_dir, "frontend")
    for rel in set(_read_existing_frontend(project_dir)) - set(instantane):
        os.remove(os.path.join(frontend_dir, rel))
    return _write_files(project_dir, instantane)

def _read_existing_frontend(project_dir):
    frontend_dir = os.path.join(project_dir, "frontend")
    snapshot = {}
    if not os.path.isdir(frontend_dir):
        return snapshot
    for root, _dirs, names in os.walk(frontend_dir):
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, frontend_dir)
            if name.endswith(foundations.ALLOWED_EXTENSIONS):
                with open(full, encoding="utf-8", errors="ignore") as fh:
                    snapshot[rel] = fh.read()
    return snapshot

def _project_guidance(project_dir):
    """Adds the direction artifacts prepared by the author to the AI brief."""
    blocks = []
    for name in (DESIGN_SYSTEM_FILENAME, DESIGN_SPEC_FILENAME,
                 ASSET_MANIFEST_FILENAME):
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                blocks.append(f"\n\n## {name} — source of truth\n{fh.read()}")
    return "".join(blocks)
