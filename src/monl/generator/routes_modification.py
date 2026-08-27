"""La route `Update`.

Le montant est RECALCULÉ ici depuis la clé étrangère STOCKÉE, jamais celle
du corps de requête — leçon du point 78 : calculer sur `data.<fk>` laissait
facturer 89 € un article à 189 €."""

from . import sql


class ModificationRoutesMixin:
    """La route `Update`."""

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
                  and f not in postpaiement_upd
                  and self.entities[base_target][f] != "Upload"]
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
