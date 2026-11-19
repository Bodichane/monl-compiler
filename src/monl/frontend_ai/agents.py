"""Command line agents, and the two fingerprint safeguards."""

import hashlib
import os
import shlex
import shutil
import subprocess
import time
import uuid

from ..design_system import activate_asset_manifest
from ..frontend_contract import PROMPT_FILENAME
from . import fondations, fournisseurs, orchestration, redaction

# ─────────────────────────────────────────────────────────────────────
# CLAUDE CODE — the work done DIRECTLY in the target folder (point 43 of the
# journal). Claude Code authenticates through the subscription ('claude
# login'), not through an API key — it is the agentic path of the keyless flow:
# instead of copy/paste (point 42), the agent reads the brief on the spot,
# writes into frontend/, and monl re-checks behind it.
#
# Two uses:
#   - interactive: 'cd MyProject && claude' — the AGENTS.md generated in the
#     project folder (see write_project_claude_md) frames the session
#     (role, forbidden files, verification command);
#   - headless: 'monl frontend --provider claude-code' invokes
#     'claude -p' with restricted permissions, then the SAME
#     re-check and the SAME single correction as the API path.
#
# A safeguard SPECIFIC to this path: unlike the API (which returns text that
# monl writes itself), Claude Code writes directly to disk. The protected
# artifacts (spec, backend, contract, state) are therefore fingerprinted BEFORE
# the run and re-checked AFTER — any modification is a blocking error, even if
# the returned frontend is correct.
# ─────────────────────────────────────────────────────────────────────

# POINT 134: THIS LIST IS AN INVARIANT *DURING* THE AGENT'S PASS, NOT A
# DECLARATION OF OWNERSHIP. The fingerprint is taken just before launching the
# agent and compared just after: the author therefore stays perfectly free to
# adapt their Dockerfile between two runs. It is that confusion that had left
# EXECUTABLE files out on the pretext that they are editable.
#
# `manage.py` is the serious hole (Codex review, checked line by line): it
# CREATES the administrator accounts — it is the boundary `selfRegister` holds
# on the API side. It was sealed in monl.json but absent from here, and the
# consistency check that would have seen it is not even reached when the agent
# does not touch frontend/: `generate_with_cli_agent` returns a SUCCESS before
# it. An agent rewriting manage.py without changing anything else was therefore
# seen by nobody, and the injected code ran at the first creation of a
# privileged account.
#
# `Dockerfile` and `.dockerignore` follow the same reasoning: they describe
# what runs at deployment, including `RUN`s.
#
# `serve.py` (point 133) was not there because it only existed after 'monl
# run'. Emitted at compile time, it is there when the AI passes, and it is IT
# that decides which folders are served.
#
# The list stays an ENUMERATION, and that is its weakness: every new artifact
# must be added by hand, and three were added after the fact. Reversing it —
# "nothing outside frontend/ moves" — is the right form, and requires walking
# the whole project; to be done, not improvised here.
PROTECTED_ARTEFACTS = ("spec.ml", "app.py", "schema.sql", "sandbox_ai.py",
                       "manage.py", "serve.py", "Dockerfile", ".dockerignore",
                       "frontend_contract.json", "docs/FRONTEND_PROMPT.md",
                       "docs/DESIGN_SYSTEM.md", "docs/DESIGN_SPEC.md",
                       "docs/ASSET_MANIFEST.json", "monl.json", ".jwt_secret")

# POINT 62: the agent's turn budget. 40 was a number set before the brief
# carried the visual intent (point 53), the editorial sections (points 55 and
# 61) and the archetype expectations (point 60): a real frontend is built file
# by file, each costing a turn, and the budget ran out BEFORE index.html
# existed. Raised to 120, and made configurable from the command line — a
# three-section site does not cost what a catalog costs.
DEFAULT_MAX_TURNS = 120

CLAUDE_CODE_INSTRUCTION = (
    "Read {brief} and build the requested frontend, writing ONLY in the "
    "frontend/ folder (entry point frontend/index.html, self-contained: "
    "no CDN). Do NOT modify any other project file — neither the .ml "
    "spec, nor app.py, nor the contract. The folder's AGENTS.md gives "
    "the context."
)

# POINT 93: a touch-up is not a build. The generic instruction ("build the
# requested frontend") invited starting from scratch, which is exactly what we
# want to avoid — the site is 95% good, and a rebuild is a draw in which one
# can lose what one liked.
RETOUCHE_INSTRUCTION = (
    "Read {brief}: it describes a defect OBSERVED on the running site. Fix "
    "that defect in the EXISTING frontend (frontend/ folder), and only that "
    "one — do not rewrite what already works, do not redo the overall "
    "layout. Do NOT modify any other project file: neither the .ml spec, nor "
    "app.py, nor the contract. The folder's AGENTS.md gives the context."
)

