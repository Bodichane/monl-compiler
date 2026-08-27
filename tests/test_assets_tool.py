"""Brique 13, COUCHE 2 — `monl assets add` / `monl assets list` (point 84).

Pourquoi ce fichier existe, et ce qu'il garde. La couche 2 est un outil qui
ÉCRIT DANS LA SPEC : c'est la première fois du projet qu'autre chose que le
dialogue guidé modifie le fichier source de l'humain. Deux propriétés sont donc
à protéger, et ni l'une ni l'autre ne se relit :

* **il écrit, le compilateur prouve.** Chaque édition est reparsée et revalidée
  avec `base_dir` avant d'être écrite. Un échec ne doit rien laisser derrière :
  ni spec à demi modifiée, ni fichier copié. C'est la seule raison pour
  laquelle la couche 2 ne peut pas produire ce que la couche 1 refuse ;
* **il ne détruit pas les commentaires.** La spec d'un projet réel est plus
  qu'à moitié faite de commentaires, et ce sont eux qui expliquent quelle
  brique fait quoi. Un aller-retour parse → regénère aurait été plus court à
  écrire et aurait effacé la documentation du projet pour poser une photo.

Le reste tient aux refus : une désignation ambiguë écrirait la photo sur la
mauvaise fiche, et personne ne le verrait avant la mise en ligne.
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

SPEC = """app BancOutil

# Ce commentaire, et tous les autres, doivent survivre à l'outil.
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

# Deux fiches, dont une au nom nordique : le slug doit rester lisible.
seed Produit
    nom: "Halo RS", prix: 149.0   # la vedette du catalogue
    nom: "Sørlund Deck", prix: 89.0

seed Maison
    nom: "Sørlund Deck"
"""


def _projet(racine, spec=SPEC):
    """Une spec sur disque et deux fichiers sources DISTINCTS.

    Distincts à dessein : c'est ce qui rend le contrôle d'écrasement
    observable — deux fichiers identiques passeraient pour idempotence."""
    (racine / "source").mkdir(exist_ok=True)
    (racine / "source" / "photo une.png").write_bytes(b"\x89PNG\r\n\x1a\nUNE")
    (racine / "source" / "photo deux.png").write_bytes(b"\x89PNG\r\n\x1a\nDEUX")
    (racine / "source" / "logo.svg").write_text('<svg viewBox="0 0 8 8"/>')
    chemin = racine / "spec.ml"
    chemin.write_text(spec, encoding="utf-8")
    return chemin


def _compile_toujours(spec_path, project_dir):
    """La spec obtenue passe-t-elle le VRAI validateur, base_dir compris ?"""
    return MonlAST(parse_monl_string(spec_path.read_text(encoding="utf-8")),
                   base_dir=str(project_dir)).validate_and_audit()


# --------------------------------------------------------------------------
# Le témoin, et les deux propriétés à protéger
# --------------------------------------------------------------------------

def test_poser_une_photo_la_copie_et_la_declare(tmp_path, capsys):
    """Le témoin de tous les refus qui suivent : sans lui, un outil qui
    refuserait TOUT passerait chacun d'eux."""
    spec = _projet(tmp_path)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert rapport["fichier"] == "assets/halo-rs.png"
    assert rapport["ou"] == "Produit.photo"
    assert (tmp_path / "assets" / "halo-rs.png").exists()
    ast = _compile_toujours(spec, tmp_path)
    assert ast["seeds"][0]["rows"][0]["photo"] == "assets/halo-rs.png"
    capsys.readouterr()


def test_les_commentaires_et_les_autres_champs_survivent(tmp_path, capsys):
    """La propriété qu'un aller-retour parse → regénère aurait détruite.

    Le commentaire de FIN DE LIGNE compte autant que les autres : il est le
    seul que l'édition textuelle risque vraiment de manger, puisqu'il vit sur
    la ligne même qu'on réécrit."""
    spec = _projet(tmp_path)
    avant = spec.read_text(encoding="utf-8")
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    apres = spec.read_text(encoding="utf-8")

    assert avant.count("#") == apres.count("#")
    assert "# Ce commentaire, et tous les autres" in apres
    assert "# la vedette du catalogue" in apres
    ligne = next(li for li in apres.splitlines() if "Halo RS" in li)
    assert ligne.endswith("# la vedette du catalogue")
    assert 'prix: 149.0' in ligne          # les autres champs sont intacts
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


