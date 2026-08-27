"""Les routes annoncées au frontend.

Même regroupement que la génération FastAPI réelle — `_compute_route_map` est
la source unique, partagée (voir generator/core.py). Un test confronte le
contrat aux décorateurs réellement écrits dans app.py."""

from . import champs, notes_de_contrat


def _routes_du_contrat(entity_specs, plans, route_map):
    """Les routes — CRUD depuis le MÊME regroupement que la génération FastAPI
    (`_compute_route_map`, jamais une logique parallèle), puis les routes de
    téléversement, qui ne sortent d'aucun workflow."""
    # Routes — mêmes clés de regroupement que la génération FastAPI réelle
    # (route_map et public sont calculés plus haut, pour les archétypes).
    routes = []
    for (act_type, target), plan in route_map.items():
        base = plan.base_target
        low = base.lower()
        access = plans.access_policies[(base, act_type)]
        is_public = access.public
        actors = sorted(access.actors)
        if act_type == "Create":
            # POINT 90 : sans cette note, une IA d'interface bâtit un tunnel
            # d'achat qui bute en 409 au tout dernier écran — le seul endroit où
            # l'utilisateur a déjà tout rempli. La contrainte doit se voir AVANT,
            # pas se découvrir à la fin.
            requise = plans.required_profiles.get(base)
            note_create = (
                f"PRÉALABLE : l'appelant doit déjà posséder un {requise}. Sinon "
                f"cette route répond 409 sans rien créer. Vérifier au chargement "
                f"(GET /{requise.lower()} renvoie les siens) et proposer la "
                f"création de la fiche AVANT le formulaire, pas après."
                if requise else None)
            # POINT 91 : la création AUSSI est verrouillée — mais seulement par
            # un PARENT réglé, jamais par l'entité elle-même : rien n'empêche
            # d'ouvrir une commande de plus, c'est y AJOUTER une ligne qui
            # remonterait le total déjà encaissé. D'où `inclure_soi=False`.
            # Le contrat le taisait alors que le backend refusait déjà : une IA
            # fidèle dessinait un « + Ajouter un article » sur une commande
            # payée (vérifié sur `exemples/02_boutique.ml`).
            verrou_parent = notes_de_contrat._verrou_paiement(plans, base, inclure_soi=False)
            message = plans.message_rules_by_trigger.get(base)
            routes.append(champs._route("POST", f"/{low}", act_type, base, is_public, actors,
                                 request_fields=champs._creatable_fields(entity_specs.get(base)),
                                 note=notes_de_contrat._joindre(note_create,
                                               notes_de_contrat._note_verrou(verrou_parent, creation=True),
                                               notes_de_contrat._note_message(message))))
            if requise:
                routes[-1]["requires_own"] = requise
            if verrou_parent:
                routes[-1]["payment_locked"] = verrou_parent
        elif act_type == "Read":
            # AJOUT (brique 23, point 106) : un rôle superviseur (declare via
            # 'sharedBy' sur la meme reference que 'accessibleBy') transperce
            # le controle par colonnes. Sans cette note, une IA d'interface
            # appliquerait le filtre de parties au moderateur lui-meme et lui
            # taillerait une vue vide — alors que le backend lui montre tout.
            _sup_lecture = sorted(access.supervisors)
            _note_lecture = notes_de_contrat._note_superviseurs(_sup_lecture, "lecture")
            list_query = champs._list_query_contract(plans, base)
            routes.append(champs._route(
                "GET", f"/{low}", "List", base, is_public, actors,
                note=notes_de_contrat._joindre(
                    "Paramètres : limit (max 200), offset. Réponse : "
                    "{status, total, limit, offset, data: [...]}.",
                    notes_de_contrat._note_list_query(list_query), _note_lecture)))
            if list_query:
                routes[-1]["list_query"] = list_query
            routes.append(champs._route("GET", f"/{low}/{{id}}", "Read", base, is_public, actors,
                                 note=_note_lecture))
            if _sup_lecture:
                routes[-1]["supervisors"] = _sup_lecture
                routes[-2]["supervisors"] = _sup_lecture
        elif act_type == "Update":
            # AJOUT (point 81) : le schéma Pydantic est UNIQUE par entité, donc
            # ces clés étrangères doivent être envoyées (sinon 422) -- mais la
            # route Update de monl ne les écrit pas : un rattachement se fixe à
            # la création. Sans cette note, le contrat laissait croire qu'une
            # interface pouvait déplacer une ligne d'un panier à l'autre, ce que
            # le backend accepte (200) sans rien changer. Même exigence que les
            # points 76 et 79 : le contrat décrit ce que le backend FAIT.
            liens = list(entity_specs.get(base, {}).get("client_foreign_keys", []))
            note_liens = None
            if liens:
                accord = ("doivent figurer dans le corps (schéma unique par entité) mais ne "
                          "sont PAS modifiés" if len(liens) > 1 else
                          "doit figurer dans le corps (schéma unique par entité) mais n'est "
                          "PAS modifié")
                note_liens = (
                    f"{', '.join(liens)} {accord} : un rattachement se fixe à la création. "
                    f"Ne pas proposer de le changer — renvoyer la valeur actuelle.")
            # POINT 91 : quatrième forme de l'angle mort des points 88 à 90. Une
            # route ne change ni de chemin, ni d'acteurs, ni de champs, et gagne
            # pourtant un refus : dès l'encaissement, elle répond 409. Sans cette
            # note, une interface fidèle au contrat dessine un bouton « Modifier »
            # sur une commande payée — et l'utilisateur découvre le refus après
            # avoir rempli le formulaire.
            verrou = notes_de_contrat._verrou_paiement(plans, base)
            # POINT 98 : la valeur qui LIBÈRE, et l'aller sans retour. Sans
            # cette note, une interface propose « repasser en préparation » sur
            # une commande annulée et découvre un 409 au clic.
            liberation = (plans.release_rules_by_entity.get(base) or [None])[0]
            routes.append(champs._route("PUT", f"/{low}/{{id}}", act_type, base, is_public, actors,
                                 note=notes_de_contrat._joindre(note_liens, notes_de_contrat._note_verrou(verrou),
                                               notes_de_contrat._note_liberation(liberation)),
                                 request_fields=champs._creatable_fields(entity_specs.get(base))))
            if verrou:
                routes[-1]["payment_locked"] = verrou
            if liberation:
                routes[-1]["releases_on"] = {
                    "field": liberation["field"], "value": liberation["value"],
                    "releases": liberation["releases"], "terminal": True}
        elif act_type == "Delete":
            verrou = notes_de_contrat._verrou_paiement(plans, base)
            # AJOUT (brique 23, point 106) : voir le bloc Read — un superviseur
            # de la suppression voit/supprime tous les enregistrements.
            _sup_delete = sorted(access.supervisors)
            routes.append(champs._route("DELETE", f"/{low}/{{id}}", act_type, base, is_public,
                                 actors,
                                 note=notes_de_contrat._joindre(notes_de_contrat._note_verrou(verrou),
                                               notes_de_contrat._note_superviseurs(_sup_delete, "suppression"))))
            if _sup_delete:
                routes[-1]["supervisors"] = _sup_delete
            if verrou:
                routes[-1]["payment_locked"] = verrou
        elif act_type == "Execute":
            tag = plan.tags[0]
            routes.append(champs._route("POST", f"/workflow/{tag.lower()}/{target.lower()}",
                                 "Execute", target, is_public, actors))

    # BRIQUE B1 : ces routes ne sont pas des CRUD JSON. Elles sont produites
    # par une déclaration Upload et doivent donc être décrites séparément dans
    # le contrat : nom multipart, limite explicite, types réellement reconnus,
    # dépôt POST et lecture GET privée.
    for upload in plans.upload_fields:
        entite = upload["entity"]
        champ = upload["field"]
        chemin = f"/{entite.lower()}/{{id}}/{champ}"
        for action, method, contract_action, note in (
                ("Update", "POST", "Upload", (
                    f"multipart/form-data obligatoire, champ de fichier '{champ}'. "
                    f"Limite exacte : {upload['max_bytes']} octets. Types acceptés "
                    f"par signature d'octets : {', '.join(upload['accepted_types'])}. "
                    "Le nom de fichier et le Content-Type déclarés par le client "
                    "sont ignorés ; le dépôt remplace l'ancien fichier après "
                    "validation.")),
                ("Read", "GET", "Download", (
                    "réponse octet/octet en téléchargement avec Content-Type "
                    "application/octet-stream et nosniff ; l'ACL de la ligne "
                    "s'applique aussi au fichier, un chemin connu ne suffit pas.")),
        ):
            access = plans.access_policies[(entite, action)]
            route = champs._route(method, chemin, contract_action, entite, False,
                           sorted(access.actors), note=note)
            route["upload"] = {
                "field_name": champ,
                "max_bytes": upload["max_bytes"],
                "accepted_types": list(upload["accepted_types"]),
                "storage": "server_disk_reference",
            }
            routes.append(route)
    return routes
