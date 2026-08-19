"""Le jeu de démonstration colle à la demande — ou ne bouge pas.

Chaque modèle du catalogue porte un jeu FIGÉ : toute boutique sortait avec
« Théière Kyoto », « Tasse Duo » et « Thé vert Sencha », qu'on ait demandé une
boulangerie ou un fleuriste. La description n'atteignait que le `brief`, donc
les TEXTES ; jamais les données.

Le fil conducteur de ces tests : une IA écrit ici de la DONNÉE qui entre dans
la spec. Chaque garde-fou est donc éprouvé dans les deux sens — il laisse
passer ce qui est juste, et il refuse le reste SANS casser la construction.
"""

import json

import pytest

from monl.parser import parse_monl_string
from monl_platform.app_templates import materialize_template
from monl_platform.seed_ai import (
    MAX_FICHES,
    blocs_de_la_reponse,
    personnaliser_le_jeu,
    prompt_de_contenu,
)


class Faux:
    """Fournisseur qui rend ce qu'on lui a dit de rendre."""

    provider_name = "faux"
    model = "faux"
    last_usage = None

    def __init__(self, reponse):
        self.reponse = reponse
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        if isinstance(self.reponse, Exception):
            raise self.reponse
        return self.reponse


def _bloc(lignes, entete="name,price,description,imageUrl,stock"):
    return "### Product\n```csv\n" + entete + "\n" + "\n".join(lignes) + "\n```\n"


BOULANGERIE = _bloc([
    'Baguette tradition,1.30,"Farine T65, levain naturel.",,80',
    'Pain au levain,4.50,"Miche de 1 kg.",,25',
])


@pytest.fixture()
def projet(tmp_path):
    """Un vrai projet issu du modèle Boutique, avec son jeu générique."""
    spec = materialize_template(3, app_name="Essai",
                                description="Une boutique.")
    (tmp_path / "spec.ml").write_text(spec, encoding="utf-8")
    return tmp_path


def _seed(projet):
    normalise = parse_monl_string((projet / "spec.ml").read_text(encoding="utf-8"))
    lignes = []
    for bloc in normalise.get("seeds", []):
        if bloc["entity"] == "Product":
            lignes += [row.get("name") for row in bloc["rows"]]
    return lignes


def test_le_jeu_du_modele_est_bien_generique_au_depart(projet):
    """Le point de départ, mesuré : sans quoi tout ce fichier ne prouve rien."""
    assert "Théière Kyoto" in _seed(projet)


def test_la_description_remplace_le_jeu_generique(projet):
    faux = Faux(BOULANGERIE)

    rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet),
                                   "Une boulangerie artisanale à Lyon.", faux)

    assert rapport["entites"] == [("Product", 2)], rapport
    noms = _seed(projet)
    assert noms == ["Baguette tradition", "Pain au levain"]
    assert "Théière Kyoto" not in noms
    # La description doit RÉELLEMENT atteindre le modèle : sans elle, il
    # écrirait un catalogue au hasard, ce qui est le défaut qu'on répare.
    assert "boulangerie artisanale à Lyon" in faux.prompts[0]


def test_un_en_tete_modifie_est_refuse_et_le_jeu_reste(projet):
    """L'IA écrit des LIGNES, jamais la structure.

    Une colonne inventée entrerait dans la spec sans exister dans l'entité —
    et les colonnes viennent du compilateur, jamais d'un modèle.
    """
    faux = Faux(_bloc(['Baguette,1.30,"Pain",,80,bio'],
                      entete="name,price,description,imageUrl,stock,label_bio"))

    rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet),
                                   "Une boulangerie.", faux)

    assert rapport["entites"] == []
    assert "Théière Kyoto" in _seed(projet)


def test_un_type_invalide_laisse_la_spec_intacte(projet):
    """Le vrai parseur et le vrai validateur ont le dernier mot (point 115).

    « 1,30 € » n'est pas un nombre : la spec obtenue ne compilerait pas, donc
    rien n'est écrit.
    """
    faux = Faux(_bloc(['Baguette,"1,30 €","Pain de tradition.",,quatre-vingts']))

    rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet),
                                   "Une boulangerie.", faux)

    assert rapport["entites"] == []
    assert rapport["raison"], "un refus doit être NOMMÉ, jamais silencieux"
    assert "Théière Kyoto" in _seed(projet)
    # La spec doit rester lisible par le vrai parseur.
    parse_monl_string((projet / "spec.ml").read_text(encoding="utf-8"))


def test_une_reponse_illisible_ne_casse_jamais_la_construction(projet):
    """Un catalogue générique est un défaut ; une construction perdue est une
    facture."""
    for reponse in ("", "Bonjour, je ne peux pas vous aider.",
                    json.dumps({"files": {}}), RuntimeError("502 Bad Gateway")):
        rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet),
                                       "Une boulangerie.", Faux(reponse))
        assert rapport["entites"] == [], reponse
        assert rapport["raison"], reponse
    assert "Théière Kyoto" in _seed(projet)


def test_sans_description_aucun_appel_n_est_fait(projet):
    """Un appel qui ne peut rien personnaliser est une dépense pure."""
    faux = Faux(BOULANGERIE)

    rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet), "   ", faux)

    assert faux.prompts == []
    assert rapport["entites"] == []


