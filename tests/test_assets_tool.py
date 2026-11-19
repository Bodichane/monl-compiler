"""Brick 13, LAYER 2 — `monl assets add` / `monl assets list` (point 84).

Why this file exists, and what it guards. Layer 2 is a tool that WRITES INTO
THE SPEC: it is the first time in the project that something other than the
guided dialogue modifies the human's source file. Two properties must
therefore be protected, and neither can be checked by rereading:

* **it writes, the compiler proves.** Every edit is reparsed and revalidated
  with `base_dir` before being written. A failure must leave nothing behind:
  neither a half-modified spec nor a copied file. It is the only reason layer 2
  cannot produce what layer 1 refuses;
* **it does not destroy comments.** A real project's spec is more than half
  comments, and they explain which brick does what. A parse → regenerate
  round trip would have been shorter to write and would have erased the
  project's documentation to place a photo.

The rest is about refusals: an ambiguous designation would write the photo on
the wrong record, and nobody would see it before going online.
"""
import json
import os

import pytest

from monl.assets_tool import (
    AssetsToolError,
    ajouter_asset,
    lister_assets,
    sluggify,
)
from monl.ast_validator import MonlAST
from monl.parser import parse_monl_string
from tests.support.cas import check_each_case

SPEC = """app BancOutil

# This comment, and all the others, must survive the tool.
entity Produit
    nom: String
    prix: Money
    photo: Image

entity Maison
    nom: String

actor Client selfRegister

rule Produit.nom required
rule Maison.nom required
rule Produit.Read public
rule Maison.Read public

workflow Voir for Client
    Read Produit
    Read Maison

# Two records, one with a Nordic name: the slug must stay readable.
seed Produit
    nom: "Halo RS", prix: 149.0   # la vedette du catalogue
    nom: "Sørlund Deck", prix: 89.0

seed Maison
    nom: "Sørlund Deck"
"""


def _project(racine, spec=SPEC):
    """A spec on disk and two DISTINCT source files.

    Distinct on purpose: that is what makes the overwrite check observable — two
    identical files would pass for idempotence."""
    (racine / "source").mkdir(exist_ok=True)
    (racine / "source" / "photo une.png").write_bytes(b"\x89PNG\r\n\x1a\nUNE")
    (racine / "source" / "photo deux.png").write_bytes(b"\x89PNG\r\n\x1a\nDEUX")
    (racine / "source" / "logo.svg").write_text('<svg viewBox="0 0 8 8"/>')
    chemin = racine / "spec.ml"
    chemin.write_text(spec, encoding="utf-8")
    return chemin


def _always_compiles(spec_path, project_dir):
    """Does the resulting spec pass the REAL validator, base_dir included?"""
    return MonlAST(parse_monl_string(spec_path.read_text(encoding="utf-8")),
                   base_dir=str(project_dir)).validate_and_audit()


# --------------------------------------------------------------------------
# The witness, and the two properties to protect
# --------------------------------------------------------------------------

def test_placing_a_photo_copies_and_declares_it(tmp_path, capsys):
    """The witness of all the refusals that follow: without it, a tool refusing
    EVERYTHING would pass each of them."""
    spec = _project(tmp_path)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert rapport["fichier"] == "assets/halo-rs.png"
    assert rapport["ou"] == "Produit.photo"
    assert (tmp_path / "assets" / "halo-rs.png").exists()
    ast = _always_compiles(spec, tmp_path)
    assert ast["seeds"][0]["rows"][0]["photo"] == "assets/halo-rs.png"
    capsys.readouterr()


def test_comments_and_other_fields_survive(tmp_path, capsys):
    """The property a parse → regenerate round trip would have destroyed.

    The END-OF-LINE comment counts as much as the others: it is the only one the
    textual edit really risks eating, since it lives on the very line being
    rewritten."""
    spec = _project(tmp_path)
    avant = spec.read_text(encoding="utf-8")
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    apres = spec.read_text(encoding="utf-8")

    assert avant.count("#") == apres.count("#")
    assert "# This comment, and all the others" in apres
    assert "# la vedette du catalogue" in apres
    ligne = next(li for li in apres.splitlines() if "Halo RS" in li)
    assert ligne.endswith("# la vedette du catalogue")
    assert 'prix: 149.0' in ligne          # the other fields are intact
    assert ligne.startswith("    ")        # l'indentation aussi
    capsys.readouterr()


