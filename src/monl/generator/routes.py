"""Génération des routes CRUD et de l'application du contrôle d'accès
(rôle, ownedBy, accessibleBy, public, hidden, categorized, compteurs).

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.

Tout le SQL de contrôle d'accès passe par la couche d'émission typée `sql`
(point 108) : une valeur ne peut y entrer que liée en paramètre, jamais collée
dans le texte. Voir generator/sql.py.
"""

from . import sql


class RoutesMixin:
    def _generate_route_lines(self):
        """Assemble les familles de routes dans un ordre stable."""
        api_lines = ["# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---"]
        api_lines.extend(self._generate_crud_and_action_route_lines())
        api_lines.extend(self._generate_payment_routes())
        api_lines.extend(self._generate_postpayment_routes())
        return api_lines

    def _route_access_context(self, plan):
        """Prépare les invariants de sécurité communs à chaque route."""
        base_target = plan.base_target
        target = plan.target
        tag = plan.tags[0]
        access = self.compilation_plans.access_policies[(base_target, plan.action)]
        allowed_actors = sorted(access.actors)
        is_public = access.public
        if is_public:
            security_check = (
                "    pass  # Route publique (règle 'public') : "
                "aucune authentification requise"
            )
            dependency_injection = ""
        elif len(allowed_actors) == 1:
            security_check = (
                f'    if current_actor != "{allowed_actors[0]}": '
                f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                f'Rôle {allowed_actors[0]} requis")'
            )
            dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
        else:
            allowed_set_literal = ", ".join(f'"{actor}"' for actor in allowed_actors)
            security_check = (
                f'    if current_actor not in {{{allowed_set_literal}}}: '
                f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                f'Rôle parmi [{", ".join(allowed_actors)}] requis")'
            )
            dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
        return {
            "base_target": base_target,
            "target": target,
            "tag": tag,
            "access": access,
            "allowed_actors": allowed_actors,
            "is_public": is_public,
            "security_check": security_check,
            "dependency_injection": dependency_injection,
            "dep_suffix": f", {dependency_injection}" if dependency_injection else "",
        }

    def _generate_crud_and_action_route_lines(self):
        """Rend les routes issues des workflows : CRUD et ``Execute``.

        Les familles paiement et post-paiement sont volontairement hors de
        cette méthode : elles naissent de règles métier dédiées et sont
        assemblées par ``_generate_route_lines`` avec la même liste de plans.
        """
        api_lines = []

        # CORRECTIF (post-v6) : les routes sont désormais regroupées par couple
        # (type d'action, cible), et non plus générées une fois par workflow.
        # Raison : avant ce correctif, deux workflows différents visant la même
        # action sur la même entité (ex. deux acteurs autorisés à faire "Delete Post"
        # via une règle 'sharedBy') produisaient deux définitions de route FastAPI
        # sur le même chemin ('@app.delete(\"/post/{id}\")' deux fois) — seule la
        # première déclarée restait effectivement joignable, la seconde était
        # silencieusement masquée, et son acteur recevait un 403 malgré une spec
        # valide. Le regroupement ci-dessous fusionne les acteurs autorisés en un
        # seul contrôle d'accès par route, listant tous les acteurs légitimes.
        route_map = self.compilation_plans.route_map

        for (act_type, _key), plan in route_map.items():
            context = self._route_access_context(plan)

            if act_type == "Create":
                api_lines.extend(self._generate_create_route_lines(
                    plan, context, act_type))
            elif act_type == "Read":
                api_lines.extend(self._generate_read_route_lines(
                    plan, context, act_type))
            elif act_type == "Update":
                api_lines.extend(self._generate_update_route_lines(
                    plan, context, act_type))
            elif act_type == "Delete":
                api_lines.extend(self._generate_delete_route_lines(
                    plan, context, act_type))
            elif act_type == "Execute":
                api_lines.extend(self._generate_execute_route_lines(
                    plan, context, act_type))

        return api_lines

    def _generate_create_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Create``."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        # AJOUT (post-v6, roadmap) : si l'entité a une relation entrante
        # (ex. "relation User hasMany Todo"), la colonne de clé étrangère
        # correspondante (ex. "user_id") est désormais réellement peuplée
        # à la création, à partir de l'identité JWT de l'appelant.
        # CORRECTIF DE GAP PRÉ-EXISTANT : cette colonne était déjà générée
        # dans schema.sql depuis les toutes premières versions, mais
        # jamais incluse dans la requête INSERT — elle restait NULL pour
        # tout enregistrement créé, rendant les relations inertes au
        # runtime malgré leur présence dans le schéma.
        reputation_rules_here = self.reputation_rules_by_trigger.get(base_target, [])
        counter_fk_columns = self._counter_fk_columns(base_target)
        is_reputation_fk = bool(counter_fk_columns)
        # POINT 99 : la question « cette colonne se peuple-t-elle depuis
        # le jeton ? » a UNE réponse, `_identity_fk_columns`, et cette
        # ligne la lit au lieu de la recalculer. Les quatre conditions
        # qui vivaient ici (route publique, cible de compteur, propriété
        # transitive, et désormais parent non-acteur) y sont réunies :
        # les tenir à deux endroits, c'était deux endroits où elles
        # pouvaient diverger — et la quatrième manquait des deux côtés.
        # Rappel des trois premières : une route publique n'a aucune
        # identité appelante fiable ; une cible de compteur est choisie
        # par le client (« j'apprécie CE post ») ; et sous propriété
        # transitive, c'est le client qui désigne le rattachement
        # (« cette ligne va dans CETTE commande ») — y écrire
        # `current_user_id` était le défaut du point 80.
        chaine_create = self._transitive_chain(base_target)
        colonnes_identite = self._identity_fk_columns().get(base_target, set())
        colonne_identite = sorted(colonnes_identite)[0] if colonnes_identite else None
        populate_owner = colonne_identite is not None
        verifie_parent = bool(chaine_create) and not is_public
        # AJOUT (roadmap, écosystème de capacités -- suite de la
        # brique 1) : un champ 'generated' est peuplé depuis le
        # pseudonyme anonyme du compte courant (déjà porté par le
        # JWT depuis /login), jamais depuis le corps de requête --
        # incompatible avec 'public' (validé par ast_validator.py),
        # donc l'appelant est nécessairement authentifié ici.
        generated_here = self.generated_fields_by_entity.get(base_target, [])
        # AJOUT (brique 17, point 90) : la fiche que l'appelant doit
        # déjà posséder. Elle se cherche par son identifiant de COMPTE,
        # donc la route a besoin de `current_user_id` même quand rien
        # d'autre ne l'exigeait.
        fiche_exigee = self._profile_lookup(base_target)
        create_deps = dependency_injection
        if populate_owner or verifie_parent or fiche_exigee:
            create_deps += ", current_user_id: int = Depends(get_current_user_id)" if create_deps else "current_user_id: int = Depends(get_current_user_id)"
        if generated_here:
            create_deps += ", current_anon_handle: str = Depends(get_current_anon_handle)" if create_deps else "current_anon_handle: str = Depends(get_current_anon_handle)"
        create_deps_suffix = f", {create_deps}" if create_deps else ""

        api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def create_{base_target.lower()}(data: {base_target}Schema{create_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        fields = list(self.entities[base_target].keys())
        insert_columns = list(fields)
        # AJOUT (brique 17, point 90) : « on ne commande pas sans être
        # identifié ». La vérification vient EN PREMIER, avant même le
        # contrôle du parent et tout calcul : un appelant sans fiche n'a
        # pas à apprendre si tel produit existe, ni à consommer du
        # stock. 409 et non 403 — ce n'est pas un droit qui manque, c'est
        # un état à corriger, et le message dit lequel.
        if fiche_exigee:
            table_fiche, colonne_fiche = fiche_exigee
            api_lines += [
                f"    cursor.execute('SELECT 1 FROM \"{table_fiche}\" "
                f'WHERE "{colonne_fiche}" = ?\', (current_user_id,))',
                "    if not cursor.fetchone():",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                # Pas d'article devant le nom de l'entité : il n'a pas de
                # genre, et « un Commande » se lisait mal.
                f"            \"Créez d'abord votre fiche "
                f"{self.required_profiles[base_target]} : un enregistrement \"",
                f"            '{base_target} sans elle ne pourrait être "
                f"rattaché à personne.'))",
            ]
        # AJOUT (brique 11, point 81) : la vérification qui remplace le
        # peuplement depuis le jeton. Sans elle, la brique ouvrirait un
        # trou plus large que celui qu'elle ferme : n'importe quel
        # compte pourrait ajouter une ligne à la commande d'autrui.
        # Elle vient AVANT tout le reste (calculs 'derivedFrom'
        # compris) : un appelant qui n'a rien à faire là ne doit même
        # pas apprendre si tel produit existe.
        #
        # Une seule réponse pour « n'existe pas » et « pas à vous » :
        # les distinguer permettrait d'énumérer les commandes des
        # autres, exactement ce que le 404 de la lecture détail évite.
        if verifie_parent:
            # La chaîne (transitive, de profondeur quelconque) se remonte
            # en un coup, depuis le parent que le CLIENT désigne via sa
            # clé étrangère (data.<fk>). Un parent absent ou étranger rend
            # le même refus : le scalaire vaut NULL ou un compte différent.
            # 403 unique pour « n'existe pas » et « pas à vous » : les
            # distinguer permettrait d'énumérer les commandes des autres,
            # exactement ce que le 404 de la lecture détail évite.
            # La valeur que le CLIENT désigne (data.<fk>) entre par
            # sql.bind : elle sort en '?' + paramètre lié, jamais dans le
            # texte. C'est la classe de défaut du point 107 rendue
            # impossible — texte et params sortent ENSEMBLE de l'objet Sql.
            _owner_q = self._chain_owner_scalar(
                base_target, sql.bind(f"data.{chaine_create['via_fk']}"))
            _sql_lit, _params_lit = sql.execute_args(_owner_q, prefix="SELECT ")
            api_lines += [
                f"    cursor.execute({_sql_lit}, {_params_lit})",
                "    _parent = cursor.fetchone()",
                "    if not _parent or _parent[0] is None or _parent[0] != current_user_id:",
                "        conn.close()",
                "        raise HTTPException(status_code=403, detail=(",
                f"            \"Contrôle d'accès : ce {chaine_create['via']} ne vous \"",
                "            'appartient pas, ou n\\'existe pas.'))",
            ]
        # AJOUT (brique 18, point 91) : on n'ajoute pas une ligne à une
        # commande DÉJÀ RÉGLÉE. Le parent vient de `data.<fk>` ici — le
        # client le désigne — mais il a été validé juste au-dessus par la
        # propriété transitive, donc c'est bien SA commande. La garde
        # vient avant tout calcul et avant tout décompte de stock : une
        # écriture refusée ne doit rien avoir consommé.
        for verrou in self._payment_locked_parents(base_target):
            api_lines += self._payment_lock_lines(
                verrou["table"], f"data.{verrou['fk_column']}",
                verrou["entity"], var="_parent_regle")
        # AJOUT (brique 10, point 77) : un champ 'derivedFrom' n'est pas
        # dans `data` — le serveur le calcule ici, AVANT l'insertion, en
        # lisant le prix sur la ligne liée que le client a désignée. Le
        # 409 vaut mieux qu'un montant faux : une référence bidon doit
        # arrêter la commande, pas la créer à zéro euro.
        derives_ici = self.derived_by_entity.get(base_target, [])
        for regle in derives_ici:
            fk_col = self._derived_source_fk(base_target,
                                             regle["source_entity"])
            var = f"_calcul_{regle['field']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{regle['source_field']}\" FROM "
                f'"{regle["source_entity"].lower()}" WHERE id = ?\', '
                f"(data.{fk_col},))",
                f"    _src_{regle['field']} = cursor.fetchone()",
                f"    if not _src_{regle['field']}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{regle['source_entity']} introuvable : impossible de calculer "
                f"{regle['field']}.'))",
                f"    if data.{regle['factor']} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'La quantité doit être strictement positive.'))",
                f"    {var} = round(float(_src_{regle['field']}[0] or 0) "
                f"* int(data.{regle['factor']}), 2)",
            ]
        calcules = {r["field"]: f"_calcul_{r['field']}" for r in derives_ici}
        # AJOUT (brique 12, point 82) : une commande naît sans ligne, donc
        # son total naît à 0 — jamais à NULL, qu'aucun frontend ne sait
        # afficher, et jamais depuis `data` (le champ n'y est plus). La
        # somme suivra les lignes, écriture par écriture.
        for nom_somme in self._aggregated_field_names(base_target):
            calcules[nom_somme] = "0"
        # AJOUT (brique 16, point 89) : l'instant de création. Écrit
        # ici, une seule fois, et retiré du SET de la route Update —
        # une date de création qui bouge n'est pas une date de création.
        for nom_date in self.timestamp_fields_by_entity.get(base_target, []):
            calcules[nom_date] = "_horodatage()"
        # BRIQUE 25 (point 113) : un champ réservé à la route
        # `apres-paiement` est absent du schéma d'entrée générique.
        # À la création il naît donc vide, exactement comme une valeur
        # de suivi qui n'existe pas encore. Le laisser tomber sur le
        # repli `data.<champ>` donnait un AttributeError et un 500 sur
        # TOUTE création de l'entité — découvert sur le checkout réel
        # de CodexShop, où fulfillmentStatus et trackingNumber sont
        # légitimement inconnus avant paiement.
        postpaiement_ici = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        for nom_postpaiement in postpaiement_ici:
            calcules[nom_postpaiement] = "None"
        # BRIQUE 22 (point 102) : le numéro lisible. Le compteur est lu
        # ET incrémenté en base ; ces lignes partent donc DANS le `try`
        # ci-dessous, pas ici — hors de la transaction, une insertion
        # refusée laisserait le compteur avancé et le numéro suivant
        # sauterait. Jamais `MAX(...) + 1` sur la table métier : il
        # redonnerait le numéro d'un enregistrement supprimé, et se
        # tromperait dès que deux créations se croisent.
        lignes_numerotation = []
        for regle in self.numbered_fields_by_entity.get(base_target, []):
            var = f"_numero_{regle['field']}"
            lignes_numerotation.append(
                f"        {var} = _attribuer_numero(cursor, "
                f"{base_target!r}, {regle['field']!r}, "
                f"{regle['format']!r}, {regle['periode']!r})")
            calcules[regle["field"]] = var
        value_exprs = [
            calcules.get(f, "current_anon_handle" if f in generated_here
                         else f"data.{f}")
            for f in fields
        ]
        if populate_owner:
            insert_columns.append(colonne_identite)
            value_exprs.append("current_user_id")
        if is_reputation_fk:
            for counter_fk in counter_fk_columns:
                insert_columns.append(counter_fk)
                value_exprs.append(f"data.{counter_fk}")
        # Tout parent que le jeton ne désigne pas doit être désigné par
        # l'appelant. Trois cas y mènent : les parents SECONDAIRES d'une
        # entité possédée (un commentaire et son article) ; sous
        # propriété transitive, le parent propriétaire lui-même — que la
        # vérification plus haut vient de valider ; et depuis le
        # point 99, TOUS les parents d'une entité fille d'une table
        # métier, qui n'a aucun propriétaire à déduire. Sur une création
        # publique la liste est vide et les colonnes restent NULL,
        # comportement historique conservé.
        for _client_fk in self._client_fk_columns(base_target):
            insert_columns.append(_client_fk)
            value_exprs.append(f"data.{_client_fk}")
        columns = ", ".join(f'"{c}"' for c in insert_columns)
        placeholders = ", ".join(["?"] * len(insert_columns))
        api_lines.append(f"    query = 'INSERT INTO \"{base_target.lower()}\" ({columns}) VALUES ({placeholders}) RETURNING id'")
        values_list = ", ".join(value_exprs)
        # CORRECTIF (bêta, intégrité transactionnelle) : l'insertion et
        # les effets 'increments'/'decrements' liés sont exécutés dans
        # UNE SEULE transaction, avec un unique commit à la fin et un
        # rollback en cas d'erreur. Avant, un commit intermédiaire après
        # l'INSERT puis un commit séparé par effet pouvaient laisser un
        # état partiel si le processus s'arrêtait entre les deux (ligne
        # créée mais compteur non mis à jour, ou l'inverse). Une cible
        # d'effet inexistante ne lève toujours pas d'erreur (UPDATE sans
        # ligne correspondante) — elle ne fait simplement rien.
        api_lines.append("    try:")
        api_lines += lignes_numerotation
        api_lines.append(f"        cursor.execute(query, ({values_list},))")
        api_lines.append("        row_id = cursor.fetchone()[0]")
        # AJOUT (brique 12, point 82) : le total du parent est recalculé
        # DANS la même transaction que l'insertion de la ligne. Un commit
        # séparé pourrait laisser une ligne créée et un total resté en
        # arrière — c'est-à-dire un panier qui ne dit pas ce qu'il coûte,
        # et sur une entité 'payable', un montant faux à encaisser.
        for recalcul in self._aggregation_recomputes(base_target):
            parent = f"data.{recalcul['fk_column']}"
            api_lines.append(
                f"        cursor.execute({recalcul['sql']!r}, ({parent}, {parent}))")
        for rule in reputation_rules_here:
            target_table = rule["target_entity"].lower()
            target_field = rule["target_field"]
            sql_op = "-" if rule["direction"] == "decrements" else "+"
            # CORRECTIF (point 86) : la colonne visée est celle qui pointe
            # vers l'entité DÉCRÉMENTÉE, pas la relation « propriétaire ».
            # Tant qu'une entité déclenchante n'avait qu'UNE relation
            # entrante (Report -> Member, Like -> Post), les deux
            # coïncidaient et personne ne voyait la différence. OrderLine
            # en a deux — Order et Product — et le code décrémentait le
            # stock du produit portant l'id de la COMMANDE. Le compilateur
            # a déjà connu ce défaut (« un mécanisme de clé étrangère qui
            # décrémentait le mauvais enregistrement ») : il est revenu
            # par la porte de la deuxième relation.
            fk_vers_cible = self._decrement_fk_column(base_target, rule)
            if not fk_vers_cible:
                raise ValueError(
                    f"Génération : aucune clé étrangère de '{base_target}' ne désigne "
                    f"'{rule['target_entity']}', alors que l'effet compteur l'exige.")
            fk_value_expr = f"data.{fk_vers_cible}"
            # BRIQUE 14 (point 86) : la quantité est soit une constante,
            # soit un champ du corps de requête ('by quantity').
            quantite = (f"data.{rule['amount_field']}" if rule.get("amount_field")
                        else str(rule["amount"]))
            # LE cœur de la brique. Un décompte qui peut passer sous son
            # plancher est un stock qui MENT : la boutique afficherait
            # -3 paires disponibles, et aurait encaissé les huit qu'elle
            # n'avait pas. Le garde-fou n'est pas une exception « stock »
            # câblée en dur — il vient de la DÉCLARATION 'min' du
            # point 85 sur le champ visé. Une réputation sans 'min'
            # continue de passer sous zéro, ce qui est son droit.
            plancher = (self.field_constraints.get(rule["target_entity"], {})
                        .get(target_field, {}).get("min"))
            borne = plancher["valeur"] if plancher else None
            if borne is not None and rule["direction"] == "decrements":
                # UNE seule instruction : la condition et l'écriture sont
                # évaluées ensemble, donc deux commandes simultanées ne
                # peuvent pas lire le même stock et le décompter deux fois.
                api_lines.append(
                    f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = "
                    f'"{target_field}" - ? WHERE id = ? AND "{target_field}" - ? >= ?\', '
                    f"({quantite}, {fk_value_expr}, {quantite}, {borne}))")
                # Ni rollback ni close ICI : on est dans le `try` de la
                # création, dont le `except Exception` s'en charge avant
                # de relayer. Les faire deux fois donnait 500 — la
                # seconde fermeture opérait sur une connexion déjà close
                # (vérifié contre un vrai serveur : le refus de stock
                # répondait 500 au lieu de 409).
                api_lines += [
                    "        if cursor.rowcount == 0:",
                    "            raise HTTPException(status_code=409, detail=(",
                    f"                '{rule['target_entity']}.{target_field} insuffisant : "
                    f"la quantité demandée dépasse ce qui reste disponible.'))",
                ]
            else:
                api_lines.append(
                    f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = \"{target_field}\" {sql_op} ? "
                    f"WHERE id = ?', ({quantite}, {fk_value_expr}))"
                )
        api_lines.append("        conn.commit()")
        # POINT 85 : jusqu'ici ce 409 ne pouvait venir que d'une clé
        # étrangère, et son message le disait. 'unique' ajoute une
        # seconde cause — le même code HTTP, mais pas la même
        # explication : répondre « référence invalide » à un doublon
        # enverrait l'appelant chercher un problème qu'il n'a pas.
        # POINT 116 : 'oncePer' a ajouté une TROISIÈME cause au même 409, et sa
        # phrase prenait le pas sur celle de 'unique' — un simple doublon de
        # champ, sur une autre cible et un autre compte, s'entendait répondre
        # « vous l'avez déjà fait pour cette cible » (vérifié contre un vrai
        # serveur). C'est exactement le défaut que le point 85 avait fermé,
        # rouvert par la brique suivante. On distingue donc les deux causes sur
        # les COLONNES que SQLite nomme dans son erreur, au lieu de supposer
        # laquelle des deux règles a parlé.
        uniques_ici = self._unique_fields(base_target)
        once_ici = [index for index in self._compute_once_per_indexes()
                    if index[0] == base_target.lower()]
        # A1 : le classement passe par SQLSTATE côté PostgreSQL et par le
        # message historique côté SQLite. TROIS branches nommées, puis un
        # `raise` INCONDITIONNEL — sans lui, une intégrité violée d'une
        # quatrième espèce (NOT NULL, CHECK, un index unique que la spec ne
        # déclare pas) sort de l'`except` sans rien lever : la route continue
        # jusqu'au `return {'status': 'success'}` APRÈS un rollback, et
        # annonce comme écrit ce qui vient d'être défait. Mesuré : une
        # référence `numbered` en double rendait 500 (UnboundLocalError sur
        # `row_id`) au lieu d'un 409, et le cas où `row_id` est déjà lié
        # aurait rendu un faux succès. Un `except` qui n'aboutit pas à un
        # `raise` est un `except` qui ment.
        once_names = tuple(index[2] for index in once_ici)
        once_signatures = tuple(
            f"{table}.{col}" for table, columns, _index in once_ici for col in columns)
        api_lines.append("    except _DATABASE_INTEGRITY_ERRORS as _err:")
        api_lines.append("        conn.rollback(); conn.close()")
        api_lines.append(
            f"        _integrity_kind = _database_integrity_kind(_err, {once_names!r}, "
            f"{once_signatures!r})")
        if once_ici:
            api_lines.append("        if _integrity_kind == 'once_per':")
            api_lines.append("            raise HTTPException(status_code=409, detail=(")
            api_lines.append(
                "                'Cette action a déjà été effectuée pour cette "
                "cible par ce compte.'))")
        # La branche `unique` est émise MÊME sans champ `unique` déclaré : la
        # brique 22 (`numbered`) pose un index unique sans qu'on le déclare,
        # et le point 85 en pose un par `unique`. Ne l'émettre que sur la
        # seconde laissait la première sans réponse.
        api_lines.append("        if _integrity_kind == 'unique':")
        api_lines.append("            raise HTTPException(status_code=409, detail=(")
        if uniques_ici:
            api_lines.append(
                f"                'Valeur déjà utilisée : {', '.join(uniques_ici)} "
                f"doit être unique.'))")
        else:
            api_lines.append(
                "                'Valeur déjà utilisée : cet enregistrement "
                "existe déjà.'))")
        api_lines.append("        if _integrity_kind == 'foreign_key':")
        api_lines.append("            raise HTTPException(status_code=409, detail=(")
        api_lines.append("                'Référence invalide : un identifiant lié fourni ne correspond à aucun '")
        api_lines.append("                'enregistrement existant.'))")
        api_lines.append("        raise HTTPException(status_code=409, detail=(")
        api_lines.append("            \"Conflit d'intégrité en base : l'écriture a été annulée, \"")
        api_lines.append("            'rien n\\'a été enregistré.'))")
        api_lines.append("    except Exception:")
        api_lines.append("        conn.rollback(); conn.close(); raise")
        api_lines.append("    conn.close()")
        api_lines.append("    return {'status': 'success', 'id': row_id}")
        api_lines.append("")

        return api_lines

    def _generate_read_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Read``."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dep_suffix = context["dep_suffix"]
        # AJOUT (roadmap point 3, complété) : route de liste, en plus
        # de la lecture par ID déjà existante — jusqu'ici il n'existait
        # aucun moyen d'énumérer les enregistrements d'une entité sans
        # déjà connaître leurs identifiants un par un.
        # AJOUT (roadmap, pagination) : 'limit'/'offset' en paramètres
        # de requête (défaut 50, plafonné à 200), plus le nombre total
        # d'enregistrements — sans ça, une table volumineuse renverrait
        # tout d'un coup, sans borne.
        # CORRECTIF (roadmap, front visuel) : les lignes sont désormais
        # renvoyées comme des objets nommés {colonne: valeur} plutôt
        # que des tableaux positionnels bruts — un front (ou tout
        # client) n'a plus besoin de connaître l'ordre exact des
        # colonnes SQL pour afficher les données correctement.
        # AJOUT (roadmap, écosystème de capacités -- brique 2) :
        # champs masqués (règle 'hidden') retirés de la réponse,
        # après construction du dict nommé mais avant de le renvoyer
        # -- jamais retirés de la base, jamais visibles par personne
        # via cette route, quel que soit qui l'appelle (contrairement
        # à 'restrictedTo', qui autorise un acteur précis).
        masked = self.hidden_fields_by_entity.get(base_target, [])
        mask_literal = ", ".join(f"'{f}'" for f in masked)
        # AJOUT (roadmap, écosystème de capacités -- brique 5) :
        # champs 'categorized' remplacés par leur libellé de
        # catégorie, dans la même passe que le masquage ci-dessus —
        # un seul parcours par ligne pour les deux transformations.
        categorized_here = self.categorized_fields_by_entity.get(base_target, [])
        public_condition = access.public_condition
        condition_fragment = None
        # POINT 116 : QUI échappe à la condition. Sans exemption, 'publicWhen'
        # cachait le contenu filtré À TOUT LE MONDE — le modérateur qui venait
        # de masquer un post ne pouvait plus ni le lister ni le relire (404),
        # et l'auteur d'un brouillon ne retrouvait jamais son brouillon. Une
        # modération à sens unique, vérifiée contre un vrai serveur.
        #
        # Deux exemptions, toutes deux DÉCLARATIVES :
        #   - le SUPERVISEUR nommé par 'sharedBy' sur la même référence : le
        #     pendant exact du superviseur d'accessibleBy (brique 23,
        #     point 106) et d'ownedBy (point 88) — même mot-clé, même sens ;
        #   - le PROPRIÉTAIRE, par sa colonne d'identité (point 99) : il voit
        #     ses propres enregistrements quel que soit leur état.
        # Rien d'implicite : un rôle qui lit l'entité sans être déclaré
        # superviseur reste soumis à la condition, sinon « masqué » ne
        # voudrait plus rien dire dès qu'on est connecté.
        condition_supervisors, condition_owner_columns = (
            self._condition_exemptions(base_target))
        apply_condition_identity = bool(
            condition_supervisors or condition_owner_columns)
        if public_condition:
            condition_fragment = sql.cat(
                sql.ident(public_condition["field"]), sql.kw(" = "),
                sql.bind(repr(public_condition["value"])))
        # AJOUT (roadmap, brique "accès à deux parties") : si une
        # règle 'accessibleBy' cible Read, la liste ne renvoie que
        # les enregistrements dont l'appelant est l'une des parties
        # (WHERE col1 = ? OR col2 = ? ...), et la lecture par ID
        # vérifie l'appartenance avant de répondre. Comme pour
        # 'ownedBy', 'public' l'emporte si les deux sont déclarés
        # (pas d'identité appelante sur une route publique).
        read_parties = access.party_fields
        apply_read_parties = bool(read_parties) and not is_public
        read_supers = access.supervisors
        apply_read_super = bool(read_supers) and apply_read_parties
        read_dep_suffix = dep_suffix
        if apply_condition_identity:
            read_dep_suffix += ", _ident: dict = Depends(get_optional_identity)"
        parties_where = parties_params = ""
        if apply_read_parties:
            read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"
            parties_where = " OR ".join(f'\"{c}\" = ?' for c in read_parties)
            parties_params = ", ".join(["current_user_id"] * len(read_parties))

        # CORRECTIF (bêta 3, fuite de données entre comptes) : une règle
        # 'ownedBy' sur Read restreint désormais réellement la lecture.
        # Le filtre est construit à l'exécution parce qu'il dépend du
        # rôle de l'appelant : seul l'acteur désigné propriétaire est
        # limité à ses enregistrements ; un rôle tiers autorisé à lire
        # l'entité (gestionnaire, responsable) continue de tout voir.
        read_owner = access.owner_entity
        apply_read_owner = bool(read_owner) and not is_public and not apply_read_parties
        # AJOUT (brique 11, point 81) : sous propriété transitive, le
        # propriétaire nommé est une ENTITÉ, jamais une valeur que
        # `current_actor` puisse prendre — l'acteur à comparer est celui
        # du bout de la chaîne. Et le filtre devient une sous-requête
        # sur l'intermédiaire : comparer la colonne directement à
        # `current_user_id` mettrait en regard un id d'enregistrement et
        # un id de compte, ce qui était le défaut du point 80.
        chaine_lecture = self._transitive_chain(base_target) if apply_read_owner else None
        read_actor = own_where_sql = None
        if apply_read_owner:
            if chaine_lecture:
                read_actor = chaine_lecture["actor"]
                # Briques 11 et 24 : le filtre est un IN imbriqué par
                # maillon, quelle que soit la profondeur de la chaîne.
                # Le compte est lié (sql.bind), jamais collé dans le texte.
                own_where_sql = self._chain_read_where(
                    base_target, sql.bind("current_user_id"))
            else:
                read_actor = read_owner
                own_where_sql = sql.cat(
                    sql.kw(' WHERE '), sql.ident(f"{read_owner.lower()}_id"),
                    sql.kw(' = '), sql.bind("current_user_id"))
            if condition_fragment:
                own_where_sql = sql.cat(
                    own_where_sql, sql.kw(" AND "), condition_fragment)
            if ", current_user_id" not in read_dep_suffix:
                read_dep_suffix += ", current_user_id: int = Depends(get_current_user_id)"
        list_params = f"limit: int = 50, offset: int = 0{read_dep_suffix}"
        api_lines.append(f"@app.get('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def list_{base_target.lower()}({list_params}):")
        api_lines.append(security_check)
        api_lines.append("    limit = max(1, min(limit, 200))")
        api_lines.append("    offset = max(0, offset)")
        if apply_read_owner:
            api_lines.append("    _own_where, _own_params = '', ()")
            api_lines.append(f"    if current_actor == \"{read_actor}\":")
            api_lines.append(f"        _own_where = {own_where_sql.text!r}")
            api_lines.append(f"        _own_params = {sql.params_tuple(own_where_sql)}")
        elif apply_read_super:
            # Le superviseur voit tout (WHERE vide) ; les parties restent
            # confinees a leurs colonnes. Meme mecanisme conditionnel que la
            # branche ownedBy juste au-dessus.
            _superset = ", ".join(f'"{s}"' for s in read_supers)
            api_lines.append("    _own_where, _own_params = '', ()")
            api_lines.append(f"    if current_actor not in {{{_superset}}}:")
            api_lines.append(f"        _own_where = ' WHERE {parties_where}'")
            api_lines.append(f"        _own_params = ({parties_params},)")
        elif apply_condition_identity:
            # POINT 116 : le WHERE de 'publicWhen' se décide à l'exécution,
            # exactement comme les deux branches ci-dessus. Par défaut la
            # condition s'applique ; un superviseur déclaré la lève entièrement,
            # un propriétaire y AJOUTE ses propres lignes (OR), il ne la
            # remplace pas — sinon il perdrait le contenu public des autres.
            base_where = sql.cat(sql.kw(" WHERE "), condition_fragment)
            api_lines.append(f"    _own_where = {base_where.text!r}")
            api_lines.append(f"    _own_params = {sql.params_tuple(base_where)}")
            if condition_owner_columns:
                frags = [sql.kw(" WHERE ("), condition_fragment]
                for col in condition_owner_columns:
                    frags += [sql.kw(" OR "), sql.ident(col), sql.kw(" = "),
                              sql.bind("_ident.get('user_id')")]
                owner_where = sql.cat(*frags, sql.kw(")"))
                api_lines.append("    if _ident.get('user_id'):")
                api_lines.append(f"        _own_where = {owner_where.text!r}")
                api_lines.append(f"        _own_params = {sql.params_tuple(owner_where)}")
            if condition_supervisors:
                _condset = ", ".join(f'"{s}"' for s in condition_supervisors)
                api_lines.append(f"    if _ident.get('actor') in {{{_condset}}}:")
                api_lines.append("        _own_where, _own_params = '', ()")
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        if apply_read_owner or apply_read_super or apply_condition_identity:
            api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"' + _own_where, _own_params)")
            api_lines.append("    total = cursor.fetchone()[0]")
            api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\"' + _own_where + ' LIMIT ? OFFSET ?', _own_params + (limit, offset))")
        elif apply_read_parties:
            api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\" WHERE {parties_where}', ({parties_params},))")
        else:
            if condition_fragment:
                api_lines.append(
                    f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\" WHERE "
                    f"{condition_fragment.text}', {sql.params_tuple(condition_fragment)})")
            else:
                api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"')")
        if not (apply_read_owner or apply_read_super or apply_condition_identity):
            api_lines.append("    total = cursor.fetchone()[0]")
            if apply_read_parties:
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE {parties_where} LIMIT ? OFFSET ?', ({parties_params}, limit, offset))")
            elif condition_fragment:
                params = sql.params_tuple(condition_fragment)
                api_lines.append(
                    f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE "
                    f"{condition_fragment.text} LIMIT ? OFFSET ?', "
                    f"{params[:-1]}limit, offset))")
            else:
                api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" LIMIT ? OFFSET ?', (limit, offset))")
        api_lines.append("    rows = cursor.fetchall()")
        api_lines.append("    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)")
        api_lines.append("    conn.close()")
        api_lines.append("    named_rows = [dict(zip(_columns, row)) for row in rows]")
        row_loop_lines = []
        if masked:
            row_loop_lines.append(f"        for _f in [{mask_literal}]: _r.pop(_f, None)")
        for cf in categorized_here:
            row_loop_lines.extend(self._emit_categorization_lines(cf, "_r", "        "))
        if row_loop_lines:
            api_lines.append("    for _r in named_rows:")
            api_lines.extend(row_loop_lines)
        api_lines.append("    return {'status': 'success', 'total': total, 'limit': limit, 'offset': offset, 'data': named_rows}")
        api_lines.append("")

        api_lines.append(f"@app.get('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def read_{base_target.lower()}(id: int{read_dep_suffix}):")
        api_lines.append(security_check)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
        api_lines.append("    row = cursor.fetchone()")
        api_lines.append("    _columns = [d[0] for d in cursor.description]  # ordre réel en base (robuste aux migrations)")
        api_lines.append("    conn.close()")
        api_lines.append("    if not row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
        api_lines.append("    named_row = dict(zip(_columns, row))")
        if public_condition:
            # POINT 116 : mêmes exemptions qu'en liste, sans quoi le
            # superviseur listerait un enregistrement qu'il ne pourrait pas
            # ouvrir. 404 et jamais 403 pour les autres : sur des identifiants
            # séquentiels, distinguer « n'existe pas » de « masqué » laisserait
            # dénombrer ce qui a été retiré.
            garde = (f"    if named_row.get({public_condition['field']!r}) != "
                     f"{public_condition['value']!r}")
            if apply_condition_identity:
                exemptions = []
                if condition_supervisors:
                    _condset = ", ".join(f'"{s}"' for s in condition_supervisors)
                    exemptions.append(f"_ident.get('actor') in {{{_condset}}}")
                for col in condition_owner_columns:
                    exemptions.append(
                        f"(_ident.get('user_id') and named_row.get({col!r}) "
                        f"== _ident.get('user_id'))")
                garde += " and not (" + " or ".join(exemptions) + ")"
            api_lines.append(
                garde + ": raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
        if apply_read_owner:
            # 404 et non 403 : sur une entité dont les identifiants sont
            # séquentiels, un 403 confirmerait l'existence de
            # l'enregistrement d'autrui — il suffirait d'énumérer les
            # identifiants pour compter les dépenses ou les commandes
            # d'un tiers. Un enregistrement qu'on n'a pas le droit de
            # lire doit être indiscernable d'un enregistrement absent.
            if chaine_lecture:
                # Une seule sous-requête scalaire remonte toute la chaîne
                # jusqu'au compte, quelle que soit sa profondeur. Un
                # maillon absent rend NULL donc « appartient à personne »,
                # et 404 est la bonne réponse pour les deux cas.
                _owner_q = self._chain_owner_scalar(
                    base_target,
                    sql.bind(f"named_row.get('{chaine_lecture['via_fk']}')"))
                _sql_lit, _params_lit = sql.execute_args(_owner_q, prefix="SELECT ")
                api_lines += [
                    f"    if current_actor == \"{read_actor}\":",
                    "        _tc = _connect(); _tcur = _tc.cursor()",
                    f"        _tcur.execute({_sql_lit}, {_params_lit})",
                    "        _tr = _tcur.fetchone(); _tc.close()",
                    "        if not _tr or _tr[0] is None or _tr[0] != current_user_id:",
                    "            raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                ]
            else:
                api_lines.append(f"    if current_actor == \"{read_actor}\" and "
                                 f"named_row.get('{read_owner.lower()}_id') != current_user_id:")
                api_lines.append("        raise HTTPException(status_code=404, detail='Enregistrement introuvable')")
        if apply_read_parties:
            # La vérification se fait AVANT le masquage 'hidden' :
            # une colonne de partie peut légitimement être masquée
            # en lecture tout en servant au contrôle d'accès.
            parties_tuple = ", ".join(f"named_row.get('{c}')" for c in read_parties)
            if apply_read_super:
                _superset = ", ".join(f'"{s}"' for s in read_supers)
                api_lines.append(f"    if current_actor not in {{{_superset}}}:")
                api_lines.append(f"        if current_user_id not in ({parties_tuple}):")
                api_lines.append("            raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")")
            else:
                api_lines.append(f"    if current_user_id not in ({parties_tuple}):")
                api_lines.append("        raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")")
        if masked:
            api_lines.append(f"    for _f in [{mask_literal}]: named_row.pop(_f, None)")
        for cf in categorized_here:
            api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
        api_lines.append("    return {'status': 'success', 'data': named_row}")
        api_lines.append("")

        return api_lines

    def _generate_update_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Update``."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        # AJOUT (post-v6, roadmap) : si une règle 'ownedBy' cible cette
        # action, un contrôle supplémentaire vérifie que l'acteur courant
        # est bien le propriétaire de l'enregistrement, en plus du
        # contrôle de rôle habituel.
        owner_entity = access.owner_entity
        # 'ownedBy' suppose une identité appelante (current_actor) —
        # incompatible avec une route 'public', qui n'en a aucune.
        # Si les deux sont déclarées sur la même action, 'public'
        # l'emporte : la route reste ouverte, sans contrôle de
        # propriété (voir docs/design_decisions.md).
        apply_ownership = owner_entity and not is_public
        # AJOUT (roadmap, brique "accès à deux parties") : même
        # principe que 'ownedBy' mais l'appelant doit être l'UNE des
        # colonnes-parties listées. Contrairement à 'ownedBy', le
        # contrôle s'applique à tous les acteurs de la route, sauf à
        # un rôle SUPERVISEUR déclaré via sharedBy sur la même
        # référence (brique 23, point 106) — celui-là transperce le
        # contrôle et modifie tous les enregistrements.
        update_parties = access.party_fields
        apply_update_parties = bool(update_parties) and not is_public
        update_supers = access.supervisors
        apply_update_super = bool(update_supers) and apply_update_parties
        update_deps = dependency_injection
        ownership_check_lines = []
        if apply_update_parties:
            update_deps += ", current_user_id: int = Depends(get_current_user_id)" if update_deps else "current_user_id: int = Depends(get_current_user_id)"
            cols_literal = ", ".join(f'\"{c}\"' for c in update_parties)
            ownership_check_lines = [
                "    _p_conn = _connect(); _p_cur = _p_conn.cursor()",
                f"    _p_cur.execute('SELECT {cols_literal} FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                "    _p_row = _p_cur.fetchone(); _p_conn.close()",
                "    if not _p_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
            ]
            if apply_update_super:
                _superset = ", ".join(f'"{s}"' for s in update_supers)
                ownership_check_lines.append(f"    if current_actor not in {{{_superset}}}:")
                ownership_check_lines.append("        if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")")
            else:
                ownership_check_lines.append("    if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")")
        elif apply_ownership:
            check_actor, owner_select = self._owner_lookup_sql(base_target, owner_entity)
            update_deps += ", current_user_id: int = Depends(get_current_user_id)" if update_deps else "current_user_id: int = Depends(get_current_user_id)"
            # CORRECTIF (roadmap, combinaison ownedBy + sharedBy) : si
            # cette route est partagée par plusieurs acteurs (ex. un
            # 'Agent' qui gère tous les tickets, en plus du 'Customer'
            # propriétaire), le contrôle de propriété ne doit s'appliquer
            # qu'à l'acteur explicitement désigné comme propriétaire par
            # la règle 'ownedBy' — pas aux autres acteurs qui partagent
            # la route par ailleurs via leur propre rôle. Sans cette
            # condition, un acteur légitimement privilégié (Agent) se
            # retrouverait bloqué à tort, puisqu'il ne "possède" jamais
            # la ressource au sens de la relation hasMany/belongsTo.
            ownership_check_lines = [
                f"    if current_actor == \"{check_actor}\":",
                "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                f"        _owner_cur.execute({owner_select.text!r}, {sql.params_tuple(owner_select)})",
                "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                "        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
            ]

        update_deps_suffix = f", {update_deps}" if update_deps else ""
        api_lines.append(f"@app.put('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def update_{base_target.lower()}(id: int, data: {base_target}Schema{update_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.extend(ownership_check_lines)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        # BRIQUE 18 (point 91) : un enregistrement encaissé est FIGÉ.
        # La garde est posée avant toute lecture et tout calcul.
        if self._payment_lock_field(base_target):
            api_lines += self._payment_lock_lines(
                base_target.lower(), "id", base_target)
        # …et une ligne d'une commande réglée l'est tout autant : c'est
        # par elle que le total remontait à 594 € après un règlement de
        # 89 €. Le parent est relu EN BASE depuis la clé étrangère
        # STOCKÉE, jamais `data.<fk>` — cette route n'écrit pas les clés
        # étrangères, donc le corps de requête peut désigner une autre
        # commande que celle à laquelle la ligne appartient (leçon du
        # point 78).
        for verrou in self._payment_locked_parents(base_target):
            lien = f"_verrou_{verrou['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{verrou['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {lien} = cursor.fetchone()",
                f"    if {lien} and {lien}[0] is not None:",
            ]
            api_lines += self._payment_lock_lines(
                verrou["table"], f"{lien}[0]", verrou["entity"],
                indent="        ", var="_parent_regle")
        fields = list(self.entities[base_target].keys())
        # CORRECTIF (point 78) : un champ 'generated' n'est PAS dans le
        # schéma Pydantic, et cette route lisait pourtant `data.<champ>`
        # pour TOUS les attributs -- donc 500 (AttributeError) sur toute
        # entité combinant 'generated' et 'Update'. Latent jusqu'ici :
        # aucun exemple ne les combinait. Un champ peuplé par le serveur
        # n'a pas à être réécrit depuis le corps de requête ; l'exclure
        # préserve aussi sa valeur (le pseudonyme ne doit pas changer).
        generated_upd = self.generated_fields_by_entity.get(base_target, [])
        # AJOUT (brique 10, point 77) : un champ 'derivedFrom' est
        # RECALCULÉ ici. Le laisser tel quel déplacerait simplement la
        # faille : créer à quantité 1 puis modifier à quantité 5 sans
        # recalcul donnerait cinq articles au prix d'un.
        derives_upd = self.derived_by_entity.get(base_target, [])
        noms_derives = {r["field"] for r in derives_upd}
        for regle in derives_upd:
            fk_col = self._derived_source_fk(base_target,
                                             regle["source_entity"])
            champ = regle["field"]
            api_lines += [
                # La ligne liée est celle STOCKÉE, relue en base — jamais
                # celle que le corps de requête déclare. Les deux sens ont
                # été essayés contre un serveur réel : cette route n'écrit
                # pas les colonnes de clé étrangère, donc la FK en base est
                # la seule vérité sur « quel article ». Calculer depuis
                # `data.<fk>` laissait un client abaisser le montant en
                # déclarant un article bon marché qu'il ne pointait pas
                # (189 € facturés 89 €, vérifié).
                f"    cursor.execute('SELECT \"{fk_col}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    _lien_{champ} = cursor.fetchone()",
                f"    if not _lien_{champ}:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                f"    cursor.execute('SELECT \"{regle['source_field']}\" FROM "
                f'"{regle["source_entity"].lower()}" WHERE id = ?\', '
                f"(_lien_{champ}[0],))",
                f"    _src_{champ} = cursor.fetchone()",
                f"    if not _src_{champ}:",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            '{regle['source_entity']} introuvable : impossible de recalculer "
                f"{champ}.'))",
                f"    if data.{regle['factor']} <= 0:",
                "        conn.close()",
                "        raise HTTPException(status_code=400, detail=(",
                "            'La quantité doit être strictement positive.'))",
                f"    _calcul_{champ} = round(float(_src_{champ}[0] or 0) "
                f"* int(data.{regle['factor']}), 2)",
            ]
        # AJOUT (brique 12, point 82) : un champ 'sumOf' n'est pas dans
        # `data` et n'a rien à faire dans le SET — le réécrire depuis la
        # requête serait rendre au client le total qu'on vient de lui
        # retirer, et lire `data.<champ>` donnerait 500 (le défaut du
        # point 78, sur une autre brique).
        sommes_upd = set(self._aggregated_field_names(base_target))
        # AJOUT (brique 16, point 89) : l'instant de création est écrit
        # à la création, un point c'est tout. L'exclure du SET est ce
        # qui le rend digne de foi ; l'y laisser aurait en plus donné
        # 500 (`data.<champ>` absent du schéma), le défaut du point 78.
        horodates_upd = set(self.timestamp_fields_by_entity.get(base_target, []))
        # BRIQUE 22 (point 102) : un numéro de commande qui change n'est
        # plus une référence — le client l'a noté, le vendeur aussi.
        horodates_upd |= {n["field"] for n
                          in self.numbered_fields_by_entity.get(base_target, [])}
        # Même exclusion sur l'Update générique : ces champs n'existent
        # pas dans son schéma Pydantic et ne s'écrivent que par la route
        # dédiée au superviseur.
        postpaiement_upd = set(
            self.postpayment_writable_by_entity.get(
                base_target, {}).get("fields", []))
        ecrits = [f for f in fields
                  if f not in generated_upd and f not in sommes_upd
                  and f not in horodates_upd
                  and f not in postpaiement_upd]
        # POINT 85 : les écritures sont rassemblées AVANT d'être émises,
        # pour pouvoir les envelopper d'un try quand l'entité porte un
        # 'unique'. C'est SQLite qui lève à l'`execute`, pas au `commit` —
        # une garde autour du seul commit donnait 500 (vérifié contre un
        # vrai serveur, pas déduit).
        lignes_ecriture = []
        # BRIQUE 20 (point 98) : atteindre une valeur DÉFAIT un effet.
        # Annuler une commande la passait en « annulée » et gardait ses
        # lignes : le stock restait consommé. La restitution existait
        # depuis le point 92, mais seulement à la SUPPRESSION — ce qui
        # efface l'historique, et un marchand veut les deux.
        #
        # LE point de la brique : ne rendre QU'UNE FOIS. L'état est lu
        # AVANT l'écriture, et la libération n'a lieu que sur la
        # TRANSITION — deux PUT successifs à « annulée » rendraient
        # sinon le stock deux fois, et la boutique s'inventerait des
        # paires. C'est ce que seul un vrai serveur montre.
        for regle in self.release_rules_by_entity.get(base_target, []):
            enfant = regle["releases"]
            fk_enfant = next(
                (p["fk_column"] for p
                 in self._compute_fk_placements().get(enfant, [])
                 if p["owner_entity"] == base_target), None)
            if not fk_enfant:
                continue
            # L'état est lu AVANT la transaction : le refus qui suit doit
            # pouvoir fermer la connexion, ce que le `except
            # IntegrityError` des écritures ne ferait pas pour lui.
            api_lines += [
                f"    cursor.execute('SELECT \"{regle['field']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "    _etat_avant = cursor.fetchone()",
                # LE trou que la première version laissait ouverte :
                # annuler rendait le stock, puis RÉACTIVER la commande la
                # laissait vivante sans rien consommer — du stock gratuit,
                # de la même famille que les exploits du point 77. Le
                # reprendre au retour supposerait qu'il soit encore
                # disponible, ce que rien ne garantit : l'état libéré est
                # donc TERMINAL, et le message dit quoi faire à la place.
                f"    if (_etat_avant and _etat_avant[0] == {regle['value']!r}",
                f"            and data.{regle['field']} != {regle['value']!r}):",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                f"            \"Cet enregistrement est {regle['value']} : ce qu'il "
                f"avait consommé a été rendu, \"",
                "            'et rien ne garantit que ce soit encore disponible. "
                "En créer un nouveau.'))",
                f"    _bascule = (_etat_avant and _etat_avant[0] != {regle['value']!r}",
                f"                and data.{regle['field']} == {regle['value']!r})",
            ]
            lignes_ecriture.append("if _bascule:")
            for decompte in self.reputation_rules_by_trigger.get(enfant, []):
                if decompte["direction"] != "decrements":
                    continue
                fk_cible = self._decrement_fk_column(enfant, decompte)
                if not fk_cible:
                    continue
                champ = decompte.get("amount_field")
                quantite = "_l[1]" if champ else str(decompte["amount"])
                colonnes = (f'"{fk_cible}", "{champ}"' if champ
                            else f'"{fk_cible}"')
                lignes_ecriture += [
                    f"    cursor.execute('SELECT {colonnes} FROM "
                    f'"{enfant.lower()}" WHERE "{fk_enfant}" = ?\', (id,))',
                    "    for _l in cursor.fetchall():",
                    # Aucun plancher : on rend un état qui a existé et
                    # qui était valide (même raison qu'au point 92).
                    f"        cursor.execute('UPDATE "
                    f'"{decompte["target_entity"].lower()}" SET '
                    f'"{decompte["target_field"]}" = "{decompte["target_field"]}" '
                    f"+ ? WHERE id = ?', (int({quantite} or 0), _l[0]))",
                ]
        # BRIQUE 19 (point 91) : le décompte suit la quantité MODIFIÉE.
        # `decrements` ne s'armait qu'à la création : créer une ligne à 1
        # puis la passer à 4 facturait quatre paires et n'en décomptait
        # qu'une (vérifié — stock 16 -> 15 pour 528 € facturés). C'est le
        # défaut du point 78 déplacé de l'argent vers la marchandise.
        #
        # On applique le DELTA, pas la nouvelle quantité : la ligne a
        # déjà consommé son ancienne valeur. Un delta négatif rend du
        # stock, et la condition `>= plancher` reste vraie — inutile de
        # traiter les deux sens séparément. Quantité et clé étrangère
        # sont relues EN BASE : cette route n'écrit pas les clés
        # étrangères (point 78 encore).
        # CORRECTIF (point 92) : cette boucle lisait `reputation_rules_here`,
        # variable de la branche `Create` — donc les règles de la DERNIÈRE
        # entité créée, pas de celle qu'on modifie. Deux conséquences, les
        # deux vérifiées : une spec qui a un `Update` sans aucun `Create`
        # faisait PLANTER le compilateur (variable jamais assignée), et un
        # `Update` précédé de la création d'une AUTRE entité héritait de ses
        # règles — modifier un avis décomptait le stock d'un produit. Le
        # défaut est né avec le décompte au PUT (point 91) : une branche
        # qui lit la variable d'une autre marche tant que l'ordre des
        # routes les met côte à côte.
        for rule in self.reputation_rules_by_trigger.get(base_target, []):
            if not rule.get("amount_field"):
                continue  # décompte d'une constante : rien ne varie
            plancher = (self.field_constraints.get(rule["target_entity"], {})
                        .get(rule["target_field"], {}).get("min"))
            if plancher is None or rule["direction"] != "decrements":
                continue  # sans plancher déclaré, rien à garantir (point 86)
            fk_cible = self._decrement_fk_column(base_target, rule)
            if not fk_cible:
                continue
            champ = rule["amount_field"]
            cible = rule["target_entity"].lower()
            vise = rule["target_field"]
            lignes_ecriture += [
                f"cursor.execute('SELECT \"{champ}\", \"{fk_cible}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                "_avant = cursor.fetchone()",
                "if _avant and _avant[1] is not None:",
                f"    _delta = int(data.{champ}) - int(_avant[0] or 0)",
                "    if _delta != 0:",
                f"        cursor.execute('UPDATE \"{cible}\" SET \"{vise}\" = "
                f'"{vise}" - ? WHERE id = ? AND "{vise}" - ? >= ?\', '
                "(_delta, _avant[1], _delta, "
                f"{plancher['valeur']}))",
                "        if cursor.rowcount == 0:",
                "            conn.rollback(); conn.close()",
                "            raise HTTPException(status_code=409, detail=(",
                f"                '{rule['target_entity']}.{vise} insuffisant : "
                f"la quantité demandée dépasse ce qui reste disponible.'))",
            ]
        if ecrits:
            update_stmt = ", ".join([f'"{f}" = ?' for f in ecrits])
            lignes_ecriture.append(f"query = 'UPDATE \"{base_target.lower()}\" SET {update_stmt} WHERE id = ?'")
            values_list = ", ".join([
                f"_calcul_{f}" if f in noms_derives else f"data.{f}"
                for f in ecrits
            ])
            lignes_ecriture.append(f"cursor.execute(query, ({values_list}, id))")
        else:
            # Entité dont TOUS les attributs sont peuplés par le serveur :
            # « SET  WHERE id = ? » serait du SQL invalide. Rien à écrire
            # n'est un succès, pas une erreur.
            lignes_ecriture.append("pass  # aucun champ modifiable par le client")
        # AJOUT (brique 12, point 82) : le total du parent suit la ligne
        # modifiée. Le parent est relu EN BASE, jamais pris dans le corps
        # de requête — la route Update n'écrit pas les clés étrangères,
        # donc `data.<fk>` peut désigner un parent auquel cette ligne
        # n'appartient pas : on recalculerait le total d'une autre
        # commande, et pas celui de la vraie. Exactement la leçon du
        # point 78, sur une autre brique.
        for recalcul in self._aggregation_recomputes(base_target):
            var = f"_parent_{recalcul['fk_column']}"
            lignes_ecriture += [
                f"cursor.execute('SELECT \"{recalcul['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"{var} = cursor.fetchone()",
                f"if {var}:",
                f"    cursor.execute({recalcul['sql']!r}, ({var}[0], {var}[0]))",
            ]
        # POINT 85 : la route Update n'écrivait AUCUNE clé étrangère, donc
        # elle ne pouvait pas lever d'IntegrityError — d'où l'absence de
        # garde jusqu'ici. 'unique' change ça : un PUT qui duplique une
        # valeur unique donnait 500 et laissait la connexion ouverte.
        # Garde posée seulement quand l'entité porte un 'unique', pour que
        # la sortie reste identique partout ailleurs.
        uniques_upd = self._unique_fields(base_target)
        if uniques_upd:
            api_lines.append("    try:")
            api_lines += [f"        {ligne}" for ligne in lignes_ecriture]
            api_lines.append("        conn.commit()")
            api_lines.append("    except _DATABASE_INTEGRITY_ERRORS:")
            api_lines.append("        conn.rollback(); conn.close()")
            api_lines.append("        raise HTTPException(status_code=409, detail=(")
            api_lines.append(
                f"            'Valeur déjà utilisée : {', '.join(uniques_upd)} "
                f"doit être unique.'))")
            api_lines.append("    conn.close()")
        else:
            api_lines += [f"    {ligne}" for ligne in lignes_ecriture]
            api_lines.append("    conn.commit(); conn.close()")
        api_lines.append("    return {'status': 'success', 'id': id}")
        api_lines.append("")

        return api_lines

    def _generate_delete_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Delete``."""
        api_lines = []
        base_target = context["base_target"]
        tag = context["tag"]
        access = context["access"]
        is_public = context["is_public"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        owner_entity = access.owner_entity
        apply_ownership = owner_entity and not is_public
        # AJOUT (roadmap, brique "accès à deux parties") — voir le
        # commentaire équivalent sur la route Update.
        delete_parties = access.party_fields
        apply_delete_parties = bool(delete_parties) and not is_public
        delete_supers = access.supervisors
        apply_delete_super = bool(delete_supers) and apply_delete_parties
        delete_deps = dependency_injection
        ownership_check_lines = []
        if apply_delete_parties:
            delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
            cols_literal = ", ".join(f'\"{c}\"' for c in delete_parties)
            ownership_check_lines = [
                "    _p_conn = _connect(); _p_cur = _p_conn.cursor()",
                f"    _p_cur.execute('SELECT {cols_literal} FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                "    _p_row = _p_cur.fetchone(); _p_conn.close()",
                "    if not _p_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
            ]
            if apply_delete_super:
                _superset = ", ".join(f'"{s}"' for s in delete_supers)
                ownership_check_lines.append(f"    if current_actor not in {{{_superset}}}:")
                ownership_check_lines.append("        if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")")
            else:
                ownership_check_lines.append("    if current_user_id not in _p_row: raise HTTPException(status_code=403, ")
                ownership_check_lines.append("        detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")")
        elif apply_ownership:
            check_actor, owner_select = self._owner_lookup_sql(base_target, owner_entity)
            delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
            # Voir le commentaire équivalent dans le bloc "Update" ci-dessus :
            # le contrôle de propriété ne s'applique qu'à l'acteur
            # explicitement désigné comme propriétaire par 'ownedBy'.
            ownership_check_lines = [
                f"    if current_actor == \"{check_actor}\":",
                "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                f"        _owner_cur.execute({owner_select.text!r}, {sql.params_tuple(owner_select)})",
                "        _owner_row = _owner_cur.fetchone(); _owner_conn.close()",
                "        if not _owner_row: raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                "        if _owner_row[0] != current_user_id: raise HTTPException(status_code=403, "
                "detail=\"Contrôle d'accès : seul le propriétaire de la ressource peut exécuter cette action\")",
            ]

        delete_deps_suffix = f", {delete_deps}" if delete_deps else ""
        api_lines.append(f"@app.delete('/{base_target.lower()}/{{id}}', tags=['{tag}'])")
        api_lines.append(f"def delete_{base_target.lower()}(id: int{delete_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.extend(ownership_check_lines)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        # POINT 96 : le pendant de `requiresOwn` à la SUPPRESSION. La
        # règle garde la création depuis le point 90 ; rien n'empêchait
        # ensuite de supprimer sa fiche et de laisser la commande sans
        # destinataire — vérifié sur `projets/SneakerLab` : 1 commande,
        # 0 fiche. Le contrôle porte sur la DERNIÈRE fiche seulement :
        # `requiresOwn` exige « au moins une », donc supprimer
        # l'avant-dernière reste légitime.
        dependantes = self._profile_dependents(base_target)
        col_compte = self._profile_account_column(base_target)
        if dependantes and col_compte:
            api_lines += [
                f"    cursor.execute('SELECT COUNT(*) FROM "
                f'"{base_target.lower()}" WHERE "{col_compte}" = ?\', '
                "(current_user_id,))",
                "    _restantes = cursor.fetchone()[0] - 1",
                "    if _restantes <= 0:",
            ]
            for nom, table, colonne in dependantes:
                api_lines += [
                    f"        cursor.execute('SELECT COUNT(*) FROM "
                    f'"{table}" WHERE "{colonne}" = ?\', (current_user_id,))',
                    "        _dep = cursor.fetchone()[0]",
                    "        if _dep:",
                    "            conn.close()",
                    "            raise HTTPException(status_code=409, detail=(",
                    # Le nom de l'entité tel que la SPEC l'écrit :
                    # c'est le vocabulaire que l'auteur du projet
                    # reconnaît, et celui du contrat frontend.
                    f"                f'Suppression impossible : {{_dep}} "
                    f"enregistrement(s) {nom} dépendent de cette fiche. '",
                    "                'Sans elle, ils ne seraient plus rattachés à "
                    "personne.'))",
                ]
        # BRIQUE 18 (point 91) : supprimer efface la trace d'un
        # encaissement. Le 409 que renvoyait la clé étrangère ne
        # protégeait rien — il suffisait de retirer les lignes d'abord,
        # et la commande réglée disparaissait de la base (vérifié).
        if self._payment_lock_field(base_target):
            api_lines += self._payment_lock_lines(
                base_target.lower(), "id", base_target)
        for verrou in self._payment_locked_parents(base_target):
            lien = f"_verrou_{verrou['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{verrou['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {lien} = cursor.fetchone()",
                f"    if {lien} and {lien}[0] is not None:",
            ]
            api_lines += self._payment_lock_lines(
                verrou["table"], f"{lien}[0]", verrou["entity"],
                indent="        ", var="_parent_regle")
        # CORRECTIF (bêta 3) : les clés étrangères sont désormais
        # réellement appliquées (PRAGMA foreign_keys), donc supprimer un
        # enregistrement encore référencé lève une IntegrityError. On la
        # traduit en 409 explicite plutôt qu'en 500 : c'est une erreur du
        # client (ordre de suppression), pas une panne du serveur.
        # AJOUT (brique 12, point 82) : le parent est lu AVANT la
        # suppression — après, la ligne n'existe plus et sa clé étrangère
        # avec elle, donc plus rien ne dit quel total recalculer. Retirer
        # un article d'un panier sans faire redescendre le total est
        # précisément le cas où la somme mentirait, et sur une entité
        # 'payable' on encaisserait un article rendu.
        recalculs_del = self._aggregation_recomputes(base_target)
        for recalcul in recalculs_del:
            var = f"_parent_{recalcul['fk_column']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{recalcul['fk_column']}\" FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {var} = cursor.fetchone()",
            ]
        # BRIQUE 15 (point 92) : la suppression DÉFAIT le décompte. Le
        # troisième branchement, celui qu'on oublie — le point 82 l'avait
        # nommé pour l'agrégation et l'avait traité ; le décompte, lui, ne
        # s'armait qu'à la création (point 86) puis à la modification
        # (point 91), jamais à la suppression. Mesuré sur SneakerLab :
        # commander trois paires puis vider son panier laissait le stock à
        # 9 sur 12. Le total du parent, lui, redescendait bien à zéro —
        # une base qui se contredit elle-même, et un catalogue qui
        # s'épuise sans qu'une seule paire soit vendue.
        #
        # La restitution ne porte AUCUN garde-fou de plancher, et c'est
        # voulu : elle rend un état qui a existé et qui était valide. Un
        # `decrements` rendu ne fait que remonter, un `increments` repris
        # ne redescend pas plus bas que la valeur d'avant la création.
        # Refuser une suppression pour cause de plancher interdirait
        # d'annuler une commande — exactement ce qu'on répare ici.
        restitutions = []
        for indice, rule in enumerate(
                self.reputation_rules_by_trigger.get(base_target, [])):
            fk_cible = self._decrement_fk_column(base_target, rule)
            if not fk_cible:
                continue
            var = f"_rendu_{indice}"
            champ = rule.get("amount_field")
            # La quantité et la clé étrangère sont lues AVANT le DELETE :
            # après, la ligne n'existe plus et rien ne dit quoi rendre ni
            # à qui. Même raison qu'au point 82, deux lignes plus haut.
            colonnes = f'"{champ}", "{fk_cible}"' if champ else f'"{fk_cible}"'
            api_lines += [
                f"    cursor.execute('SELECT {colonnes} FROM "
                f'"{base_target.lower()}" WHERE id = ?\', (id,))',
                f"    {var} = cursor.fetchone()",
            ]
            restitutions.append({
                "var": var,
                # Décompter, c'est retrancher : rendre, c'est ajouter.
                "op": "+" if rule["direction"] == "decrements" else "-",
                "table": rule["target_entity"].lower(),
                "champ": rule["target_field"],
                "montant": (f"int({var}[0] or 0)" if champ
                            else str(rule["amount"])),
                "fk_index": 1 if champ else 0,
            })
        api_lines.append("    try:")
        api_lines.append(f"        cursor.execute('DELETE FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
        for recalcul in recalculs_del:
            var = f"_parent_{recalcul['fk_column']}"
            api_lines += [
                f"        if {var}:",
                f"            cursor.execute({recalcul['sql']!r}, ({var}[0], {var}[0]))",
            ]
        for rendu in restitutions:
            var = rendu["var"]
            api_lines += [
                f"        if {var} and {var}[{rendu['fk_index']}] is not None:",
                f"            cursor.execute('UPDATE \"{rendu['table']}\" SET "
                f'"{rendu["champ"]}" = "{rendu["champ"]}" {rendu["op"]} ? '
                f"WHERE id = ?', ({rendu['montant']}, {var}[{rendu['fk_index']}]))",
            ]
        api_lines.append("        conn.commit()")
        api_lines.append("    except _DATABASE_INTEGRITY_ERRORS:")
        api_lines.append("        conn.rollback(); conn.close()")
        api_lines.append("        raise HTTPException(status_code=409, detail=(")
        api_lines.append("            \"Suppression impossible : cet enregistrement est encore référencé \"")
        api_lines.append("            'par des données liées. Supprimez-les d\\'abord.'")
        api_lines.append("        ))")
        api_lines.append("    conn.close()")
        api_lines.append("    return {'status': 'success', 'id': id}")
        api_lines.append("")

        return api_lines

    def _generate_execute_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Execute``."""
        api_lines = []
        target = context["target"]
        tag = context["tag"]
        security_check = context["security_check"]
        dependency_injection = context["dependency_injection"]
        api_lines.append(f"@app.post('/workflow/{tag.lower()}/{target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
        api_lines.append(security_check)
        # CORRECTIF (point 85) : `.dict()` est DÉPRÉCIÉ en Pydantic v2 et
        # sera retiré en v3 — vérifié en le déclenchant. Tout backend
        # généré portant un bloc 'custom' aurait cessé de fonctionner à
        # la première installation sur Pydantic 3, sans que rien dans le
        # dépôt ne le signale (aucun exemple, aucun test n'exerçait ce
        # chemin : c'est le trou de couverture qui l'a fait trouver).
        api_lines.append(f"    result = sandbox_ai.{target}(payload.model_dump())")
        api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
        api_lines.append("")

        return api_lines
    def _generate_postpayment_routes(self):
        lignes = []
        for entite, config in sorted(self.postpayment_writable_by_entity.items()):
            table = entite.lower()
            schema = f"{entite}ApresPaiementSchema"
            lignes += ["", f"class {schema}(BaseModel):"]
            for field in config["fields"]:
                field_type = self.entities[entite][field]
                py_type = "str"
                if field_type == "Integer":
                    py_type = "int"
                elif field_type in ("Float", "Money"):
                    py_type = "float"
                elif field_type == "Boolean":
                    py_type = "bool"
                choix = self.enumerated_fields.get(entite, {}).get(field)
                if choix:
                    valeurs = ", ".join(repr(v) for v in choix)
                    py_type = f"Literal[{valeurs}]"
                contraintes = self.field_constraints.get(entite, {}).get(field, {})
                bornes = []
                for nom, mot_texte, mot_nombre in (("min", "min_length", "ge"),
                                                    ("max", "max_length", "le")):
                    borne = contraintes.get(nom)
                    if borne:
                        mot = mot_texte if borne["portee"] == "longueur" else mot_nombre
                        bornes.append(f"{mot}={borne['valeur']}")
                if py_type == "str":
                    limite = {"Text": 20000, "Email": 320, "UUID": 36}.get(
                        field_type, 255)
                    if not any(b.startswith("max_length=") for b in bornes):
                        bornes.append(f"max_length={limite}")
                    if field_type == "Email":
                        bornes.append(r"pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'")
                    if field_type == "UUID":
                        bornes.append(
                            r"pattern=r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'")
                if bornes and not choix:
                    lignes.append(
                        f"    {field}: Optional[{py_type}] = Field(None, {', '.join(bornes)})")
                else:
                    lignes.append(f"    {field}: Optional[{py_type}] = None")

            existence = sql.cat(
                sql.kw("SELECT id, "), sql.ident("payment_status"),
                sql.kw(" FROM "), sql.ident(table),
                sql.kw(" WHERE id = "), sql.bind("id"))
            existence_sql, existence_params = sql.execute_args(existence)
            lignes += [
                "",
                f"@app.put('/{table}/{{id}}/apres-paiement', tags=['Paiement'])",
                f"def modifier_{table}_apres_paiement(id: int, data: {schema}, "
                "current_actor: str = Depends(verify_jwt_and_get_actor)):",
                f"    if current_actor != {config['actor']!r}:",
                "        raise HTTPException(status_code=403, detail=(",
                "            \"Contrôle d'accès : seules les parties de la ressource \"",
                "            'peuvent exécuter cette action'))",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute({existence_sql}, {existence_params})",
                "    enregistrement = cursor.fetchone()",
                "    if not enregistrement:",
                "        conn.close()",
                "        raise HTTPException(status_code=404, detail='Enregistrement introuvable')",
                "    if enregistrement[1] != 'payee':",
                "        conn.close()",
                "        raise HTTPException(status_code=409, detail=(",
                "            'Action disponible uniquement après confirmation du paiement'))",
            ]
            for field in config["fields"]:
                update = sql.cat(
                    sql.kw("UPDATE "), sql.ident(table), sql.kw(" SET "),
                    sql.ident(field), sql.kw(" = "), sql.bind(f"data.{field}"),
                    sql.kw(" WHERE id = "), sql.bind("id"))
                update_sql, update_params = sql.execute_args(update)
                lignes += [
                    f"    if data.{field} is not None:",
                    f"        cursor.execute({update_sql}, {update_params})",
                ]
            lignes += [
                "    conn.commit(); conn.close()",
                "    return {'status': 'success', 'id': id}",
                "",
            ]
        return lignes

    # ─────────────────────────────────────────────────────────────────
    # BRIQUE PAIEMENT (point 74). Deux routes seulement, et un principe :
    # le montant encaissé vient de la BASE, jamais du client. Un panier
    # qui envoie son propre prix est un panier qu'on peut négocier.
    #
    # Les secrets viennent de l'environnement (même règle que le secret
    # JWT). Absents, les routes existent mais répondent 503 en nommant la
    # variable manquante : un paiement doit refuser bruyamment, jamais
    # échouer en silence — et le smoke test reste vert hors ligne.
    # ─────────────────────────────────────────────────────────────────
    def _generate_payment_routes(self):
        if not self.payable_by_entity:
            return []
        lignes = [
            "",
            "# ── Paiement (brique 'payable') ──────────────────────────────",
            "STRIPE_SECRET_KEY = (os.environ.get('STRIPE_SECRET_KEY') or '').strip()",
            "STRIPE_WEBHOOK_SECRET = (os.environ.get('STRIPE_WEBHOOK_SECRET') or '').strip()",
            "# Point de terminaison surchargeable : indispensable pour éprouver",
            "# le parcours complet sans appeler Stripe (voir tests).",
            "STRIPE_BASE_URL = (os.environ.get('MONL_STRIPE_BASE_URL')",
            "                   or 'https://api.stripe.com').rstrip('/')",
            "",
            "def _exiger_cle_paiement(nom, valeur):",
            "    if not valeur:",
            "        raise HTTPException(status_code=503, detail=(",
            "            f\"Paiement indisponible : la variable d'environnement {nom} n'est pas \"",
            "            'définie sur le serveur. Aucun règlement ne peut être accepté tant '",
            "            \"qu'elle manque.\"))",
            "",
            "def _session_paiement(montant_centimes, devise, reference, retour):",
            "    \"\"\"Crée une session de règlement. Le montant est en CENTIMES,",
            "    calculé côté serveur depuis la base.\"\"\"",
            "    corps = urllib.parse.urlencode({",
            "        'mode': 'payment',",
            "        'success_url': retour + '?paiement=ok',",
            "        'cancel_url': retour + '?paiement=annule',",
            "        'client_reference_id': str(reference),",
            "        'line_items[0][quantity]': '1',",
            "        'line_items[0][price_data][currency]': devise,",
            "        'line_items[0][price_data][unit_amount]': str(montant_centimes),",
            "        'line_items[0][price_data][product_data][name]': f'Commande {reference}',",
            "    }).encode()",
            "    requete = urllib.request.Request(",
            "        STRIPE_BASE_URL + '/v1/checkout/sessions', data=corps, method='POST')",
            "    requete.add_header('Authorization', 'Bearer ' + STRIPE_SECRET_KEY)",
            "    requete.add_header('Content-Type', 'application/x-www-form-urlencoded')",
            "    try:",
            "        with urllib.request.urlopen(requete, timeout=15) as reponse:",
            "            return json.loads(reponse.read() or b'{}')",
            "    except urllib.error.HTTPError as e:",
            "        with e:",
            "            detail = (e.read() or b'')[:400].decode('utf-8', 'replace')",
            "        raise HTTPException(status_code=502, detail=(",
            "            f'Le prestataire de paiement a refusé la demande ({e.code}) : {detail}'))",
            "    except urllib.error.URLError as e:",
            "        raise HTTPException(status_code=502, detail=(",
            "            f'Prestataire de paiement injoignable : {e.reason}'))",
            "",
        ]
        for entite, champ in sorted(self.payable_by_entity.items()):
            table = entite.lower()
            # POINT 99 : la colonne comparée à `current_user_id` doit porter un
            # identifiant de COMPTE — donc celle de `_identity_fk_columns`, et
            # non la première relation entrante venue. Sur une entité fille
            # d'une table métier, cette première relation porte l'id d'une ligne
            # de catalogue : la comparaison aurait été fausse dans les deux sens
            # (le propriétaire ne peut plus payer, un inconnu le peut si les
            # deux identifiants coïncident). Le validateur refuse désormais ce
            # cas ; l'assertion plus bas garantit qu'aucune divergence entre lui
            # et cette ligne ne puisse écrire une route sans contrôle.
            colonnes_compte = self._identity_fk_columns().get(entite, set())
            proprio = ({"fk_column": sorted(colonnes_compte)[0]}
                       if colonnes_compte else None)
            # POINT 87 : sous propriété TRANSITIVE, la clé étrangère de l'entité
            # désigne l'intermédiaire, pas un compte — c'est pourquoi le
            # point 81 refusait d'encaisser ici. Une jointure d'un cran rend
            # l'id de COMPTE, donc la comparaison qui suit est identique au cas
            # direct : rien d'autre ne change dans cette route.
            #
            # L'invariant à ne PAS casser : le montant, l'état et le
            # propriétaire sortent de la MÊME lecture. Deux requêtes séparées
            # rouvriraient la fenêtre entre le contrôle d'accès et le calcul du
            # montant — donc la jointure entre DANS le SELECT, elle ne s'ajoute
            # pas à côté.
            chaine = self._transitive_chain(entite)
            if not chaine and not proprio:
                # POINT 99 : sans propriétaire, la route encaisserait n'importe
                # quel enregistrement pour n'importe quel appelant authentifié
                # (IDOR). Le validateur l'interdit — arriver ici signifie qu'il a
                # divergé de cette couche. Échouer à la génération vaut mieux
                # qu'écrire une route de paiement sans contrôle d'accès, même
                # raisonnement que `_derived_source_fk`.
                raise ValueError(
                    f"Génération : '{entite}' est 'payable' mais aucune colonne ne "
                    f"porte l'identifiant du compte propriétaire — la route de "
                    f"règlement ne pourrait opposer de 403 à personne.")
            if chaine:
                # Briques 11 et 24 : une chaîne de JOIN, une par maillon, jusqu'au
                # compte. Montant, état et propriétaire sortent de la MÊME lecture.
                _depuis, _cur, _fk = self._chain_join(entite)
                colonnes = f't."{champ}", t.payment_status, {_cur}."{_fk}"'
                depuis = _depuis
            else:
                colonnes = (f'"{champ}", payment_status, "{proprio["fk_column"]}"')
                depuis = f'"{table}"'
            lignes += [
                f"@app.post('/{table}/{{id}}/paiement', tags=['Paiement'])",
                f"def payer_{table}(id: int, request: Request, "
                "current_user_id: int = Depends(get_current_user_id)):",
                "    _exiger_cle_paiement('STRIPE_SECRET_KEY', STRIPE_SECRET_KEY)",
                "    conn = _connect(); cursor = conn.cursor()",
                f"    cursor.execute('SELECT {colonnes} FROM {depuis} WHERE "
                f"{'t.' if chaine else ''}id = ?', (id,))",
                "    ligne = cursor.fetchone()",
                "    conn.close()",
                # Sous jointure, une ligne ORPHELINE (intermédiaire disparu) ne
                # rend aucun résultat : elle n'appartient à personne, et 404 est
                # la bonne réponse — surtout pas « payable par quiconque ».
                "    if not ligne:",
                "        raise HTTPException(status_code=404, detail='Introuvable.')",
            ]
            lignes += [
                "    montant, etat, proprietaire = ligne",
                "    if proprietaire is not None and proprietaire != current_user_id:",
                "        raise HTTPException(status_code=403, detail="
                "'Cet enregistrement ne vous appartient pas.')",
            ]
            lignes += [
                "    if etat == 'payee':",
                "        raise HTTPException(status_code=409, detail='Déjà réglé.')",
                "    centimes = int(round(float(montant or 0) * 100))",
                "    if centimes <= 0:",
                "        raise HTTPException(status_code=400, detail=(",
                "            'Montant nul ou négatif : rien à encaisser.'))",
                "    retour = str(request.base_url).rstrip('/') + '/site/'",
                # CORRECTIF SÉCURITÉ : la référence porte désormais le nom de
                # l'entité. Un simple id numérique se confondait avec celui
                # d'une AUTRE entité payable de la même app -- le webhook
                # marquait alors comme payé un enregistrement d'une table
                # totalement différente, portant seulement le même id.
                f"    reference = '{entite}:' + str(id)",
                "    session = _session_paiement(centimes, 'eur', reference, retour)",
                "    return {'status': 'success', 'url': session.get('url'),",
                "            'session_id': session.get('id'), 'montant_centimes': centimes}",
                "",
            ]
        lignes += [
            "@app.post('/paiement/webhook', tags=['Paiement'])",
            "async def paiement_webhook(request: Request):",
            "    _exiger_cle_paiement('STRIPE_WEBHOOK_SECRET', STRIPE_WEBHOOK_SECRET)",
            "    brut = await request.body()",
            "    entete = request.headers.get('stripe-signature', '')",
            "    # Signature Stripe : t=<horodatage>,v1=<hmac sha256 de \"t.corps\">.",
            "    # Sans cette vérification, n'importe qui marquerait n'importe",
            "    # quelle commande comme payée avec un simple curl.",
            "    horodatage, signatures = None, []",
            "    for morceau in entete.split(','):",
            "        cle, _, valeur = morceau.partition('=')",
            "        if cle.strip() == 't': horodatage = valeur.strip()",
            "        elif cle.strip() == 'v1': signatures.append(valeur.strip())",
            "    if not horodatage or not signatures:",
            "        raise HTTPException(status_code=400, detail='Signature absente ou malformée.')",
            "    # POINT 91 : l'horodatage était LU pour vérifier la signature, mais",
            "    # jamais daté. Un appel signé capté une fois restait donc rejouable",
            "    # indéfiniment — c'est la parade que Stripe documente, et elle ne",
            "    # coûte que ces trois lignes. Tolérance de cinq minutes : au-delà,",
            "    # ce n'est plus un réseau lent, c'est un rejeu.",
            "    try:",
            "        _age = abs(datetime.datetime.now(datetime.timezone.utc).timestamp()",
            "                   - int(horodatage))",
            "    except ValueError:",
            "        raise HTTPException(status_code=400, detail='Horodatage de signature illisible.')",
            "    if _age > 300:",
            "        raise HTTPException(status_code=400, detail=(",
            "            'Signature expirée : cet appel a plus de cinq minutes.'))",
            "    attendue = hmac.new(STRIPE_WEBHOOK_SECRET.encode(),",
            "                        (horodatage + '.').encode() + brut, hashlib.sha256).hexdigest()",
            "    if not any(hmac.compare_digest(attendue, s) for s in signatures):",
            "        raise HTTPException(status_code=400, detail='Signature invalide.')",
            "    evenement = json.loads(brut or b'{}')",
            "    objet = (evenement.get('data') or {}).get('object') or {}",
            "    reference = objet.get('client_reference_id') or ''",
            "    # La référence est 'EntiteQualifiee:id' (voir la création de session",
            "    # ci-dessus) : un id nu se confondrait avec celui d'une AUTRE entité",
            "    # payable de la même app, et marquerait payé le mauvais enregistrement.",
            "    entite_ref, _, id_texte = str(reference).partition(':')",
            "    if (evenement.get('type') != 'checkout.session.completed'",
            "            or not id_texte.isdigit()):",
            "        return {'status': 'ignored'}",
            "    id_cible = int(id_texte)",
            "    conn = _connect(); cursor = conn.cursor()",
            "    try:",
        ]
        for indice, entite in enumerate(sorted(self.payable_by_entity)):
            mot_cle = "if" if indice == 0 else "elif"
            lignes.append(f"        {mot_cle} entite_ref == '{entite}':")
            lignes.append(
                f"            cursor.execute('UPDATE \"{entite.lower()}\" SET payment_status = ?, "
                f"payment_ref = ? WHERE id = ?', ('payee', objet.get('id'), id_cible))")
        lignes += [
            "        conn.commit()",
            "    except Exception:",
            "        conn.rollback(); conn.close(); raise",
            "    conn.close()",
            "    return {'status': 'success'}",
            "",
        ]
        return lignes
