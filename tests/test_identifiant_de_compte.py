"""Inscription par e-mail ou téléphone — point 95.

`capability auth` était déclaratif depuis la brique 1 : le bloc se parsait, se
validait, traversait tout le pipeline et ne changeait RIEN à la génération.
C'est sa première vraie fonction — contraindre la FORME de l'identifiant de
compte.

Ce que la brique décide, et qui ne va pas de soi :

* **le champ reste `username` SUR LE FIL.** Le renommer en `email` aurait cassé
  le formulaire d'inscription de tout projet existant pour un gain cosmétique.
  C'est le CONTRAT qui dit quelle forme il attend, et l'IA d'interface qui
  étiquette l'écran ;
* **la substance n'est pas la validation, c'est la NORMALISATION.**
  `Jean@Ex.com` et `jean@ex.com` sont la même boîte, `06 12 34 56 78` et
  `+33612345678` le même numéro. Sans forme canonique, l'unicité est
  contournable — deux comptes pour une personne — et la connexion échoue selon
  la façon dont on tape ;
* **la même normalisation aux TROIS endroits** : `/register`, `/login` et
  `manage.py`. Un seul oubli crée des comptes auxquels on ne peut pas se
  connecter ;
* **rien n'est déclaré = rien ne change.** Toute spec écrite avant ce point
  compile à l'identique. Deviner « email par défaut » verrouillerait tous les
  projets existants au premier recompilage.
"""
import json
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

from monl.ast_validator import ASTValidationError, MonlAST
from monl.cli import compile_project
from monl.parser import parse_monl_string
from tests.support.server import free_port as _port_libre

SPEC = """app BancIdentifiant

entity Note
    texte: String

relation Client hasMany Note

actor Client selfRegister
actor Patron

rule Note.Read ownedBy Client

capability auth
    identifier: email, phone

workflow Ecrire for Client
    Create Note
    Read Note
"""

SANS_FORME = SPEC.replace("capability auth\n    identifier: email, phone\n",
                          "capability auth\n")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# Ce que la compilation accepte et refuse
# --------------------------------------------------------------------------

def test_les_formes_declarees_traversent_last(capsys):
    ast = _valide(SPEC)
    assert ast["security"]["auth_identifier"] == ["email", "phone"]
    capsys.readouterr()


def test_sans_declaration_aucune_contrainte(capsys):
    """None et non [] : « rien de déclaré » n'est pas « aucune forme valide »."""
    assert _valide(SANS_FORME)["security"]["auth_identifier"] is None
    capsys.readouterr()


def test_une_forme_inconnue_est_refusee(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("identifier: email, phone", "identifier: pigeon"))
    assert "pigeon" in str(refus.value)
    capsys.readouterr()


def test_libre_cumule_avec_une_forme_stricte_est_refuse(capsys):
    """'libre' accepte tout : le cumuler annule l'autre sans le dire. Une règle
    écrite qui ne produit rien, c'est exactement ce que le point 85 refuse."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("identifier: email, phone", "identifier: email, libre"))
    assert "libre" in str(refus.value)
    capsys.readouterr()


def test_identifier_hors_de_auth_est_refuse(capsys):
    """C'est l'inscription qu'il contraint : ailleurs, il ne voudrait rien dire."""
    spec = SPEC.replace("capability auth\n    identifier: email, phone",
                        "capability auth\ncapability payment\n    identifier: email")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "auth" in str(refus.value)
    capsys.readouterr()


def test_une_spec_sans_bloc_indente_compile_comme_avant(tmp_path, capsys):
    """LE témoin de compatibilité : le bloc indenté est optionnel, et une brique
    dormante qui se réveille ne doit rien casser de ce qui existait."""
    (tmp_path / "a.ml").write_text(SANS_FORME, encoding="utf-8")
    compile_project(str(tmp_path / "a.ml"), str(tmp_path / "a"))
    genere = (tmp_path / "a" / "app.py").read_text(encoding="utf-8")
    capsys.readouterr()
    assert "AUTH_IDENTIFIER_FORMS = []" in genere
    # La fonction existe quand même : un seul chemin de code, exercé partout.
    assert "def _normalize_identifier" in genere


# --------------------------------------------------------------------------
# Le comportement, contre un vrai serveur
# --------------------------------------------------------------------------

