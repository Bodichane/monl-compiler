"""Reprendre la main sur un compte dont le mot de passe est perdu.

Sans courriel, un mot de passe perdu rendait le compte ET ses projets
définitivement inaccessibles. C'était écrit dans les conditions
d'utilisation, ce qui rend la chose honnête mais ne la rend pas acceptable :
la première personne à qui ça arrive perd tout son travail.

La voie écartée mérite d'être connue. « On vous envoie un lien » suppose un
serveur de courriel, un domaine à réputation et une dépendance réseau dans un
service qui n'en a aucune — et la politique de confidentialité promet
qu'aucun courriel n'est envoyé. Le code de secours déplace la garde chez la
personne : elle reçoit huit codes une fois, elle les range où elle veut.
C'est le contrat déjà passé pour les clés d'API, donc ni une nouvelle
promesse ni un nouveau mode de stockage.

Tout est éprouvé contre un vrai serveur : c'est le seul moyen de vérifier
qu'un code réellement présenté sur le fil réinitialise réellement un mot de
passe, et que les sessions ouvertes tombent bien avec.
"""

import os
import sqlite3

import requests

from monl_platform.identity import IdentityStore
from tests.support.server import uvicorn_server

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANCIEN = "MotDePasse-Ancien-2026"
NOUVEAU = "MotDePasse-Nouveau-2026"


def _serveur(dossier):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    return uvicorn_server(str(dossier), env=env,
                          module="monl_platform.app:app", ready_path="/health")


def _inscrire(base, adresse, mot_de_passe=ANCIEN):
    session = requests.Session()
    reponse = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": adresse, "password": mot_de_passe})
    assert reponse.status_code == 201, reponse.text
    return session, reponse.json()


def _espace(tmp_path):
    candidat = tmp_path / "platform-projects"
    return candidat if candidat.exists() else tmp_path


# ---------------------------------------------------------------------------
# Ce que l'inscription remet
# ---------------------------------------------------------------------------

def test_linscription_remet_huit_codes_une_seule_fois(tmp_path):
    with _serveur(tmp_path) as base:
        session, corps = _inscrire(base, "codes@exemple.test")
        codes = corps["recovery_codes"]
        assert len(codes) == 8
        assert len(set(codes)) == 8, "deux codes identiques divisent les chances par deux"
        assert all(len(c) >= 16 for c in codes), "un code court se devine"

        # Ils ne ressortent NULLE PART ailleurs — comme une clé d'API.
        etat = session.get(f"{base}/api/auth/recovery-codes", timeout=30).json()
        assert etat == {"remaining": 8}
        me = session.get(f"{base}/api/auth/me", timeout=30).text
        for code in codes:
            assert code not in me, "un code ressort d'une route de lecture"


def test_les_codes_ne_sont_jamais_stockes_en_clair(tmp_path):
    """La promesse de la politique de confidentialité, vérifiée EN BASE.

    Un code lisible en base annulerait tout l'intérêt : qui lit le fichier
    entre dans n'importe quel compte sans connaître aucun mot de passe.
    """
    with _serveur(tmp_path) as base:
        _, corps = _inscrire(base, "clair@exemple.test")
        codes = corps["recovery_codes"]

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        stockes = [r[0] for r in db.execute("SELECT code_hash FROM recovery_codes")]
    assert len(stockes) == 8
    for code in codes:
        assert code not in stockes
        assert not any(code in valeur for valeur in stockes)


# ---------------------------------------------------------------------------
# Reprendre la main
# ---------------------------------------------------------------------------

def test_un_code_rend_le_compte_et_fait_tomber_les_sessions(tmp_path):
    with _serveur(tmp_path) as base:
        session, corps = _inscrire(base, "reprise@exemple.test")
        code = corps["recovery_codes"][0]
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 200

        reprise = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "reprise@exemple.test", "code": code, "password": NOUVEAU})
        assert reprise.status_code == 204, reprise.text

        # L'ancien mot de passe ne vaut plus rien…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": ANCIEN}).status_code == 401
        # …le nouveau ouvre…
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "reprise@exemple.test", "password": NOUVEAU}).status_code == 200
        # …et la session d'AVANT est morte. Sans ça, la réinitialisation ne
        # servirait à rien dans le seul cas qui compte : quelqu'un est déjà entré.
        assert session.get(f"{base}/api/auth/me", timeout=30).status_code == 401


def test_un_code_ne_sert_quune_fois(tmp_path):
    with _serveur(tmp_path) as base:
        _, corps = _inscrire(base, "unefois@exemple.test")
        code = corps["recovery_codes"][0]
        for _ in range(1):
            assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "unefois@exemple.test", "code": code,
                "password": NOUVEAU}).status_code == 204
        rejoue = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "unefois@exemple.test", "code": code,
            "password": "Encore-Un-Autre-2026"})
        assert rejoue.status_code == 401
        # Le mot de passe posé par le PREMIER usage tient toujours.
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "unefois@exemple.test", "password": NOUVEAU}).status_code == 200


