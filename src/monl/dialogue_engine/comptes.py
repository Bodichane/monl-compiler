"""Qui s'inscrit, et sous quelle forme d'identifiant.

POINT 138 : la question de l'identifiant n'était posée par PERSONNE — tout
projet né du dialogue acceptait `'!!!'` comme identifiant de compte. Une
brique qui contraint une ENTRÉE doit être branchée au dialogue, sinon elle
ne protège que les specs écrites à la main."""

from .fondations import PHONE_PREFIX_RE


class ComptesMixin:
    """Qui s'inscrit, et sous quelle forme d'identifiant."""

    def _ask_self_register(self, actors, managers, owned):
        """Quel rôle peut créer son compte depuis le site ?

        Question de sécurité, donc posée — jamais devinée. L'ordre des
        options porte la recommandation : d'abord les rôles qui ne gèrent
        aucune donnée en écriture (un visiteur, un client), car ouvrir
        l'inscription à un rôle gestionnaire revient à laisser n'importe qui
        s'attribuer les droits d'écriture.
        """
        if not actors:
            return None
        # Un rôle est « privilégié » s'il écrit sur des données COMMUNES.
        # Écrire uniquement sur ses propres enregistrements (règle ownedBy)
        # ou sur sa propre fiche de profil (entité homonyme de l'acteur) ne
        # l'est pas : c'est précisément ce que fait un client ou un membre.
        # Sans cette distinction, un modèle où chaque rôle gère quelque
        # chose proposerait l'administrateur en tête — soit exactement la
        # faille d'élévation de privilège corrigée par ailleurs.
        privilegies = set()
        for entite, gestionnaires in managers.items():
            for acteur in gestionnaires:
                if owned.get(entite) == acteur or entite == acteur:
                    continue
                privilegies.add(acteur)
        consommateurs = [a for a in actors if a not in privilegies]
        ordonnes = consommateurs + [a for a in actors if a in privilegies]
        aides = {a: ("recommended — writes only to their own data"
                     if a in consommateurs else
                     "manages shared data: enable with care")
                 for a in ordonnes}
        choisi = self._ask_choice(
            "Which role can create an account on the site?",
            ordonnes, allow_none=True, hints=aides)
        if choisi is None:
            self._show(self.ui.note(
                "No online registration: accounts will be created on the "
                "server with 'python3 manage.py adduser'."))
        return choisi

    def _ask_account_identifier(self, self_register):
        """Avec quoi les comptes se connectent-ils ? (brique 1, point 95)

        La brique existe depuis le point 95 et le dialogue ne l'a jamais
        proposée : aucune spec issue d'un modèle ne déclarait d'identifiant, et
        `username` restait du texte libre. Constaté sur `projets/AtelierNaya`,
        atelier de beauté à Cotonou : `'!!!'` et même deux espaces créaient un
        compte, et l'atelier recevait des réservations qu'il ne pouvait
        honorer faute de pouvoir joindre qui que ce soit. Même famille que le
        point 90 — une commande sans destinataire est inexpédiable.

        La question n'est posée QUE si quelqu'un s'inscrit en ligne : sans
        inscription, les comptes naissent dans `manage.py`, d'où le contrôle
        de forme est volontairement absent (rôles de service sans adresse).

        L'ORDRE des options porte la recommandation, comme dans
        `_ask_self_register`. Le téléphone vient en tête : sur le marché visé,
        c'est le canal de rappel réel, bien avant le courriel.

        Ne rien choisir laisse la spec SANS bloc `capability auth` — pas un
        bloc vide. `None` n'est pas `[]` (point 95) : c'est ce qui garantit
        qu'une spec écrite avant cette question compile à l'identique.
        """
        if not self_register:
            return None
        choix = self._ask_choice(
            "How will users sign in?",
            ["Phone number", "Email address", "Phone or email, user's choice"],
            allow_none=True,
            hints={
                "Phone number": "recommended if you call your customers back",
                "Email address": "if you communicate in writing",
                "Phone or email, user's choice": "each person signs up as they prefer",
            })
        if choix is None:
            self._show(self.ui.note(
                "Unrestricted identifier: any text can be used for an account, "
                "and you will have no way to contact the person again."))
            return None
        formes = {"Phone number": ["phone"],
                  "Email address": ["email"],
                  "Phone or email, user's choice": ["email", "phone"]}[choix]

        prefixe = None
        if "phone" in formes:
            # POINT 95 : sans indicatif, « 97… » et « +22997… » sont DEUX
            # comptes pour une seule personne. monl fait DÉCLARER ce qu'il ne
            # peut pas deviner — il ne connaît pas le pays de l'application.
            def valide(a):
                if a == "":
                    return True, None
                if PHONE_PREFIX_RE.match(a):
                    return True, a
                return False, None
            prefixe = self._ask(
                self.ui.field("Country calling code for phone numbers "
                              "(e.g. +229 for Benin, leave blank for none) > "),
                valide, "A calling code starts with + followed by 1 to 4 digits.",
                kind="free_text")
            if prefixe is None:
                self._show(self.ui.note(
                    "Without a calling code, '97…' and '+22997…' will be "
                    "different accounts for the same person."))
        configuration = {"formes": formes, "prefixe": prefixe}
        if formes == ["email"]:
            configuration.update(self._ask_email_verification())
        return configuration

    def _ask_email_verification(self):
        """Le producteur de la brique : uniquement une inscription par e-mail."""
        if not self._ask_yes_no("Require email address confirmation before sign-in?"):
            return {}
        duree = self._ask_positive_seconds("Confirmation link validity, in seconds")
        maximum = self._ask_positive_seconds("Maximum resends in the window")
        fenetre = self._ask_positive_seconds("Resend window, in seconds")
        return {"verify_email": duree, "verify_resend": (maximum, fenetre)}

    def _ask_positive_seconds(self, titre):
        def valide(value):
            if value.isdecimal() and int(value) > 0:
                return True, int(value)
            return False, None
        return self._ask(self.ui.field(titre + " > "), valide,
                         "Enter a strictly positive integer.", kind="free_text")
