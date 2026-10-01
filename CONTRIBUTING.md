# Working on monl

> **Status.** Public repository under **FSL-1.1-ALv2** — free use except
> competing use, conversion to Apache-2.0 after two years (see [LICENSE](LICENSE)
> and [LICENSE-FAQ.md](LICENSE-FAQ.md)).
> Outside contributions are not open at this time. This document describes how
> to work on the repository — it is for the maintainer, a future authorized
> collaborator, and any development AI working here. Bug reports and feedback
> are still welcome in the *issues*.

## Setup

```bash
pipx install -e ".[dev]" # or: pip install -e ".[dev]" --break-system-packages
python3 -m pytest tests/ -q
```

The suite takes about six minutes: it starts real servers. This is deliberate;
see below.

## The non-negotiable rule

**Every change is proven through real execution, never by code review alone.**
Compile for real, restart a real server, make real calls, run the suite.

This is not a decorative principle. Several real bugs in the project —
`FOREIGN KEY` constraint ordering, a collision with a reserved SQL keyword,
over-escaped backslashes between templating layers, a foreign key mechanism
that decremented the wrong record — would **never** have been found by reading
the code. Tests therefore start ephemeral servers and execute the real dialogue
instead of simulating it; that is why they are slow.

Corollary: a test that cannot fail is worthless. If you write a safeguard,
check that it still **detects** something — a silent check is worse than no
check, because it gives false confidence.

## Before opening a pull request

```bash
ruff check src tests                                   # zero findings expected
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing
python3 -m pytest tests/test_architecture.py -q        # architecture boundaries
```

CI reruns all of this on Python 3.10, 3.12, and 3.14, and `main` is protected:
nothing merges unless all three checks pass.

## Repository rules

**The journal comes first.** [`docs/design_decisions.md`](docs/design_decisions.md)
contains 74 points, each explaining *why* a rule exists, not just *what* it is.
**Consult it before adding anything**: some pitfalls cannot be inferred from the
code. Every structural decision should add a numbered point explaining what
was rejected and why.

**Exceptions include their reason.** A `ruff` exception without a written
justification in `pyproject.toml`, an orphaned `# noqa`, or a contract clause
that nothing checks: three ways to reopen a door the project deliberately
closed. A clause that nothing checks is not a clause.

**Boundaries are executable.** The compiler (`parser`, `ast_validator`,
`generator`) ignores the orchestrator; `tui.py` contains no dialogue logic;
`app_templates.py` is data, not code. `tests/test_architecture.py` checks this
— do not bypass it; fix the dependency.

**Determinism is established.** No AI and no network calls in the compiler:
same spec, same output, byte for byte. The only AI in the lifecycle builds the
frontend from the contract.

**Clean up after a manual compilation** (the test suite no longer dirties the
root):

```bash
rm -f app.py schema.sql sandbox_ai.py manage.py .jwt_secret .monl_theme_seed *.db \
      frontend_contract.json FRONTEND_PROMPT.md FRONTEND_UPDATE_PROMPT.md monl.json serve.py
```

## Commit messages

Format `type(scope): imperative summary`, followed by a body explaining
**why** — not the list of changed files, which `git diff` already shows. If the
change corresponds to a journal point, cite it by number.

```
fix(cohérence): le scellé du backend n'était mesuré par rien

Point 64 du journal. check_coherence vérifiait l'empreinte de la spec et
celle du contrat, mais seulement l'EXISTENCE de app.py — une retouche
manuelle passait sans un mot, pendant que 'monl run' affichait
« Cohérence statique vérifiée ».
```

## Where to make changes

| What you want to do | Where |
|---|---|
| Add a dialogue question | The relevant module in `src/monl/dialogue_engine/` |
| Add or change an application template | `src/monl/app_templates.py` |
| Add a `.ml` language keyword | The relevant module in `src/monl/parser/`, then `src/monl/ast_validator/` |
| Change what the backend generates | The relevant module in `src/monl/generator/` |
| Change what the frontend AI receives | The relevant module in `src/monl/frontend_contract/` |
| Add a launch check | The relevant module in `src/monl/cli/` (static) or `src/monl/smoke_test/` (real) |
| Understand *why* a rule exists | `docs/design_decisions.md` |
