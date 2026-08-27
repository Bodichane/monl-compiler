"""Le contrat d'authentification et les parcours de la brique B4.

Une spec historique ne gagne ni route ni octet de contrat par défaut : les
parcours ne sont ajoutés que si la spec les déclare."""

from . import champs, notes_de_contrat


def _fonctions_dauth(plans, routes):
    """Les parcours d'authentification déclarés (brique B4)."""
    # BRIQUE B4 : ces parcours ne viennent d'aucun workflow métier. Ils sont
    # donc ajoutés ici, exactement comme les routes de paiement, et seulement
    # si la spec les déclare. Une spec historique ne gagne ainsi ni route ni
    # octet de contrat par défaut.
    auth_features = dict(plans.auth_features or {})
    auth_actors = sorted(plans.actors)
    if auth_features.get("password_reset"):
        routes.extend([
            champs._route(
                "POST", "/password-reset/request", "PasswordResetRequest",
                "Authentication", True, [], request_fields=["username"],
                note=("Réponse générique et de durée plancher identique que le "
                      "compte existe ou non ; ne jamais annoncer si un message "
                      "est parti.")),
            champs._route(
                "POST", "/password-reset/confirm", "PasswordResetConfirm",
                "Authentication", True, [],
                request_fields=["username", "token", "password"],
                note=("Jeton opaque à usage unique et durée limitée : le "
                      "serveur ne le renvoie jamais par une route de lecture ; "
                      "un changement de mot de passe ne change pas le rôle.")),
        ])
    if auth_features.get("refresh_tokens"):
        refresh_route = champs._route(
            "POST", "/refresh", "Refresh", "Authentication", False,
            auth_actors, request_fields=["refresh_token"],
            note=("Présenter le jeton de rafraîchissement opaque, pas le JWT "
                  "d'accès. Chaque succès le révoque et en émet un nouveau ; "
                  "un jeton révoqué ou expiré répond 401."))
        refresh_route["auth_mode"] = "refresh_token"
        routes.append(refresh_route)
    if auth_features.get("totp"):
        routes.extend([
            champs._route(
                "POST", "/totp/setup", "TotpSetup", "Authentication", False,
                auth_actors,
                note=("Parcours d'activation authentifié, à afficher une seule "
                      "fois ; ne pas transformer sa réponse en route de lecture.")),
            champs._route(
                "POST", "/totp/enable", "TotpEnable", "Authentication", False,
                auth_actors, request_fields=["code"],
                note=("Active le double facteur après vérification d'un code "
                      "TOTP courant.")),
        ])
    return auth_features

