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
                        f"Structure : 'phone_prefix' doit être un indicatif "
                        f"international — un '+' suivi de 1 à 4 chiffres "
                        f"(trouvé : {valeur!r}).")
                prefixe = valeur
            if "identifier" not in capacite:
                continue
            if capacite["name"] != "auth":
                raise ASTValidationError(
                    f"Structure : 'identifier' n'a de sens que sur "
                    f"'capability auth' (trouvé sur '{capacite['name']}') — "
                    "c'est l'inscription qu'il contraint.")
            demandees = list(dict.fromkeys(capacite["identifier"]))
            inconnues = [f for f in demandees if f not in self.FORMES_IDENTIFIANT]
            if inconnues:
                raise ASTValidationError(
                    f"Structure : forme(s) d'identifiant inconnue(s) : "
                    f"{', '.join(inconnues)}. Formes reconnues : "
                    f"{', '.join(self.FORMES_IDENTIFIANT)}.")
            # 'libre' accepte tout : le cumuler avec une forme stricte annule
            # cette dernière sans le dire. Un refus vaut mieux qu'une règle
            # écrite qui ne produit rien — c'est tout le point 85.
            if "libre" in demandees and len(demandees) > 1:
                raise ASTValidationError(
                    "Structure : 'identifier: libre' accepte déjà n'importe "
                    "quelle chaîne — le combiner avec "
                    f"{', '.join(f for f in demandees if f != 'libre')} "
                    "n'ajouterait aucune contrainte et laisserait croire le "
                    "contraire.")
            if formes is not None:
                raise ASTValidationError(
                    "Structure : 'identifier' déclaré deux fois sur "
                    "'capability auth' — une seule liste, sinon laquelle "
                    "s'applique ?")
            formes = demandees
        # Un indicatif sans forme 'phone' ne produirait RIEN : c'est ce que le
        # point 85 refuse. Le dire vaut mieux que le laisser croire appliqué.
        if prefixe and not (formes and "phone" in formes):
            raise ASTValidationError(
                "Structure : 'phone_prefix' n'a de sens qu'avec "
                "'identifier: … phone' — sans numéro à mettre sous forme "
                "canonique, il ne s'appliquerait à rien.")
        self.auth_phone_prefix = prefixe
        return formes

    def _valider_capacites(self):
        """Valide les capacités déclarées et prépare l'authentification B4."""
        known_capabilities = {"auth", "payment"}
        names = [capability["name"] for capability in self.capabilities_raw]
        unknown = [name for name in names if name not in known_capabilities]
        if unknown:
            raise ASTValidationError(
                f"Structure : capacité(s) inconnue(s) déclarée(s) avec 'capability' : {', '.join(unknown)}. "
                f"Capacités reconnues : {', '.join(sorted(known_capabilities))}."
            )
        self.capabilities = list(dict.fromkeys(names))
        self.auth_identifier = self._valider_identifiant_de_compte(self.capabilities_raw)

        allowed_auth_options = {
            "name", "identifier", "phone_prefix", "lockout", "password_reset",
            "refresh_tokens", "totp",
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
                    f"'{opt}' appartient à 'capability {accueil[opt]}'"
                    for opt in hors_sujet if opt in accueil)
                inconnues = sorted(opt for opt in hors_sujet if opt not in accueil)
                detail = " ; ".join(remedes + [f"'{o}' est inconnue" for o in inconnues])
                raise ASTValidationError(
                    f"Structure : option(s) déplacée(s) ou inconnue(s) sur "
                    f"'capability {nom}' — {detail}.")
            if nom == "payment" and "provider" in capability:
                if self.payment_provider is not None:
                    raise ASTValidationError(
                        "Structure : le prestataire de paiement est déclaré "
                        "deux fois — une application encaisse par UNE seule "
                        "voie, sinon le webhook ne sait plus quelle signature "
                        "vérifier.")
                self.payment_provider = self._valider_prestataire(
                    capability["provider"])
            if nom == "payment" and "currency" in capability:
                if self.payment_currency is not None:
                    raise ASTValidationError(
                        "Structure : la devise est déclarée deux fois — une "
                        "application encaisse dans UNE seule devise, sinon "
                        "'montant' ne veut plus rien dire d'une commande à "
                        "l'autre.")
                self.payment_currency = self._valider_devise(capability["currency"])
            if nom != "auth":
                continue
            for option in ("lockout", "password_reset", "refresh_tokens", "totp"):
                if option not in capability:
                    continue
                if option in features:
                    raise ASTValidationError(
                        f"Structure : l'option '{option}' est déclarée deux fois "
                        "sur 'capability auth'.")
                features[option] = capability[option]

        lockout = features.get("lockout")
        if lockout:
            if lockout["max_attempts"] < 1:
                raise ASTValidationError(
                    "Structure : 'lockout' exige au moins 1 échec avant verrouillage.")
            if lockout["window_seconds"] < 1:
                raise ASTValidationError(
                    "Structure : la fenêtre de 'lockout' doit être exprimée en secondes positives.")
        for option, libelle in (("password_reset", "password_reset"),
                                ("refresh_tokens", "refresh_tokens")):
            if option in features and features[option] < 1:
                raise ASTValidationError(
                    f"Structure : '{libelle}' doit être une durée positive en secondes.")
        if "password_reset" in features and (
                not self.auth_identifier or "email" not in self.auth_identifier):
            raise ASTValidationError(
                "Structure : 'password_reset' exige 'capability auth' avec "
                "'identifier: email' : le message de récupération doit avoir "
                "une adresse de compte, sans deviner un champ métier.")
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
                declare.append(f"la devise '{self.payment_currency['code']}'")
            if self.payment_provider:
                declare.append(f"le prestataire '{self.payment_provider}'")
            if declare:
                raise ASTValidationError(
                    f"Structure : 'capability payment' déclare "
                    f"{' et '.join(declare)}, mais aucune règle 'payable' ne "
                    f"dit quoi encaisser — cette configuration ne "
                    f"s'appliquerait à rien. Ajouter "
                    f"'rule Entite.champ payable', ou retirer ces lignes.")

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
            constat = (f"la devise déclarée est '{effective}'"
                       if self.payment_currency else
                       f"aucune ligne 'currency' n'est déclarée, donc le "
                       f"défaut s'applique : '{effective}'")
            raise ASTValidationError(
                f"Structure : le prestataire '{prestataire}' n'encaisse qu'en "
                f"{attendue}, or {constat}. Cette "
                f"configuration compilerait sans jamais pouvoir encaisser : "
                f"le refus arrive maintenant plutôt qu'au premier vrai "
                f"paiement. Ajouter 'currency: {attendue.split(', ')[0]}' au "
                f"bloc 'capability payment'.")

    def _valider_prestataire(self, nom):
        """Résout le prestataire d'encaissement — ou refuse en l'expliquant."""
        nom = str(nom).lower()
        if nom in PRESTATAIRES:
            return nom
        if nom in PRESTATAIRES_ECARTES:
            raise ASTValidationError(
                f"Structure : le prestataire '{nom}' n'est pas implémenté par "
                f"monl, et ce n'est pas un oubli : {PRESTATAIRES_ECARTES[nom]}. "
                f"Prestataires disponibles : {', '.join(sorted(PRESTATAIRES))}.")
        raise ASTValidationError(
            f"Structure : prestataire de paiement inconnu : '{nom}'. "
            f"Disponibles : {', '.join(sorted(PRESTATAIRES))}.")

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
                f"Structure : la devise '{code}' a trois décimales, et les "
                f"prestataires de paiement y imposent un arrondi particulier "
                f"que monl ne sait pas encore appliquer. Elle est refusée "
                f"plutôt qu'encaissée à peu près.")
        raise ASTValidationError(
            f"Structure : devise '{code}' inconnue de monl. Elle n'est pas "
            f"devinée à deux décimales : une devise sans sous-unité facturée "
            f"comme l'euro multiplierait chaque montant par cent. Devises "
            f"reconnues : {', '.join(sorted(DEVISES))}.")
