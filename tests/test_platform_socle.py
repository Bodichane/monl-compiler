"""Preuves d'exécution du socle de plateforme, sans serveur HTTP public."""

import json
from math import isclose

import pytest

from monl.cli import compile_project
from monl_platform.app_templates import materialize_template
from monl_platform.builder import BuildIsolationError, build_project
from monl_platform.paths import project_directory
from monl_platform.quota import QuotaExceededError, TokenQuota
from monl_platform.store import PlatformStore

SPEC = """app PlatformSocle

entity Item
    label: String

# Admin est provisionné hors ligne ; le frontend minimal sert de témoin de la
# boucle de construction, pas de promesse d'interface d'administration.
actor Admin

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item

seed Item
    label: \"Alpha\"
"""

GOOD_FRONT = """<!doctype html><html><body><div id=\"l\"></div>
<script>
fetch('/item?limit=5').then(r => r.json()).then(d => {
  document.getElementById('l').textContent = d.data.map(i => i.label).join(', ');
});
</script></body></html>"""

BAD_FRONT = """<!doctype html><html><body>
<script>fetch('/fantome/1'); casse();</script>
</body></html>"""


def _price_table(path):
    path.write_text(
        json.dumps(
            {
                "currency": "RUB",
                "prices": {
                    "yandex": {
                        "modele-test": {
                            "input_per_million_tokens": 100,
                            "output_per_million_tokens": 200,
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )


@pytest.fixture()
def platform(tmp_path):
    store = PlatformStore(tmp_path)
    root = tmp_path / "projects"
    yield store, root
    store.close()


def _new_project(platform, identifier="alice", slug="site"):
    store, _root = platform
    account = store.create_account(identifier)
    project = store.create_project(account, slug)
    return account, project


def _quota(platform, maximum=10_000):
    store, root = platform
    return TokenQuota(store, root, maximum)


class _Provider:
    provider_name = "yandex"
    model = "modele-test"
    last_usage = None

    def __init__(self, content=GOOD_FRONT, input_tokens=123, output_tokens=45):
        self.content = content
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = 0

    def __call__(self, _prompt):
        self.calls += 1
        self.last_usage = {
            "duration_seconds": 0.25,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
        }
        return json.dumps({"files": {"index.html": self.content}})


def test_quota_refuse_avant_toute_depense(platform):
    store, root = platform
    account, project = _new_project(platform)
    directory = project_directory(root, account, project)
    directory.joinpath(".monl_ai_usage.jsonl").write_text(
        json.dumps(
            {
                "run_id": "precedent",
                "provider": "yandex",
                "model": "modele-test",
                "input_tokens": 70,
                "output_tokens": 30,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    provider = _Provider()

    with pytest.raises(QuotaExceededError):
        build_project(
            project,
            SPEC,
            provider,
            account_id=account,
            store=store,
            workspace_root=root,
            quota=_quota(platform, maximum=100),
        )

    assert provider.calls == 0
    assert not directory.joinpath("spec.ml").exists()
    build = store.list_builds(project)[0]
    assert build["state"] == "echouee"
    assert "quota" in build["error_message"]


def test_deux_utilisateurs_sont_isoles(platform):
    store, root = platform
    alice, projet_alice = _new_project(platform, "alice", "site")
    bob, projet_bob = _new_project(platform, "bob", "site")
    alice_dir = project_directory(root, alice, projet_alice)
    bob_dir = project_directory(root, bob, projet_bob)
    alice_dir.joinpath("secret.txt").write_text("alice", encoding="utf-8")

    assert alice_dir != bob_dir
    assert not bob_dir.joinpath("secret.txt").exists()
    with pytest.raises(BuildIsolationError):
        build_project(
            projet_alice,
            SPEC,
            _Provider(),
            account_id=bob,
            store=store,
            workspace_root=root,
            quota=_quota(platform),
        )
    with pytest.raises(ValueError, match="remontée"):
        store.create_project(alice, "../autre")


def test_construction_reussie_enregistre_la_consommation_reelle(platform, tmp_path):
    store, root = platform
    account, project = _new_project(platform)
    prices = tmp_path / "prices.json"
    _price_table(prices)
    provider = _Provider()

    build = build_project(
        project,
        SPEC,
        provider,
        account_id=account,
        store=store,
        workspace_root=root,
        quota=_quota(platform),
        prices_path=prices,
    )

    assert build["state"] == "reussie"
    assert build["run_id"]
    assert build["input_tokens"] == 123
    assert build["output_tokens"] == 45
    assert build["tokens_consumed"] == 168
    assert isclose(build["cost"], 0.0213)
    assert build["currency"] == "RUB"
    assert build["price_status"] == "declared"
    assert build["started_at"] and build["finished_at"]
    assert (root / "accounts" / str(account) / "projects" / str(project) / "spec.ml").is_file()


def test_construction_echouee_conserve_les_erreurs_de_verification(platform):
    store, root = platform
    account, project = _new_project(platform)
    build = build_project(
        project,
        SPEC,
        _Provider(content=BAD_FRONT, input_tokens=10, output_tokens=5),
        account_id=account,
        store=store,
        workspace_root=root,
        quota=_quota(platform),
    )

    assert build["state"] == "echouee"
    assert build["error_message"]
    assert "fantome" in build["error_message"]
    assert "REFUSÉ" in build["error_message"]
    # Renversement rendu nécessaire par le contrôle fetch : la construction
    # refuse désormais `/fantome/1` avant le smoke test, donc le JavaScript
    # `casse()` n'est volontairement jamais exécuté ni rapporté.
    assert build["run_id"]
    assert build["tokens_consumed"] == 30


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
