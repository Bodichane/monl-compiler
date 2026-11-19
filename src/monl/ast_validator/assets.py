"""The files supplied by the HUMAN, and the demo dataset.

Brick 13 (point 83): two families of checks, deliberately separate — FORM
(absolute path, `..` traversal, remote URL under `Image`), always active
because they are pure; EXISTENCE only when `base_dir` is known, otherwise
the validator stays QUIET rather than guessing. Added to it is the
attachment of a child `seed` (brick 21, point 100), which designates its
parent by a VALUE and never by a rank."""

import os

from .base import DEFAULT_ASSETS_DIR, ASTValidationError


def candidates_asset(base_dir, folder, path):
    """The two places where a declared asset can live, in the order tried.

    A seed value is already 'assets/x.jpg' (it is the URL the browser will
    request); a logo is declared by its name ALONE, the contract then
    prefixing it with the folder. Both forms are therefore legitimate."""
    path = path.strip()
    return [os.path.join(base_dir, path),
            os.path.join(base_dir, folder, path)]


def resolve_asset(base_dir, folder, path):
    """Where a declared asset really lives, or None.

    SINGLE SOURCE of resolution (point 84): the validator uses it to REFUSE at
    compile time, the 'monl assets' tool to REPORT. Two implementations would
    eventually diverge — the tool would say "present" where the compiler would
    say "missing"."""
    return next((c for c in candidates_asset(base_dir, folder, path)
                 if os.path.isfile(c)), None)


