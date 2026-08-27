"""`monl-platform admin` — les gestes d'exploitation, éprouvés sur un vrai service.

Toute intervention sur un compte passait par `sqlite3` à la main, serveur
arrêté : tenable à dix comptes, pas à cent, et chaque geste risquait une
requête tapée de travers, sans trace de qui l'avait faite.

**Ces tests vérifient l'EFFET, jamais l'affichage.** Une commande qui imprime
« clé révoquée » sans que la clé cesse de fonctionner serait pire qu'absente :
on la croirait faite. Chaque geste d'écriture est donc rejoué contre un
serveur réel, ou relu en base.

La voie écartée mérite d'être connue : un panneau web aurait demandé sa propre
authentification, une colonne de privilège dans `users`, et serait devenu la
cible dont une seule faille donne tous les comptes. Qui possède le shell
possède déjà la base — la ligne de commande n'ajoute aucune surface d'attaque.
"""

import json
import os
import sqlite3
import subprocess
import sys
import time

import pytest
import requests

from monl_platform.identity import IdentityStore
from tests.support.server import uvicorn_server

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOT_DE_PASSE = "MotDePasse-Administration-2026"


def _environnement(**extra):
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.join(RACINE, "src")
    env.update(extra)
    return env


def _serveur(dossier, **extra):
    return uvicorn_server(str(dossier), env=_environnement(**extra),
                          module="monl_platform.app:app", ready_path="/health")


def _espace(tmp_path):
    candidat = tmp_path / "platform-projects"
    return candidat if candidat.exists() else tmp_path


def admin(tmp_path, *arguments):
    """Lance la commande comme l'exploitant la lance, et rend le processus."""
    return subprocess.run(
        [sys.executable, "-m", "monl_platform", "admin", *arguments,
         "--workspace", str(_espace(tmp_path))],
        capture_output=True, text=True, env=_environnement(), cwd=RACINE, timeout=120)


def _inscrire(base, adresse):
    session = requests.Session()
    reponse = session.post(f"{base}/api/auth/register", timeout=30,
                           json={"email": adresse, "password": MOT_DE_PASSE})
    assert reponse.status_code == 201, reponse.text
    return session, reponse.json()


# ---------------------------------------------------------------------------
# Lectures
# ---------------------------------------------------------------------------

def test_la_liste_montre_les_comptes_et_ce_quils_portent(tmp_path):
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "alice@exemple.test")
        _inscrire(base, "bob@exemple.test")
        assert session.post(f"{base}/api/keys", json={"name": "portable"},
                            timeout=30).status_code == 201

    rendu = admin(tmp_path, "comptes")
    assert rendu.returncode == 0, rendu.stderr
    assert "alice@exemple.test" in rendu.stdout
    assert "bob@exemple.test" in rendu.stdout
    ligne_alice = next(ligne for ligne in rendu.stdout.splitlines()
                       if ligne.startswith("alice@"))
    assert ligne_alice.split()[-3:] == ["0", "1", "8"], ligne_alice


def test_le_detail_dun_compte_nomme_ses_projets_et_ses_cles(tmp_path):
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "detail@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "poste-fixe"}, timeout=30)
        identifiant_cle = cle.json()["id"]
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec}, timeout=180)
        assert projet.status_code == 201, projet.text

    rendu = admin(tmp_path, "compte", "detail@exemple.test")
    assert rendu.returncode == 0, rendu.stderr
    assert projet.json()["id"] in rendu.stdout
    assert identifiant_cle in rendu.stdout
    assert "poste-fixe" in rendu.stdout
    assert "Codes de secours restants : 8" in rendu.stdout


def test_ladresse_est_normalisee_comme_a_linscription(tmp_path):
    """Sans ça, l'exploitant tape l'adresse telle qu'on la lui a dictée et ne
    trouve rien, alors que le compte existe."""
    with _serveur(tmp_path) as base:
        _inscrire(base, "casse@exemple.test")
    rendu = admin(tmp_path, "compte", "  CASSE@Exemple.TEST  ")
    assert rendu.returncode == 0, rendu.stderr
    assert "casse@exemple.test" in rendu.stdout


