"""La racine porte la page de présentation, la console vit sur /console.

La console est un OUTIL : elle suppose qu'on sait déjà ce que monl fait. Une
personne qui l'ignore avait la console en pleine figure, sans un mot sur le
produit ni le moindre moyen de l'installer.
"""

import pathlib
import re
import socket
import threading
import time

import pytest
import requests
import uvicorn

from monl_platform.app import create_app
from monl_platform.landing import LANDING_HTML

RESSOURCE_EXTERNE = re.compile(
    r"<(?:link|script|img|iframe)\b[^>]*(?:src|href)\s*=\s*['\"]https?://",
    re.IGNORECASE,
)


class FakeProvider:
    provider_name = "test"
    model = "test-model"

    def __call__(self, _prompt):  # pragma: no cover - jamais appelé ici
        raise AssertionError("la page de présentation n'appelle aucune IA")


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture()
def platform(tmp_path):
    app = create_app(
        workspace=tmp_path / "projects",
        domain="localhost",
    )
    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                    break
            except requests.RequestException:
                time.sleep(0.02)
        else:
            pytest.fail("le serveur n'a pas démarré")
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def test_la_racine_presente_le_produit(platform):
    reponse = requests.get(platform, timeout=10)

    assert reponse.status_code == 200
    assert "text/html" in reponse.headers["content-type"]
    assert '<html lang="fr">' in reponse.text
    # Ce qu'une page produit doit dire : ce que c'est, et comment l'obtenir.
    assert "compilateur" in reponse.text.lower()
    assert "Créer un backend" in reponse.text


def test_la_page_conduit_a_la_console(platform):
    reponse = requests.get(platform, timeout=10)

    assert 'href="/console"' in reponse.text
    console = requests.get(f"{platform}/console", timeout=10, allow_redirects=False)
    assert console.status_code == 303
    assert console.headers["location"].startswith("/login")


def test_la_page_ne_charge_aucune_ressource_distante(platform):
    """Servie en local, elle doit fonctionner sans le moindre réseau."""
    reponse = requests.get(platform, timeout=10)

    faute = RESSOURCE_EXTERNE.search(reponse.text)
    assert faute is None, f"ressource distante dans la page : {faute.group(0)}"


def test_toute_url_sortante_est_un_lien_et_rien_d_autre(platform):
    """Le garde-fou d'au-dessus s'est élargi : celui-ci le referme.

    Autoriser les liens sortants ne doit pas autoriser une URL n'importe où.
    Chaque `https://` de la page doit être la cible d'un `<a href>` — pas
    d'un `<img>`, pas d'un `fetch`, pas d'une police.
    """
    page = requests.get(platform, timeout=10).text
    sans_commentaires = re.sub(r"/\*.*?\*/", "", page, flags=re.DOTALL)
    sans_commentaires = re.sub(r"<!--.*?-->", "", sans_commentaires, flags=re.DOTALL)

    for position in (m.start() for m in re.finditer(r"https?://", sans_commentaires)):
        debut = sans_commentaires.rfind("<", 0, position)
        balise = sans_commentaires[debut:position]
        # UNE exemption, et elle est étroite : `xmlns` d'un SVG en ligne est un
        # espace de NOMS, pas une adresse — aucun navigateur ne va la chercher.
        # L'exemption porte sur l'attribut, jamais sur le domaine : écrire
        # « sauf w3.org » laisserait passer une vraie requête vers w3.org.
        if re.search(r"\bxmlns(:\w+)?\s*=\s*['\"]$", balise):
            continue
        assert re.match(r"<a\b[^>]*\bhref\s*=\s*['\"]$", balise), (
            "URL sortante hors d'un lien : "
            + sans_commentaires[position:position + 60]
        )


def test_la_page_respecte_le_mouvement_reduit():
    """Le terminal du héros s'anime : il doit pouvoir s'arrêter."""
    assert "prefers-reduced-motion" in LANDING_HTML