def test_une_fiche_sur_deux_lignes_reste_une_fiche(tmp_path, capsys):
    """`STRING_LITERAL` est compilé avec /s : une valeur de seed PEUT tenir sur
    plusieurs lignes, et le parseur l'accepte (vérifié contre le vrai parseur,
    pas supposé). Compter les lignes de contenu au lieu des FICHES décalait donc
    toutes les suivantes — et une photo écrite sur la mauvaise fiche produit une
    spec parfaitement compilable. Le repérage travaille en PLAGES pour ça."""
    spec = _projet(tmp_path, SPEC_MULTILIGNE)
    r1 = ajouter_asset(str(spec), str(tmp_path),
                       str(tmp_path / "source" / "photo une.png"), pour="Deck")
    r2 = ajouter_asset(str(spec), str(tmp_path),
                       str(tmp_path / "source" / "photo deux.png"), pour="Halo RS")
    assert r1["fichier"] == "assets/deck.png"
    assert r2["fichier"] == "assets/halo-rs.png"

    ast = _compile_toujours(spec, tmp_path)
    lignes = ast["seeds"][0]["rows"]
    # Chaque photo sur SA fiche : c'est tout l'enjeu.
    assert lignes[0]["nom"] == "Halo RS" and lignes[0]["photo"] == "assets/halo-rs.png"
    assert lignes[1]["nom"] == "Deck" and lignes[1]["photo"] == "assets/deck.png"
    # La valeur multi-lignes et le commentaire terminal sont intacts.
    assert "\n" in lignes[0]["desc"]
    assert "# note terminale" in spec.read_text(encoding="utf-8")
    capsys.readouterr()


def test_redeclarer_a_lidentique_ne_touche_pas_la_spec(tmp_path, capsys):
    """Réécrire un texte identique invaliderait l'empreinte de
    'monl run --check' — et ferait croire à une évolution qui n'a pas eu lieu."""
    spec = _projet(tmp_path)
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
# Le nom du fichier
# --------------------------------------------------------------------------

@pytest.mark.parametrize("texte, attendu", [
    ("Halo RS", "halo-rs"),
    ("Sørlund Deck", "sorlund-deck"),      # NFKD ne décompose pas le « ø »
    ("Café Crème", "cafe-creme"),
    ("Air 95 — édition", "air-95-edition"),
    ("  ", ""),
])
def test_le_slug_reste_lisible(texte, attendu):
    """« Sørlund » donnait « srlund » avant la table de translittération : un
    nom de fichier muet là où le nom était lisible. Le catalogue du projet
    porte déjà une maison nordique — le cas n'est pas théorique."""
    assert sluggify(texte) == attendu


def test_une_source_sans_extension_est_refusee(tmp_path):
    """Servi tel quel, un fichier sans extension arrive en octet-stream : le
    navigateur ne l'affiche pas, et rien ne le dit."""
    spec = _projet(tmp_path)
    (tmp_path / "source" / "sansext").write_bytes(b"\x89PNG")
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "sansext"), pour="Halo RS")
    assert "extension" in str(refus.value)


def test_as_refuse_un_chemin(tmp_path):
    """--as nomme un fichier, pas une destination : accepter un chemin
    rouvrirait la porte que la couche 1 ferme (sortir du projet)."""
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Halo RS", nom="../evade.png")
    assert "pas un chemin" in str(refus.value)


# --------------------------------------------------------------------------
# Les refus de désignation — deviner écrirait sur la mauvaise fiche
# --------------------------------------------------------------------------

def test_une_valeur_inconnue_est_refusee_avec_une_suggestion(tmp_path):
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo")
    assert "'Halo RS'" in str(refus.value)          # la suggestion, pas seulement le refus


def test_une_valeur_partagee_par_deux_entites_est_refusee(tmp_path):
    """« Sørlund Deck » nomme un produit ET une maison : écrire la photo sur
    l'une des deux au hasard ne se verrait qu'en ligne."""
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Sørlund Deck")
    message = str(refus.value)
    assert "2 lignes" in message and "--entity" in message


def test_entity_leve_lambiguite(tmp_path, capsys):
    """Le témoin du refus ci-dessus : l'échappatoire annoncée fonctionne."""
    spec = _projet(tmp_path)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Sørlund Deck", entity="Produit")
    assert rapport["fichier"] == "assets/sorlund-deck.png"
    _compile_toujours(spec, tmp_path)
    capsys.readouterr()


def test_une_entite_sans_champ_image_est_refusee_en_nommant_le_remede(tmp_path):
    """Maison n'a que des String : un chemin y passerait sans vérification,
    donc l'outil refuse plutôt que d'écrire là où la couche 1 est aveugle."""
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Sørlund Deck", entity="Maison")
    message = str(refus.value)
    assert "aucun champ de type 'Image'" in message
    assert "photo: Image" in message          # le remède, pas seulement le refus


def test_deux_champs_image_exigent_field(tmp_path, capsys):
    spec = _projet(tmp_path, SPEC.replace("    photo: Image",
                                          "    photo: Image\n    apercu: Image"))
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    assert "--field" in str(refus.value)
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS", field="apercu")
    assert rapport["ou"] == "Produit.apercu"
    _compile_toujours(spec, tmp_path)
    capsys.readouterr()