def test_un_compte_inconnu_echoue_franchement(tmp_path):
    IdentityStore(tmp_path)
    rendu = admin(tmp_path, "compte", "personne@exemple.test")
    assert rendu.returncode == 1
    assert "Aucun compte" in rendu.stderr


# ---------------------------------------------------------------------------
# Écritures — l'effet, pas l'affichage
# ---------------------------------------------------------------------------

def test_les_nouveaux_codes_ouvrent_vraiment_le_compte(tmp_path):
    """Le geste de dépannage entier : quelqu'un a perdu son mot de passe ET
    ses codes, l'exploitant lui en dicte de nouveaux, et il reprend la main.

    Vérifier que la commande imprime huit codes ne prouverait rien : ce qui
    compte est qu'un de ces codes, présenté sur le fil, réinitialise vraiment
    le mot de passe.
    """
    with _serveur(tmp_path) as base:
        _, corps = _inscrire(base, "bloque@exemple.test")
        anciens = corps["recovery_codes"]

        rendu = admin(tmp_path, "codes", "bloque@exemple.test")
        assert rendu.returncode == 0, rendu.stderr
        nouveaux = [ligne.strip() for ligne in rendu.stdout.splitlines()
                    if ligne.startswith("  ") and ligne.strip()]
        assert len(nouveaux) == 8
        assert not set(anciens) & set(nouveaux)

        # L'ancienne série est morte…
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": anciens[0],
            "password": "Repris-Par-Ancien-2026"}).status_code == 401
        # …la nouvelle ouvre.
        assert requests.post(f"{base}/api/auth/recover", timeout=30, json={
            "email": "bloque@exemple.test", "code": nouveaux[0],
            "password": "Repris-Par-Nouveau-2026"}).status_code == 204
        assert requests.post(f"{base}/api/auth/login", timeout=30, json={
            "email": "bloque@exemple.test",
            "password": "Repris-Par-Nouveau-2026"}).status_code == 200


def test_une_cle_revoquee_cesse_de_fonctionner_sur_le_fil(tmp_path):
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "cle@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "à révoquer"},
                           timeout=30).json()
        appel = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        entete = {"Authorization": f"Bearer {cle['key']}"}
        assert requests.post(f"{base}/mcp", json=appel, headers=entete,
                             timeout=30).status_code == 200

        rendu = admin(tmp_path, "revoquer-cle", cle["id"])
        assert rendu.returncode == 0, rendu.stderr

        refus = requests.post(f"{base}/mcp", json=appel, headers=entete, timeout=30)
        assert refus.status_code in (401, 403), refus.text

    # Deux fois : elle n'est plus active, la commande le dit sans mentir.
    encore = admin(tmp_path, "revoquer-cle", cle["id"])
    assert encore.returncode == 1
    assert "Aucune clé active" in encore.stderr


def test_prolonger_repousse_lecheance_depuis_maintenant(tmp_path):
    """« Garde-le trente jours de plus » se dit après coup, souvent sur un
    projet DÉJÀ échu : repartir de l'ancienne date ne prolongerait rien."""
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "prolonge@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        db.execute("UPDATE projects SET expires_at = ?", (int(time.time()) - 100_000,))

    assert admin(tmp_path, "prolonger", projet, "--jours", "30").returncode == 0
    with sqlite3.connect(magasin.path) as db:
        echeance = db.execute("SELECT expires_at FROM projects").fetchone()[0]
    assert echeance > int(time.time()) + 29 * 24 * 3600


def test_prolonger_sans_limite_retire_lecheance(tmp_path):
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "toujours@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

    assert admin(tmp_path, "prolonger", projet, "--jamais").returncode == 0
    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        assert db.execute("SELECT expires_at FROM projects").fetchone()[0] is None


