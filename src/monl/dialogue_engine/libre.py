"""Le chemin sans modèle : l'usager décrit ses entités."""

from .fondations import FIELD_TYPES, RELATION_TYPES


class LibreMixin:
    """Le chemin sans modèle : l'usager décrit ses entités."""

    def _run_free(self):
        """Le dialogue libre historique — inchangé, derrière « partir de zéro »."""
        self._show(self.ui.plan(["Identité du projet", "Données", "Accès public",
                                 "Acteurs", "Droits d'écriture", "Relations",
                                 "Finitions"]))
        self._show(self.ui.phase(0))
        app_name = self._ask_identifier("Nom de l'application (ex. StudioNova) > ")
        description = self._ask_free_text("Décrivez le projet en une phrase (servira à la page d'accueil) > ")

        # Entités et champs
        entities = {}   # name -> [(field, type)]
        self._show(self.ui.phase(1))
        self._show(self.ui.section(
            "Définissons les données (entités). Exemple : Project, Message, Article…"))
        while True:
            prompt = ("Nom de la 1ère entité > " if not entities
                      else "Nom d'une autre entité (vide pour terminer) > ")
            name = (self._ask_identifier(prompt, forbidden=entities.keys()) if not entities
                    else self._ask_optional_identifier(prompt, forbidden=entities.keys()))
            if name is None:
                break
            fields = []
            while True:
                taken = [f for f, _ in fields]
                fprompt = (f"  Premier champ de {name} > " if not fields
                           else f"  Autre champ de {name} (vide pour terminer) > ")
                fname = (self._ask_identifier(fprompt, forbidden=taken) if not fields
                         else self._ask_optional_identifier(fprompt, forbidden=taken))
                if fname is None:
                    break
                ftype = self._ask_choice(f"  Type de {name}.{fname} ?", FIELD_TYPES)
                fields.append((fname, ftype))
            entities[name] = fields

        entity_names = list(entities.keys())

        # Vitrine publique (lecture sans compte) et création publique (contact)
        self._show(self.ui.phase(2))
        public_read = []
        for ent in entity_names:
            if self._ask_yes_no(f"L'entité {ent} doit-elle être LISIBLE sans compte (vitrine publique) ?"):
                public_read.append(ent)
        public_create = self._ask_choice(
            "Une entité peut-elle être CRÉÉE sans compte (ex. formulaire de contact) ?",
            entity_names, allow_none=True)

        # Acteurs
        actors = []
        self._show(self.ui.phase(3))
        self._show(self.ui.section("Qui utilise l'application ? (ex. Admin, Visitor, Member…)"))
        while True:
            prompt = ("Nom du 1er acteur > " if not actors
                      else "Autre acteur (vide pour terminer) > ")
            a = (self._ask_identifier(prompt, forbidden=actors) if not actors
                 else self._ask_optional_identifier(prompt, forbidden=actors))
            if a is None:
                break
            actors.append(a)

        # Gestion en écriture : un acteur unique par défaut (aucune collision
        # possible, règle stricte n° 1 respectée PAR CONSTRUCTION), ou un
        # partage EXPLICITE entre plusieurs acteurs — auquel cas le dialogue
        # émet les règles 'sharedBy' correspondantes, exactement la voie
        # légitime prévue par le compilateur (point 1 du journal).
        managers = {}  # ent -> [acteurs] (1 seul, ou 2+ si partagé)
        for ent in entity_names:
            if len(actors) == 1:
                managers[ent] = [actors[0]]
                continue
            pick = self._ask_choice(
                f"Qui gère {ent} en écriture (création/modification/suppression) ?",
                actors + ["(plusieurs acteurs se partagent la gestion)"])
            if pick != "(plusieurs acteurs se partagent la gestion)":
                managers[ent] = [pick]
                continue
            shared = [a for a in actors
                      if self._ask_yes_no(f"  {a} participe-t-il à la gestion de {ent} ?")]
            if len(shared) < 2:
                self._say(self.ui.error("Un partage exige au moins deux acteurs — "
                                        "gestion attribuée au premier acteur."))
                shared = [shared[0] if shared else actors[0]]
            managers[ent] = shared

        # Propriété par enregistrement (ownedBy) : seul le créateur d'un
        # enregistrement peut le modifier/supprimer. Nécessite une entité
        # "propriétaire" homonyme de l'acteur + la relation qui fournit la
        # colonne de clé étrangère (motif canonique : exemples/03, point 5
        # du journal). Non proposé quand la gestion est partagée (v1).
        owned = {}  # ent -> entité propriétaire
        for ent in entity_names:
            if len(managers[ent]) != 1:
                continue
            actor = managers[ent][0]
            if not self._ask_yes_no(
                    f"Chaque enregistrement de {ent} doit-il appartenir à son "
                    f"créateur (lui seul pourra le modifier/supprimer) ?"):
                continue
            owned[ent] = actor
            if actor not in entities:
                entities[actor] = [("displayName", "String")]
                entity_names.append(actor)
                managers[actor] = [actor]
                self._show(self.ui.note(
                    f"Entité propriétaire '{actor}' créée automatiquement "
                    f"(displayName: String), reliée par '{actor} hasMany {ent}'."))

        # Lecteurs supplémentaires (les lectures ne créent pas de collision)
        readers = {ent: set() for ent in entity_names}
        for ent in entity_names:
            for act in actors:
                if act in managers[ent]:
                    continue
                if self._ask_yes_no(f"{act} peut-il LIRE {ent} (une fois connecté) ?"):
                    readers[ent].add(act)

        # Relations
        relations = []
        if len(entity_names) >= 2 and self._ask_yes_no("\nDes entités sont-elles liées entre elles ?"):
            while True:
                src = self._ask_choice("Entité source de la relation ?", entity_names + ["(terminer)"])
                if src == "(terminer)":
                    break
                rtype = self._ask_choice(
                    f"Type de lien depuis {src} ? (hasMany : {src} contient plusieurs cibles)",
                    RELATION_TYPES)
                targets = [e for e in entity_names if e != src]
                tgt = self._ask_choice("Entité cible ?", targets)
                relations.append((src, rtype, tgt))
                if not self._ask_yes_no("Ajouter une autre relation ?"):
                    break

        self._show(self.ui.phase(6))
        self_register = self._ask_self_register(actors, managers, owned)
        account_identifier = self._ask_account_identifier(self_register)
        upload_rules = self._ask_uploads(entities, public_read, owned)
        payable = self._ask_payable(entities, owned, relations, managers, readers)
        want_seed = self._ask_yes_no("Pré-remplir le site avec des données de démonstration ?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Transmettre votre description à l'IA frontend comme brief de page d'accueil ?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = self._ask_editorial_sections() if want_landing else []
        links = self._ask_footer_links() if want_landing else []

        # Entités propriétaires + relations de propriété (helper partagé
        # avec le chemin « modèle » ; dédupliqué si déjà déclaré à la main).
        readers = {e: readers.get(e, set()) for e in entities}
        managers = {e: managers.get(e, [actors[0]]) for e in entities}
        self._ensure_ownership_structure(entities, managers, readers, owned, relations)

        self._recap(app_name, entities, actors, self_register, public_read, owned,
                    payable=payable)
        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read,
                               [public_create] if public_create else [],
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               links=links,
                               image_topic=image_topic,
                               self_register=self_register,
                               account_identifier=account_identifier,
                               payable=payable,
                               extra_rules=upload_rules)

        # Garantie finale : la spec émise DOIT compiler. On la revalide par le
        # vrai pipeline — si ce n'est pas le cas, c'est un bug du moteur, pas
        # de l'utilisateur, et on échoue bruyamment plutôt que de rendre un
        # fichier cassé.
        from ..ast_validator import MonlAST
        from ..parser import parse_monl_string
        MonlAST(parse_monl_string(spec)).validate_and_audit()
        return spec

    @staticmethod
    def _ensure_ownership_structure(entities, managers, readers, owned, relations):
        """Toute règle ownedBy exige une entité propriétaire homonyme de
        l'acteur + la relation qui fournit la clé étrangère (point 5, motif
        de exemples/03). Créées ici si absentes — partagé entre le chemin
        « modèle » et le chemin libre."""
        for ent, owner in list(owned.items()):
            if owner not in entities:
                entities[owner] = [("displayName", "String")]
                managers[owner] = [owner]
                readers[owner] = set()
            if (owner, "hasMany", ent) not in relations:
                relations.append((owner, "hasMany", ent))

    @staticmethod
    def _nom_de_ligne(entite, entities):
        """Un nom d'entité libre pour la ligne de panier. Une collision
        silencieuse écraserait une entité de l'utilisateur."""
        base = f"Ligne{entite}"
        nom, n = base, 2
        while nom in entities:
            nom, n = f"{base}{n}", n + 1
        return nom
