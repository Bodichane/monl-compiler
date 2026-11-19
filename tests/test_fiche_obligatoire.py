"""Brick 17: "no ordering without being identified" — point 90.

Why this brick. On `projets/SneakerLab`, two real orders carried an account
with NO customer record at all:

    commande 10  compte 7  login=sondeur  fiche=— AUCUNE —
    commande 11  compte 7  login=sondeur  fiche=— AUCUNE —

Nothing required creating a record before ordering, and the account registry
(`_monl_users`) is exposed by no route — deliberately, it carries password
hashes. The administrator therefore saw an order they could assign to nobody:
no name, no address, no way to get one. For a shop, it is not a display
defect, it is an **unshippable order**.

Two paths existed. Exposing the account identity to allowed roles would have
given the login — but a login cannot be shipped to, and it eroded the
promise of the `generated` pseudonym (brick 7). Guaranteeing the record fixes
the substance without touching authentication: that is the path chosen.

What the brick decides, and what did not go without saying:

* **the check comes FIRST**, before the parent check and before any
  calculation. A caller without a record need not learn whether a product
  exists, nor consume stock on the way;
* **409, not 403.** It is not a missing right — it is a state to fix, and the
  message says which. A 403 would suggest the account is badly provisioned;
* **the record is looked up by ACCOUNT id**, through `_identity_fk_columns` —
  point 88's single source. Finding it otherwise would rewrite half of the bug
  that point fixed;
* **only `Create` can require it.** On a read or an update, the record
  already exists: requiring a record afterwards would make inaccessible data
  one owns.
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
from tests.support.processus import arreter_processus
from tests.support.server import free_port as _port_libre

SPEC = """app BancFiche

entity Commande
    statut: String

entity Client
    nom: String

relation Client hasMany Commande
relation Client hasMany Client

actor Client selfRegister
actor Patron

rule Commande.statut required
rule Client.nom required
rule Commande.Read ownedBy Client
rule Client.Read ownedBy Client
rule Client.Delete ownedBy Client
rule Commande.Create requiresOwn Client

workflow Acheter for Client
    Create Commande
    Read Commande
    Create Client
    Read Client
    # POINT 96: `Delete Client` tests the rule's COUNTERPART. Without this
    # action, the brick had no way to be caught out — and it was: `requiresOwn`
    # guarded creation, and nothing then prevented deleting one's record while
    # leaving the order without a recipient.
    Delete Client

workflow Gerer for Patron
    Read Commande
    Read Client
"""

SANS_REGLE = SPEC.replace("rule Commande.Create requiresOwn Client\n", "")


def _valide(spec):
    return MonlAST(parse_monl_string(spec)).validate_and_audit()


# --------------------------------------------------------------------------
# What compilation must refuse
# --------------------------------------------------------------------------

def test_the_bench_spec_compiles(capsys):
    """The witness of the refusals that follow."""
    ast = _valide(SPEC)
    assert ast["security"]["required_profiles"] == {"Commande": "Client"}
    capsys.readouterr()


def test_a_reference_without_action_is_refused(capsys):
    """Refused by the GRAMMAR, not the validator: the `REFERENCE` token requires
    the dot. The validator still carries the guard, like its eight sibling rules
    — written here so that the day the grammar loosens, the deciding layer is
    chosen and not discovered."""
    from monl.parser import MonlSyntaxError

    with pytest.raises(MonlSyntaxError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Commande requiresOwn Client"))
    assert "an Entity.field or Entity.Action reference" in str(refus.value)
    capsys.readouterr()


def test_a_nonexistent_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Fantome.Create requiresOwn Client"))
    assert "does not exist" in str(refus.value)
    capsys.readouterr()


def test_an_action_other_than_create_is_refused(capsys):
    """On Read/Update/Delete, the record already exists: the record can no longer
    prevent anything, it would only make inaccessible what one owns."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Commande.Update requiresOwn Client"))
    assert "Create" in str(refus.value)
    capsys.readouterr()


def test_requiring_a_nonexistent_entity_is_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("requiresOwn Client", "requiresOwn Fantome"))
    assert "not a declared entity" in str(refus.value)
    capsys.readouterr()


