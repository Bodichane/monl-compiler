"""Le sommaire de `docs/design_decisions.md` doit pointer sur des titres réels.

Le fichier fait 140 points et son sommaire est la seule façon d'y naviguer.
**Dix liens pointaient dans le vide** quand ce test a été écrit : les ancres
avaient été tapées sans accents (`#132-…-mourait-au-demarrage-a-plusieurs-…`)
là où les titres les gardent, un titre avait été reformulé après coup
(« sort » devenu « sorti »), et un autre avait perdu la ponctuation qui
doublait un tiret dans son ancre.

Aucun de ces dix n'a jamais fait échouer quoi que ce soit : un lien mort dans
du Markdown ne lève rien, il ne fait qu'envoyer en haut de page. C'est
exactement la forme d'erreur que CLAUDE.md interdit de laisser vivre — celle
qui rend du vert en ne vérifiant rien. Un document se garde comme du code
(point 141).
"""

import re
import unicodedata
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent.parent / "docs" / "design_decisions.md"


def ancre_github(titre):
    """L'ancre que GitHub fabrique pour un titre de section.

    Minuscules, ponctuation retirée, espaces en tirets — les lettres
    accentuées sont CONSERVÉES, et c'est là que les dix liens se trompaient.
    Une ponctuation entourée d'espaces (« Brique 29 : le site ») laisse deux
    espaces, donc DEUX tirets : le détail n'est pas cosmétique, il départage
    un lien juste d'un lien mort.
    """
    texte = titre.strip().lower()
    texte = "".join(c for c in texte
                    if c.isalnum() or c in " -_"
                    or unicodedata.category(c).startswith("M"))
    return texte.replace(" ", "-")


def _titres_et_liens():
    contenu = JOURNAL.read_text(encoding="utf-8")
    titres = [(m.group(1), m.group(0)[3:])
              for m in re.finditer(r"^## (\d+)\. .+$", contenu, re.M)]
    liens = re.findall(r"\[(\d+)\]\(#([^)]+)\)", contenu)
    return titres, liens


def test_chaque_lien_du_sommaire_atteint_un_titre():
    titres, liens = _titres_et_liens()
    ancres = {ancre_github(titre) for _, titre in titres}
    pendants = [f"[{num}](#{lien})" for num, lien in liens if lien not in ancres]
    assert not pendants, (
        f"{len(pendants)} lien(s) du sommaire ne mènent nulle part : {pendants}")


# Le point 6 est un doublon RÉSERVÉ du point 1, vide, gardé pour ne pas
# décaler la numérotation des points 7 à 30 — référencée dans le README,
# dans CLAUDE.md et dans les commentaires du code. Son absence du sommaire
# est délibérée : il n'a pas de contenu à atteindre. L'exception est ÉCRITE
# ici plutôt que devinée, sinon le test se contenterait de la constater.
SANS_CONTENU = {"6"}


def test_chaque_point_du_journal_figure_au_sommaire():
    """Le pendant : un point écrit et jamais listé est un point qu'on ne
    retrouve pas. Les deux directions sont gardées, parce que les deux
    fautes existent — le sommaire qui cite un titre disparu, et le titre que
    le sommaire oublie."""
    titres, liens = _titres_et_liens()
    listes = {num for num, _ in liens}
    absents = sorted({num for num, _ in titres} - listes - SANS_CONTENU, key=int)
    assert not absents, f"points absents du sommaire : {absents}"


def test_la_regle_dancre_est_bien_celle_de_github():
    """Le témoin. Sans lui, un algorithme d'ancre FAUX rendrait les deux
    tests ci-dessus verts en comparant deux erreurs entre elles."""
    assert (ancre_github("137. Brique 29 : le site réclamait six fichiers")
            == "137-brique-29--le-site-réclamait-six-fichiers")
    assert (ancre_github("110. Rust évalué par un spike mesuré, et écarté")
            == "110-rust-évalué-par-un-spike-mesuré-et-écarté")
    assert ancre_github("42. L'apostrophe disparaît") == "42-lapostrophe-disparaît"
