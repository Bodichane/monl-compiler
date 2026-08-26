"""Le pied de page a des destinations, et deux couches disent la même chose.

La brique 30 (point 144) permettait de DÉCLARER des liens ; rien ne les
produisait. Ni le dialogue guidé, ni aucun des dix modèles, ni la console de
la plateforme n'en écrivait un seul — donc tout site sortait avec un pied de
page sans une seule destination, ce que le mainteneur a vu à l'œil avant que
la moindre mesure ne le dise. Une règle qui ne produit rien est ce que le
point 85 interdit au compilateur ; l'interdit vaut pour ce qui écrit la spec.
"""

import json
import shutil
import subprocess

import pytest

from monl.dialogue_engine import adresse_de_lien
from monl_platform.app import _liens_de_pied
from monl_platform.app_templates import materialize_template
from monl_platform.console import CONSOLE_HTML

#: Les entrées qui décident. Chacune est une façon dont quelqu'un écrit
#: réellement une adresse — la dernière colonne est ce qu'un navigateur doit
#: recevoir.
CAS = [
    ("contact@atelier.fr", "mailto:contact@atelier.fr"),
    ("instagram.com/atelier", "https://instagram.com/atelier"),
    ("www.exemple.fr", "https://www.exemple.fr"),
    ("https://x.com/atelier", "https://x.com/atelier"),
    ("mailto:a@b.fr", "mailto:a@b.fr"),
    ("tel:+33612345678", "tel:+33612345678"),
    # Le numéro s'écrit AVEC des espaces : c'est la seule valeur de cette
    # liste qui en contienne légitimement.
    ("+33 6 12 34 56 78", "tel:+33612345678"),
    ("06 12 34 56 78", "tel:0612345678"),
    ("06.12.34.56.78", "tel:06.12.34.56.78"),
    # Ce qui n'a qu'une lecture est complété ; le reste est ÉCARTÉ, jamais
    # deviné — un lien qui mène ailleurs est pire qu'un lien absent.
    ("pas une adresse", None),
    ("bonjour", None),
    ("", None),
    ("   ", None),
]


def test_une_adresse_incomplete_est_completee_sans_jamais_etre_devinee():
    for saisie, attendu in CAS:
        assert adresse_de_lien(saisie) == attendu, saisie


def _fonction_js(nom):
    """Extrait une fonction du script de la console, telle qu'elle est servie."""
    debut = CONSOLE_HTML.index(f"function {nom}(")
    fin = CONSOLE_HTML.index("\n  }\n", debut) + len("\n  }\n")
    return CONSOLE_HTML[debut:fin]


def test_la_console_et_le_serveur_completent_a_l_identique():
    """Deux mises en œuvre de la même règle finissent par diverger.

    Celle du navigateur décide ce que l'usager voit accepté ; celle du
    serveur décide ce qui atteint la spec. Si elles s'écartent, la console
    annonce un lien enregistré que le serveur écarte en silence — un défaut
    qu'aucune des deux ne peut voir seule.
    """
    node = shutil.which("node")
    if not node:
        pytest.skip("node absent : les deux couches ne peuvent pas être confrontées")

    script = (
        _fonction_js("adresseDeLien")
        + "\nconst cas = " + json.dumps([saisie for saisie, _ in CAS]) + ";"
        + "\nconsole.log(JSON.stringify(cas.map(function (s) {"
        + " return adresseDeLien(s); })));"
    )
    fini = subprocess.run([node, "-e", script], capture_output=True, text=True,
                          timeout=60)
    assert fini.returncode == 0, fini.stderr
    cote_navigateur = json.loads(fini.stdout.strip())

    assert cote_navigateur == [attendu for _, attendu in CAS]


def test_le_serveur_ecarte_ce_qu_il_ne_comprend_pas():
    liens = _liens_de_pied([
        {"label": "Instagram", "url": "instagram.com/atelier"},
        {"label": "Bruit", "url": "pas une adresse"},
        {"label": "", "url": "https://exemple.fr"},
        {"label": "instagram", "url": "https://autre.fr"},   # doublon de libellé
        {"label": 'Guillemet"', "url": "https://exemple.fr"},
        "pas un objet",
    ])

    assert liens == [{"label": "Instagram", "url": "https://instagram.com/atelier"}]


def test_un_projet_de_la_plateforme_porte_ses_liens_jusqu_a_la_spec():
    """Le bout en bout : ce que la console envoie doit atteindre le DSL."""
    spec = materialize_template(
        1, app_name="AtelierTest", description="Un atelier de céramique.",
        links=_liens_de_pied([
            {"label": "Courriel", "url": "contact@atelier.fr"},
            {"label": "Instagram", "url": "instagram.com/atelier"},
        ]),
    )

    assert 'link "Courriel": "mailto:contact@atelier.fr"' in spec
    assert 'link "Instagram": "https://instagram.com/atelier"' in spec


def test_sans_lien_la_spec_reste_exactement_celle_d_avant():
    """Contre-épreuve : la question ne doit rien changer quand on n'y répond
    pas — sinon tout projet existant verrait sa spec bouger."""
    spec = materialize_template(1, app_name="AtelierTest",
                                description="Un atelier de céramique.")

    assert "link " not in spec
