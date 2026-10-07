# monl — Claude Code plugin

Describe your app in plain words, and Claude builds a working backend with a database, API, accounts and permissions — then checks that it runs.

## Try it

```text
/monl-compiler:monl-spec <what your app should do>
```

For example:

- A booking site with customer accounts and appointment reservations.
- A small shop with cart and payment.
- A team task board with assignments and progress tracking.

## What happens

1. Claude writes a short spec file describing your app.
2. monl compiles that file into the backend.
3. monl starts the backend on a local test server and checks that it works.

Under the hood: FastAPI, SQLite and JWT; the compiler is deterministic and uses no AI.

## Then build the interface

Once the backend runs, the `monl-frontend` skill helps Claude build its screens. What the site must do and how it should be laid out already comes from the compiled project (`docs/FRONTEND_PROMPT.md`, `frontend_contract.json`). The skill adds the step a test cannot do: Claude takes desktop and mobile screenshots of its own site, looks at them and fixes what it sees, such as cut-off text or a cramped mobile header.

## What the plugin runs, writes and downloads

The plugin contains no hooks or MCP servers. The `monl-spec` skill asks Claude to run the compiler:

- `monl` if already installed, or `uvx --from monl-compiler==1.0.0rc1 monl`, which downloads that exact package version and its dependencies from PyPI.
- It writes `spec.ml` and the compiled directory only in your project.
- Verification (`monl run --check`) starts a temporary local server with a fresh database, then stops it after the test.

The `monl-frontend` skill runs one script, `scripts/apercu.py` (Python standard library only):

- It copies the compiled project to a temporary directory, without its database, and serves it on `127.0.0.1` on a free port.
- It takes two screenshots with a local Chrome or Chromium in headless mode, then stops the server and removes the copy.
- It writes only the two images, in a temporary directory outside your project, and prints their paths.
- If it finds no browser, it says so and the skill tells Claude not to claim a visual review. Set `MONL_BROWSER` to choose one.

The compiler makes no network calls and sends no data elsewhere. The skill reads `reference/`, which contains exact copies of the language examples and grammar.

## Prerequisites

An environment that can run commands, typically Claude Code, with [uv](https://docs.astral.sh/uv/) or Python 3.10+ and `pip`.

## License and source

Functional Source License 1.1, Apache 2.0 Future License (`LicenseRef-FSL-1.1-ALv2`); [source, documentation and examples](https://github.com/Bodichane/monl-compiler).