def _appel(url, corps=None, jeton=None, methode=None):
    donnees = json.dumps(corps).encode() if corps is not None else None
    requete = urllib.request.Request(url, data=donnees, method=methode)
    requete.add_header("Content-Type", "application/json")
    if jeton:
        requete.add_header("Authorization", f"Bearer {jeton}")
    try:
        with urllib.request.urlopen(requete, timeout=10) as reponse:
            return reponse.status, json.loads(reponse.read() or b"{}")
    except urllib.error.HTTPError as err:
        try:
            brut = err.read()
            return err.code, json.loads(brut or b"{}")
        except ValueError:
            return err.code, {"detail": brut.decode("utf-8", "replace")}
        finally:
            err.close()


@pytest.fixture
def serveur(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def _degeler(dossier):
    """La limitation de débit (5 essais/minute) répondrait à la place de la
    brique : ce n'est pas elle qu'on éprouve ici."""
    conn = sqlite3.connect(str(dossier / "app.db"))
    conn.execute("DELETE FROM _monl_rate_limit")
    conn.commit()
    conn.close()


def _inscrire(base, dossier, login, mdp="motdepasse1"):
    _degeler(dossier)
    return _appel(base + "/register",
                  {"username": login, "password": mdp, "actor": "Client"})


def _connecter(base, dossier, login, mdp="motdepasse1"):
    _degeler(dossier)
    return _appel(base + "/login", {"username": login, "password": mdp})


@pytest.mark.parametrize("bon", ["alice@exemple.fr", "+33 6 12 34 56 78",
                                 "0612345699", "a.b+c@sous.domaine.co.uk"])
def test_les_formes_declarees_sont_acceptees(serveur, bon):
    base, dossier = serveur
    code, reponse = _inscrire(base, dossier, bon)
    assert code == 200, reponse


@pytest.mark.parametrize("mauvais", ["alice", "pas-un-courriel", "alice@",
                                     "@exemple.fr", "12345", "alice exemple.fr"])
def test_les_autres_formes_sont_refusees(serveur, mauvais):
    base, dossier = serveur
    code, reponse = _inscrire(base, dossier, mauvais)
    assert code == 422, reponse


def test_deux_ecritures_de_la_meme_adresse_sont_UN_seul_compte(serveur):
    """LE cœur de la brique. Sans forme canonique, le contrôle d'unicité est
    contournable en changeant une majuscule : deux comptes pour une personne,
    et le second reçoit les commandes du premier."""
    base, dossier = serveur
    assert _inscrire(base, dossier, "alice@exemple.fr")[0] == 200

    code, reponse = _inscrire(base, dossier, "Alice@Exemple.FR")

    assert code == 409, reponse
    # Et le message nomme ce qui est vraiment en conflit.
    assert "adresse" in reponse["detail"] or "identifiant" in reponse["detail"]


def test_deux_ecritures_du_meme_numero_sont_UN_seul_compte(serveur):
    """Un numéro se tape avec des espaces, des points ou des tirets — jamais
    deux fois pareil."""
    base, dossier = serveur
    assert _inscrire(base, dossier, "+33 6 12 34 56 78")[0] == 200
    for variante in ["+33612345678", "+33-6-12-34-56-78", "+33 (6) 12.34.56.78"]:
        code, reponse = _inscrire(base, dossier, variante)
        assert code == 409, f"{variante} a créé un second compte : {reponse}"


@pytest.mark.parametrize("variante", ["alice@exemple.fr", "Alice@Exemple.FR",
                                      "  alice@exemple.fr  ", "ALICE@EXEMPLE.FR"])
def test_on_se_reconnecte_quelle_que_soit_la_facon_de_taper(serveur, variante):
    """L'AUTRE moitié, et celle qu'on oublie : normaliser d'un seul côté crée
    des comptes auxquels on ne peut plus se connecter."""
    base, dossier = serveur
    _inscrire(base, dossier, "alice@exemple.fr")
    code, reponse = _connecter(base, dossier, variante)
    assert code == 200, reponse


def test_un_identifiant_mal_forme_a_la_connexion_ne_revele_rien(serveur):
    """401 et non 422 : la connexion ne doit pas apprendre à un attaquant quelle
    forme les comptes ont — un identifiant mal formé n'existe simplement pas."""
    base, dossier = serveur
    code, _ = _connecter(base, dossier, "alice")
    assert code == 401


def test_le_jeton_porte_la_forme_canonique(serveur):
    """`sub` sert d'identité dans tout le backend : y laisser la casse tapée
    ferait deux identités pour un compte."""
    import base64
    base, dossier = serveur
    _inscrire(base, dossier, "alice@exemple.fr")
    _, reponse = _connecter(base, dossier, "Alice@Exemple.FR")
    corps = reponse["access_token"].split(".")[1]
    corps += "=" * (-len(corps) % 4)
    assert json.loads(base64.urlsafe_b64decode(corps))["sub"] == "alice@exemple.fr"


def test_manage_py_normalise_comme_le_serveur(serveur):
    """Le troisième endroit, celui qu'on oublie. Un compte provisionné hors
    ligne avec 'Patron@Ex.com' serait stocké tel quel, et la connexion — qui
    normalise — chercherait 'patron@ex.com' : un compte tout neuf auquel on ne
    peut pas se connecter."""
    base, dossier = serveur
    proc = subprocess.run(
        [sys.executable, "manage.py", "adduser", "Patron@Exemple.FR", "Patron"],
        cwd=str(dossier), input="motdepasse1\nmotdepasse1\n",
        capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stdout + proc.stderr

    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute(
            "SELECT username FROM _monl_users WHERE actor = 'Patron'").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "patron@exemple.fr", "manage.py a stocké la forme tapée"
    code, reponse = _connecter(base, dossier, "Patron@Exemple.FR")
    assert code == 200, reponse


def test_un_compte_anterieur_continue_de_fonctionner(serveur):
    """La règle ne vaut que pour les inscriptions à VENIR. Convertir un compte
    existant est impossible (on n'invente pas une adresse) et le supprimer
    serait pire — le serveur les compte et les nomme au démarrage, comme au
    point 89 pour les horodatages manquants."""
    base, dossier = serveur
    # LE PIÈGE : sans ce compte-ci, l'INSERT ... SELECT ci-dessous ne copie
    # RIEN (table vide), et le test passerait en prouvant l'inverse de ce qu'il
    # annonce — un 401 pour compte inexistant au lieu d'un 401 pour mot de passe
    # faux. Même famille de piège qu'au point 90 (« existe-t-il au moins une
    # fiche ? » passait tant qu'on n'employait qu'UN compte).
    assert _inscrire(base, dossier, "alice@exemple.fr")[0] == 200
    conn = sqlite3.connect(str(dossier / "app.db"))
    # Un compte tel qu'il existait AVANT la déclaration : un pseudo, et le
    # hachage d'un mot de passe connu (celui d'alice, donc 'motdepasse1').
    copies = conn.execute(
        "INSERT INTO _monl_users (username, password_hash, salt, actor, anon_handle)"
        " SELECT 'ancien_pseudo', password_hash, salt, 'Client', 'Anon#4242'"
        " FROM _monl_users WHERE username = 'alice@exemple.fr'").rowcount
    conn.commit()
    conn.close()
    assert copies == 1, "le compte antérieur n'a pas été créé : le test ne prouverait rien"

    code, reponse = _connecter(base, dossier, "ancien_pseudo")

    assert code == 200, f"un compte antérieur doit continuer de se connecter : {reponse}"


def test_le_smoke_test_respecte_la_forme_quil_fait_appliquer(tmp_path, capsys):
    """LE bug trouvé en appliquant la brique à un vrai projet. Le smoke test
    inscrivait un compte nommé 'smoke' en dur : sur toute app déclarant
    `identifier: email`, il recevait 422 sur sa PROPRE inscription et déclarait
    l'application cassée. Le vérificateur ne peut pas ignorer une règle qu'il
    fait par ailleurs appliquer.

    Vu sur `projets/SneakerLab` : trois erreurs (`/register` 422, `/login` 401,
    `POST /customer` 401) qui ne venaient ni du backend ni du frontend, mais de
    monl lui-même."""
    from monl.smoke_test import run_smoke_test

    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()

    ok, erreurs, _avertissements = run_smoke_test(str(tmp_path), say=lambda *_: None)

    assert ok, erreurs


def test_lidentifiant_du_smoke_suit_la_forme_declaree():
    """Trois formes, trois identifiants — et des identifiants DISTINCTS par
    rang : la boucle d'élévation de privilège en essaie un par rôle
    provisionné, et deux inscriptions sous le même identifiant donneraient un
    409 qu'on lirait à tort comme un refus de rôle."""
    from monl.smoke_test import _identifiant_smoke

    def contrat(formes):
        return {"api": {"auth": {"register": {"identifier_forms": formes}}}}

    assert _identifiant_smoke(contrat(["email"])) == "smoke@monl.test"
    assert _identifiant_smoke(contrat(["phone"])).startswith("+336")
    assert _identifiant_smoke(contrat([])) == "smoke"
    distincts = {_identifiant_smoke(contrat(["email"]), r) for r in (0, 1, 2)}
    assert len(distincts) == 3


# --------------------------------------------------------------------------
# L'indicatif : '06…' et '+336…' sont la même ligne — si on sait d'où
# --------------------------------------------------------------------------

SPEC_PREFIXE = SPEC.replace('    identifier: email, phone\n',
                            '    identifier: email, phone\n    phone_prefix: "+33"\n')


def test_un_indicatif_mal_forme_est_refuse(capsys):
    for mauvais in ['"33"', '"+"', '"+abc"', '"+123456"']:
        with pytest.raises(ASTValidationError) as refus:
            _valide(SPEC_PREFIXE.replace('"+33"', mauvais))
        assert "indicatif" in str(refus.value)
    capsys.readouterr()


def test_un_indicatif_sans_forme_phone_est_refuse(capsys):
    """Il ne s'appliquerait à rien : une règle écrite qui ne produit rien est
    exactement ce que le point 85 refuse."""
    spec = SPEC_PREFIXE.replace("identifier: email, phone", "identifier: email")
    with pytest.raises(ASTValidationError) as refus:
        _valide(spec)
    assert "phone" in str(refus.value)
    capsys.readouterr()


def test_le_contrat_transmet_lindicatif_au_frontend(tmp_path, capsys):
    (tmp_path / "spec.ml").write_text(SPEC_PREFIXE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    contrat = json.loads(
        (tmp_path / "frontend_contract.json").read_text(encoding="utf-8")
    )
    inscription = contrat["api"]["auth"]["register"]
    assert inscription["identifier_forms"] == ["email", "phone"]
    assert inscription["phone_prefix"] == "+33"
    assert "+33" in inscription["note"]
    assert "+33" in (tmp_path / "FRONTEND_PROMPT.md").read_text(encoding="utf-8")
    capsys.readouterr()


@pytest.fixture
def serveur_prefixe(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC_PREFIXE, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def test_national_et_international_sont_UN_seul_compte(serveur_prefixe):
    """LE trou trouvé en éprouvant la brique sur le vrai site : '06 12 34 56 78'
    et '+33612345678' désignent la même ligne et faisaient deux comptes. monl ne
    peut pas le deviner — l'indicatif dépend du pays — alors il le fait
    DÉCLARER."""
    base, dossier = serveur_prefixe
    assert _inscrire(base, dossier, "06 12 34 56 78")[0] == 200
    for variante in ["+33612345678", "+33 6 12 34 56 78", "0612345678"]:
        code, reponse = _inscrire(base, dossier, variante)
        assert code == 409, f"{variante} a créé un second compte : {reponse}"


def test_la_forme_stockee_est_linternationale(serveur_prefixe):
    """La forme canonique doit être celle qui ne dépend pas du pays : c'est
    elle qu'on enverra un jour à un prestataire, et elle ne se relit pas."""
    base, dossier = serveur_prefixe
    _inscrire(base, dossier, "06 12 34 56 78")
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute(
            "SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+33612345678"


@pytest.mark.parametrize("notation", ["06 12 34 56 78", "+33612345678",
                                      "0612345678", "+33 6 12 34 56 78"])
def test_on_se_connecte_dans_les_deux_notations(serveur_prefixe, notation):
    base, dossier = serveur_prefixe
    _inscrire(base, dossier, "06 12 34 56 78")
    code, reponse = _connecter(base, dossier, notation)
    assert code == 200, reponse


def test_sans_indicatif_declare_les_deux_notations_restent_distinctes(serveur):
    """La limite ÉNONCÉE, et son témoin. Sans `phone_prefix`, monl ignore de
    quel pays vient un '06…' : il ne le rattache à rien plutôt que de deviner
    la France. Le test existe pour que ce comportement soit un choix visible
    et non un oubli — c'est la déclaration qui l'ouvre."""
    base, dossier = serveur
    assert _inscrire(base, dossier, "06 12 34 56 78")[0] == 200
    assert _inscrire(base, dossier, "+33612345678")[0] == 200


# --------------------------------------------------------------------------
# POINT 138 — un pays SANS zéro interurbain
#
# Tout ce qui précède éprouve la France, où le numéro national porte un `0` de
# tête que la forme internationale remplace. La règle avait été écrite depuis
# cet exemple, puis généralisée sans être éprouvée ailleurs : elle ne
# canonicalisait QUE les numéros commençant par zéro.
#
# Au Bénin — marché visé, et pays d'`projets/AtelierNaya` — le numéro local
# s'écrit sans zéro de tête. `phone_prefix: "+229"` ne produisait donc RIEN :
# la personne inscrite en « 97 12 34 56 » ne se reconnaissait pas en
# « +229 97 12 34 56 », soit exactement les deux comptes que l'indicatif
# existe pour empêcher. Une règle déclarée qui ne produit rien est ce que le
# point 85 refuse.
# --------------------------------------------------------------------------
SPEC_BENIN = SPEC.replace('    identifier: email, phone\n',
                          '    identifier: phone\n    phone_prefix: "+229"\n')


@pytest.fixture
def serveur_benin(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC_BENIN, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if proc.poll() is not None:
                pytest.fail(proc.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5):
                    pass
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)
        if proc.stdout is not None:
            proc.stdout.close()


def test_un_numero_sans_zero_de_tete_est_bien_internationalise(serveur_benin):
    """Le cœur du défaut. Avant, la forme STOCKÉE restait « 97123456 » — un
    numéro qu'aucun prestataire ne sait joindre et qui ne se relit pas hors du
    Bénin."""
    base, dossier = serveur_benin
    assert _inscrire(base, dossier, "97 12 34 56")[0] == 200
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute("SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+22997123456"


@pytest.mark.parametrize("notation", ["97123456", "97 12 34 56", "97-12-34-56",
                                      "+22997123456", "+229 97 12 34 56",
                                      "22997123456"])
def test_toutes_les_facons_decrire_un_numero_beninois_ouvrent_le_meme_compte(
        serveur_benin, notation):
    base, dossier = serveur_benin
    _inscrire(base, dossier, "97123456")
    code, reponse = _connecter(base, dossier, notation)
    assert code == 200, reponse


def test_un_numero_deja_international_nest_pas_prefixe_deux_fois(serveur_benin):
    """Le piège que la correction pouvait introduire : « 22997123456 », tapé
    sans le `+`, ne doit pas devenir « +22922997123456 » — ce serait un
    TROISIÈME compte, créé par la correction elle-même."""
    base, dossier = serveur_benin
    assert _inscrire(base, dossier, "22997123456")[0] == 200
    connexion = sqlite3.connect(str(dossier / "app.db"))
    try:
        stocke = connexion.execute("SELECT username FROM _monl_users").fetchone()[0]
    finally:
        connexion.close()
    assert stocke == "+22997123456"
    assert _inscrire(base, dossier, "97123456")[0] == 409


def test_manage_py_normalise_comme_le_serveur_sans_zero_de_tete(serveur_benin):
    """Point 95, le troisième endroit — celui qu'on oublie. Diverger ici crée
    un compte que `manage.py` sait écrire et que personne ne sait ouvrir."""
    base, dossier = serveur_benin
    sortie = subprocess.run(
        [sys.executable, "manage.py", "adduser", "97 99 88 77", "Patron"],
        cwd=str(dossier), input="motdepasse1\nmotdepasse1\n",
        capture_output=True, text=True, timeout=60)
    assert sortie.returncode == 0, sortie.stdout + sortie.stderr
    code, reponse = _connecter(base, dossier, "+22997998877")
    assert code == 200, reponse
