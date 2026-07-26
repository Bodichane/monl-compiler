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
                populate_owner = owner_info and not is_public and not is_reputation_fk
                # AJOUT (roadmap, écosystème de capacités -- suite de la
                # brique 1) : un champ 'generated' est peuplé depuis le
                # pseudonyme anonyme du compte courant (déjà porté par le
                # JWT depuis /login), jamais depuis le corps de requête --
                # incompatible avec 'public' (validé par ast_validator.py),
                # donc l'appelant est nécessairement authentifié ici.
                generated_here = self.generated_fields_by_entity.get(base_target, [])
                create_deps = dependency_injection
                if populate_owner:
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
                value_exprs = [("current_anon_handle" if f in generated_here else f"data.{f}") for f in fields]
                if populate_owner:
                    insert_columns.append(owner_info["fk_column"])
                    value_exprs.append("current_user_id")
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
                for rule in reputation_rules_here:
                    target_table = rule["target_entity"].lower()
                    target_field = rule["target_field"]
                    amount = rule["amount"]
                    sql_op = "-" if rule["direction"] == "decrements" else "+"
                    fk_value_expr = f"data.{owner_info['fk_column']}"
                    api_lines.append(
                        f"        cursor.execute('UPDATE \"{target_table}\" SET \"{target_field}\" = \"{target_field}\" {sql_op} ? "
                        f"WHERE id = ?', ({amount}, {fk_value_expr}))"
                    )
                api_lines.append("        conn.commit()")
                api_lines.append("    except sqlite3.IntegrityError:")
                api_lines.append("        conn.rollback(); conn.close()")
                api_lines.append("        raise HTTPException(status_code=409, detail=(")
                api_lines.append("            'Référence invalide : un identifiant lié fourni ne correspond à aucun '")
                api_lines.append("            'enregistrement existant.'")
                api_lines.append("        ))")
                api_lines.append("    except Exception:")
                api_lines.append("        conn.rollback(); conn.close(); raise")
                api_lines.append("    conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': row_id}}")
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
                if apply_read_owner:
                    owner_fk = f"{read_owner.lower()}_id"
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
                    api_lines.append(f"    if current_actor == \"{read_owner}\":")
                    api_lines.append(f"        _own_where = ' WHERE \"{owner_fk}\" = ?'")
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
                    api_lines.append(f"    if current_actor == \"{read_owner}\" and "
                                     f"named_row.get('{owner_fk}') != current_user_id:")
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
                    fk_col = f"{owner_entity.lower()}_id"
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
                        f"    if current_actor == \"{owner_entity}\":",
                        "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                        f"        _owner_cur.execute('SELECT \"{fk_col}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
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
                fields = list(self.entities[base_target].keys())
                update_stmt = ", ".join([f'"{f}" = ?' for f in fields])
                api_lines.append(f"    query = 'UPDATE \"{base_target.lower()}\" SET {update_stmt} WHERE id = ?'")
                values_list = ", ".join([f"data.{f}" for f in fields])
                api_lines.append(f"    cursor.execute(query, ({values_list}, id))")
                api_lines.append("    conn.commit(); conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': id}}")
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
                    fk_col = f"{owner_entity.lower()}_id"
                    delete_deps += ", current_user_id: int = Depends(get_current_user_id)" if delete_deps else "current_user_id: int = Depends(get_current_user_id)"
                    # Voir le commentaire équivalent dans le bloc "Update" ci-dessus :
                    # le contrôle de propriété ne s'applique qu'à l'acteur
                    # explicitement désigné comme propriétaire par 'ownedBy'.
                    ownership_check_lines = [
                        f"    if current_actor == \"{owner_entity}\":",
                        "        _owner_conn = _connect(); _owner_cur = _owner_conn.cursor()",
                        f"        _owner_cur.execute('SELECT \"{fk_col}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
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
                # CORRECTIF (bêta 3) : les clés étrangères sont désormais
                # réellement appliquées (PRAGMA foreign_keys), donc supprimer un
                # enregistrement encore référencé lève une IntegrityError. On la
                # traduit en 409 explicite plutôt qu'en 500 : c'est une erreur du
                # client (ordre de suppression), pas une panne du serveur.
                api_lines.append("    try:")
                api_lines.append(f"        cursor.execute('DELETE FROM \"{base_target.lower()}\" WHERE id = ?', (id,))")
                api_lines.append("        conn.commit()")
                api_lines.append("    except sqlite3.IntegrityError:")
                api_lines.append("        conn.rollback(); conn.close()")
                api_lines.append("        raise HTTPException(status_code=409, detail=(")
                api_lines.append("            \"Suppression impossible : cet enregistrement est encore référencé \"")
                api_lines.append("            'par des données liées. Supprimez-les d\\'abord.'")
                api_lines.append("        ))")
                api_lines.append("    conn.close()")
                api_lines.append(f"    return {{'status': 'success', 'id': id}}")
                api_lines.append("")
                
            elif act_type == "Execute":
                api_lines.append(f"@app.post('/workflow/{tag.lower()}/{target.lower()}', tags=['{tag}'])")
                api_lines.append(f"def execute_{target.lower()}(payload: {target}InputSchema, {dependency_injection}):")
                api_lines.append(security_check)
                api_lines.append(f"    result = sandbox_ai.{target}(payload.dict())")
                api_lines.append("    return {'status': 'executed', 'sandbox_result': result}")
                api_lines.append("")
                    
        return api_lines
