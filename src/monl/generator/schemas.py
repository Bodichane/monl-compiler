"""Generation of the Pydantic schemas (CRUD inputs and 'custom' blocks).

Extracted from the former monolithic module src/generator.py (1307 lines)
when it was split into a package — see docs/design_decisions.md."""

from string import Template

from ..ast_validator.champs import ChampsMixin


class SchemasMixin:
    def _generate_schema_lines(self):
        """Input schemas: one per entity, one per 'custom' block."""
        api_lines = []
        # 1. Generation of the standard CRUD schemas
        for ent_name, attrs in self.entities.items():
            api_lines.append(Template(r"""class ${ent_name}Schema(BaseModel):""").substitute(ent_name=ent_name))
            # ADDED (roadmap, capability ecosystem -- follow-up to brick 1): a
            # 'generated' field does NOT appear in the Pydantic schema -- the
            # client cannot even try to supply it in the request body (like the
            # 'ownedBy' foreign key column, which is not there either). It is
            # filled further down, at creation, from the current account's
            # anonymous pseudonym.
            generated_here_schema = self.generated_fields_by_entity.get(ent_name, [])
            # ADDED (brick 10, point 77): a 'derivedFrom' field is calculated
            # by the server, hence absent from the schema for the same reason
            # as a 'generated' field. This schema serves creation AND update (a
            # single {Ent}Schema): removing it from there closes at once both
            # paths through which the client wrote the amount that `payable`
            # then reread.
            derives_ici = self._derived_field_names(ent_name)
            # ADDED (brick 12, point 82): a 'sumOf' field is recomputed by the
            # server on every write of a child line. Same treatment, same
            # reason: leaving it in the schema would let the client write a
            # cart's total, i.e. the point 77 flaw coming back through the
            # cart.
            sommes_ici = self._aggregated_field_names(ent_name)
            # ADDED (brick 16, point 89): a 'timestamp' field is written by the
            # server at creation. Leaving it in the schema would make the date
            # declarative — that is, worthless: an order book where everyone
            # picks their own dates attests to nothing.
            horodates_ici = self.timestamp_fields_by_entity.get(ent_name, [])
            # BRICK 22 (point 102): a number the client could write would
            # number nothing — they would pick their own, and two clients would
            # pick the same.
            horodates_ici = [*horodates_ici, *[
                n["field"] for n in self.numbered_fields_by_entity.get(ent_name, [])]]
            # BRICK 25 (point 113): a 'writableAfterPayment' field must be
            # written ONLY by the dedicated route, never by the generic create
            # or update routes the client can reach.
            postpaiement_ici = self.postpayment_writable_by_entity.get(
                ent_name, {}).get("fields", [])
            has_schema_field = False
            non_blank = []
            for attr_name, attr_type in attrs.items():
                if (attr_name in generated_here_schema or attr_name in derives_ici
                        or attr_name in sommes_ici or attr_name in horodates_ici
                        or (ent_name, attr_name) in self.event_counters
                        or attr_name in postpaiement_ici
                        or attr_type == "Upload"):
                    continue
                non_blank.extend(self._non_blank_field(ent_name, attr_name, attr_type))
                py_type = "str"
                if attr_type == "Integer": py_type = "int"
                if attr_type in ["Float", "Money"]: py_type = "float"
                if attr_type == "Boolean": py_type = "bool"
                # FIX (beta 3): text fields had NO length bound — a string of
                # several MB was accepted and written to the database, which is
                # enough to fill the disk with a ten-line loop. The bound
                # mirrors the matching SQL column (VARCHAR(255) for String,
                # VARCHAR(320) for Email, long text for Text): the refusal
                # comes at input validation, with an explicit 422, rather than
                # in the middle of an INSERT.
                #
                # POINT 85: 'min'/'max' had NO effect. They arrive here, in the
                # only place an input bound can live — Pydantic validation,
                # hence a 422 before any INSERT. The validator has already
                # decided what each bound means for each type (length for text,
                # value for a number) and refused what it cannot bound: here we
                # only write it.
                #
                # BRICK 19 (point 96): a value FROM A LIST. `Literal` rather
                # than a pattern: Pydantic refuses with 422 BEFORE any INSERT
                # (same place as the point 85 bounds), and the list comes out
                # as is in the OpenAPI schema — hence in /docs, without having
                # to copy it. The values go through `repr()`: never manual
                # interpolation between quotes, that is the lesson of
                # `categorized` (brick 5).
                choix = self.enumerated_fields.get(ent_name, {}).get(attr_name)
                if choix:
                    valeurs = ", ".join(repr(v) for v in choix)
                    api_lines.append(Template(r"""    ${attr_name}: Literal[${valeurs}]""").substitute(attr_name=attr_name, valeurs=valeurs))
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
                    bornes.append(Template(r"""${mot}=${value}""").substitute(mot=mot, value=borne_regle['valeur']))
                if py_type == "str":
                    borne = {"Text": 20000, "Email": 320, "UUID": 36}.get(attr_type, 255)
                    # A declared 'max' wins over the column bound: the
                    # validator checked it does not exceed it.
                    if not any(b.startswith("max_length=") for b in bornes):
                        bornes.append(Template(r"""max_length=${borne}""").substitute(borne=borne))
                    # POINT 91: the 'Email' type only fixed a LENGTH —
                    # 'not-an-email' went into the database with a 200. A type
                    # that names an address and checks none is exactly what
                    # point 85 refuses: a rule that produces nothing. The
                    # pattern is deliberately broad (one at sign, a dot after
                    # it, no space): monl checks the FORM, it cannot attest
                    # that a mailbox exists — that would need sending
                    # something, hence an outgoing call the compiler forbids
                    # itself.
                    if attr_type == "Email":
                        bornes.append(r"pattern=r'^[^@\s]+@[^@\s]+\.[^@\s]{2,}$'")
                    # POINT 101: the sibling type had the same defect, and it
                    # stood ten points longer. 'UUID' only fixed a length of
                    # 255: `smoke-reference` went into the database under a
                    # name that promises a universally unique identifier. The
                    # point 91 reasoning applies word for word — a type that
                    # NAMES a thing and checks none of it is a rule that
                    # produces nothing (point 85).
                    #
                    # The canonical form, and nothing more: neither version nor
                    # variant. Requiring the version digit would reject the nil
                    # UUID and future versions, though they are well formed --
                    # monl checks the FORM, it does not judge provenance.
                    if attr_type == "UUID":
                        bornes.append(
                            Template(r"""pattern=r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$$'""").substitute())
                    api_lines.append(Template(r"""    ${attr_name}: str = Field(..., ${value})""").substitute(attr_name=attr_name, value=', '.join(bornes)))
                elif bornes:
                    api_lines.append(Template(r"""    ${attr_name}: ${py_type} = Field(..., ${value})""").substitute(attr_name=attr_name, py_type=py_type, value=', '.join(bornes)))
                else:
                    api_lines.append(Template(r"""    ${attr_name}: ${py_type}""").substitute(attr_name=attr_name, py_type=py_type))
                has_schema_field = True
            # ADDED (roadmap, capability ecosystem -- brick 3, generalized into
            # brick 4): every relation to a 'decrements'/'increments' target is
            # a client choice ("I report/like THIS precise target"), whatever
            # its position among the incoming relations. The column's single
            # source is the counter plan through `_counter_fk_columns`.
            for _counter_fk in self._counter_fk_columns(ent_name):
                api_lines.append(Template(r"""    ${counter_fk}: int""").substitute(counter_fk=_counter_fk))
                has_schema_field = True
            # ADDED (beta 3): parents other than the owner — the client must be
            # able to say which linked record it attaches to.
            for _client_fk in self._client_fk_columns(ent_name):
                api_lines.append(Template(r"""    ${client_fk}: int""").substitute(client_fk=_client_fk))
                has_schema_field = True
            # Syntactic safety net: if ALL of an entity's attributes are
            # 'generated' (no other field, no FK column added above), the class
            # body would be empty -- invalid in Python.
            if not has_schema_field:
                api_lines.append("    pass")
            api_lines.extend(_blank_validator_lines(non_blank))
            api_lines.append(Template(r"""
""").substitute())

        # 2. Strict schemas for the inputs of 'custom' functions
        api_lines.append("# --- VALIDATION SCHEMAS DEDICATED TO THE AI SANDBOX ---")
        for func in self.custom_functions:
            func_name = func["name"]
            inputs = func.get("input", [])

            api_lines.append(Template(r"""class ${func_name}InputSchema(BaseModel):""").substitute(func_name=func_name))
            if not inputs:
                api_lines.append("    pass")
            else:
                for inp in inputs:
                    if "reference" in inp:
                        ref = inp["reference"]
                        ent, attr = ref.split(".") if "." in ref else (ref, "id")
                        attr_type = self.entities.get(ent, {}).get(attr, "String")
                        py_type = "int" if attr_type == "Integer" else ("float" if attr_type in ["Float", "Money"] else ("bool" if attr_type == "Boolean" else "str"))
                        api_lines.append(Template(r"""    ${attr}: ${py_type}""").substitute(attr=attr.replace('.', '_'), py_type=py_type))
                    else:
                        inp_name = inp.get("name", "context")
                        inp_type = inp.get("type", "String")
                        py_type = "int" if inp_type == "Integer" else ("float" if inp_type in ["Float", "Money"] else ("bool" if inp_type == "Boolean" else "str"))
                        api_lines.append(Template(r"""    ${inp_name}: ${py_type}""").substitute(inp_name=inp_name, py_type=py_type))
            api_lines.append(Template(r"""
""").substitute())

        return api_lines

    def _required_text_validator(self, entity, fields):
        return _blank_validator_lines([
            field for field in fields
            if self._non_blank_field(entity, field, self.entities[entity][field])])

    def _non_blank_field(self, entity, field, type_):
        if (type_ in ChampsMixin.BORNES_TEXTE
                and self.field_constraints.get(entity, {}).get(field, {}).get("required")):
            return [field]
        return []


def _blank_validator_lines(fields):
    if not fields:
        return []
    return [
        Template(r"""    @field_validator(${value})""").substitute(value=', '.join(map(repr, fields))),
        *Template(r"""    @classmethod
    def _refuse_blank(cls, value):
        if value is not None and not value.strip():
            raise ValueError('required text must not be blank')
        return value""").substitute().split("\n"),
    ]
