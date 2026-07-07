# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX
# Ce fichier contient uniquement des fonctions de logique pure.
# L'IA a interdiction de modifier l'infrastructure ou d'accéder à la base de données.

def autoArchiveTodo(context: dict) -> dict:
    """
    CONSIGNE IA : Analyse le titre et archive automatiquement si le mot clé [Archive] est detecté
    """
    title = context.get('Todo.title', '')
    if '[Archive]' in title:
        return {'status': 'archived'}
    return {'status': 'active'}