class AssetsMixin:
    """The files supplied by the HUMAN, and the demo dataset."""

    def _check_forme_path_asset(self, valeur, ou, image=False):
        """PURE checks on an asset path — no disk access, hence always active,
        including when the spec is validated in memory.

        An absolute or climbing path leaves the project: served as is by the
        browser it would lead nowhere, and written in a seed it gives the illusion
        of an asset. A remote URL is legitimate — but not under the 'Image' type,
        whose whole value is to be verifiable: the compiler makes no network call,
        so it can assert nothing about a URL. `String` remains for that case."""
        if not isinstance(valeur, str) or not valeur.strip():
            raise ASTValidationError(
                f"Structure: {ou} expects a non-empty file path.")
        path = valeur.strip()
        if image and "://" in path:
            raise ASTValidationError(
                f"Structure: {ou} is '{path}', a remote address, but type "
                f"'Image' designates a LOCAL file that the compiler verifies. monl makes "
                f"no network calls, so it cannot verify a URL. Place the file "
                f"in the assets directory, or declare this field as 'String' for a remote "
                f"address (not verified).")
        if path.startswith(("/", "\\")) or ":" in path.split("/")[0]:
            raise ASTValidationError(
                f"Structure: {ou} is '{path}', an ABSOLUTE path. Assets are relative "
                f"to the project; otherwise the site could only be served from this machine.")
        if ".." in path.replace("\\", "/").split("/"):
            raise ASTValidationError(
                f"Structure: {ou} is '{path}', which TRAVELS outside the project ('..'). An asset "
                f"must live in the project to be deployed with it.")

    def _check_asset_present(self, valeur, ou):
        """EXISTENCE check — only when we know where the project is.

        Without 'base_dir' (spec validated in memory), we stay QUIET rather than
        guessing: a false refusal would be worse than no check. The silence is
        explicit, not accidental."""
        if not self.base_dir:
            return
        path = valeur.strip()
        folder = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        if resolve_asset(self.base_dir, folder, path):
            return
        candidates = candidates_asset(self.base_dir, folder, path)
        tried = " or ".join(os.path.relpath(c, self.base_dir) for c in candidates)
        raise ASTValidationError(
            f"Structure: {ou} points to '{path}', which does not exist ({tried} not found). "
            f"A declared but missing asset produces a broken image online, detectable only "
            f"by looking at the page -- that is why compilation fails here.")

    # Types on which a seed value can DESIGNATE a parent row. A number is
    # excluded: matching two floats is already dubious, and a price or a stock
    # names nothing — the designation must be readable.
    TYPES_DESIGNATION = ("String", "Text", "Email", "UUID")

    def _relation_parent_child(self, parent, child):
        """True if a declared relation links `parent` to `child`, in either
        direction. Extracted from `_valider_parent_de_seed` (ceiling)."""
        return any(
            (rel["type"] in ("hasMany", "hasOne")
             and rel["source"] == parent and rel["target"] == child)
            or (rel["type"] == "belongsTo"
                and rel["source"] == child and rel["target"] == parent)
            for rel in self.relations
        )

    def _validate_parent_of_seed(self, entity, parent):
        """BRICK 21 (point 100): `seed Child for Parent.field "value"`.

        Seven refusals, and the first is the one that carries the brick: the
        parent row must be designated WITHOUT AMBIGUITY at compile time. A seed
        that attached "at random among two" would produce a different storefront
        from one compilation to the next, and nobody would see it before looking
        at the screen."""
        target = parent["entity"]
        field = parent["field"]
        valeur = parent["value"]
        if target not in self.entities:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to '{target}', "
                f"which is not a declared entity.")
        # Same relation convention as everywhere else (see
        # _compute_fk_placements): without it, no column would carry the
        # attachment.
        if not self._relation_parent_child(target, entity):
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to '{target}', but "
                f"no relation links them (e.g. '{target} hasMany {entity}') -- there "
                f"is no column to store this attachment.")
        # POINT 99: an ACTOR parent's column carries an ACCOUNT identifier, not
        # a row id. A seed is inserted before any account exists: there is
        # nothing to designate there.
        if target in self.actors:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to actor "
                f"'{target}'. This column stores an ACCOUNT identifier, "
                f"set at creation from the caller's token -- demo data is inserted "
                f"at startup, when no account exists yet, so there is no one to designate.")
        if field not in self.entities[target]:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block designates its parent by "
                f"'{target}.{field}', which is not a declared field on '{target}'.")
        type_declare = self.entities[target][field]
        if type_declare not in self.TYPES_DESIGNATION:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block designates its parent by "
                f"'{target}.{field}', of type {type_declare}. Designating a row "
                f"requires a field that NAMES it: "
                f"{', '.join(self.TYPES_DESIGNATION)}.")
        # The order really matters: demo data is inserted table by table, in
        # the DECLARATION order of the blocks. A parent seeded after its child
        # would not yet be in the database when attaching, and the row would be
        # discarded at startup. Refuse here rather than silently reorder: the
        # spec would say one thing and the server would do another.
        already = [s for s in self.seeds if s["entity"] == target]
        if not already:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to a "
                f"'{target}' that no 'seed' block has declared yet. Demo data "
                f"is inserted in block order: write 'seed {target}' BEFORE 'seed {entity}'.")
        matches = [line for block in already for line in block["rows"]
                           if line.get(field) == valeur]
        if not matches:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to {target} "
                f"'{field}: \"{valeur}\"', which no row in 'seed {target}' "
                f"contains. A typo here would leave the storefront incomplete without "
                f"any indication.")
        if len(matches) > 1:
            raise ASTValidationError(
                f"Structure: the 'seed {entity}' block is attached to {target} "
                f"'{field}: \"{valeur}\"', but {len(matches)} rows in "
                f"'seed {target}' have this value -- there is no way to tell which one. "
                f"Designate it using a field whose values are distinct.")

    def _validate_assets_and_seeds(self):
        """Validates the local assets and the demo data."""
        self.assets = dict(self.assets_raw)
        assets_dir = self.assets.get("dir", DEFAULT_ASSETS_DIR)
        self._check_forme_path_asset(assets_dir, "assets.dir")
        self.assets["dir"] = assets_dir
        for key in ("logo", "favicon"):
            if key not in self.assets_raw:
                continue
            value = self.assets_raw[key]
            self._check_forme_path_asset(value, f"assets.{key}")
            self._check_asset_present(value, f"assets.{key}")

        self.seeds = []
        for seed in self.seeds_raw:
            entity = seed["entity"]
            if entity not in self.entities:
                raise ASTValidationError(f"Structure: the 'seed' block targets entity '{entity}', which does not exist.")
            entity_fields = self.entities[entity]
            if seed.get("parent"):
                self._validate_parent_of_seed(entity, seed["parent"])
            for index, row in enumerate(seed["rows"], start=1):
                for field, value in row.items():
                    self._check_cell_of_seed(entity, entity_fields, index, field, value)
            self.seeds.append(seed)

    def _check_cell_of_seed(self, entity, entity_fields, index, field, value):
        """A `seed` value: declared field, type respected, never an Upload, image
        present. Extracted from `_valider_assets_et_seeds` (complexity ceiling);
        refusals and messages unchanged."""
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
            self._check_forme_path_asset(value, location, image=True)
            self._check_asset_present(value, location)
