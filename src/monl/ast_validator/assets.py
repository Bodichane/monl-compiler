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
                f"Structure: {ou} expects a non-empty file path.")
        chemin = valeur.strip()
        if image and "://" in chemin:
            raise ASTValidationError(
                f"Structure: {ou} is '{chemin}', a remote address, but type "
                f"'Image' designates a LOCAL file that the compiler verifies. monl makes "
                f"no network calls, so it cannot verify a URL. Place the file "
                f"in the assets directory, or declare this field as 'String' for a remote "
                f"address (not verified).")
        if chemin.startswith(("/", "\\")) or ":" in chemin.split("/")[0]:
            raise ASTValidationError(
                f"Structure: {ou} is '{chemin}', an ABSOLUTE path. Assets are relative "
                f"to the project; otherwise the site could only be served from this machine.")
        if ".." in chemin.replace("\\", "/").split("/"):
            raise ASTValidationError(
                f"Structure: {ou} is '{chemin}', which TRAVELS outside the project ('..'). An asset "
                f"must live in the project to be deployed with it.")

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
        essayes = " or ".join(os.path.relpath(c, self.base_dir) for c in candidats)
        raise ASTValidationError(
            f"Structure: {ou} points to '{chemin}', which does not exist ({essayes} not found). "
            f"A declared but missing asset produces a broken image online, detectable only "
            f"by looking at the page -- that is why compilation fails here.")

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
                f"Structure: the 'seed {entity}' block is attached to '{cible}', "
                f"which is not a declared entity.")
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
                f"Structure: the 'seed {entity}' block is attached to '{cible}', but "
                f"no relation links them (e.g. '{cible} hasMany {entity}') -- there "
                f"is no column to store this attachment.")
        # POINT 99 : la colonne d'un parent ACTEUR porte un identifiant de
        # COMPTE, pas l'id d'une ligne. Un seed s'insère avant qu'aucun compte
        # n'existe : il n'y a rien à y désigner.
        if cible in self.actors:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to actor "
                f"'{cible}'. This column stores an ACCOUNT identifier, "
                f"set at creation from the caller's token -- demo data is inserted "
                f"at startup, when no account exists yet, so there is no one to designate.")
        if champ not in self.entities[cible]:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block designates its parent by "
                f"'{cible}.{champ}', which is not a declared field on '{cible}'.")
        type_declare = self.entities[cible][champ]
        if type_declare not in self.TYPES_DESIGNATION:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block designates its parent by "
                f"'{cible}.{champ}', of type {type_declare}. Designating a row "
                f"requires a field that NAMES it: "
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
                f"Structure: the 'seed {entity}' block is attached to a "
                f"'{cible}' that no 'seed' block has declared yet. Demo data "
                f"is inserted in block order: write 'seed {cible}' BEFORE 'seed {entity}'.")
        correspondances = [ligne for bloc in deja for ligne in bloc["rows"]
                           if ligne.get(champ) == valeur]
        if not correspondances:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to {cible} "
                f"'{champ}: \"{valeur}\"', which no row in 'seed {cible}' "
                f"contains. A typo here would leave the storefront incomplete without "
                f"any indication.")
        if len(correspondances) > 1:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to {cible} "
                f"'{champ}: \"{valeur}\"', but {len(correspondances)} rows in "
                f"'seed {cible}' have this value -- there is no way to tell which one. "
                f"Designate it using a field whose values are distinct.")

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

        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'seed' block targets entity '{entity}', which does not exist.")
            entity_fields = self.entities[entity]
            if seed.get("parent"):
                self._valider_parent_de_seed(entity, seed["parent"])
            for index, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    self._verifier_cellule_de_seed(entity, entity_fields, index, field, value)
            self.seeds.append(seed)

    def _verifier_cellule_de_seed(self, entity, entity_fields, index, field, value):
        """Une valeur de `seed` : champ déclaré, type respecté, jamais d'Upload,
        image présente. Extraite de `_valider_assets_et_seeds` (plafond de
        complexité) ; refus et messages inchangés."""
        numeric_types = {"Integer", "Float", "Money"}
        if field not in entity_fields:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block (row {index}) references field "
                f"'{field}', which is not declared on '{entity}'."
            )
        declared_type = entity_fields[field]
        is_number = isinstance(value, (int, float)) and not isinstance(value, bool)
        if declared_type in numeric_types and not is_number:
            raise ASTValidationError(
                f"Structure: 'seed {entity}' (row {index}), field '{field}' of type "
                f"{declared_type} expects a number, received a string."
            )
        if declared_type not in numeric_types and is_number:
            raise ASTValidationError(
                f"Structure: 'seed {entity}' (row {index}), field '{field}' of type "
                f"{declared_type} expects a quoted string, received a number."
            )
        if declared_type == "Upload":
            raise ASTValidationError(
                f"Structure: a seed cannot provide '{entity}.{field}' "
                "of type Upload. Bytes arrive only at runtime through "
                "the multipart route, never in the spec or sealed artifacts.")
        if declared_type == "Image":
            location = f"seed {entity} (row {index}), field '{field}'"
            self._verifier_forme_chemin_asset(value, location, image=True)
            self._verifier_asset_present(value, location)
