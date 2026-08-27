"""La route `Create`.

C'est la plus longue du générateur, et pour cause : elle porte le décompte
de stock, la dérivation, l'agrégation, le préalable `requiresOwn`, la
numérotation, l'horodatage et le verrou de paiement — tous dans LA MÊME
transaction que l'insertion."""

from . import sql


class CreationRoutesMixin:
    """La route `Create`."""

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
        message_here = self.message_rules_by_trigger.get(base_target)
        # AJOUT (brique 17, point 90) : la fiche que l'appelant doit
        # déjà posséder. Elle se cherche par son identifiant de COMPTE,
        # donc la route a besoin de `current_user_id` même quand rien
        # d'autre ne l'exigeait.
        fiche_exigee = self._profile_lookup(base_target)
        create_deps = dependency_injection
        if populate_owner or verifie_parent or fiche_exigee or message_here:
            create_deps += ", current_user_id: int = Depends(get_current_user_id)" if create_deps else "current_user_id: int = Depends(get_current_user_id)"
        if generated_here:
            create_deps += ", current_anon_handle: str = Depends(get_current_anon_handle)" if create_deps else "current_anon_handle: str = Depends(get_current_anon_handle)"
        create_deps_suffix = f", {create_deps}" if create_deps else ""

        api_lines.append(f"@app.post('/{base_target.lower()}', tags=['{tag}'])")
        api_lines.append(f"def create_{base_target.lower()}(data: {base_target}Schema{create_deps_suffix}):")
        api_lines.append(security_check)
        api_lines.append("    conn = _connect(); cursor = conn.cursor()")
        fields = [
            field for field, type_ in self.entities[base_target].items()
            if type_ != "Upload"
        ]
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
        if message_here:
            # Le commit métier est terminé avant le lancement du thread. Une
            # panne SMTP ne peut donc ni annuler la ligne ni transformer une
            # route métier en route d'attente réseau.
            api_lines.append(
                f"    _declencher_message({base_target!r}, current_user_id, row_id)")
        api_lines.append("    return {'status': 'success', 'id': row_id}")
        api_lines.append("")

        return api_lines
