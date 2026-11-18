"""Le contrat de chaque entité : champs, rôles, ce que le serveur peuple."""

from ..ast_validator.champs import ChampsMixin
from ..ir import PAYMENT_REF_COLUMN, PAYMENT_STATUS_COLUMN
from . import champs, roles_de_champs


def _specs_des_entites(entities, fk_placements, lisibles, plans):
    """Le contrat de chaque entité : champs, rôles, ce que le serveur peuple."""
    # POINT 79 : un champ 'derivedFrom' est CALCULÉ par le serveur, donc absent
    # des corps de requête — exactement comme un champ 'generated'. Le contrat
    # devait le dire : sans cela il annonçait `total` parmi les champs à
    # envoyer, et une IA d'interface fidèle au contrat aurait bâti un
    # formulaire de prix que le serveur ignore. C'est le défaut du point 76,
    # reproduit sur la brique qui venait de le corriger — la leçon « déclarer
    # ce que le backend fait VRAIMENT » vaut aussi quand une brique retire
    # quelque chose, pas seulement quand elle ajoute une colonne.
    # POINT 82 : même exigence pour 'sumOf'. Le défaut du point 76 s'est déjà
    # reproduit deux fois (points 79 et 81) : le déclarer d'emblée ici plutôt
    # que d'attendre qu'une IA d'interface bâtisse un champ « total » que le
    # serveur recalcule. Un total de panier est le cas où l'écart se voit le
    # plus vite — il change à chaque ligne ajoutée.
    # POINT 89 : quatrième membre de la même famille. Le défaut du point 76 s'est
    # reproduit sur chacune des trois précédentes ; celle-ci arrive déclarée.
    # POINT 102 : cinquième membre de la même famille, déclarée d'emblée elle
    # aussi. Sans ça le contrat annoncerait un « numéro de commande » parmi les
    # champs à saisir, et une IA d'interface fidèle au contrat dessinerait un
    # formulaire que le serveur ignore.
    entity_specs = {}
    for ent, fields in entities.items():
        field_list = []
        entity_model = plans.entity_models[ent]
        for fname, ftype in fields.items():
            policy = entity_model.fields[fname]
            derive = policy.derived_rule
            somme = policy.aggregate_rule
            numero = policy.numbering_rule
            peuple_par_le_serveur = policy.server_generated
            champ = {
                "name": fname,
                "type": ftype,
                # POINT 91 : ce que le SERVEUR exige, pas ce que la spec déclare.
                # Le contrat reflétait `rule X.y required` — or les schémas
                # Pydantic générés rendent obligatoire TOUT champ d'entrée, sans
                # exception (point 85 : « required reste une assertion, les
                # schémas rendent déjà tout champ obligatoire »). Un frontend
                # fidèle au contrat omettait donc les champs non déclarés et
                # récoltait un 422. Vu en vrai : ajouter `email` et `address` à
                # une fiche client a cassé le formulaire d'un site en marche,
                # alors que le contrat les annonçait facultatifs.
                "required": not peuple_par_le_serveur and not policy.upload_rule,
                # hidden : jamais présent dans les réponses de lecture
                "hidden_in_reads": policy.hidden_in_reads,
                # generated, derivedFrom ou sumOf : à NE PAS envoyer, le serveur
                # le peuple lui-même (et l'ignorerait dans le corps de requête)
                "server_generated": peuple_par_le_serveur,
                # categorized : la lecture renvoie un libellé, pas le nombre
                "categorized_in_reads": policy.categorized_in_reads,
                "postpayment_only": policy.postpayment_only,
            }
            # BRIQUE B3 : seules les déclarations de la spec apparaissent.
            # L'absence de ces clés signifie « non filtrable/triable » ; cela
            # garde le contrat des specs historiques inchangé à l'octet.
            if fname in plans.filterable_fields.get(ent, ()):
                valeurs_filtre = (list(policy.allowed_values)
                                   if policy.allowed_values else None)
                if ftype == "Boolean":
                    valeurs_filtre = ["true", "false"]
                champ["filterable"] = True
                champ["filter"] = {
                    "parameter": fname,
                    "kind": "exact",
                    "allowed_values": valeurs_filtre,
                }
            if fname in plans.sortable_fields.get(ent, ()):
                champ["sortable"] = True
            if policy.upload_rule:
                # BRIQUE B1 : le champ est une entrée multipart dédiée, pas
                # une valeur JSON et pas un asset Image. Le contrat expose la
                # limite, les types, le nom exact du champ et les deux routes
                # ajoutées plus bas ; l'IA frontend n'a rien à deviner.
                champ["upload"] = {
                    "field_name": fname,
                    "max_bytes": policy.upload_rule.max_bytes,
                    "accepted_types": list(policy.upload_rule.accepted_types),
                    "storage": "server_disk_reference",
                    "note": ("bytes received at runtime; the client's file name and "
                             "Content-Type are ignored, the type is established "
                             "by byte signature; private read according to the "
                             "row's ACL, as a byte-for-byte download"),
                }
            # BRIQUE 19 (point 96) : les valeurs permises. Sans elles, l'IA
            # dessine un champ TEXTE et l'utilisateur invente un statut qui
            # récolte un 422 — alors que la liste tient dans un menu déroulant.
            # Même raison que les bornes ci-dessous : le contrat décrit ce que le
            # backend REFUSE autant que ce qu'il accepte.
            choix = policy.allowed_values
            if choix:
                champ["allowed_values"] = list(choix)
            # POINT 85 : les bornes 'min'/'max' donnent un 422 avant tout INSERT.
            # Le contrat DOIT les annoncer : une interface qui les ignore laisse
            # l'utilisateur remplir un formulaire pour se faire refuser au bout,
            # alors qu'elle pouvait le dire tout de suite. Même raison que pour
            # `server_generated` (point 79) — le contrat décrit ce que le backend
            # fait VRAIMENT, y compris ce qu'il REFUSE.
            for nom, borne in (("min", policy.constraints.minimum),
                               ("max", policy.constraints.maximum)):
                if borne:
                    champ[f"{nom}_{'length' if borne.portee == 'longueur' else 'value'}"] = \
                        borne.valeur
            champ.update(_non_blank_constraint(ftype, policy))
            if policy.constraints.unique:
                champ["unique"] = True
                champ["unique_note"] = ("unique value enforced by the database: a "
                                        "duplicate creation or update answers "
                                        "409, not 422 — tell the user rather "
                                        "than replaying the request.")
            if derive:
                champ["derived_from"] = (f"{derive.source_entity}."
                                         f"{derive.source_field}")
                champ["derived_factor"] = derive.factor
                champ["note"] = (
                    f"calculated by the server: {derive.source_entity}."
                    f"{derive.source_field} × {derive.factor}. Do not "
                    f"send it, and do not calculate it in the browser to "
                    f"show it before creation — reread the value returned by "
                    f"the server, it is the one that will be charged.")
            if somme:
                champ["summed_from"] = (f"{somme.source_entity}."
                                        f"{somme.source_field}")
                champ["note"] = (
                    f"total recalculated by the server: sum of the attached "
                    f"{somme.source_entity}.{somme.source_field}. "
                    f"Do not send it. It changes with each {somme.source_entity} "
                    f"added, modified or deleted: reread the "
                    f"{ent} after each line write rather than keeping a "
                    f"total in the browser, which would drift.")
            if policy.timestamped:
                champ["created_at"] = True
                champ["note"] = (
                    "creation instant, written by the server in ISO 8601 UTC "
                    "(e.g. '2026-07-31T04:18:22.310+00:00'), and never changed afterwards. "
                    "Do not send it: neither on creation nor on update. "
                    "It sorts as text — comparing the strings is enough, "
                    "no need to convert them to order a list. "
                    "MAY BE EMPTY on records created before the rule was "
                    "added: show a dash, never today's date — that date "
                    "was not lost, it never existed.")
            if numero:
                champ["numbered_as"] = numero.format
                champ["note"] = (
                    f"readable number assigned by the server on creation, on the "
                    f"template “{numero.format}”, and never changed afterwards. "
                    f"Do not send it: neither on creation nor on update. "
                    f"It is the reference a human reads and dictates — SHOW it "
                    f"wherever the record is identified (list, detail, order "
                    f"confirmation), preferably before the technical `id`, "
                    f"and make it copyable. "
                    + ("It sorts as text, the sequence part being padded "
                       "with zeros. " if "{N" in numero.format else "")
                    + "MAY BE EMPTY on records created before the rule was "
                      "added: show a dash, never an invented number.")
            field_list.append(champ)
        # POINT 88 : une clé étrangère de monl référence l'une de DEUX choses,
        # et le contrat n'en disait qu'une. Celles que la route Create peuple
        # depuis le jeton portent un identifiant de COMPTE (`_monl_users.id`) ;
        # les autres portent l'`id` de la table métier. `schema.sql` écrit
        # d'ailleurs deux `REFERENCES` différents — le contrat, lui, annonçait
        # « references: Customer » dans les deux cas.
        #
        # Ce que ça coûtait : une interface qui suit le contrat joint
        # `order.customer_id` à `customer.id`, alors que la bonne jointure est
        # `customer.customer_id`. Une jointure qui marche À MOITIÉ — juste tant
        # que l'id de compte et l'id de fiche coïncident, c'est-à-dire sur les
        # premiers enregistrements, c'est-à-dire pendant les tests.
        identity_cols = plans.identity_foreign_keys.get(ent, frozenset())
        fks = []
        for p in fk_placements.get(ent, []):
            lien = {"column": p["fk_column"], "references": p["owner_entity"],
                    "unique": p["unique"]}
            if p["fk_column"] in identity_cols:
                lien["references_account"] = True
                # La fiche métier se retrouve par la colonne HOMONYME, qui porte
                # le même identifiant de compte — pas par son `id`.
                lien["note"] = (
                    f"contains an ACCOUNT identifier (the holder's), "
                    f"not the `id` of a {p['owner_entity']} record. To "
                    f"find the record: look for the {p['owner_entity']} whose "
                    f"`{p['fk_column']}` has this same value — never the one "
                    f"whose `id` has it, the match would be accidental.")
            else:
                lien["references_account"] = False
                lien["note"] = (f"contains the `id` of a "
                                f"{p['owner_entity']} record.")
            fks.append(lien)
        roles = roles_de_champs._assign_field_roles(field_list)
        for f in field_list:
            f["role"] = roles.get(f["name"])
        # POINT 76 : les deux colonnes de suivi de la brique 'payable' sont
        # présentes dans toutes les réponses de lecture (le générateur fait un
        # SELECT *) mais n'étaient déclarées NULLE PART dans le contrat. Une IA
        # d'interface qui le suit à la lettre ne pouvait donc pas savoir
        # qu'elles existent, et ne pouvait pas afficher l'état d'un règlement :
        # le bouton de paiement était dessinable, son résultat non.
        #
        # Ajoutées APRÈS l'attribution des rôles, volontairement : passées à
        # _assign_field_roles, elles auraient pris deux des trois emplacements
        # « méta » (point 35) et se seraient fait afficher comme des
        # informations secondaires quelconques, en évinçant de vrais champs de
        # la spec. Elles n'ont donc aucun rôle — ce qu'il faut en faire est dit
        # en toutes lettres dans le brief, pas déduit d'un rôle de mise en page.
        if ent in plans.payable_by_entity:
            # Chaque colonne porte SA propre explication : les décrire d'une
            # seule phrase commune faisait annoncer « 'en_attente' / 'payee' »
            # pour `payment_ref`, qui contient une référence de session — vu en
            # relisant le brief produit, pas le code.
            suivi = (
                (PAYMENT_STATUS_COLUMN,
                 "payment state, written by the server alone: 'en_attente' "
                 "while nothing is charged, 'payee' once the provider's "
                 "webhook is received — this field says whether it is paid"),
                (PAYMENT_REF_COLUMN,
                 "the session reference at the provider, written by the "
                 "server alone; useful for accounting reconciliation, of no "
                 "interest to the visitor. It may be filled AS SOON AS the "
                 "session opens, before any charge: so it is not a payment "
                 "indicator, payment_status is what says whether it is "
                 "paid"),
            )
            for colonne, explication in suivi:
                field_list.append({
                    "name": colonne,
                    "type": "String",
                    "required": False,
                    "hidden_in_reads": False,
                    # Jamais fourni par le client : même interdit que 'generated'.
                    "server_generated": True,
                    "categorized_in_reads": False,
                    "payment_tracking": True,
                    "note": explication,
                    "role": None,
                })
        entity_specs[ent] = {
            "fields": field_list, "foreign_keys": fks,
            "client_foreign_keys": champs._client_supplied_fks(plans, ent),
            "archetype": roles_de_champs._archetype(
                roles, ent in lisibles,
                bool(plans.access_policies.get((ent, "Read"), None)
                     and plans.access_policies[(ent, "Read")].public)),
        }
    return entity_specs


def _non_blank_constraint(type_, policy):
    if (type_ in ChampsMixin.BORNES_TEXTE and policy.constraints.required
            and not policy.server_generated):
        return {"non_blank": True}
    return {}
