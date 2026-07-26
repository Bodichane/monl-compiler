"""Génération des schémas Pydantic (entrées CRUD et blocs 'custom').

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""


class SchemasMixin:
    def _generate_schema_lines(self):
        """Schémas d'entrée : un par entité, un par bloc 'custom'."""
        api_lines = []
        # 1. Génération des schémas CRUD standards
        for ent_name, attrs in self.entities.items():
            api_lines.append(f"class {ent_name}Schema(BaseModel):")
            # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1) :
            # un champ 'generated' n'apparaît PAS dans le schéma Pydantic --
            # le client ne peut même pas tenter de le fournir dans le corps de
            # requête (comme la colonne de clé étrangère 'ownedBy', qui n'y
            # figure pas non plus). Il est peuplé plus bas, à la création,
            # depuis le pseudonyme anonyme du compte courant.
            generated_here_schema = self.generated_fields_by_entity.get(ent_name, [])
            has_schema_field = False
            for attr_name, attr_type in attrs.items():
                if attr_name in generated_here_schema:
                    continue
                py_type = "str"
                if attr_type == "Integer": py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type == "Boolean": py_type = "bool"
                # CORRECTIF (bêta 3) : les champs texte n'avaient AUCUNE borne
                # de longueur — une chaîne de plusieurs Mo était acceptée et
                # écrite en base, ce qui suffit à remplir le disque avec une
                # boucle de dix lignes. La borne reflète la colonne SQL
                # correspondante (VARCHAR(255) pour String, VARCHAR(320) pour
                # Email, texte long pour Text) : le refus arrive à la
                # validation d'entrée, avec un 422 explicite, plutôt qu'au
                # milieu d'un INSERT.
                if py_type == "str":
                    borne = {"Text": 20000, "Email": 320}.get(attr_type, 255)
                    api_lines.append(f"    {attr_name}: str = Field(..., max_length={borne})")
                else:
                    api_lines.append(f"    {attr_name}: {py_type}")
                has_schema_field = True
            # AJOUT (roadmap, écosystème de capacités -- brique 3, généralisée
            # en brique 4) : quand la relation entrante de cette entité est
            # la cible d'une règle 'decrements'/'increments' (ex.
            # Report -> Member, ou Like -> Post), sa colonne de clé étrangère
            # n'est PAS de la même nature qu'un "ceci m'appartient" (qui se
            # peuple tout seul depuis l'identité JWT de l'appelant, voir plus
            # bas) : c'est un choix du client ("je signale/j'apprécie CETTE
            # cible précise"), donc un champ normal du corps de requête.
            owner_info_for_schema = self._get_incoming_relation(ent_name)
            if owner_info_for_schema and any(
                r["target_entity"] == owner_info_for_schema["source"]
                for r in self.reputation_rules_by_trigger.get(ent_name, [])
            ):
                api_lines.append(f"    {owner_info_for_schema['fk_column']}: int")
                has_schema_field = True
            # AJOUT (bêta 3) : parents autres que le propriétaire — le client
            # doit pouvoir dire à quel enregistrement lié il se rattache.
            for _client_fk in self._client_fk_columns(ent_name):
                api_lines.append(f"    {_client_fk}: int")
                has_schema_field = True
            # Filet de sécurité syntaxique : si TOUS les attributs d'une
            # entité sont 'generated' (aucun autre champ, pas de colonne FK
            # ajoutée ci-dessus), le corps de la classe serait vide --
            # invalide en Python.
            if not has_schema_field:
                api_lines.append("    pass")
            api_lines.append("\n")

        # 2. Schémas stricts pour les entrées des fonctions 'custom'
        api_lines.append("# --- SCHÉMAS DE VALIDATION DÉDIÉS POUR LA SANDBOX IA ---")
        for func in self.custom_functions:
            func_name = func["name"]
            inputs = func.get("input", [])
            
            api_lines.append(f"class {func_name}InputSchema(BaseModel):")
            if not inputs:
                api_lines.append("    pass")
            else:
                for inp in inputs:
                    if "reference" in inp:
                        ref = inp["reference"]
                        ent, attr = ref.split(".") if "." in ref else (ref, "id")
                        attr_type = self.entities.get(ent, {}).get(attr, "String")
                        py_type = "int" if attr_type == "Integer" else ("float" if attr_type in ["Float", "Money"] else ("bool" if attr_type == "Boolean" else "str"))
                        api_lines.append(f"    {attr.replace('.', '_')}: {py_type}")
                    else:
                        inp_name = inp.get("name", "context")
                        inp_type = inp.get("type", "String")
                        py_type = "int" if inp_type == "Integer" else ("float" if inp_type in ["Float", "Money"] else ("bool" if inp_type == "Boolean" else "str"))
                        api_lines.append(f"    {inp_name}: {py_type}")
            api_lines.append("\n")

        return api_lines
