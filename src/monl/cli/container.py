"""What a project takes along to run elsewhere."""

import os

from ..serving import render_wrapper
from . import nomenclature


def _ensure_container_artifacts(staging_dir, uploads=False):
    """Emits the container templates without overwriting the author's."""
    dockerfile = nomenclature.DEFAULT_DOCKERFILE
    dockerignore = nomenclature.DEFAULT_DOCKERIGNORE
    requirements = nomenclature.DEFAULT_REQUIREMENTS
    if uploads:
        # The Dockerfile no longer moves: it installs `-r requirements.txt`, so
        # the Upload dependency has only ONE place to be added.
        requirements = nomenclature.REQUIREMENTS_UPLOAD
        dockerignore += ".monl_uploads/\n"
    defaults = {
        "Dockerfile": dockerfile,
        ".dockerignore": dockerignore,
        "requirements.txt": requirements,
    }
    for name, content in defaults.items():
        path = os.path.join(staging_dir, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            continue
        # A template emitted during an earlier compilation is refreshed; a
        # really customized Docker file stays the author's responsibility.
        with open(path, encoding="utf-8") as fh:
            current = fh.read()
        if name == "Dockerfile":
            # `content` is the current template, with or without Upload
            # applied: BOTH current forms must be recognized as "never
            # touched", otherwise a spec that loses its Upload would keep the
            # now useless dependency.
            known = (nomenclature.DEFAULT_DOCKERFILE, content, *nomenclature.DOCKERFILES_INHERITED)
        elif name == ".dockerignore":
            known = (nomenclature.DEFAULT_DOCKERIGNORE,)
        else:
            # BOTH forms (with and without Upload) count as "never touched": a
            # spec that loses its Upload must see the dependency disappear, as
            # for the Dockerfile above. REQUIREMENTS_UPLOAD is ALSO the form
            # emitted before the dependency became conditional: a single entry
            # is therefore enough, and adding an identical one would protect
            # against nothing.
            known = (nomenclature.DEFAULT_REQUIREMENTS,
                      nomenclature.REQUIREMENTS_UPLOAD)
        if current in known and current != content:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)

def _emit_wrapper(staging_dir, contract):
    """Writes serve.py AT COMPILE TIME, no longer only at 'monl run'.

    POINT 133. The Dockerfile produced by 'monl compile' ran `app:app`: the
    image served the API and answered 404 on /site and on the photos, because
    the wrapper that mounts them was written only by 'monl run'. A product
    whose selling point is "a delivered site" thus delivered an API without a
    site. Checked by really building the image, not by rereading the code.

    The assets folder comes from the CONTRACT, already derived from the spec
    and checked consistent with it — rereading the spec here would make a
    second parser to drift (same reason as `_assets_dir_du_projet`, of which
    this is the compile-time counterpart).

    Written unconditionally: it is generated code, not a template the author
    adapts. The Dockerfile stays editable — hence two treatments."""
    assets_dir = (contract.get("assets") or {}).get("dir") or None
    with open(os.path.join(staging_dir, "serve.py"), "w", encoding="utf-8") as fh:
        fh.write(render_wrapper(assets_dir))
