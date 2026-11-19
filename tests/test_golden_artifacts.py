"""Golden tests of the deterministic artifacts of a representative spec."""

import hashlib
from pathlib import Path

from monl.cli import compile_project

SPEC = """app Golden

entity Note
    titre: String
    publiee: Boolean

actor Auteur selfRegister

rule Note.Read public

workflow Ecrire for Auteur
    Create Note
    Read Note
"""

# Backend bench dedicated to the two sources added at point 181. It stays
# separate from SPEC: the historical golden must keep proving that the
# artifacts of a spec without these rules do not change. Here, the two extra
# indexes are indeed present in _LOOKUP_INDEXES.
SPEC_LOOKUP_SOURCES = """app GoldenLookup

entity Note
    titre: String
    status: String

entity Message
    contenu: Text
    member_id: Integer
    recipient_id: Integer

actor Reader selfRegister

rule Note.Read publicWhen status "published"
rule Message.Read accessibleBy member_id, recipient_id

workflow Lire for Reader
    Read Note
    Read Message
"""

# WAL startup now retries within the busy timeout and propagates expiry. POINT
# 201: the three benches gain the field_validator import in app.py. monl.json
# seals this fingerprint and language_version (point 200). All other measured
# artifacts stay byte-identical. ENGLISH MIGRATION, BATCH 3: every artifact
# carrying READ text changes — error messages of app.py and manage.py,
# schema.sql header, serve.py wrapper, contract notes, frontend brief,
# AGENTS.md and README.md; monl.json seals these fingerprints. The scope check
# holds: Dockerfile, requirements.txt and .dockerignore stay byte-identical —
# translating touches neither dependencies nor deployment.
GOLDENS = {
    # PROJECT A1: app.py carries the dialect choice at startup, PostgreSQL
    # migrations and structured integrity errors. schema.sql changes too, to
    # use DOUBLE PRECISION on SQLite/PostgreSQL. manage.py now reuses the
    # backend connection. monl.json moves because it seals the generated
    # backend's fingerprint. Two A1 review fixes move app.py and manage.py a
    # second time: the integrity `except` ends with an unconditional `raise`
    # (without it a fourth kind of error came out raising nothing), and
    # manage.py imports app.py from _connect() and not at the top of the file
    # (imported at the top, it stopped working from another folder). POINT 132:
    # the base now starts without dying on a database another process is
    # writing — tolerant `_activer_wal`, and initialization retried. The change
    # lives in the RUNTIME, so only app.py and monl.json (which seals its
    # fingerprint) move: schema.sql, manage.py and the Dockerfile stay byte for
    # byte, which is the scope check. Generating a JWT secret at the first
    # start of an archive without `.jwt_secret` is a second runtime change:
    # app.py and monl.json move deliberately, the other artifacts stay
    # unchanged. POINT 138: the calling code now applies even without a leading
    # zero (it only canonicalized a European number). Normalization lives in
    # the TWO places that must stay identical, so app.py AND manage.py move,
    # plus monl.json which seals the backend fingerprint. schema.sql, the
    # contract, the brief, the wrapper and the container stay byte for byte:
    # the fix only touches the account identifier. This project adds
    # `_LOOKUP_INDEXES` and the intermediate dependency `_identite_du_jeton` in
    # the compiled runtime: app.py really changes. The PostgreSQL pool is also
    # a runtime evolution: app.py carries its settings, its closing in the
    # lifespan and its explicit fallback; monl.json seals its fingerprint.
    # schema.sql, manage.py and requirements.txt stay out of scope:
    # psycopg[pool] is the compilation extra, not a dependency of the delivered
    # project. POINT 191: the real diff adds the list of oneOf columns reserved
    # to after-payment and generalizes point 89's SINGLE loop counting
    # unrecoverable NULLs. No route nor contract changes here.
    "app.py": "0cb4c86e4ef7e1a9b469862489884c5deec653ba1d34317eb55f036169c9833c",
    "schema.sql": "e33bc5b4cf0dbf78cb0290372e41521db6752de5691f43a9566b79e8137641be",
    # `sandbox_ai.py` LEAVES the fingerprints, and it is not a loosening: the
    # bench spec has no `custom` block, so the module is no longer produced. It
    # only held a comment, `app.py` imported it without ever calling it, and
    # deleting it made startup fail — a file that does nothing and cannot be
    # removed. Its absence is ASSERTED below rather than merely no longer
    # looked at, and its presence with a `custom` block is guarded by
    # `tests/test_bloc_custom_absent.py`. app.py therefore loses its import
    # line: its fingerprint changes with it.
    "manage.py": "252dc4b6f1c87a488be8f84423a418b7c348e56cc28fa3752a0669b2e4cadc83",
    # POINT 133: the Dockerfile ran `app:app`, so the image served the API and
    # answered 404 on /site and on photos — the wrapper mounting them was only
    # written by 'monl run'. It is now produced by 'monl compile' and the CMD
    # runs it. serve.py enters here: an artifact produced and not pinned would
    # be a blind spot, and it decides which folders are served. app.py,
    # schema.sql, manage.py and sandbox_ai.py do NOT move — the change's scope
    # check.
    "serve.py": "29767912bcffa904b3b9afca78d22b449c8862298572b5367e3ec80b29e40993",
    # THE DOCKERFILE NO LONGER LISTS ANY DEPENDENCY: it installs `-r
    # requirements.txt`. Two lists to keep in agreement always diverge, and
    # this one diverged already — the template only added 'python-multipart' if
    # the spec declares an Upload, while requirements.txt ALWAYS listed it. It
    # also now says that MONL_ENV=production makes MONL_JWT_SECRET mandatory:
    # the container refused to start without it, and one had to read its logs
    # to learn it. ONLY the Dockerfile and requirements.txt move — app.py,
    # schema.sql, manage.py, the contract, the brief and the wrapper stay byte
    # for byte: the scope check of a change that only touches deployment.
    "Dockerfile": "4c19d2ee5a783537c784ddfcc69472c658ec9381088e6e17efc9aff488a31f0f",
    # requirements.txt was followed by NO fingerprint while it ships in every
    # archive: an artifact nobody looks at can change without anyone knowing.
    "requirements.txt": "27a4075fed32b2a5edc575357721c5946ed99054bd0488bc219463d077f9ea06",
    ".dockerignore": "7b7115e2c802900c8522a4090b06ad13d6f7733dcba154ee3bd392020219ff0b",
    # A2 adds the _monl_migrations history and the additive/explicit migration
    # runtime; these artifacts stay deterministic. The contract and the brief
    # stay byte-identical: A2 does not change what the frontend must draw.
    # AUTHENTICATION CONTRACT: the contract and the brief now NAME the fields
    # /register and /login return (`access_token`, `token_type`, `status`,
    # `user_id`) instead of announcing "a JWT token" without saying under which
    # name to read it. Only these two artifacts move, plus monl.json which
    # seals their fingerprint: app.py, schema.sql and manage.py stay
    # byte-identical — proof that the fix is about what the backend DECLARES,
    # not what it does. BRICK 30: the contract carries `links`, the list of
    # OUTGOING addresses declared in `landing`. It is empty here, and the
    # fingerprint moves anyway: the KEY now always exists, like `faq` in its
    # time. Only the contract, the brief and monl.json change — app.py,
    # schema.sql and manage.py stay byte-identical, proof that the brick is
    # about what the frontend must DRAW and not what the backend does.
    "frontend_contract.json": "d3cfebcebc8bdc43f98bc59363d67f62b7baf652f49d73030312041f7972a92c",
    # The brief gains the workflow coverage floor, the explicit ban on local
    # image files outside the manifest and the inline SVG alternative, then the
    # executable map of required markers: this fingerprint changes deliberately
    # with these rules, while the backend artifacts stay byte-identical. POINT
    # 176: documents go into `docs/` and the project memory is called
    # AGENTS.md. The brief changes fingerprint for a reason of SUBSTANCE and
    # not only location — it tells the AI where to find the visual direction,
    # so it had to learn the new paths. `README.md` enters here because it
    # ships: an artifact nobody looks at can change without anyone knowing,
    # same argument as requirements.txt. THE SCOPE CHECK: app.py, schema.sql,
    # manage.py, serve.py, the contract, the Dockerfile and monl.json stay
    # byte-identical — tidying files touches nothing of what the backend DOES.
    "docs/FRONTEND_PROMPT.md": "584f80272c12f7b8a2df9e9cfc63de854ee520a7a67b68a42567cf6481d4e403",
    "AGENTS.md": "cdf84f9c37cbc5b23818d9f769704285a11c52ce7f48149f390bb19d3a5188c8",
    "README.md": "a20e092d4391b8de165f8ec3b705b55828dcb3ed89373a20492c198ff7c89be7",
    # A2 review: manage.py NAMES the remedy instead of letting a traceback slip
    # when the database awaits a migration. app.py does NOT move — proof that
    # the fix only touches the administration command. 0.9.0-beta.7, then
    # beta.8, then BRICK 30: monl.json moves for TWO distinct causes — it seals
    # the compiler version number, and the contract's fingerprint, which just
    # gained its `links` key. Both add up, so at each merge the fingerprint is
    # NEITHER side's and must be recomputed. Taking either one would give a
    # test that passes while proving nothing. All other artifacts stay
    # byte-identical, three times in a row: that is what this test is here to
    # hold. monl.json seals the fingerprint of this new app.py; no other
    # artifact is touched by the two backend fixes. 0.9.0-beta.9: only
    # monl.json moves, and `diff -r` between two compilations of the same code
    # under beta.8 then beta.9 shows only one line — `compiler_version`. The
    # fourth version in a row where this is true. POINT 191: the real diff only
    # changes backend_sha256.app.py, reflecting the counting loop above; every
    # other fingerprint is fixed. 0.9.0-beta.10: `diff -r` between two
    # compilations of the same code under beta.9 then beta.10 only shows
    # `compiler_version` (and `.jwt_secret`, random, outside this test). The
    # fifth version in a row.
    "monl.json": "045e6e116e2d43a62952a5bfd5a24c4e8dbafdc8658cc861b5e1a3a897ec4da9",
}

