"""Le chemin guidé : le catalogue de modèles, et le mode express."""

from .fondations import DESIGN_IMAGERY, DESIGN_REGISTERS, FIELD_TYPES


class ParcoursMixin:
    """Le chemin guidé : le catalogue de modèles, et le mode express."""

    # ---------- déroulé du dialogue ----------
    def run(self):
        """Mène la conversation complète et retourne le texte de la spec .ml.
        REFONTE (point 45) : le dialogue ouvre sur le catalogue des 10 types
        d'applications les plus construits par les devs web — choisir un
        modèle pré-remplit tout et ne pose que les questions de suivi
        propres au modèle. « Partir de zéro » conserve le dialogue libre."""
        from ..app_templates import FREE_MODE_LABEL, TEMPLATES
        self._show(self.ui.banner())
        # AJOUT (bêta 3) : le libellé et son explication sont désormais deux
        # colonnes distinctes du menu, au lieu d'une seule chaîne « nom — aide »
        # qui débordait sur les terminaux étroits. La valeur de retour reste la
        # chaîne complète : le reste du moteur est inchangé.
        labels = [f"{t['name']} — {t['hint']}" for t in TEMPLATES] + [FREE_MODE_LABEL]
        courts = {label: TEMPLATES[i]["name"] for i, label in enumerate(labels[:-1])}
        courts[FREE_MODE_LABEL] = FREE_MODE_LABEL.split(" (")[0]
        aides = {t["name"]: f'{t["hint"]} — {self._ligne_de_compte(t)}'
                 for t in TEMPLATES}
        aides[courts[FREE_MODE_LABEL]] = "décrire librement mes entités, sans modèle"

        self._show(self.ui.plan(["Type d'application", "Identité du projet",
                                 "Options du modèle", "Finitions"]))
        self._show(self.ui.phase(0))
        choisi_court = self._ask_choice("Quel type d'application construisez-vous ?",
                                        [courts[label] for label in labels], hints=aides)
        picked = labels[[courts[label] for label in labels].index(choisi_court)]
        if picked == FREE_MODE_LABEL:
            return self._run_free()
        template = TEMPLATES[labels.index(picked)]
        if self.choose_experience:
            experience = self._ask_choice(
                "Quelle expérience souhaitez-vous ?",
                ["Création rapide avec l’IA", "Personnalisation détaillée"],
                hints={
                    "Création rapide avec l’IA":
                        "recommandé — Monl prépare structure, contenu et direction visuelle",
                    "Personnalisation détaillée":
                        "toutes les questions de structure, contenu et présentation",
                })
            self.express = experience.startswith("Création rapide")
        return self._run_from_template(template)

    @staticmethod
    def _express_intent(template):
        """Direction sûre et suffisamment précise pour le mode express.

        Elle ne change jamais le contrat fonctionnel : elle autorise seulement
        l'IA frontend à faire son métier éditorial et visuel à partir du modèle.
        """
        name = template["name"]
        if name in {"Portfolio / site vitrine", "Blog"}:
            register, imagery = DESIGN_REGISTERS[1][1], DESIGN_IMAGERY[0][1]
        elif name in {"Gestion de tâches", "Inventaire / gestion de stock",
                      "Suivi de dépenses personnelles"}:
            register, imagery = DESIGN_REGISTERS[2][1], DESIGN_IMAGERY[1][1]
        elif name in {"Boutique en ligne", "Classement communautaire"}:
            register, imagery = DESIGN_REGISTERS[3][1], DESIGN_IMAGERY[0][1]
        else:
            register, imagery = DESIGN_REGISTERS[1][1], DESIGN_IMAGERY[0][1]
        return (
            "utiliser immédiatement le parcours principal attendu pour cette "
            f"catégorie ; {register} ; {imagery} ; mode express : l’IA frontend "
            "rédige les textes de présentation manquants, crée une page dense en "
            "blocs utiles et produit des illustrations SVG locales cohérentes, "
            "sans inventer de donnée, de route ni de fonctionnalité"
        )

    @staticmethod
    def _ligne_de_compte(template):
        """Les visiteurs auront-ils un compte ? DÉRIVÉ, jamais écrit à la main.

        La question « site web ou application ? » n'existe pas dans le
        dialogue, et c'est volontaire : tout ce que monl produit a un serveur
        et une base. Ce qui varie, c'est si quelqu'un s'inscrit — et on ne
        choisit pas dans une liste sans savoir ce qu'elle implique.

        La réponse vient de `_default_self_register`, celle-là même que le
        dialogue emploie comme défaut : la ligne affichée ne peut donc pas
        diverger de ce qui sera réellement construit. Écrire une table à la
        main la ferait cesser de border au premier modèle ajouté — point 146.

        Le sens de cette fonction est ÉTROIT et la phrase le respecte : elle
        dit quel rôle serait offert à l'inscription libre, PAS si le site est
        lisible sans compte. « Inventaire » n'a pas de rôle public et n'est
        pourtant pas une vitrine.
        """
        managers = {n: [m["manager"]] for n, m in template["entities"].items()}
        owned = {n: m["manager"] for n, m in template["entities"].items()
                 if m["owned"]}
        role = ParcoursMixin._default_self_register(
            template["actors"], managers, owned)
        return (f"inscription libre : {role}" if role
                else "comptes créés par l'administrateur")

    @staticmethod
    def _default_self_register(actors, managers, owned):
        """Choix prudent du rôle public, pendant déterministe de la question."""
        privilegies = {
            actor
            for entity, entity_managers in managers.items()
            for actor in entity_managers
            if owned.get(entity) != actor and entity != actor
        }
        return next((actor for actor in actors if actor not in privilegies), None)

    @staticmethod
    def _express_image_topic(template):
        """Mot-clé public par catégorie, sans divulguer le brief libre.

        Les URL sont chargées chez un tiers par le navigateur. Y injecter la
        description transmettrait potentiellement un client, un lieu ou une
        idée encore confidentielle.
        """
        return {
            "Portfolio / site vitrine": "creative-studio",
            "Blog": "editorial",
            "Boutique en ligne": "products",
            "Gestion de tâches": "workspace",
            "Forum / réseau social": "community",
            "Petites annonces": "marketplace",
            "Réservation de rendez-vous": "wellness-service",
            "Inventaire / gestion de stock": "warehouse",
            "Suivi de dépenses personnelles": "finance-desk",
            "Classement communautaire": "competition",
        }.get(template["name"], "abstract")

    def _run_from_template(self, template):
        """Chemin « modèle » : questions de suivi spécifiques, puis les
        finitions communes. Le modèle est copié en profondeur — le catalogue
        n'est jamais muté entre deux exécutions (déterminisme)."""
        import copy

        from ..app_templates import apply_effects
        template = copy.deepcopy(template)

        self._show(self.ui.phase(1))
        app_name = self._ask_identifier("Nom de l'application (ex. StudioNova) > ")
        description = self._ask_free_text(
            "Décrivez le projet en une phrase (servira de brief frontend) > ")

        if self.express:
            entities = {name: list(meta["fields"])
                        for name, meta in template["entities"].items()}
            actors = list(template["actors"])
            managers = {name: [meta["manager"]]
                        for name, meta in template["entities"].items()}
            readers = {name: set(meta["readers"])
                       for name, meta in template["entities"].items()}
            public_read = [name for name, meta in template["entities"].items()
                           if meta["public_read"]]
            public_create = [name for name, meta in template["entities"].items()
                             if meta["public_create"]]
            owned = {name: meta["manager"]
                     for name, meta in template["entities"].items() if meta["owned"]}
            relations = list(template["relations"])
            self._ensure_ownership_structure(
                entities, managers, readers, owned, relations)
            self_register = self._default_self_register(actors, managers, owned)
            self._recap(app_name, entities, actors, self_register, public_read, owned)
            spec = self._emit_spec(
                app_name, description, entities, relations, actors, managers,
                readers, public_read, public_create, owned,
                want_seed=bool(template["seeds"]), want_landing=True,
                design_intent=self._express_intent(template), sections=(),
                links=self.express_links,
                image_topic=self._express_image_topic(template),
                self_register=self_register,
                extra_rules=template["extra_rules"], custom_seeds=template["seeds"])
            from ..ast_validator import MonlAST
            from ..parser import parse_monl_string
            MonlAST(parse_monl_string(spec)).validate_and_audit()
            return spec

        self._show(self.ui.phase(2))
        for followup in template["followups"]:
            if self._ask_yes_no(followup["ask"]):
                apply_effects(template, followup["effects"])

        # Conversion du modèle vers le format de l'émetteur
        entities = {name: list(meta["fields"]) for name, meta in template["entities"].items()}
        actors = list(template["actors"])
        managers = {name: [meta["manager"]] for name, meta in template["entities"].items()}
        readers = {name: set(meta["readers"]) for name, meta in template["entities"].items()}
        public_read = [n for n, m in template["entities"].items() if m["public_read"]]
        public_create = [n for n, m in template["entities"].items() if m["public_create"]]
        owned = {n: m["manager"] for n, m in template["entities"].items() if m["owned"]}
        relations = list(template["relations"])

        # Échappatoire : une entité personnalisée en plus du modèle.
        while self._ask_yes_no("Ajouter une entité personnalisée en plus du modèle ?"):
            name = self._ask_identifier("  Nom de l'entité > ", forbidden=entities.keys())
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
            managers[name] = [actors[0] if len(actors) == 1
                              else self._ask_choice(f"  Qui gère {name} en écriture ?", actors)]
            readers[name] = set()
            if self._ask_yes_no(f"  {name} doit-elle être lisible sans compte ?"):
                public_read.append(name)

        self._ensure_ownership_structure(entities, managers, readers, owned, relations)

        self._show(self.ui.phase(3))
        self_register = self._ask_self_register(actors, managers, owned)
        account_identifier = self._ask_account_identifier(self_register)
        upload_rules = self._ask_uploads(entities, public_read, owned)
        payable = (self._ask_payable(entities, owned, relations, managers, readers)
                   if template.get("accept_payments", True) else None)
        want_seed = bool(template["seeds"]) and self._ask_yes_no(
            "Pré-remplir le site avec les données de démonstration du modèle ?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Transmettre votre description à l'IA frontend comme brief de page d'accueil ?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = (self._ask_editorial_sections(template.get("sections", []))
                    if want_landing else [])
        links = self._ask_footer_links() if want_landing else []
        self._recap(app_name, entities, actors, self_register, public_read, owned,
                    payable=payable)

        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read, public_create,
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               links=links,
                               image_topic=image_topic,
                               self_register=self_register,
                               account_identifier=account_identifier,
                               extra_rules=template["extra_rules"] + upload_rules,
                               extra_workflows=template.get("extra_workflows", ()),
                               custom_seeds=template["seeds"],
                               payable=payable)
        from ..ast_validator import MonlAST
        from ..parser import parse_monl_string
        MonlAST(parse_monl_string(spec)).validate_and_audit()
        return spec