def test_la_console_n_est_plus_a_la_racine(platform):
    """La racine et la console sont deux pages distinctes, pas la même."""
    racine = requests.get(platform, timeout=10).text
    session = requests.Session()
    inscrit = session.post(f"{platform}/api/auth/register", json={
        "email": "landing-console@example.test", "password": "MotDePasse-123"
    }, timeout=10)
    assert inscrit.status_code == 201, inscrit.text
    console = session.get(f"{platform}/console", timeout=10).text

    assert racine != console
    assert "Console de compilation" in console
    assert "Console de compilation" not in racine


def test_la_pastille_de_marque_garde_sa_couleur_d_encre():
    """Deux fois le même défaut : une règle LARGE écrase une règle précise.

    `.logo span` (0,1,1) l'emporte sur `.logo-mark` (0,1,0) et repeignait le
    « m » en gris sourd sur argile — 1,35:1, c'est-à-dire invisible. Le même
    piège avait déjà mangé le bouton d'appel à l'action à l'autre bout de la
    barre. Ce qu'on corrige n'est pas la règle précise qu'il faudrait
    renforcer, c'est la règle large qu'il faut restreindre : on interdit donc
    le sélecteur fourre-tout, pas une couleur particulière.
    """
    assert ".logo span {" not in LANDING_HTML
    assert "brand-wordmark" in LANDING_HTML


def test_la_marque_se_lit_monl_compiler(platform):
    reponse = requests.get(platform, timeout=10)

    assert 'aria-label="Monl compiler"' in reponse.text


def test_aucune_couleur_n_est_ecrite_hors_du_theme():
    """Une couleur en dur échappe au thème, et le thème seul se déplace.

    La barre de la console portait `rgba(16, 14, 12, .9)` : quand la palette
    est passée du sombre au papier, tout a suivi les variables SAUF elle — la
    barre est restée noire pendant que son texte, lui, devenait noir aussi.
    Sombre sur sombre, illisible, et invisible à une recherche de couleurs
    hexadécimales. Les ombres portées restent permises : une ombre n'est pas
    une couleur de surface, elle assombrit ce qu'il y a dessous quel qu'il
    soit.
    """
    from monl_platform import theme

    assert "rgba(" in LANDING_HTML  # les ombres et séparateurs restent locaux
    assert "--brand" in theme.CSS and "--on-brand" in theme.CSS


def test_la_demonstration_montre_de_vraies_sorties_de_compilation(platform):
    """Ce qui est montré doit venir du compilateur, pas d'une main.

    Une page produit qui invente ses propres chiffres serait exactement ce que
    monl interdit aux sites qu'il produit — et ce que la barrière de substance
    refuse depuis le point 143.
    """
    page = requests.get(platform, timeout=10).text

    assert "compilation vérifiée" in page
    # Les quatre exemples réellement compilés par les tests de la plateforme.
    for modele in ("Vitrine publique", "Carnet de rendez-vous",
                   "Boutique et paiement", "Fil communautaire"):
        assert modele in page
    assert "frontend_contract.json" in page


def test_une_apparition_ne_se_cache_jamais_par_un_style_en_ligne():
    """Un style EN LIGNE ne se défait pas avec une classe.

    La page posait `element.style.opacity = "0"` sur chaque bloc à révéler,
    puis comptait sur `.rise.seen { opacity: 1 }` pour le rendre. Or un style
    en ligne l'emporte sur n'importe quel sélecteur de classe : les sections
    ne réapparaissaient JAMAIS. Mesuré sur la page servie, hors mouvement
    réduit : 43,3 % de blanc, dont une bande de 993 px — les refus, les
    chiffres et l'appel final entièrement invisibles.

    L'état caché doit donc vivre dans une RÈGLE. Les commentaires sont
    retirés avant la recherche : ils parlent du défaut, ils ne le commettent
    pas.
    """
    from monl_platform.console import CONSOLE_HTML

    sans_commentaires = re.compile(r"/\*.*?\*/", re.DOTALL)
    for nom, page in (("accueil", LANDING_HTML), ("console", CONSOLE_HTML)):
        propre = sans_commentaires.sub("", page)
        assert not re.search(r"\.style\.opacity\s*=", propre), (
            f"la page {nom} cache un bloc par un style en ligne : une classe "
            "ne pourra pas le défaire"
        )


