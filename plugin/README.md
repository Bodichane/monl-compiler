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

Once the backend runs, five skills help Claude build its screens from what the backend actually allows: `monl-showcase`, `monl-design-system`, `monl-ui-patterns`, `monl-commerce` and `monl-operations`. Claude picks the ones that fit your app.

## What the plugin runs, writes and downloads

The plugin contains no hooks, MCP servers or scripts. The `monl-spec` skill asks Claude to run the compiler:

- `monl` if already installed, or `uvx --from monl-compiler==0.9.0b10 monl`, which downloads that exact package version and its dependencies from PyPI.
- It writes `spec.ml` and the compiled directory only in your project.
- Verification (`monl run --check`) starts a temporary local server with a fresh database, then stops it after the test.

The compiler makes no network calls and sends no data elsewhere. The skill reads `reference/`, which contains exact copies of the language examples and grammar.

## Prerequisites

An environment that can run commands, typically Claude Code, with [uv](https://docs.astral.sh/uv/) or Python 3.10+ and `pip`.

## License and source

Functional Source License 1.1, Apache 2.0 Future License (`LicenseRef-FSL-1.1-ALv2`); [source, documentation and examples](https://github.com/Bodichane/monl-compiler).
