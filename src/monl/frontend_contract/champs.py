"""Ce qu'une route accepte, et ce que le client a le droit d'écrire.

Tout champ peuplé par le SERVEUR sort des `request_fields` via
`server_generated` (points 76 et 79) : le contrat décrit ce que le backend
fait vraiment, pas seulement ce que la spec déclare."""

from ..ir import CompilationPlans


def _route(method, path, action, entity, is_public, actors, request_fields=None, note=None):
    r = {"method": method, "path": path, "action": action, "entity": entity,
         "auth_required": not is_public, "allowed_actors": actors}
    if request_fields is not None:
        r["request_fields"] = request_fields
    if note:
        r["note"] = note
    return r

def _list_query_contract(plans: CompilationPlans, entity):
    """Contrat explicite des capacités de liste déclarées pour une entité."""
    model = plans.entity_models[entity]
    filters = []
    for field in plans.filterable_fields.get(entity, ()):
        policy = model.fields[field]
        values = list(policy.allowed_values) if policy.allowed_values else None
        if policy.type == "Boolean":
            values = ["true", "false"]
        filters.append({
            "field": field,
            "parameter": field,
            "kind": "exact",
            "allowed_values": values,
        })
    sort_fields = list(plans.sortable_fields.get(entity, ()))
    result = {}
    if filters:
        result["filters"] = filters
    if sort_fields:
        result["sort"] = {
            "parameter": "sort",
            "direction_parameter": "direction",
            "fields": sort_fields,
            "directions": ["asc", "desc"],
        }
    return result

def _client_supplied_fks(plans: CompilationPlans, entity):
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
    colonnes = []
    owner = plans.incoming_relations.get(entity)
    owners = {
        r["target_entity"] for r in plans.reputation_rules_by_trigger.get(entity, ())
    }
    if owner and owner["source"] in owners:
        colonnes.append(owner["fk_column"])
    colonnes.extend(plans.client_foreign_keys.get(entity, ()))
    return colonnes

def _creatable_fields(entity_spec):
    if not entity_spec:
        return []
    return ([f["name"] for f in entity_spec["fields"]
             if not f["server_generated"] and not f.get("postpayment_only")
             and not f.get("upload")]
            + list(entity_spec.get("client_foreign_keys", [])))

def _assets_contract(assets):
    """Section 'assets' du contrat : où sont les fichiers de l'humain, et
    lesquels sont déclarés. `served_at` dit l'URL réelle, pas le chemin disque —
    c'est celle-là que le navigateur demandera."""
    dossier = assets.get("dir") or "assets"
    contrat = {
        "dir": dossier,
        "served_at": f"/site/{dossier}/",
        "note": (f"Fichiers fournis par l'humain (photos, logo). Les référencer en chemin "
                 f"RELATIF depuis la page : '{dossier}/…'. Ne jamais les modifier ni les "
                 f"déplacer : ils ne sont pas produits par l'IA, et ce dossier vit HORS de "
                 f"frontend/ pour survivre à une reconstruction du frontend."),
    }
    for cle in ("logo", "favicon"):
        if assets.get(cle):
            contrat[cle] = f"{dossier}/{assets[cle]}"
    if "logo" in contrat:
        contrat["logo_note"] = ("Un vrai logo est fourni : l'utiliser dans l'en-tête plutôt "
                                "qu'un mot-symbole en texte.")
    return contrat
