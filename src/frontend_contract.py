# ─────────────────────────────────────────────────────────────────────
# CONTRAT FRONTEND — pivot "monl orchestrateur" (brique 2).
#
# À partir de la spec validée (le DSL reste la SOURCE DE VÉRITÉ), ce module
# produit deux artefacts dans le dossier du projet :
#
#   - frontend_contract.json : description machine-lisible et EXHAUSTIVE de
#     ce que le backend généré expose réellement — routes (méthode, chemin,
#     authentification, acteurs), schémas d'entités (champs, types, requis,
#     hidden/generated/categorized), conventions d'auth (register/login/
#     logout, en-tête Authorization: Bearer), pagination. Rien n'y est
#     deviné : tout est dérivé des mêmes structures que la génération des
#     routes (_compute_route_map du générateur), donc contrat et API ne
#     peuvent pas diverger.
#
#   - FRONTEND_PROMPT.md : brief prêt à donner à une IA spécialisée (Claude,
#     GPT…) pour générer l'interface. Il embarque le contrat, les contraintes
#     (où écrire les fichiers, ne jamais toucher aux artefacts backend) et
#     les conventions d'appel de l'API.
#
# Le frontend produit par l'IA est attendu dans frontend/ (index.html en
# entrée) ; 'monl run' le sert sur /site sans modifier app.py (voir
# cli.py, wrapper serve.py).
# ─────────────────────────────────────────────────────────────────────
import hashlib
import json
import os

CONTRACT_VERSION = 3  # 2 : base_url même origine (51) · 3 : rôles + archétypes (54)

# RÔLES DE CHAMPS ET ARCHÉTYPES (point 54) — restauration, dans le CONTRAT,
# de ce que le point 35 dérivait pour le frontend que monl générait lui-même,
# et que le pivot (point 41) a supprimé sans le transposer. Sans ces rôles,
# un champ n'est qu'un `{nom, type}` : l'IA UI doit redeviner depuis les noms
# lequel est le titre, lequel est l'image de couverture, alors que monl sait
# le déduire de façon déterministe. Même philosophie qu'aux thèmes : dérivé
# de la spec, jamais déclaré dans le DSL métier.
MEDIA_HINTS = ("image", "photo", "cover", "couverture", "avatar", "picture",
               "thumbnail", "vignette", "banner", "banniere", "illustration",
               "visuel", "url")
CATEGORY_HINTS = ("category", "categorie", "genre", "kind", "tag", "rubrique",
                  "status", "statut", "etat", "type")


def _assign_field_roles(fields):
    """Attribue un rôle à chaque champ VISIBLE, dans l'ordre de priorité du
    point 35 : média, titre, description, prix, catégorie, puis méta (3 au
    plus). Les champs `hidden` n'en reçoivent aucun — ils ne sont jamais
    rendus, leur donner un rôle inviterait l'IA à les afficher."""
    visibles = [f for f in fields if not f["hidden_in_reads"]]
    roles = {}

    media = next((f["name"] for f in visibles
                  if f["type"] in ("String", "Text")
                  and any(h in f["name"].lower() for h in MEDIA_HINTS)), None)
    if media:
        roles[media] = "media"
    # Le titre est le premier String qui n'est pas déjà le média : sur une
    # entité dont le seul String est `imageUrl`, prendre ce champ comme titre
    # afficherait une URL en guise de nom (défaut réel du repli).
    titre = next((f["name"] for f in visibles
                  if f["type"] == "String" and f["name"] not in roles), None)
    if titre:
        roles[titre] = "title"
    description = next((f["name"] for f in visibles
                        if f["type"] == "Text" and f["name"] not in roles), None)
    if description:
        roles[description] = "description"
    prix = next((f["name"] for f in visibles
                 if f["type"] == "Money" and f["name"] not in roles), None)
    if prix:
        roles[prix] = "price"
    categorie = next((f["name"] for f in visibles
                      if f["name"] not in roles
                      and any(h in f["name"].lower() for h in CATEGORY_HINTS)), None)
    if categorie:
        roles[categorie] = "category"
    for f in visibles:                       # méta : 3 au plus (point 35)
        if f["name"] not in roles and sum(1 for r in roles.values() if r == "meta") < 3:
            roles[f["name"]] = "meta"
    return roles


