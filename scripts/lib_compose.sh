#!/usr/bin/env sh
# Bibliothèque partagée par les scripts de déploiement — pas un exécutable.
#
# `compose ps -q <service>` (une seule cible) est du Docker Compose v2 :
# podman-compose 1.6.0 — le fournisseur que deploy/README.md recommande pour
# Podman — le refuse (« unrecognized arguments »), sa forme de `ps` n'accepte
# aucun nom de service. Les DEUX fournisseurs posent en revanche le même
# label sur chaque conteneur qu'ils créent (`com.docker.compose.service`) :
# on le relit directement au runtime plutôt que de dépendre d'une syntaxe
# `ps` que l'un des deux ignore. Vérifié en réel (podman + podman-compose) :
# le premier essai était Docker Compose v2 seulement et échouait ici.
find_container_by_service() {
    runtime=$1
    service=$2
    shift 2
    for candidat in "$@"; do
        [ -n "$candidat" ] || continue
        label=$("$runtime" inspect --format \
            '{{ index .Config.Labels "com.docker.compose.service" }}' \
            "$candidat" 2>/dev/null || true)
        if [ "$label" = "$service" ]; then
            printf '%s\n' "$candidat"
            return 0
        fi
    done
    return 1
}
