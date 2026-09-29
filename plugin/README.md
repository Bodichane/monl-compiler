# monl — Claude Code plugin

monl compiles a declarative specification (a `.ml` file) into a complete
backend: a SQLite schema, a FastAPI REST API, JWT authentication, role-based
and record-level access control, and a contract describing the interface to
build. The compiler is deterministic and uses no AI.

This plugin teaches Claude to write that specification from a user's
requirements, compile it, prove the result against a real server, and then
build the application's interface.

## Skills

- **`monl-spec`** — from requirements to a verified backend: write `spec.ml`,
  compile it, read compiler rejections, run verification, and evolve the spec.
  Invoke with: `/monl-compiler:monl-spec <what the application should do>`.
- **`monl-showcase`**, **`monl-design-system`**, **`monl-ui-patterns`**,
  **`monl-commerce`**, **`monl-operations`** — build a compiled project's
  interface in accordance with its contract.

## What the plugin runs, writes, and downloads

The plugin contains no hooks, MCP servers, or scripts. The `monl-spec` skill
asks Claude to run the compiler's command-line interface:

- `monl`, if the user has already installed it; otherwise
  `uvx --from monl-compiler==0.9.0b10 monl`, which **downloads from PyPI** the
  `monl-compiler` package at that exact version and its dependencies;
- it writes `spec.ml` and the compiled directory **in the user's project**;
- verification (`monl run --check`) starts an ephemeral **local** server on a
  fresh database for the duration of a test, then stops it.

No data is sent elsewhere: the compiler makes no network calls. The
`reference/` directory contains exact copies of the language examples and
grammar, which the skill reads.

## Prerequisites

An environment that can run commands — typically Claude Code — with
[uv](https://docs.astral.sh/uv/) or Python 3.10+ and `pip`.

## License and source

Functional Source License 1.1, Apache 2.0 Future License
(`LicenseRef-FSL-1.1-ALv2`). Source code, documentation, and examples:
<https://github.com/Bodichane/monl-compiler>.
