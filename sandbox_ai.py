# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX
# Ce fichier contient uniquement des fonctions de logique pure.
# L'IA a interdiction de modifier l'infrastructure ou d'accéder à la base de données.

def autoArchiveTodo(context: dict) -> dict:
    """
    CONSIGNE IA : Logique métier custom.
    """
    title = context.get('Todo.title', '')
    if '[Archive]' in title:
        return {'status': 'archived'}
    else:
        return {'status': 'active'}