SPEC_MULTILIGNE = """app BancMulti

entity Produit
    nom: String
    desc: Text
    photo: Image

actor Client selfRegister

rule Produit.nom required
rule Produit.Read public

workflow Voir for Client
    Read Produit

seed Produit
    nom: "Halo RS", desc: "Mousse épaisse,
    et une description qui court sur deux lignes."   # note terminale
    nom: "Deck", desc: "Court."
"""


def test_a_record_on_two_lines_stays_one_record(tmp_path, capsys):
    """`STRING_LITERAL` is compiled with /s: a seed value CAN span several lines,
    and the parser accepts it (checked against the real parser, not assumed).
    Counting content lines instead of RECORDS therefore shifted all the following
    ones — and a photo written on the wrong record produces a perfectly compilable
    spec. Locating works in RANGES for that reason."""
    spec = _project(tmp_path, SPEC_MULTILIGNE)
    r1 = ajouter_asset(str(spec), str(tmp_path),
                       str(tmp_path / "source" / "photo une.png"), pour="Deck")
    r2 = ajouter_asset(str(spec), str(tmp_path),
                       str(tmp_path / "source" / "photo deux.png"), pour="Halo RS")
    assert r1["fichier"] == "assets/deck.png"
    assert r2["fichier"] == "assets/halo-rs.png"

    ast = _always_compiles(spec, tmp_path)
    lignes = ast["seeds"][0]["rows"]
    # Each photo on ITS record: that is the whole point.
    assert lignes[0]["nom"] == "Halo RS" and lignes[0]["photo"] == "assets/halo-rs.png"
    assert lignes[1]["nom"] == "Deck" and lignes[1]["photo"] == "assets/deck.png"
    # The multi-line value and the trailing comment are intact.
    assert "\n" in lignes[0]["desc"]
    assert "# note terminale" in spec.read_text(encoding="utf-8")
    capsys.readouterr()


def test_redeclaring_identically_does_not_touch_the_spec(tmp_path, capsys):
    """Rewriting an identical text would invalidate 'monl run --check''s
    fingerprint — and suggest an evolution that did not happen."""
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    empreinte = spec.read_text(encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "assets" / "halo-rs.png"),
                            pour="Halo RS", nom="halo-rs.png")
    assert rapport["spec_changee"] is False
    assert rapport["deja_en_place"] is True
    assert spec.read_text(encoding="utf-8") == empreinte
    capsys.readouterr()


# --------------------------------------------------------------------------
# The file name
# --------------------------------------------------------------------------

def test_the_slug_stays_readable():
    """"Sørlund" gave "srlund" before the transliteration table: a mute file name
    where the name was readable. The project's catalog already carries a Nordic
    house — the case is not theoretical."""
    table = [
        ("Halo RS", "halo-rs"),
        ("Sørlund Deck", "sorlund-deck"),      # NFKD does not decompose "ø"
        ("Café Crème", "cafe-creme"),
        ("Air 95 — édition", "air-95-edition"),
        ("  ", ""),
    ]

    def cas(texte, attendu):
        assert sluggify(texte) == attendu

    check_each_case(table, cas)


def test_a_source_without_extension_is_refused(tmp_path):
    """Served as is, a file without extension arrives as octet-stream: the
    browser does not display it, and nothing says so."""
    spec = _project(tmp_path)
    (tmp_path / "source" / "sansext").write_bytes(b"\x89PNG")
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "sansext"), pour="Halo RS")
    assert "extension" in str(refus.value)


def test_as_refuses_a_path(tmp_path):
    """--as names a file, not a destination: accepting a path would reopen the
    door layer 1 closes (leaving the project)."""
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Halo RS", nom="../evade.png")
    assert "not a path" in str(refus.value)


# --------------------------------------------------------------------------
# Designation refusals — guessing would write on the wrong record
# --------------------------------------------------------------------------

def test_an_unknown_value_is_refused_with_a_suggestion(tmp_path):
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo")
    assert "'Halo RS'" in str(refus.value)          # the suggestion, not only the refusal