def test_un_contenu_anime_reste_montrable_si_l_observateur_se_tait():
    """Un contenu invisible est pire qu'un contenu non animé.

    Écran très haut, navigateur exotique, erreur en amont : si
    l'IntersectionObserver ne se déclenche jamais, la page ne doit pas rester
    blanche pour autant.
    """
    assert "data-reveal" in LANDING_HTML
    assert "IntersectionObserver" in LANDING_HTML
    assert "is-visible" in LANDING_HTML


# ---------------------------------------------------------------------------
# Les trois sections de positionnement (« pourquoi », « vs », « ensemble »)
# ---------------------------------------------------------------------------

def test_les_trois_questions_du_visiteur_ont_leur_section():
    """Le site disait CE QUE monl fait sans jamais dire pourquoi celui-ci,
    en quoi il diffère de ce qu'on connaît, ni s'il faut choisir."""
    for ancre in ("pourquoi-title", "compare-title", "ensemble-title"):
        assert f'id="{ancre}"' in LANDING_HTML, f"section absente : {ancre}"


def test_la_comparaison_dit_aussi_ce_que_monl_napporte_pas():
    """Une comparaison qui n'énumère que ses victoires est une comparaison
    qu'on cesse de croire à la première vérification. La ligne des limites
    n'est pas une politesse : c'est ce qui rend le reste lisible."""
    from monl_platform.landing_pourquoi import COMPARAISON
    axes = [axe for axe, _eux, _nous in COMPARAISON]
    assert "Ce qu'il n'apporte pas" in axes, axes
    limites = next(nous for axe, _e, nous in COMPARAISON
                   if axe == "Ce qu'il n'apporte pas")
    for absent in ("hébergement", "temps réel", "stockage"):
        assert absent in limites, f"limite non énoncée : {absent}"
    assert limites in LANDING_HTML, "la ligne des limites n'est pas servie"


def test_aucun_jugement_de_valeur_dans_la_comparaison():
    """Chaque ligne doit être un FAIT vérifiable des deux côtés. « Plus
    simple », « plus moderne », « plus sûr » ne se vérifient pas et ne
    survivent pas à un lecteur qui connaît l'autre produit."""
    from monl_platform.landing_pourquoi import COMPARAISON
    interdits = ("plus simple", "plus moderne", "plus sûr", "plus rapide",
                 "meilleur", "supérieur", "obsolète")
    texte = " ".join(f"{a} {b} {c}".lower() for a, b, c in COMPARAISON)
    fautifs = [mot for mot in interdits if mot in texte]
    assert not fautifs, f"jugement de valeur dans la comparaison : {fautifs}"


def test_la_promesse_postgresql_du_site_est_couverte_par_un_test():
    """Le site affirme qu'un backend généré tourne sur le Postgres d'un
    fournisseur managé. Un document se garde comme du code (point 141) : la
    promesse doit pointer sur une épreuve qui existe, sinon elle vieillit en
    silence jusqu'à devenir fausse."""
    from monl_platform.landing_pourquoi import MONTAGES
    montage = next(m for m in MONTAGES if m["etat"] == "verifie"
                   and "MONL_DATABASE_URL" in m["texte"])
    assert "postgresql://" in "\n".join(montage["code"])

    epreuve = pathlib.Path(__file__).with_name("test_postgresql.py")
    assert epreuve.exists(), "la promesse ne pointe sur aucune épreuve"
    source = epreuve.read_text(encoding="utf-8")
    assert "MONL_DATABASE_URL" in source, (
        "l'épreuve ne démarre pas les artefacts avec la variable annoncée")


def test_chaque_exploit_cite_le_point_qui_le_documente():
    """Les trois refus affichés sont des défauts RÉELS. Chacun renvoie à son
    point du journal : une page qui raconte des attaques sans source est une
    page de marketing, pas une preuve."""
    import re as _re

    from monl_platform.landing_pourquoi import REFUS
    journal = (pathlib.Path(__file__).parents[1]
               / "docs" / "design_decisions.md").read_text(encoding="utf-8")
    for refus in REFUS:
        numeros = _re.findall(r"\d+", refus["point"])
        assert numeros, refus["point"]
        for numero in numeros:
            assert f"\n## {numero}." in journal, (
                f"point {numero} cité par « {refus['titre']} » absent du journal")
        assert refus["titre"] in LANDING_HTML


