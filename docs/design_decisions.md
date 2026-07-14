# MonLang — Choix de conception assumés

Ce document répertorie les règles strictes et opinionées du compilateur — ce
qu'elles interdisent, pourquoi ce choix a été fait, et comment le contourner
quand le besoin est légitime. Objectif : servir à la fois de documentation
pour qui écrit une spec MonLang, et de mémoire pour le mainteneur du projet.

## Sommaire

**Sécurité et contrôle d'accès** : [1](#1-collision-de-privilèges-critical_collision) Collision de privilèges ·
[2](#2-restriction-de-champ-restrictedto) Restriction de champ ·
[3](#3-avertissement-sur-les-suppressions-non-admin-critical_warning) Avertissement suppressions non-Admin ·
[5](#5-contrôle-daccès-par-propriété-ownedby) Contrôle par propriété (`ownedBy`) ·
[9](#9-limitation-de-débit-sur-login) Limitation de débit `/login` ·
[11](#11-secret-jwt-unique-par-projet-faille-corrigée) Secret JWT unique par projet ·
[12](#12-révocation-de-token-logout) Révocation de token ·
[13](#13-limitation-de-débit-sur-register) Limitation de débit `/register` ·
[16](#16-actions-publiques-public--cas-dusage-portfolio) Actions publiques (`public`)

**Échappatoire IA** : [4](#4-garde-fou-statique-sur-le-code-généré-par-lia) Garde-fou statique (`custom`) ·
[21](#21-bloc-landing--front-marketing-sur--deuxième-échappatoire-ia) Bloc `landing` (garde-fou texte)

**API et données** : [7](#7-registre-dutilisateurs-réel-register-login) Registre d'utilisateurs réel ·
[8](#8-relations-belongsto-et-hasone) Relations `belongsTo`/`hasOne` ·
[10](#10-route-de-liste-get-entite) Route de liste ·
[14](#14-pagination-sur-la-route-de-liste) Pagination

**Front et identité visuelle** : [15](#15-identité-visuelle-du-front-minimal) Thème automatique ·
[17](#17-surcharge-explicite-du-rendu-visuel-bloc-ui) Surcharge `ui` ·
[18](#18-agencement-de-liste-adapté-au-rôle-de-chaque-entité) Agencement par rôle d'entité ·
[19](#19-front-minimal-en-react-au-lieu-de-js-impératif) Front React (retiré depuis, voir 22) ·
[20](#20-unicité-visuelle-par-projet-graine-monlang_theme_seed) Unicité visuelle par projet ·
[22](#22-suppression-du-back-office-ui--monlang-ne-génère-plus-de-front-crud) Suppression du back-office `/ui` ·
[23](#23-tableau-de-bord-post-connexion-app-et-corrections-diverses) Tableau de bord post-connexion (`/app`) ·
[24](#24-écosystème-de-capacités--brique-1--capability-auth) Écosystème de capacités (brique 1) ·
[25](#25-écosystème-de-capacités--brique-2--masquage-de-champ-hidden) Masquage de champ (brique 2) ·
[26](#26-écosystème-de-capacités--brique-3--réputation-dynamique-decrements) Réputation dynamique (brique 3) ·
[27](#27-écosystème-de-capacités--brique-4--appréciations-increments) Appréciations (brique 4) ·
[28](#28-écosystème-de-capacités--brique-5--likes-en-catégories-categorized) Likes en catégories (brique 5)

---

## 1. Collision de privilèges (`CRITICAL_COLLISION`)

**Ce qu'elle interdit :** par défaut, deux acteurs différents ne peuvent pas
avoir le droit d'effectuer la même action d'écriture (`Create`, `Update`,
`Delete`) sur la même entité. La compilation échoue si c'est le cas.

**Pourquoi :** dans un système où chaque route n'a historiquement qu'un seul
acteur autorisé, permettre silencieusement à plusieurs acteurs d'accéder à la
même action rendrait difficile de savoir, en lisant la spec, qui a réellement
le droit de faire quoi. La règle stricte force à rendre ce partage explicite
plutôt qu'accidentel.

**Comment le contourner légitimement :** déclarer une règle `sharedBy` :
```
rule Post.Delete sharedBy Admin, Moderator
```
Le compilateur fusionne alors les deux workflows en une seule route, avec un
contrôle d'accès qui accepte n'importe lequel des acteurs listés. Voir
`exemples/06_moderation_shared.yaml` pour un exemple complet.

---

## 2. Restriction de champ (`restrictedTo`)

**Ce qu'elle interdit :** une règle `rule Entite.champ restrictedTo Acteur`
marque un champ comme sensible. Si un bloc `custom` (logique IA) appelé par
un acteur différent de celui déclaré utilise ce champ en entrée, l'audit de
sécurité statique émet un avertissement `[SECURITY_AUDIT]`.

**Pourquoi :** empêcher qu'une donnée sensible (email, information privée...)
soit exposée à la logique métier générée par IA pour un acteur qui ne devrait
pas y avoir accès, même indirectement via un bloc `custom`.

**Comment le contourner légitimement :** ce n'est pas un blocage strict de la
compilation — c'est un avertissement. Si l'usage est volontaire, il suffit de
documenter pourquoi dans la spec (aucune syntaxe d'acquittement n'existe
encore pour faire taire l'avertissement).

---

## 3. Avertissement sur les suppressions non-`Admin` (`CRITICAL_WARNING`)

**Ce qu'elle signale :** tout workflow permettant à un acteur autre que
`Admin` d'exécuter une action `Delete` déclenche un avertissement (pas un
blocage).

**Pourquoi :** la suppression est l'action la plus risquée du CRUD de base
(irréversible sans sauvegarde) — le compilateur attire l'attention dessus
plutôt que de la laisser passer silencieusement, sans pour autant l'interdire
puisque c'est un besoin métier légitime dans de nombreux cas (un `User` qui
supprime ses propres données, par exemple).

**Comment réagir :** ce n'est qu'un signal — à charge du développeur de la
spec de vérifier que la suppression est bien protégée au niveau infra
(sauvegarde, log d'audit, etc.), ce que le compilateur ne peut pas garantir
depuis la spec seule.

---

## 4. Garde-fou statique sur le code généré par l'IA

**Ce qu'il interdit :** le code Python produit par le LLM pour remplir un
bloc `custom` est rejeté s'il contient :
- un import parmi une liste bannie (`os`, `subprocess`, `socket`, `requests`,
  `pickle`, etc. — modules réseau, système, ou de désérialisation dangereuse)
- un appel à une fonction bannie (`eval`, `exec`, `open`, `__import__`,
  `getattr`/`setattr`, etc.)
- une requête SQL construite par f-string, concaténation `+` ou `%` à
  l'intérieur d'un appel `.execute()`
- une boucle `while True`/`while 1` sans `break` détectable

**Pourquoi :** le bloc `custom` est pensé comme une zone de logique métier
pure (transformer des données, appliquer une règle de calcul) — il ne doit
jamais avoir besoin d'accéder au système de fichiers, au réseau, ou à la base
de données directement. Tout ce qui ressemble à une tentative de sortir de ce
périmètre est bloqué par défaut, sans exception.

**Comment le contourner légitimement :** ce n'est volontairement pas prévu.
Si un besoin métier réel nécessite un accès réseau ou fichier depuis la
logique custom, ce n'est plus un cas d'usage pour le bloc `custom` — il faut
l'implémenter comme une route à part entière dans le socle déterministe, où
le code n'est pas généré par un LLM et peut donc être audité normalement par
un humain avant déploiement.

---

## 5. Contrôle d'accès par propriété (`ownedBy`)

**Ce qu'elle permet :** une règle `rule Entite.Action ownedBy EntiteProprietaire`
(sur `Update` ou `Delete`) restreint l'action au seul enregistrement qui
appartient à l'acteur courant, en plus du contrôle de rôle habituel. Elle
nécessite qu'une relation compatible soit déclarée entre les deux entités
(`hasMany`, `hasOne`, ou `belongsTo` — voir point 8) — c'est elle qui fournit
la colonne de clé étrangère utilisée pour vérifier la propriété.

**Comment ça marche au runtime :** à l'inscription (`POST /register`), un
compte est créé avec un identifiant numérique réel (`user_id`) dans la table
`_monlang_users`. À la connexion (`POST /login`), ce `user_id` est porté par
le JWT. À la création d'un enregistrement, il est automatiquement enregistré
comme propriétaire. Sur `Update` et `Delete`, l'application vérifie que le
`user_id` du token correspond bien au propriétaire enregistré, sinon elle
renvoie un `403`.

**Combinaison avec plusieurs acteurs (`sharedBy` implicite) :** si une route
`Update`/`Delete` est partagée entre plusieurs acteurs (ex. un `Customer`
propriétaire et un `Agent` au rôle plus large), le contrôle de propriété ne
s'applique **qu'à l'acteur explicitement désigné comme propriétaire** par la
règle `ownedBy` — un acteur qui partage la route via un rôle différent n'est
pas soumis à cette restriction, seulement au contrôle de rôle. Voir
`exemples/09_owned_and_shared.yaml`.

**Limite de conception qui demeure :** le registre d'utilisateurs (point 7)
n'a pas de vérification d'email ni de récupération de compte — un mot de
passe oublié est définitivement perdu dans ce prototype. Voir
`exemples/07_ownership_demo.yaml` pour un exemple complet d'`ownedBy` seul.

**Effet de bord positif (gap corrigé au passage) :** avant cet ajout, les
colonnes de clé étrangère générées dans `schema.sql` pour les relations
`hasMany` n'étaient en réalité jamais renseignées par les routes `Create` —
elles restaient `NULL` pour tout enregistrement créé, rendant les relations
inertes au runtime malgré leur présence dans le schéma. Elles sont
désormais peuplées automatiquement pour toute entité ayant une relation
entrante, qu'une règle `ownedBy` soit déclarée ou non.

---

## 6. Collision de privilèges (`CRITICAL_COLLISION`)

---

## 7. Registre d'utilisateurs réel (`/register`, `/login`)

**Ce qui a changé :** l'application générée possède désormais une vraie
table `_monlang_users` (créée automatiquement, indépendamment de la spec),
avec mot de passe haché (PBKDF2-HMAC-SHA256, salé, 100 000 itérations — pas
de dépendance externe type bcrypt nécessaire). `POST /register` crée un
compte ; `POST /login` vérifie username + mot de passe contre la base et
délivre un JWT dont l'`actor` et le `user_id` viennent du compte réel, pas
d'une déclaration libre du client.

**Ce que ça remplace :** avant cet ajout, `actor` et `user_id` étaient
directement fournis par le client à la connexion, sans aucune vérification —
n'importe qui pouvait se déclarer `Admin`. C'était documenté comme une
limite assumée du prototype ; ce n'en est plus une pour l'identité de base.

**Limites qui demeurent (prototype) :** pas de politique de robustesse du
mot de passe au-delà d'une longueur minimale (8 caractères), pas de
vérification d'email, pas de procédure de récupération de compte, pas de
rotation de la clé JWT. Une seule limitation de débit protège `/login`
(point 9) — `/register` n'en a pas encore.

---

## 8. Relations `belongsTo` et `hasOne`

**Ce qui a changé :** ces deux types de relation étaient acceptés par la
grammaire depuis le début, mais totalement ignorés par le générateur — une
spec qui les utilisait compilait sans erreur mais ne produisait aucune
colonne de clé étrangère, aucun effet réel. Ils sont désormais implémentés :
- `relation A hasMany B` : `B` porte la colonne `a_id` (A est parent)
- `relation A hasOne B` : identique à `hasMany`, avec en plus une contrainte
  `UNIQUE` sur la colonne (garantit une relation 1-1)
- `relation A belongsTo B` : `A` porte la colonne `b_id` (B est parent —
  c'est l'inverse de `hasMany`/`hasOne` en termes de placement de la colonne)

Voir `exemples/08_relations_demo.yaml` pour un exemple des 3 types.

---

## 9. Limitation de débit sur `/login`

**Ce qu'elle fait :** au-delà de 5 tentatives de connexion en moins de 60
secondes depuis la même adresse IP, l'application renvoie `429 Too Many
Requests` plutôt que de continuer à vérifier les identifiants.

**Limite assumée (prototype) :** le compteur est conservé en mémoire du
processus Python — remis à zéro à chaque redémarrage du serveur, et non
partagé entre plusieurs instances si l'application est un jour répliquée.
Suffisant pour freiner un script d'attaque naïf en local, pas conçu pour
résister à une attaque distribuée à grande échelle (nécessiterait un
magasin partagé type Redis en production).

---

## 10. Route de liste (`GET /entite`)

**Ce qui a changé :** une action `Read` dans un workflow générait jusqu'ici
uniquement `GET /entite/{id}` (lecture par identifiant connu) — il n'existait
aucun moyen d'énumérer les enregistrements existants sans déjà connaître
leurs identifiants un par un. `GET /entite` (sans paramètre) est désormais
générée en plus, avec le même contrôle d'accès que la lecture par ID.

**Limite assumée :** pas de pagination — pour une table avec un très grand
nombre d'enregistrements, cette route renvoie tout d'un coup. Acceptable
pour un prototype, à revoir avant tout usage à plus grande échelle.

---

## 11. Secret JWT unique par projet (faille corrigée)

**Ce qui a changé :** le secret utilisé pour signer les JWT était jusqu'ici
une chaîne fixe, codée en dur dans `generator.py`, **identique dans toutes
les applications générées par MonLang**. Un token forgé avec cette clé pour
une application était donc valide sur n'importe quelle autre application
issue du même compilateur — et puisque le code source de MonLang est
public, cette clé l'était de fait aussi.

**Ce qui a été fait :** un secret aléatoire de 32 octets (`secrets.token_hex`)
est désormais généré une seule fois par projet, à la première compilation,
et stocké dans `.jwt_secret` (ajouté au `.gitignore` — ne doit jamais être
commité). `app.py` lit ce fichier au démarrage et refuse de démarrer s'il
est absent, avec un message clair. Recompiler la spec ne régénère pas ce
secret (pour ne pas invalider les sessions actives) — il faut le supprimer
manuellement pour en forcer le renouvellement.

**Limite qui demeure :** un seul secret par projet, pas de rotation
automatique périodique. Suffisant pour un prototype ; une vraie mise en
production voudrait une rotation régulière et un stockage dans un
gestionnaire de secrets plutôt qu'un fichier local.

---

## 12. Révocation de token (`/logout`)

**Ce qui a changé :** chaque JWT émis porte désormais un identifiant unique
(`jti`). `POST /logout` enregistre ce `jti` dans une liste noire persistante
(`_monlang_revoked_tokens`) — toute présentation ultérieure de ce token est
alors rejetée (`401`), même s'il n'a pas encore atteint sa date d'expiration
naturelle (2h par défaut).

**Limite assumée :** la liste noire grandit indéfiniment (pas de purge
automatique des entrées expirées) — négligeable à l'échelle d'un prototype,
mais à surveiller si le volume de connexions/déconnexions devient important.

---

## 13. Limitation de débit sur `/register`

**Ce qui a changé :** le mécanisme de limitation de débit (point 9) a été
généralisé pour protéger `/register` en plus de `/login` — jusqu'ici, rien
n'empêchait de créer des comptes en masse ou d'énumérer les noms
d'utilisateur déjà pris (le code `409` révèle qu'un nom existe déjà).

---

## 14. Pagination sur la route de liste

**Ce qui a changé :** `GET /entite` accepte désormais `limit` (défaut 50,
plafonné à 200) et `offset` (défaut 0), et renvoie le nombre total
d'enregistrements en plus des données de la page demandée. Comble la limite
signalée au point 10.

---

## 15. Identité visuelle du front minimal

**Ce qui a changé :** le front généré (`/ui`) n'utilise plus une seule mise
en page générique pour toutes les applications. Il choisit un système de
design complet (palette de 4 couleurs, typographies, rayon de bordure,
traitement des cartes) parmi 5 propositions distinctes : `editorial` (blog,
articles), `market` (e-commerce, commandes), `console` (todo, tickets,
tâches — thème sombre), `civic` (réservations, réseau social, événements),
et `ledger` (repli neutre pour les domaines sans signal clair).

**Comment le choix est fait :** le vocabulaire de la spec (nom de l'app,
noms d'entités, noms d'attributs) est comparé à des mots-clés propres à
chaque thème. Le thème le mieux assorti est retenu ; en cas d'égalité ou
d'absence de signal, le choix est réparti de façon stable (hachage du nom
de l'app) entre les thèmes candidats, pour que deux applications généralistes
différentes ne se ressemblent pas non plus.

**Rendu des données :** les routes `Read`/liste renvoient désormais des
objets nommés (`{"title": ..., "content": ...}`) plutôt que des tableaux
positionnels bruts — le front les affiche en cartes (titre, extrait,
badges de prix/booléens/métadonnées selon le type de chaque attribut)
plutôt qu'en JSON brut dans une balise `<pre>`.

**Limite assumée :** le choix du thème reste une heuristique par mots-clés,
pas une analyse sémantique — une entité au nom inhabituel peut atterrir
dans un thème moins évidemment approprié (le thème neutre `ledger` ou le
repli par hachage prennent le relais dans ce cas, sans jamais casser le
rendu).

---

## 16. Actions publiques (`public`) — cas d'usage portfolio

**Ce qui a changé :** une règle `rule Entite.Action public` retire
entièrement l'obligation d'authentification sur la route générée
correspondante — ni token JWT, ni contrôle de rôle. Jusqu'ici, MonLang
supposait que tout consommateur de données était un acteur authentifié,
ce qui rendait impossible un cas d'usage aussi simple qu'un portfolio
(projets lisibles par n'importe qui, formulaire de contact ouvert).

**Limites/interactions assumées :**
- `public` n'est valable que sur `Create`, `Read`, `Update`, `Delete` — pas
  sur `Execute` (une fonction custom garde toujours besoin d'une identité).
- Si `public` et `ownedBy` sont déclarées sur la même action, `public`
  l'emporte : la route reste ouverte, sans contrôle de propriété (une route
  publique n'a par définition aucune identité à comparer).
- Une action publique n'a pas de colonne de propriétaire peuplée à la
  création (pas d'identité fiable disponible) — la colonne de clé étrangère
  associée reste `NULL` dans ce cas précis.
- Les actions publiques sont exclues de la détection de collision de
  privilèges (point 1) : le contrôle de rôle étant entièrement désactivé,
  la notion de "plusieurs acteurs en conflit" ne s'applique plus.

Voir `exemples/10_portfolio_public.yaml` pour un exemple complet (projets
publics, formulaire de contact public, gestion réservée à `Admin`).

---

## 17. Surcharge explicite du rendu visuel (bloc `ui`)

**Ce qui a changé :** un bloc optionnel `ui NomEntite` permet de surcharger
ce que le générateur devine automatiquement pour le front minimal (point 15) :
```
ui Project
    theme: market
    primary: title
    order: title, price, stock
```
- `theme` : force le thème visuel de toute l'application (un seul système
  de design par app — la première surcharge valide trouvée dans la spec
  l'emporte sur la détection automatique par mots-clés). Doit être l'un des
  5 thèmes connus (`editorial`, `market`, `console`, `civic`, `ledger`) ;
  un nom inconnu est silencieusement ignoré, la sélection automatique reprend
  la main.
- `primary` : impose quel attribut sert de titre de carte, à la place de la
  détection automatique (`title`/`name`/`subject`/`label`, ou premier
  `String`).
- `order` : impose l'ordre d'affichage des champs dans les formulaires et
  les cartes ; les attributs non listés sont ajoutés à la suite, dans leur
  ordre de déclaration.

**Ce qui est validé :** l'existence de l'entité, et que `primary`/`order`
référencent bien des attributs réels de cette entité — une faute de frappe
est détectée à la compilation plutôt que de produire un rendu silencieusement
dégradé.

Voir `exemples/10_portfolio_public.yaml` (thème `editorial` forcé, ordre des
champs de `Project` explicite).

## 18. Agencement de liste adapté au rôle de chaque entité

**Ce qui a changé :** au-delà du thème (identité visuelle commune à toute
l'app), chaque entité reçoit désormais un agencement de liste détecté
automatiquement selon sa forme (`_compute_entity_layout`, toujours par
types/mots-clés, jamais par le contenu des données) :
- `board` (kanban) : entité "tâche" avec un champ de statut ou un booléen
  d'achèvement — groupé en colonnes sur ce champ.
- `shop` : présence d'un attribut `Money` — grille catalogue élargie.
- `feed` : vocabulaire chronologique (post/tweet/comment/message/...) ou
  date + corps de texte — liste verticale de lecture.
- `table` : aucun champ exploitable comme titre (entité de liaison ou de
  données pures, ex. `Like`, `OrderItem`) — rangées compactes.
- `cards` : agencement par défaut (comportement historique), sinon.

Ainsi deux entités très différentes d'une même app (une todo-list et un
catalogue produit) ne sont plus rendues avec la même grille de cartes.

## 19. Front minimal en React (au lieu de JS impératif)

**Ce qui a changé :** `_generate_frontend` produit un vrai front React
(composants, hooks, state) plutôt que de la manipulation directe du DOM.
Aucune étape de build : React, ReactDOM et Babel standalone sont chargés
depuis un CDN, et le JSX est transpilé dans le navigateur au chargement de
la page — un compromis assumé pour rester fidèle au principe "zéro
outillage à installer pour utiliser l'app générée", à ne pas reproduire
pour un produit à fort trafic (la transpilation à la volée a un coût ; il
faudrait alors un vrai pipeline Vite/esbuild).

## 20. Unicité visuelle par projet (graine `.monlang_theme_seed`)

**Le problème :** le thème (point 15) est choisi par mots-clés du domaine
avant tout hachage — deux projets de même domaine (deux todo-lists, par
exemple) obtenaient donc systématiquement le même thème ET le même
agencement, quel que soit le nom de l'app.

**Ce qui a changé :** une graine aléatoire de 16 octets est générée une
seule fois par projet, à la première compilation, et conservée dans
`.monlang_theme_seed` (jamais commitée — même logique que `.jwt_secret`,
point 11). Elle sert à appliquer une variation fine *sur* le thème choisi
par le domaine (rotation de teinte des couleurs d'accent, rayon des
bordures) sans jamais le remplacer : deux todo-lists restent reconnaissables
comme telles (même palette de base, mêmes polices), mais cessent d'être des
pixels identiques. Recompiler la spec NE régénère PAS la graine (le style
du projet reste stable dans le temps) ; il faut supprimer le fichier à la
main pour en tirer un nouveau look. Les attributs de fond/texte
(`bg`/`surface`/`ink`) ne sont jamais modifiés, pour ne pas risquer de
dégrader le contraste.

## 21. Bloc `landing` — front marketing sur `/`, deuxième échappatoire IA

**Le problème :** `/ui` (points 15-20) est un vrai back-office (CRUD, kanban,
feed...), pas une page de conversion. Une vraie landing (gros titre vendeur,
image de marque, copie publicitaire) suppose des choix de direction
artistique qu'un compilateur par mots-clés ne peut pas improviser — ce
n'est pas un problème de "polish" mais de nature de la tâche.

**Ce qui a changé :** un bloc optionnel `landing`, sur le même principe que
`custom` (échappatoire IA balisée) : absent de la spec, comportement
inchangé (`/` redirige vers `/docs`). Présent, il active `/` avec deux modes
exclusifs :

- **`mode: ai`** (+ `brief` optionnel) : `generator.py` produit d'abord un
  gabarit 100% déterministe (thème + graine du point 20, propre au projet),
  avec des zones de texte balisées par des
  commentaires `<!--LANDING:clé-->...<!--/LANDING:clé-->`. Une étape
  **séparée et non bloquante** (`ai_landing_filler.py`, appelée depuis
  `main.py` après le socle, comme `ai_sandbox_filler.py` pour `custom`)
  interroge ensuite Ollama pour rédiger le texte (titre, sous-titre, CTA,
  3 points forts) et l'injecte dans ces zones. Si l'IA est indisponible, le
  gabarit déterministe déjà écrit reste tel quel — jamais d'échec de
  compilation à cause de la landing.
- **`mode: template`** (+ `template: "chemin/fichier.html"`) : importe un
  fichier HTML fourni par l'utilisateur (designer, export Framer...) et y
  substitue uniquement les emplacements qu'il a balisés avec
  `data-monlang="clé"` (texte) ou `data-monlang-href="clé"` (attribut
  href/src), pour un jeu de clés réservées connues
  (`app_name`, `headline`, `subheadline`, `cta_label`, `cta_target`,
  `feature_1/2/3`). Aucun appel IA dans ce mode ; tout reste déterministe.
  Voir `templates/signal.html` pour un exemple, et
  `exemples/12_landing_template_demo.yaml` pour son usage.

**Garde-fou spécifique au mode `ai` :** contrairement à `custom` (où l'IA
écrit du code Python vérifié par un garde-fou AST), ici l'IA n'a JAMAIS le
droit d'écrire du HTML — seulement du texte brut, sur un schéma JSON strict
à 6 clés. `validate_generated_landing_copy_safety` (dans
`ai_landing_filler.py`) rejette tout champ contenant un motif de balise, un
gestionnaire d'évènement JS, ou un schéma d'URL exécutable, en plus d'un
échappement HTML systématique à l'injection (défense en profondeur) — parce
que ce contenu est servi à de vrais visiteurs anonymes sur `/`, ce qui en
fait une surface XSS bien plus sensible qu'un code `custom` exécuté
uniquement côté serveur. Testé avec un faux serveur Ollama renvoyant une
charge `<img src=x onerror=...>` : rejetée avant toute écriture dans
`landing.html`.

**Sécurité du chemin de fichier (`mode: template`) :** `ast_validator.py`
refuse tout `template:` absolu ou contenant `..` — un chemin ne peut jamais
s'échapper du projet, avant même que le générateur ne touche au système de
fichiers.

Voir `exemples/11_landing_ai_demo.yaml` (mode `ai`) et
`exemples/12_landing_template_demo.yaml` (mode `template`).

## 22. Suppression du back-office `/ui` — MonLang ne génère plus de front CRUD

**Décision explicite de l'utilisateur** (pas une correction de bug ni une
régression) : le front React auto-généré sur `/ui` (points 15, 18, 19, 20 —
identité visuelle, agencement par entité, migration React, unicité par
projet) a été **entièrement retiré**. `_generate_frontend` et tous les
helpers qui n'existaient que pour lui (`_compute_entity_actions`,
`_compute_entity_field_roles`, `_compute_entity_visual_roles`,
`_compute_entity_layout`, `_entity_icon`, `_ordered_entity_fields`,
`APP_JSX_TEMPLATE`) sont supprimés de `generator.py`. `generate_all` ne
produit plus que 3 artefacts d'infrastructure (`schema.sql`, `app.py`,
`sandbox_ai.py`) plus, le cas échéant, `landing.html`.

**Ce que ça implique concrètement :**
- `/` redirige vers `/docs` par défaut (comportement du point 4a, inchangé) ;
  ou sert `landing.html` si un bloc `landing` est présent (point 21).
- La route `/ui` n'existe plus du tout.
- Le CTA par défaut de la landing (`_deterministic_landing_copy`) pointe
  vers `/docs` au lieu de `/ui`.
- `ui NomEntite / theme: ...` reste utile : il influence désormais
  l'identité visuelle de `landing.html` (via `_select_theme`, toujours en
  place). `primary`/`order` sont conservés dans la grammaire pour ne pas
  casser les specs existantes qui les utilisent, mais n'ont plus aucun
  effet sur le rendu — il n'y a plus de rendu de carte à personnaliser.
- Les deux seules sources de front possibles sont désormais : (1) `/docs`
  (Swagger/OpenAPI, gratuit, toujours là) ; (2) `landing.html` (`mode: ai`
  ou `mode: template`, point 21) — l'IA locale et le gabarit importé par
  l'utilisateur sont les SEULES façons d'obtenir un rendu visuel au-delà de
  la documentation d'API brute. Un garde-fou de non-régression
  (`test_no_example_ever_produces_frontend_html` dans
  `tests/test_compile_all.py`) verrouille cette décision.

**Pourquoi ce choix tient debout :** un back-office CRUD généré par
mots-clés (points 15-20) donnait un outil de travail correct mais jamais
un vrai produit fini ; une landing (IA ou importée) répond directement au
besoin réel — donner un visage présentable à l'app — sans le entretenir un
second système de rendu que personne n'utilisait pour autre chose que du
test manuel rapide. `/docs` couvre déjà ce besoin de test manuel.

## 23. Tableau de bord post-connexion (`/app`) et corrections diverses

**Le problème initial :** après connexion sur la landing, rien ne se
passait de concret — au mieux un jeton à copier-coller manuellement dans
`/docs`. Pas "un site moderne".

**Ce qui a changé :**
- **`/app`**, nouvelle page, séparée de `/`. Après connexion, `landing.html`
  stocke le jeton en `sessionStorage` puis navigue réellement vers `/app`
  (vraie URL différente, pas un simple défilement). `dashboard.html` lit ce
  jeton au chargement ; absent → retour immédiat vers `/`. Protection
  d'expérience, pas de sécurité — chaque appel API reste vérifié côté
  serveur comme n'importe quel appel authentifié.
- **`_compute_actor_capabilities`** dérive, depuis les vrais `workflow` de
  la spec, ce que l'acteur connecté peut faire (entités + actions CRUD +
  fonctions `custom` avec leurs entrées). Embarqué en JSON, zéro contenu
  IA. Le tableau de bord se construit dynamiquement à partir de ça.
- **Boutons d'action directement sur chaque ligne** (Modifier/Supprimer,
  pré-remplis avec le bon ID) plutôt que d'exiger de le retaper à la main.
- **Liste toujours rafraîchie automatiquement** (au premier rendu de la
  carte, et après chaque création/modification/suppression) au lieu d'un
  chargement purement manuel.
- **Session expirée détectée proprement** : tout appel authentifié passe
  par `apiFetch`, qui intercepte un 401, efface le jeton, et renvoie vers
  `/?session_expired=1` — la landing affiche alors un message clair au lieu
  d'un échec muet.
- **Menu "Acteur" trié intelligemment** : l'acteur pré-sélectionné à
  l'inscription est celui qui a le droit `Create` sur au moins une entité
  et dont le nom ne contient pas "admin", plutôt qu'un tri alphabétique pur
  qui plaçait souvent "Admin" en premier sans que rien ne le signale.
- **Widget de compte pour le mode `template`** : un gabarit importé est un
  fichier HTML arbitraire, MonLang ne sait pas où il prévoit un formulaire
  de connexion. Un petit widget autonome (styles scopés `monlang-auth`,
  jamais de collision avec les classes du gabarit) est injecté avant
  `</body>` — même comportement que le mode `ai` : vrai `POST /register`
  puis `/login`, redirection vers `/app`.

**Deux bugs préexistants corrigés en cours de route, sans rapport avec ce
qui précède :**
- **Collision avec un mot-clé SQL réservé** : une entité nommée `Order`
  faisait échouer `schema.sql` silencieusement (`ORDER` est un mot-clé
  SQLite). Noms de table ET de colonne systématiquement entre guillemets
  doubles désormais, dans `_generate_sql` et dans toutes les requêtes de
  `_generate_secure_fastapi` — plus fiable que de maintenir une liste de
  mots réservés à jour.
- **Contraintes `FOREIGN KEY` entrelacées avec des colonnes** : masqué par
  le bug précédent (le premier échec empêchait le second de se déclencher).
  Dès qu'une entité a 2 relations ou plus, toutes les colonnes FK sont
  désormais déclarées avant toute contrainte `FOREIGN KEY` — l'ordre que le
  SQL standard exige.

**Méthode de travail sur ce point** : chaque correctif a été prouvé par
exécution réelle (jsdom + serveur relancé + vrais appels), pas par relecture
du code — plusieurs des bugs ci-dessus (l'ordre des `FOREIGN KEY`, le
`scrollIntoView` absent de jsdom masquant un vrai message de succès, le
sur-échappement de backslash entre deux couches de templating Python) ne se
seraient jamais révélés autrement.

## 24. Écosystème de capacités — brique 1 : `capability auth`

**Contexte** : vision à long terme d'un MonLang composé de "capacités"
assemblables (auth, messagerie, paiement, recherche...) plutôt que d'un
unique DSL monolithique. Décision explicite : construire **brique par
brique**, chacune testée avant la suivante, plutôt que de viser d'emblée
plusieurs DSL séparés et un IR multi-cible (React/Flutter/Spring/...) — un
projet d'une tout autre ampleur, à reconsidérer seulement une fois
plusieurs capacités réelles éprouvées.

**Cette brique (la première) est délibérément sans effet** : un bloc
optionnel `capability` (ex. `capability auth`), validé contre une liste
blanche de noms connus (`auth` est la seule pour l'instant — tout autre nom
est rejeté à la compilation, pas ignoré en silence), qui traverse tout le
pipeline (grammaire Lark → `ast_validator.py` → AST normalisé →
`generator.py`, où il est stocké sur `self.capabilities`) sans qu'aucun
générateur ne le consulte encore. L'authentification (register/login/JWT)
reste générée systématiquement, exactement comme avant.

**Objectif** : prouver que le concept de "capacité déclarée dans la spec"
tient dans toute la chaîne, sur un existant qui fonctionne déjà (testé sur
`exemples/10_portfolio_public.yaml`), avant d'en construire une seule qui
change réellement un comportement. Preuve faite par compilation comparée :
`app.py` et `schema.sql` sont strictement identiques, bloc `capability`
présent ou non.

**Prochaines briques prévues** (chacune changera réellement la génération,
contrairement à celle-ci) :
- Masquage de champ à la lecture publique (ex. cacher l'auteur d'un post
  anonyme) — nécessaire pour un cas d'usage "réseau social anonyme".
- Contrôle d'accès à deux parties (`ownedBy` ne couvre qu'un seul
  propriétaire ; une messagerie privée a besoin qu'expéditeur ET
  destinataire y aient accès).

Voir `exemples/10_portfolio_public.yaml` pour l'usage.

## 25. Écosystème de capacités — brique 2 : masquage de champ (`hidden`)

**Cas d'usage déclencheur** : un réseau social anonyme (posts publics, mais
sans aucun profil, photo, ni identifiant d'auteur visible) — voir la
discussion sur la vision d'écosystème. Un champ `author` classique fuiterait
un identifiant stable (le `user_id`) dans chaque réponse `GET /post`,
suffisant pour recouper "quels posts viennent du même compte" même sans
jamais afficher de pseudo.

**Ce qui a changé :** nouvelle règle `rule Entite.champ hidden` (grammaire,
`ast_validator.py`, `generator.py`). Le champ visé doit être un attribut
réellement déclaré sur l'entité (jamais `id`, structurellement nécessaire à
la navigation CRUD — la validation échoue proprement sinon). Une fois
masqué, le champ est retiré de **toutes** les réponses de lecture de son
entité — liste et détail — après construction de la ligne nommée, avant
l'envoi. Il reste en base, et reste utilisable en écriture (`Create`,
`Update`) : masquer n'est pas restreindre l'accès à l'action, c'est
retirer un champ de ce qui est renvoyé.

**Différence de fond avec `restrictedTo`** (point 2) : `restrictedTo`
autorise un acteur précis à voir un champ confidentiel — c'est une
restriction d'accès. `hidden` masque pour tout le monde, y compris les
acteurs authentifiés — c'est de l'anonymisation, pas de la confidentialité.
Les deux répondent à des questions différentes ("qui a le droit de voir
ceci ?" vs. "ce champ ne doit jamais apparaître, point").

**Effet de bord corrigé au passage** : le choix automatique du "champ
d'aperçu" affiché sur la landing (`_compute_landing_functional_context`,
point 21) ignore désormais les champs masqués — un champ retiré des
réponses API n'a évidemment aucun sens comme titre de carte d'aperçu.

**Preuve, testée en conditions réelles** (`exemples/13_anon_forum_demo.yaml`,
serveur relancé, vrais appels) : un post créé avec un champ `author` rempli
est bien stocké, mais `GET /post` et `GET /post/{id}`, tous deux publics
(sans jeton), ne renvoient jamais ce champ.

## 26. Écosystème de capacités — brique 3 : réputation dynamique (`decrements`)

**Cas d'usage déclencheur** : la vision d'un réseau social où la visibilité
n'est plus liée à l'ancienneté ou à un nombre d'abonnés figé, mais à un
score qui baisse quand le comportement est signalé — confirmé par
l'utilisateur : le déclencheur est un signalement (`Report`), rien d'autre
pour cette première version (pas de hausse par "like" — volontairement
laissé à une brique suivante).

**Ce qui a changé :** nouvelle règle `rule Entite.Create decrements
Entite.champ [by N]` (défaut `N = 1`). Validée à trois niveaux :
l'action déclenchante doit être `Create` (seule prise en charge pour
l'instant), le champ ciblé doit être un attribut `Integer`/`Float`
réellement déclaré, et une relation doit exister entre les deux entités
(même vérification que pour `ownedBy`, point 5).

**La vraie difficulté de cette brique, découverte en la construisant** : le
mécanisme existant de clé étrangère peuple automatiquement la colonne avec
l'identité de l'appelant courant (motif « ce Todo m'appartient »). Mais un
signalement cible un membre *choisi par le client* — pas l'auteur du
signalement lui-même. Réutiliser le mécanisme existant aurait décrémenté la
réputation du signaleur, pas de la personne signalée. Corrigé en détectant
ce cas précis : quand la relation entrante d'une entité est la cible d'une
règle `decrements`, sa clé étrangère devient un champ normal du corps de
requête (`member_id: int` dans le schéma Pydantic) plutôt qu'auto-peuplée
par `current_user_id` — les deux motifs ("m'appartient" vs. "je désigne
quelqu'un d'autre") ne peuvent pas partager le même mécanisme.

La décrémentation elle-même s'exécute après le commit de l'insertion (le
signalement reste valablement enregistré même si la cible n'existe plus) :
`UPDATE cible SET champ = champ - N WHERE id = <clé fournie par le client>`.

**Preuve, testée en conditions réelles** (`exemples/14_reputation_demo.yaml`,
serveur relancé, vrais appels) : un membre créé avec `reputation = 100`,
signalé deux fois (`decrements ... by 10`) → `90` puis `80`, vérifié
directement en base après chaque appel.

**Toujours hors de portée, assumé** : l'algorithme de recommandation basé
sur les likes (un moteur de scoring/ML, pas quelque chose qu'un compilateur
déclaratif peut produire — voir aussi point 27).

## 27. Écosystème de capacités — brique 4 : appréciations (`increments`)

**Contexte** : symétrique de `decrements` (point 26) pour la hausse d'un
compteur — cas d'usage typique : un like sur un post fait monter son
compteur d'appréciations. Un essai antérieur de cette brique avait été
**explicitement annulé** dans `src/parser.py` : une seule règle de grammaire
paramétrée par le mot-clé (`"decrements"` ou `"increments"` comme littéral
partagé) aurait fait atteindre le Transformer sans distinction, puisque Lark
filtre les littéraux de chaîne anonymes avant transformation — `increments`
aurait donc été silencieusement étiqueté `decrements`. Retiré plutôt que
laissé à moitié fait (voir aussi le point 21 sur le même piège avec
`restrictedTo`/`sharedBy`).

**Ce qui a changé :** nouvelle règle `rule Entite.Create increments
Entite.champ [by N]` (défaut `N = 1`), en grammaire ET en Transformer via
**deux productions Lark nommées distinctes** (`decrement_rule` et
`increment_rule`) plutôt qu'une seule règle partagée — ce choix élimine
structurellement le piège ci-dessus, puisque chaque production a sa propre
méthode Python qui sait déjà quel type de règle elle construit, sans jamais
avoir besoin d'inspecter un littéral filtré par Lark.

**Généralisation, pas duplication :** `ast_validator.py` traite
`decrements` et `increments` dans la **même boucle de validation** (mêmes
trois conditions : `Create` uniquement, champ `Integer`/`Float` réel,
relation existante) — chaque règle validée porte désormais un champ
`"direction"` (`"decrements"` ou `"increments"`) dans `self.reputation_rules`,
plutôt que deux listes séparées. `generator.py` lit ce champ pour choisir
l'opérateur SQL de la mise à jour post-commit (`+` ou `-`) ; tout le reste du
mécanisme (peuplement de la clé étrangère cible depuis le corps de requête
plutôt que depuis `current_user_id`, exécution après le commit de
l'insertion déclenchante) est strictement partagé entre les deux sens,
puisque la difficulté de fond (« qui la clé étrangère doit-elle
représenter ? ») ne dépend pas du signe de l'effet.

**Preuve, testée en conditions réelles** (`exemples/15_likes_demo.yaml`,
serveur relancé, vrais appels) : un post créé avec `likes = 0`, apprécié
deux fois (`increments ... by 5`) → vérifié directement en base après les
deux appels : `likes = 10`.

**Toujours hors de portée, assumé** : identique au point 26 — l'algorithme
de recommandation basé sur les likes reste un moteur de scoring/ML, pas
quelque chose qu'un compilateur déclaratif peut produire.

## 28. Écosystème de capacités — brique 5 : likes en catégories (`categorized`)

**Cas d'usage déclencheur** : afficher un compteur de likes en catégories
("peu"/"populaire"/"viral") plutôt qu'en nombre exact — décision explicite
de l'utilisateur sur trois points, tranchés avant l'implémentation
(cohérent avec la méthode du projet : fixer la forme exacte d'une règle
avant d'écrire la grammaire, comme pour `decrements` au point 26) :
1. Syntaxe sur une seule ligne, seuils fixes déclarés dans la spec (pas un
   bloc indenté façon `ui`, pas de paliers génériques figés).
2. Le champ numérique brut est **remplacé**, jamais exposé à côté de la
   catégorie — cohérent avec `hidden` qui retire un champ plutôt que d'en
   ajouter un.
3. Portée volontairement générale : n'importe quel champ `Integer`/`Float`
   de n'importe quelle entité, pas seulement les champs déjà ciblés par
   `increments`/`decrements` — utile aussi pour un prix ou un stock, pas
   seulement des likes.

**Ce qui a changé :** nouvelle règle `rule Entite.champ categorized: "label1"
below N1, "label2" below N2, ..., "labelFinal" otherwise`. Chaque palier est
soit `below` (seuil strict, exclusif), soit `otherwise` (palier de secours).
Validée à plusieurs niveaux dans `ast_validator.py` :
- le champ ciblé doit être un attribut `Integer`/`Float` réellement déclaré ;
- incompatible avec `hidden` sur le même champ (l'un retire le champ,
  l'autre le remplace par une valeur dérivée — les deux ne peuvent pas
  s'appliquer en même temps sans que l'un des deux comportements soit
  silencieusement ignoré) ;
- une seule règle `categorized` autorisée par champ ;
- au moins un palier `below` et un palier `otherwise` (minimum 2 paliers) ;
- seul le **dernier** palier peut être `otherwise` — un palier de secours
  ailleurs dans la liste est rejeté à la compilation plutôt que de produire
  un ordre de correspondance ambigu ;
- le dernier palier **doit** être `otherwise` — sans lui, une valeur
  au-delà du dernier seuil n'aurait aucune catégorie ;
- les seuils `below` doivent être strictement croissants (détecte un
  ordre inversé ou dupliqué à la compilation plutôt qu'au runtime).

**Génération :** `generator.py` construit une chaîne `if`/`elif`/`else`
Python directement dans les routes `Read` générées (liste et détail), sur
le même dict de ligne nommé déjà utilisé pour le masquage de champ (`hidden`,
point 25) — une seule passe par ligne pour les deux transformations. Les
libellés utilisateur sont injectés via `repr()` plutôt qu'une interpolation
manuelle entre guillemets, pour rester un littéral Python valide quel que
soit leur contenu (apostrophe, antislash...) — la validation garantit par
ailleurs que la chaîne `if`/`elif`/`else` générée est toujours syntaxiquement
correcte et couvre nécessairement toute valeur possible du champ, grâce au
palier `otherwise` obligatoire en dernière position.

**Preuve, testée en conditions réelles** (`exemples/16_likes_categories_demo.yaml`,
combinant `increments` du point 27 et `categorized`, serveur relancé, vrais
appels) : un post à 0 like → `"likes_category": "peu"` ; après 2 likes à +5
(10 bruts) → `"populaire"` ; après 18 likes de plus (100 bruts) → `"viral"` —
sur la route détail ET la route liste, le champ `likes` brut n'apparaissant
jamais dans aucune réponse. Chemin d'erreur également vérifié : un
`otherwise` placé avant le dernier palier est rejeté à la compilation avec
un message clair.