def _auth_du_contrat(auth_features, plans):
    """Le contrat d'authentification, assemblé."""
    auth_contract = {
        # AJOUT (bêta 3) : seuls les rôles marqués 'selfRegister' dans la
        # spec peuvent être choisis à l'inscription — les autres sont
        # provisionnés hors ligne (manage.py) et renvoient 403 ici.
        # L'interface ne doit donc proposer QUE cette liste.
        "register": {"method": "POST", "path": "/register",
                     "response": {"status": "'success'",
                                  "user_id": "int — l'identifiant du compte créé"},
                     "self_register_actors": list(plans.self_register_actors),
                     "body": {"username": notes_de_contrat._libelle_identifiant(plans.auth_identifier),
                              "password": "str (8+ caractères)",
                              "actor": f"un rôle parmi {list(plans.self_register_actors)}"},
                     # POINT 95 : le champ reste nommé 'username' SUR LE
                     # FIL (le renommer casserait le formulaire de tout
                     # projet existant) — c'est ici que le contrat dit
                     # ce qu'il doit vraiment contenir, et l'IA qui
                     # étiquette l'écran en conséquence.
                     "identifier_forms": list(plans.auth_identifier or ()),
                     "phone_prefix": plans.auth_phone_prefix,
                     "note": notes_de_contrat._joindre(
                         ("403 si le rôle demandé n'est pas ouvert à l'inscription libre"
                          if plans.self_register_actors else
                          "aucun rôle ouvert : l'inscription est fermée, "
                          "les comptes sont créés par manage.py"),
                         notes_de_contrat._note_identifiant(plans.auth_identifier,
                                           plans.auth_phone_prefix))},
        # POINT 76 APPLIQUÉ À L'AUTHENTIFICATION. Le contrat doit dire ce que
        # le backend renvoie VRAIMENT, pas seulement qu'il renvoie quelque
        # chose. `returns` annonçait « un token JWT » sans jamais NOMMER la
        # clé JSON : une IA d'interface devait deviner entre `token`,
        # `access_token` et `jwt`. Trompée, elle envoie
        # `Authorization: Bearer undefined` — et c'est le pire cas de figure :
        # aucune exception JavaScript, aucun appel hors contrat, donc LE SMOKE
        # TEST PASSE et personne ne peut se connecter.
        #
        # Que ce soit un oubli et non un choix se lit dans le brief lui-même :
        # la réponse paginée y est nommée au caractère près depuis toujours
        # (`{status, total, limit, offset, data}`), et la brique B4 nomme son
        # `refresh_token`. Seule la réponse d'origine ne s'était jamais
        # décrite.
        #
        # AUCUNE entrée nouvelle dans `_contract_signature` (cli.py), et c'est
        # délibéré : la seule chose qui fasse varier cette forme est
        # `capability refresh_tokens`, dont la configuration est déjà hachée
        # sous « authentification B4 ». Ajouter un second témoin de la même
        # variation ferait rapporter deux fois le même changement.
        "login": {"method": "POST", "path": "/login",
                  "body": {"username": "str", "password": "str"},
                  "response": {
                      "access_token": "str — le JWT, à placer dans l'en-tête "
                                      "Authorization: Bearer",
                      "token_type": "'bearer'"},
                  "returns": "un token JWT dans le champ `access_token` "
                             "(validité 2 h par défaut, "
                             "réglable par MONL_TOKEN_TTL_HOURS)"},
        "logout": {"method": "POST", "path": "/logout",
                   "response": {"status": "'success'", "detail": "str"}},
        "header": "Authorization: Bearer <token> sur toute route non publique",
        "rate_limit": "5 tentatives / 60 s / IP sur /register et /login",
    }
    if auth_features.get("totp"):
        auth_contract["login"]["body"]["totp_code"] = (
            "str (6 chiffres, requis après activation du double facteur)")
    if auth_features.get("refresh_tokens"):
        auth_contract["login"]["returns"] = (
            "un token JWT d'accès dans `access_token` (validité réglable par "
            "MONL_TOKEN_TTL_SECONDS) et un jeton de rafraîchissement opaque "
            "dans `refresh_token`")
        auth_contract["login"]["response"]["refresh_token"] = (
            "str — jeton OPAQUE de rafraîchissement (ce n'est pas un JWT), "
            "à conserver et à rejouer sur POST /refresh")
    b4_contract = {}
    if auth_features.get("lockout"):
        b4_contract["account_lockout"] = {
            "max_attempts": auth_features["lockout"]["max_attempts"],
            "window_seconds": auth_features["lockout"]["window_seconds"],
            "failure_response": "401 générique, identique à un compte inexistant",
        }
    if auth_features.get("password_reset"):
        b4_contract["password_reset"] = {
            "request_path": "/password-reset/request",
            "confirm_path": "/password-reset/confirm",
            "ttl_seconds": auth_features["password_reset"],
            "single_use": True,
            "invalidated_on_password_change": True,
            "privacy": "réponse générique et durée plancher identique, sans énumération",
        }
    if auth_features.get("refresh_tokens"):
        b4_contract["refresh_tokens"] = {
            "path": "/refresh",
            "ttl_seconds": auth_features["refresh_tokens"],
            "rotation": True,
            "access_token_is_jwt": True,
            "refresh_token_is_jwt": False,
        }
    if auth_features.get("totp"):
        b4_contract["totp"] = {
            "setup_path": "/totp/setup",
            "enable_path": "/totp/enable",
            "step_seconds": 30,
            "replay_protection": True,
        }
    if b4_contract:
        auth_contract["features"] = b4_contract
    return auth_contract, b4_contract
