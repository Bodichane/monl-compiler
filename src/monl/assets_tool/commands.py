"""The two verbs: `add` and `list`.

The tool deletes nothing, writes no credit, does not recompile — an orphan
is REPORTED, `monl update` stays the explicit action."""

import os
import shutil

from ..ast_validator import DEFAULT_ASSETS_DIR, resolve_asset
from .editing import _ask_prop_assets, _replace_entry, _write_pair
from .foundations import NAMES_OF_CREDITS, AssetsToolError, _sha256
from .resolution import _name_of_file, _resolve_seed, paths_declares
from .specio import _charger, _revalidate


# The next two functions are extracted from `ajouter_asset` (complexity
# ceiling): same checks, same message, same rollback.
def _state_destination(project_dir, folder, file, source, force):
    """(destination, in place, existed, identical) — refuses to overwrite
    DIFFERENT contents without --force."""
    destination = os.path.join(project_dir, folder, file)
    on_place = os.path.abspath(destination) == os.path.abspath(source)
    existed = os.path.exists(destination)
    identical = existed and _sha256(destination) == _sha256(source)
    if existed and not identical and not on_place and not force:
        raise AssetsToolError(
            f"'{folder}/{file}' already exists with DIFFERENT contents. "
            f"Run again with --force to overwrite it, or choose --as <another-name>.")
    return destination, on_place, existed, identical


def _cancel_copie(backup, destination, existed, on_place):
    """Puts the disk back as it was: the overwritten file is restored, a newly
    copied one is removed. Once moved back, the backup no longer exists, so
    the caller's `finally` has nothing left to delete."""
    if backup and os.path.exists(backup):
        shutil.move(backup, destination)
    elif not existed and not on_place and os.path.exists(destination):
        os.remove(destination)


def _flags_of_report(existed, identical, on_place, previous, valeur):
    """The report's three derived flags, in their display order."""
    return {
        "ecrase": bool(existed and not identical and not on_place),
        "deja_en_place": on_place or identical,
        "remplace": previous if previous and previous != valeur else None,
    }


def add_asset(spec_path, project_dir, source, pour=None, target=None,
                  entity=None, field=None, name=None, force=False):
    """Copies a file into the assets folder and DECLARES it in the spec.

    `pour` targets a seed row by one of its values; `cible` is 'logo' or
    'favicon'. Returns a report (dict) — display belongs to the CLI."""
    if bool(pour) == bool(target):
        raise AssetsToolError(
            "Specify a destination: --for \"<value>\" for a seed row, "
            "or --logo / --favicon.")
    if not os.path.isfile(source):
        raise AssetsToolError(f"'{source}' does not exist or is not a file.")

    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    folder = (normalized.get("assets") or {}).get("dir") or DEFAULT_ASSETS_DIR
    file = _name_of_file(source, name, pour, target)

    with open(spec_path, encoding="utf-8") as fh:
        lines = fh.readlines()

    if target:
        # The logo is declared by its name ALONE: it is the frontend contract
        # that prefixes it with the folder (_assets_contract). Writing
        # 'assets/logo.svg' here would give '/site/assets/assets/logo.svg' to
        # the browser.
        valeur = file
        nouvelles, i_line, previous = _ask_prop_assets(lines, target, valeur, folder)
        ou, entity_name, field_name = f"assets.{target}", None, None
    else:
        entity_name, field_name, range_ = _resolve_seed(normalized, lines, pour, entity, field)
        # A seed value is the URL the browser will request: it therefore
        # carries the folder.
        valeur = f"{folder}/{file}"
        nouvelles, previous = _replace_entry(
            lines, range_, lambda text: _write_pair(text, field_name, valeur))
        i_line = range_[0]
        ou = f"{entity_name}.{field_name}"

    destination, on_place, existed, identical = _state_destination(
        project_dir, folder, file, source, force)

    backup = None
    try:
        if not on_place and not identical:
            os.makedirs(os.path.dirname(destination), exist_ok=True)
            if existed:
                # Overwriting under --force stays reversible for the duration
                # of the revalidation: without this copy, a compiler refusal
                # would leave the old file destroyed for nothing.
                backup = destination + ".monl-precedent"
                shutil.copy2(destination, backup)
            shutil.copy2(source, destination)
        text = "".join(nouvelles)
        apres = _revalidate(text, spec_path)
        # THE guarantee of layer 2, stated precisely: does what the tool has
        # just written resolve to a real file? Checked with the COMPILER's
        # resolver (resoudre_asset), not with a second implementation that
        # would end up diverging. This check targets our write and not the
        # whole spec: otherwise another missing asset would make the tool
        # unusable precisely where it serves to place one.
        if not resolve_asset(project_dir, folder, valeur):
            raise AssetsToolError(
                f"Write CANCELLED — '{valeur}' does not resolve to a file after "
                f"writing. This is exactly what layer 1 rejects during compilation, "
                f"and the tool must not produce it.")
        # Redeclaring what is already declared must write nothing: rewriting an
        # identical text would invalidate the 'monl run --check' fingerprint
        # for nothing.
        spec_changed = text != "".join(lines)
        if spec_changed:
            with open(spec_path, "w", encoding="utf-8") as fh:
                fh.write(text)
    except Exception:
        _cancel_copie(backup, destination, existed, on_place)
        raise
    finally:
        if backup and os.path.exists(backup):
            os.remove(backup)

    return {
        "fichier": f"{folder}/{file}",
        "valeur": valeur,
        "ou": ou,
        "entite": entity_name,
        "champ": field_name,
        "ligne": i_line + 1,
        **_flags_of_report(existed, identical, on_place, previous, valeur),
        "spec_changee": spec_changed,
        "orphelin": _orphan(previous, valeur, apres, project_dir),
        "avertissements": _warnings(project_dir, folder, file, spec_changed,
                                          apres, valeur, seed=target is None),
    }

