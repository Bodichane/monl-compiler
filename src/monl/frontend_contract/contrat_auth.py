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
    if auth_features.get("verify_email"):
        routes.extend([
            champs._route("POST", "/verify-email", "VerifyEmail", "Authentication",
                          True, [], request_fields=["username", "token"],
                          note="Confirmation by POST: opaque token bound to the account, single use and time-limited. No GET consumes the link."),
            champs._route("POST", "/verify-email/resend", "VerifyEmailResend", "Authentication",
                          True, [], request_fields=["username"],
                          note="Rate-limited resend, generic response with the same duration floor, even when the limit is reached."),
        ])
    if auth_features.get("password_reset"):
        routes.extend([
            champs._route(
                "POST", "/password-reset/request", "PasswordResetRequest",
                "Authentication", True, [], request_fields=["username"],
                note=("Generic response with the same duration floor whether "
                      "the account exists or not; never announce whether a "
                      "message was sent.")),
            champs._route(
                "POST", "/password-reset/confirm", "PasswordResetConfirm",
                "Authentication", True, [],
                request_fields=["username", "token", "password"],
                note=("Opaque, single-use, time-limited token: the server "
                      "never returns it through a read route; a password "
                      "change does not change the role.")),
        ])
    if auth_features.get("refresh_tokens"):
        refresh_route = champs._route(
            "POST", "/refresh", "Refresh", "Authentication", False,
            auth_actors, request_fields=["refresh_token"],
            note=("Present the opaque refresh token, not the access JWT. "
                  "Each success revokes it and issues a new one; a revoked "
                  "or expired token answers 401."))
        refresh_route["auth_mode"] = "refresh_token"
        routes.append(refresh_route)
    if auth_features.get("totp"):
        routes.extend([
            champs._route(
                "POST", "/totp/setup", "TotpSetup", "Authentication", False,
                auth_actors,
                note=("Authenticated activation flow, to be shown only once; "
                      "do not turn its response into a read route.")),
            champs._route(
                "POST", "/totp/enable", "TotpEnable", "Authentication", False,
                auth_actors, request_fields=["code", "password"],
                note=("Enables two-factor authentication after checking a "
                      "current TOTP code and the current password; revokes every "
                      "session and requires a new sign-in with TOTP.")),
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
                                  "user_id": "int — the identifier of the created account"},
                     "self_register_actors": list(plans.self_register_actors),
                     "body": {"username": notes_de_contrat._libelle_identifiant(plans.auth_identifier),
                              "password": "str (8+ characters)",
                              "actor": f"a role among {list(plans.self_register_actors)}"},
                     # POINT 95 : le champ reste nommé 'username' SUR LE
                     # FIL (le renommer casserait le formulaire de tout
                     # projet existant) — c'est ici que le contrat dit
                     # ce qu'il doit vraiment contenir, et l'IA qui
                     # étiquette l'écran en conséquence.
                     "identifier_forms": list(plans.auth_identifier or ()),
                     "phone_prefix": plans.auth_phone_prefix,
                     "note": notes_de_contrat._joindre(
                         ("403 if the requested role is not open to self-registration"
                          if plans.self_register_actors else
                          "no open role: registration is closed, "
                          "accounts are created with manage.py"),
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
                      "access_token": "str — the JWT, to put in the "
                                      "Authorization: Bearer header",
                      "token_type": "'bearer'"},
                  "returns": "a JWT in the `access_token` field "
                             "(valid 2 h by default, "
                             "configurable with MONL_TOKEN_TTL_HOURS)"},
        "logout": {"method": "POST", "path": "/logout",
                   "response": {"status": "'success'", "detail": "str"}},
        "header": "Authorization: Bearer <token> on every non-public route",
        "rate_limit": "5 attempts / 60 s / IP on /register and /login",
    }
    if auth_features.get("totp"):
        auth_contract["login"]["body"]["totp_code"] = (
            "str (6 digits, required once two-factor authentication is enabled)")
    if auth_features.get("refresh_tokens"):
        auth_contract["login"]["returns"] = (
            "an access JWT in `access_token` (validity configurable with "
            "MONL_TOKEN_TTL_SECONDS) and an opaque refresh token "
            "in `refresh_token`")
        auth_contract["login"]["response"]["refresh_token"] = (
            "str — OPAQUE refresh token (it is not a JWT), "
            "to keep and replay on POST /refresh")
    b4_contract = {}
    if auth_features.get("verify_email"):
        auth_contract["login"]["errors"] = {
            "403": {"code": "email_not_verified", "message": "Confirm your email address before signing in."},
            "401": "Invalid credentials. (wrong password or missing account)",
        }
        auth_contract["register"]["response"] = {"status": "pending", "user_id": "int", "detail": "str"}
        auth_contract["register"]["note"] += " Confirmation required, no session token before confirmation. A new registration on an unconfirmed address replaces the password and resends a message within the verify_resend quota; warn the user."
        b4_contract["verify_email"] = {
            "confirm_path": "/verify-email", "resend_path": "/verify-email/resend",
            "confirm_body": {"username": "str", "token": "str"},
            "ttl_seconds": auth_features["verify_email"],
            "resend": auth_features["verify_resend"],
            "single_use": True, "invalidated_on_resend": True,
            "login_unconfirmed": {"status": 403, "code": "email_not_verified"},
            "online_registration_only": True,
            "unconfirmed_registration": "A new registration replaces the password and resends a message, within the verify_resend quota. The frontend must warn the user.",
        }
    if auth_features.get("lockout"):
        b4_contract["account_lockout"] = {
            "max_attempts": auth_features["lockout"]["max_attempts"],
            "window_seconds": auth_features["lockout"]["window_seconds"],
            "failure_response": "generic 401, identical to a missing account",
        }
    if auth_features.get("password_reset"):
        b4_contract["password_reset"] = {
            "request_path": "/password-reset/request",
            "confirm_path": "/password-reset/confirm",
            "ttl_seconds": auth_features["password_reset"],
            "single_use": True,
            "invalidated_on_password_change": True,
            "privacy": "generic response and identical duration floor, no enumeration",
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
            "enable_body": {"code": "string", "password": "string (required, current password)"},
            "enable_invalidates_sessions": True,
            "step_seconds": 30,
            "replay_protection": True,
        }
    if b4_contract:
        auth_contract["features"] = b4_contract
    return auth_contract, b4_contract
