"""Les blocs `capability`, et la forme de l'identifiant de compte.

POINT 95 : `capability auth` contraint la FORME de l'identifiant. La
substance n'est pas la validation, c'est la NORMALISATION — sans forme
canonique, l'unicité se contourne en changeant une majuscule."""

from .socle import (
    DEVISE_PAR_DEFAUT,
    DEVISES,
    DEVISES_PAR_PRESTATAIRE,
    PRESTATAIRE_PAR_DEFAUT,
    PRESTATAIRES,
    PRESTATAIRES_ECARTES,
    ASTValidationError,
)


class CapacitesMixin:
    """Les blocs `capability`, et la forme de l'identifiant de compte."""

    # POINT 95 : formes reconnues pour l'identifiant de compte. 'libre' est le
    # comportement historique (n'importe quelle chaîne) et reste le défaut :
    # une spec qui ne dit rien compile exactement comme avant.
    FORMES_IDENTIFIANT = ("email", "phone", "libre")

    def _valider_identifiant_de_compte(self, capacites):
        """Formes acceptées par '/register', déclarées sur 'capability auth'.

        Retourne None quand rien n'est déclaré — et ce None compte : il vaut
        « aucune contrainte », pas « email par défaut ». Deviner ici
        verrouillerait tous les projets existants au premier recompilage."""
        formes, prefixe = None, None
        for capacite in capacites:
            if "phone_prefix" in capacite:
                valeur = capacite["phone_prefix"].strip()
                # Un indicatif est un '+' suivi de 1 à 4 chiffres : pas de
                # motif à importer pour si peu, et une dépendance de moins.
                if not (valeur.startswith("+") and valeur[1:].isdigit()
                        and 1 <= len(valeur) - 1 <= 4):
                    raise ASTValidationError(
                        f"Structure: 'phone_prefix' must be an international "
                        f"calling code—a '+' followed by 1 to 4 digits "
                        f"(found: {valeur!r}).")
                prefixe = valeur
            if "identifier" not in capacite:
                continue
            if capacite["name"] != "auth":
                raise ASTValidationError(
                    f"Structure: 'identifier' only makes sense on "
                    f"'capability auth' (found on '{capacite['name']}')— "
                    "it constrains registration.")
            demandees = list(dict.fromkeys(capacite["identifier"]))
            inconnues = [f for f in demandees if f not in self.FORMES_IDENTIFIANT]
            if inconnues:
                raise ASTValidationError(
                    f"Structure: unknown identifier form(s): "
                    f"{', '.join(inconnues)}. Recognized forms: "
                    f"{', '.join(self.FORMES_IDENTIFIANT)}.")
            # 'libre' accepte tout : le cumuler avec une forme stricte annule
            # cette dernière sans le dire. Un refus vaut mieux qu'une règle
            # écrite qui ne produit rien — c'est tout le point 85.
            if "libre" in demandees and len(demandees) > 1:
                raise ASTValidationError(
                    "Structure: 'identifier: libre' already accepts any "
                    "string—combining it with "
                    f"{', '.join(f for f in demandees if f != 'libre')} "
                    "would add no constraint and imply otherwise.")
            if formes is not None:
                raise ASTValidationError(
                    "Structure: 'identifier' declared twice on "
                    "'capability auth'—there must be one list; otherwise, "
                    "which one applies?")
            formes = demandees
        # Un indicatif sans forme 'phone' ne produirait RIEN : c'est ce que le
        # point 85 refuse. Le dire vaut mieux que le laisser croire appliqué.
        if prefixe and not (formes and "phone" in formes):
            raise ASTValidationError(
                "Structure: 'phone_prefix' only makes sense with "
                "'identifier: … phone'—without a number to canonicalize, "
                "it would have no effect.")
        self.auth_phone_prefix = prefixe
        return formes

    def _valider_capacites(self):
        """Valide les capacités déclarées et prépare l'authentification B4."""
        known_capabilities = {"auth", "payment"}
        names = [capability["name"] for capability in self.capabilities_raw]
        unknown = [name for name in names if name not in known_capabilities]
        if unknown:
            raise ASTValidationError(
                f"Structure: unknown capability/capabilities declared with 'capability': {', '.join(unknown)}. "
                f"Recognized capabilities: {', '.join(sorted(known_capabilities))}."
            )
        self.capabilities = list(dict.fromkeys(names))
        self.auth_identifier = self._valider_identifiant_de_compte(self.capabilities_raw)

        allowed_auth_options = {
            "name", "identifier", "phone_prefix", "lockout", "password_reset",
            "refresh_tokens", "totp", "verify_email", "verify_resend",
        }
        # BRIQUE 2a : 'currency' est la première option qui n'appartient PAS à
        # 'capability auth'. La grammaire partage un seul jeu de propriétés
        # entre toutes les capacités — c'est donc ici, et nulle part ailleurs,
        # que chaque option est rattachée à sa capacité.
        allowed_payment_options = {"currency", "provider"}
        options_par_capacite = {
            "auth": allowed_auth_options - {"name"},
            "payment": allowed_payment_options,
        }
        features = {}
        self.payment_currency = None
        self.payment_provider = None
        for capability in self.capabilities_raw:
            nom = capability["name"]
            options = set(capability) - {"name"}
            permises = options_par_capacite.get(nom, set())
            hors_sujet = options - permises
            if hors_sujet:
                # Nommer la capacité qui ACCEPTE l'option, quand elle existe :
                # « currency n'a pas de sens ici » enverrait chercher une faute
                # de frappe alors que la ligne est simplement au mauvais
                # endroit.
                accueil = {opt: cap
                           for cap, opts in options_par_capacite.items()
                           for opt in opts}
                remedes = sorted(
                    f"'{opt}' belongs under 'capability {accueil[opt]}'"
                    for opt in hors_sujet if opt in accueil)
                inconnues = sorted(opt for opt in hors_sujet if opt not in accueil)
                detail = "; ".join(remedes + [f"'{o}' is unknown" for o in inconnues])
                raise ASTValidationError(
                    f"Structure: misplaced or unknown option(s) on "
                    f"'capability {nom}'—{detail}.")
            if nom == "payment" and "provider" in capability:
                if self.payment_provider is not None:
                    raise ASTValidationError(
                        "Structure: the payment provider is declared twice— "
                        "an application can accept payments through only ONE "
                        "provider, or the webhook cannot know which signature "
                        "to verify.")
                self.payment_provider = self._valider_prestataire(
                    capability["provider"])
            if nom == "payment" and "currency" in capability:
                if self.payment_currency is not None:
                    raise ASTValidationError(
                        "Structure: the currency is declared twice—an "
                        "application accepts payments in only ONE currency, "
                        "or 'montant' no longer has a consistent meaning "
                        "across orders.")
                self.payment_currency = self._valider_devise(capability["currency"])
            if nom != "auth":
                continue
            for option in ("lockout", "password_reset", "refresh_tokens", "totp",
                           "verify_email", "verify_resend"):
                if option not in capability:
                    continue
                if option in features:
                    raise ASTValidationError(
                        f"Structure: option '{option}' is declared twice "
                        "on 'capability auth'.")
                features[option] = capability[option]

        lockout = features.get("lockout")
        if lockout:
            if lockout["max_attempts"] < 1:
                raise ASTValidationError(
                    "Structure: 'lockout' requires at least 1 failed attempt before locking the account.")
            if lockout["window_seconds"] < 1:
                raise ASTValidationError(
                    "Structure: the 'lockout' window must be a positive number of seconds.")
        for option, libelle in (("password_reset", "password_reset"),
                                ("refresh_tokens", "refresh_tokens")):
            if option in features and features[option] < 1:
                raise ASTValidationError(
                    f"Structure: '{libelle}' must be a positive duration in seconds.")
        if "password_reset" in features and (
                not self.auth_identifier or "email" not in self.auth_identifier):
            raise ASTValidationError(
                "Structure: 'password_reset' requires 'capability auth' with "
                "'identifier: email': the recovery message needs an account "
                "address; a business field cannot be guessed.")
        self._valider_verification_email(features)
        self.auth_features = features

        # BRIQUE 2a : une devise déclarée sans rien à encaisser ne produit
        # RIEN. C'est le point 85 mot pour mot — refuser une règle sans effet
        # plutôt que l'ignorer en silence, sinon l'auteur croit avoir configuré
        # son application.
        #
        # LE RECOUPEMENT VIT ICI, ET C'EST UNE QUESTION D'ORDRE, PAS DE GOÛT.
        # Écrit d'abord dans `_valider_securite_calculs_paiement` — l'endroit
        # « logique », auprès des autres refus de paiement — il ne se
        # déclenchait JAMAIS : le pipeline y passe à l'étape 261, et
        # `_valider_capacites` ne pose `payment_currency` qu'à l'étape 344. La
        # garde lisait donc toujours `None`. Elle est ici parce que c'est le
        # premier moment où les DEUX informations existent : `payable_fields`
        # est posé dès l'étape 228. Même famille que le point 92 — une garde
        # qui lit une variable pas encore assignée est une garde qui ment, et
        # seul un test qui EXIGE le refus le révèle.
        if not self.payable_fields:
            declare = []
            if self.payment_currency:
                declare.append(f"currency '{self.payment_currency['code']}'")
            if self.payment_provider:
                declare.append(f"provider '{self.payment_provider}'")
            if declare:
                raise ASTValidationError(
                    f"Structure: 'capability payment' declares "
                    f"{' and '.join(declare)}, but no 'payable' rule "
                    f"specifies what to charge—this configuration would "
                    f"have no effect. Add "
                    f"'rule Entite.field payable', or remove these lines.")

        # BRIQUE 2b, SUITE : le prestataire et la devise sont déclarés
        # séparément, donc rien n'empêchait de les déclarer INCOMPATIBLES.
        # La devise EFFECTIVE est comparée, pas seulement la déclarée : sans
        # ligne `currency`, le défaut est l'euro (DEVISE_PAR_DEFAUT), et
        # `provider: fedapay` tout seul partait donc encaisser en euros chez
        # un prestataire qui n'en accepte pas. Le refus NOMME la devise
        # attendue — un message qui dirait seulement « incompatible »
        # laisserait chercher.
        prestataire = self.payment_provider or PRESTATAIRE_PAR_DEFAUT
        acceptees = DEVISES_PAR_PRESTATAIRE.get(prestataire)
        effective = (self.payment_currency or {}).get("code") or DEVISE_PAR_DEFAUT
        if acceptees is not None and effective not in acceptees:
            attendue = ", ".join(sorted(acceptees))
            constat = (f"the declared currency is '{effective}'"
                       if self.payment_currency else
                       f"no 'currency' line is declared, so the default "
                       f"applies: '{effective}'")
            raise ASTValidationError(
                f"Structure: provider '{prestataire}' only accepts "
                f"{attendue}, but {constat}. This configuration would compile "
                f"without ever being able to accept a payment; it is rejected "
                f"now rather than at the first real payment. Add 'currency: "
                f"{attendue.split(', ')[0]}' to the 'capability payment' block.")

    def _valider_verification_email(self, features):
        """Deux réglages ensemble, un destinataire exclusivement e-mail."""
        if ("verify_email" in features) != ("verify_resend" in features):
            raise ASTValidationError("Structure: verify_email and verify_resend must be declared together.")
        if "verify_email" not in features:
            return
        if self.auth_identifier != ["email"]:
            raise ASTValidationError("Structure: verify_email requires identifier: email exclusively.")
        if features["verify_email"] < 1:
            raise ASTValidationError("Structure: verify_email requires a positive duration in seconds.")
        resend = features["verify_resend"]
        if resend["max_attempts"] < 1 or resend["window_seconds"] < 1:
            raise ASTValidationError("Structure: verify_resend requires a positive maximum and window.")

    def _valider_prestataire(self, nom):
        """Résout le prestataire d'encaissement — ou refuse en l'expliquant."""
        nom = str(nom).lower()
        if nom in PRESTATAIRES:
            return nom
        if nom in PRESTATAIRES_ECARTES:
            raise ASTValidationError(
                f"Structure: provider '{nom}' is not implemented by "
                f"monl, and this is intentional: {PRESTATAIRES_ECARTES[nom]}. "
                f"Available providers: {', '.join(sorted(PRESTATAIRES))}.")
        raise ASTValidationError(
            f"Structure: unknown payment provider: '{nom}'. "
            f"Available providers: {', '.join(sorted(PRESTATAIRES))}.")

    def _valider_devise(self, code):
        """Résout un code ISO en {code, exponent} — ou refuse en l'expliquant.

        L'exposant est calculé ICI et une seule fois : le générateur le LIT, il
        ne le redérive pas. Deux tables finiraient par diverger, et une
        divergence d'unité se paie sur le relevé bancaire (voir DEVISES).
        """
        code = str(code).upper()
        if code in DEVISES:
            return {"code": code, "exponent": DEVISES[code]}
        # Trois décimales : refusées NOMMÉMENT, pour que le message n'envoie
        # pas chercher une faute de frappe dans un code parfaitement valide.
        if code in {"BHD", "IQD", "JOD", "KWD", "LYD", "OMR", "TND"}:
            raise ASTValidationError(
                f"Structure: currency '{code}' has three decimal places, and "
                f"payment providers require special rounding that monl does "
                f"not yet support. It is rejected rather than charged with "
                f"an approximation.")
        raise ASTValidationError(
            f"Structure: currency '{code}' is unknown to monl. Its precision "
            f"is not guessed as two decimal places: charging a currency with "
            f"no subunit like the euro would multiply every amount by one "
            f"hundred. Recognized currencies: {', '.join(sorted(DEVISES))}.")
