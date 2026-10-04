# Stability contract for 1.0

This is the compatibility policy for the first stable release. Beta releases
remain prereleases; this document does not declare that 1.0 has shipped.

## Guaranteed interfaces

- **Language:** existing valid specifications retain their meaning within a
  major release. The keywords, actions and types are recorded in
  [the language 1 witness](../tests/grammaire_v1.txt), extracted from the Lark
  productions in `src/monl/parser/grammaire.py`. `LANGUAGE_VERSION` is defined
  once in `src/monl/parser/version.py`. `monl --version` reports it and compile
  writes `language_version` in `monl.json`. This metadata is informational:
  older project states without it remain accepted; artifact freshness still
  uses regeneration and hashes, not version equality.
- **CLI:** the verbs `init`, `compile`, `run`, `update`, `diff`, `usage`,
  `migrate`, `frontend`, `retouche`, `import`, `assets add`, `assets list`,
  `content export`, and `content import` retain their documented purpose.
  Their parser and dispatch live in `src/monl/cli/dispatch.py`.
- **Frontend contract:** the JSON structure and field meanings of
  `frontend_contract.json` are public interfaces. `monl_contract_version`
  identifies the interface schema, independently of package and language
  versions. Its base is `CONTRACT_VERSION` in
  `src/monl/frontend_contract/fondations.py`; assembly may select the next
  schema for the brick-4 contract. Consumers must read the emitted value.
  Contract assembly lives in `src/monl/frontend_contract/assemblage.py`;
  [golden artifacts](../tests/test_golden_artifacts.py) guard its output.
- **Generated HTTP API:** for an unchanged specification, documented routes,
  HTTP methods, request/response shapes and authorization semantics remain
  compatible. Routes depend on the capabilities declared by the spec; the
  generated contract and OpenAPI describe that application's API.
  `401` means missing, invalid or expired authentication; `403` means denied
  permission (including registration of a non-self-registering actor);
  `404` means missing or deliberately hidden resources; `409` means a state
  or integrity conflict; `422` means invalid request data. These behaviors
  are implemented in `src/monl/generator/` (runtime authentication, access
  checks, payment/stock guards and Pydantic schemas).
- **Deployment configuration:** the environment variables and their documented
  meanings in [SECURITE.md](SECURITE.md#deployment-settings-environment-variables)
  are supported interfaces. [The variable witness](../tests/test_securite_variables.py)
  compares that documentation with generated code in both directions.

## Outside this guarantee

The internal generated Python code, helper names and file implementation are
not a library API. The hosted platform and the AI frontend prompts are outside
this compiler stability contract. AI-generated frontend output is not
reproducible or covered by language compatibility.

## Versioning and deprecation

Package releases follow semantic versioning: patches fix compatible behavior,
minor releases add compatible capabilities, and major releases may break
public interfaces. A language break requires both a `LANGUAGE_VERSION`
increment and a package major release. Keep historical witnesses and add a
witness for the new language version. Compatible keywords must be added to
the current witness; removing a recorded keyword without a language increment
fails `tests/test_architecture.py`. This lexical ratchet complements the
semantic tests and the compilation of every repository and plugin example in
[tests/test_compile_all.py](../tests/test_compile_all.py); it cannot prove
semantic equivalence by itself.

**One exception, stated rather than hidden:** a minor release may start
refusing a specification whose compiled behavior was a security or correctness
defect — a rule that silently did the wrong thing. monl has done this before:
`payable` with a client-writable amount (point 79) and a counter on an entity
named like an actor (point 199, which lowered the wrong profile's score).
Such a refusal always names the cause and the fix in the compiler message, and
is listed in the release notes. Keeping the old behavior would preserve the
defect, not compatibility.

A deprecated public interface remains available for at least one minor release
with a warning, a documented replacement and a migration test before removal.
Removal that breaks a public interface requires a major release. The inventory
and removal rules live in [DEPRECATIONS.md](DEPRECATIONS.md).