def test_a_value_shared_by_two_entities_is_refused(tmp_path):
    """"Sørlund Deck" names a product AND a house: writing the photo on one of the
    two at random would only show online."""
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Sørlund Deck")
    message = str(refus.value)
    assert "2 rows" in message and "--entity" in message
    # Each candidate is named in English ("Produit row 5"); it read
    # "Produit ligne 5" after the migration, unseen by the check above.
    assert " row " in message and "ligne" not in message, message


def test_entity_leve_lambiguite(tmp_path, capsys):
    """The witness of the refusal above: the announced way out works."""
    spec = _project(tmp_path)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Sørlund Deck", entity="Produit")
    assert rapport["fichier"] == "assets/sorlund-deck.png"
    _always_compiles(spec, tmp_path)
    capsys.readouterr()


def test_an_entity_without_image_field_is_refused_naming_the_remedy(tmp_path):
    """Maison only has Strings: a path would go through unchecked, so the tool
    refuses rather than writing where layer 1 is blind."""
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Sørlund Deck", entity="Maison")
    message = str(refus.value)
    assert "no field of type 'Image'" in message
    assert "photo: Image" in message          # the remedy, not only the refusal


def test_two_image_fields_require_field(tmp_path, capsys):
    spec = _project(tmp_path, SPEC.replace("    photo: Image",
                                          "    photo: Image\n    apercu: Image"))
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    assert "--field" in str(refus.value)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS", field="apercu")
    assert rapport["ou"] == "Produit.apercu"
    _always_compiles(spec, tmp_path)
    capsys.readouterr()


def test_field_on_a_non_image_field_is_refused(tmp_path):
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Halo RS", field="nom")
    assert "not 'Image'" in str(refus.value)


def test_writing_into_an_already_broken_spec_is_refused(tmp_path):
    """Without this check, the revalidation failure would blame the tool for a
    defect that existed before it."""
    spec = _project(tmp_path, SPEC.replace('photo: Image', 'photo: Inconnu'))
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    assert "does not compile as it stands" in str(refus.value)
    assert not (tmp_path / "assets").exists()      # nothing was copied


# --------------------------------------------------------------------------
# Overwriting and rollback
# --------------------------------------------------------------------------

def test_a_different_file_with_the_same_name_is_not_overwritten_without_force(tmp_path, capsys):
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo deux.png"),
                      pour="Halo RS", nom="halo-rs.png")
    assert "--force" in str(refus.value)
    assert (tmp_path / "assets" / "halo-rs.png").read_bytes().endswith(b"UNE")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo deux.png"),
                            pour="Halo RS", nom="halo-rs.png", force=True)
    assert rapport["ecrase"] is True
    assert (tmp_path / "assets" / "halo-rs.png").read_bytes().endswith(b"DEUX")
    capsys.readouterr()


def test_a_compiler_refusal_leaves_nothing_behind(tmp_path, monkeypatch, capsys):
    """The safety net, tested by forcing it.

    The tool is built so that the CLI CANNOT produce an invalid spec: every faulty
    path is intercepted before writing. Rollback is therefore only reachable by
    causing the failure — and a safety net nothing tests is not a net, it is a
    decoration."""
    spec = _project(tmp_path)
    avant = spec.read_text(encoding="utf-8")

    import monl.assets_tool as outil

    def refus(*_a, **_k):
        raise AssetsToolError("refus simulé du compilateur")
    monkeypatch.setattr(outil.commandes, "_revalider", refus)

    with pytest.raises(AssetsToolError):
        outil.ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert spec.read_text(encoding="utf-8") == avant
    assert not (tmp_path / "assets" / "halo-rs.png").exists()
    capsys.readouterr()


def test_a_refusal_after_force_restores_the_previous_file(tmp_path, monkeypatch, capsys):
    """Overwriting under --force must stay reversible during revalidation:
    otherwise a compiler refusal would destroy the old file for nothing."""
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    avant = spec.read_text(encoding="utf-8")

    import monl.assets_tool as outil
    monkeypatch.setattr(outil.commandes, "_revalider",
                        lambda *_a, **_k: (_ for _ in ()).throw(
                            AssetsToolError("refus simulé")))
    with pytest.raises(AssetsToolError):
        outil.ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo deux.png"),
                            pour="Halo RS", nom="halo-rs.png", force=True)
    assert (tmp_path / "assets" / "halo-rs.png").read_bytes().endswith(b"UNE")
    assert spec.read_text(encoding="utf-8") == avant
    assert not (tmp_path / "assets" / "halo-rs.png.monl-precedent").exists()
    capsys.readouterr()


