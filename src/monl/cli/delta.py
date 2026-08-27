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
        sections.append("## Nouvelles routes à exploiter\n"
                        + bullet(added_routes, "brancher"))
    if removed_routes:
        sections.append("## Routes SUPPRIMÉES — retirer tout appel\n"
                        + bullet(removed_routes, "ne plus appeler"))
    if added_fields:
        sections.append("## Nouveaux champs à afficher/saisir\n"
                        + bullet(added_fields, "intégrer"))
    if removed_fields:
        sections.append("## Champs SUPPRIMÉS — retirer des vues et formulaires\n"
                        + bullet(removed_fields, "retirer"))
    if changed_types:
        sections.append(
            "## Types de champs MODIFIÉS — revoir saisie et affichage\n"
            "Le nom du champ n'a pas bougé, mais sa valeur attendue si : "
            "adapter le contrôle de saisie, le formatage et les messages "
            "d'erreur au nouveau type.\n"
            + bullet(changed_types, "adapter"))
    # POINT 88 : un rôle qui gagne l'accès à une route existante n'ajoute aucune
    # route, mais réclame souvent tout un écran (un back-office, une vue de
    # supervision). C'est le cas le plus silencieux du delta : rien n'est cassé,
    # et pourtant il manque quelque chose.
    if added_acces:
        sections.append(
            "## Rôles nouvellement autorisés — écrans à prévoir\n"
            "Ces routes existaient déjà ; un rôle de plus peut désormais les "
            "appeler. Vérifier que l'interface le lui propose, et qu'un rôle "
            "de supervision voit bien l'ensemble des enregistrements — pas "
            "seulement les siens.\n"
            + bullet(added_acces, "ouvrir à"))
    if removed_acces:
        sections.append(
            "## Accès RETIRÉS — masquer ce qui répondra 403\n"
            + bullet(removed_acces, "ne plus proposer à"))
    # POINT 99 : la clé étrangère change de nature sans changer de nom. Deux
    # conséquences bien distinctes pour l'interface — une jointure à refaire, ou
    # un champ obligatoire de plus au formulaire de création — d'où les deux
    # consignes séparées plutôt qu'une phrase qui couvrirait les deux à moitié.
    if changed_liens:
        sections.append(
            "## Rattachements dont la nature a changé\n"
            "Pour chacun : si la ligne dit « un identifiant de compte », joindre "
            "par la colonne HOMONYME de la fiche, jamais par son `id`. Si elle "
            "dit « à envoyer par le client », le formulaire de création doit "
            "proposer de CHOISIR l'enregistrement lié (une liste déroulante "
            "alimentée par la route de lecture correspondante) — sans ce champ, "
            "la création répond 422.\n"
            + bullet(changed_liens, "revoir"))
    # POINT 89 : le champ existe toujours et porte le même nom — seul son sens a
    # changé. C'est le second cas silencieux du delta : rien n'est cassé, et
    # pourtant un formulaire est devenu un affichage.
    if scelles:
        sections.append(
            "## Champs devenus en LECTURE SEULE — retirer des formulaires\n"
            "Le serveur les calcule ou les horodate désormais lui-même. Les "
            "envoyer n'échoue pas : ils sont simplement ignorés, ce qui est "
            "pire — l'utilisateur croit avoir saisi une valeur.\n"
            + bullet(scelles, "ne plus envoyer, seulement afficher"))
    if liberes:
        sections.append(
            "## Champs redevenus SAISISSABLES\n"
            + bullet(liberes, "proposer à la saisie"))
    # POINT 90 : la route n'a pas bougé, son PRÉALABLE oui. C'est le parcours
    # utilisateur qu'il faut reprendre, pas un champ à ajouter.
    if added_prea:
        sections.append(
            "## PRÉALABLES ajoutés — le parcours change, pas seulement l'écran\n"
            "Ces routes existaient déjà et répondent désormais 409 tant que "
            "l'appelant ne possède pas l'enregistrement nommé. Vérifier au "
            "chargement et proposer la création AVANT le formulaire : découvert "
            "à la fin, le refus tombe là où l'utilisateur a déjà tout rempli.\n"
            + bullet(added_prea, "prévoir"))
    if removed_prea:
        sections.append(
            "## Préalables LEVÉS — l'étape intermédiaire n'est plus nécessaire\n"
            + bullet(removed_prea, "ne plus imposer"))
    # POINT 91 : la route n'a pas bougé, elle a gagné un REFUS conditionnel.
    # C'est un bouton à masquer selon l'état de l'enregistrement affiché — pas
    # un écran de plus, pas un champ de plus : le cas le plus facile à manquer
    # en relisant la seule liste des routes.
    if added_verrous:
        sections.append(
            "## VERROUS de paiement — actions à masquer sur un enregistrement payé\n"
            "Ces routes existaient déjà et répondent désormais 409 dès que "
            "l'enregistrement concerné est réglé (`payment_status` vaut "
            "`payee`). Conditionner l'affichage du bouton à ce champ, que les "
            "routes de lecture renvoient déjà : découvert au clic, le refus "
            "arrive après que l'utilisateur a modifié son panier. Un montant "
            "encaissé ne se modifie plus, il se rembourse chez le prestataire.\n"
            + bullet(added_verrous, "conditionner"))
    if removed_verrous:
        sections.append(
            "## Verrous LEVÉS — l'action redevient possible après règlement\n"
            + bullet(removed_verrous, "ne plus conditionner"))
    # POINT 94 : du CONTENU, pas des données. Aucune route ne le sert — il
    # n'existe que dans le contrat, donc une IA qui ne le lit pas ici ne
    # l'apprendra nulle part ailleurs.
    if added_contenus:
        sections.append(
            "## Contenu éditorial AJOUTÉ — à publier sur l'accueil\n"
            "Le texte complet est dans `FRONTEND_PROMPT.md` (rubriques "
            "« Contenu éditorial » et « Questions fréquentes »). Une FAQ se rend "
            "en entrées distinctes — jamais en un seul paragraphe.\n"
            + bullet(added_contenus, "publier"))
    if removed_contenus:
        sections.append(
            "## Contenu RETIRÉ — à faire disparaître de la page\n"
            + bullet(removed_contenus, "retirer"))
    if modifies_contenus:
        sections.append(
            "## Contenu RÉÉCRIT — même titre, texte différent\n"
            "Le titre n'a pas bougé, le texte si : reprendre la version à jour "
            "dans `FRONTEND_PROMPT.md`. C'est le changement le plus facile à "
            "manquer, puisque rien n'a l'air d'avoir bougé.\n"
            + bullet(modifies_contenus, "remplacer le texte de"))
    body = f"""# Mise à jour du frontend (delta généré par 'monl update')

Le backend a évolué. Modifiez le frontend existant dans `frontend/` pour
refléter UNIQUEMENT les changements ci-dessous — ne réécrivez pas ce qui
fonctionne déjà. Le contrat complet à jour est dans `frontend_contract.json`
(les règles de `FRONTEND_PROMPT.md` restent en vigueur).

{chr(10).join(sections)}

Après modification, `monl run` revalidera l'ensemble (cohérence statique
+ smoke test comportemental) avant tout lancement.

Si vous lisez ceci dans une conversation (sans clé API) : rendez le
frontend mis à jour en ZIP téléchargeable ou en `index.html` autonome —
l'utilisateur l'installera avec `monl import <fichier> <projet>`.
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
    changed_types = {f"{field} : {old_types[field]} → {new_types[field]}"
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
    added_fields = {f"{c} (lecture seule — écrit par le serveur)" if c in new_ro else c
                    for c in added_fields}

    print("\n─── Delta du contrat frontend ───")
    for item in sorted(added_routes):
        print(f"  + route ajoutée : {item}")
    for item in sorted(removed_routes):
        print(f"  - route retirée : {item}")
    for item in sorted(added_fields):
        print(f"  + champ ajouté : {item}")
    for item in sorted(removed_fields):
        print(f"  - champ retiré : {item}")
    for item in sorted(added_acces):
        print(f"  + accès ouvert : {item}")
    for item in sorted(removed_acces):
        print(f"  - accès retiré : {item}")
    for item in sorted(scelles):
        print(f"  ! champ devenu en lecture seule : {item}")
    for item in sorted(liberes):
        print(f"  ! champ redevenu saisissable : {item}")
    for item in sorted(added_prea):
        print(f"  ! préalable ajouté : {item}")
    for item in sorted(removed_prea):
        print(f"  ! préalable levé : {item}")
    for item in sorted(added_verrous):
        print(f"  ! verrou de paiement : {item}")
    for item in sorted(removed_verrous):
        print(f"  ! verrou de paiement levé : {item}")
    for item in sorted(changed_liens):
        print(f"  ! rattachement : {item}")
    for item in sorted(changed_types):
        print(f"  ! type de champ changé : {item}")
    for item in sorted(added_contenus):
        print(f"  + contenu ajouté : {item}")
    for item in sorted(removed_contenus):
        print(f"  - contenu retiré : {item}")
    for item in sorted(modifies_contenus):
        print(f"  ! contenu réécrit : {item}")
    for item in sorted(added_sections):
        print(f"  + section obligatoire : {item} — à dessiner sur l'accueil")
    for item in sorted(removed_sections):
        print(f"  - section obligatoire retirée : {item}")
    for item in sorted(modifies_sections):
        print(f"  ! section obligatoire durcie : {item} — son contenu minimal a changé")
    if not changes:
        print("  (aucun changement d'interface — le frontend existant reste valide)")
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
        print(f"  → Consigne prête pour l'IA frontend : {os.path.basename(brief_path)}")
    print("──────────────────────────────────────────────────────────────────")
    return changes

def cmd_update(project_dir):
    project_dir, spec_path = emplacement._situer_projet(project_dir, "mettre à jour")
    ancienne = emplacement._signature_precedente(project_dir)
    nouveau = construction.compile_project(spec_path, project_dir)
    _rapporter_delta(ancienne, signature._contract_signature(nouveau), project_dir)
    print("La base de données existante est préservée : les nouvelles colonnes "
          "sont ajoutées par migration additive au démarrage (docs/MIGRATIONS.md).")

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
    project_dir, spec_path = emplacement._situer_projet(project_dir, "comparer")
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

    print("\n[DRY-RUN] Aucun fichier modifié — comparaison seule.")
    changes = _rapporter_delta(ancienne, signature._contract_signature(nouveau),
                               project_dir, ecrire_brief=False)
    if changes:
        print("Pour appliquer ce changement et écrire la consigne d'évolution : "
              "monl update")
    return changes