# ─────────────────────────────────────────────────────────────────────
# POINT 69 (continued): "and also codex and others". The agentic path depended
# on Claude Code only through its command line — the fingerprint safeguard, the
# re-check and the single correction are shared by any agent that writes to
# disk. The table below is therefore only the variable part: which binary,
# which arguments.
#
# HONESTY ABOUT VERIFICATION: only 'claude' is proven against the real binary
# (tests with a fake agent + real use). The 'codex' and 'gemini' lines follow
# the non-interactive invocation these tools publish, but NEITHER was installed
# on the development machine: they are given as presets, not as guarantees.
# That is precisely why '--agent-command' exists — a free template lets you
# wire any agent (or fix a preset that has become wrong) without waiting for a
# monl release.
# ─────────────────────────────────────────────────────────────────────
CLI_AGENTS = {
    "claude-code": {
        "binary": "claude",
        "args": lambda instruction, max_turns: [
            "-p", instruction, "--permission-mode", "acceptEdits",
            "--max-turns", str(max_turns)],
        "auth": "Claude Code: 'claude login' (subscription, no key)",
    },
    "codex": {
        "binary": "codex",
        "args": lambda instruction, max_turns: [
            "exec", "--sandbox", "workspace-write", "--skip-git-repo-check",
            instruction],
        "auth": "Codex CLI: 'codex login' (ChatGPT subscription) or OPENAI_API_KEY",
    },
    "gemini": {
        "binary": "gemini",
        "args": lambda instruction, max_turns: ["--yolo", "-p", instruction],
        "auth": "Gemini CLI: 'gemini' (Google account) or GEMINI_API_KEY",
    },
}

def build_agent_argv(agent, instruction, max_turns, agent_command=None):
    """Returns an agent's complete command line.

    'agent_command' is a free template where {instruction} is substituted —
    for example 'my-agent --auto {instruction}'. It wins over the table, which
    also allows fixing a preset on the spot."""
    if agent_command:
        parts = shlex.split(agent_command)
        if not parts:
            raise fondations.FrontendAIError("--agent-command is empty.")
        if not any("{instruction}" in p for p in parts):
            raise fondations.FrontendAIError(
                "--agent-command must contain {instruction} — without it, "
                "the agent would start without knowing what to do.")
        argv = [p.replace("{instruction}", instruction) for p in parts]
        return argv[0], argv[1:]
    if agent not in CLI_AGENTS:
        raise fondations.FrontendAIError(
            f"unknown agent: {agent} — known: {', '.join(sorted(CLI_AGENTS))} "
            "(or --agent-command for any other).")
    entry = CLI_AGENTS[agent]
    return entry["binary"], entry["args"](instruction, max_turns)

