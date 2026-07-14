import os
import re
import json
import html
import requests
from ast_validator import MonLangAST
from parser import parse_monlang_file

# AJOUT (roadmap, front marketing) : échappatoire IA pour la landing "/",
# construite exactement sur le même schéma que ai_sandbox_filler.py pour les
# fonctions "custom" — un pont Ollama local, non bloquant, avec un garde-fou
# d'analyse statique avant toute injection dans un artefact déjà généré.
#
# DIFFÉRENCE DE FOND avec ai_sandbox_filler.py : là où la sandbox "custom"
# laisse l'IA écrire du CODE PYTHON (vérifié par un vrai garde-fou AST contre
# les imports dangereux, l'injection SQL, etc.), ici l'IA n'a JAMAIS le droit
# d'écrire du HTML/CSS/JS : elle ne renvoie que du TEXTE BRUT (titre,
# sous-titre uniquement -- le reste de la page est fonctionnel, pas rédigé),
# inséré dans un gabarit HTML
# déjà entièrement construit par le générateur déterministe (voir
# generator.py::_generate_landing_ai_shell). Le risque n'est donc pas
# l'exécution de code arbitraire côté serveur (comme pour "custom"), mais
# l'injection de contenu (XSS) dans une page servie à de vrais visiteurs
# anonymes -- d'où un garde-fou différent, taillé pour du texte : rejet de
# tout ce qui ressemble à une balise ou un gestionnaire d'évènement, et
# échappement HTML systématique même après le rejet de motifs dangereux
# (défense en profondeur : le garde-fou peut avoir un trou, l'échappement
# rattrape le coup).

OLLAMA_URL = "http://localhost:11434/api/chat"
LANDING_KEYS = ["headline", "subheadline"]

# Motifs refusés dans un champ de copie marketing : tout ce qui pourrait
# constituer une balise HTML, un gestionnaire d'évènement JS, ou un schéma
# d'URL exécutable. Volontairement large (mieux vaut rejeter un texte
# légitime border-line que laisser passer une tentative d'injection).
_DANGEROUS_PATTERN = re.compile(
    r"<[a-zA-Z/!]|javascript:|data:text/html|on\w+\s*=", re.IGNORECASE
)


def validate_generated_landing_copy_safety(fields: dict):
    """Garde-fou dédié au texte marketing (pendant, pour la landing, du
    garde-fou AST de ai_sandbox_filler.py pour le code Python) : chaque champ
    doit être une chaîne courte, sans rien qui ressemble à du HTML/JS actif.
    Lève une exception si un champ est absent, trop long, ou suspect --
    l'appelant (run_landing_ai_filler) traite toute exception ici comme un
    échec non bloquant de l'étape IA, exactement comme pour 'custom'."""
    for key in LANDING_KEYS:
        if key not in fields:
            raise ValueError(f"Champ manquant dans la réponse IA : '{key}'.")
        value = fields[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Champ '{key}' vide ou non textuel dans la réponse IA.")
        max_len = 90 if key in ("headline", "subheadline") else 40
        if len(value) > max_len:
            raise ValueError(f"Champ '{key}' trop long ({len(value)} caractères, max {max_len}).")
        if _DANGEROUS_PATTERN.search(value):
            raise PermissionError(
                f"🛑 [SECURITY_BLOCKED] Le champ '{key}' généré par l'IA contient un motif "
                f"HTML/JS actif interdit dans un contenu de landing — rejeté."
            )
    print("🛡️  [GUARDRAIL] La copie marketing générée par l'IA a passé le contrôle anti-injection.")


def generate_landing_copy_with_ai(app_name, entity_names, brief):
    """Interroge Ollama au format JSON strict pour obtenir uniquement du
    texte marketing (jamais de HTML) — même modèle et même schéma de requête
    que generate_custom_logic_with_ai dans ai_sandbox_filler.py."""
    print(f"🤖 L'IA locale (Qwen) rédige la copie marketing de la landing pour '{app_name}'...")

    prompt = f"""
    Tu rédiges le titre et le sous-titre d'une page d'accueil pour une
    application logicielle réelle. Le reste de la page (formulaires,
    aperçu de données) est déjà fonctionnel et généré séparément — tu ne
    rédiges QUE ces deux phrases.

    Application : {app_name}
    Entités principales gérées par l'app : {", ".join(entity_names) or "aucune"}
    Brief du client (peut être vide) : {brief or "aucun, improvise à partir du nom et des entités"}

    Consignes strictes :
    - Sois CONCRET : décris ce que l'app fait réellement (nomme les entités
      ci-dessus si pertinent), jamais de formule marketing vague ("boostez
      votre productivité", "révolutionnez votre workflow", etc.).
    - Aucun superlatif creux ("le meilleur", "incroyable", "révolutionnaire").
    - Le sous-titre doit rester factuel, comme une description de fonctionnalité.

    Réponds UNIQUEMENT au format JSON avec exactement ces 2 clés, chacune une
    chaîne de texte brut (pas de HTML, pas de markdown) :
    - "headline" : titre principal, factuel, moins de 10 mots
    - "subheadline" : une phrase décrivant concrètement ce que l'app permet de faire, moins de 20 mots

    Exemple de format attendu :
    {{"headline": "...", "subheadline": "..."}}
    """

    payload = {
        "model": "qwen2.5-coder:3b",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.4},
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=90)
        response.raise_for_status()
        return json.loads(response.json()["message"]["content"])
    except Exception as e:
        raise RuntimeError(f"Erreur d'API : {e}")