def _archetype(roles, lisible, public):
    """Forme d'interface déduite des rôles présents ET de qui peut lire.

    La lisibilité PUBLIQUE est une condition du point 35 que la première
    version de cette fonction avait laissée tomber — et le défaut s'est vu
    tout de suite : l'entité `Message` d'un formulaire de contact (auteur +
    contenu) se voyait conseiller « grandes vignettes en grille ». Une
    collection interne se gère, elle ne se parcourt pas : elle mérite un
    tableau dense, jamais une vitrine.

    `shop` l'emporte sur `gallery` : un prix commande la mise en page bien
    plus qu'une image (le point 35 déclenchait déjà la boutique sur un champ
    Money). `list` reste le repli — sans rien à montrer, une galerie
    n'apporterait qu'une grille nue.

    ÉCART ASSUMÉ avec le point 35, qui exigeait un titre ET (un média OU une
    description) : un média SEUL suffit désormais. Une entité `photo + légende`
    sans champ titre — cas banal d'un portfolio — retombait en liste, et son
    image, sa seule raison d'être, se réduisait à une rangée de tableau.
    """
    if not lisible:
        return "form"
    if not public:
        return "list"
    valeurs = set(roles.values())
    if "price" in valeurs:
        return "shop"
    if "media" in valeurs or ("title" in valeurs and "description" in valeurs):
        return "gallery"
    return "list"


ARCHETYPE_GUIDANCE = {
    "gallery": ("galerie — le média commande la mise en page : grandes "
                "vignettes en grille, titre et catégorie en accompagnement, "
                "vue de détail au clic"),
    "shop": ("boutique — le prix est l'information décisive : il doit rester "
             "lisible sans effort à côté de chaque article, avec un appel à "
             "l'action clair"),
    "list": ("liste — rien à mettre en vitrine ici, ou collection réservée "
             "aux comptes autorisés : lecture dense et rapide, en rangées "
             "plutôt qu'en cartes"),
    "form": ("formulaire seul — cette entité s'écrit mais ne se lit nulle "
             "part : ne construire aucune vue de liste, juste la saisie"),
}
CONTRACT_FILENAME = "frontend_contract.json"
PROMPT_FILENAME = "FRONTEND_PROMPT.md"


