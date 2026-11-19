"""The framework: entities, relations, actors, workflows, seeds."""

import math

from lark import Transformer, v_args

from .errors import NombreHorsLimites


def _tous(blocs, cle):
    """Every top-level block of one kind, in declaration order."""
    return [b[cle] for b in blocs if cle in b]


def _premier(blocs, cle):
    """The first top-level block of a kind that appears at most once."""
    return next((b[cle] for b in blocs if cle in b), None)


@v_args(inline=True)
class StructureMixin(Transformer):
    """The framework: entities, relations, actors, workflows, seeds.

    INHERITS FROM ``Transformer`` ON PURPOSE, and carries its OWN
    ``@v_args``. Lark applies this decorator by SKIPPING any name already
    present in the MRO above the decorated class: a bare mixin's methods would
    therefore never be wrapped, and would receive a LIST of children instead
    of inlined arguments. Nothing would crash — the meaning of the parse would
    change."""

    def app(self, name, *blocks):
        # FIX (roadmap, discovered while assembling the anonymous social
        # network): a comment line alone between two top-level blocks (e.g. a
        # comment explaining the next rule) breaks the contiguous merging of
        # the '_NL' terminal -- the lexer then produces TWO separate _NL tokens
        # (before and after the comment) instead of one. The second, met alone
        # as an alternative of '?block', matches no transformed rule: Lark does
        # not inline it (0 children, not 1) and lets a raw Tree('block', [])
        # through -- never met before, because no existing example used a
        # comment on its own line. isinstance() filters this phantom node
        # rather than letting it crash the list comprehension below with
        # 'argument of type Tree is not a container or iterable'.
        valid_blocks = [b for b in blocks if isinstance(b, dict)]
        return {
            "app": str(name),
            "entities": _tous(valid_blocks, "entity"),
            "relations": _tous(valid_blocks, "relation"),
            "actors": _tous(valid_blocks, "actor"),
            "self_register_actors": [b["actor"] for b in valid_blocks
                                     if "actor" in b and b.get("self_register")],
            "rules": _tous(valid_blocks, "rule"),
            "workflows": _tous(valid_blocks, "workflow"),
            "custom_logic": _tous(valid_blocks, "custom"),
            "ui_overrides": _tous(valid_blocks, "ui"),
            "landing": _premier(valid_blocks, "landing"),
            "capabilities": _tous(valid_blocks, "capability"),
            "seeds": _tous(valid_blocks, "seed"),
            "assets": _premier(valid_blocks, "assets"),
            "migrations": _tous(valid_blocks, "migration"),
        }

    def entity(self, name, *attributes):
        return {"entity": {"name": str(name), "attributes": list(attributes)}}

    def attribute(self, name, type_str):
        return {"name": str(name), "type": str(type_str)}

    def relation(self, source, rel_type, target):
        return {"relation": {"source": str(source), "type": str(rel_type), "target": str(target)}}

    def actor(self, name, self_register=None):
        # 'self_register' is the SELF_REGISTER token when present in the spec,
        # None otherwise (named Lark production, see CLAUDE.md).
        return {"actor": str(name), "self_register": self_register is not None}

    def workflow(self, name, actor_name, *actions):
        return {"workflow": {"name": str(name), "actor": str(actor_name), "actions": list(actions)}}

    def crud_action(self, action_type, target):
        return {"type": str(action_type), "target": str(target)}

    def execute_action(self, custom_block_name):
        return {"type": "Execute", "target": str(custom_block_name)}

    def custom_block(self, name, *props):
        prop_dict = {}
        for p in props:
            if p:
                prop_dict.update(p)
        return {"custom": {"name": str(name), **prop_dict}}

    def input_prop(self, *params):
        return {"input": list(params)}

    def output_prop(self, param):
        return {"output": param}

    def description_prop(self, string_literal):
        return {"description": str(string_literal).strip('"')}

    def io_param(self, name_or_ref, type_str=None):
        if type_str:
            return {"name": str(name_or_ref), "type": str(type_str)}
        return {"reference": str(name_or_ref)}

    # ADDED (frontend roadmap, 'seed' block): demo data.
    def seed_block(self, name, *reste):
        # BRICK 21: the parent designation is OPTIONAL and arrives, when it
        # exists, before the rows. It is recognized by its key rather than its
        # position: a spec without `for` must produce exactly what it produced
        # before this point.
        parent, rows = None, []
        for item in reste:
            if isinstance(item, dict) and "__seed_parent__" in item:
                parent = item["__seed_parent__"]
            else:
                rows.append(item)
        return {"seed": {"entity": str(name), "parent": parent, "rows": rows}}

    def seed_parent(self, entity, field, value):
        token = str(value)
        return {"__seed_parent__": {
            "entity": str(entity), "field": str(field),
            "value": token[1:-1].replace('\\"', '"').replace('\\\\', '\\'),
        }}

    def seed_row(self, *pairs):
        record = {}
        for p in pairs:
            record.update(p)
        return record

    def seed_pair(self, name, value):
        token = str(value)
        if token.startswith('"'):
            # String: strip the quotes and unescape \" and \\.
            parsed = token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        else:
            # Number: integer or decimal (Money/Float accept a dot). The
            # grammar also accepts the exponent (`1e3`): it is a decimal, never
            # an `int()`, which crashed (point 204). An outsized exponent gives
            # infinity, which no database can store: refused.
            if any(c in token for c in ".eE"):
                parsed = float(token)
                if not math.isfinite(parsed):
                    raise NombreHorsLimites(token)
            else:
                parsed = int(token)
        return {str(name): parsed}
