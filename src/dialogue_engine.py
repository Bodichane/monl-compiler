# ─────────────────────────────────────────────────────────────────────
# MOTEUR DE DIALOGUE GUIDÉ — pivot "monl orchestrateur" (brique 1).
#
# Objectif : remplacer l'écriture manuelle d'une spec .ml par une
# conversation guidée par RÈGLES (aucun modèle d'IA). Les questions sont
# fermées autant que possible, chaque réponse est validée, et la spec
# produite est TOUJOURS revalidée par le vrai parseur + l'audit AST avant
# d'être rendue — même garantie de déterminisme que le compilateur.
#
# Décision de conception : le moteur ne reçoit JAMAIS stdin directement.
# Il consomme une fonction ask(prompt) -> str, ce qui permet :
#   - en usage réel : ask = input (voir cli.py)
#   - en test : ask = itérateur de réponses scriptées (exécution réelle,
#     conformément à la méthode de travail du projet — pas de mock du
#     pipeline, la spec produite est réellement compilée dans les tests).
#
# Couvert depuis le point 41 : ownedBy (propriété par enregistrement, avec
# création automatique de l'entité propriétaire et de sa relation) et
# sharedBy (gestion partagée entre plusieurs acteurs). Hors de portée
# assumé : accessibleBy (accès à deux parties) et blocs custom
# (échappatoire IA) — briques suivantes.
# ─────────────────────────────────────────────────────────────────────
import re

IDENT_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")

# Types proposés dans le menu — sous-ensemble sûr des types de la grammaire
# (Date/UUID exclus du menu v1 : peu utiles sans widget de saisie dédié).
FIELD_TYPES = ["String", "Text", "Integer", "Float", "Money", "Boolean", "Email", "DateTime"]

# Types qu'on sait seeder de façon déterministe (la grammaire 'seed' n'accepte
# que STRING_LITERAL et SIGNED_NUMBER — pas de booléen ni de date).
SEEDABLE_TYPES = {"String", "Text", "Integer", "Float", "Money", "Email"}

RELATION_TYPES = ["hasMany", "hasOne", "belongsTo"]

# AJOUT (point 53) : intention visuelle. Le brief transmis à l'IA UI se
# résumait à la phrase de description — souvent trois mots — face à un contrat
# qui décrit les routes au champ près. L'IA recevait donc toute la structure et
# presque aucune intention, et rendait le dénominateur commun. Ces deux menus
# captent ce qu'aucune spec ne peut déduire : le registre voulu et la place des
# images. Menus FERMÉS (le dialogue reste déterministe et sans IA) ; chaque
# entrée porte un libellé court pour l'écran et une phrase pour le brief.
DESIGN_REGISTERS = [
    ("Sobre et institutionnel",
     "registre sobre et institutionnel : lisibilité et confiance avant tout, "
     "peu d'effets, hiérarchie typographique nette"),
    ("Chaleureux et éditorial",
     "registre chaleureux et éditorial : longues plages de texte, respiration "
     "généreuse, matière et nuances plutôt que contrastes brutaux"),
    ("Dense et fonctionnel",
     "registre dense et fonctionnel : l'outil prime sur la vitrine, "
     "information compacte, l'utilisateur va vite et revient souvent"),
    ("Affirmé et graphique",
     "registre affirmé et graphique : grandes échelles typographiques, "
     "contrastes marqués, parti pris visuel assumé"),
]

DESIGN_IMAGERY = [
    ("Les images portent le site",
     "les images portent le site (photo, œuvre, produit) : elles occupent de "
     "grandes surfaces et commandent la mise en page"),
    ("Texte d'abord, images d'appoint",
     "le texte porte le site, les images viennent en appui et restent "
     "secondaires dans la mise en page"),
    ("Aucune image",
     "aucune image : tout repose sur la typographie, l'espacement et la "
     "couleur"),
]


class DialogueError(Exception):
    """Réponse invalide répétée ou incohérence — le moteur ne devine jamais."""


