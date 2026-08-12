"""Le compilateur ne décide RIEN du visuel (point 72).

monl calculait une palette et des piles typographiques, les posait dans le
contrat, et les décrivait longuement dans le brief. C'était présenté comme une
suggestion — mais une suggestion écrite dans le document qui fait foi n'est pas
neutre : elle oriente, et le compilateur oriente mal, faute de savoir à quoi ce
projet-là doit ressembler.

La règle est désormais nette : **la direction de design vient du dialogue**,
formulée par l'auteur, et voyage par le brief. Le compilateur transmet ce qu'il
sait — structure, rôles, routes, contenu, intention déclarée — et se tait sur
le reste.

Prouver qu'un compilateur INTERDIT quelque chose est facile. Prouver qu'il se
TAIT l'est beaucoup moins, et c'est précisément ce que ce fichier vérifie : un
silence que rien ne mesure finit par se remplir à nouveau.
"""
import os
import re
import tempfile

from monl.ast_validator import MonlAST
from monl.frontend_contract import _render_prompt, build_contract
from monl.generator import MonlSecureGenerator
from monl.parser import parse_monl_file

BASE = """app Reparation

entity Piece
    label: String

actor Client selfRegister

workflow Catalogue for Client
    Create Piece
    Read Piece
"""

AVEC_UI = BASE + """
ui Piece
    theme: atelier
    primary: label
"""

AVEC_BRIEF = BASE + """
landing
    brief: "Un atelier de réparation qui veut un registre sobre et technique."
"""

# Une couleur écrite en dur, sous n'importe quelle forme.
HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# Les familles que le compilateur proposait dans ses piles système.
POLICES = ("Helvetica", "Arial", "Georgia", "Palatino", "Verdana", "Trebuchet",
           "Times New Roman", "Menlo", "Consolas", "SFMono", "ui-monospace")


def _contrat(spec_source, workdir):
    chemin = os.path.join(workdir, "spec.ml")
    with open(chemin, "w", encoding="utf-8") as fh:
        fh.write(spec_source)
    ast = MonlAST(parse_monl_file(chemin)).validate_and_audit()
    generateur = MonlSecureGenerator(ast, output_dir=workdir)
    return build_contract(ast, generateur)


def _brief(spec_source, workdir):
    contrat = _contrat(spec_source, workdir)
    return contrat, _render_prompt(contrat)


# ------------------------------------------------- ce que le contrat ne dit plus --
def test_le_contrat_ne_porte_plus_aucun_bloc_design():
    """Le bloc 'design' portait palette, typographies, rayon et style de
    carte. Il n'existe plus : le contrat décrit ce que monl sait, pas ce
    qu'il devinait."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(BASE, workdir)
    assert "design" not in contrat, sorted(contrat)


def test_le_contrat_porte_des_competences_de_finition_sans_theme_visuel():
    """Les skills imposent une profondeur, pas une palette calculée."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat, brief = _brief(BASE, workdir)
    assert contrat["design_skills"][0] == "monl-showcase"
    assert "$monl-showcase" in brief
    assert "niveau de profondeur et de finition" in brief


def test_le_contrat_ne_contient_aucune_couleur_ecrite_en_dur():
    """Retirer la clé ne suffirait pas si les couleurs ressortaient
    ailleurs — dans une note, un exemple, un champ voisin."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat = _contrat(BASE, workdir)
    trouvees = HEX.findall(str(contrat))
    assert not trouvees, f"couleurs imposées par le compilateur : {trouvees}"


def test_le_brief_ne_prescrit_ni_couleur_ni_police():
    """Le brief est le document que l'IA d'interface lit vraiment. C'est là
    que la prescription se réinstallerait le plus naturellement."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)

    couleurs = HEX.findall(brief)
    assert not couleurs, f"le brief impose des couleurs : {couleurs}"

    citees = [p for p in POLICES if p.lower() in brief.lower()]
    assert not citees, f"le brief impose des familles typographiques : {citees}"


# ------------------------------------------ ce que le brief doit continuer à dire --
def test_le_brief_transmet_l_intention_venue_du_dialogue():
    """Se taire sur le goût ne veut pas dire se taire tout court : ce que
    l'AUTEUR a formulé doit arriver intact à l'IA d'interface. C'est la
    seule direction légitime."""
    with tempfile.TemporaryDirectory() as workdir:
        contrat, brief = _brief(AVEC_BRIEF, workdir)
    assert "registre sobre et technique" in contrat["brief"]
    assert "registre sobre et technique" in brief


