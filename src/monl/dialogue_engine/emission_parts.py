"""Morceaux nommés de l'émission déterministe d'une spec."""

from .fondations import SEEDABLE_TYPES


def spec_header(app_name, description, image_topic):
    """Émet l'en-tête et son commentaire documentaire."""
    lines = [f"app {app_name}", "",
             "# Spécification générée par le dialogue guidé monl (déterministe, sans IA).",
             f"# Brief du projet : {description}"]
    if image_topic:
        lines.append(f"# Sujet des illustrations : {image_topic}")
    lines.append("")
    return lines


def emit_structure(lines, entities, relations, actors, self_register):
    """Émet entités, relations et acteurs dans l'ordre de la spec."""
    for ent, fields in entities.items():
        lines.append(f"entity {ent}")
        for fname, ftype in fields:
            lines.append(f"    {fname}: {ftype}")
        lines.append("")
    for src, rtype, tgt in relations:
        lines.append(f"relation {src} {rtype} {tgt}")
    if relations:
        lines.append("")
    for act in actors:
        lines.append(f"actor {act} selfRegister" if act == self_register
                     else f"actor {act}")
    lines.append("")


def emit_capability(lines, account_identifier):
    """Émet l'identifiant seulement si l'utilisateur l'a choisi."""
    if not account_identifier:
        return
    lines.append("# La FORME de l'identifiant de compte est vérifiée ET normalisée :")
    lines.append("# sans forme canonique, une majuscule de plus fait un second compte.")
    lines.append("capability auth")
    lines.append(f"    identifier: {', '.join(account_identifier['formes'])}")
    if account_identifier.get("prefixe"):
        lines.append(f'    phone_prefix: "{account_identifier["prefixe"]}"')
    lines.append("")


def calculated_server_fields(emitter, payable):
    """Retourne les champs que le serveur calcule au lieu de les requérir."""
    calculated = set()
    if payable:
        line_entity = payable.get("line_entity") or payable["entity"]
        calculated.add((payable["entity"], payable["field"]))
        field = (emitter.CHAMP_SOUS_TOTAL if payable.get("line_entity")
                 else payable["field"])
        calculated.add((line_entity, field))
    return calculated


def public_when_entities(extra_rules):
    return {
        rule.split()[1].split(".", 1)[0]
        for rule in extra_rules
        if rule.startswith("rule ") and " publicWhen " in rule
    }


def emit_ownership_rules(lines, public_read, owned):
    for ent, owner in owned.items():
        if ent not in public_read:
            lines.append(f"rule {ent}.Read ownedBy {owner}")
        lines.append(f"rule {ent}.Update ownedBy {owner}")
        lines.append(f"rule {ent}.Delete ownedBy {owner}")


def emit_shared_rules(lines, entities, managers):
    for ent in entities:
        if len(managers[ent]) <= 1:
            continue
        shared_list = ", ".join(managers[ent])
        for action in ("Create", "Update", "Delete"):
            lines.append(f"rule {ent}.{action} sharedBy {shared_list}")


def emit_base_rules(lines, entities, extra_rules, public_read,
                    public_create, owned, managers, calculated):
    """Émet les règles communes avant les capacités avancées."""
    for ent, fields in entities.items():
        first_field = fields[0][0]
        if (ent, first_field) not in calculated:
            lines.append(f"rule {ent}.{first_field} required")
    public_when = public_when_entities(extra_rules)
    for ent in public_read:
        if ent not in public_when:
            lines.append(f"rule {ent}.Read public")
    for ent in public_create:
        lines.append(f"rule {ent}.Create public")
    emit_ownership_rules(lines, public_read, owned)
    emit_shared_rules(lines, entities, managers)


def emit_payment_header(lines, entite):
    lines.extend([
        "",
        "# POINT 89 : la date d'arrivée, écrite par le serveur à la",
        "# création et jamais ensuite. Elle disparaît des corps de",
        "# requête : une date qu'on se donne à soi-même n'atteste de",
        f"# rien, et un carnet de {entite} où chacun choisit ses dates",
        "# ne dit plus dans quel ordre honorer.",
    ])


def emit_stock_rule(lines, payable, source, porteur, facteur):
    stock = payable.get("stock_field")
    if not stock:
        return
    lines.extend([
        "# POINT 85 : ce plancher n'est pas décoratif — c'est lui qui",
        "# arme la vérification de disponibilité ci-dessous. Sans lui,",
        "# le décompte passerait sous zéro et le stock mentirait.",
        f"rule {source}.{stock} min 0",
        "",
        "# POINT 86 : le stock suit les commandes, et retire CE QUE LE",
        "# CLIENT A DEMANDÉ — pas une constante. Commander plus que le",
        "# stock disponible répond 409, sans rien décompter.",
        f"rule {porteur}.Create decrements {source}.{stock} by {facteur}",
        "",
    ])