def _orphan(previous, valeur, normalized, project_dir):
    """Has the old file become an orphan? REPORTED, never deleted.

    A deliberate decision: a file dropped by the human is not erased on the
    deduction of a declaration tool. It may serve elsewhere — SneakerLab's
    frontend hard-codes three photos the spec ignores."""
    if not previous or previous == valeur:
        return None
    folder, declares = paths_declares(normalized)
    if previous in declares:
        return None
    if not resolve_asset(project_dir, folder, previous):
        return None
    return previous

def _warnings(project_dir, folder, file, spec_changed, normalized,
                    valeur, seed):
    """What success does NOT imply. Traps actually met, not hypotheses."""
    messages = []
    # 0. Placing a photo does not make the project compilable: the OTHER
    # declared and missing assets still block it. The tool only checks what it
    # writes (see _valider) — so it must say what is still missing, otherwise
    # 'monl update' would fail without anyone knowing why.
    _folder, declares = paths_declares(normalized)
    missing = [c for c in sorted(declares)
                 if c != valeur and not resolve_asset(project_dir, folder, c)]
    if missing:
        messages.append(
            f"{len(missing)} other declared asset(s) are still missing: "
            + ", ".join(missing)
            + ". Compilation will reject them — 'monl assets list' shows their status.")
    # 1. The seed only feeds a FRESH database. SneakerLab's migration to layer
    # 1 showed it: 12 items kept the old path, and the site would have shown 12
    # empty frames with nothing reporting it. Concerns ONLY editing a seed:
    # saying it when placing a logo would be an off-topic warning, and an
    # off-topic warning teaches people to ignore all of them.
    if seed and spec_changed and os.path.exists(os.path.join(project_dir, "app.db")):
        messages.append(
            "The database already exists: the 'seed' block only populates a NEW "
            "database. Existing records keep their old values — update them via "
            "the API (PUT) or start with an empty database.")
    # 2. Credits: completeness, never truthfulness (point 83).
    for candidate in NAMES_OF_CREDITS:
        path = os.path.join(project_dir, folder, candidate)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fh:
            if file not in fh.read():
                messages.append(
                    f"{folder}/{candidate} does not mention '{file}'. monl cannot "
                    f"verify attribution; it can only report that it is missing.")
        break
    # 3. The spec changed: the artifacts did not follow it.
    if spec_changed:
        messages.append("Spec changed: run 'monl update' to resynchronize the "
                        "backend and contract.")
    return messages

# ----------------------------------------------------------------- list --
def lister_assets(spec_path, project_dir):
    """What the spec declares, what is present, what lies around undeclared."""
    project_dir = os.path.abspath(project_dir)
    normalized = _charger(spec_path)
    folder, declares = paths_declares(normalized)

    lines, resolved = [], set()
    for path in sorted(declares):
        found = resolve_asset(project_dir, folder, path)
        if found:
            resolved.add(os.path.realpath(found))
        lines.append({
            "chemin": path,
            "origines": declares[path],
            "present": bool(found),
            # A logo is declared by its name alone: saying WHERE it was found
            # avoids suggesting it lives at the project root.
            "resolu": os.path.relpath(found, project_dir) if found else None,
            "taille": os.path.getsize(found) if found else None,
        })

    # "Orphan" is not a reproach: a credits file, or a photo hard-coded in a
    # frontend page, legitimately lives here without the spec declaring it. The
    # report observes, it does not judge.
    racine = os.path.join(project_dir, folder)
    orphans = []
    if os.path.isdir(racine):
        for base, _sous, files in os.walk(racine):
            for name in files:
                path = os.path.join(base, name)
                if os.path.realpath(path) not in resolved:
                    orphans.append(os.path.relpath(path, project_dir))
    return {"dir": folder, "declares": lines, "orphelins": sorted(orphans)}
