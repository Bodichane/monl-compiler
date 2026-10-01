# Platform deployment

These files prepare a Docker/Podman deployment behind a TLS reverse proxy.
They contain no secrets and do not replace the configuration of the
DNS or hosting provider.

The commands use Docker Compose v2 (`docker compose`). With Podman,
first install a compatible Compose provider (`podman-compose`,
for example), then run the scripts with `CONTAINER_RUNTIME=podman`;
the script then adds the Docker image format required to transport the
`HEALTHCHECK`. A Docker machine remains the simplest option.

**Two Podman pitfalls, both measured in production.**

*The PATH of a non-interactive session.* `podman-compose` is often installed
in `~/.local/bin`, which is NOT in the `PATH` of an `ssh server
'command'` — the script then fails with `looking up compose provider failed`
while listing seven paths, none of which is the right one. Remote deployment
therefore requires `export PATH="$HOME/.local/bin:$PATH"` before the call,
or an absolute path.

*Machine restart.* What restarts the containers after a
restart is `podman-restart.service`, whose command is
`podman start --all --filter restart-policy=always`. A service declared
`restart: unless-stopped` **is not included in this filter** and stays down
indefinitely. The compose file therefore declares `restart: always` everywhere, and a test
guards it. Check that the mechanism is armed:

```bash
loginctl enable-linger "$USER"          # otherwise nothing runs outside the session
systemctl --user enable --now podman-restart.service
```

Prove it to yourself WITHOUT restarting, by replaying exactly what boot does:

```bash
podman stop monl-compiler_platform_1
systemctl --user restart podman-restart.service
podman ps --format '{{.Names}} {{.Status}}'   # must be « Up »
```

A container that does not come back leaves **no trace**: it did not
crash; it never started. This is the quietest failure of the lot.

CI also builds `Dockerfile.platform`, starts the image, and checks its
healthcheck on every push: a packaging or readiness regression is
detected before manual deployment.

On a `v*` tag, the image workflow also publishes
`ghcr.io/bodichane/monl-platform` after this check. To use it, make the GHCR
package accessible to the server, then set `MONL_PLATFORM_IMAGE` to
a specific tag in `.env`, then run:

```bash
USE_PREBUILT_IMAGE=1 scripts/deploy_platform.sh
```

The local image remains the default fallback.
In `USE_PREBUILT_IMAGE=1` mode, the script refuses `latest` and references
without a tag; use an immutable release tag or a `sha256` digest.

## Prepare the machine

```bash
git clone https://github.com/Bodichane/monl-compiler.git
cd monl-compiler
cp .env.platform.example .env
$EDITOR .env
chmod 600 .env
python3 scripts/check_platform_env.py .env
```

Set at least `MONL_PLATFORM_DOMAIN` and
`MONL_PLATFORM_PUBLIC_URL`. If no OAuth provider is enabled,
`MONL_PLATFORM_OAUTH_STATE_SECRET` may remain empty. Never put a
real value in the repository.

DNS must point the value of `MONL_PLATFORM_DOMAIN` and its wildcard
(`*.MONL_PLATFORM_DOMAIN`, replacing this text with the real domain) to the
machine. The wildcard is required for the hosts assigned to
compiled projects.

The machine firewall must expose only TCP 80 and 443. Port 8022 is
bound to `127.0.0.1` and must never be opened directly to the Internet.

## Start

The recommended path chains validation, the Compose check, the build,
startup, local readiness, and the `healthy` state of the backup service:

```bash
scripts/deploy_platform.sh
```

Equivalent commands remain available if an operator needs to
intervene between two steps.

Port 8022 remains private. Install the reverse proxy and copy
`deploy/nginx/monl-platform.conf.example` into the Nginx configuration after
replacing the domain and installing the TLS certificate.

After enabling the proxy:

```bash
curl -fsS https://monl.example.com/health
curl -fsS https://monl.example.com/ready
./scripts/smoke_platform.sh https://monl.example.com
```

## Checks before opening

- sign-up, sign-in, and recovery with a backup code;
- compilation of a spec and download of the archive;
- creation and then revocation of an MCP key;
- isolation of projects between two accounts;
- explicit `503` response if a declared OAuth provider lacks a secret;
- backup created in `/backups`, then restoration tested on a copy;
- `healthy` state of the `backup` service after its first copy;
- external alert connected to `/ready`;
- renewable certificate and configured proxy logs.

The Compose backup remains on the same machine: export the files in the
`monl-platform-backups` volume to separate storage before opening.

To copy backups to a host directory without knowing the prefixed name
of the Compose volume:

```bash
sudo install -d -m 700 /var/backups/monl
sudo scripts/export_platform_backups.sh /var/backups/monl
```

Then synchronize `/var/backups/monl` to off-machine storage
(restic, S3, rsync to another host, etc.). The script never modifies the
source volume and refuses a relative export path or the root `/`.