def inject_copy_into_landing(fields: dict):
    """Remplace, dans 'landing.html' déjà généré par le socle déterministe,
    le contenu situé entre chaque paire de marqueurs
    <!--LANDING:clé-->...<!--/LANDING:clé--> — jamais rien d'autre dans le
    fichier. Le texte est échappé HTML avant insertion (défense en
    profondeur, en plus du garde-fou de validate_generated_landing_copy_safety).
    Si 'headline' ou 'cta_label' apparaissent à plusieurs endroits du gabarit
    (ex. le CTA de la barre de nav ET celui du corps de page), TOUTES les
    occurrences de la clé sont remplacées, pas seulement la première."""
    landing_path = os.path.join(os.path.dirname(__file__), "../landing.html")
    if not os.path.exists(landing_path):
        print(f"❌ Erreur : '{landing_path}' n'existe pas (le socle déterministe n'a pas été généré).")
        return

    with open(landing_path, "r", encoding="utf-8") as f:
        content = f.read()

    replaced = []
    for key, value in fields.items():
        safe_value = html.escape(value.strip())
        pattern = re.compile(
            r"<!--LANDING:" + re.escape(key) + r"-->.*?<!--/LANDING:" + re.escape(key) + r"-->",
            re.DOTALL,
        )
        new_content, n = pattern.subn(f"<!--LANDING:{key}-->{safe_value}<!--/LANDING:{key}-->", content)
        if n:
            content = new_content
            replaced.append(key)

    with open(landing_path, "w", encoding="utf-8") as f:
        f.write(content)

    print(f"🔒 Injection réussie ! Copie marketing IA appliquée à : {', '.join(replaced)}.")


def run_landing_ai_filler(file_path):
    """Point d'entrée appelé (non bloquant) depuis main.py après la
    génération du socle déterministe — même orchestration que run_ai_filler
    dans ai_sandbox_filler.py. Ne fait rien si la spec n'a pas de bloc
    'landing', ou si son mode n'est pas 'ai' (le mode 'template' n'appelle
    jamais l'IA, par construction)."""
    raw_json = parse_monlang_file(file_path)
    ast_manager = MonLangAST(raw_json)
    normalized_ast = ast_manager.validate_and_audit()

    landing_config = normalized_ast.get("landing")
    if not landing_config or landing_config.get("mode") != "ai":
        return False

    app_name = normalized_ast["meta"]["appName"]
    entity_names = list(normalized_ast["schema"]["entities"].keys())
    brief = landing_config.get("brief")

    fields = generate_landing_copy_with_ai(app_name, entity_names, brief)
    validate_generated_landing_copy_safety(fields)
    inject_copy_into_landing(fields)
    return True