class GuidedDialogue:
    def __init__(self, ask, say=None, max_retries=3, ui=None):
        """Dialogue guidé à règles, entièrement déterministe : aucune IA,
        aucun appel réseau. Chaque réponse est validée en saisie stricte
        (numéros, o/n, identifiants) et redemandée tant qu'elle est invalide.
        La spécification produite est ensuite revalidée par le vrai parseur
        avant d'être écrite."""
        self._ask_fn = ask
        self._say = say or (lambda *_: None)
        self.max_retries = max_retries
        # AJOUT (bêta 3) : couche de présentation. Par défaut, rendu nu —
        # chaînes strictement identiques à l'historique, donc les tests
        # scriptés et toute sortie redirigée sont insensibles à l'habillage.
        # L'entrée interactive (run_interactive_dialogue) injecte le rendu
        # stylé. Le moteur, lui, ne connaît que cette interface.
        from tui import PlainDialogueUI
        self.ui = ui or PlainDialogueUI()

    def _show(self, rendu):
        """N'affiche que ce que la couche de présentation a produit."""
        if rendu:
            self._say(rendu)

    # ---------- primitives de question (chacune valide et redemande) ----------
    def _ask(self, prompt, validate, error_msg, kind="free_text", options=None):
        for _ in range(self.max_retries):
            answer = self._ask_fn(prompt).strip()
            ok, value = validate(answer)
            if ok:
                return value
            self._say(self.ui.error(error_msg))
        raise DialogueError(f"Réponse invalide après {self.max_retries} tentatives : {prompt!r}")

    def _ask_identifier(self, prompt, forbidden=()):
        prompt = self.ui.field(prompt)

        def validate(a):
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Identifiant attendu (lettres/chiffres, commence par une lettre, sans doublon).",
                         kind="identifier")

    def _ask_optional_identifier(self, prompt, forbidden=()):
        """Comme _ask_identifier mais une réponse vide signifie 'terminé'."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if IDENT_RE.match(a) and a not in forbidden:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Identifiant attendu (ou vide pour terminer), sans doublon.",
                         kind="identifier")

    def _ask_choice(self, prompt, options, allow_none=False, hints=None):
        full = self.ui.menu(prompt, options, allow_none=allow_none, hints=hints)

        def validate(a):
            if allow_none and a == "0":
                return True, None
            if a.isdigit() and 1 <= int(a) <= len(options):
                return True, options[int(a) - 1]
            return False, None
        return self._ask(full, validate, "Choisir un numéro du menu.",
                         kind="choice", options=list(options) + (["aucun"] if allow_none else []))

    def _ask_yes_no(self, prompt):
        def validate(a):
            low = a.lower()
            if low in ("o", "oui", "y", "yes"):
                return True, True
            if low in ("n", "non", "no"):
                return True, False
            return False, None
        return self._ask(self.ui.yes_no(prompt), validate, "Répondre o ou n.", kind="yes_no")

    def _ask_free_text(self, prompt):
        prompt = self.ui.field(prompt)

        def validate(a):
            # Les guillemets doubles casseraient le STRING_LITERAL émis.
            if a and '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate, "Texte non vide, sans guillemets doubles.",
                         kind="free_text")

    def _ask_design_intent(self):
        """Intention visuelle (point 53) — posée UNIQUEMENT si l'utilisateur
        transmet un brief : sans page d'accueil à écrire, ces réponses
        n'auraient personne à qui servir. Rend la phrase ajoutée au brief.

        Ce que la structure ne dit pas : une même spec (entités, routes,
        rôles) sert aussi bien un portfolio contemplatif qu'un back-office
        pressé. L'IA UI ne peut pas trancher, et sans indication elle rend
        le dénominateur commun."""
        self._show(self.ui.section(
            "Intention visuelle — ce que la structure ne dit pas à l'IA "
            "qui dessinera l'interface."))
        action = self._ask_free_text(
            "Que doit pouvoir faire le visiteur en arrivant ? > ")
        registre = self._ask_choice("Quel registre visuel ?",
                                    [court for court, _ in DESIGN_REGISTERS])
        images = self._ask_choice("Quelle place pour les images ?",
                                  [court for court, _ in DESIGN_IMAGERY])
        phrase_registre = dict(DESIGN_REGISTERS)[registre]
        phrase_images = dict(DESIGN_IMAGERY)[images]
        return (f"le visiteur doit pouvoir {action.rstrip('.')} ; "
                f"{phrase_registre} ; {phrase_images}")

    def _ask_image_topic(self):
        """Sujet des images de démonstration (point 59). Le compilateur ne
        peut pas le déduire : « Blog pour des experts en cyber » est une
        phrase libre, en français, dont extraire un mot-clé d'illustration
        relèverait de l'interprétation — ce que le dialogue s'interdit. On
        demande donc, plutôt que de rendre des photos au hasard."""
        if not self._ask_yes_no(
                "Les images de démonstration doivent-elles illustrer un sujet "
                "précis ? (sinon : photos génériques)"):
            return None
        return self._ask_free_text(
            "  Mot-clé d'illustration, en anglais de préférence "
            "(ex. cybersecurity, pottery, architecture) > ")

    @staticmethod
    def _est_champ_image(nom):
        return any(k in nom.lower() for k in ("image", "photo", "cover", "avatar",
                                              "picture", "visuel", "illustration"))

    def _ask_editorial_sections(self):
        """Contenu éditorial statique (point 55). Une entité, un champ, une
        route décrivent des DONNÉES : rien dans une spec ne peut porter un
        « à propos ». Sans ces sections, l'IA n'a littéralement aucune
        matière pour autre chose qu'une liste et un formulaire."""
        sections = []
        if not self._ask_yes_no(
                "Ajouter du texte de présentation (à propos, méthode, "
                "services…) ? Aucune donnée du site ne peut le fournir."):
            return sections
        while True:
            titre = self._ask_free_text(
                f"  Titre de la section {len(sections) + 1} "
                f"(ex. À propos) > ")
            corps = self._ask_free_text("  Son texte > ")
            sections.append({"title": titre, "body": corps})
            if not self._ask_yes_no("  Ajouter une autre section ?"):
                return sections

    # ---------- déroulé du dialogue ----------
    def run(self):
        """Mène la conversation complète et retourne le texte de la spec .ml.
        REFONTE (point 45) : le dialogue ouvre sur le catalogue des 10 types
        d'applications les plus construits par les devs web — choisir un
        modèle pré-remplit tout et ne pose que les questions de suivi
        propres au modèle. « Partir de zéro » conserve le dialogue libre."""
        from app_templates import TEMPLATES, FREE_MODE_LABEL
        self._show(self.ui.banner())
        # AJOUT (bêta 3) : le libellé et son explication sont désormais deux
        # colonnes distinctes du menu, au lieu d'une seule chaîne « nom — aide »
        # qui débordait sur les terminaux étroits. La valeur de retour reste la
        # chaîne complète : le reste du moteur est inchangé.
        labels = [f"{t['name']} — {t['hint']}" for t in TEMPLATES] + [FREE_MODE_LABEL]
        courts = {label: TEMPLATES[i]["name"] for i, label in enumerate(labels[:-1])}
        courts[FREE_MODE_LABEL] = FREE_MODE_LABEL.split(" (")[0]
        aides = {TEMPLATES[i]["name"]: TEMPLATES[i]["hint"] for i in range(len(TEMPLATES))}
        aides[courts[FREE_MODE_LABEL]] = "décrire librement mes entités, sans modèle"

        self._show(self.ui.plan(["Type d'application", "Identité du projet",
                                 "Options du modèle", "Finitions"]))
        self._show(self.ui.phase(0))
        choisi_court = self._ask_choice("Quel type d'application construisez-vous ?",
                                        [courts[l] for l in labels], hints=aides)
        picked = labels[[courts[l] for l in labels].index(choisi_court)]
        if picked == FREE_MODE_LABEL:
            return self._run_free()
        template = TEMPLATES[labels.index(picked)]
        return self._run_from_template(template)

    def _run_from_template(self, template):
        """Chemin « modèle » : questions de suivi spécifiques, puis les
        finitions communes. Le modèle est copié en profondeur — le catalogue
        n'est jamais muté entre deux exécutions (déterminisme)."""
        import copy
        from app_templates import apply_effects
        template = copy.deepcopy(template)

        self._show(self.ui.phase(1))
        app_name = self._ask_identifier("Nom de l'application (ex. StudioNova) > ")
        description = self._ask_free_text(
            "Décrivez le projet en une phrase (servira de brief frontend) > ")

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
        want_seed = bool(template["seeds"]) and self._ask_yes_no(
            "Pré-remplir le site avec les données de démonstration du modèle ?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Transmettre votre description à l'IA frontend comme brief de page d'accueil ?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = self._ask_editorial_sections() if want_landing else []
        self._recap(app_name, entities, actors, self_register, public_read, owned)

        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read, public_create,
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               image_topic=image_topic,
                               self_register=self_register,
                               extra_rules=template["extra_rules"],
                               custom_seeds=template["seeds"])
        from parser import parse_monl_string
        from ast_validator import MonlAST
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
        want_seed = self._ask_yes_no("Pré-remplir le site avec des données de démonstration ?")
        image_topic = self._ask_image_topic() if want_seed else None
        want_landing = self._ask_yes_no(
            "Transmettre votre description à l'IA frontend comme brief de page d'accueil ?")
        design_intent = self._ask_design_intent() if want_landing else None
        sections = self._ask_editorial_sections() if want_landing else []

        # Entités propriétaires + relations de propriété (helper partagé
        # avec le chemin « modèle » ; dédupliqué si déjà déclaré à la main).
        readers = {e: readers.get(e, set()) for e in entities}
        managers = {e: managers.get(e, [actors[0]]) for e in entities}
        self._ensure_ownership_structure(entities, managers, readers, owned, relations)

        self._recap(app_name, entities, actors, self_register, public_read, owned)
        spec = self._emit_spec(app_name, description, entities, relations, actors,
                               managers, readers, public_read,
                               [public_create] if public_create else [],
                               owned, want_seed, want_landing,
                               design_intent=design_intent,
                               sections=sections,
                               image_topic=image_topic,
                               self_register=self_register)

        # Garantie finale : la spec émise DOIT compiler. On la revalide par le
        # vrai pipeline — si ce n'est pas le cas, c'est un bug du moteur, pas
        # de l'utilisateur, et on échoue bruyamment plutôt que de rendre un
        # fichier cassé.
        from parser import parse_monl_string
        from ast_validator import MonlAST
        MonlAST(parse_monl_string(spec)).validate_and_audit()
        return spec

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

    def _recap(self, app_name, entities, actors, self_register, public_read, owned):
        """Dernier regard sur ce qui va être écrit, avant compilation."""
        lignes = [
            ("Application", app_name),
            ("Entités", ", ".join(entities) or "aucune"),
            ("Rôles", ", ".join(actors) or "aucun"),
            ("Inscription en ligne", self_register or "fermée (manage.py)"),
            ("Lisible sans compte", ", ".join(public_read) or "rien"),
        ]
        prives = [e for e in owned if e not in public_read]
        if prives:
            lignes.append(("Lecture réservée au propriétaire", ", ".join(prives)))
        if owned:
            lignes.append(("Propriété par créateur",
                           ", ".join(f"{e} ({a})" for e, a in owned.items())))
        self._show(self.ui.recap("Ce que la spec va déclarer", lignes))

    # ---------- émission déterministe de la spec ----------
    def _emit_spec(self, app_name, description, entities, relations, actors,
                   managers, readers, public_read, public_create,
                   owned, want_seed, want_landing, design_intent=None,
                   sections=(),
                   image_topic=None,
                   self_register=None, extra_rules=(), custom_seeds=None):
        lines = [f"app {app_name}", "",
                 "# Spécification générée par le dialogue guidé monl (déterministe, sans IA).",
                 f"# Brief du projet : {description}", ""]

        for ent, fields in entities.items():
            lines.append(f"entity {ent}")
            for fname, ftype in fields:
                lines.append(f"    {fname}: {ftype}")
            lines.append("")

        for src, rtype, tgt in relations:
            lines.append(f"relation {src} {rtype} {tgt}")
        if relations:
            lines.append("")

        # CORRECTIF (bêta 3) : sans le marqueur 'selfRegister', '/register'
        # refuse toute inscription — une spec issue du dialogue produisait donc
        # une application dont personne ne pouvait créer de compte.
        for act in actors:
            lines.append(f"actor {act} selfRegister" if act == self_register
                         else f"actor {act}")
        lines.append("")

        # Règles : premier champ requis, lecture/création publiques
        for ent, fields in entities.items():
            first_field = fields[0][0]
            lines.append(f"rule {ent}.{first_field} required")
        for ent in public_read:
            lines.append(f"rule {ent}.Read public")
        for ent in public_create:
            lines.append(f"rule {ent}.Create public")
        for ent, owner in owned.items():
            # CORRECTIF (bêta 3, fuite entre comptes) : une entité possédée par
            # ses créateurs ET non lisible sans compte est de la donnée privée
            # (dépenses, commandes, tâches personnelles). Sans cette règle, tout
            # titulaire d'un compte listait les enregistrements de tous les
            # autres — seule l'écriture était protégée. La règle est écrite en
            # clair dans la spec : elle reste relisable et supprimable.
            if ent not in public_read:
                lines.append(f"rule {ent}.Read ownedBy {owner}")
            lines.append(f"rule {ent}.Update ownedBy {owner}")
            lines.append(f"rule {ent}.Delete ownedBy {owner}")
        for ent in entities:
            if len(managers[ent]) > 1:
                shared_list = ", ".join(managers[ent])
                for action in ("Create", "Update", "Delete"):
                    lines.append(f"rule {ent}.{action} sharedBy {shared_list}")
        # Règles avancées portées par les modèles du catalogue (increments,
        # hidden, categorized…) — émises telles quelles, validées comme tout
        # le reste par le parseur + l'audit en sortie de dialogue.
        lines.extend(extra_rules)
        lines.append("")

        # Workflows : un gestionnaire CRUD complet par entité (jamais de
        # collision d'écriture), puis un workflow de lecture par lecteur.
        for ent in entities:
            for actor in managers[ent]:
                suffix = f"By{actor}" if len(managers[ent]) > 1 else ""
                lines.append(f"workflow Manage{ent}{suffix} for {actor}")
                for action in ("Create", "Read", "Update", "Delete"):
                    lines.append(f"    {action} {ent}")
                lines.append("")
        for act in actors:
            readable = [ent for ent in entities if act in readers[ent]]
            if readable:
                lines.append(f"workflow Browse{act} for {act}")
                for ent in readable:
                    lines.append(f"    Read {ent}")
                lines.append("")

        if want_seed:
            custom_seeds = custom_seeds or {}
            # Données réalistes du modèle en priorité ; repli générique pour
            # les entités publiques qui n'en ont pas.
            from app_templates import image_topic_url
            verrou = 0
            for ent, rows in custom_seeds.items():
                if not rows or ent not in entities:
                    continue
                lines.append(f"seed {ent}")
                for row in rows:
                    parts = []
                    for f, v in row.items():
                        # Le catalogue est chargé avant le dialogue : ses URL
                        # d'illustration ignorent le sujet du projet. On les
                        # remplace ici, une fois qu'il est connu (point 59).
                        if image_topic and self._est_champ_image(f):
                            verrou += 1
                            v = image_topic_url(image_topic, verrou)
                        parts.append(f"{f}: {self._literal(v)}")
                    lines.append("    " + ", ".join(parts))
                lines.append("")
            for ent in public_read:
                if ent in custom_seeds:
                    continue
                seedable = [(f, t) for f, t in entities[ent] if t in SEEDABLE_TYPES]
                if not seedable:
                    continue
                lines.append(f"seed {ent}")
                for n in (1, 2, 3):
                    parts = [f"{f}: {self._seed_value(f, t, n, image_topic)}"
                             for f, t in seedable]
                    lines.append("    " + ", ".join(parts))
                lines.append("")

        if want_landing:
            # Le brief porte la description ET l'intention visuelle : c'est la
            # seule phrase du contrat qui dise à l'IA UI à quoi sert le site
            # (point 53). Le commentaire d'en-tête, lui, reste court.
            brief = (f"{description.rstrip('.')} — {design_intent}"
                     if design_intent else description)
            lines.append("landing")
            lines.append(f'    brief: "{brief}"')
            for s in sections:
                lines.append(f'    section "{s["title"]}": "{s["body"]}"')
            lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _literal(value):
        """Valeur de seed -> littéral DSL (la grammaire n'accepte que
        STRING_LITERAL et SIGNED_NUMBER)."""
        if isinstance(value, bool):
            raise DialogueError("un seed ne peut pas contenir de booléen (grammaire)")
        if isinstance(value, (int, float)):
            return str(value)
        return '"' + str(value).replace('"', "'") + '"'

    @staticmethod
    def _seed_value(field_name, ftype, n, image_topic=None):
        low = field_name.lower()
        if ftype in ("Integer",):
            return str(n * 10)
        if ftype in ("Float", "Money"):
            return f"{n * 10}.5"
        if ftype == "Email":
            return f'"demo{n}@exemple.fr"'
        if any(k in low for k in ("image", "photo", "url", "cover", "avatar")):
            # 1600×900 : la source doit tenir un hero pleine largeur sur écran
            # haute densité, sinon elle est agrandie et paraît molle (point 59).
            if image_topic:
                from app_templates import image_topic_url
                return f'"{image_topic_url(image_topic, n)}"'
            return f'"https://picsum.photos/seed/demo{n}/1600/900"'
        if ftype == "Text":
            return f'"Contenu de démonstration numéro {n}, généré par le dialogue guidé."'
        return f'"Exemple {n}"'


def run_interactive_dialogue():
    """Point d'entrée réel (stdin/stdout) utilisé par cli.py.

    C'est le seul endroit où le rendu stylé est injecté : partout ailleurs
    (tests, sortie redirigée), le moteur reste en rendu nu.
    """
    from tui import PlainDialogueUI, StyledDialogueUI, Terminal
    terminal = Terminal()
    # Hors terminal interactif (sortie redirigée, CI), rendu nu : un journal
    # ne doit contenir ni séquence ANSI ni caractère de dessin.
    ui = StyledDialogueUI(terminal) if terminal.color else PlainDialogueUI()
    dialogue = GuidedDialogue(ask=input, say=print, ui=ui)
    return dialogue.run()
