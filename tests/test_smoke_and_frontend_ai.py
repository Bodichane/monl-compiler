# Tests of the behavioral smoke test (point 1) and of the frontend AI loop
# (point 4). Faithful to the project's method: real ephemeral servers, never
# mere rereading — only the AI PROVIDER is fake (orchestration itself runs for
# real end to end).
import json
import pathlib

import pytest

from monl.cli import compile_project
from monl.design_system import activate_asset_manifest
from monl.frontend_ai import (
    RETOUCH_PROMPT_FILENAME,
    FrontendAIError,
    generate_and_verify,
    parse_files_payload,
    parse_single_file_payload,
)
from monl.smoke_test import run_smoke_test

SPEC = """app SmokeApp

entity Item
    label: String
    price: Money

# Admin is provisioned offline; these tests' minimal frontend is not a promise
# of a public back office.
actor Admin

rule Item.label required
rule Item.Read public

workflow ManageItem for Admin
    Create Item
    Read Item
    Update Item
    Delete Item

seed Item
    label: "Alpha", price: 9.5
    label: "Beta", price: 19.5
"""

GOOD_FRONT = """<!doctype html><html><body><div id="l"></div>
<script>
fetch('/item?limit=5').then(r => r.json()).then(d => {
  document.getElementById('l').textContent = d.data.map(i => i.label).join(', ');
});
</script></body></html>"""

BAD_FRONT = ("<!doctype html><html><body><script>"
             "fetch('/fantome/1'); casse();</script></body></html>")

ABSOLUTE_FRONT = ("<!doctype html><html><body><script>"
                  "fetch('http://127.0.0.1:8000/item?limit=5');"
                  "</script></body></html>")


@pytest.fixture()
def project(tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "spec.ml").write_text(SPEC, encoding="utf-8")
    compile_project(str(proj / "spec.ml"), str(proj))
    return proj


def _quiet(*_a, **_k):
    pass


def test_smoke_passes_without_frontend_and_does_not_touch_the_database(project):
    # Sentinel: a real database with marker content.
    sentinel = project / "app.db"
    sentinel.write_bytes(b"donnees-reelles-intouchables")
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert ok, errors
    assert sentinel.read_bytes() == b"donnees-reelles-intouchables", (
        "the smoke test modified the project's real database")


