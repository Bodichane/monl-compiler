"""Le contrat de chaque entité : champs, rôles, ce que le serveur peuple."""

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
                    "max_bytes": policy.upload_rule["max_bytes"],
                    "accepted_types": list(policy.upload_rule["accepted_types"]),
                    "storage": "server_disk_reference",
                    "note": ("octets reçus à l'exécution ; le nom de fichier et le "
                             "Content-Type client sont ignorés, le type est établi "
                             "par signature d'octets ; lecture privée selon l'ACL de "
                             "la ligne, en téléchargement octet/octet"),
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
            for nom in ("min", "max"):
                borne = policy.constraints.get(nom)
                if borne:
                    champ[f"{nom}_{'length' if borne['portee'] == 'longueur' else 'value'}"] = \
                        borne["valeur"]
            if policy.constraints.get("unique"):
                champ["unique"] = True
                champ["unique_note"] = ("valeur unique imposée par la base : une "
                                        "création ou une modification en doublon "
                                        "répond 409, pas 422 — le dire à l'utilisateur "
                                        "plutôt que de rejouer la requête.")
            if derive:
                champ["derived_from"] = (f"{derive['source_entity']}."
                                         f"{derive['source_field']}")
                champ["derived_factor"] = derive["factor"]
                champ["note"] = (
                    f"calculé par le serveur : {derive['source_entity']}."
                    f"{derive['source_field']} × {derive['factor']}. Ne pas "
                    f"l'envoyer, et ne pas le calculer côté navigateur pour "
                    f"l'afficher avant création — relire la valeur renvoyée par "
                    f"le serveur, c'est elle qui sera encaissée.")
            if somme:
                champ["summed_from"] = (f"{somme['source_entity']}."
                                        f"{somme['source_field']}")
                champ["note"] = (
                    f"total recalculé par le serveur : somme des "
                    f"{somme['source_entity']}.{somme['source_field']} rattachés. "
                    f"Ne pas l'envoyer. Il change à chaque {somme['source_entity']} "
                    f"ajouté, modifié ou supprimé : relire le "
                    f"{ent} après chaque écriture de ligne plutôt que de tenir un "
                    f"total côté navigateur, qui divergerait.")
            if policy.timestamped:
                champ["created_at"] = True
                champ["note"] = (
                    "instant de création, écrit par le serveur en ISO 8601 UTC "
                    "(ex. '2026-07-31T04:18:22.310+00:00'), et jamais modifié ensuite. "
                    "Ne pas l'envoyer : ni à la création, ni à la modification. "
                    "Il se trie comme du texte — comparer les chaînes suffit, "
                    "inutile de les convertir pour ordonner une liste. "
                    "PEUT ÊTRE VIDE sur les enregistrements créés avant l'ajout "
                    "de la règle : afficher un tiret, jamais la date du jour — "
                    "cette date-là n'a pas été perdue, elle n'a jamais existé.")
            if numero:
                champ["numbered_as"] = numero["format"]
                champ["note"] = (
                    f"numéro lisible attribué par le serveur à la création, sur le "
                    f"gabarit « {numero['format']} », et jamais modifié ensuite. "
                    f"Ne pas l'envoyer : ni à la création, ni à la modification. "
                    f"C'est la référence que l'humain lit et dicte — l'AFFICHER "
                    f"partout où l'enregistrement est identifié (liste, détail, "
                    f"accusé de commande), de préférence avant l'`id` technique, "
                    f"et la rendre copiable. "
                    + ("Il se trie comme du texte, la partie séquence étant "
                       "complétée par des zéros. " if "{N" in numero["format"] else "")
                    + "PEUT ÊTRE VIDE sur les enregistrements créés avant l'ajout "
                      "de la règle : afficher un tiret, jamais un numéro inventé.")
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
                    f"contient un identifiant de COMPTE (celui du titulaire), "
                    f"pas l'`id` d'un enregistrement {p['owner_entity']}. Pour "
                    f"retrouver la fiche : chercher le {p['owner_entity']} dont "
                    f"`{p['fk_column']}` vaut cette même valeur — jamais celui "
                    f"dont `id` la vaut, la correspondance serait fortuite.")
            else:
                lien["references_account"] = False
                lien["note"] = (f"contient l'`id` d'un enregistrement "
                                f"{p['owner_entity']}.")
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
                 "état du règlement, écrit par le serveur seul : 'en_attente' "
                 "tant que rien n'est encaissé, 'payee' une fois le webhook du "
                 "prestataire reçu — c'est ce champ qui dit si c'est payé"),
                (PAYMENT_REF_COLUMN,
                 "référence de la session chez le prestataire, écrite par le "
                 "serveur seul ; utile pour un rapprochement comptable, sans "
                 "intérêt pour le visiteur. Elle peut être renseignée DÈS "
                 "l'ouverture de la session, avant tout encaissement : ce "
                 "n'est donc pas un indicateur de règlement, c'est "
                 "payment_status qui dit si c'est payé"),
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
