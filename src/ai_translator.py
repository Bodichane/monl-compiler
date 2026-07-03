import os
import sys
from llama_cpp import Llama

SYSTEM_PROMPT = """
Tu es le moteur de traduction IA officiel du langage "MonLang". 
Ton unique rôle est de traduire une demande utilisateur en langage naturel vers une spécification MonLang valide au format YAML.

Tu dois impérativement respecter la syntaxe stricte suivante :
1. Commencer par : app NomDeLApp
2. Déclarer les entités avec 4 espaces d'indentation pour leurs attributs. Types valides : String, Text, Integer, Float, Boolean, Date, DateTime, Email, UUID, Money.
3. Déclarer les relations : relation EntiteA hasMany/belongsTo/hasOne EntiteB
4. Déclarer les acteurs : actor NomActeur
5. Déclarer les contraintes : rule Entite.attribut required/unique/min/max
6. Déclarer les workflows : workflow NomDuWorkflow for NomActeur (suivi des actions Create/Read/Update/Delete avec 4 espaces)

Exemple de sortie attendue :
app TodoApp
entity Todo
    title: String
    completed: Boolean
relation User hasMany Todo
actor User
rule Todo.title required
workflow Manage for User
    Create Todo

CONSIGNE CRUCIALE : Ne donne AUCUNE explication, aucun texte de politesse, pas de balises markdown. Renvoie UNIQUEMENT le code MonLang brut.
"""

def prompt_to_monlang(user_prompt):
    model_path = os.path.join(os.path.dirname(__file__), "../models/qwen2.5-coder-3b.gguf")
    
    if not os.path.exists(model_path):
        print(f"❌ Erreur : Le modèle GGUF est introuvable dans '{model_path}'")
        return None
        
    print("🤖 Chargement du modèle IA local en cours (cela peut prendre quelques secondes)...")
    try:
        # Initialisation du modèle en local (n_ctx=2048 pour la mémoire)
        llm = Llama(model_path=model_path, n_ctx=2048, verbose=False)
        
        print("✍️  L'IA analyse votre demande et rédige le fichier MonLang...")
        
        # Structuration de la requête au format Chat
        prompt = f"<|im_start|>system\n{SYSTEM_PROMPT}<|im_end|>\n<|im_start|>user\n{user_prompt}<|im_end|>\n<|im_start|>assistant\n"
        
        response = llm(prompt, max_tokens=1024, stop=["<|im_end|>"], echo=False)
        generated_code = response["choices"][0]["text"].strip()
        return generated_code
        
    except Exception as e:
        print(f"❌ Erreur lors de l'exécution du modèle local : {e}")
        return None

if __name__ == "__main__":
    test_prompt = "Je veux une application de gestion de bibliothèque. Il y a des Livres (titre, isbn). Il y a des Membres (nom, email unique). Un membre peut emprunter plusieurs livres. Le bibliothécaire peut ajouter des livres."
    
    result = prompt_to_monlang(test_prompt)
    if result:
        print("\n✨ SPÉCIFICATION MONLANG GÉNÉRÉE PAR L'IA EN LOCAL :")
        print("-" * 50)
        print(result)
        print("-" * 50)
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        