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
        aides = {a: ("recommandé — n'écrit que sur ses propres données"
                     if a in consommateurs else
                     "gère des données communes : à ouvrir en connaissance de cause")
                 for a in ordonnes}
        choisi = self._ask_choice(
            "Quel rôle peut créer son compte depuis le site ?",
            ordonnes, allow_none=True, hints=aides)
        if choisi is None:
            self._show(self.ui.note(
                "Aucune inscription en ligne : les comptes seront créés sur le "
                "serveur avec 'python3 manage.py adduser'."))
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
            "Avec quoi les comptes se connectent-ils ?",
            ["Numéro de téléphone", "Adresse e-mail", "Téléphone ou e-mail, au choix"],
            allow_none=True,
            hints={
                "Numéro de téléphone": "recommandé si vous rappelez vos clients",
                "Adresse e-mail": "si vos échanges se font par écrit",
                "Téléphone ou e-mail, au choix": "chacun s'inscrit comme il préfère",
            })
        if choix is None:
            self._show(self.ui.note(
                "Identifiant libre : n'importe quel texte fera un compte, et "
                "vous n'aurez aucun moyen de recontacter la personne."))
            return None
        formes = {"Numéro de téléphone": ["phone"],
                  "Adresse e-mail": ["email"],
                  "Téléphone ou e-mail, au choix": ["email", "phone"]}[choix]

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
                self.ui.field("Indicatif du pays pour les numéros "
                              "(ex. +229 pour le Bénin, vide pour aucun) > "),
                valide, "Un indicatif commence par + suivi de 1 à 4 chiffres.",
                kind="free_text")
            if prefixe is None:
                self._show(self.ui.note(
                    "Sans indicatif, '97…' et '+22997…' seront deux comptes "
                    "différents pour la même personne."))
        return {"formes": formes, "prefixe": prefixe}
