import os
import json
from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | _NL
    
    entity: "entity" NAME _NL _INDENT attribute+ _DEDENT
    attribute: NAME ":" TYPE _NL
    
    relation: "relation" NAME RELATION_TYPE NAME _NL
    
    actor: "actor" NAME _NL
    
    rule: "rule" REFERENCE VALIDATION_TYPE _NL
        | "rule" REFERENCE VALIDATION_TYPE INT _NL
        | "rule" REFERENCE "restrictedTo" NAME _NL
    
    workflow: "workflow" NAME "for" NAME _NL _INDENT action+ _DEDENT
    
    ?action: crud_action | execute_action
    crud_action: ACTION_TYPE NAME _NL
               | ACTION_TYPE REFERENCE _NL
    execute_action: "Execute" NAME _NL

    custom_block: "custom" NAME _NL _INDENT custom_prop+ _DEDENT
    custom_prop: "input" ":" io_param ("," io_param)* _NL
               | "output" ":" io_param _NL
               | "description" ":" STRING_LITERAL _NL

    io_param: NAME ":" TYPE
            | REFERENCE

    TYPE: "String" | "Text" | "Integer" | "Float" | "Boolean" | "Date" | "DateTime" | "Email" | "UUID" | "Money"
    RELATION_TYPE: "hasMany" | "belongsTo" | "hasOne"
    ACTION_TYPE: "Create" | "Read" | "Update" | "Delete"
    VALIDATION_TYPE: "required" | "unique" | "min" | "max"
    
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    REFERENCE: /[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*/
    STRING_LITERAL: /"[^"\\]*(?:\\.[^"\\]*)*"/
    
    _NL: /(\r?\n[\t ]*)+/
    %declare _INDENT _DEDENT

    %import common.INT
    %import common.WS_INLINE
    %ignore WS_INLINE
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
        
    def rule(self, reference, valid_type, value=None):
        data = {"reference": str(reference), "type": str(valid_type)}
        if value is not None:
            data["value"] = str(value)
        return {"rule": data}
        
    def workflow(self, name, actor_name, *actions):
        return {"workflow": {"name": str(name), "actor": str(actor_name), "actions": list(actions)}}
        
    def crud_action(self, action_type, target):
        return {"type": str(action_type), "target": str(target)}

    def execute_action(self, custom_block_name):
        return {"type": "Execute", "target": str(custom_block_name)}

    def custom_block(self, name, *props):
        prop_dict = {}
        for p in props:
            prop_dict.update(p)
        return {"custom": {"name": str(name), **prop_dict}}

    def custom_prop(self, key, *values):
        if str(key) == "description":
            # On extrait le texte pur du premier token Lark trouvé
            raw_text = "".join([str(v) for v in values]) if values else ""
            clean_desc = raw_text.strip('"')
            return {"description": clean_desc}
        return {str(key): list(values)}



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

def parse_monlang_file(file_path):
    parser = Lark(grammar, parser='lalr', postlex=MonLangIndenter())
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    return MonLangTransformer().transform(parser.parse(content + "\n"))

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    try:
        result = parse_monlang_file(sample_path)
        print("🎉 PARSING RÉUSSI !\n", json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Erreur lors du parsing : {e}")