def test_le_nombre_de_fiches_est_borne(projet):
    """Au-delà, ce n'est plus une démonstration : c'est du remplissage payé."""
    faux = Faux(_bloc([f'Pain {i},1.30,"Une miche.",,10'
                       for i in range(MAX_FICHES + 8)]))

    rapport = personnaliser_le_jeu(str(projet / "spec.ml"), str(projet),
                                   "Une boulangerie.", faux)

    assert rapport["entites"] == [("Product", MAX_FICHES)]
    assert len(_seed(projet)) == MAX_FICHES


def test_les_blocs_se_lisent_avec_ou_sans_cloture():
    """Un modèle clôture ou non son CSV : les deux doivent passer, comme au
    point 145 — l'emballage ne doit jamais décider du sort du contenu."""
    nu = "### Product\nname,price\nPain,1.30\n"
    clos = "### Product\n```csv\nname,price\nPain,1.30\n```\n"

    assert blocs_de_la_reponse(nu) == blocs_de_la_reponse(clos)
    assert blocs_de_la_reponse(nu)["Product"].startswith("name,price")


def test_le_brief_interdit_d_inventer_une_colonne_ou_une_image():
    """Ce que la consigne dit compte autant que ce que le contrôle refuse :
    un refus qu'on pouvait éviter est une dépense pour rien."""
    prompt = prompt_de_contenu("Une boulangerie.",
                               {"Product": "name,price\nPain,1.30"})

    assert "à l'identique" in prompt
    assert "VIDE" in prompt          # les colonnes d'image
    assert str(MAX_FICHES) in prompt


# ---- Au niveau de la plateforme : ce qui est personnalisé, et ce qui ne l'est pas ----

SPEC_A_SOI = """app SpecPersonnelle

entity Piece
    name: String

actor Admin

rule Piece.Read public

seed Piece
    name: "Ma vraie pièce, écrite à la main"

workflow ManagePiece for Admin
    Create Piece
    Read Piece
"""


def _plateforme(tmp_path, provider):
    import socket
    import threading
    import time

    import requests
    import uvicorn

    from monl_platform.app import create_app

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    app = create_app(
        database=tmp_path / "platform.db",
        workspace_root=tmp_path / "projects",
        domain="localhost",
        jwt_secret="secret-de-plateforme-pour-le-contenu-1234567",
        provider=provider,
        poll_interval=0.01,
        start_worker=False,
    )
    serveur = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    fil = threading.Thread(target=serveur.run, daemon=True)
    fil.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(200):
        try:
            if requests.get(f"{base}/health", timeout=0.2).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.02)
    else:
        pytest.fail("la plateforme n'a pas démarré")
    return base, serveur, fil, tmp_path / "projects"


def test_une_spec_fournie_par_l_usager_n_est_JAMAIS_touchee(tmp_path):
    """Elle porte ses VRAIES données : les réécrire serait les détruire.

    C'est la frontière de toute cette brique — l'IA ne remplace que le
    placeholder d'un modèle du catalogue, jamais ce qu'une personne a écrit.
    """
    import requests

    faux = Faux(BOULANGERIE)
    base, serveur, fil, racine = _plateforme(tmp_path, faux)
    try:
        jeton = requests.post(f"{base}/register", json={
            "identifier": "spec@example.test", "password": "MotDePasse-123"},
            timeout=10).json()["token"]
        cree = requests.post(
            f"{base}/projects", headers={"Authorization": f"Bearer {jeton}"},
            json={"slug": "spec-a-soi", "spec": SPEC_A_SOI,
                  "description": "Une boulangerie artisanale."},
            timeout=30)
        assert cree.status_code == 201, cree.text
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)

    ecrite = next(racine.rglob("spec.ml")).read_text(encoding="utf-8")
    assert "Ma vraie pièce, écrite à la main" in ecrite
    assert "Baguette" not in ecrite
    assert faux.prompts == [], "aucun appel ne doit être fait sur une spec fournie"


def test_un_projet_issu_d_un_modele_recoit_un_catalogue_a_son_sujet(tmp_path):
    """La contre-épreuve : sans elle, un garde-fou qui n'appellerait JAMAIS
    l'IA passerait le test ci-dessus et paraîtrait correct."""
    import requests

    faux = Faux(BOULANGERIE)
    base, serveur, fil, racine = _plateforme(tmp_path, faux)
    try:
        jeton = requests.post(f"{base}/register", json={
            "identifier": "modele@example.test", "password": "MotDePasse-123"},
            timeout=10).json()["token"]
        cree = requests.post(
            f"{base}/projects", headers={"Authorization": f"Bearer {jeton}"},
            json={"slug": "boulangerie", "model": "Boutique en ligne",
                  "app_name": "Fournil", "description": "Une boulangerie artisanale."},
            timeout=60)
        assert cree.status_code == 201, cree.text
    finally:
        serveur.should_exit = True
        fil.join(timeout=10)

    ecrite = next(racine.rglob("spec.ml")).read_text(encoding="utf-8")
    assert "Baguette tradition" in ecrite
    assert "Théière Kyoto" not in ecrite
    assert faux.prompts, "le modèle devait être appelé"