def _fingerprint_protected(project_dir):
    prints = {}
    for name in PROTECTED_ARTEFACTS:
        path = os.path.join(project_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                prints[name] = hashlib.sha256(fh.read()).hexdigest()
    return prints

def _fingerprint_frontend(project_dir):
    """Fingerprint of ALL of frontend/'s content (POINT 73).

    The fingerprint safeguard only watched the PROTECTED artifacts — what an
    agent must not touch. Nobody measured what it was supposed to produce:
    `frontend/index.html` already existed, consistency passed, the smoke test
    too, and monl announced "Frontend built" while the agent had not written
    a line. A check that cannot tell "built" from "left intact" checks
    nothing."""
    prints = {}
    racine = os.path.join(project_dir, "frontend")
    for dossier, _sous, fichiers in os.walk(racine):
        for nom in fichiers:
            chemin = os.path.join(dossier, nom)
            with open(chemin, "rb") as fh:
                prints[os.path.relpath(chemin, racine)] = hashlib.sha256(fh.read()).hexdigest()
    return prints

def run_cli_agent(project_dir, instruction, max_turns=DEFAULT_MAX_TURNS,
                  command=None, agent="claude-code", agent_command=None):
    """Invokes the agent in the project folder. 'command' can be injected for
    tests (fake executable) — the same approach as the API path's fake
    provider: the orchestration really runs, only the agent is simulated.

    POINT 62: running out of the turn budget is NOT an execution error. The
    agent may have written a complete frontend at turn 39 and gone over at
    the 40th; treating it as a hard failure threw away work the verification
    might have accepted, and deprived the loop of its correction pass.
    Returned as a warning, what follows decides on the evidence."""
    wanted, args = build_agent_argv(agent, instruction, max_turns, agent_command)
    binary = command or shutil.which(wanted)
    if not binary:
        auth = CLI_AGENTS.get(agent, {}).get("auth", "")
        raise fondations.FrontendAIError(
            f"the executable '{wanted}' was not found — install it, then "
            "authenticate" + (f" ({auth})" if auth else "")
            + ". Without a command-line agent, two paths remain: "
              "'monl frontend --provider <api>' with a key, or 'monl import' "
              "after a copy/paste in any chat.")
    proc = subprocess.run(
        [binary] + args,
        cwd=project_dir, capture_output=True, text=True, timeout=1800)
    sortie = (proc.stderr or proc.stdout) or ""
    if proc.returncode != 0:
        if "max turns" in sortie.lower():
            return sortie          # budget exhausted: verification will decide
        raise fondations.FrontendAIError(f"agent '{agent}' exited with an error: "
                              + sortie[-400:])
    return proc.stdout

def run_claude_code(project_dir, instruction, max_turns=DEFAULT_MAX_TURNS,
                    command=None):
    """Alias kept for compatibility.

    Use ``run_cli_agent(..., agent="claude-code")`` in new code. See
    ``docs/DEPRECATIONS.md`` for the removal policy."""
    return run_cli_agent(project_dir, instruction, max_turns=max_turns,
                         command=command, agent="claude-code")

def generate_with_cli_agent(project_dir, update_mode=False, say=print,
                            command=None, max_turns=DEFAULT_MAX_TURNS,
                            agent="claude-code", agent_command=None,
                            retouche_mode=False, generate_images=False,
                            image_provider=None):
    """The point 4 loop, command line agent version: run the agent in the target
    folder → check the protected artifacts → re-check (consistency + smoke
    test) → at most one correction. Returns (ok, errors).

    POINT 69: the body is strictly the one written for Claude Code. A
    third-party agent loosens NO safeguard — that is the point of the
    generalization: what protects the project does not depend on who writes."""
    nom = agent_command.split()[0] if agent_command else agent
    project_dir = os.path.abspath(project_dir)
    run_id = uuid.uuid4().hex
    operation = orchestration._nom_de_loperation(update_mode, retouche_mode)
    orchestration._exiger_fournisseur_dimages(generate_images, image_provider)
    image_failures = orchestration._generer_les_images(
        project_dir, generate_images, image_provider, operation, run_id, say)
    brief, gabarit = _brief_et_gabarit(project_dir, update_mode, retouche_mode)
    instruction = gabarit.format(brief=brief)

    last_errors = []
    for attempt in (1, 2):
        if attempt == 2:
            say(f" -> Automatic correction: errors sent back to {nom} (once only)…")
            instruction = (gabarit.format(brief=brief)
                           + " Your previous attempt failed the monl check; "
                             "fix the frontend accordingly: "
                           + " ; ".join(last_errors))
        say(f" -> {nom} is working in {project_dir} (attempt {attempt}/2)…")
        before = _fingerprint_protected(project_dir)
        front_avant = _fingerprint_frontend(project_dir)
        # POINT 97: the agent's response is KEPT. It used to be thrown away,
        # and it is precisely what must be read when nothing moved: an agent
        # that declines explains why — the touch-up instruction even asks it to
        # — and monl displayed a false assumption instead ("rephrase by naming
        # the screen"), on a request that named them.
        reponse_agent = _executer_lagent(
            project_dir, instruction, max_turns, command, agent, agent_command,
            operation, attempt, run_id)

        # Safeguard: nothing other than frontend/ must have moved.
        touched = _artefacts_touches(before, _fingerprint_protected(project_dir))
        if touched:
            say(f" ❌ {nom} modified protected artifacts: "
                + ", ".join(touched))
            say("    Restore them from your version control, then run again — "
                "the frontend is the ONLY allowed scope.")
            return False, [f"protected artifact modified: {n}" for n in touched]

        if not os.path.exists(os.path.join(project_dir, "frontend", "index.html")):
            last_errors = ["frontend/index.html missing after the run — the "
                           "entry point required by the contract was not produced"]
            say(f" ❌ {last_errors[0]}")
            continue

        # POINT 73: the agent wrote nothing. Otherwise a pre-existing valid
        # frontend passes ALL the following checks — index.html is there,
        # consistency holds, the smoke test passes — and monl announces a build
        # that did not happen. We say so, rather than congratulating the agent
        # on its predecessor's work.
        if _fingerprint_frontend(project_dir) == front_avant:
            return _rien_na_change(nom, retouche_mode, reponse_agent, say)

        # The transition is performed by the orchestrator, after the agent's
        # scope check: modifying the manifest therefore cannot serve to hide a
        # write outside frontend/.
        activate_asset_manifest(project_dir)
        say(" -> Automatic recheck (consistency + smoke test)…")
        ok, errors, warnings = orchestration._reverifier(project_dir, say)
        # Same rule as in the API path: check_coherence() is the single
        # collection of completeness errors for this verification.
        for w in warnings:
            say(f" ⚠️  {w}")
        if image_failures:
            for error in errors:
                say(f" ❌ {error}")
            say(" ❌ Delivery refused: the manifest remains the authority for the "
                "planned images; run again once the provider is available.")
            return False, errors
        if ok:
            say(f" ✅ Frontend built by {nom} and verified: 'monl run' is ready.")
            return True, []
        last_errors = errors
        for e in errors:
            say(f" ❌ {e}")
    say(" ❌ Failed after correction — the files stay in frontend/ for "
        "inspection; 'monl run' will refuse to start while the smoke test fails.")
    return False, last_errors


def _brief_et_gabarit(project_dir, update_mode, retouche_mode):
    """The brief to read and the instruction template; refuses a missing brief."""
    brief = redaction.brief_evolution(update_mode, retouche_mode) or PROMPT_FILENAME
    if not os.path.exists(os.path.join(project_dir, brief)):
        origine = ("'monl retouche' did not write its instruction" if retouche_mode
                   else "run 'monl update' first" if update_mode
                   else "run 'monl compile' first")
        raise fondations.FrontendAIError(f"{brief} missing from the project — {origine}.")
    return brief, RETOUCHE_INSTRUCTION if retouche_mode else CLAUDE_CODE_INSTRUCTION


def _executer_lagent(project_dir, instruction, max_turns, command, agent,
                     agent_command, operation, attempt, run_id):
    """Runs the agent once, records its duration, returns its answer."""
    started = time.monotonic()
    reponse_agent = run_cli_agent(
        project_dir, instruction, max_turns=max_turns,
        command=command, agent=agent, agent_command=agent_command)
    modele = agent if agent in CLI_AGENTS else "custom"
    agent_usage = type("AgentUsage", (), {"provider_name": "agent", "model": modele})()
    fournisseurs._record_provider_usage(
        project_dir, agent_usage, operation=operation,
        attempt=attempt, run_id=run_id,
        usage={"duration_seconds": round(time.monotonic() - started, 3),
               "input_tokens": None, "output_tokens": None, "total_tokens": None})
    return reponse_agent


def _artefacts_touches(before, after):
    """Protected artifacts added, removed or changed by the agent."""
    return sorted(set(before) ^ set(after)
                  | {n for n in before if n in after and before[n] != after[n]})


def _rien_na_change(nom, retouche_mode, reponse_agent, say):
    """The agent wrote nothing in frontend/: a failure on a touch-up only."""
    # POINT 93: on a TOUCH-UP, changing nothing is not a neutral state
    # — it is the request left unhandled. The human reported a defect
    # they SEE; answering "all is well" would be the opposite of an
    # honest report, and point 73 already says we do not congratulate
    # an agent on its predecessor's work.
    if retouche_mode:
        say(f" ❌ {nom} modified NO file in frontend/ — the "
            "requested touch-up was not made.")
        _expliquer_le_refus(reponse_agent, say)
        return False, ["no frontend change: touch-up not applied"]
    say(f" ⚠️  {nom} modified NO file in frontend/.")
    say("    A valid frontend already existed: the agent judged that it")
    say("    met the contract and rewrote nothing. Nothing is broken,")
    say("    but nothing was built either.")
    say("    To force a rewrite, empty frontend/ first ")
    say("    (back it up), or use 'monl frontend --update' to")
    say("    ask for an EVOLUTION of what exists.")
    return True, []


def _expliquer_le_refus(reponse_agent, say):
    """Shows the agent's own reason, or how to rephrase when it gave none."""
    explication = (reponse_agent or "").strip()
    if explication:
        # THE point: guessing in the agent's place is what made the
        # message wrong. It has a reason, and here it is.
        say("    What the agent answers:")
        for ligne in explication.splitlines()[-12:]:
            if ligne.strip():
                say(f"      {ligne.rstrip()}")
        say("    If the request concerns CONTENT (a section to "
            "remove, a text to structure),")
        say("    it is settled in the spec, then 'monl update' — "
            "not by a display touch-up.")
    else:
        say("    Rephrasing the request by naming the screen and the element "
            "(\"the images in the Trends section are badly framed\")")
        say("    gives the AI something to locate it.")


def generate_with_claude_code(project_dir, update_mode=False, say=print,
                              command=None, max_turns=DEFAULT_MAX_TURNS):
    """Original name (point 43), kept: the Claude Code path is a special case of
    generate_with_cli_agent."""
    return generate_with_cli_agent(project_dir, update_mode=update_mode, say=say,
                                   command=command, max_turns=max_turns,
                                   agent="claude-code")