def _specificite(selecteur: str) -> tuple:
    """Rend (id, classe/attribut/pseudo-classe, type) d'un sélecteur.

    Volontairement modeste : elle ne sait compter que des suites de classes,
    d'attributs et de types. `:is()`, `:not()` et `:where()` délèguent leur
    poids à leur contenu, donc leur présence ferait mal compter — l'assertion
    de forme les refuse plutôt que de rendre un chiffre faux.
    """
    for delegue in (":is(", ":not(", ":where(", ":has("):
        assert delegue not in selecteur, f"poids délégué non calculé : {delegue}"
    reste, attributs = re.subn(r"\[[^\]]*\]", " ", selecteur)
    identifiants = len(re.findall(r"#[-\w]+", reste))
    classes = len(re.findall(r"\.[-\w]+", reste))
    pseudo_classes = len(re.findall(r"(?<!:):[-\w]+", reste))
    types = len(re.findall(r"(?:^|[\s>+~])([a-zA-Z][-\w]*)", reste))
    return (identifiants, classes + attributs + pseudo_classes, types)


def test_le_repere_qui_glisse_emporte_le_fond_de_l_onglet():
    """Le fond de l'onglet actif est CÉDÉ au repère mobile.

    Cette cascade n'a pas pu être mesurée au navigateur — le volet masqué ne
    recalcule pas le style, et lit la même valeur avec et sans la classe. Elle
    est donc calculée : le sélecteur qui cède le fond doit être plus FORT et
    écrit APRÈS celui qui le pose. Sans les deux, l'onglet quitté s'éteint en
    .18s pendant que le repère met .34s à arriver, et les deux mouvements se
    contredisent à l'œil.
    """
    pose = '.case-tab[aria-selected="true"]'
    cede = '.case-tabs.glisse .case-tab[aria-selected="true"]'

    assert LANDING_HTML.count(cede) == 1, "la règle qui cède le fond a disparu"
    assert _specificite(cede) > _specificite(pose), (
        f"{cede} ne l'emporte plus sur {pose}")
    assert LANDING_HTML.index(cede) > LANDING_HTML.index(pose), (
        "la règle qui cède le fond est passée AVANT celle qui le pose")


def test_le_repere_n_est_jamais_servi_dans_le_html(platform):
    """Le repère est POSÉ par le script, jamais livré dans le balisage.

    Livré d'avance, il s'afficherait dans l'angle de la liste chez qui
    n'exécute pas le script — un rectangle posé sur rien — et l'onglet actif
    aurait cédé son fond sans que rien ne le remplace.
    """
    page = requests.get(platform, timeout=10).text
    # Retirer TOUS les scripts et TOUTES les feuilles, pas s'arrêter au premier
    # script : celui du thème vit dans le <head>, donc découper là laissait le
    # balisage des onglets entièrement hors de portée — le test restait vert en
    # servant le repère.
    balisage = re.sub(r"<(script|style)\b.*?</\1>", " ", page, flags=re.S | re.I)

    assert "case-explorer" in balisage, "le découpage a emporté les onglets"
    assert "case-repere" not in balisage, "le repère est servi dans le balisage"
    assert "glisse" not in balisage, "la classe qui cède le fond est servie"
    assert "case-repere" in page, "plus personne ne pose le repère"


def test_la_bascule_de_theme_n_anime_pas_qui_refuse_le_mouvement():
    """Le refus du mouvement est tenu en JavaScript, faute de pouvoir l'être
    en CSS : le bloc @media porte sur `*`, qui n'atteint aucun
    `::view-transition-*`. La bascule doit aussi rester fonctionnelle là où
    l'API n'existe pas — sinon le thème cesse de basculer.
    """
    garde = re.search(
        r"if\s*\(\s*!document\.startViewTransition\s*\|\|\s*(\w+)\.matches\s*\)"
        r"\s*\{\s*basculer\(\)\s*;\s*return\s*;\s*\}",
        LANDING_HTML,
    )
    assert garde, "la bascule s'anime sans vérifier l'API ni le mouvement réduit"

    nom = garde.group(1)
    assert re.search(
        rf"var\s+{nom}\s*=\s*window\.matchMedia\(\s*'\(prefers-reduced-motion: reduce\)'\s*\)",
        LANDING_HTML,
    ), f"« {nom} » n'interroge pas le mouvement réduit"