def build_contract(normalized_ast, generator):
    """Construit le dictionnaire du contrat depuis l'AST normalisé et une
    instance de MonlSecureGenerator (réutilisée UNIQUEMENT pour ses
    calculs — _compute_route_map, champs masqués… — jamais pour générer)."""
    app_name = normalized_ast["meta"]["appName"]
    entities = normalized_ast["schema"]["entities"]
    hidden = generator.hidden_fields_by_entity
    generated = generator.generated_fields_by_entity
    categorized = {
        ent: [c["field"] for c in rules]
        for ent, rules in generator.categorized_fields_by_entity.items()
    }
    required = set()
    for rule in normalized_ast["security"].get("rules", []):
        if isinstance(rule, dict) and rule.get("type") == "required":
            required.add(rule.get("reference", ""))

    fk_placements = generator._compute_fk_placements()

    # Calculés AVANT les entités : l'archétype dépend de qui peut lire, pas
    # seulement des champs (voir _archetype). Même source de vérité que la
    # génération FastAPI — _compute_route_map, jamais une logique parallèle.
    route_map = generator._compute_route_map()
    public = generator.public_actions
    lisibles = {info["base_target"] for (act, _t), info in route_map.items()
                if act == "Read"}

    entity_specs = {}
    for ent, fields in entities.items():
        field_list = []
        for fname, ftype in fields.items():
            field_list.append({
                "name": fname,
                "type": ftype,
                "required": f"{ent}.{fname}" in required,
                # hidden : jamais présent dans les réponses de lecture
                "hidden_in_reads": fname in hidden.get(ent, []),
                # generated : à NE PAS envoyer à la création (rejeté sinon)
                "server_generated": fname in generated.get(ent, []),
                # categorized : la lecture renvoie un libellé, pas le nombre
                "categorized_in_reads": fname in categorized.get(ent, []),
            })
        fks = [
            {"column": p["fk_column"], "references": p["owner_entity"], "unique": p["unique"]}
            for p in fk_placements.get(ent, [])
        ]
        roles = _assign_field_roles(field_list)
        for f in field_list:
            f["role"] = roles.get(f["name"])
        entity_specs[ent] = {
            "fields": field_list, "foreign_keys": fks,
            "client_foreign_keys": _client_supplied_fks(generator, ent),
            "archetype": _archetype(roles, ent in lisibles, (ent, "Read") in public),
        }

    # Routes — mêmes clés de regroupement que la génération FastAPI réelle
    # (route_map et public sont calculés plus haut, pour les archétypes).
    routes = []
    for (act_type, target), info in route_map.items():
        base = info["base_target"]
        low = base.lower()
        is_public = (base, act_type) in public
        actors = sorted(info["actors"])
        if act_type == "Create":
            routes.append(_route("POST", f"/{low}", act_type, base, is_public, actors,
                                 request_fields=_creatable_fields(entity_specs.get(base))))
        elif act_type == "Read":
            routes.append(_route("GET", f"/{low}", "List", base, is_public, actors,
                                 note="Paramètres : limit (max 200), offset. Réponse : "
                                      "{status, total, limit, offset, data: [...]}."))
            routes.append(_route("GET", f"/{low}/{{id}}", "Read", base, is_public, actors))
        elif act_type == "Update":
            routes.append(_route("PUT", f"/{low}/{{id}}", act_type, base, is_public, actors,
                                 request_fields=_creatable_fields(entity_specs.get(base))))
        elif act_type == "Delete":
            routes.append(_route("DELETE", f"/{low}/{{id}}", act_type, base, is_public, actors))
        elif act_type == "Execute":
            tag = info["tags"][0]
            routes.append(_route("POST", f"/workflow/{tag.lower()}/{target.lower()}",
                                 "Execute", target, is_public, actors))
    routes.sort(key=lambda r: (r["entity"], r["path"], r["method"]))

    # Identité visuelle déterministe (point 20 : stable par projet via
    # .monl_theme_seed) — transmise à l'IA frontend comme DIRECTION de
    # design, pas comme rendu : c'est elle qui écrit le HTML/CSS, monl
    # fournit palette/typos pour que deux apps ne se ressemblent jamais.
    theme_name, theme = generator._select_theme(seed=generator._load_or_create_theme_seed())
    design = {k: v for k, v in theme.items() if k != "keywords"}
    design["name"] = theme_name

    landing = normalized_ast.get("landing") or {}

    contract = {
        "monl_contract_version": CONTRACT_VERSION,
        "app": app_name,
        "brief": landing.get("brief"),
        # Contenu éditorial statique (point 55) : aucune entité, aucune route
        # ne peut le porter — c'est la seule matière du contrat qui ne soit
        # pas une donnée.
        "sections": landing.get("sections") or [],
        "design": design,
        "source_of_truth": "spec monl (.ml) — ne jamais modifier le backend à la main",
        "api": {
            # MÊME ORIGINE, jamais d'URL absolue : 'monl run' monte frontend/
            # sur /site du serveur qui sert déjà l'API (SERVE_WRAPPER, cli.py),
            # donc l'origine de la page EST celle de l'API. Une base absolue
            # codée en dur (ce champ valait "http://127.0.0.1:8000") casse dès
            # que le port change — 'monl run --port', et le port éphémère du
            # smoke test, qui rejetait alors le frontend pour avoir suivi le
            # contrat à la lettre (point 51 du journal).
            "base_url": "",
            "base_url_note": ("même origine que la page : appeler les routes "
                              "en chemins relatifs (/entite), jamais d'URL "
                              "absolue ni de port codé en dur"),
            "auth": {
                # AJOUT (bêta 3) : seuls les rôles marqués 'selfRegister' dans la
                # spec peuvent être choisis à l'inscription — les autres sont
                # provisionnés hors ligne (manage.py) et renvoient 403 ici.
                # L'interface ne doit donc proposer QUE cette liste.
                "register": {"method": "POST", "path": "/register",
                             "self_register_actors": list(generator.self_register_actors),
                             "body": {"username": "str", "password": "str (8+ caractères)",
                                      "actor": f"un rôle parmi {list(generator.self_register_actors)}"},
                             "note": ("403 si le rôle demandé n'est pas ouvert à l'inscription libre"
                                      if generator.self_register_actors else
                                      "aucun rôle ouvert : l'inscription est fermée, "
                                      "les comptes sont créés par manage.py")},
                "login": {"method": "POST", "path": "/login",
                          "body": {"username": "str", "password": "str"},
                          "returns": "un token JWT (validité 2 h par défaut, "
                                     "réglable par MONL_TOKEN_TTL_HOURS)"},
                "logout": {"method": "POST", "path": "/logout"},
                "header": "Authorization: Bearer <token> sur toute route non publique",
                "rate_limit": "5 tentatives / 60 s / IP sur /register et /login",
            },
        },
        "actors": sorted(generator.actors),
        "self_register_actors": list(generator.self_register_actors),
        "entities": entity_specs,
        "routes": routes,
        "frontend_rules": {
            "output_dir": "frontend/",
            "entry_point": "frontend/index.html",
            "served_at": "/site (par 'monl run', sans toucher app.py)",
            "forbidden": ["modifier app.py, schema.sql, sandbox_ai.py, landing.html, "
                          "dashboard.html ou la spec .ml",
                          "appeler des chemins d'API absents de 'routes'",
                          "envoyer un champ server_generated à la création"],
        },
    }
    return contract


