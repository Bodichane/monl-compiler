"""La table « Ce que cette plateforme ne fait pas » est CONFRONTÉE au code.

Elle était écrite à la main, et une de ses quatre lignes s'était périmée sans
bruit : « Aucun téléversement — une spec déclarant un bloc `assets` ou un champ
`Image` est refusée ». Mesuré contre la plateforme en marche, une spec portant
un champ `Upload` compile en 201, et le backend produit reçoit de vrais
fichiers depuis la brique 32. C'est le défaut du point 178 par une autre porte :
une affirmation que rien ne relie à ce que le code fait.

Ce fichier ne relit pas le texte de la table pour vérifier qu'il est bien écrit
— il MESURE ce que le compilateur accepte et refuse, puis exige que la table
ne dise pas le contraire.
"""

import contextlib
import io
import re
from pathlib import Path

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.parser import parse_monl_string
from monl_platform.guide import guide_html
from monl_platform.guide_data import LIMITES

RACINE = Path(__file__).resolve().parent.parent

SOCLE = """app Vitrine

entity Realisation
    titre: String
{champs}
actor Admin selfRegister
{relation}
rule Realisation.titre required
{regles}
workflow Gerer for Admin
    Create Realisation
    Read Realisation
    Update Realisation
{seed}
landing
    brief: "Une vitrine."
    link "Contact": "mailto:a@b.c"
"""


def _spec(champs="", regles="rule Realisation.Read public", relation="", seed=""):
    return SOCLE.format(champs=champs, regles=regles, relation=relation, seed=seed)


def _compile(spec, dossier):
    """Le chemin de la PLATEFORME : `base_dir` est le dossier du projet, donc
    l'existence des fichiers déclarés est vraiment vérifiée (point 83)."""
    with contextlib.redirect_stdout(io.StringIO()):
        return MonlAST(parse_monl_string(spec),
                       base_dir=str(dossier)).validate_and_audit()


# --- ce que le compilateur fait VRAIMENT -------------------------------------

def test_un_champ_upload_compile(tmp_path):
    """Le fichier envoyé à l'EXÉCUTION : c'est ce que la table niait."""
    spec = _spec(
        champs="    piece: Upload\n",
        relation="\nrelation Admin hasMany Realisation\n",
        regles=('rule Realisation.piece upload max 5242880 types "image/png"\n'
                "rule Realisation.Read ownedBy Admin\n"
                "rule Realisation.Update ownedBy Admin"))
    assert _compile(spec, tmp_path)["meta"]["appName"] == "Vitrine"


def test_un_champ_image_sans_valeur_compile(tmp_path):
    """Un champ `Image` déclare un TYPE, pas un chemin — il n'y a rien à
    vérifier tant qu'aucune valeur ne désigne un fichier."""
    assert _compile(_spec(champs="    photo: Image\n"), tmp_path)


def test_un_asset_declare_mais_absent_est_refuse(tmp_path):
    """La limite RÉELLE : le fichier fourni à la COMPILATION."""
    spec = 'app Vitrine\n\nassets\n    dir: "assets"\n    logo: "absent.svg"\n' \
           + _spec()[len("app Vitrine\n"):]
    with pytest.raises(ASTValidationError, match=re.escape("absent.svg")):
        _compile(spec, tmp_path)


def test_une_valeur_image_pointant_un_fichier_absent_est_refusee(tmp_path):
    spec = _spec(champs="    photo: Image\n",
                 seed='\nseed Realisation\n    titre: "Halo"\n'
                      '    photo: "absente.jpg"\n')
    with pytest.raises(ASTValidationError, match=re.escape("absente.jpg")):
        _compile(spec, tmp_path)


# --- la table ne doit pas dire le contraire ----------------------------------

def test_aucune_limite_ne_nie_le_televersement_a_l_execution(tmp_path):
    """Le défaut exact qui s'était périmé.

    Le lien est DÉRIVÉ : on compile d'abord la spec `Upload` ; si elle passe,
    aucune ligne de la table n'a le droit de dire qu'on ne peut envoyer aucun
    fichier. Recopier la phrase attendue ne mesurerait que ma propre recopie."""
    spec = _spec(
        champs="    piece: Upload\n",
        relation="\nrelation Admin hasMany Realisation\n",
        regles=('rule Realisation.piece upload max 5242880 types "image/png"\n'
                "rule Realisation.Read ownedBy Admin\n"
                "rule Realisation.Update ownedBy Admin"))
    _compile(spec, tmp_path)                      # échoue ici si ça ne compile plus

    for titre, texte in LIMITES:
        entier = f"{titre} {texte}".lower()
        assert "aucun téléversement" not in entier, (
            f"la table nie le téléversement alors qu'une spec `Upload` "
            f"compile : « {titre} »")