def test_an_entity_cannot_require_itself(capsys):
    """The first record could never be created."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC.replace("rule Commande.Create requiresOwn Client",
                             "rule Client.Create requiresOwn Client"))
    assert "cannot require itself" in str(refus.value)
    capsys.readouterr()


def test_requiring_an_entity_nobody_owns_is_refused(capsys):
    """"Owning one" only makes sense if ownership is deduced from the token.
    Without an 'ownedBy' rule leading to an actor, the question has no answer."""
    # BOTH ownership rules must go: since point 96 the bench also carries
    # 'Client.Delete ownedBy Client', and a single one is enough for ownership
    # to be deduced from the token.
    sans_propriete = (SPEC.replace("rule Client.Read ownedBy Client\n", "")
                          .replace("rule Client.Delete ownedBy Client\n", ""))
    with pytest.raises(ASTValidationError) as refus:
        _valide(sans_propriete)
    assert "is not owned by any actor" in str(refus.value)
    capsys.readouterr()


def test_a_public_creation_is_refused(capsys):
    """Without an identified caller, no record can be looked up. Same refusal as
    'generated' and 'payable', same reason."""
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.Create public\n")
    assert "public" in str(refus.value)
    capsys.readouterr()


def test_two_rules_on_the_same_entity_are_refused(capsys):
    with pytest.raises(ASTValidationError) as refus:
        _valide(SPEC + "rule Commande.Create requiresOwn Client\n")
    assert "only one is allowed" in str(refus.value)
    capsys.readouterr()


# --------------------------------------------------------------------------
# What generation must write
# --------------------------------------------------------------------------

def _compile(dossier, spec, capsys):
    dossier.mkdir(parents=True, exist_ok=True)
    (dossier / "spec.ml").write_text(spec, encoding="utf-8")
    compile_project(str(dossier / "spec.ml"), str(dossier))
    capsys.readouterr()
    return (dossier / "app.py").read_text(encoding="utf-8")


def test_the_rule_really_changes_the_output(tmp_path, capsys):
    """Point 85's discipline: no brick leaves without this test."""
    assert _compile(tmp_path / "a", SPEC, capsys) != _compile(tmp_path / "b",
                                                             SANS_REGLE, capsys)


def test_the_check_is_the_very_first_query(tmp_path, capsys):
    """What decides the order: a caller without a record must learn nothing about
    the catalog, and above all consume nothing. Placed after the parent check or
    after a 'derivedFrom' calculation, it would leak the existence of a linked
    record — and, on an entity that counts stock, it would let the counting
    happen before the refusal."""
    genere = _compile(tmp_path, SPEC, capsys)
    creation = genere.split("def create_commande")[1].split("@app.")[0]
    premiere = next(li for li in creation.splitlines() if "cursor.execute(" in li)
    assert 'SELECT 1 FROM "client"' in premiere, creation


def test_the_record_is_looked_up_by_account_id(tmp_path, capsys):
    """POINT 88: the ownership column of an entity created by its holder carries
    an ACCOUNT id, not the row's `id`. Looking up `WHERE id = ?` would find
    someone else's record as soon as the two diverge."""
    genere = _compile(tmp_path, SPEC, capsys)
    creation = genere.split("def create_commande")[1].split("@app.")[0]
    ligne = next(li for li in creation.splitlines() if 'SELECT 1 FROM "client"' in li)
    assert '"client_id" = ?' in ligne
    assert "current_user_id" in ligne


def test_the_contract_announces_the_prerequisite(tmp_path, capsys):
    """Without this note, an interface AI builds a checkout funnel that hits a
    409 on the last screen — the only place where the user has already filled
    everything in."""
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    capsys.readouterr()
    contrat = json.loads((tmp_path / "frontend_contract.json").read_text(encoding="utf-8"))
    route = next(r for r in contrat["routes"]
                 if r["method"] == "POST" and r["path"] == "/commande")
    assert route["requires_own"] == "Client"
    assert "PREREQUISITE" in route["note"]
    assert "BEFORE" in route["note"], "le contrat doit dire QUAND, pas seulement quoi"


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
        with err:
            brut = err.read()
            try:
                return err.code, json.loads(brut or b"{}")
            except ValueError:
                return err.code, {"brut": brut[:300].decode("utf-8", "replace")}


def _compte(base, nom):
    _appel(base + "/register", {"username": nom, "password": "motdepasse1",
                                "actor": "Client"})
    _, jeton = _appel(base + "/login", {"username": nom, "password": "motdepasse1"})
    return jeton["access_token"]


@pytest.fixture
def boutique(tmp_path):
    (tmp_path / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(tmp_path / "spec.ml"), str(tmp_path))
    port = _port_libre()
    processus = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app:app", "--host", "127.0.0.1",
         "--port", str(port)],
        cwd=str(tmp_path), stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(120):
            if processus.poll() is not None:
                pytest.fail(processus.stdout.read().decode("utf-8", "replace")[-2000:])
            try:
                with urllib.request.urlopen(base + "/docs", timeout=5) as reponse:
                    reponse.read()
                break
            except OSError:
                time.sleep(0.25)
        else:
            pytest.fail("le serveur n'a jamais répondu")
        yield base, tmp_path
    finally:
        arreter_processus(processus, delai=10)


