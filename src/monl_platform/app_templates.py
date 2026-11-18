"""Non-interactive entry point to the monl application catalog."""

import contextlib
import io

from monl.app_templates import TEMPLATES
from monl.dialogue_engine import GuidedDialogue


def _template_index(template):
    if isinstance(template, bool):
        raise ValueError("a template must be its number or its name")
    if isinstance(template, int):
        if 1 <= template <= len(TEMPLATES):
            return template
        raise ValueError(f"unknown template: {template}")
    names = {item["name"]: index for index, item in enumerate(TEMPLATES, 1)}
    try:
        return names[str(template)]
    except KeyError as exc:
        raise ValueError(f"unknown template: {template}") from exc


def materialize_template(
    template,
    *,
    app_name="MonProjet",
    description=None,
    actor_choice=1,
    say=None,
    links=(),
):
    """Materializes a template into a spec by going through the real dialogue.

    Express mode does not make a parallel spec: it asks the
    ``GuidedDialogue`` to choose the template, then lets its emitter and its
    parser/audit revalidation produce the DSL. ``template`` accepts the
    catalog's 1-based number or its exact name."""
    index = _template_index(template)
    if description is None:
        description = f"Application built from the {TEMPLATES[index - 1]['name']} template."
    answers = iter((str(index), app_name, description, str(actor_choice)))
    dialogue = GuidedDialogue(
        ask=lambda _prompt: next(answers),
        say=say,
        express=True,
        express_links=links,
    )
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        spec = dialogue.run()
    if say is not None:
        for line in output.getvalue().splitlines():
            say(line)
    return spec


spec_from_template = materialize_template
