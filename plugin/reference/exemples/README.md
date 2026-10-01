# Specification Examples

The additional business functions of the dialogue are grouped into two
complete projects under `projets/`: `CommunauteHub` and `GestionPro`.

**Five `.ml` files, one page each: the complete description of five
applications.** This is the only thing written by hand. The database schema, REST
API, authentication, access control, and frontend contract are derived from it
at compile time.

| Specification | What it describes | What it demonstrates about the language |
|---|---|---|
| `01_portfolio.ml` | Public gallery + administration area | `public` for reading, contact form open for writing only, `seed` block |
| `02_boutique.ml` | Catalog and orders | Two actors, `ownedBy` on orders, pinned theme |
| `03_reseau_social.ml` | Anonymous social network | The densest: `generated` (pseudonym), `hidden`, `categorized`, `increments` / `decrements`, `accessibleBy` (private messaging) |
| `04_kanban.ml` | Team tasks | Ownership by record, including reading |
| `05_classement.ml` | Community ranking | Transactional counters: one vote raises a score |

## Reading and compiling them

```bash
monl compile exemples/01_portfolio.ml --output /tmp/portfolio
```

```bash
monl run /tmp/portfolio
```

Each file is commented: what is declared, and **why** this rule rather than
another. Reading them in order gives a progression from the simplest to the
most complete.

## What the test suite does with them

`tests/test_compile_all.py` compiles all five on each run, and
`tests/test_audit_offensif_exemples.py` reruns the offensive audit on each one — role
impersonation, forged JWT, privilege escalation. An example therefore cannot stop
compiling or become vulnerable without CI reporting it.

That is also what makes them reliable as documentation: syntax shown
here is necessarily syntax the compiler still accepts.
