import os
import json
from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

# Grammaire MonLang v6 - Support des descriptions multi-lignes (Bug #1)
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | ui_block | landing_block | capability_block | _NL
    
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
    ?rule: constraint_rule | restriction_rule | sharing_rule | ownership_rule | visibility_rule | masking_rule | decrement_rule | increment_rule | categorization_rule

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
    # AJOUT (roadmap, cas d'usage portfolio) : "public" retire l'obligation
    # d'authentification pour une action précise (ex. lire des articles sans
    # compte, envoyer un message de contact sans compte). Ex. :
    #   rule Project.Read public
    #   rule Message.Create public
    visibility_rule: "rule" REFERENCE "public" _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 2) : "hidden" retire
    # un CHAMP (pas une action) de toutes les réponses de lecture de son
    # entité -- liste et détail -- sans le retirer de la base ni empêcher
    # son utilisation en écriture. Cas d'usage : un réseau social où les
    # posts sont publics mais leur auteur ne doit jamais apparaître dans la
    # réponse API. Contrairement à "restrictedTo" (qui exige un acteur
    # précis), "hidden" masque pour TOUT LE MONDE, y compris les acteurs
    # authentifiés -- c'est la différence de fond entre "confidentiel" et
    # "anonyme". Ex. :
    #   rule Post.author hidden
    masking_rule: "rule" REFERENCE "hidden" _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 3) : "decrements"
    # déclenche, à la création d'un enregistrement d'une entité (typiquement
    # un signalement), la décrémentation d'un champ numérique sur l'entité
    # liée dont il dépend (via une relation existante, ex.
    # "Member hasMany Report"). Ex. :
    #   rule Report.Create decrements Member.reputation
    #   rule Report.Create decrements Member.reputation by 10
    # Le montant par défaut (sans "by N") est 1.
    #
    # AJOUT (roadmap, écosystème de capacités -- brique 4) : "increments",
    # symétrique de "decrements" pour les likes/appréciations. Ex. :
    #   rule Like.Create increments Post.likes
    # DÉLIBÉRÉMENT deux productions Lark nommées séparées plutôt qu'une seule
    # règle paramétrée par un mot-clé partagé : "decrements"/"increments" sont
    # des littéraux de chaîne anonymes, filtrés par Lark avant d'atteindre le
    # Transformer (même piège déjà rencontré et corrigé pour
    # "restrictedTo"/"sharedBy", voir plus haut) -- un essai précédent de
    # règle unique avait donc silencieusement étiqueté tout "increments" comme
    # "decrements" et a été retiré plutôt que laissé à moitié fait.
    decrement_rule: "rule" REFERENCE "decrements" REFERENCE _NL
                   | "rule" REFERENCE "decrements" REFERENCE "by" INT _NL
    increment_rule: "rule" REFERENCE "increments" REFERENCE _NL
                   | "rule" REFERENCE "increments" REFERENCE "by" INT _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 5) : "categorized"
    # remplace un champ numérique (Integer/Float) par un libellé de
    # catégorie dans toutes les réponses de lecture -- sur le même principe
    # que "hidden" (retire un champ), mais en le substituant par une donnée
    # dérivée plutôt qu'en le supprimant purement. Cas d'usage déclencheur :
    # des likes affichés en catégories ("peu"/"populaire"/"viral") plutôt
    # qu'en nombre exact. Chaque palier est soit "below" (seuil strict,
    # exclusif), soit "otherwise" (palier de secours, un seul autorisé,
    # obligatoirement en dernière position -- voir ast_validator.py pour la
    # validation complète). Ex. :
    #   rule Post.likes categorized: "peu" below 10, "populaire" below 100, "viral" otherwise
    categorization_rule: "rule" REFERENCE "categorized" ":" category_clause ("," category_clause)* _NL
    ?category_clause: category_below | category_otherwise
    category_below: STRING_LITERAL "below" INT
    category_otherwise: STRING_LITERAL "otherwise"

    # AJOUT (roadmap, contrôle du rendu visuel) : bloc optionnel "ui" pour
    # surcharger ce que le générateur devine automatiquement. Ex. :
    #   ui Project
    #       theme: market
    #       primary: title
    #       order: title, price, stock
    # SUPPRESSION (roadmap, sur demande explicite) : MonLang ne génère plus
    # de back-office CRUD par entité (voir generate_all) — seul "theme" a
    # encore un effet (il influence l'identité visuelle de "landing.html",
    # voir le bloc "landing" plus bas). "primary" et "order" sont conservés
    # dans la grammaire pour ne pas casser les specs existantes qui les
    # utilisent, mais n'ont plus aucun effet sur le rendu.
    ui_block: "ui" NAME _NL _INDENT ui_prop+ _DEDENT
    ?ui_prop: ui_theme | ui_primary | ui_order
    ui_theme: "theme" ":" NAME _NL
    ui_primary: "primary" ":" NAME _NL
    ui_order: "order" ":" NAME ("," NAME)* _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 1) : bloc "capability",
    # volontairement le plus simple possible pour l'instant -- une simple
    # déclaration, sans sous-propriétés. Objectif de cette première brique :
    # prouver que le concept de "capacité" tient dans tout le pipeline
    # (grammaire -> validateur -> AST normalisé -> générateur) SANS changer
    # aucun comportement existant. L'authentification (register/login/JWT)
    # est déjà générée systématiquement pour toute app -- ce bloc la rend
    # seulement explicite/déclarée plutôt qu'implicite dans le code. Les
    # capacités futures (masquage de champ, accès à deux parties...) sont
    # celles qui changeront réellement le comportement ; celle-ci sert de
    # gabarit sûr, testé sur le portfolio, avant d'aller plus loin.
    capability_block: "capability" NAME _NL

    # AJOUT (roadmap, front marketing) : bloc optionnel "landing", au même
    # titre que "custom" (échappatoire IA balisée) — active une page
    # d'accueil marketing sur "/". C'est volontairement le SEUL front que
    # MonLang puisse générer (aucun back-office CRUD auto-généré) : deux
    # modes exclusifs, chacun avec son propre filet de sécurité déterministe :
    #   landing                              landing
    #       mode: ai                             mode: template
    #       brief: "..." (optionnel)             template: "chemin/vers/fichier.html"
    # "mode: ai" appelle l'IA locale (même pont Ollama que "custom") pour
    # rédiger uniquement du TEXTE (titre, sous-titre, CTA, points forts) —
    # jamais du HTML/CSS — injecté dans un gabarit déterministe. "mode:
    # template" importe un fichier HTML fourni par l'utilisateur et y
    # substitue des emplacements balisés "data-monlang=...". Dans les deux
    # cas, si l'étape IA ou le fichier importé est absent/indisponible, un
    # gabarit 100% déterministe est utilisé — jamais d'échec de compilation
    # à cause de "landing". Sans bloc "landing" du tout, "/" redirige
    # simplement vers "/docs" (documentation Swagger/OpenAPI de FastAPI).
    landing_block: "landing" _NL _INDENT landing_prop+ _DEDENT
    ?landing_prop: landing_mode | landing_template | landing_brief
    landing_mode: "mode" ":" NAME _NL
    landing_template: "template" ":" STRING_LITERAL _NL
    landing_brief: "brief" ":" STRING_LITERAL _NL

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
            "rules": [b["rule"] for b in valid_blocks if "rule" in b],
            "workflows": [b["workflow"] for b in valid_blocks if "workflow" in b],
            "custom_logic": [b["custom"] for b in valid_blocks if "custom" in b],
            "ui_overrides": [b["ui"] for b in valid_blocks if "ui" in b],
            "landing": next((b["landing"] for b in valid_blocks if "landing" in b), None),
            "capabilities": [b["capability"] for b in valid_blocks if "capability" in b],
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

    def visibility_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "public"}}

    def masking_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "hidden"}}

    def decrement_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "decrements",
            "value": str(target_ref), "amount": int(amount) if amount is not None else 1,
        }}

    def increment_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "increments",
            "value": str(target_ref), "amount": int(amount) if amount is not None else 1,
        }}

    def category_below(self, label, threshold):
        return {"label": str(label).strip('"'), "below": int(threshold)}

    def category_otherwise(self, label):
        return {"label": str(label).strip('"'), "otherwise": True}

    def categorization_rule(self, reference, *clauses):
        return {"rule": {
            "reference": str(reference), "type": "categorized",
            "value": list(clauses),
        }}

    def ui_theme(self, name):
        return {"theme": str(name)}

    def ui_primary(self, name):
        return {"primary": str(name)}

    def ui_order(self, *names):
        return {"order": [str(n) for n in names]}

    def ui_block(self, entity_name, *props):
        merged = {}
        for p in props:
            if p:
                merged.update(p)
        return {"ui": {"entity": str(entity_name), **merged}}

    def landing_mode(self, name):
        return {"mode": str(name)}

    def landing_template(self, string_literal):
        return {"template": str(string_literal).strip('"')}

    def landing_brief(self, string_literal):
        return {"brief": str(string_literal).strip('"')}

    def landing_block(self, *props):
        merged = {}
        for p in props:
            if p:
                merged.update(p)
        return {"landing": merged}

    def capability_block(self, name):
        return {"capability": str(name)}

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
