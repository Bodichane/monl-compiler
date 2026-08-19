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

# POINT 64 : séparateur de paragraphes dans un texte éditorial. La grammaire
# n'accepte pas de retour à la ligne dans un STRING_LITERAL ; ce caractère
# tient sa place dans la spec et n'existe QUE là — le contrat frontend le
# retraduit en saut de paragraphe (frontend_contract.paragraphes). Choisi
# parce qu'il ne se tape pas par accident dans de la prose française.
PARAGRAPH_SEP = " ¶ "

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


def adresse_de_lien(saisie):
    """Rend l'adresse telle qu'un navigateur saura l'ouvrir, ou None.

    SOURCE UNIQUE, partagée par le dialogue guidé et par la console web de
    la plateforme : deux règles de complétion finiraient par diverger, et
    c'est celle qui décide si un lien de pied de page mène quelque part.

    Personne ne tape « mailto: » ni « https:// » spontanément, et une adresse
    sans schéma est lue comme un chemin RELATIF : le lien mène alors à une
    page inexistante du site lui-même. Compléter n'est pas deviner tant qu'il
    n'existe qu'UNE lecture — et l'appelant DIT ce qu'il a complété, ce qui
    est toute la différence avec le fait de corriger d'office (point 105).
    """
    saisie = saisie.strip()
    if not saisie:
        return None
    if saisie.lower().startswith(("https://", "http://", "mailto:", "tel:")):
        return saisie
    # Le téléphone AVANT le refus des espaces : « +33 6 12 34 56 78 » est
    # la façon dont tout le monde écrit un numéro, et c'est la seule
    # valeur de cette liste qui en contienne légitimement.
    compact = saisie.replace(" ", "")
    if re.fullmatch(r"\+?[0-9.\-]{6,20}", compact):
        return "tel:" + compact
    if " " in saisie:
        return None
    if "@" in saisie and "." in saisie.split("@")[-1]:
        return "mailto:" + saisie
    domaine = saisie.split("/")[0]
    if "." in domaine and not domaine.startswith("."):
        return "https://" + saisie
    return None


