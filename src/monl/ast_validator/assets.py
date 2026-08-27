"""Les fichiers fournis par l'HUMAIN, et le jeu de démonstration.

Brique 13 (point 83) : deux familles de contrôles, séparées à dessein — de
FORME (chemin absolu, remontée `..`, URL distante sous `Image`), toujours
actifs car purs ; d'EXISTENCE seulement quand `base_dir` est connu, sinon
le validateur se TAIT plutôt que de deviner. S'y ajoute le rattachement
d'un `seed` enfant (brique 21, point 100), qui désigne son parent par une
VALEUR et jamais par un rang."""

import os

from .socle import DEFAULT_ASSETS_DIR, ASTValidationError


def candidats_asset(base_dir, dossier, chemin):
    """Les deux endroits où un asset déclaré peut vivre, dans l'ordre d'essai.

    Une valeur de seed vaut déjà 'assets/x.jpg' (c'est l'URL que le navigateur
    demandera) ; un logo est déclaré par son SEUL nom, le contrat préfixant
    ensuite par le dossier. Les deux formes sont donc légitimes."""
    chemin = chemin.strip()
    return [os.path.join(base_dir, chemin),
            os.path.join(base_dir, dossier, chemin)]


def resoudre_asset(base_dir, dossier, chemin):
    """Où vit réellement un asset déclaré, ou None.

    SOURCE UNIQUE de la résolution (point 84) : le validateur s'en sert pour
    REFUSER à la compilation, l'outil 'monl assets' pour RAPPORTER. Deux
    implémentations finiraient par diverger — l'outil dirait « présent » là où
    le compilateur dirait « absent »."""
    return next((c for c in candidats_asset(base_dir, dossier, chemin)
                 if os.path.isfile(c)), None)


