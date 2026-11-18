"""Assembling the contract.

Each section lives in its own module; `build_contract` calls them in order
and seals the result. Every brick that adds a promise to the contract must
ask whether `_contract_signature` (cli/signature.py) sees it — six times
the answer was no."""

from ..design_skills import select_design_skills
from ..ir import CompilationIR
from . import champs, contrat_auth, contrat_entites, contrat_paiement, contrat_routes, fondations


def _contenu_et_regles(devise, entity_specs, normalized_ast, plans, prestataire, public_conditions, routes):
    """Editorial content, messages and business rules announced to the
    frontend."""
    routes.sort(key=lambda r: (r["entity"], r["path"], r["method"]))

    # POINT 72: NO computed visual identity anymore. The contract describes
    # what monl knows — structure, roles, routes, content, declared intent —
    # and nothing of what it used to guess: neither palette, nor typefaces, nor
    # radius. The design direction comes up from the dialogue, through the
    # brief.
    landing = normalized_ast.get("landing") or {}

    design_skills = select_design_skills(entity_specs, routes)
    message_contracts = [
        {
            "trigger": f"{rule['trigger_entity']}.{rule['trigger_action']}",
            "recipient": "the authenticated account, through its email identifier",
            "subject": rule["subject"],
            "body": fondations.paragraphes(rule["body"]),
            "delivery": "asynchronous attempt after commit, with no retry and no delivery guarantee",
            "note": ("After the creation succeeds, tell the user that a "
                     "message attempt was started. Do not promise delivery; "
                     "failures are logged server-side."),
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
    # BRICK 2a: the currency is declared ONLY if there is something to charge.
    # A spec without `payable` therefore adds no key, and its contract stays
    # byte-identical — the condition for a new brick not to rewrite the
    # projects that do not use it.
    if plans.payable_by_entity:
        business_rules["payment"] = {
            "provider": prestataire,
            "currency": devise["code"],
            # The exponent is GIVEN, not left to deduce: it is what says
            # whether `montant_centimes` is divided by a hundred or not, and an
            # interface that had to know the list of currencies without a
            # subunit would end up wrong on the least common one.
            "minor_unit_exponent": devise["exponent"],
        }
    return business_rules, design_skills, landing

def build_contract(normalized_ast: CompilationIR, plans_or_generator):
    """Builds the contract from the IR and the shared analyses.

    The production path passes ``CompilationPlans``. Accepting a generator is
    deliberately kept for historical Python integrations; it only builds the
    plans object once."""
    plans = fondations._coerce_plans(plans_or_generator)
    app_name = normalized_ast["meta"]["appName"]
    entities = normalized_ast["schema"]["entities"]
    # POINT 91: the list of 'rule X.y required' NO LONGER fills the contract's
    # `required` — the generated schemas make every input field mandatory,
    # declared or not, and the contract must say what the server requires. It
    # is therefore no longer read here: keeping it "for information" would
    # reopen the door just closed, two sources for one question.
    fk_placements = plans.foreign_key_placements

    # Computed BEFORE the entities: the archetype depends on who can read, not
    # only on the fields (see _archetype). Same source of truth as FastAPI
    # generation — _compute_route_map, never parallel logic.
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
        # A spec without B4 keeps the historical version and shape byte for
        # byte; a B4 spec makes its delta visible to the frontend.
        "monl_contract_version": fondations.CONTRACT_VERSION + (1 if b4_contract else 0),
        "app": app_name,
        "brief": landing.get("brief"),
        "design_skills": design_skills,
        # Static editorial content (point 55): no entity, no route can carry it
        # — it is the only material in the contract that is not data.
        "sections": [{"title": s["title"], "body": fondations.paragraphes(s["body"])}
                     for s in (landing.get("sections") or [])],
        # POINT 94: the FAQ is a LIST, and the contract must say so. Rendered
        # as a section, it becomes the block of prose it used to be again — the
        # interface cannot guess a structure it is not given.
        "faq": [{"question": q["question"], "answer": fondations.paragraphes(q["answer"])}
                for q in (landing.get("faq") or [])],
        # BRICK 30: the OUTGOING addresses, in declared order. The contract
        # carries them because the footer is an interface promise just like a
        # route: an AI that does not see them draws an empty footer, and that
        # is exactly what is being fixed.
        "links": [{"label": lien["label"], "url": lien["url"]}
                  for lien in (landing.get("links") or [])],
        "source_of_truth": "monl spec (.ml) — never modify the backend by hand",
        # ADDED (brick 13, point 83): the assets SUPPLIED BY THE HUMAN. The
        # contract said nothing about them, so an interface AI could not know a
        # logo existed — the demo shop's header was a plain word of text, for
        # lack of anything better. Every file named here was checked present at
        # compile time: the AI can refer to it safely.
        "assets": champs._assets_contract(plans.assets or {}),
        "api": {
            # SAME ORIGIN, never an absolute URL: 'monl run' mounts frontend/
            # on /site of the server that already serves the API
            # (SERVE_WRAPPER, cli.py), so the page's origin IS the API's. A
            # hard-coded absolute base (this field used to be
            # "http://127.0.0.1:8000") breaks as soon as the port changes —
            # 'monl run --port', and the smoke test's ephemeral port, which
            # then rejected the frontend for following the contract to the
            # letter (point 51 of the journal).
            "base_url": "",
            "base_url_note": ("same origin as the page: call the routes with "
                              "relative paths (/entity), never an absolute "
                              "URL or a hard-coded port"),
            "auth": auth_contract,
        },
        "actors": sorted(plans.actors),
        "self_register_actors": list(plans.self_register_actors),
        # Business rules that do not reduce to plain CRUD: the frontend
        # contract must know that public content is filtered by its status and
        # that an account can create only one occurrence per combination of
        # targets (like or vote, for example).
        "business_rules": business_rules,
        "entities": entity_specs,
        "routes": routes,
        "frontend_rules": {
            "output_dir": "frontend/",
            "entry_point": "frontend/index.html",
            "served_at": "/site (by 'monl run', without touching app.py)",
            "forbidden": ["modify app.py, schema.sql, sandbox_ai.py, landing.html, "
                          "dashboard.html or the .ml spec",
                          "call API paths absent from 'routes'",
                          "send a server_generated field on creation"]
                         + (["call POST /paiement/webhook: it is the payment "
                             "provider's route, it requires a signature and "
                             "will refuse any request from the browser"]
                            if payables else []),
        },
    }
    return contract