def test_smoke_validates_a_correct_frontend(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(GOOD_FRONT, encoding="utf-8")
    ok, errors, warnings = run_smoke_test(str(project), say=_quiet)
    assert ok, errors
    # the initial fetch was indeed observed (not a silent false positive)
    assert not any("the frontend made no API calls" in w for w in warnings)


def test_coherence_refuses_a_missing_local_image(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="missing.svg"></body></html>',
        encoding="utf-8")
    activate_asset_manifest(str(project))
    from monl.frontend_ai import _frontend_local_reference_errors
    errors = _frontend_local_reference_errors(str(project))
    assert any("local resource missing" in error for error in errors)


def test_coherence_refuses_each_of_the_three_missing_local_svgs(project):
    front = project / "frontend"
    front.mkdir()
    paths = (
        "assets/product/vase-rondeur.svg",
        "assets/product/bol-terre.svg",
        "assets/product/plateau-ligne.svg",
    )
    sources = "".join(f'<img src="{path}">' for path in paths)
    (front / "index.html").write_text(
        f"<!doctype html><html><body>{sources}</body></html>",
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors

    errors = _frontend_local_reference_errors(str(project))
    missing = [error for error in errors if "local resource missing" in error]
    assert len(missing) == len(paths)
    for path in paths:
        assert sum(path in error for error in missing) == 1


def test_a_render_template_is_not_a_file_path(project):
    # A <script> body is not markup: `src="${...}"` there designates an image
    # the API will return. Read as a tag, it made the very form the contract
    # ASKS FOR (rendering the API's real images) be refused — it is the form of
    # demo/ and projets/CodexShop.
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<!doctype html><html><body><div id="l"></div>'
        '<script>const carte = (p) => `<img src="${esc(p.imageUrl)}" alt="">`;'
        '</script><script src="app.js"></script></body></html>',
        encoding="utf-8")
    (front / "app.js").write_text("const esc = (s) => String(s);", encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    assert _frontend_local_reference_errors(str(project)) == []


def test_the_absolute_site_mount_path_is_served_but_not_outside_site(project):
    # serve.py mounts frontend/ on /site: `/site/hero.svg` is exactly what the
    # wrapper serves (form of projets/StudioNova, checked as 200 against a real
    # server). `/hero.svg`, served by nobody, is the faulty one.
    front = project / "frontend"
    front.mkdir()
    (front / "hero.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="/site/hero.svg"></body></html>',
        encoding="utf-8")
    assert _frontend_local_reference_errors(str(project)) == []
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="/hero.svg"></body></html>',
        encoding="utf-8")
    assert any("jamais servie" in error
               for error in _frontend_local_reference_errors(str(project)))


def test_a_declared_but_missing_assets_folder_falls_back_on_frontend(project):
    # The wrapper only mounts the assets folder if it EXISTS on disk. Declared
    # in the spec does not mean present: when it is missing, the request falls
    # back on /site and `assets/x.svg` is served from frontend/assets/. Taking
    # the contract at its word made three projets/KoraMaison images that answer
    # 200 be refused.
    contract_path = project / "frontend_contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["assets"] = {"dir": "assets"}
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    front = project / "frontend"
    (front / "assets").mkdir(parents=True)
    (front / "assets" / "photo.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1"/>',
        encoding="utf-8")
    (front / "index.html").write_text(
        '<!doctype html><html><body><img src="assets/photo.svg"></body></html>',
        encoding="utf-8")
    from monl.frontend_ai import _frontend_local_reference_errors
    assert _frontend_local_reference_errors(str(project)) == []

    # The root folder exists: IT is what is mounted, and the file is looked up
    # there — a namesake frontend/assets/ no longer saves it.
    (project / "assets").mkdir()
    assert any("local resource missing" in error
               for error in _frontend_local_reference_errors(str(project)))


def test_smoke_blocks_a_broken_frontend(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(BAD_FRONT, encoding="utf-8")
    ok, errors, _w = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("casse" in e for e in errors), errors          # exception JS
    assert any("/fantome" in e for e in errors), errors        # hors contrat


def test_smoke_names_the_absolute_url_instead_of_fetch_failed(project):
    """Regression (point 51): with the ephemeral server listening on a free port,
    a frontend hard-targeting 8000 failed with 'TypeError: fetch failed' — a
    message silent about the cause, on which automatic correction went round in
    circles twice before giving up. The failure must stay a failure (this port
    would also break 'monl run --port'), but named."""
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(ABSOLUTE_FRONT, encoding="utf-8")
    ok, errors, warnings = run_smoke_test(str(project), say=_quiet)
    assert not ok
    assert any("Absolute URL forbidden" in e for e in errors), errors
    # The attempt counts as a call: otherwise the report would conclude "no API
    # call on load", which is false and muddles the trail.
    assert not any("the frontend made no API calls" in w for w in warnings), warnings


def test_parse_files_payload_guards_crazy():
    with pytest.raises(FrontendAIError):   # path traversal
        parse_files_payload(json.dumps({"files": {"../evil.html": "x", "index.html": "x"}}))
    with pytest.raises(FrontendAIError):   # extension interdite
        parse_files_payload(json.dumps({"files": {"index.html": "x", "run.py": "x"}}))
    with pytest.raises(FrontendAIError):   # index.html manquant
        parse_files_payload(json.dumps({"files": {"app.js": "x"}}))
    # Markdown fences tolerated despite the instruction
    fenced = "```json\n" + json.dumps({"files": {"index.html": "ok"}}) + "\n```"
    assert parse_files_payload(fenced) == {"index.html": "ok"}


def test_parse_single_file_payload_accepts_a_css_without_index():
    payload = json.dumps({"files": {"styles.css": "body { color: #111; }"}})
    assert parse_single_file_payload(payload, "styles.css") == {
        "styles.css": "body { color: #111; }"
    }
    with pytest.raises(FrontendAIError):
        parse_single_file_payload(
            json.dumps({"files": {"app.js": "ok"}}), "styles.css")


def test_standard_svg_is_accepted_but_a_remote_resource_is_refused():
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8"><circle cx="4" cy="4" r="3"/></svg>'
    assert parse_single_file_payload(
        json.dumps({"files": {"hero.svg": svg}}), "hero.svg")["hero.svg"] == svg
    distant = '<svg xmlns="http://www.w3.org/2000/svg"><image href="https://exemple.test/photo.png"/></svg>'
    with pytest.raises(FrontendAIError, match="external resource"):
        parse_single_file_payload(
            json.dumps({"files": {"hero.svg": distant}}), "hero.svg")


def test_coherence_spots_a_dataset_id_compared_without_conversion(project):
    front = project / "frontend"
    front.mkdir()
    (front / "app.js").write_text(
        "const id = button.dataset.id; state.items.find((item) => item.id === id);",
        encoding="utf-8")
    from monl.frontend_ai import _frontend_behavioral_quality_errors
    errors = _frontend_behavioral_quality_errors(str(project))
    assert any("unnormalized DOM identifier" in error for error in errors)

    (front / "app.js").write_text(
        "const id = Number(button.dataset.id); state.items.find((item) => item.id === id);",
        encoding="utf-8")
    assert _frontend_behavioral_quality_errors(str(project)) == []


def test_design_refuses_reused_generated_image_and_duplicated_editorial_text(project):
    front = project / "frontend"
    front.mkdir()
    (front / "index.html").write_text(
        '<img src="hero.svg"><img src="hero.svg">', encoding="utf-8")
    from monl.frontend_ai import (
        _editorial_content_errors,
        _generated_asset_reuse_errors,
    )
    image_errors = _generated_asset_reuse_errors(
        str(front), [{"path": "hero.svg"}])
    assert any("generated asset reused" in error for error in image_errors)

    section_body = ("Maison Serein propose une parenthèse calme, avec des gestes "
                    "précis et une écoute attentive pour chaque personne reçue.")
    (project / "frontend_contract.json").write_text(json.dumps({
        "sections": [{"title": "À propos", "body": section_body}],
    }), encoding="utf-8")
    text_errors = _editorial_content_errors(
        str(project), section_body + " " + section_body)
    assert any("editorial content repeated" in error for error in text_errors)


def test_loop_ia_fixed_puis_succeeds(project):
    calls = []

    def provider(prompt):
        calls.append(prompt)
        payload = BAD_FRONT if len(calls) == 1 else GOOD_FRONT
        return json.dumps({"files": {"index.html": payload}})

    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert ok, errors
    assert len(calls) == 2
    # the 2nd attempt carries the errors really observed
    assert "CHECK FAILED" in calls[1]
    assert "casse" in calls[1] or "/fantome" in calls[1]


def test_ai_loop_fails_after_a_single_correction(project):
    calls = []

    def provider(prompt):
        calls.append(prompt)
        return json.dumps({"files": {"index.html": BAD_FRONT}})

    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert not ok and errors
    assert len(calls) == 2, "never more than ONE automatic correction"
    # the files stay inspectable, but run will refuse (blocking smoke)
    assert (project / "frontend" / "index.html").exists()


#: Two phantom paths instead of one: strictly worse than BAD_FRONT, on the same
#: scale and without changing anything else.
PIRE_FRONT = ("<!doctype html><html><body><script>"
              "fetch('/fantome/1'); fetch('/autre-fantome');"
              "</script></body></html>")


def test_a_degrading_correction_does_not_replace_the_previous_attempt(project):
    """monl kept the LAST attempt; it keeps the BEST one.

    Measured on a real paid build: asked to fix two lines, the model rewrote the
    whole site and lost fourteen routes out of fifteen — two complete user
    journeys with them. The first attempt was nearly good. The user paid for two
    passes and left with the worse of the two.
    """
    rendered = [BAD_FRONT, PIRE_FRONT]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": {"index.html": rendered.pop(0)}})

    ok, errors = generate_and_verify(str(project), provider, say=dits.append)

    assert not ok, "both attempts fail: the verdict stays a failure"
    kept = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert kept == BAD_FRONT, (
        "the degraded attempt was kept although it is worse")
    assert any("Attempt 1 restored" in line for line in dits), dits
    # The REPORTED errors must describe the kept files: returning the discarded
    # attempt's would describe a frontend absent from disk.
    assert not any("/autre-fantome" in e for e in errors), errors
    assert any("/fantome/1" in e for e in errors), errors


def test_an_improving_correction_is_kept(project):
    """Indispensable counter-proof: a safeguard always freezing the first attempt
    would cancel automatic correction entirely, and pass for good."""
    rendered = [PIRE_FRONT, BAD_FRONT]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": {"index.html": rendered.pop(0)}})

    ok, errors = generate_and_verify(str(project), provider, say=dits.append)

    assert not ok
    kept = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert kept == BAD_FRONT, "the better of the two is the second here"
    assert not any("restaurée" in line for line in dits), dits


def test_restoration_leaves_no_file_from_the_discarded_attempt(project):
    """A mix of the two attempts would be worse than either: the restored file
    would call a script its version did not write."""
    rendered = [
        {"index.html": BAD_FRONT},
        {"index.html": PIRE_FRONT, "extra.js": "console.log('tentative 2');"},
    ]
    dits = []

    def provider(_prompt):
        return json.dumps({"files": rendered.pop(0)})

    generate_and_verify(str(project), provider, say=dits.append)

    assert (project / "frontend" / "index.html").read_text(
        encoding="utf-8") == BAD_FRONT
    assert not (project / "frontend" / "extra.js").exists(), (
        "a file from the discarded attempt survives in the kept frontend")


# ---- 'monl import': the path WITHOUT an API key (claude.ai subscription) ----
import zipfile

from monl.frontend_ai import import_and_verify, load_frontend_source

GOOD_SPLIT_HTML = ('<!doctype html><html><body><div id="l"></div>'
                   '<script src="app.js"></script></body></html>')
GOOD_SPLIT_JS = ("fetch('/item?limit=5').then(r => r.json()).then(d => {"
                 "document.getElementById('l').textContent = d.total;});")


def test_realistic_zip_import_subfolder_and_stray_file(project, tmp_path):
    """A zip 'as Claude returns it': subfolder, separate JS, file outside the
    allowlist — installed, filtered, and app.js's fetch is indeed TESTED (local
    scripts are inlined before jsdom, otherwise false positive)."""
    zpath = tmp_path / "telechargement.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("mon-app/index.html", GOOD_SPLIT_HTML)
        z.writestr("mon-app/app.js", GOOD_SPLIT_JS)
        z.writestr("mon-app/notes.py", "parasite")
    ok, errors = import_and_verify(str(project), str(zpath), say=_quiet)
    assert ok, errors
    assert (project / "frontend" / "app.js").exists()
    assert not (project / "frontend" / "notes.py").exists()


def test_import_refuses_zip_slip_and_cdn(project, tmp_path):
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as z:
        z.writestr("../evasion.html", "x")
        z.writestr("index.html", "x")
    with pytest.raises(FrontendAIError):
        load_frontend_source(str(evil))

    cdn = tmp_path / "cdn.zip"
    with zipfile.ZipFile(cdn, "w") as z:
        z.writestr("index.html", '<html><body>'
                   '<script src="https://cdn.exemple.com/lib.js"></script>'
                   '</body></html>')
    ok, errors = import_and_verify(str(project), str(cdn), say=_quiet)
    assert not ok
    assert any("CDN" in e for e in errors), errors


def test_html_only_import_and_backup_of_the_previous(project, tmp_path):
    single = tmp_path / "telechargement.html"
    single.write_text(GOOD_FRONT, encoding="utf-8")
    ok, _e = import_and_verify(str(project), str(single), say=_quiet)
    assert ok
    # Re-importing on top: the old frontend is kept, never lost.
    ok, _e = import_and_verify(str(project), str(single), say=_quiet)
    assert ok
    assert (project / "frontend.precedent" / "index.html").exists()


# ---- Claude Code: working directly in the target folder ----
import stat

from monl.frontend_ai import generate_with_claude_code
from monl.frontend_contract import PROJECT_CLAUDE_MD_MARKER


def _fake_agent(tmp_path, body):
    """A fake 'claude' executable — orchestration runs for real, only the agent
    is simulated (same approach as the API provider)."""
    script = tmp_path / "fake_claude"
    script.write_text("#!/usr/bin/env python3\nimport os, sys\n" + body,
                      encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


GOOD_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
"""

FIXER_AGENT = """os.makedirs("frontend", exist_ok=True)
if not os.path.exists(".attempt"):
    open(".attempt", "w").write("x")
    open("frontend/index.html", "w").write(
        "<html><body><script>fetch('/fantome/1'); boom();</script></body></html>")
else:
    assert "fantome" in sys.argv[2] or "boom" in sys.argv[2]
    open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
"""

EVIL_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open("app.py", "a").write("\\n# intrusion\\n")
"""


def test_project_claude_md_generated_and_never_overwritten(project):
    claude_md = project / "AGENTS.md"
    assert claude_md.exists()
    assert PROJECT_CLAUDE_MD_MARKER in claude_md.read_text(encoding="utf-8")
    # Taken over by the user (marker removed) -> untouchable.
    claude_md.write_text("# mes propres consignes", encoding="utf-8")
    compile_project(str(project / "spec.ml"), str(project))
    assert claude_md.read_text(encoding="utf-8") == "# mes propres consignes"


def test_claude_code_succeeds_and_checks(project, tmp_path):
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert ok, errors


def test_claude_code_receives_the_errors_and_corrects_itself(project, tmp_path):
    agent = _fake_agent(tmp_path, FIXER_AGENT)
    msgs = []
    ok, errors = generate_with_claude_code(str(project), command=agent, say=msgs.append)
    assert ok, errors
    assert any("Automatic correction" in m for m in msgs)


MAXTURNS_AGENT = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write('''<html><body><div id="l"></div>
<script>fetch('/item?limit=5').then(r=>r.json()).then(d=>{
document.getElementById('l').textContent=d.total;});</script></body></html>''')
sys.stderr.write("Error: Reached max turns (40)\\n")
sys.exit(1)
"""

MAXTURNS_EMPTY_AGENT = """sys.stderr.write("Error: Reached max turns (40)\\n")
sys.exit(1)
"""

CRASH_AGENT = """sys.stderr.write("Error: authentication failed\\n")
sys.exit(1)
"""


def test_turn_budget_exhausted_but_frontend_valid(project, tmp_path):
    """POINT 62: the agent can finish its work on the last turn and go over by a
    hair. The produced frontend must be checked on the evidence, not thrown away
    because the process returned a non-zero exit code."""
    agent = _fake_agent(tmp_path, MAXTURNS_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert ok, errors


def test_budget_exhausted_without_output_goes_through_correction(project, tmp_path):
    """The same overrun, but without a frontend: it is a failure — which must go
    through the correction loop, not interrupt the command."""
    agent = _fake_agent(tmp_path, MAXTURNS_EMPTY_AGENT)
    msgs = []
    ok, errors = generate_with_claude_code(str(project), command=agent, say=msgs.append)
    assert not ok
    assert any("index.html missing" in e for e in errors), errors
    assert any("Automatic correction" in m for m in msgs)


def test_a_real_agent_error_stays_an_error(project, tmp_path):
    """The relaxation only applies to the turn budget: an authentication failure
    must keep stopping dead."""
    from monl.frontend_ai import FrontendAIError
    agent = _fake_agent(tmp_path, CRASH_AGENT)
    with pytest.raises(FrontendAIError):
        generate_with_claude_code(str(project), command=agent, say=_quiet)


def test_claude_code_cannot_touch_the_backend(project, tmp_path):
    agent = _fake_agent(tmp_path, EVIL_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any("app.py" in e for e in errors), errors


# POINT 134: the SNEAKY agent does NOT touch frontend/. That is the whole
# difference with EVIL_AGENT — and it is the path that escaped the safeguard.
SNEAKY_AGENT = """open("manage.py", "a").write("\\n# porte derobee\\n")
"""


def test_an_agent_cannot_rewrite_manage_py(project, tmp_path):
    """manage.py CREATES administrator accounts — it is the boundary
    `selfRegister` holds on the API side. It was sealed in monl.json but absent
    from the artifacts whose fingerprint is compared before/after the agent's
    pass.

    The worst case is reproduced here: a VALID frontend already exists and the
    agent does not touch it. `generate_with_cli_agent` then returns a SUCCESS
    even before calling `check_coherence` — so without the fix, monl answered
    "nothing is broken" on a booby-trapped manage.py. The injected code ran at
    the first privileged account creation.
    """
    frontend = project / "frontend"
    frontend.mkdir(exist_ok=True)
    (frontend / "index.html").write_text(
        "<html><body>déjà là</body></html>", encoding="utf-8")
    before = (project / "manage.py").read_text(encoding="utf-8")

    agent = _fake_agent(tmp_path, SNEAKY_AGENT)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)

    assert not ok, "a rewritten manage.py must make the build FAIL"
    assert any("manage.py" in e for e in errors), errors
    # The file stays on disk — monl says to restore it, it does not do it for
    # you (point 73). The test NOTES it rather than suggesting a repair.
    assert (project / "manage.py").read_text(encoding="utf-8") != before


# The agent does REAL frontend work — and takes advantage of it on the way. It
# is the case that passed every check: protected fingerprints OK, consistency
# OK, smoke test OK (it does not read the Dockerfile), success announced.
SABOTEUR_DOCKER = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open("Dockerfile", "w").write(
    open("Dockerfile").read().replace('"serve:app"', '"app:app"'))
"""

SABOTEUR_SECRET = """os.makedirs("frontend", exist_ok=True)
open("frontend/index.html", "w").write("<html><body>ok</body></html>")
open(".dockerignore", "w").write("*.db\\n__pycache__\\n")
"""


def test_an_agent_cannot_put_the_container_back_to_404(project, tmp_path):
    """Undoing point 133 in the Dockerfile breaks NOTHING checkable: consistency
    passes, the smoke test does not read the Dockerfile, and the next image
    answers 404 on /site again. Only the protected fingerprint could see it — and
    it did not look at this file."""
    agent = _fake_agent(tmp_path, SABOTEUR_DOCKER)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any("Dockerfile" in e for e in errors), errors


def test_an_agent_cannot_get_the_jwt_secret_shipped(project, tmp_path):
    """The worse of the two: `.dockerignore` excludes `.jwt_secret` from the
    template's `COPY . .`. Removing it brings the token signing secret into the
    image — hence into every registry it is pushed to. No other monl check looks
    at this file."""
    agent = _fake_agent(tmp_path, SABOTEUR_SECRET)
    ok, errors = generate_with_claude_code(str(project), command=agent, say=_quiet)
    assert not ok
    assert any(".dockerignore" in e for e in errors), errors


def test_everything_executing_outside_frontend_is_protected():
    """The protected fingerprint is an invariant DURING the agent's pass, not a
    declaration of ownership: the author adapts their Dockerfile between two runs
    without trouble. That confusion is what had left executable files outside on
    the pretext that they are editable."""
    from monl.frontend_ai import PROTECTED_ARTIFACTS
    for name in ("manage.py", "serve.py", "Dockerfile", ".dockerignore"):
        assert name in PROTECTED_ARTIFACTS, name


# ───────────────────────────────────────────────────────────────────── POINT
# 69: any API key, any agent
#
# Two paths opened, two ways to test them without network or third-party
# binary: the HTTP request is intercepted (we check what monl SENDS), and the
# agent is a fake executable recording its argv (we check what monl LAUNCHES).
# Orchestration itself runs for real.
# ─────────────────────────────────────────────────────────────────────
from monl.frontend_ai import (
    CLI_AGENTS,
    OPENAI_COMPATIBLE,
    PROVIDERS,
    build_agent_argv,
    generate_with_cli_agent,
)


def test_openai_compatible_provider_shapes_the_request(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    vu = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": '{"files": {}}'}}]}

    def faux_post(url, headers=None, json=None, timeout=None):
        vu.update(url=url, headers=headers, body=json)
        return Response()

    import requests
    monkeypatch.setattr(requests, "post", faux_post)

    call = PROVIDERS["groq"](model="un-modele")
    assert call("le brief") == '{"files": {}}'
    assert vu["url"] == "https://api.groq.com/openai/v1/chat/completions"
    assert vu["headers"]["Authorization"] == "Bearer cle-de-test"
    assert vu["body"]["model"] == "un-modele"
    assert vu["body"]["messages"][0]["content"] == "le brief"


def test_yandex_uses_its_authentication_and_measures_tokens(monkeypatch):
    """Yandex speaks Chat Completions, but requires Api-Key and the Cloud folder."""
    monkeypatch.setenv("YANDEX_API_KEY", "cle-yandex")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "dossier-yandex")
    monkeypatch.delenv("MONL_AI_CHUNK_MAX_TOKENS", raising=False)
    vu = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {
                "choices": [{"message": {"content": "{\"files\": {}}"}}],
                "usage": {"prompt_tokens": 101, "completion_tokens": 23,
                          "total_tokens": 124},
            }

    def faux_post(url, headers=None, json=None, timeout=None):
        vu.update(url=url, headers=headers, body=json)
        return Response()

    import requests
    monkeypatch.setattr(requests, "post", faux_post)
    model = "gpt://dossier-yandex/yandexgpt/latest"
    call = PROVIDERS["yandex"](model=model)

    assert call("brief") == '{"files": {}}'
    assert vu["url"] == "https://ai.api.cloud.yandex.net/v1/chat/completions"
    assert vu["headers"]["Authorization"] == "Api-Key cle-yandex"
    assert vu["headers"]["OpenAI-Project"] == "dossier-yandex"
    assert vu["body"]["model"] == model
    assert vu["body"]["temperature"] == 0.3
    assert vu["body"]["max_tokens"] == 8000
    # REVERSAL, measured against the real service: Yandex REFUSES
    # reasoning_effort='none' with HTTP 400 ("Input should be 'low', 'medium'
    # or 'high'"), so this assertion described a request body the service never
    # accepted — every --provider yandex build died at the first call. Omitting
    # the field is what the preset's comment meant, and what the service
    # accepts.
    assert "reasoning_effort" not in vu["body"]
    assert vu["body"]["response_format"]["type"] == "json_schema"
    assert vu["body"]["response_format"]["json_schema"]["strict"] is True
    assert call.last_usage["input_tokens"] == 101
    assert call.last_usage["output_tokens"] == 23
    assert call.last_usage["total_tokens"] == 124


def test_yandex_frontend_is_generated_file_by_file(project, monkeypatch):
    """The sequential preset keeps the contract and checks the three files
    together after assembling them."""
    calls = []

    class Provider:
        provider_name = "yandex"
        model = "deepseek-v4-flash/latest"
        chunked_generation = True
        last_usage = None

        def __call__(self, prompt):
            calls.append(prompt)
            line = next(text for text in prompt.splitlines()
                         if text.startswith("The target file is exactly: "))
            target = line.rsplit(": ", 1)[1]
            contents = {
                "index.html": GOOD_SPLIT_HTML,
                "styles.css": "body { color: #111; }",
                "app.js": GOOD_SPLIT_JS,
            }
            self.last_usage = {"duration_seconds": 0.1,
                               "input_tokens": 100, "output_tokens": 200,
                               "total_tokens": 300}
            return json.dumps({"files": {target: contents[target]}})

    provider = Provider()
    ok, errors = generate_and_verify(str(project), provider, say=_quiet)
    assert ok, errors
    assert len(calls) == 3
    assert all("one piece at a time" in prompt for prompt in calls)
    assert (project / "frontend" / "index.html").exists()
    assert (project / "frontend" / "styles.css").exists()
    assert (project / "frontend" / "app.js").exists()


def test_yandex_names_the_missing_folder(monkeypatch):
    monkeypatch.setenv("YANDEX_API_KEY", "cle-yandex")
    monkeypatch.delenv("YANDEX_FOLDER_ID", raising=False)
    with pytest.raises(FrontendAIError) as error:
        PROVIDERS["yandex"](model="gpt://dossier/yandexgpt/latest")
    assert "YANDEX_FOLDER_ID" in str(error.value)


def test_the_api_ceiling_is_set_by_the_environment(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    monkeypatch.setenv("MONL_AI_MAX_TOKENS", "8000")
    vu = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda _url, **kw: (vu.update(kw), Response())[1])
    assert PROVIDERS["groq"](model="un-modele")("brief") == "ok"
    assert vu["json"]["max_tokens"] == 8000


def test_telemetry_keeps_neither_prompt_nor_response(project, monkeypatch):
    """The log serves the product price, not copying the client's content."""
    from monl.frontend_ai import USAGE_FILENAME

    class Provider:
        provider_name = "yandex"
        model = "modele-test"
        last_usage = None

        def __call__(self, prompt):
            assert "SmokeApp" in prompt
            self.last_usage = {"duration_seconds": 0.25, "input_tokens": 100,
                               "output_tokens": 20, "total_tokens": 120}
            return json.dumps({"files": {"index.html": GOOD_FRONT}})

    ok, errors = generate_and_verify(str(project), Provider(), say=_quiet)
    assert ok, errors
    content = (project / USAGE_FILENAME).read_text(encoding="utf-8")
    event = json.loads(content)
    assert event["provider"] == "yandex"
    assert event["operation"] == "construction"
    assert event["total_tokens"] == 120
    assert "SmokeApp" not in content
    assert GOOD_FRONT not in content


def test_each_preset_names_its_own_key_variable(monkeypatch):
    """A missing key must name THE expected variable: "missing key" without
    saying which sends the user to read the code."""
    from monl.frontend_ai import FrontendAIError
    for name, (_url, variable) in OPENAI_COMPATIBLE.items():
        if name == "ollama":
            continue                      # local server: no key required
        monkeypatch.delenv(variable, raising=False)
        with pytest.raises(FrontendAIError) as e:
            PROVIDERS[name](model="un-modele")
        assert variable in str(e.value), name


def test_no_default_model_outside_the_anthropic_path(monkeypatch):
    """The message must ask for --model, not let a request go towards a guessed
    identifier."""
    from monl.frontend_ai import FrontendAIError
    monkeypatch.setenv("GROQ_API_KEY", "cle-de-test")
    with pytest.raises(FrontendAIError) as e:
        PROVIDERS["groq"](model=None)
    assert "--model" in str(e.value)


def test_free_endpoint_through_the_environment(monkeypatch):
    monkeypatch.setenv("MONL_AI_BASE_URL", "https://exemple.interne/v1")
    monkeypatch.setenv("MONL_AI_API_KEY", "cle-maison")
    vu = {}

    class Response:
        status_code = 200
        text = ""

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    import requests
    monkeypatch.setattr(requests, "post",
                        lambda url, **kw: (vu.update(url=url), Response())[1])
    call = PROVIDERS["openai-compatible"](model="modele-maison")
    assert call("brief") == "ok"
    assert vu["url"] == "https://exemple.interne/v1/chat/completions"


def test_each_agent_has_its_own_command_line():
    """The point of the generalization: the instruction travels to the agent,
    whatever the shape of its argv."""
    for name in CLI_AGENTS:
        binary, args = build_agent_argv(name, "CONSIGNE", 120)
        assert binary == CLI_AGENTS[name]["binary"]
        assert "CONSIGNE" in args, name
    assert build_agent_argv("codex", "CONSIGNE", 120)[1][0] == "exec"


def test_free_template_for_an_unlisted_agent():
    binary, args = build_agent_argv(None, "CONSIGNE", 120,
                                     agent_command="mon-agent --auto {instruction}")
    assert (binary, args) == ("mon-agent", ["--auto", "CONSIGNE"])


def test_template_without_instruction_is_refused():
    from monl.frontend_ai import FrontendAIError
    with pytest.raises(FrontendAIError) as e:
        build_agent_argv(None, "CONSIGNE", 120, agent_command="mon-agent --auto")
    assert "{instruction}" in str(e.value)


def test_unknown_agent_is_refused_naming_the_known_ones():
    from monl.frontend_ai import FrontendAIError
    with pytest.raises(FrontendAIError) as e:
        build_agent_argv("inexistant", "CONSIGNE", 120)
    assert "claude-code" in str(e.value) and "--agent-command" in str(e.value)


def test_a_third_party_agent_builds_and_checks_for_real(project, tmp_path):
    """The full loop (run → fingerprints → consistency → smoke test) through the
    'codex' path, with a fake binary."""
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_cli_agent(str(project), command=agent,
                                         agent="codex", say=_quiet)
    assert ok, errors


def test_a_third_party_agent_cannot_touch_the_backend_either(project, tmp_path):
    """The safeguard does NOT depend on who writes: it is the whole stake of
    point 69's generalization."""
    agent = _fake_agent(tmp_path, EVIL_AGENT)
    ok, errors = generate_with_cli_agent(str(project), command=agent,
                                         agent="codex", say=_quiet)
    assert not ok
    assert any("app.py" in e for e in errors), errors


def test_the_free_template_goes_through_the_whole_loop(project, tmp_path):
    agent = _fake_agent(tmp_path, GOOD_AGENT)
    ok, errors = generate_with_cli_agent(
        str(project), agent_command=f"{agent} {{instruction}}", say=_quiet)
    assert ok, errors


# --------------------------------------------------------------------------
# POINT 93: the touch-up — fixing without rebuilding
# --------------------------------------------------------------------------

REQUEST = "les images de la section Tendances sont mal cadrées"

NOOP_AGENT = "pass  # l'agent ne touche à rien\n"

RETOUCH_AGENT = """open("frontend/index.html", "a").write(
    "<!-- object-position ajusté -->")
"""


def _project_with_frontend(project):
    front = project / "frontend"
    front.mkdir(exist_ok=True)
    (front / "index.html").write_text(GOOD_FRONT, encoding="utf-8")
    return front


def test_the_touch_up_writes_its_instruction_and_backs_up_existing(project):
    """The backup is not overzealousness: no automatic check can settle a matter
    of taste, so the only guarantee one can offer is being able to go back. It is
    a COPY — the AI must find the existing work in place to evolve it."""
    from monl.cli import cmd_retouch

    front = _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)

    consigne = (project / RETOUCH_PROMPT_FILENAME).read_text(encoding="utf-8")
    assert REQUEST in consigne
    assert (project / "frontend.precedent" / "index.html").read_text(
        encoding="utf-8") == GOOD_FRONT
    assert front.joinpath("index.html").exists(), "the existing work must stay in place"


def test_the_touch_up_refuses_a_project_without_frontend(project):
    """Touching up what does not exist makes no sense — and the message must
    point to the command that builds, not leave it to guesswork."""
    from monl.cli import cmd_retouch

    with pytest.raises(SystemExit):
        cmd_retouch(str(project), REQUEST, say=_quiet)


def test_the_touch_up_refuses_an_empty_request(project):
    from monl.cli import cmd_retouch

    _project_with_frontend(project)
    with pytest.raises(SystemExit):
        cmd_retouch(str(project), "   ", say=_quiet)


def test_the_touch_up_prompt_carries_request_files_and_contract(project):
    """The three pieces are indispensable together: the request says WHAT, the
    current files say it is an evolution and not a new page, the contract recalls
    what stays non-negotiable."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import build_generation_prompt

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)

    prompt = build_generation_prompt(str(project), False, retouch_mode=True)
    assert REQUEST in prompt
    assert "Current frontend files" in prompt
    assert "fetch('/item?limit=5')" in prompt, "the existing work must be attached"
    assert "Reminder of the original contract" in prompt


def test_the_touch_up_asks_for_the_narrowest_interpretation(project):
    """Without this instruction, "the images are badly cropped" invites redoing
    the whole layout — and a too broad touch-up can no longer be told apart from a
    rebuild, that is from what the command avoids."""
    from monl.cli import cmd_retouch

    _project_with_frontend(project)
    path = cmd_retouch(str(project), REQUEST, say=_quiet)
    consigne = pathlib.Path(path).read_text(encoding="utf-8")
    assert "NARROWEST" in consigne
    assert "do not redo the overall layout" in consigne.lower()
    # And the content safeguard: what comes from the spec is not fixed by a
    # display trick (the FAQ case, point 94).
    assert "guessed structure" in consigne


def test_the_agent_gets_a_touch_up_instruction_not_a_build_one(project, tmp_path):
    """The agent path must change template: "build the requested frontend"
    invited starting from scratch."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)
    spy = tmp_path / "argv.json"
    agent = _fake_agent(tmp_path, RETOUCH_AGENT + f"""
import json
json.dump(sys.argv, open({str(spy)!r}, "w"))
""")
    generate_with_cli_agent(str(project), command=agent, say=_quiet,
                            retouch_mode=True)

    argv = json.loads(spy.read_text(encoding="utf-8"))
    instruction = " ".join(argv)
    assert RETOUCH_PROMPT_FILENAME in instruction
    assert "defect OBSERVED" in instruction
    assert "build the requested frontend" not in instruction


def test_a_touch_up_changing_nothing_is_a_failure(project, tmp_path):
    """POINT 73 pushed one notch further. On a BUILD, "the agent wrote nothing"
    is a warning: a valid frontend already existed. On a TOUCH-UP, it is the
    request unhandled — the human reported a defect they SEE, and answering
    "everything is fine" would be the opposite of an honest report."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)
    agent = _fake_agent(tmp_path, NOOP_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouch_mode=True)

    assert not ok
    assert any("touch-up not applied" in e for e in errors), errors


def test_the_touch_up_cannot_touch_the_backend_either(project, tmp_path):
    """The safeguard does not depend on the command using it — that is the whole
    stake of having ONE path to the AI and not two."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)
    agent = _fake_agent(tmp_path, EVIL_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouch_mode=True)

    assert not ok
    assert any("app.py" in e for e in errors), errors


def test_a_successful_touch_up_evolves_existing_and_rechecks(project, tmp_path):
    """The end to end: the agent modifies, monl re-checks (consistency + smoke
    test), and what the agent wrote is STILL there after the check."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)
    agent = _fake_agent(tmp_path, RETOUCH_AGENT)

    ok, errors = generate_with_cli_agent(str(project), command=agent, say=_quiet,
                                         retouch_mode=True)

    assert ok, errors
    rendered = (project / "frontend" / "index.html").read_text(encoding="utf-8")
    assert "object-position ajusté" in rendered
    assert "fetch('/item?limit=5')" in rendered, "the existing work must not be rewritten"


DECLINING_AGENT = """print("Je ne peux pas retirer cette rubrique depuis frontend/ :")
print("elle vient du bloc 'landing' de la spec, et FRONTEND_PROMPT.md exige")
print("qu'elle soit lisible au fil de l'accueil. Cela se règle dans la spec.")
"""


def test_when_the_agent_declines_its_reason_is_shown(project, tmp_path):
    """POINT 97: the failure message was an ASSUMPTION, and it was false.
    "Rephrase by naming the screen and the element" was displayed on a request
    that named them — because the real reason ("this section comes from the
    spec, not the frontend") had been thrown away with the agent's output.

    The touch-up instruction explicitly asks the AI to REPORT this case rather
    than work around it; hearing it and not repeating it was the costliest
    possible defect — it sent the user rephrasing an already clear request."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), "retire la rubrique À propos de l'accueil", say=_quiet)
    agent = _fake_agent(tmp_path, DECLINING_AGENT)
    msgs = []

    ok, _errors = generate_with_cli_agent(str(project), command=agent,
                                          say=msgs.append, retouch_mode=True)

    output = "\n".join(msgs)
    assert not ok
    assert "elle vient du bloc 'landing' de la spec" in output, output
    # And the old assumption must NO LONGER be displayed when the agent spoke.
    assert "Rephrasing the request" not in output, output
    # …replaced by the gesture that really fits.
    assert "monl update" in output, output


def test_without_explanation_the_rephrasing_advice_stays(project, tmp_path):
    """The witness: a mute agent says nothing useful, and there the rephrasing
    advice keeps its full meaning. Removing it for good would have left the user
    without a lead."""
    from monl.cli import cmd_retouch
    from monl.frontend_ai import generate_with_cli_agent

    _project_with_frontend(project)
    cmd_retouch(str(project), REQUEST, say=_quiet)
    agent = _fake_agent(tmp_path, NOOP_AGENT)
    msgs = []

    generate_with_cli_agent(str(project), command=agent, say=msgs.append,
                            retouch_mode=True)

    assert "Rephrasing the request" in "\n".join(msgs)


# ---- The fenced block safety net (point 148) ----

def test_a_file_returned_in_a_fenced_block_is_accepted():
    """The fallback that cost a quarter of a real build.

    A sequential stage must wrap a whole JavaScript file in a JSON string: every
    line break escaped, every quote doubled. A cheap model breaks on it, and the
    retry loop then pushes it towards what PARSES — measured, `app.js` ended at
    834 output tokens.
    """
    content = 'const a = "guillemet";\nfetch("/item");\n'
    brut = "Voici le fichier :\n```javascript\n" + content + "```\n"

    rendered = parse_single_file_payload(brut, "app.js")

    assert rendered == {"app.js": content}


def test_json_stays_the_normal_path():
    """Counter-proof: the safety net must not replace the contract."""
    brut = json.dumps({"files": {"app.js": "const a = 1;"}})

    assert parse_single_file_payload(brut, "app.js") == {"app.js": "const a = 1;"}


def test_a_block_containing_the_json_is_not_taken_for_a_file():
    """Otherwise we would put `{"files": …}` into app.js: it parses, and it does
    not work — the worst of both worlds."""
    brut = "```json\n{\"files\": {\"app.js\": \"const a = 1;\"}}\n```"

    assert parse_single_file_payload(brut, "app.js") == {"app.js": "const a = 1;"}


def test_the_safety_net_goes_through_the_same_safeguards():
    """No path bypasses validation: it is the repository's rule."""
    with pytest.raises(FrontendAIError, match="extension refused"):
        parse_single_file_payload("```\nrm -rf /\n```", "script.sh")
    # An empty block is not a file: we keep the original JSON error.
    with pytest.raises(FrontendAIError, match="unreadable"):
        parse_single_file_payload("pas de json, pas de bloc", "app.js")


def test_the_largest_block_wins_over_a_comment_excerpt():
    """A talkative model illustrates its answer before returning the file."""
    file = "fetch('/item');\n" * 20
    brut = ("Je vais utiliser :\n```js\nfetch()\n```\n"
            "Voici le fichier complet :\n```js\n" + file + "```")

    assert parse_single_file_payload(brut, "app.js") == {"app.js": file}


def test_a_truncated_response_never_goes_through_the_safety_net():
    """The risk the safety net itself introduced.

    A model illustrating with a small CLOSED excerpt then cut off in the middle of
    the real file leaves an open block. Without a guard, the largest closed block
    would be the excerpt — and monl would write three lines into app.js believing
    it held the file. Worse: the ladder enlarging the output ceiling, made exactly
    for this case, would never be reached again.
    """
    truncated = ("Je commence par :\n```js\nfetch('/item');\n```\n"
                "Voici le fichier complet :\n```js\n" + "const x = 1;\n" * 40)

    with pytest.raises(FrontendAIError, match="unreadable"):
        parse_single_file_payload(truncated, "app.js")


def test_the_retry_ladder_really_reaches_its_bound():
    """A bound no path reaches constrains nothing.

    The ladder went 8,000 → 12,000 → 18,000 while the code announced a maximum
    ceiling of 32,000 — including in the error message, which would therefore have
    lied had it fired. This test binds the THREE numbers: changing one without the
    others makes it fail.
    """
    from monl.frontend_ai import (
        CHUNK_MAX_RETRIES,
        CHUNK_RETRY_MAX_OUTPUT_TOKENS,
        DEFAULT_CHUNK_MAX_OUTPUT_TOKENS,
        _raise_chunk_output_limit,
    )

    class Stage:
        max_output_tokens = DEFAULT_CHUNK_MAX_OUTPUT_TOKENS

    stage = Stage()
    steps = [stage.max_output_tokens]
    for _ in range(CHUNK_MAX_RETRIES):
        assert _raise_chunk_output_limit(stage), "the ladder stops too early"
        steps.append(stage.max_output_tokens)

    assert steps[-1] == CHUNK_RETRY_MAX_OUTPUT_TOKENS, (
        f"the last retry caps at {steps[-1]} while the declared bound "
        f"is {CHUNK_RETRY_MAX_OUTPUT_TOKENS}: it constrains nothing")
    assert steps == sorted(set(steps)), steps
