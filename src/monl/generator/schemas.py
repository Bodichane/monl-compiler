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
            # AJOUT (brique 10, point 77) : un champ 'derivedFrom' est calculé
            # par le serveur, donc absent du schéma pour la même raison qu'un
            # champ 'generated'. Ce schéma sert à la création ET à la
            # modification (un seul {Ent}Schema) : l'en retirer ferme d'un coup
            # les deux chemins par lesquels le client écrivait le montant que
            # `payable` relisait ensuite.
            derives_ici = self._derived_field_names(ent_name)
            # AJOUT (brique 12, point 82) : un champ 'sumOf' est recalculé par le
            # serveur à chaque écriture d'une ligne enfant. Même traitement, même
            # raison : le laisser dans le schéma reviendrait à laisser le client
            # écrire le total d'un panier, c'est-à-dire la faille du point 77
            # revenue par le panier.
            sommes_ici = self._aggregated_field_names(ent_name)
            # AJOUT (brique 16, point 89) : un champ 'timestamp' est écrit par le
            # serveur à la création. Le laisser dans le schéma rendrait la date
            # déclarative — c'est-à-dire sans valeur : un carnet de commandes
            # dont chacun choisit ses dates n'atteste de rien.
            horodates_ici = self.timestamp_fields_by_entity.get(ent_name, [])
            # BRIQUE 22 (point 102) : un numéro que le client pourrait écrire ne
            # numéroterait rien — il choisirait le sien, et deux clients
            # choisiraient le même.
            horodates_ici = list(horodates_ici) + [
                n["field"] for n in self.numbered_fields_by_entity.get(ent_name, [])]
            has_schema_field = False
            for attr_name, attr_type in attrs.items():
                if (attr_name in generated_here_schema or attr_name in derives_ici
                        or attr_name in sommes_ici or attr_name in horodates_ici):
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
                # POINT 85 : 'min'/'max' n'avaient AUCUN effet. Ils arrivent ici,
                # au seul endroit où une borne d'entrée peut vivre — la
                # validation Pydantic, donc un 422 avant tout INSERT. Le
                # validateur a déjà tranché ce que chaque borne signifie selon le
                # type (longueur pour du texte, valeur pour un nombre) et refusé
                # ce qu'elle ne sait pas borner : ici on ne fait que l'écrire.
                # BRIQUE 19 (point 96) : une valeur PARMI UNE LISTE. `Literal`
                # plutôt qu'un motif : Pydantic refuse en 422 AVANT tout INSERT
                # (même place que les bornes du point 85), et la liste sort
                # telle quelle dans le schéma OpenAPI — donc dans /docs, sans
                # qu'on ait à la recopier. Les valeurs passent par `repr()` :
                # jamais d'interpolation manuelle entre guillemets, c'est la
                # leçon de `categorized` (brique 5).
                choix = self.enumerated_fields.get(ent_name, {}).get(attr_name)
                if choix:
                    valeurs = ", ".join(repr(v) for v in choix)
                    api_lines.append(f"    {attr_name}: Literal[{valeurs}]")
                    has_schema_field = True
                    continue
                contraintes = self.field_constraints.get(ent_name, {}).get(attr_name, {})
                bornes = []
                for nom, mot_texte, mot_nombre in (("min", "min_length", "ge"),
                                                   ("max", "max_length", "le")):
                    borne_regle = contraintes.get(nom)
                    if not borne_regle:
                        continue
                    mot = mot_texte if borne_regle["portee"] == "longueur" else mot_nombre
                    bornes.append(f"{mot}={borne_regle['valeur']}")
                if py_type == "str":
                    borne = {"Text": 20000, "Email": 320, "UUID": 36}.get(attr_type, 255)
                    # Un 'max' déclaré l'emporte sur la borne de colonne : le
                    # validateur a vérifié qu'il ne la dépasse pas.
                    if not any(b.startswith("max_length=") for b in bornes):
                        bornes.append(f"max_length={borne}")
                    # POINT 91 : le type 'Email' ne fixait qu'une LONGUEUR —
                    # 'pas-un-courriel' entrait en base avec un 200. Un type qui
                    # nomme une adresse et n'en vérifie aucune est exactement ce
                    # que le point 85 refuse : une règle qui ne produit rien.
                    # Le motif est volontairement large (une arobase, un point
                    # après, aucun espace) : monl vérifie la FORME, il ne peut
                    # pas attester qu'une boîte existe — cela demanderait un
                    # envoi, donc un appel sortant que le compilateur s'interdit.
                    if attr_type == "Email":
                        bornes.append(r"pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'")
                    # POINT 101 : le type frère avait le même défaut, et il est
                    # resté debout dix points de plus. 'UUID' ne fixait qu'une
                    # longueur de 255 : `smoke-reference` entrait en base sous un
                    # nom qui promet un identifiant universellement unique. Le
                    # raisonnement du point 91 s'applique mot pour mot — un type
                    # qui NOMME une chose et n'en vérifie aucune est une règle
                    # qui ne produit rien (point 85).
                    #
                    # La forme canonique, et rien de plus : ni version ni
                    # variante. Exiger le chiffre de version rejetterait l'UUID
                    # nul et les versions à venir, alors qu'ils sont bien formés
                    # -- monl vérifie la FORME, il ne juge pas la provenance.
                    if attr_type == "UUID":
                        bornes.append(
                            r"pattern=r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'")
                    api_lines.append(f"    {attr_name}: str = Field(..., {', '.join(bornes)})")
                elif bornes:
                    api_lines.append(f"    {attr_name}: {py_type} = Field(..., {', '.join(bornes)})")
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