def _route(method, path, action, entity, is_public, actors, request_fields=None, note=None):
    r = {"method": method, "path": path, "action": action, "entity": entity,
         "auth_required": not is_public, "allowed_actors": actors}
    if request_fields is not None:
        r["request_fields"] = request_fields
    if note:
        r["note"] = note
    return r


def _client_supplied_fks(generator, entity):
    """Colonnes de clé étrangère que le CLIENT doit envoyer à la création.

    Reproduit À L'IDENTIQUE ce que generator/schemas.py inscrit dans le
    schéma Pydantic — et s'appuie sur ses méthodes, jamais sur une logique
    parallèle. Le contrat les ignorait : il annonçait `POST /comment` avec le
    seul champ `content` alors que le backend exigeait aussi `article_id`,
    et tout frontend fidèle au contrat récoltait un 422 (point 57).

    Deux origines distinctes, même conséquence pour le client :
      - la cible d'un compteur (`increments`/`decrements`) : « j'apprécie CE
        post » est un choix de l'appelant, pas une propriété déduite ;
      - les parents autres que le propriétaire : le propriétaire se peuple
        depuis le JWT, le reste doit être dit (un commentaire et SON article).
    """
    if not hasattr(generator, "_get_incoming_relation"):
        return []
    colonnes = []
    owner = generator._get_incoming_relation(entity)
    if owner and any(r["target_entity"] == owner["source"]
                     for r in generator.reputation_rules_by_trigger.get(entity, [])):
        colonnes.append(owner["fk_column"])
    colonnes.extend(generator._client_fk_columns(entity))
    return colonnes