def test_the_old_file_is_reported_orphan_and_kept(tmp_path, capsys):
    """A file placed by the human is not erased on a declaration tool's
    deduction: SneakerLab's frontend hard-codes photos the spec ignores."""
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo deux.png"),
                            pour="Halo RS", nom="vedette.png")
    assert rapport["remplace"] == "assets/halo-rs.png"
    assert rapport["orphelin"] == "assets/halo-rs.png"
    assert (tmp_path / "assets" / "halo-rs.png").exists()
    capsys.readouterr()


# --------------------------------------------------------------------------
# The logo: an 'assets' block created from scratch
# --------------------------------------------------------------------------

def test_the_logo_creates_the_missing_assets_block(tmp_path, capsys):
    """Sending the human to write four lines by hand before being able to place
    their logo would make the tool useless where it serves most."""
    spec = _project(tmp_path)
    assert "assets\n" not in spec.read_text(encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "logo.svg"), cible="logo")
    assert rapport["ou"] == "assets.logo"
    ast = _always_compiles(spec, tmp_path)
    # The logo is declared by its name ALONE: the contract prefixes it with the
    # folder. Writing 'assets/logo.svg' here would give
    # '/site/assets/assets/…'.
    assert ast["assets"]["logo"] == "logo.svg"
    assert ast["assets"]["dir"] == "assets"
    texte = spec.read_text(encoding="utf-8")
    assert texte.index("assets\n") < texte.index("entity Produit")
    capsys.readouterr()


def test_the_favicon_joins_the_existing_block(tmp_path, capsys):
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "logo.svg"), cible="logo")
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), cible="favicon")
    ast = _always_compiles(spec, tmp_path)
    assert ast["assets"] == {"dir": "assets", "logo": "logo.svg",
                             "favicon": "favicon.png"}
    assert spec.read_text(encoding="utf-8").count("assets\n") == 1
    capsys.readouterr()


def test_designating_two_destinations_at_once_is_refused(tmp_path):
    spec = _project(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "logo.svg"))
    assert "--logo" in str(refus.value)
    with pytest.raises(AssetsToolError):
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "logo.svg"),
                      pour="Halo RS", cible="logo")


# --------------------------------------------------------------------------
# What success does not imply
# --------------------------------------------------------------------------

def test_an_existing_database_triggers_the_seed_warning(tmp_path, capsys):
    """The trap met while migrating SneakerLab: the seed only feeds a NEW
    database, so 12 records kept the old path and the site would have shown 12
    empty frames without a word."""
    spec = _project(tmp_path)
    (tmp_path / "app.db").write_bytes(b"SQLite format 3\x00")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert any("NEW database" in m for m in rapport["avertissements"])
    capsys.readouterr()


def test_an_incomplete_credits_file_is_reported_without_being_written(tmp_path, capsys):
    """"monl checks completeness, never truthfulness" (point 83): the tool notes
    the absence, it invents no attribution — and does not write into a file that
    remains a project convention."""
    spec = _project(tmp_path)
    (tmp_path / "assets").mkdir(exist_ok=True)
    credits = tmp_path / "assets" / "CREDITS.json"
    credits.write_text(json.dumps({"photos": []}), encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert any("halo-rs.png" in m and "attribution" in m
               for m in rapport["avertissements"])
    assert json.loads(credits.read_text(encoding="utf-8")) == {"photos": []}
    capsys.readouterr()


# --------------------------------------------------------------------------
# The completeness report
# --------------------------------------------------------------------------

def test_list_tells_declared_present_and_undeclared_apart(tmp_path, capsys):
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "logo.svg"), cible="logo")
    (tmp_path / "assets" / "traine.jpg").write_bytes(b"\xff\xd8\xffJPEG")

    rapport = lister_assets(str(spec), str(tmp_path))
    par_chemin = {li["chemin"]: li for li in rapport["declares"]}
    assert par_chemin["assets/halo-rs.png"]["present"] is True
    assert par_chemin["assets/halo-rs.png"]["origines"] == ["Produit[1].photo"]
    assert par_chemin["logo.svg"]["origines"] == ["assets.logo"]
    assert par_chemin["logo.svg"]["resolu"] == os.path.join("assets", "logo.svg")
    assert rapport["orphelins"] == [os.path.join("assets", "traine.jpg")]
    capsys.readouterr()