def test_expirer_laisse_la_purge_faire_le_menage(tmp_path):
    """Effacer depuis la commande doublerait le chemin de suppression, et deux
    chemins finissent par diverger — celui qu'on emprunte le moins étant celui
    qui se casse. La commande marque échu, la purge nettoie."""
    with _serveur(tmp_path, MONL_PURGE_INTERVAL_SECONDS="1") as base:
        session, _ = _inscrire(base, "expire@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]

        assert admin(tmp_path, "expirer", projet).returncode == 0

        magasin = IdentityStore(_espace(tmp_path))
        for _ in range(40):
            with sqlite3.connect(magasin.path) as db:
                if db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0:
                    break
            time.sleep(0.25)
        with sqlite3.connect(magasin.path) as db:
            assert db.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 0


def test_supprimer_sans_confirmer_ne_touche_a_rien(tmp_path):
    """Le témoin. Sans lui, une commande qui supprimerait TOUJOURS passerait
    le test suivant."""
    with _serveur(tmp_path) as base:
        _inscrire(base, "prudent@exemple.test")

    rendu = admin(tmp_path, "supprimer-compte", "prudent@exemple.test")
    assert rendu.returncode == 1
    assert "Rien n'a été fait" in rendu.stdout
    assert "prudent@exemple.test" in admin(tmp_path, "comptes").stdout


def test_supprimer_avec_confirmer_efface_jusquau_disque(tmp_path):
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "partant@exemple.test")
        spec = requests.get(f"{base}/api/examples/vitrine", timeout=30).json()["spec"]
        projet = session.post(f"{base}/api/compile", json={"spec": spec},
                              timeout=180).json()["id"]
        dossier = next(chemin for chemin in tmp_path.rglob(projet) if chemin.is_dir())
        assert dossier.is_dir()

    rendu = admin(tmp_path, "supprimer-compte", "partant@exemple.test", "--confirmer")
    assert rendu.returncode == 0, rendu.stderr
    assert not dossier.exists(), "le dossier compilé survit à la suppression"

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        for table in ("users", "projects", "api_keys", "recovery_codes"):
            assert db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


# ---------------------------------------------------------------------------
# La trace
# ---------------------------------------------------------------------------

def test_tout_geste_qui_ecrit_laisse_une_trace(tmp_path):
    """« Qui a supprimé ce compte ? » est la question qu'on pose le jour où ça
    tourne mal. Sans journal, elle n'a pas de réponse."""
    with _serveur(tmp_path) as base:
        session, _ = _inscrire(base, "trace@exemple.test")
        cle = session.post(f"{base}/api/keys", json={"name": "tracee"},
                           timeout=30).json()["id"]

    gestes = {
        "codes_regeneres_par_exploitant": ("codes", "trace@exemple.test"),
        "cle_revoquee_par_exploitant": ("revoquer-cle", cle),
        "compte_supprime_par_exploitant": ("supprimer-compte", "trace@exemple.test",
                                           "--confirmer"),
    }
    for evenement, arguments in gestes.items():
        rendu = admin(tmp_path, *arguments)
        assert rendu.returncode == 0, rendu.stderr
        assert evenement in rendu.stderr, f"{evenement} absent du journal"


def test_le_journal_de_ladministration_ne_livre_aucun_identifiant_nu(tmp_path):
    """Même règle que pour le serveur : les identifiants sont tronqués à huit
    caractères — assez pour recouper, trop court pour ressembler à un secret."""
    with _serveur(tmp_path) as base:
        _, corps = _inscrire(base, "nu@exemple.test")

    magasin = IdentityStore(_espace(tmp_path))
    with sqlite3.connect(magasin.path) as db:
        identifiant = db.execute("SELECT id FROM users").fetchone()[0]

    rendu = admin(tmp_path, "codes", "nu@exemple.test")
    assert identifiant not in rendu.stderr, "l'identifiant complet est journalisé"
    assert identifiant[:8] in rendu.stderr
    # Et aucun code de secours ne doit finir dans le journal.
    for code in corps["recovery_codes"]:
        assert code not in rendu.stderr