def _creatable_fields(entity_spec):
    if not entity_spec:
        return []
    return ([f["name"] for f in entity_spec["fields"] if not f["server_generated"]]
            + list(entity_spec.get("client_foreign_keys", [])))


def _render_prompt(contract):
    routes_lines = []
    for r in contract["routes"]:
        auth = "public" if not r["auth_required"] else f"JWT ({', '.join(r['allowed_actors'])})"
        # Le corps attendu n'apparaissait NULLE PART dans le brief : l'IA
        # devait le déduire de la liste des champs, sans jamais voir les
        # colonnes de rattachement (article_id d'un commentaire). Elle ne
        # pouvait pas les deviner, et le serveur répondait 422 (point 57).
        corps = (f" — corps : `{{{', '.join(r['request_fields'])}}}`"
                 if r.get("request_fields") else "")
        routes_lines.append(f"- `{r['method']} {r['path']}` — {r['action']} "
                            f"{r['entity']} — {auth}{corps}")
    entities_lines = []
    ROLE_LABELS = {"title": "TITRE — l'identifie d'un coup d'œil",
                   "media": "MÉDIA — l'image de l'enregistrement",
                   "description": "DESCRIPTION — le texte long",
                   "price": "PRIX", "category": "CATÉGORIE — bon pour un filtre",
                   "meta": "méta — information secondaire"}
    for ent, spec in contract["entities"].items():
        flags = []
        for f in spec["fields"]:
            marks = []
            if f.get("role"):
                marks.append(ROLE_LABELS[f["role"]])
            if f["required"]:
                marks.append("requis")
            if f["hidden_in_reads"]:
                marks.append("jamais renvoyé en lecture")
            if f["server_generated"]:
                marks.append("généré serveur — NE PAS envoyer")
            if f["categorized_in_reads"]:
                marks.append("lu comme libellé de catégorie")
            suffix = f" ({'; '.join(marks)})" if marks else ""
            flags.append(f"  - `{f['name']}: {f['type']}`{suffix}")
        forme = ARCHETYPE_GUIDANCE[spec["archetype"]]
        entities_lines.append(f"### {ent}\n_Forme conseillée : {forme}._\n"
                              + "\n".join(flags))

    brief_line = (f"\n**Brief produit :** {contract['brief']}\n" if contract.get("brief") else "")

    # Contenu éditorial (point 55). Écrit en toutes lettres que ce texte doit
    # être RENDU tel quel : c'est du contenu, pas une consigne de style, et
    # rien d'autre dans le contrat n'en fournit.
    sections_block = ""
    if contract.get("sections"):
        corps = "\n\n".join(f"### {s['title']}\n{s['body']}"
                            for s in contract["sections"])
        sections_block = (
            "\n## Contenu éditorial à publier tel quel\n"
            "Ces textes sont fournis par l'auteur du projet : ils doivent "
            "apparaître dans l'interface, chacun dans sa propre section, avec "
            "le titre donné. Ne pas les réécrire, ne pas les inventer ailleurs "
            "— aucune route d'API ne les sert, ils n'existent qu'ici.\n\n"
            + corps + "\n")
    design = contract["design"]
    design_block = (
        f"## Direction de design "
        + ("(IMPOSÉE par la spec — vérifiée au smoke test)\n"
           if design.get("pinned") else
           "(proposition déterministe, propre à ce projet)\n")
        + f"Système « {design['name']} » — fond `{design['bg']}`, surfaces `{design['surface']}`, "
        f"texte `{design['ink']}`, accents `{design['accent']}` / `{design['accent2']}`, "
        f"rayon `{design['radius']}`.\n"
        f"Typographies : titres {design['font_display']}, corps {design['font_body']}"
        # Ces piles ne contiennent QUE des familles déjà présentes sur les
        # machines : le brief ne peut plus proposer une police que sa propre
        # règle d'autonomie interdit de charger (point 52).
        + " — piles système, aucune police à télécharger : c'est le choix des "
          "familles et leur traitement (graisses, interlettrage, échelle) qui "
          "portent l'identité, pas un fichier distant"
        + ". Vous écrivez le HTML/CSS ; "
        + ("la spec ÉPINGLE ce thème : ces cinq couleurs doivent apparaître "
           "telles quelles dans votre CSS, le smoke test le vérifie.\n"
           if design.get("pinned") else
           "cette direction garantit une identité stable et distincte pour ce "
           "projet ; vous pouvez vous en écarter si votre parti pris sert mieux "
           "le sujet — l'écart est signalé, pas bloquant.\n")
        # Point 56 : sans ces tons, une interface n'a que cinq valeurs plates
        # et rend des aplats sans profondeur. Ils sont déduits de la palette,
        # donc justes sur un thème sombre comme sur un thème clair.
        + f"""
**Tons dérivés — la palette n'est pas plate.** Déduits des cinq couleurs
ci-dessus, à employer plutôt que d'improviser des gris :
- `{design['ink_soft']}` texte secondaire (légendes, méta, libellés)
- `{design['border']}` filets, séparateurs, contours de champs
- `{design['surface_alt']}` second niveau de surface (en-têtes, zones inertes)
- `{design['accent_soft']}` fond teinté (étiquettes, état sélectionné)
- `{design['accent_strong']}` survol et état actif de l'accent

Une interface sans texte atténué, sans filet et sans état de survol paraît
plate quelle que soit la qualité de sa palette. Ces cinq tons existent pour
qu'aucune de ces trois choses ne manque.
""")
    return f"""# Brief frontend — {contract['app']} (généré par monl)
{brief_line}
Vous êtes une IA spécialisée en interfaces. Générez le frontend de
l'application **{contract['app']}** en respectant STRICTEMENT le contrat
ci-dessous. Le backend existe déjà et ne doit pas être modifié.

{design_block}
## Règles non négociables
- Écrire tous les fichiers dans `frontend/`, avec `frontend/index.html`
  comme point d'entrée (HTML/CSS/JS statiques, aucun build requis).
- Frontend AUTONOME : aucune librairie CDN, aucun script externe — tout le
  JS/CSS vit dans `frontend/` (c'est ce qui rend le smoke test possible).
- N'appeler QUE les routes listées plus bas, en chemins RELATIFS —
  `fetch('/entite')`, JAMAIS `fetch('http://127.0.0.1:8000/entite')`. Le
  frontend est servi sur `/site` par le serveur qui porte l'API : l'origine
  est déjà la bonne. Une URL absolue avec un port codé en dur casse au
  premier `monl run --port` et fait échouer le smoke test.
- Authentification : `POST /register` (username, password 8+, actor parmi
  {contract['self_register_actors'] or "AUCUN — inscription fermée, ne pas "
   "construire de formulaire d'inscription"}), `POST /login` → token JWT, à
  envoyer ensuite en en-tête `Authorization: Bearer <token>` sur toute route
  non publique. Les rôles déclarés mais absents de cette liste
  ({[a for a in contract['actors'] if a not in contract['self_register_actors']] or "aucun"})
  sont provisionnés hors ligne : ils se connectent par `/login`, jamais par
  `/register`.
- Les routes de liste sont paginées : `?limit=&offset=`, réponse
  `{{status, total, limit, offset, data}}`.
- Ne jamais envoyer un champ marqué « généré serveur » à la création.
- Ne pas modifier `app.py`, `schema.sql`, la spec `.ml` ni les autres
  artefacts monl.

{sections_block}
## Entités
{chr(10).join(entities_lines)}

## Routes disponibles
{chr(10).join(routes_lines)}

## Contrat machine-lisible complet
Le fichier `frontend_contract.json` (même dossier) contient la version
exhaustive de ce contrat — s'y référer en cas de doute.

---

## Vous lisez ceci dans une conversation (claude.ai, sans clé API) ?
Générez le frontend demandé, puis rendez-le sous une forme téléchargeable :
soit un fichier ZIP contenant les fichiers (index.html à la racine ou dans
un unique sous-dossier), soit un `index.html` AUTONOME (CSS et JS inclus
dans le fichier). L'utilisateur l'installera ensuite avec :
`monl import <fichier téléchargé> <dossier du projet>` — monl
re-vérifiera automatiquement l'ensemble (cohérence + smoke test) et, en cas
d'erreurs, elles vous seront recollées ici pour correction.
"""


