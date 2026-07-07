# ÉCHAPPATOIRE IA BALISÉ - ZONE DE SANDBOX

def autoArchiveTodo(context: dict) -> dict:
    """
    CONSIGNE IA : Analyse le titre et archive automatiquement si le mot clé [Archive] est detecté
    """
    title = context.get('reference', '').get('title', '')
    if '[Archive]' in title:
        return {'status': 'archived'}
    return {'status': 'active'}