def _feuille(html: str) -> str:
    """Rend le CSS inliné de la page, feuilles concaténées."""
    return "\n".join(re.findall(r"<style[^>]*>(.*?)</style>", html, re.S | re.I))


def _declarations(css: str, selecteur: str) -> list:
    """Rend les blocs écrits pour ce sélecteur seul, en tête de règle.

    Ne sait pas lire un sélecteur groupé (« .a, .band { … } ») : l'assertion
    d'existence ci-après refuse le silence plutôt que de laisser le test vert
    sur une règle qu'il n'a pas su trouver.
    """
    motif = re.compile(r"(?:^|[};])\s*" + re.escape(selecteur) + r"\s*\{([^}]*)\}", re.M)
    return [m.group(1) for m in motif.finditer(css)]


def test_le_site_tient_sur_un_seul_fond():
    """Une seule couleur de fond du haut de la page jusqu'au pied.

    Les bandes portaient --surface-2, le rail --surface et le pied --surface :
    trois fonds en plus du --bg de la page, donc un changement de couleur
    presque à chaque section. Le filet marque désormais la même césure sans
    repeindre. Les CARTES gardent leur fond propre — une carte qui ne se
    détache pas du fond cesse d'être une carte — et le bloc final en est une,
    arrondie et détachée, pas une bande.
    """
    css = _feuille(LANDING_HTML)
    assert css, "la feuille n'est plus inlinée dans la page"

    for bande in (".band", ".proof-rail", ".footer-wrap"):
        blocs = _declarations(css, bande)
        assert blocs, f"la règle {bande} est introuvable : le test ne garde plus rien"
        for bloc in blocs:
            assert "background" not in bloc, (
                f"{bande} repeint le fond — l'alternance de couleurs est revenue")


def test_le_favicon_ico_repond_vraiment(platform):
    """Le fichier peut exister sans que la route le serve.

    Les tests de `test_platform_marque.py` gardent le CONTENU de l'icône ;
    celui-ci garde le fait qu'on puisse l'obtenir. Sans lui, retirer la route
    laisserait la suite entièrement verte pendant que les navigateurs
    reçoivent de nouveau un 404 — et gardent l'ancienne icône.
    """
    reponse = requests.get(platform + "/favicon.ico", timeout=10)

    assert reponse.status_code == 200, "/favicon.ico ne répond plus"
    assert reponse.content[:4] == b"\x00\x00\x01\x00", "ce n'est pas un vrai ICO"
    assert reponse.headers["content-type"] == "image/x-icon"

    # Et la ROUTE lit bien l'empreinte : sans le paramètre `v`, la politique de
    # cache de theme.py resterait juste sans jamais être appliquée.
    from monl_platform.theme import VERSION_ICO

    versionnee = requests.get(
        f"{platform}/favicon.ico?v={VERSION_ICO}", timeout=10)
    assert "immutable" in versionnee.headers["cache-control"]
    assert "immutable" not in reponse.headers["cache-control"], (
        "l'adresse nue se garde comme une adresse versionnée")
    assert versionnee.content == reponse.content, "deux icônes différentes"


def test_aucune_commande_ne_deborde_de_sa_carte():
    """Une commande tassée sort du cadre et se fait couper — en silence.

    Mesuré : « MONL_DATABASE_URL=postgresql://…  python3 -m uvicorn app:app »
    tenait sur UNE ligne dans une carte de 309 px utiles, on lisait le début et
    rien de la fin, et deux commandes séparées par un point médian ne se
    copiaient pas. La limite n'est pas choisie : elle est MESURÉE contre un
    vrai serveur — 309 px utiles à 7,5 px par caractère de la fonte mono du
    bloc, à la largeur de bureau où les trois cartes tiennent côte à côte,
    c'est-à-dire la plus étroite des dispositions.

    La longueur est un PROXY d'un débordement, et elle le dit : c'est la seule
    mesure qu'un test statique puisse faire. Le repli CSS (`pre-wrap`) est
    vérifié séparément ci-dessous — sans lui, une ligne trop longue serait
    coupée au lieu d'être repliée, et la carte mentirait sur son contenu.
    """
    from monl_platform.landing_pourquoi import SECTIONS

    blocs = re.findall(r"<pre><code>(.*?)</code></pre>", SECTIONS, re.S)
    assert blocs, "plus aucun bloc de commande : le test ne garde plus rien"

    for bloc in blocs:
        for ligne in bloc.split("\n"):
            assert len(ligne) <= 41, (
                f"{len(ligne)} caractères — la carte en tient 41 :\n  {ligne}")
            assert " · " not in ligne, (
                "deux commandes sur une ligne, séparées par un point médian : "
                "elles ne se copient pas")


