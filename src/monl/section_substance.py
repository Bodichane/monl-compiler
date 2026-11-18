"""What a section must CONTAIN so as not to be an empty shell.

The completeness check (point 118) verified that a marker was PRESENT. A
marker names a section, it does not prove there is something in it:
`<section data-monl-section="hero"></section>` passed every check, and the
repository's test stated it in black and white. A site made of eight
empty tags was therefore declared complete.

This module measures a section's SUBSTANCE. Three principles, each born
from a different way of getting it wrong:

1. **Never ask for what comes from the API.** A catalog fills at runtime;
   requiring product rows in the static HTML would push the AI to invent
   some — exactly what monl refuses everywhere else. We require the
   container, the title and the empty state, never the data.
2. **The threshold is PER SECTION, not global.** A closing banner fits in
   one sentence and a button; asking two hundred characters of it would
   produce filler, that is, the opposite of the quality sought.
3. **A section declared in the spec is judged on WHAT IT DECLARES.**
   Asking a hundred characters of a section whose author wrote fifty would
   make an honest spec fail.

The reference practices — five to eight blocks for a product page, a
menu/address/booking for a restaurant, work + about + proof + contact for
a portfolio — all say the same thing: the number of sections AND the
substance of each. The number lives in `ui_patterns.py`, the substance
here."""

from __future__ import annotations

from html.parser import HTMLParser

#: Elements that are never closed: counting them as open would make the depth
#: leak and swallow the whole end of the document into the first section.
VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

HEADINGS = frozenset({"h1", "h2", "h3", "h4"})
ACTIONS = frozenset({"a", "button"})
#: The body of a script or a style is not text a human reads.
OPAQUE = frozenset({"script", "style", "template"})

#: What each family of section must carry. `text` is a number of visible
#: characters, title included.
SUBSTANCE_RULES = {
    "hero": {"heading": True, "text": 80, "action": True},
    "catalogue": {"heading": True, "text": 40},
    "panier": {"heading": True},
    "workspace": {"heading": True, "action": True},
    "editorial": {"heading": True, "text": 200},
    "trust": {"heading": True, "text": 120},
    "faq": {"heading": True, "text": 150},
    "contact": {"heading": True, "form": True},
    "booking": {"heading": True, "form": True},
    "closing-cta": {"heading": True, "action": True},
    # The footer has NO title: imposing one would make people write "Footer" in
    # large type, which no real site does. What it must carry is a way to go
    # elsewhere and a way to know who is speaking.
    "footer": {"text": 60, "action": True},
}

#: A section declared by the author: title, and the text they wrote.
DEFAULT_TEXT = 100


def rule_for(slug: str, declared_body_length: int | None = None) -> dict:
    """A section's substance rule, by its slug.

    `declared_body_length` is supplied only for a section written in the
    spec: we then never require more than what the author declared."""
    if slug in SUBSTANCE_RULES:
        return dict(SUBSTANCE_RULES[slug])
    seuil = DEFAULT_TEXT
    if declared_body_length is not None:
        seuil = max(20, min(DEFAULT_TEXT, declared_body_length))
    return {"heading": True, "text": seuil}


class _Sonde(HTMLParser):
    """Records the substance carried by each marked element.

    Sections can nest (a declared section lives inside the editorial block),
    hence a STACK: what is met is counted for every open section, not only the
    last one."""

    def __init__(self, markers):
        super().__init__(convert_charrefs=True)
        self._attendus = {}
        for marker in markers:
            nom, _, valeur = marker.partition("=")
            self._attendus.setdefault(nom.strip(), set()).add(valeur.strip().strip('"'))
        self.releves: dict[str, dict] = {}
        self._pile: list[tuple[str, dict | None]] = []
        self._opaque = 0

    # -- depth tracking ------------------------------------------------------
    # The stack carries the tag's NAME, not only the record: a tag never closed
    # — a `<p>` without `</p>` is perfectly legal HTML5 — would otherwise make
    # the depth leak, and the section would count the text of everything that
    # follows it. A barrier that counts its neighbor's text no longer refuses
    # anything.
    def handle_starttag(self, tag, attrs):
        if tag in OPAQUE:
            self._opaque += 1
        releve = None
        aplat = dict(attrs)
        for nom, valeurs in self._attendus.items():
            valeur = aplat.get(nom)
            if valeur is not None and valeur in valeurs:
                cle = f'{nom}="{valeur}"'
                releve = self.releves.setdefault(
                    cle, {"text": "", "heading": False, "action": False, "form": False}
                )
                break
        if tag not in VOID_ELEMENTS:
            self._pile.append((tag, releve))
        self._noter(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID_ELEMENTS and self._pile:
            self._pile.pop()
        if tag in OPAQUE:
            self._opaque = max(0, self._opaque - 1)

    def handle_endtag(self, tag):
        if tag in OPAQUE:
            self._opaque = max(0, self._opaque - 1)
        if tag in VOID_ELEMENTS:
            return
        for rang in range(len(self._pile) - 1, -1, -1):
            if self._pile[rang][0] == tag:
                del self._pile[rang:]
                return
        # Orphan closing tag: ignore it rather than pop at random, which would
        # close a section that asked for nothing.

    def handle_data(self, data):
        if self._opaque:
            return
        texte = " ".join(data.split())
        if not texte:
            return
        for _tag, releve in self._pile:
            if releve is not None:
                releve["text"] = (releve["text"] + " " + texte).strip()

    # -- recording -----------------------------------------------------------
    def _noter(self, tag):
        if tag in HEADINGS:
            cle = "heading"
        elif tag in ACTIONS:
            cle = "action"
        elif tag == "form":
            cle = "form"
        else:
            return
        for _tag, releve in self._pile:
            if releve is not None:
                releve[cle] = True


def substance_errors(html: str, rules: dict[str, dict]) -> list[str]:
    """Refuses any marked section that does not carry its substance.

    A MISSING section is not reported here: that is already the job of the
    presence check, and saying it twice would muddle the report."""
    if not rules:
        return []
    sonde = _Sonde(rules)
    sonde.feed(html)
    sonde.close()
    errors = []
    for marker, regle in rules.items():
        releve = sonde.releves.get(marker)
        if releve is None:
            continue
        nom = marker.partition("=")[2].strip('"') or marker
        manques = []
        if regle.get("heading") and not releve["heading"]:
            manques.append("a heading (<h1> to <h4>)")
        if regle.get("action") and not releve["action"]:
            manques.append("an action (<a> or <button>)")
        if regle.get("form") and not releve["form"]:
            manques.append("a <form>")
        seuil = regle.get("text")
        if seuil:
            longueur = len(releve["text"])
            if longueur < seuil:
                manques.append(
                f"readable text ({longueur} of {seuil} characters required)"
                )
        if manques:
            errors.append(
                f"empty or incomplete section — ‘{nom}’: missing "
                + ", ".join(manques)
                + ". A marked section must contain substantive content, not just its name."
            )
    return errors
