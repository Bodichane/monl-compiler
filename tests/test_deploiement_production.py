"""Contrats statiques des artefacts de mise en ligne.

Ces tests ne démarrent pas Docker : ils empêchent qu'une modification de
configuration rende le runbook incohérent ou expose accidentellement un
secret dans le dépôt.
"""

import os
import re
import subprocess
from pathlib import Path

import yaml

from scripts.check_platform_env import lire_env, valider

RACINE = Path(__file__).parents[1]


def test_exemple_env_ne_contient_pas_de_secret_reel():
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


def test_compose_garde_le_port_prive_et_attend_la_readiness():
    contenu = (RACINE / "compose.platform.yaml").read_text(encoding="utf-8")

    assert '"127.0.0.1:8022:8022"' in contenu
    assert "image: ${MONL_PLATFORM_IMAGE:-monl-platform:local}" in contenu
    assert "condition: service_healthy" in contenu
    assert "MONL_PLATFORM_PUBLIC_URL" in contenu
    assert "MONL_PLATFORM_OAUTH_STATE_SECRET" in contenu
    assert "healthcheck:" in contenu
    assert "MONL_BACKUP_MAX_AGE_SECONDS" in contenu
    assert "nouvel essai dans 60 s" in contenu
    for variable in ("MONL_OAUTH_GITHUB_CLIENT_ID", "MONL_OAUTH_GITHUB_SECRET",
                     "MONL_OAUTH_GOOGLE_CLIENT_ID", "MONL_OAUTH_GOOGLE_SECRET"):
        assert variable in contenu


