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
                    f"Structure : '{ou}' doit référencer 'Entite.champ', reçu '{reference}'.")
            entite, champ = reference.split(".", 1)
            if entite not in self.entities:
                raise ASTValidationError(
                    f"Structure : '{ou}' référence l'entité '{entite}', qui n'existe pas. "
                    f"Entités déclarées : {', '.join(sorted(self.entities))}.")
            type_champ = self.entities[entite].get(champ)
            if type_champ is None:
                proches = [c for c in self.entities[entite] if c.lower() == champ.lower()]
                indice = f" Peut-être '{proches[0]}' ?" if proches else ""
                raise ASTValidationError(
                    f"Structure : '{ou}' référence le champ '{champ}', que l'entité "
                    f"'{entite}' ne déclare pas.{indice} Champs de {entite} : "
                    f"{', '.join(self.entities[entite])}. Une contrainte sur un champ "
                    f"inexistant ne s'applique à rien -- et laisse croire le contraire.")

            if type_champ == "Upload":
                raise ASTValidationError(
                    f"Structure : '{ou}' ne s'applique pas à '{reference}' de type Upload. "
                    "Un dépôt se contraint par 'upload max … types …', qui produit "
                    "les refus multipart réels du backend.")

            contraintes = self.field_constraints.setdefault((entite, champ), {})
            if type_regle in contraintes:
                raise ASTValidationError(
                    f"Structure : '{ou}' est déclaré deux fois sur le même champ.")
            if type_regle in ("required", "unique"):
                contraintes[type_regle] = True
                continue

            # 'min'/'max' : la grammaire n'accepte qu'un entier positif.
            try:
                borne = int(rule.get("value"))
            except (TypeError, ValueError):
                raise ASTValidationError(
                    f"Structure : '{ou}' attend un nombre entier "
                    f"(reçu '{rule.get('value')}').") from None
            if type_champ in self.BORNES_TEXTE:
                limite = self.LONGUEUR_COLONNE[type_champ]
                if borne > limite:
                    raise ASTValidationError(
                        f"Structure : '{ou} {borne}' dépasse la longueur de la colonne "
                        f"'{champ}' ({type_champ} = {limite} caractères). La contrainte "
                        f"promettrait une donnée que la base ne peut pas tenir.")
                contraintes[type_regle] = {"portee": "longueur", "valeur": borne}
            elif type_champ in self.BORNES_NOMBRE:
                contraintes[type_regle] = {"portee": "valeur", "valeur": borne}
            else:
                raise ASTValidationError(
                    f"Structure : '{ou}' porte sur '{champ}' de type '{type_champ}', "
                    f"que '{type_regle}' ne sait pas borner. Bornes de LONGUEUR sur "
                    f"{', '.join(self.BORNES_TEXTE)} ; bornes de VALEUR sur "
                    f"{', '.join(self.BORNES_NOMBRE)}.")

        for (entite, champ), contraintes in self.field_constraints.items():
            bas, haut = contraintes.get("min"), contraintes.get("max")
            if bas and haut and bas["valeur"] > haut["valeur"]:
                raise ASTValidationError(
                    f"Structure : '{entite}.{champ}' a min {bas['valeur']} et "
                    f"max {haut['valeur']} : aucune valeur ne satisfait les deux.")

    def _valider_champs_masques(self):
        """Valide les règles ``hidden`` et prépare les champs à masquer."""
        self.masked_fields = set()
        for rule in self.rules:
            if rule["type"] != "hidden":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'hidden' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'hidden' cible l'entité '{entity}' qui n'existe pas.")
            if field not in self.entities[entity]:
                raise ASTValidationError(
                    f"Structure : la règle 'hidden' référence le champ '{field}', qui n'est pas un attribut "
                    f"déclaré de '{entity}' (ou est 'id', qui ne peut pas être masqué)."
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
                    f"Structure : la règle 'categorized' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'categorized' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("Integer", "Float"):
                raise ASTValidationError(
                    f"Structure : 'categorized' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"Integer ou Float déclaré (reçu : {field_type or 'champ inexistant'})."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'categorized' -- incompatible : "
                    f"'hidden' retire le champ, 'categorized' le remplace par une catégorie dérivée de sa valeur."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'categorized' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            seen_fields.add((entity, field))

            clauses = rule["value"]
            if len(clauses) < 2:
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' doit déclarer au moins un seuil ('below') "
                    f"et un palier de secours ('otherwise')."
                )
            for clause in clauses[:-1]:
                if "otherwise" in clause:
                    raise ASTValidationError(
                        f"Structure : 'categorized' sur '{entity}.{field}' -- seul le DERNIER palier peut être "
                        f"'otherwise' (palier de secours), reçu ailleurs dans la liste."
                    )
            if "otherwise" not in clauses[-1]:
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' doit se terminer par un palier 'otherwise' "
                    f"(palier de secours qui couvre toute valeur au-delà du dernier seuil)."
                )
            thresholds = [clause["below"] for clause in clauses[:-1]]
            if thresholds != sorted(set(thresholds)) or len(thresholds) != len(set(thresholds)):
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' -- les seuils 'below' doivent être "
                    f"strictement croissants (reçu : {thresholds})."
                )
            if any(not clause["label"].strip() for clause in clauses):
                raise ASTValidationError(
                    f"Structure : 'categorized' sur '{entity}.{field}' -- chaque palier doit avoir un libellé non vide."
                )
            self.categorized_fields.append({"entity": entity, "field": field, "clauses": clauses})

    def _valider_champs_enumeres(self):
        """Valide les champs texte limités à une liste de valeurs."""
        self.enumerated_fields = {}
        for rule in self.rules:
            if rule["type"] != "oneOf":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'oneOf' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'oneOf' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type not in ("String", "Text"):
                raise ASTValidationError(
                    f"Structure : 'oneOf' cible '{entity}.{field}', qui doit être un champ String ou Text "
                    f"(reçu : {field_type or 'champ inexistant'}) — pour un nombre, 'min'/'max' ou "
                    f"'categorized' disent déjà cela."
                )
            values = rule["value"]
            if len(values) < 2:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' n'énumère qu'une valeur — "
                    f"un champ qui n'a qu'une valeur possible n'a pas besoin d'être saisi."
                )
            empty_values = [value for value in values if not value.strip()]
            if empty_values:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' contient une valeur vide — "
                    f"elle serait indistinguable d'un champ non rempli à l'écran."
                )
            duplicates = [value for value in set(values) if values.count(value) > 1]
            if duplicates:
                raise ASTValidationError(
                    f"Structure : 'oneOf' sur '{entity}.{field}' répète "
                    f"{', '.join(repr(duplicate) for duplicate in sorted(duplicates))} — une liste de choix "
                    f"qui propose deux fois la même chose est une erreur de saisie."
                )
            if entity in self.enumerated_fields and field in self.enumerated_fields[entity]:
                raise ASTValidationError(
                    f"Structure : deux règles 'oneOf' sur '{entity}.{field}' — laquelle des deux listes s'appliquerait ?"
                )
            if any(generated["entity"] == entity and generated["field"] == field for generated in self.generated_fields):
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'generated' et 'oneOf' — "
                    f"le serveur l'écrit lui-même, la liste de choix ne serait jamais lue."
                )
            self.enumerated_fields.setdefault(entity, {})[field] = list(values)
