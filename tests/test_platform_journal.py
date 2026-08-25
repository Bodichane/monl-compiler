"""Le journal ne doit pas pouvoir écrire un secret.

La plateforme garde des mots de passe, des jetons de session et des clés
d'API. Un journal est précisément l'endroit où ces valeurs fuient : on
journalise « pour déboguer », la ligne part dans les logs de l'hébergeur, et
elle y reste. Ces tests vérifient que le masquage tient par le NOM du champ
ET par la FORME de la valeur — parce que se fier au seul nom laisse passer
`identifiant=monl_AbC…`, qui n'annonce rien.
"""

import logging

from monl_platform import journal as J


def test_un_champ_qui_annonce_un_secret_est_masque():
    ligne = J.evenement("essai", password="hunter2", mot_de_passe="hunter2",
                        session_token="abc", api_key_secret="xyz")
    assert "hunter2" not in ligne
    assert "abc" not in ligne and "xyz" not in ligne
    assert ligne.count(J.MASQUE) == 4


def test_une_cle_dapi_est_masquee_meme_sous_un_nom_anodin():
    """Le cas que le masquage par nom seul laisse passer."""
    cle = "monl_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6"
    ligne = J.evenement("essai", identifiant=cle, valeur=cle)
    assert cle not in ligne
    assert ligne == f"essai identifiant={J.MASQUE} valeur={J.MASQUE}"


def test_un_jeton_de_forte_entropie_est_masque_sous_nimporte_quel_nom():
    jeton = "T3uc3xWnqbNYoAMPOZ8L5VAC0C0wS7mYoT3P1znKtgM"
    assert J.MASQUE in J.evenement("essai", ref=jeton)


def test_ce_qui_nest_pas_un_secret_passe_tel_quel():
    """Le témoin : un masquage qui masquerait tout serait inutilisable."""
    ligne = J.evenement("compilation", projet="a3f9", routes=17, duree_ms=812)
    assert ligne == "compilation projet=a3f9 routes=17 duree_ms=812"


def test_un_champ_peut_sappeler_nom_sans_percuter_le_parametre():
    """Le nom de champ le plus naturel en français. Avant que le paramètre ne
    soit positionnel uniquement, ceci levait un TypeError — donc la
    journalisation cassait exactement là où on en avait besoin."""
    assert J.evenement("projet", nom="Boutique") == "projet nom=Boutique"


def test_une_valeur_multiligne_ne_peut_pas_fabriquer_une_fausse_ligne():
    """Sans ça, un nom de projet contenant un saut de ligne écrit ce qu'il
    veut dans le journal — une entrée forgée se lit comme une vraie."""
    ligne = J.evenement("projet", nom="innocent\n2026-01-01 ERROR faux evenement")
    assert "\n" not in ligne
    assert ligne.startswith('projet nom="innocent 2026-01-01 ERROR faux evenement"')


def test_le_journal_ecrit_reellement_sur_son_flux(caplog):
    """`evenement` rend une chaîne ; encore faut-il qu'elle soit ÉMISE."""
    J.configurer()
    with caplog.at_level(logging.INFO, logger=J.NOM):
        J.journal.propagate = True          # caplog écoute la racine
        try:
            J.evenement("demarrage", workspace="/data")
        finally:
            J.journal.propagate = False
    assert "demarrage workspace=/data" in caplog.text


def test_les_niveaux_distinguent_lincident_du_train_train():
    assert J.anomalie("debit_depasse", compte="u1")
    assert J.panne("compilation_impossible", projet="p1")