def emit_payable(emitter, lines, payable):
    """Émet les règles de calcul, de stock et d'encaissement."""
    if not payable:
        return
    entite, montant = payable["entity"], payable["field"]
    source, prix = payable["source_entity"], payable["source_field"]
    facteur = payable["factor"]
    ligne = payable.get("line_entity")
    porteur = ligne or entite
    calcule = (payable.get("line_subtotal", emitter.CHAMP_SOUS_TOTAL)
               if ligne else montant)
    emit_payment_header(lines, entite)
    lines.append(f"rule {entite}.{emitter.CHAMP_DATE} timestamp")
    lines.append("")
    if not ligne:
        lines.extend([
            "# La quantité est le seul chiffre que l'acheteur fournit,",
            "# et elle est obligatoire : sans elle le calcul ci-dessous",
            "# porterait sur du vide.",
            f"rule {entite}.{facteur} required",
            "",
        ])
    lines.extend([
        "# POINT 79 : le montant est CALCULÉ PAR LE SERVEUR — prix au",
        f"# catalogue ({source}.{prix}) multiplié par la quantité. Le",
        f"# champ {porteur}.{calcule} disparaît donc des corps de requête,",
        "# à la création comme à la modification. Sans ce calcul,",
        "# l'acheteur fixerait lui-même ce qu'il règle : il devient",
        "# propriétaire de ce qu'il crée, donc le payeur.",
        f"rule {porteur}.{calcule} derivedFrom {source}.{prix} by {facteur}",
        "",
    ])
    if ligne:
        lines.extend([
            "# POINT 82 : le total du panier est la SOMME de ses lignes,",
            "# recalculée par le serveur à chaque ligne ajoutée, modifiée",
            "# ou supprimée. Sommer un sous-total que le navigateur",
            "# écrirait serait la faille du point 77 en une addition de",
            "# plus : le compilateur le refuse.",
            f"rule {entite}.{montant} sumOf {ligne}.{calcule}",
            "",
        ])
    emit_stock_rule(lines, payable, source, porteur, facteur)
    lines.extend([
        "# Encaissement : le champ nommé porte le MONTANT, donc",
        "# l'entité à encaisser. Deux routes en découlent —",
        "# POST /entite/{id}/paiement (aucun corps : le montant est",
        "# relu en base) et POST /paiement/webhook, dont la",
        "# signature est vérifiée. Sans STRIPE_SECRET_KEY, elles",
        "# répondent 503 ; le reste de l'application fonctionne.",
        f"rule {entite}.{montant} payable",
        "",
    ])


def emit_extra_rules(lines, extra_rules, payable):
    rules = [
        rule for rule in extra_rules
        if payable or " writableAfterPayment " not in f" {rule} "
    ]
    lines.extend(rules)
    lines.append("")


def emit_management_workflow(lines, ent, actor, managers):
    suffix = f"By{actor}" if len(managers[ent]) > 1 else ""
    lines.append(f"workflow Manage{ent}{suffix} for {actor}")
    for action in ("Create", "Read", "Update", "Delete"):
        lines.append(f"    {action} {ent}")
    lines.append("")


def emit_browse_workflow(lines, act, entities, readers):
    readable = [ent for ent in entities if act in readers[ent]]
    if not readable:
        return
    lines.append(f"workflow Browse{act} for {act}")
    for ent in readable:
        lines.append(f"    Read {ent}")
    lines.append("")


def emit_workflows(lines, entities, managers, extra_workflows, actors, readers):
    """Émet workflows de gestion, additionnels et de lecture."""
    for ent in entities:
        for actor in managers[ent]:
            emit_management_workflow(lines, ent, actor, managers)
    for workflow in extra_workflows:
        lines.append(f"workflow {workflow['name']} for {workflow['actor']}")
        for action, target in workflow["actions"]:
            lines.append(f"    {action} {target}")
        lines.append("")
    for act in actors:
        emit_browse_workflow(lines, act, entities, readers)


def emit_custom_seeds(emitter, lines, entities, custom_seeds):
    for ent, rows in custom_seeds.items():
        if not rows or ent not in entities:
            continue
        lines.append(f"seed {ent}")
        for row in rows:
            parts = [f"{field}: {emitter._literal(value)}"
                     for field, value in row.items()]
            lines.append("    " + ", ".join(parts))
        lines.append("")


def emit_default_seeds(emitter, lines, entities, public_read, custom_seeds,
                       image_topic):
    for ent in public_read:
        if ent in custom_seeds:
            continue
        seedable = [(field, type_) for field, type_ in entities[ent]
                    if type_ in SEEDABLE_TYPES]
        if not seedable:
            continue
        lines.append(f"seed {ent}")
        for number in (1, 2, 3):
            parts = [f"{field}: {emitter._seed_value(field, type_, number, image_topic)}"
                     for field, type_ in seedable]
            lines.append("    " + ", ".join(parts))
        lines.append("")


def emit_seeds(emitter, lines, entities, public_read, want_seed,
               custom_seeds, image_topic):
    """Émet les seeds du catalogue, puis les seeds génériques."""
    if not want_seed:
        return
    custom_seeds = custom_seeds or {}
    emit_custom_seeds(emitter, lines, entities, custom_seeds)
    emit_default_seeds(emitter, lines, entities, public_read, custom_seeds, image_topic)


def landing_brief(description, design_intent, image_topic):
    brief = (f"{description.rstrip('.')} — {design_intent}"
             if design_intent else description)
    if image_topic:
        brief = (f"{brief.rstrip('.')}. Les illustrations doivent "
                 f"évoquer : {image_topic}.")
    return brief


def emit_landing(lines, description, design_intent, image_topic,
                 want_landing, sections, links):
    """Émet le brief, les sections et les liens de la landing."""
    if not want_landing:
        return
    brief = landing_brief(description, design_intent, image_topic)
    lines.append("landing")
    lines.append(f'    brief: "{brief}"')
    for section in sections:
        lines.append(f'    section "{section["title"]}": "{section["body"]}"')
    for link in links:
        lines.append(f'    link "{link["label"]}": "{link["url"]}"')
    lines.append("")
