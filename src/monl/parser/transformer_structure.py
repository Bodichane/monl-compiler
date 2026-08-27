"""La charpente : entités, relations, acteurs, workflows, seeds."""

from lark import Transformer, v_args


@v_args(inline=True)
class StructureMixin(Transformer):
    """La charpente : entités, relations, acteurs, workflows, seeds.

    HÉRITE DE ``Transformer`` À DESSEIN, et porte son PROPRE ``@v_args``.
    Lark applique ce décorateur en SAUTANT tout nom déjà présent dans la MRO
    au-dessus de la classe décorée : les méthodes d'un mixin nu ne seraient
    donc jamais enveloppées, et recevraient une LISTE d'enfants au lieu
    d'arguments inlinés. Rien ne planterait — le sens du parsing changerait.
    """

    def app(self, name, *blocks):
        # CORRECTIF (roadmap, découvert en assemblant le réseau social anonyme) :
        # une ligne de commentaire seule entre deux blocs de premier niveau (ex.
        # un commentaire pour expliquer la règle suivante) casse la fusion
        # contiguë du terminal '_NL' -- le lexer produit alors DEUX tokens _NL
        # séparés (avant et après le commentaire) au lieu d'un seul. Le second,
        # rencontré seul comme alternative de '?block', ne matche aucune règle
        # transformée : Lark ne l'inline pas (0 enfant, pas 1) et laisse passer
        # un Tree('block', []) brut -- jamais rencontré avant, car aucun exemple
        # existant n'utilisait de commentaire sur sa propre ligne. isinstance()
        # filtre ce nœud fantôme plutôt que de le laisser faire planter la
        # compréhension de liste ci-dessous avec 'argument of type Tree is not
        # a container or iterable'.
        valid_blocks = [b for b in blocks if isinstance(b, dict)]
        return {
            "app": str(name),
            "entities": [b["entity"] for b in valid_blocks if "entity" in b],
            "relations": [b["relation"] for b in valid_blocks if "relation" in b],
            "actors": [b["actor"] for b in valid_blocks if "actor" in b],
            "self_register_actors": [b["actor"] for b in valid_blocks
                                     if "actor" in b and b.get("self_register")],
            "rules": [b["rule"] for b in valid_blocks if "rule" in b],
            "workflows": [b["workflow"] for b in valid_blocks if "workflow" in b],
            "custom_logic": [b["custom"] for b in valid_blocks if "custom" in b],
            "ui_overrides": [b["ui"] for b in valid_blocks if "ui" in b],
            "landing": next((b["landing"] for b in valid_blocks if "landing" in b), None),
            "capabilities": [b["capability"] for b in valid_blocks if "capability" in b],
            "seeds": [b["seed"] for b in valid_blocks if "seed" in b],
            "assets": next((b["assets"] for b in valid_blocks if "assets" in b), None),
            "migrations": [b["migration"] for b in valid_blocks if "migration" in b],
        }

    def entity(self, name, *attributes):
        return {"entity": {"name": str(name), "attributes": list(attributes)}}

    def attribute(self, name, type_str):
        return {"name": str(name), "type": str(type_str)}

    def relation(self, source, rel_type, target):
        return {"relation": {"source": str(source), "type": str(rel_type), "target": str(target)}}

    def actor(self, name, self_register=None):
        # 'self_register' est le token SELF_REGISTER quand il est présent
        # dans la spec, None sinon (production Lark nommée, cf. CLAUDE.md).
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

    # AJOUT (roadmap frontend, bloc 'seed') : données de démonstration.
    def seed_block(self, name, *reste):
        # BRIQUE 21 : la désignation de parent est OPTIONNELLE et arrive, quand
        # elle existe, avant les lignes. On la reconnaît à sa clé plutôt qu'à sa
        # position : une spec sans `for` doit produire exactement ce qu'elle
        # produisait avant ce point.
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
            # Chaîne : on retire les guillemets et déséchappe les \" et \\.
            parsed = token[1:-1].replace('\\"', '"').replace('\\\\', '\\')
        else:
            # Nombre : entier ou décimal (les Money/Float acceptent un point).
            parsed = float(token) if ("." in token) else int(token)
        return {str(name): parsed}
