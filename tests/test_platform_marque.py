"""L'identité, vérifiée plutôt qu'espérée.

`theme.py` affirme dans son propre docstring que les contrastes tiennent WCAG
AA. Une affirmation dans un commentaire ne protège de rien : c'est exactement
ce que le point 85 reproche aux règles qui ne produisent rien. Ce fichier
calcule les ratios depuis les variables réellement déclarées, et refuse les
couleurs écrites en dur ailleurs que dans la feuille.

Ce qu'il a fallu pour l'écrire : la refonte d'identité précédente avait laissé
CINQ verts de l'ancienne palette dans `console.py` (bordure du terminal,
points, texte des commentaires, bordure du champ de saisie). Ils ont traversé
un changement complet de palette sans que rien ne le dise, parce qu'une
couleur en dur n'appartient à aucun thème et ne casse jamais.
"""

import pathlib
import re

import pytest

from monl_platform import theme

PAQUET = pathlib.Path(theme.__file__).parent
COULEUR = re.compile(r"#[0-9a-fA-F]{6}\b")


def _luminance(hexa: str) -> float:
    hexa = hexa.lstrip("#")
    canaux = [int(hexa[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    lineaire = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in canaux]
    return 0.2126 * lineaire[0] + 0.7152 * lineaire[1] + 0.0722 * lineaire[2]


def contraste(avant: str, arriere: str) -> float:
    clair, sombre = sorted((_luminance(avant), _luminance(arriere)), reverse=True)
    return (clair + 0.05) / (sombre + 0.05)


def _palette(bloc: str) -> dict[str, str]:
    """Les variables d'un bloc de déclarations CSS."""
    return {nom: valeur for nom, valeur in
            re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", bloc)}


def _blocs() -> dict[str, dict[str, str]]:
    css = theme.CSS
    racine = css[css.index(":root {"):css.index("@media (prefers-color-scheme: dark)")]
    sombre_debut = css.index(':root[data-theme="dark"] {')
    sombre = css[sombre_debut:css.index("}", sombre_debut)]
    clair = _palette(racine)
    # Le thème sombre ne redéclare que ce qui change : le reste est hérité.
    return {"clair": clair, "sombre": {**clair, **_palette(sombre)}}


# Les couples qui portent du texte ou délimitent un contrôle. Un couple absent
# de cette liste n'est pas « sûr », il n'est pas mesuré — l'ajouter est le
# geste attendu quand on ajoute un rôle de couleur.
COUPLES_TEXTE = [
    ("ink", "bg"), ("ink", "surface"), ("ink", "surface-2"),
    ("muted", "bg"), ("muted", "surface"), ("muted", "surface-2"),
    ("brand", "bg"), ("brand", "surface"), ("brand", "soft"),
    ("on-brand", "brand"),
    ("code-ink", "code-bg"), ("code-accent", "code-bg"), ("code-muted", "code-bg"),
    ("danger", "danger-bg"),
]
COUPLES_CONTROLE = [("line-strong", "bg"), ("line-strong", "surface")]


@pytest.mark.parametrize("theme_nom", ["clair", "sombre"])
def test_le_texte_tient_le_contraste_wcag_aa(theme_nom):
    palette = _blocs()[theme_nom]
    for avant, arriere in COUPLES_TEXTE:
        assert avant in palette and arriere in palette, f"{avant}/{arriere} absent"
        ratio = contraste(palette[avant], palette[arriere])
        assert ratio >= 4.5, (
            f"[{theme_nom}] {avant} ({palette[avant]}) sur {arriere} "
            f"({palette[arriere]}) : {ratio:.2f}:1, il faut 4.5")


@pytest.mark.parametrize("theme_nom", ["clair", "sombre"])
def test_les_controles_se_distinguent_du_fond(theme_nom):
    """WCAG 1.4.11 : un composant d'interface se délimite à 3:1. C'est la
    raison d'être de `--line-strong` — `--line`, lui, ne sépare que des cartes
    et n'a pas à tenir ce seuil."""
    palette = _blocs()[theme_nom]
    for avant, arriere in COUPLES_CONTROLE:
        ratio = contraste(palette[avant], palette[arriere])
        assert ratio >= 3.0, (
            f"[{theme_nom}] bordure de contrôle {palette[avant]} sur "
            f"{palette[arriere]} : {ratio:.2f}:1, il faut 3.0")


@pytest.mark.parametrize("theme_nom", ["clair", "sombre"])
def test_les_deux_themes_declarent_les_memes_roles(theme_nom):
    """Un rôle défini d'un seul côté laisse l'autre thème hériter d'une
    couleur pensée pour le premier — c'est ainsi qu'un fond clair se retrouve
    sur une page sombre."""
    blocs = _blocs()
    manquants = set(blocs["clair"]) - set(blocs["sombre"])
    assert not manquants, f"rôles absents du thème sombre : {sorted(manquants)}"


def test_aucune_couleur_en_dur_hors_de_la_feuille():
    """La refonte précédente a laissé cinq verts dans `console.py`. Une couleur
    en dur n'appartient à aucun thème : elle survit à tout changement de
    palette sans jamais échouer."""
    fautifs = {}
    for module in sorted(PAQUET.glob("*.py")):
        if module.name in {"theme.py", "theme_fragments.py"}:
            continue
        trouvees = COULEUR.findall(module.read_text(encoding="utf-8"))
        if trouvees:
            fautifs[module.name] = sorted(set(trouvees))
    assert not fautifs, (
        f"couleurs écrites en dur hors de theme.py : {fautifs} — "
        "employez une variable CSS (var(--brand), var(--code-muted)…)")


def test_le_signe_de_la_page_suit_la_couleur_du_texte():
    """Le défaut d'origine : un signe qui portait son propre fond disparaissait
    sur le thème sombre. En `currentColor`, il ne le peut plus."""
    assert "currentColor" in theme.LOGO_MARK
    assert "<text" not in theme.LOGO_MARK, "un tracé ne dépend d'aucune police"
    # Aucune couleur figée : ni fond, ni trait.
    assert not COULEUR.findall(theme.LOGO_MARK), theme.LOGO_MARK


def test_le_favicon_porte_ses_couleurs_car_il_na_rien_a_heriter():
    """La seule exception, et elle est justifiée : un onglet de navigateur
    n'offre aucune couleur héritée, et en attend un fond."""
    assert "<text" not in theme.FAVICON
    assert "currentColor" not in theme.FAVICON
    # Écrit SANS citer de couleur : la version précédente attendait `#ffb020`
    # en dur et n'aurait rien vu d'un favicon repeint dans une teinte
    # illisible, tant que ce littéral y figurait. Ce qui compte est le
    # CONTRASTE entre la pastille et ses tracés — c'est vrai de toute palette.
    couleurs = COULEUR.findall(theme.FAVICON)
    assert len(couleurs) >= 2, f"il faut un fond et au moins un tracé : {couleurs}"
    fond, traces = couleurs[0], couleurs[1:]
    for trace in traces:
        ratio = contraste(trace, fond)
        assert ratio >= 4.5, f"tracé {trace} sur {fond} : {ratio:.2f}:1"


def test_le_fichier_de_marque_et_la_feuille_dessinent_le_meme_signe():
    """Deux sources finiraient par diverger, et c'est `docs/BRAND.md` qui
    renvoie vers le fichier : il doit montrer ce que la page sert vraiment."""
    svg = (pathlib.Path(theme.__file__).parents[2] / "docs/brand/monl-mark.svg"
           ).read_text(encoding="utf-8")
    traces = re.findall(r'd="([^"]+)"', theme.LOGO_MARK)
    assert traces, "le signe ne contient plus aucun tracé"
    for trace in traces:
        assert trace in svg, f"tracé absent de docs/brand/monl-mark.svg : {trace}"


# ---------------------------------------------------------------------------
# Cibles tactiles
# ---------------------------------------------------------------------------

# Sélecteur → module qui le déclare. La liste est explicite plutôt que
# devinée : un test qui cherche « tout ce qui ressemble à un bouton » finit
# par mesurer des conteneurs, et un test qui se trompe sur une page correcte
# apprend à ne plus lire les tests (point 57).
CIBLES = [
    (".navlinks a", "theme_fragments.py"),
    (".primary, .secondary, .ghost, .nav-cta", "theme_fragments.py"),
    (".icon-btn", "theme_fragments.py"),
    (".copy", "theme_fragments.py"),
    (".brand", "theme_fragments.py"),
    (".toc a", "guide_template.py"),
    (".rail button", "console_template.py"),
    (".auth-tabs button", "account.py"),
    # Ajoutés APRÈS mesure au navigateur : la liste ne les contenait pas, donc
    # le test était vert pendant que treize liens de pied de page rendaient
    # 22,4 px sur CHAQUE page. Une garantie ne couvre que ce qu'on y inscrit.
    (".footer nav a", "theme_fragments.py"),
    (".service-status", "theme_fragments.py"),
    (".docs-nav a", "docs_page.py"),
]
MINIMUM = 44


def _hauteur_declaree(source: str, selecteur: str) -> int | None:
    """La `min-height` (ou `height`) du bloc qui suit ce sélecteur."""
    debut = source.find(selecteur + " {")
    if debut == -1:
        debut = source.find(selecteur + "{")
    if debut == -1:
        return None
    bloc = source[debut:source.find("}", debut)]
    trouve = re.search(r"(?:min-)?height:\s*(\d+)px", bloc)
    return int(trouve.group(1)) if trouve else None


@pytest.mark.parametrize("selecteur,module", CIBLES)
def test_les_cibles_tactiles_font_au_moins_44px(selecteur, module):
    """WCAG 2.5.5 : une cible se rate au doigt sous 44 px. Un lien de
    navigation raté n'échoue pas — il ouvre la page d'à côté, ce qui est pire
    qu'un clic sans effet."""
    source = (PAQUET / module).read_text(encoding="utf-8")
    hauteur = _hauteur_declaree(source, selecteur)
    assert hauteur is not None, (
        f"`{selecteur}` ne déclare plus de hauteur dans {module} — "
        "si la règle a été renommée, mettez CIBLES à jour plutôt que de "
        "supprimer la garantie")
    assert hauteur >= MINIMUM, (
        f"`{selecteur}` ({module}) : {hauteur}px, il en faut {MINIMUM}")


def test_le_wordmark_suit_le_theme_au_lieu_de_porter_son_fond():
    """Le défaut mesuré : en `<img>`, la bannière du logo garde son fond
    #2e2b25 quel que soit le thème — soit 1,29:1 contre la page sombre, un
    logo littéralement invisible dans l'en-tête. Un raster ne peut pas suivre
    un thème ; c'est la raison du SVG en ligne, pas une préférence.

    Le test porte donc sur le MOYEN autant que sur le résultat : revenir à une
    balise `<img>` reperdrait la garantie sans qu'aucune couleur ne change."""
    assert "<img" not in theme.WORDMARK, (
        "un raster ne suit aucun thème — le wordmark doit rester en SVG inline")
    assert "currentColor" in theme.WORDMARK, "la bannière doit hériter du texte"
    assert "var(--bg)" in theme.WORDMARK, "les lettres doivent creuser dans le fond"
    assert not COULEUR.findall(theme.WORDMARK), (
        f"couleur figée dans le wordmark : {COULEUR.findall(theme.WORDMARK)}")
    assert theme.WORDMARK in theme.page(title="t", description="d", body=""), (
        "le wordmark n'est pas servi dans la page")


@pytest.mark.parametrize("theme_nom", ["clair", "sombre"])
def test_le_wordmark_reste_lisible_dans_les_deux_themes(theme_nom):
    """La bannière prend `--ink`, les lettres `--bg` : l'inversion est
    automatique, mais elle n'est vraie que si les deux couples tiennent."""
    palette = _blocs()[theme_nom]
    banniere = contraste(palette["ink"], palette["bg"])
    assert banniere >= 4.5, (
        f"[{theme_nom}] bannière {palette['ink']} sur page {palette['bg']} : "
        f"{banniere:.2f}:1")


def test_les_traces_de_marque_ne_portent_aucune_couleur():
    """`brand.py` est de la DONNÉE : les couleurs se composent dans theme.py.

    Exempter un fichier de plus de la règle « aucune couleur en dur » élargirait
    la porte que `test_aucune_couleur_en_dur_hors_de_la_feuille` ferme — c'est
    pourquoi les tracés en sortent au lieu d'y entrer."""
    from monl_platform import brand
    source = pathlib.Path(brand.__file__).read_text(encoding="utf-8")
    assert not COULEUR.findall(source), COULEUR.findall(source)
    for nom in ("BANNIERE", "LETTRES", "MARQUE_M"):
        assert getattr(brand, nom).startswith("M"), f"{nom} n'est pas un tracé"


def test_les_balises_de_partage_ninventent_aucune_adresse(monkeypatch):
    """Une image de partage doit être ABSOLUE pour qu'un robot la récupère.
    La déduire de l'en-tête `Host` la ferait pointer où un tiers veut — même
    frontière qu'au point 145 pour l'adresse de retour OAuth. Sans URL publique
    déclarée, monl se tait plutôt que de deviner."""
    monkeypatch.delenv("MONL_PLATFORM_PUBLIC_URL", raising=False)
    muet = theme.page(title="t", description="d", body="")
    assert "og:image" not in muet, "une image de partage a été inventée"
    assert 'name="twitter:card" content="summary"' in muet

    monkeypatch.setenv("MONL_PLATFORM_PUBLIC_URL", "https://exemple.test/")
    parlant = theme.page(title="t", description="d", body="")
    assert 'content="https://exemple.test/brand/monl-social.png"' in parlant
    assert 'content="summary_large_image"' in parlant
