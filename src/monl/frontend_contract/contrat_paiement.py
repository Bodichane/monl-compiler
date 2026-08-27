"""Encaissement : les deux routes, la devise, le prestataire, l'après-paiement.

La DEVISE fait partie de l'interface : sans elle, une boutique de Cotonou
affiche des euros sur des francs CFA. Le PRESTATAIRE aussi — « Payer par
carte » et « Payer par Mobile Money » ne se dessinent pas pareil."""

from ..ir import PAYMENT_STATUS_COLUMN
from . import champs


def _paiement_du_contrat(plans, routes):
    """Encaissement : les deux routes, la devise, le prestataire, et ce qui
    reste modifiable APRÈS règlement (point 113)."""
    # BRIQUE PAIEMENT (point 74). Ces deux routes ne sortent PAS de
    # route_map — elles ne naissent pas d'un workflow mais d'une règle
    # `payable` — et le contrat les ignorait donc. Conséquence concrète :
    # l'IA d'interface ne pouvait pas dessiner le bouton de règlement, et
    # se le serait de toute façon interdit, puisque le contrat lui défend
    # d'appeler un chemin absent de `routes`. Une brique que le contrat ne
    # décrit pas est une brique sans interface.
    payables = plans.payable_by_entity
    # BRIQUE 2a : la DEVISE fait partie de l'interface. Sans elle, l'IA écrit
    # « € » parce que c'est ce qu'elle a vu partout ailleurs, et une boutique
    # de Cotonou affiche des euros sur des francs CFA. L'exposant voyage avec
    # le code : c'est lui qui dit s'il faut diviser `montant_centimes` par cent
    # (euro) ou pas du tout (franc CFA).
    devise = plans.payment_currency or {"code": "EUR", "exponent": 2}
    # BRIQUE 2b : le prestataire fait partie de l'interface. « Payer par
    # carte » et « Payer par Mobile Money » ne se dessinent pas pareil, et
    # l'IA écrirait « carte bancaire » par défaut faute de le savoir.
    prestataire = plans.payment_provider or "stripe"
    for entite, champ in sorted(payables.items()):
        # POINT 87 : sous propriété transitive, « appartient » se lit à travers
        # l'intermédiaire, et un enregistrement dont l'intermédiaire a disparu
        # répond 404. L'interface doit connaître les deux, sinon elle traite un
        # 404 comme une erreur technique là où c'est une réponse métier.
        chaine = plans.transitive_ownership.get(entite)
        premier = chaine["chain"][0] if chaine else None
        via = (f"Ce {entite} appartient à qui possède son/sa "
               f"{premier} : c'est cette chaîne (de profondeur "
               f"{len(chaine['chain'])} maillon(s)) que le 403 vérifie, et "
               f"un {entite} dont le/la {premier} n'existe plus répond "
               f"404. " if premier else "")
        routes.append(champs._route(
            "POST", f"/{entite.lower()}/{{id}}/paiement", "Pay", entite,
            False, sorted(plans.actors),
            note=(via + "Ouvre une session de règlement pour cet enregistrement. "
                  "AUCUN corps : le montant est lu dans la base depuis "
                  f"`{champ}`, jamais reçu du client. Réponse : {{status, url, "
                  "session_id, montant_centimes, devise, montant} — rediriger "
                  "le navigateur vers `url`. "
                  # Le nom `montant_centimes` est conservé (point 95 : le
                  # renommer casserait le bouton « Payer » de tout projet
                  # existant), mais il ne veut PAS dire « centimes » partout :
                  # c'est l'unité mineure de la devise. Le dire est la seule
                  # façon d'empêcher une interface de diviser par cent un
                  # montant en francs CFA.
                  + (f"Le règlement passe par **{prestataire}** : "
                     + ("le payeur choisit son opérateur de MOBILE MONEY "
                        "(MTN MoMo, Moov, Wave) sur la page du prestataire — "
                        "ne pas écrire « carte bancaire ». "
                        if prestataire == "fedapay"
                        else "le payeur règle par carte sur la page du "
                             "prestataire. "))
                  + f"Les montants sont en **{devise['code']}** : afficher "
                  f"`montant` tel quel avec ce code, et ne JAMAIS diviser "
                  f"`montant_centimes` par cent sans regarder l'exposant — "
                  + ("cette devise n'a pas de sous-unité, les deux champs "
                     "portent la même valeur. " if devise["exponent"] == 0
                     else f"ici l'exposant vaut {devise['exponent']}. ")
                  + "403 si l'enregistrement appartient à "
                  "quelqu'un d'autre, 409 s'il est déjà réglé, 503 si le "
                  "serveur n'a pas de clé de paiement configurée. "
                  # Point 76 : boucler la boucle. Savoir ouvrir un règlement
                  # ne dit pas comment en montrer l'issue ; c'est le champ de
                  # suivi qui la porte, et il n'est PAS à jour au retour du
                  # prestataire (c'est son webhook qui l'écrit, plus tard).
                  f"L'issue se lit dans `{PAYMENT_STATUS_COLUMN}` de "
                  f"{entite} ('en_attente' / 'payee') : ne pas l'annoncer "
                  "payé au retour de l'utilisateur, le webhook du "
                  "prestataire peut n'être pas encore arrivé.")))
    if payables:
        routes.append(champs._route(
            "POST", "/paiement/webhook", "Webhook", "Paiement", False, [],
            note=("Appelée par le PRESTATAIRE de paiement, jamais par le "
                  "frontend : elle exige une signature que seul le "
                  "prestataire sait produire. Listée ici pour que la liste "
                  "des routes reste exhaustive, pas pour être appelée.")))

    # BRIQUE writableAfterPayment. Cette route est générée hors de route_map,
    # comme celles de paiement ci-dessus : elle doit donc rejoindre le contrat
    # explicitement. Sinon les champs sont bien marqués `postpayment_only`,
    # mais l'interface n'a aucun chemin autorisé pour les modifier.
    postpayment = plans.postpayment_writable_by_entity
    for entite, config in sorted(postpayment.items()):
        fields = list(config["fields"])
        routes.append(champs._route(
            "PUT", f"/{entite.lower()}/{{id}}/apres-paiement",
            "UpdateAfterPayment", entite, False, [config["actor"]],
            request_fields=fields,
            note=("Écriture réservée au rôle superviseur après règlement : "
                  f"permet de renseigner {', '.join(f'`{f}`' for f in fields)}. "
                  "Tous les champs sont facultatifs dans le corps ; envoyer "
                  "uniquement ceux qui changent. 404 si l'enregistrement "
                  "n'existe pas, 403 pour tout autre rôle.")))
    return devise, payables, prestataire
