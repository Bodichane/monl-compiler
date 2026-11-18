#!/usr/bin/env sh
set -eu

racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
env_file=${ENV_FILE:-"$racine/.env"}
compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}
container_runtime=${CONTAINER_RUNTIME:-docker}
use_prebuilt_image=${USE_PREBUILT_IMAGE:-0}
python_bin=${PYTHON_BIN:-python3}
. "$racine/scripts/lib_compose.sh"

case "$use_prebuilt_image" in
    0|1) ;;
    *)
        printf 'USE_PREBUILT_IMAGE must be 0 or 1.\n' >&2
        exit 2
        ;;
esac

case "$env_file" in
    /*) ;;
    *) env_file="$PWD/$env_file" ;;
esac
case "$compose_file" in
    /*) ;;
    *) compose_file="$PWD/$compose_file" ;;
esac

compose() {
    if [ "$container_runtime" = podman ]; then
        # OCI does not carry HEALTHCHECK. The Docker format keeps it when
        # the podman-compose provider builds the image.
        "$container_runtime" compose --podman-build-args="--format docker" "$@"
    else
        "$container_runtime" compose "$@"
    fi
}

cd "$racine"
if ! command -v "$container_runtime" >/dev/null 2>&1; then
    printf 'Container runtime not found (%s).\n' "$container_runtime" >&2
    exit 1
fi
if ! command -v curl >/dev/null 2>&1; then
    printf 'curl is required to check local readiness.\n' >&2
    exit 1
fi
if ! command -v "$python_bin" >/dev/null 2>&1; then
    printf 'Python interpreter not found (%s); set PYTHON_BIN.\n' "$python_bin" >&2
    exit 1
fi
"$python_bin" scripts/check_platform_env.py "$env_file"
compose --env-file "$env_file" -f "$compose_file" config --quiet
if [ "$use_prebuilt_image" = 1 ]; then
    images=$(compose --env-file "$env_file" -f "$compose_file" config --images)
    case "$images" in
        *monl-platform:local*)
            printf 'USE_PREBUILT_IMAGE=1 requires a non-local MONL_PLATFORM_IMAGE.\n' >&2
            exit 2
            ;;
    esac
    while IFS= read -r image; do
        [ -n "$image" ] || continue
        image_ref=${image##*/}
        case "$image_ref" in
            *@sha256:*) ;;
            *:latest)
                printf 'USE_PREBUILT_IMAGE=1 refuses the mutable tag latest: %s\n' "$image" >&2
                exit 2
                ;;
            *:*) ;;
            *)
                printf 'USE_PREBUILT_IMAGE=1 requires a tag or a digest: %s\n' "$image" >&2
                exit 2
                ;;
        esac
    done <<EOF
$images
EOF
    compose --env-file "$env_file" -f "$compose_file" pull
    compose --env-file "$env_file" -f "$compose_file" up --detach
else
    compose --env-file "$env_file" -f "$compose_file" up --build --detach
fi
compose --env-file "$env_file" -f "$compose_file" ps

# `up -d` returns before readiness, and a first connection can be reset
# during initialization. An explicit loop also covers this case, which `curl
# --retry` does not always retry.
pret=false
for tentative in $(seq 1 90); do
    if curl --fail --silent --show-error --max-time 2 \
        http://127.0.0.1:8022/ready >/dev/null; then
        pret=true
        break
    fi
    sleep 1
done
if [ "$pret" != true ]; then
    printf 'The platform does not become ready on 127.0.0.1:8022.\n' >&2
    compose --env-file "$env_file" -f "$compose_file" logs --tail=100 platform || true
    exit 1
fi
backup_started=false
for tentative in $(seq 1 90); do
    backup_container=$(find_container_by_service "$container_runtime" sauvegarde \
        $(compose --env-file "$env_file" -f "$compose_file" ps -q) || true)
    if [ -n "$backup_container" ]; then
        backup_started=true
        break
    fi
    sleep 1
done
if [ "$backup_started" != true ]; then
    printf 'The backup service does not start.\n' >&2
    compose --env-file "$env_file" -f "$compose_file" logs --tail=100 sauvegarde || true
    exit 1
fi
backup_healthy=false
for tentative in $(seq 1 90); do
    backup_health=$("$container_runtime" inspect \
        --format '{{.State.Health.Status}}' "$backup_container" 2>/dev/null || true)
    if [ "$backup_health" = healthy ]; then
        backup_healthy=true
        break
    fi
    sleep 1
done
if [ "$backup_healthy" != true ]; then
    printf 'The backup service does not become healthy.\n' >&2
    compose --env-file "$env_file" -f "$compose_file" logs --tail=100 sauvegarde || true
    exit 1
fi
scripts/smoke_platform.sh http://127.0.0.1:8022