def test_list_shows_a_declared_but_missing_asset(tmp_path, capsys):
    """THE defect this test found, and keeps closed.

    The report first loaded the spec with `base_dir` — so validation failed on
    the missing asset itself, and `monl assets list` refused to run in the only
    case where it was useful. The tool now validates FORM without existence, and
    computes presence itself: layer 1's split is what makes it possible."""
    spec = _project(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    os.remove(tmp_path / "assets" / "halo-rs.png")
    rapport = lister_assets(str(spec), str(tmp_path))
    manquants = [li for li in rapport["declares"] if not li["present"]]
    assert [li["chemin"] for li in manquants] == ["assets/halo-rs.png"]
    capsys.readouterr()


def test_add_stays_usable_when_another_asset_is_missing(tmp_path, capsys):
    """The other half of the same defect: revalidating the WHOLE spec with
    base_dir made the tool unusable on a spec declaring two missing photos —
    impossible to place one, the other making revalidation fail. The guarantee is
    about what the tool WRITES, and the other gaps are stated."""
    spec = _project(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8").replace(
        'nom: "Sørlund Deck", prix: 89.0',
        'nom: "Sørlund Deck", prix: 89.0, photo: "assets/jamais-fournie.png"'),
        encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert rapport["fichier"] == "assets/halo-rs.png"
    assert any("jamais-fournie.png" in m and "missing" in m
               for m in rapport["avertissements"])
    capsys.readouterr()


def test_a_path_that_does_not_resolve_is_refused_and_rolled_back(tmp_path, monkeypatch, capsys):
    """The guarantee's last line, tested by preventing the copy.

    Without this check, the tool could write a declaration the compiler will
    refuse — exactly the defect layer 1 closes. The check uses the COMPILER's
    resolver, not a second implementation: that is what guarantees the same
    verdict on both sides."""
    spec = _project(tmp_path)
    avant = spec.read_text(encoding="utf-8")

    import monl.assets_tool as outil
    monkeypatch.setattr(outil.commandes.shutil, "copy2", lambda *_a, **_k: None)

    with pytest.raises(AssetsToolError) as refus:
        outil.ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert "does not resolve to a file" in str(refus.value)
    assert spec.read_text(encoding="utf-8") == avant
    capsys.readouterr()


# --------------------------------------------------------------------------
# The real journey, through the command line
# --------------------------------------------------------------------------

def test_the_full_journey_through_the_command_line(tmp_path, capsys):
    """Everything above calls the function; here argparse, monl.json and the
    display are tested — the path the human takes."""
    from monl.cli import compile_project, main

    spec = _project(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()

    main(["assets", "add", str(tmp_path / "source" / "photo une.png"),
          "--for", "Halo RS", "--dir", str(tmp_path)])
    sortie = capsys.readouterr().out
    assert "assets/halo-rs.png" in sortie
    assert "Produit.photo" in sortie
    assert "monl update" in sortie

    main(["assets", "list", str(tmp_path)])
    sortie = capsys.readouterr().out
    assert "assets/halo-rs.png" in sortie and "Produit[1].photo" in sortie

    # The spec moved: 'monl run --check' must say so, and 'monl update' resolve
    # it. It is the cycle the tool's warning announces.
    from monl.cli import check_coherence
    ok, erreurs, _ = check_coherence(str(tmp_path))
    assert not ok and any("monl update" in e for e in erreurs)
    capsys.readouterr()


def test_the_command_line_exits_with_error_on_a_refusal(tmp_path, capsys):
    from monl.cli import compile_project, main

    spec = _project(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    with pytest.raises(SystemExit) as sortie:
        main(["assets", "add", str(tmp_path / "source" / "photo une.png"),
              "--for", "Inexistant", "--dir", str(tmp_path)])
    assert sortie.value.code == 1
    assert "No seed row has the value" in capsys.readouterr().out
