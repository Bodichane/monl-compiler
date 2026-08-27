"""L'assemblage du contrat.

Chaque section vit dans son module ; `build_contract` les appelle dans
l'ordre et scelle le résultat. Toute brique qui ajoute une promesse au
contrat doit se demander si `_contract_signature` (cli/signature.py) la
voit — six fois la réponse a été non."""

from ..design_skills import select_design_skills
from ..ir import CompilationIR
from . import champs, contrat_auth, contrat_entites, contrat_paiement, contrat_routes, fondations


def _contenu_et_regles(devise, entity_specs, normalized_ast, plans, prestataire, public_conditions, routes):
    """Contenu éditorial, messages et règles métier annoncés au frontend."""
    routes.sort(key=lambda r: (r["entity"], r["path"], r["method"]))

    # POINT 72 : plus AUCUNE identité visuelle calculée. Le contrat décrit ce
    # que monl sait — structure, rôles, routes, contenu, intention déclarée —
    # et rien de ce qu'il devinait : ni palette, ni typographies, ni rayon.
    # La direction de design remonte du dialogue, par le brief.
    landing = normalized_ast.get("landing") or {}

    design_skills = select_design_skills(entity_specs, routes)
    message_contracts = [
        {
            "trigger": f"{rule['trigger_entity']}.{rule['trigger_action']}",
            "recipient": "le compte authentifié, via son identifiant email",
            "subject": rule["subject"],
            "body": fondations.paragraphes(rule["body"]),
            "delivery": "tentative asynchrone après commit, sans retry ni garantie de remise",
            "note": ("Après le succès de la création, informer l'utilisateur "
                     "qu'une tentative de message a été lancée. Ne pas "
                     "promettre la remise ; les échecs sont journalisés "
                     "côté serveur."),
        }
        for rule in sorted(
            plans.message_rules_by_trigger.values(),
            key=lambda item: (item["trigger_entity"], item["trigger_action"]))
    ]
    business_rules = {
        "public_when": {
            f"{entity}.{action}": dict(condition)
            for (entity, action), condition in sorted(public_conditions.items())
        },
        "once_per": list(plans.once_per_rules),
    }
    if message_contracts:
        business_rules["messages"] = message_contracts
    # BRIQUE 2a : la devise n'est déclarée QUE s'il y a quelque chose à
    # encaisser. Une spec sans `payable` n'ajoute donc aucune clé, et son
    # contrat reste identique à l'octet — condition pour qu'une brique nouvelle
    # ne réécrive pas les projets qui ne s'en servent pas.
    if plans.payable_by_entity:
        business_rules["payment"] = {
            "provider": prestataire,
            "currency": devise["code"],
            # L'exposant est DONNÉ, pas laissé à déduire : c'est lui qui dit si
            # `montant_centimes` se divise par cent ou pas, et une interface
            # qui devrait connaître la liste des devises sans sous-unité
            # finirait par se tromper sur la moins courante.
            "minor_unit_exponent": devise["exponent"],
        }
    return business_rules, design_skills, landing