PROJECT_CLAUDE_MD_MARKER = "<!-- généré par monl — orchestration frontend -->"

PROJECT_CLAUDE_MD = """{marker}
# {app} — mémoire de projet pour Claude Code

Ce dossier est un projet monl : le backend (app.py, schema.sql,
sandbox_ai.py) est GÉNÉRÉ depuis la spec `spec.ml` (ou le fichier .ml
présent) — la spec est la source de vérité, le backend un artefact scellé.

## Ton rôle ici : le FRONTEND, rien d'autre

- Lis `FRONTEND_PROMPT.md` : c'est le contrat complet (routes, auth,
  champs, direction de design). Version machine-lisible :
  `frontend_contract.json`.
- Écris UNIQUEMENT dans `frontend/`, point d'entrée `frontend/index.html`.
  HTML/CSS/JS statiques, AUTONOMES (aucun CDN, aucun script externe —
  condition de vérifiabilité du smoke test).
- Pour faire ÉVOLUER un frontend existant après un changement de spec,
  lis `FRONTEND_UPDATE_PROMPT.md` (généré par `monl update`) et modifie
  l'existant, ne réécris pas de zéro.

## Interdits absolus

Ne JAMAIS modifier : la spec `.ml`, `app.py`, `schema.sql`,
`sandbox_ai.py`, `frontend_contract.json`, `FRONTEND_PROMPT.md`,
`monl.json`, `.jwt_secret`. Si le backend semble devoir changer, c'est
la SPEC qu'il faut faire évoluer (par l'utilisateur), puis `monl update`.

## Vérifier ton travail

`monl run . --check` (si `monl` est sur le PATH) exécute la
vérification complète : cohérence statique + smoke test comportemental
(serveur éphémère, routes du contrat éprouvées en HTTP réel, ton
`index.html` exécuté dans jsdom). Corrige jusqu'à ce que ce soit vert —
`monl run .` refusera de lancer tant que le smoke test échoue.
"""


