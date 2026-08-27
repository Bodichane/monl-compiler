"""Les routes de lecture : liste et détail.

Un `SELECT *` : toute colonne ajoutée par une brique sort dans les réponses
et doit donc être déclarée au contrat (point 76)."""

from . import sql


class LectureRoutesMixin:
    """Les routes de lecture : liste et détail."""

    def _generate_read_route_lines(self, plan, context, act_type):
        """Rend la famille de route ``Read``."""
        # BRIQUE B3 : conserver le chemin historique byte pour byte quand la
        # spec ne déclare aucune capacité de liste. La nouvelle émission est
        # isolée ci-dessous afin que pagination et golden artifacts restent
        # inchangés pour toutes les specs existantes.
        if (self.filterable_fields_by_entity.get(context["base_target"])
                or self.sortable_fields_by_entity.get(context["base_target"])):
            return self._generate_read_route_lines_with_query(plan, context, act_type)
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

    def _list_query_annotation(self, entity, field):
        """Type FastAPI du paramètre de filtre exact déclaré en spec."""
        choices = self.enumerated_fields.get(entity, {}).get(field)
        if choices:
            return "Optional[Literal[{}]]".format(
                ", ".join(repr(value) for value in choices))
        type_map = {
            "Integer": "int", "Float": "float", "Money": "float",
            "Boolean": "bool",
        }
        return f"Optional[{type_map.get(self.entities[entity][field], 'str')}]"