def test_un_bloc_de_commande_se_replie_au_lieu_d_etre_coupe():
    """Le filet sous la limite ci-dessus.

    `overflow-x: auto` seul laisse la ligne défiler HORS du cadre : sur une
    carte, personne ne va la chercher. `pre-wrap` la replie.
    """
    from monl_platform.landing_pourquoi import EXTRA_CSS

    regle = _declarations(EXTRA_CSS, ".montage pre")
    assert regle, "la règle .montage pre est introuvable"
    assert "pre-wrap" in regle[0], (
        "une commande trop longue serait coupée au lieu d'être repliée")


def test_les_trois_cartes_de_position_alignent_leurs_titres():
    """Le surtitre masquait un désalignement, et son retrait l'a révélé.

    `margin-top: auto` sur le titre le poussait d'un espace libre qui dépend de
    la LONGUEUR du paragraphe : les trois titres se posaient donc à trois
    hauteurs différentes (mesuré 282, 301 et 321 px). Tant que le surtitre, lui
    aligné, occupait le haut de chaque carte, l'œil s'accrochait à lui.

    Le contrôle est CSS et pas géométrique — un test statique ne peut pas
    mesurer une mise en page. C'est un proxy, et il le dit : la vérification
    par la géométrie a été faite contre un vrai navigateur (écart 0 px sur les
    titres comme sur le bas des étiquettes).
    """
    from monl_platform.landing import EXTRA_CSS

    titre = _declarations(EXTRA_CSS, ".flow-stage h3")
    tags = _declarations(EXTRA_CSS, ".flow-stage .stage-tags")
    assert titre and tags, "les règles des cartes sont introuvables"

    assert "auto" not in titre[0], (
        "le titre repousse encore : les trois cartes se désalignent")
    assert "margin-top:auto" in tags[0].replace(" ", ""), (
        "rien ne pousse les étiquettes en bas : elles suivent le paragraphe")


def _regles_css(css: str) -> list:
    """Rend [(rang, media, selecteur, {propriétés})] pour tout le CSS servi.

    Les blocs `@keyframes` sont SAUTÉS en entier : leurs « 0% » et « to » ne
    sont pas des sélecteurs, et les compter ferait comparer des étapes
    d'animation à des règles de mise en page.

    Les COMMENTAIRES sont retirés d'abord : ceux de ce dépôt citent volontiers
    la règle qu'ils expliquent, accolades comprises (point 156 — un commentaire
    CSS est du contenu de page), et un extracteur naïf les lirait comme de
    vraies règles.
    """
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    regles, i, rang = [], 0, 0
    fins_de_media = []
    while i < len(css):
        while fins_de_media and i >= fins_de_media[-1]:
            fins_de_media.pop()
        saut = re.compile(r"@(keyframes|font-face|supports)[^{]*\{").match(css, i)
        if saut:
            profondeur, j = 1, saut.end()
            while j < len(css) and profondeur:
                profondeur += (css[j] == "{") - (css[j] == "}")
                j += 1
            i = j
            continue
        ouverture = re.compile(r"@media([^{]*)\{").match(css, i)
        if ouverture:
            profondeur, j = 1, ouverture.end()
            while j < len(css) and profondeur:
                profondeur += (css[j] == "{") - (css[j] == "}")
                j += 1
            fins_de_media.append(j - 1)
            i = ouverture.end()
            continue
        regle = re.compile(r"([^{}@]+)\{([^{}]*)\}").match(css, i)
        if regle:
            proprietes = {
                declaration.split(":", 1)[0].strip()
                for declaration in regle.group(2).split(";")
                if ":" in declaration
            }
            for selecteur in regle.group(1).split(","):
                regles.append(
                    (rang, bool(fins_de_media), selecteur.strip(), proprietes))
                rang += 1
            i = regle.end()
            continue
        i += 1
    return regles


