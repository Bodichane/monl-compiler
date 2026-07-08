import os
import json
from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

# Grammaire MonLang v6 - Support des descriptions multi-lignes (Bug #1)
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | _NL
    
    entity: "entity" NAME _NL _INDENT attribute+ _DEDENT
    attribute: NAME ":" TYPE _NL
    
    relation: "relation" NAME RELATION_TYPE NAME _NL
    
    actor: "actor" NAME _NL
    
    # CORRECTIF (post-v6) : la règle "rule" est éclatée en 3 productions nommées.
    # Raison : dans la grammaire précédente, les mots-clés "restrictedTo"/"sharedBy"
    # étaient des littéraux anonymes filtrés par Lark avant transformation, ce qui
    # empêchait la méthode rule() de savoir quel type de règle elle traitait
    # (le mot-clé "restrictedTo" n'atteignait jamais le Transformer). Conséquence :
    # rule["type"] ne valait jamais "restrictedTo", et l'audit de sécurité associé
    # dans ast_validator.py ne se déclenchait donc jamais. Même classe de bug que
    # celui déjà corrigé sur le bloc "custom" en v3.
    ?rule: constraint_rule | restriction_rule | sharing_rule | ownership_rule

    constraint_rule: "rule" REFERENCE VALIDATION_TYPE _NL
                   | "rule" REFERENCE VALIDATION_TYPE INT _NL
    restriction_rule: "rule" REFERENCE "restrictedTo" NAME _NL
    sharing_rule: "rule" REFERENCE "sharedBy" NAME ("," NAME)* _NL
    # AJOUT (post-v6, roadmap) : "ownedBy" restreint une action Update/Delete au
    # seul enregistrement appartenant à l'acteur courant, via la relation FK
    # existante entre l'entité et l'acteur propriétaire. Ex. :
    #   relation User hasMany Todo
    #   rule Todo.Update ownedBy User
    ownership_rule: "rule" REFERENCE "ownedBy" NAME _NL

    workflow: "workflow" NAME "for" NAME _NL _INDENT action+ _DEDENT
    
    ?action: crud_action | execute_action
    crud_action: ACTION_TYPE NAME _NL
               | ACTION_TYPE REFERENCE _NL
    execute_action: "Execute" NAME _NL

    custom_block: "custom" NAME _NL _INDENT (input_prop | output_prop | description_prop)+ _DEDENT
    input_prop: "input" ":" io_param ("," io_param)* _NL
    output_prop: "output" ":" io_param _NL
    description_prop: "description" ":" STRING_LITERAL _NL

    io_param: NAME ":" TYPE
            | REFERENCE

    TYPE: "String" | "Text" | "Integer" | "Float" | "Boolean" | "Date" | "DateTime" | "Email" | "UUID" | "Money"
    RELATION_TYPE: "hasMany" | "belongsTo" | "hasOne"
    ACTION_TYPE: "Create" | "Read" | "Update" | "Delete"
    VALIDATION_TYPE: "required" | "unique" | "min" | "max"
    
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    REFERENCE: /[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*/
    
    # CORRECTIF BUG v6 #1 : Ajout du flag /s pour autoriser les retours à la ligne dans les guillemets
    STRING_LITERAL: /"(?:[^"\\]|\\.)*"/s
    
    _NL: /(\r?\n[\t ]*)+/
    COMMENT: /#[^\n]*/
    
    %declare _INDENT _DEDENT

    %import common.INT
    %import common.WS_INLINE
    %ignore WS_INLINE
    %ignore COMMENT
"""

@v_args(inline=True)
class MonLangTransformer(Transformer):
    def app(self, name, *blocks):
        valid_blocks = [b for b in blocks if b is not None]
        return {
            "app": str(name),
            "entities": [b["entity"] for b in valid_blocks if "entity" in b],
            "relations": [b["relation"] for b in valid_blocks if "relation" in b],
            "actors": [b["actor"] for b in valid_blocks if "actor" in b],
            "rules": [b["rule"] for b in valid_blocks if "rule" in b],
            "workflows": [b["workflow"] for b in valid_blocks if "workflow" in b],
            "custom_logic": [b["custom"] for b in valid_blocks if "custom" in b]
        }
        
    def entity(self, name, *attributes):
        return {"entity": {"name": str(name), "attributes": list(attributes)}}
        
    def attribute(self, name, type_str):
        return {"name": str(name), "type": str(type_str)}
        
    def relation(self, source, rel_type, target):
        return {"relation": {"source": str(source), "type": str(rel_type), "target": str(target)}}
        
    def actor(self, name):
        return {"actor": str(name)}
        
    def constraint_rule(self, reference, valid_type, value=None):
        data = {"reference": str(reference), "type": str(valid_type)}
        if value is not None:
            data["value"] = str(value)
        return {"rule": data}

    def restriction_rule(self, reference, actor_name):
        return {"rule": {"reference": str(reference), "type": "restrictedTo", "value": str(actor_name)}}

    def sharing_rule(self, reference, *actor_names):
        return {"rule": {"reference": str(reference), "type": "sharedBy", "value": [str(a) for a in actor_names]}}

    def ownership_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "ownedBy", "value": str(owner_entity)}}
        
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

class MonLangIndenter(PythonIndenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4

def parse_monlang_string(content):
    """Parse une chaîne MonLang directement (sans passer par un fichier).
    Utilisé par parse_monlang_file, et par ai_translator.py pour valider
    une spec générée par l'IA avant de l'écrire sur disque."""
    parser = Lark(grammar, parser='lalr', postlex=MonLangIndenter())
    return MonLangTransformer().transform(parser.parse(content + "\n"))

def parse_monlang_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return parse_monlang_string(content)
