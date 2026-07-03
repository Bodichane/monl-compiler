import os
import json
from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

# 1. Définition de la grammaire révisée de MonLang
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | _NL
    
    entity: "entity" NAME _NL _INDENT attribute+ _DEDENT
    attribute: NAME ":" TYPE _NL
    
    relation: "relation" NAME RELATION_TYPE NAME _NL
    
    actor: "actor" NAME _NL
    
    rule: "rule" REFERENCE VALIDATION_TYPE _NL
        | "rule" REFERENCE VALIDATION_TYPE INT _NL
    
    workflow: "workflow" NAME "for" NAME _NL _INDENT action+ _DEDENT
    action: ACTION_TYPE NAME _NL
          | ACTION_TYPE REFERENCE _NL

    TYPE: "String" | "Text" | "Integer" | "Float" | "Boolean" | "Date" | "DateTime" | "Email" | "UUID" | "Money"
    RELATION_TYPE: "hasMany" | "belongsTo" | "hasOne"
    ACTION_TYPE: "Create" | "Read" | "Update" | "Delete"
    VALIDATION_TYPE: "required" | "unique" | "min" | "max"
    
    NAME: /[a-zA-Z_][a-zA-Z0-9_]*/
    REFERENCE: /[a-zA-Z_][a-zA-Z0-9_]*\.[a-zA-Z_][a-zA-Z0-9_]*/
    
    # Terminaux pour la gestion des fins de lignes et de blocs
    _NL: /(\r?\n[\t ]*)+/
    
    # Déclaration explicite pour le module d'indentation
    %declare _INDENT _DEDENT

    %import common.INT
    %import common.WS_INLINE
    %ignore WS_INLINE
"""

# 2. Le Transformer convertit l'arbre syntaxique en dictionnaire exploitable
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
            "workflows": [b["workflow"] for b in valid_blocks if "workflow" in b]
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
            data["value"] = int(value)
        return {"rule": data}
        
    def workflow(self, name, actor_name, *actions):
        return {"workflow": {"name": str(name), "actor": str(actor_name), "actions": list(actions)}}
        
    def action(self, action_type, target):
        return {"type": str(action_type), "target": str(target)}

# 3. Classe de configuration personnalisée de l'indenteur pour MonLang
class MonLangIndenter(PythonIndenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4

def parse_monlang_file(file_path):
    # Injection du composant d'indentation postlex
    parser = Lark(grammar, parser='lalr', postlex=MonLangIndenter())
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    raw_tree = parser.parse(content + "\n")
    json_ast = MonLangTransformer().transform(raw_tree)
    return json_ast

if __name__ == "__main__":
    sample_path = os.path.join(os.path.dirname(__file__), "../exemples/01_todo_list.yaml")
    
    try:
        result = parse_monlang_file(sample_path)
        print("🎉 PARSING REUSSI ! Voici le JSON généré :\n")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Erreur lors du parsing : {e}")