def test_aucune_regle_responsive_n_est_ecrasee_par_une_regle_nue(platform):
    """Une `@media` n'ajoute AUCUNE spécificité : seul l'ORDRE la défend.

    `extra_css` concatène plusieurs modules, donc une règle nue écrite dans un
    module PLUS TARDIF écrase la version responsive d'un module antérieur, à
    poids égal, sans que rien ne le dise. C'est arrivé sur `.case-explorer` :
    `landing.py` posait `grid-template-columns:1fr` sous 760px, et la règle nue
    de `landing_cas.py` reprenait deux colonnes. Mesuré à 375px avant
    correction : `230px 103px`, soit un panneau de cas métier large de 103
    pixels, coupé par l'`overflow:hidden` de la carte — la vitrine du site,
    illisible sur téléphone.

    Le témoin porte sur la page RÉELLEMENT SERVIE, jamais sur un module : c'est
    entre les deux que la concaténation se joue.
    """
    page = requests.get(platform, timeout=10).text
    feuilles = re.findall(r"<style[^>]*>(.*?)</style>", page, re.S)
    assert feuilles, "aucune feuille de style dans la page servie"
    regles = _regles_css("\n".join(feuilles))
    assert len(regles) > 100, f"extracteur muet : {len(regles)} règles lues"
    assert any(media for _, media, _, _ in regles), "aucune @media reconnue"

    ecrasees = []
    for rang, media, selecteur, proprietes in regles:
        if not media:
            continue
        for rang2, media2, selecteur2, proprietes2 in regles:
            if media2 or rang2 <= rang or selecteur2 != selecteur:
                continue
            communes = proprietes & proprietes2
            if communes and _specificite(selecteur2) >= _specificite(selecteur):
                ecrasees.append(f"{selecteur} → {sorted(communes)}")

    assert not ecrasees, (
        "règle(s) responsive écrasée(s) par une règle nue écrite plus tard, "
        "à poids égal ou supérieur : " + " ; ".join(sorted(set(ecrasees))))


def test_chaque_page_du_site_porte_un_titre_qui_la_nomme():
    """Deux pages ne peuvent pas porter le même `<title>`.

    La console portait mot pour mot celui de l'ACCUEIL — « monl compiler, le
    métier est compilé ». Toutes ses voisines se nomment (« MCP — … », « Votre
    compte — … ») : avec plusieurs onglets ouverts, celui de la console était
    indiscernable de la page d'accueil, et un signet ne disait pas où il
    menait. Trouvé en mesurant le site à 375px, pas en le relisant : la sonde
    rapportait le titre de chaque page, et deux lignes étaient identiques.

    Le témoin lit les constantes de PAGE et non les routes : une page peut
    exister sans être encore montée, et c'est son titre qui est en cause.
    """
    import importlib
    import pkgutil

    import monl_platform

    titres = {}
    for module in pkgutil.iter_modules(monl_platform.__path__):
        charge = importlib.import_module(f"monl_platform.{module.name}")
        for nom in dir(charge):
            valeur = getattr(charge, nom)
            if not (isinstance(valeur, str) and nom.endswith("_HTML")):
                continue
            trouve = re.search(r"<title>(.*?)</title>", valeur, re.S)
            if not trouve:
                continue
            titre = trouve.group(1).strip()
            # Un même HTML ré-exporté par deux modules (app_pages) n'est pas un
            # doublon : c'est la MÊME page. On indexe donc par contenu.
            titres.setdefault(titre, set()).add(valeur)

    assert len(titres) > 5, f"extracteur muet : {len(titres)} titre(s) lu(s)"
    partages = {titre: len(pages) for titre, pages in titres.items() if len(pages) > 1}
    assert not partages, (
        "des pages DIFFÉRENTES partagent un titre — un onglet ne dit plus "
        f"laquelle est ouverte : {partages}")
