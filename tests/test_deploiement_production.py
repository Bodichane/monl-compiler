"""Static contracts of the deployment artifacts.

These tests do not start Docker: they prevent a configuration change from
making the runbook inconsistent or accidentally exposing a secret in the
repository.
"""

import os
import re
import subprocess
from pathlib import Path

import yaml

from scripts.check_platform_env import lire_env, valider

RACINE = Path(__file__).parents[1]


def test_example_env_contains_no_real_secret():
    contenu = (RACINE / ".env.platform.example").read_text(encoding="utf-8")
    gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")

    assert "MONL_PLATFORM_DOMAIN=" in contenu
    assert "MONL_PLATFORM_PUBLIC_URL=" in contenu
    assert "MONL_COOKIE_SECURE=1" in contenu
    assert "MONL_TRUST_PROXY=1" in contenu
    assert "MONL_PLATFORM_OAUTH_STATE_SECRET=" in contenu
    assert "ghp_" not in contenu
    assert "sk_live_" not in contenu
    assert ".env.*" in gitignore
    assert "!.env.platform.example" in gitignore
    dockerignore = (RACINE / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in dockerignore
    assert ".env.*" in dockerignore


def test_compose_keeps_the_port_private_and_waits_for_readiness():
    contenu = (RACINE / "compose.platform.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8022:8022"' in contenu
    assert "image: ${MONL_PLATFORM_IMAGE:-monl-platform:local}" in contenu
    assert "condition: service_healthy" in contenu
    assert "MONL_PLATFORM_PUBLIC_URL" in contenu
    assert "MONL_PLATFORM_OAUTH_STATE_SECRET" in contenu
    assert "healthcheck:" in contenu
    assert "MONL_BACKUP_MAX_AGE_SECONDS" in contenu
    assert "retrying in 60 s" in contenu
    for variable in ("MONL_OAUTH_GITHUB_CLIENT_ID", "MONL_OAUTH_GITHUB_SECRET",
                     "MONL_OAUTH_GOOGLE_CLIENT_ID", "MONL_OAUTH_GOOGLE_SECRET"):
        assert variable in contenu


def test_each_service_comes_back_after_a_machine_reboot():
    """`always`, and never `unless-stopped` — the nuance costs the service.

    What restarts the containers after a reboot is `podman-restart.service`,
    whose command is `podman start --all --filter restart-policy=always`. A
    container declared `unless-stopped` does not enter this filter: it stays
    down.

    Measured on the hosting machine, not deduced — after a reboot, `monl-nginx`
    (started with `always`) was running, the platform had been `Created` for fifty
    minutes, and **nothing had said so**. A container that does not come back
    leaves no trace: it did not crash, it never started.

    The witness covers ALL services, not today's two: a service added later would
    otherwise inherit the defect silently.
    """
    compose = yaml.safe_load(
        (RACINE / "compose.platform.yaml").read_text(encoding="utf-8"))
    politiques = {
        nom: service.get("restart")
        for nom, service in compose["services"].items()
    }

    assert politiques, "aucun service lu : le témoin ne garderait rien"
    fautifs = {nom: valeur for nom, valeur in politiques.items()
               if valeur != "always"}
    assert not fautifs, (
        f"ces services ne remonteront pas après un redémarrage : {fautifs} — "
        f"seul `always` entre dans le filtre de podman-restart.service"
    )


def test_the_folded_backup_command_is_valid_shell():
    compose = yaml.safe_load((RACINE / "compose.platform.yaml").read_text(encoding="utf-8"))
    commande = compose["services"]["sauvegarde"]["command"][2]
    resultat = subprocess.run(["sh", "-n"], input=commande, text=True, capture_output=True)

    assert resultat.returncode == 0, resultat.stderr


def test_proxy_passes_the_host_name_and_scheme():
    contenu = (RACINE / "deploy/nginx/monl-platform.conf.example").read_text(
        encoding="utf-8"
    )

    assert "monl.example.com *.monl.example.com" in contenu
    assert "proxy_set_header Host $host;" in contenu
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in contenu
    assert "return 301 https://$host$request_uri;" in contenu
    assert "127.0.0.1:8022" in contenu


def test_proxy_does_not_cap_uploads_below_what_the_app_accepts():
    """This block ALSO serves hosted sites (*.monl.example.com), one of which can
    declare `rule X.champ upload max N` up to 32 MiB (measured,
    tests/test_depot_depuis_le_dialogue.py). The original nginx cap was 256 KiB —
    well below the 5 MiB limit already exercised in the repository
    (test_limites_du_guide.py) — so an upload the compiled backend accepts would
    have been refused by the proxy, with a 413, before even reaching the
    application."""
    contenu = (RACINE / "deploy/nginx/monl-platform.conf.example").read_text(
        encoding="utf-8"
    )
    correspondance = re.search(r"client_max_body_size\s+([0-9]+)([kKmMgG]?);", contenu)
    assert correspondance, "aucun client_max_body_size déclaré"
    valeur, unite = correspondance.groups()
    multiplicateur = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[unite.lower()]
    octets = int(valeur) * multiplicateur

    LIMITE_DEPOT_MAX_TESTEE = 32 * 1024 * 1024
    assert octets >= LIMITE_DEPOT_MAX_TESTEE, (
        f"client_max_body_size ({octets} octets) est sous une limite d'upload "
        f"déjà exercée par la suite ({LIMITE_DEPOT_MAX_TESTEE} octets) : "
        "un dépôt valide pour l'application serait refusé par le proxy.")


def test_smoke_platform_probes_both_endpoints_and_is_executable():
    script = RACINE / "scripts/smoke_platform.sh"
    contenu = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert "/health" in contenu
    assert "/ready" in contenu
    assert "curl --fail" in contenu


def test_script_deploiement_enchaine_validation_compose_et_readiness():
    script = RACINE / "scripts/deploy_platform.sh"
    contenu = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert "check_platform_env.py" in contenu
    assert "config --quiet" in contenu
    assert "up --build --detach" in contenu
    assert 'container_runtime=${CONTAINER_RUNTIME:-docker}' in contenu
    assert 'use_prebuilt_image=${USE_PREBUILT_IMAGE:-0}' in contenu
    assert 'python_bin=${PYTHON_BIN:-python3}' in contenu
    assert 'Container runtime not found' in contenu
    assert 'curl is required' in contenu
    assert 'Python interpreter not found' in contenu
    assert "config --images" in contenu
    assert "non-local MONL_PLATFORM_IMAGE" in contenu
    assert "refuses the mutable tag latest" in contenu
    assert "requires a tag or a digest" in contenu
    assert "@sha256:" in contenu
    assert "compose --env-file \"$env_file\" -f \"$compose_file\" pull" in contenu
    assert "http://127.0.0.1:8022/ready" in contenu
    assert "for tentative in $(seq 1 90)" in contenu
    assert 'if [ "$pret" != true ]' in contenu
    assert "The platform does not become ready" in contenu
    assert "logs --tail=100 platform" in contenu
    # `compose ps -q <service>` is Docker Compose v2: podman-compose 1.6.0 —
    # the provider deploy/README.md recommends for Podman — refuses a service
    # name as argument. Tested for real (podman + podman-compose): the script
    # failed on "unrecognized arguments: sauvegarde". `lib_compose.sh` (single
    # source, shared with export_platform_backups.sh) reads the compose LABEL
    # both providers set, never a `ps` syntax one of them ignores.
    assert ". \"$racine/scripts/lib_compose.sh\"" in contenu
    assert "find_container_by_service" in contenu
    assert 'backup_started=false' in contenu
    assert 'if [ "$backup_started" != true ]' in contenu
    assert "The backup service does not start" in contenu
    assert "logs --tail=100 sauvegarde" in contenu
    assert 'backup_healthy=false' in contenu
    assert "{{.State.Health.Status}}" in contenu
    assert 'if [ "$backup_healthy" != true ]' in contenu
    assert "does not become healthy" in contenu
    assert 'if [ "$container_runtime" = podman ]' in contenu
    assert '--podman-build-args="--format docker"' in contenu
    assert "smoke_platform.sh http://127.0.0.1:8022" in contenu


def test_deployment_refuses_a_mutable_prebuilt_image(tmp_path):
    script = RACINE / "scripts/deploy_platform.sh"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join([
            "MONL_PLATFORM_DOMAIN=monl.example.com",
            "MONL_PLATFORM_PUBLIC_URL=https://monl.example.com",
            "MONL_COOKIE_SECURE=1",
            "MONL_TRUST_PROXY=1",
        ]) + "\n",
        encoding="utf-8",
    )
    compose_file = tmp_path / "compose.yaml"
    compose_file.write_text("services: {}\n", encoding="utf-8")
    runtime = tmp_path / "runtime"
    runtime.write_text(
        "#!/bin/sh\n"
        "case \"$*\" in\n"
        "  *'config --images'*) printf '%s\\n' \"$FAKE_IMAGE\" ;;\n"
        "esac\n",
        encoding="utf-8",
    )
    runtime.chmod(0o755)

    for image in ("ghcr.io/bodichane/monl-platform:latest", "ghcr.io:5000/monl-platform"):
        resultat = subprocess.run(
            [str(script)],
            cwd=RACINE,
            env={
                **os.environ,
                "ENV_FILE": str(env_file),
                "COMPOSE_FILE": str(compose_file),
                "CONTAINER_RUNTIME": str(runtime),
                "USE_PREBUILT_IMAGE": "1",
                "FAKE_IMAGE": image,
            },
            capture_output=True,
            text=True,
        )
        assert resultat.returncode == 2
        assert "mutable tag latest" in resultat.stderr or "a tag or a digest" in resultat.stderr


def test_backup_export_is_bounded_to_a_host_folder():
    script = RACINE / "scripts/export_platform_backups.sh"
    contenu = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert 'racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)' in contenu
    assert 'compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}' in contenu
    assert 'env_file=${ENV_FILE:-"$racine/.env"}' in contenu
    assert 'container_runtime=${CONTAINER_RUNTIME:-docker}' in contenu
    # Same defect, same fix as deploy_platform.sh: `ps -q <service>` is not
    # supported by podman-compose (see the neighboring script's test).
    assert ". \"$racine/scripts/lib_compose.sh\"" in contenu
    assert "find_container_by_service" in contenu
    assert '--env-file "$env_file"' in contenu
    assert "/backups" in contenu
    assert 'umask 077' in contenu
    assert 'chmod 700 "$destination"' in contenu
    assert 'cp "$conteneur:/backups/." "$destination/"' in contenu
    assert 'alpine:3.20' not in contenu
    assert 'destination" = "/"' in contenu

    runbook = (RACINE / "deploy/README.md").read_text(encoding="utf-8")
    assert "sudo scripts/export_platform_backups.sh /var/backups/monl" in runbook

    relatif = subprocess.run([str(script), "exports"], capture_output=True, text=True)
    assert relatif.returncode == 2
    racine = subprocess.run([str(script), "/"], capture_output=True, text=True)
    assert racine.returncode == 2


def test_runbook_documents_dns_tls_and_offsite_backups():
    contenu = (RACINE / "deploy/README.md").read_text(encoding="utf-8")

    for attendu in ("wildcard", "TLS certificate", "separate storage",
                    "smoke_platform.sh", "MONL_PLATFORM_PUBLIC_URL",
                    "check_platform_env.py", "chmod 600 .env",
                    "export_platform_backups.sh", "Dockerfile.platform",
                    "packaging or readiness regression", "firewall", "TCP 80 and 443",
                    # The two Podman traps measured at point 189. A document
                    # describing a limit without giving the remedy it knows
                    # sends people working for nothing (point 166): the witness
                    # therefore requires the CAUSE and the ACTION, not just the
                    # symptom.
                    "podman-restart.service", "restart-policy=always",
                    "enable-linger", 'export PATH="$HOME/.local/bin:$PATH"'):
        assert attendu in contenu, f"le runbook ne dit plus : {attendu}"


def test_ci_builds_and_probes_the_platform_image():
    contenu = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "docker compose -f compose.platform.yaml config --quiet" in contenu
    assert "python scripts/check_platform_env.py .env.platform.example" in contenu
    assert "docker build --file Dockerfile.platform --tag monl-platform:ci ." in contenu
    assert "monl_platform.backup_healthcheck" in contenu
    assert "http://127.0.0.1:18022/ready" in contenu
    assert "{{.State.Health.Status}}" in contenu
    assert "healthy=false" in contenu
    assert 'test "$healthy" = true' in contenu
    assert "docker inspect --format '{{.Config.User}}' monl-platform-ci" in contenu
    assert "needs: verifier" in contenu


def test_documentation_no_longer_says_compose_backups_do_not_exist():
    contenu = (RACINE / "docs/EXPLOITATION.md").read_text(encoding="utf-8")
    assert "pas de sauvegarde automatique" not in contenu.lower()
    assert "sauvegarde" in contenu.lower()


def test_the_image_workflow_tests_then_publishes_ghcr():
    chemin = RACINE / ".github/workflows/platform-image.yml"
    contenu = chemin.read_text(encoding="utf-8")

    assert 'docker build --file Dockerfile.platform --tag monl-platform:release .' in contenu
    assert "monl_platform.backup_healthcheck" in contenu
    assert "{{.State.Health.Status}}" in contenu
    assert "ghcr.io/bodichane/monl-platform" in contenu
    assert "docker/login-action@v3.4.0" in contenu
    assert "docker/metadata-action@v5.6.1" in contenu
    assert "docker/build-push-action@v6.17.0" in contenu
    assert "packages: write" in contenu
    actions = [ligne.split("uses:", 1)[1].strip() for ligne in contenu.splitlines()
               if "uses:" in ligne]
    assert actions and all("@v" in action and action.rsplit("@v", 1)[1].count(".") == 2
                           for action in actions)
    publication = (RACINE / "docs/PUBLICATION.md").read_text(encoding="utf-8")
    assert "platform-image.yml" in publication
    assert "ghcr.io/bodichane/monl-platform:<tag>" in publication


def test_example_env_passes_production_validation():
    valeurs, erreurs_lecture = lire_env(RACINE / ".env.platform.example")
    assert valider(valeurs, erreurs_lecture) == []


def test_validation_refuse_un_domaine_local_ou_un_proxy_non_securise():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "localhost",
        "MONL_PLATFORM_PUBLIC_URL": "http://localhost",
        "MONL_COOKIE_SECURE": "0",
        "MONL_TRUST_PROXY": "0",
    })

    assert any("localhost" in erreur for erreur in erreurs)
    assert any("HTTPS" in erreur for erreur in erreurs)
    assert any("MONL_COOKIE_SECURE" in erreur for erreur in erreurs)
    assert any("MONL_TRUST_PROXY" in erreur for erreur in erreurs)


def test_validation_refuses_a_loopback_public_url():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://127.0.0.1",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("PUBLIC_URL" in erreur and "localhost" in erreur for erreur in erreurs)


def test_validation_requires_the_state_secret_if_oauth_is_enabled():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
        "MONL_OAUTH_GITHUB_CLIENT_ID": "client",
        "MONL_OAUTH_GITHUB_SECRET": "secret",
    })

    assert any("OAUTH_STATE_SECRET" in erreur for erreur in erreurs)


def test_validation_refuse_un_secret_detat_oauth_trop_court():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
        "MONL_PLATFORM_OAUTH_STATE_SECRET": "trop-court",
        "MONL_OAUTH_GITHUB_CLIENT_ID": "client",
        "MONL_OAUTH_GITHUB_SECRET": "secret",
    })

    assert any("32 characters" in erreur for erreur in erreurs)


def test_validation_allows_a_console_on_a_distinct_host():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "sites.monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://console.monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert erreurs == []


def test_validation_does_not_crash_on_a_malformed_url():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://[",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("HTTPS" in erreur for erreur in erreurs)
