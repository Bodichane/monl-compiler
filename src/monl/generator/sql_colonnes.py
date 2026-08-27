"""Les colonnes et les index que le schéma doit porter.

La migration reste ADDITIVE (point 32) : elle rattrape une colonne, jamais
son contenu. Un index unique plutôt qu'une contrainte de colonne, parce
que SQLite ne sait pas ajouter `UNIQUE` à une colonne existante."""




class SqlColonnesMixin:
    """Les colonnes et les index que le schéma doit porter."""

    def _unique_fields(self, entity):
        """Les champs de cette entité déclarés 'unique' (point 85)."""
        return sorted(champ for champ, contraintes
                      in self.field_constraints.get(entity, {}).items()
                      if contraintes.get("unique"))

    def _once_per_rules_for(self, entity):
        return [rule for rule in self.once_per_rules
                if rule["trigger_entity"] == entity]

    def _compute_once_per_indexes(self):
        """Index uniques multi-colonnes issus des règles `oncePer`."""
        indexes = []
        placements = self._compute_fk_placements()
        for rule in self.once_per_rules:
            entity = rule["trigger_entity"]
            columns = []
            for parent in rule["parents"]:
                placement = next(
                    (p for p in placements.get(entity, [])
                     if p["owner_entity"] == parent), None)
                if not placement:
                    raise ValueError(
                        f"Génération : aucune clé étrangère de '{entity}' ne désigne "
                        f"'{parent}', alors que 'oncePer' l'exige.")
                # POINT 116 : un index composite sur une colonne que la route
                # Create n'écrit JAMAIS ne refuse rien — SQLite tient deux NULL
                # pour distincts, donc la règle passe la compilation, crée son
                # index, et laisse voter dix fois. C'est arrivé sur
                # `exemples/03_reseau_social.ml` : la colonne visée par un
                # `increments` sort de l'INSERT quand elle est la PREMIÈRE
                # relation entrante, et `oncePer Member, Post` ne mordait plus.
                # Refuser plutôt que produire une règle sans effet — c'est
                # exactement ce que le point 85 a fermé pour `unique`.
                ecrites = set(self._client_fk_columns(entity))
                ecrites |= set(self._identity_fk_columns().get(entity, set()))
                # La branche compteur de la route Create écrit ces colonnes
                # hors des FK client. Le refus reste donc actif pour une
                # colonne réellement jamais écrite, sans rejeter une écriture
                # serveur réelle.
                ecrites |= set(self._counter_fk_columns(entity))
                if placement["fk_column"] not in ecrites:
                    raise ValueError(
                        f"Génération : 'oncePer' sur '{entity}' désigne '{parent}', "
                        f"mais la colonne '{placement['fk_column']}' n'est jamais "
                        f"écrite à la création — l'unicité ne refuserait rien. "
                        f"Déclarer la relation vers l'acteur AVANT celle visée par "
                        f"un 'increments'/'decrements', pour que la colonne du "
                        f"parent reste fournie par le client.")
                columns.append(placement["fk_column"])
            index_name = "idx_once_per_{}_{}".format(
                entity.lower(), "_".join(c.lower() for c in columns))
            indexes.append((entity.lower(), columns, index_name))
        return indexes

    def _compute_unique_indexes(self):
        """POINT 85 : [(table, colonne, nom_d_index)] pour chaque 'rule
        Entite.champ unique'.

        Source unique du nom d'index, pour que la création au démarrage et toute
        vérification ultérieure désignent le même objet. Le nom porte la table et
        la colonne : deux entités peuvent avoir un champ homonyme.

        POINT 102 : un champ 'numbered' y entre sans avoir à déclarer 'unique'.
        Un numéro de commande en double n'est pas un numéro — l'exiger dans la
        spec ferait dépendre la garantie d'une ligne qu'on peut oublier d'écrire.
        Le nom d'index étant dérivé de la table et de la colonne, déclarer les
        deux ne produit qu'un seul index."""
        vises = {
            (entite, champ)
            for entite, champs in self.field_constraints.items()
            for champ, contraintes in champs.items()
            if contraintes.get("unique")
        }
        vises |= {(entite, regle["field"])
                  for entite, regles in self.numbered_fields_by_entity.items()
                  for regle in regles}
        return [
            (entite.lower(), champ, f"idx_unique_{entite.lower()}_{champ.lower()}")
            for entite, champ in sorted(vises)
        ]

    def _compute_numbered_columns(self):
        """POINT 102 : [(table, colonne)] pour chaque 'rule Entite.champ numbered'.

        Même usage que `_compute_timestamp_columns` et même honnêteté : les
        enregistrements antérieurs à la règle n'ont PAS de numéro, et on ne leur
        en invente pas — les numéroter au démarrage prétendrait un ordre
        d'arrivée que le serveur n'a pas observé."""
        return [
            (entite.lower(), regle["field"])
            for entite, regles in sorted(self.numbered_fields_by_entity.items())
            for regle in regles
        ]

    def _compute_timestamp_columns(self):
        """POINT 89 : [(table, colonne)] pour chaque 'rule Entite.champ timestamp'.

        Sert uniquement au constat de démarrage : compter les enregistrements
        antérieurs à l'ajout de la règle, qui n'auront jamais de date."""
        return [
            (entite.lower(), champ)
            for entite, champs in sorted(self.timestamp_fields_by_entity.items())
            for champ in sorted(champs)
        ]

    def _compute_expected_columns(self):
        """AJOUT (roadmap long terme, migrations sans perte de données) :
        retourne {nom_table: [(colonne, type_sql), ...]} pour toutes les
        tables métier, dans l'ordre exact de _generate_sql (attributs
        déclarés puis clés étrangères entrantes). L'id n'y figure pas : il
        est toujours créé par le CREATE TABLE initial et n'est jamais
        ajouté a posteriori. Sert à init_db() pour détecter, au démarrage,
        les colonnes présentes dans la spec mais absentes d'une base déjà
        créée, et les ajouter par ALTER TABLE ADD COLUMN — opération
        purement additive, qui ne touche ni ne supprime aucune donnée
        existante."""
        fk_placements = self._compute_fk_placements()
        expected = {}
        for ent_name, attrs in self.entities.items():
            table = ent_name.lower()
            columns = []
            for attr_name, attr_type in attrs.items():
                columns.append((attr_name, self._map_type_to_sql(attr_type)))
            if ent_name in self.payable_by_entity:
                # Le DEFAULT compte ici autant que dans le CREATE TABLE : sur
                # une base existante, SQLite l'applique aux lignes déjà
                # présentes. Sans lui, ajouter `payable` à une spec en
                # production laisserait les anciens enregistrements à NULL et
                # les nouveaux à 'en_attente' — deux façons de dire la même
                # chose, que toute lecture devrait ensuite réconcilier.
                columns.append(("payment_status", "VARCHAR(32) DEFAULT 'en_attente'"))
                columns.append(("payment_ref", "VARCHAR(255)"))
            for placement in fk_placements.get(ent_name, []):
                columns.append((placement["fk_column"], "INTEGER"))
            expected[table] = columns
        return expected

    def _compute_migrations(self):
        """Prépare les migrations validées pour l'app générée.

        Les types DSL sont conservés pour les messages et leurs types SQL sont
        ajoutés ici afin que le runtime n'ait aucune table de correspondance
        indépendante du générateur.
        """
        prepared = []
        for migration in self.migrations:
            operations = []
            for operation in migration["operations"]:
                item = dict(operation)
                if item["kind"] == "alter":
                    item["from_sql_type"] = self._map_type_to_sql(item["from_type"])
                    item["to_sql_type"] = self._map_type_to_sql(item["to_type"])
                operations.append(item)
            prepared.append({"name": migration["name"], "operations": operations})
        return prepared

    def _map_type_to_sql(self, type_str):
        mapping = {
            "String": "VARCHAR(255)", "Text": "TEXT", "Integer": "INTEGER",
            # Float est un nombre binaire, pas une monnaie : DOUBLE PRECISION
            # est le type partagé SQLite/PostgreSQL. Money reste NUMERIC à
            # échelle fixe ci-dessous, car ses valeurs partent chez Stripe et
            # un flottant binaire n'est pas un type d'argent.
            "Float": "DOUBLE PRECISION", "Boolean": "BOOLEAN", "Date": "DATE",
            "DateTime": "TIMESTAMP", "Email": "VARCHAR(255)", "UUID": "UUID",
            "Money": "NUMERIC(10, 2)",
            # Brique 13 (point 83) : 'Image' stocke un CHEMIN relatif au projet,
            # pas le binaire. Même colonne qu'un String, donc — la différence est
            # ailleurs : le validateur vérifie que le fichier existe, et le
            # contrat le déclare comme média sans avoir à deviner d'après le nom.
            "Image": "VARCHAR(255)",
            # Brique B1 : référence opaque vers le stockage runtime, jamais
            # les octets. Contrairement à Image, aucune existence n'est
            # vérifiée à la compilation.
            "Upload": "VARCHAR(255)",
        }
        return mapping.get(type_str, "TEXT")
