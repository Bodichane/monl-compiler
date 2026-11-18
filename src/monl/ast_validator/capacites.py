"""The `capability` blocks, and the form of the account identifier.

POINT 95: `capability auth` constrains the FORM of the identifier. The
substance is not validation, it is NORMALIZATION — without a canonical
form, uniqueness can be bypassed by changing a capital letter."""

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
    """The `capability` blocks, and the form of the account identifier."""

    # POINT 95: recognized forms for the account identifier. 'libre' is the
    # historical behavior (any string) and stays the default: a spec that says
    # nothing compiles exactly as before.
    FORMES_IDENTIFIANT = ("email", "phone", "libre")

    @staticmethod
    def _indicatif_valide(brut):
        """The cleaned `phone_prefix` calling code, or a refusal. Extracted from
        `_valider_identifiant_de_compte` (complexity ceiling)."""
        valeur = brut.strip()
        # A calling code is a '+' followed by 1 to 4 digits: no pattern to
        # import for so little, and one dependency fewer.
        if not (valeur.startswith("+") and valeur[1:].isdigit()
                and 1 <= len(valeur) - 1 <= 4):
            raise ASTValidationError(
                f"Structure: 'phone_prefix' must be an international "
                f"calling code—a '+' followed by 1 to 4 digits "
                f"(found: {valeur!r}).")
        return valeur

    def _formes_demandees(self, brutes):
        """The identifier forms of a list, deduplicated in order, or a refusal.
        Extracted from `_valider_identifiant_de_compte` (ceiling)."""
        demandees = list(dict.fromkeys(brutes))
        inconnues = [f for f in demandees if f not in self.FORMES_IDENTIFIANT]
        if inconnues:
            raise ASTValidationError(
                f"Structure: unknown identifier form(s): "
                f"{', '.join(inconnues)}. Recognized forms: "
                f"{', '.join(self.FORMES_IDENTIFIANT)}.")
        # 'libre' accepts everything: combining it with a strict form cancels
        # the latter without saying so. A refusal is better than a written rule
        # that produces nothing — that is all of point 85.
        if "libre" in demandees and len(demandees) > 1:
            raise ASTValidationError(
                "Structure: 'identifier: libre' already accepts any "
                "string—combining it with "
                f"{', '.join(f for f in demandees if f != 'libre')} "
                "would add no constraint and imply otherwise.")
        return demandees

    def _valider_identifiant_de_compte(self, capacites):
        """Forms accepted by '/register', declared on 'capability auth'.

        Returns None when nothing is declared — and that None matters: it means
        "no constraint", not "email by default". Guessing here would lock every
        existing project on its first recompilation."""
        formes, prefixe = None, None
        for capacite in capacites:
            if "phone_prefix" in capacite:
                prefixe = self._indicatif_valide(capacite["phone_prefix"])
            if "identifier" not in capacite:
                continue
            if capacite["name"] != "auth":
                raise ASTValidationError(
                    f"Structure: 'identifier' only makes sense on "
                    f"'capability auth' (found on '{capacite['name']}')— "
                    "it constrains registration.")
            demandees = self._formes_demandees(capacite["identifier"])
            if formes is not None:
                raise ASTValidationError(
                    "Structure: 'identifier' declared twice on "
                    "'capability auth'—there must be one list; otherwise, "
                    "which one applies?")
            formes = demandees
        # A calling code without a 'phone' form would produce NOTHING: that is
        # what point 85 refuses. Saying so is better than letting people
        # believe it applies.
        if prefixe and not (formes and "phone" in formes):
            raise ASTValidationError(
                "Structure: 'phone_prefix' only makes sense with "
                "'identifier: … phone'—without a number to canonicalize, "
                "it would have no effect.")
        self.auth_phone_prefix = prefixe
        return formes

    def _valider_capacites(self):
        """Validates the declared capabilities and prepares B4 authentication."""
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

        features = self._lire_les_options()

        self._valider_options_auth(features)
        self.auth_features = features

        self._refuser_paiement_sans_payable()
        self._exiger_devise_du_prestataire()

    def _lire_les_options(self):
        """Ties each option to its capability; returns the auth features."""
        allowed_auth_options = {
            "name", "identifier", "phone_prefix", "lockout", "password_reset",
            "refresh_tokens", "totp", "verify_email", "verify_resend",
        }
        # BRICK 2a: 'currency' is the first option that does NOT belong to
        # 'capability auth'. The grammar shares a single set of properties
        # across all capabilities — so it is here, and nowhere else, that each
        # option is tied to its capability.
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
                self._refuser_options_hors_sujet(nom, hors_sujet, options_par_capacite)
            self._lire_option_paiement(nom, capability)
            if nom != "auth":
                continue
            self._lire_options_auth(capability, features)
        return features

    def _refuser_options_hors_sujet(self, nom, hors_sujet, options_par_capacite):
        """Names the capability that ACCEPTS a misplaced option."""
        # Name the capability that ACCEPTS the option, when it exists:
        # "currency makes no sense here" would send people looking for
        # a typo when the line is simply in the wrong place.
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

    def _lire_option_paiement(self, nom, capability):
        """One provider and one currency at most, each validated."""
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

    def _lire_options_auth(self, capability, features):
        """Collects the B4 options, each declared once."""
        for option in ("lockout", "password_reset", "refresh_tokens", "totp",
                       "verify_email", "verify_resend"):
            if option not in capability:
                continue
            if option in features:
                raise ASTValidationError(
                    f"Structure: option '{option}' is declared twice "
                    "on 'capability auth'.")
            features[option] = capability[option]

    def _valider_options_auth(self, features):
        """Positive durations, and an email address for password reset."""
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

    def _refuser_paiement_sans_payable(self):
        """A payment configuration with nothing to charge has no effect."""
        # BRICK 2a: a currency declared with nothing to charge produces
        # NOTHING. It is point 85 word for word — refuse a rule with no effect
        # rather than silently ignore it, otherwise the author believes they
        # configured their application.
        #
        # THE CROSS-CHECK LIVES HERE, AND IT IS A MATTER OF ORDER, NOT OF
        # TASTE. Written first in `_valider_securite_calculs_paiement` — the
        # "logical" place, next to the other payment refusals — it NEVER fired:
        # the pipeline reaches it at step 261, and `_valider_capacites` sets
        # `payment_currency` only at step 344. The guard therefore always read
        # `None`. It is here because this is the first moment where BOTH pieces
        # of information exist: `payable_fields` is set as early as step 228.
        # Same family as point 92 — a guard that reads a variable not yet
        # assigned is a guard that lies, and only a test that REQUIRES the
        # refusal reveals it.
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

    def _exiger_devise_du_prestataire(self):
        """The EFFECTIVE currency must be one the provider accepts."""
        # BRICK 2b, CONTINUED: the provider and the currency are declared
        # separately, so nothing prevented declaring them INCOMPATIBLE. The
        # EFFECTIVE currency is compared, not just the declared one: without a
        # `currency` line, the default is the euro (DEVISE_PAR_DEFAUT), and
        # `provider: fedapay` alone therefore set off to charge in euros at a
        # provider that accepts none. The refusal NAMES the expected currency —
        # a message that only said "incompatible" would leave people searching.
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
        """Two settings together, an email-only recipient."""
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
        """Resolves the payment provider — or refuses and explains why."""
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
        """Resolves an ISO code into {code, exponent} — or refuses and explains why.

        The exponent is computed HERE and only once: the generator READS it, it
        does not derive it again. Two tables would eventually diverge, and a unit
        divergence is paid for on the bank statement (see DEVISES)."""
        code = str(code).upper()
        if code in DEVISES:
            return {"code": code, "exponent": DEVISES[code]}
        # Three decimals: refused BY NAME, so that the message does not send
        # people looking for a typo in a perfectly valid code.
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
