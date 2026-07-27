import os
import re

from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

# Grammaire monl v6 - Support des descriptions multi-lignes (Bug #1)
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | ui_block | landing_block | capability_block | seed_block | _NL
    
    entity: "entity" NAME _NL _INDENT attribute+ _DEDENT
    attribute: NAME ":" TYPE _NL
    
    relation: "relation" NAME RELATION_TYPE NAME _NL
    
    # CORRECTIF (bêta 3, faille d'élévation de privilège) : un acteur n'est
    # PAS inscriptible librement par défaut. Sans le marqueur 'selfRegister',
    # les comptes portant ce rôle sont provisionnés hors ligne (manage.py) —
    # sans quoi n'importe qui pouvait s'inscrire en choisissant le rôle le
    # plus privilégié de l'application. Ex. :
    #   actor Customer selfRegister
    #   actor ShopManager
    actor: "actor" NAME SELF_REGISTER? _NL
    SELF_REGISTER: "selfRegister"
    
    # CORRECTIF (post-v6) : la règle "rule" est éclatée en 3 productions nommées.
    # Raison : dans la grammaire précédente, les mots-clés "restrictedTo"/"sharedBy"
    # étaient des littéraux anonymes filtrés par Lark avant transformation, ce qui
    # empêchait la méthode rule() de savoir quel type de règle elle traitait
    # (le mot-clé "restrictedTo" n'atteignait jamais le Transformer). Conséquence :
    # rule["type"] ne valait jamais "restrictedTo", et l'audit de sécurité associé
    # dans ast_validator.py ne se déclenchait donc jamais. Même classe de bug que
    # celui déjà corrigé sur le bloc "custom" en v3.
    ?rule: constraint_rule | restriction_rule | sharing_rule | ownership_rule | access_rule | visibility_rule | masking_rule | decrement_rule | increment_rule | categorization_rule | generation_rule

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

    # AJOUT (roadmap, écosystème de capacités -- brique "accès à deux
    # parties") : 'ownedBy' ne couvre qu'un seul propriétaire ; une
    # messagerie privée a besoin qu'expéditeur ET destinataire accèdent au
    # même enregistrement. 'accessibleBy' liste les COLONNES (au moins
    # deux, imposé par la grammaire -- avec une seule, 'ownedBy' suffit)
    # de l'entité qui contiennent chacune un identifiant d'utilisateur
    # autorisé. Production Lark nommée distincte, comme pour
    # decrement_rule/increment_rule (même piège de filtrage Lark, voir
    # CLAUDE.md).
    access_rule: "rule" REFERENCE "accessibleBy" NAME ("," NAME)+ _NL
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

    # AJOUT (roadmap, écosystème de capacités -- suite de la brique 1,
    # "capability auth") : "generated" retire un champ String du corps de
    # requête attendu par la route Create de son entité -- le serveur le
    # peuple seul, à partir d'un pseudonyme anonyme stable généré une seule
    # fois par compte à l'inscription (voir /register dans generator.py),
    # jamais fourni ni contrôlable par le client. Cas d'usage déclencheur :
    # un champ "author" dont l'intégrité doit être garantie (contrairement
    # à un "author" en String libre rempli à la main par le client, voir
    # docs/design_decisions.md point 29). Ex. :
    #   rule Post.author generated
    generation_rule: "rule" REFERENCE "generated" _NL

    # AJOUT (roadmap, contrôle du rendu visuel) : bloc optionnel "ui" pour
    # surcharger ce que le générateur devine automatiquement. Ex. :
    #   ui Project
    #       theme: market
    #       primary: title
    #       order: title, price, stock
    # SUPPRESSION (roadmap, sur demande explicite) : monl ne génère plus
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

    # Bloc optionnel "landing" : transmet un brief marketing (titre, ton,
    # intention) au contrat frontend, pour orienter l'IA d'interface. C'est
    # une simple donnée textuelle — monl ne génère aucune page lui-même.
    # Seule la clé "brief" a un effet. Les clés "mode" et "template" sont
    # acceptées pour compatibilité avec d'anciennes specs mais sont sans
    # effet (l'audit émet un avertissement). Sans bloc "landing", "/"
    # redirige vers "/docs" (documentation Swagger/OpenAPI de FastAPI).
    # AJOUT (point 55) : "section" répétable — le seul endroit du contrat où
    # du contenu ÉDITORIAL peut vivre. Tout le reste décrit des DONNÉES ;
    # une page « à propos » n'a aucune entité, aucun champ, aucune route
    # d'où naître, et l'IA d'interface n'avait donc rien pour la construire.
    #   landing
    #       brief: "…"
    #       section "À propos": "Photographe basée à Lyon depuis 2015…"
    landing_block: "landing" _NL _INDENT landing_prop+ _DEDENT
    ?landing_prop: landing_mode | landing_template | landing_brief | landing_section
    landing_mode: "mode" ":" NAME _NL
    landing_template: "template" ":" STRING_LITERAL _NL
    landing_brief: "brief" ":" STRING_LITERAL _NL
    landing_section: "section" STRING_LITERAL ":" STRING_LITERAL _NL

    workflow: "workflow" NAME "for" NAME _NL _INDENT action+ _DEDENT
    
    ?action: crud_action | execute_action
    crud_action: ACTION_TYPE NAME _NL
               | ACTION_TYPE REFERENCE _NL
    execute_action: "Execute" NAME _NL

    custom_block: "custom" NAME _NL _INDENT (input_prop | output_prop | description_prop)+ _DEDENT
    input_prop: "input" ":" io_param ("," io_param)* _NL
    output_prop: "output" ":" io_param _NL
    description_prop: "description" ":" STRING_LITERAL _NL

    # AJOUT (roadmap frontend, "je veux des sites complets") : bloc 'seed' —
    # données de démonstration pré-remplies, insérées au démarrage si la
    # table est vide (idempotent). Une app data-driven paraît vide sans
    # données ; ce bloc fait qu'un portfolio, une boutique ou un fil social
    # s'affichent avec des éléments réels dès la première ouverture. Une ligne =
    # un enregistrement (paires 'champ: valeur'). Les valeurs peuvent être
    # des chaînes (avec URLs d'images publiques), des entiers ou des
    # décimaux. Ex. :
    #   seed Project
    #       title: "Refonte Aurora", imageUrl: "https://picsum.photos/seed/a/600/400", year: 2024
    seed_block: "seed" NAME _NL _INDENT seed_row+ _DEDENT
    seed_row: seed_pair ("," seed_pair)* _NL
    seed_pair: NAME ":" seed_value
    ?seed_value: STRING_LITERAL | SIGNED_NUMBER

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
    %import common.SIGNED_NUMBER
    %import common.WS_INLINE
    %ignore WS_INLINE
    %ignore COMMENT
