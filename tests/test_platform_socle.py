"""Preuves d'exécution du socle de plateforme, sans serveur HTTP public.

POINT 162. Ce fichier éprouvait la boucle de CONSTRUCTION : quota, appel du
modèle, consommation de jetons, snapshot. Le constructeur retiré, ce qui reste
à prouver est la compilation d'un projet de compte — déterministe, hors ligne,
et confinée au dossier privé de son propriétaire.
"""

import uuid

import pytest

from monl.cli import compile_project
from monl_platform.app_templates import materialize_template
from monl_platform.compilation import ProjectIsolationError, compiler_le_projet
from monl_platform.identity import IdentityStore
from monl_platform.paths import project_directory
from monl_platform.service import PlatformInputError
from monl_platform.store import PlatformStore

SPEC = """app PlatformSocle

entity Item
    label: String

actor Admin

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item

seed Item
    label: "Alpha"
"""


@pytest.fixture()
def platform(tmp_path):
    store = PlatformStore(tmp_path)
    root = tmp_path / "projects"
    yield store, root
    store.close()


def _new_project(platform, identifier="alice", slug="site"):
    store, _root = platform
    identity = IdentityStore(store.workspace)
    email = identifier if "@" in identifier else f"{identifier}@example.test"
    user = identity.register(email, "MotDePasse-123")
    project = uuid.uuid4().hex
    identity.add_project(user["id"], project, slug)
    store.create_project(user["id"], project, slug)
    return user["id"], project


def _poser_la_spec(root, account, project, spec=SPEC):
    directory = project_directory(root, account, project)
    directory.joinpath("spec.ml").write_text(spec, encoding="utf-8")
    return directory


def test_compiler_un_projet_produit_son_backend_dans_le_dossier_prive(platform):
    store, root = platform
    account, project = _new_project(platform)
    directory = _poser_la_spec(root, account, project)

    resultat = compiler_le_projet(
        project, account_id=account, store=store, workspace_root=root
    )

    assert (directory / "app.py").is_file()
    assert (directory / "serve.py").is_file()
    assert (directory / "frontend_contract.json").is_file()
    assert resultat["contract"]["routes"], "le contrat doit décrire des routes"
    # Le cap : la plateforme ne construit AUCUNE interface.
    assert not (directory / "frontend").exists()
    assert ".jwt_secret" not in resultat["files"]


def test_une_spec_refusee_est_une_faute_d_entree_pas_une_panne(platform):
    """Le validateur tranche AVANT le worker : le message doit rester lisible."""
    store, root = platform
    account, project = _new_project(platform)
    _poser_la_spec(root, account, project, spec="app Cassee\n\nentity\n")

    with pytest.raises(PlatformInputError):
        compiler_le_projet(
            project, account_id=account, store=store, workspace_root=root
        )


def test_deux_utilisateurs_sont_isoles(platform):
    store, root = platform
    alice, projet_alice = _new_project(platform, "alice", "site")
    bob, projet_bob = _new_project(platform, "bob", "site")
    alice_dir = project_directory(root, alice, projet_alice)
    bob_dir = project_directory(root, bob, projet_bob)
    alice_dir.joinpath("secret.txt").write_text("alice", encoding="utf-8")

    assert alice_dir != bob_dir
    assert not bob_dir.joinpath("secret.txt").exists()
    with pytest.raises(ProjectIsolationError):
        compiler_le_projet(
            projet_alice, account_id=bob, store=store, workspace_root=root
        )
    with pytest.raises(ValueError, match="remontée"):
        store.create_project(alice, uuid.uuid4().hex, "../autre")


def test_un_modele_du_catalogue_produit_une_spec_qui_compile(tmp_path):
    spec = materialize_template(
        "Portfolio / site vitrine",
        app_name="CatalogueSocle",
        description="Un portfolio de démonstration.",
    )
    spec_path = tmp_path / "spec.ml"
    spec_path.write_text(spec, encoding="utf-8")
    compile_project(str(spec_path), str(tmp_path))

    assert "app CatalogueSocle" in spec
    assert (tmp_path / "app.py").is_file()
    assert (tmp_path / "frontend_contract.json").is_file()