def test_la_limite_des_fichiers_nomme_les_deux_moments():
    """Une limite qui ne dit pas QUAND le fichier arrive laisse croire que la
    plateforme n'en accepte aucun — c'est la lecture qui s'est périmée."""
    ligne = next((f"{t} {x}" for t, x in LIMITES
                  if "compilation" in t.lower()), None)
    assert ligne, f"aucune ligne sur les fichiers de compilation : {LIMITES}"
    assert "Upload" in ligne
    assert "assets" in ligne


# --- ce qu'on dit au lecteur d'installer -------------------------------------

def _nom_de_distribution():
    """Le nom LU dans `pyproject.toml`, jamais recopié.

    L'import est DANS la fonction et porte son repli : `tomllib` n'arrive
    qu'en 3.11, le minimum déclaré est 3.10, et un import de tête ferait
    échouer la COLLECTE du fichier entier sur cette version — le témoin
    d'architecture qui l'interdit a mordu en écrivant ce banc."""
    try:
        import tomllib
    except ModuleNotFoundError:      # 3.10 : `tomllib` n'arrive qu'en 3.11
        import tomli as tomllib      # noqa: I001  (déclaré dans l'extra `dev`)
    with open(RACINE / "pyproject.toml", "rb") as f:
        return tomllib.load(f)["project"]["name"]


def _noms_installes_depuis_un_index(texte):
    """Les noms que les commandes `pip install` / `pipx install` vont CHERCHER
    sur un index, par opposition à un chemin local ou à un fichier d'exigences.

    Un chemin porte une barre oblique, commence par un point ou un tilde ; un
    drapeau commence par un tiret ; l'argument qui suit `-r`, `-c` ou
    `--requirement` est un FICHIER. L'extra (`[ai]`) et une contrainte de
    version (`==0.9.0b9`) sont retirés : c'est le NOM qui décide de ce qui
    est installé."""
    noms = []
    for commande in re.findall(r"pipx? install ([^<\n`]*)", texte):
        suivant_est_un_fichier = False
        for brut in commande.split():
            argument = brut.strip("\"'")
            if suivant_est_un_fichier:
                suivant_est_un_fichier = False
                continue
            if argument in {"-r", "-c", "--requirement", "--constraint"}:
                suivant_est_un_fichier = True
                continue
            if (not argument or argument.startswith(("-", ".", "/", "~"))
                    or "/" in argument):
                continue
            noms.append(re.split(r"[\[=<>!~;]", argument)[0])
    return noms


def test_l_extracteur_distingue_un_nom_d_un_chemin():
    """Sans ce témoin, un extracteur qui ne rend rien rendrait la règle
    ci-dessous verte sans rien regarder (point 161)."""
    assert _noms_installes_depuis_un_index("pip install monl") == ["monl"]
    assert _noms_installes_depuis_un_index(
        "pip install 'monl-compiler[ai]'") == ["monl-compiler"]
    assert _noms_installes_depuis_un_index(
        "pipx install monl-compiler==0.9.0b9") == ["monl-compiler"]
    assert _noms_installes_depuis_un_index(
        "pip install ./monl-compiler -r requirements.txt -e .") == []


@pytest.mark.parametrize("chemin", ["README.md", "QUICKSTART.md"])
def test_une_installation_depuis_un_index_nomme_la_vraie_distribution(chemin):
    """`monl-compiler` est publié sur PyPI depuis la 0.9.0-beta.9 : l'ancien
    témoin, qui interdisait toute installation depuis un index tant que rien
    n'était publié, l'annonçait lui-même — « le jour de la publication, c'est
    lui qui rappellera de revisiter ces lignes ».

    Le danger qui reste est le NOM. `monl` tout court est LIBRE sur l'index
    (point 167bis) : une documentation qui écrirait `pip install monl`
    ferait installer le paquet de quiconque s'en emparerait. Toute
    installation depuis un index doit donc nommer la distribution LUE dans
    `pyproject.toml`.

    Mesuré le 24/09/2026 : sans `--pre`, `pip install monl-compiler` installe
    bien la bêta — pip accepte une pré-version quand l'index n'a rien d'autre.
    Le drapeau n'est donc pas exigé ici ; l'exiger enseignerait une étape
    inutile."""
    nom = _nom_de_distribution()
    etrangers = [n for n in _noms_installes_depuis_un_index(
        (RACINE / chemin).read_text(encoding="utf-8")) if n != nom]
    assert not etrangers, (
        f"{chemin} fait installer depuis un index autre chose que {nom} : "
        f"{etrangers}")


def test_le_guide_n_installe_que_la_vraie_distribution():
    """Même règle sur la page SERVIE, et pas sur la constante du module :
    c'est entre les deux que le point 163 a vu une page se casser."""
    nom = _nom_de_distribution()
    etrangers = [n for n in _noms_installes_depuis_un_index(guide_html())
                 if n != nom]
    assert not etrangers, (
        f"le guide servi fait installer autre chose que {nom} : {etrangers}")
