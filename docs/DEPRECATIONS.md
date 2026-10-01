# Historical Compatibility and Deprecations

This file sets out the compatibility maintained during beta. A compatibility is removed only after a warning period and a migration test.

| Item | Current state | Recommended replacement |
|---|---|---|
| `*.yaml` | Accepted for older specs | Use `*.ml` |
| `landing.mode` / `landing.template` | Accepted, warning during validation, no effect on backend | Keep only `landing.brief`, `section`, and `question` |
| `run_claude_code()` | Alias retained for compatibility | Use `run_cli_agent(..., agent="claude-code")` or `generate_with_cli_agent()` |
| `generate_with_claude_code()` | Facade retained | Use `generate_with_cli_agent()` |

## Removal Rules

- Nothing will be removed without an internal usage search and a compatibility test.
- Warnings for `landing.mode` and `landing.template` are already emitted by the validator.
- `.yaml` extensions remain compilable while external examples or projects depend on them.
- Claude Code aliases will be removed only after a beta version explicitly announces the breaking change.

The `docs/phase_*.md` documents and `CODEBASE_AUDIT.md` describe design history and dated audits; they are not normative descriptions of the current architecture. For that, consult the [README](../README.md) and CI results.
