# monl — Choix de conception assumés

> **Note (0.9.0-beta.2).** Certains points ci-dessous décrivent des fonctions
> d'IA locale (Ollama) depuis retirées : réponses libres au dialogue (`--nl`),
> traduction d'une description en spec (`--prompt`), et remplissage des blocs
> `custom`. Le compilateur est désormais entièrement déterministe ; ces
> passages sont conservés comme historique de conception. Voir `CHANGELOG.md`.

Ce document répertorie les règles strictes et opinionées du compilateur — ce
qu'elles interdisent, pourquoi ce choix a été fait, et comment le contourner
quand le besoin est légitime. Objectif : servir à la fois de documentation
pour qui écrit une spec monl, et de mémoire pour le mainteneur du projet.

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
[20](#20-unicité-visuelle-par-projet-graine-monl_theme_seed) Unicité visuelle par projet ·
[22](#22-suppression-du-back-office-ui--monl-ne-génère-plus-de-front-crud) Suppression du back-office `/ui` ·
[23](#23-tableau-de-bord-post-connexion-app-et-corrections-diverses) Tableau de bord post-connexion (`/app`) ·
[24](#24-écosystème-de-capacités--brique-1--capability-auth) Écosystème de capacités (brique 1) ·
[25](#25-écosystème-de-capacités--brique-2--masquage-de-champ-hidden) Masquage de champ (brique 2) ·
[26](#26-écosystème-de-capacités--brique-3--réputation-dynamique-decrements) Réputation dynamique (brique 3) ·
[27](#27-écosystème-de-capacités--brique-4--appréciations-increments) Appréciations (brique 4) ·
[28](#28-écosystème-de-capacités--brique-5--likes-en-catégories-categorized) Likes en catégories (brique 5) ·
[29](#29-écosystème-de-capacités--assemblage-final-réseau-social-anonyme) Assemblage final (réseau social anonyme) ·
[30](#30-écosystème-de-capacités--pseudonyme-anonyme-généré-generated) Pseudonyme anonyme généré (`generated`) ·
[31](#31-écosystème-de-capacités--accès-à-deux-parties-accessibleby) Accès à deux parties (`accessibleBy`) ·
[32](#32-migrations-de-schéma-sans-perte-de-données) Migrations de schéma sans perte de données ·
[33](#33-rate-limiting-persistant-multi-workers) Rate limiting persistant multi-workers ·
[34](#34-enrichissement-du-mode-template-état-de-connexion) Enrichissement du mode template ·
[35](#35-frontend--archétypes-dinterface-dérivés-de-la-spec) Frontend : archétypes d'interface dérivés de la spec ·
[36](#36-données-de-démonstration-seed--des-sites-complets) Données de démonstration (`seed`) ·
[37](#37-frontend--images-robustes-librairies-cdn-et-ton-vitrine) Frontend : images robustes, librairies CDN et ton vitrine ·
[38](#38-espace-connecté-interactif--fil-social-façon-twitter) Espace connecté interactif (fil social Twitter-like) ·
[39](#39-frontend--sections-éditoriales-et-dashboards-lisibles) Sections éditoriales et dashboards lisibles ·
[40](#40-pivot--monl-orchestrateur-dialogue-guidé-contrat-frontend-runupdate) Pivot : monl orchestrateur ·
[41](#41-le-pivot-mené-à-terme--boucle-fermée-et-suppression-du-frontend-généré) Pivot mené à terme (boucle fermée, frontend généré supprimé) ·
[42](#42-monl-import--la-voie-sans-clé-api-abonnement-claudeai) `monl import` : la voie sans clé API ·
[43](#43-claude-code--le-travail-directement-dans-le-dossier-cible) Claude Code : le travail directement dans le dossier cible ·
[44](#44-modèle-local-pour-comprendre-lutilisateur--linterprète-pas-le-rédacteur) Modèle local : l'interprète, pas le rédacteur ·
[45](#45-le-dialogue-ouvre-sur-un-catalogue-de-10-modèles-dapplications) Le dialogue ouvre sur un catalogue de 10 modèles ·
[46](#46-la-démonstration-complète-ateliervélo-et-ce-quelle-prouve) La démonstration complète (AtelierVélo)

**Bêta 3 et suite** — attention, la numérotation repart à 45 : les numéros 45
et 46 désignent chacun DEUX points distincts (séquelle d'une fusion, laissée
en l'état car de nombreux renvois internes s'y appuient) ·
[45](#45-le-rôle-ne-peut-pas-être-choisi-par-celui-qui-sinscrit-bêta-3) Le rôle n'est pas choisi par celui qui s'inscrit ·
[46](#46-le-déterminisme-doit-être-testé-entre-processus-bêta-3) Le déterminisme se teste entre processus ·
[47](#47-découper-le-générateur-avant-de-le-réécrire-bêta-3) Découper le générateur avant de le réécrire ·
[48](#48-une-clause-de-contrat-que-rien-ne-vérifie-nest-pas-une-clause-bêta-3) Une clause que rien ne vérifie n'est pas une clause ·
[49](#49-le-dialogue-montre-son-parcours-avant-de-le-faire-subir-bêta-3) Le dialogue montre son parcours ·
[50](#50-une-règle-de-propriété-qui-ne-couvre-pas-la-lecture-nen-est-pas-une-bêta-3) Une règle de propriété doit couvrir la lecture ·
[51](#51-un-contrat-qui-dicte-un-port-en-dur-punit-lia-qui-lui-obéit) Un contrat qui dicte un port en dur punit l'IA qui lui obéit ·
[52](#52-proposer-une-police-que-le-même-contrat-interdit-de-charger) Proposer une police que le même contrat interdit de charger ·
[53](#53-le-dialogue-interrogeait-la-structure-jamais-lintention) Le dialogue interrogeait la structure, jamais l'intention ·
[54](#54-le-pivot-a-supprimé-une-intelligence-au-lieu-de-la-déplacer) Le pivot a supprimé une intelligence au lieu de la déplacer ·
[55](#55-monl-modélisait-des-données-un-site-est-surtout-du-contenu) monl modélisait des données, un site est surtout du contenu ·
[56](#56-cinq-couleurs-plates-ne-font-pas-une-palette) Cinq couleurs plates ne font pas une palette ·
[57](#57-un-contrat-qui-décrit-mal-le-corps-est-pire-quun-contrat-muet) Un contrat qui décrit mal le corps est pire qu'un contrat muet ·
[58](#58-rendre-la-main--sans-épinglage-le-visuel-appartient-à-lia) Rendre la main : sans épinglage, le visuel appartient à l'IA

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
`exemples/06_moderation_shared.ml` pour un exemple complet.

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
`_monl_users`. À la connexion (`POST /login`), ce `user_id` est porté par
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
`exemples/09_owned_and_shared.ml`.

**Limite de conception qui demeure :** le registre d'utilisateurs (point 7)
n'a pas de vérification d'email ni de récupération de compte — un mot de
passe oublié est définitivement perdu dans ce prototype. Voir
`exemples/07_ownership_demo.ml` pour un exemple complet d'`ownedBy` seul.

**Effet de bord positif (gap corrigé au passage) :** avant cet ajout, les
colonnes de clé étrangère générées dans `schema.sql` pour les relations
`hasMany` n'étaient en réalité jamais renseignées par les routes `Create` —
elles restaient `NULL` pour tout enregistrement créé, rendant les relations
inertes au runtime malgré leur présence dans le schéma. Elles sont
désormais peuplées automatiquement pour toute entité ayant une relation
entrante, qu'une règle `ownedBy` soit déclarée ou non.

---

## 6. Collision de privilèges (`CRITICAL_COLLISION`)

*(Numéro réservé : doublon historique du point [1](#1-collision-de-privilèges-critical_collision),
créé par erreur lors d'une réorganisation du document. Le contenu vit au
point 1. Ce titre est conservé volontairement pour ne pas décaler la
numérotation des points 7 à 30, référencée un peu partout — README,
CLAUDE.md, commentaires du code.)*

---

## 7. Registre d'utilisateurs réel (`/register`, `/login`)

**Ce qui a changé :** l'application générée possède désormais une vraie
table `_monl_users` (créée automatiquement, indépendamment de la spec),
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

Voir `exemples/08_relations_demo.ml` pour un exemple des 3 types.

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
les applications générées par monl**. Un token forgé avec cette clé pour
une application était donc valide sur n'importe quelle autre application
issue du même compilateur — et puisque le code source de monl est
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
(`_monl_revoked_tokens`) — toute présentation ultérieure de ce token est
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
correspondante — ni token JWT, ni contrôle de rôle. Jusqu'ici, monl
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

Voir `exemples/10_portfolio_public.ml` pour un exemple complet (projets
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

Voir `exemples/10_portfolio_public.ml` (thème `editorial` forcé, ordre des
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

## 20. Unicité visuelle par projet (graine `.monl_theme_seed`)

**Le problème :** le thème (point 15) est choisi par mots-clés du domaine
avant tout hachage — deux projets de même domaine (deux todo-lists, par
exemple) obtenaient donc systématiquement le même thème ET le même
agencement, quel que soit le nom de l'app.

**Ce qui a changé :** une graine aléatoire de 16 octets est générée une
seule fois par projet, à la première compilation, et conservée dans
`.monl_theme_seed` (jamais commitée — même logique que `.jwt_secret`,
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
  `data-monl="clé"` (texte) ou `data-monl-href="clé"` (attribut
  href/src), pour un jeu de clés réservées connues
  (`app_name`, `headline`, `subheadline`, `cta_label`, `cta_target`,
  `feature_1/2/3`). Aucun appel IA dans ce mode ; tout reste déterministe.
  Voir `templates/signal.html` pour un exemple, et
  `exemples/12_landing_template_demo.ml` pour son usage.

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

Voir `exemples/11_landing_ai_demo.ml` (mode `ai`) et
`exemples/12_landing_template_demo.ml` (mode `template`).

## 22. Suppression du back-office `/ui` — monl ne génère plus de front CRUD

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
  fichier HTML arbitraire, monl ne sait pas où il prévoit un formulaire
  de connexion. Un petit widget autonome (styles scopés `monl-auth`,
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

**Contexte** : vision à long terme d'un monl composé de "capacités"
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
`exemples/10_portfolio_public.ml`), avant d'en construire une seule qui
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

Voir `exemples/10_portfolio_public.ml` pour l'usage.

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

**Preuve, testée en conditions réelles** (`exemples/13_anon_forum_demo.ml`,
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

**Preuve, testée en conditions réelles** (`exemples/14_reputation_demo.ml`,
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

**Preuve, testée en conditions réelles** (`exemples/15_likes_demo.ml`,
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

**Preuve, testée en conditions réelles** (`exemples/16_likes_categories_demo.ml`,
combinant `increments` du point 27 et `categorized`, serveur relancé, vrais
appels) : un post à 0 like → `"likes_category": "peu"` ; après 2 likes à +5
(10 bruts) → `"populaire"` ; après 18 likes de plus (100 bruts) → `"viral"` —
sur la route détail ET la route liste, le champ `likes` brut n'apparaissant
jamais dans aucune réponse. Chemin d'erreur également vérifié : un
`otherwise` placé avant le dernier palier est rejeté à la compilation avec
un message clair.

## 29. Écosystème de capacités — assemblage final (réseau social anonyme)

**Objectif** : combiner toutes les briques (1 à 5) dans une seule spec
cohérente — le banc d'essai annoncé depuis le début de la vision produit
(voir points 24-28) — pour prouver qu'elles composent sans interférer entre
elles, pas seulement isolément. Voir `exemples/17_anon_social_network.ml`.

**Composition retenue**, chaque brique dans son rôle le plus naturel plutôt
que toutes empilées sur la même entité :
- `capability auth` (brique 1) déclarée explicitement.
- `Post` : lecture publique (`public`, point 16), auteur remplacé par un
  pseudonyme anonyme stable généré côté serveur (`generated`, point 30 —
  voir mise à jour ci-dessous). Ses `likes` sont catégorisés
  (`categorized`, brique 5).
- `Like.Create increments Post.likes` (brique 4) fait monter le compteur
  catégorisé ci-dessus.
- `Report.Create decrements Member.reputation` (brique 3) fait baisser la
  réputation du membre ciblé.
- `Comment` : lecture publique, mais `Update`/`Delete` restreints au
  propriétaire réel (`ownedBy`, point 5) via une vraie relation
  `Member hasMany Comment` — contrairement à `Post`, ses commentaires ne
  sont pas anonymes, seulement modifiables par leur auteur.

**Mise à jour (voir point 30)** : à l'origine, `Post.author` utilisait
`hidden` (masqué entièrement, champ rempli à la main par le client, sans
garantie d'intégrité). Remplacé depuis par `rule Post.author generated`
dès que la brique correspondante a existé — `hidden` avait justement pour
limite de ne pouvoir cibler qu'un attribut *déclaré* de l'entité, jamais
la colonne de clé étrangère qu'une relation ajoute automatiquement, ce qui
aurait empêché de combiner anonymat ET propriété réelle (`ownedBy`) sur
`Post` ; `generated` contourne le problème autrement, en ne s'appuyant sur
aucune relation/FK du tout (juste le pseudonyme de compte porté par le
JWT). `Comment` reste volontairement identifié (`ownedBy`, pas anonyme),
par choix de composition et non par contrainte technique.

**Bug réel découvert en assemblant cette spec (pas par relecture)** : une
ligne de commentaire seule entre deux blocs de premier niveau (ex. un
commentaire au-dessus d'une règle, sur sa propre ligne) faisait planter la
compilation avec `TypeError: argument of type 'Tree' is not a container or
iterable`. Cause : le terminal `_NL` (fin de ligne) ne fusionne que des
retours à la ligne *contigus* ; un commentaire entre deux d'entre eux casse
cette contiguïté et produit un second token `_NL` isolé, qui matche alors
l'alternative `_NL` de `?block` sans qu'aucune méthode du Transformer ne le
traite -- Lark n'inline pas ce nœud vide (0 enfant, la règle `?block`
n'inline que les nœuds à exactement 1 enfant) et laisse passer un
`Tree('block', [])` brut. Jamais rencontré avant, car aucun des 16 exemples
précédents n'utilisait de commentaire sur sa propre ligne. Un premier
correctif défensif (`isinstance(b, dict)` dans `MonlTransformer.app()`)
a d'abord traité le symptôme au niveau racine seulement.

**Chantier repris et résolu à la racine** : un commentaire seul À
L'INTÉRIEUR d'un bloc indenté (entre deux attributs d'`entity`, ou deux
actions d'un `workflow`) faisait, lui, carrément échouer le parsing
(`UnexpectedToken`) -- `attribute+`/`action+` (et les productions
équivalentes de `custom_block`/`ui_block`/`landing_block`) n'ont aucune
alternative pour absorber un `_NL` isolé, contrairement à `?block`. Plutôt
que corriger 5 règles de grammaire séparément (une par bloc indenté,
chacune à valider indépendamment, avec le risque de perturber l'indenteur
sur chacune), le correctif retenu agit en amont du lexer, dans
`parse_monl_string()` (`src/parser.py`) : toute ligne qui n'est QUE du
commentaire (rien d'autre que des espaces avant `#`) est retirée du texte
source via une regex (`_strip_standalone_comment_lines`) avant même que
Lark ne le voie -- la ligne disparaît complètement, comme si elle n'avait
jamais existé, ce qui restaure la contiguïté du run de retours à la ligne
qui l'entourait, PARTOUT (racine ET blocs indentés), en un seul endroit.
Les commentaires en fin de ligne réelle (ex. `entity Post  # note`) ne sont
pas concernés par cette regex (du contenu non-blanc précède le `#`) et
restent gérés par `%ignore COMMENT` comme avant. Le correctif défensif
`isinstance(b, dict)` dans `app()` reste en place (inoffensif, coûte rien),
mais n'est plus strictement nécessaire pour ce cas précis.

**Preuve, testée en conditions réelles** (serveur relancé, vrais appels,
revérifié après le passage à `generated`) : deux comptes (`alice`, `bob`)
enregistrés ; une tentative d'alice d'imposer `"author": "FAKE"` dans le
corps de sa requête `POST /post` est ignorée, ses deux posts affichent le
même pseudonyme stable (`Anon#6484`), celui de bob est différent
(`Anon#3155`), lisibles SANS jeton ; les `likes` s'affichent toujours en
catégorie (`"likes_category"`, jamais le nombre brut) ; un signalement de
bob fait passer la réputation d'alice de 100 à 90 (vérifié directement en
base) ; bob peut modifier son propre commentaire, alice reçoit un `403` en
tentant de modifier celui de bob.

## 30. Écosystème de capacités — pseudonyme anonyme généré (`generated`)

**Cas d'usage déclencheur** : le point 29 notait que `Post.author`, dans
l'assemblage final, reste un `String` libre rempli à la main par le
client — rien ne garantit son intégrité (n'importe quel texte, y compris
vide, y compris usurper le style d'un autre pseudonyme). Trois décisions
tranchées avec l'utilisateur avant l'implémentation :
1. **Stabilité** : le pseudonyme est généré **une seule fois par compte**,
   à `/register` (ex. `Anon#3821`), et reste identique sur tous les
   enregistrements créés ensuite par ce compte — pas un nouveau pseudonyme
   à chaque création (ce qui aurait empêché de reconnaître "ces posts
   viennent du même auteur", contraire à l'esprit d'un réseau social), ni
   un identifiant stable de bout en bout entre toutes les entités (deux
   entités différentes utilisant chacune leur propre règle `generated`
   partagent quand même le MÊME pseudonyme de compte, un compromis
   volontairement simple pour cette première version).
2. **Syntaxe** : nouvelle règle `rule Entite.champ generated`, sur le même
   principe qu'une ligne que `hidden`/`categorized`.
3. **Entrée client** : le champ est retiré du schéma Pydantic de la route
   `Create` — le client ne peut même pas tenter de le fournir (même
   traitement que la colonne de clé étrangère peuplée par `ownedBy`).

**Ce qui a changé :** `_monl_users` gagne une colonne `anon_handle`
(contrainte `UNIQUE`, généré à `/register` sous la forme `Anon#` + 4
chiffres aléatoires, avec jusqu'à 10 tentatives en cas de collision plutôt
qu'un échec d'inscription pour une coïncidence statistiquement rare). Porté
par le JWT depuis `/login` (comme `actor`/`user_id`), donc disponible sans
requête DB supplémentaire via une nouvelle dépendance
`get_current_anon_handle`. Le générateur retire le champ ciblé du schéma
Pydantic (avec un filet `pass` si l'entité n'a alors plus aucun champ) et
peuple la colonne, à l'insertion, depuis ce pseudonyme plutôt que depuis
`data.<champ>`.

**Validation dans `ast_validator.py` :**
- le champ ciblé doit être un attribut `String` réellement déclaré (un
  pseudonyme est toujours du texte court, jamais un nombre/booléen/date) ;
- incompatible avec `hidden` sur le même champ (`generated` produit déjà
  une valeur sûre à afficher — la masquer en plus n'a pas de sens, ce
  serait alors juste ne pas déclarer le champ du tout) ;
- une seule règle `generated` autorisée par champ ;
- incompatible avec une action `Create` `public` sur la même entité :
  `generated` dérive le pseudonyme de l'appelant authentifié, qu'une route
  publique n'a par définition pas.

**Preuve, testée en conditions réelles** (`exemples/18_generated_pseudonym_demo.ml`,
serveur relancé, vrais appels) : alice tente d'imposer
`"author": "JE_SUIS_QUELQUUN_D_AUTRE"` dans le corps de sa requête — ignoré
silencieusement (absent du schéma) ; ses deux posts affichent le même
pseudonyme (`Anon#3143`, vérifié aussi directement dans
`_monl_users`) ; le post de bob affiche un pseudonyme différent
(`Anon#9658`). Chemins d'erreur également vérifiés : `generated` + `hidden`
sur le même champ, et `generated` + `Create public` sur la même entité,
tous deux rejetés à la compilation avec un message clair.

---

## 31. Écosystème de capacités — accès à deux parties (`accessibleBy`)

**Le problème :** `ownedBy` (point 5) ne connaît qu'UN propriétaire par
enregistrement — celui désigné par la colonne de clé étrangère de la
relation. Une messagerie privée casse ce modèle : l'expéditeur ET le
destinataire doivent pouvoir lire (et supprimer) le même message, mais
personne d'autre — pas même un autre utilisateur du même rôle. Cette brique
était identifiée dès la brique 1 (« contrôle d'accès à deux parties »)
et restée non cadrée jusqu'ici.

**Ce qu'elle fait :**
```
rule Message.Read accessibleBy user_id, recipient_id
rule Message.Delete accessibleBy user_id, recipient_id
```
liste les COLONNES de l'entité qui contiennent chacune l'identifiant d'un
utilisateur autorisé sur l'enregistrement. Sur la route générée :
- **Read (liste)** : `WHERE col1 = ? OR col2 = ?` — l'appelant ne voit que
  les enregistrements dont il est une partie ; le `total` paginé est
  calculé sur le même filtre.
- **Read (détail)**, **Update**, **Delete** : 404 si l'enregistrement
  n'existe pas, 403 si l'identifiant JWT de l'appelant n'apparaît dans
  aucune des colonnes listées.

**Règles strictes du compilateur :**
- Au moins **deux colonnes distinctes** (imposé par la grammaire ET validé) :
  avec une seule partie, `ownedBy` est l'outil adapté.
- Chaque colonne doit être soit un champ `Integer` déclaré de l'entité
  (ex. `recipient_id`), soit la colonne de clé étrangère dérivée d'une
  relation entrante (ex. `user_id` via `User hasMany Message` — auto-peuplée
  à la création, même mécanisme que pour `ownedBy`, point 5).
- Actions autorisées : `Read`, `Update`, `Delete` uniquement (`Create` n'a
  pas encore d'enregistrement dont vérifier les parties ; c'est justement
  la création qui les fixe).
- **Conflit bloquant** avec `ownedBy` sur la même action (`accessibleBy`
  généralise `ownedBy` : choisir l'un des deux).
- Comme pour `ownedBy`, `public` l'emporte si les deux sont déclarés sur la
  même action (une route publique n'a pas d'identité appelante).

**Différence assumée avec `ownedBy` :** le contrôle s'applique à TOUS les
acteurs de la route, pas seulement à un rôle désigné — les parties sont des
colonnes de données, pas des rôles. La combinaison avec un rôle superviseur
via `sharedBy` (un modérateur qui lirait tous les messages) n'est PAS
couverte par cette première version ; à cadrer si le besoin se présente.

**Preuve, testée en conditions réelles** (`exemples/19_private_messages.ml`,
`tests/test_access_parties.py` — serveur uvicorn éphémère compilé via
`--output` dans un dossier temporaire) : Alice envoie un message à Bob ;
Alice et Bob le voient chacun dans leur liste (`total: 1`) et y accèdent
par ID ; Carol — même rôle `User`, jeton valide — a une liste vide
(`total: 0`), reçoit 403 sur l'accès direct et 403 sur la suppression ;
Bob (destinataire, pas expéditeur) peut le supprimer. Les cas d'erreur de
compilation (colonne inconnue, type non-Integer, action `Create`, parties
identiques, conflit `ownedBy`) sont chacun couverts par un test dédié.

---

## 32. Migrations de schéma sans perte de données

**Le problème :** `schema.sql` crée les tables en `CREATE TABLE IF NOT
EXISTS`, ce qui préserve bien les données d'une base existante mais ne
répercute AUCUNE évolution de la spec : ajouter un champ à une entité
laissait la table inchangée, le champ n'apparaissait jamais. La seule
« migration » possible était de supprimer `app.db` — donc de tout perdre.

**Ce qui est fait :** au démarrage, après l'exécution de `schema.sql`,
`init_db()` compare pour chaque table les colonnes réelles
(`PRAGMA table_info`) aux colonnes attendues par la spec courante
(constante `_EXPECTED_COLUMNS` figée dans `app.py` à la compilation, injectée
via `repr()` pour un littéral toujours valide), et applique les
`ALTER TABLE ADD COLUMN` manquants. C'est **purement additif** : aucune
donnée n'est lue, déplacée ou supprimée ; les lignes existantes reçoivent
`NULL` sur les nouvelles colonnes.

**Ce qui n'est volontairement PAS fait :** suppression de colonne (SQLite
n'a pas de `DROP COLUMN` sans reconstruction, et ce serait destructif),
changement de type, renommage. Tous ces cas peuvent détruire des données ;
ils restent des interventions manuelles. Détail complet dans
`docs/MIGRATIONS.md`.

**Bug corrigé au passage (révélé par l'exécution) :** `ADD COLUMN` place les
nouvelles colonnes en fin de table. Or les routes Read reconstruisaient
l'ordre des colonnes de façon *supposée* (`id`, attributs, puis FK), ce qui,
après migration, décalait tout le mapping `dict(zip(...))` — une FK
`user_id` revenait à `None`, un champ prenait la valeur d'un autre. Corrigé
en dérivant les noms de colonnes de `cursor.description` (l'ordre réel que
SQLite renvoie pour `SELECT *`), robuste à toute migration.

**Preuve, testée en conditions réelles** (`tests/test_migrations.py`) : une
spec v1 crée une note ; après recompilation d'une spec v2 (deux champs
ajoutés à `Note` + une nouvelle entité `Tag`) dans le même dossier avec
`app.db` conservée, la note v1 se relit correctement alignée (`title`
intact, `user_id` correct, `body`/`priority` à `null`), et les nouveaux
champs acceptent des écritures.

---

## 33. Rate limiting persistant multi-workers

**Le problème :** la limitation de débit sur `/register` et `/login` (5
tentatives / 60 s / IP) reposait sur un dictionnaire en mémoire de
processus (`_RATE_LIMIT_ATTEMPTS`). Sous plusieurs workers uvicorn/gunicorn
— configuration de déploiement normale — chaque worker avait son propre
compteur : un attaquant réparti sur N workers obtenait N fois le quota. La
révocation de token, elle, était déjà persistée en base (table
`_monl_revoked_tokens`), donc correcte en multi-workers ; seul le rate
limiting posait problème.

**Ce qui est fait :** chaque tentative est enregistrée dans une table
`_monl_rate_limit` (bucket, IP, instant), partagée par tous les workers.
`_check_rate_limit` purge les entrées hors fenêtre, compte les tentatives
récentes de l'IP pour le bucket, bloque en 429 au-delà du seuil, puis
enregistre la tentative courante. Un index `(bucket, client_ip,
attempted_at)` accélère la fenêtre glissante.

**Preuve, testée en conditions réelles** (`tests/test_rate_limit_shared.py`,
serveur lancé avec `--workers 2`) : sur 7 tentatives de login erronées, les
5 premières passent (401), la 6e et la 7e sont bloquées (429) — le quota est
bien global, alors que l'ancien compteur en mémoire en aurait autorisé 10.

---

## 34. Enrichissement du mode template (état de connexion)

**Le problème :** le widget de compte injecté dans une landing en mode
`template` (point 22) ne gérait que la première connexion — il reproposait
toujours le formulaire d'inscription, même pour un visiteur déjà connecté,
sans aucun accès direct à son espace ni moyen de se déconnecter.

**Ce qui est fait :** le widget reflète désormais l'état de connexion. Au
chargement (et à chaque ouverture du panneau), il vérifie la présence d'un
jeton en `sessionStorage` :
- **sans jeton** : le bouton affiche « Se connecter » et le formulaire
  inscription/connexion (comportement d'origine) ;
- **avec jeton** : le bouton affiche « Mon compte », le formulaire est
  masqué au profit d'un accès direct « Accéder à mon espace » (`/app`) et
  d'un bouton « Se déconnecter » qui appelle réellement `/logout` (révoque
  le jeton côté serveur, voir point sur la révocation) puis nettoie le
  stockage local.

Les styles restent scopés sous `monl-auth` pour ne pas entrer en
collision avec le gabarit importé.

**Preuve** : bascule connecté/déconnecté validée via jsdom en développement
(toggle « Se connecter » ↔ « Mon compte », formulaire masqué quand un jeton
est présent) ; présence déterministe des composants (état connecté, lien
`/app`, bouton `/logout`, logique `refreshAuthState`) vérifiée en CI par
`tests/test_template_widget.py`, sans dépendance Node.

---

## 35. Frontend : archétypes d'interface dérivés de la spec

**Le point de départ :** le front généré était visuellement varié (5 thèmes
dérivés du domaine, variation fine par projet) mais structurellement
uniforme — une seule *disposition*. L'aperçu public d'une entité en lecture
libre se réduisait à une grille de simples titres. Une vitrine (portfolio,
catalogue) méritait une forme d'interface propre.

**Le principe, fidèle à la philosophie :** introduire des *archétypes*
d'interface **dérivés de la spec**, comme les thèmes le sont du vocabulaire —
jamais une information visuelle dans le DSL métier, choix 100% automatique
et déterministe. Premier archétype livré : la galerie/portfolio.

**Dérivation (100% auto, `_compute_gallery_plan`) :** pour une entité en
lecture publique, le rôle de chaque champ est déduit de son nom et de son
type — champ-titre (premier String), champ-média (nom évoquant une
image/URL : image, photo, cover, url, avatar…), champ-description (premier
Text), puis jusqu'à 3 champs-méta. Les champs `hidden` (point 2) ne sont
JAMAIS exposés. Si l'entité n'a pas au moins un titre ET (un média OU une
description), la galerie n'apporterait rien de plus que la grille simple :
on garde alors cette dernière (repli automatique).

**Rendu riche déterministe (CSS/JS vanilla, aux couleurs du thème) :**
cartes en grille responsive, apparition en cascade (délai croissant par
carte), skeletons animés pendant le chargement (`aria-busy`), effet de
survol, média en image de fond ou initiale du titre en repli, étiquettes
méta, et une lightbox (expansion au clic, fermeture Échap/clic extérieur).
Les animations respectent `prefers-reduced-motion`.

**Preuve** : le plan est vérifié en CI (`tests/test_gallery_archetype.py` :
dérivation correcte, repli sur grille simple pour une entité trop pauvre,
exclusion stricte des champs `hidden`) ; le rendu complet (3 cartes, média
vs initiale de repli, cascade 0/70/140 ms, étiquettes, lightbox au bon
titre) est validé via jsdom en développement sur
`exemples/10_portfolio_public.ml`.

**Deux archétypes supplémentaires livrés, même modèle :**

- **Boutique / e-commerce** (`_compute_shop_plan`) : déclenché quand une
  entité publique porte un champ `Money` (prix). Rendu : cartes produit,
  prix mis en avant (formaté en euros), badge de disponibilité dérivé du
  stock (« En stock » / « Plus que N » / « Épuisé »), bouton d'achat
  désactivé si épuisé. Prioritaire sur la galerie (le prix est un signal
  plus spécifique). Preuve : `exemples/20_ecommerce_vitrine.ml`, rendu
  validé via jsdom (3 produits, badges in/low/out, bouton désactivé sur
  l'épuisé, prix `1 200,00 €`).

- **Fil social / réseau** (`_compute_feed_plan`) : déclenché quand une
  entité publique a un champ de contenu (`Text`, ou `String` nommé
  content/message/body…) ET un signal social (champ auteur, champ
  `generated` d'auteur anonyme, ou règle `increments`/`categorized`). Rendu :
  fil vertical de posts, avatar-initiale, pseudonyme (anonyme si `generated`),
  contenu, compteur de likes — affiché en catégories quand une règle
  `categorized` s'applique. Détail subtil résolu : un compteur catégorisé
  est renvoyé par l'API sous `<champ>_category` (voir point de la brique 5),
  donc le plan expose cette clé JSON réelle (`counter_key`), pas le nom brut.
  Preuve : `exemples/17_anon_social_network.ml`, rendu validé via jsdom
  (auteurs anonymes, avatars, likes « peu »/« populaire »/« viral »).

**Deux derniers archétypes livrés, même modèle :**

- **Kanban / tableau** (`_compute_kanban_plan`) : déclenché quand une entité
  publique porte un champ de statut (nom évoquant status/état/phase/étape…).
  Rendu : tableau à colonnes, une colonne par valeur de statut — les
  colonnes sont **découvertes à l'exécution** depuis les données (le DSL ne
  déclare aucune énumération de statuts), avec compteur par colonne et
  cartes titre/description/méta. Preuve : `exemples/21_kanban_board.ml`,
  rendu validé via jsdom (3 colonnes À faire/En cours/Terminé, compteurs
  corrects, 5 cartes réparties).

- **Liste classée** (`_compute_ranked_plan`) : déclenchée quand une entité
  publique porte un compteur — champ ciblé par `increments`/`decrements`,
  champ `categorized`, ou Integer au nom évocateur (score, votes, points…).
  Rendu : liste triée par ordre décroissant, rang affiché, podium coloré
  pour le top 3 ; un compteur catégorisé est trié selon l'ordre des
  catégories. Preuve : `exemples/22_ranked_list.ml`, rendu validé via jsdom
  (tri Beta 87 → Delta 3, rangs corrects).

**Sélection (`_compute_archetype`)** : un seul archétype est retenu par
entité publique, par ordre de spécificité — boutique (prix) > kanban
(statut) > fil (contenu + auteur/date) > liste classée (compteur) > galerie
(vitrine visuelle) > grille simple. Déterministe, 100% dérivé de la spec.

**Départage feed vs classement (arbitrage de conception) :** une entité
« titre + compteur + description » ressemble structurellement à un fil
social. Le signal distinctif retenu : le fil exige un **auteur** (champ
auteur ou pseudonyme `generated`) ou un **flux temporel** (champ date) ; un
compteur sans auteur ni date est un classement. Ce raffinement (testé)
évite que le feed capte les entités de classement.

Les 6 archétypes (grille simple, galerie, boutique, kanban, fil, liste
classée) couvrent l'essentiel des familles d'applications générables. La
suite éventuelle relèverait de variantes plutôt que de nouvelles familles.

---

## 36. Données de démonstration (`seed`) : des sites complets

**Le problème (retour utilisateur) :** les sites générés paraissaient vides.
La cause : une application data-driven sans données affiche des sections
vides (« Chargé depuis GET /project »… mais zéro projet en base). Le
squelette était là, le contenu manquait — et rien, dans la spec, ne
permettait de fournir des données.

**Ce qui est fait :** un bloc `seed NomEntité` déclare des enregistrements de
démonstration (une ligne = un enregistrement, paires `champ: valeur`,
chaînes ou nombres). Ils sont insérés au démarrage par `init_db()` **si la
table est vide** — idempotent : un redémarrage n'empile pas de doublons, et
des données réelles créées via l'API ne sont jamais écrasées. Le bloc est
validé à la compilation (entité et champs existants, types cohérents), comme
le reste du langage. Détail complet : `docs/SEED.md`.

**Images sans hébergement :** les seeds utilisent des URLs publiques stables
(picsum.photos, clé fixe → image reproductible), chargées côté navigateur.
Aucune image n'est téléchargée ni stockée par le compilateur.

**Champs `generated` :** un pseudonyme anonyme d'auteur (`generated`) est
normalement assigné par le serveur, pas fourni dans le seed. Le compilateur
lui donne une valeur synthétique stable (`Anon#1000`…) pour que les
enregistrements de démo soient complets (fil social anonyme cohérent).

**Consolidation des exemples (retour utilisateur) :** les 22 exemples
disparates — souvent une seule fonctionnalité chacun, sans landing ni
données — sont remplacés par **5 sites complets**, chacun avec bloc `landing`
et données de démonstration : `01_portfolio` (galerie de 6 projets),
`02_boutique` (catalogue de 6 produits), `03_reseau_social` (fusionne
anonymat + likes catégorisés + réputation + messages privés + commentaires),
`04_kanban` (7 tâches sur 3 colonnes), `05_classement` (6 entrées triées).

**Preuve, testée en conditions réelles** (`tests/test_seed.py` + lancement
des 5 exemples) : chaque site démarre peuplé sans aucune création manuelle
(portfolio 6 projets avec images, boutique 6 produits dont un épuisé, réseau
social 5 posts d'auteurs anonymes `Anon#…` avec likes « confidentiel /
populaire / viral », kanban réparti sur ses colonnes, classement trié
203→12), et reste stable au redémarrage (idempotence). Les cas d'erreur
(entité inconnue, champ inconnu, type incohérent) sont chacun couverts par
un test.

---

## 37. Frontend : images robustes, librairies CDN et ton vitrine

Trois ajustements issus d'un retour utilisateur sur le rendu des sites.

**Images invisibles → balise `<img>` robuste.** Les visuels étaient posés en
`background-image` sur une `<div>` dont la hauteur reposait sur
`aspect-ratio` ; quand cette propriété ne s'appliquait pas (ou que l'URL
tardait), la div avait une hauteur nulle et l'image restait invisible, sans
erreur. Désormais chaque média est une vraie `<img loading="lazy">` avec
`object-fit: cover`, une hauteur minimale explicite (repli d'`aspect-ratio`),
et un placeholder (initiale du titre) TOUJOURS présent en fond. Un `onerror`
retire proprement l'image si elle échoue, laissant le placeholder. S'applique
à la galerie, à la boutique et à la lightbox. Fini le rendu à hauteur nulle.

**Librairies externes via CDN, mais dégradables.** La landing charge
maintenant Lucide (icônes : panier sur le bouton d'achat, cœur des likes…)
et AOS (animations d'entrée au défilement des sections), via CDN unpkg — même
principe que les Google Fonts déjà utilisées. Point crucial : l'usage est
**entièrement dégradable**. Chaque appel (`lucide.createIcons`, `AOS.init`)
est gardé ; une règle CSS `[data-aos]:not(.aos-init)` force la visibilité des
sections tant qu'AOS n'a pas initialisé. Résultat vérifié (jsdom, tous CDN
coupés) : si un CDN est indisponible, la page reste entièrement fonctionnelle
et visible — les icônes sont simplement absentes et les sections n'ont pas
d'animation d'entrée. Aucune logique métier n'en dépend.

**Ton vitrine plutôt que technique.** Les sous-titres exposaient la
plomberie (« Chargé en direct depuis `GET /project`, sans compte requis »,
« Fonctionne réellement via `POST /message` »). Ils sont remplacés par des
formulations orientées visiteur (« Une sélection de nos réalisations
récentes », « Notre catalogue, disponible à la commande »…). L'information
technique n'est pas perdue : elle est conservée en **commentaire HTML** au
même endroit, utile au développeur qui lit la source.

**Preuve** : `tests/test_landing_polish.py` (balise img + fallback, présence
et dégradabilité des CDN, retrait des mentions visibles avec conservation en
commentaire) ; dégradation sans CDN validée via jsdom.

---

## 38. Espace connecté interactif : fil social façon Twitter

**Le problème (retour utilisateur) :** une fois connecté au réseau social,
on tombait sur un tableau de bord CRUD générique — « des blocs seuls » : une
carte par entité avec formulaire et liste brute. Aucune interaction sociale
(liker, commenter, messages), rien qui ressemble à un vrai réseau.

**Ce qui est fait :** l'espace connecté (`/app`) devient **conscient de
l'archétype**. Quand l'app est un réseau social (détection
`_compute_social_dashboard_plan`, 100% dérivée de la spec), le CRUD
générique est remplacé par un fil interactif inspiré de Twitter :
- **composer** un post en haut ;
- **fil** des posts, chacun avec avatar/pseudonyme anonyme, contenu, et une
  barre d'actions **like / dislike / repost** (icônes Lucide) qui POSTent
  réellement sur les entités de réaction et rafraîchissent les compteurs ;
- **commentaires** dépliables sous chaque post (chargement + ajout inline) ;
- panneau **messages privés** (DM) et **profil** (pseudonyme + rôle, lus du
  jeton) en colonne latérale.

**Dérivation.** Les réactions sont découvertes par croisement : une entité X
telle que `Post hasMany X` ET une règle `X.Create increments Post.<compteur>`
donne un bouton, l'icône étant choisie d'après le nom du compteur
(likes→cœur, dislikes→pouce bas, reposts→repartage). Commentaire et
messagerie privée (`accessibleBy`) sont détectés de même. La spec du réseau
social a été enrichie en conséquence (entités `Dislike`, `Repost`, compteurs
`dislikes`/`reposts`).

**Garde-fou anti faux positif :** un feed seul ne suffit pas — le formulaire
de contact d'un portfolio (`Message` : author + content) ressemblait à un
post. On exige de VRAIES interactions (au moins une réaction OU une entité
de commentaire) pour activer le dashboard social ; sinon, le CRUD générique
est conservé. Les 4 autres exemples gardent donc leur tableau de bord.

**Formulaires adaptatifs.** En marge : les formulaires (inscription, contact)
passent en largeur fluide (`width: min(100%, 440px)`, padding en `clamp`),
et le panneau d'auth flottant du mode template en `width: min(280px,
calc(100vw - 2rem))` — plus de débordement sur petit écran.

**Preuve, testée en conditions réelles** : back-end vérifié (post →
like/dislike/repost à 200, compteurs qui montent, commentaire, DM) ; rendu du
dashboard validé via jsdom (composer, 2 posts, 6 boutons de réaction, profil
affichant le pseudonyme, panneau messages, like et commentaires déclenchés au
clic). `tests/test_social_dashboard.py` couvre la dérivation, l'interactivité
et le non-déclenchement sur une app non sociale.

---

## 39. Frontend : sections éditoriales et dashboards lisibles

Deux compléments issus d'un retour utilisateur ("plus de texte, une section À
propos comme sur un vrai site ; et les autres dashboards aussi interactifs").

**Sections éditoriales standard sur la landing.** La landing gagne deux
sections attendues d'un vrai site : « À propos » et « Ce que nous proposons »
(trois points de réassurance), plus les liens de navigation associés. Le
contenu est DÉRIVÉ de la spec (aucun texte inventé au hasard, aucun appel
IA) : le corps de l'À propos reprend le `brief`, et le vocabulaire s'adapte à
l'archétype de l'entité publique — un portfolio parle de « réalisations » et
titre « À propos / Notre approche », une boutique de « produits / La maison /
Pourquoi nous choisir », un réseau social de « Notre manifeste / L'esprit de
la communauté », un kanban de « Notre méthode », un classement de « Le
principe ». Voir `_build_content_sections`.

**Dashboards génériques lisibles.** Les 4 tableaux de bord non sociaux
(portfolio, boutique, kanban, classement) affichaient leurs listes en JSON
brut — « des blocs seuls ». Désormais, chaque ligne est résumée lisiblement
selon l'archétype de l'entité : vignette (si champ image), titre, et une
info clé (prix pour une boutique, statut pour un kanban, score pour un
classement). Réalisé sans réécrire un dashboard par archétype : une map
`DASH_ARCHETYPES` (entité → {titre, secondaire, média}, dérivée des plans
d'archétype existants) est injectée dans le CRUD générique, dont le rendu de
ligne s'appuie dessus. Les contrôles de création/édition/suppression restent
inchangés. Voir `_compute_dash_archetypes`.

**Preuve** : `tests/test_content_sections.py` (présence des sections,
adaptation du vocabulaire par archétype, injection de la map et rendu de
ligne) ; rendu du dashboard boutique validé via jsdom (nom + vignette + prix
au lieu du JSON brut).

---

## 40. Pivot : monl orchestrateur (dialogue guidé, contrat frontend, run/update)

**Le constat :** une seule IA ne produit pas toujours des applications
complexes de manière cohérente. Plutôt que de tout générer, monl devient
une plateforme qui ORCHESTRE la création du logiciel : il transforme une
idée en architecture fiable (le DSL reste la source de vérité), puis laisse
des IA spécialisées construire dessus.

**Ce qui a été construit (chaque brique prouvée par exécution réelle) :**

1. **Dialogue guidé sans IA** (`src/dialogue_engine.py`) : la commande
   `monl` mène une conversation à questions fermées, validées et
   redemandées, et émet une spec `.ml`. Deux garanties de déterminisme :
   la spec émise est TOUJOURS revalidée par le vrai parseur + audit AST
   avant d'être rendue (un moteur qui émet une spec invalide échoue
   bruyamment — c'est un bug du moteur, jamais de l'utilisateur) ; et un
   seul gestionnaire d'écriture est demandé par entité, donc la règle
   stricte n° 1 (collision de privilèges) est inviolable PAR CONSTRUCTION.
   Le moteur ne lit jamais stdin directement : il consomme une fonction
   `ask(prompt)`, ce qui permet de le tester avec des réponses scriptées et
   une compilation réelle (`tests/test_dialogue_engine.py`). Hors de portée
   assumé de cette v1 : `ownedBy`/`accessibleBy`/`sharedBy`, blocs `custom`,
   landing `template`. À terme, cette couche pourra être remplacée par un
   petit modèle spécialisé — l'interface `ask()` est déjà le point de
   greffe.

2. **Contrat frontend** (`src/frontend_contract.py`) : à chaque
   compilation, `frontend_contract.json` (machine-lisible) et
   `FRONTEND_PROMPT.md` (brief prêt à donner à Claude/GPT) décrivent
   exhaustivement ce que le backend expose : routes avec méthode/chemin/
   auth/acteurs, champs avec `required`/`hidden`/`generated`/`categorized`,
   conventions d'auth et de pagination. Le contrat est dérivé des MÊMES
   structures que la génération des routes (`_compute_route_map`) — un test
   confronte chaque route du contrat aux décorateurs réellement écrits dans
   `app.py` (`tests/test_orchestrator.py`), donc toute divergence future
   casse la CI.

3. **`monl run`** (`src/cli.py`) : vérifie la cohérence de l'ensemble
   avant de lancer — spec inchangée depuis la compilation (empreinte
   SHA-256 dans `monl.json`), artefacts présents, contrat non édité à la
   main, et frontend n'appelant que des chemins du contrat (avertissement
   best-effort, pas un blocage : un chemin peut être construit
   dynamiquement). Le frontend produit par l'IA (`frontend/index.html`) est
   monté sur `/site` via un wrapper `serve.py` généré au lancement — jamais
   en modifiant `app.py`, qui reste un artefact scellé du compilateur.

4. **`monl update`** : recompile la spec dans le même dossier (les
   migrations additives du point 32 préservent la base), régénère le
   contrat, et rapporte le DELTA (routes/champs ajoutés/retirés) — c'est
   exactement l'information à transmettre à l'IA frontend pour qu'elle
   fasse évoluer l'interface sans repartir de zéro.

**Ce que le pivot ne change PAS :** le pipeline de compilation
(parser → audit → générateur), les règles strictes, les échappatoires IA
non bloquantes, et `python3 src/main.py` qui reste utilisable tel quel.
Le CLI orchestrateur est une couche AU-DESSUS, pas une réécriture.


---

## 41. Le pivot mené à terme : boucle fermée et suppression du frontend généré

**La suppression (demandée explicitement) :** puisque l'interface est
désormais déléguée à une IA spécialisée via le contrat, TOUT le frontend
que monl générait lui-même a été retiré — landing (modes `ai` et
`template`), tableau de bord `/app`, archétypes d'interface (galerie,
boutique, kanban, fil social, liste classée), widget d'auth du mode
template, `ai_landing_filler.py`, `templates/`, et les 5 fichiers de tests
associés. `generator.py` passe de ~4200 à ~1350 lignes ; il ne produit plus
que le backend (`app.py`, `schema.sql`, `sandbox_ai.py`). Ce qui décrivait
ces fonctionnalités aux points 15, 17-23, 34-39 est de l'histoire, pas de
l'actualité.

**Ce qui a été conservé en changeant de rôle :**
- Le bloc `landing` reste ACCEPTÉ par la grammaire (aucune spec existante
  ne casse) mais seul `brief:` a un effet : il alimente le brief produit du
  contrat frontend. `mode`/`template` déclenchent un avertissement explicite
  — jamais une régression silencieuse.
- L'identité visuelle déterministe (points 15, 17, 20 : `_select_theme`,
  `.monl_theme_seed`, surcharge `ui / theme`) ne produit plus de HTML :
  elle est transmise à l'IA frontend comme DIRECTION de design (palette,
  typographies) dans le contrat — deux projets ne se ressemblent toujours
  jamais, mais c'est l'IA qui écrit le rendu.
- Un test verrouille la disparition : plus aucun exemple ne doit jamais
  produire `landing.html`, `dashboard.html` ni `frontend.html`
  (`tests/test_compile_all.py`).

**La boucle fermée (les 4 chantiers annoncés au point 40) :**

1. **Smoke test comportemental** (`src/smoke_test.py`, intégré à
   `monl run`) : « cohérent » ne suffisait pas, il faut que ça
   FONCTIONNE. Avant tout lancement, un serveur uvicorn éphémère démarre
   dans un dossier temporaire (base neuve — un test prouve que la base
   réelle n'est jamais touchée) ; chaque route du contrat est éprouvée en
   HTTP réel (publiques → 200, protégées → refus sans jeton, compte réel
   créé par register/login pour vérifier l'accès avec jeton, une création
   réelle avec un corps conforme au contrat) ; si Node.js est présent,
   `frontend/index.html` est exécuté dans jsdom contre ce serveur, ses
   `fetch()` routés et journalisés — exception JavaScript ou appel hors
   contrat = lancement refusé (`--skip-smoke` pour contourner). Bug réel
   trouvé par exécution, jamais par relecture : le `fetch` injecté APRÈS
   `new JSDOM(...)` n'est jamais vu par les scripts de la page (ils
   s'exécutent pendant la construction) — l'injection doit se faire dans
   `beforeParse`. jsdom est installé une seule fois dans `~/.monl/jsdom`
   (hors dépôt, comme les modèles Ollama).

2. **Dialogue guidé enrichi** (`src/dialogue_engine.py`) : `ownedBy`
   (propriété par enregistrement — l'entité propriétaire homonyme de
   l'acteur est créée automatiquement si absente, avec sa relation
   `hasMany`, motif canonique du point 5 et de `exemples/03`) et `sharedBy`
   (gestion partagée : un workflow par acteur + les règles `sharedBy`, la
   voie légitime prévue par la règle stricte n° 1). L'interdiction
   d'homonymie acteur/entité du dialogue v1 a été levée : c'est précisément
   le motif dont `ownedBy` a besoin.

3. **`monl update` actionnable** : quand le contrat change, le delta
   n'est plus seulement affiché — il est écrit dans
   `FRONTEND_UPDATE_PROMPT.md`, formulé comme consigne prête à donner à
   l'IA frontend (« brancher telle route », « retirer tel champ des vues »),
   avec l'instruction de faire ÉVOLUER l'existant, pas de réécrire.

4. **`monl frontend`** (`src/frontend_ai.py`) : l'orchestration
   complète. Le brief (ou le delta + les fichiers existants en `--update`)
   est envoyé à un fournisseur IA (`claude` via l'API Anthropic, clé dans
   `ANTHROPIC_API_KEY` — jamais en argument de commande), les fichiers
   rendus sont écrits dans `frontend/` puis l'ensemble est RE-VÉRIFIÉ
   automatiquement (cohérence + smoke test). En cas d'échec, les erreurs
   constatées sont renvoyées UNE FOIS au modèle pour correction — même
   filet que `--prompt` (phase 7), jamais de boucle infinie. La réponse du
   modèle est traitée comme une entrée non fiable (même philosophie que le
   garde-fou des blocs `custom`, point 4) : chemins confinés à `frontend/`,
   extensions en liste blanche, `index.html` obligatoire, taille plafonnée.
   Le fournisseur est une simple fonction `provider(prompt) -> str` :
   testable par exécution réelle avec un fournisseur factice
   (`tests/test_smoke_and_frontend_ai.py` prouve la boucle
   cassé→correction→succès ET l'arrêt après une seule correction),
   extensible à d'autres IA sans toucher à la boucle.


---

## 42. `monl import` : la voie sans clé API (abonnement claude.ai)

**Le constat :** le cas le plus courant n'est pas la clé API — c'est
l'abonnement Claude. `monl frontend` (point 41) exige `ANTHROPIC_API_KEY` ;
il fallait une voie où l'humain fait lui-même l'aller-retour avec la
conversation. Le flux devient :

1. copier `FRONTEND_PROMPT.md` (ou `FRONTEND_UPDATE_PROMPT.md` pour une
   évolution) dans la conversation claude.ai — les deux briefs contiennent
   désormais une consigne dédiée demandant au modèle de rendre le résultat
   en ZIP téléchargeable ou en `index.html` autonome ;
2. télécharger ce que Claude produit ;
3. `monl import <téléchargement> <projet>`.

**Ce que l'import accepte** (les formes réelles sous lesquelles un frontend
revient d'une conversation) : un `.zip` (avec racine intelligente — si
`index.html` vit dans un unique sous-dossier type `mon-app/`, c'est lui qui
devient la racine), un `index.html` seul, un dossier déjà décompressé, ou le
JSON `{"files": ...}` de la voie API.

**Mêmes garde-fous que la voie API** — la source vient d'une conversation,
elle est traitée comme une entrée non fiable : protection zip-slip (chemin
`../` ou absolu = archive refusée), extensions en liste blanche (les
fichiers hors liste sont ignorés avec avertissement, jamais installés),
`index.html` obligatoire, taille plafonnée. Le frontend précédent est
déplacé dans `frontend.precedent/` avant installation — rien n'est jamais
perdu par un import.

**Même re-vérification** : cohérence statique + smoke test comportemental.
PAS d'auto-correction ici — l'humain est déjà dans la boucle : en cas
d'échec, les erreurs sont affichées, prêtes à être recollées dans la
conversation Claude pour obtenir un correctif, puis réimporter.

**Deux bugs réels trouvés par exécution en éprouvant cette voie** (jamais
visibles en relecture) :
- un `fetch` vivant dans `app.js` (chargé par `<script src>`) n'était
  JAMAIS exécuté par le runner jsdom — jsdom ne charge pas les ressources
  externes par défaut, et son API de chargement a changé entre versions
  (`ResourceLoader` n'existe plus en v29). Correctif robuste et indépendant
  de la version : les `<script src>` locaux sont inlinés dans le HTML avant
  construction du DOM. Sans cela, le smoke test d'un frontend multi-fichiers
  était un faux positif silencieux ;
- conséquence assumée : les scripts CDN (`https://…`) ne sont pas chargés —
  le contrat exige désormais explicitement un frontend AUTONOME (tout le
  JS/CSS dans `frontend/`), et un script externe fait échouer le smoke test
  avec un message clair. C'est une contrainte de vérifiabilité, pas une
  limitation accidentelle.


---

## 43. Claude Code : le travail directement dans le dossier cible

**Le constat :** le point 42 (copier le brief, télécharger, importer)
fonctionne mais garde un aller-retour manuel. Claude Code supprime cet
aller-retour ET fonctionne avec l'abonnement ('claude login' — aucune clé
API) : l'agent lit le brief sur place, écrit dans frontend/, monl
re-vérifie derrière. Faits produit vérifiés dans la documentation
officielle (mode headless `claude -p`, `--permission-mode acceptEdits`,
`--max-turns`) — jamais de mémoire.

**Deux usages :**

1. **Interactif** : `cd MonProjet && claude`. Chaque compilation génère
   désormais un `CLAUDE.md` DANS le dossier du projet
   (`write_project_claude_md`) qui cadre la session : rôle (le frontend,
   rien d'autre), lecture de `FRONTEND_PROMPT.md` /
   `FRONTEND_UPDATE_PROMPT.md`, interdits absolus (spec, backend, contrat,
   état), et la commande de vérification (`monl run . --check`) pour que
   l'agent itère lui-même jusqu'au vert. Ce CLAUDE.md porte un marqueur :
   s'il est repris en main par l'utilisateur (marqueur retiré), il n'est
   PLUS JAMAIS écrasé par les recompilations — même convention de propriété
   que `.jwt_secret`.

2. **Headless** : `monl frontend --provider claude-code` invoque
   `claude -p` dans le dossier du projet avec `--permission-mode
   acceptEdits` et un plafond `--max-turns`, puis applique la MÊME
   re-vérification (cohérence + smoke test) et la MÊME correction unique
   que la voie API — les erreurs constatées sont réinjectées dans la
   consigne de la seconde invocation.

**Le garde-fou spécifique à cette voie :** contrairement à l'API (qui rend
du texte que monl écrit lui-même après filtrage), Claude Code écrit
DIRECTEMENT sur le disque. Les artefacts protégés (spec, `app.py`,
`schema.sql`, `sandbox_ai.py`, contrat, briefs, `monl.json`,
`.jwt_secret`) sont donc empreints (SHA-256) AVANT chaque exécution et
re-vérifiés APRÈS : toute modification est une erreur bloquante avec la
liste des fichiers touchés, même si le frontend rendu est par ailleurs
correct. Testé avec un agent factice « malveillant » qui ajoute une ligne à
`app.py` (`tests/test_smoke_and_frontend_ai.py`).

**Testabilité :** l'exécutable `claude` est injectable (`command=`) — même
approche que le fournisseur API factice : l'orchestration complète
(empreintes, vérification, correction) s'exécute pour de vrai, seul l'agent
est simulé. Trois scénarios prouvés par exécution : agent correct, agent
qui se corrige (les erreurs sont bien dans la consigne de la 2e
invocation), agent qui touche le backend.


---

## 44. Modèle local pour comprendre l'utilisateur : l'interprète, pas le rédacteur

**La question posée :** un modèle local qui comprend les besoins de
l'utilisateur et produit le DSL, est-ce faisable maintenant ?

**La réponse en deux temps.** Produire le DSL intégralement, c'est la
phase 7 (`--prompt`, `src/ai_translator.py`) — elle existe, mais elle est
structurellement fragile : un modèle local de 3B n'a JAMAIS vu monl à
l'entraînement, lui demander de rédiger un DSL inventé d'un bloc impose
une boucle de correction et échoue encore parfois. Comprendre
l'utilisateur, en revanche, est faisable maintenant et de façon robuste —
à condition d'inverser la répartition des rôles :

**LE MODÈLE N'ÉCRIT JAMAIS DE DSL. IL INTERPRÈTE.** Le dialogue guidé
déterministe (brique 1 du pivot) reste le squelette ; le modèle local
(`src/nl_interpreter.py`, Ollama, température 0 — aucune donnée ne quitte
la machine) ne fait que mapper une réponse LIBRE vers la réponse fermée
attendue : « c'est l'admin qui s'en occupe » → « 1 », « oui bien sûr » →
« o », « les messages des clients » → « Message ». C'est une tâche de
classification, à la portée d'un 3B, là où la synthèse de DSL ne l'est pas.

**Trois propriétés de sûreté, par construction :**
1. L'interprète n'intervient QU'APRÈS un échec de la validation stricte —
   une réponse déjà conforme ne passe jamais par le modèle (prouvé par
   test : sur 14 réponses libres, 13 interprétations, la 14e était déjà
   valide).
2. Sa proposition repasse par le MÊME validateur que la saisie stricte, et
   elle est AFFICHÉE (« ↳ compris comme : 'Admin' ») — un mauvais mapping
   est rejeté et la question redemandée, jamais accepté en silence
   (prouvé par test avec un mapping absurde injecté).
3. Si Ollama tombe — au départ ou EN COURS de dialogue — l'interprète est
   débranché avec un message explicite et le dialogue continue en saisie
   stricte : jamais bloquant (prouvé par test avec un interprète qui lève
   `InterpreterUnavailable` au premier appel).

C'était le point de greffe `ask()` annoncé dès le point 40 (« cette couche
pourra évoluer vers un petit modèle spécialisé ») — la greffe est faite,
et l'émission de la spec reste 100 % déterministe.

**Usage :** `monl init --nl` (option `--nl-model`). Et `--prompt`
(traduction intégrale, phase 7) est désormais intégré au pipeline
orchestrateur complet (contrat, CLAUDE.md de projet, état) au lieu de
s'arrêter au backend — assumé comme la voie « plus fragile mais plus
rapide », documentée comme telle dans l'aide du CLI.

**Le vrai modèle spécialisé (fine-tuné sur monl) : faisable, pas fait.**
C'est un projet distinct : générer un jeu d'entraînement synthétique
(la grammaire Lark + le validateur + les exemples permettent de produire
des paires description↔spec valides en quantité), fine-tuner un petit
modèle (LoRA sur un 3B), et l'évaluer contre la suite de tests existante.
L'architecture n'aura pas à changer : `--nl-model` et `--prompt-model`
pointent déjà vers n'importe quel modèle Ollama — un modèle spécialisé s'y
branchera tel quel. Limite honnête de cette session : Ollama n'est pas
disponible dans l'environnement de test — l'orchestration complète est
prouvée avec des interprètes factices (mêmes mappings qu'un 3B produirait
sur cette tâche de classification), le premier essai avec un vrai modèle
local reste à faire sur machine utilisateur.


---

## 45. Le dialogue ouvre sur un catalogue de 10 modèles d'applications

**Le constat (issu du premier test utilisateur réel) :** partir d'une page
blanche (« nommez votre première entité ») est la friction principale du
dialogue — l'utilisateur pense « je veux une boutique », pas « j'ai besoin
d'une entité Product avec un champ price de type Money ».

**La refonte :** le dialogue ouvre désormais sur les 10 types
d'applications les plus construits par les développeurs web — portfolio,
blog, boutique, gestion de tâches, forum/réseau social, petites annonces,
réservation de rendez-vous, inventaire, suivi de dépenses, classement
communautaire — plus « Partir de zéro », qui conserve le dialogue libre
historique intact. Choisir un modèle pré-remplit entités, acteurs, règles
(y compris les briques avancées : `ownedBy` pour les commandes/annonces/
tâches, `increments` pour les likes et les votes) et des données de
démonstration RÉALISTES en français. Puis viennent uniquement des questions
de suivi PROPRES AU MODÈLE (« classer les produits par catégorie ? »,
« suivre le stock ? », « permettre les commentaires ? ») dont les effets se
tissent jusque dans les seeds — accepter « catégories » ajoute le champ ET
des valeurs cohérentes dans les données de démo. Résultat mesuré : une
boutique complète (catalogue public, commandes possédées par leurs clients,
catégories, stock, données réalistes) en 8 réponses au lieu d'une
vingtaine, sans page blanche.

**Décisions structurantes :**
- Les modèles sont de la DONNÉE (`src/app_templates.py`), pas du code : le
  dialogue les assemble via le MÊME émetteur déterministe que le chemin
  libre, et la spec finale repasse par le vrai parseur + l'audit. Le
  catalogue est copié en profondeur à chaque exécution (jamais muté — testé).
- Une « entité personnalisée » peut être ajoutée en plus du modèle :
  l'échappatoire qui évite de retomber sur « partir de zéro » pour un seul
  écart au modèle.
- L'émetteur a été étendu au passage : `extra_rules` (lignes de règles
  avancées émises telles quelles, validées comme le reste) et
  `custom_seeds` (données réalistes du modèle, repli générique sinon) ;
  `public_create` devient une liste ; la création des entités propriétaires
  (`_ensure_ownership_structure`) est partagée entre les deux chemins.
- Le VERROU : chaque modèle du catalogue est déroulé par les tests dans les
  deux chemins extrêmes — toutes les questions de suivi refusées ET toutes
  acceptées — via le vrai dialogue (réponses scriptées), et compilé
  (`tests/test_app_templates.py`, paramétré). Ajouter un 11e modèle qui
  viole une règle stricte du compilateur casse immédiatement la CI.
- Compatibilité : le chemin libre est inchangé derrière l'option 11 ; les
  réponses libres (`--nl`, point 44) fonctionnent sur les deux chemins
  puisque la greffe est dans les primitives de question.


---

## 46. La démonstration complète (AtelierVélo) et ce qu'elle prouve

**Le besoin (bilan v6) :** prouver le concept de bout en bout plutôt
qu'ajouter de la complexité. La démo est dans `demo/` (spec + frontend),
racontée sorties réelles à l'appui dans `docs/DEMO.md`, et VERROUILLÉE par
`tests/test_demo.py` : la spec livrée doit toujours compiler et le frontend
livré toujours passer le smoke test — la démo ne peut pas pourrir en
silence.

**Le parcours exécuté (rien n'est rédigé de mémoire) :** dialogue modèle
« Boutique » en 8 réponses → spec de 63 lignes mobilisant `ownedBy`,
lecture publique et seeds réalistes → frontend écrit par une IA RÉELLE
(Claude jouant le rôle, contre le contrat : catalogue filtrable, compte
client, commandes, direction de design « market », zéro CDN) → smoke test
vert du premier coup → utilisation réelle (compte « lea », commande 34,50 €)
→ évolution (`Order.note` ajouté à la spec, `run` refuse, `update` produit
le delta et le brief) → le frontend évolue en deux retouches ciblées → la
commande créée AVANT la migration est toujours là, la nouvelle colonne à
`null`.

**Ce que la démo établit qu'aucun test unitaire ne montrait :** la chaîne
entière tient avec une vraie IA frontend — c'était le seul maillon jamais
exercé qu'avec des agents factices. Et le brief de mise à jour suffit à
obtenir une évolution CIBLÉE (deux retouches) plutôt qu'une réécriture.

**Bilan v6 acté au passage :** la frontière backend/frontend (empreintes,
contrat vérifié contre app.py, smoke bloquant) et `monl update`
(migrations additives, delta, brief) existaient déjà — restent ouverts :
les migrations destructives (renommage/suppression de colonnes), des
messages d'erreur plus pédagogiques, et l'architecture à plugins,
volontairement REPORTÉE : extraire des plugins sans plusieurs consommateurs
réels serait de l'abstraction spéculative, la complexité que le bilan
voulait justement éviter.


---

## 45. Le rôle ne peut pas être choisi par celui qui s'inscrit (bêta 3)

**Constat d'audit.** Le modèle de sécurité affirmait que le rôle provenait
« du compte réel, jamais d'une déclaration du client ». C'était vrai après
l'inscription, et faux à l'inscription : `POST /register` acceptait le champ
`actor` du client et le validait contre la seule liste des rôles déclarés.
Sur `exemples/02_boutique.ml`, deux appels anonymes suffisaient à obtenir un
compte `ShopManager` et à écrire dans le catalogue. Les tests offensifs
couvraient le jeton forgé et l'en-tête `x_actor`, pas ce chemin — parce
qu'ils partaient tous du principe que le compte était légitime.

**Décision.** L'inscription libre devient une propriété déclarée de l'acteur,
pas un droit implicite : `actor Client selfRegister` l'ouvre, `actor Admin`
ne l'ouvre pas. Trois raisons de mettre le marqueur dans le DSL plutôt qu'un
réglage de déploiement :

1. c'est une décision d'architecture applicative (« qui peut devenir quoi »),
   donc elle appartient à la source de vérité, comme `ownedBy` ou `public` ;
2. elle est alors visible à la relecture de la spec, vérifiable à la
   compilation, publiable dans le contrat frontend et éprouvable par le smoke
   test — un réglage d'environnement n'aurait rien de tout cela ;
3. le défaut peut être sûr. Une spec qui ne dit rien ferme l'inscription : le
   pire cas est une application dont personne ne peut créer de compte sans
   passer par le serveur, pas une application dont n'importe qui devient
   administrateur.

**Conséquence assumée.** Le défaut fermé exige un chemin de provisionnement,
sans quoi une application sans acteur `selfRegister` serait inutilisable :
d'où `manage.py`, généré à côté de `app.py`, qui sait aussi initialiser la
base pour que le premier compte puisse être créé avant le premier démarrage.
La frontière devient « posséder le serveur » au lieu de « savoir envoyer un
POST ». Les six specs livrées ont été mises à jour ; c'est une rupture de
compatibilité assumée pour une bêta, tracée dans `CHANGELOG.md`.

## 46. Le déterminisme doit être testé entre processus (bêta 3)

`self.actors` était un `set`, sérialisé par `list()` dans l'AST normalisé.
L'ordre d'itération d'un ensemble Python dépend de `PYTHONHASHSEED`, donc
`VALID_ACTORS` changeait d'une compilation à l'autre : la promesse « même
spec, même backend à l'octet près » était fausse, et invérifiable par un test
exécuté dans un seul processus. Le test de reproductibilité compile désormais
dans deux sous-processus aux graines de hachage opposées. Règle générale :
aucun ensemble non ordonné ne doit atteindre la sortie générée — soit on
conserve l'ordre de déclaration (acteurs), soit on trie explicitement
(`public`, `hidden_fields`).

## 47. Découper le générateur avant de le réécrire (bêta 3)

`generator.py` atteignait 1 307 lignes et concentrait quatre couches sans
rapport (schéma SQL, socle runtime, routes, direction visuelle). Chaque
correctif de sécurité de la bêta 3 devait être écrit à travers cette couche,
ce qui la rendait bloquante plus tôt que prévu par la feuille de route.

Découpage en package par mixins plutôt que réécriture par templates : le
passage aux templates (chantier GA) demande de figer la sortie par des
*golden-file tests*, qui n'ont de sens qu'une fois les couches séparées. Le
découpage a été fait par tranches de lignes, sans réécriture du corps des
méthodes, et validé en comparant octet à octet la sortie générée sur les six
specs avant et après. C'est cette vérification — pas la relecture — qui rend
l'opération sûre sur un générateur de code.


## 48. Une clause de contrat que rien ne vérifie n'est pas une clause (bêta 3)

**Constat.** Le frontend de la démo n'appliquait pas la palette publiée dans
son propre `frontend_contract.json` — et rien ne le signalait. Toutes les
autres clauses du contrat sont confrontées à un livrable (les routes à
`app.py` par `tests/test_orchestrator.py`, le comportement au smoke test) ;
`design` était la seule à ne l'être par rien. Dans un produit dont la thèse
est « le contrat fait foi », une clause invérifiée décrédibilise les autres.

**Décision.** La sévérité dépend de l'ORIGINE de la direction, pas de son
contenu :

- **épinglée** par un bloc `ui … theme:` — l'auteur de la spec a tranché, la
  palette est publiée exacte et le smoke test exige de la retrouver dans les
  styles livrés. Un écart fait échouer le lancement.
- **déduite** du vocabulaire des entités — c'est une proposition du
  compilateur, obtenue par correspondance de mots-clés. L'écart est signalé
  avec la marche à suivre pour la rendre contraignante, mais ne bloque rien.

Rendre contraignante une palette *devinée* punirait un bon parti pris de
l'interface pour faire respecter une supposition du compilateur. À l'inverse,
laisser une palette *déclarée* sans effet reviendrait à admettre que la spec
n'est pas la source de vérité qu'on annonce. Cette asymétrie est la même que
celle déjà retenue pour `ui / theme` (repli silencieux sur un défaut) face aux
blocs `capability` (liste blanche stricte) : strict sur ce qui est déclaré,
tolérant sur ce qui est déduit.

**Conséquence.** Un thème épinglé échappe à la variation de teinte propre au
projet (point 39) : une valeur vérifiable doit être exacte et reproductible,
pas décalée par une graine. La variation continue de s'appliquer aux thèmes
déduits, où elle sert son objectif d'origine — éviter que deux applications du
même domaine soient des pixels identiques.


## 49. Le dialogue montre son parcours avant de le faire subir (bêta 3)

Un entretien dont on ne voit pas la fin est subi : à la cinquième question,
l'utilisateur ne sait plus s'il en reste deux ou vingt, et l'abandon devient
rationnel. Le dialogue affiche donc son déroulé complet AVANT la première
question, puis marque l'étape en cours (`02/04  IDENTITÉ DU PROJET`). C'est le
seul élément réellement nouveau de cette présentation — le reste (menus
alignés, invite dédiée, récapitulatif) ne fait que rendre lisible ce qui
existait déjà.

**Contraintes tenues.** Aucune dépendance (ni `rich` ni `colorama`) : le socle
doit rester hors-ligne et sans surface d'attaque supplémentaire, donc tout
passe par des séquences ANSI écrites à la main. Dégradation silencieuse hors
terminal interactif, sous `NO_COLOR`, et sur un encodage sans caractères de
dessin — un journal de CI ne doit contenir ni séquence d'échappement ni glyphe
cassé.

**Séparation retenue.** Le moteur de dialogue ne connaît pas `src/tui.py` : il
appelle une interface de présentation (`PlainDialogueUI`) dont la version nue
reproduit exactement les chaînes historiques, et l'entrée interactive y
substitue le rendu stylé. Conséquence directe : les tests scriptés exercent le
vrai moteur sans dépendre d'un seul caractère d'habillage, et l'esthétique peut
évoluer sans jamais toucher à ce qui produit la spec.

**Une question ajoutée, pas un réglage deviné.** Le dialogue demande désormais
quel rôle peut créer son compte depuis le site — sans quoi, depuis le point 45,
il produisait des applications où personne ne pouvait s'inscrire. Cette
question est de sécurité : elle est posée, jamais déduite. L'ordre des réponses
porte l'avis du compilateur (d'abord les rôles qui n'écrivent que sur leurs
propres enregistrements, ceux dont l'inscription libre n'ouvre aucun droit sur
les données communes), et « aucune » reste disponible pour une application dont
tous les comptes sont provisionnés.


## 50. Une règle de propriété qui ne couvre pas la lecture n'en est pas une (bêta 3)

`ownedBy` restreignait `Update` et `Delete`, jamais `Read` : sur une
application de dépenses personnelles, deux comptes se lisaient mutuellement,
et seule l'écriture était refusée. Le même angle mort que la faille
d'inscription (point 45) : une porte gardée, une fenêtre ouverte.

**Filtrage par acteur, pas par route.** Le filtre ne s'applique qu'à l'acteur
nommé par la règle. Un gestionnaire de boutique doit voir toutes les
commandes ; un responsable, toutes les tâches. Filtrer la route entière aurait
cassé les applications que la règle est censée protéger — c'est la même nuance
que celle déjà retenue pour `ownedBy` en écriture face à `sharedBy`.

**404 plutôt que 403 en lecture directe.** Les identifiants sont séquentiels :
un 403 confirmerait l'existence de l'enregistrement d'autrui, et il suffirait
d'énumérer pour compter les dépenses d'un tiers. Un enregistrement qu'on n'a
pas le droit de lire doit être indiscernable d'un enregistrement absent.
`accessibleBy` répond encore 403 dans le même cas : divergence connue, à
unifier — elle est signalée ici plutôt que laissée à découvrir.

**Refuser plutôt qu'ignorer.** `rule X.Read ownedBy A` compilait sans effet, et
`ownedBy` sur `Create` était accepté sans que le générateur n'en fasse rien.
Une règle de sécurité silencieusement ignorée est pire que son absence :
l'auteur de la spec croit la protection en place et ne la teste pas. Les deux
cas échouent désormais à la compilation.

**Défaut appliqué par le dialogue.** Une entité possédée par ses créateurs et
non lisible sans compte reçoit automatiquement la règle de lecture, écrite en
clair dans la spec produite — visible, relisable, supprimable. Le défaut est
sûr, mais il n'est pas caché.

## 51. Un contrat qui dicte un port en dur punit l'IA qui lui obéit

`monl frontend --provider claude-code` a échoué deux fois de suite sur un
message indéchiffrable : `TypeError: fetch failed`. Le frontend produit était
pourtant correct — il faisait exactement ce que le contrat lui ordonnait.

**Le contrat mentait.** `api.base_url` valait `"http://127.0.0.1:8000"`, et le
brief en faisait une consigne : « N'appeler QUE les routes listées plus bas,
sur `http://127.0.0.1:8000` ». L'IA a codé `var API_BASE =
'http://127.0.0.1:8000'`. Mais le smoke test démarre son serveur éphémère sur
un **port libre tiré au hasard** (point 1), et le shim `fetch` du runner jsdom
ne réécrivait que les chemins commençant par `/`. L'URL absolue filait donc
vers un port où personne n'écoutait. Le vérificateur recalait le frontend pour
avoir suivi le contrat à la lettre, et la correction automatique — à qui on ne
transmettait que « fetch failed » — ne pouvait pas deviner la cause : ses deux
tentatives étaient condamnées d'avance.

**Ce n'était pas un artefact de test.** `monl run` monte `frontend/` sur
`/site` du serveur qui porte déjà l'API (`SERVE_WRAPPER`, cli.py) : l'origine
de la page EST celle de l'API. Un `monl run --port 9000` aurait donc produit
une application ouvrant une interface sur 9000 qui interroge 8000. Le port en
dur était un vrai défaut de production, que le smoke test signalait mal plutôt
qu'à tort.

**Corriger la consigne, pas le vérificateur.** `api.base_url` vaut désormais
`""` (même origine) et le brief exige des chemins relatifs. La tentation était
de faire réécrire les URL absolues par le shim jsdom : ç'aurait été un faux
positif — le frontend serait passé au vert ici et cassé sous `--port`. La
faute reste une faute ; seul son signalement change. Le shim la nomme
explicitement (« URL absolue interdite… ») au lieu de la laisser mourir en
`fetch failed`, et la consigne l'enregistre comme un appel tenté, sans quoi le
rapport concluait « aucun appel API au chargement » — faux, et brouillant la
piste.

**Un runner muet n'apprend rien.** Un `fetch` rejeté que la page n'attrape pas
tuait le process Node avant l'émission du rapport : le smoke test ne disait
plus que « le runner jsdom n'a rendu aucun rapport ». Même famille de défaut
que ci-dessus — la cause existe, le message la perd. Le runner intercepte
maintenant `unhandledRejection` et le consigne comme erreur JS (dédoublonné de
ce que le shim a déjà nommé).

`monl_contract_version` passe à **2** : la lecture de `api.base_url` change de
sens. Les projets déjà compilés se resynchronisent par `monl update`.

## 52. Proposer une police que le même contrat interdit de charger

Question posée devant le premier site généré : « pourquoi est-il aussi
minimaliste ? ». Le CSS livré portait la réponse, écrite par l'IA elle-même en
tête de fichier : *« Google Fonts non chargées (frontend autonome, sans CDN) :
les piles de secours portent l'identité typographique. »*

**Le contrat se contredisait.** Sa direction de design annonçait
`Fraunces` et `Inter` avec l'URL Google Fonts qui va avec ; ses règles non
négociables, quatre lignes plus bas, interdisaient toute ressource externe.
L'IA UI a tranché correctement — l'autonomie prime — mais l'arbitrage laissait
`Fraunces` devenir Georgia et `Inter` la police système. La moitié la plus
visible d'une identité, sa typographie, s'évaporait à **chaque** projet, et il
ne restait de la « direction » que cinq couleurs.

**Pourquoi personne ne l'avait vu.** Le point 48 avait rendu la clause design
vérifiable — mais pour les couleurs seulement. La typographie restait la part
non contrôlée de cette clause, et une clause que rien ne vérifie finit par
mentir sans que rien ne s'en aperçoive. Le smoke test confronte désormais
aussi la police de titrage aux styles livrés.

**Des piles système, pas des fontes embarquées.** Encoder les woff2 en base64
dans le CSS généré aurait restitué les fontes exactes, au prix du poids sur
chaque projet et d'une question de licence à trancher pour l'utilisateur.
Autoriser un `<link>` distant aurait coûté bien plus cher : c'est l'autonomie
du frontend qui rend le smoke test possible hors ligne, donc qui rend le reste
vérifiable. Les six systèmes nomment maintenant des familles réellement
présentes sur les machines — le thème `atelier` (bêta 3) l'avait déjà fait,
les cinq autres l'ont rejoint. Un test refuse toute famille hors liste.

**Rester distincts sans Google Fonts.** Le catalogue existe pour que deux
applications ne se ressemblent jamais ; six thèmes qui retombent tous sur
Georgia auraient perdu cette raison d'être. Chaque système garde donc une face
de titrage qui lui est propre — Palatino pour `editorial`, Arial Narrow pour
`market`, Georgia pour `civic`, Times pour `ledger`, chasse fixe pour
`console`, grotesque pour `atelier` — et un test le vérifie.

**Un écart typographique ne bloque jamais.** Même thème épinglé : `#D9F227`
est une valeur exacte, présente ou absente, tandis qu'une pile de polices a
des quasi-équivalents (`Helvetica` pour `'Helvetica Neue'`) qu'une recherche
textuelle ne distingue pas d'un oubli. Bloquer un build sur cette nuance
punirait un bon parti pris pour une différence invisible — le faux positif que
le point 48 s'interdit. Seule une couleur manquante reste bloquante.

## 53. Le dialogue interrogeait la structure, jamais l'intention

Suite du point 52, même question de départ : pourquoi les sites générés
se ressemblent-ils tous, en sobre ? Les polices n'étaient qu'une moitié de la
réponse. L'autre tenait dans ce que l'IA UI recevait comme matière.

**Un brief de trois mots face à un contrat au champ près.** Le dialogue
demandait « Décrivez le projet en une phrase », et cette phrase — souvent
`portfolio pour photographe`, faute de frappe comprise — constituait le SEUL
énoncé d'intention du brief. Les soixante-dix lignes restantes décrivaient des
routes, des types de champs, la pagination et l'authentification. L'IA
recevait donc toute la structure et presque aucun dessein. À qui ne dit rien,
elle rend le dénominateur commun — ce n'est pas un défaut du modèle, c'est
l'absence de commande.

**Ce qu'une spec ne peut pas déduire.** Les mêmes entités, les mêmes rôles et
les mêmes routes servent aussi bien un portfolio contemplatif qu'un
back-office pressé. Aucune analyse du schéma ne tranchera entre les deux :
c'est une décision, pas une déduction. Le dialogue pose donc trois questions
— ce que le visiteur doit pouvoir faire, le registre visuel, la place des
images — et les coud à la description dans le `brief` du bloc `landing`.

**Menus fermés, pas champs libres.** Deux des trois questions sont des menus.
Le dialogue est déterministe et sans IA (point 40) : des réponses libres
demanderaient une interprétation qu'il n'a pas les moyens de faire, et
produiraient des briefs de qualité très inégale. Chaque entrée porte un
libellé court pour l'écran et une phrase complète pour le brief — ce que lit
l'IA est ainsi toujours formulé, jamais un mot-clé nu.

**Posées seulement si elles servent.** L'intention n'est demandée que si
l'utilisateur transmet un brief. Sans page d'accueil à écrire, ces trois
questions ne feraient perdre du temps à personne d'utile.

**Limite connue, assumée pour l'instant.** Le registre déclaré n'influence pas
encore le choix du système visuel, qui reste déduit du vocabulaire des
entités. Un portfolio dont l'entité s'appelle `Project` reçoit toujours le
thème `console` (sombre, chasse fixe) parce que « project » est un de ses
mots-clés — en contradiction directe avec un registre « chaleureux et
éditorial » fraîchement déclaré. Le raccourci tentant — faire émettre au
dialogue un bloc `ui … theme:` — serait faux : ce bloc ÉPINGLE le thème, donc
rend tout écart de palette bloquant (point 48), alors que l'utilisateur a
choisi un registre, pas une palette. Une expression plus faible qu'un
épinglage reste à concevoir ; c'est la brique suivante, pas un correctif.

## 54. Le pivot a supprimé une intelligence au lieu de la déplacer

Question de l'utilisateur devant le site regénéré : « le site est tout court,
page d'accueil et Travaux, pas de section à propos, et la même couleur
partout ». Trois symptômes, une même origine pour les deux premiers.

**Ce que le contrat savait dire.** Un champ n'y était qu'un
`{nom, type, requis}`. Rien n'indiquait lequel est le titre, lequel porte
l'image de couverture, lequel n'est qu'une donnée secondaire. L'IA UI devait
redeviner depuis les noms ce que **monl savait déjà déduire** : le point 35
dérivait des archétypes d'interface (galerie, boutique) et le rôle de chaque
champ, de façon déterministe, depuis la seule spec. Le pivot du point 41 a
supprimé ce calcul avec le frontend généré — `generator/core.py` le dit noir
sur blanc, « landing, dashboard, archétypes — tous retirés » — **sans jamais
le transposer dans le contrat**. Une capacité éprouvée n'a pas été remplacée :
elle a été perdue, et c'est le modèle en aval qui a hérité du travail.

**Rétabli côté contrat, pas côté rendu.** Chaque champ visible reçoit un rôle
(`title`, `media`, `description`, `price`, `category`, `meta`), chaque entité
une forme conseillée, et le brief les énonce en clair. monl ne dessine
toujours rien : il transmet ce qu'il sait, ce qui est précisément le contrat
du pivot. Même philosophie qu'aux thèmes — dérivé de la spec, jamais déclaré
dans le DSL métier.

**Un média seul suffit à une galerie.** Le point 35 exigeait un titre ET (un
média OU une description). Une entité `photo + légende` sans champ titre — cas
banal d'un portfolio — retombait donc en liste, réduisant à une rangée de
tableau l'image qui est sa seule raison d'être. La règle est assouplie : un
média suffit.

**La lisibilité publique est une condition, pas un détail.** La première
version de la dérivation l'avait laissée tomber, et le défaut a sauté aux yeux
au premier essai : l'entité `Message` d'un formulaire de contact se voyait
conseiller « grandes vignettes en grille ». Une collection réservée aux
comptes autorisés se **gère** (tableau dense) ; seule une entité en lecture
publique se **parcourt** (vitrine). Une entité qu'on écrit sans jamais la
relire reçoit `form` : aucune vue de liste à construire.

**Ce que ce point ne corrige pas.** L'absence de section « à propos » a une
autre cause, traitée au point suivant : aucun emplacement du contrat ne peut
porter du contenu éditorial statique. monl modélise des données, pas des
pages — et un portfolio est surtout du contenu avec un peu de données.

## 55. monl modélisait des données, un site est surtout du contenu

Deuxième moitié de la réponse au point 54 : « pas de section à propos ». Il
n'y en avait pas parce qu'il ne POUVAIT pas y en avoir.

**Rien dans le contrat ne pouvait porter du texte.** Entités, champs, routes,
règles : tout y décrit des données. Une page « à propos », une présentation de
la méthode, une liste de services n'ont ni entité, ni champ, ni route d'où
naître. L'IA d'interface n'avait donc aucune matière pour construire autre
chose qu'une liste et un formulaire — et le lui reprocher n'aurait aucun sens.
Le constat vaut au-delà du cas : **un portfolio est surtout du contenu
éditorial avec un peu de données**, et monl ne savait exprimer que la seconde
moitié.

**Une section, pas un système de pages.** Le bloc `landing` accueille
désormais une clé `section` répétable — un titre, un texte :

```
landing
    brief: "portfolio de photographe"
    section "À propos": "Photographe basée à Lyon depuis 2015…"
```

Une seule règle de grammaire couvre à propos, méthode, services, mentions —
tout l'éditorial. La tentation d'un vrai modèle de pages (arborescence,
gabarits, ordre, blocs imbriqués) a été écartée : ce serait un CMS, un projet
d'une autre ampleur, alors que le besoin observé est de faire arriver du texte
jusqu'à l'IA.

**Publié tel quel, pas reformulé.** Le brief dit explicitement que ces textes
sont de l'auteur et doivent apparaître sans réécriture. Sans cette consigne,
un modèle traite volontiers un paragraphe comme une intention à réinterpréter
— alors que le `brief`, lui, EST une intention. Deux natures de texte
voisines dans le même document : les confondre produirait un « à propos »
inventé, ce qui est pire que pas d'« à propos » du tout.

**Titre et texte obligatoires.** Une section sans titre donnerait une rubrique
anonyme, une section vide un blanc dans la page. Les deux échouent à la
compilation plutôt qu'à l'écran.

**Posées seulement si un brief part.** Comme l'intention visuelle du point 53 :
sans page d'accueil à écrire, ces textes n'auraient nulle part où aller.

## 56. Cinq couleurs plates ne font pas une palette

Troisième symptôme du même signalement (points 54 et 55) : « la même couleur
partout, aucune variation ».

**Ce que le contrat livrait.** Cinq valeurs — fond, surface, texte, deux
accents. Rien d'autre. Or une interface a besoin de choses qu'aucune de ces
cinq ne fournit : un texte secondaire plus discret que le texte principal, un
filet de séparation plus léger qu'une bordure pleine, un second niveau de
surface, un fond teinté pour une étiquette, un état de survol. Faute de les
recevoir, le modèle les improvise au jugé — ou, plus souvent, s'en passe. La
mesure sur le frontend livré était nette : **un seul `rgba()`, aucun dégradé,
aucun `color-mix`**. Cinq aplats, aucune profondeur.

**Déduits, pas choisis.** Les cinq tons dérivés se calculent par mélange vers
le fond (s'éloigner du texte) ou vers le texte (s'en rapprocher), jamais par
un éclaircissement absolu — qui blanchirait un thème sombre. Le même calcul
sert donc `editorial` (fond crème) et `console` (fond presque noir).

**Après la variation, jamais avant.** Chaque projet décale la teinte de ses
accents (point 20). Dériver un survol de l'accent d'origine produirait une
nuance qui jure avec l'accent réellement affiché : les tons sont calculés en
dernier.

**Calibré sur le pire cas, pas sur la moyenne.** Le premier mélange retenu
pour le texte secondaire donnait 4,26:1 sur le fond du thème `civic` — sous
le seuil WCAG AA de 4,5:1. Une nuance proposée par le compilateur ne doit pas
rendre illisible ce qu'elle sert à hiérarchiser : la valeur a été resserrée
jusqu'à ce que **les six thèmes** passent, et un test le vérifie thème par
thème plutôt que sur un cas représentatif.

**Non vérifiés, et c'est délibéré.** Le smoke test continue de ne contrôler
que les cinq couleurs de base. Exiger la présence des tons dérivés
reproduirait le faux positif écarté au point 52 : une interface peut très bien
construire sa profondeur autrement (opacité, `color-mix`, filtres) sans que
ces six chaînes apparaissent. Ils sont une matière offerte, pas une clause.

## 57. Un contrat qui décrit mal le corps est pire qu'un contrat muet

`monl frontend` a échoué deux fois de suite sur une spec de blog :
`POST /comment avec un corps conforme au contrat a répondu 422`. Le message
disait l'essentiel sans qu'on l'entende : le corps venait DU CONTRAT, et le
serveur le refusait. Or l'en-tête de `frontend_contract.py` promet que
« contrat et API ne peuvent pas diverger ».

**Ce que le contrat oubliait.** `Comment` a deux parents : `Reader` (son
propriétaire, peuplé depuis le JWT) et `Article` (la cible du commentaire,
que seul le client peut désigner). Le générateur fait cette distinction
depuis la bêta 3 — `_client_fk_columns` — et inscrit `article_id: int` dans
le schéma Pydantic. Le contrat, lui, listait les seuls ATTRIBUTS de l'entité :
`{content}`. Tout frontend qui suivait le contrat à la lettre récoltait un
422. Un contrat muet aurait laissé l'IA lire le schéma ; un contrat faux lui
a fait croire qu'elle avait raison.

**Réutiliser, jamais réimplémenter.** Le contrat appelle désormais
`_client_fk_columns` et reproduit la clause « cible de compteur » de
`generator/schemas.py`. Même principe que `_compute_route_map` : quand deux
couches doivent s'accorder, l'une des deux appelle l'autre — deux logiques
parallèles finissent toujours par diverger, et c'est exactement ce qui s'est
produit ici.

**Le brief n'annonçait aucun corps.** Découverte au passage : la liste des
routes ne mentionnait ni champs ni corps de requête. Même corrigé, le contrat
JSON n'aurait rien changé — l'IA lit `FRONTEND_PROMPT.md`, pas le JSON.
Chaque route de création ou de mise à jour affiche maintenant son corps.

**Le vérificateur mentait aussi.** Le smoke test annonçait « un corps conforme
au contrat » tout en le construisant depuis les champs de l'entité, sans
regarder `request_fields`. Il reproduisait donc l'oubli qu'il aurait dû
détecter. Il lit désormais le contrat, et va chercher un parent RÉEL avant de
rattacher une création : les clés étrangères sont contraintes en base
(`PRAGMA foreign_keys = ON`), inventer un identifiant ferait échouer
l'insertion pour une raison étrangère au contrat. Sans parent lisible, le
chemin n'est pas éprouvé — et le dire est plus honnête que de le déclarer
vert ou rouge à tort.

**Le garde-fou qui manquait.** Un test confronte désormais, pour chaque route
de création et de mise à jour, le corps annoncé aux classes Pydantic
réellement écrites dans `app.py` — comme le point 40 le faisait déjà pour les
décorateurs de routes. La clause « corps de requête » était la dernière du
contrat que rien ne confrontait au code généré (voir point 48).

**Faux positif corrigé au passage.** L'avertissement « chemins absents du
contrat : /edit » visait `'/edit">Modifier</a>'` — la fin d'une route de
navigation `#/article/<id>/edit` coupée par une concaténation JavaScript.
Le vérificateur n'examinait que le DÉBUT du littéral ; il examine maintenant
le littéral entier et rejette ce qui contient un chevron ou une espace. Toute
application monopage déclenchait cet avertissement : crier au loup à chaque
génération décrédibilise les signaux qui, eux, sont vrais.

## 58. Rendre la main : sans épinglage, le visuel appartient à l'IA

Trois générations de suite ont rendu le même aplat crème, malgré les points 52
(polices), 54 (archétypes) et 56 (tons dérivés). La mesure a montré pourquoi,
et le diagnostic accuse la direction elle-même.

**Une palette sans surface sombre.** Des dix tons publiés, cinq passaient au
crible d'une luminance supérieure à 0,55 — et c'étaient les seuls utilisables
sur de grandes zones. Les cinq autres étaient des couleurs de TEXTE et
d'accent. Aucun bandeau contrasté, aucun hero plein, aucun pied de page dense
n'était donc composable : tout ce qui est large restait crème ou blanc, par
construction. Le point 56 a même aggravé le cas en écrivant « à employer
plutôt que d'improviser des gris » : la porte à l'invention fermée, celle du
contraste jamais ouverte.

**Le fond du problème n'était pas la palette.** On pouvait y ajouter une
surface sombre et continuer à prescrire. Le choix retenu va plus loin :
**monl cesse de prescrire le visuel dès lors que la spec ne l'épingle pas**.
Le compilateur sait des choses réelles — la structure, les rôles des champs,
le contenu éditorial, l'intention déclarée au dialogue — et il les transmet
toutes. Comment cela se regarde n'en fait pas partie ; c'est le métier du
modèle d'interface, et une direction déduite du vocabulaire des entités était
une devinette déguisée en consigne.

**Ce qui reste opposable.** Deux exigences seulement, aucune n'étant affaire
de goût : un contraste texte/fond d'au moins 4,5:1 (une interface illisible
n'est pas un parti pris), et l'autonomie du frontend — aucune ressource
distante, puisque c'est elle qui rend le smoke test possible hors ligne, donc
tout le reste vérifiable. La règle d'autonomie a été explicitement CONSERVÉE
au moment de rendre la main : elle n'est pas une contrainte esthétique.

**L'épinglage garde tous ses droits.** `ui … theme:` reste contraignant et
vérifié : quand l'auteur de la spec a tranché, il a tranché. L'asymétrie du
projet ne bouge pas — stricte sur ce qui est déclaré, désormais muette sur ce
qui n'était que deviné, au lieu de tolérante.

**Ce qu'on perd, sciemment.** Le point 20 promettait que deux applications ne
se ressembleraient jamais, garanti par une identité déterministe par projet.
Cette garantie disparaît pour les projets sans épinglage : deux sites générés
pourront se ressembler si le modèle a des habitudes. C'est le prix assumé —
une ressemblance possible entre deux projets coûte moins cher qu'une
uniformité certaine sur tous, et l'utilisateur qui veut une identité imposée
dispose d'un bloc `ui` pour le dire.

**Le vérificateur suit.** `_verifier_palette` ne contrôle plus rien en
l'absence d'épinglage. Avertir sur l'écart à une devinette poussait à
reproduire l'aplat, exactement le contraire du but recherché.
