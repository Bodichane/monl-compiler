"""
Traduction Langage Naturel -> Spécification MonLang (Phase 7).

CORRECTIF (post-v6) : ce module utilisait auparavant llama_cpp avec un
fichier de modèle .gguf local (absent du dépôt, plusieurs Go). Il est
réécrit ici pour utiliser un serveur Ollama local via son API HTTP
(http://localhost:11434), exactement comme src/ai_sandbox_filler.py le
fait déjà pour remplir les blocs 'custom'. Ça évite de dupliquer un modèle
volumineux dans le dépôt et laisse le choix du modèle à l'utilisateur
(voir README.md, section "Configurer le modèle IA local").
"""
import os
import requests

from parser import parse_monlang_string

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5-coder:3b"

SYSTEM_PROMPT = """Tu es le moteur de traduction officiel du langage "MonLang".
Ton unique rôle est de traduire une demande utilisateur en langage naturel
vers une spécification MonLang valide.

Tu dois impérativement respecter cette syntaxe stricte (indentation de 4
espaces, pas d'accolades, pas de point-virgule) :

app NomDeLApp

entity NomEntite
    attribut: Type

relation EntiteSource hasMany EntiteCible
relation EntiteSource belongsTo EntiteCible
relation EntiteSource hasOne EntiteCible

actor NomActeur

rule Entite.attribut required
rule Entite.attribut unique
rule Entite.attribut min 0
rule Entite.attribut restrictedTo NomActeur
rule Entite.ActionType sharedBy ActeurA, ActeurB

workflow NomDuWorkflow for NomActeur
    Create Entite
    Read Entite
    Update Entite
    Delete Entite

Types d'attributs valides : String, Text, Integer, Float, Boolean, Date,
DateTime, Email, UUID, Money.

Exemple de sortie attendue pour "une todo-list simple" :
app TodoApp

entity Todo
    title: String
    completed: Boolean

actor User

rule Todo.title required

workflow ManageTodo for User
    Create Todo
    Read Todo
    Update Todo
    Delete Todo

CONSIGNE CRUCIALE : réponds au format JSON avec une seule clé "spec"
contenant le texte MonLang brut (pas de balises markdown, pas
d'explication, pas de ```). Le texte doit être directement compilable
tel quel.
"""


def _call_ollama(user_prompt, model, correction_context=None):
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if correction_context:
        messages.append({"role": "user", "content": correction_context["previous_prompt"]})
        messages.append({"role": "assistant", "content": correction_context["previous_output"]})
        messages.append({"role": "user", "content": (
            f"Cette spécification ne compile pas. Erreur du parseur : "
            f"{correction_context['error']}\n"
            f"Corrige la spécification en respectant strictement la syntaxe "
            f"décrite précédemment, et renvoie à nouveau un JSON avec la clé \"spec\"."
        )})
    else:
        messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.1},
    }

    response = requests.post(OLLAMA_URL, json=payload, timeout=90)
    response.raise_for_status()
    content = response.json()["message"]["content"]

    import json
    parsed = json.loads(content)
    return parsed["spec"]


def prompt_to_monlang(user_prompt, model=DEFAULT_MODEL, max_retries=1):
    """Traduit une description en langage naturel en spécification MonLang,
    en validant la sortie avec le vrai parseur avant de la retourner. Si le
    YAML produit ne compile pas, retente une fois en donnant l'erreur exacte
    du parseur au modèle pour qu'il se corrige lui-même."""
    print(f"🤖 Traduction de la demande en spécification MonLang (modèle '{model}')...")

    attempt = 0
    last_error = None
    last_output = None
    last_prompt = user_prompt

    while attempt <= max_retries:
        try:
            if attempt == 0:
                spec_text = _call_ollama(user_prompt, model)
            else:
                spec_text = _call_ollama(
                    user_prompt, model,
                    correction_context={
                        "previous_prompt": last_prompt,
                        "previous_output": last_output,
                        "error": str(last_error),
                    },
                )
        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                f"❌ Impossible de joindre le serveur Ollama sur {OLLAMA_URL}. "
                f"Vérifiez qu'Ollama tourne bien en local ('ollama serve') et que "
                f"le modèle '{model}' est installé ('ollama pull {model}'). Détail : {e}"
            )
        except Exception as e:
            raise RuntimeError(f"❌ Erreur lors de l'appel au modèle IA : {e}")

        last_output = spec_text
        try:
            parse_monlang_string(spec_text)
            print(f"✅ Spécification générée et validée par le parseur (tentative {attempt + 1}/{max_retries + 1}).")
            return spec_text
        except Exception as e:
            last_error = e
            print(f"⚠️  Tentative {attempt + 1}/{max_retries + 1} : la spec générée ne compile pas ({e}).")
            attempt += 1

    raise RuntimeError(
        f"❌ Échec : l'IA n'a pas produit de spécification MonLang valide après "
        f"{max_retries + 1} tentative(s). Dernière erreur du parseur : {last_error}\n"
        f"Dernière sortie brute obtenue :\n{last_output}"
    )


def save_spec_to_file(spec_text, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(spec_text.strip() + "\n")
    print(f"💾 Spécification sauvegardée dans '{output_path}'.")
