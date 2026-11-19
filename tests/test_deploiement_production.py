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
    content = (RACINE / ".env.platform.example").read_text(encoding="utf-8")
    gitignore = (RACINE / ".gitignore").read_text(encoding="utf-8")

    assert "MONL_PLATFORM_DOMAIN=" in content
    assert "MONL_PLATFORM_PUBLIC_URL=" in content
    assert "MONL_COOKIE_SECURE=1" in content
    assert "MONL_TRUST_PROXY=1" in content
    assert "MONL_PLATFORM_OAUTH_STATE_SECRET=" in content
    assert "ghp_" not in content
    assert "sk_live_" not in content
    assert ".env.*" in gitignore
    assert "!.env.platform.example" in gitignore
    dockerignore = (RACINE / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in dockerignore
    assert ".env.*" in dockerignore


def test_compose_keeps_the_port_private_and_waits_for_readiness():
    content = (RACINE / "compose.platform.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8022:8022"' in content
    assert "image: ${MONL_PLATFORM_IMAGE:-monl-platform:local}" in content
    assert "condition: service_healthy" in content
    assert "MONL_PLATFORM_PUBLIC_URL" in content
    assert "MONL_PLATFORM_OAUTH_STATE_SECRET" in content
    assert "healthcheck:" in content
    assert "MONL_BACKUP_MAX_AGE_SECONDS" in content
    assert "retrying in 60 s" in content
    for variable in ("MONL_OAUTH_GITHUB_CLIENT_ID", "MONL_OAUTH_GITHUB_SECRET",
                     "MONL_OAUTH_GOOGLE_CLIENT_ID", "MONL_OAUTH_GOOGLE_SECRET"):
        assert variable in content


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
    policies = {
        name: service.get("restart")
        for name, service in compose["services"].items()
    }

    assert policies, "no service read: the witness would guard nothing"
    offenders = {name: valeur for name, valeur in policies.items()
               if valeur != "always"}
    assert not offenders, (
        f"these services will not come back after a restart: {offenders} — "
        f"only `always` enters podman-restart.service's filter"
    )


def test_the_folded_backup_command_is_valid_shell():
    compose = yaml.safe_load((RACINE / "compose.platform.yaml").read_text(encoding="utf-8"))
    order = compose["services"]["sauvegarde"]["command"][2]
    result = subprocess.run(["sh", "-n"], input=order, text=True, capture_output=True)

    assert result.returncode == 0, result.stderr


def test_proxy_passes_the_host_name_and_scheme():
    content = (RACINE / "deploy/nginx/monl-platform.conf.example").read_text(
        encoding="utf-8"
    )

    assert "monl.example.com *.monl.example.com" in content
    assert "proxy_set_header Host $host;" in content
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in content
    assert "return 301 https://$host$request_uri;" in content
    assert "127.0.0.1:8022" in content


def test_proxy_does_not_cap_uploads_below_what_the_app_accepts():
    """This block ALSO serves hosted sites (*.monl.example.com), one of which can
    declare `rule X.champ upload max N` up to 32 MiB (measured,
    tests/test_depot_depuis_le_dialogue.py). The original nginx cap was 256 KiB —
    well below the 5 MiB limit already exercised in the repository
    (test_limites_du_guide.py) — so an upload the compiled backend accepts would
    have been refused by the proxy, with a 413, before even reaching the
    application."""
    content = (RACINE / "deploy/nginx/monl-platform.conf.example").read_text(
        encoding="utf-8"
    )
    match = re.search(r"client_max_body_size\s+([0-9]+)([kKmMgG]?);", content)
    assert match, "no client_max_body_size declared"
    valeur, unite = match.groups()
    multiplier = {"": 1, "k": 1024, "m": 1024**2, "g": 1024**3}[unite.lower()]
    bytes_ = int(valeur) * multiplier

    LIMIT_UPLOAD_MAX_TESTEE = 32 * 1024 * 1024
    assert bytes_ >= LIMIT_UPLOAD_MAX_TESTEE, (
        f"client_max_body_size ({bytes_} bytes) is below an upload limit "
        f"already exercised by the suite ({LIMIT_UPLOAD_MAX_TESTEE} bytes): "
        "an upload valid for the application would be refused by the proxy.")


def test_smoke_platform_probes_both_endpoints_and_is_executable():
    script = RACINE / "scripts/smoke_platform.sh"
    content = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert "/health" in content
    assert "/ready" in content
    assert "curl --fail" in content


def test_deploy_script_chains_validation_compose_and_readiness():
    script = RACINE / "scripts/deploy_platform.sh"
    content = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert "check_platform_env.py" in content
    assert "config --quiet" in content
    assert "up --build --detach" in content
    assert 'container_runtime=${CONTAINER_RUNTIME:-docker}' in content
    assert 'use_prebuilt_image=${USE_PREBUILT_IMAGE:-0}' in content
    assert 'python_bin=${PYTHON_BIN:-python3}' in content
    assert 'Container runtime not found' in content
    assert 'curl is required' in content
    assert 'Python interpreter not found' in content
    assert "config --images" in content
    assert "non-local MONL_PLATFORM_IMAGE" in content
    assert "refuses the mutable tag latest" in content
    assert "requires a tag or a digest" in content
    assert "@sha256:" in content
    assert "compose --env-file \"$env_file\" -f \"$compose_file\" pull" in content
    assert "http://127.0.0.1:8022/ready" in content
    assert "for tentative in $(seq 1 90)" in content
    assert 'if [ "$pret" != true ]' in content
    assert "The platform does not become ready" in content
    assert "logs --tail=100 platform" in content
    # `compose ps -q <service>` is Docker Compose v2: podman-compose 1.6.0 —
    # the provider deploy/README.md recommends for Podman — refuses a service
    # name as argument. Tested for real (podman + podman-compose): the script
    # failed on "unrecognized arguments: sauvegarde". `lib_compose.sh` (single
    # source, shared with export_platform_backups.sh) reads the compose LABEL
    # both providers set, never a `ps` syntax one of them ignores.
    assert ". \"$racine/scripts/lib_compose.sh\"" in content
    assert "find_container_by_service" in content
    assert 'backup_started=false' in content
    assert 'if [ "$backup_started" != true ]' in content
    assert "The backup service does not start" in content
    assert "logs --tail=100 sauvegarde" in content
    assert 'backup_healthy=false' in content
    assert "{{.State.Health.Status}}" in content
    assert 'if [ "$backup_healthy" != true ]' in content
    assert "does not become healthy" in content
    assert 'if [ "$container_runtime" = podman ]' in content
    assert '--podman-build-args="--format docker"' in content
    assert "smoke_platform.sh http://127.0.0.1:8022" in content


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
        result = subprocess.run(
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
        assert result.returncode == 2
        assert "mutable tag latest" in result.stderr or "a tag or a digest" in result.stderr


def test_backup_export_is_bounded_to_a_host_folder():
    script = RACINE / "scripts/export_platform_backups.sh"
    content = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert 'racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)' in content
    assert 'compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}' in content
    assert 'env_file=${ENV_FILE:-"$racine/.env"}' in content
    assert 'container_runtime=${CONTAINER_RUNTIME:-docker}' in content
    # Same defect, same fix as deploy_platform.sh: `ps -q <service>` is not
    # supported by podman-compose (see the neighboring script's test).
    assert ". \"$racine/scripts/lib_compose.sh\"" in content
    assert "find_container_by_service" in content
    assert '--env-file "$env_file"' in content
    assert "/backups" in content
    assert 'umask 077' in content
    assert 'chmod 700 "$destination"' in content
    assert 'cp "$conteneur:/backups/." "$destination/"' in content
    assert 'alpine:3.20' not in content
    assert 'destination" = "/"' in content

    runbook = (RACINE / "deploy/README.md").read_text(encoding="utf-8")
    assert "sudo scripts/export_platform_backups.sh /var/backups/monl" in runbook

    relative = subprocess.run([str(script), "exports"], capture_output=True, text=True)
    assert relative.returncode == 2
    racine = subprocess.run([str(script), "/"], capture_output=True, text=True)
    assert racine.returncode == 2


def test_runbook_documents_dns_tls_and_offsite_backups():
    content = (RACINE / "deploy/README.md").read_text(encoding="utf-8")

    for expected in ("wildcard", "TLS certificate", "separate storage",
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
        assert expected in content, f"the runbook no longer says: {expected}"


def test_ci_builds_and_probes_the_platform_image():
    content = (RACINE / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "docker compose -f compose.platform.yaml config --quiet" in content
    assert "python scripts/check_platform_env.py .env.platform.example" in content
    assert "docker build --file Dockerfile.platform --tag monl-platform:ci ." in content
    assert "monl_platform.backup_healthcheck" in content
    assert "http://127.0.0.1:18022/ready" in content
    assert "{{.State.Health.Status}}" in content
    assert "healthy=false" in content
    assert 'test "$healthy" = true' in content
    assert "docker inspect --format '{{.Config.User}}' monl-platform-ci" in content
    assert "needs: verifier" in content


def test_documentation_no_longer_says_compose_backups_do_not_exist():
    content = (RACINE / "docs/EXPLOITATION.md").read_text(encoding="utf-8")
    assert "pas de sauvegarde automatique" not in content.lower()
    assert "sauvegarde" in content.lower()


def test_the_image_workflow_tests_then_publishes_ghcr():
    path = RACINE / ".github/workflows/platform-image.yml"
    content = path.read_text(encoding="utf-8")

    assert 'docker build --file Dockerfile.platform --tag monl-platform:release .' in content
    assert "monl_platform.backup_healthcheck" in content
    assert "{{.State.Health.Status}}" in content
    assert "ghcr.io/bodichane/monl-platform" in content
    assert "docker/login-action@v3.4.0" in content
    assert "docker/metadata-action@v5.6.1" in content
    assert "docker/build-push-action@v6.17.0" in content
    assert "packages: write" in content
    actions = [line.split("uses:", 1)[1].strip() for line in content.splitlines()
               if "uses:" in line]
    assert actions and all("@v" in action and action.rsplit("@v", 1)[1].count(".") == 2
                           for action in actions)
    publication = (RACINE / "docs/PUBLICATION.md").read_text(encoding="utf-8")
    assert "platform-image.yml" in publication
    assert "ghcr.io/bodichane/monl-platform:<tag>" in publication


def test_example_env_passes_production_validation():
    values, errors_read = lire_env(RACINE / ".env.platform.example")
    assert valider(values, errors_read) == []


def test_validation_refuses_a_local_domain_or_an_insecure_proxy():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "localhost",
        "MONL_PLATFORM_PUBLIC_URL": "http://localhost",
        "MONL_COOKIE_SECURE": "0",
        "MONL_TRUST_PROXY": "0",
    })

    assert any("localhost" in error for error in errors)
    assert any("HTTPS" in error for error in errors)
    assert any("MONL_COOKIE_SECURE" in error for error in errors)
    assert any("MONL_TRUST_PROXY" in error for error in errors)


def test_validation_refuses_a_loopback_public_url():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://127.0.0.1",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("PUBLIC_URL" in error and "localhost" in error for error in errors)


def test_validation_requires_the_state_secret_if_oauth_is_enabled():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
        "MONL_OAUTH_GITHUB_CLIENT_ID": "client",
        "MONL_OAUTH_GITHUB_SECRET": "secret",
    })

    assert any("OAUTH_STATE_SECRET" in error for error in errors)


def test_validation_refuses_a_too_short_oauth_state_secret():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
        "MONL_PLATFORM_OAUTH_STATE_SECRET": "trop-court",
        "MONL_OAUTH_GITHUB_CLIENT_ID": "client",
        "MONL_OAUTH_GITHUB_SECRET": "secret",
    })

    assert any("32 characters" in error for error in errors)


def test_validation_allows_a_console_on_a_distinct_host():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "sites.monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://console.monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert errors == []


def test_validation_does_not_crash_on_a_malformed_url():
    errors = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://[",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("HTTPS" in error for error in errors)
