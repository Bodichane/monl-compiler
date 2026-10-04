# Specification Examples

**Five `.ml` files, one page each: the complete description of five
applications.** This is the only thing written by hand. The database schema, REST
API, authentication, access control, and frontend contract are derived from it
at compile time.

| Specification | What it describes | What it demonstrates about the language |
|---|---|---|
| `01_portfolio.ml` | Public gallery + administration area | `public` for reading, contact form open for writing only, `seed` block (demo records), checked local images |
| `02_boutique.ml` | Catalog and orders | Product variants, owned orders and lines, server-calculated totals, stock changes, payments and cancellation |
| `03_reseau_social.ml` | Anonymous social network | The densest: `generated` (pseudonym), conditional public reads, moderation, `categorized`, `increments` / `decrements`, `accessibleBy` (private messaging) |
| `04_kanban.ml` | Public team board | Managers create, edit and delete tasks; contributors update status; `sharedBy` access |
| `05_classement.ml` | Community ranking | Public entries, self-registration, transactional counters: each vote raises a score |

## Reading and compiling them

In a repository clone, enter `exemples/` first. Inside the plugin, open the
examples folder under reference, or copy that entire folder to your workspace.
Run these commands from the folder containing the `.ml` files and `assets/`:

```bash
monl compile 01_portfolio.ml --output /tmp/portfolio
```

```bash
monl run /tmp/portfolio
```

Keep `assets/` beside the specs: the portfolio checks its logo, favicon and
cover files at compilation. These are ordinary files shipped with the plugin.
The examples use French sample data and comments.

Each file is commented: what is declared, and **why** this rule rather than
another. Reading them in order gives a progression from the simplest to the
most complete.

## What the test suite does with them

In the monl repository, `tests/test_compile_all.py` compiles all five on each run, and
`tests/test_audit_offensif_exemples.py` reruns the offensive audit on each one — role
impersonation, forged JWT, privilege escalation. CI reports compilation failures and regressions covered by these audits;
these checks do not guarantee that every possible vulnerability is detected.
The test files belong to the repository and are not shipped with the plugin.

That is also what makes them reliable as documentation: syntax shown
here is necessarily syntax the compiler still accepts.
