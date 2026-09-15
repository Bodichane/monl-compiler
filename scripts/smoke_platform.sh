#!/usr/bin/env sh
set -eu

base_url=${1:-https://monl.example.com}
base_url=${base_url%/}

for endpoint in /health /ready; do
    printf 'GET %s%s ... ' "$base_url" "$endpoint"
    curl --fail --silent --show-error --max-time 10 "$base_url$endpoint" >/dev/null
    printf 'OK\n'
done

printf 'Plateforme joignable et prête : %s\n' "$base_url"