"""

@v_args(inline=True)
class MonlTransformer(Transformer):
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

    def access_rule(self, reference, *party_columns):
        return {"rule": {"reference": str(reference), "type": "accessibleBy",
                         "value": [str(c) for c in party_columns]}}

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

    def generation_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "generated"}}

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

    def landing_section(self, titre, corps):
        # Marqueur temporaire : les sections s'ACCUMULENT, alors que les
        # autres clés du bloc s'écrasent. Un simple merge les perdrait
        # toutes sauf la dernière.
        return {"_section": {"title": str(titre).strip('"'),
                             "body": str(corps).strip('"')}}

    def landing_block(self, *props):
        merged, sections = {}, []
        for p in props:
            if not p:
                continue
            if "_section" in p:
                sections.append(p["_section"])
            else:
                merged.update(p)
        if sections:
            merged["sections"] = sections
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

    # AJOUT (roadmap frontend, bloc 'seed') : données de démonstration.
    def seed_block(self, name, *rows):
        return {"seed": {"entity": str(name), "rows": list(rows)}}

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

class MonlIndenter(PythonIndenter):
    NL_type = '_NL'
    OPEN_PAREN_types = []
    CLOSE_PAREN_types = []
    INDENT_type = '_INDENT'
    DEDENT_type = '_DEDENT'
    tab_len = 4

# CORRECTIF (roadmap, découvert en assemblant le réseau social anonyme,
# point 29 de docs/design_decisions.md) : une ligne de commentaire SEULE
# (rien d'autre que des espaces avant le '#') casse la fusion contiguë du
# terminal _NL -- son regex (`(\r?\n[\t ]*)+`) ne peut matcher que des
# retours à la ligne consécutifs, et le texte du commentaire interrompt
# cette contiguïté, produisant DEUX tokens _NL séparés au lieu d'un seul.
# Au niveau racine, ça laissait passer un Tree('block', []) non transformé
# (voir le correctif défensif dans app() ci-dessus) ; À L'INTÉRIEUR d'un
# bloc indenté (entity/workflow/...), ça faisait carrément échouer le
# parsing (`UnexpectedToken`), car aucune des règles `attribute+`/`action+`
# etc. n'a d'alternative pour absorber un _NL isolé.
# CORRIGÉ EN AMONT DU LEXER plutôt que règle de grammaire par règle (5
# endroits différents à corriger et tester séparément, avec le risque de
# perturber l'indenteur sur chacun) : toute ligne qui n'est QUE du
# commentaire est retirée du texte source avant même que Lark ne le voie --
# la ligne disparaît complètement, comme si elle n'avait jamais existé,
# donc la contiguïté du run de retours à la ligne qui l'entourait est
# restaurée. Les commentaires en fin de ligne réelle (ex.
# "rule Post.author hidden  # note") ne sont PAS concernés par cette regex
# (il y a du contenu non-blanc avant le '#') -- ils restent gérés par
# `%ignore COMMENT` dans la grammaire, comme avant.
_STANDALONE_COMMENT_LINE = re.compile(r"^[ \t]*#[^\n]*$")

def _strip_standalone_comment_lines(content):
    """Retire les lignes qui ne sont QUE du commentaire (voir bloc de
    commentaires ci-dessus) et retourne (texte_nettoye, table_de_lignes) où
    table_de_lignes[i] = numéro (1-based) de la ligne ORIGINALE correspondant
    à la ligne i+1 du texte nettoyé. AJOUT (roadmap, erreurs lisibles) : la
    table permet de reporter les erreurs de syntaxe sur la vraie ligne du
    fichier de l'utilisateur, pas sur la ligne du texte nettoyé."""
    kept_lines = []
    line_map = []
    for idx, line in enumerate(content.split("\n")):
        if _STANDALONE_COMMENT_LINE.match(line):
            continue
        kept_lines.append(line)
        line_map.append(idx + 1)
    return "\n".join(kept_lines), line_map


