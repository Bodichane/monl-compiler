"""Génération des routes CRUD et de l'application du contrôle d'accès
(rôle, ownedBy, accessibleBy, public, hidden, categorized, compteurs).

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class RoutesMixin:
    def _generate_route_lines(self):
        """Une route FastAPI par couple (action, entité) du plan de routes."""
        api_lines = []
        api_lines.append("# --- ENFORCEMENT DU CONTRÔLE D'ACCÈS PAR JWT ET PERSISTANCE ---")

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
        route_map = self._compute_route_map()

        for (act_type, _key), info in route_map.items():
            allowed_actors = sorted(info["actors"])
            base_target = info["base_target"]
            target = info["target"]
            tag = info["tags"][0]

            # AJOUT (roadmap, cas d'usage portfolio) : une action marquée
            # 'public' via une règle DSL ("rule Entite.Action public") ne
            # requiert plus aucune authentification sur la route générée —
            # ni dépendance JWT, ni contrôle de rôle. Utile pour un contenu
            # librement consultable (portfolio) ou un formulaire ouvert
            # (message de contact) sans exiger de compte.
            is_public = (base_target, act_type) in self.public_actions

            if is_public:
                security_check = "    pass  # Route publique (règle 'public') : aucune authentification requise"
                dependency_injection = ""
            elif len(allowed_actors) == 1:
                security_check = (f'    if current_actor != "{allowed_actors[0]}": '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle {allowed_actors[0]} requis")')
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"
            else:
                allowed_set_literal = ", ".join(f'"{a}"' for a in allowed_actors)
                security_check = (f'    if current_actor not in {{{allowed_set_literal}}}: '
                                   f'raise HTTPException(status_code=403, detail="Contrôle d\'accès : '
                                   f'Rôle parmi [{", ".join(allowed_actors)}] requis")')
                dependency_injection = "current_actor: str = Depends(verify_jwt_and_get_actor)"

            # Utilisé partout où dependency_injection doit s'insérer après
            # un ou plusieurs paramètres déjà présents dans la signature —
            # évite une virgule traînante invalide en syntaxe Python quand
            # dependency_injection est vide (route publique).
            dep_suffix = f", {dependency_injection}" if dependency_injection else ""

            if act_type == "Create":
                # AJOUT (post-v6, roadmap) : si l'entité a une relation entrante
                # (ex. "relation User hasMany Todo"), la colonne de clé étrangère
                # correspondante (ex. "user_id") est désormais réellement peuplée
                # à la création, à partir de l'identité JWT de l'appelant.
                # CORRECTIF DE GAP PRÉ-EXISTANT : cette colonne était déjà générée
                # dans schema.sql depuis les toutes premières versions, mais
                # jamais incluse dans la requête INSERT — elle restait NULL pour
                # tout enregistrement créé, rendant les relations inertes au
                # runtime malgré leur présence dans le schéma.
                owner_info = self._get_incoming_relation(base_target)
                # AJOUT (roadmap, écosystème de capacités -- brique 3,
                # généralisée en brique 4) : si cette relation entrante est la
                # cible d'une règle 'decrements'/'increments' (ex. "je
                # signale CE membre" ou "j'apprécie CE post"), ce n'est pas un
                # motif "propriétaire = appelant courant" -- le client fournit
                # explicitement la cible dans le corps de la requête (voir la
                # génération du schéma Pydantic ci-dessus), donc on ne tente
                # PAS de la peupler automatiquement depuis current_user_id.
                reputation_rules_here = self.reputation_rules_by_trigger.get(base_target, [])
                is_reputation_fk = owner_info and any(
                    r["target_entity"] == owner_info["source"] for r in reputation_rules_here
                )
                # Une route publique n'a par définition aucune identité
                # appelante fiable — on ne tente pas d'y rattacher une clé
                # étrangère "propriétaire" dans ce cas (la colonne reste NULL).
                # AJOUT (brique 11, point 81) : sous propriété transitive, la
                # colonne « propriétaire » ne se peuple PAS depuis le jeton --
                # c'est le client qui désigne l'enregistrement de rattachement
                # (« cette ligne va dans CETTE commande »). Y écrire
                # `current_user_id` était le défaut du point 80 : le
                # rattachement demandé disparaissait en silence, remplacé par
                # l'id du compte appelant.
                chaine_create = self._transitive_chain(base_target)
                populate_owner = (owner_info and not is_public
                                  and not is_reputation_fk and not chaine_create)
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
                    api_lines += [
                        f"    cursor.execute('SELECT \"{chaine_create['actor_fk']}\" FROM "
                        f'"{chaine_create["via_table"]}" WHERE id = ?\', '
                        f"(data.{chaine_create['via_fk']},))",
                        "    _parent = cursor.fetchone()",
                        "    if not _parent or _parent[0] != current_user_id:",
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
                value_exprs = [
                    calcules.get(f, "current_anon_handle" if f in generated_here
                                 else f"data.{f}")
                    for f in fields
                ]
                if populate_owner:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append("current_user_id")
                    for _client_fk in self._client_fk_columns(base_target):
                        insert_columns.append(_client_fk)
                        value_exprs.append(f"data.{_client_fk}")
                elif verifie_parent:
                    # Toutes les clés étrangères viennent du client ici, y
                    # compris celle du parent propriétaire — que la
                    # vérification ci-dessus vient de valider.
                    for _client_fk in self._client_fk_columns(base_target):
                        insert_columns.append(_client_fk)
                        value_exprs.append(f"data.{_client_fk}")
                elif is_reputation_fk:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append(f"data.{owner_info['fk_column']}")
                columns = ", ".join(f'"{c}"' for c in insert_columns)
                placeholders = ", ".join(["?"] * len(insert_columns))
                api_lines.append(f"    query = 'INSERT INTO \"{base_target.lower()}\" ({columns}) VALUES ({placeholders})'")
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
                api_lines.append(f"        cursor.execute(query, ({values_list},))")
                api_lines.append("        row_id = cursor.lastrowid")
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
                    fk_vers_cible = (self._decrement_fk_column(base_target, rule)
                                     or owner_info["fk_column"])
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
                uniques_ici = self._unique_fields(base_target)
                api_lines.append("    except sqlite3.IntegrityError as _err:")
                api_lines.append("        conn.rollback(); conn.close()")
                if uniques_ici:
                    api_lines.append("        if 'UNIQUE constraint failed' in str(_err):")
                    api_lines.append("            raise HTTPException(status_code=409, detail=(")
                    api_lines.append(
                        f"                'Valeur déjà utilisée : {', '.join(uniques_ici)} "
                        f"doit être unique.'))")
                api_lines.append("        raise HTTPException(status_code=409, detail=(")
                api_lines.append("            'Référence invalide : un identifiant lié fourni ne correspond à aucun '")
                api_lines.append("            'enregistrement existant.'")
                api_lines.append("        ))")
                api_lines.append("    except Exception:")
                api_lines.append("        conn.rollback(); conn.close(); raise")
                api_lines.append("    conn.close()")
                api_lines.append("    return {'status': 'success', 'id': row_id}")
                api_lines.append("")

            elif act_type == "Read":
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
                # AJOUT (roadmap, brique "accès à deux parties") : si une
                # règle 'accessibleBy' cible Read, la liste ne renvoie que
                # les enregistrements dont l'appelant est l'une des parties
                # (WHERE col1 = ? OR col2 = ? ...), et la lecture par ID
                # vérifie l'appartenance avant de répondre. Comme pour
                # 'ownedBy', 'public' l'emporte si les deux sont déclarés
                # (pas d'identité appelante sur une route publique).
                read_parties = self.access_parties.get(f"{base_target}.Read")
                apply_read_parties = bool(read_parties) and not is_public
                read_dep_suffix = dep_suffix
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
                read_owner = self.ownership.get(f"{base_target}.Read")
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
                        own_where_sql = (
                            f' WHERE "{chaine_lecture["via_fk"]}" IN '
                            f'(SELECT id FROM "{chaine_lecture["via_table"]}" '
                            f'WHERE "{chaine_lecture["actor_fk"]}" = ?)'
                        )
                    else:
                        read_actor = read_owner
                        own_where_sql = f' WHERE "{read_owner.lower()}_id" = ?'
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
                    api_lines.append(f"        _own_where = {own_where_sql!r}")
                    api_lines.append("        _own_params = (current_user_id,)")
                api_lines.append("    conn = _connect(); cursor = conn.cursor()")
                if apply_read_owner:
                    api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"' + _own_where, _own_params)")
                    api_lines.append("    total = cursor.fetchone()[0]")
                    api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\"' + _own_where + ' LIMIT ? OFFSET ?', _own_params + (limit, offset))")
                elif apply_read_parties:
                    api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\" WHERE {parties_where}', ({parties_params},))")
                else:
                    api_lines.append(f"    cursor.execute('SELECT COUNT(*) FROM \"{base_target.lower()}\"')")
                if not apply_read_owner:
                    api_lines.append("    total = cursor.fetchone()[0]")
                    if apply_read_parties:
                        api_lines.append(f"    cursor.execute('SELECT * FROM \"{base_target.lower()}\" WHERE {parties_where} LIMIT ? OFFSET ?', ({parties_params}, limit, offset))")
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
                if apply_read_owner:
                    # 404 et non 403 : sur une entité dont les identifiants sont
                    # séquentiels, un 403 confirmerait l'existence de
                    # l'enregistrement d'autrui — il suffirait d'énumérer les
                    # identifiants pour compter les dépenses ou les commandes
                    # d'un tiers. Un enregistrement qu'on n'a pas le droit de
                    # lire doit être indiscernable d'un enregistrement absent.
                    if chaine_lecture:
                        # La chaîne se remonte d'un cran : à qui appartient
                        # l'enregistrement intermédiaire que celui-ci désigne ?
                        # Un intermédiaire absent est traité comme un refus —
                        # une ligne orpheline n'appartient à personne.
                        api_lines += [
                            f"    if current_actor == \"{read_actor}\":",
                            "        _tc = _connect(); _tcur = _tc.cursor()",
                            f"        _tcur.execute('SELECT \"{chaine_lecture['actor_fk']}\" FROM "
                            f'"{chaine_lecture["via_table"]}" WHERE id = ?\', '
                            f"(named_row.get('{chaine_lecture['via_fk']}'),))",
                            "        _tr = _tcur.fetchone(); _tc.close()",
                            "        if not _tr or _tr[0] != current_user_id:",
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
                    api_lines.append(f"    if current_user_id not in ({parties_tuple}):")
                    api_lines.append("        raise HTTPException(status_code=403, detail=\"Contrôle d'accès : seules les parties de la ressource peuvent la consulter\")")
                if masked:
                    api_lines.append(f"    for _f in [{mask_literal}]: named_row.pop(_f, None)")
                for cf in categorized_here:
                    api_lines.extend(self._emit_categorization_lines(cf, "named_row", "    "))
                api_lines.append("    return {'status': 'success', 'data': named_row}")
                api_lines.append("")

            elif act_type == "Update":
                # AJOUT (post-v6, roadmap) : si une règle 'ownedBy' cible cette
                # action, un contrôle supplémentaire vérifie que l'acteur courant
                # est bien le propriétaire de l'enregistrement, en plus du
                # contrôle de rôle habituel.
                owner_entity = self.ownership.get(f"{base_target}.Update")
                # 'ownedBy' suppose une identité appelante (current_actor) —
                # incompatible avec une route 'public', qui n'en a aucune.
                # Si les deux sont déclarées sur la même action, 'public'
                # l'emporte : la route reste ouverte, sans contrôle de
                # propriété (voir docs/design_decisions.md).
                apply_ownership = owner_entity and not is_public
                # AJOUT (roadmap, brique "accès à deux parties") : même
                # principe que 'ownedBy' mais l'appelant doit être l'UNE des
                # colonnes-parties listées. Contrairement à 'ownedBy', le
                # contrôle s'applique à tous les acteurs de la route (les
                # parties sont des colonnes de données, pas des rôles) —
                # combiner avec 'sharedBy' pour un rôle superviseur n'est
                # pas couvert par cette première version (documenté).
                update_parties = self.access_parties.get(f"{base_target}.Update")
                apply_update_parties = bool(update_parties) and not is_public
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
                        "    if current_user_id not in _p_row: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")",
                    ]
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
                        f"        _owner_cur.execute({owner_select!r}, (id,))",
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
                ecrits = [f for f in fields
                          if f not in generated_upd and f not in sommes_upd
                          and f not in horodates_upd]
                # POINT 85 : les écritures sont rassemblées AVANT d'être émises,
                # pour pouvoir les envelopper d'un try quand l'entité porte un
                # 'unique'. C'est SQLite qui lève à l'`execute`, pas au `commit` —
                # une garde autour du seul commit donnait 500 (vérifié contre un
                # vrai serveur, pas déduit).
                lignes_ecriture = []
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
                    api_lines.append("    except sqlite3.IntegrityError:")
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

            elif act_type == "Delete":
                owner_entity = self.ownership.get(f"{base_target}.Delete")
                apply_ownership = owner_entity and not is_public
                # AJOUT (roadmap, brique "accès à deux parties") — voir le
                # commentaire équivalent sur la route Update.
                delete_parties = self.access_parties.get(f"{base_target}.Delete")
                apply_delete_parties = bool(delete_parties) and not is_public
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
                        "    if current_user_id not in _p_row: raise HTTPException(status_code=403, "
                        "detail=\"Contrôle d'accès : seules les parties de la ressource peuvent exécuter cette action\")",
                    ]
                elif apply_ownership:
                    check_actor, owner_select = self._owner_lookup_sql(base_target, owner_entity)
                    delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
                    # Voir le commentaire équivalent dans le bloc "Update" ci-dessus :
                    # le contrôle de propriété ne s'applique qu'à l'acteur
                    # explicitement désigné comme propriétaire par 'ownedBy'.
                    ownership_check_lines = [
                        f"    if current_actor == \"{check_actor}\":",
                        "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                        f"        _owner_cur.execute({owner_select!r}, (id,))",
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
                api_lines.append("    except sqlite3.IntegrityError:")
                api_lines.append("        conn.rollback(); conn.close()")
                api_lines.append("        raise HTTPException(status_code=409, detail=(")
                api_lines.append("            \"Suppression impossible : cet enregistrement est encore référencé \"")
                api_lines.append("            'par des données liées. Supprimez-les d\\'abord.'")
                api_lines.append("        ))")
                api_lines.append("    conn.close()")
                api_lines.append("    return {'status': 'success', 'id': id}")
                api_lines.append("")

            elif act_type == "Execute":
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

        api_lines.extend(self._generate_payment_routes())
        return api_lines

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
            proprio = self._get_incoming_relation(entite)
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
            if chaine:
                colonnes = f't."{champ}", t.payment_status, p."{chaine["actor_fk"]}"'
                depuis = (f'"{table}" t JOIN "{chaine["via_table"]}" p '
                          f'ON p.id = t."{chaine["via_fk"]}"')
                a_un_proprietaire = True
            else:
                colonnes = f'"{champ}", payment_status'
                if proprio:
                    colonnes += f', "{proprio["fk_column"]}"'
                depuis = f'"{table}"'
                a_un_proprietaire = bool(proprio)
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
            if a_un_proprietaire:
                lignes += [
                    "    montant, etat, proprietaire = ligne",
                    "    if proprietaire is not None and proprietaire != current_user_id:",
                    "        raise HTTPException(status_code=403, detail="
                    "'Cet enregistrement ne vous appartient pas.')",
                ]
            else:
                lignes.append("    montant, etat = ligne")
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
