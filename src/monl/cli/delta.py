"""Ce qui a changé depuis la dernière construction.

`_rapporter_delta` est PARTAGÉ par `update` et `diff` : deux calculs de
delta divergeraient, et c'est le calcul que six points ont eu du mal à
tenir juste."""

import contextlib
import io
import os
import tempfile

from ..errors import MonlError
from ..frontend_ai import UPDATE_PROMPT_FILENAME
from . import construction, emplacement, signature

# ----------------------------------------------------------------- update --
# Les noms des deux briefs d'évolution vivent dans frontend_ai (qui les
# CONSOMME) et sont importés en tête de ce module (qui les ÉCRIT).

def _write_update_brief(project_dir, added_routes, removed_routes,
                        added_fields, removed_fields,
                        added_acces=(), removed_acces=(),
                        scelles=(), liberes=(),
                        added_prea=(), removed_prea=(),
                        added_verrous=(), removed_verrous=(),
                        added_contenus=(), removed_contenus=(),
                        modifies_contenus=(), changed_liens=(),
                        changed_types=()):
    """Point 3 du pivot : le delta n'est pas qu'informatif, il devient une
    CONSIGNE prête à donner à l'IA frontend — la boucle se ferme sans que
    l'humain ait à reformuler le changement."""
    def bullet(items, verb):
        return "\n".join(f"- {verb} `{i}`" for i in sorted(items))
    sections = []
    if added_routes:
        sections.append("## New routes to use\n"
                        + bullet(added_routes, "connect"))
    if removed_routes:
        sections.append("## REMOVED routes — remove every call\n"
                        + bullet(removed_routes, "stop calling"))
    if added_fields:
        sections.append("## New fields to display or enter\n"
                        + bullet(added_fields, "integrate"))
    if removed_fields:
        sections.append("## REMOVED fields — remove from views and forms\n"
                        + bullet(removed_fields, "remove"))
    if changed_types:
        sections.append(
            "## CHANGED field types — review input and display\n"
            "The field name is unchanged, but its expected value is: "
            "adapt input validation, formatting, and error messages to the "
            "new type.\n"
            + bullet(changed_types, "adapt"))
    # POINT 88 : un rôle qui gagne l'accès à une route existante n'ajoute aucune
    # route, mais réclame souvent tout un écran (un back-office, une vue de
    # supervision). C'est le cas le plus silencieux du delta : rien n'est cassé,
    # et pourtant il manque quelque chose.
    if added_acces:
        sections.append(
            "## Newly authorized roles — plan screens\n"
            "These routes already existed; one more role can now call them. "
            "Make sure the interface offers them to that role, and that a "
            "supervisor role can see all records, not only its own.\n"
            + bullet(added_acces, "make available to"))
    if removed_acces:
        sections.append(
            "## REMOVED access — hide actions that will return 403\n"
            + bullet(removed_acces, "stop offering to"))
    # POINT 99 : la clé étrangère change de nature sans changer de nom. Deux
    # conséquences bien distinctes pour l'interface — une jointure à refaire, ou
    # un champ obligatoire de plus au formulaire de création — d'où les deux
    # consignes séparées plutôt qu'une phrase qui couvrirait les deux à moitié.
    if changed_liens:
        sections.append(
            "## Relationships whose kind changed\n"
            "For each one: if the line says ‘an account identifier’, join "
            "through the matching profile column, never its `id`. If it says "
            "‘provided by the client’, the creation form must let the user "
            "CHOOSE the related record (a dropdown populated by the matching "
            "read route); without this field, creation returns 422.\n"
            + bullet(changed_liens, "review"))
    # POINT 89 : le champ existe toujours et porte le même nom — seul son sens a
    # changé. C'est le second cas silencieux du delta : rien n'est cassé, et
    # pourtant un formulaire est devenu un affichage.
    if scelles:
        sections.append(
            "## Fields now READ-ONLY — remove from forms\n"
            "The server now calculates or timestamps these fields itself. "
            "Sending them does not fail: they are simply ignored, which is "
            "worse because users think they entered a value.\n"
            + bullet(scelles, "stop sending; display only"))
    if liberes:
        sections.append(
            "## Fields editable again\n"
            + bullet(liberes, "offer for input"))
    # POINT 90 : la route n'a pas bougé, son PRÉALABLE oui. C'est le parcours
    # utilisateur qu'il faut reprendre, pas un champ à ajouter.
    if added_prea:
        sections.append(
            "## Added PREREQUISITES — the user flow changes, not just the screen\n"
            "These routes already existed and now return 409 until the caller "
            "owns the named record. Check during loading and offer creation "
            "BEFORE the form: if discovered at the end, the refusal arrives "
            "after the user has filled everything in.\n"
            + bullet(added_prea, "plan for"))
    if removed_prea:
        sections.append(
            "## Removed PREREQUISITES — the intermediate step is no longer needed\n"
            + bullet(removed_prea, "stop requiring"))
    # POINT 91 : la route n'a pas bougé, elle a gagné un REFUS conditionnel.
    # C'est un bouton à masquer selon l'état de l'enregistrement affiché — pas
    # un écran de plus, pas un champ de plus : le cas le plus facile à manquer
    # en relisant la seule liste des routes.
    if added_verrous:
        sections.append(
            "## PAYMENT LOCKS — hide actions on a paid record\n"
            "These routes already existed and now return 409 once the record "
            "has been paid (`payment_status` is `payee`). Show the button only "
            "when this field allows it; read routes already return it. If "
            "discovered on click, the refusal comes after the user changed "
            "their cart. A captured payment cannot be edited; refund it through "
            "the provider.\n"
            + bullet(added_verrous, "condition"))
    if removed_verrous:
        sections.append(
            "## Removed locks — the action is available again after payment\n"
            + bullet(removed_verrous, "stop conditioning"))
    # POINT 94 : du CONTENU, pas des données. Aucune route ne le sert — il
    # n'existe que dans le contrat, donc une IA qui ne le lit pas ici ne
    # l'apprendra nulle part ailleurs.
    if added_contenus:
        sections.append(
            "## ADDED editorial content — publish on the home page\n"
            "The full text is in `FRONTEND_PROMPT.md` (the ‘Editorial content’ "
            "and ‘Frequently asked questions’ sections). Render each FAQ item "
            "separately, never as one paragraph.\n"
            + bullet(added_contenus, "publish"))
    if removed_contenus:
        sections.append(
            "## REMOVED content — remove from the page\n"
            + bullet(removed_contenus, "remove"))
    if modifies_contenus:
        sections.append(
            "## REWRITTEN content — same title, different text\n"
            "The title is unchanged, but the text changed: use the current "
            "version in `FRONTEND_PROMPT.md`. This is the easiest change to "
            "miss because nothing appears to have moved.\n"
            + bullet(modifies_contenus, "replace the text of"))
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
    """Compare deux signatures de contrat, imprime le delta, et rend True s'il
    y a de quoi réécrire quelque chose.

    POINT 103 : extrait de `cmd_update` pour que `monl diff` en soit le MÊME
    rapport, et pas une deuxième implémentation. Deux calculs de delta
    finiraient par diverger — et c'est précisément le calcul dont cinq points
    (88 à 91, 94, 99) ont montré qu'il est difficile à tenir juste."""
    (old_routes, old_fields, old_acces, old_ro, old_prea, old_verrous,
     old_contenus, old_liens, old_types, old_sections) = ancienne
    (new_routes, new_fields, new_acces, new_ro, new_prea, new_verrous,
     new_contenus, new_liens, new_types, new_sections) = nouvelle

    added_routes, removed_routes = new_routes - old_routes, old_routes - new_routes
    added_fields, removed_fields = new_fields - old_fields, old_fields - new_fields
    # Les accès d'une route qui vient d'apparaître ou de disparaître sont déjà
    # dits par les deux listes ci-dessus : ne garder que les routes qui EXISTAIENT
    # des deux côtés, sinon chaque ajout serait rapporté deux fois.
    stables = new_routes & old_routes
    added_acces = {a for a in new_acces - old_acces if a.split(" → ")[0] in stables}
    removed_acces = {a for a in old_acces - new_acces if a.split(" → ")[0] in stables}
    # POINT 89 : même filtre, même raison — un champ qui vient d'apparaître est
    # déjà décrit par `added_fields`, où sa lecture seule est annotée.
    champs_stables = new_fields & old_fields
    scelles = (new_ro - old_ro) & champs_stables
    liberes = (old_ro - new_ro) & champs_stables
    # Même filtre que pour les accès : une route qui vient d'apparaître porte
    # son préalable dans « route ajoutée », l'y compter deux fois noierait le
    # signal.
    added_prea = {p for p in new_prea - old_prea if p.split(" → ")[0] in stables}
    removed_prea = {p for p in old_prea - new_prea if p.split(" → ")[0] in stables}
    # POINT 91 : même filtre, quatrième fois. Poser `payable` fige des routes
    # qui existaient déjà — le frontend doit retirer un bouton, sans qu'aucun
    # chemin, acteur ou champ n'ait changé.
    added_verrous = {v for v in new_verrous - old_verrous
                     if v.split(" → ")[0] in stables}
    removed_verrous = {v for v in old_verrous - new_verrous
                       if v.split(" → ")[0] in stables}
    # POINT 94 : trois cas, pas deux — un contenu peut être RÉÉCRIT sans changer
    # de titre, et c'est le cas le plus silencieux des trois.
    added_contenus = set(new_contenus) - set(old_contenus)
    removed_contenus = set(old_contenus) - set(new_contenus)
    modifies_contenus = {c for c in set(new_contenus) & set(old_contenus)
                         if new_contenus[c] != old_contenus[c]}
    # POINT 99 : même arbitrage anti-doublon qu'aux points 88 à 91, appliqué aux
    # entités plutôt qu'aux routes. Les rattachements d'une entité qui vient
    # d'apparaître sont déjà dits par ses routes et ses champs ; seuls ceux
    # d'une entité qui existait des deux côtés méritent une ligne.
    entites_stables = {f.split(".", 1)[0] for f in new_fields & old_fields}
    changed_liens = {li for li in (new_liens - old_liens)
                     if li.split(".", 1)[0] in entites_stables}
    changed_types = {f"{field}: {old_types[field]} → {new_types[field]}"
                     for field in (new_fields & old_fields)
                     if old_types.get(field) != new_types.get(field)}
    # POINT 119 : trois cas comme pour le contenu (point 94) — une section
    # peut apparaître, disparaître, ou voir sa règle DURCIE sans changer de
    # nom. Le troisième est le silencieux : relever le texte exigé de `trust`
    # ne renomme rien et rend pourtant le site non conforme.
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
    # Le nom seul ne dit pas qu'un champ neuf est en lecture seule ; la rubrique
    # du brief s'intitule « à afficher/saisir », ce qui serait un contresens sur
    # un horodatage ou un total calculé.
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
# POINT 103 : `monl update` écrit PUIS rapporte. Tant que le rapport dit ce
# qu'on attendait, l'ordre est sans conséquence ; le jour où il annonce un
# écran entier à réécrire, on aimerait l'avoir su avant d'avoir recompilé et
# remplacé le contrat de référence.
#
# `monl diff` répond à la même question sans rien toucher : il compile dans un
# dossier TEMPORAIRE, compare, imprime, et s'en va. Aucun fichier du projet
# n'est écrit — ni app.py, ni le contrat, ni monl.json, ni la consigne
# d'évolution.
def cmd_diff(project_dir):
    project_dir, spec_path = emplacement._situer_projet(project_dir, "compare")
    ancienne = emplacement._signature_precedente(project_dir)

    # Le dossier de sortie est jetable, mais `base_dir` doit rester le VRAI
    # projet : c'est lui qui porte les assets déclarés, et les vérifier dans un
    # dossier vide ferait échouer la compilation pour une raison qui n'existe
    # pas (brique 13, point 83).
    with tempfile.TemporaryDirectory(prefix="monl-diff-") as atelier:
        tampon = io.StringIO()
        try:
            with contextlib.redirect_stdout(tampon):
                nouveau = construction.compile_project(spec_path, atelier,
                                          base_dir=project_dir, save_state=False)
        except MonlError as err:
            # La compilation a échoué : c'est SON message qui est utile, pas le
            # nôtre. Les interruptions système remontent naturellement.
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
