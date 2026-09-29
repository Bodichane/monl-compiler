# Web Platform and MCP Server

Monl keeps a single compilation authority. The command line, web platform, and MCP server call the same Python pipeline:
`monl.cli.compile_project`.

The platform does not generate design or run AI agents. It is used to:

1. explain the boundary between a free-form interface and compiled business logic;
2. enter or import a `.ml` specification;
3. validate and then compile the backend;
4. inspect the entities, actors, and contract routes;
5. download the backend, its SQL schema, and its contract;
6. expose the same operations to agents through MCP.

## Launch the platform

After installing the package:

```bash
monl-platform --host 127.0.0.1 --port 8022
```

Or from the repository:

```bash
python3 -m monl_platform --port 8022
```

The compilation workspace defaults to `platform-projects/`. To choose another location:

```bash
MONL_PLATFORM_WORKSPACE=/var/lib/monl monl-platform --host 0.0.0.0
```

For a containerized installation, the repository provides a non-root image and a persistent volume:

```bash
cp .env.platform.example .env
# Replace the domain and public URL in .env before starting.
python3 scripts/check_platform_env.py .env
docker compose -f compose.platform.yaml up --build -d
```

The port is exposed only on `127.0.0.1`: put an HTTPS reverse proxy in front of the service. `MONL_COOKIE_SECURE=1` requires HTTPS. Set `MONL_TRUST_PROXY=1` only if the proxy replaces the incoming public `X-Forwarded-For` header.

DNS must point the value of `MONL_PLATFORM_DOMAIN` and its wildcard to the proxy: each compiled project gets its own subdomain. An Nginx example ready to adapt (using `monl.example.com` as a placeholder) is in `deploy/nginx/monl-platform.conf.example`; the full runbook is in [`deploy/README.md`](../deploy/README.md). Check `/health` and `/ready` after TLS is set up and before opening registration.

Downloads never include `.jwt_secret`. The backend generates one on first startup, so a platform secret is not carried over.

## Web API

| Method | Route | Effect |
|---|---|---|
| `GET` | `/health` | Service status |
| `GET` | `/ready` | SQLite and storage availability |
| `POST` | `/api/auth/register` | Creates an account and session |
| `POST` | `/api/auth/login` | Opens a session |
| `POST` | `/api/auth/logout` | Revokes the active session |
| `GET` | `/api/templates` | Catalog of ten business templates |
| `POST` | `/api/validate` | Validation without persistent writes |
| `POST` | `/api/compile` | Backend and contract in an opaque project |
| `GET` | `/api/projects` | Projects for the active account |
| `GET` | `/api/projects/{id}` | Manifest and summary |
| `GET` | `/api/projects/{id}/contract` | Full frontend contract |
| `GET` | `/api/projects/{id}/download` | ZIP archive without secrets |
| `POST` | `/api/keys` | Creates an MCP key shown once |
| `DELETE` | `/api/keys/{id}` | Revokes an MCP key |
| `POST` | `/mcp` | MCP HTTP transport with a Bearer key |

The platform never accepts an output path provided by the client. A spec is limited to 256 KB and each project receives an opaque UUID.

## Local MCP over stdio

```json
{
  "mcpServers": {
    "monl": {
      "command": "monl-mcp"
    }
  }
}
```

From the repository, the equivalent command is:

```bash
python3 -m monl_platform.mcp_server
```

## MCP tools

- `monl_list_templates`: discover business templates;
- `monl_validate_spec`: get errors from the real parser and audit;
- `monl_compile_backend`: compile and receive the project ID and download address;
- `monl_list_projects`: find projects without having to remember an ID;
- `monl_inspect_contract`: read the manifest and full contract;
- `monl_diff_spec`: what a new spec would change in the interface, **without writing anything** (equivalent to `monl diff`);
- `monl_update_backend`: recompile an EXISTING project and receive the contract delta (equivalent to `monl update`). The ID and download address do not change; a refused spec leaves the project intact.

**The archive is fetched with the same key**: `GET` on `download_url` with `Authorization: Bearer <MCP key>`. No browser is needed — this was the last step that required the site. The address is absolute when `MONL_PLATFORM_PUBLIC_URL` is declared, relative otherwise; it is never derived from the `Host` header, which a third party controls.

The delta counts **ten categories** — routes, fields, access, read-only, prerequisites, payment locks, editorial content, associations, field types, required sections. This is not excessive caution: ten times (points 88 to 119), a change that touched no route left an entire screen to rewrite while the delta said “no interface changes.”

## Operational safeguards

- `scrypt` passwords, sessions, and keys stored only as fingerprints;
- projects isolated by account, expiring after 30 days by default;
- five login or registration attempts per minute per IP;
- ten compilations per hour per account, 120 MCP calls per minute;
- counters persisted in SQLite and shared between web workers;
- at most two simultaneous compilations per web process;
- each compilation runs in a subprocess bounded by CPU time, memory, file size, and number of file descriptors;
- the container is non-root, without capabilities, and read-only outside `/data`.

Operational values are configured with `MONL_PROJECT_RETENTION_DAYS`, `MONL_MAX_CONCURRENT_COMPILES`, `MONL_COMPILE_TIMEOUT_SECONDS`, `MONL_COMPILE_CPU_SECONDS`, `MONL_COMPILE_MEMORY_MB`, and `MONL_COMPILE_OUTPUT_MB`.
