"""What changed since the last build.

`_rapporter_delta` is SHARED by `update` and `diff`: two delta
calculations would diverge, and it is the calculation six points struggled
to keep right."""

import contextlib
import io
import os
import tempfile

from ..errors import MonlError
from ..frontend_ai import UPDATE_PROMPT_FILENAME
from . import construction, emplacement, signature

# ----------------------------------------------------------------- update --
# The names of the two evolution briefs live in frontend_ai (which CONSUMES
# them) and are imported at the top of this module (which WRITES them).

def _write_update_brief(project_dir, added_routes, removed_routes,
                        added_fields, removed_fields,
                        added_acces=(), removed_acces=(),
                        scelles=(), liberes=(),
                        added_prea=(), removed_prea=(),
                        added_verrous=(), removed_verrous=(),
                        added_contenus=(), removed_contenus=(),
                        modifies_contenus=(), changed_liens=(),
                        changed_types=()):
    """Point 3 of the pivot: the delta is not just informative, it becomes an
    INSTRUCTION ready to give to the frontend AI — the loop closes without the
    human having to rephrase the change."""
    def bullet(items, verb):
        return "\n".join(f"- {verb} `{i}`" for i in sorted(items))
    sections = []
    # A table rather than seventeen `if`s: the order of the sections is the
    # order of the rows, and one more instruction adds no branch.
    consignes = (
        (added_routes,
         "## New routes to use\n",
         "connect"),
        (removed_routes,
         "## REMOVED routes — remove every call\n",
         "stop calling"),
        (added_fields,
         "## New fields to display or enter\n",
         "integrate"),
        (removed_fields,
         "## REMOVED fields — remove from views and forms\n",
         "remove"),
        (changed_types,
         "## CHANGED field types — review input and display\n"
         "The field name is unchanged, but its expected value is: "
         "adapt input validation, formatting, and error messages to the "
         "new type.\n",
         "adapt"),
        # POINT 88: a role that gains access to an existing route adds no
        # route, but often calls for a whole screen (a back office, a
        # supervision view). It is the delta's most silent case: nothing is
        # broken, and yet something is missing.
        (added_acces,
         "## Newly authorized roles — plan screens\n"
         "These routes already existed; one more role can now call them. "
         "Make sure the interface offers them to that role, and that a "
         "supervisor role can see all records, not only its own.\n",
         "make available to"),
        (removed_acces,
         "## REMOVED access — hide actions that will return 403\n",
         "stop offering to"),
        # POINT 99: the foreign key changes nature without changing name. Two
        # quite distinct consequences for the interface — a join to redo, or
        # one more mandatory field in the creation form — hence the two
        # separate instructions rather than one sentence that would half cover
        # both.
        (changed_liens,
         "## Relationships whose kind changed\n"
         "For each one: if the line says ‘an account identifier’, join "
         "through the matching profile column, never its `id`. If it says "
         "‘provided by the client’, the creation form must let the user "
         "CHOOSE the related record (a dropdown populated by the matching "
         "read route); without this field, creation returns 422.\n",
         "review"),
        # POINT 89: the field still exists and carries the same name — only its
        # meaning changed. It is the delta's second silent case: nothing is
        # broken, and yet a form has become a display.
        (scelles,
         "## Fields now READ-ONLY — remove from forms\n"
         "The server now calculates or timestamps these fields itself. "
         "Sending them does not fail: they are simply ignored, which is "
         "worse because users think they entered a value.\n",
         "stop sending; display only"),
        (liberes,
         "## Fields editable again\n",
         "offer for input"),
        # POINT 90: the route did not move, its PREREQUISITE did. It is the
        # user journey that must be reworked, not a field to add.
        (added_prea,
         "## Added PREREQUISITES — the user flow changes, not just the screen\n"
         "These routes already existed and now return 409 until the caller "
         "owns the named record. Check during loading and offer creation "
         "BEFORE the form: if discovered at the end, the refusal arrives "
         "after the user has filled everything in.\n",
         "plan for"),
        (removed_prea,
         "## Removed PREREQUISITES — the intermediate step is no longer needed\n",
         "stop requiring"),
        # POINT 91: the route did not move, it gained a conditional REFUSAL. It
        # is a button to hide depending on the state of the displayed record —
        # not one more screen, not one more field: the easiest case to miss
        # when rereading only the list of routes.
        (added_verrous,
         "## PAYMENT LOCKS — hide actions on a paid record\n"
         "These routes already existed and now return 409 once the record "
         "has been paid (`payment_status` is `payee`). Show the button only "
         "when this field allows it; read routes already return it. If "
         "discovered on click, the refusal comes after the user changed "
         "their cart. A captured payment cannot be edited; refund it through "
         "the provider.\n",
         "condition"),
        (removed_verrous,
         "## Removed locks — the action is available again after payment\n",
         "stop conditioning"),
        # POINT 94: CONTENT, not data. No route serves it — it exists only in
        # the contract, so an AI that does not read it here will learn it
        # nowhere else.
        (added_contenus,
         "## ADDED editorial content — publish on the home page\n"
         "The full text is in `FRONTEND_PROMPT.md` (the ‘Editorial content’ "
         "and ‘Frequently asked questions’ sections). Render each FAQ item "
         "separately, never as one paragraph.\n",
         "publish"),
        (removed_contenus,
         "## REMOVED content — remove from the page\n",
         "remove"),
        (modifies_contenus,
         "## REWRITTEN content — same title, different text\n"
         "The title is unchanged, but the text changed: use the current "
         "version in `FRONTEND_PROMPT.md`. This is the easiest change to "
         "miss because nothing appears to have moved.\n",
         "replace the text of"),
    )
    sections.extend(entete + bullet(items, verbe)
                    for items, entete, verbe in consignes if items)
    body = f"""# Frontend update (delta generated by 'monl update')

The backend has changed. Update the existing frontend in `frontend/` to
reflect ONLY the changes below; do not rewrite what already works. The full,
current contract is in `frontend_contract.json` (the rules in
`FRONTEND_PROMPT.md` still apply).

{chr(10).join(sections)}

After the change, `monl run` will revalidate everything (static consistency
+ behavioral smoke test) before launch.

If you are reading this in a conversation (without an API key): provide the
updated frontend as a downloadable ZIP or standalone `index.html`; the user
will install it with `monl import <file> <project>`.
"""
    path = os.path.join(project_dir, UPDATE_PROMPT_FILENAME)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(body)
    return path

