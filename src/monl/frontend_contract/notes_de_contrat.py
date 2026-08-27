"""Ce que le contrat DIT à l'IA d'interface, en toutes lettres.

Une brique que le contrat ne décrit pas est une brique sans interface : ces
notes sont donc du produit, pas du commentaire. `_verrou_paiement` appelle
`_payment_locked_parents` du générateur et ne recalcule RIEN (point 91) —
deux vérités finiraient par diverger."""

from ..ir import CompilationPlans

_LIBELLES_IDENTIFIANT = {"email": "une adresse e-mail",
                         "phone": "un numéro de téléphone"}

def _libelle_identifiant(formes):
    """Ce que le champ 'username' doit RÉELLEMENT contenir (point 95)."""
    formes = [f for f in (formes or [])
              if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return "str"
    return "str — " + " ou ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)

def _note_identifiant(formes, phone_prefix=None):
    """Sans cette note, l'IA étiquette « nom d'utilisateur » et laisse un champ
    texte libre : l'utilisateur saisit un pseudo, récolte un 422, et l'écran ne
    lui dit pas pourquoi (point 95)."""
    formes = [f for f in (formes or []) if f in _LIBELLES_IDENTIFIANT]
    if not formes:
        return None
    quoi = " ou ".join(_LIBELLES_IDENTIFIANT[f] for f in formes)
    saisie = ("type=\"email\"" if formes == ["email"]
              else "type=\"tel\"" if formes == ["phone"]
              else "un champ texte acceptant les deux")
    prefix_note = (
        f" Pour le téléphone, l'indicatif déclaré est `{phone_prefix}` : "
        "accepter aussi la notation nationale et l'annoncer près du champ."
        if phone_prefix and "phone" in formes else ""
    )
    return (f"IDENTIFIANT : le champ `username` doit contenir {quoi} — 422 "
            f"sinon. L'étiqueter en conséquence à l'inscription ET à la "
            f"connexion (utiliser {saisie}), jamais « nom d'utilisateur ». "
            f"Le serveur met la valeur sous forme canonique (adresse en "
            f"minuscules, numéro réduit à ses chiffres) : deux écritures de la "
            f"même adresse sont le MÊME compte, et la connexion accepte l'une "
            f"comme l'autre.{prefix_note}")

def _note_liberation(regle):
    """Ce que l'interface doit savoir d'une valeur qui libère (point 98)."""
    if not regle:
        return None
    return (f"LIBÉRATION : passer `{regle['field']}` à « {regle['value']} » rend "
            f"ce que les {regle['releases']} liés avaient décompté (le stock, "
            f"typiquement). L'opération n'a lieu qu'à la TRANSITION : y repasser "
            f"une seconde fois ne rend rien de plus. Et c'est un aller SANS "
            f"retour — toute autre valeur est ensuite refusée en 409, car rien "
            f"ne garantit que ce qui a été rendu soit encore disponible. Ne pas "
            f"proposer de réactiver : proposer d'en créer un nouveau.")

def _verrou_paiement(plans: CompilationPlans, entite, inclure_soi=True):
    """Entité dont l'encaissement FIGE les écritures sur 'entite' — elle-même si
    elle est payable, sinon le parent dont elle alimente le total (point 91).

    `inclure_soi=False` pour la CRÉATION : une entité payable ne se verrouille
    pas elle-même à la création (elle n'existe pas encore), seul un parent déjà
    réglé refuse une ligne de plus.

    Source unique partagée avec le générateur : `_payment_locked_parents` est ce
    qui produit réellement les gardes dans app.py. Recalculer la chaîne ici en
    ferait deux vérités, dont l'une finirait fausse."""
    if inclure_soi and entite in plans.payable_by_entity:
        return entite
    verrous = plans.payment_locked_parents.get(entite, ())
    return verrous[0]["entity"] if verrous else None

def _note_verrou(verrou, creation=False):
    if not verrou:
        return None
    action = ("cette route refuse d'y rattacher un enregistrement de plus"
              if creation else "cette route répond 409 et n'écrit rien")
    return (f"VERROU : dès que le/la {verrou} est réglé (payment_status vaut "
            f"'payee'), {action} — 409. Masquer ou "
            f"désactiver l'action sur un enregistrement payé plutôt que de "
            f"laisser l'utilisateur la découvrir refusée — un montant encaissé "
            f"ne se modifie plus, il se rembourse chez le prestataire.")

def _note_message(regle):
    """Note de contrat pour une notification déclenchée par Create."""
    if not regle:
        return None
    return (
        "NOTIFICATION : après le commit réussi de cette création, une tentative "
        f"asynchrone envoie à l'adresse du compte le sujet « {regle['subject']} ». "
        "Afficher qu'une tentative de message a été lancée, sans promettre la "
        "remise : une panne SMTP n'annule pas l'écriture et est journalisée côté "
        "serveur.")

def _joindre(*notes):
    retenues = [n for n in notes if n]
    return " ".join(retenues) if retenues else None

def _note_superviseurs(supers, action_nom):
    """AJOUT (brique 23, point 106) : le rôle superviseur (declare via
    'sharedBy' sur une action regie par 'accessibleBy') transperce le controle
    par colonnes. Note de contrat : l'IA d'interface doit donner à ce rôle la
    vision/maîtrise de TOUT, et aux autres rôles seulement leurs parties."""
    if not supers:
        return None
    roles = ", ".join(supers)
    return (f"SUPERVISION ({action_nom}) : le rôle {roles} accède à TOUS les "
            f"enregistrements, sans restriction de parties. Les autres rôles "
            f"autorisés ici ne voient/modifient que les enregistrements dont "
            f"ils sont une des parties.")

def _note_list_query(query):
    """Texte court transmis à l'IA frontend avec le contrat JSON."""
    if not query:
        return None
    notes = []
    if query.get("filters"):
        filtres = []
        for item in query["filters"]:
            valeurs = item["allowed_values"]
            suffixe = (" parmi " + ", ".join(repr(v) for v in valeurs)
                       if valeurs is not None else " une valeur exacte du type du champ")
            filtres.append(f"paramètre {item['parameter']}{suffixe}")
        notes.append("FILTRAGE exact, seulement sur les champs déclarés : "
                     + "; ".join(filtres))
    if query.get("sort"):
        tri = query["sort"]
        notes.append("TRI : paramètre sort parmi "
                     + ", ".join(tri["fields"])
                     + ", avec direction=asc ou direction=desc. Aucun autre "
                     "champ, opérateur ou langage de recherche n'est accepté.")
    return " ".join(notes)
