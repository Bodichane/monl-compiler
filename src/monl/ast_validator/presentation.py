"""What the spec says about the SCREEN, without deciding anything visual.

Point 72: the compiler decides NOTHING — neither palette nor typography.
It checks the shape of `ui`, of `landing` and of the footer links (brick
30, point 144), whose address must carry a scheme, otherwise the browser
reads it as a RELATIVE path on the site itself."""

from .base import ASTValidationError


class PresentationMixin:
    """What the spec says about the SCREEN, without deciding anything visual."""

    def _validate_ui_overrides(self):
        """Validates the entities and fields referenced by the ``ui`` block."""
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

    def _validate_landing(self):
        """Normalizes the editorial content kept for the frontend contract."""
        self.landing = None
        if self.landing_raw is None:
            return
        for obsolete in ("mode", "template"):
            if self.landing_raw.get(obsolete):
                print(f"⚠️  'landing / {obsolete}' has been obsolete since the pivot "
                      f"(point 41 in docs/design_decisions.md): monl no longer generates "
                      f"a home page — only 'brief' is passed to the frontend AI.")
        sections = self._pairs_editorial("sections", "section", "title", "body")
        faq = self._pairs_editorial("faq", "question", "question", "answer")
        self.landing = {"brief": self.landing_raw.get("brief"), "sections": sections,
                        "faq": faq, "links": self._validate_links_outgoing()}

    def _pairs_editorial(self, key, name, first, second):
        """Sections and questions have the same shape: two non-empty texts. A single
        walk, hence a single refusal message to keep right."""
        pairs = []
        for entry in self.landing_raw.get(key) or []:
            a = (entry.get(first) or "").strip()
            b = (entry.get(second) or "").strip()
            if not a or not b:
                raise ValueError(
                    f"SEMANTIC_ERROR: a '{name}' in 'landing' requires a non-empty "
                    f"{first} AND {second} (found: {first}={a!r}, {second}={b!r})."
                )
            pairs.append({first: a, second: b})
        return pairs

    #: What a browser can open from a footer. `tel:` and `mailto:` are among
    #: them: on a commerce site, they are often the TWO links that matter
    #: most.
    SCHEMES_OF_LINK = ("https://", "http://", "mailto:", "tel:")

    def _validate_links_outgoing(self):
        """Normalizes the footer links — or refuses and explains why.

        monl does NOT CHECK that an address responds: it makes no network call,
        and claiming otherwise would be lying (same boundary as point 83 for
        remote images). What it checks is that a browser will be able to open it
        — an "instagram.com/atelier" without a scheme is read as a RELATIVE path
        and leads to a nonexistent page on the site itself. A link that does not
        work is worse than a missing link: it shows."""
        links, labels, addresses = [], set(), set()
        for entry in self.landing_raw.get("links") or []:
            label = (entry.get("label") or "").strip()
            url = (entry.get("url") or "").strip()
            if not label or not url:
                raise ValueError(
                    "SEMANTIC_ERROR: a 'link' in 'landing' requires a non-empty label AND "
                    f"URL (found: label={label!r}, URL={url!r})."
                )
            if not url.lower().startswith(self.SCHEMES_OF_LINK):
                raise ValueError(
                    f"SEMANTIC_ERROR: link '{label}' has URL {url!r}, "
                    "which the browser will read as a path on the site itself. "
                    "Enter the full URL: "
                    + ", ".join(f"'{s}…'" for s in self.SCHEMES_OF_LINK) + "."
                )
            marker = label.casefold()
            if marker in labels:
                raise ValueError(
                    f"SEMANTIC_ERROR: two links in 'landing' have the label "
                    f"'{label}'. A footer that repeats a label makes it unclear "
                    "which link to follow."
                )
            if url in addresses:
                raise ValueError(
                    f"SEMANTIC_ERROR: URL {url!r} is declared twice "
                    "in 'landing'."
                )
            labels.add(marker)
            addresses.add(url)
            links.append({"label": label, "url": url})
        return links
