#!/usr/bin/env sh
# Library shared by the deployment scripts — not an executable.
#
# `compose ps -q <service>` (a single target) is Docker Compose v2:
# podman-compose 1.6.0 — the provider deploy/README.md recommends for
# Podman — refuses it ("unrecognized arguments"); its form of `ps` accepts
# no service name. BOTH providers, however, set the same label on every
# container they create (`com.docker.compose.service`): it is read back
# directly at runtime rather than depending on a `ps` syntax one of the two
# ignores. Checked for real (podman + podman-compose): the first attempt
# was Docker Compose v2 only and failed here.
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