def test_le_brief_garde_les_deux_exigences_qui_ne_sont_pas_du_gout():
    """Contraste et autonomie ne sont pas des partis pris : l'un rend
    l'interface lisible, l'autre la rend vérifiable par le smoke test.
    Les confondre avec de la prescription esthétique les ferait tomber
    avec elle."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "4,5:1" in brief and "WCAG" in brief
    assert "aucune ressource distante" in brief


def test_le_brief_dit_par_quel_moyen_une_icone_est_possible():
    """POINT 104 : constat du mainteneur — aucun site produit n'employait
    d'icône. Ce n'était pas un défaut de l'IA : le brief interdit les CDN et ne
    disait NULLE PART que le SVG en ligne fonctionne. Lue seule, la règle
    d'autonomie se lit « pas d'icônes possibles ».

    Énoncer un MOYEN n'est pas prescrire un goût — même frontière qu'au
    point 72 pour le contraste WCAG et l'autonomie."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "SVG" in brief
    assert "en liste blanche" in brief or ".svg" in brief


def test_le_brief_ne_recommande_aucune_icone_ni_aucun_style_dicone():
    """La contre-épreuve du test précédent, et la garantie du point 72 : monl
    dit par quel MOYEN, jamais s'il en faut ni lesquelles. Sans ce test, la
    ligne ajoutée au point 104 pourrait dériver vers de la prescription à la
    première réécriture."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    bas = brief.lower()
    # Les librairies ne sont nommées que pour dire qu'elles sont HORS D'ATTEINTE.
    for interdit in ("style d'icône", "icônes arrondies", "icônes pleines",
                     "jeu d'icônes recommandé", "utiliser des icônes pour",
                     "ajouter une icône"):
        assert interdit not in bas, interdit
    assert "n'est atteignable" in bas or "atteignable" in bas


def test_le_brief_dit_explicitement_que_le_visuel_ne_vient_pas_du_compilateur():
    """Un brief muet laisserait croire à un oubli. Il doit énoncer la règle,
    sinon l'IA d'interface cherchera la direction qu'elle croit manquante."""
    with tempfile.TemporaryDirectory() as workdir:
        _contrat_, brief = _brief(BASE, workdir)
    assert "ne vient PAS de monl" in brief


# ------------------------------------------------------ le bloc 'ui' est inerte --
def test_un_bloc_ui_reste_accepte_mais_sans_effet():
    """Même politique qu'au point 41 pour 'landing mode/template' : la
    grammaire continue d'accepter la clé pour ne casser aucune spec
    existante, mais plus rien ne s'en sert. Le contrat doit être
    RIGOUREUSEMENT identique avec et sans le bloc."""
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        sans = _contrat(BASE, a)
        avec = _contrat(AVEC_UI, b)
    assert sans == avec, "le bloc 'ui' influence encore le contrat"


def test_deux_projets_de_domaines_opposes_recoivent_le_meme_silence():
    """Le compilateur choisissait autrefois son système visuel d'après le
    vocabulaire (boutique -> 'market', blog -> 'editorial'). Cette déduction
    a disparu : deux domaines opposés ne doivent plus différer que par ce
    qu'ils déclarent réellement."""
    boutique = BASE.replace("Piece", "Product").replace("Reparation", "Boutique")
    journal = BASE.replace("Piece", "Article").replace("Reparation", "Journal")
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        c1, b1 = _brief(boutique, a)
        c2, b2 = _brief(journal, b)

    assert "design" not in c1 and "design" not in c2
    # Le paragraphe de direction de design est le MÊME mot pour mot : il ne
    # dépend plus d'aucune déduction sur le domaine.
    extrait = "## Direction de design — elle ne vient PAS de monl"
    bloc1 = b1[b1.index(extrait):b1.index("## Règles non négociables")]
    bloc2 = b2[b2.index(extrait):b2.index("## Règles non négociables")]
    assert bloc1 == bloc2, "la direction de design dépend encore du domaine"


def test_la_consigne_de_retouche_rappelle_le_moyen_des_icones():
    """POINT 104, seconde moitié — trouvée en LANÇANT une retouche, pas en
    relisant le code. La ligne du point 104 n'était posée que sur le brief de
    CONSTRUCTION ; la consigne de retouche, elle, disait « même autonomie
    (aucun CDN) » et rien d'autre. Une retouche du type « rends cette section
    plus lisible » se serait donc heurtée au même mur.

    C'est la leçon du point 93 sur un autre objet : il n'y a qu'une voie vers
    l'IA, mais DEUX briefs — et ce qu'on écrit dans l'un ne se propage pas à
    l'autre."""
    from monl.cli import _write_retouche_brief
    with tempfile.TemporaryDirectory() as workdir:
        chemin = _write_retouche_brief(workdir, "la section retours est terne")
        with open(chemin, encoding="utf-8") as fh:
            texte = fh.read()
    # Le brief est mis en forme sur 79 colonnes : chercher une phrase telle
    # quelle échouerait au premier retour à la ligne inséré au milieu.
    continu = " ".join(texte.split())
    assert "SVG" in continu
    assert "pas une consigne" in continu, \
        "le rappel doit dire que c'est un MOYEN, jamais une prescription"