def test_field_sur_un_champ_non_image_est_refuse(tmp_path):
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"),
                      pour="Halo RS", field="nom")
    assert "pas 'Image'" in str(refus.value)


def test_ecrire_dans_une_spec_deja_cassee_est_refuse(tmp_path):
    """Sans ce contrôle, l'échec de la revalidation ferait accuser l'outil
    d'un défaut qui existait avant lui."""
    spec = _projet(tmp_path, SPEC.replace('photo: Image', 'photo: Inconnu'))
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    assert "ne compile pas en l'état" in str(refus.value)
    assert not (tmp_path / "assets").exists()      # rien n'a été copié


# --------------------------------------------------------------------------
# Écrasement et retour en arrière
# --------------------------------------------------------------------------

def test_un_fichier_different_de_meme_nom_nest_pas_ecrase_sans_force(tmp_path, capsys):
    spec = _projet(tmp_path)
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


def test_un_refus_du_compilateur_ne_laisse_rien_derriere(tmp_path, monkeypatch, capsys):
    """Le filet, éprouvé en le forçant.

    L'outil est construit pour que le CLI ne PUISSE pas produire une spec
    invalide : tous les chemins fautifs sont interceptés avant l'écriture. Le
    retour en arrière n'est donc atteignable qu'en provoquant l'échec — et un
    filet que rien n'éprouve n'est pas un filet, c'est une décoration."""
    spec = _projet(tmp_path)
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


def test_un_refus_apres_force_restaure_le_fichier_precedent(tmp_path, monkeypatch, capsys):
    """Écraser sous --force doit rester réversible le temps de la
    revalidation : sinon un refus du compilateur détruirait l'ancien fichier
    pour rien."""
    spec = _projet(tmp_path)
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


def test_lancien_fichier_est_signale_orphelin_et_conserve(tmp_path, capsys):
    """Un fichier déposé par l'humain ne s'efface pas sur la déduction d'un
    outil de déclaration : le frontend de SneakerLab référence en dur des
    photos que la spec ignore."""
    spec = _projet(tmp_path)
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
# Le logo : un bloc 'assets' créé de toutes pièces
# --------------------------------------------------------------------------

def test_le_logo_cree_le_bloc_assets_absent(tmp_path, capsys):
    """Renvoyer l'humain écrire quatre lignes à la main avant de pouvoir poser
    son logo rendrait l'outil inutile là où il sert le plus."""
    spec = _projet(tmp_path)
    assert "assets\n" not in spec.read_text(encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "logo.svg"), cible="logo")
    assert rapport["ou"] == "assets.logo"
    ast = _compile_toujours(spec, tmp_path)
    # Le logo se déclare par son SEUL nom : c'est le contrat qui préfixe par le
    # dossier. Écrire 'assets/logo.svg' ici donnerait '/site/assets/assets/…'.
    assert ast["assets"]["logo"] == "logo.svg"
    assert ast["assets"]["dir"] == "assets"
    texte = spec.read_text(encoding="utf-8")
    assert texte.index("assets\n") < texte.index("entity Produit")
    capsys.readouterr()


def test_le_favicon_rejoint_le_bloc_existant(tmp_path, capsys):
    spec = _projet(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "logo.svg"), cible="logo")
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), cible="favicon")
    ast = _compile_toujours(spec, tmp_path)
    assert ast["assets"] == {"dir": "assets", "logo": "logo.svg",
                             "favicon": "favicon.png"}
    assert spec.read_text(encoding="utf-8").count("assets\n") == 1
    capsys.readouterr()


def test_designer_deux_destinations_a_la_fois_est_refuse(tmp_path):
    spec = _projet(tmp_path)
    with pytest.raises(AssetsToolError) as refus:
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "logo.svg"))
    assert "--logo" in str(refus.value)
    with pytest.raises(AssetsToolError):
        ajouter_asset(str(spec), str(tmp_path),
                      str(tmp_path / "source" / "logo.svg"),
                      pour="Halo RS", cible="logo")


# --------------------------------------------------------------------------
# Ce que la réussite n'implique pas
# --------------------------------------------------------------------------

def test_une_base_existante_declenche_lavertissement_du_seed(tmp_path, capsys):
    """Le piège vécu en migrant SneakerLab : le seed ne nourrit qu'une base
    NEUVE, donc 12 fiches gardaient l'ancien chemin et le site aurait montré
    12 cadres vides sans un mot."""
    spec = _projet(tmp_path)
    (tmp_path / "app.db").write_bytes(b"SQLite format 3\x00")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert any("base NEUVE" in m for m in rapport["avertissements"])
    capsys.readouterr()


