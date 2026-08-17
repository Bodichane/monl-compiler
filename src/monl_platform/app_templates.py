"""Point d'entrée non interactif vers le catalogue d'applications monl."""

import contextlib
import io

from monl.app_templates import TEMPLATES
from monl.dialogue_engine import GuidedDialogue


def _template_index(template):
    if isinstance(template, bool):
        raise ValueError("un modèle doit être son numéro ou son nom")
    if isinstance(template, int):
        if 1 <= template <= len(TEMPLATES):
            return template
        raise ValueError(f"modèle inconnu : {template}")
    names = {item["name"]: index for index, item in enumerate(TEMPLATES, 1)}
    try:
        return names[str(template)]
    except KeyError as exc:
        raise ValueError(f"modèle inconnu : {template}") from exc


def materialize_template(
    template,
    *,
    app_name="MonProjet",
    description=None,
    actor_choice=1,
    say=None,
):
    """Matérialise un modèle en spec en passant par le vrai dialogue.

    Le mode express ne fabrique pas une spec parallèle : il demande au
    ``GuidedDialogue`` de choisir le modèle, puis laisse son émetteur et sa
    revalidation parser/audit produire le DSL. ``template`` accepte le numéro
    1-based du catalogue ou son nom exact.
    """
    index = _template_index(template)
    if description is None:
        description = f"Application issue du modèle {TEMPLATES[index - 1]['name']}."
    answers = iter((str(index), app_name, description, str(actor_choice)))
    dialogue = GuidedDialogue(
        ask=lambda _prompt: next(answers),
        say=say,
        express=True,
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        spec = dialogue.run()
    if say is not None:
        for line in output.getvalue().splitlines():
            say(line)
    return spec


spec_from_template = materialize_template
