"""Ce qu'un champ accepte, et ce qu'il montre.

Les quatre contraintes du point 85 (`required`, `unique`, `min`, `max` —
les plus anciennes règles du compilateur, qui ne produisaient RIEN avant
lui), le masquage `hidden`, la substitution `categorized`, et la liste
fermée `oneOf` (point 96)."""

from .socle import ASTValidationError


class ChampsMixin:
    """Ce qu'un champ accepte, et ce qu'il montre."""

    # Les quatre VALIDATION_TYPE de la grammaire, et ce qu'ils bornent selon le
    # type du champ. La longueur pour du texte, la valeur pour un nombre : c'est
    # la seule lecture naturelle de « min 3 » sur un nom et de « min 0 » sur un
    # prix, et elle doit être écrite quelque part plutôt que devinée.
    BORNES_TEXTE = ("String", "Text", "Email")

    BORNES_NOMBRE = ("Integer", "Float", "Money")

    # Longueur maximale de la colonne SQL correspondante (correctif bêta 3) :
    # un 'max' au-delà promettrait une donnée que la colonne ne peut pas tenir.
    LONGUEUR_COLONNE = {"String": 255, "Email": 320, "Text": 20000}

    def _valider_contraintes_de_champ(self):
        """POINT 85 : les quatre règles qui ne faisaient rien.

        `required`, `unique`, `min` et `max` — les plus anciennes du compilateur —
        étaient acceptées sans que RIEN ne les vérifie ni ne les applique. Deux
        constats, tous deux obtenus par exécution :

        * une référence fantôme passait en silence. `rule Product.nom required`
          au lieu de `name` : l'auteur croit tenir une contrainte, il n'en a
          aucune, et rien ne le dit ;
        * la sortie était IDENTIQUE À L'OCTET avec ou sans ces règles.
          `exemples/02_boutique.ml` déclare `rule Product.price min 0`, et le
          serveur acceptait `price: -99` — dans une boutique où le prix se
          multiplie en sous-total, se somme en total et part chez Stripe.

        Cette méthode ferme la première moitié (les références), et remplit
        `self.field_constraints` dont le générateur applique la seconde."""
        self.field_constraints = {}
        for rule in self.rules:
            type_regle = rule["type"]
            if type_regle not in ("required", "unique", "min", "max"):
                continue
            reference = rule["reference"]
            ou = f"rule {reference} {type_regle}"
            if "." not in reference:
                raise ASTValidationError(
                    f"Structure: '{ou}' must reference 'Entity.field', got '{reference}'.")
            entite, champ = reference.split(".", 1)
            if entite not in self.entities:
                raise ASTValidationError(
                    f"Structure: '{ou}' references entity '{entite}', which does not exist. "
                    f"Declared entities: {', '.join(sorted(self.entities))}.")
            type_champ = self.entities[entite].get(champ)
            if type_champ is None:
                proches = [c for c in self.entities[entite] if c.lower() == champ.lower()]
                indice = f" Did you mean '{proches[0]}'?" if proches else ""
                raise ASTValidationError(
                    f"Structure: '{ou}' references field '{champ}', which entity "
                    f"'{entite}' does not declare.{indice} Fields of {entite}: "
                    f"{', '.join(self.entities[entite])}. A constraint on a nonexistent field "
                    f"does not apply to anything—and suggests otherwise.")

            if type_champ == "Upload":
                raise ASTValidationError(
                    f"Structure: '{ou}' does not apply to '{reference}' of type Upload. "
                    "Constrain an upload with 'upload max … types …', which produces "
                    "real multipart rejections in the backend.")

            contraintes = self.field_constraints.setdefault((entite, champ), {})
            if type_regle in contraintes:
                raise ASTValidationError(
                    f"Structure: '{ou}' is declared twice on the same field.")
            if type_regle in ("required", "unique"):
                contraintes[type_regle] = True
                continue

            # 'min'/'max' : la grammaire n'accepte qu'un entier positif.
            try:
                borne = int(rule.get("value"))
            except (TypeError, ValueError):
                raise ASTValidationError(
                    f"Structure: '{ou}' expects an integer "
                    f"(got '{rule.get('value')}').") from None
            if type_champ in self.BORNES_TEXTE:
                limite = self.LONGUEUR_COLONNE[type_champ]
                if borne > limite:
                    raise ASTValidationError(
                        f"Structure: '{ou} {borne}' exceeds the column length "
                        f"'{champ}' ({type_champ} = {limite} characters). The constraint "
                        f"would promise data the database cannot store.")
                contraintes[type_regle] = {"portee": "longueur", "valeur": borne}
            elif type_champ in self.BORNES_NOMBRE:
                contraintes[type_regle] = {"portee": "valeur", "valeur": borne}
            else:
                raise ASTValidationError(
                    f"Structure: '{ou}' targets '{champ}' of type '{type_champ}', "
                    f"which '{type_regle}' cannot bound. LENGTH bounds apply to "
                    f"{', '.join(self.BORNES_TEXTE)}; VALUE bounds apply to "
                    f"{', '.join(self.BORNES_NOMBRE)}.")

        for (entite, champ), contraintes in self.field_constraints.items():
            bas, haut = contraintes.get("min"), contraintes.get("max")
            if bas and haut and bas["valeur"] > haut["valeur"]:
                raise ASTValidationError(
                    f"Structure: '{entite}.{champ}' has min {bas['valeur']} and "
                    f"max {haut['valeur']}: no value satisfies both.")

    def _valider_champs_masques(self):
        """Valide les règles ``hidden`` et prépare les champs à masquer."""
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] != "hidden":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'hidden' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'hidden' rule targets entity '{entity}' which does not exist.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure: the 'hidden' rule references field '{field}', which is not a declared attribute "
                    f"of '{entity}' (or is 'id', which cannot be hidden)."
                )
            self.masked_fields.add((entity, field))

    def _valider_champs_categorises(self):
        """Valide les règles ``categorized`` après les champs ``hidden``."""
        self.categorized_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "categorized":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'categorized' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'categorized' rule targets entity '{entity}' which does not exist.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure: 'categorized' targets field '{entity}.{field}', which must be a declared "
                    f"Integer or Float attribute (got: {field_type or 'nonexistent field'})."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and 'categorized'—incompatible: "
                    f"'hidden' removes the field, while 'categorized' replaces it with a category derived from its value."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure: multiple 'categorized' rules declared for '{entity}.{field}'—only one is allowed."
                )
            seen_fields.add((entity, field))

            clauses = rule["value"]
            self._valider_paliers_categorises(entity, field, clauses)
            self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

    @staticmethod
    def _valider_paliers_categorises(entity, field, clauses):
        """Les paliers d'un `categorized` : au moins un seuil, `otherwise` en
        dernier et seulement là, seuils strictement croissants, libellés non
        vides. Extrait de `_valider_champs_categorises` (plafond de
        complexité) ; refus et messages inchangés."""
        if len(clauses) < 2:
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' must declare at least one threshold ('below') "
                f"and a fallback tier ('otherwise')."
            )
        for clause in clauses[:-1]:
            if "otherwise" in clause:
                raise ASTValidationError(
                    f"Structure: 'categorized' on '{entity}.{field}'—only the LAST tier can be "
                    f"'otherwise' (fallback tier); it appeared earlier in the list."
                )
        if "otherwise" not in clauses[-1]:
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' must end with an 'otherwise' tier "
                f"(the fallback tier that covers every value beyond the last threshold)."
            )
        thresholds = [clause["below"] for clause in clauses[:-1]]
        if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' —'below' thresholds must be "
                f"strictly increasing (got: {thresholds})."
            )
        if any(not clause["label"].strip() for clause in clauses):
            raise ASTValidationError(
                f"Structure: 'categorized' on '{entity}.{field}' —each tier must have a non-empty label."
            )

    def _valider_champs_enumeres(self):
        """Valide les champs texte limités à une liste de valeurs."""
        self.enumerated_fields = {}
        for rule in self.rules:
            if rule["type"] != "oneOf":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'oneOf' rule must reference 'Entity.field', got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'oneOf' rule targets entity '{entity}' which does not exist.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("String", "Text"):
                raise ASTValidationError(
                    f"Structure: 'oneOf' targets '{entity}.{field}', which must be a String or Text field "
                    f"(got: {field_type or 'nonexistent field'})—for a number, 'min'/'max' or "
                    f"'categorized' already provide this."
                )
            values = rule["value"]
            if len(values) < 2:
                raise ASTValidationError(
                    f"Structure: 'oneOf' on '{entity}.{field}' lists only one value—"
                    f"a field with only one possible value does not need to be entered."
                )
            empty_values = [value for value in values if not value.strip()]
            if empty_values:
                raise ASTValidationError(
                    f"Structure: 'oneOf' on '{entity}.{field}' contains an empty value—"
                    f"it would be indistinguishable from an unfilled field on screen."
                )
            duplicates = [value for value in set(values) if values.count(value) > 1]
            if duplicates:
                raise ASTValidationError(
                    f"Structure: 'oneOf' on '{entity}.{field}' repeats "
                    f"{', '.join(repr(duplicate) for duplicate in sorted(duplicates))}—a choice list "
                    f"that offers the same option twice is a data entry error."
                )
            if entity in self.enumerated_fields and field in self.enumerated_fields[entity]:
                raise ASTValidationError(
                    f"Structure: two 'oneOf' rules on '{entity}.{field}'—which list would apply?"
                )
            if any(generated["entity"] == entity and generated["field"] == field for generated in self.generated_fields):
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'generated' and 'oneOf'—"
                    f"the server writes it itself, so the choice list would never be read."
                )
            self.enumerated_fields.setdefault(entity, {})[field] = list(values)