def test_chaque_service_remonte_apres_un_redemarrage_de_la_machine():
    """`always`, et jamais `unless-stopped` — la nuance coûte le service.

    Ce qui relance les conteneurs après un redémarrage, c'est
    `podman-restart.service`, dont la commande est
    `podman start --all --filter restart-policy=always`. Un conteneur déclaré
    `unless-stopped` n'entre pas dans ce filtre : il reste à terre.

    Mesuré sur la machine d'hébergement, pas déduit — après un redémarrage,
    `monl-nginx` (lancé en `always`) tournait, la plateforme était en `Created`
    depuis cinquante minutes, et **rien ne l'avait dit**. Un conteneur qui ne
    remonte pas ne laisse aucune trace : il n'a pas planté, il n'a jamais
    démarré.

    Le témoin porte sur TOUS les services, pas sur les deux d'aujourd'hui : un
    service ajouté plus tard hériterait sinon du défaut en silence.
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


def test_commande_de_sauvegarde_repliee_est_du_shell_valide():
    compose = yaml.safe_load((RACINE / "compose.platform.yaml").read_text(encoding="utf-8"))
    commande = compose["services"]["sauvegarde"]["command"][2]
    resultat = subprocess.run(["sh", "-n"], input=commande, text=True, capture_output=True)

    assert resultat.returncode == 0, resultat.stderr


def test_proxy_transmet_le_nom_hote_et_le_schema():
    contenu = (RACINE / "deploy/nginx/monl-platform.conf.example").read_text(
        encoding="utf-8"
    )

    assert "monl.example.com *.monl.example.com" in contenu
    assert "proxy_set_header Host $host;" in contenu
    assert "proxy_set_header X-Forwarded-Proto $scheme;" in contenu
    assert "return 301 https://$host$request_uri;" in contenu
    assert "127.0.0.1:8022" in contenu


def test_proxy_ne_plafonne_pas_les_depots_sous_ce_que_lapp_accepte():
    """Ce bloc dessert AUSSI les sites hébergés (*.monl.example.com), dont un
    peut déclarer `rule X.champ upload max N` jusqu'à 32 Mio (mesuré,
    tests/test_depot_depuis_le_dialogue.py). Le plafond nginx d'origine était
    de 256 Kio — bien en-dessous de la limite 5 Mio déjà exercée dans le
    dépôt (test_limites_du_guide.py) — donc un dépôt que le backend compilé
    accepte se serait fait refuser par le proxy, en 413, avant même
    d'atteindre l'application."""
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


def test_smoke_platform_sonde_les_deux_endpoints_et_est_executable():
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
    assert 'Runtime de conteneur introuvable' in contenu
    assert 'curl est requis' in contenu
    assert 'Interpréteur Python introuvable' in contenu
    assert "config --images" in contenu
    assert "MONL_PLATFORM_IMAGE non locale" in contenu
    assert "refuse le tag mutable latest" in contenu
    assert "exige un tag ou un digest" in contenu
    assert "@sha256:" in contenu
    assert "compose --env-file \"$env_file\" -f \"$compose_file\" pull" in contenu
    assert "http://127.0.0.1:8022/ready" in contenu
    assert "for tentative in $(seq 1 90)" in contenu
    assert 'if [ "$pret" != true ]' in contenu
    assert "La plateforme ne devient pas prête" in contenu
    assert "logs --tail=100 platform" in contenu
    # `compose ps -q <service>` est du Docker Compose v2 : podman-compose
    # 1.6.0 — le fournisseur que deploy/README.md recommande pour Podman —
    # refuse un nom de service en argument. Éprouvé en réel (podman +
    # podman-compose) : le script échouait sur « unrecognized arguments:
    # sauvegarde ». `lib_compose.sh` (source unique, partagée avec
    # export_platform_backups.sh) lit le LABEL de compose posé par les deux
    # fournisseurs, jamais une syntaxe `ps` que l'un des deux ignore.
    assert ". \"$racine/scripts/lib_compose.sh\"" in contenu
    assert "find_container_by_service" in contenu
    assert 'backup_started=false' in contenu
    assert 'if [ "$backup_started" != true ]' in contenu
    assert "Le service sauvegarde ne démarre pas" in contenu
    assert "logs --tail=100 sauvegarde" in contenu
    assert 'backup_healthy=false' in contenu
    assert "{{.State.Health.Status}}" in contenu
    assert 'if [ "$backup_healthy" != true ]' in contenu
    assert "ne devient pas healthy" in contenu
    assert 'if [ "$container_runtime" = podman ]' in contenu
    assert '--podman-build-args="--format docker"' in contenu
    assert "smoke_platform.sh http://127.0.0.1:8022" in contenu


def test_deploiement_refuse_une_image_preconstruite_mutable(tmp_path):
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
        assert "tag mutable latest" in resultat.stderr or "tag ou un digest" in resultat.stderr


def test_export_des_sauvegardes_est_borne_a_un_dossier_hote():
    script = RACINE / "scripts/export_platform_backups.sh"
    contenu = script.read_text(encoding="utf-8")

    assert script.stat().st_mode & 0o111
    assert 'racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)' in contenu
    assert 'compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}' in contenu
    assert 'env_file=${ENV_FILE:-"$racine/.env"}' in contenu
    assert 'container_runtime=${CONTAINER_RUNTIME:-docker}' in contenu
    # Même défaut, même correctif que deploy_platform.sh : `ps -q <service>`
    # n'est pas supporté par podman-compose (voir le test du script voisin).
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


def test_runbook_documente_le_dns_le_tls_et_les_sauvegardes_hors_site():
    contenu = (RACINE / "deploy/README.md").read_text(encoding="utf-8")

    for attendu in ("wildcard", "certificat TLS", "stockage séparé",
                    "smoke_platform.sh", "MONL_PLATFORM_PUBLIC_URL",
                    "check_platform_env.py", "chmod 600 .env",
                    "export_platform_backups.sh", "Dockerfile.platform",
                    "régression de packaging", "pare-feu", "TCP 80 et 443",
                    # Les deux pièges de Podman mesurés au point 189. Un
                    # document qui décrit une limite sans donner le remède
                    # qu'il connaît envoie travailler pour rien (point 166) :
                    # le témoin exige donc la CAUSE et le GESTE, pas juste le
                    # symptôme.
                    "podman-restart.service", "restart-policy=always",
                    "enable-linger", 'export PATH="$HOME/.local/bin:$PATH"'):
        assert attendu in contenu, f"le runbook ne dit plus : {attendu}"


def test_la_ci_construit_et_sonde_l_image_de_plateforme():
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


def test_documentation_ne_redit_pas_que_les_sauvegardes_compose_nexistent_pas():
    contenu = (RACINE / "docs/EXPLOITATION.md").read_text(encoding="utf-8")
    assert "pas de sauvegarde automatique" not in contenu.lower()
    assert "sauvegarde" in contenu.lower()


def test_le_workflow_d_image_teste_puis_publie_ghcr():
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


def test_exemple_env_passe_la_validation_de_production():
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


def test_validation_refuse_une_url_publique_loopback():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://127.0.0.1",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("PUBLIC_URL" in erreur and "localhost" in erreur for erreur in erreurs)


def test_validation_exige_le_secret_detat_si_oauth_est_active():
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

    assert any("32 caractères" in erreur for erreur in erreurs)


def test_validation_autorise_une_console_sur_un_hote_distinct():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "sites.monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://console.monl.example.com",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert erreurs == []


def test_validation_ne_plante_pas_sur_une_url_malformee():
    erreurs = valider({
        "MONL_PLATFORM_DOMAIN": "monl.example.com",
        "MONL_PLATFORM_PUBLIC_URL": "https://[",
        "MONL_COOKIE_SECURE": "1",
        "MONL_TRUST_PROXY": "1",
    })

    assert any("HTTPS" in erreur for erreur in erreurs)
