"""Ce qu'une section doit CONTENIR pour ne pas être une coquille vide.

Le contrôle de complétude (point 118) vérifiait qu'un marqueur était PRÉSENT.
Un marqueur nomme une section, il ne prouve pas qu'il y a quelque chose
dedans : `<section data-monl-section="hero"></section>` passait tous les
contrôles, et le test du dépôt l'affirmait noir sur blanc. Un site fait de
huit balises vides était donc déclaré complet.

Ce module mesure la MATIÈRE d'une section. Trois principes, chacun né d'une
façon différente de se tromper :

1. **On ne demande jamais ce qui vient de l'API.** Un catalogue se remplit à
   l'exécution ; exiger des lignes de produits dans le HTML statique
   pousserait l'IA à en inventer — exactement ce que monl refuse partout
   ailleurs. On exige le contenant, le titre et l'état vide, jamais les
   données.
2. **Le seuil est PAR SECTION, pas global.** Un bandeau de conclusion tient
   en une phrase et un bouton ; lui réclamer deux cents caractères ferait
   produire du remplissage, c'est-à-dire l'inverse de la qualité visée.
3. **Une section déclarée dans la spec est jugée sur CE QU'ELLE DÉCLARE.**
   Demander cent caractères à une section dont l'auteur en a écrit cinquante
   ferait échouer une spec honnête.

Les pratiques de référence — cinq à huit blocs pour une page produit, un
menu/adresse/réservation pour un restaurant, travaux + à-propos + preuve +
contact pour un portfolio — disent toutes la même chose : le nombre de
sections ET la matière de chacune. Le nombre vit dans `ui_patterns.py`, la
matière ici.
"""

from __future__ import annotations

from html.parser import HTMLParser

#: Éléments qui ne se referment pas : les compter comme ouverts ferait fuir
#: la profondeur et avaler toute la fin du document dans la première section.
VOID_ELEMENTS = frozenset({
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
    "meta", "param", "source", "track", "wbr",
})

HEADINGS = frozenset({"h1", "h2", "h3", "h4"})
ACTIONS = frozenset({"a", "button"})
#: Le corps d'un script ou d'un style n'est pas du texte lu par un humain.
OPAQUE = frozenset({"script", "style", "template"})

#: Ce que chaque famille de section doit porter. `text` est un nombre de
#: caractères visibles, titre compris.
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
    # Le pied de page n'a PAS de titre : lui en imposer un ferait écrire
    # « Pied de page » en gros, ce qu'aucun site réel ne fait. Ce qu'il doit
    # porter, c'est de quoi partir ailleurs et de quoi savoir qui parle.
    "footer": {"text": 60, "action": True},
}

#: Une section déclarée par l'auteur : titre, et le texte qu'il a écrit.
DEFAULT_TEXT = 100


def rule_for(slug: str, declared_body_length: int | None = None) -> dict:
    """Règle de substance d'une section, par son slug.

    `declared_body_length` n'est fourni que pour une section écrite dans la
    spec : on n'exige alors jamais plus que ce que l'auteur a déclaré.
    """
    if slug in SUBSTANCE_RULES:
        return dict(SUBSTANCE_RULES[slug])
    seuil = DEFAULT_TEXT
    if declared_body_length is not None:
        seuil = max(20, min(DEFAULT_TEXT, declared_body_length))
    return {"heading": True, "text": seuil}


class _Sonde(HTMLParser):
    """Relève la matière portée par chaque élément marqué.

    Les sections peuvent s'imbriquer (une section déclarée vit à l'intérieur
    du bloc éditorial), d'où une PILE : ce qu'on rencontre est compté pour
    toutes les sections ouvertes, pas seulement la dernière.
    """

    def __init__(self, markers):
        super().__init__(convert_charrefs=True)
        self._attendus = {}
        for marker in markers:
            nom, _, valeur = marker.partition("=")
            self._attendus.setdefault(nom.strip(), set()).add(valeur.strip().strip('"'))
        self.releves: dict[str, dict] = {}
        self._pile: list[tuple[str, dict | None]] = []
        self._opaque = 0

    # -- suivi de profondeur ------------------------------------------------
    # La pile porte le NOM de la balise, pas seulement le relevé : une balise
    # jamais refermée — un `<p>` sans `</p>` est du HTML5 parfaitement légal —
    # ferait sinon fuir la profondeur, et la section compterait le texte de
    # tout ce qui la suit. Une barrière qui compte le texte du voisin ne
    # refuse plus rien.
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
        # Balise fermante orpheline : on l'ignore plutôt que de dépiler au
        # hasard, ce qui refermerait une section qui n'a rien demandé.

    def handle_data(self, data):
        if self._opaque:
            return
        texte = " ".join(data.split())
        if not texte:
            return
        for _tag, releve in self._pile:
            if releve is not None:
                releve["text"] = (releve["text"] + " " + texte).strip()

    # -- relevé -------------------------------------------------------------
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
    """Refuse toute section marquée qui ne porte pas sa matière.

    Une section ABSENTE n'est pas signalée ici : c'est déjà le rôle du
    contrôle de présence, et le dire deux fois brouillerait le rapport.
    """
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
            manques.append("un titre (<h1> à <h4>)")
        if regle.get("action") and not releve["action"]:
            manques.append("une action (<a> ou <button>)")
        if regle.get("form") and not releve["form"]:
            manques.append("un <form>")
        seuil = regle.get("text")
        if seuil:
            longueur = len(releve["text"])
            if longueur < seuil:
                manques.append(
                    f"du texte lisible ({longueur} caractères sur {seuil} attendus)"
                )
        if manques:
            errors.append(
                f"section vide ou incomplète — « {nom} » : il manque "
                + ", ".join(manques)
                + ". Une section marquée doit porter sa matière, pas seulement son nom."
            )
    return errors