def test_le_code_dun_autre_compte_ne_marche_pas(tmp_path):
    """Le piège du test à un seul compte : sans le second, « ce code
    fonctionne-t-il ? » passerait même si le code de n'importe qui ouvrait
    n'importe quel compte."""
    with _serveur(tmp_path) as base:
        _, premier = _inscrire(base, "alice@exemple.test")
        _inscrire(base, "bob@exemple.test")
        vole = requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bob@exemple.test", "code": premier["recovery_codes"][0],
            "password": NOUVEAU})
        assert vole.status_code == 401
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bob@exemple.test", "password": ANCIEN}).status_code == 200


def test_un_code_invente_est_refuse(tmp_path):
    with _serveur(tmp_path) as base:
        _inscrire(base, "invente@exemple.test")
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "invente@exemple.test", "code": "pas-un-vrai-code",
            "password": NOUVEAU}).status_code == 401


def test_le_refus_ne_distingue_pas_les_causes(tmp_path):
    """Distinguer « adresse inconnue » de « code faux » apprendrait à un
    attaquant laquelle des deux il tient déjà."""
    with _serveur(tmp_path) as base:
        _, corps = _inscrire(base, "muet@exemple.test")
        reponses = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "personne@exemple.test", "code": corps["recovery_codes"][0],
                "password": NOUVEAU}),
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "muet@exemple.test", "code": "faux", "password": NOUVEAU}),
        ]
        assert {r.status_code for r in reponses} == {401}
        assert len({r.json()["detail"] for r in reponses}) == 1


def test_la_recuperation_est_bornee_en_frequence(tmp_path):
    """Huit codes vivants par compte font huit chances par essai : sans
    plafond, la seule chose qui protégerait serait la patience de
    l'attaquant."""
    with _serveur(tmp_path) as base:
        _inscrire(base, "borne@exemple.test")
        codes_recus = [
            requests.post(f"{base}/api/auth/recover", timeout=30, json={
                "email": "borne@exemple.test", "code": f"essai-{numero}",
                "password": NOUVEAU}).status_code
            for numero in range(8)
        ]
        assert 429 in codes_recus, f"aucun plafond atteint : {codes_recus}"


# ---------------------------------------------------------------------------
# Régénérer
# ---------------------------------------------------------------------------

def test_une_nouvelle_serie_invalide_lancienne(tmp_path):
    """Régénérer se fait souvent parce qu'on craint une fuite. Cumuler les
    séries laisserait vivre exactement ce dont on veut se débarrasser."""
    with _serveur(tmp_path) as base:
        session, corps = _inscrire(base, "renouvelle@exemple.test")
        anciens = corps["recovery_codes"]

        neufs = session.post(f"{base}/api/auth/recovery-codes", timeout=30)
        assert neufs.status_code == 201
        neufs = neufs.json()["recovery_codes"]
        assert len(neufs) == 8
        assert not set(anciens) & set(neufs)
        assert session.get(f"{base}/api/auth/recovery-codes",
                           timeout=30).json() == {"remaining": 8}

        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": anciens[0],
            "password": NOUVEAU}).status_code == 401
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "renouvelle@exemple.test", "code": neufs[0],
            "password": NOUVEAU}).status_code == 204


def test_regenerer_exige_une_session(tmp_path):
    with _serveur(tmp_path) as base:
        _inscrire(base, "anonyme@exemple.test")
        assert requests.post(f"{base}/api/auth/recovery-codes",
                             timeout=30).status_code == 401
        assert requests.get(f"{base}/api/auth/recovery-codes",
                            timeout=30).status_code == 401


def test_supprimer_le_compte_emporte_ses_codes(tmp_path):
    """Des codes orphelins seraient des clés d'un compte qui n'existe plus."""
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "efface@exemple.test")
        assert session.request("DELETE", f"{base}/api/auth/account", timeout=30,
                               json={"password": ANCIEN}).status_code == 204

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        assert db.execute("SELECT COUNT(*) FROM recovery_codes").fetchone()[0] == 0


def test_les_comptes_anterieurs_sont_comptes_et_non_convertis(tmp_path):
    """La migration additive rattrape une table, jamais son contenu (point 89).

    Fabriquer des codes au démarrage pour les comptes existants serait pire :
    il faudrait les leur montrer, et personne ne les lirait. Ils sont NOMMÉS.
    """
    magasin = IdentityStore(tmp_path)
    magasin.register("ancien@exemple.test", ANCIEN)
    assert magasin.comptes_sans_codes() == 1

    magasin.create_recovery_codes(
        magasin.authenticate("ancien@exemple.test", ANCIEN)["id"])
    assert magasin.comptes_sans_codes() == 0