def test_ordering_without_a_record_is_refused_and_creates_nothing(boutique):
    base, _ = boutique
    jeton = _compte(base, "zoe")

    code, reponse = _appel(base + "/commande", {"statut": "panier"}, jeton)
    assert code == 409
    assert "Client profile" in reponse["detail"]

    _, liste = _appel(base + "/commande", jeton=jeton)
    assert liste["total"] == 0, "un refus ne doit rien avoir créé"


def test_the_created_record_opens_ordering(boutique):
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _appel(base + "/client", {"nom": "Zoé Martin"}, jeton)

    code, _ = _appel(base + "/commande", {"statut": "panier"}, jeton)
    assert code == 200


def test_someone_elses_record_is_not_enough(boutique):
    """THE brick's test. A check written "is there at least one record?" would
    pass here — and the first record created in the shop would open ordering to
    everyone. The proof therefore requires TWO accounts, only one of which has
    its record."""
    base, _ = boutique
    avec = _compte(base, "zoe")
    _appel(base + "/client", {"nom": "Zoé Martin"}, avec)
    sans = _compte(base, "bob")

    code, reponse = _appel(base + "/commande", {"statut": "panier"}, sans)
    assert code == 409, "la fiche de Zoé ne doit rien ouvrir à Bob"
    assert "Client profile" in reponse["detail"]


def test_every_order_is_now_assignable(boutique):
    """The hole the brick closes, stated the right way round: after it, there can
    no longer be an order whose holder is unknown."""
    import sqlite3

    base, dossier = boutique
    for nom in ("zoe", "bob"):
        jeton = _compte(base, nom)
        _appel(base + "/client", {"nom": nom.title()}, jeton)
        _appel(base + "/commande", {"statut": "panier"}, jeton)

    conn = sqlite3.connect(dossier / "app.db")
    orphelines = conn.execute(
        'SELECT COUNT(*) FROM commande WHERE client_id NOT IN '
        '(SELECT client_id FROM client)').fetchone()[0]
    conn.close()
    assert orphelines == 0


# --------------------------------------------------------------------------
# POINT 96: the counterpart on DELETION
# --------------------------------------------------------------------------

def test_deleting_ones_last_record_with_an_order_is_refused(boutique):
    """THE hole, measured on `projets/SneakerLab` by comparing the journey with a
    classic shop's: `DELETE /customer` answered 200 and left 1 order for 0
    records. `requiresOwn` had guarded CREATION since point 90; the hole reopened
    from the other end, and the resulting state was exactly the one that point
    exists to prevent — an order the administrator can assign to nobody."""
    base, dossier = boutique
    jeton = _compte(base, "zoe")
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, jeton)
    _appel(base + "/commande", {"statut": "panier"}, jeton)

    code, reponse = _appel(f"{base}/client/{fiche['id']}", jeton=jeton, methode="DELETE")

    assert code == 409, reponse
    assert "Commande" in reponse["detail"]
    conn = sqlite3.connect(str(dossier / "app.db"))
    assert conn.execute("SELECT COUNT(*) FROM client").fetchone()[0] == 1
    conn.close()


def test_without_an_order_the_record_stays_deletable(boutique):
    """THE witness, and it counts as much: a guard refusing every deletion would
    pass the previous test while guaranteeing nothing, and would make the
    account impossible to close."""
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, jeton)

    code, reponse = _appel(f"{base}/client/{fiche['id']}", jeton=jeton, methode="DELETE")

    assert code == 200, reponse


def test_the_second_to_last_record_stays_deletable(boutique):
    """`requiresOwn` requires "at least one": as long as one remains, the order
    stays attached. Refusing here would be stricter than the rule."""
    base, _ = boutique
    jeton = _compte(base, "zoe")
    _, premiere = _appel(base + "/client", {"nom": "Zoé"}, jeton)
    _, seconde = _appel(base + "/client", {"nom": "Zoé pro"}, jeton)
    _appel(base + "/commande", {"statut": "panier"}, jeton)

    code, reponse = _appel(f"{base}/client/{seconde['id']}", jeton=jeton, methode="DELETE")
    assert code == 200, reponse
    # …but the LAST one stays protected.
    code, _ = _appel(f"{base}/client/{premiere['id']}", jeton=jeton, methode="DELETE")
    assert code == 409


def test_ANOTHER_accounts_record_does_not_protect_mine(boutique):
    """The test trap, again: with a single account, "is there a record
    somewhere?" would pass. The count must be about MY account."""
    base, _ = boutique
    zoe = _compte(base, "zoe")
    autre = _compte(base, "max")
    _appel(base + "/client", {"nom": "Max"}, autre)
    _, fiche = _appel(base + "/client", {"nom": "Zoé"}, zoe)
    _appel(base + "/commande", {"statut": "panier"}, zoe)

    code, _ = _appel(f"{base}/client/{fiche['id']}", jeton=zoe, methode="DELETE")

    assert code == 409, "la fiche d'un autre compte a été comptée comme la mienne"