class MonlSyntaxError(Exception):
    """AJOUT (roadmap, erreurs lisibles) : erreur de syntaxe monl avec
    ligne/colonne du FICHIER SOURCE (pas du texte nettoyé des commentaires),
    extrait de la ligne fautive, curseur, et suggestions quand Lark les
    connaît. Avant : l'utilisateur recevait l'exception Lark brute
    (UnexpectedToken avec numéro de ligne décalé si la spec contenait des
    lignes de commentaire)."""

    def __init__(self, message, line=None, column=None, source_line=None, file_path=None):
        self.line = line
        self.column = column
        self.file_path = file_path
        parts = []
        location = ""
        if file_path:
            location = os.path.basename(file_path)
        if line is not None:
            location += f"{':' if location else 'ligne '}{line}"
            if column is not None:
                location += f":{column}"
        if location:
            parts.append(f"Erreur de syntaxe monl ({location}) : {message}")
        else:
            parts.append(f"Erreur de syntaxe monl : {message}")
        if source_line is not None:
            parts.append(f"    {source_line}")
            if column is not None:
                parts.append("    " + " " * max(column - 1, 0) + "^")
        super().__init__("\n".join(parts))


# Traduction des noms de tokens de la grammaire vers le vocabulaire du DSL,
# pour que "attendu : ..." parle à l'utilisateur plutôt qu'au mainteneur.
_TOKEN_LABELS = {
    "NAME": "un nom (entité, acteur, champ...)",
    "TYPE": "un type (String, Integer, Boolean, Email, Float...)",
    "REFERENCE": "une référence Entite.champ ou Entite.Action",
    "RELATION_TYPE": "hasMany / hasOne / belongsTo",
    "_NL": "un retour à la ligne",
    "_INDENT": "un bloc indenté",
    "_DEDENT": "la fin du bloc indenté",
    "ESCAPED_STRING": "une chaîne entre guillemets",
    "NUMBER": "un nombre",
    "$END": "la fin du fichier",
    "COLON": "':'",
    "COMMA": "','",
}


def _format_lark_error(err, original_content, line_map, file_path=None):
    from lark.exceptions import UnexpectedCharacters, UnexpectedToken
    original_lines = original_content.split("\n")
    line = getattr(err, "line", None)
    column = getattr(err, "column", None)
    real_line = None
    source_line = None
    if isinstance(line, int) and line >= 1:
        # Reporte la ligne du texte nettoyé sur la ligne du fichier original.
        real_line = line_map[line - 1] if line - 1 < len(line_map) else line
        if real_line - 1 < len(original_lines):
            source_line = original_lines[real_line - 1]
    if isinstance(err, UnexpectedToken):
        token_repr = "fin de fichier" if err.token.type == "$END" else f"'{err.token}'"
        expected = sorted(
            {_TOKEN_LABELS.get(t, t) for t in (err.accepts or err.expected or [])}
        )
        message = f"élément inattendu : {token_repr}."
        if expected:
            message += " Attendu ici : " + " ; ".join(expected) + "."
    elif isinstance(err, UnexpectedCharacters):
        message = f"caractère inattendu : '{err.char}'."
    else:
        message = str(err).split("\n")[0]
    return MonlSyntaxError(message, line=real_line, column=column,
                              source_line=source_line, file_path=file_path)


def parse_monl_string(content, file_path=None):
    """Parse une chaîne monl directement (sans passer par un fichier).
    Utilisé par parse_monl_file pour valider
    une spec générée par l'IA avant de l'écrire sur disque.
    Lève MonlSyntaxError (message localisé : fichier, ligne, colonne,
    extrait) plutôt que l'exception Lark brute."""
    from lark.exceptions import UnexpectedInput
    parser = Lark(grammar, parser='lalr', postlex=MonlIndenter())
    original = content + "\n"
    stripped, line_map = _strip_standalone_comment_lines(original)
    if not stripped.endswith("\n"):
        stripped += "\n"
        line_map.append(line_map[-1] + 1 if line_map else 1)
    try:
        tree = parser.parse(stripped)
    except UnexpectedInput as err:
        raise _format_lark_error(err, original, line_map, file_path=file_path) from None
    return MonlTransformer().transform(tree)

def parse_monl_file(file_path):
    with open(file_path, encoding='utf-8') as f:
        content = f.read()
    return parse_monl_string(content, file_path=file_path)
