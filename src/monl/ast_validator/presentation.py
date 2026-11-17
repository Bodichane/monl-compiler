"""Ce que la spec dit de l'ÉCRAN, sans rien décider du visuel.

Point 72 : le compilateur ne décide RIEN — ni palette, ni typographie. Il
vérifie la forme de `ui`, de `landing` et des liens de pied de page
(brique 30, point 144), dont l'adresse doit porter un schéma sans quoi le
navigateur la lit comme un chemin RELATIF du site lui-même."""

from .socle import ASTValidationError


class PresentationMixin:
    """Ce que la spec dit de l'ÉCRAN, sans rien décider du visuel."""

    def _valider_ui_overrides(self):
        """Valide les entités et champs référencés par le bloc ``ui``."""
        self.ui_overrides = {}
        for override in self.ui_overrides_raw:
            entity = override["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'ui {entity}' block targets an entity that does not exist.")
            primary = override.get("primary")
            if primary and primary not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: 'ui {entity}' references 'primary: {primary}', which is not an attribute of '{entity}'."
                )
            order = override.get("order")
            if order:
                unknown = [field for field in order if field not in self.entities[entity]]
                if unknown:
                    raise ASTValidationError(
                        f"Structure: 'ui {entity}' references unknown fields in 'order': {unknown}."
                    )
            self.ui_overrides[entity] = {
                "theme": override.get("theme"), "primary": primary, "order": order,
            }

    def _valider_landing(self):
        """Normalise le contenu éditorial conservé pour le contrat frontend."""
        self.landing = None
        if self.landing_raw is None:
            return
        for obsolete in ("mode", "template"):
            if self.landing_raw.get(obsolete):
                print(f"⚠️  'landing / {obsolete}' has been obsolete since the pivot "
                      f"(point 41 in docs/design_decisions.md): monl no longer generates "
                      f"a home page — only 'brief' is passed to the frontend AI.")
        sections = []
        for section in self.landing_raw.get("sections") or []:
            title = (section.get("title") or "").strip()
            body = (section.get("body") or "").strip()
            if not title or not body:
                raise ValueError(
                    "SEMANTIC_ERROR: a 'section' in 'landing' requires a non-empty title AND body "
                    f"(found: title={title!r}, body={body!r})."
                )
            sections.append({"title": title, "body": body})
        faq = []
        for entry in self.landing_raw.get("faq") or []:
            question = (entry.get("question") or "").strip()
            answer = (entry.get("answer") or "").strip()
            if not question or not answer:
                raise ValueError(
                    "SEMANTIC_ERROR: a 'question' in 'landing' requires a non-empty question AND answer "
                    f"(found: question={question!r}, answer={answer!r})."
                )
            faq.append({"question": question, "answer": answer})
        self.landing = {"brief": self.landing_raw.get("brief"), "sections": sections,
                        "faq": faq, "links": self._valider_liens_sortants()}

    #: Ce qu'un navigateur sait ouvrir depuis un pied de page. `tel:` et
    #: `mailto:` en font partie : sur un site de commerce, ce sont souvent les
    #: DEUX liens qui comptent le plus.
    SCHEMES_DE_LIEN = ("https://", "http://", "mailto:", "tel:")

    def _valider_liens_sortants(self):
        """Normalise les liens du pied de page — ou refuse en l'expliquant.

        monl ne VÉRIFIE pas qu'une adresse répond : il ne fait aucun appel
        réseau, et le prétendre serait mentir (même frontière qu'au point 83
        pour les images distantes). Ce qu'il vérifie, c'est qu'un navigateur
        saura l'ouvrir — un « instagram.com/atelier » sans schéma est lu comme
        un chemin RELATIF et mène à une page inexistante du site lui-même.
        Un lien qui ne marche pas est pire qu'un lien absent : il se voit.
        """
        liens, libelles, adresses = [], set(), set()
        for entree in self.landing_raw.get("links") or []:
            label = (entree.get("label") or "").strip()
            url = (entree.get("url") or "").strip()
            if not label or not url:
                raise ValueError(
                    "SEMANTIC_ERROR: a 'link' in 'landing' requires a non-empty label AND "
                    f"URL (found: label={label!r}, URL={url!r})."
                )
            if not url.lower().startswith(self.SCHEMES_DE_LIEN):
                raise ValueError(
                    f"SEMANTIC_ERROR: link '{label}' has URL {url!r}, "
                    "which the browser will read as a path on the site itself. "
                    "Enter the full URL: "
                    + ", ".join(f"'{s}…'" for s in self.SCHEMES_DE_LIEN) + "."
                )
            repere = label.casefold()
            if repere in libelles:
                raise ValueError(
                    f"SEMANTIC_ERROR: two links in 'landing' have the label "
                    f"'{label}'. A footer that repeats a label makes it unclear "
                    "which link to follow."
                )
            if url in adresses:
                raise ValueError(
                    f"SEMANTIC_ERROR: URL {url!r} is declared twice "
                    "in 'landing'."
                )
            libelles.add(repere)
            adresses.add(url)
            liens.append({"label": label, "url": url})
        return liens
