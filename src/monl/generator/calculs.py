"""Ce que le serveur CALCULE : dérivation, somme, compteurs.

POINT 92 : `_decrement_fk_column` est la source UNIQUE de la colonne visée
par un `decrements`/`increments`, pour les TROIS branchements (création,
modification, suppression). Le calcul recopié à chaque branche est
exactement là qu'a vécu le bug du point 86."""




class CalculsMixin:
    """Ce que le serveur CALCULE : dérivation, somme, compteurs."""

    def _derived_field_names(self, entity):
        """Champs de 'entity' calculés par le serveur (brique 10, point 77).

        Ils doivent être traités comme les champs 'generated' partout où le
        client pourrait les fournir : absents du schéma Pydantic, et exclus des
        valeurs d'écriture qu'on lit dans `data`."""
        return [plan.field for plan in self._effects("derive", target=entity)]

    def _derived_source_fk(self, entity, source_entity):
        """Colonne de clé étrangère de 'entity' qui désigne la ligne de
        'source_entity' à lire. Le validateur a garanti que la relation existe
        et que la source n'est PAS le propriétaire — donc cette colonne est
        fournie par le client, jamais déduite du jeton."""
        for placement in self._compute_fk_placements().get(entity, []):
            if placement["owner_entity"] == source_entity:
                return placement["fk_column"]
        # Le validateur a déjà exigé la relation : arriver ici signifie que la
        # validation et le placement des clés étrangères ont divergé. Échouer à
        # la génération vaut mieux qu'émettre 'data.None' dans le app.py.
        raise ValueError(
            f"Génération : aucune colonne de clé étrangère de '{entity}' ne "
            f"désigne '{source_entity}', alors que le validateur l'exigeait "
            f"pour 'derivedFrom'."
        )

    def _aggregated_field_names(self, entity):
        """Champs de 'entity' qui sont une SOMME de ses enfants (brique 12).

        Traités partout comme les champs 'derivedFrom' : absents du schéma
        Pydantic, et jamais lus dans `data`."""
        return [plan.field for plan in self._effects("aggregate", target=entity)]

    def _aggregation_recomputes(self, source_entity):
        """Sommes à recalculer après toute écriture sur 'source_entity'.

        Retourne, par règle, la requête de recalcul et la colonne de clé
        étrangère qui désigne le parent. La somme est RECALCULÉE depuis la table
        plutôt qu'ajustée d'un delta : un ajustement se désynchronise dès qu'une
        écriture échoue à mi-chemin, un recalcul est toujours juste. COALESCE
        pour qu'un panier vidé retombe à 0 et non à NULL ; ROUND parce qu'une
        somme de flottants dérive (0.1 + 0.2), et c'est un montant."""
        recalculs = []
        placements = self._compute_fk_placements().get(source_entity, [])
        for plan in self._effects("aggregate", trigger=source_entity):
            fk = next((p["fk_column"] for p in placements
                       if p["owner_entity"] == plan.target_entity), None)
            # Le validateur a exigé la relation parent-enfant : arriver ici sans
            # colonne signifie que validation et placement des clés étrangères
            # ont divergé. Échouer à la génération vaut mieux qu'émettre une
            # requête qui additionnerait la table entière.
            if not fk:
                raise ValueError(
                    f"Génération : aucune colonne de clé étrangère de "
                    f"'{source_entity}' ne désigne '{plan.target_entity}', alors que "
                    f"le validateur l'exigeait pour 'sumOf'."
                )
            recalculs.append({
                "fk_column": fk,
                "sql": (f'UPDATE "{plan.target_entity.lower()}" SET "{plan.field}" = '
                        f'(SELECT ROUND(COALESCE(SUM("{plan.source_field}"), 0), 2) '
                        f'FROM "{source_entity.lower()}" WHERE "{fk}" = ?) '
                        f'WHERE id = ?'),
            })
        return recalculs

    def _decrement_fk_column(self, trigger_entity, rule):
        """Colonne de 'trigger_entity' qui désigne l'enregistrement DÉCRÉMENTÉ,
        ou None (point 92).

        Source unique des trois branchements d'un `decrements`/`increments` —
        création, modification, suppression. C'est ici qu'a vécu le bug du
        point 86 : la colonne visée est celle qui pointe vers l'entité de la
        RÈGLE, pas la relation « propriétaire », et les deux ne coïncident que
        tant que l'entité déclenchante n'a qu'UNE relation entrante. Le calcul
        était recopié à chaque branchement ; le recopier une fois de plus, c'est
        rouvrir la porte à la troisième occurrence du même défaut."""
        placements = self._compute_fk_placements().get(trigger_entity, [])
        return next((p["fk_column"] for p in placements
                     if p["owner_entity"] == rule["target_entity"]), None)

    def _counter_fk_columns(self, trigger_entity):
        """FK écrites par la branche compteur à la création.

        Chaque colonne vient de `_decrement_fk_column`, quelle que soit la
        position de la relation dans la spec. La liste est dédoublonnée pour
        qu'une entité qui porte plusieurs effets sur la même cible n'ajoute
        cette FK qu'une seule fois à son schéma et à son INSERT.
        """
        colonnes = []
        for rule in self.reputation_rules_by_trigger.get(trigger_entity, []):
            fk_column = self._decrement_fk_column(trigger_entity, rule)
            if fk_column and fk_column not in colonnes:
                colonnes.append(fk_column)
        return colonnes

    def _emit_categorization_lines(self, categorized_field, row_var, indent):
        """AJOUT (roadmap, écosystème de capacités -- brique 5) : génère le
        code source Python qui remplace, sur un dict de ligne déjà nommé
        (row_var), un champ numérique par son libellé de catégorie
        (ex. 'likes' -> 'likes_category'). La validation dans
        ast_validator.py garantit que 'clauses' se termine toujours par
        exactement un palier 'otherwise', et que tous les paliers 'below'
        qui précèdent sont strictement croissants -- donc la chaîne
        if/elif/.../else générée ici est toujours syntaxiquement valide et
        couvre nécessairement toute valeur possible."""
        field = categorized_field["field"]
        clauses = categorized_field["clauses"]
        cat_key = f"{field}_category"
        # repr() plutôt qu'une interpolation manuelle entre guillemets : le
        # libellé vient d'un STRING_LITERAL utilisateur et peut contenir des
        # apostrophes/antislashs -- repr() produit toujours un littéral
        # Python syntaxiquement valide, quel que soit le contenu.
        lines = [f"{indent}_v = {row_var}.pop('{field}')"]
        for i, clause in enumerate(clauses):
            label_literal = repr(clause["label"])
            if "otherwise" in clause:
                lines.append(f"{indent}else: {row_var}['{cat_key}'] = {label_literal}")
            else:
                keyword = "if" if i == 0 else "elif"
                lines.append(f"{indent}{keyword} _v < {clause['below']}: {row_var}['{cat_key}'] = {label_literal}")
        return lines
