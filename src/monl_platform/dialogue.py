"""Replay the guided dialogue for the web console.

The browser keeps only the answers already given. Each call starts again
from the beginning of the deterministic engine and stops at the next
unanswered ``ask``. This module therefore keeps no conversation state on
the server side."""

from __future__ import annotations

import contextlib
import io
import threading

from monl.dialogue_engine import DialogueError, GuidedDialogue
from monl.tui import PlainDialogueUI

# The limits stay under the platform's general JSON body limit, while leaving
# enough room for the free dialogue and its paragraphs.
MAX_DIALOGUE_ANSWERS = 96
MAX_DIALOGUE_ANSWER_BYTES = 2_048
_STDOUT_LOCK = threading.Lock()


class DialogueInputError(ValueError):
    """Malformed web answer or one impossible to continue."""


class DialogueIncomplete(Exception):
    """The engine has just asked for the next answer."""

    def __init__(self, prompt: str, meta: dict | None = None):
        self.prompt = prompt
        # What the engine KNOWS about this question (point 171): its kind, its
        # options, their hints. Without it, the console only receives the
        # TERMINAL text and has no choice but to paste it as is.
        self.meta = meta


def bounded_answers(value) -> list[str]:
    """Validates the browser's answers without truncating them."""
    if not isinstance(value, list):
        raise DialogueInputError("The 'answers' field must be a list of strings.")
    if len(value) > MAX_DIALOGUE_ANSWERS:
        raise DialogueInputError(
            f"The dialogue accepts at most {MAX_DIALOGUE_ANSWERS} answers."
        )
    for answer in value:
        if not isinstance(answer, str):
            raise DialogueInputError("Each dialogue answer must be a string.")
        if len(answer.encode("utf-8")) > MAX_DIALOGUE_ANSWER_BYTES:
            raise DialogueInputError(
                "Each dialogue answer must fit in "
                f"{MAX_DIALOGUE_ANSWER_BYTES} UTF-8 bytes."
            )
    return value


def submit(answers: list[str], candidate: str | None) -> dict:
    """Replays, and says whether the proposed answer was ACCEPTED.

    THE DEFECT THIS FUNCTION CLOSES, measured and not assumed. The engine
    retries three times before raising (``max_retries``), and the browser never
    pops: a refused answer therefore stayed in the list and burned an attempt
    FOREVER. Three typos on the same question and the dialogue died —
    forty-eight answers lost, with no way back, while the console politely
    offered to "start over".

    The signal that settles it: when the engine refuses, it asks the SAME
    question text again (checked by execution). An answer that does not move
    the question forward is therefore never kept, and the attempt budget is
    never touched."""
    before = replay(answers)
    if candidate is None or before["complete"]:
        return {**before, "accepted": candidate is None, "answers": list(answers)}

    apres = replay([*answers, candidate])
    refused = not apres["complete"] and apres["question"] == before["question"]
    if refused:
        # The engine's messages SAY why ("✗ Choose a menu number."):
        # returning them is the whole point: without them the user sees their
        # question come back with no explanation.
        return {**apres, "accepted": False, "answers": list(answers)}
    return {**apres, "accepted": True, "answers": [*answers, candidate]}


def bounded_answer(value) -> str | None:
    """The PROPOSED answer, bounded like the others, or nothing."""
    if value is None:
        return None
    bounded_answers([value])
    return value


def replay(answers: list[str]) -> dict:
    """Returns the next question, or the complete spec from the real engine."""
    remaining = list(answers)
    said: list[str] = []

    def ask(prompt=""):
        if not remaining:
            # LATE binding: `dialogue` does not exist yet when this closure is
            # defined, but it does when it is CALLED — the engine can only ask
            # a question once built.
            raise DialogueIncomplete(prompt, dialogue.last_question)
        return remaining.pop(0)

    dialogue = GuidedDialogue(ask=ask, say=said.append, ui=PlainDialogueUI())
    output = io.StringIO()
    try:
        # The real validator's historical audit still writes its lines to
        # stdout. Capturing it returns them to the console with the rest of the
        # log; the lock prevents a concurrent replay from mixing two dialogues
        # in the same global buffer.
        with _STDOUT_LOCK, contextlib.redirect_stdout(output):
            spec = dialogue.run()
    except DialogueIncomplete as incomplete:
        meta = incomplete.meta or {}
        return {
            "complete": False,
            "question": incomplete.prompt,
            "messages": said,
            "kind": meta.get("kind"),
            "title": meta.get("title"),
            "options": meta.get("options"),
            "hints": meta.get("hints"),
        }
    except DialogueError as exc:
        raise DialogueInputError(str(exc)) from exc

    said.extend(line for line in output.getvalue().splitlines() if line)
    if remaining:
        raise DialogueInputError(
            "The dialogue is complete, but extra answers were provided."
        )
    return {
        "complete": True,
        "question": None,
        "messages": said,
        "kind": None,
        "title": None,
        "options": None,
        "hints": None,
        "spec": spec,
    }