def _rapporter_delta(ancienne, nouvelle, project_dir, ecrire_brief=True):
    """Compares two contract signatures, prints the delta, and returns True if
    there is something to rewrite.

    POINT 103: extracted from `cmd_update` so that `monl diff` is the SAME
    report, not a second implementation. Two delta calculations would
    eventually diverge — and it is precisely the calculation that five points
    (88 to 91, 94, 99) showed is hard to keep right."""
    (old_routes, old_fields, old_acces, old_ro, old_prea, old_verrous,
     old_contenus, old_liens, old_types, old_sections) = ancienne
    (new_routes, new_fields, new_acces, new_ro, new_prea, new_verrous,
     new_contenus, new_liens, new_types, new_sections) = nouvelle

    added_routes, removed_routes = new_routes - old_routes, old_routes - new_routes
    added_fields, removed_fields = new_fields - old_fields, old_fields - new_fields
    # The access of a route that just appeared or disappeared is already stated
    # by the two lists above: keep only the routes that EXISTED on both sides,
    # otherwise every addition would be reported twice.
    stables = new_routes & old_routes
    added_acces = {a for a in new_acces - old_acces if a.split(" → ")[0] in stables}
    removed_acces = {a for a in old_acces - new_acces if a.split(" → ")[0] in stables}
    # POINT 89: same filter, same reason — a field that just appeared is
    # already described by `added_fields`, where its read-only status is
    # annotated.
    champs_stables = new_fields & old_fields
    scelles = (new_ro - old_ro) & champs_stables
    liberes = (old_ro - new_ro) & champs_stables
    # Same filter as for access: a route that just appeared carries its
    # prerequisite in "route added", counting it twice would drown the signal.
    added_prea = {p for p in new_prea - old_prea if p.split(" → ")[0] in stables}
    removed_prea = {p for p in old_prea - new_prea if p.split(" → ")[0] in stables}
    # POINT 91: same filter, fourth time. Setting `payable` freezes routes that
    # already existed — the frontend must remove a button, without any path,
    # actor or field having changed.
    added_verrous = {v for v in new_verrous - old_verrous
                     if v.split(" → ")[0] in stables}
    removed_verrous = {v for v in old_verrous - new_verrous
                       if v.split(" → ")[0] in stables}
    # POINT 94: three cases, not two — content can be REWRITTEN without
    # changing its title, and it is the most silent of the three.
    added_contenus = set(new_contenus) - set(old_contenus)
    removed_contenus = set(old_contenus) - set(new_contenus)
    modifies_contenus = {c for c in set(new_contenus) & set(old_contenus)
                         if new_contenus[c] != old_contenus[c]}
    # POINT 99: the same anti-duplication trade-off as in points 88 to 91,
    # applied to entities rather than routes. The attachments of an entity that
    # just appeared are already stated by its routes and fields; only those of
    # an entity that existed on both sides deserve a line.
    entites_stables = {f.split(".", 1)[0] for f in new_fields & old_fields}
    changed_liens = {li for li in (new_liens - old_liens)
                     if li.split(".", 1)[0] in entites_stables}
    changed_types = {f"{field}: {old_types[field]} → {new_types[field]}"
                     for field in (new_fields & old_fields)
                     if old_types.get(field) != new_types.get(field)}
    # POINT 119: three cases as for content (point 94) — a section can appear,
    # disappear, or have its rule TIGHTENED without changing name. The third is
    # the silent one: raising the text required by `trust` renames nothing and
    # yet makes the site non-compliant.
    added_sections = set(new_sections) - set(old_sections)
    removed_sections = set(old_sections) - set(new_sections)
    modifies_sections = {c for c in set(new_sections) & set(old_sections)
                         if new_sections[c] != old_sections[c]}
    changes = any((added_routes, removed_routes, added_fields, removed_fields,
                   added_acces, removed_acces, scelles, liberes,
                   added_prea, removed_prea, added_verrous, removed_verrous,
                   added_contenus, removed_contenus, modifies_contenus,
                   changed_liens, changed_types,
                   added_sections, removed_sections, modifies_sections))
    # The name alone does not say a new field is read-only; the brief's section
    # is titled "to display/enter", which would be a misreading for a timestamp
    # or a calculated total.
    added_fields = {f"{c} (read-only — set by the server)" if c in new_ro else c
                    for c in added_fields}

    print("\n─── Frontend contract delta ───")
    for item in sorted(added_routes):
        print(f"  + route added: {item}")
    for item in sorted(removed_routes):
        print(f"  - route removed: {item}")
    for item in sorted(added_fields):
        print(f"  + field added: {item}")
    for item in sorted(removed_fields):
        print(f"  - field removed: {item}")
    for item in sorted(added_acces):
        print(f"  + access granted: {item}")
    for item in sorted(removed_acces):
        print(f"  - access removed: {item}")
    for item in sorted(scelles):
        print(f"  ! field is now read-only: {item}")
    for item in sorted(liberes):
        print(f"  ! field is editable again: {item}")
    for item in sorted(added_prea):
        print(f"  ! prerequisite added: {item}")
    for item in sorted(removed_prea):
        print(f"  ! prerequisite removed: {item}")
    for item in sorted(added_verrous):
        print(f"  ! payment lock: {item}")
    for item in sorted(removed_verrous):
        print(f"  ! payment lock removed: {item}")
    for item in sorted(changed_liens):
        print(f"  ! relationship: {item}")
    for item in sorted(changed_types):
        print(f"  ! field type changed: {item}")
    for item in sorted(added_contenus):
        print(f"  + content added: {item}")
    for item in sorted(removed_contenus):
        print(f"  - content removed: {item}")
    for item in sorted(modifies_contenus):
        print(f"  ! content rewritten: {item}")
    for item in sorted(added_sections):
        print(f"  + required section: {item} — add to the home page")
    for item in sorted(removed_sections):
        print(f"  - required section removed: {item}")
    for item in sorted(modifies_sections):
        print(f"  ! required section strengthened: {item} — its minimum content changed")
    if not changes:
        print("  (no interface changes — the existing frontend remains valid)")
    elif ecrire_brief:
        brief_path = _write_update_brief(project_dir, added_routes, removed_routes,
                                         added_fields, removed_fields,
                                         added_acces, removed_acces,
                                         scelles, liberes,
                                         added_prea, removed_prea,
                                         added_verrous, removed_verrous,
                                         added_contenus, removed_contenus,
                                         modifies_contenus, changed_liens,
                                         changed_types)
        print(f"  → Instructions ready for the frontend AI: {os.path.basename(brief_path)}")
    print("──────────────────────────────────────────────────────────────────")
    return changes

