#!/usr/bin/env sh
set -eu
umask 077

racine=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
compose_file=${COMPOSE_FILE:-"$racine/compose.platform.yaml"}
env_file=${ENV_FILE:-"$racine/.env"}
container_runtime=${CONTAINER_RUNTIME:-docker}

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
        printf 'Le dossier d’export doit être un chemin absolu.\n' >&2
        exit 2
        ;;
esac
if [ "$destination" = "/" ]; then
    printf 'Refus d’exporter directement vers la racine.\n' >&2
    exit 2
fi

mkdir -p "$destination"
chmod 700 "$destination"
conteneur=$("$container_runtime" compose --env-file "$env_file" -f "$compose_file" ps -q sauvegarde)
if [ -z "$conteneur" ]; then
    printf 'Le service sauvegarde n’est pas démarré.\n' >&2
    exit 1
fi

# `cp` lit le montage /backups du conteneur sans lancer une image auxiliaire
# ni demander un téléchargement réseau. La source n'est jamais modifiée.
"$container_runtime" cp "$conteneur:/backups/." "$destination/"

printf 'Sauvegardes exportées vers %s\n' "$destination"