def build_contract(normalized_ast: CompilationIR, plans_or_generator):
    """Construit le contrat depuis l'IR et les analyses communes.

    La voie de production transmet ``CompilationPlans``. L'acceptation d'un
    générateur reste volontairement conservée pour les intégrations Python
    historiques ; elle ne fait que construire l'objet de plans une fois.
    """
    plans = fondations._coerce_plans(plans_or_generator)
    app_name = normalized_ast["meta"]["appName"]
    entities = normalized_ast["schema"]["entities"]
    # POINT 91 : la liste des 'rule X.y required' ne sert PLUS à peupler le
    # `required` du contrat — les schémas générés rendent tout champ d'entrée
    # obligatoire, déclaré ou non, et le contrat doit dire ce que le serveur
    # exige. Elle n'est donc plus lue ici : la garder pour « information »
    # rouvrirait la porte à ce qu'on vient de fermer, deux sources pour une
    # même question.
    fk_placements = plans.foreign_key_placements

    # Calculés AVANT les entités : l'archétype dépend de qui peut lire, pas
    # seulement des champs (voir _archetype). Même source de vérité que la
    # génération FastAPI — _compute_route_map, jamais une logique parallèle.
    route_map = plans.route_map
    public_conditions = plans.public_conditions
    lisibles = {plan.base_target for (act, _t), plan in route_map.items()
                if act == "Read"}

    entity_specs = contrat_entites._specs_des_entites(entities, fk_placements, lisibles, plans)

    routes = contrat_routes._routes_du_contrat(entity_specs, plans, route_map)

    devise, payables, prestataire = contrat_paiement._paiement_du_contrat(plans, routes)

    auth_features = contrat_auth._fonctions_dauth(plans, routes)

    business_rules, design_skills, landing = _contenu_et_regles(devise, entity_specs, normalized_ast, plans, prestataire, public_conditions, routes)
    auth_contract, b4_contract = contrat_auth._auth_du_contrat(auth_features, plans)
    contract = {
        # Une spec sans B4 conserve la version et la forme historiques à
        # l'octet ; une spec B4 rend son delta visible au frontend.
        "monl_contract_version": fondations.CONTRACT_VERSION + (1 if b4_contract else 0),
        "app": app_name,
        "brief": landing.get("brief"),
        "design_skills": design_skills,
        # Contenu éditorial statique (point 55) : aucune entité, aucune route
        # ne peut le porter — c'est la seule matière du contrat qui ne soit
        # pas une donnée.
        "sections": [{"title": s["title"], "body": fondations.paragraphes(s["body"])}
                     for s in (landing.get("sections") or [])],
        # POINT 94 : la FAQ est une LISTE, et le contrat doit le dire. Rendue
        # comme une section, elle redevient le pavé de prose qu'elle était —
        # l'interface ne peut pas deviner une structure qu'on ne lui donne pas.
        "faq": [{"question": q["question"], "answer": fondations.paragraphes(q["answer"])}
                for q in (landing.get("faq") or [])],
        # BRIQUE 30 : les adresses SORTANTES, dans l'ordre déclaré. Le contrat
        # les porte parce que le pied de page est une promesse d'interface au
        # même titre qu'une route : une IA qui ne les voit pas dessine un pied
        # de page vide, et c'est très exactement ce qu'on répare.
        "links": [{"label": lien["label"], "url": lien["url"]}
                  for lien in (landing.get("links") or [])],
        "source_of_truth": "spec monl (.ml) — ne jamais modifier le backend à la main",
        # AJOUT (brique 13, point 83) : les assets FOURNIS PAR L'HUMAIN. Le
        # contrat n'en disait rien, donc une IA d'interface ne pouvait pas savoir
        # qu'un logo existait — l'en-tête de la boutique de démonstration était
        # un simple mot en texte, faute de mieux. Chaque fichier nommé ici a été
        # vérifié présent à la compilation : l'IA peut s'y référer sans risque.
        "assets": champs._assets_contract(plans.assets or {}),
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
            "auth": auth_contract,
        },
        "actors": sorted(plans.actors),
        "self_register_actors": list(plans.self_register_actors),
        # Règles métier qui ne se réduisent pas à un simple CRUD : le contrat
        # frontend doit savoir qu'un contenu public est filtré par son statut
        # et qu'un compte ne peut créer qu'une occurrence par combinaison de
        # cibles (like/vote, par exemple).
        "business_rules": business_rules,
        "entities": entity_specs,
        "routes": routes,
        "frontend_rules": {
            "output_dir": "frontend/",
            "entry_point": "frontend/index.html",
            "served_at": "/site (par 'monl run', sans toucher app.py)",
            "forbidden": ["modifier app.py, schema.sql, sandbox_ai.py, landing.html, "
                          "dashboard.html ou la spec .ml",
                          "appeler des chemins d'API absents de 'routes'",
                          "envoyer un champ server_generated à la création"]
                         + (["appeler POST /paiement/webhook : c'est la route "
                             "du prestataire de paiement, elle exige une "
                             "signature et refusera toute requête du navigateur"]
                            if payables else []),
        },
    }
    return contract
