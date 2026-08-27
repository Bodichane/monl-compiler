"""La route `Delete`, et les actions de workflow.

Le parent est lu AVANT le `DELETE` : après, la clé étrangère a disparu et
plus rien ne dit quoi rendre ni à qui (points 82 et 92)."""

from . import sql


class SuppressionRoutesMixin:
    """La route `Delete`, et les actions de workflow."""

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
        upload_refs = []
        for upload in self.upload_fields_by_entity.get(base_target, []):
            ref_var = f"_upload_ref_{upload['field']}"
            api_lines += [
                f"    cursor.execute('SELECT \"{upload['field']}\" FROM \"{base_target.lower()}\" WHERE id = ?', (id,))",
                f"    {ref_var} = cursor.fetchone()",
            ]
            upload_refs.append((upload, ref_var))
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
        for upload, ref_var in upload_refs:
            api_lines += [
                f"    if {ref_var} and {ref_var}[0]:",
                f"        _remove_upload({base_target.lower()!r}, id, {upload['field']!r}, {ref_var}[0])",
            ]
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