# POINT 203: app.py gains the global security ASGI envelope; monl.json seals
# its fingerprint. The other artifacts stay identical.

# Fingerprints of the fixture that really carries `publicWhen` and
# `accessibleBy`: the fix adds the `status` and `recipient_id` indexes to the
# runtime, and monl.json seals the new app.py.
LOOKUP_GOLDENS = {
    # Recomputed when merging points 182 and 183: each branch had written ITS
    # fingerprint, and the combined code produces a THIRD one. git's automatic
    # merge did not report it — only this test did. Checked before writing it
    # again: the measured app.py does carry the pool (`_close_database_pool`)
    # AND the `accessibleBy`/`publicWhen` indexes (`recipient_id` in
    # `_LOOKUP_INDEXES`), and nothing else moved. POINT 191: same runtime diff
    # as the main golden — new after-payment list empty here, and counting
    # shared with timestamps.
    "app.py": "6c96a32742129565c9027ea1e6b28e3d64a750d0933bf36f49d403282af04037",
    # 0.9.0-beta.9: monl.json alone, for the same reason as above. POINT 191:
    # the real diff only changes the sealed app.py fingerprint. 0.9.0-beta.10:
    # monl.json alone, `compiler_version`, as above.
    "monl.json": "1291a22be672f206e608f0b5b515127faf2171fd34498d2453a0963223fe483a",
}