def cmd_update(project_dir):
    project_dir, spec_path = emplacement._situer_projet(project_dir, "update")
    ancienne = emplacement._signature_precedente(project_dir)
    nouveau = construction.compile_project(spec_path, project_dir)
    _rapporter_delta(ancienne, signature._contract_signature(nouveau), project_dir)
    print("The existing database is preserved: new columns are added by an "
          "additive migration at startup (docs/MIGRATIONS.md).")

# ------------------------------------------------------------------- diff --
# POINT 103: `monl update` writes THEN reports. As long as the report says what
# was expected, the order has no consequence; the day it announces a whole
# screen to rewrite, one would have liked to know before recompiling and
# replacing the reference contract.
#
# `monl diff` answers the same question without touching anything: it compiles
# into a TEMPORARY folder, compares, prints, and leaves. No project file is
# written — neither app.py, nor the contract, nor monl.json, nor the evolution
# instruction.
def cmd_diff(project_dir):
    project_dir, spec_path = emplacement._situer_projet(project_dir, "compare")
    ancienne = emplacement._signature_precedente(project_dir)

    # The output folder is throwaway, but `base_dir` must stay the REAL
    # project: it is the one carrying the declared assets, and checking them in
    # an empty folder would make compilation fail for a reason that does not
    # exist (brick 13, point 83).
    with tempfile.TemporaryDirectory(prefix="monl-diff-") as atelier:
        tampon = io.StringIO()
        try:
            with contextlib.redirect_stdout(tampon):
                nouveau = construction.compile_project(spec_path, atelier,
                                          base_dir=project_dir, save_state=False)
        except MonlError as err:
            # Compilation failed: it is ITS message that is useful, not ours.
            # System interrupts propagate naturally.
            print(tampon.getvalue(), end="")
            print(f" ❌ {err}")
            raise SystemExit(1) from err

    print("\n[DRY-RUN] No files changed — comparison only.")
    changes = _rapporter_delta(ancienne, signature._contract_signature(nouveau),
                               project_dir, ecrire_brief=False)
    if changes:
        print("To apply this change and write the update instructions: "
              "monl update")
    return changes
