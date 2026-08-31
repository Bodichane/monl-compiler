"""La chaîne marchande, posée en une question (point 86).

Le dialogue produit la chaîne ENTIÈRE — panier, propriété transitive,
`derivedFrom`, `sumOf`, `min`, décompte, `payable`. Toute modification de
l'ordre des questions après `_ask_self_register` doit faire vérifier
`tests/test_app_templates.py` : trois modèles posent la question `payable`,
et les réponses scriptées se décalent sinon."""

class CommerceMixin:
    """La chaîne marchande, posée en une question (point 86)."""

    CHAMP_QUANTITE = "quantite"

    # BRIQUE B1 : un seul menu porte les trois choix qu'un Upload exige. Il
    # n'existe pas de plafond ou de type implicite : l'usager choisit un profil
    # dont le libellé expose le champ, la limite exacte et les MIME autorisés.
    UPLOAD_PROFILES = (
        ("Photo", "photo", 5 * 1024 * 1024, ("image/png", "image/jpeg")),
        ("Document PDF", "document", 10 * 1024 * 1024, ("application/pdf",)),
    )

    # POINT 86 : le sous-total d'une ligne de panier. Nommé ici plutôt qu'en dur
    # dans l'émetteur — deux endroits finiraient par diverger.
    CHAMP_SOUS_TOTAL = "sousTotal"

    # POINT 89 : la date d'arrivée de ce qu'on encaisse. AUCUNE question ne la
    # propose, volontairement : elle est écrite par le serveur, ne peut donc pas
    # être fausse, et une commande sans date n'est pas une commande — la seule
    # réponse utile serait « oui ». Le dialogue émet déjà de même le total, le
    # plancher de stock et le décompte sans les faire arbitrer un par un.
    CHAMP_DATE = "creeLe"

    @classmethod
    def _upload_profiles_for(cls, fields):
        """Profils que cette entité peut recevoir sans collision de champ."""
        types = dict(fields)
        existants = [name for name, type_ in fields if type_ == "Upload"]
        if len(existants) > 1:
            return []
        result = []
        for label, default_field, maximum, accepted_types in cls.UPLOAD_PROFILES:
            field = existants[0] if existants else default_field
            if not existants and field in types:
                continue
            result.append((label, field, maximum, accepted_types))
        return result

    def _ask_uploads(self, entities, public_read, owned):
        """Déclare les dépôts qu'un dialogue peut produire de façon sûre.

        Un Upload doit avoir une route Read et Update privée, et une ACL par
        ligne. Le dialogue produit ces routes et l'ACL `ownedBy` pour une
        entité possédée non publique ; toutes les autres sont donc exclues
        avant de poser la question. Un profil choisi écrit le champ et la
        règle complète en un seul passage.
        """
        public = set(public_read)
        rules = []
        for entity, fields in entities.items():
            if entity not in owned or entity in public:
                continue
            profiles = self._upload_profiles_for(fields)
            if not profiles:
                continue
            labels = [
                f"{label} — champ {field}, {maximum} octets, "
                f"types {', '.join(accepted_types)}"
                for label, field, maximum, accepted_types in profiles
            ]
            # La question DIT ce qu'elle produit. Sans ça, on choisit « Photo »
            # pour une annonce en croyant que les acheteurs la verront — or la
            # règle écrite est `ownedBy`, et eux récoltent 403 (mesuré). monl
            # ne sait pas servir publiquement un fichier déposé, et le taire
            # ferait construire un catalogue sans images.
            choice = self._ask_choice(
                f"Quel dépôt de fichier pour {entity} ? "
                "(le fichier ne sera lisible que par son propriétaire)",
                labels, allow_none=True)
            if choice is None:
                continue
            profile = profiles[labels.index(choice)]
            _label, field, maximum, accepted_types = profile
            if not any(name == field for name, _type in fields):
                fields.append((field, "Upload"))
            mime_list = ", ".join(f'"{mime}"' for mime in accepted_types)
            rules.append(
                f"rule {entity}.{field} upload max {maximum} types {mime_list}")
        return rules

    def _ask_payable(self, entities, owned, relations, managers, readers):
        """Quel montant cette application encaisse-t-elle ? (points 75 et 79)

        La brique `payable` (point 74) était inaccessible depuis le seul
        chemin que la plupart des utilisateurs empruntent : il fallait écrire
        la spec à la main. Une capacité que le dialogue ne sait pas exprimer
        n'existe pas pour eux.

        **Ce que le point 79 a changé.** La question partait d'un champ `Money`
        sur une entité possédée. C'était trop peu : le créateur d'un
        enregistrement en devient le propriétaire, donc le payeur — et si le
        montant est un champ ordinaire, le payeur fixe lui-même ce qu'il règle.
        Le compilateur le refuse désormais. Le dialogue ne peut donc plus poser
        la question sur la seule présence d'un `Money` : il lui faut de quoi
        faire CALCULER le montant par le serveur.

        Concrètement il faut un catalogue : une AUTRE entité portant un prix,
        que l'entité encaissée peut référencer. Le dialogue construit alors la
        structure complète — une quantité, la relation vers le catalogue, et les
        deux règles — au lieu de laisser l'auteur assembler ça de tête.

        **Ce que cette exigence a révélé.** Sur les trois modèles du catalogue
        qui portaient un `Money` sur une entité possédée, deux n'avaient aucun
        catalogue à référencer — et pour une bonne raison : dans « Petites
        annonces » le vendeur crée son annonce, donc il en est le propriétaire,
        donc le payeur ; il se paierait lui-même. Dans « Suivi de dépenses », le
        registre est personnel. La question n'aurait jamais dû leur être posée.
        Un refus du compilateur a corrigé une question du dialogue.

        Renvoie None, ou un dictionnaire décrivant la dérivation. Mute
        `entities` et `relations` pour y ajouter ce que la brique exige.
        """
        candidats = []
        for ent in entities:
            if ent not in owned:
                continue
            montants = [c for c, t in entities[ent] if t == "Money"]
            if not montants:
                continue
            # Un catalogue : une autre entité portant un prix. C'est lui qui
            # permet au serveur de calculer, donc de ne pas croire le client.
            for source in entities:
                # Ni l'entité elle-même, ni son PROPRIÉTAIRE : la clé étrangère
                # du propriétaire vient du jeton, pas du client, donc aucune
                # ligne ne pourrait y être désignée. Le validateur le refuse ;
                # le dialogue ne doit pas proposer ce que le compilateur rejette.
                if source == ent or source == owned.get(ent) or source in owned:
                    continue
                prix = [c for c, t in entities[source]
                        if t in ("Money", "Float", "Integer")]
                if prix:
                    candidats.append((ent, montants[0], source, prix[0]))
        if not candidats:
            return None
        if not self._ask_yes_no(
                "Cette application encaisse-t-elle un paiement en ligne ?"):
            return None
        if len(candidats) == 1:
            choix = candidats[0]
        else:
            libelles = [f"{e}.{m} (calculé depuis {s}.{p})"
                        for e, m, s, p in candidats]
            choix = candidats[libelles.index(
                self._ask_choice("Quel montant encaisser ?", libelles))]
        entite, montant, source, prix = choix
        resultat = {"entity": entite, "field": montant,
                    "source_entity": source, "source_field": prix,
                    "factor": self.CHAMP_QUANTITE}
        # POINT 89 : l'horodatage, ajouté en QUEUE — la règle « premier champ
        # requis » de l'émetteur porterait sinon sur un champ que le client ne
        # peut pas envoyer, et la compilation échouerait (recoupement du
        # point 85).
        if not any(c == self.CHAMP_DATE for c, _t in entities[entite]):
            entities[entite].append((self.CHAMP_DATE, "DateTime"))

        # POINT 86 : le dialogue savait produire une commande à UN article — la
        # forme du point 77 — alors que le compilateur sait faire un panier
        # depuis le point 82. Une capacité que le dialogue n'exprime pas
        # n'existe pas pour qui n'écrit pas la spec à la main : c'est
        # exactement l'argument qui avait fait naître cette question au
        # point 75, resté valable quatre briques plus tard.
        panier = self._ask_yes_no(
            f"Un(e) {entite} peut-il contenir PLUSIEURS articles différents ?")
        if panier:
            ligne = self._nom_de_ligne(entite, entities)
            # La quantité EN PREMIER : la règle « premier champ requis » de
            # l'émetteur la rend obligatoire, ce dont le calcul a besoin.
            entities[ligne] = [(self.CHAMP_QUANTITE, "Integer"),
                               (self.CHAMP_SOUS_TOTAL, "Money")]
            for rel in ((entite, "hasMany", ligne), (source, "hasMany", ligne)):
                if rel not in relations:
                    relations.append(rel)
            managers[ligne] = list(managers.get(entite, []))
            readers[ligne] = set(readers.get(entite, set()))
            # Propriété TRANSITIVE (point 81) : la ligne appartient à qui possède
            # sa commande. L'émetteur écrit 'ownedBy <entite>' depuis ce
            # dictionnaire — aucune syntaxe particulière à inventer ici.
            owned[ligne] = entite
            resultat["line_entity"] = ligne
            self._show(self.ui.note(
                f"Panier : chaque {ligne} porte un article et sa quantité ; "
                f"{entite}.{montant} en est la SOMME, recalculée par le serveur "
                f"à chaque ligne ajoutée, modifiée ou supprimée."))
        else:
            # Forme mono-article : la quantité vit sur l'entité encaissée.
            if not any(c == self.CHAMP_QUANTITE for c, _t in entities[entite]):
                entities[entite].append((self.CHAMP_QUANTITE, "Integer"))
            if not any(r[0] == source and r[2] == entite for r in relations):
                relations.append((source, "hasMany", entite))

        # POINT 86 : le décompte de stock, rendu atteignable ici. Le champ n'est
        # pas DEVINÉ parmi les entiers du catalogue — le deviner mal ferait
        # décompter autre chose que ce qu'on croit, en silence.
        stocks = [c for c, t in entities[source] if t == "Integer" and c != prix]
        if stocks and self._ask_yes_no(
                f"Faut-il décompter un stock de {source} à chaque achat ?"):
            resultat["stock_field"] = (stocks[0] if len(stocks) == 1 else
                                       self._ask_choice("Quel champ porte le stock ?",
                                                        stocks))

        self._show(self.ui.note(
            f"Montant encaissé : {entite}.{montant} — CALCULÉ par le serveur, "
            "jamais envoyé par le navigateur. Sans ce calcul, l'acheteur "
            "fixerait lui-même son prix."))
        return resultat
