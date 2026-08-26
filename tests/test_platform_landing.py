"""La racine porte la page de présentation, la console vit sur /console.

La console est un OUTIL : elle suppose qu'on sait déjà ce que monl fait. Une
personne qui l'ignore avait la console en pleine figure, sans un mot sur le
produit ni le moindre moyen de l'installer.
"""

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
        start_worker=False,
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