def test_ladministration_nouvre_aucune_route(tmp_path):
    """La décision qui porte ce module : la surface HTTP ne bouge PAS.

    Un panneau web serait devenu la cible dont une seule faille donne tous les
    comptes. Ce test échoue si quelqu'un ajoute un jour une route
    d'administration en pensant bien faire.
    """
    with _serveur(tmp_path) as base:
        schema = requests.get(f"{base}/openapi.json", timeout=30).json()
        chemins = list(schema["paths"])
    assert not [chemin for chemin in chemins if "admin" in chemin.lower()], chemins
    assert "administration" not in json.dumps(schema).lower()


def test_les_actions_de_la_cli_sont_aussi_verifiees_dans_le_processus(tmp_path, capsys):
    """Les subprocess prouvent le geste complet ; ceci couvre ses décisions.

    Une commande qui imprime le bon texte mais branche le mauvais argument
    resterait autrement invisible à la couverture : ici chaque action lit ou
    modifie le même magasin, et les assertions portent sur l'effet obtenu.
    """
    from argparse import Namespace

    from monl_platform import administration
    from monl_platform.service import CompilationService

    magasin = IdentityStore(tmp_path)
    service = CompilationService(tmp_path)
    user = magasin.register("direct@exemple.test", MOT_DE_PASSE)
    project_id = "projet-direct"
    magasin.add_project(user["id"], project_id, "Projet direct")
    key = magasin.create_api_key(user["id"], "poste")

    assert administration._date(None) == "—"
    assert administration._echeance(None) == "jamais"
    assert administration._comptes(magasin, service, Namespace()) == 0
    assert "direct@exemple.test" in capsys.readouterr().out

    administration._compte(magasin, service, Namespace(email="direct@exemple.test"))
    detail = capsys.readouterr().out
    assert project_id in detail and key["id"] in detail
    administration._projets(magasin, service, Namespace(compte=None))
    assert project_id in capsys.readouterr().out

    administration._codes(magasin, service,
                          Namespace(email="direct@exemple.test"))
    codes = [line.strip() for line in capsys.readouterr().out.splitlines()
             if line.startswith("  ")]
    assert len(codes) == 8
    assert magasin.consume_recovery_code(
        user["email"], codes[0], "Nouveau-MotDePasse-2026")

    assert administration._prolonger(
        magasin, service, Namespace(projet=project_id, jours=2, jamais=False)
    ) == 0
    assert administration._expirer(
        magasin, service, Namespace(projet=project_id)
    ) == 0
    assert administration._revoquer(
        magasin, service, Namespace(cle=key["id"])
    ) == 0
    assert administration._supprimer(
        magasin, service,
        Namespace(email="direct@exemple.test", confirmer=False)
    ) == 1
    capsys.readouterr()
    assert administration._supprimer(
        magasin, service,
        Namespace(email="direct@exemple.test", confirmer=True)
    ) == 0
    assert magasin.compte_par_adresse("direct@exemple.test") is None


def test_la_cli_nomme_les_entrees_invalides_et_les_positions_d_options(tmp_path, capsys):
    from argparse import Namespace

    from monl_platform import administration

    magasin = IdentityStore(tmp_path)
    with pytest.raises(SystemExit) as erreur:
        administration._compte_ou_sortir(magasin, "absent@exemple.test")
    assert erreur.value.code == 1
    assert "Aucun compte" in capsys.readouterr().err

    assert administration._prolonger(
        magasin, None, Namespace(projet="absent", jours=30, jamais=False)
    ) == 1
    assert administration._expirer(
        magasin, None, Namespace(projet="absent")
    ) == 1
    assert administration._revoquer(
        magasin, None, Namespace(cle="absent")
    ) == 1
    capsys.readouterr()

    # Le parseur accepte --workspace avant ET après le sous-verbe.
    assert administration.main(["--workspace", str(tmp_path), "comptes"]) == 0
    assert administration.main(["comptes", "--workspace", str(tmp_path)]) == 0
    assert "Aucun compte" in capsys.readouterr().out
