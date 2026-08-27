"""Charger la spec, et faire PROUVER le résultat par le compilateur.

La revalidation se fait SANS `base_dir` : l'existence de ce que l'outil
écrit est vérifiée à part. Une garantie trop large n'est pas plus sûre,
elle est fausse ailleurs (point 84)."""

import contextlib
import io

from ..ast_validator import MonlAST
from ..parser import parse_monl_string
from .fondations import AssetsToolError


# ------------------------------------------------- lecture de la spec --
def _valider(texte, spec_path):
    """Le vrai parseur et le vrai validateur, SANS base_dir. Volontairement.

    C'est la portée exacte dont l'outil a besoin, et elle vient de la coupure
    forme/existence de la couche 1 : les contrôles de forme sont purs, donc ils
    s'appliquent ; la vérification d'EXISTENCE, non — et c'est ce qu'il faut.

    Deux raisons, toutes deux découvertes en éprouvant l'outil, pas en le
    relisant. `monl assets list` ne pouvait pas rapporter un asset manquant :
    charger la spec avec base_dir échouait sur ce manquant même, si bien que le
    rapport refusait de tourner dans le seul cas où il servait. Et `add` était
    inutilisable sur une spec qui déclare deux photos absentes — impossible
    d'en poser une, puisque l'autre faisait échouer la revalidation.

    L'existence de ce que l'outil ÉCRIT est vérifiée séparément, avec le même
    résolveur que le compilateur (`resoudre_asset`) : la garantie reste, elle
    est simplement énoncée juste. Le validateur affiche son audit de sécurité —
    déjà vu à la compilation : on l'étouffe."""
    with contextlib.redirect_stdout(io.StringIO()):
        raw = parse_monl_string(texte, file_path=spec_path)
        return MonlAST(raw).validate_and_audit()

def _charger(spec_path):
    """État de départ. Refuser tôt sur une spec déjà cassée n'est pas du zèle :
    sans ce contrôle, l'échec de la revalidation d'après édition ferait accuser
    l'outil d'un défaut qui existait avant lui."""
    with open(spec_path, encoding="utf-8") as fh:
        texte = fh.read()
    try:
        return _valider(texte, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"La spec ne compile pas en l'état : {err}\n"
            f"   L'outil refuse d'y écrire tant qu'elle est cassée — sinon "
            f"l'échec suivant semblerait venir de lui.") from None

def _revalider(texte, spec_path):
    """LE contrôle qui rend cet outil sûr : la spec obtenue est-elle valide ?

    Reparsée par le vrai parseur, revalidée par le vrai validateur — tous les
    refus du compilateur s'appliquent donc à ce que l'outil vient d'écrire.
    C'est ce qui fait que la couche 2 ne peut pas produire ce que la couche 1
    refuse."""
    try:
        return _valider(texte, spec_path)
    except Exception as err:
        raise AssetsToolError(
            f"Écriture ANNULÉE — la spec obtenue ne compilerait pas : {err}\n"
            f"   Ni la spec ni le dossier d'assets n'ont été modifiés.") from None
