"""`monl run`: mount the site on /site of the server that already hosts the
API."""

import os
import subprocess
import sys

from ..serving import rendre_wrapper
from . import coherence, location


def _eprouver_avant_lancement(project_dir):
    """The smoke test that precedes `monl run`; exits with code 1 if it fails.
    Extracted from `cmd_run` (complexity ceiling); outputs unchanged."""
    from ..smoke_test import run_smoke_test
    print(" -> Behavioral smoke test (temporary server, fresh database)…")
    smoke_ok, smoke_errors, smoke_warnings = run_smoke_test(project_dir)
    for w in smoke_warnings:
        print(f" ⚠️  {w}")
    if not smoke_ok:
        for e in smoke_errors:
            print(f" ❌ {e}")
        print(" ❌ Smoke test failed — the application will not be started "
              "(bypass knowingly with --skip-smoke).")
        sys.exit(1)
    print(" ✅ Smoke test passed: the API responds according to the contract"
          + (" and the frontend runs without errors." if os.path.isdir(
              os.path.join(os.path.abspath(project_dir), "frontend")) else "."))


def cmd_run(project_dir, check_only=False, port=8000, skip_smoke=False):
    ok, errors, warnings = coherence.check_coherence(project_dir)
    for w in warnings:
        print(f" ⚠️  {w}")
    if not ok:
        for e in errors:
            print(f" ❌ {e}")
        sys.exit(1)
    print(" ✅ Static consistency verified (spec ↔ backend ↔ contract ↔ frontend).")

    # Point 1 of the pivot: static consistency does not guarantee that it
    # WORKS. A behavioral smoke test on an ephemeral server (fresh database,
    # real data untouched): the contract's routes exercised over real HTTP, the
    # frontend run in jsdom if Node is available.
    if not skip_smoke:
        _eprouver_avant_lancement(project_dir)
    if check_only:
        return

    project_dir = os.path.abspath(project_dir)
    has_frontend = os.path.isdir(os.path.join(project_dir, "frontend"))
    assets_dir = location._assets_dir_du_projet(project_dir)
    # POINT 133: ALWAYS `serve:app`, with or without a frontend. The wrapper
    # can now start without one — and running `app:app` here while the Docker
    # image runs `serve:app` would make two behaviors for one project, only one
    # of which would be exercised.
    #
    # POINT 134: but it is NO LONGER rewritten on every launch. It used to be,
    # and since it was sealed this rewrite turned against the project: should a
    # later monl version change the wrapper's rendering, 'monl run' wrote a
    # text `monl.json` does not recognize — the NEXT launch refused to start,
    # wrongly blaming a "manual modification". A command that invalidates the
    # state it has just checked.
    #
    # It is therefore written only if it is MISSING, or if the state does not
    # seal it — that is, for a project compiled by an earlier monl, which has
    # nothing to contradict. A sealed wrapper has just been checked byte for
    # byte by the consistency check: rewriting it would bring nothing.
    # Refreshing it stays the job of 'monl update', which recompiles AND
    # re-records the fingerprint.
    wrapper = os.path.join(project_dir, "serve.py")
    etat = location._load_state(project_dir) or {}
    scelle = "serve.py" in (etat.get("backend_sha256") or {})
    if not os.path.exists(wrapper) or not scelle:
        with open(wrapper, "w", encoding="utf-8") as fh:
            fh.write(rendre_wrapper(assets_dir))
    module = "serve:app"
    if has_frontend:
        print(f" -> Frontend mounted at http://127.0.0.1:{port}/site")
        if assets_dir and os.path.isdir(os.path.join(project_dir, assets_dir)):
            print(f" -> Assets ({assets_dir}/) mounted at "
                  f"http://127.0.0.1:{port}/site/{assets_dir}/")
    else:
        print(" -> No frontend: the API is available; /site will return 404 "
              "(build the interface with 'monl frontend').")
    print(f" -> Starting: uvicorn {module} (port {port})")
    subprocess.run([sys.executable, "-m", "uvicorn", module,
                    "--host", "127.0.0.1", "--port", str(port)], cwd=project_dir)
