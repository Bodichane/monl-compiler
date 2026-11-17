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
                    f"Structure: the 'generated' rule must reference 'Entity.field'; got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'generated' rule targets entity '{entity}', which does not exist.")
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                raise ASTValidationError(
                    f"Structure: 'generated' targets field '{entity}.{field}', which must be a declared "
                    f"String attribute (got: {field_type or 'field does not exist'}) -- a pseudonym is always "
                    f"short text."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and 'generated' -- incompatible: "
                    f"'generated' already produces a safe value to display; hiding it as well makes no sense."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure: multiple 'generated' rules declared for '{entity}.{field}' -- only one is allowed."
                )
            seen_fields.add((entity, field))
            if (entity, "Create") in self.public_actions:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is 'generated', but '{entity}.Create' is 'public' -- "
                    f"incompatible: 'generated' requires an authenticated caller from whom to derive the pseudonym."
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
                    f"Structure: the 'timestamp' rule must reference 'Entity.field'; got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'timestamp' rule targets entity '{entity}', which does not exist."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "DateTime":
                indice = (
                    " -- 'Date' would truncate the time known by the server, and two records from the same day "
                    "could no longer be ordered" if field_type == "Date" else ""
                )
                raise ASTValidationError(
                    f"Structure: 'timestamp' targets field '{entity}.{field}', which must be "
                    f"a declared DateTime attribute (got: {field_type or 'field does not exist'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and 'timestamp' -- "
                    f"incompatible: the client cannot write it and could not read it either, "
                    f"so this field would exist nowhere."
                )
            if (entity, field) in seen_fields:
                raise ASTValidationError(
                    f"Structure: multiple 'timestamp' rules declared for '{entity}.{field}' -- only one is allowed."
                )
            if any(timestamp["entity"] == entity for timestamp in self.timestamp_fields):
                other = next(timestamp["field"] for timestamp in self.timestamp_fields if timestamp["entity"] == entity)
                raise ASTValidationError(
                    f"Structure: '{entity}' has two 'timestamp' fields ('{other}' and "
                    f"'{field}') -- both would receive the SAME creation time. "
                    f"A modification timestamp would be a different feature, not this one."
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
                f"Structure: the 'numbered' format for '{entity}.{field}' has an "
                f"unmatched brace: {gabarit!r}.")
        sequences = [j for j in jalons if set(j) == {"N"}]
        inconnus = [j for j in jalons
                    if j not in self.JALONS_DATE and set(j) != {"N"}]
        if inconnus:
            raise ASTValidationError(
                f"Structure: the 'numbered' format for '{entity}.{field}' uses "
                f"{', '.join(repr('{' + j + '}') for j in inconnus)}, which has no "
                f"meaning. Accepted tokens: '{{YYYY}}', '{{MM}}', '{{DD}}', and a sequence "
                f"of Ns ('{{NNNN}}' = four digits).")
        if not sequences:
            raise ASTValidationError(
                f"Structure: the 'numbered' format for '{entity}.{field}' has no "
                f"sequence ('{{NNNN}}') -- all records would have the SAME "
                f"number, which would not be a number at all.")
        if len(sequences) > 1:
            raise ASTValidationError(
                f"Structure: the 'numbered' format for '{entity}.{field}' contains "
                f"{len(sequences)} sequences -- nothing says which one to increment.")
        # Une date incomplète fait se répéter la séquence : 'CMD-{MM}-{NNNN}'
        # redonne 'CMD-03-0001' tous les mois de mars. L'index unique
        # l'attraperait, mais un an plus tard et en production.
        # strict=False assumé : on apparie chaque jalon avec le SUIVANT, donc
        # les deux suites n'ont volontairement pas la même longueur.
        for précédent, suivant in zip(self.JALONS_DATE, self.JALONS_DATE[1:],
                                      strict=False):
            if "{" + suivant + "}" in gabarit and "{" + précédent + "}" not in gabarit:
                raise ASTValidationError(
                    f"Structure: the 'numbered' format for '{entity}.{field}' uses "
                    f"'{{{suivant}}}' without '{{{précédent}}}' -- the sequence would reset "
                    f"without the number identifying the period, and "
                    f"two records would eventually have the same number.")

    def _valider_champs_numerotes(self):
        """Valide les numéros lisibles générés côté serveur."""
        self.numbered_fields = []
        for rule in self.rules:
            if rule["type"] != "numbered":
                continue
            if "." not in rule["reference"]:
                raise ASTValidationError(
                    f"Structure: the 'numbered' rule must reference 'Entity.field'; got '{rule['reference']}'."
                )
            entity, field = rule["reference"].split(".", 1)
            if entity not in self.entities:
                raise ASTValidationError(
                    f"Structure: the 'numbered' rule targets entity '{entity}', which does not exist."
                )
            field_type = self.entities.get(entity, {}).get(field)
            if field_type != "String":
                indice = (
                    " -- a 'UUID' validates its format as of point 101, and a readable number does not have that format"
                    if field_type == "UUID" else ""
                )
                raise ASTValidationError(
                    f"Structure: 'numbered' targets field '{entity}.{field}', which must "
                    f"be a declared String attribute (got: {field_type or 'field does not exist'}){indice}."
                )
            if (entity, field) in self.masked_fields:
                raise ASTValidationError(
                    f"Structure: '{entity}.{field}' is both 'hidden' and "
                    f"'numbered' -- incompatible: the client cannot write it and could not "
                    f"read it either, so this number would exist for nobody."
                )
            if any(numbered["entity"] == entity and numbered["field"] == field for numbered in self.numbered_fields):
                raise ASTValidationError(
                    f"Structure: multiple 'numbered' rules declared for '{entity}.{field}' -- only one is allowed."
                )
            self._valider_gabarit_de_numero(entity, field, rule["value"])
            self.numbered_fields.append({
                "entity": entity, "field": field, "format": rule["value"],
                "periode": self._periode_du_gabarit(rule["value"]),
            })