def _empreintes(project_dir: Path):
    return {
        name: hashlib.sha256((project_dir / name).read_bytes()).hexdigest()
        for name in GOLDENS
    }


def test_a_recompilation_keeps_the_artifacts_deterministic(tmp_path, capsys):
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert _empreintes(tmp_path) == GOLDENS
    _no_useless_custom_module(tmp_path)

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    assert _empreintes(tmp_path) == GOLDENS
    _no_useless_custom_module(tmp_path)


def test_two_folders_produce_the_same_sources(tmp_path, capsys):
    """The output path and the local secret must not contaminate the sources."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC, encoding="utf-8")
    premier, second = tmp_path / "premier", tmp_path / "second"
    premier.mkdir()
    second.mkdir()

    compile_project(str(spec), str(premier))
    capsys.readouterr()
    compile_project(str(spec), str(second))
    capsys.readouterr()

    for name in GOLDENS:
        assert (premier / name).read_bytes() == (second / name).read_bytes(), name


def test_the_point_181_filter_sources_are_in_the_golden(
        tmp_path, capsys):
    """The backend golden exercises the two filter families added."""
    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC_LOOKUP_SOURCES, encoding="utf-8")

    compile_project(str(spec), str(tmp_path))
    capsys.readouterr()
    empreintes = _empreintes(tmp_path)
    assert {name: empreintes[name] for name in ("app.py", "monl.json")} == {
        name: LOOKUP_GOLDENS[name] for name in ("app.py", "monl.json")
    }


def _no_useless_custom_module(project_dir: Path):
    """Removing a fingerprint ASSERTS nothing — no longer looking is not a
    guarantee. The bench spec having no `custom` block, the module's absence is
    the expected result, and that is what is measured.

    Its PRESENCE when a `custom` block exists is guarded elsewhere
    (`tests/test_bloc_custom_absent.py`): without this counter-proof, never
    emitting it again would make both files green while killing the brick.
    """
    assert not (project_dir / "sandbox_ai.py").exists(), (
        "un module 'custom' vide est livré alors que la spec n'en déclare aucun")


# D3–D5: only the B4 artifacts carry the session version, the password required
# for TOTP, operator recovery and their documentation. The two historical
# benches above stay byte-identical.
B4_GOLDENS = {
    'app.py': '0d08ea56e0dc1b5a29db96a8e768e5bf9e3316767143497f015df55eddc54bf3',
    'schema.sql': 'e433095c18c9ecdbd10fe9b91e47d4ed9d68ad1907260dd4ae72963cd5078117',
    'manage.py': '8890b92555cde836199dca66d97721f38eeb52c23eccae563134ae3d2a0df310',
    'frontend_contract.json': 'd401b1bb32e18760c2d4731ce0f506fe0265efe6744639d5200a304a5825a482',
    'README.md': 'e443518e613cc0c531ad30c7c7ad54290873380700cc70f6e7cee100821f6d6d',
    'monl.json': '1c081522d4bb96d3689528e91d2d3aedb7beadf32614d65f982b987ebc631618',
}


def test_empreintes_b4_securite(tmp_path, capsys):
    from tests.test_authentification_b4 import SPEC_B4

    spec = tmp_path / "spec.ml"
    spec.write_text(SPEC_B4, encoding="utf-8")
    for _ in range(2):
        compile_project(str(spec), str(tmp_path))
        capsys.readouterr()
        assert {name: hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
                for name in B4_GOLDENS} == B4_GOLDENS
