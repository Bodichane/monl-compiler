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


def _installations_depuis_un_index(texte):
    """Les commandes `pip install` qui NOMMENT la distribution au lieu de
    désigner un chemin.

    La distinction ne se fait pas par un motif à trous — `./monl-compiler`
    contient le nom et n'est pas une installation depuis un index. On isole
    chaque argument, on retire l'extra `[ai]`, et on compare au nom LU dans
    `pyproject.toml` : un chemin porte une barre oblique ou commence par un
    point, donc il ne peut pas être égal au nom."""
    nom = _nom_de_distribution()
    fautifs = []
    for commande in re.findall(r"pip install ([^<\n`]*)", texte):
        for brut in commande.split():
            argument = brut.strip("\"'").split("[")[0]
            if argument == nom:
                fautifs.append(f"pip install {brut}")
    return fautifs


@pytest.mark.parametrize("chemin", ["README.md", "QUICKSTART.md"])
def test_aucune_documentation_ne_fait_installer_depuis_un_index(chemin):
    """`monl-compiler` n'est publié sur AUCUN index (point 167, toujours vrai).
    Une commande `pip install monl-compiler` échoue donc chez le lecteur, et
    une commande qui échoue est pire qu'une commande absente : elle se voit
    (même argument qu'au point 144 pour un lien sans schéma).

    Le nom est LU dans `pyproject.toml`, jamais recopié.

    LIMITE ÉNONCÉE : ce témoin ne peut pas vérifier que le paquet est absent de
    PyPI — la suite ne fait aucun appel réseau. Il garde la cohérence entre ce
    qu'on montre et ce que le dépôt permet ; le jour de la publication, c'est
    lui qui rappellera de revisiter ces lignes."""
    fautifs = _installations_depuis_un_index(
        (RACINE / chemin).read_text(encoding="utf-8"))
    assert not fautifs, f"{chemin} fait installer depuis un index : {fautifs}"


def test_le_guide_ne_fait_pas_installer_depuis_un_index():
    """Même règle sur la page SERVIE, et pas sur la constante du module :
    c'est entre les deux que le point 163 a vu une page se casser."""
    fautifs = _installations_depuis_un_index(guide_html())
    assert not fautifs, f"le guide servi fait installer depuis un index : {fautifs}"
