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


def test_un_identifiant_de_compte_reste_lisible_donc_recoupable():
    """Le défaut trouvé en lançant le serveur, pas en relisant le code.

    Un identifiant de compte est un `uuid4().hex` de 32 caractères : la règle
    de forte entropie l'avalait, et TOUTES les lignes disaient
    `compte=[masqué]`. Un journal qui masque le compte ne dit plus si deux
    cents connexions refusées viennent d'un compte ou de deux cents.

    Le remède ne touche PAS au masquage — c'est ce qu'on lui passe qui change.
    """
    identifiant = "a3f91b2c4d5e6f708192a3b4c5d6e7f8"
    assert len(identifiant) == 32

    # Passé entier, il EST masqué — et c'est correct : la règle ne sait pas
    # distinguer un identifiant d'un jeton.
    assert J.MASQUE in J.evenement("connexion", compte=identifiant)

    # Raccourci, il traverse et reste le même d'une ligne à l'autre.
    court = J.court(identifiant)
    assert court == "a3f91b2c"
    premiere = J.evenement("connexion", compte=court)
    seconde = J.evenement("cle_creee", compte=court, cle=J.court("ff00"))
    assert J.MASQUE not in premiere and J.MASQUE not in seconde
    assert premiere == "connexion compte=a3f91b2c"
    assert "compte=a3f91b2c" in seconde


def test_les_evenements_de_lapplication_ne_masquent_pas_le_compte():
    """La garantie au vrai point d'appel : c'est `app.py` qui doit passer un
    identifiant court, pas seulement `journal.py` qui doit savoir le faire."""
    import re
    from pathlib import Path

    source = Path(__file__).resolve().parent.parent / "src" / "monl_platform" / "app.py"
    texte = source.read_text(encoding="utf-8")
    nus = re.findall(r'(?:compte|cle|projet)=(?!court\()(?:user\["id"\]|'
                     r'cle\["id"\]|key_id|manifest\["id"\])', texte)
    assert not nus, f"identifiants journalisés sans `court()` : {nus}"
