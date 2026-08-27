"""Les champs que le SERVEUR peuple, et que le client ne peut pas écrire.

`generated` (brique 7), `timestamp` (point 89) et `numbered` (point 102).
Leur point commun est le point 78 : un champ peuplé par le serveur doit
sortir du schéma d'entrée ET de la route Update, sinon la valeur est
écartée en silence — pire qu'un refus."""

import re

from .socle import ASTValidationError


class ChampsServeurMixin:
    """Les champs que le SERVEUR peuple, et que le client ne peut pas écrire."""

    def _valider_champs_generes(self):
        """Valide les pseudonymes générés côté serveur."""
        self.generated_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "generated":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'generated' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : la règle 'generated' cible l'entité '{entity}' qui n'existe pas.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                raise ASTValidationError(
                    f"Structure : 'generated' cible le champ '{entity}.{field}', qui doit être un attribut "
                    f"String déclaré (reçu : {field_type or 'champ inexistant'}) -- un pseudonyme est toujours "
                    f"du texte court."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'generated' -- incompatible : "
                    f"'generated' produit déjà une valeur sûre à afficher, la masquer en plus n'a pas de sens."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'generated' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            seen_fields.add((entity, field))
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est 'generated', mais '{entity}.Create' est 'public' -- "
                    f"incompatible : 'generated' exige un appelant authentifié dont dériver le pseudonyme."
                )
            self.generated_fields.append({"entity": entity, "field": field})

    def _valider_champs_horodates(self):
        """Valide les instants de création attribués par le serveur."""
        self.timestamp_fields = []
        seen_fields = set()
        for rule in self.rules:
            if rule["type"] != "timestamp":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'timestamp' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "DateTime":
                indice = (
                    " -- 'Date' tronquerait l'heure que le serveur connaît, et deux enregistrements du même jour "
                    "ne seraient plus ordonnables" if field_type == "Date" else ""
                )
                raise ASTValidationError(
                    f"Structure : 'timestamp' cible le champ '{entity}.{field}', qui doit être "
                    f"un attribut DateTime déclaré (reçu : {field_type or 'champ inexistant'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et 'timestamp' -- "
                    f"incompatible : le client ne peut pas l'écrire et ne pourrait pas le lire, "
                    f"donc ce champ n'existerait nulle part."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'timestamp' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            if any(timestamp["entity"] == entity for timestamp in self.timestamp_fields):
                other = next(timestamp["field"] for timestamp in self.timestamp_fields if timestamp["entity"] == entity)
                raise ASTValidationError(
                    f"Structure : '{entity}' porte deux champs 'timestamp' ('{other}' et "
                    f"'{field}') -- tous deux recevraient le MÊME instant de création. "
                    f"Un horodatage de modification serait une autre brique, pas celle-ci."
                )
            seen_fields.add((entity, field))
            self.timestamp_fields.append({"entity": entity, "field": field})

    # Jalons acceptés dans un gabarit de numéro. La séquence est le seul
    # obligatoire : sans elle, tous les enregistrements porteraient le même
    # numéro — une règle qui ne produit rien (point 85), doublée d'un index
    # unique qui refuserait la deuxième création.
    JALONS_DATE = ("YYYY", "MM", "DD")

    def _periode_du_gabarit(self, gabarit):
        """Sur quoi la séquence se REMET À ZÉRO : '' (jamais), 'YYYY',
        'YYYY-MM' ou 'YYYY-MM-DD'.

        Déduite des jalons de date présents, jamais déclarée à part : deux
        façons de dire la même chose finiraient par se contredire."""
        présents = [j for j in self.JALONS_DATE if "{" + j + "}" in gabarit]
        return "-".join(présents)

    def _valider_gabarit_de_numero(self, entity, field, gabarit):
        """Cinq refus sur la forme du gabarit lui-même."""
        jalons = re.findall(r"\{([^{}]*)\}", gabarit)
        # Une accolade orpheline ne serait pas vue par la recherche ci-dessus :
        # la compter séparément, sinon 'CMD-{YYYY' passerait pour du texte.
        if gabarit.count("{") != len(jalons) or gabarit.count("}") != len(jalons):
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' a une "
                f"accolade orpheline : {gabarit!r}.")
        sequences = [j for j in jalons if set(j) == {"N"}]
        inconnus = [j for j in jalons
                    if j not in self.JALONS_DATE and set(j) != {"N"}]
        if inconnus:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' emploie "
                f"{', '.join(repr('{' + j + '}') for j in inconnus)}, qui ne veut rien "
                f"dire. Jalons acceptés : '{{YYYY}}', '{{MM}}', '{{DD}}', et une suite "
                f"de N pour la séquence ('{{NNNN}}' = quatre chiffres).")
        if not sequences:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' n'a aucune "
                f"séquence ('{{NNNN}}') -- tous les enregistrements porteraient le MÊME "
                f"numéro, ce qui n'en est pas un.")
        if len(sequences) > 1:
            raise ASTValidationError(
                f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' contient "
                f"{len(sequences)} séquences -- rien ne dit laquelle s'incrémente.")
        # Une date incomplète fait se répéter la séquence : 'CMD-{MM}-{NNNN}'
        # redonne 'CMD-03-0001' tous les mois de mars. L'index unique
        # l'attraperait, mais un an plus tard et en production.
        # strict=False assumé : on apparie chaque jalon avec le SUIVANT, donc
        # les deux suites n'ont volontairement pas la même longueur.
        for précédent, suivant in zip(self.JALONS_DATE, self.JALONS_DATE[1:],
                                      strict=False):
            if "{" + suivant + "}" in gabarit and "{" + précédent + "}" not in gabarit:
                raise ASTValidationError(
                    f"Structure : le gabarit de 'numbered' sur '{entity}.{field}' emploie "
                    f"'{{{suivant}}}' sans '{{{précédent}}}' -- la séquence se remettrait "
                    f"à zéro sans que le numéro dise de quelle période il s'agit, et "
                    f"deux enregistrements finiraient par porter le même.")

    def _valider_champs_numerotes(self):
        """Valide les numéros lisibles générés côté serveur."""
        self.numbered_fields = []
        for rule in self.rules:
            if rule["type"] != "numbered":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' doit référencer 'Entite.champ', reçu '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure : la règle 'numbered' cible l'entité '{entity}' qui n'existe pas."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                indice = (
                    " -- un 'UUID' vérifie sa forme depuis le point 101, et un numéro lisible n'en a pas la forme"
                    if field_type == "UUID" else ""
                )
                raise ASTValidationError(
                    f"Structure : 'numbered' cible le champ '{entity}.{field}', qui doit "
                    f"être un attribut String déclaré (reçu : {field_type or 'champ inexistant'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure : '{entity}.{field}' est à la fois 'hidden' et "
                    f"'numbered' -- incompatible : le client ne peut pas l'écrire et ne "
                    f"pourrait pas le lire, donc ce numéro n'existerait pour personne."
                )
            if any(numbered["entity"] == entity and numbered["field"] == field for numbered in self.numbered_fields):
                raise ASTValidationError(
                    f"Structure : plusieurs règles 'numbered' déclarées pour '{entity}.{field}' -- une seule autorisée."
                )
            self._valider_gabarit_de_numero(entity, field, rule["value"])
            self.numbered_fields.append({
                "entity": entity, "field": field, "format": rule["value"],
                "periode": self._periode_du_gabarit(rule["value"]),
            })
