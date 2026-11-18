#!/usr/bin/env sh
set -eu
umask 077

racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}
env_file=${ENV_FILE:-"$racine/.env"}
container_runtime=${CONTAINER_RUNTIME:-docker}
. "$racine/scripts/lib_compose.sh"

case "$env_file" in
    /*) ;;
    *) env_file="$PWD/$env_file" ;;
esac
case "$compose_file" in
    /*) ;;
    *) compose_file="$PWD/$compose_file" ;;
esac

if [ "$#" -ne 1 ]; then
    printf 'Usage : %s /chemin/absolu/vers/export\n' "$0" >&2
    exit 2
fi

destination=$1
case "$destination" in
    /*) ;;
    *)
        printf 'The export folder must be an absolute path.\n' >&2
        exit 2
        ;;
esac
if [ "$destination" = "/" ]; then
    printf 'Refus d’exporter directement vers la racine.\n' >&2
    exit 2
fi

mkdir -p "$destination"
chmod 700 "$destination"
conteneur=$(find_container_by_service "$container_runtime" sauvegarde \
    $("$container_runtime" compose --env-file "$env_file" -f "$compose_file" ps -q) || true)
if [ -z "$conteneur" ]; then
    printf 'The backup service is not running.\n' >&2
    exit 1
fi

# `cp` reads the container's /backups mount without starting an auxiliary
# image or requiring a network download. The source is never modified.
"$container_runtime" cp "$conteneur:/backups/." "$destination/"

printf 'Backups exported to %s\n' "$destination"
