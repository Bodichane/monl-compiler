"""Rejouer le dialogue guidé pour la console web.

Le navigateur ne conserve que les réponses déjà données. Chaque appel repart
du début du moteur déterministe et s'arrête au prochain ``ask`` sans réponse.
Ce module ne garde donc aucun état de conversation côté serveur.
"""

from __future__ import annotations

import contextlib
import io
import threading

from monl.dialogue_engine import DialogueError, GuidedDialogue
from monl.tui import PlainDialogueUI

# Les limites restent sous la limite générale de corps JSON de la plateforme,
# tout en laissant assez de place au dialogue libre et à ses paragraphes.
MAX_DIALOGUE_ANSWERS = 96
MAX_DIALOGUE_ANSWER_BYTES = 2_048
_STDOUT_LOCK = threading.Lock()


class DialogueInputError(ValueError):
    """Réponse web mal formée ou impossible à poursuivre."""


class DialogueIncomplete(Exception):
    """Le moteur vient de demander la prochaine réponse."""

    def __init__(self, prompt: str, meta: dict | None = None):
        self.prompt = prompt
        # Ce que le moteur SAIT de cette question (point 171) : sa nature, ses
        # options, leurs aides. Sans elle, la console ne reçoit que le texte de
        # TERMINAL et n'a d'autre choix que de le coller tel quel.
        self.meta = meta


def bounded_answers(value) -> list[str]:
    """Valider les réponses du navigateur sans les tronquer."""
    if not isinstance(value, list):
        raise DialogueInputError("Le champ 'answers' doit être une liste de textes.")
    if len(value) > MAX_DIALOGUE_ANSWERS:
        raise DialogueInputError(
            f"Le dialogue accepte au plus {MAX_DIALOGUE_ANSWERS} réponses."
        )
    for answer in value:
        if not isinstance(answer, str):
            raise DialogueInputError("Chaque réponse du dialogue doit être un texte.")
        if len(answer.encode("utf-8")) > MAX_DIALOGUE_ANSWER_BYTES:
            raise DialogueInputError(
                "Chaque réponse du dialogue doit tenir en "
                f"{MAX_DIALOGUE_ANSWER_BYTES} octets UTF-8."
            )
    return value


def soumettre(answers: list[str], candidate: str | None) -> dict:
    """Rejouer, et dire si la réponse proposée a été ACCEPTÉE.

    LE DÉFAUT QUE CETTE FONCTION FERME, mesuré et non supposé. Le moteur
    retente trois fois avant de lever (``max_retries``), et le navigateur ne
    dépile jamais : une réponse refusée restait donc dans la liste et brûlait
    une tentative POUR TOUJOURS. Trois fautes de frappe sur la même question et
    le dialogue mourait — quarante-huit réponses perdues, sans retour possible,
    pendant que la console proposait poliment de « recommencer ».

    Le signal qui permet de trancher : quand le moteur refuse, il redemande le
    MÊME texte de question (vérifié par exécution). Une réponse qui ne fait pas
    avancer la question n'est donc jamais retenue, et le budget de tentatives
    n'est jamais entamé.
    """
    avant = replay(answers)
    if candidate is None or avant["complete"]:
        return {**avant, "accepted": candidate is None, "answers": list(answers)}

    apres = replay([*answers, candidate])
    refusee = not apres["complete"] and apres["question"] == avant["question"]
    if refusee:
        # Les messages du moteur DISENT pourquoi (« ✗ Choisir un numéro du
        # menu. ») : les rendre est tout l'intérêt: sans eux l'usager voit sa
        # question revenir sans explication.
        return {**apres, "accepted": False, "answers": list(answers)}
    return {**apres, "accepted": True, "answers": [*answers, candidate]}


def bounded_answer(value) -> str | None:
    """La réponse PROPOSÉE, bornée comme les autres, ou rien."""
    if value is None:
        return None
    bounded_answers([value])
    return value


def replay(answers: list[str]) -> dict:
    """Retourner la question suivante, ou la spec complète du moteur réel."""
    remaining = list(answers)
    said: list[str] = []

    def ask(prompt=""):
        if not remaining:
            # Liaison TARDIVE : `dialogue` n'existe pas encore quand cette
            # fermeture est définie, mais il existe quand elle est APPELÉE —
            # le moteur ne peut poser une question qu'une fois construit.
            raise DialogueIncomplete(prompt, dialogue.derniere_question)
        return remaining.pop(0)

    dialogue = GuidedDialogue(ask=ask, say=said.append, ui=PlainDialogueUI())
    sortie = io.StringIO()
    try:
        # L'audit historique du vrai validateur écrit encore ses lignes sur
        # stdout. Le capturer les rend à la console avec le reste du journal ;
        # le verrou évite qu'un rejeu concurrent mélange deux dialogues dans
        # le même tampon global.
        with _STDOUT_LOCK, contextlib.redirect_stdout(sortie):
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

    said.extend(ligne for ligne in sortie.getvalue().splitlines() if ligne)
    if remaining:
        raise DialogueInputError(
            "Le dialogue est terminé, mais des réponses supplémentaires ont été fournies."
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