class AssetsMixin:
    """Les fichiers fournis par l'HUMAIN, et le jeu de démonstration."""

    def _verifier_forme_chemin_asset(self, valeur, ou, image=False):
        """Contrôles PURS sur un chemin d'asset — aucun accès disque, donc
        toujours actifs, y compris quand la spec est validée en mémoire.

        Un chemin absolu ou remontant sort du projet : servi tel quel par le
        navigateur il ne mènerait à rien, et écrit dans un seed il donne
        l'illusion d'un asset. Une URL distante, elle, est légitime — mais pas
        sous le type 'Image', dont toute la valeur est d'être vérifiable : le
        compilateur ne fait aucun appel réseau, il ne peut donc rien affirmer
        d'une URL. `String` reste là pour ce cas."""
        if not isinstance(valeur, str) or not valeur.strip():
            raise ASTValidationError(
                f"Structure : {ou} attend un chemin de fichier non vide.")
        chemin = valeur.strip()
        if image and "://" in chemin:
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', une adresse distante, alors que le type "
                f"'Image' désigne un fichier LOCAL que le compilateur vérifie. monl ne fait "
                f"aucun appel réseau : il ne peut rien affirmer d'une URL. Déposer le fichier "
                f"dans le dossier d'assets, ou déclarer ce champ 'String' pour une adresse "
                f"distante (non vérifiée).")
        if chemin.startswith(("/", "\\")) or ":" in chemin.split("/")[0]:
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', un chemin ABSOLU. Les assets sont relatifs "
                f"au projet, sans quoi le site ne serait servable que depuis cette machine.")
        if ".." in chemin.replace("\\", "/").split("/"):
            raise ASTValidationError(
                f"Structure : {ou} vaut '{chemin}', qui REMONTE hors du projet ('..'). Un asset "
                f"doit vivre dans le projet pour être déployé avec lui.")

    def _verifier_asset_present(self, valeur, ou):
        """Contrôle d'EXISTENCE — seulement quand on sait où est le projet.

        Sans 'base_dir' (spec validée en mémoire), on se TAIT plutôt que de
        deviner : un faux refus serait pire que l'absence de contrôle. Le
        silence est explicite, pas accidentel."""
        if not self.base_dir:
            return
        chemin = valeur.strip()
        dossier = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        if resoudre_asset(self.base_dir, dossier, chemin):
            return
        candidats = candidats_asset(self.base_dir, dossier, chemin)
        essayes = " ni ".join(os.path.relpath(c, self.base_dir) for c in candidats)
        raise ASTValidationError(
            f"Structure : {ou} désigne '{chemin}', qui n'existe pas ({essayes} introuvable). "
            f"Un asset déclaré mais absent donne une image cassée en ligne, que seul l'œil "
            f"repère -- c'est pourquoi la compilation échoue ici.")

    # Types sur lesquels une valeur de seed peut DÉSIGNER une ligne parente.
    # Un nombre est exclu : rapprocher deux flottants est déjà douteux, et un
    # prix ou un stock ne nomme rien — la désignation doit se lire.
    TYPES_DESIGNATION = ("String", "Text", "Email", "UUID")

    def _valider_parent_de_seed(self, entity, parent):
        """BRIQUE 21 (point 100) : `seed Enfant for Parent.champ "valeur"`.

        Sept refus, et le premier est celui qui porte la brique : la ligne
        parente doit être désignée SANS AMBIGUÏTÉ à la compilation. Un seed qui
        rattacherait « au hasard parmi deux » produirait une vitrine différente
        d'une compilation à l'autre, et personne ne le verrait avant de regarder
        l'écran."""
        cible = parent["entity"]
        champ = parent["field"]
        valeur = parent["value"]
        if cible not in self.entities:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à '{cible}', "
                f"qui n'est pas une entité déclarée.")
        # Même convention de relation que partout ailleurs (voir
        # _compute_fk_placements) : sans elle, aucune colonne ne porterait le
        # rattachement.
        lie = any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == cible and rel["target"] == entity)
            or (rel["type"] == "belongsTo"
                and rel["source"] == entity and rel["target"] == cible)
            for rel in self.relations
        )
        if not lie:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à '{cible}', mais "
                f"aucune relation ne les lie (ex. '{cible} hasMany {entity}') -- il "
                f"n'existe donc aucune colonne où écrire ce rattachement.")
        # POINT 99 : la colonne d'un parent ACTEUR porte un identifiant de
        # COMPTE, pas l'id d'une ligne. Un seed s'insère avant qu'aucun compte
        # n'existe : il n'y a rien à y désigner.
        if cible in self.actors:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à l'acteur "
                f"'{cible}'. Cette colonne-là porte un identifiant de COMPTE, "
                f"renseigné à la création depuis le jeton de l'appelant -- un jeu "
                f"de démonstration s'insère au démarrage, quand aucun compte "
                f"n'existe encore, et n'a donc personne à désigner.")
        if champ not in self.entities[cible]:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' désigne son parent par "
                f"'{cible}.{champ}', qui n'est pas un champ déclaré sur '{cible}'.")
        type_declare = self.entities[cible][champ]
        if type_declare not in self.TYPES_DESIGNATION:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' désigne son parent par "
                f"'{cible}.{champ}', de type {type_declare}. Désigner une ligne "
                f"demande un champ qui la NOMME : "
                f"{', '.join(self.TYPES_DESIGNATION)}.")
        # L'ordre compte pour de vrai : les données de démonstration sont
        # insérées table par table, dans l'ordre de DÉCLARATION des blocs. Un
        # parent semé après son enfant ne serait pas encore en base au moment de
        # rattacher, et la ligne serait écartée au démarrage. Refuser ici plutôt
        # que de réordonner en silence : la spec dirait une chose et le serveur
        # en ferait une autre.
        deja = [s for s in self.seeds if s["entity"] == cible]
        if not deja:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache à un "
                f"'{cible}' qu'aucun bloc 'seed' n'a encore déclaré. Les données "
                f"de démonstration sont insérées dans l'ordre des blocs : "
                f"écrire 'seed {cible}' AVANT 'seed {entity}'.")
        correspondances = [ligne for bloc in deja for ligne in bloc["rows"]
                           if ligne.get(champ) == valeur]
        if not correspondances:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache au {cible} "
                f"'{champ}: \"{valeur}\"', qu'aucune ligne de 'seed {cible}' ne "
                f"porte. Une coquille ici donnerait une vitrine amputée sans que "
                f"rien ne le dise.")
        if len(correspondances) > 1:
            raise ASTValidationError(
                f"Structure : le bloc 'seed {entity}' se rattache au {cible} "
                f"'{champ}: \"{valeur}\"', mais {len(correspondances)} lignes de "
                f"'seed {cible}' portent cette valeur -- rien ne dit à laquelle. "
                f"Désigner par un champ dont les valeurs sont distinctes.")

    def _valider_assets_et_seeds(self):
        """Valide les assets locaux et les données de démonstration."""
        self.assets = dict(self.assets_raw)
        assets_dir = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        self._verifier_forme_chemin_asset(assets_dir, "assets.dir")
        self.assets["dir"] = assets_dir
        for key in ("logo", "favicon"):
            if key not in self.assets_raw:
                continue
            value = self.assets_raw[key]
            self._verifier_forme_chemin_asset(value, f"assets.{key}")
            self._verifier_asset_present(value, f"assets.{key}")

        numeric_types = {"Integer", "Float", "Money"}
        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure : le bloc 'seed' cible l'entité '{entity}' qui n'existe pas.")
            entity_fields = self.entities[entity]
            if seed.get("parent"):
                self._valider_parent_de_seed(entity, seed["parent"])
            for index, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    if field not in entity_fields:
                        raise ASTValidationError(
                            f"Structure : le bloc 'seed {entity}' (ligne {index}) référence le champ "
                            f"'{field}', qui n'est pas déclaré sur '{entity}'."
                        )
                    declared_type = entity_fields[field]
                    is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
                    if declared_type in numeric_types and not is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {index}), champ '{field}' de type "
                            f"{declared_type} attend un nombre, reçu une chaîne."
                        )
                    if declared_type not in numeric_types and is_number:
                        raise ASTValidationError(
                            f"Structure : 'seed {entity}' (ligne {index}), champ '{field}' de type "
                            f"{declared_type} attend une chaîne entre guillemets, reçu un nombre."
                        )
                    if declared_type == "Upload":
                        raise ASTValidationError(
                            f"Structure : un seed ne peut pas fournir '{entity}.{field}' "
                            "de type Upload. Les octets arrivent uniquement à "
                            "l'exécution par la route multipart, jamais dans la spec "
                            "ou les artefacts scellés.")
                    if declared_type == "Image":
                        location = f"seed {entity} (ligne {index}), champ '{field}'"
                        self._verifier_forme_chemin_asset(value, location, image=True)
                        self._verifier_asset_present(value, location)
            self.seeds.append(seed)