def test_un_fichier_de_credits_incomplet_est_signale_sans_etre_ecrit(tmp_path, capsys):
    """« monl vérifie la complétude, jamais la véracité » (point 83) : l'outil
    constate l'absence, il n'invente aucune attribution — et n'écrit pas dans
    un fichier qui reste une convention de projet."""
    spec = _projet(tmp_path)
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
# Le rapport de complétude
# --------------------------------------------------------------------------

def test_list_distingue_declare_present_et_non_declare(tmp_path, capsys):
    spec = _projet(tmp_path)
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


def test_list_montre_un_asset_declare_mais_absent(tmp_path, capsys):
    """LE défaut que ce test a trouvé, et qu'il garde fermé.

    Le rapport chargeait d'abord la spec avec `base_dir` — donc la validation
    échouait sur l'asset manquant lui-même, et `monl assets list` refusait de
    tourner dans le seul cas où il servait. L'outil valide désormais la FORME
    sans l'existence, et calcule la présence lui-même : c'est la coupure de la
    couche 1 qui rend ça possible."""
    spec = _projet(tmp_path)
    ajouter_asset(str(spec), str(tmp_path),
                  str(tmp_path / "source" / "photo une.png"), pour="Halo RS")
    os.remove(tmp_path / "assets" / "halo-rs.png")
    rapport = lister_assets(str(spec), str(tmp_path))
    manquants = [li for li in rapport["declares"] if not li["present"]]
    assert [li["chemin"] for li in manquants] == ["assets/halo-rs.png"]
    capsys.readouterr()


def test_add_reste_utilisable_quand_un_autre_asset_manque(tmp_path, capsys):
    """L'autre moitié du même défaut : revalider TOUTE la spec avec base_dir
    rendait l'outil inutilisable sur une spec déclarant deux photos absentes —
    impossible d'en poser une, l'autre faisant échouer la revalidation. La
    garantie porte sur ce que l'outil ÉCRIT, et les autres manques sont dits."""
    spec = _projet(tmp_path)
    spec.write_text(spec.read_text(encoding="utf-8").replace(
        'nom: "Sørlund Deck", prix: 89.0',
        'nom: "Sørlund Deck", prix: 89.0, photo: "assets/jamais-fournie.png"'),
        encoding="utf-8")
    rapport = ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert rapport["fichier"] == "assets/halo-rs.png"
    assert any("jamais-fournie.png" in m and "absent" in m
               for m in rapport["avertissements"])
    capsys.readouterr()


def test_un_chemin_qui_ne_resout_pas_est_refuse_et_annule(tmp_path, monkeypatch, capsys):
    """La dernière ligne de la garantie, éprouvée en empêchant la copie.

    Sans cette vérification, l'outil pourrait écrire une déclaration que le
    compilateur refusera — exactement le défaut que la couche 1 ferme. Le
    contrôle emploie le résolveur DU COMPILATEUR, pas une seconde
    implémentation : c'est ce qui garantit le même verdict des deux côtés."""
    spec = _projet(tmp_path)
    avant = spec.read_text(encoding="utf-8")

    import monl.assets_tool as outil
    monkeypatch.setattr(outil.commandes.shutil, "copy2", lambda *_a, **_k: None)

    with pytest.raises(AssetsToolError) as refus:
        outil.ajouter_asset(str(spec), str(tmp_path),
                            str(tmp_path / "source" / "photo une.png"),
                            pour="Halo RS")
    assert "ne résout vers aucun fichier" in str(refus.value)
    assert spec.read_text(encoding="utf-8") == avant
    capsys.readouterr()


# --------------------------------------------------------------------------
# Le parcours réel, par la ligne de commande
# --------------------------------------------------------------------------

def test_le_parcours_complet_par_la_ligne_de_commande(tmp_path, capsys):
    """Tout ce qui précède appelle la fonction ; ici c'est argparse, monl.json
    et l'affichage qui sont éprouvés — le chemin que l'humain emprunte."""
    from monl.cli import compile_project, main

    spec = _projet(tmp_path)
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

    # La spec a bougé : 'monl run --check' doit le dire, et 'monl update' le
    # résoudre. C'est le cycle annoncé par l'avertissement de l'outil.
    from monl.cli import check_coherence
    ok, erreurs, _ = check_coherence(str(tmp_path))
    assert not ok and any("monl update" in e for e in erreurs)
    capsys.readouterr()


def test_la_ligne_de_commande_sort_en_erreur_sur_un_refus(tmp_path, capsys):
    from monl.cli import compile_project, main

    spec = _projet(tmp_path)
    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    with pytest.raises(SystemExit) as sortie:
        main(["assets", "add", str(tmp_path / "source" / "photo une.png"),
              "--for", "Inexistant", "--dir", str(tmp_path)])
    assert sortie.value.code == 1
    assert "Aucune ligne de seed" in capsys.readouterr().out