def write_project_claude_md(app_name, output_dir):
    """Écrit le CLAUDE.md du PROJET (pas celui du dépôt monl) — c'est lui
    qui cadre une session 'cd projet && claude'. Jamais écrasé s'il a été
    repris en main par l'utilisateur (absence du marqueur)."""
    path = os.path.join(output_dir, "CLAUDE.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            if PROJECT_CLAUDE_MD_MARKER not in fh.read():
                return  # CLAUDE.md personnel de l'utilisateur : intouchable
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(PROJECT_CLAUDE_MD.format(marker=PROJECT_CLAUDE_MD_MARKER, app=app_name))


def generate_frontend_contract(normalized_ast, generator, output_dir):
    """Écrit frontend_contract.json + FRONTEND_PROMPT.md ; retourne le contrat."""
    contract = build_contract(normalized_ast, generator)
    contract_path = os.path.join(output_dir, CONTRACT_FILENAME)
    with open(contract_path, "w", encoding="utf-8") as fh:
        json.dump(contract, fh, ensure_ascii=False, indent=2, sort_keys=True)
    with open(os.path.join(output_dir, PROMPT_FILENAME), "w", encoding="utf-8") as fh:
        fh.write(_render_prompt(contract))
    write_project_claude_md(contract["app"], output_dir)
    return contract


def contract_sha256(output_dir):
    path = os.path.join(output_dir, CONTRACT_FILENAME)
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()