class GuidedDialogue:
    def __init__(self, ask, say=None, max_retries=3, ui=None, express=False,
                 choose_experience=False, express_links=()):
        """Dialogue guidé à règles, entièrement déterministe : aucune IA,
        aucun appel réseau. Chaque réponse est validée en saisie stricte
        (numéros, o/n, identifiants) et redemandée tant qu'elle est invalide.
        La spécification produite est ensuite revalidée par le vrai parseur
        avant d'être écrite."""
        self._ask_fn = ask
        self._say = say or (lambda *_: None)
        self.max_retries = max_retries
        self.express = express
        self.choose_experience = choose_experience
        # Le mode express ne pose AUCUNE question de finition — c'est sa
        # raison d'être. Ses liens de pied de page arrivent donc par
        # l'appelant (la console web), jamais par une question de plus.
        self.express_links = tuple(express_links or ())
        # AJOUT (bêta 3) : couche de présentation. Par défaut, rendu nu —
        # chaînes strictement identiques à l'historique, donc les tests
        # scriptés et toute sortie redirigée sont insensibles à l'habillage.
        # L'entrée interactive (run_interactive_dialogue) injecte le rendu
        # stylé. Le moteur, lui, ne connaît que cette interface.
        from .tui import PlainDialogueUI
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

    def _ask_optional_free_text(self, prompt):
        """Comme _ask_free_text, mais une réponse vide vaut « passer »."""
        prompt = self.ui.field(prompt)

        def validate(a):
            if a == "":
                return True, None
            if '"' not in a and "\n" not in a:
                return True, a
            return False, None
        return self._ask(prompt, validate,
                         "Texte sans guillemets doubles (ou vide pour passer).",
                         kind="free_text")

    def _ask_paragraphs(self, prompt):
        """Un texte éditorial en PLUSIEURS paragraphes (point 64).

        Une saisie d'une seule ligne était un piège silencieux : un « à
        propos » collé depuis un traitement de texte arrivait aplati, ses
        paragraphes recollés sans même une espace (« …8 ans.Mon travail… »),
        et l'IA d'interface recevait un mur de texte sans césure possible.
        Le retour à la ligne reste interdit — il casserait le
        STRING_LITERAL émis — donc on demande les paragraphes l'un après
        l'autre, et on les joint par un séparateur que le contrat retraduit
        en vrais sauts de paragraphe.

        Rend None si le premier paragraphe est vide (rubrique passée)."""
        premier = self._ask_optional_free_text(prompt)
        if not premier:
            return None
        paragraphes = [premier]
        while True:
            suite = self._ask_optional_free_text(
                "    … paragraphe suivant (vide pour terminer) > ")
            if not suite:
                return PARAGRAPH_SEP.join(paragraphes)
            paragraphes.append(suite)

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
        """Sujet des illustrations (point 59, réécrit). Le compilateur ne peut
        pas le déduire : « Blog pour des experts en cyber » est une phrase
        libre, en français, dont extraire un mot-clé relèverait de
        l'interprétation — ce que le dialogue s'interdit.

        Ce que la réponse produit a CHANGÉ : plus aucune URL distante, mais
        une phrase du brief qui dit à l'IA d'interface ce que les visuels
        doivent évoquer. La question garde donc un effet ; ce sont les images
        de démonstration livrées par un tiers qui ont disparu."""
        if not self._ask_yes_no(
                "Les illustrations doivent-elles évoquer un sujet précis ? "
                "(sinon : aucune indication visuelle)"):
            return None
        return self._ask_free_text(
            "  Mot-clé d'illustration, en anglais de préférence "
            "(ex. cybersecurity, pottery, architecture) > ")

    @staticmethod
    def _est_champ_image(nom):
        return any(k in nom.lower() for k in ("image", "photo", "cover", "avatar",
                                              "picture", "visuel", "illustration"))

    #: Ce qu'un pied de page porte SOUVENT, dans l'ordre où on y pense. La
    #: liste est PROPOSÉE, jamais imposée : chaque entrée se passe en laissant
    #: vide, exactement comme les rubriques du point 61.
    LIENS_PROPOSES = (
        {"label": "Courriel", "ask": "adresse de contact"},
        {"label": "Téléphone", "ask": "numéro à appeler"},
        {"label": "Instagram", "ask": "adresse du compte"},
        {"label": "Facebook", "ask": "adresse de la page"},
        {"label": "LinkedIn", "ask": "adresse de la page"},
    )

    #: La complétion vit au niveau du module : la console web de la
    #: plateforme la partage sans instancier un dialogue.
    _adresse_complete = staticmethod(adresse_de_lien)

    def _ask_footer_links(self):
        """Les liens du pied de page (brique 29).

        La brique existait depuis le point 141 et RIEN ne la produisait : ni
        ce dialogue ni aucun des dix modèles ne déclarait un seul lien, donc
        tout site sortait avec un pied de page sans destination. Une règle qui
        ne produit rien est exactement ce que le point 85 interdit au
        compilateur ; l'interdit vaut autant pour le dialogue qui écrit la
        spec.

        monl ne vérifie PAS qu'une adresse répond — il ne fait aucun appel
        réseau (même frontière qu'au point 83 pour les images distantes). Il
        vérifie qu'un navigateur saura l'ouvrir, et c'est tout ce qu'il
        promet.
        """
        liens, vus = [], set()

        def retenir(label, saisie):
            adresse = self._adresse_complete(saisie)
            if adresse is None:
                self._say(self.ui.error(
                    f"Adresse incomprise : {saisie!r}. Attendu une adresse web "
                    "(exemple.fr/atelier), un courriel ou un numéro — le lien "
                    "est passé."))
                return
            if adresse != saisie.strip():
                self._say(self.ui.note(f"enregistré : {adresse}"))
            if label.casefold() in vus:
                self._say(self.ui.error(
                    f"« {label} » est déjà pris : un pied de page qui répète "
                    "un libellé fait hésiter sur lequel suivre — lien ignoré."))
                return
            vus.add(label.casefold())
            liens.append({"label": label, "url": adresse})

        self._show(self.ui.section(
            "Pied de page — où vous joindre, et où vous suivre. Un pied sans "
            "aucune destination donne un site à l'abandon. monl ne vérifie pas "
            "qu'une adresse répond : il vérifie qu'un navigateur saura "
            "l'ouvrir. Laisser vide pour passer."))
        for propose in self.LIENS_PROPOSES:
            saisie = self._ask_optional_free_text(
                f"  {propose['label']} — {propose['ask']} > ")
            if saisie:
                retenir(propose["label"], saisie)
        while self._ask_yes_no("  Ajouter un autre lien (X, YouTube, TikTok, "
                               "presse…) ?"):
            libelle = self._ask_free_text("  Son libellé (ex. YouTube) > ")
            saisie = self._ask_optional_free_text("  Son adresse > ")
            if saisie:
                retenir(libelle, saisie)
        return liens

    def _ask_editorial_sections(self, defaults=()):
        """Contenu éditorial statique (point 55). Une entité, un champ, une
        route décrivent des DONNÉES : rien dans une spec ne peut porter un
        « à propos ». Sans ces sections, l'IA n'a littéralement aucune
        matière pour autre chose qu'une liste et un formulaire.

        POINT 61 : quand le modèle choisi porte des rubriques attendues de sa
        catégorie, on n'en demande plus l'EXISTENCE — on en demande le TEXTE,
        rubrique par rubrique. Demander « voulez-vous un à propos ? » à qui
        construit un portfolio est la même faute qu'au point 60. Une réponse
        vide passe la rubrique : le standard est proposé, jamais imposé."""
        sections = []
        entete_montree = False
        for spec in defaults:
            if not entete_montree:
                entete_montree = True
                self._show(self.ui.section(
                    "Textes de présentation — ces rubriques sont attendues sur "
                    "un site de ce type. Aucune donnée ne peut les fournir : "
                    "seul votre texte le peut. Un paragraphe par saisie ; "
                    "laisser vide pour passer."))
            corps = self._ask_paragraphs(
                f"  {spec['title']} — {spec['ask']} > ")
            if corps:
                sections.append({"title": spec["title"], "body": corps})
        if defaults:
            if not self._ask_yes_no("  Ajouter une autre section ?"):
                return sections
        elif not self._ask_yes_no(
                "Ajouter du texte de présentation (à propos, méthode, "
                "services…) ? Aucune donnée du site ne peut le fournir."):
            return sections
        while True:
            titre = self._ask_free_text(
                f"  Titre de la section {len(sections) + 1} "
                f"(ex. À propos) > ")
            corps = self._ask_paragraphs("  Son texte > ")
            if corps:
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
        from .app_templates import FREE_MODE_LABEL, TEMPLATES
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

        from .app_templates import apply_effects
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
            from .ast_validator import MonlAST
            from .parser import parse_monl_string
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
                               extra_rules=template["extra_rules"],
                               extra_workflows=template.get("extra_workflows", ()),
                               custom_seeds=template["seeds"],
                               payable=payable)
        from .ast_validator import MonlAST
        from .parser import parse_monl_string
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
                               payable=payable)

        # Garantie finale : la spec émise DOIT compiler. On la revalide par le
        # vrai pipeline — si ce n'est pas le cas, c'est un bug du moteur, pas
        # de l'utilisateur, et on échoue bruyamment plutôt que de rendre un
        # fichier cassé.
        from .ast_validator import MonlAST
        from .parser import parse_monl_string
        MonlAST(parse_monl_string(spec)).validate_and_audit()
        return spec

    CHAMP_QUANTITE = "quantite"
    # POINT 86 : le sous-total d'une ligne de panier. Nommé ici plutôt qu'en dur
    # dans l'émetteur — deux endroits finiraient par diverger.
    CHAMP_SOUS_TOTAL = "sousTotal"
    # POINT 89 : la date d'arrivée de ce qu'on encaisse. AUCUNE question ne la
    # propose, volontairement : elle est écrite par le serveur, ne peut donc pas
    # être fausse, et une commande sans date n'est pas une commande — la seule
    # réponse utile serait « oui ». Le dialogue émet déjà de même le total, le
    # plancher de stock et le décompte sans les faire arbitrer un par un.
    CHAMP_DATE = "creeLe"

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

    @staticmethod
    def _nom_de_ligne(entite, entities):
        """Un nom d'entité libre pour la ligne de panier. Une collision
        silencieuse écraserait une entité de l'utilisateur."""
        base = f"Ligne{entite}"
        nom, n = base, 2
        while nom in entities:
            nom, n = f"{base}{n}", n + 1
        return nom

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

    def _recap(self, app_name, entities, actors, self_register, public_read, owned,
               payable=None):
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
        if payable:
            lignes.append((
                "Montant encaissé",
                f"{payable['entity']}.{payable['field']} — calculé par le serveur "
                f"({payable['source_entity']}.{payable['source_field']} × "
                f"{payable['factor']}), clé Stripe requise"))
        self._show(self.ui.recap("Ce que la spec va déclarer", lignes))

    # ---------- émission déterministe de la spec ----------
    def _emit_spec(self, app_name, description, entities, relations, actors,
                   managers, readers, public_read, public_create,
                   owned, want_seed, want_landing, design_intent=None,
                   sections=(), links=(),
                   image_topic=None,
                   self_register=None, extra_rules=(), extra_workflows=(),
                   custom_seeds=None,
                   payable=None):
        lines = [f"app {app_name}", "",
                 "# Spécification générée par le dialogue guidé monl (déterministe, sans IA).",
                 f"# Brief du projet : {description}"]
        # Écrit AUSSI en commentaire : sans bloc `landing`, la spec n'a pas de
        # brief où porter le sujet, et l'humain qui rouvre le fichier doit
        # quand même savoir ce qu'il avait demandé. Un commentaire ne va pas au
        # contrat — c'est assumé : il documente, il ne promet rien.
        if image_topic:
            lines.append(f"# Sujet des illustrations : {image_topic}")
        lines.append("")

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

        # POINT 86 : les champs que le SERVEUR calcule ne peuvent pas être
        # « requis » — le client ne peut pas les envoyer. Le dialogue posait la
        # règle sur le premier champ de chaque entité sans regarder si la brique
        # de paiement venait de lui retirer le droit d'être écrit.
        calcules_par_le_serveur = set()
        if payable:
            porte = payable.get("line_entity") or payable["entity"]
            calcules_par_le_serveur.add((payable["entity"], payable["field"]))
            calcules_par_le_serveur.add(
                (porte, self.CHAMP_SOUS_TOTAL if payable.get("line_entity")
                 else payable["field"]))

        # Règles : premier champ requis, lecture/création publiques
        for ent, fields in entities.items():
            first_field = fields[0][0]
            if (ent, first_field) in calcules_par_le_serveur:
                continue
            lines.append(f"rule {ent}.{first_field} required")
        # Une visibilité conditionnelle remplace la visibilité publique
        # inconditionnelle : conserver les deux règles ferait échouer le
        # validateur et, surtout, rendrait le filtre métier inopérant.
        public_when_entities = {
            rule.split()[1].split(".", 1)[0]
            for rule in extra_rules
            if rule.startswith("rule ") and " publicWhen " in rule
        }
        for ent in public_read:
            if ent not in public_when_entities:
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
        if payable:
            # POINT 75 : les règles sont écrites en clair, avec ce qu'elles
            # déclenchent. L'auteur doit pouvoir les relire — et les supprimer —
            # sans ouvrir la documentation : c'est le seul endroit de la spec
            # qui fasse sortir une requête du backend.
            entite, montant = payable["entity"], payable["field"]
            source, prix = payable["source_entity"], payable["source_field"]
            lines.append("")
            lines.append("# POINT 89 : la date d'arrivée, écrite par le serveur à la")
            lines.append("# création et jamais ensuite. Elle disparaît des corps de")
            lines.append("# requête : une date qu'on se donne à soi-même n'atteste de")
            lines.append(f"# rien, et un carnet de {entite} où chacun choisit ses dates")
            lines.append("# ne dit plus dans quel ordre honorer.")
            lines.append(f"rule {entite}.{self.CHAMP_DATE} timestamp")
            facteur = payable["factor"]
            ligne = payable.get("line_entity")
            # POINT 86 : deux formes possibles. Sans panier, le montant est
            # calculé sur l'entité encaissée elle-même (forme du point 77) ;
            # avec panier, il est la SOMME des sous-totaux de ses lignes
            # (point 82). Les deux satisfont l'exigence du point 79 — un montant
            # qu'aucun corps de requête ne peut porter.
            porteur = ligne or entite
            calcule = payable.get("line_subtotal", self.CHAMP_SOUS_TOTAL) if ligne else montant
            lines.append("")
            if not ligne:
                lines.append("# La quantité est le seul chiffre que l'acheteur fournit,")
                lines.append("# et elle est obligatoire : sans elle le calcul ci-dessous")
                lines.append("# porterait sur du vide.")
                lines.append(f"rule {entite}.{facteur} required")
                lines.append("")
            lines.append("# POINT 79 : le montant est CALCULÉ PAR LE SERVEUR — prix au")
            lines.append(f"# catalogue ({source}.{prix}) multiplié par la quantité. Le")
            lines.append(f"# champ {porteur}.{calcule} disparaît donc des corps de requête,")
            lines.append("# à la création comme à la modification. Sans ce calcul,")
            lines.append("# l'acheteur fixerait lui-même ce qu'il règle : il devient")
            lines.append("# propriétaire de ce qu'il crée, donc le payeur.")
            lines.append(f"rule {porteur}.{calcule} derivedFrom {source}.{prix} by {facteur}")
            lines.append("")
            if ligne:
                lines.append("# POINT 82 : le total du panier est la SOMME de ses lignes,")
                lines.append("# recalculée par le serveur à chaque ligne ajoutée, modifiée")
                lines.append("# ou supprimée. Sommer un sous-total que le navigateur")
                lines.append("# écrirait serait la faille du point 77 en une addition de")
                lines.append("# plus : le compilateur le refuse.")
                lines.append(f"rule {entite}.{montant} sumOf {ligne}.{calcule}")
                lines.append("")
            if payable.get("stock_field"):
                stock = payable["stock_field"]
                lines.append("# POINT 85 : ce plancher n'est pas décoratif — c'est lui qui")
                lines.append("# arme la vérification de disponibilité ci-dessous. Sans lui,")
                lines.append("# le décompte passerait sous zéro et le stock mentirait.")
                lines.append(f"rule {source}.{stock} min 0")
                lines.append("")
                lines.append("# POINT 86 : le stock suit les commandes, et retire CE QUE LE")
                lines.append("# CLIENT A DEMANDÉ — pas une constante. Commander plus que le")
                lines.append("# stock disponible répond 409, sans rien décompter.")
                lines.append(f"rule {porteur}.Create decrements {source}.{stock} by {facteur}")
                lines.append("")
            lines.append("# Encaissement : le champ nommé porte le MONTANT, donc")
            lines.append("# l'entité à encaisser. Deux routes en découlent —")
            lines.append("# POST /entite/{id}/paiement (aucun corps : le montant est")
            lines.append("# relu en base) et POST /paiement/webhook, dont la")
            lines.append("# signature est vérifiée. Sans STRIPE_SECRET_KEY, elles")
            lines.append("# répondent 503 ; le reste de l'application fonctionne.")
            lines.append(f"rule {entite}.{montant} payable")
            lines.append("")
        # Règles avancées portées par les modèles du catalogue (increments,
        # hidden, categorized…) — émises telles quelles, validées comme tout
        # le reste par le parseur + l'audit en sortie de dialogue.
        # Les règles post-paiement ne sont valides que si le dialogue a
        # effectivement activé le paiement. Le modèle reste donc compilable
        # quand l'utilisateur refuse cette option.
        rules_to_emit = [
            rule for rule in extra_rules
            if payable or " writableAfterPayment " not in f" {rule} "
        ]
        lines.extend(rules_to_emit)
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
        for workflow in extra_workflows:
            lines.append(f"workflow {workflow['name']} for {workflow['actor']}")
            for action, target in workflow["actions"]:
                lines.append(f"    {action} {target}")
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
            for ent, rows in custom_seeds.items():
                if not rows or ent not in entities:
                    continue
                lines.append(f"seed {ent}")
                for row in rows:
                    parts = []
                    for f, v in row.items():
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
            # Le sujet d'illustration ne produit plus d'URL distante : il part
            # ICI, dans la seule phrase du contrat que l'IA d'interface lit
            # pour savoir à quoi sert le site. Sans ce report, la question du
            # dialogue deviendrait une question sans effet — ce que le
            # point 85 interdit au compilateur, et qui vaut autant pour le
            # dialogue qui écrit la spec.
            if image_topic:
                brief = (f"{brief.rstrip('.')}. Les illustrations doivent "
                         f"évoquer : {image_topic}.")
            lines.append("landing")
            lines.append(f'    brief: "{brief}"')
            for s in sections:
                lines.append(f'    section "{s["title"]}": "{s["body"]}"')
            # Brique 29 : les destinations du pied de page. Sans elles, le
            # pied sort sans un seul lien — et rien dans la spec ne peut les
            # inventer, pas plus qu'une entité ne peut porter un « à propos ».
            for lien in links:
                lines.append(f'    link "{lien["label"]}": "{lien["url"]}"')
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
            # VIDE, jamais une URL distante : une démonstration qui va chercher
            # ses images chez un tiers contredit l'autonomie que monl promet, et
            # ne s'ouvre pas hors ligne. La vraie photo passe par
            # `monl assets add` (brique 13). Voir `_img` dans app_templates.py.
            return '""'
        if ftype == "Text":
            return f'"Contenu de démonstration numéro {n}, généré par le dialogue guidé."'
        return f'"Exemple {n}"'


def run_interactive_dialogue():
    """Point d'entrée réel (stdin/stdout) utilisé par cli.py.

    C'est le seul endroit où le rendu stylé est injecté : partout ailleurs
    (tests, sortie redirigée), le moteur reste en rendu nu.
    """
    from .tui import PlainDialogueUI, StyledDialogueUI, Terminal
    terminal = Terminal()
    # Hors terminal interactif (sortie redirigée, CI), rendu nu : un journal
    # ne doit contenir ni séquence ANSI ni caractère de dessin.
    ui = StyledDialogueUI(terminal) if terminal.color else PlainDialogueUI()
    dialogue = GuidedDialogue(ask=input, say=print, ui=ui,
                              choose_experience=True)
    return dialogue.run()
