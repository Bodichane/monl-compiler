"""Ce que le site doit MONTRER : registre visuel, images, textes, pied de page.

Point 72 : le dialogue recueille une DIRECTION, il ne choisit ni palette ni
typographie. Brique 30 (point 146) : les liens de pied de page sont
DÉCLARÉS ici — une brique sans producteur n'existe pas."""

from .fondations import DESIGN_IMAGERY, DESIGN_REGISTERS, adresse_de_lien


class DirectionMixin:
    """Ce que le site doit MONTRER : registre visuel, images, textes, pied de page."""

    def _ask_design_intent(self):
        """Intention visuelle (point 53) — posée UNIQUEMENT si l'utilisateur
        transmet un brief : sans page d'accueil à écrire, ces réponses
        n'auraient personne à qui servir. Rend la phrase ajoutée au brief.

        Ce que la structure ne dit pas : une même spec (entités, routes,
        rôles) sert aussi bien un portfolio contemplatif qu'un back-office
        pressé. L'IA UI ne peut pas trancher, et sans indication elle rend
        le dénominateur commun."""
        self._show(self.ui.section(
            "Visual direction — what the structure does not tell the AI "
            "that will design the interface."))
        action = self._ask_free_text(
            "What should visitors be able to do when they arrive? > ")
        registre = self._ask_choice("Which visual style?",
                                    [court for court, _ in DESIGN_REGISTERS])
        images = self._ask_choice("How prominent should images be?",
                                  [court for court, _ in DESIGN_IMAGERY])
        phrase_registre = dict(DESIGN_REGISTERS)[registre]
        phrase_images = dict(DESIGN_IMAGERY)[images]
        return (f"the visitor must be able to {action.rstrip('.')} ; "
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
                "Should the illustrations evoke a specific subject? "
                "(otherwise: no visual guidance)"):
            return None
        return self._ask_free_text(
            "  Illustration keyword, preferably in English "
            "(e.g. cybersecurity, pottery, architecture) > ")

    @staticmethod
    def _est_champ_image(nom):
        return any(k in nom.lower() for k in ("image", "photo", "cover", "avatar",
                                              "picture", "visuel", "illustration"))

    #: Ce qu'un pied de page porte SOUVENT, dans l'ordre où on y pense. La
    #: liste est PROPOSÉE, jamais imposée : chaque entrée se passe en laissant
    #: vide, exactement comme les rubriques du point 61.
    LIENS_PROPOSES = (
        {"label": "Email", "ask": "contact address"},
        {"label": "Phone", "ask": "phone number"},
        {"label": "Instagram", "ask": "account address"},
        {"label": "Facebook", "ask": "page address"},
        {"label": "LinkedIn", "ask": "page address"},
    )

    #: La complétion vit au niveau du module : la console web de la
    #: plateforme la partage sans instancier un dialogue.
    _adresse_complete = staticmethod(adresse_de_lien)

    def _ask_footer_links(self):
        """Les liens du pied de page (brique 30).

        La brique existait depuis le point 144 et RIEN ne la produisait : ni
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
                    f"Unrecognized address: {saisie!r}. Expected a web address "
                    "(example.com/studio), an email address, or a phone number — "
                    "skipping this link."))
                return
            if adresse != saisie.strip():
                self._say(self.ui.note(f"saved: {adresse}"))
            if label.casefold() in vus:
                self._say(self.ui.error(
                    f"‘{label}’ is already used: a footer with duplicate labels "
                    "makes it unclear which link to follow — skipping this link."))
                return
            vus.add(label.casefold())
            liens.append({"label": label, "url": adresse})

        self._show(self.ui.section(
            "Footer — how to contact and follow you. A footer with no "
            "destinations makes a site look abandoned. monl does not check "
            "whether an address responds; it checks that a browser can open it. "
            "Leave blank to skip."))
        for propose in self.LIENS_PROPOSES:
            saisie = self._ask_optional_free_text(
                f"  {propose['label']} — {propose['ask']} > ")
            if saisie:
                retenir(propose["label"], saisie)
        while self._ask_yes_no("  Add another link (X, YouTube, TikTok, "
                               "press…) ?"):
            libelle = self._ask_free_text("  Its label (e.g. YouTube) > ")
            saisie = self._ask_optional_free_text("  Its address > ")
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
                    "About content — these sections are expected on this type "
                    "of site. No data can provide them; only your text can. "
                    "Enter one paragraph at a time; leave blank to skip."))
            corps = self._ask_paragraphs(
                f"  {spec['title']} — {spec['ask']} > ")
            if corps:
                sections.append({"title": spec["title"], "body": corps})
        if defaults:
            if not self._ask_yes_no("  Add another section?"):
                return sections
        elif not self._ask_yes_no(
                "Add about content (about, approach, services…)? No site data "
                "can provide this."):
            return sections
        while True:
            titre = self._ask_free_text(
                f"  Section title {len(sections) + 1} "
                f"(e.g. About) > ")
            corps = self._ask_paragraphs("  Its text > ")
            if corps:
                sections.append({"title": titre, "body": corps})
            if not self._ask_yes_no("  Add another section?"):
                return sections
