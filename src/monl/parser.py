import ast as py_ast
import os
import re

from lark import Lark, Transformer, v_args
from lark.indenter import PythonIndenter

from .errors import ParseError

# Grammaire monl v6 - Support des descriptions multi-lignes (Bug #1)
grammar = r"""
    ?start: app
    
    app: "app" NAME _NL block*
    
    ?block: entity | relation | actor | rule | workflow | custom_block | ui_block | landing_block | capability_block | seed_block | assets_block | migration_block | _NL
    
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
    ?rule: constraint_rule | restriction_rule | postpayment_rule | sharing_rule | ownership_rule | access_rule | visibility_rule | conditional_visibility_rule | uniqueness_rule | masking_rule | decrement_rule | increment_rule | categorization_rule | generation_rule | payable_rule | derivation_rule | aggregation_rule | timestamp_rule | numbering_rule | requirement_rule | oneof_rule | release_rule | upload_rule | send_rule | filter_rule | sort_rule

    constraint_rule: "rule" REFERENCE VALIDATION_TYPE _NL
                   | "rule" REFERENCE VALIDATION_TYPE INT _NL
    # AJOUT (brique 19, point 96) : une valeur PARMI UNE LISTE. Nommée comme
    # « la prochaine brique évidente » aux points 91 et 92, et pour cause : sur
    # une commande NON réglée, le client posait `status: "livrée"` et le serveur
    # l'acceptait. Un statut n'est pas du texte, c'est un état parmi quelques-uns
    # — et une pointure n'est pas une chaîne libre.
    #   rule Order.status oneOf "panier", "en préparation", "expédiée"
    oneof_rule: "rule" REFERENCE "oneOf" STRING_LITERAL ("," STRING_LITERAL)* _NL
    # AJOUT (brique 20, point 98) : atteindre une VALEUR défait un effet.
    # Le seul bug vivant que la comparaison à une boutique classique avait
    # laissé (point 96) : annuler une commande la passait en « annulée » et
    # gardait ses lignes — donc le stock restait consommé. Supprimer les lignes
    # le rendait (point 92), mais effaçait l'historique ; un marchand veut les
    # deux. `oneOf` était le préalable : il fallait pouvoir désigner un état.
    #   rule Order.status "annulée" releases OrderLine
    release_rule: "rule" REFERENCE STRING_LITERAL "releases" NAME _NL
    # BRIQUE B1 : un Upload est un fichier envoyé à l'exécution par le client.
    # Il ne partage volontairement pas la sémantique d'Image : Image est un
    # chemin d'asset fourni à la compilation, tandis qu'Upload est une colonne
    # de référence opaque accompagnée d'une route multipart générée.
    # La limite et les types sont obligatoires : une déclaration qui ne produit
    # pas un refus observable (taille/type) serait une syntaxe de confort vide.
    # Le type réel est déterminé côté backend par signature d'octets, jamais par
    # l'extension ou le nom fournis par le client.
    upload_rule: "rule" REFERENCE "upload" "max" INT "types" STRING_LITERAL ("," STRING_LITERAL)* _NL
    # BRIQUE B2 : un message part après une création métier réussie. Le
    # séparateur '¶' structure le corps en paragraphes ; inventer une grammaire
    # multiligne ici ferait traverser à nouveau la frontière d'indentation.
    #   rule Order.Create sends "Commande reçue" "Votre commande¶est prise en compte"
    send_rule: "rule" REFERENCE "sends" STRING_LITERAL STRING_LITERAL _NL
    # BRIQUE B3 : capacités de lecture explicites, sans langage de requête.
    # Chaque champ est déclaré séparément ; le client ne choisit jamais un
    # opérateur ni une expression. Ex. :
    #   rule Order.Read filter status
    #   rule Order.Read sort placedAt
    # La direction est une des deux valeurs fixes de la route (asc/desc), pas
    # un fragment SQL envoyé par le client.
    filter_rule: "rule" REFERENCE "filter" NAME _NL
    sort_rule: "rule" REFERENCE "sort" NAME _NL
    restriction_rule: "rule" REFERENCE "restrictedTo" NAME _NL
    postpayment_rule: "rule" REFERENCE "writableAfterPayment" NAME _NL
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
    # Publication conditionnelle : une ressource peut être publique seulement
    # dans un état métier précis. Exemple :
    #   rule Article.Read publicWhen status "published"
    # La condition est appliquée côté API (liste ET détail), jamais seulement
    # dans le frontend : un contenu modéré ne doit pas rester accessible par
    # son identifiant.
    conditional_visibility_rule: "rule" REFERENCE "publicWhen" NAME STRING_LITERAL _NL
    # Un vote ou un like est souvent unique par compte et par cible. Une règle
    # composite vaut mieux qu'un champ-fingerprint fourni par le client : les
    # colonnes de relation sont déterminées par le serveur et l'index SQLite
    # protège aussi les requêtes concurrentes.
    uniqueness_rule: "rule" REFERENCE "oncePer" NAME ("," NAME)+ _NL

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
    # AJOUT (brique 14, point 86) : « by » accepte un NOM DE CHAMP en plus d'un
    # entier. 'by 1' retire toujours la même chose (une réputation, un like) ;
    # 'by quantity' retire CE QUE LE CLIENT A DEMANDÉ — c'est ce qui manquait
    # pour qu'une boutique décompte son stock. Deux alternatives distinctes
    # plutôt qu'un terminal commun : INT et NAME ne se lisent pas pareil, et le
    # transformateur doit savoir lequel il a reçu.
    decrement_rule: "rule" REFERENCE "decrements" REFERENCE _NL
                   | "rule" REFERENCE "decrements" REFERENCE "by" INT _NL
                   | "rule" REFERENCE "decrements" REFERENCE "by" NAME _NL
    increment_rule: "rule" REFERENCE "increments" REFERENCE _NL
                   | "rule" REFERENCE "increments" REFERENCE "by" INT _NL
                   | "rule" REFERENCE "increments" REFERENCE "by" NAME _NL

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

    # AJOUT (roadmap, écosystème de capacités -- brique paiement, point 74) :
    #   rule Order.total payable
    # désigne le champ qui porte le MONTANT, donc l'entité à encaisser. Une
    # production nommée à part, comme pour 'increments'/'decrements' : un
    # mot-clé partagé rouvrirait le piège de filtrage Lark du point 27.
    payable_rule: "rule" REFERENCE "payable" _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 10, point 77) :
    #   rule Order.total derivedFrom Product.price by quantity
    # le champ nommé à gauche est CALCULÉ PAR LE SERVEUR depuis un champ d'une
    # ligne liée, multiplié par un champ de l'entité elle-même. Il disparaît
    # des corps de requête (création ET modification) : c'est tout l'objet de
    # la brique. Sans elle, `payable` relisait en base un montant que le client
    # y avait écrit -- deux exploits prouvés, voir point 77.
    # Production nommée à part, comme 'increments'/'decrements' et 'payable' :
    # un mot-clé partagé rouvrirait le piège de filtrage Lark du point 27.
    derivation_rule: "rule" REFERENCE "derivedFrom" REFERENCE "by" NAME _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 12, point 82) :
    #   rule Commande.total sumOf Ligne.sousTotal
    # le champ nommé à gauche est la SOMME d'un champ de toutes les lignes
    # enfants. Recalculé par le serveur à chaque écriture d'une ligne (création,
    # modification, suppression), donc absent des corps de requête comme un
    # champ 'derivedFrom'. C'est la brique qui rend une commande à plusieurs
    # articles chiffrable -- `derivedFrom` ne sait lire qu'UNE ligne liée.
    # Production nommée à part, même raison que ci-dessus (piège Lark, point 27).
    aggregation_rule: "rule" REFERENCE "sumOf" REFERENCE _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 16, point 89) :
    #   rule Order.placedAt timestamp
    # le champ nommé porte l'instant de CRÉATION de l'enregistrement, écrit par
    # le serveur et jamais ensuite. Absent des corps de requête comme un champ
    # 'generated' : une date qu'on peut se donner n'atteste de rien.
    # Production nommée à part, même raison que ci-dessus (piège Lark, point 27).
    timestamp_rule: "rule" REFERENCE "timestamp" _NL

    # AJOUT (brique 22, point 102) :
    #   rule Order.reference numbered "CMD-{YYYY}-{NNNN}"
    # le champ nommé porte un NUMÉRO LISIBLE, attribué par le serveur à la
    # création et jamais ensuite. Même famille que 'timestamp' : absent des corps
    # de requête, création comme modification. Le mot-clé n'est pas 'reference' —
    # il se confondrait avec le nom du champ qu'on lui donne presque toujours,
    # et 'rule Order.reference reference …' ne se lit pas.
    numbering_rule: "rule" REFERENCE "numbered" STRING_LITERAL _NL

    # AJOUT (roadmap, écosystème de capacités -- brique 17, point 90) :
    #   rule Order.Create requiresOwn Customer
    # l'appelant doit DÉJÀ posséder un enregistrement de l'entité nommée pour
    # pouvoir créer celui-ci. Née d'un constat sur une boutique réelle : deux
    # commandes portaient un compte sans aucune fiche client, donc sans nom ni
    # adresse — des commandes qu'on ne peut pas expédier.
    # Production nommée à part, même raison que ci-dessus (piège Lark, point 27).
    requirement_rule: "rule" REFERENCE "requiresOwn" NAME _NL

    # AJOUT (roadmap, contrôle du rendu visuel) : bloc optionnel "ui" pour
    # surcharger ce que le générateur devine automatiquement. Ex. :
    #   ui Project
    #       theme: market
    #       primary: title
    #       order: title, price, stock
    # SUPPRESSION (roadmap, sur demande explicite) : monl ne génère plus
    # de back-office CRUD par entité (voir generate_all).
    # POINT 72 : "theme" n'a plus d'effet non plus — le compilateur ne décide
    # RIEN du visuel, il n'a donc plus de thème à épingler. Les trois clés
    # restent ACCEPTÉES par la grammaire pour ne casser aucune spec
    # existante (même politique qu'au point 41 pour 'landing mode/template'),
    # mais aucune n'influence quoi que ce soit. La direction de design vient
    # du dialogue, et voyage par le brief.
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
    # AJOUT (point 95) : 'capability auth' gagne sa PREMIÈRE fonction, après
    # avoir été purement déclaratif depuis la brique 1. Le bloc indenté est
    # OPTIONNEL — toute spec écrite avant ce point continue de compiler à
    # l'identique, ce qui est la condition pour qu'une brique dormante se
    # réveille sans casser ce qui existe.
    #   capability auth
    #       identifier: email, phone
    capability_block: "capability" NAME _NL [_INDENT capability_prop+ _DEDENT]
    ?capability_prop: capability_identifier | capability_phone_prefix | capability_lockout | capability_password_reset | capability_refresh_tokens | capability_totp | capability_currency | capability_provider
    capability_identifier: "identifier" ":" NAME ("," NAME)* _NL
    # AJOUT (point 95, trouvé en éprouvant la brique sur un vrai site) :
    # '06 12 34 56 78' et '+33612345678' sont le MÊME numéro, et faisaient deux
    # comptes. monl ne peut pas le deviner — l'indicatif dépend du pays, et
    # rien dans une spec ne le dit. Il le fait donc DÉCLARER, faute de quoi la
    # promesse « deux écritures = un compte » serait fausse dans le cas le plus
    # courant.
    #       phone_prefix: "+33"
    capability_phone_prefix: "phone_prefix" ":" STRING_LITERAL _NL
    # BRIQUE B4 : options d'authentification déclaratives. Les durées sont en
    # secondes et aucune valeur par défaut n'est injectée dans une spec qui ne
    # demande pas la capacité.
    #   lockout: 5 in 300
    #   password_reset: 900
    #   refresh_tokens: 2592000
    #   totp
    capability_lockout: "lockout" ":" INT "in" INT _NL
    capability_password_reset: ("password_reset" | "passwordReset") ":" INT _NL
    capability_refresh_tokens: ("refresh_tokens" | "refreshTokens") ":" INT _NL
    capability_totp: "totp" _NL | "totp" ":" "true" _NL
    # BRIQUE 2a : la DEVISE de l'encaissement, déclarée sur 'capability payment'.
    # Elle existe parce que le code figeait 'eur' et multipliait tout montant
    # par 100 — or le franc CFA n'a PAS de sous-unité : facturer 5 000 XOF
    # aurait envoyé 500 000 au prestataire. Ce n'est pas une préférence de
    # présentation, c'est l'unité dans laquelle on encaisse.
    #   capability payment
    #       currency: XOF
    capability_currency: "currency" ":" NAME _NL
    # BRIQUE 2b : le PRESTATAIRE d'encaissement. Stripe n'opère pas en Afrique
    # de l'Ouest, où l'argent passe par le mobile money derrière un agrégateur.
    #   capability payment
    #       provider: fedapay
    #       currency: XOF
    capability_provider: "provider" ":" NAME _NL

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
    # AJOUT (roadmap, brique 13 -- point 83) : bloc optionnel "assets", qui
    # déclare les fichiers fournis par l'HUMAIN (logo, icône, photos) et le
    # dossier où ils vivent. Il existe parce que monl ne savait pas qu'un asset
    # existe : un chemin d'image faux compilait en silence, et `monl frontend`
    # renommait frontend/ -- donc égarait les photos qu'on y avait déposées.
    #   assets
    #       dir: "assets"
    #       logo: "logo.svg"
    #       favicon: "favicon.png"
    assets_block: "assets" _NL _INDENT assets_prop+ _DEDENT
    ?assets_prop: assets_dir | assets_logo | assets_favicon
    assets_dir: "dir" ":" STRING_LITERAL _NL
    assets_logo: "logo" ":" STRING_LITERAL _NL
    assets_favicon: "favicon" ":" STRING_LITERAL _NL

    # Une migration non additive doit être NOMMÉE et exécutée explicitement.
    # La spec décrit l'état cible ; l'opération conserve assez d'information
    # pour vérifier sa précondition et, quand c'est possible, la défaire.
    migration_block: "migration" NAME _NL _INDENT migration_operation+ _DEDENT
    ?migration_operation: rename_migration | alter_migration | drop_migration
    rename_migration: "rename" REFERENCE "to" NAME _NL
    alter_migration: "alter" REFERENCE "from" TYPE "to" TYPE _NL
    drop_migration: "drop" REFERENCE _NL

    landing_block: "landing" _NL _INDENT landing_prop+ _DEDENT
    ?landing_prop: landing_mode | landing_template | landing_brief | landing_section
                 | landing_question
    landing_mode: "mode" ":" NAME _NL
    landing_template: "template" ":" STRING_LITERAL _NL
    landing_brief: "brief" ":" STRING_LITERAL _NL
    landing_section: "section" STRING_LITERAL ":" STRING_LITERAL _NL
    # AJOUT (point 94) : "question" répétable — une FAQ est une LISTE de
    # couples, et `section` ne savait dire qu'un titre et un texte. Les quatre
    # questions de `projets/SneakerLab` tenaient donc dans UNE chaîne, et
    # l'interface les rendait collées en un seul paragraphe : elle était
    # fidèle, c'est le modèle de contenu qui ne savait pas dire « une FAQ ».
    # Forme PLATE, comme `section` : une FAQ est la collection des `question`
    # du bloc. Un sous-bloc indenté aurait ajouté un niveau à la seule
    # grammaire où l'indentation a déjà coûté deux bugs (point 6).
    #   landing
    #       question "Comment choisir ma taille ?": "Nos paires taillent…"
    landing_question: "question" STRING_LITERAL ":" STRING_LITERAL _NL

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
    #       title: "Refonte Aurora", imageUrl: "assets/aurora.jpg", year: 2024
    #
    # BRIQUE 21 (point 100) : un seed d'ENFANT désigne sa ligne parente. Sans
    # cette forme, une entité fille d'une table métier ne pouvait pas figurer
    # dans les données de démonstration -- sa clé étrangère n'est pas un champ
    # déclaré, donc le validateur la refusait. Le parent est nommé par un CHAMP
    # et une VALEUR, jamais par un rang : un numéro de ligne ne dit rien à la
    # lecture, et se décale dès qu'on insère une ligne au milieu. Ex. :
    #   seed Variant for Product.name "Chaise Ligne"
    #       finish: "Chêne naturel", price: 249.90, stock: 12
    seed_block: "seed" NAME seed_parent? _NL _INDENT seed_row+ _DEDENT
    seed_parent: "for" NAME "." NAME STRING_LITERAL
    seed_row: seed_pair ("," seed_pair)* _NL
    seed_pair: NAME ":" seed_value
    ?seed_value: STRING_LITERAL | SIGNED_NUMBER

    io_param: NAME ":" TYPE
            | REFERENCE

    TYPE: "String" | "Text" | "Integer" | "Float" | "Boolean" | "Date" | "DateTime" | "Email" | "UUID" | "Money" | "Image" | "Upload"
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

    def constraint_rule(self, reference, valid_type, value=None):
        data = {"reference": str(reference), "type": str(valid_type)}
        if value is not None:
            data["value"] = str(value)
        return {"rule": data}

    def oneof_rule(self, reference, *valeurs):
        return {"rule": {"reference": str(reference), "type": "oneOf",
                         "value": [str(v).strip('"') for v in valeurs]}}

    def release_rule(self, reference, valeur, entite):
        return {"rule": {"reference": str(reference), "type": "releases",
                         "value": str(valeur).strip('"'), "entity": str(entite)}}

    def upload_rule(self, reference, maximum, *types):
        return {"rule": {
            "reference": str(reference), "type": "upload",
            "max_bytes": int(maximum),
            "accepted_types": [str(value).strip('"') for value in types],
        }}

    def send_rule(self, reference, subject, body):
        def decode(token):
            try:
                return str(py_ast.literal_eval(str(token)))
            except (SyntaxError, ValueError):
                # Le lexer a déjà garanti un STRING_LITERAL. Ce repli garde un
                # diagnostic de validation lisible si une future évolution de
                # la grammaire accepte une séquence d'échappement inconnue.
                return str(token)[1:-1]

        return {"rule": {
            "reference": str(reference), "type": "sends",
            "subject": decode(subject), "body": decode(body),
        }}

    def filter_rule(self, reference, field):
        return {"rule": {"reference": str(reference), "type": "filter",
                          "field": str(field)}}

    def sort_rule(self, reference, field):
        return {"rule": {"reference": str(reference), "type": "sort",
                          "field": str(field)}}

    def restriction_rule(self, reference, actor_name):
        return {"rule": {"reference": str(reference), "type": "restrictedTo", "value": str(actor_name)}}

    def postpayment_rule(self, reference, actor_name):
        return {"rule": {"reference": str(reference), "type": "writableAfterPayment",
                         "value": str(actor_name)}}

    def sharing_rule(self, reference, *actor_names):
        return {"rule": {"reference": str(reference), "type": "sharedBy", "value": [str(a) for a in actor_names]}}

    def ownership_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "ownedBy", "value": str(owner_entity)}}

    def access_rule(self, reference, *party_columns):
        return {"rule": {"reference": str(reference), "type": "accessibleBy",
                         "value": [str(c) for c in party_columns]}}

    def visibility_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "public"}}

    def conditional_visibility_rule(self, reference, field, value):
        return {"rule": {"reference": str(reference), "type": "publicWhen",
                          "field": str(field),
                          "value": str(value).strip('"')}}

    def uniqueness_rule(self, reference, *parents):
        return {"rule": {"reference": str(reference), "type": "oncePer",
                          "parents": [str(parent) for parent in parents]}}

    def masking_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "hidden"}}

    def _quantite(self, amount):
        """« by 3 » ou « by quantity » — l'un est une constante, l'autre un champ
        de l'entité déclenchante (brique 14, point 86). Le type du jeton Lark
        les distingue : ne pas le perdre ici, le validateur en a besoin."""
        if amount is None:
            return {"amount": 1, "amount_field": None}
        if getattr(amount, "type", None) == "INT" or str(amount).isdigit():
            return {"amount": int(amount), "amount_field": None}
        return {"amount": None, "amount_field": str(amount)}

    def decrement_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "decrements",
            "value": str(target_ref), **self._quantite(amount),
        }}

    def increment_rule(self, trigger_ref, target_ref, amount=None):
        return {"rule": {
            "reference": str(trigger_ref), "type": "increments",
            "value": str(target_ref), **self._quantite(amount),
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

    def payable_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "payable"}}

    def derivation_rule(self, reference, source_ref, factor):
        return {"rule": {
            "reference": str(reference), "type": "derivedFrom",
            "value": str(source_ref), "factor": str(factor),
        }}

    def aggregation_rule(self, reference, source_ref):
        return {"rule": {
            "reference": str(reference), "type": "sumOf",
            "value": str(source_ref),
        }}

    def timestamp_rule(self, reference):
        return {"rule": {"reference": str(reference), "type": "timestamp"}}

    def numbering_rule(self, reference, gabarit):
        token = str(gabarit)
        return {"rule": {"reference": str(reference), "type": "numbered",
                         "value": token[1:-1].replace('\\"', '"')
                                             .replace('\\\\', '\\')}}

    def requirement_rule(self, reference, owner_entity):
        return {"rule": {"reference": str(reference), "type": "requiresOwn",
                         "value": str(owner_entity)}}

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

    def landing_question(self, question, reponse):
        # Même marqueur temporaire que les sections, même raison : les
        # questions s'ACCUMULENT là où les autres clés s'écrasent.
        return {"_question": {"question": str(question).strip('"'),
                              "answer": str(reponse).strip('"')}}

    def landing_block(self, *props):
        merged, sections, faq = {}, [], []
        for p in props:
            if not p:
                continue
            if "_section" in p:
                sections.append(p["_section"])
            elif "_question" in p:
                faq.append(p["_question"])
            else:
                merged.update(p)
        if sections:
            merged["sections"] = sections
        # L'ORDRE DE DÉCLARATION est conservé : dans une FAQ il porte du sens
        # (on répond d'abord à ce qu'on demande le plus), et rien ne permet de
        # le retrouver après coup.
        if faq:
            merged["faq"] = faq
        return {"landing": merged}

    def assets_dir(self, valeur):
        return {"dir": str(valeur).strip('"')}

    def assets_logo(self, valeur):
        return {"logo": str(valeur).strip('"')}

    def assets_favicon(self, valeur):
        return {"favicon": str(valeur).strip('"')}

    def assets_block(self, *props):
        merged = {}
        for p in props:
            if p:
                merged.update(p)
        return {"assets": merged}

    def rename_migration(self, reference, new_name):
        return {"kind": "rename", "reference": str(reference),
                "new_name": str(new_name)}

    def alter_migration(self, reference, old_type, new_type):
        return {"kind": "alter", "reference": str(reference),
                "from_type": str(old_type), "to_type": str(new_type)}

    def drop_migration(self, reference):
        return {"kind": "drop", "reference": str(reference)}

    def migration_block(self, name, *operations):
        return {"migration": {"name": str(name),
                               "operations": list(operations)}}

    def capability_identifier(self, *formes):
        return {"identifier": [str(f) for f in formes]}

    def capability_phone_prefix(self, valeur):
        return {"phone_prefix": str(valeur).strip('"')}

    def capability_lockout(self, maximum, fenetre):
        return {"lockout": {"max_attempts": int(maximum),
                             "window_seconds": int(fenetre)}}

    def capability_password_reset(self, duree):
        return {"password_reset": int(duree)}

    def capability_refresh_tokens(self, duree):
        return {"refresh_tokens": int(duree)}

    def capability_totp(self):
        return {"totp": True}

    def capability_provider(self, nom):
        # Minuscules dès le parsing : 'FedaPay' et 'fedapay' sont le même
        # prestataire, et laisser passer les deux ferait deux specs pour une
        # seule intention (même raison que pour la devise).
        return {"provider": str(nom).lower()}

    def capability_currency(self, code):
        # Normalisé en majuscules dès le parsing : 'xof' et 'XOF' sont le même
        # code ISO, et laisser passer les deux ferait deux specs différentes
        # pour une seule intention.
        return {"currency": str(code).upper()}

    def capability_block(self, name, *props):
        # Le bloc indenté étant optionnel, Lark passe None quand il est absent :
        # une capacité sans propriété reste exactement ce qu'elle était.
        options = {}
        for p in props:
            if p:
                options.update(p)
        return {"capability": {"name": str(name), **options}}

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


class MonlSyntaxError(ParseError):
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


_PARSER = None


def _get_parser():
    """Le parseur Lark, construit UNE fois et réutilisé (point 110).

    Sa construction — la compilation de la grammaire LALR — coûte ~50 ms ; la
    refaire à chaque appel dominait le temps de parsing (mesuré : parseur en
    cache 0,4 ms/parse contre 50 ms en le reconstruisant). Un parseur Lark est
    réutilisable entre parses ; seul le Transformer est réinstancié à chaque
    appel, pour rester sans état."""
    global _PARSER
    if _PARSER is None:
        _PARSER = Lark(grammar, parser='lalr', postlex=MonlIndenter())
    return _PARSER


def parse_monl_string(content, file_path=None):
    """Parse une chaîne monl directement (sans passer par un fichier).
    Utilisé par parse_monl_file pour valider
    une spec générée par l'IA avant de l'écrire sur disque.
    Lève MonlSyntaxError (message localisé : fichier, ligne, colonne,
    extrait) plutôt que l'exception Lark brute."""
    from lark.exceptions import UnexpectedInput
    parser = _get_parser()
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
