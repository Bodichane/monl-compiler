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
[16](#16-actions-publiques-public--cas-dusage-portfolio) Actions publiques (`public`) ·
[106](#106-rôle-superviseur-au-dessus-daccessibleby-brique-23) Rôle superviseur (`accessibleBy`) ·
[107](#107-la-chaîne-de-propriété-qui-remonte-toute-la-profondeur-brique-24) Propriété transitive en profondeur (brique 24) ·
[108](#108-lémission-sql-typée-la-frontière-de-sécurité) Émission SQL typée (frontière de sécurité) ·
[109](#109-le-contrôle-daccès-sort-de-lombre-du-validateur) Le contrôle d'accès, sorti du fourre-tout du validateur ·
[110](#110-rust-évalué-par-un-spike-mesuré--et-écarté) Rust évalué par un spike mesuré, et écarté ·
[111](#111-public-requiresown-et-payable-sortent-du-fourre-tout) `public`, `requiresOwn` et `payable` sortent du fourre-tout ·
[112](#112-restrictedto-jamais-validé-structurellement) `restrictedTo` jamais validé structurellement ·
[113](#113-le-verrou-de-paiement-bloquait-aussi-le-superviseur-et-personne-ne-le-savait) Le verrou de paiement bloquait aussi le superviseur ·
[114](#114-le-point-113-fermé-sur-les-deux-sites-et-un-trou-quil-avait-laissé) Point 113 adopté sur les deux sites, et son propre trou refermé ·
[115](#115-brique-26--monl-content-exportimport-le-contenu-en-masse) Brique 26 : `monl content export`/`import`, le contenu en masse ·
[116](#116-briques-27-et-28--publicwhen-et-onceper-livrées-sans-leurs-garde-fous) Briques 27 et 28 : `publicWhen` et `oncePer`, livrées sans leurs garde-fous ·
[117](#117-la-colonne-du-compteur-avait-deux-sources-et-lordre-des-relations-tranchait) La colonne du compteur avait deux sources, et l'ordre des relations tranchait ·
[118](#118-le-backend-savait-tout-faire-sauf-se-déployer) Le backend savait tout faire sauf se déployer ·
[119](#119-la-couche-données-choisit-son-dialecte-au-démarrage) La couche données choisit son dialecte au démarrage ·
[120](#120-les-migrations-non-additives-sont-nommées-et-refusent-le-démarrage) Migrations non additives nommées ·
[121](#121-le-fichier-déposé-par-le-client-est-un-upload-pas-une-image) Le fichier déposé par le client est un `Upload`, pas une `Image`
[122](#122-monl-sait-envoyer-un-message-sans-promettre-sa-remise) Envoi de message sans promettre sa remise ·
[123](#123-filtrer-et-trier-sans-inventer-un-langage-de-requête) Filtrer et trier sans inventer un langage de requête ·

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
[58](#58-rendre-la-main--sans-épinglage-le-visuel-appartient-à-lia) Rendre la main : sans épinglage, le visuel appartient à l'IA ·
[59](#59-où-vit-un-contenu-et-à-quoi-ressemblent-les-images-de-démonstration) Où vit un contenu, et à quoi ressemblent les images de démonstration ·
[60](#60-ce-qui-est-standard-nest-pas-une-question) Ce qui est standard n'est pas une question ·
[61](#61-demander-le-texte-dune-rubrique-plutôt-que-son-existence) Demander le texte d'une rubrique plutôt que son existence ·
[62](#62-un-budget-épuisé-nest-pas-une-panne) Un budget épuisé n'est pas une panne ·
[63](#63-mesurer-le-dépôt-pas-seulement-le-faire-passer-au-vert) Mesurer le dépôt, pas seulement le faire passer au vert ·
[64](#64-ce-qui-traverse-mal-la-frontière-et-ce-que-personne-ne-mesurait) Ce qui traverse mal la frontière, et ce que personne ne mesurait ·
[65](#65-un-paquet-quon-ne-peut-pas-installer-nest-pas-un-paquet) Un paquet qu'on ne peut pas installer n'est pas un paquet ·
[66](#66-rendre-public-ne-pardonne-pas-les-exceptions-à-ses-propres-règles) Rendre public ne pardonne pas les exceptions à ses propres règles ·
[67](#67-un-test-qui-échoue-une-fois-sur-deux-est-pire-quun-test-absent) Un test qui échoue une fois sur deux est pire qu'un test absent ·
[68](#68-une-démo-qui-versionne-sa-propre-sortie-se-contredit) Une démo qui versionne sa propre sortie se contredit ·
[69](#69-le-garde-fou-ne-doit-pas-dépendre-de-qui-écrit) Le garde-fou ne doit pas dépendre de qui écrit ·
[70](#70-compiler-nest-pas-se-comporter-et-le-câblage-ne-se-relit-pas) Compiler n'est pas se comporter, et le câblage ne se relit pas ·
[71](#71-ce-que-le-compilateur-refuse-nétait-presque-pas-mesuré) Ce que le compilateur refuse n'était presque pas mesuré ·
[72](#72-le-compilateur-na-pas-davis-sur-le-visuel) Le compilateur n'a pas d'avis sur le visuel ·
[73](#73-un-agent-qui-ne-touche-à-rien-a-quand-même--construit-) Un agent qui ne touche à rien a quand même « construit » ·
[74](#74-encaisser-et-le-montant-qui-ne-vient-jamais-du-client) Encaisser, et le montant qui ne vient jamais du client ·
[75](#75-payable-accessible-depuis-le-dialogue-et-deux-trous-que-lassemblage-a-montrés) `payable` accessible depuis le dialogue, et deux trous que l'assemblage a montrés ·
[76](#76-un-champ-que-lapi-renvoie-et-que-le-contrat-taisait) Un champ que l'API renvoie et que le contrat taisait ·
[77](#77-le-montant-venait-bien-de-la-base--et-cest-le-client-qui-lavait-écrit) Le montant venait bien de la base — et c'est le client qui l'avait écrit ·
[78](#78-derivedfrom-et-le-champ-serveur-que-la-route-update-réécrivait) `derivedFrom`, et le champ serveur que la route Update réécrivait ·
[79](#79-le-refus-cassant--une-boutique-quon-peut-voler-ne-doit-pas-compiler) Le refus cassant : une boutique qu'on peut voler ne doit pas compiler ·
[80](#80-le-propriétaire-est-un-compte-et-le-panier-qui-la-révélé) Le propriétaire est un compte, et le panier qui l'a révélé ·
[81](#81-la-propriété-transitive--quand-le-contrôle-daccès-devient-une-jointure) La propriété transitive : quand le contrôle d'accès devient une jointure ·
[82](#82-le-panier-qui-sait-ce-quil-coûte-et-la-faille-du-point-77-arrêtée-à-lentrée) Le panier qui sait ce qu'il coûte, et la faille du point 77 arrêtée à l'entrée ·
[83](#83-monl-ne-savait-pas-quun-fichier-existe--le-type-image-et-le-bloc-assets) monl ne savait pas qu'un fichier existe : le type `Image` et le bloc `assets` ·
[84](#84-loutil-qui-écrit-dans-la-spec-et-la-garantie-quil-fallait-énoncer-juste) L'outil qui écrit dans la spec, et la garantie qu'il fallait énoncer juste ·
[85](#85-les-quatre-règles-qui-ne-faisaient-rien) Les quatre règles qui ne faisaient rien ·
[86](#86-décompter-ce-que-le-client-a-demandé-et-le-plancher-qui-larme) Décompter ce que le client a demandé, et le plancher qui l'arme ·
[87](#87-encaisser-une-ligne-et-le-refus-qui-protégeait-dautre-chose-que-ce-quil-disait) Encaisser une ligne, et le refus qui protégeait d'autre chose que ce qu'il disait ·
[88](#88-le-back-office-et-les-deux-mensonges-quil-a-fait-tomber) Le back-office, et les deux mensonges qu'il a fait tomber ·
[89](#89-la-date-que-personne-ne-peut-se-donner-et-la-colonne-quon-ne-rattrape-pas) La date que personne ne peut se donner, et la colonne qu'on ne rattrape pas ·
[90](#90-on-ne-commande-pas-sans-être-identifié) On ne commande pas sans être identifié ·
[91](#91-ce-quon-a-encaissé-ne-se-remodifie-plus) Ce qu'on a encaissé ne se remodifie plus ·
[92](#92-le-stock-qui-ne-revenait-jamais-et-la-variable-qui-fuyait) Le stock qui ne revenait jamais, et la variable qui fuyait ·
[93](#93-retoucher-sans-reconstruire) Retoucher sans reconstruire ·
[94](#94-une-faq-est-une-liste-et-le-contenu-que-le-delta-ne-regardait-pas) Une FAQ est une liste, et le contenu que le delta ne regardait pas ·
[95](#95-sinscrire-avec-son-adresse-et-la-forme-canonique-qui-porte-la-brique) S'inscrire avec son adresse, et la forme canonique qui porte la brique ·
[96](#96-un-statut-nest-pas-du-texte-et-la-fiche-quon-pouvait-effacer) Un statut n'est pas du texte, et la fiche qu'on pouvait effacer ·
[97](#97-le-message-qui-devinait-à-la-place-de-lagent) Le message qui devinait à la place de l'agent ·
[98](#98-annuler-rend-les-paires-et-la-transition-quon-ne-joue-quune-fois) Annuler rend les paires, et la transition qu'on ne joue qu'une fois ·
[99](#99-le-rattachement-fantôme-et-la-sécurité-qui-nétait-quun-accident) Le rattachement fantôme, et la sécurité qui n'était qu'un accident ·
[100](#100-une-vitrine-qui-montre-des-enfants-et-la-désignation-qui-se-lit) Une vitrine qui montre des enfants, et la désignation qui se lit ·
[101](#101-le-type-frère-resté-debout-dix-points-de-plus) Le type frère, resté debout dix points de plus ·
[102](#102-le-numéro-que-lhumain-lit-et-dicte) Le numéro que l'humain lit et dicte ·
[103](#103-voir-le-delta-avant-décrire) Voir le delta avant d'écrire ·
[104](#104-les-icônes-quon-croyait-interdites) Les icônes qu'on croyait interdites ·
[105](#105-deux-messages-qui-envoyaient-corriger-ce-qui-nétait-pas-cassé) Deux messages qui envoyaient corriger ce qui n'était pas cassé

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

## 59. Où vit un contenu, et à quoi ressemblent les images de démonstration

Deux reproches d'usage après la remise de main du point 58, tous deux
imputables à ce que le contrat NE DIT PAS.

**« L'à propos n'apparaît pas sur la page principale. »** Il était pourtant
bien là — sur une route à part, `#/apropos`, atteignable par le seul menu. Le
point 55 disait quoi publier, jamais OÙ. Or un visiteur qui n'ouvre que
l'accueil ne voyait jamais ce texte : pour un « à propos », c'est manquer sa
raison d'être. Même défaut que le formulaire de contact relégué en vue
séparée quelques essais plus tôt — l'IA choisit une application à vues, et
tout ce qui n'est pas la liste principale disparaît de la page d'accueil.
Le brief exige désormais la présence AU FIL de l'accueil, en autorisant une
version courte prolongée par une page dédiée : la contrainte porte sur la
présence, pas sur la longueur.

**« Fais en sorte que les images soient plus précises. »** Deux défauts
distincts se cachaient derrière la même phrase, et la mesure les a séparés.

*Netteté.* Les seeds servaient du 800×600. Un hero occupe toute la largeur
d'un conteneur d'environ 1120 px, doublée sur un écran haute densité : la
source était agrandie près de trois fois, donc molle. Les images de
démonstration sont passées en 1600×900 — format qui correspond aussi mieux
aux proportions d'un hero ou d'une carte que le 4:3 d'origine.

*Pertinence.* `picsum.photos` ne rend que des photos arbitraires : un blog de
cybersécurité s'illustrait de paysages. Le sujet ne se déduit pas de la
description — « Blog pour des experts en cyber » est une phrase libre, en
français, dont extraire un mot-clé d'illustration relèverait de
l'interprétation, ce que le dialogue s'interdit depuis le point 40. Il le
DEMANDE donc, et n'émet la question que si des données de démonstration sont
réellement produites. Le service retenu (`loremflickr`) accepte un mot-clé ;
son paramètre `lock` fige le tirage, sans quoi chaque rechargement changerait
l'image et le rendu cesserait d'être reproductible.

**Le catalogue ne peut pas connaître le sujet.** Les modèles d'applications
sont chargés avant le dialogue : leurs URL d'illustration sont écrites sans
savoir de quoi parlera le projet. Elles sont donc réécrites à l'émission de
la spec, une fois le mot-clé connu — plutôt que de dupliquer la logique
d'image dans chacun des dix modèles.

## 60. Ce qui est standard n'est pas une question

Deux demandes liées : alléger le dialogue, et donner à l'IA de quoi
« ressembler à des sites similaires ». Les recensements publics de ce que
contient une page de chaque type ont servi de source aux deux.

**Une question dont la réponse est toujours « oui » n'est pas une question.**
Le catalogue posait seize questions de suivi. Confrontées aux listes
d'essentiels de leur catégorie, huit décrivaient des éléments que personne ne
refuse : le moyen de contact d'un portfolio, la date d'un article, la
disponibilité d'un produit, la priorité et l'échéance d'une carte kanban, le
lieu et le contact vendeur d'une annonce, la description d'une prestation.
Les demander faisait porter à l'utilisateur un choix qui n'en est pas un — et,
pire, produisait par défaut des applications amputées de l'évident, puisque le
parcours « tout refuser » est un chemin réel, éprouvé par la CI. Elles sont
devenues des acquis du modèle. Huit questions restent, celles qui tranchent
vraiment : catégories, commentaires, likes, fournisseurs, seuil d'alerte.

**Un manque révélé par la même source.** Le modèle Blog n'avait pas de champ
`author`, alors que la signature figure dans toutes les anatomies d'article —
elle est ce qui distingue un billet d'une page institutionnelle. Ajoutée.

**Ce que le contrat ne disait pas : à quoi ressemble une page de ce genre.**
Il annonçait les données disponibles, jamais les attentes que l'on a en
arrivant sur une galerie, une fiche produit ou un tableau de gestion. Or deux
sites du même genre se ressemblent précisément parce qu'ils répondent aux
mêmes attentes. Chaque archétype porte donc désormais, dans le brief, ce qu'un
visiteur s'attend à y trouver et de quoi cette page est voisine. C'est un
repère, pas une maquette : après le point 58, monl ne prescrit plus de forme —
il décrit un genre, et laisse le modèle le traiter.

**La disponibilité n'est pas une donnée secondaire.** Le champ `stock` se
voyait attribuer le rôle « méta », donc traité comme un détail de bas de
fiche, alors qu'il figure au-dessus de la ligne de flottaison d'une fiche
produit, au même rang que le prix. Il a son rôle propre.

**Limite de la méthode.** Trois modèles — inventaire, dépenses, forum — n'ont
pas été confrontés à une source : leurs questions restent en l'état. Décider
sans mesure y aurait été du même ordre que ce que ce point corrige.

Sources principales consultées : recensements d'éléments de fiche produit
(Qikify, VWO, Martech Zone), d'anatomie d'article (Equinet, HubSpot),
d'essentiels de portfolio (Fueler, Pixpa), de carte kanban (Asana, Wrike,
ClickUp), de page de réservation (Microsoft Bookings, Trafft) et de petites
annonces (aDirectory, RadiusTheme).

## 61. Demander le texte d'une rubrique plutôt que son existence

Suite directe du point 60, appliquée cette fois au **contenu éditorial** et
non plus aux champs. Même méthode : confronter chaque modèle du catalogue aux
recensements publics de ce que contient une page de son genre.

**Le point 55 avait ouvert la porte, le dialogue la refermait.** Le bloc
`landing` sait porter des sections depuis le point 55, mais le dialogue les
introduisait par une question o/n générique — « ajouter du texte de
présentation ? » — suivie d'un formulaire vide : titre, puis texte. Trois
défauts cumulés. La question porte sur quelque chose que personne ne refuse
sur un site vitrine. Le parcours « tout refuser », éprouvé par la CI, produit
donc un portfolio **sans à propos** — exactement l'amputation que le point 60
corrigeait ailleurs. Et l'utilisateur qui accepte se retrouve devant une page
blanche : à lui de deviner quelles rubriques un site de son genre comporte,
alors que la réponse est publique et documentée.

**Chaque modèle porte donc ses rubriques attendues, et le dialogue en demande
le TEXTE.** Le portfolio ne demande plus s'il faut un à propos : il demande
« À propos — qui vous êtes, depuis quand, ce qui distingue votre travail ».
Le titre est acquis, l'intitulé dit ce qu'on attend dedans, seul le contenu
est demandé. Rubriques retenues, une source par ligne :

| Modèle | Rubriques | Ce que la source donne pour acquis |
|---|---|---|
| Portfolio | À propos, Services | « about » et une offre lisible figurent dans tous les essentiels de portfolio |
| Blog | À propos de l'auteur, Ligne éditoriale | la bio est la page centrale d'un site d'écriture ; la ligne éditoriale dit au lecteur s'il est au bon endroit |
| Boutique | À propos, Livraison et retours, FAQ | livraison/retours et FAQ sont placés au-dessus du reste : ils lèvent les objections d'achat |
| Forum | À propos, Règles de la communauté | des règles écrites et visibles depuis l'accueil sont le premier levier de modération |
| Petites annonces | Comment ça marche, Conseils de sécurité | une place de marché entre particuliers doit dire ce qu'elle prend en charge et ce qu'elle laisse aux deux parties |
| Réservation | À propos, Horaires et accès, Politique d'annulation | la politique d'annulation doit figurer **avec** le formulaire, pas dans un coin |
| Classement | À propos, Comment fonctionne le vote | un classement n'est crédible que si la règle du vote est écrite (qui vote, combien de fois, comment on départage) |

**Vide passe la rubrique.** Le standard est proposé, jamais imposé : une
réponse vide n'écrit pas la section. C'est la différence avec le point 60, où
l'acquis est un champ que l'utilisateur ne voit plus — ici il voit la
proposition et peut la refuser d'une touche. Un texte, contrairement à un
champ, ne peut pas être fourni par défaut : personne d'autre que l'auteur ne
sait ce qu'il y a à dire, et l'inventer serait exactement le « à propos
inventé » que le point 55 écartait.

**Trois modèles n'en reçoivent aucune, délibérément.** Kanban, inventaire,
dépenses sont des outils internes : ils s'ouvrent sur un tableau, pas sur une
page d'accueil, et aucune source ne donne de rubrique attendue pour un écran
sans visiteur à convaincre. Ils retombent sur l'offre générique historique.
Leur inventer un « à propos » aurait été décider sans mesure — la limite déjà
posée au point 60.

**Ce que les tests figent.** Que les invites réellement posées nomment chaque
rubrique du modèle (le test lit les prompts, il ne relit pas le code) ; que
l'ancienne question o/n ait disparu là où des rubriques existent ; qu'une
rubrique laissée vide soit absente de la spec ; et que les trois outils
internes n'en portent aucune. Les deux parcours de bout en bout du catalogue
(tout refuser / tout accepter) traversent désormais ces questions et
recompilent la spec produite.

Sources principales consultées : essentiels de portfolio (Fueler, Portfolio
Studio, Prismic), sites d'auteur et pages de bio (Tertulia, SCBWI,
ProductiveShop), homepage et FAQ e-commerce (ConvertCart, Smith.ai,
StoreYa), lignes directrices de communauté (Hivebrite, Later, Guild),
sécurité des petites annonces (ConnectingDeals, FasterCapital), politiques
d'annulation (Acuity, Square, vcita, Microsoft Bookings) et règles de
concours à vote communautaire (AmusementRating, MLB).

## 62. Un budget épuisé n'est pas une panne

Signalé en usage réel, sur le projet StudioNova : `monl frontend
--provider claude-code` s'arrête sur `Error: Reached max turns (40)`, sans
frontend et sans diagnostic.

**Le chiffre avait vieilli.** 40 tours ont été posés quand le brief tenait en
quelques lignes. Depuis, il porte l'intention visuelle (point 53), les
attentes d'archétype (point 60) et les rubriques éditoriales (points 55 et
61) : un frontend réel se construit fichier par fichier, chacun coûtant un
tour, et le budget s'épuisait AVANT que `index.html` n'existe. Relevé à 120,
et exposé en `--max-turns` — un site à trois rubriques ne coûte pas ce que
coûte un catalogue, et figer une valeur unique reproduirait la même dette.

**Le code de sortie mentait sur ce qui s'était passé.** L'orchestrateur
traitait tout retour non nul comme une panne d'exécution et remontait une
`FrontendAIError`, qui interrompt la commande. Or l'agent peut très bien
avoir écrit un frontend complet au 39e tour et dépasser au 40e : le travail
était jeté sans jamais être regardé, alors que la vérification (cohérence +
smoke test) existait précisément pour trancher sur pièces. Le dépassement de
budget est donc devenu un avertissement — le frontend produit, s'il existe,
est vérifié comme n'importe quel autre ; s'il n'existe pas, l'échec emprunte
la boucle de correction au lieu d'arrêter net.

**Le relâchement s'arrête là, et c'est testé.** Une panne d'authentification,
un binaire absent, un plantage : tout ce qui n'est pas un dépassement de
budget continue d'interrompre. La distinction se lit dans la sortie de
l'agent, pas dans le code de retour — seul `max turns` est reconnu. Trois
tests couvrent les trois cas (budget épuisé avec frontend valide, budget
épuisé sans rien produire, vraie erreur), chacun avec un exécutable factice :
l'orchestration s'exécute pour de vrai, seul l'agent est simulé.

## 63. Mesurer le dépôt, pas seulement le faire passer au vert

137 tests qui passent disent qu'aucune régression connue n'est revenue. Ils
ne disent ni ce qui n'est pas couvert, ni si les frontières d'architecture
tiennent encore, ni si un avertissement traîne depuis six mois. Trois outils
ont été retenus, un par question — et un quatrième écarté.

**Ruff, avec un jeu de règles choisi.** Le catalogue complet crie sur du code
délibéré ; un linter qu'on apprend à ignorer ne vaut pas mieux que pas de
linter (point 48, encore). D'où un `select` restreint et, surtout, des
exceptions QUI PORTENT LEUR RAISON : les caractères « ambigus » sont la
langue du projet ; les lignes vides à espaces de `parser.py` sont à
l'intérieur du littéral de grammaire Lark, et y toucher modifierait le texte
analysé ; les imports en milieu de `frontend_ai.py` sont groupés par voie
(API, Claude Code, import). 152 signalements au départ, 103 corrigés
mécaniquement, **zéro restant** — donc tout nouveau signalement est un vrai.

**Deux défauts réels trouvés, pas du style.** `apply_effects` enrichissait les
lignes de seed avec `zip()` : un modèle qui fournirait deux valeurs pour trois
lignes aurait produit, en silence, une ligne à qui il manque un champ que les
autres ont. `strict=True` en fait une erreur immédiate. Et une exception de
lecture JSON était relancée sans sa cause, ce qui coupait la trace au moment
précis où l'on cherche pourquoi le modèle a rendu du texte illisible.

**La couverture chiffre un manque déjà connu.** 82 % au total. Le point bas
est `cli.py` à 35 %, en partie parce que plusieurs de ses chemins ne sont
éprouvés qu'à travers des sous-processus, que l'instrument ne suit pas. Et la
mesure confirme l'avertissement de `CLAUDE.md` : **`rule … hidden` n'apparaît
dans aucun test ni aucun exemple** — une régression y passerait sans bruit.

**Les frontières deviennent un test, pas une dépendance.** import-linter était
le meilleur choix sur le papier ; il exige des paquets, or `src/` est plat
pendant toute la bêta (chantier GA assumé). Plutôt que de tordre
l'arborescence pour un outil, `tests/test_architecture.py` construit le graphe
d'imports avec `ast` — **imports en tête de fichier ET dans les fonctions**,
puisque c'est là que les dépendances interdites se cachent — et vérifie six
contrats énoncés depuis toujours dans `CLAUDE.md` : le compilateur ignore
l'orchestrateur, le catalogue est de la donnée, la présentation ne connaît pas
le moteur. Ils tiennent tous. Le seul cycle du dépôt, `cli ↔ frontend_ai`, est
déclaré comme connu : le test échouera sur le suivant, pas sur celui-là.

**Sans CI, rien de tout cela ne survit.** Le dépôt n'avait aucun workflow :
tout reposait sur la discipline de lancer les commandes. `.github/workflows/
ci.yml` joue ruff puis la suite complète avec couverture, sur la borne basse
déclarée (3.10) et une version récente.

**Écartés, et pourquoi.** `pydeps` et `pyreverse` exigent graphviz, retiré de
la machine — et la carte du code rend déjà ce service. `mutmut` (tests des
tests) est le prochain palier logique, mais il fait tourner la suite des
dizaines de fois : à ouvrir quand elle sera plus rapide, pas avant.

## 64. Ce qui traverse mal la frontière, et ce que personne ne mesurait

Quatre corrections issues du même mouvement : appliquer les outils du point 63
plutôt que de se contenter de les installer.

**Un texte n'est pas une ligne.** Les rubriques éditoriales (point 61)
arrivaient jusqu'à l'IA, mais aplaties : un « à propos » collé depuis un
traitement de texte y perdait ses paragraphes, recollés sans même une espace
(« …8 ans.Mon travail… »), et une liste numérotée perdait sa structure. Le
retour à la ligne reste interdit — il casserait le `STRING_LITERAL` émis, et
assouplir la grammaire pour ça reviendrait à faire porter au langage un
problème de saisie. Le dialogue demande donc **un paragraphe par saisie**,
ligne vide pour terminer, et joint le tout par un séparateur (`¶`) qui
n'existe QUE dans la spec : `frontend_contract.paragraphes()` le retraduit en
vrais sauts. Une spec écrite à la main, ou antérieure à ce point, traverse
inchangée — le marqueur est un ajout, pas un format.

**Une règle du langage que rien n'éprouvait.** `rule Entite.champ hidden`
(brique 2) n'apparaissait dans aucun test ni aucun exemple depuis la bêta 3.
`tests/test_masquage_hidden.py` la confronte à un vrai serveur : le champ
disparaît de la liste ET du détail, pour l'appelant connecté comme pour
l'anonyme, tout en restant écrivable et bien présent en base — vérifié par
lecture SQLite directe, pas par une réponse d'API qui pourrait mentir de la
même façon. La règle tient. Ce n'est plus une supposition.

**La suite de tests salissait le dépôt qu'elle vérifiait.**
`tests/test_compile_all.py` compilait dans la RACINE : chaque exécution y
redéposait `app.py`, `schema.sql`, `sandbox_ai.py`, `manage.py` et
`.jwt_secret` — et le rituel de nettoyage de `CLAUDE.md` existait pour ça. Le
générateur accepte un `output_dir` depuis toujours ; il est désormais employé.
Effet de bord utile : un artefact trouvé ne peut plus être le reliquat d'une
compilation précédente, donc l'assertion vaut vraiment quelque chose.

**« app.py reste scellé » n'était mesuré par rien.** Découvert en écrivant le
premier test du parcours de commandes, pas en relisant le code :
`check_coherence` vérifiait l'empreinte de la spec et celle du contrat, mais
seulement l'EXISTENCE de `app.py` et `schema.sql`. Une retouche manuelle
passait donc sans un mot — pendant que `monl run` affichait « Cohérence
statique vérifiée (spec ↔ backend ↔ contrat ↔ frontend) ». L'état
(`monl.json`) porte maintenant l'empreinte des quatre artefacts scellés
(`app.py`, `schema.sql`, `sandbox_ai.py`, `manage.py` — les deux derniers
portent des droits). Un projet compilé avant ce point n'est pas en erreur : il
est muet, et le dire vaut mieux que laisser croire à une vérification qui n'a
pas eu lieu.

**Ce que ça dit de la méthode.** Le trou du scellé n'a pas été trouvé par la
mesure de couverture, ni par le linter, ni par la relecture : il est apparu en
écrivant l'assertion « une retouche manuelle doit être détectée », qui a
échoué. Écrire un test, c'est formuler une promesse — et c'est là qu'on
s'aperçoit qu'elle n'était pas tenue.

## 65. Un paquet qu'on ne peut pas installer n'est pas un paquet

Le chantier repoussé depuis la bêta 3, fait ici parce qu'il bloquait tout le
reste : outillage, distribution, et la crédibilité du mot « installable ».

**Ce que la structure plate coûtait vraiment.** `src/` contenait dix modules
de premier niveau. Rien ne les rendait importables : chaque fichier de tests
ouvrait sur un `sys.path.insert` suivi d'imports marqués `noqa: E402`, `cli.py`
en faisait autant pour lui-même, et l'installation passait par un shim
(`run_monl.py`) dont le seul rôle était de rejouer cette manipulation. Vingt
fois la même incantation, un ordre d'instructions à respecter sous peine
d'`ImportError`, et un `pip install` qui ne donnait pas vraiment un paquet.
Trois conséquences en cascade : import-linter inutilisable (il exige des
paquets), distribution impossible, et un `parser.py` de premier niveau qui
entrait en concurrence avec le nom d'un module de la bibliothèque standard.

**Le code vit désormais dans `src/monl/`**, les dépendances internes s'écrivent
en relatif (`from .parser import …`), `pip install -e .` fournit la commande
`monl`, et `import monl` fonctionne depuis n'importe quel dossier. Les tests
importent `monl.xxx` ; la seule incantation restante est concentrée dans
`tests/conftest.py`, pour le cas où la suite tourne sans installation.

**Le piège du déménagement, et pourquoi il aurait été invisible.** Le test des
frontières (point 63) lit le graphe d'imports avec `ast` en ignorant les
imports relatifs — ce qui était juste quand « relatif » ne désignait que
l'intérieur de `generator/`. En passant tout le code en paquet, TOUTES les
dépendances internes sont devenues relatives : le test aurait continué à
passer en ne regardant plus rien. Il connaît maintenant l'étage de chaque
fichier (`from .parser` dans `monl/` désigne un module de premier niveau, le
même écrit dans `monl/generator/` désigne un voisin du sous-paquet), et un
test supplémentaire vérifie que le graphe voit encore les dépendances connues
du dépôt. **Un garde-fou muet est pire qu'un garde-fou absent : il rassure.**

**Le dossier de sortie par défaut était faux depuis toujours.** Le générateur
déduisait sa racine de l'emplacement de son propre fichier — deux niveaux
au-dessus de `src/generator/`. Tant que le code vivait dans le dépôt, ça
tombait sur la racine et faisait illusion ; une fois monl installé, le même
calcul aurait écrit l'application au milieu de `site-packages`. C'est
désormais le dossier courant, ce qu'attend n'importe quel outil en ligne de
commande — et ce qui coïncide avec l'ancien comportement quand on lance depuis
la racine du dépôt.

**Vérifié pour de vrai**, conformément à la méthode : `pip install -e .`, puis
`monl compile` lancé depuis un dossier temporaire hors du dépôt, qui produit
une application complète là où on l'appelle. La CI le rejoue à chaque push —
un dépôt vert dont le `pip install` échoue n'est utilisable que par son
auteur.

## 66. Rendre public ne pardonne pas les exceptions à ses propres règles

Le dépôt est passé en public. Deux choses l'attendaient.

**Un secret versionné.** `.jwt_secret` est généré en permissions 0600 et ignoré
par git depuis toujours — mais celui de `demo/` avait échappé à la règle,
committé en même temps que le dossier de démonstration dont la suite de tests
dépend. Sa portée réelle est faible (rien n'est déployé), sa portée symbolique
ne l'est pas : le projet traitait comme sensible un fichier qu'il publiait.
Retiré du suivi, avec `demo/app.db` qui l'accompagnait — une base contenant un
compte, son hash de mot de passe et trois lignes de limitation de débit. Les
deux se régénèrent au premier démarrage ; vérifié en les retirant du disque
avant de rejouer les tests de `demo/`, qui passent sans eux.

**L'historique n'est pas réécrit, et c'est un choix.** Le secret d'une démo
locale ne justifie pas de casser tous les clones existants. La règle
générale reste l'inverse : un secret réel exige la réécriture ET sa
révocation, parce que retirer un fichier ne retire rien de l'historique.

**Une CI qui ne se déclenchait jamais.** Le workflow n'écoutait que `main` et
les pull requests — donc pousser une branche de travail ne lançait rien, et la
page Actions restait vide en donnant l'illusion d'un dépôt sans intégration
continue. Il écoute désormais toutes les branches. Les pull requests rejouent
la même chose une seconde fois : doublon assumé, le retour immédiat vaut mieux
que l'élégance du graphe d'exécutions.

## 67. Un test qui échoue une fois sur deux est pire qu'un test absent

Première vraie leçon de la CI : `verifier (3.12)` a échoué deux fois de suite
sur la branche `readme`, puis le même code est passé au troisième essai. 3.10
passait à chaque fois. **Aucun changement de code entre les trois** — la
branche ne touchait que de la documentation.

**Ce n'était donc pas une incompatibilité de version, mais un test instable.**
Et c'est plus grave qu'un bug franc : dans une CI devenue bloquante, un test
qui échoue une fois sur deux apprend à relancer jusqu'au vert. L'habitude prise,
la protection ne protège plus rien — elle ne fait que retarder les fusions.

**Le coupable : une mesure de temps sur une machine partagée.** Le test du canal
temporel (`/login` ne doit pas trahir l'existence d'un compte par son temps de
réponse) comparait deux mesures HTTP à la moitié du coût d'un hachage PBKDF2.
Chez le mainteneur, machine calme, l'écart est net. Sur un runner GitHub —
machine virtuelle mutualisée, voisins bruyants, préemption — une seule
interruption d'ordonnancement pendant les deux mesures d'un groupe suffit à
faire exploser l'écart mesuré.

**Ce qu'il ne fallait surtout pas faire : élargir le seuil.** C'est la
correction réflexe, et elle rend le test aveugle à la fuite qu'il surveille —
un canal temporel exploitable, précisément ce qui avait été corrigé en bêta 3.
Un test qu'on desserre jusqu'à ce qu'il passe ne teste plus rien.

**Ce qui a été fait à la place**, sans toucher à ce qui est prouvé :
- **cinq échantillons par groupe** au lieu de deux, en retenant le minimum — le
  bruit ne peut qu'AJOUTER du temps, jamais en retirer ;
- **la mesure entière rejouée jusqu'à trois fois**, l'échec n'étant déclaré que
  si les trois tours dépassent le seuil. Une vraie fuite temporelle est
  systématique : elle se reproduit à chaque tour. Le bruit, non ;
- le **quota vidé entre les groupes** (5 tentatives / 60 s, persistées en base
  depuis le point 33) : le test se limitait à cinq mesures faute de pouvoir en
  prendre davantage. Effacer une table de compteurs côté banc d'essai
  n'affaiblit rien du produit.

**Un second défaut, trouvé en chemin.** Le serveur de ce test était démarré à la
main et arrêté par une ligne placée APRÈS les mesures : tout échec d'assertion
laissait un `uvicorn` orphelin et un dossier temporaire derrière lui, sur une
machine qui allait en enchaîner d'autres. Un test instable qui fuit un
processus contamine les suivants, et l'échec d'après n'a plus aucun rapport
avec sa cause. Passé sous `try/finally`.

**Ce que l'épisode dit de l'outillage.** Le diagnostic a été fait sans lire les
journaux : `gh` n'est pas installé sur la machine du mainteneur, et l'API
GitHub refuse les logs sans authentification. Restaient les métadonnées
publiques — quel job, quelle étape, quel verdict — qui suffisaient à établir
l'essentiel : l'étape en échec était la suite de tests, 3.10 passait, le run
suivant était vert. **Savoir qu'un échec est intermittent vaut déjà la moitié
du diagnostic.**

## 68. Une démo qui versionne sa propre sortie se contredit

Deux corrections d'un même geste : ce que le dépôt montre de lui-même.

**`demo/` versionnait le code que monl-compiler génère.** `app.py`, `schema.sql`,
`manage.py`, `sandbox_ai.py`, `monl.json`, le contrat, le brief, le wrapper de
service : neuf fichiers dérivés, committés à côté de la spec dont ils
découlent. Dans un projet dont toute la thèse est « la spécification est
l'unique source de vérité, on ne maintient pas le code produit », c'est une
contradiction affichée en page d'accueil du dépôt.

**Et le README du dossier affirmait déjà le contraire** — « ce dossier ne
contient que ce qui fait foi ». Personne ne l'avait vérifié. Même motif qu'au
point 64 : une promesse écrite que rien ne mesure finit par devenir fausse
sans que personne ne s'en aperçoive.

**La preuve du dommage était là.** Le contrat livré dans `demo/` datait
d'avant les points 51, 52 et 56 : il annonçait encore une URL absolue avec un
port codé en dur, une police à télécharger, et aucun ton dérivé. Un lecteur
qui l'aurait pris pour référence aurait construit contre un contrat périmé.
Du code généré versionné ne prévient pas quand il devient faux.

**Ne restent que `spec.ml` et `frontend/`** — l'écrit humain et l'écrit de
l'IA, les deux seules choses qu'aucune recompilation ne peut reproduire. Les
tests, eux, n'ont rien perdu : ils compilaient DÉJÀ dans un dossier temporaire
à partir de ces deux entrées. Les neuf autres fichiers n'étaient utiles à
personne.

**La démo change de projet : AtelierVélo cède la place à StudioNova.** Un
portfolio de photographe, dont le frontend a été écrit par Claude Code contre
le contrat, en conditions réelles. Ce changement a un effet secondaire qu'il
fallait choisir plutôt que subir : l'ancienne démo épinglait un thème, et un
test s'en servait pour prouver qu'un frontend livré respecte une palette
imposée. StudioNova n'épingle rien — et son IA s'est autorisé une palette
sombre entièrement différente de celle qui lui était proposée.

Le test n'a donc pas été supprimé, il a été **retourné** : il prouve désormais
la moitié la moins intuitive du point 58, sur un livrable réel. Qu'un
compilateur INTERDISE quelque chose se vérifie facilement ; qu'il se TAISE
quand il n'a rien à dire est beaucoup plus rare à tester — et c'est
précisément ce qui distingue une direction de design proposée d'une direction
imposée. La contrainte, elle, reste éprouvée sur un frontend construit pour
l'occasion, juste à côté.

**Les exemples restent, mais disent enfin ce qu'ils sont.** `exemples/` ne
contient pas cinq applications : il contient les cinq fichiers `.ml` qui
suffisent à les décrire — la seule chose écrite à la main. Un `README.md` le
dit maintenant en première ligne, avec ce que chaque spécification démontre du
langage. Un lecteur qui croit ouvrir des applications passe à côté de la thèse
du projet.

---

## 69. Le garde-fou ne doit pas dépendre de qui écrit

Demande du mainteneur : « je veux qu'on puisse utiliser n'importe quelle clé
API et aussi codex et autre ». Deux voies existaient, toutes deux nommées
d'après un seul fournisseur — `PROVIDERS = {"claude": claude_provider}` avec
l'URL d'Anthropic en dur, et `run_claude_code` avec `claude` en dur. Le
commentaire d'en-tête du module promettait pourtant depuis le pivot que
l'abstraction était « une simple fonction `provider(prompt) -> str` […]
extensible (GPT ou autre) sans toucher à la boucle d'orchestration ». La
promesse était juste ; personne ne l'avait honorée.

**Voie API : deux dialectes suffisent.** Anthropic Messages d'un côté, OpenAI
Chat Completions de l'autre — ce second dialecte est parlé par Groq, OpenAI,
OpenRouter, DeepSeek, Mistral, xAI, Together et tout serveur local (Ollama,
llama.cpp, vLLM). Écrire un fournisseur par marque aurait produit du code
dupliqué et une liste éternellement en retard d'un acteur. À la place, un seul
`openai_provider(model, base_url, key_env)`, une table de préréglages qui
n'épargne que la frappe, et `--provider openai-compatible` +
`MONL_AI_BASE_URL` pour tout point de terminaison que la table ignore. La clé
reste lue dans l'environnement, jamais en argument : la règle posée pour la
voie Anthropic n'avait aucune raison d'être plus laxiste ailleurs.

**Aucun modèle par défaut hors voie Anthropic, à dessein.** La tentation était
d'inscrire `llama-3.3-70b-versatile` pour Groq, `gpt-4o` pour OpenAI. Les
catalogues changent tous les mois : un identifiant périmé en dur transforme une
erreur claire (« préciser `--model` ») en 404 obscur six mois plus tard, chez
un utilisateur qui n'a rien changé. `--model` est donc exigé, et le message le
dit avec sa raison.

**Voie agent : la partie variable est la ligne de commande, rien d'autre.**
L'empreinte des artefacts protégés, la re-vérification (cohérence + smoke test)
et la correction unique du point 43 ne doivent rien à Claude Code. Seuls le
binaire et son argv changent — d'où une table `CLI_AGENTS` réduite à cela, et
`run_cli_agent` qui reprend mot pour mot le corps écrit pour Claude Code. Un
agent tiers ne relâche AUCUN garde-fou : c'est le sens de la généralisation,
et deux tests l'établissent en faisant tenter à un agent « codex » factice
exactement l'intrusion que l'agent Claude factice ne pouvait pas commettre.

**Ce qui est vérifié et ce qui ne l'est pas — dit franchement.** Seul `claude`
est éprouvé contre le vrai binaire. `codex` et `gemini` suivent l'invocation non
interactive publiée par ces outils, mais aucun des deux n'était installé sur la
machine de développement : ce sont des préréglages, pas des garanties, et le
commentaire de la table le dit à cet endroit précis plutôt que dans un coin de
documentation. C'est exactement pourquoi `--agent-command` existe : un gabarit
libre où `{instruction}` est substitué permet de câbler n'importe quel agent, ou
de corriger un préréglage devenu faux, sans attendre une version de monl.
Refuser un gabarit sans `{instruction}` plutôt que de lancer l'agent muet est
la même politique qu'ailleurs — échouer en nommant la cause.

Les anciens noms (`run_claude_code`, `generate_with_claude_code`) sont conservés
comme cas particuliers : la voie du point 43 reste ce qu'elle était, et les
tests écrits pour elle continuent de la couvrir sans réécriture.

---

## 70. Compiler n'est pas se comporter, et le câblage ne se relit pas

Trois écarts entre ce que le dépôt promettait et ce qu'il mesurait, tous
trouvés en regardant la couverture plutôt que le code.

**Cinq briques sur huit n'étaient prouvées que par compilation.**
`exemples/03_reseau_social.ml` fait passer `generated`, `increments`,
`decrements`, `categorized` et `capability auth` par le compilateur à chaque
exécution de la suite — et c'est tout ce qu'il en prouve. CLAUDE.md
l'avertissait déjà en toutes lettres (« compiler n'est pas se comporter
correctement »), sans que personne n'en tire la conséquence. Même motif qu'au
point 64 : l'avertissement écrit ne remplace pas la mesure.

`tests/test_briques_comportement.py` les éprouve désormais contre un serveur
réel, sur une spec qui les assemble comme le fait le réseau social — c'est
l'assemblage qui avait révélé deux bugs au point 29, pas les briques prises
isolément. Ce que chaque test cherche est choisi, pas décoratif :

- **`generated`** — un client qui envoie quand même `author` ne doit pas voir
  sa valeur atterrir en base. C'est la seule des cinq dont un défaut serait une
  faille d'intégrité et non un affichage faux ; elle ouvre donc la marche. La
  stabilité du pseudonyme est vérifiée *à travers une reconnexion* : tiré à
  chaque session, il casserait le fil d'un même auteur, et une création unique
  ne peut pas le voir.
- **`increments` / `decrements`** — le témoin voisin EST le test. Un compteur
  qui monte prouve seulement qu'un UPDATE a eu lieu ; c'est le post non visé,
  resté à sa valeur, qui prouve que la clé étrangère désigne le bon
  enregistrement. CLAUDE.md liste précisément « un mécanisme de clé étrangère
  qui décrémentait le mauvais enregistrement » parmi les bugs jamais révélés à
  la lecture.
- **`categorized`** — la borne, et elle seule, est l'endroit où une chaîne
  `if/elif` générée peut se décaler d'un cran sans bruit. `below 10` est
  strict : 9, 10, 99 et 100 l'encadrent des deux côtés.
- **L'atomicité de la bêta 1**, au passage : une clé étrangère qui ne pointe
  sur rien est refusée en 409, et l'enregistrement déclencheur ne subsiste pas.
  Un like orphelin dont le compteur n'a jamais bougé serait exactement l'état
  partiel que la transaction unique existe pour interdire.

**Une assertion écrite au jugé, corrigée par l'exécution.** Le test du schéma
OpenAPI vérifiait d'abord qu'`author` apparaît côté lecture. Il échoue : les
routes de lecture générées ne déclarent aucun `response_model`, donc rien n'y
est typé. L'assertion a été refaite contre le composant réellement référencé
par la requête de création plutôt que contre le texte de la route — `author`
absent d'une chaîne prouverait aussi bien que le champ a disparu qu'il n'a
jamais été cherché au bon endroit.

**Le quota, encore.** Ouvrir un compte par test dépasse les 5 tentatives / 60 s
du point 13. La table de compteurs est vidée entre les tests, exactement comme
au point 67 et pour la même raison : desserrer le quota lui-même rendrait
aveugle un garde-fou du produit, vider une table côté banc d'essai ne coûte
rien.

**`main()` n'était traversée par aucun test.** `tests/test_cli_commandes.py`
(point 64) éprouvait ce que font `compile_project`, `check_coherence`,
`cmd_run` et `cmd_update` ; personne n'éprouvait ce qui les appelle. Les cent
lignes d'argparse et de dispatch de `cli.py` étaient le seul chemin qu'un
utilisateur emprunte réellement, et le seul que rien ne regardait — d'où
`cli.py` à 58 %, point bas du dépôt pour la deuxième fois après le point 64.

Une erreur de câblage y est silencieuse par construction : un `--skip-smoke`
non transmis lance le smoke test quand même, un `--port` perdu en route ramène
tout le monde sur 8000 alors que le point 51 a fait tout un travail pour que le
port ne soit pas figé, et un code de sortie 0 sur échec fait passer au vert
n'importe quelle CI qui appelle `monl run --check`. Rien de tout cela ne casse
un test existant. `tests/test_cli_dispatch.py` vérifie l'aiguillage et les
arguments transmis — pas le travail au bout, qui a déjà ses tests — y compris
les deux promesses du point 69 que le dispatch porte seul : `--agent-command`
l'emporte sur `--provider` (sans quoi il ne pourrait corriger aucun préréglage)
et le modèle par défaut n'existe QUE pour la voie Anthropic.

**Le stub qui manquait, et ce qu'il apprend.** Le premier jet interceptait les
deux voies de `monl frontend` sans remplacer `PROVIDERS` : les vrais
fournisseurs exigent leur clé dès leur *construction*, donc le dispatch
échouait avant d'avoir choisi sa voie et le test mesurait l'absence de clé.
Un test vert pour la mauvaise raison est le même défaut qu'un garde-fou muet.

**Résultat mesuré** : 189 tests (contre 164), couverture 87 % (contre 85),
`cli.py` de 58 % à 79 %. Le chiffre global n'est pas l'objet — les deux
fichiers couvrent ce dont l'échec serait silencieux, pas ce qui remonte un
pourcentage.

**Et une dette de documentation soldée en chemin.** `docs/BETA.md` listait
encore « empaqueter en vrai paquet Python » parmi les chantiers restants alors
que le point 65 l'a livré, faisant passer pour dû ce qui était fait. La
priorité n°1 de la même liste — isoler l'exécution du code `custom` — a été
descendue au rang 6 avec sa raison écrite : elle datait de l'époque où les
blocs `custom` étaient remplis par une IA locale, fonction retirée en bêta 1.
Le générateur n'y écrit plus que des coquilles vides que l'auteur du projet
complète lui-même ; isoler du code écrit sciemment par l'auteur n'est plus la
même frontière de sécurité. La couche données devient le chantier bloquant,
seule à plafonner l'usage réel.

---

## 71. Ce que le compilateur refuse n'était presque pas mesuré

Suite immédiate du point 70, sur la moitié du dépôt que la mesure désignait
encore.

**La thèse du projet vivait dans des `raise` que personne n'atteignait.** Le
README affiche comme différence de fond avec un générateur d'IA qu'« une règle
sans effet est refusée à la compilation plutôt qu'ignorée en silence ».
`test_parser_errors.py` couvrait les erreurs de SYNTAXE (Lark, trois tests) et
`test_exploit*.py` les attaques au runtime. Entre les deux, la cinquantaine de
refus d'`ast_validator.py` — l'endroit exact où cette promesse se tient —
n'était exercée par presque rien : 76 %, et les lignes manquantes étaient très
majoritairement des `raise`.

`tests/test_validateur_refus.py` les met sous tension : cibles inexistantes,
types incompatibles, paliers `categorized` mal formés, règles qui se
contredisent (`hidden`+`categorized`, `hidden`+`generated`, `generated`+Create
`public`, `ownedBy`+`accessibleBy`), collision de privilèges, workflows visant
un acteur ou une entité absents, `Execute` sur un bloc `custom` inexistant,
blocs `ui` et `seed` mal câblés. Chaque test vérifie AUSSI que le message
nomme la cause : refuser sans dire quoi laisse à l'auteur de la spec la moitié
du travail que le compilateur existe pour éviter.

**Les témoins ne sont pas un ornement, ils sont le test.** Un validateur cassé
qui refuserait TOUTE spec passerait une suite composée uniquement de refus —
et paraîtrait plus robuste que jamais. Chaque famille de refus est donc
accompagnée de la spec valide la plus proche possible, celle qui ne diffère que
par ce qui est fautif, et cette spec doit compiler. C'est le corollaire écrit
dans CONTRIBUTING.md (« un test qui ne peut pas échouer ne vaut rien ») appliqué
à une suite entière plutôt qu'à un test isolé.

**Le témoin a trouvé un garde-fou que la lecture n'avait pas listé.** En
construisant la spec valide de `increments`, elle est refusée : un compteur
exige une relation entre l'entité déclencheuse et l'entité cible, sans quoi il
n'existe aucune clé étrangère d'où tirer QUEL enregistrement incrémenter — la
règle ne serait pas seulement inefficace, elle serait ambiguë. Ce refus a gagné
son propre test, ainsi que celui qui limite les compteurs à `Create`.

**Où vit un garde-fou compte autant que son existence.** Le « au moins deux
colonnes » d'`accessibleBy` (point 31) n'est PAS dans le validateur : la
grammaire exige la virgule, donc une colonne unique ne l'atteint jamais. Le
test le dit explicitement plutôt que d'attendre un `ASTValidationError` qui ne
viendra pas — savoir quelle couche tient un garde-fou est ce qui permet de ne
pas le déplacer par mégarde.

Résultat : `ast_validator.py` de 76 % à 86 %.

## Deux fuites de descripteurs, dont une dans le produit

La suite émettait des `ResourceWarning` depuis longtemps, traités comme du
bruit. Le point 67 avait pourtant déjà montré ce que coûte une ressource
laissée derrière soi : un `uvicorn` orphelin contamine les tests suivants, et
l'échec d'après n'a plus aucun rapport avec sa cause. Passer la suite sous
`-W error::ResourceWarning` a séparé trois origines.

**Côté banc d'essai, un piège Python classique** : `with sqlite3.connect(...)`
ne ferme PAS la connexion — il ne fait que valider ou annuler la transaction.
Six occurrences venaient d'être introduites au point 70, deux préexistaient.
Un gestionnaire de contexte local fait les deux.

**Côté produit, deux vraies fuites** dans `src/monl/smoke_test.py` :

- un `urllib.error.HTTPError` **est** la réponse : le lire ne suffit pas, il
  faut le fermer. Chaque 401 attendu — et le smoke test en provoque à dessein,
  pour vérifier que les routes protégées le sont — laissait un descripteur ;
- `stderr=PIPE` sur le serveur éphémère ouvre un tuyau que ni `terminate()` ni
  `wait()` ne referment.

Les deux sont modestes en volume, mais le smoke test tourne à **chaque
`monl run`** : c'est du code que l'utilisateur exécute, pas seulement la CI. La
suite passe désormais sans un seul `ResourceWarning`, ce qui rend le prochain
détectable.

**Ce que l'épisode confirme** : le code généré, lui, était propre — il ferme
ses connexions explicitement (`generator/runtime.py`). Le défaut était dans
l'outillage qui l'entoure, c'est-à-dire précisément la partie que la thèse du
projet ne protège pas, puisqu'elle n'est pas dérivée d'une spec.

---

## 72. Le compilateur n'a pas d'avis sur le visuel

Demande du mainteneur : « retire les contraintes pour les polices et autre,
monl ne doit s'occuper de rien concernant le frontend, cela doit être décidé
seulement dans le dialogue. »

**Ce qui existait.** `generator/theme.py` choisissait un système visuel complet
— palette, piles typographiques, rayon, style de carte — parmi six, d'après le
vocabulaire de la spec (`product`/`order`/`price` → `market`,
`post`/`article` → `editorial`), avec une variation de teinte par projet tirée
de `.monl_theme_seed`. Le résultat partait dans `frontend_contract.json` >
`design` et occupait une bonne page du brief.

**Pourquoi c'était là.** Le point 20 ne cherchait pas à rendre service : il
cherchait à ce que deux applications ne se ressemblent pas. Le point 58 avait
déjà reculé une première fois, en rendant la direction non contraignante sauf
épinglage explicite.

**Pourquoi ça tombe.** Une suggestion écrite dans le document qui fait foi
n'est pas neutre — elle oriente. Et le compilateur oriente mal : il ne sait pas
à quoi ce projet-là doit ressembler, il ne connaît que des noms de tables. La
seule direction légitime est celle que l'auteur a formulée lui-même, et il l'a
déjà formulée : le dialogue lui demande son registre visuel et la place qu'il
veut donner aux images. Cette réponse voyage dans le brief. Il y avait donc
deux directions concurrentes dans le même document, l'une déclarée par un
humain, l'autre déduite d'un dictionnaire de mots-clés.

**Ce qui a été retiré** : `generator/theme.py` en entier (et son mixin dans
`core.py`), le bloc `design` du contrat, la page de prescription du brief,
la graine `.monl_theme_seed`, et `_verifier_palette` du smoke test — qui n'a
plus rien à vérifier puisque plus rien n'est imposé.

**Ce qui reste, et ce n'est pas une inconséquence** : le contraste WCAG
(4,5:1) et l'autonomie du frontend. Ni l'un ni l'autre n'est une question de
goût — le premier rend l'interface lisible, le second la rend vérifiable par le
smoke test. Les confondre avec de la prescription esthétique les aurait fait
tomber avec elle.

**Le bloc `ui … theme:` reste ACCEPTÉ mais inerte**, même politique qu'au
point 41 pour `landing mode/template` : aucune spec existante ne casse, mais
plus rien ne s'en sert. Aucun exemple ni la démo n'en utilisait — le périmètre
réel se limitait à deux fichiers de tests.

**Le prix, assumé.** Ce que le point 20 protégeait disparaît : deux projets
génériques peuvent désormais converger vers ce que l'IA d'interface produit par
défaut. C'était le sens même de la demande — monl cesse de compenser par une
devinette ce qui relève de l'auteur et de l'IA. Qui veut une identité
distinctive la décrit dans le dialogue.

**Ce que les tests vérifient maintenant.** `tests/test_design_contract.py` est
retourné : il ne prouve plus qu'une palette épinglée est respectée, il prouve
que le compilateur **se tait**. Aucun bloc `design`, aucune couleur
hexadécimale nulle part dans le contrat, aucune famille typographique citée
dans le brief, un bloc `ui` rigoureusement sans effet sur le contrat, et deux
domaines opposés (boutique, journal) qui reçoivent le même paragraphe mot pour
mot. Prouver qu'un compilateur interdit quelque chose est facile ; prouver
qu'il se tait l'est beaucoup moins — et un silence que rien ne mesure finit par
se remplir à nouveau.

---

## 73. Un agent qui ne touche à rien a quand même « construit »

Le garde-fou d'empreinte (`_fingerprint_protected`, point 69) surveillait les
artefacts **protégés** — ce qu'un agent ne doit pas modifier. Personne ne
mesurait ce qu'il était censé **produire**.

**Le scénario, réel.** Un `frontend/index.html` valide existe déjà, hérité
d'une génération précédente. L'agent est lancé, examine le contrat, juge que
l'existant y répond, et n'écrit pas une ligne. Ensuite : les artefacts protégés
sont intacts (aucune alerte), la vérification de cohérence passe (le contrat
correspond toujours), le smoke test passe (la page se charge et appelle des
routes légitimes). monl annonce « Frontend construit ». Rien n'est faux dans
chacun de ces contrôles pris isolément — et pourtant la conclusion l'est.

**Le correctif** : `_fingerprint_frontend` prend l'empreinte de TOUT le contenu
de `frontend/` avant l'appel et la compare après. Identique = l'agent n'a rien
écrit, et monl le dit, avec les deux issues possibles (vider `frontend/` pour
forcer une réécriture, ou `--update` pour demander une évolution de
l'existant). Le retour reste un succès : rien n'est cassé, et féliciter l'agent
pour le travail de son prédécesseur est le seul défaut à corriger.

**La leçon, généralisable** : un contrôle qui ne sait pas distinguer
« construit » de « laissé intact » ne contrôle rien. Le point 69 avait posé la
bonne moitié du garde-fou — ce qui ne doit pas bouger — sans jamais poser
l'autre : ce qui doit bouger.

---

## 74. Encaisser, et le montant qui ne vient jamais du client

Première brique de l'écosystème de capacités depuis l'assemblage du réseau
social (points 24-31), et la première dont un défaut ne se paie pas en
affichage faux mais en argent.

```
rule Commande.total payable
```

La règle nomme le champ qui porte le **montant** ; l'entité qui le contient est
celle qu'on encaisse. Deux colonnes de suivi apparaissent dans `schema.sql`
(`payment_status`, `payment_ref`, jamais fournies par le client — retirées des
schémas d'entrée comme un champ `generated`, et ajoutées aux bases existantes
par le mécanisme de migration du point 32 — avec leur `DEFAULT`, sans quoi
ajouter `payable` à une spec en production laisserait les anciennes lignes à
`NULL` et les nouvelles à `en_attente`, deux façons de dire la même chose que
toute lecture devrait ensuite réconcilier), et deux routes dans `app.py` :
`POST /commande/{id}/paiement` et `POST /paiement/webhook`.

### Le principe, et il n'y en a qu'un

**Le montant encaissé vient de la BASE, jamais du client.** La route de
règlement n'accepte aucun corps de requête : elle relit le champ `payable` à
chaque demande. Un panier qui envoie son propre prix est un panier qu'on peut
négocier. C'est aussi pourquoi le montant est relu à *chaque* appel plutôt que
figé à la création : un prix corrigé en base ne doit pas laisser encaisser
l'ancien.

### Ce que le compilateur refuse

Six refus, tous à la compilation — un paiement mal déclaré doit échouer avant
d'être mis en ligne, jamais au moment d'encaisser :

- **entité inexistante**, **champ inexistant** — les deux cibles manquées ;
- **champ non numérique** (`Money`, `Float` ou `Integer` seulement) : on
  n'encaisse pas du texte, et en tirer un nombre serait deviner ;
- **`hidden` sur le même champ** : un montant qu'on ne peut pas lire ne peut
  pas être vérifié par celui qui le règle ;
- **deux champs `payable` sur la même entité** : plus rien ne dit lequel
  encaisser. Additionner serait une invention, prendre le premier un tirage au
  sort ;
- **création `public` sur la même entité** : encaisser exige de savoir qui
  paie — et à qui rembourser. Même raisonnement qu'au point 30 pour
  `generated`, avec de l'argent au bout.

Un septième `raise` existe dans `ast_validator.py` — la référence qui ne
nommerait pas `Entite.champ` — et il est **inatteignable** : le terminal
`REFERENCE` de la grammaire exige le point. Le vrai garde-fou est dans
`parser.py`. C'est exactement la situation du point 71 avec `accessibleBy` :
`tests/test_validateur_refus.py` le dit explicitement plutôt que d'attendre un
`ASTValidationError` qui ne viendra pas. Savoir quelle couche tient un
garde-fou est ce qui permet de ne pas le déplacer un jour en croyant le
renforcer.

### Le premier appel sortant

Jusqu'ici, un backend généré par monl ne parlait à personne : il servait des
routes, lisait un SQLite, et c'était tout. Encaisser change cela, et il faut le
dire — `json` et `urllib` entrent dans `runtime.py` pour cette seule raison.

Trois conséquences ont été traitées comme telles, pas comme des détails :

- **Les secrets viennent de l'environnement**, même règle que le secret JWT
  (point 11). `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`.
- **Absents, les routes existent et répondent 503 en nommant la variable
  manquante.** Un paiement doit refuser bruyamment, jamais échouer en silence
  — et, corollaire qui compte autant : le reste du serveur démarre et
  fonctionne normalement, donc `monl run` et le smoke test restent verts hors
  ligne, sur un projet fraîchement compilé qui n'a évidemment aucune clé.
- **Le point de terminaison est surchargeable** (`MONL_STRIPE_BASE_URL`).
  Sans cela, la brique ne serait éprouvable qu'en appelant le vrai Stripe,
  c'est-à-dire jamais.

### La signature du webhook

C'est le seul endroit de tout le backend généré où un tiers **non authentifié**
écrit en base. Sans vérification de signature, `curl` suffit à marquer
n'importe quelle commande comme payée. La signature Stripe
(`t=<horodatage>,v1=<HMAC-SHA256 de « horodatage.corps »>`) est donc recalculée
et comparée en temps constant, et le lien entre session et enregistrement passe
par `client_reference_id` — le seul fil qui relie un règlement réussi à une
ligne de la base.

### Ce que le contrat frontend ignorait

Ces deux routes ne naissent pas d'un workflow : elles échappent à
`_compute_route_map`, donc au contrat. Le défaut n'était pas cosmétique — le
contrat interdit par ailleurs à l'IA d'interface d'appeler un chemin absent de
`routes`. Autrement dit : **une brique que le contrat ne décrit pas est une
brique sans interface**, et le bouton de règlement était indessinable.

En le corrigeant, un second manque est apparu : le champ `note` des routes
existait dans le contrat JSON mais **n'atteignait pas le brief**, alors que
c'est le brief que l'IA lit. La forme de la réponse paginée y manquait depuis
toujours. Le webhook, lui, est listé pour que l'inventaire reste exhaustif,
mais explicitement écarté — signature du prestataire, pas un JWT, et une
interdiction en toutes lettres dans `frontend_rules.forbidden`.

### Ce que les tests prouvent

`tests/test_paiement.py` embarque un **faux Stripe** : un serveur HTTP local
qui parle le dialecte de la vraie API et, surtout, **enregistre ce qu'on lui
envoie**. Un banc d'essai qui se contenterait de répondre 200 laisserait passer
exactement le bug qui coûte de l'argent. Le test central envoie donc un corps
de requête annonçant un tout autre montant, puis vérifie le `unit_amount`
réellement reçu.

Le reste couvre les cinq refus au runtime (403 pour l'enregistrement d'autrui,
404, 409 sur un règlement déjà encaissé, 400 sur un montant nul, 503 sans clé),
le 502 qui remonte le message du prestataire, le parcours complet
commande → session → notification signée, et cinq formes de signature invalide
essayées séparément : une seule branche défaillante de l'analyse de l'en-tête
suffirait à ouvrir la porte. Deux cas méritaient leur propre test — une
signature authentique couvrant un **autre** corps, et une signature bien formée
produite avec une **autre** clé —, tous deux refusés sans que la commande
bouge.

`exemples/02_boutique.ml` porte la règle (`Order.totalAmount`), donc la brique
est recompilée à chaque exécution de la suite par `tests/test_compile_all.py`,
comme les huit précédentes. Un test dédié prouve un comportement ; un exemple
prouve qu'une spec réaliste continue de compiler autour.

### Le défaut que seule l'exécution a montré

La suite était verte, `ruff` muet, et `monl run` échouait quand même sur toute
spec déclarant `payable`. Le smoke test exige qu'une route non publique refuse
une requête sans jeton, en **401 ou 403** ; `/paiement/webhook` est bien
protégée, mais par la signature du prestataire — sans clé configurée elle
répond 503, avec clé 400. Elle faisait exactement son travail et se faisait
recaler pour cela.

Rien dans le code ne trahissait le conflit : les deux couches avaient raison
séparément. Il a fallu compiler un projet payable et lancer le smoke test — la
règle de CLAUDE.md, appliquée à la lettre, et le seul chemin qui menait à ce
défaut.

La correction distingue les deux régimes d'authentification par ce que le
contrat dit **déjà** : une route protégée sans aucun acteur autorisé n'est pas
une route à jeton. Ce qui reste exigé dans les deux cas est ce qui compte
vraiment — une requête nue est refusée. `tests/test_paiement.py` compile un
projet payable, vérifie sa cohérence et rejoue le smoke test sans aucune clé,
pour que la régression ne puisse pas revenir en silence.

### Ce qui est hors périmètre, et assumé

La devise est `eur` en dur ; il n'y a ni remboursement, ni abonnement, ni
paiement échelonné ; le seul prestataire câblé est Stripe. Le webhook n'a pas
d'autre idempotence que le verrou `payee`. Aucun de ces manques n'est un oubli
— chacun est une brique à part entière, et la méthode du projet est d'en
éprouver une avant d'en commencer une autre.

## 75. `payable` accessible depuis le dialogue, et deux trous que l'assemblage a montrés

Le point 74 avait donné la brique `payable`, mais un seul chemin pour
l'écrire : la spec à la main. Le dialogue guidé (`src/dialogue_engine.py`),
qui est le chemin que la quasi-totalité des utilisateurs empruntent, ne savait
pas la proposer — une capacité qu'un dialogue déterministe ne sait pas
exprimer n'existe pour personne d'autre que qui lit `docs/`.

### La question part de la spec, pas d'un drapeau de modèle

`_ask_payable` ne regarde pas un réglage porté par le catalogue
(`src/app_templates.py`) : elle regarde ce que la spec en cours de
construction CONTIENT déjà — un champ `Money` sur une entité possédée par son
créateur. Un drapeau dans le catalogue n'aurait servi que les modèles qui y
pensent ; partir du contenu réel fait marcher la question aussi bien pour une
entité de modèle que pour une entité personnalisée ajoutée à la main, ou pour
le mode libre. Un seul champ candidat : la question est posée telle quelle,
avec un rappel que le montant est relu en base et jamais envoyé par le
navigateur. Plusieurs champs candidats (rare — un seul `payable` par entité,
voir point 74) : un choix supplémentaire nomme lequel.

**Pourquoi seulement une entité possédée.** Sans propriétaire, la route de
règlement n'a personne à qui opposer un 403 : n'importe quel compte pourrait
ouvrir une session de paiement sur l'enregistrement d'un autre et en découvrir
le montant par la réponse. Le dialogue ne propose donc que la forme dont
l'objet — l'argent — supporte d'être pris au sérieux, même si le validateur,
lui, autorisait jusqu'ici une forme plus faible (voir plus bas).

### Deux trous que seul le fait d'assembler a montrés

Écrire la question a obligé à relire le reste de la brique en s'imaginant
utilisateur plutôt qu'auteur du validateur, et deux trous sont apparus — ni
l'un ni l'autre visible en relisant `payable` isolément :

**Premier trou : `payable` sans relation entrante passait la compilation.**
Rien n'empêchait `rule Entite.champ payable` sur une entité sans aucun
`hasMany`/`hasOne`/`belongsTo` la ciblant. Le générateur n'a alors AUCUN moyen
de déterminer un propriétaire pour la route de règlement, qui accepte alors
n'importe quel appelant authentifié pour n'importe quel enregistrement — un
IDOR, sur la brique dont l'objet est l'argent. La même exigence existait déjà
pour `increments`/`decrements` (points 3-4) ; `payable` ne l'avait pas héritée.
Corrigé dans `ast_validator.py` par le même test qu'utilise déjà
`_get_incoming_relation` (`generator/core.py`) pour trouver le propriétaire à
la génération : une relation `hasMany`/`hasOne` ciblant l'entité, ou
`belongsTo` la portant, sinon refus explicite à la compilation.
`tests/test_validateur_refus.py` ajoute la relation manquante à ses deux specs
`payable` pour rester dans le cas désormais exigé, et
`tests/test_app_templates.py` doit désormais tenir compte de la nouvelle
question pour les trois modèles du catalogue qui portent un champ `Money` sur
une entité possédée (Boutique en ligne, Petites annonces, Suivi de dépenses
personnelles) — sans cela, le dialogue attend une réponse pour `payable` que
le test ne fournit pas, et toute réponse suivante se retrouve décalée d'un
cran.

**Second trou : deux entités `payable` dans la même app pouvaient se
confondre au webhook.** La référence envoyée à Stripe
(`client_reference_id`) n'était qu'un id numérique. Avec une seule entité
`payable` par app (le seul cas éprouvé jusqu'ici), l'id suffisait. Dès qu'une
deuxième entité `payable` existe, deux enregistrements de tables différentes
peuvent partager le même id — et le webhook, qui ne savait lire qu'un entier,
aurait marqué payé le mauvais enregistrement, dans la mauvaise table. Corrigé
en qualifiant la référence par le nom de l'entité (`'Order:42'` plutôt que
`'42'`, `generator/routes.py`) : la route de règlement l'écrit à la création
de la session, le webhook la découpe sur `:` et n'agit que si le nom qualifie
une entité `payable` réellement déclarée — un `if`/`elif` par entité plutôt
qu'un `UPDATE` unique, pour qu'ajouter une entité `payable` n'introduise
jamais une ambiguïté silencieuse entre ses tables.

### Ce que les tests prouvent

`tests/test_paiement.py` fait désormais transiter la référence qualifiée de
bout en bout contre le faux Stripe embarqué (point 74) : la session envoyée
porte `'Commande:<id>'`, et le webhook ne règle que l'enregistrement que cette
référence nomme. `tests/test_validateur_refus.py` couvre le nouveau refus (pas
de relation entrante). Aucun des deux trous n'était visible en relisant le
code de `payable` isolément — c'est en écrivant la question du dialogue, donc
en s'imaginant utilisateur du bout en bout, qu'ils sont apparus. Conforme à la
méthode du projet : chaque brique assemblée dans un chemin réel révèle ce
qu'une lecture isolée ne montre pas (voir points 26, 31, 70).

## 76. Un champ que l'API renvoie et que le contrat taisait

Le point 74 avait tiré une leçon en une phrase : **une brique que le contrat ne
décrit pas est une brique sans interface.** Elle avait été appliquée aux
*routes* de `payable`, et s'est arrêtée là. Les deux colonnes de suivi
(`payment_status`, `payment_ref`) que la même brique ajoute à l'entité
n'étaient déclarées **nulle part** dans le contrat.

Ce n'est pas un oubli cosmétique, parce que le backend les renvoie bel et bien :
les routes de lecture générées font un `SELECT *`. Toute réponse contient donc
`payment_status`, mais aucun artefact censé décrire le backend ne le mentionne
— ni `entities.Order.fields`, ni le brief. Une IA d'interface fidèle au contrat
ne pouvait pas savoir que le champ existe, donc ne pouvait pas afficher l'issue
d'un règlement : **le bouton de paiement était dessinable, son résultat non.**

Le défaut est apparu en câblant réellement le bouton sur une boutique (voir
point 75 pour la brique elle-même) : il a fallu lire `app.py` puis interroger un
serveur pour découvrir un champ que le contrat aurait dû annoncer. Un
orchestrateur dont le contrat est incomplet fait faire ce travail à chaque IA
d'interface, à chaque projet.

### Déclarer sans laisser croire que c'est modifiable

Les deux colonnes sont ajoutées à `entities.<Entite>.fields` avec
`server_generated: true` — le même marqueur que la brique `generated` (point 30),
et l'interdit qui l'accompagne déjà dans `frontend_rules.forbidden` (« envoyer
un champ server_generated à la création ») s'applique sans qu'il faille en
écrire un second. `_creatable_fields` les exclut donc des corps de requête
annoncés, ce qu'un test garantissait déjà **dans l'autre sens** : le point 74
vérifiait qu'elles ne figurent pas en entrée, sans jamais vérifier qu'elles
figurent en sortie. Un garde-fou peut être exact et pourtant laisser passer le
défaut symétrique.

### Pourquoi elles n'ont aucun rôle

Les rôles de champ (point 35, restaurés dans le contrat au point 54) commandent
la mise en page, et « méta » n'a que **trois** emplacements. Passées à
`_assign_field_roles`, ces deux colonnes en prenaient deux : elles se faisaient
afficher comme des informations secondaires quelconques, tout en évinçant de
vrais champs de la spec. Elles sont donc ajoutées **après** l'attribution des
rôles, et n'en reçoivent aucun.

C'est cohérent avec le point 72 : le compilateur ne décide pas du visuel. Ce
qu'il faut faire de ces champs est dit **en toutes lettres** dans le brief, pas
déduit d'un rôle de mise en page qui orienterait le rendu sans le dire.

### Ce que « décrire » veut dire

Annoncer `payment_status: String` n'aurait presque rien réglé : sans les
valeurs, une IA doit deviner à quoi comparer, et devinera `paid`. Le contrat
porte donc l'explication — `'en_attente'` tant que rien n'est encaissé,
`'payee'` une fois le webhook reçu — et la note de la route de règlement y
renvoie : savoir *ouvrir* un paiement ne dit pas comment en *montrer* l'issue.
Avec la précision qui compte pour l'honnêteté de l'interface : **le champ n'est
pas à jour au retour de l'utilisateur**, puisque c'est le webhook du prestataire
qui l'écrit, plus tard. Une interface qui annonce « payé » au retour mentira une
fois sur dix.

Un défaut de plus, trouvé en relisant le brief **produit** et non le code qui le
produit : une explication commune aux deux colonnes faisait annoncer
« 'en_attente' / 'payee' » pour `payment_ref`, qui contient une référence de
session. Chaque colonne porte désormais la sienne.

### Une cinquième copie évitée

Les deux noms de colonnes étaient écrits en dur dans quatre couches (schéma
SQL, liste de colonnes de lecture, routes de paiement, et maintenant le
contrat). Quatre copies d'un nom, c'est quatre occasions de le faire dériver —
`PAYMENT_STATUS_COLUMN` / `PAYMENT_REF_COLUMN` vivent désormais dans
`generator/core.py`, la couche qui les crée, et le contrat les importe. Pas de
cycle : le générateur n'importe pas `frontend_contract`.

`CONTRACT_VERSION` passe à 4. L'ajout est additif — un frontend existant
continue de fonctionner — mais la version est ce qui permet de dire *depuis
quand* un champ est annonçable.

### Ce que les tests prouvent

Quatre tests, dont un témoin (sans `payable`, aucune trace de ces colonnes : les
déclarer partout enverrait une IA lire un champ toujours absent). Les trois
autres ont été **vérifiés par contre-épreuve** — neutraliser le correctif les
fait échouer tous les trois. Un test qui passe avant comme après le correctif ne
prouve rien, et c'est précisément ce qui était arrivé au point 74 : la
couverture existante était exacte, et muette sur le défaut.

## 77. Le montant venait bien de la base — et c'est le client qui l'avait écrit

Le point 74 avait posé l'invariant central de `payable` : **le montant vient de
la BASE, jamais du corps de requête.** La route de règlement n'accepte aucun
corps, relit le champ à chaque appel, et un test l'atteste en envoyant un corps
qui annonce un tout autre montant.

Cet invariant est vrai. Il ne protège rien.

En câblant une vraie boutique (SneakerLab, ~500 lignes de frontend, catalogue de
14 produits), la question qui n'avait jamais été posée s'est posée d'elle-même :
**qui a écrit le montant que la route relit ?** La réponse est le client, et par
deux chemins indépendants.

### Le premier chemin : la création

Rien dans monl ne sait calculer un montant côté serveur. Le frontend fait donc
l'évident — `total = prix × quantité` dans le navigateur — puis l'envoie :

```
POST /order  {"total": 0.01, "status": "5x Peak Cement (189 EUR chacune)"}
POST /order/1/paiement
  → le prestataire reçoit unit_amount = 1
```

**Un centime encaissé pour 945 euros de marchandise.** La brique a fait
exactement son travail : elle a lu le montant en base. Le montant en base valait
un centime.

### Le second chemin : la modification

Fermer la création ne suffirait pas, et c'est le piège que seule l'exécution a
montré. Une commande parfaitement honnête peut être réécrite ensuite :

```
POST /order  {"total": 189.0, ...}      → total = 189 en base
PUT  /order/1 {"total": 0.01, ...}      → 200, total = 0.01 en base
POST /order/1/paiement                  → le prestataire reçoit 1
```

`rule Order.Update ownedBy Customer` donne ce droit au propriétaire — c'est
précisément ce qu'`ownedBy` est censé accorder — et `total` figure dans le corps
du `PUT`. Aucune règle de la spec n'est violée. **Le champ encaissé doit être
inécrivable à la création ET à la modification** ; une brique qui ne traiterait
que la création laisserait le trou entier.

### Ce que ce défaut dit de la méthode

Les deux exploits tiennent en trois requêtes `curl`. Aucun test ne les
couvrait, et pourtant `tests/test_paiement.py` compte 24 tests, dont un
consacré à cette garantie exacte. Il vérifiait que la ROUTE ignore le corps
qu'on lui donne — ce qu'elle fait — sans jamais demander d'où venait la valeur
qu'elle relit. Un test peut être juste, ciblé, et mesurer le maillon voisin de
celui qui casse.

Ce que la compilation d'exemples ne montrait pas non plus : `exemples/02_boutique.ml`
compile `Order.totalAmount payable` à chaque exécution de la suite. Compiler
n'est pas se comporter (point 70), et se comporter correctement sur le chemin
prévu n'est pas résister au chemin détourné.

C'est le premier défaut du projet trouvé en **construisant un site complet
plutôt qu'une brique**. Les briques 1 à 9 avaient chacune leur test dédié ; il a
fallu un frontend réel, avec un panier, un prix et une quantité, pour que la
question « qui écrit ce nombre ? » devienne inévitable.

### Ce qui est décidé

La correction n'est pas dans la route de paiement, qui est correcte. Elle est en
amont, en deux temps :

1. **Une brique `derivedFrom`** — un champ calculé par le serveur depuis une
   ligne liée (`rule Order.total derivedFrom Product.price by quantity`), retiré
   des schémas de création ET de modification. Trois des quatre mécanismes
   nécessaires existent déjà : la FK fournie par le client
   (`_client_fk_columns`), le retrait d'un champ du schéma de création (brique
   `generated`), et l'écriture SQL sur une ligne liée dans la transaction de
   création (`increments`/`decrements`). Seule manque la **lecture** d'une
   valeur sur cette ligne avant l'insertion.
2. **Puis un refus dans `payable`** : un champ de montant que le client peut
   écrire doit faire échouer la compilation. Aujourd'hui monl compile sans
   broncher une boutique qu'on peut voler. Ce refus est cassant — la spec de
   SneakerLab cesserait de compiler — et c'est le comportement correct : elle
   n'aurait jamais dû compiler. La garantie du point 74 cesse alors d'être une
   promesse de documentation pour devenir une propriété que le compilateur
   vérifie, comme ses sept autres refus.

Le hors-périmètre du point 74 listait la devise en dur, l'absence de
remboursement, d'abonnement et d'idempotence au-delà du verrou `payee`. Il ne
mentionnait pas celle-ci, qui était la seule à coûter de l'argent.

## 78. `derivedFrom`, et le champ serveur que la route Update réécrivait

Brique 10, réponse directe au point 77. `rule Order.total derivedFrom Product.price by quantity`
déclare un champ **calculé par le serveur** depuis une ligne liée. Le client
envoie l'article et la quantité ; il n'envoie jamais le montant.

### Trois mécanismes sur quatre existaient déjà

C'est ce qui a rendu la brique petite, et ce qui la rend cohérente avec le
reste plutôt que posée à côté :

| Besoin | Réutilisé de |
|---|---|
| Le client désigne la ligne liée | `_client_fk_columns` (bêta 3) |
| Retirer un champ du schéma d'entrée | brique `generated` (point 30) |
| Toucher une ligne liée en SQL dans la transaction de création, 409 si la référence est bidon | `increments`/`decrements` (points 27-28) |
| **Lire** une valeur sur cette ligne avant d'insérer | nouveau |

Le schéma Pydantic est **unique par entité** (`{Ent}Schema`, partagé entre
`POST` et `PUT`). En retirer le champ calculé ferme donc d'un seul geste les
**deux** chemins du point 77 — c'est la propriété d'architecture qui a permis
que la correction soit une brique et non un chantier.

### Treize refus à la compilation

Un calcul mal déclaré doit échouer à la compilation : c'est un montant à
encaisser, un échec au runtime coûterait de l'argent. Deux refus méritent leur
justification, les autres sont de simple cohérence de types :

- **Le multiplicateur doit porter `required`.** Sans lui, un client qui omet la
  quantité ferait calculer sur du vide.
- **La source ne peut pas être le propriétaire.** La clé étrangère du
  propriétaire est peuplée depuis le JETON, jamais choisie par le client : si la
  source possédait l'entité, aucune ligne ne pourrait être désignée à la
  création. Corollaire : l'entité calculée doit AVOIR un propriétaire, puisque
  c'est lui qui distingue la clé étrangère du serveur de celle du client.

### Le défaut que seule l'exécution a montré, et dans les deux sens

Le montant doit être **recalculé** au `PUT`, sinon la faille se déplace
simplement : créer à quantité 1 puis modifier à quantité 5 donnerait cinq
articles au prix d'un. Reste à savoir depuis QUELLE ligne liée recalculer.

Une version intermédiaire calculait depuis `data.<fk>` — la valeur du corps de
requête — en croyant corriger un décalage. C'était une régression, et elle a été
vue en éprouvant la brique, pas en la relisant : **la route `Update` de monl
n'écrit pas les colonnes de clé étrangère.** La FK en base reste donc la seule
vérité sur « quel article », et un client pouvait facturer 89 € un article à
189 € en déclarant un article bon marché qu'il ne pointait pas. Le calcul se
fait sur la FK **stockée**, relue en base.

Les deux sens ont été essayés contre un serveur réel avant de trancher. C'est
exactement le motif que CLAUDE.md décrit : « un mécanisme de clé étrangère qui
décrémentait le mauvais enregistrement » ne s'était pas révélé autrement, et
celui-ci non plus.

### Un défaut préexistant, trouvé en passant

En excluant les champs calculés de la route `Update`, une question s'est posée
d'elle-même : comment les champs `generated` y survivaient-ils, eux qui sont
absents du schéma pour la même raison ? Ils n'y survivaient pas.

`update_<entite>` lisait `data.<champ>` pour **tous** les attributs de
l'entité. Toute entité combinant `generated` et une action `Update` produisait
donc un **HTTP 500** : `AttributeError: 'PostSchema' object has no attribute 'author'`.

Latent depuis le point 30, et invisible pour une raison précise :
`exemples/03_reseau_social.ml` porte `rule Post.author generated` mais son
workflow ne déclare que `Create Post`. La compilation passait, la brique avait
son test de comportement — et la combinaison des deux n'existait nulle part.
**Neuf briques testées une par une ne testent pas leurs paires.**

Le correctif est le même geste que pour `derivedFrom` : un champ peuplé par le
serveur n'a pas à être réécrit depuis le corps de requête, et l'exclure préserve
sa valeur — le pseudonyme d'un compte ne doit pas changer parce qu'on a modifié
le texte d'un message. Un garde-fou syntaxique accompagne l'exclusion : une
entité dont TOUS les attributs seraient peuplés par le serveur produirait
`UPDATE ... SET  WHERE id = ?`, du SQL invalide ; ne rien avoir à écrire est un
succès, pas une erreur.

### Ce que la brique ne couvre pas

Une commande = **un** article × quantité. Un panier multi-articles demande une
entité de jonction et une agrégation (somme des lignes) : `derivedFrom` y
resterait utile — elle calculerait le sous-total de chaque ligne — mais
l'agrégat est une brique à part, à éprouver après celle-ci.

Le refus qui rendrait la garantie du point 74 structurelle — **`payable` doit
refuser un champ de montant que le client peut écrire** — n'est pas encore en
place. Il est cassant (la spec de SneakerLab cesserait de compiler, ce qui est
le comportement correct : elle n'aurait jamais dû compiler) et suppose que
`derivedFrom` existe pour offrir l'alternative. C'est désormais le cas.

## 79. Le refus cassant : une boutique qu'on peut voler ne doit pas compiler

Le point 77 a montré que la garantie de `payable` ne protégeait rien ; le point
78 a donné `derivedFrom`, de quoi la rendre vraie. Restait à la rendre
**obligatoire**. C'est l'objet de ce point, et le premier refus cassant du
projet.

### Le raisonnement, en trois pas

Ce refus n'est pas une précaution générale : il découle d'une chaîne que
l'architecture rend inévitable.

1. La clé étrangère du propriétaire est peuplée avec `current_user_id` à la
   création (`populate_owner`, generator/routes.py). Donc **le créateur d'un
   enregistrement en est toujours le propriétaire.**
2. La route de règlement oppose un 403 à quiconque n'est pas le propriétaire.
   Donc **le propriétaire est le payeur.**
3. Par conséquent, si le montant figure dans le corps de création, **le payeur
   écrit lui-même ce qu'il paie.**

Il n'y a donc aucun cas légitime à préserver : pas même la facture qu'un
administrateur créerait pour un client, puisque cet administrateur en
deviendrait le propriétaire et que le client se ferait refuser le règlement.
`payable` exige désormais que son champ de montant porte une règle
`derivedFrom`, et le message de refus nomme la sortie plutôt que le seul
problème.

Le refus vit dans un recoupement final, après les deux boucles de validation :
il a besoin des deux listes. Les refus antérieurs de `payable` (deux champs
payables, création `public`) se déclenchent toujours **avant** lui, ce que les
tests exploitent — leurs specs n'ont pas eu besoin d'ajouter un calcul.

### Ce que la cascade a révélé

Casser volontairement fait apparaître ce que la compilation autorisait. La suite
a désigné 41 échecs dans 5 fichiers, et parmi eux une découverte qui ne
concernait pas le compilateur mais le **dialogue** :

`_ask_payable` (point 75) proposait l'encaissement dès qu'un champ `Money`
existait sur une entité possédée. Trois modèles du catalogue remplissaient cette
condition ; **deux n'avaient aucun catalogue à référencer**, et pour une bonne
raison :

- « Petites annonces » — le vendeur crée son annonce, donc il en est le
  propriétaire, donc le payeur. Il se paierait lui-même.
- « Suivi de dépenses personnelles » — un registre personnel. Payer sa propre
  dépense, à qui ?

La question n'aurait jamais dû leur être posée. **Un refus du compilateur a
corrigé une question du dialogue** : `_ask_payable` exige maintenant un
catalogue — une autre entité, qui ne soit pas le propriétaire, portant un prix —
et construit lui-même la structure complète (quantité, relation, les trois
règles) au lieu de laisser l'auteur l'assembler de tête.

### Le défaut du point 76, reproduit sur la brique qui le corrigeait

Après recompilation, le contrat de SneakerLab annonçait encore `total` parmi les
champs à envoyer (`request_fields`), alors que le serveur l'ignore désormais.
Une IA d'interface fidèle au contrat aurait bâti un champ de prix inutile — et
aurait pu croire ce prix respecté.

C'est exactement le défaut du point 76, sur la brique née pour le corriger. La
leçon écrite alors — « déclarer ce que le backend fait VRAIMENT » — avait été
formulée pour une brique qui **ajoute** une colonne ; elle vaut tout autant
quand une brique **retire** la possibilité d'écrire un champ. Les champs
`derivedFrom` sont donc marqués `server_generated` dans le contrat, avec leur
formule et une consigne explicite : ne pas l'envoyer, et ne pas le calculer côté
navigateur pour l'afficher avant création — relire la valeur renvoyée par le
serveur, c'est elle qui sera encaissée.

### Le prix payé, et pourquoi il valait la peine

Sept fichiers ont dû changer : l'exemple de référence, trois specs de test, le
dialogue, le critère du test de catalogue, et la boutique SneakerLab elle-même
(spec + frontend, qui calculait son total dans le navigateur).

Aucune de ces retouches n'était un contournement du refus : chacune consistait à
donner à une boutique la forme qu'elle aurait dû avoir. `exemples/02_boutique.ml`
gagne une quantité, une relation vers le catalogue et la règle de calcul — c'est
la boutique qu'on aurait écrite si la brique avait existé.

**Une suite verte n'est pas une preuve d'absence de faille.** Les 24 tests de
`test_paiement.py` passaient tous avant le point 77, et la boutique était
volable en trois requêtes. Ce que ces tests mesuraient était juste ; ce qu'ils ne
mesuraient pas ne se voyait pas. Construire un site complet l'a montré — c'est
la seule méthode qui l'a montré.

## 80. Le propriétaire est un compte, et le panier qui l'a révélé

Manque suivant sur la liste : le **panier multi-articles**. Une commande ne sait
toujours pas ce qu'elle contient — depuis le point 78 elle porte un article et
une quantité, donc un seul article. Avant de cadrer une brique, la question
préalable : monl sait-il déjà exprimer une entité de jonction ?

La sonde est une spec de trois entités — `Commande hasMany Ligne`,
`Product hasMany Ligne` — donc une `Ligne` à deux parents. Elle a répondu deux
fois, et la seconde réponse était un défaut.

### Premier retour : le refus de `derivedFrom`, à juste titre

`rule Ligne.sousTotal derivedFrom Product.prix by quantite` est refusé : `Ligne`
n'a pas de propriétaire. Le refus du point 78 fait son travail — mais il pose la
vraie question. **Qui possède une ligne de commande ?** Elle appartient à une
commande, qui appartient à un client. La propriété est *transitive*, et rien dans
monl ne l'exprime.

### Second retour : `ownedBy Commande` compilait

Écrire `rule Ligne.Read ownedBy Commande` passait la compilation sans un mot.
Le code produit, lui, était incohérent sur trois points :

```sql
CREATE TABLE "ligne" (
    ...
    "commande_id" INTEGER,
    FOREIGN KEY ("commande_id") REFERENCES _monl_users(id)   -- vers les COMPTES
);
```

```python
cursor.execute(query, (data.quantite, _calcul_sousTotal, current_user_id, ...))
#                                                        ^^^^^^^^^^^^^^^ l'appelant,
#                                                        pas la commande demandée
_own_where = ' WHERE "commande_id" = ?'   # un id de commande comparé à un id de compte
```

Éprouvé contre un vrai serveur, avec plusieurs commandes pour que les
identifiants divergent : le client demande explicitement le rattachement à la
commande 3, et la ligne enregistre `commande_id = 2` — l'identifiant de son
propre compte. **Le rattachement demandé est ignoré en silence.** La coïncidence
des premiers identifiants (utilisateur 1, commande 1) masquait le défaut sur un
essai naïf ; il a fallu créer deux comptes et trois commandes pour le voir.

### Pourquoi c'est le défaut le plus grave de la série

Les points 77 à 79 concernaient une brique jeune. Celui-ci touche `ownedBy`,
**brique 5, présente depuis les premières versions**, et il contredit la phrase
que le README affiche comme la différence de fond avec un générateur d'IA :

> une règle sans effet est refusée à la compilation plutôt qu'ignorée en silence

Ici la règle n'était pas sans effet : elle avait un effet FAUX. C'est pire, et
c'était silencieux.

### Ce qui est décidé : refuser, pas rattraper

La propriété se matérialise par une colonne peuplée avec `current_user_id` et
déclarée `REFERENCES _monl_users(id)`. Elle désigne donc **forcément un compte**.
`ownedBy` exige désormais que le propriétaire nommé soit un **acteur**, et le
message de refus dit à la fois ce qui cloche et ce qui manque — la propriété
transitive, qui n'existe pas encore.

Implémenter la transitivité maintenant serait tentant : c'est la brique du
panier, et elle est à portée. Mais le refus vaut d'être livré seul et tout de
suite. Une spec qui compile en produisant un rattachement qui ne marche pas
coûte plus cher qu'une spec qui ne compile pas : le premier défaut se découvre en
production, le second à la compilation. Et la brique transitive mérite d'être
cadrée pour elle-même, pas bricolée dans la foulée d'un correctif.

### Ce que la brique du panier devra résoudre

Le cadrage que cette sonde a produit, pour la suite :

- **Propriété transitive** — `Ligne` appartient à qui possède sa `Commande`. Le
  contrôle d'accès devient une jointure, plus une comparaison de colonne.
- **Clé étrangère vers un enregistrement, fournie par le client** — le
  mécanisme existe (`_client_fk_columns`) mais il est réservé aux parents
  NON-propriétaires ; ici le parent propriétaire est justement celui que le
  client doit désigner.
- **Agrégation** — `Commande.total` comme somme des `Ligne.sousTotal`.
  `derivedFrom` calcule depuis UNE ligne liée ; sommer plusieurs enfants est un
  autre mécanisme, et le montant doit rester recalculé à chaque écriture d'une
  ligne, sinon la faille du point 77 revient par la porte du panier.

Trois briques, donc, pas une. C'est exactement ce qu'une sonde est censée
apprendre avant qu'on écrive la première ligne.

---

## 81. La propriété transitive : quand le contrôle d'accès devient une jointure

**Brique 11.** `rule Ligne.Read ownedBy Commande` — le propriétaire nommé est
une ENTITÉ, et la chaîne remonte jusqu'à un compte par la règle `ownedBy` de cet
intermédiaire. Première des trois briques du panier cadrées au point 80.

### Ce qui change, et pourquoi c'est un renversement

En propriété directe, la colonne de propriété est **déduite du jeton** : le
serveur y écrit `current_user_id`, le client ne la voit même pas dans le schéma
Pydantic. C'est ce qui rendait la garantie facile — personne ne peut mentir sur
une valeur qu'il ne fournit pas.

En propriété transitive, cette colonne est **fournie par le client** : « cette
ligne va dans CETTE commande ». Le client désigne son parent, donc il peut
désigner celui d'un autre. La brique déplace la garantie d'un cran : au lieu
d'être vraie par construction, elle devient vraie **par vérification**.

D'où la règle de conception qui tient toute la brique : *une clé étrangère que
le client fournit doit être validée à l'écriture, une clé étrangère déduite du
jeton n'a rien à valider.* La brique n'aurait pas de sens sans le contrôle
qu'elle ajoute à la création — elle ouvrirait un trou plus large que celui
qu'elle ferme, puisque n'importe quel compte pourrait déposer une ligne dans le
panier d'autrui.

### Les quatre chemins, et la forme du filtre

`_transitive_chain()` (generator/core.py) est la source unique : elle rend les
DEUX colonnes que la jointure met en regard — celle qui désigne l'intermédiaire
sur l'entité, celle qui porte l'id de compte sur l'intermédiaire.

- **Création** — lecture du parent désigné, 403 si absent OU si le compte ne
  correspond pas. Une seule réponse pour les deux cas : les distinguer
  permettrait d'énumérer les commandes des autres, exactement ce que le 404 de
  la lecture détail évite déjà. Vérifié : sans le contrôle, « inexistante »
  donne 409 (contrainte de clé étrangère) et « pas à vous » donne 200 — les deux
  cas étaient bel et bien distinguables.
- **Liste** — `WHERE "commande_id" IN (SELECT id FROM "commande" WHERE
  "client_id" = ?)`.
- **Détail** — la chaîne se remonte d'un cran depuis la ligne lue, 404 en cas de
  refus (précédent du projet : un enregistrement qu'on n'a pas le droit de lire
  doit être indiscernable d'un enregistrement absent).
- **Modification / suppression** — une jointure qui rend l'id de COMPTE du
  propriétaire. Elle renvoie donc la même chose qu'en propriété directe, ce qui
  laisse la comparaison qui suit **inchangée** : les deux cas se rejoignent dans
  `_owner_lookup_sql()`. Ces deux blocs de routes.py étaient identiques et
  auraient dû être corrigés deux fois ; ils partagent désormais leur requête.

Un intermédiaire absent ne rend aucune ligne, donc 404 : une ligne orpheline
n'appartient à personne, et c'est la bonne réponse.

### Ce qui reste refusé, et pourquoi

Le point 80 refusait toute entité comme propriétaire. Le refus se resserre au
lieu de disparaître — cinq cas, chacun parce qu'il produirait du code faux :

1. **L'intermédiaire n'a pas de propriétaire** — la chaîne ne remonte à aucun
   compte, il n'y a rien à comparer. C'est le cas exact que le point 80 avait
   trouvé en train de compiler en silence.
2. **Chaîne à deux niveaux** (`Detail` → `Ligne` → `Commande` → `Client`) — la
   jointure générée n'a qu'un seul niveau. Accepter compilerait un filtre sur le
   mauvais maillon : la classe de défaut que le point 80 a fermée, qu'on ne
   rouvre pas par la profondeur.
3. **Intermédiaire à plusieurs propriétaires** — chaîne ambiguë, le serveur ne
   saurait pas lequel vérifier.
4. **Mélange direct + transitif sur la même entité** — sa colonne de propriété
   serait à la fois peuplée depuis le jeton et fournie par le client.
5. **`payable` sur une entité possédée transitivement** — la route de règlement
   identifie le payeur par une clé étrangère de COMPTE, qu'une chaîne transitive
   ne fournit pas. C'est le point 80 qui reviendrait par la caisse. Le message
   nomme l'entité qu'il faut encaisser à la place (la commande, pas la ligne).

### La composition, qui est là où les briques se cassent

Leçon du point 78 : *neuf briques testées une par une ne testent pas leurs
paires.* `derivedFrom` + propriété transitive fonctionne, et il fallait le
vérifier plutôt que l'espérer — le montant de la ligne reste calculé par le
serveur, et **recalculé au `PUT` depuis la clé étrangère stockée**, jamais celle
du corps de requête (l'invariant du point 78 tient sur une entité dont la
colonne de propriété est désormais cliente).

Un test fige aussi un comportement dont dépend la sécurité de la brique : la
route Update de monl **n'écrit pas les clés étrangères**. Sans cela, un client
déposerait une ligne dans le panier d'un tiers en passant par la modification.

### Le contrat, troisième récidive du même défaut

Points 76 et 79 : *le contrat doit décrire ce que le backend FAIT.* Il annonçait
`order_id` dans le corps du `PUT` — vrai (le schéma Pydantic est unique par
entité, donc l'omettre donne 422) et trompeur : la route ne l'écrit pas. Une IA
d'interface fidèle au contrat aurait proposé « changer l'article de cette
ligne », le backend aurait répondu 200, et rien n'aurait changé. Une note
explicite le dit maintenant, sur toute route `PUT` qui porte des clés étrangères
clientes — donc pas seulement pour cette brique : le défaut préexistait pour
tout parent non-propriétaire, le panier l'a simplement rendu atteignable.

La colonne transitive, elle, est arrivée correctement dans le contrat sans une
ligne de code supplémentaire : `_client_fk_columns()` est partagé avec le
générateur de schémas. C'est le bénéfice direct d'avoir mis le changement dans
le helper commun plutôt qu'en ligne dans routes.py.

### Ce que la sonde du point 80 avait appris, et qui a servi

Les identifiants du test sont volontairement **divergents** (trois commandes
créées avant celles qui portent les assertions). Le premier essai de la sonde
n'avait rien montré parce que « utilisateur 1 » et « commande 1 » coïncidaient :
une comparaison fausse passait pour juste. Le test l'affirme explicitement
(`assert commande != compte, "identifiants confondus : le test ne prouve rien"`)
plutôt que d'en dépendre en silence.

### Contre-épreuves

Les douze tests sont passés du premier coup, ce qui est un motif de méfiance et
non de satisfaction. Trois neutralisations, chacune isolant son test :

- retirer le contrôle du parent à la création → seuls les deux tests de refus
  d'écriture tombent (et révèlent la distinguabilité 409/200 décrite plus haut) ;
- remettre le filtre de liste en comparaison directe (la forme du point 80) →
  seul le test de liste tombe, et de la façon caractéristique du défaut : le
  client ne voit plus **ses propres** lignes ;
- neutraliser aussi l'écriture de la clé étrangère → dix tests sur douze
  tombent. Contre-épreuve trop grossière pour conclure quoi que ce soit de
  précis, refaite en version chirurgicale ci-dessus. Une contre-épreuve qui
  casse tout ne prouve rien de plus qu'une qui casse le bon test.

### Ce qui reste pour que le panier existe vraiment

`Commande.total` comme **somme** des `Ligne.sousTotal` — brique 3 du cadrage du
point 80, toujours à faire. Sans elle, une commande à plusieurs lignes ne sait
pas ce qu'elle coûte, donc `exemples/02_boutique.ml` reste sur son modèle à un
article : y ajouter des lignes maintenant produirait un total incohérent avec
son contenu. Le refus n° 5 ci-dessus est la version « échoue à la compilation »
de cette limite.

### Gap trouvé en chemin, non corrigé : le contrôle de cohérence est muet sur la version du compilateur

`monl run --check` annonce « Cohérence statique vérifiée (spec ↔ backend ↔
contrat ↔ frontend) ». Il compare aux **empreintes enregistrées à la
compilation** (`monl.json`), ce qui détecte une retouche à la main — son but — et
rien d'autre. `monl.json` ne retient aucune version de compilateur.

Conséquence vérifiée sur `projets/SneakerLab` : son `frontend_contract.json`
n'a pas la note `PUT` que le compilateur courant produirait, et le contrôle
affiche ✅. Un projet reste donc sur le compilateur qui l'a construit sans que
rien ne le dise — y compris quand le compilateur a depuis fermé un trou.
Correctif évident (inscrire la version dans `monl.json`, avertir si elle
diffère), mais le choix entre avertissement et erreur touche tous les projets
existants : à décider, pas à trancher en passant.

---

## 82. Le panier qui sait ce qu'il coûte, et la faille du point 77 arrêtée à l'entrée

**Brique 12.** `rule Commande.total sumOf Ligne.sousTotal` — le champ nommé est
la SOMME d'un champ de toutes les lignes enfants, recalculée par le serveur à
chaque écriture de ligne. Troisième et dernière brique du panier cadrée au
point 80 ; avec elle, `exemples/02_boutique.ml` devient une vraie boutique à
plusieurs articles.

### Ce que `derivedFrom` ne pouvait pas faire

`derivedFrom` lit UNE ligne liée : prix × quantité. Une commande ne pouvait donc
porter qu'un seul article, et c'est exactement ce qu'était la boutique d'exemple
depuis le point 77 — une commande avec un `product_id` et une `quantity`. La
propriété transitive (point 81) lui a donné des lignes correctement protégées,
mais la commande ne savait toujours pas ce qu'elle coûtait.

### Le refus qui porte toute la brique

Le cadrage du point 80 l'annonçait : *« le montant doit rester recalculé à chaque
écriture d'une ligne, sinon la faille du point 77 revient par la porte du
panier »*. Elle revenait par une porte de plus, qu'il fallait fermer aussi.

Un champ `sumOf` est calculé par le serveur : il satisfait donc le refus cassant
du point 79, qui exige que le montant encaissé ne soit pas écrivable par le
client. Mais **additionner un montant que le client écrit ne produit pas un total
sûr** — il produit un total que le client contrôle, en une addition de plus. Le
payeur reprend la main sur ce qu'il règle, exactement comme au point 77 : la
brique qui rend le panier chiffrable aurait rouvert le trou que la précédente
avait fermé.

D'où le refus : ce qu'on somme pour encaisser doit être lui-même calculé par le
serveur. Et son emplacement, qui est le point de conception intéressant — il vit
dans le **recoupement avec `payable`**, pas dans la boucle `sumOf`. Parce que
sommer un champ que le client fournit reste parfaitement légitime hors paiement :
`rule Commande.nbArticles sumOf Ligne.quantite` compte des articles, il
n'encaisse rien. C'est le CUMUL qui est fautif, pas la somme. Un refus posé au
mauvais endroit aurait interdit un usage sain pour empêcher un usage dangereux.

### Recalculer, jamais ajuster

La somme est **relue depuis la table** à chaque écriture, pas ajustée d'un delta.
Un ajustement (`total = total + sousTotal`) se désynchronise dès qu'une écriture
échoue à mi-chemin, et rien ne le rattrape ensuite ; un recalcul est toujours
juste, même après un incident. `COALESCE` pour qu'un panier vidé retombe à 0 et
non à NULL — aucune interface n'affiche « null € », et en SQLite une somme
partant de NULL reste NULL.

Trois branchements, et le troisième est celui qu'on oublie :

- **Création** de ligne : recalcul DANS la même transaction que l'insertion. Un
  commit séparé pourrait laisser une ligne créée et un total resté en arrière —
  un panier qui ne dit pas ce qu'il coûte, et sur une entité `payable`, un
  montant faux à encaisser.
- **Modification** : le parent est relu EN BASE, jamais pris dans le corps de
  requête. La route Update de monl n'écrit pas les clés étrangères, donc
  `data.<fk>` peut désigner un parent auquel la ligne n'appartient pas : on
  recalculerait le total d'une autre commande et pas celui de la vraie. Même
  leçon que le point 78, sur une autre brique.
- **Suppression** : le parent est lu AVANT le `DELETE`. Après, la ligne n'existe
  plus et sa clé étrangère avec elle — plus rien ne dit quel total recalculer.

### Contre-épreuves

Douze tests verts du premier coup, donc quatre neutralisations, chacune isolant
son test — et chacune donnant un chiffre concret plutôt qu'un échec abstrait :

- pas de recalcul au `DELETE` → le règlement demande **50,35 € au lieu de
  10,15 €** : l'article rendu, encaissé quand même ;
- pas de recalcul au `PUT` → **10,05 € au lieu de 100,50 €** : dix articles au
  prix d'un, la faille du point 77 déplacée sur la quantité ;
- pas de recalcul à la création → le total reste à 0 et la route de règlement
  répond « Montant nul : rien à encaisser » ;
- `ROUND` retiré → **101,19999999999999**.

Ce dernier a demandé une correction du test lui-même : mes premiers prix (12,35 et
7,80) ne dérivaient PAS, donc le test d'arrondi passait avec ou sans `ROUND` —
une tautologie. Il a fallu chercher des valeurs qui dérivent réellement
(`round(10.05×3, 2) + round(10.15×7, 2) == 101.19999999999999`). Le test porte
maintenant une assertion qui le protège de retomber dans ce piège :
`assert brute != round(brute, 2), "les prix du banc ne dérivent plus : ce test
redevient tautologique"`. **Une contre-épreuve sert autant à valider le test qu'à
valider le code.**

### Deux tests qui visaient la mauvaise garde

Deux refus, écrits d'abord sur la spec commune, atteignaient un refus ANTÉRIEUR :

- le cumul `derivedFrom` + `sumOf` était intercepté par le contrôle du
  multiplicateur (`Commande` n'a pas de champ quantité) — il a fallu une spec où
  la règle `derivedFrom` est elle-même valide pour que le recoupement soit
  atteint ;
- l'exigence de propriétaire sur l'entité sommée était interceptée par la même
  exigence de `derivedFrom` (point 78) — le test validait la garde d'une autre
  brique. Corrigé en sommant un champ ordinaire (`Ligne.quantite`).

Un test de refus qui passe ne prouve rien tant qu'on n'a pas vérifié QUEL refus a
répondu. C'est la troisième fois que ce piège se présente (déjà au point 78).

### Le contrat, sans attendre la récidive

Le défaut du point 76 s'était déjà reproduit deux fois (points 79 et 81). Cette
fois le champ `sumOf` est déclaré `server_generated` d'emblée, avec une note qui
dit ce qu'une interface doit en faire : relire le parent après chaque écriture de
ligne plutôt que tenir un total côté navigateur, qui divergerait. Un total de
panier est justement le cas où l'écart se verrait le plus vite.

### Ce que la chaîne complète permet maintenant

Points 74 à 82, bout à bout : la brique 10 calcule chaque ligne, la brique 11 la
rattache à son panier et la protège, la brique 12 les somme, la brique 9 encaisse
le résultat. Éprouvé de bout en bout par
`tests/test_agregation.py::test_le_montant_encaisse_est_la_somme_du_panier`, qui
vérifie le montant sur ce que le PRESTATAIRE reçoit — décodé de son corps de
requête, pas lu dans la base.

---

## 83. monl ne savait pas qu'un fichier existe : le type `Image` et le bloc `assets`

**Brique 13.** Un type de champ `Image` et un bloc `assets` qui déclare le dossier
des fichiers fournis par l'humain, son logo, son icône. Née d'une question
d'ergonomie — « comment faciliter l'intégration des logos et photos ? » — et
arrivée ailleurs : le problème n'était pas la saisie, c'était que **rien ne
vérifiait quoi que ce soit**.

### Ce que la sonde a trouvé, avant d'écrire une ligne

Quatre constats, tous vérifiés plutôt que supposés :

1. **Il n'existait aucun type `Image`.** Un champ portant une image se
   reconnaissait à son NOM (`MEDIA_HINTS = ("image", "photo", "cover", …)`).
   `imageUrl` marchait par chance ; `apercu` ou `cliche` n'auraient pas été
   reconnus, et l'IA d'interface n'en aurait pas fait un `<img>`.
2. **Un chemin faux compilait en silence.** Trois cas essayés, trois succès :
   `"images/ce-fichier-n-existe-pas.jpg"`, `"imgs/halo-rs.jpeg"` (dossier ET
   extension mal tapés), et `"/etc/passwd"`.
3. **Le smoke test ne chargeait aucune image** — jsdom ne récupère pas les
   ressources externes. Un site aux douze images mortes le passait.
4. **Le plus grave : `monl frontend` égarait les photos.** Le dossier `frontend/`
   est *renommé* en `frontend.precedent/` puis réécrit depuis les fichiers de
   l'IA, et la liste blanche est `.html .css .js .svg .json` — **`.jpg` en est
   absent**. Le seul endroit où l'humain déposait ses photos était précisément
   celui que monl traite comme un jetable d'IA. Rien ne l'avertissait.

### La décision de conception : deux couches, la brique d'abord

Il y avait deux réponses possibles, et l'ordre importe. Un outil
(`monl assets add photo.jpg --for "Halo RS"`) répond littéralement à la question
posée. Mais **l'outil seul aurait automatisé l'écriture de chaînes que personne
ne vérifie** — il aurait rendu les fautes plus rapides à produire. La brique
seule apporte déjà l'essentiel : plus aucune image cassée ne franchit la
compilation. L'outil reste à faire, ensuite.

### Forme et existence, séparées à dessein

`_verifier_forme_chemin_asset` est **pur** : chemin absolu, remontée `..`, URL
distante sous un type `Image`. Il s'applique toujours, y compris quand une spec
est validée en mémoire. `_verifier_asset_present` demande `base_dir` (le dossier
de la spec) et se **tait** sans lui — un faux refus serait pire que l'absence de
contrôle, et le silence est explicite plutôt qu'accidentel. C'est ce partage qui
permet aux tests d'exercer trois refus sans écrire un seul fichier.

Le refus d'URL distante mérite son mot : `Image` promet un fichier *vérifiable*,
et monl ne fait aucun appel réseau — il ne peut donc rien affirmer d'une URL.
`String` reste là pour ce cas, non vérifié. Interdire l'un pour garantir l'autre
aurait été le mauvais échange ; un test fige d'ailleurs que `String` +
`https://…` compile toujours.

### Déclaré bat devine

Le rôle `media` du contrat vient désormais du TYPE, l'heuristique de nom ne
servant plus que de repli pour les specs qui n'ont pas adopté `Image`. Un test
le prouve avec un nom qu'aucune heuristique ne reconnaît (`cliche`).

Et le contrat porte enfin une section `assets` : dossier, `served_at`, logo,
favicon. Sans elle, une IA d'interface ne pouvait pas savoir qu'un logo
existait — l'en-tête de la boutique de démonstration était un mot en texte,
faute de mieux.

### « Existe » n'est pas « servi »

C'est l'autre moitié de la question, et la seule qui compte pour un navigateur.
Le smoke test lançait `app:app` : **ni `/site` ni les assets ne passaient par
HTTP**, donc « servi » n'était vérifié nulle part. Il monte maintenant le projet
avec le MÊME wrapper que `monl run`, et fait un vrai GET sur chaque asset
déclaré.

Ce partage a demandé un module : `serving.py`. Le wrapper vivait dans `cli.py`,
et `cli` importe `smoke_test` — l'inverse ferait un cycle. Le dupliquer aurait
créé deux wrappers à faire dériver, ce que le projet refuse ailleurs
(`PAYMENT_*_COLUMN`, `_compute_route_map`). D'où une **feuille** volontaire, qui
n'importe rien du projet, avec sa frontière inscrite dans
`tests/test_architecture.py`.

**Le montage des assets doit précéder celui de `/site`** : Starlette teste les
routes dans l'ordre d'enregistrement, et `/site` monté d'abord absorberait
`/site/assets/…` pour aller le chercher dans `frontend/`, où il n'est pas.
Contre-épreuve faite en inversant l'ordre : **trois 404**, et le smoke test
refuse de lancer l'application. C'est exactement le défaut que ce contrôle
existe pour attraper, et il n'aurait été visible qu'à l'œil, sur la page.

### Deux défauts trouvés en chemin

**Dans le client HTTP du smoke test.** Il décodait toute réponse en JSON et
n'attrapait que `json.JSONDecodeError` — or `UnicodeDecodeError` n'en est pas un.
Le premier octet d'un PNG faisait remonter la trace complète. Latent depuis
toujours : rien de binaire n'était jamais demandé. Le commentaire d'origine
disait « /docs renvoie du HTML » — le texte avait été prévu, le binaire non.

**Dans mon propre correctif du point 81.** En branchant `base_dir`, j'ai écrit
`base_dir=project_dir` dans `_empreintes_regenerees(spec_path)`, où cette
variable n'existe pas. Le `except Exception` de la fonction l'aurait **masqué**
en désactivant silencieusement le contrôle de version du compilateur. C'est le
test du point 81 qui l'a rattrapé — une garde qui protège une garde.

### Adopté par un vrai projet

`projets/SneakerLab` est migré : `frontend/images/` → `assets/`, `imageUrl:
String` → `Image`, chemins de seed et références en dur du frontend
resynchronisés. Un détail qui n'allait pas de soi — le seed ne s'applique qu'à
une base NEUVE, donc les douze lignes existantes gardaient l'ancien chemin et le
site aurait montré douze cadres vides. Vérifié en réel après migration : les
images répondent 200 sur `/site/assets/…`, et l'ancien chemin donne bien 404.

Ce que la brique n'a pas pu éprouver là-bas : le logo. SneakerLab n'en a pas —
son en-tête reste un mot-symbole en texte. Déclarer `logo:` sans fichier ferait
échouer la compilation, ce qui est le comportement voulu.

---

## 84. L'outil qui écrit dans la spec, et la garantie qu'il fallait énoncer juste

Couche 2 du point 83, délibérément remise à plus tard : `monl assets add
photo.jpg --for "Halo RS"`. La raison de l'attente vaut d'être répétée, parce
qu'elle est la décision de conception la plus utile de la paire — **un outil qui
écrit `assets/halo-rs.jpg` dans un seed automatise l'écriture d'une chaîne.**
Avant la couche 1, personne ne vérifiait cette chaîne : l'outil aurait
industrialisé la production d'images cassées, plus vite et plus proprement. La
brique d'abord, l'ergonomie ensuite.

Le contrat de l'outil tient en une phrase : **il écrit, le compilateur prouve.**
Chaque édition est reparsée par le vrai parseur et revalidée par le vrai
validateur, en mémoire, avant d'être écrite sur disque. Un échec ne laisse rien
derrière : ni spec à demi modifiée, ni fichier copié. C'est la discipline du
dialogue guidé — « la spec produite est revalidée par le vrai parseur avant
d'être écrite » — appliquée à une édition chirurgicale.

### L'édition est textuelle, et ce n'était pas de la paresse

Un aller-retour parse → regénère aurait été plus court à écrire. Il aurait aussi
effacé tous les commentaires de la spec. Or la spec de `projets/SneakerLab` est
plus qu'à moitié faite de commentaires, et ce sont eux qui expliquent quelle
brique fait quoi et pourquoi le compilateur refuserait autre chose : **détruire
la documentation du projet pour poser une photo** aurait été un mauvais échange.

L'édition textuelle a son prix, payé en petits scanners qui suivent l'état
« dans une chaîne » : découper une ligne de seed sur les virgules HORS
guillemets (un descriptif en contient presque toujours une, et découper
naïvement en ferait deux champs dont l'un est du texte libre), et isoler un
commentaire de fin de ligne sans couper au premier dièse rencontré. Un test fige
la propriété entière : le nombre de `#` du fichier est identique avant et après,
et la ligne réécrite conserve son indentation, ses autres champs et son
commentaire terminal.

### Une fiche n'est pas une ligne

Le terminal du parseur est `STRING_LITERAL: /"(?:[^"\\]|\\.)*"/s` — drapeau `/s`,
et la classe accepte déjà le retour à la ligne. **Une valeur de seed peut donc
tenir sur deux lignes**, et le parseur l'accepte : vérifié en le lui donnant, pas
déduit de la lecture de la grammaire.

La première version repérait les fiches en comptant les lignes de contenu du
bloc. Une description sur deux lignes décalait donc toutes les fiches suivantes,
et une photo écrite sur la mauvaise fiche produit une spec **parfaitement
compilable** : aucun contrôle n'aurait rien vu, l'erreur ne se serait montrée
qu'à l'œil, sur la page. Exactement le genre de défaut que le point 83 existe
pour empêcher, reproduit par sa propre couche 2.

Ce qui a sauvé la situation n'était pas le repérage mais le **filet posé par
défiance** : l'outil compare le nombre de fiches trouvées dans le fichier à celui
de l'AST, et refuse si les deux diffèrent. Une valeur multi-lignes rend toujours
« lignes > fiches », donc le cas tombait sur un refus, jamais sur une écriture
fausse. Un filet écrit sans savoir ce qu'il attraperait a attrapé quelque chose.

Le repérage travaille désormais en **plages** `(première ligne, dernière ligne)`,
l'état « chaîne ouverte » étant reporté d'une ligne à la suivante — une
continuation n'est alors testée ni pour son indentation ni pour un `#` en tête,
puisque dans une chaîne ces caractères ne veulent plus rien dire. Le refus reste
en place derrière, par principe.

### Le défaut que les tests ont trouvé : une garantie trop large

Première version : charger et revalider la spec **avec `base_dir`**, donc avec la
vérification d'existence de la couche 1. Cela semblait la position la plus sûre.
C'était un défaut, et il avait deux faces, dont une trouvée par un test écrit
sans y penser :

* **`monl assets list` ne pouvait pas rapporter un asset manquant.** Charger la
  spec échouait sur ce manquant même — le rapport refusait de tourner dans le
  seul cas où il servait ;
* **`add` était inutilisable sur une spec déclarant deux photos absentes.**
  Impossible d'en poser une : l'autre faisait échouer la revalidation. L'outil
  refusait de réparer ce qu'il était fait pour réparer.

La correction n'est pas d'affaiblir le contrôle, c'est de l'**énoncer juste**. Ce
qu'il faut prouver n'est pas « toute la spec est complète » — c'est « le chemin
que je viens d'écrire résout vers un vrai fichier ». Donc : revalidation SANS
`base_dir` (tous les refus structurels et de forme s'appliquent, la coupure
forme/existence du point 83 rendant cela possible), puis vérification ciblée de
l'écriture avec `resoudre_asset`, **le résolveur du compilateur**, sorti du
validateur pour être partagé au lieu d'être réécrit. Ce qui manque encore
ailleurs est dit en avertissement, nommé, plutôt que bloqué.

Leçon générale, valable au-delà des assets : **une garantie trop large n'est pas
plus sûre, elle est fausse ailleurs.** Elle bloque des usages légitimes en
prétendant protéger, et le prix se paie dans le seul cas où l'outil servait.

### Ce que l'outil refuse, et pourquoi deviner serait pire

La fiche est désignée par une de ses **valeurs** (`--for "Halo RS"`), pas par un
numéro : c'est ce que l'humain a sous les yeux. D'où les refus :

* valeur inconnue → refus **avec suggestion** (`difflib`), parce qu'une faute de
  frappe est le cas le plus probable ;
* valeur partagée par deux entités → refus nommant les candidates et exigeant
  `--entity`. Écrire la photo sur l'une des deux au hasard ne se verrait qu'en
  ligne ;
* entité sans champ `Image` → refus **nommant le remède** (`photo: Image`), parce
  qu'un champ `String` accepterait n'importe quel chemin en silence ;
* deux champs `Image` → `--field` exigé ; `--field` sur un champ non-`Image` →
  refus disant son type ;
* `--as` recevant un chemin → refus : accepter un chemin rouvrirait la porte que
  la couche 1 ferme ;
* source sans extension → refus : servie telle quelle, elle arrive en
  octet-stream et le navigateur ne l'affiche pas ;
* spec déjà cassée → refus d'y écrire. Sans lui, l'échec de la revalidation
  ferait accuser l'outil d'un défaut qui existait avant lui.

### Ce que l'outil ne fait pas

**Il ne supprime rien.** Remplacer la photo d'une fiche laisse l'ancien fichier
orphelin : il est SIGNALÉ, pas effacé. Un fichier déposé par l'humain ne
s'efface pas sur la déduction d'un outil de déclaration — et le frontend de
SneakerLab référence en dur des photos que la spec ignore.

**Il n'écrit aucun crédit.** C'est la règle du point 83 tenue : *monl vérifie la
complétude, jamais la véracité*. Un champ d'attribution obligatoire et
invérifiable invite à l'inventer — expérience faite avec quatre photographes
inconnus. En revanche, si le dossier porte déjà un fichier de crédits, l'outil
dit quand le nouveau fichier n'y figure pas. Constater une absence est de la
complétude ; remplir la ligne serait de la véracité.

**Il ne recompile pas.** `monl update` reste le geste explicite, avec son
rapport de delta à lire. L'outil le rappelle — mais seulement si la spec a
vraiment changé : redéclarer à l'identique n'écrit rien, sinon l'empreinte de
`monl run --check` serait invalidée pour rien.

**Il n'écrase pas sans le dire.** Un fichier de même nom au contenu différent
exige `--force`, et l'écrasement reste réversible le temps de la revalidation —
sans quoi un refus détruirait l'ancien fichier pour rien.

### Deux détails qui ne se devinent pas

**Le logo se déclare par son SEUL nom.** C'est le contrat frontend qui préfixe
par le dossier (`_assets_contract`) : écrire `assets/logo.svg` dans le bloc
`assets` donnerait `/site/assets/assets/logo.svg` au navigateur. Une valeur de
seed, elle, porte le dossier — c'est l'URL que la page demandera. Deux formes,
deux raisons, et le résolveur accepte les deux.

**Le slug translittère ce que NFKD ne décompose pas.** « Sørlund » donnait
« srlund », « Bæk » donnait « bk » — un nom de fichier muet là où le nom était
lisible. Le catalogue de SneakerLab porte déjà une maison nordique : le cas
n'est pas théorique. Petite table explicite (ø, æ, œ, ß, þ, ð, đ, ł…), pas une
bibliothèque de plus.

### Le filet, éprouvé en le forçant

L'outil est construit pour que la ligne de commande ne PUISSE pas produire une
spec invalide : tous les chemins fautifs sont interceptés avant l'écriture. Le
retour en arrière n'est donc atteignable qu'en provoquant l'échec — et **un
filet que rien n'éprouve n'est pas un filet, c'est une décoration.** Deux tests
le forcent : revalidation qui refuse (la spec est inchangée, le fichier copié est
retiré), et refus après `--force` (l'ancien fichier est RESTAURÉ, et le fichier
de sauvegarde ne traîne pas). Un troisième neutralise la copie pour vérifier que
la garantie finale — « ce chemin résout-il ? » — n'est pas décorative non plus.

`tests/test_assets_tool.py` (33 tests) et une frontière de plus dans
`test_architecture.py` : `assets_tool` ne connaît que `parser` et
`ast_validator`. C'est ce qui lui permet de revalider une spec sans rien
compiler, et ce qui empêche le cycle avec `cli`, qui l'appelle.

### Adopté par un vrai projet, et la case cochée du point 83

Le point 83 se terminait sur un manque : *« Ce que la brique n'a pas pu éprouver
là-bas : le logo. SneakerLab n'en a pas. »* Il en a un maintenant, et il a été
posé **par l'outil** — pas à la main :

```
monl assets add sneakerlab-mark.svg --logo --dir projets/SneakerLab
monl assets add projets/SneakerLab/assets/logo.svg --favicon --as logo.svg --dir projets/SneakerLab
```

Le second appel exerce le cas « le fichier est déjà à sa place » : rien n'est
copié, seule la déclaration est ajoutée, et logo et favicon désignent le même
fichier. Le contrat sort `assets/logo.svg` pour les deux (préfixe appliqué une
seule fois), le smoke test fait un vrai GET sur chacun, et le serveur réel
répond 200 en `image/svg+xml`. `monl assets list` sur le projet dit la vérité
sans qu'on lui souffle : douze photos déclarées et présentes, trois fichiers
présents et non déclarés — le fichier de crédits, et les deux sneakers retirés
du catalogue au point 83, laissés sur disque à dessein.

---

## 85. Les quatre règles qui ne faisaient rien

`required`, `unique`, `min` et `max` sont les plus ANCIENNES règles du
compilateur — antérieures à toutes les briques. Elles étaient acceptées par la
grammaire, et **c'est tout**.

Le point de départ n'était pas un soupçon, c'était un chiffre : `schemas.py`
plafonnait à 65 % de couverture, le plus mauvais du générateur. J'ai annoncé au
passage que c'était « le seul endroit où je ne peux pas affirmer que ce qui
n'est pas couvert est sans conséquence », et je suis allé lire. Le bloc non
couvert n'était pas la logique d'écriture client — c'étaient les schémas
d'entrée des blocs `custom`, qu'aucun exemple ni aucun test n'exerçait. En les
éprouvant, deux défauts sont tombés, dont un qui n'avait rien à voir.

### Le premier : `payload.dict()`

La route d'un bloc `custom` appelait `payload.dict()` — **déprécié en Pydantic
v2, retiré en v3**. Vérifié en le déclenchant sous `-W error::DeprecationWarning`,
pas déduit. Tout backend généré portant un bloc `custom` aurait cessé de
fonctionner à la première installation sur Pydantic 3, et rien dans le dépôt ne
l'aurait signalé : aucun exemple, aucun test n'empruntait ce chemin.

### Le second, trouvé par une faute de frappe

En écrivant la spec d'épreuve j'ai tapé `rule Colis.nom required` sur une entité
qui n'a pas de champ `nom`. **Ça a compilé.** En élargissant :

```
⛔ SILENCE : rule Colis.champFantome required
⛔ SILENCE : rule Colis.champFantome unique
   ok refus : rule Colis.champFantome hidden
   ok refus : rule Colis.champFantome generated
   ok refus : rule Colis.champFantome categorized: …
   ok refus : rule Colis.champFantome payable
   ok refus : rule Colis.champFantome derivedFrom …
   ok refus : rule Colis.champFantome sumOf …
⛔ SILENCE : rule Fantome.reference required
```

**Toutes les briques ajoutées depuis le point 24 valident leur référence ; les
quatre règles d'origine, jamais.** L'auteur croit tenir une contrainte, il n'en
a aucune, et rien ne le dit.

### Ce qui a rendu la chose sérieuse

Compilé deux fois le même projet, une fois avec `rule X.f required` et
`rule X.g unique`, une fois sans. **`diff` muet sur `app.py` ET sur
`schema.sql`.** Les quatre règles ne produisaient rien du tout.

Éprouvé contre un vrai serveur : deux POST du même `poids` sur un champ déclaré
`unique` → deux fois 200, deux lignes en base. Puis, sur `exemples/02_boutique.ml`
qui déclare `rule Product.price min 0` et `rule Product.stock min 0` :

```
POST price=-99 stock=-5 → {"status":"success","id":7}
en base → [('Sonde', -99, -5)]
```

**L'exemple livré avec monl portait deux contraintes qui ne faisaient rien.** Et
dans cette boutique-là le prix se multiplie en sous-total (`derivedFrom`), se
somme en total (`sumOf`) et part chez le prestataire (`payable`) : cette borne
était la dernière chose entre le catalogue et un montant négatif encaissé.

### Ce qui a été fait

**La référence est validée** — entité et champ doivent exister, avec suggestion
sur une faute de casse. **`min`/`max` deviennent des contraintes Pydantic**,
donc un 422 avant tout INSERT ; leur portée dépend du type, et cette lecture est
écrite plutôt que devinée : longueur sur `String`/`Text`/`Email`, valeur sur
`Integer`/`Float`/`Money`. Un `max` au-delà de la colonne SQL est refusé (il
promettrait une donnée que la base ne peut pas tenir), un type qui ne se borne
pas aussi, et des bornes contradictoires également.

**`unique` devient un index unique.** Un INDEX et non une contrainte de colonne,
pour une raison qui commande : SQLite ne sait pas ajouter `UNIQUE` à une colonne
existante, alors que `CREATE UNIQUE INDEX IF NOT EXISTS` s'applique à une table
déjà peuplée et reste idempotent — la promesse de migration additive (point 32)
est donc tenue. Sur une base qui contient DÉJÀ des doublons, l'index ne peut pas
naître : c'est un changement non automatisable, et le serveur le NOMME au
démarrage en continuant de tourner, plutôt que de le laisser disparaître dans le
`ℹ️ DB déjà initialisée` qui aurait aussi avalé tout le reste du script.

`required`, lui, reste une assertion : les schémas Pydantic de monl rendent
DÉJÀ tout champ obligatoire. Il est désormais vérifié, pas appliqué — et c'est
dit, plutôt que laissé croire.

### Deux détails qui ne se devinent pas

**Le 409 avait déjà une cause, il en a maintenant deux.** Répondre « référence
invalide » à un doublon enverrait l'appelant chercher un problème qu'il n'a pas :
le message distingue.

**SQLite lève à l'`execute`, pas au `commit`.** La première version entourait le
seul `conn.commit()` de la route Update : le PUT en doublon répondait **500**.
Trouvé contre un vrai serveur. La route Update n'écrivant aucune clé étrangère,
elle n'avait jamais eu de garde — `unique` est la première chose qui pouvait l'y
faire lever.

### Un refus de plus, venu du dialogue

`required` sur un champ que le SERVEUR calcule est désormais refusé. Le contrat
frontend dirait sinon deux choses opposées sur le même champ — « à remplir » via
`required`, « à ne pas envoyer » via `server_generated` — et l'IA d'interface
recevrait deux consignes contradictoires. `unique` reste permis sur ces
champs-là : un pseudonyme `generated` a toutes les raisons d'être unique, et
l'index s'applique en base sans rien demander au client.

`tests/test_contraintes_de_champ.py` (22 tests), dont le plus utile est celui
qui compile avec et sans les quatre règles et **exige que les sorties diffèrent** :
il échoue le jour où l'une d'elles redevient décorative.

---

## 86. Décompter ce que le client a demandé, et le plancher qui l'arme

`decrements` savait retirer une CONSTANTE (`by 3`). C'est juste pour une
réputation ou un like. Une boutique a besoin de retirer *ce que le client a
commandé* — et `exemples/02_boutique.ml` encaissait pour de vrai depuis le
point 74 **sans jamais toucher à son stock** : on pouvait commander cinquante
paires sur douze, et payer. L'interface de `projets/SneakerLab` limitait la
quantité au stock affiché ; l'API, non, et c'est elle qui compte.

La grammaire accepte donc `by <champ>` en plus de `by <entier>`, avec la même
exigence que le multiplicateur de `derivedFrom` (point 77) et pour la même
raison : le champ doit porter `required`, sinon un client qui l'omet ferait
décompter sur du vide.

### Le plancher n'est pas câblé, il est déclaré

Un décompte qui passe sous zéro est un stock qui MENT — la fiche afficherait
« -3 disponibles » après avoir encaissé les huit qu'elle n'avait pas. Mais une
réputation, elle, a parfaitement le droit d'être négative : c'est même l'usage
d'origine de la brique.

Ce qui distingue les deux n'est pas le nom du champ, et surtout pas une
exception « stock » écrite en dur dans le compilateur. C'est la DÉCLARATION
`rule Product.stock min 0`, arrivée la veille avec le point 85. **La
vérification de disponibilité s'arme donc toute seule à partir de ce que la spec
dit**, et reste absente là où rien ne la demande. Les deux points se sont
rencontrés sans avoir été pensés ensemble.

Une SEULE instruction SQL porte la condition et l'écriture :

```sql
UPDATE "product" SET "stock" = "stock" - ? WHERE id = ? AND "stock" - ? >= ?
```

puis `rowcount == 0` → 409, dans la transaction de création : le refus ne laisse
donc aucune ligne derrière lui. Lire le stock puis l'écrire aurait laissé deux
commandes simultanées lire le même chiffre et décompter chacune de son côté.

### Le bug que le SQL généré a montré

La première version écrivait `WHERE id = data.commande_id` : elle décomptait le
stock du produit **portant l'identifiant de la commande**. La colonne visée
venait de `_get_incoming_relation`, c'est-à-dire de la relation « propriétaire »
— et tant qu'une entité déclenchante n'avait qu'UNE relation entrante
(`Report → Member`, `Like → Post`), les deux coïncidaient. `OrderLine` en a
deux. Le compilateur avait déjà connu ce défaut (« un mécanisme de clé étrangère
qui décrémentait le mauvais enregistrement ») ; il est revenu par la porte de la
deuxième relation. Trouvé en LISANT le SQL généré, pas en relisant le code.

Le test correspondant compare avec des identifiants volontairement divergents —
même précaution qu'à la sonde du point 81, où « utilisateur 1 » et « commande 1 »
coïncidaient et ne prouvaient rien.

Second défaut, trouvé contre le serveur : le refus répondait **500**. Le
`raise HTTPException` fermait la connexion avant de lever, et le `except
Exception` de la création la refermait — sur une connexion déjà close.

### Contre-épreuve

Garde-fou neutralisé dans le générateur : exactement trois tests tombent, et la
boutique accepte de vendre ce qu'elle n'a pas (`[200, 200, 200, 200]` au lieu de
`[200, 200, 200, 409]`). Remis : vert.

### Le dialogue guidé rattrape le DSL

Même argument qu'au point 75, resté valable quatre briques plus tard : **une
capacité que le dialogue n'exprime pas n'existe pas** pour qui n'écrit pas la
spec à la main. Le dialogue produisait encore la forme MONO-ARTICLE du point 77
— une commande à un seul article — alors que le compilateur sait faire un panier
depuis le point 82.

Deux questions de plus (« plusieurs articles ? », « décompter un stock ? »), et
il produit désormais la chaîne entière :

```
entity LigneOrder
rule LigneOrder.Read ownedBy Order                              (point 81)
rule LigneOrder.sousTotal derivedFrom Product.price by quantite (point 77)
rule Order.total sumOf LigneOrder.sousTotal                     (point 82)
rule Product.stock min 0                                        (point 85)
rule LigneOrder.Create decrements Product.stock by quantite     (point 86)
rule Order.total payable                                        (point 74)
```

Le champ du stock n'est pas DEVINÉ parmi les entiers du catalogue : le deviner
mal ferait décompter autre chose que ce qu'on croit, en silence. Il est demandé.

Cette sortie a révélé un dernier défaut : le dialogue écrivait `rule Order.total
required` sur un champ que le serveur calcule — d'où le refus ajouté au
point 85. Un dialogue a corrigé un validateur, après qu'un validateur eut
corrigé une question du dialogue (point 75). C'est la troisième fois que les
deux couches se rattrapent l'une l'autre.

### Éprouvé sur la vraie boutique

`projets/SneakerLab`, sur son stock réel de 12 Halo RS :

```
commander 17 paires → 409 « Product.stock insuffisant »
commander 2         → 200
stock 12            → 10
```

`tests/test_stock.py` (11 tests) tient la brique ; `exemples/02_boutique.ml` la
compile.

---

## 87. Encaisser une ligne, et le refus qui protégeait d'autre chose que ce qu'il disait

Le point 81 refusait `payable` sur toute entité possédée à travers un
intermédiaire, avec ce motif :

> la route de règlement identifie le payeur par une clé étrangère de COMPTE,
> qu'une chaîne transitive ne fournit pas.

**C'était exact du code d'alors, et faux de la brique.** La propriété transitive
livrait déjà, dans `_owner_lookup_sql`, la jointure qui rend l'id de compte —
Update et Delete l'employaient depuis le point 81. Seule la route de règlement
avait été écrite avant, et continuait de comparer `current_user_id` à la clé
étrangère brute. Le refus protégeait donc d'une **comparaison fausse**, pas
d'une impossibilité : il fermait un cas légitime pour un défaut situé ailleurs.

Une facture rattachée à un contrat, une prestation rattachée à un dossier, une
ligne d'une commande : toutes ont la même forme, et aucune n'avait de raison
d'être exclue.

### Ce qui a changé, et ce qui ne devait pas changer

La jointure entre **DANS le SELECT existant**, jamais à côté. C'est l'invariant
du point 74 : *le montant, l'état et le propriétaire sortent de la MÊME
lecture*, sinon une fenêtre se rouvre entre le contrôle d'accès et le calcul du
montant. La requête devient

```sql
SELECT t."<montant>", t.payment_status, p."<actor_fk>"
FROM "<table>" t JOIN "<intermédiaire>" p ON p.id = t."<via_fk>"
WHERE t.id = ?
```

et rend exactement le même triplet qu'en propriété directe — donc **la
comparaison qui suit est inchangée**, comme pour Update et Delete au point 81.
Un test compte les `cursor.execute` de la route générée et exige qu'il n'y en
ait qu'un.

Conséquence gratuite et correcte : une ligne ORPHELINE (intermédiaire disparu)
ne rend aucun résultat, donc 404. Elle n'appartient à personne — surtout pas
« payable par quiconque ».

### Ce qui garde la brique sûre n'a pas bougé

Trois refus, tous vérifiés ailleurs et intacts : la chaîne doit remonter à un
acteur (point 81), le montant doit rester incalculable par le client
(point 79 — un test le confirme explicitement sur une entité transitive), et une
relation entrante doit exister (point 75). Le raisonnement du point 79 tient
d'ailleurs mieux ici qu'ailleurs : le créateur d'une ligne doit **prouver qu'il
possède** la commande à laquelle il la rattache (contrôle de création du
point 81), donc il en est bien le propriétaire, donc le payeur.

### La contre-épreuve, et ce qu'elle a montré

Jointure neutralisée dans le générateur, tests relancés :

```
FAILED test_un_tiers_ne_peut_pas_payer
  AssertionError: {"status":"success","url":"https://paiement.example/s", …}
```

**Bob règle la ligne d'Alice, avec succès.** C'est très exactement le trou dont
le refus du point 81 protégeait — et la preuve que le refus visait juste, même
si sa formulation attribuait le défaut à la brique plutôt qu'à la route. Le test
de la ligne orpheline tombe aussi, en 403 au lieu de 404 : un verdict faux dans
l'autre sens.

Les identifiants du banc sont volontairement DIVERGENTS (compte, commande et
ligne portent des id différents). Sans cette précaution, la sonde du point 81
n'avait rien montré parce que « utilisateur 1 » et « commande 1 » coïncidaient ;
la même erreur ici aurait fait passer la contre-épreuve pour un succès.

`tests/test_paiement_transitif.py` (5 tests, faux Stripe embarqué — le montant
est vérifié sur ce que le PRESTATAIRE reçoit). Le test du point 81 qui gardait
le refus a été retourné : il garde désormais l'inverse, avec un témoin qui
vérifie que le refus du point 79 n'a pas été levé au passage.

### Ce qui reste ouvert

La chaîne de propriété ne remonte toujours qu'**UN** intermédiaire. Ce n'est pas
un oubli du point 87 : c'est une décision distincte, avec son propre coût
(jointures à profondeur variable dans quatre chemins d'accès), et rien ne l'a
encore réclamée.

---

## 88. Le back-office, et les deux mensonges qu'il a fait tomber

Demande : la page où le marchand gère les commandes de ses clients. J'ai
commencé par vérifier ce que l'API permettait déjà, plutôt que par imaginer une
brique.

### Ce qui existait déjà, et que je croyais à faire

Je m'attendais à devoir construire un « rôle superviseur » — c'est même listé
comme brique non cadrée depuis le point 31. **Il existe.** Le contrôle de
propriété généré est GARDÉ par l'acteur :

```python
if current_actor not in {"Client", "Patron"}: … 403
if current_actor == "Client":        # ← le filtre ne s'applique qu'à lui
    … vérifie que la commande lui appartient
```

Donc `rule Commande.Update sharedBy Client, Patron` donne exactement la
sémantique voulue : le client ne touche que ses commandes, le patron toutes.
Idem en lecture — `list_order` ne pose son `WHERE customer_id = ?` que pour le
propriétaire désigné. **Zéro ligne de compilateur.** Ce qui manquait à
`projets/SneakerLab` était dans sa propre spec (l'admin n'avait que `Read Order`)
et dans son registre de comptes (aucun compte Admin n'existait).

La leçon est celle du point 87, deux jours plus tôt : *un refus, ou une absence,
peut protéger d'autre chose que ce qu'il annonce*. Il vaut mieux compiler et
lire le code produit que raisonner sur ce dont on se souvient.

### Premier mensonge : la clé étrangère

Le contrat annonçait à l'IA d'interface :

```json
"foreign_keys": [{"column": "customer_id", "references": "Customer"}]
```

et `schema.sql`, dans le même projet :

```sql
FOREIGN KEY ("customer_id") REFERENCES _monl_users(id)
```

**Une clé étrangère de monl référence l'une de DEUX choses** — le registre des
comptes quand la route Create la peuple depuis le jeton (`_identity_fk_columns`,
bêta 3), l'`id` d'une table métier sinon. Le générateur connaît la distinction
depuis longtemps ; le contrat ne la transportait pas.

Ce que ça coûte, sur les données réelles de SneakerLab :

| commande | `customer_id` | jointure suggérée par le contrat | vraie fiche |
|---|---|---|---|
| 7 | 1 | `customer.id = 1` → « bodi » | **bodi** ✅ |
| 8 | 5 | `customer.id = 5` → rien | Sonde (fiche 2) ❌ |

**Une jointure qui marche à moitié.** La pire espèce : juste sur les premiers
enregistrements, c'est-à-dire tant que l'identifiant de compte et celui de la
fiche coïncident, c'est-à-dire pendant les tests. Le back-office aurait affiché
le bon nom sur la commande la plus ancienne, et rien sur les suivantes.

Même motif qu'aux points 76 et 79 : *le contrat décrit ce que la spec déclare,
pas ce que le backend fait vraiment*. Il porte désormais `references_account` et
une note qui dit quoi faire à la place — chercher la fiche dont la colonne
HOMONYME porte la même valeur, jamais celle dont l'`id` la porte. Le brief
lisible le dit aussi : les colonnes de liaison n'y figuraient pas du tout, alors
qu'une page d'administration ne fait presque que ça.

Le test confronte le contrat aux `REFERENCES` **réellement écrits** dans
`schema.sql` — même principe que la confrontation aux décorateurs d'`app.py`
(point 40) — et exige que les DEUX sortes soient représentées dans le jeu
d'essai : un banc qui n'en contiendrait qu'une laisserait passer un contrat qui
répond toujours pareil. Contre-épreuve : ancien contrat rétabli, le test tombe
en nommant les deux versions.

### Second mensonge : « aucun changement d'interface »

Après avoir ouvert le carnet à l'administrateur, `monl update` a répondu :

```
─── Delta du contrat frontend ───
  (aucun changement d'interface — le frontend existant reste valide)
```

Faux. L'admin venait de gagner six accès. `_contract_signature` comparait
`{méthode} {chemin}` et `{Entité}.{champ}` — **jamais QUI a le droit d'appeler**.
Or ouvrir une route existante à un rôle de plus ne crée aucune route : c'est le
changement le plus silencieux qui soit, et c'est précisément celui qui réclame
un écran entier.

« Le frontend existant reste valide » était vrai et trompeur : rien n'était
cassé, et pourtant tout un back-office manquait. Le rapport de delta existe pour
dire ce qu'il reste à écrire, pas seulement ce qui est cassé.

Le delta rapporte désormais `+ accès ouvert` / `- accès retiré`, et la consigne
pour l'IA frontend contient une rubrique dédiée. Un détail qui compte : les
accès d'une route qui vient d'apparaître sont ignorés — ils sont déjà dits par
« route ajoutée », et les compter deux fois noierait le signal qu'on vient
d'ajouter. Un test le vérifie.

### Ce que ça donne en réel

```
── l'admin voit TOUTES les commandes ──
total : 3
  commande   7  en préparation     89 EUR  compte 1  payee
  commande   8  panier              0 EUR  compte 5  en_attente
  commande   9  panier            298 EUR  compte 5  en_attente
── fiches clients, indexées par la colonne homonyme ──
{1: 'bodi', 5: 'Sonde'}

── l'admin fait avancer la commande 7 (compte 1, pas la sienne) → 200
── le client 5 tente la même commande 7                          → 403
```

### Ce qui reste avant la page elle-même

**La date.** Aucune table métier générée par monl ne porte d'horodatage — un
carnet de commandes sans date n'est pas un carnet. C'est le seul vrai manque de
compilateur pour ce back-office, et il ne se rattrape pas : les commandes déjà
passées n'auront jamais de date rétroactive. Prochaine brique.

**Le filtrage.** La route de liste n'offre que `limit`/`offset`. « Les commandes
à expédier » se fera donc côté navigateur, ce qui passe à l'échelle de
SneakerLab et pas au-delà. À décider une fois la page écrite, sur ce qui coince
vraiment — pas maintenant.

---

## 89. La date que personne ne peut se donner, et la colonne qu'on ne rattrape pas

Le point 88 s'achevait sur un constat : aucune table métier générée par monl ne
portait d'horodatage. Un carnet de commandes sans date ne dit ni ce qui est
récent, ni dans quel ordre honorer — le back-office de `projets/SneakerLab`
affichait trois commandes sans moyen de savoir laquelle attendait depuis le plus
longtemps.

```
rule Order.placedAt timestamp
```

Le champ doit être déclaré `DateTime`. Le serveur l'écrit à la création, en
ISO 8601 UTC, et jamais ensuite.

### Ce qui fait la brique, et qui n'allait pas de soi

**Le client ne peut pas la fournir — ni à la création, ni à la modification.**
C'est la même raison que `generated` (point 30) et `derivedFrom` (point 77) :
une date qu'on se donne à soi-même n'atteste de rien. La contre-épreuve tient en
une requête — un POST portant `"placedAt": "2019-01-01T00:00:00+00:00"` doit
produire une commande datée d'aujourd'hui. L'exclure du `SET` de la route Update
évite en prime le 500 du point 78 (`data.<champ>` absent du schéma) : la leçon
« neuf briques testées une par une ne testent pas leurs paires » a servi ici
avant de coûter quelque chose, pour la première fois.

**`Date` est refusé, et le refus explique.** Tronquer au jour perdrait une
information que le serveur possède, et rendrait deux enregistrements du même
jour impossibles à ordonner — c'est-à-dire l'usage même d'un horodatage. `Date`
reste un type légitime partout ailleurs : c'est `timestamp` qui n'en veut pas,
donc c'est `timestamp` qui doit le dire.

**La milliseconde, pas la seconde.** Le contrat annonce que ces chaînes se
trient comme du texte — vrai parce que le décalage est toujours `+00:00` et le
format de largeur fixe. À la seconde près, deux commandes passées coup sur coup
portaient la MÊME date : la propriété qu'on venait d'annoncer devenait fausse
exactement au moment où un carnet en a besoin. Quatre caractères, et le tri
redevient total. Vérifié — deux créations à 30 ms d'écart :

```
  NOUVELLE-1   2026-07-31T01:39:03.397+00:00
  NOUVELLE-2   2026-07-31T01:39:03.427+00:00
```

**Aucun refus nouveau pour les cumuls.** `generated` exige un `String`,
`derivedFrom` et `sumOf` un champ numérique, `payable` de même : un `DateTime`
ne peut porter aucune des trois, et le refus de type tombe avant. Écrire un
quatrième refus inatteignable aurait fait croire à une protection. De même,
`required` et les bornes sont hérités du recoupement du point 85 — il a suffi
d'ajouter les champs horodatés à `peuples_par_le_serveur`, sans une ligne de
plus. C'est le bénéfice de l'avoir groupé là plutôt qu'éparpillé.

### La colonne qu'on ne rattrape pas

La migration additive (point 32) rattrape une colonne absente. Elle ne rattrape
jamais son contenu — et pour toute brique jusqu'ici, ça n'avait aucune
importance : une colonne vide est une colonne vide, le client la remplira. Une
date de création, elle, est **irréparable** : l'instant est passé et le serveur
ne l'a pas vu.

La tentation était un `DEFAULT CURRENT_TIMESTAMP`. Il aurait daté d'aujourd'hui
toutes les commandes d'avant-hier — une base de données qui MENT, ce qui est
strictement pire qu'une case vide. On compte, on nomme, on laisse à `NULL` :

```
🔧 Migration : colonne "placedAt" ajoutée à "order" (TIMESTAMP).
ℹ️ "order"."placedAt" : 3 enregistrement(s) créé(s) avant l'ajout de
   l'horodatage restent sans date. Elle ne peut pas être reconstituée —
   les dater après coup serait faux.
```

Et le contrat frontend le dit à l'IA d'interface : *« PEUT ÊTRE VIDE […] :
afficher un tiret, jamais la date du jour — cette date-là n'a pas été perdue,
elle n'a jamais existé. »* C'est le prolongement de la règle du point 83 —
**monl vérifie la complétude, jamais la véracité** : ici il refuse d'inventer
une donnée qu'il ne peut pas constater.

Sur SneakerLab, en réel — trois commandes d'avant la brique, deux d'après, dont
une où le client a tenté une date de 2001 :

```
  n°7   — jamais horodatee —                    89 EUR  expédiée
  n°8   — jamais horodatee —                     0 EUR  panier
  n°9   — jamais horodatee —                   298 EUR  panier
  n°10  2026-07-31T01:52:55.611+00:00            0 EUR  panier
  n°11  2026-07-31T01:52:55.639+00:00            0 EUR  panier
```

### L'angle mort du point 88, sur l'autre moitié du contrat

En posant la règle sur SneakerLab, `monl update` a annoncé :

```
  + champ ajouté : Order.placedAt
```

dans une rubrique intitulée « Nouveaux champs à afficher/**saisir** ». Faux : ce
champ ne se saisit pas. Et en tirant le fil, un trou plus large est apparu — le
delta comparait des NOMS de champs. Poser `rule Order.total derivedFrom …` sur
un champ qui existait déjà ne renomme rien : la réponse était « aucun changement
d'interface », pendant que le formulaire de prix devenait un champ que le
serveur ignore.

C'est exactement le point 88 sur l'autre moitié du contrat : là, un acteur de
plus sur une route existante ; ici, un sens de plus sur un champ existant. Dans
les deux cas rien n'est cassé, et pourtant l'interface est fausse. **Le pire des
deux, d'ailleurs** : envoyer la valeur n'échoue même pas, elle est silencieusement
écartée — l'utilisateur croit avoir saisi une date.

La signature de contrat porte donc un quatrième ensemble, les champs en lecture
seule, et le delta rapporte `! champ devenu en lecture seule` avec sa rubrique
dans la consigne. Un champ neuf, lui, est annoncé annoté plutôt que dans une
nouvelle rubrique — il est déjà dans « champs ajoutés », l'y compter deux fois
noierait le signal (même arbitrage qu'au point 88).

### Le dialogue guidé l'émet sans poser de question

`_ask_payable` ajoute le champ et la règle à l'entité encaissée, en QUEUE de la
liste — la règle « premier champ requis » de l'émetteur porterait sinon sur un
champ que le client ne peut pas envoyer, et la compilation échouerait sur le
recoupement du point 85.

Aucune question ne le propose, volontairement : la date est écrite par le
serveur, donc elle ne peut pas être fausse, et une commande sans date n'est pas
une commande — la seule réponse utile serait « oui ». Le dialogue émet déjà de
même le total, le plancher de stock et le décompte sans les faire arbitrer un
par un.

### Éprouvé par

`tests/test_horodatage.py` (20 tests) : dix refus de compilation, quatre
vérifications sur le code écrit — dont celle qui exige que compiler AVEC et SANS
la règle donne des sorties différentes, discipline du point 85 — et six contre un
serveur réel, y compris le redémarrage sur une base déjà peuplée. Les deux
garde-fous ont été neutralisés un par un : sans l'exclusion du schéma d'entrée,
quatre tests tombent ; sans celle du `SET`, deux. Plus deux tests de delta dans
`tests/test_orchestrator.py`, et un dans `tests/test_app_templates.py` pour le
dialogue.

---

## 90. On ne commande pas sans être identifié

Le point 89 posé, le back-office avait sa date. Il lui manquait toujours le
client. Une inspection de la base de `projets/SneakerLab` a montré pourquoi :

```
commande 7   compte 1  login=bodi       fiche=bodi
commande 8   compte 5  login=sonde_neg  fiche=Sonde
commande 10  compte 7  login=sondeur    fiche=— AUCUNE —
commande 11  compte 7  login=sondeur    fiche=— AUCUNE —
```

**Rien n'obligeait à créer une fiche avant de commander.** Et le registre des
comptes (`_monl_users`) n'est exposé par aucune route — délibérément, il porte
les empreintes de mots de passe. L'administrateur voyait donc une commande qu'il
ne pouvait attribuer à personne : ni nom, ni adresse, ni moyen d'en obtenir un.
Pour une boutique, ce n'est pas un défaut d'affichage : c'est une **commande
inexpédiable**.

```
rule Order.Create requiresOwn Customer
```

### Le choix entre deux voies, et pourquoi celle-ci

La première idée était d'exposer l'identité du compte aux rôles autorisés — un
`revealsAccount` déclaratif. Elle a été écartée pour deux raisons qui se
renforcent : **un login ne s'expédie pas** (l'admin aurait su *qui*, sans jamais
savoir *où*), et ça entamait la promesse du pseudonyme `generated` (brique 7),
qui existe précisément pour qu'une identité de compte ne transpire jamais dans
une réponse.

Garantir la fiche règle le fond sans toucher à l'authentification. Et une fois la
fiche garantie, lui ajouter `email` et `address` suffit à rendre la commande
expédiable — ce qui est le vrai besoin, et ne demande aucun compilateur.

### Les décisions

**La vérification vient EN PREMIER**, avant le contrôle du parent (point 81) et
avant tout calcul `derivedFrom`. Deux raisons distinctes : un appelant sans fiche
n'a pas à apprendre si tel produit existe, et sur une entité qui décompte du
stock, une vérification tardive laisserait le décompte se produire avant le
refus.

**409, pas 403.** Ce n'est pas un droit qui manque — c'est un état à corriger, et
le message dit lequel : *« Créez d'abord votre fiche Customer. »* Un 403
laisserait croire à un compte mal provisionné, donc à un problème qu'on ne peut
pas résoudre soi-même.

**La fiche est cherchée par identifiant de COMPTE**, via `_identity_fk_columns` —
la source unique installée au point 88. Un `WHERE id = ?` trouverait la fiche de
quelqu'un d'autre dès que l'id de compte et l'id de ligne divergent, c'est-à-dire
partout sauf sur les premiers enregistrements. Un test l'exige explicitement.

**Seule `Create` peut l'exiger.** Sur Read, Update ou Delete, l'enregistrement
existe déjà : une fiche exigée a posteriori ne protégerait rien et rendrait
inaccessibles des données qu'on possède. Refus explicite.

L'erreur qu'on écrit naturellement — « existe-t-il au moins une fiche ? » — est
attrapée par un test qui emploie DEUX comptes dont un seul a la sienne. Sans lui,
la première fiche créée sur la boutique ouvrirait la commande à tout le monde.

### Le troisième angle mort du delta

En posant la règle sur SneakerLab, `monl update` a répondu **« aucun changement
d'interface »**. La route n'avait ni changé de chemin, ni d'acteurs, ni de
champs. Elle avait gagné une CONDITION — et c'est tout le parcours d'achat qu'il
fallait reprendre.

C'est la troisième fois que le même angle mort se manifeste :

| Point | Ce qui change sans rien renommer |
|---|---|
| 88 | un ACTEUR de plus sur une route existante |
| 89 | un champ qui devient calculé par le serveur |
| 90 | une route qui gagne un PRÉALABLE |

Trois fois la même leçon : **le delta doit comparer tout ce que le contrat
promet, pas seulement ce qui porte un nom nouveau.** La signature de contrat
compte désormais cinq ensembles. Le contrat, lui, porte `requires_own` et une
note qui dit *quand* vérifier — « proposer la création AVANT le formulaire » :
découvert à la fin, le refus tombe là où l'utilisateur a déjà tout rempli.

### Ce que ça ne répare pas

Les commandes 10 et 11 restent orphelines. La règle empêche les suivantes, elle
ne reconstitue pas les précédentes — même limite que l'horodatage du point 89, et
pour la même raison : monl vérifie la complétude, il n'invente pas de donnée.

### Éprouvé par

`tests/test_fiche_obligatoire.py` (17 tests) : neuf refus de compilation, quatre
vérifications sur le code écrit — dont l'ordre des requêtes et la colonne
employée — et quatre contre un serveur réel, dont celui des deux comptes. Les
deux erreurs plausibles ont été injectées : vérification non portée sur
l'appelant (2 tests tombent), garde-fou retiré (5 tombent). Plus un test de delta
dans `tests/test_orchestrator.py`.

---

## 91. Ce qu'on a encaissé ne se remodifie plus

`payable` (point 74) garantissait que le montant encaissé venait de la BASE, et
les points 77 à 82 ont fermé, un par un, les chemins par lesquels le client
pouvait écrire ce montant. Aucun de ces points ne s'est demandé ce qui se passe
**après** l'encaissement. La réponse, mesurée sur `projets/SneakerLab` avant
d'écrire une ligne de code, était : tout.

Une commande réglée 89 € acceptait une paire à 149 € — la route `POST /orderline`
recalculait consciencieusement le total à **238 €**, `payment_status` restant
`payee`. Porter la quantité à cinq donnait **594 €**. Le back-office affichait
« Payée » en face d'un montant que personne n'avait réglé. C'est la faille du
point 77 revenue par la seule porte que ces points n'avaient pas regardée : non
plus « quel montant le client peut-il écrire », mais « pendant combien de temps ».

### Le verrou, et pourquoi il ne pouvait pas se poser sur la seule commande

Verrouiller l'entité payable en `Update` et `Delete` était l'idée évidente, et
elle n'aurait servi à rien : le total ne se modifie pas par la commande, il se
modifie par la LIGNE. Le verrou vit donc là où le total se recalcule —
`_payment_locked_parents` (generator/core.py) est le pendant exact de
`_aggregation_recomputes` : **partout où une écriture recalcule la somme d'un
parent, ce parent peut déjà avoir été encaissé.** Cinq portes, pas une : Update
et Delete de la commande, Create, Update et Delete de la ligne.

Trois décisions à ne pas rouvrir.

**409 et non 403.** Ce n'est pas un droit qui manque — le propriétaire est bien
chez lui — c'est un état devenu définitif. Le message renvoie vers un
remboursement chez le prestataire, seul endroit où l'argent peut revenir.

**Le parent est relu EN BASE en `Update`/`Delete`, depuis la clé étrangère
STOCKÉE.** Le corps de requête peut désigner une autre commande que celle à
laquelle la ligne appartient : on verrouillerait sur la commande d'à côté et on
laisserait modifier celle qui est payée. C'est la leçon du point 78, pour la
troisième fois — elle vaut pour toute lecture de parent, pas seulement pour les
montants. En `Create`, le parent vient de `data.<fk>`, mais il a été validé juste
au-dessus par la propriété transitive (point 81) : c'est bien la commande de
l'appelant.

**La garde vient AVANT tout calcul et tout décompte.** Placée après, un refus
aurait déjà consommé du stock — même raisonnement qu'au point 90.

La contre-épreuve est dans le test, et elle est la moitié qui compte : *avant*
règlement, les cinq écritures passent toujours. Un verrou qui figerait tout
ferait passer les cinq premiers tests sans rien garantir, et rendrait la boutique
inutilisable.

### L'angle mort du contrat et du delta, quatrième fois

Un backend qui refuse et un frontend qui l'ignore font une interface qui ment.
Le verrou ne change **ni chemin, ni acteur, ni champ** : c'est exactement la
forme des angles morts des points 88 (un acteur de plus), 89 (un champ devenu
calculé) et 90 (une route qui gagne un préalable). Quatrième fois, même
conclusion, et il faut la considérer comme une règle plutôt que comme une série
de coïncidences : **toute brique qui ajoute une promesse au contrat doit se
demander si `_contract_signature` (cli.py) la voit.** Elle compte désormais
**six** ensembles.

Le contrat porte donc `payment_locked` sur chaque route verrouillée, plus une
note qui dit quoi en faire — conditionner le bouton à `payment_status`, que les
routes de lecture renvoient déjà (point 76). Et `monl update` rapporte
`! verrou de paiement : PUT /commande/{id} → figé une fois Commande réglé`, avec
la rubrique correspondante dans la consigne pour l'IA. Un verrou porté par une
route qui vient d'APPARAÎTRE est exclu du rapport : déjà dit par « route
ajoutée », même arbitrage anti-doublon qu'aux trois points précédents.

**Le trou que l'écriture du contrat a révélé, lui, était dans le contrat.** La
note du verrou n'avait été posée que sur `Update` et `Delete` — les deux routes
auxquelles on pense quand on dit « figé ». `POST /ligne` ne portait rien, alors
que le backend refusait déjà d'y rattacher une ligne de plus : une IA fidèle au
contrat dessinait un « + Ajouter un article » sur une commande payée, et le refus
se découvrait au clic. C'est la cinquième porte du verrou, celle par laquelle le
total remontait, oubliée dans la seule couche qui parle à l'interface.

La nuance qui va avec : la création se verrouille par un **parent** réglé,
jamais par l'entité payable elle-même — d'où le `inclure_soi=False` de
`_verrou_paiement`. Ouvrir une commande de plus reste permis ; c'est y ajouter
une ligne qui est refusé. Un verrou annoncé là ferait disparaître le bouton
« Commander », et le témoin qui l'interdit est dans les tests.

La route de règlement, elle, lit aussi `payment_status` et refuse un second
paiement — mais ce n'est pas ce verrou-ci, et sa propre note le disait déjà
(« 409 s'il est déjà réglé »). Le test de non-divergence les distingue par le
message de `_payment_lock_lines`, pas par la simple présence de `'payee'` : ce
qui est confronté n'est pas une liste de chemins attendus, mais l'ÉGALITÉ entre
ce que le contrat annonce et ce que `app.py` garde réellement.

### Le décompte qui ne s'armait qu'une fois

Même sonde, autre trou : `rule OrderLine.Create decrements Product.stock by
quantity` (point 86) ne s'armait qu'à la CRÉATION. Créer une ligne à 1 puis la
passer à 4 facturait quatre paires et n'en décomptait qu'une — stock 16 → 15
pour 528 € facturés. Le point 78 déplacé de l'argent vers la marchandise.

La route `Update` applique désormais le **DELTA**, pas la nouvelle quantité : la
ligne a déjà consommé son ancienne valeur. Un delta négatif rend du stock, et la
condition `>= plancher` reste vraie — inutile de traiter les deux sens
séparément, une seule instruction SQL suffit, comme à la création. Quantité et
clé étrangère sont relues en base, toujours pour la même raison.

### Deux réparations plus petites, du même passage

**Le type `Email` ne vérifiait rien.** Il ne fixait qu'une longueur de colonne
(320) : `'pas-un-courriel'` entrait en base avec un 200, et le colis ne partait
nulle part. C'est exactement ce que le point 85 refuse — une règle qui ne produit
rien. Un motif est désormais posé dans le schéma Pydantic. Il est volontairement
large (une arobase, un point après, aucun espace) : **monl vérifie la forme, il
ne peut pas attester qu'une boîte existe** — cela demanderait un envoi, donc un
appel sortant que le compilateur s'interdit partout ailleurs que chez le
prestataire de paiement.

**La signature du webhook n'était pas datée.** L'horodatage était LU pour
vérifier la signature, jamais comparé à l'heure. Un appel légitime capté une fois
restait donc rejouable indéfiniment. Tolérance de cinq minutes, comme le
documente Stripe. Les tests existants signaient avec `t=1700000000` — une date de
novembre 2023 — et passaient précisément parce que le serveur ne datait rien :
ils signent maintenant à l'heure courante, comme le vrai prestataire.

### Ce que ça ne répare pas

**Le statut reste un texte libre.** Sur une commande NON réglée, le client pose
encore `status: "livrée"` et le serveur l'accepte : il n'existe aucune brique
« valeur parmi une liste ». Le verrou ne le couvre qu'une fois l'encaissement
fait. C'est la prochaine brique évidente de cette série, et elle n'est pas
écrite.

Restent aussi hors de portée, et assumés : les frais de port et la TVA (le total
est la somme des lignes, rien d'autre — une décision produit, pas un défaut du
compilateur), l'unicité d'une adresse (une ligne de spec, `rule X.email unique`,
la brique existe depuis le point 85), et tout envoi de courriel.

### Éprouvé par

`tests/test_verrou_paiement.py` (15 tests) : les cinq portes fermées contre un
vrai serveur et un faux Stripe, avec vérification que le total n'a pas bougé d'un
centime après chaque refus ; la contre-épreuve des cinq écritures avant
règlement ; le non-débordement sur la commande d'à côté ; le rejeu d'un webhook
vieux de dix minutes ; et le type `Email` dans les deux sens (cinq adresses
refusées, deux acceptées — un motif trop strict passerait le premier test).
Plus trois tests de décompte au PUT dans `tests/test_stock.py`, qui a gagné
`Update Ligne` dans son banc : sans cette action, la brique n'avait aucune façon
d'être prise en défaut.

Et quatre tests dans `tests/test_orchestrator.py` pour la couche contrat : la
non-divergence entre `payment_locked` et les gardes réellement écrites dans
`app.py` (avec le témoin `POST /commande`, qui ne doit JAMAIS être verrouillé),
le témoin sans `payable` — un panier de pièces détachées reste modifiable, sans
quoi un verrou qui figerait tout passerait tous les autres — le delta de
`monl update`, et le non-doublon sur une route qui naît déjà verrouillée.

## 92. Le stock qui ne revenait jamais, et la variable qui fuyait

Le point 91 fermé, une seconde sonde a été passée sur `projets/SneakerLab` —
serveur réel, appels réels, quatorze questions posées au serveur plutôt qu'au
code. Le contrôle d'accès tient, les rôles tiennent, le préalable de fiche tient,
l'horodatage tient. Trois défauts sont tombés, dont **deux introduits par le
point 91 lui-même**.

### Le troisième branchement, celui qu'on oublie

Commander trois paires puis vider son panier laissait le stock à **9 sur 12**.
Le décompte s'armait à la création (point 86), puis à la modification
(point 91) — jamais à la suppression. Le total du parent, lui, redescendait bien
à zéro depuis le point 82 : la base se contredisait donc elle-même, et le
catalogue s'épuisait sans qu'une seule paire ait été vendue. Sur une boutique
dont les stocks vont de 5 à 28, il suffit de quelques paniers abandonnés pour
afficher « épuisé » sur toute une série.

Le point 82 avait pourtant NOMMÉ le piège, pour l'agrégation : « trois
branchements, et le troisième est celui qu'on oublie — création, modification,
suppression ». Il l'avait nommé et traité pour `sumOf`. Le décompte, arrivé
quatre points plus tard, ne l'a pas hérité : **une leçon écrite dans un point ne
protège pas la brique du point suivant**, et c'est la seule raison pour laquelle
ce défaut a vécu six points.

**La restitution ne porte AUCUN garde-fou de plancher**, et c'est le seul choix
qui tienne : elle rétablit un état qui a existé et qui était valide. Un
`decrements` rendu ne fait que remonter ; un `increments` repris ne redescend pas
plus bas que la valeur d'avant la création. Un plancher ici ne protégerait rien
et interdirait d'annuler une commande — exactement ce qu'on répare. La quantité
et la clé étrangère sont relues EN BASE **avant** le `DELETE` : après, la ligne
n'existe plus et rien ne dit quoi rendre ni à qui (même ordre qu'au point 82,
deux instructions plus haut dans la même route).

La restitution rend la quantité **courante**, pas celle de la création : une
ligne créée à 1 puis passée à 3 a consommé 3. C'est automatique puisqu'on lit la
base, mais c'est ce que le test vérifie — le lire ailleurs laisserait deux paires
évaporées.

### La variable qui fuyait d'une branche à l'autre

Le décompte au PUT (point 91) lisait `reputation_rules_here` : une variable
assignée dans la branche `Create` de la boucle de génération, relue dans la
branche `Update`. Elle contenait donc les règles de la **dernière entité créée**,
pas de celle qu'on modifie. Deux conséquences, les deux vérifiées :

* une spec qui a un `Update` **sans aucun `Create`** faisait planter le
  compilateur — `cannot access local variable`. Aucun exemple, aucun test
  n'exerçait ce chemin : toutes les specs du dépôt créent quelque chose ;
* un `Update` précédé de la création d'une **autre** entité héritait de ses
  règles. Sur une spec à deux entités liées au même produit, **modifier un avis
  décomptait le stock** — la règle appartenait à la ligne de commande.

Ce qui masquait le défaut est instructif : quand `Create X` précède
immédiatement `Update X` dans l'ordre des routes, la variable contient les bonnes
règles et tout fonctionne. Il suffit qu'une autre entité s'intercale. **Un bug
d'ordre d'itération ne se voit pas sur la spec qui l'a fait naître.**

Le correctif tient en une ligne — relire les règles depuis
`reputation_rules_by_trigger` dans la branche qui en a besoin — mais il vient
avec une source unique, `_decrement_fk_column` (generator/core.py) : la colonne
de rattachement était recalculée à l'identique dans chaque branchement, et c'est
précisément là qu'a vécu le bug du point 86. La recopier une troisième fois,
c'était en préparer la troisième occurrence.

### L'avertissement qui criait au loup

`monl run --check` signalait quatre chemins « absents du contrat » sur
SneakerLab : `/admin`, `/catalogue`, `/commandes`, `/compte`. Aucun n'était un
défaut — ce sont les routes de NAVIGATION d'une application monopage
(`href="#/catalogue"`, puis `aller('/catalogue')` en JavaScript). Le vérificateur
prenait tout littéral commençant par `/` pour une URL d'API.

Un avertissement qui se trompe sur un site correct n'est pas prudent : **il
apprend à ne plus lire les avertissements**, et le jour où il dit vrai personne
ne le lit. Il valait donc mieux l'affûter que le supprimer — la preuve est dans
le fichier lui-même : si `#/x` y figure, `/x` est une route de navigation. Un
vrai chemin d'API mal tapé, lui, n'apparaît jamais derrière un dièse, et reste
signalé. C'est le même arbitrage qu'au point 57, sur le même avertissement.

### Ce que la sonde a confirmé, et qui ne change pas

Le reste tient, et le dire vaut autant que le reste : un client ne voit ni les
commandes ni les fiches d'autrui, ne crée pas de ligne chez un tiers (403), ne
s'inscrit pas en `Admin` (403), ne commande pas sans fiche (409) ; l'`Admin` voit
tout le carnet et modifie les statuts (point 88) ; prix et stock négatifs sont
refusés (422), un produit encore commandé n'est pas supprimable (409), le
rattachement d'une ligne ne se déplace pas, et `placedAt` comme `total` ignorent
ce que le client prétend leur donner.

Deux constats sans correctif, assumés : le **statut reste un texte libre**
(déjà noté au point 91 — c'est la prochaine brique), et **annuler** une commande
côté SneakerLab la passe en `annulée` sans rendre le stock, puisque ses lignes
demeurent. Rendre le stock sur un changement de statut supposerait une brique
« effet déclenché par une valeur », qui n'existe pas et qui commence par
« valeur parmi une liste ». Le parcours qui rend vraiment le stock — supprimer
les lignes puis la commande — est celui du bouton « Vider le panier », et il est
correct depuis ce point.

### Ce que ça ne répare pas

**Les unités déjà perdues.** Comme au point 90, la brique ne rattrape pas
l'existant : un stock amputé par un panier abandonné avant ce correctif le reste,
et seul un `UPDATE` à la main le rétablit. La migration additive (point 32)
rattrape une colonne, jamais l'historique de ce qui s'est passé dessus.

### Éprouvé par

`tests/test_stock.py`, qui gagne `Delete Ligne` dans son banc — sans cette
action, la brique n'avait toujours aucune façon d'être prise en défaut, exactement
comme il avait fallu ajouter `Update Ligne` au point 91. Huit tests : la
restitution simple, la quantité courante et non celle de la création, le produit
visé et pas un autre, le cycle vider/recommander trois fois (la forme sous
laquelle le défaut se voyait en production), l'absence de plancher sur la
restitution, l'ordre lecture-avant-suppression, et les deux régressions de la
variable qui fuyait — la spec sans `Create`, et l'entité qui héritait des règles
d'une autre. Plus un test dans `tests/test_orchestrator.py` pour l'avertissement
affûté, avec son témoin : un chemin réellement fautif doit rester signalé.

## 93. Retoucher sans reconstruire

Le site de `projets/SneakerLab` était juste au regard du contrat, vérifié vert
par `monl run --check` — et ses trois images de tendance étaient mal cadrées.
Entre ces deux états, monl n'avait **aucun geste** :

* `monl frontend` RECONSTRUIT. On jette un site bon à 95 % pour un tirage non
  déterministe, dont on peut perdre ce qu'on aimait ;
* `monl update` ne parle que du **delta de spec**. Ici la spec n'a pas bougé :
  il répond, à juste titre, « aucun changement d'interface » ;
* restait l'édition à la main, c'est-à-dire hors de la boucle de vérification.

`monl retouche "<ce qui cloche>"` comble exactement ce trou, et **ne fait rien
de neuf** : elle réutilise la voie d'évolution du point 4 en changeant la seule
chose qui manquait — l'origine du brief, une phrase humaine au lieu d'un diff.

### Une seule voie vers l'IA, et c'est le point

Le dispatch appelait l'IA en ligne dans `main()`. Recopier ces quinze lignes
pour la retouche aurait fait **deux chemins vers le modèle, donc deux endroits
où les garde-fous peuvent diverger** — ce que CLAUDE.md interdit nommément
(« ne jamais contourner le garde-fou d'empreinte en ajoutant une voie »). D'où
`_lancer_ia`, partagé, et `brief_evolution()` qui ne décide QUE du nom du brief.
Empreinte des artefacts protégés, empreinte du frontend qui doit bouger
(point 73), cohérence, smoke test, une correction au plus : tout est commun, et
un test le vérifie en lançant un agent malveillant par la voie retouche.

### Trois décisions

**Ne rien changer est un ÉCHEC.** Sur une construction, « l'agent n'a rien
écrit » est un avertissement : un frontend valide existait déjà (point 73). Sur
une retouche, c'est la demande non traitée — l'humain a signalé un défaut qu'il
VOIT, et répondre « tout va bien » serait le contraire d'un rapport honnête. La
commande sort en erreur et suggère de nommer l'écran et l'élément.

**L'interprétation la plus ÉTROITE.** Sans cette consigne, « les images sont mal
cadrées » invite à refaire la mise en page — et une retouche trop large ne se
distingue plus d'une reconstruction, c'est-à-dire de ce qu'on évite. La consigne
le dit, et le résultat l'a confirmé : 20 lignes modifiées sur ~2500, les seules
tuiles de tendance.

**Une sauvegarde systématique.** `monl import` sauvegarde depuis toujours ; la
retouche en a plus besoin encore, puisqu'elle porte sur un site qui MARCHE. Une
COPIE et non un déplacement : l'IA doit trouver l'existant en place pour le
faire évoluer.

### Ce que monl ne promet pas, et qu'il faut dire

Que le résultat soit plus **beau**. Le smoke test prouve que la page tourne
encore et respecte le contrat, jamais que le cadrage s'est amélioré. Même
honnêteté qu'au point 83 : **monl vérifie la complétude, pas le goût.** C'est
précisément pourquoi la sauvegarde est systématique — la seule garantie qu'on
puisse offrir sur une question de goût, c'est de pouvoir revenir en arrière.

### Éprouvée en réel

Sur SneakerLab, par la voie `claude-code`. La demande — « les trois images de la
section Tendances sont mal cadrées, la chaussure apparaît petite et placée trop
bas » — a produit un `--cadrage` réglable par photo (1,12 / 1,18 / 1,42), avec
`object-position: center bottom`. Les trois valeurs suivent réellement le vide de
chaque cliché : `tendance-ville.jpg` a ~45 % de blanc au-dessus du sujet, et
c'est elle qui reçoit le cadrage le plus fort. Plus huit tests dans
`tests/test_smoke_and_frontend_ai.py`, avec agent factice : la consigne et la
sauvegarde, les deux refus (pas de frontend, demande vide), le contenu du prompt,
l'instruction de retouche distincte de celle de construction, la retouche vide
qui échoue, l'agent malveillant qui reste bloqué, et le bout en bout où
l'existant n'est PAS réécrit.

## 94. Une FAQ est une liste, et le contenu que le delta ne regardait pas

Sur SneakerLab, les quatre questions fréquentes sortaient **collées en un seul
paragraphe**. Le premier réflexe était d'accuser le frontend ; il était fidèle.
Dans la spec, les quatre questions tenaient dans UNE chaîne :

```
section "Questions fréquentes": "Comment choisir ma taille ? Nos paires
taillent normalement… Puis-je annuler une commande ? Oui, tant qu'elle est…"
```

Et la grammaire ne connaissait qu'une forme — `section "titre": "texte"`. L'IA a
reçu un bloc de prose et en a fait un `<p>`. **C'est le modèle de contenu qui ne
savait pas dire « une FAQ ».**

La leçon vaut au-delà du cas : une retouche n'aurait pas réparé ça proprement.
Elle aurait fait deviner à l'IA où commencent les questions, en découpant sur
les points d'interrogation — une structure devinée, qui se reperd à la
reconstruction suivante. La consigne de retouche le dit désormais en toutes
lettres : un défaut qui vient de ce que la spec ne dit pas doit être signalé, pas
contourné par une astuce d'affichage.

### La forme retenue, et celle qui a été écartée

`question "…": "…"` **répétable dans `landing`**, exactement comme `section`.
Un sous-bloc `faq` indenté aurait ajouté un niveau d'indentation à la seule
grammaire où l'indentation a déjà coûté deux bugs (point 6 : un commentaire seul
dans un bloc indenté faisait échouer le parsing). La FAQ est donc la collection
des `question` du bloc, et **l'ordre de déclaration est conservé** : dans une
FAQ il porte du sens — on répond d'abord à ce qu'on demande le plus — et rien ne
permettrait de le retrouver après coup.

Le contrat porte `faq` comme une liste de couples, et le brief le dit en toutes
lettres : *une LISTE, pas un texte suivi ; jamais en un seul paragraphe*. Sans
cette phrase, déposer les couples dans la même rubrique que les sections laissait
refaire exactement le pavé qu'on répare — l'IA ne lit pas le JSON, elle lit le
brief.

### L'angle mort du delta, cinquième fois — et la première hors des données

En écrivant la brique, la question du point 88 s'est posée d'elle-même : *est-ce
que `_contract_signature` la voit ?* Non. Et pas seulement la FAQ : **le contenu
éditorial n'y a JAMAIS figuré**. Ajouter une rubrique « à propos » ne touche
aucune route, aucun champ — `monl update` répondait « aucun changement
d'interface » avec un bloc entier à écrire sur l'accueil. L'angle mort existait
pour `section` depuis le point 55 ; la FAQ y serait tombée le jour de sa
naissance.

Le delta compte donc **sept** ensembles, et le septième est un DICTIONNAIRE là
où les six autres sont des ensembles : le texte compte autant que le titre.
Comparer les seuls titres serait l'erreur exacte du point 89 — réécrire
« Livraison et retours » de fond en comble ne renomme rien, et il faut pourtant
re-rendre la page. D'où trois cas et non deux : ajouté, retiré, **réécrit**.

Cinq fois la même leçon, sur cinq briques différentes. Ce n'est plus une série de
coïncidences : c'est une question à poser à chaque brique qui ajoute une promesse
au contrat, et elle mérite d'être posée avant d'écrire le code plutôt qu'après.

### Éprouvé par

Six tests dans `tests/test_orchestrator.py` : la FAQ comme liste de couples et sa
non-confusion avec les sections, l'ordre conservé, le brief qui dit qu'il s'agit
d'une liste, le témoin (sans `question`, aucune trace dans le brief), le refus
d'une question sans réponse, et le delta sur ses trois cas — dont le silencieux.
Appliqué en réel à `projets/SneakerLab` : `monl update` a rapporté les quatre
questions ajoutées et la section retirée, et l'IA a rendu un `<dl>` de quatre
entrées numérotées, dans l'ordre déclaré.

## 95. S'inscrire avec son adresse, et la forme canonique qui porte la brique

`POST /register` prenait un `username` libre. Sur une boutique réelle, c'est un
non-sens : `projets/SneakerLab` demandait un pseudonyme au compte, puis une
adresse e-mail dans la fiche client — **deux identités pour une personne**, et
un compte auquel on ne peut rien envoyer.

La brique 1 (`capability auth`) attendait depuis le début. Elle traversait tout
le pipeline — grammaire, validateur, AST normalisé, générateur — sans changer une
ligne du code produit ; CLAUDE.md le notait comme « cohérent, elle n'a par
construction aucun effet sur la génération ». C'est sa **première vraie
fonction** :

```
capability auth
    identifier: email, phone
```

Le bloc indenté est **optionnel**, et c'est la condition pour qu'une brique
dormante se réveille sans rien casser : toute spec écrite avant ce point compile
à l'octet près. `None` (rien de déclaré) n'est pas `[]` (aucune forme valide) —
deviner « email par défaut » aurait verrouillé tous les projets existants au
premier recompilage.

### Ce que la brique n'est PAS : de la validation

Vérifier qu'une chaîne ressemble à une adresse est la partie facile, et la moins
utile. **La substance est la NORMALISATION.** `Jean@Ex.com` et `jean@ex.com` sont
la même boîte ; `06 12 34 56 78`, `+33612345678` et `+33 (6) 12.34.56.78` le même
numéro. Sans forme canonique :

* le contrôle d'unicité se contourne en changeant une majuscule — **deux comptes
  pour une personne**, et le second reçoit les commandes du premier ;
* la connexion échoue selon la façon dont on tape, ce que personne ne retient.

La valeur STOCKÉE est donc la forme canonique, et c'est sur elle que porte
l'unicité. Sur l'e-mail, seul le domaine est officiellement insensible à la
casse — mais aucun fournisseur réel ne distingue la partie locale, et ne pas
l'abaisser laisserait ouvrir deux comptes pour une seule boîte : exactement ce
que l'unicité est censée empêcher.

**Aux TROIS endroits, et le troisième est celui qu'on oublie.** `/register`,
`/login` et **`manage.py`**. Normaliser d'un seul côté crée des comptes auxquels
on ne peut pas se connecter : un compte provisionné hors ligne avec
`Patron@Ex.com` serait stocké tel quel pendant que la connexion, elle,
chercherait `patron@ex.com`. Le contrôle de FORME, en revanche, n'est
délibérément pas appliqué dans `manage.py` : l'administrateur travaille sur la
machine qui héberge la base et provisionne parfois des rôles de service, qui
n'ont ni adresse ni numéro.

### Trois décisions de plus

**Le champ reste `username` sur le fil.** Le renommer en `email` aurait cassé le
formulaire d'inscription de tout projet existant pour un gain cosmétique. C'est
le CONTRAT qui dit ce qu'il doit contenir (`identifier_forms`, plus une note qui
dit d'étiqueter l'écran et de choisir `type="email"` ou `type="tel"`), et l'IA
d'interface qui en tire l'écran. Le contrat décrit ce que le backend fait
vraiment — points 76, 79, 88, 89 — et ici « ce qu'il fait » inclut ce qu'il
REFUSE.

**401 à la connexion, jamais 422.** La forme n'est pas vérifiée à `/login` : un
identifiant mal formé n'existe simplement pas en base, et le 401 habituel répond
sans apprendre à un attaquant quelle forme les comptes ont. Même famille de
raisonnement que le correctif d'énumération par canal temporel de la bêta 3.

**Le message de conflit nomme ce qui est en conflit.** « Ce nom d'utilisateur
existe déjà » ne veut rien dire sur une inscription par e-mail — d'autant que le
conflit est souvent invisible pour l'appelant, puisqu'il porte sur la forme
normalisée de ce qu'il a tapé.

### Le delta, sixième fois — et la question posée AVANT cette fois

Le point 94 concluait que « toute brique qui ajoute une promesse au contrat doit
se demander si `_contract_signature` la voit » mérite d'être posée **avant**
d'écrire le code. Elle l'a été. Réponse : non. Déclarer `identifier: email` ne
crée aucune route et ne renomme aucun champ — le corps de `/register` garde les
mêmes clés — mais l'écran d'inscription change entièrement : étiquette, type de
saisie, message d'erreur. Sans ajout, `monl update` aurait répondu « aucun
changement d'interface » pendant qu'un formulaire se mettait à répondre 422 sans
expliquer pourquoi.

### Ce que ça ne répare pas, et ce que monl ne peut pas faire

**Les comptes existants.** Déclarer `identifier: email` ne les efface pas et ne
les convertit pas — on n'invente pas une adresse. Ils continuent de se connecter,
et le serveur les COMPTE et les NOMME au démarrage, comme le point 89 le fait
pour les horodatages manquants. La règle ne vaut que pour les inscriptions à
venir, et le dire vaut mieux que laisser croire à une application uniforme.

**La vérification.** monl contrôle la FORME, jamais l'existence : attester
qu'une boîte reçoit ou qu'une ligne sonne demanderait un envoi, donc un appel
sortant que le compilateur s'interdit partout ailleurs que chez le prestataire
de paiement. C'est la limite déjà énoncée au point 91 pour le type `Email`, et
elle emporte le reste : **pas de code de confirmation, pas de récupération de
mot de passe par courriel.** Ce sont des briques à part, qui commencent toutes
par « monl sait envoyer un message » — ce qu'il ne sait pas faire.

Le motif de numéro est volontairement large (indicatif optionnel, séparateurs
usuels, 6 à 15 chiffres — E.164 plafonne à 15). Un motif strict refuserait des
numéros valides ailleurs qu'en France, et monl n'a aucun moyen de savoir d'où
appelle l'utilisateur.

### Un défaut que seule l'exécution a montré

Le `app.py` généré **ne démarrait pas** : `NameError: name 're' is not defined`.
Le générateur n'ajoutait pas `import re` aux imports du fichier produit. Invisible
en relisant le générateur — le code qui manque ne saute pas aux yeux — et
immédiat au premier `uvicorn`. La méthode du projet, une fois de plus.

### Éprouvé par

`tests/test_identifiant_de_compte.py` (26 tests). Contre un vrai serveur : les
quatre formes acceptées, les six refusées, **les deux écritures d'une même
adresse et d'un même numéro qui doivent être UN seul compte**, la reconnexion
quelle que soit la façon de taper, le 401 (et non 422) à la connexion, la forme
canonique dans le `sub` du jeton, `manage.py` qui normalise comme le serveur — et
un compte antérieur qui continue de fonctionner. Ce dernier test contenait le
piège habituel : sans compte préalable, son `INSERT ... SELECT` ne copiait rien
et il passait en prouvant l'inverse de ce qu'il annonçait (un 401 pour compte
inexistant). Il compte désormais les lignes copiées avant de conclure.

### Le vérificateur qui n'obéissait pas à sa propre règle

Trouvé en appliquant la brique à `projets/SneakerLab`, pas en la testant. Le
smoke test inscrit un compte pour éprouver le parcours ; il le faisait sous
`'smoke'`, codé en dur. Sur une app déclarant `identifier: email`, il recevait
donc **422 sur sa propre inscription**, puis 401 partout ensuite — trois erreurs
qui ne venaient ni du backend ni du frontend, mais de monl lui-même, et qui
accusaient une application parfaitement saine.

`_identifiant_smoke` dérive désormais l'identifiant du CONTRAT, comme tout le
reste du smoke test. Un rang distingue les comptes d'un même passage : la boucle
d'élévation de privilège en essaie un par rôle provisionné, et deux inscriptions
sous le même identifiant donneraient un 409 qu'on lirait à tort comme un refus
de rôle. Le domaine `.test` est réservé par la RFC 2606 — jamais routable, donc
jamais un vrai destinataire par accident.

La leçon dépasse le cas : **un vérificateur est un client comme un autre.**
Toute brique qui contraint une entrée doit se demander si le smoke test, qui
appelle ces mêmes routes, respecte la contrainte — sinon il déclare cassé ce
qu'il devrait valider.

### « 06 12 34 56 78 » et « +33612345678 » sont la même ligne

Trouvé en éprouvant la brique de bout en bout sur la vraie boutique, après que
les tests soient passés au vert : ils n'essayaient que des variantes
INTERNATIONALES du même numéro. Les deux notations donnaient donc deux comptes,
et la promesse centrale de la brique — « deux écritures = un compte » — était
fausse dans le cas le plus courant.

monl ne peut pas le deviner : l'indicatif dépend du pays, et rien dans une spec
ne le dit. Il le fait donc **déclarer** :

```
capability auth
    identifier: email, phone
    phone_prefix: "+33"
```

Déclaré, un numéro national est mis sous forme internationale (`0` initial
remplacé par l'indicatif) ; absent, les deux notations restent deux comptes — et
un test le vérifie, pour que ce soit un choix visible et non un oubli. La forme
STOCKÉE est l'internationale : c'est celle qui ne dépend pas du pays, donc la
seule qu'on puisse relire ailleurs. Un indicatif sans `phone` dans `identifier`
est refusé : il ne s'appliquerait à rien.

C'est la même logique qu'au point 86, où `min` ARME la vérification de stock :
**ce que le compilateur ne peut pas savoir, il le fait déclarer plutôt que de le
supposer.**

## 96. Un statut n'est pas du texte, et la fiche qu'on pouvait effacer

Le parcours de SneakerLab a été rejoué en entier contre celui d'une boutique
classique — commander, payer, expédier, annuler — et confronté à ce qu'un
marchand attend. Deux trous en sont sortis, dont un que le point 90 croyait
fermé.

### La fiche qu'on pouvait effacer

`DELETE /customer` répondait **200** alors que la cliente avait une commande. En
base : **1 commande, 0 fiche.** C'est exactement l'état que le point 90 a été
écrit pour empêcher — une commande que l'administrateur ne peut attribuer à
personne, donc inexpédiable. `requiresOwn` gardait la CRÉATION et rien d'autre :
**le trou se rouvrait par l'autre bout.**

`_profile_dependents` est le pendant exact de `_profile_lookup`, à l'autre bout
du cycle de vie. Deux décisions :

**Seule la DERNIÈRE fiche est protégée.** `requiresOwn` exige « au moins une » ;
supprimer l'avant-dernière reste donc légitime, et refuser serait plus strict que
la règle qu'on applique. Le décompte porte sur les fiches de CE compte — avec un
seul compte dans le banc, « existe-t-il une fiche quelque part ? » passerait, et
c'est le piège habituel de ce projet.

**409 et non 403**, comme au point 90 : un état à corriger, pas un droit qui
manque. Le message nomme ce qui dépend de la fiche.

Le témoin compte autant que le refus : sans commande, la fiche reste supprimable.
Un garde qui refuserait toute suppression passerait le premier test sans rien
garantir, et rendrait le compte impossible à fermer.

### Un statut n'est pas du texte

Sur une commande NON réglée, le client posait `status: "livrée"` et le serveur
l'acceptait — il se déclarait livré tout seul. Le défaut était NOMMÉ comme « la
prochaine brique évidente » aux points 91 et 92 ; il aura fallu comparer la
boutique à une vraie pour le traiter.

```
rule Order.status oneOf "panier", "à régler", "en préparation", "expédiée", "livrée", "annulée"
```

**`Literal` plutôt qu'un motif.** Le refus tombe à la validation Pydantic — un
422 AVANT tout INSERT, même place que les bornes du point 85 — et la liste sort
telle quelle dans le schéma OpenAPI, donc dans `/docs`, sans qu'on ait à la
recopier. Le message d'erreur ÉNUMÈRE les valeurs permises : un 422 qui ne dit
pas ce qu'il attend oblige à lire la documentation.

**Types TEXTE seulement.** Pour un nombre, `min`/`max` (point 85) et
`categorized` (brique 5) disent déjà cela ; une troisième façon d'exprimer la
même contrainte finirait par en contredire une autre. Refusés aussi : une seule
valeur (le champ n'aurait pas à être saisi), une valeur vide (indistinguable
d'un champ non rempli à l'écran), un doublon, et le cumul avec `generated` (le
serveur écrit le champ, la liste ne serait jamais lue).

**L'ORDRE de déclaration est conservé** : sur un statut c'est celui du cycle de
vie, et c'est celui qu'un menu déroulant doit présenter.

Le contrat porte `allowed_values`, et le brief dit **MENU DÉROULANT** en toutes
lettres : sans cela l'IA dessine un champ texte, et l'utilisateur invente une
valeur qui récolte un 422 alors que la liste tenait dans un menu.

### Le delta, sixième fois

Poser `oneOf` ne renomme rien — et la liste peut changer sans que le champ bouge
(« remboursée » ajoutée au carnet). Le digest porte donc les VALEURS et pas leur
seule présence : comparer les noms serait l'erreur du point 89, pour la troisième
fois.

### Le vérificateur, deuxième occurrence

Le point 95 avait établi qu'« un vérificateur est un client comme un autre ». La
règle s'est appliquée immédiatement : le smoke test construit ses corps de
requête depuis `request_fields`, avec `smoke-<champ>` pour toute chaîne — refusé
par un `Literal`. Il lit désormais `allowed_values` et prend la première valeur
déclarée (sur un statut, l'état initial). **Toute brique qui contraint une entrée
contraint aussi le smoke test**, et il n'a aucun moyen de le savoir s'il code ses
valeurs en dur.

### Ce que la comparaison a montré et que ce point NE traite PAS

* **Pas de taille.** Une boutique de sneakers où l'on commande sans pointure.
  Le modèle juste n'est pas évident — une taille sur la ligne de commande se
  déclare en deux lignes avec `oneOf`, mais un vrai marchand tient son stock PAR
  TAILLE, ce qui demande une entité `Variant` (`Product hasMany Variant`, le
  stock et le décompte portés par elle). Les deux ne coûtent pas la même chose et
  ne disent pas la même chose : c'est une décision produit, pas un défaut du
  compilateur.
* **Pas de référence de commande lisible** (« SL-2026-0001 ») : seul l'`id`
  technique existe. Une brique « numéro lisible » supposerait une séquence
  formatée, que rien ne porte aujourd'hui.
* **Pas de numéro de suivi transporteur** : un champ à ajouter, une décision à
  prendre sur qui l'écrit.
* Et toujours hors de portée, assumé : frais de port, TVA, courriels.

### Éprouvé par

`tests/test_valeur_parmi_une_liste.py` (24 tests) : les refus de compilation,
le test qui exige une sortie DIFFÉRENTE avec et sans la règle (point 85), le
contrat et le brief, le témoin sans règle, le delta, et contre un vrai serveur
les quatre valeurs acceptées, les quatre refusées, le message qui énumère, la
contrainte au PUT — le branchement qu'on oublie — et le refus qui ne laisse rien
en base. Plus quatre tests dans `tests/test_fiche_obligatoire.py`, dont le banc a
gagné `Delete Client` : sans cette action la brique n'avait aucune façon d'être
prise en défaut, comme il avait fallu ajouter `Update Ligne` au point 91 et
`Delete Ligne` au point 92.

## 97. Le message qui devinait à la place de l'agent

Une retouche réelle : « retire À propos de la page principale. Pour livraison et
retours améliore l'affichage, je veux pas un paragraphe. » monl a répondu :

```
❌ claude-code n'a modifié AUCUN fichier de frontend/ — la retouche n'a pas été faite.
   Reformuler la demande en nommant l'écran et l'élément…
```

**La demande les nommait.** Le conseil était donc faux, et il envoyait
l'utilisateur reformuler une phrase déjà claire.

L'agent, lui, avait une raison — et une bonne : ces deux rubriques viennent du
bloc `landing` de la SPEC, et `FRONTEND_PROMPT.md` exige qu'elles soient lisibles
au fil de l'accueil. Les retirer ou les restructurer depuis `frontend/` aurait été
exactement ce que la consigne de retouche lui interdit : *« si le défaut vient de
ce que la spec dit, le signaler plutôt que le contourner par une astuce
d'affichage »*. Il a obéi. **monl a jeté sa réponse avec la sortie du
processus**, puis a inventé une explication à la place.

Le correctif tient en une variable : `run_cli_agent` RENDAIT déjà la sortie de
l'agent, personne ne la lisait. Elle s'affiche désormais quand rien n'a bougé,
suivie du geste qui convient — la spec puis `monl update`, pas une retouche. Le
conseil de reformulation reste, mais seulement quand l'agent n'a rien dit : un
agent muet ne laisse aucune piste, et le supprimer aurait laissé l'utilisateur
sans rien.

**La leçon, plus large que le cas.** Un outil qui orchestre une IA reçoit deux
choses : un résultat, et un compte rendu. Ne garder que le premier revient à
supposer que l'échec est toujours de la même nature — ici « la demande est trop
vague » — alors que la brique avait justement été écrite pour qu'un autre cas
existe. **Une hypothèse affichée comme un diagnostic est pire qu'un message
vague** : elle envoie corriger ce qui n'est pas cassé.

### Ce que la demande est devenue

Les deux moitiés se réglaient dans la spec, et aucune n'avait besoin d'une
brique nouvelle :

* « À propos » retirée du bloc `landing` — sur monl il n'y a qu'une page, donc
  retirer la rubrique la retire du site ;
* « Livraison et retours » découpée avec le séparateur `¶` du point 64, que la
  grammaire acceptait depuis toujours et que personne n'avait employé ici : même
  texte, mot pour mot, mais quatre paragraphes au lieu d'un dans le contrat.

Puis — et seulement là — une retouche a fait le reste : 25 lignes de CSS, aucun
mot ni balise touchés, les quatre blocs numérotés et filetés comme la FAQ juste
en dessous. **Le partage est celui que le point 94 décrivait : la structure vient
de la spec, la forme vient de la retouche.** Demander la forme avant d'avoir la
structure, c'est demander à l'IA de deviner — et c'est ce que le premier appel a
refusé de faire.

### Éprouvé par

Deux tests dans `tests/test_smoke_and_frontend_ai.py` : un agent factice qui
décline en expliquant (sa raison doit s'afficher, et l'ancienne hypothèse
disparaître), et le témoin d'un agent muet (le conseil de reformulation doit
rester — sinon on retire la seule piste quand il n'y en a pas d'autre).

## 98. Annuler rend les paires, et la transition qu'on ne joue qu'une fois

Le dernier bug vivant qu'avait laissé la comparaison à une boutique classique
(point 96) : annuler une commande la passait en « annulée » et **gardait ses
lignes**, donc le stock restait consommé pour de bon. Supprimer les lignes le
rendait depuis le point 92 — mais efface la commande du carnet. **Un marchand
veut les deux** : la trace et les paires.

```
rule Order.status "annulée" releases OrderLine
```

`oneOf` (point 96) était le préalable, et pas seulement par commodité : c'est
lui qui rend le refus possible. Sans liste de valeurs déclarée, la valeur
déclencheuse serait une chaîne libre, et une faute de frappe donnerait une règle
qui **ne se déclenche jamais** — exactement ce que le point 85 refuse. La règle
exige donc `oneOf` sur le champ, et que la valeur y figure.

### Ne rendre QU'UNE FOIS

L'état est lu AVANT l'écriture, et la libération n'a lieu qu'à la **transition**.
Sans cette garde, deux `PUT` successifs à « annulée » rendraient le stock deux
fois et la boutique s'inventerait des paires. C'est le genre de défaut qu'aucune
relecture ne donne : il faut appeler la route deux fois de suite.

### L'état libéré est TERMINAL

Le trou que la première version laissait ouvert, trouvé en l'éprouvant : annuler
rendait le stock, puis **réactiver** laissait la commande vivante sans rien avoir
consommé. Du stock gratuit — même famille que les exploits du point 77.

Reprendre le stock au retour supposerait qu'il soit encore disponible, ce que
rien ne garantit : une autre commande a pu passer entre-temps. Le refus est donc
la seule réponse honnête, et le message dit quoi faire à la place (en créer une
nouvelle). Le contrat le porte (`releases_on.terminal`) et le brief l'écrit :
**ne pas proposer de réactiver.**

Le refus vit AVANT la transaction d'écriture : le `except sqlite3.IntegrityError`
qui enveloppe les écritures ne fermerait pas la connexion pour lui.

Aucun plancher sur la restitution, comme au point 92 — on rend un état qui a
existé et qui était valide.

### Ce qui n'a PAS eu besoin d'être écrit

Le cumul avec le verrou du point 91 : une commande RÉGLÉE refuse déjà tout
`Update`, donc son statut ne peut pas passer à « annulée » et la question du
remboursement ne se pose pas ici. Un refus de cumul aurait été inatteignable, et
un refus inatteignable fait croire à une protection.

### Le delta, septième fois

`releases` ne crée aucune route et ne change aucun champ — mais un bouton
« réactiver » devient un 409, et un écran doit expliquer que l'annulation rend
les paires. Septième ensemble à entrer dans `_contract_signature`, et la question
a été posée avant d'écrire le code, comme le point 94 le demandait.

### Éprouvé par

`tests/test_liberation.py` (16 tests) : les sept refus de compilation, le test
qui exige une sortie différente avec et sans la règle, le contrat, le delta — et
contre un vrai serveur : annuler rend le stock, **annuler GARDE les lignes**
(toute la raison d'être de la brique), trois annulations de suite ne rendent
qu'une fois, la réactivation est refusée sans rien consommer, un autre statut ne
libère rien (le témoin), et annuler une commande ne rend pas ce que la commande
d'à côté avait consommé.

Vérifié en réel sur `projets/SneakerLab` : Halo RS 12 → 9 à la commande, 12 à
l'annulation, 12 encore après deux ré-annulations, 409 à la réactivation, et la
commande reste au carnet en « annulée ».

## 99. Le rattachement fantôme, et la sécurité qui n'était qu'un accident

Ce point ne vient pas d'un besoin nouveau. Il vient d'une **sonde** : pour juger
une proposition extérieure qui présentait le « stock par taille » comme une
grosse brique à écrire (parseur, validateur, générateur SQL, routes), il fallait
d'abord vérifier ce que le compilateur savait déjà faire. Le modèle s'écrit
entièrement avec la syntaxe existante — `relation Produit hasMany Variante` — et
il compile. Ce n'était donc pas une brique.

Mais le `schema.sql` produit disait ceci :

```sql
CREATE TABLE IF NOT EXISTS "variante" ( ... "produit_id" INTEGER,
    FOREIGN KEY ("produit_id") REFERENCES _monl_users(id) )
```

et le `app.py` cela :

```python
INSERT INTO "variante" ("taille", "prix", "stock", "produit_id") VALUES (?,?,?,?)
    (data.taille, data.prix, data.stock, current_user_id,)
```

**La variante était rattachée au vendeur qui l'avait créée, jamais à son
produit** — et le client n'avait aucun moyen d'en désigner un : la colonne
n'existait dans aucun schéma d'entrée. Le nom disait le lien métier, le contenu
portait un identifiant de compte, et le contrat annonçait fidèlement
`references_account: true`. Rien n'échouait nulle part.

### Ce qui manquait, en une ligne

`_identity_fk_columns` (generator/core.py) répond à la question « cette colonne
se peuple-t-elle depuis le jeton ? ». Elle écartait bien trois cas — création
publique, cible de compteur, propriété transitive — mais retenait **n'importe
quelle relation entrante** pour le quatrième. Or « peuplée depuis l'identité de
l'appelant » n'a de sens que si le parent EST un compte. La condition manquante
tient en cinq mots : *le parent doit être un acteur*.

C'est le **défaut du point 80 par l'autre bout**. Là on nommait explicitement une
entité comme propriétaire et le rattachement produit était faux ; ici on n'en
nomme aucune, et il l'est tout autant. Les deux fois, une clé étrangère
recevait une valeur qui n'était pas de sa nature, en silence.

### Pourquoi personne ne l'avait vu en vingt briques

Aucun exemple du dépôt ne présente une entité fille d'une table **métier**.
`Like` et `Report` y échappent parce qu'ils sont cibles d'un compteur (« CE
post »), `Comment` parce qu'il déclare `ownedBy Member`, `OrderLine` parce qu'il
est possédé transitivement, `Order` et `Post` parce que leur parent est un
acteur. Les cinq exemples et `projets/SneakerLab` compilent tous des enfants
d'acteurs. La sonde qui a révélé le défaut tenait en trois relations, et elle a
été écrite pour évaluer une proposition, pas pour chercher un bug.

C'est le pendant exact de la leçon du point 78 — *neuf briques testées une par
une ne testent pas leurs paires* — appliquée cette fois non aux paires de
briques, mais aux **formes de spec qu'aucun exemple n'écrit**.

### L'ordre de déclaration ne décide plus

Le correctif en emporte un second, plus discret. Avec deux parents et aucune
règle `ownedBy`, l'ancien code retenait `placements[0]` : le propriétaire se
décidait à l'ordre d'écriture de la spec, et un parent métier déclaré en premier
volait la place de l'acteur. Désormais seuls les parents acteurs sont candidats,
et `ownedBy` tranche entre eux. Le correctif de la bêta 3 avait déjà cherché à
supprimer cette dépendance à l'ordre ; il ne l'avait fait qu'à moitié.

### `payable` perd une sécurité ACCIDENTELLE, donc gagne un refus

C'est la partie du point qu'il ne fallait surtout pas oublier. La route de
règlement compare la colonne de propriété à `current_user_id`. Cette spec
compilait, et la comparaison était juste :

```
relation Produit hasMany Facture
rule Facture.total payable
```

Juste **par accident** : la colonne recevait `current_user_id` faute de savoir
faire autrement, c'est-à-dire à cause du défaut que ce point corrige. Le
rattachement redevenu honnête, `produit_id` porte l'id d'une ligne de catalogue,
et la comparaison devient fausse dans les deux sens — le propriétaire ne peut
plus payer, et un inconnu le peut dès que les deux identifiants coïncident.

Le refus doit donc être écrit, sans quoi la correction ouvrirait un trou plus
large que celui qu'elle ferme (même raisonnement qu'à la brique 11, point 81).
Deux formes sont acceptées, et deux seulement : un parent **acteur** (la colonne
porte un id de compte) ou une **chaîne transitive** (point 87, la jointure rend
ce même id). La cible d'un compteur est exclue même quand c'est un acteur :
cette colonne-là est choisie par le client, elle ne dit pas à qui la ligne
appartient.

Le refus vit dans un recoupement APRÈS la boucle des décomptes — il lui faut
`reputation_rules` complet, même placement et même raison que le recoupement
`payable`/`derivedFrom` du point 79. Et la route de règlement **échoue
désormais à la génération** si aucune colonne de compte n'est disponible :
écrire une route de paiement sans contrôle d'accès vaut moins qu'un compilateur
qui s'arrête, même raisonnement que `_derived_source_fk`.

### L'angle mort du delta, sixième fois — mais la question posée d'avance

Une clé étrangère ne vit pas dans `entities.<E>.fields` : elle vit dans
`foreign_keys`. `_contract_signature` ne la regardait donc pas, et `monl update`
aurait répondu « aucun changement d'interface » pendant qu'un formulaire de
création gagnait un champ obligatoire. La signature compte un **huitième
ensemble**, qui porte les deux façons dont un rattachement change sans changer
de nom :

- **ce qu'il contient** — un id de compte ou l'id d'une ligne métier ; c'est la
  raison d'être du point 88, une jointure faite sur la mauvaise des deux marche
  À MOITIÉ ;
- **qui le renseigne** — le serveur depuis le jeton, ou le client. Passer du
  premier au second ajoute un menu déroulant au formulaire ; sans lui, la
  création répond 422.

La consigne écrite pour l'IA frontend dit les deux séparément : une jointure à
refaire et un champ à ajouter ne se corrigent pas au même endroit.

Corrigé au passage dans le même rapport : le verrou de paiement était **imprimé
deux fois** (deux boucles identiques sur `added_verrous`).

### Ce que ça ne répare pas

Les enregistrements déjà en base gardent la valeur fautive : la migration
additive rattrape une colonne, jamais son contenu (point 89, et pour la même
raison — inventer une correspondance serait une base qui MENT). Et
`CREATE TABLE IF NOT EXISTS` laisse à une base existante son ancienne contrainte
`REFERENCES`. Un projet qui aurait compilé une entité dans ce cas doit être
repris à la main ; aucun projet du dépôt n'est concerné.

### Un voisin repéré, laissé ouvert

`requiresOwn` (point 90) devient un **no-op silencieux** quand l'entité exigée
n'a aucune colonne de compte — `_profile_lookup` rend `None` et la règle ne
produit rien. Ce n'est pas né ici (c'était déjà le cas sous propriété transitive
ou création publique), mais le point 85 est formel : une règle qui ne produit
rien doit être refusée. Le refus n'est pas écrit, faute de pouvoir l'exprimer
dans le validateur sans y recopier `_identity_fk_columns` — deux vérités
finiraient par diverger. À traiter avec la question plus large de savoir où doit
vivre cette distinction.

### Éprouvé par

`tests/test_rattachement.py` (18 tests). **11 d'entre eux échouent sans la
correction** — dont, contre un vrai serveur, `assert 4 == 2` : l'identifiant du
compte écrit là où celui du produit devait être. Le banc inscrit trois figurants
avant le vendeur pour que son identifiant ne coïncide avec celui d'aucun
produit : c'est la leçon de la sonde du point 81, et sans elle le rattachement
fautif passerait le test.

Le reste : le schéma SQL et le schéma d'entrée, l'indépendance à l'ordre des
relations, le contrat et le huitième ensemble du delta, les trois refus autour
de `payable` (dont le témoin transitif, qui doit continuer de passer), et la
chaîne complète du « stock par taille » — deux tailles du même produit ont des
stocks indépendants, le plancher tient par variante, et un produit inexistant
ne crée pas de variante orpheline.

Les **non-régressions** comptent autant : une entité fille d'un acteur continue
de se peupler depuis le jeton et sa colonne reste hors du corps de requête ; la
cible d'un compteur reste désignée par le client. Une correction qui rendrait
toutes les clés étrangères clientes ouvrirait un trou bien plus large.

Vérifié enfin par comparaison octet à octet : les cinq exemples et
`projets/SneakerLab` produisent des artefacts **identiques** avant et après. La
correction ne change que le cas qui était cassé.

## 100. Une vitrine qui montre des enfants, et la désignation qui se lit

Le point 99 a rendu honnête la clé étrangère d'une entité fille d'une table
métier. Il restait qu'une telle entité **ne pouvait pas figurer dans les données
de démonstration** : un bloc `seed` n'accepte que des champs DÉCLARÉS, et une
colonne de rattachement n'en est pas un.

```
REFUSÉ : le bloc 'seed Variante' référence le champ 'produit_id',
         qui n'est pas déclaré sur 'Variante'.
```

Conséquence concrète : une boutique à variantes s'ouvrait sur un catalogue dont
**rien n'était commandable**. Le compilateur savait produire la forme, le serveur
savait la servir, et la vitrine restait vide — la couverture de compilation sans
le comportement, exactement ce que le point 95 dénonce.

C'est le même angle mort que le point 99, par une troisième porte. Aucun exemple
n'écrivait d'enfant de table métier ; aucun `seed` n'avait donc jamais eu à en
déclarer un.

```
seed Variant for Product.name "Chaise Ligne"
    finish: "Chêne naturel", price: 249.90, stock: 12
    finish: "Noyer fumé", price: 289.00, stock: 5
```

### Désigner par une valeur, jamais par un rang

Le rang (« la 3ᵉ ligne du bloc `seed Product` ») était la forme la plus simple à
implémenter, et c'est la mauvaise. Un numéro ne se lit pas — dans une spec où
plus de la moitié du texte sert à expliquer, `for Product 3` n'apprend rien — et
il se décale silencieusement dès qu'on insère une ligne au milieu du bloc
parent. La désignation nomme donc un CHAMP et une VALEUR.

Ce n'est pas une invention : `monl assets add --for "Halo RS"` (point 84) tranche
déjà pareil, avec la même phrase dans son code — *la fiche est désignée par une
de ses VALEURS, et non par un numéro : c'est ce que l'humain a sous les yeux*.
Deux outils, une seule façon de montrer du doigt.

Le champ est nommé explicitement (`Product.name`) plutôt que deviné. monl a un
mécanisme d'attribution de rôles qui saurait proposer un « titre » — s'en servir
ici aurait fait dépendre le rattachement d'une heuristique d'affichage.

### Les sept refus, et celui qui porte la brique

Le premier est **l'ambiguïté** : deux lignes parentes portant la valeur désignée
font échouer la compilation, en disant combien. Deviner donnerait une vitrine
différente d'une compilation à l'autre, et personne ne le verrait avant de
regarder l'écran. Symétriquement, une valeur que **personne ne porte** est
refusée : c'est la coquille type, et sans ce refus elle amputerait la vitrine
d'une rubrique entière sans un mot.

Le troisième mérite d'être connu : **un parent ACTEUR est refusé**. Cette
colonne-là porte un identifiant de COMPTE (point 99) ; or un jeu de
démonstration s'insère au démarrage, quand aucun compte n'existe encore. Il n'y a
personne à désigner. La brique hérite ainsi, sans une ligne de plus, de la
distinction que le point 99 venait d'établir.

Le quatrième porte sur le TYPE du champ de désignation : texte seulement.
Rapprocher deux flottants est déjà douteux ; surtout, un prix ou un stock ne
NOMME rien.

Le cinquième est **l'ordre** : un parent semé après son enfant est refusé. Les
données sont insérées table par table, dans l'ordre de déclaration des blocs ;
un parent qui arrive après ne serait pas en base au moment de rattacher.
Réordonner en silence aurait été possible — et c'est précisément ce qu'il ne
faut pas faire : la spec dirait une chose et le serveur en ferait une autre.

Les deux derniers sont mécaniques : l'entité parente doit exister, et une
relation doit les lier (sans elle, aucune colonne ne porte le rattachement).

### Le rattachement se résout au DÉMARRAGE

C'est la décision qu'un test départage, pas un raisonnement. Résoudre à la
compilation aurait voulu dire écrire un `id` en dur dans `_SEED_DATA`, en
supposant que le parent vient d'être semé et porte donc l'`id` de son rang. Or le
socle ne sème une table que **si elle est vide** : sur une base où les produits
existent déjà, le parent n'est pas réinséré et son `id` réel n'a aucun rapport
avec un rang.

La désignation voyage donc telle quelle jusqu'au serveur, et se résout par un
`SELECT id FROM "product" WHERE "name" = ?` au démarrage.
`test_le_rattachement_suit_lid_reel_pas_le_rang` peuple la table parente avec les
identifiants 17 et 41 avant le premier démarrage : les variantes s'y rattachent.
Un rang aurait écrit 1 et 3, et la vitrine aurait montré des variantes
orphelines.

Quand la résolution échoue — seul chemin possible, une base dont la table
parente est déjà peuplée AUTREMENT — la ligne est écartée et le serveur **le
dit**. Une vitrine amputée sans un mot enverrait chercher la panne dans le
frontend.

### Ce que la brique a contraint ailleurs, et qu'on a failli oublier

`src/monl/assets_tool.py` lit les blocs `seed` **textuellement**, par une
expression régulière ancrée en fin de ligne (`^seed\s+(\w+)\s*(#.*)?$`). La
nouvelle forme d'en-tête ne correspondait plus : l'outil sautait le bloc en
silence alors que l'AST le contenait, et la correspondance fichier ↔ AST — sur
laquelle repose toute l'écriture de photos — ne tenait plus.

C'est la leçon des points 95 et 96 (*le vérificateur est un client comme un
autre*) élargie : **toute brique qui change la FORME d'une ligne de spec
contraint aussi les outils qui la lisent textuellement**, pas seulement ceux qui
l'exécutent. Il n'y en a qu'un aujourd'hui, et il est nommé dans `CLAUDE.md`
comme le seul endroit du dépôt qui écrive dans la spec de l'humain — raison de
plus pour ne pas l'oublier la prochaine fois.

Question posée d'avance, comme le veut la règle des points 88 à 99 : est-ce que
`_contract_signature` doit voir cette brique ? **Non**, et c'est la première fois
que la réponse est un vrai non. Un jeu de démonstration ne change ni les routes,
ni les champs, ni les accès : il remplit une base. Le contrat décrit ce que le
serveur EXPOSE, pas ce qu'il contient.

### L'exemple qui ferme le trou de corpus

`exemples/02_boutique.ml` gagne son entité `Variant` : le produit est ce qu'on
MONTRE, la variante ce qu'on VEND. `price` et `stock` quittent `Product`,
`derivedFrom` lit `Variant.price`, le décompte vise `Variant.stock`, et neuf
variantes sont semées sur six produits — dont une épuisée et une en stock faible,
pour que la vitrine montre les deux cas dès l'ouverture.

Le corpus cesse ainsi d'être aveugle à la forme qui a produit les points 99 et
100. C'est le vrai enjeu : ces deux défauts n'ont pas été trouvés par une revue,
mais par une spec de trois relations que personne n'avait jamais écrite.

### Éprouvé par

`tests/test_seed_parent.py` (15 tests) : les sept refus, la forme du socle
généré, la non-régression d'une spec qui n'emploie pas la brique — et contre un
vrai serveur, le rattachement correct de trois variantes sur deux produits,
l'idempotence au redémarrage, la résolution par `id` réel contre rang, et le
parent introuvable qui est NOMMÉ.

Vérifié en réel sur `exemples/02_boutique.ml` : les 9 variantes s'attachent à
leurs 6 produits au démarrage ; commander 2 « Noyer fumé » fait passer son stock
de 5 à 3 pendant que le « Chêne naturel » du même produit reste à 12 ; le total
de la commande vaut 578,00 € (2 × 289,00, dérivé puis sommé) ; et en commander 99
répond 409 sans rien avoir consommé.

Découvert au passage, sans rapport avec la brique : `Order.reference` est de type
`UUID`, et `UUID` ne génère RIEN — c'est un champ texte que le client remplit
librement. Une commande sans référence répond 422, et deux commandes peuvent
porter la même. C'est la motivation d'une brique `reference` à venir, et la
question à trancher d'abord : que devient le type `UUID` le jour où elle existe ?

## 101. Le type frère, resté debout dix points de plus

Trouvé en préparant la brique `reference`, et en vérifiant d'abord ce que le
compilateur promettait déjà. `exemples/02_boutique.ml` déclare :

```
entity Order
    reference: UUID
```

Le serveur acceptait `CMD-1`, `smoke-reference`, et la chaîne vide. Le type
`UUID` ne produisait qu'une chose : `VARCHAR` avec une longueur de 255. Deux
commandes pouvaient donc porter la même « référence », sous un nom qui promet un
identifiant universellement unique.

### Ce n'était pas un arbitrage à ouvrir

Le point 91 a déjà tranché cette question exacte, pour le type d'à côté :

> le type `Email` ne fixait qu'une LONGUEUR — `pas-un-courriel` entrait en base
> avec un 200. Un type qui nomme une adresse et n'en vérifie aucune est
> exactement ce que le point 85 refuse : une règle qui ne produit rien.

`UUID` est le même péché, laissé debout dix points de plus. La correction
applique la décision existante au type frère, avec le même motif dans le schéma
Pydantic — donc un 422 avant tout INSERT, et la forme visible dans `/docs`.

**La forme canonique, et rien de plus** : ni chiffre de version, ni variante.
Les exiger rejetterait l'UUID nul et les versions à venir, alors qu'ils sont
parfaitement bien formés. monl vérifie la FORME ; juger la provenance d'un
identifiant n'est pas de son ressort — même frontière qu'au point 95, où il
vérifie qu'une adresse est bien écrite sans prétendre qu'une boîte la reçoit.

**La contre-épreuve compte autant que le refus.** Un motif trop strict ferait
passer tous les tests de rejet en cassant les vrais identifiants ; le banc
vérifie donc aussi que l'UUID nul et la casse majuscule restent acceptés. C'est
la structure du point 91, reprise telle quelle.

### Le vérificateur est un client comme un autre — TROISIÈME fois

`_sample_value` envoyait `smoke-reference` pour un champ `UUID`. Le smoke test
aurait donc déclaré cassée une boutique saine, après `'smoke'` refusé par
`identifier: email` (point 95) et `'smoke-status'` refusé par `oneOf`
(point 96). Cette fois la question a été posée AVANT d'écrire le motif, pas
après un faux diagnostic — c'est la seule différence, et c'est celle qui compte.

La valeur est FIXE et non tirée au sort : un vérificateur doit rendre deux fois
le même verdict sur la même application.

### Ce que ça ne répare pas

Aucune donnée existante n'est convertie : une base qui contient déjà des
références mal formées continue de les rendre. La règle ne vaut que pour les
écritures à venir — comme au point 95, et pour la même raison. Contrairement au
point 95, en revanche, le serveur ne les COMPTE pas au démarrage : le constat de
démarrage existe pour les comptes, dont la forme conditionne la connexion ; une
référence mal formée n'empêche rien.

### Éprouvé par

`tests/test_type_uuid.py` (15 tests) : sept formes refusées, trois acceptées
(dont l'UUID nul et les majuscules), le témoin d'un champ `String` voisin qui ne
gagne aucun motif, le test qui exige une sortie DIFFÉRENTE de celle d'un
`String`, et deux tests sur le vérificateur — sa valeur d'échantillon, puis le
smoke test lancé pour de vrai sur une spec à `UUID`.

Ce point laisse entière la vraie question de `Order.reference` : un numéro de
commande lisible n'est pas un UUID, et le client n'a rien à faire à l'écrire.
C'est la brique suivante.

## 102. Le numéro que l'humain lit et dicte

Le point 101 a rendu le type `UUID` honnête, et ce faisant a rendu visible le
vrai problème. `exemples/02_boutique.ml` déclarait :

```
entity Order
    reference: UUID
```

Un champ que le CLIENT remplissait, et qui exige désormais la forme canonique
d'un UUID. Or personne ne dicte `3f2504e0-4f89-41d3-9a0c-0305e82c3301` au
téléphone, et personne ne l'écrit sur un bon de livraison. Un carnet de
commandes veut « CMD-2026-0001 » — et ce numéro-là n'est pas une donnée du
client : c'est le marchand qui l'attribue.

```
rule Order.reference numbered "CMD-{YYYY}-{NNNN}"
```

Même famille que `timestamp` (point 89) : peuplé par le serveur à la création,
absent des corps de requête à la création COMME à la modification. Un numéro de
commande qui change n'est plus une référence — le client l'a noté, le vendeur
aussi.

### Le mot-clé n'est pas `reference`

`rule Order.reference reference "…"` ne se lit pas, et le champ s'appelle
« reference » dans à peu près tous les cas d'usage. `numbered` rejoint la famille
des participes du DSL — `hidden`, `generated`, `categorized`, `payable`.

### Le compteur vit dans une table SYSTÈME

C'est la décision de fond, et elle se justifie par ce qu'elle interdit.
`MAX(reference) + 1` sur la table métier aurait été plus simple et faux deux
fois : il **redonne le numéro d'un enregistrement supprimé** — deux factures
portant la même référence, à des mois d'intervalle — et il se trompe dès que
deux créations se croisent.

`_monl_sequences (entite, champ, periode, dernier)` a pour clé primaire le
triplet, et c'est la PÉRIODE qui fait repartir la séquence : à chaque année, ou
mois, ou jour, selon les jalons du gabarit. Rien n'est jamais effacé, et une
période vide (`''`) désigne une séquence globale — le cas d'un gabarit sans
date.

L'attribution vit **dans la transaction de création**. Hors d'elle, une
insertion refusée — stock insuffisant, parent introuvable, verrou de paiement —
laisserait le compteur avancé et le numéro suivant sauterait sans raison.

L'index unique est créé **sans qu'on ait à déclarer `unique`**. Un numéro en
double n'est pas un numéro ; faire dépendre cette garantie d'une ligne de spec
qu'on peut oublier d'écrire serait rouvrir la porte du point 85. Le nom d'index
étant dérivé de la table et de la colonne, déclarer les deux ne produit qu'un
seul index.

### Six refus, et celui qui porte la brique

Un gabarit **sans séquence** (`"CMD-{YYYY}"`) est refusé : tous les
enregistrements porteraient le même numéro, ce qui n'en est pas un. C'est le
point 85 appliqué au gabarit lui-même — et sans ce refus, l'index unique
transformerait la faute en 409 à la deuxième commande, en production.

Un **mois sans année** (`"CMD-{MM}-{NNNN}"`) est refusé aussi, et c'est le plus
subtil : la séquence repart chaque mois, donc `CMD-03-0001` revient tous les mois
de mars. L'index unique l'attraperait — un an plus tard.

Les quatre autres sont mécaniques : deux séquences (rien ne dit laquelle
s'incrémente), un jalon inconnu, une accolade orpheline, un champ qui n'est pas
`String`. Ce dernier **nomme explicitement `UUID`** dans son message : c'est le
type qu'on est tenté de choisir pour une référence, et depuis le point 101 un
numéro lisible n'y entrerait jamais. Un refus qui ne dit pas pourquoi envoie
essayer autre chose au hasard.

`min`/`max` sur un champ numéroté sont refusés **sans une ligne de plus** : la
brique rejoint le recoupement groupé du point 89, exactement ce que ce
regroupement avait été fait pour gagner.

### Les enregistrements antérieurs restent SANS numéro

Point 89, mot pour mot. La migration additive rattrape une colonne, jamais son
contenu. Numéroter au démarrage les commandes déjà en base prétendrait un ordre
d'arrivée que le serveur n'a pas observé — et sur un carnet de commandes, un
numéro inventé finit sur une facture. Le serveur les COMPTE, les nomme, et le
contrat dit à l'IA d'afficher un tiret.

La séquence, elle, repart de 1. Une base de quarante commandes anciennes verra
donc sa quarante-et-unième porter `CMD-2026-0001` : c'est honnête, et toute autre
règle demanderait de deviner ce que les quarante premières auraient porté.

### Ce que le contrat doit dire

`numbered_as` porte le gabarit, et la note dit trois choses : ne pas l'envoyer,
l'AFFICHER partout où l'enregistrement est identifié (de préférence avant l'`id`
technique, et copiable), et afficher un tiret sur les anciens. Sans la deuxième,
une IA d'interface range le numéro parmi les champs techniques et l'humain
continue de dicter un `id`.

`_contract_signature` le voit sans une ligne de plus : le champ devient
`server_generated`, donc l'ensemble « lecture seule » du point 89 le rapporte.
La question a été posée avant d'écrire le code, et pour une fois la réponse
existante suffisait.

### Éprouvé par

`tests/test_numerotation.py` (24 tests) : les douze refus de compilation, la
disparition du champ des deux schémas, l'index unique, le test qui exige une
sortie différente sans la règle, le contrat — et contre un vrai serveur : les
numéros qui se suivent, le client qui ne peut ni les choisir ni les modifier,
huit créations simultanées qui donnent huit numéros distincts, une période
antérieure qui ne décale pas la séquence, et la base déjà peuplée dont les
anciennes lignes restent vides.

Le test qui porte la conception est
`test_le_numero_ne_recule_pas_apres_une_suppression` : c'est lui, et pas celui
sur la concurrence, qui départage la table système d'un `MAX(...) + 1`. SQLite
sérialise les écritures, et cette sérialisation masquerait la différence sous
une charge de huit requêtes — le test de concurrence prouve l'absence de
collision et de « database is locked », pas l'atomicité. Le dire plutôt que de
laisser croire.

Vérifié en réel sur `exemples/02_boutique.ml`, qui abandonne son `UUID` : trois
commandes créées sans qu'aucun corps ne porte de référence sortent
`CMD-2026-0001`, `-0002`, `-0003`, et le smoke test passe sans un avertissement.

## 103. Voir le delta avant d'écrire

`monl update` écrit PUIS rapporte. Tant que le rapport dit ce qu'on attendait,
l'ordre est sans conséquence. Le jour où il annonce un écran entier à réécrire
— et six points ont montré que ça arrive (88 à 91, 94, 99) — on aimerait
l'avoir su avant d'avoir recompilé et remplacé le contrat de référence.

```bash
monl diff        # même rapport, aucun fichier touché
```

### Une source, pas deux

La tentation était d'écrire un second calcul de delta, plus simple, « juste pour
regarder ». C'est exactement ce que ce dépôt refuse : le calcul du delta est
celui dont **six points** ont montré qu'il est difficile à tenir juste, et deux
implémentations divergeraient au premier ajout. `_rapporter_delta` est donc
extrait de `cmd_update` et partagé, avec `_situer_projet` et
`_signature_precedente`. Le test qui l'atteste compare les deux sorties ligne à
ligne.

### Le piège du dossier jetable

Un dry-run compile dans un dossier temporaire. Mais `compile_project` validait
les assets déclarés **dans son dossier de sortie** — donc un projet
parfaitement valide aurait échoué en annonçant un logo manquant qui, lui, est
bien là. C'est le seul endroit où le geste a demandé de rouvrir du code
existant : `compile_project` accepte désormais `base_dir` (où sont les fichiers
de l'humain) séparément du dossier de sortie, et `save_state` pour ne pas
déposer d'état pendant un essai. Les deux gardent le comportement historique
par défaut.

Cette asymétrie existait déjà, discrètement : `compile_monl` résout les assets
depuis le dossier de la SPEC, `compile_project` depuis le dossier de sortie. Sur
un projet ordinaire les deux coïncident, ce qui est la raison pour laquelle
personne ne l'avait vue.

### Ce qui n'est pas écrit

Ni `app.py`, ni `schema.sql`, ni le contrat, ni `monl.json`, ni
`FRONTEND_UPDATE_PROMPT.md`. Le test ne vérifie pas une LISTE de fichiers — il
compare l'empreinte de l'ARBRE entier avant et après. Une liste laisse passer le
fichier auquel on n'a pas pensé ; c'est le raisonnement des garde-fous
d'empreinte du point 73, appliqué en sens inverse.

Le contrat déjà posé mérite une mention à part : il est la RÉFÉRENCE de la
comparaison. L'écraser pendant un dry-run rendrait le geste suivant aveugle.

### Détail d'ergonomie

La compilation d'essai est silencieuse — son bandeau et son audit n'apprennent
rien à qui demande un diff. Mais si elle échoue, c'est SON message qui
s'affiche : le nôtre ne dirait que « ça n'a pas marché ». Et `diff` ne renvoie
vers `monl update` que lorsqu'il y a quelque chose à appliquer — envoyer
appliquer un changement qui n'existe pas apprend à ne plus lire les messages
(même arbitrage qu'aux points 57 et 92).

### Éprouvé par

`tests/test_diff.py` (10 tests) : l'empreinte de l'arbre inchangée, le contrat
de référence intact, la consigne d'évolution non écrite (et écrite par `update`,
sur la même spec), l'égalité ligne à ligne des deux rapports, le silence quand
la spec n'a pas bougé, l'arrêt sans `monl.json`, le message du compilateur
laissé passer, et le projet à assets qui compile sans se plaindre d'un fichier
qui existe.

## 104. Les icônes qu'on croyait interdites

Constat du mainteneur, en regardant les sites produits : **aucun n'emploie
d'icône**. Aucune, jamais, quel que soit le projet.

La tentation était de conclure à un défaut de l'IA d'interface, ou à un manque
de direction visuelle. C'est le brief qu'il fallait lire — même réflexe qu'au
point 94, où une FAQ collée venait de la SPEC et non du frontend.

Le brief dit :

> Frontend AUTONOME : aucune librairie CDN, aucun script externe

et ne dit **nulle part** ce qui reste possible. Une IA qui lit cette ligne
conclut correctement que Font Awesome, Material Icons et Lucide sont hors
d'atteinte — et, faute de savoir que le SVG en ligne fonctionne, elle joue la
sécurité et n'en met aucune. Le `.svg` est pourtant en liste blanche depuis
toujours (`ALLOWED_EXTENSIONS`, frontend_ai.py) : le moyen existait, il n'était
simplement écrit nulle part.

### Pourquoi ce n'est pas une entorse au point 72

Le point 72 a retiré du contrat toute prescription visuelle — palette,
typographie, rayon — au motif qu'« une suggestion écrite dans le document qui
fait foi n'est pas neutre ». Il a en même temps gardé deux choses, et l'a écrit :
le contraste WCAG et l'autonomie du frontend, parce que « ni l'un ni l'autre
n'est une question de goût ».

Un MOYEN tombe du même côté que ces deux-là. Le brief ne dit pas s'il faut des
icônes, ni lesquelles, ni dans quel style — il dit par quel moyen elles sont
possibles, précisément parce que la règle d'autonomie, lue seule, laisse croire
qu'elles ne le sont pas. Corriger une lecture erronée n'est pas orienter le
goût.

La frontière est mince, et elle est donc gardée par un TEST : le brief ne doit
recommander aucune icône ni aucun style d'icône. Sans ce garde-fou, la ligne
ajoutée ici dériverait vers de la prescription à la première réécriture.

### DEUX briefs, et la moitié qui manquait

Trouvé en LANÇANT une retouche, pas en relisant le code : la ligne ci-dessus
n'était posée que sur le brief de CONSTRUCTION. La consigne de `monl retouche`
est un document séparé, et elle disait « même autonomie (aucun CDN) » sans un
mot de plus. La retouche qui a servi de banc a réussi — mais parce que l'auteur
avait demandé des icônes explicitement. Une demande du type « rends cette
section plus lisible » se serait heurtée au même mur.

C'est la leçon du point 93 sur un autre objet. Il n'y a qu'UNE voie vers l'IA
(`_lancer_ia`), et c'est ce qui garde les garde-fous identiques — mais il y a
DEUX briefs, et ce qu'on écrit dans l'un ne se propage pas à l'autre. Toute
règle ajoutée au brief de construction doit donc se demander si la retouche en
a besoin.

### Éprouvé par

Trois tests dans `tests/test_design_contract.py` — le fichier qui prouve que le
compilateur se TAIT sur le visuel, et qui est donc le bon endroit pour poser la
limite de ce silence : l'un exige que le moyen soit énoncé dans le brief de
construction, le deuxième qu'aucune recommandation ne le soit, le troisième que
la consigne de retouche porte le même rappel.

Vérifié en réel sur `projets/SneakerLab` : une retouche demandant « des icônes
et un peu de texte » sur la rubrique livraison/retours a produit quatre SVG en
ligne — zéro auparavant — avec `aria-hidden` et un texte court par carte.

Ce point ne fait rien reconstruire : les sites existants n'ont pas d'icônes et
n'en auront pas tant qu'ils ne sont pas régénérés. Il change ce que la
PROCHAINE construction saura.

## 105. Deux messages qui envoyaient corriger ce qui n'était pas cassé

Constat du mainteneur, en lançant une retouche sur un vrai projet :

```
monl retouche /projets/SneakerLab "utilise plutôt des icônes …" --provider claude-code
❌ monl.json introuvable — ce dossier n'est pas un projet monl.
```

Une seule ligne de réponse, et deux fautes distinctes dedans — dont aucune n'est
celle que le message désigne.

### Le dossier n'existait pas du tout

`_load_state` rend `None` aussi bien pour « dossier absent » que pour « dossier
sans monl.json », et les quatre appels concluaient à la seconde. `monl frontend`
allait plus loin encore : « lancer 'monl' ou 'monl compile' » — il envoyait
recompiler un projet que monl n'avait jamais trouvé.

C'est le reproche du point 97, sur un autre message : **une hypothèse affichée
comme un diagnostic est pire qu'un message vague.** Là-bas, monl conseillait de
reformuler une demande qui était déjà claire ; ici, il conseille de compiler un
dossier qui n'existe pas.

Les deux questions se posent dans un ordre, et il faut le respecter : le dossier
existe-t-il, PUIS porte-t-il un projet. Répondre à la seconde quand la première
a échoué, c'est répondre à côté.

`_erreur_de_chemin` (cli.py) est cette première question, partagée par les
quatre points d'entrée. Elle explique aussi la faute qui a motivé le point :
**une barre oblique de tête**. `/projets/SneakerLab` n'est pas « projets/SneakerLab
ici » — c'est `SneakerLab` dans un dossier `projets` à la RACINE DU SYSTÈME.
Quand le voisin relatif existe, monl le propose ; quand il n'existe pas non
plus, il ne propose rien, parce qu'un chemin inventé enverrait chercher une
deuxième fois pour rien.

### Et les deux arguments étaient inversés

`retouche` est le SEUL geste dont le premier argument n'est pas le dossier :
`run`, `update`, `diff`, `compile` et `frontend` le prennent tous en tête.
Écrire le dossier d'abord est donc le réflexe — et monl répondait « ce dossier
n'est pas un projet monl » en parlant de la PHRASE qu'on venait de lui donner.

Trois façons de traiter ça, et le choix n'est pas neutre :

- **inverser l'ordre des arguments** : casse `monl retouche "texte"`, la forme
  la plus courante, puisque le dossier vaut « . » par défaut ;
- **accepter les deux ordres en devinant** : magique, et faux le jour où une
  demande ressemble à un chemin ;
- **NOMMER l'inversion**, et laisser l'auteur la corriger. C'est ce qui est
  fait.

Le diagnostic ne s'appuie pas sur une intuition mais sur deux faits opposés :
la demande ne contient aucune espace et ressemble à un chemin, tandis que le
« dossier » contient des espaces. Un faux positif ne coûterait qu'un message —
il ne change aucun comportement — mais il refuserait une retouche bien écrite,
d'où le test qui l'interdit explicitement.

**La commande proposée doit MARCHER telle quelle.** Recopier le chemin dont on
vient de dire qu'il est faux ferait buter une deuxième fois, sur un autre
message : la suggestion corrige donc aussi la barre oblique quand elle le peut.

### Éprouvé par

`tests/test_chemins_et_arguments.py` (13 tests) : le dossier absent nommé comme
tel et sans un mot sur monl.json ni la compilation, la barre oblique expliquée,
la suggestion qui ne s'invente pas de voisin, les gestes qui s'arrêtent sur le
chemin plutôt que sur l'état, la vérification de cohérence qui ne conseille plus
de recompiler — puis l'inversion détectée, l'ordre correct qui ne déclenche
rien (le témoin qui compte le plus : un faux positif refuserait une retouche
valide), et la commande proposée dont le chemin est déjà corrigé.

---

## 106. Rôle superviseur au-dessus d'`accessibleBy` (brique 23)

**Le problème :** la brique 8 (`accessibleBy`, point 31) enferme chaque action
dans ses colonnes-parties : seuls l'expéditeur et le destinataire d'un message
privé le lisent/suppriment. Une messagerie a presque toujours besoin d'un tiers
superviseur — un modérateur qui doit pouvoir lire, voire retirer, TOUS les
messages, sans être artificiellement compté parmi les parties de chacun. Les
colonnes ne disent pas « qui peut tout voir » ; il faut le déclarer.

**La syntaxe retenue :** on réutilise `sharedBy` sur la MÊME référence qu'une
action déjà régie par `accessibleBy` :
```
rule PrivateMessage.Read   accessibleBy member_id, recipient_id
rule PrivateMessage.Delete accessibleBy member_id, recipient_id
rule PrivateMessage.Read   sharedBy Moderator
rule PrivateMessage.Delete sharedBy Moderator
```
Le rôle ainsi nommé devient **superviseur** de cette action : il liste, lit,
modifie et supprime TOUS les enregistrements, sans restriction de parties. Les
parties, elles, restent confinées à leurs colonnes. Un rôle non répertorié dans
le `sharedBy` d'une action `accessibleBy` — même s'il a un workflow qui l'y fait
entrer — subit, lui, le filtre de parties. C'est le pendant exact du superviseur
personne déjà acquis pour `ownedBy` au point 88 (`rule X.Update sharedBy
Proprietaire, Patron` : chacun ne touche que les siens, l'autre voit tout).

Un seul froncement de sourcil possible : pourquoi `sharedBy` plutôt qu'une
nouvelle syntaxe ? Parce que le mot dit déjà, dans monl, « ce rôle partage
l'accès à cette action au-delà du propriétaire » — relire le point 88. Une
syntaxe neuve ajouterait une règle à apprendre pour un cas que `sharedBy`
recouvre sémantiquement. La différence de comportement (transpercer les
colonnes) n'est pas une syntaxe mais une conséquence de la présence conjointe
d'`accessibleBy`.

**Ce qui change dans le validateur (`ast_validator.py`) :**
- chaque action `accessibleBy` collecte désormais les rôles porte-parole d'un
  `sharedBy` de même référence → `access_supervisors`;
- chaque rôle ainsi nommé doit être un acteur déclaré (pas de fantôme);
- **exemption de CRITICAL_COLLISION pour les actions `accessibleBy`**, miroir
  exact de celle déjà reconnue aux actions `ownedBy`. Le point 1 (deux acteurs
  sur une même écriture) est une collision de PRIVILÈGES ; `accessibleBy`,
  comme `ownedBy`, décide l'accès à CHAQUE enregistrement par ses données, pas
  par les rôles — un rôle Membre et un rôle Modérateur peuvent donc
  légitimement partager la même route. Sans cette exemption, ajouter un
  superviseur forcerait à nommer les parties dans le `sharedBy` pour couvrir
  la collision, ce qui les déclarerait (à tort) superviseurs à leur tour.

**Ce qui change dans le générateur (`routes.py`) :** sur une action
`accessibleBy` qui a des superviseurs, le contrôle par colonnes devient
conditionnel :
- **liste (Read)** : `WHERE col1 = ? OR col2 = ?` n'est posé que si le rôle
  appelant n'est pas superviseur — le superviseur voit tout (WHERE vide);
- **détail / Update / Delete** : le 403 de parties est gardé derrière
  `if current_actor not in {"Moderateur"}`.
Le mécanisme conditionnel réutilise exactement celui déjà en place pour
`ownedBy` (`_own_where`), donc il n'ajoute pas une troisième voie mais étend la
deuxième.

**Dans le contrat frontend :** chaque route de lecture/suppression gagne, quand
il y a un superviseur, un champ `supervisors` et une note `SUPERVISION` — sans
quoi une IA d'interface appliquerait le filtre de parties au modérateur lui-même
et lui dessinerait une vue LITÉRALEMENT VIDE.

**Preuve, testée en conditions réelles** (`tests/test_access_parties.py`, volet
superviseur, serveur éphémère + Sessions) : le modérateur provisionné hors
ligne (insérer dans `_monl_users` avec le hachage pbkdf2 de `manage.py`) voit la
liste complète, lit un message dont il n'est ni émetteur ni destinataire, et le
supprime — quand Carol, tier du même rôle `User`, reste à 0 en liste et reçoit
403 en direct. Compilé par `exemples/03_reseau_social.ml`. Validations
supplémentaires : superviseur inconnu refusé, absence de collision, `sharedBy`
sans `accessibleBy` qui ne fabrique aucun superviseur.

**La formulation en garde-fou :** un `sharedBy` posé sur une action qui n'est
PAS régie par `accessibleBy` ne produit AUCUN superviseur — il reste le partage
de privilèges historique, inchangé au point 1. Les deux lectures de `sharedBy`
ne se font pas concurrence : elles sont disjointes par la présence ou non
d'`accessibleBy` sur la même référence.

---

## 107. La chaîne de propriété qui remonte toute la profondeur (brique 24)

Le point 87 laissait un « ce qui reste ouvert » explicite : la propriété
transitive (brique 11) ne remontait qu'**UN** intermédiaire. `Ligne → Commande
→ Client` marchait ; `Ligne → Bloc → Commande → Client` était REFUSÉ à la
compilation (« plus d'un niveau »), et le refus se réclamait du point 80 — deux
indirections « compileraient en filtrant sur le mauvais maillon ». La décision
était assumée, avec son coût nommé : des jointures à profondeur variable dans
quatre chemins d'accès.

Cette brique lève le refus. La marche de la chaîne remonte désormais maillon par
maillon jusqu'à un ACTEUR, quelle que soit la profondeur, et la classe de défaut
du point 80 ne reparaît PAS : un **cycle**, un **cul-de-sac** (aucun compte au
bout) et un **maillon possédé par plusieurs entités** (chemin ambigu) restent
trois refus à la compilation. Le validateur (`ast_validator.py`) remplace la
résolution à un cran par une boucle `while maillon not in self.actors`, et
`transitive_ownership[entity]` porte maintenant `{"chain": [...], "actor": ...}`
au lieu de `{"via": ..., "actor": ...}` — la liste, du bas vers le haut.

### Une seule source par chemin, comme au point 81

Cinq chemins doivent filtrer sur le compte : création (403 si le parent n'est
pas à l'appelant), liste (`WHERE ... IN`), détail (404), Update et Delete
(jointure rendant l'id de compte). Chacun a désormais son constructeur dans
`generator/core.py`, tous bâtis sur `_transitive_chain` (la source unique) :
`_chain_owner_scalar` (sous-requête scalaire imbriquée par maillon),
`_chain_read_where` (le `IN` imbriqué de la liste), `_chain_owner_from_row` (le
propriétaire d'une ligne depuis son id) et `_chain_join` (la séquence de `JOIN`
des routes de règlement). Ne pas réécrire une remontée ailleurs — c'est le même
principe que `_owner_lookup_sql` au point 81, généralisé à N maillons.

### Ce qu'une relecture n'aurait pas montré — et n'a pas montré

La première version de la brique **compilait, et plantait**. Deux défauts, de la
même famille, invisibles à la lecture et fatals à l'exécution :

- La vérification du parent à la **création** collait la valeur que le client
  désigne DANS le texte SQL (`... WHERE id = (data.bloc_id)`), au lieu de la
  passer en paramètre lié. SQLite y lisait un nom de colonne : `no such column:
  data.commande_id`. Toute création d'entité transitive répondait **500** — pas
  seulement la profondeur 2 neuve, mais la **brique 11 elle-même**, qui marchait.
- La lecture **détail** écrivait `(_via,)` dans le tuple de paramètres du code
  généré, où `_via` n'était le nom d'aucune variable de la route (l'expression
  `named_row.get(...)` avait été mise dans une variable de génération, puis
  recopiée telle quelle) : `NameError`, 500 à chaque détail.

Les routes Update et Delete, elles, liaient correctement (`', (id,))`) — la
preuve que le défaut n'était pas conceptuel mais un oubli de liaison, deux fois.
Les deux n'ont été trouvés qu'en **générant un vrai serveur et en frappant les
routes** : 14 tests déjà verts (`test_propriete_transitive.py`,
`test_paiement_transitif.py`) tombaient en *Internal Server Error*. Correctif :
lier le paramètre partout, comme Update/Delete le faisait déjà. C'est,
une fois de plus, la leçon de méthode du projet — **compiler n'est pas se
comporter correctement**, et une brique de sécurité qui n'a pas été exécutée
n'est pas une brique.

### Le piège du banc, transposé à la profondeur 2

`tests/test_transitive_profondeur.py` éprouve la résolution (2 et 3 maillons),
les trois refus, et la profondeur 2 contre un vrai serveur (création, détail,
liste, Update, Delete, refus croisés entre deux clients). Le témoin du point 80
a dû être étendu : faire diverger non seulement les id de commande mais aussi
ceux de **bloc**, sans quoi le premier bloc (id 1) coïncide avec le premier
compte (id 1) et « le maillon stocké est-il bien le bloc, pas le compte ? » passe
par accident. Même précaution qu'au point 81, un cran plus bas.

---

## 108. L'émission SQL typée, la frontière de sécurité

Le point 107 s'est corrigé en deux lignes : lier `data.<fk>` en paramètre au
lieu de le coller dans le texte SQL. Mais le correctif ne fermait que
*l'occurrence* ; la **possibilité** restait. `_chain_owner_scalar` acceptait un
« fragment de premier maillon » sous forme de chaîne — rien n'empêchait un
appelant de lui repasser une valeur comme texte, exactement ce qu'avait fait la
brique 24. Une classe de défaut qui se corrige par vigilance reviendra. Cette
décision la rend **structurellement impossible.**

### La couche : `generator/sql.py`

Un fragment `Sql` porte son TEXTE (du SQL fixe où chaque valeur est un `?`) et
ses PARAMÈTRES (les expressions Python source à lier, dans l'ordre des `?`).
Trois portes d'entrée, et trois seulement :

- **`bind(expr)`** — LA SEULE façon de faire entrer une valeur : elle sort en
  `?`, l'expression est retenue à part. Il n'existe aucune fonction qui place
  une valeur dans le texte.
- **`ident(nom)`** — un identifiant entre guillemets, qui REFUSE un guillemet
  interne plutôt que de l'échapper en silence (une entité ou colonne validée
  n'en porte jamais ; deviner masquerait une divergence amont).
- **`kw(texte)`** — du SQL fixe, qui refuse un `?` : un placeholder ne s'écrit
  qu'avec `bind`, sinon une valeur pourrait se glisser dans un fragment réputé
  « fixe ».

On compose avec `cat`. À l'émission (`execute_args`, `params_tuple`), un
garde-fou vérifie que le nombre de `?` égale le nombre de paramètres — un
builder mal écrit échoue à la génération plutôt que de produire un `execute`
qui planterait. **Texte et paramètres sortent ENSEMBLE d'un seul objet** :
l'appelant ne peut plus les désolidariser, ce qui était la faille du point 107.

### Ce qui a bougé, et ce qui n'a pas bougé

Les builders du contrôle d'accès (`_chain_owner_scalar`, `_chain_read_where`,
`_chain_owner_from_row`, `_chain_join`, `_owner_lookup_sql` dans
`generator/core.py`) et leurs cinq sites d'appel dans `generator/routes.py`
(création, liste, détail, Update, Delete) passent tous par cette couche. **Le
SQL généré est resté identique à l'octet** — vérifié en régénérant : mêmes `?`,
mêmes jointures. Les 706 tests restent donc l'oracle, inchangés, et la preuve
que le refactor n'a rien déplacé du comportement. `sql.py` vit DANS le package
`generator` (un seul nœud d'architecture, point 65) : aucune frontière déplacée.

### La portée, honnête

C'est la **première pierre** de « séparer le code de sécurité », pas la
séparation entière. Ce qui est acquis : toute construction de SQL de contrôle
d'accès passe désormais par une frontière typée où une valeur ne peut pas fuir
dans le texte. Ce qui reste : consolider les refus du validateur et l'audit de
sécurité dans un noyau explicite. Et c'est le **préalable à tout portage Rust** :
cette couche définit noir sur blanc le contrat d'émission qu'un cœur Rust devrait
reproduire — la frontière se conçoit une fois, dans le langage qu'on maîtrise,
avant de la traduire.

Éprouvée par `tests/test_sql_emission.py` : l'invariant de la couche (une valeur
ne traverse jamais le texte, un identifiant à guillemet refusé, l'équilibre
`?`/params), ET un garde-fou de régression qui compile une chaîne à deux maillons
et **interdit sur le code réellement généré** le motif du point 107 — une valeur
client collée dans une comparaison SQL.

**L'enforcement à l'échelle du projet** vit dans `tests/test_invariants_securite.py` :
il compile CHAQUE spec du dépôt (les cinq exemples + une spec profondeur 2), parse
l'`app.py` généré en AST, et exige qu'aucun littéral de chaîne qui est du SQL ne
contienne une expression client ou d'exécution (`data.`, `named_row`,
`current_user_id`) — ces valeurs doivent toujours être liées, jamais dans le
texte. La méthode est en AST et non en sous-chaîne : un `x = data.y` Python n'est
pas un littéral, donc jamais un faux positif ; seul un `'... = data.y ...'` DANS
une requête est fautif, ce qui est exactement la forme du point 107. Avec le
garde-fou du garde-fou (l'invariant DOIT voir passer du contrôle d'accès qui lie
ses valeurs), le défaut du point 107 devient inexpédiable sur toute spec, pas
seulement sur celle qui l'avait révélé.

---

## 109. Le contrôle d'accès, sorti de l'ombre du validateur

Le point 108 a séparé le versant ÉMISSION de la sécurité (le SQL généré). Restait
le versant DÉCISION : les refus qui déterminent qui peut toucher quoi. Ils
vivaient noyés au milieu de `_validate_structures`, une méthode de ~1480 lignes
qui valide aussi les contraintes de champ, les gabarits de numéro, les seeds, les
assets… La leçon du point 107 est directe : **le défaut de la brique 24 vivait
dans exactement ce genre de logique de sécurité anonyme, perdue dans un
fourre-tout.** Ce qu'on ne voit pas, on ne le relit pas.

Le modèle de contrôle d'accès forme pourtant un bloc cohérent — propriété directe
(`ownedBy`), résolution de la chaîne transitive jusqu'à un acteur (briques 11 et
24), accès à plusieurs parties (`accessibleBy`), rôle superviseur (brique 23). Ces
225 lignes sont désormais une méthode nommée, `_valider_controle_dacces()`,
appelée par `_validate_structures`. Une frontière de lecture, pas seulement de
code : quand on cherche « comment monl décide-t-il l'accès ? », il y a un endroit.

### Ce qui a rendu l'extraction sûre

Le bloc n'utilise que `self.*`. Les deux variables locales de
`_validate_structures` qui pouvaient l'accrocher — la matrice de collision
multi-acteurs (`access_matrix`) et `shared_permissions` — sont posées en tête de
la méthode et consommées tout en bas, pour un AUTRE contrôle (les collisions
d'autorisation) ; le cluster d'accès ne les touche pas. Vérifié avant de couper,
puis prouvé après : **déplacement d'octets exact, zéro ligne réécrite, les 717
tests inchangés comme oracle.** Sur du code de sécurité, un refactor se prouve
par la suite qui ne bouge pas, pas par relecture.

### La portée, honnête (suite du point 108)

C'est la deuxième pierre de « séparer le code de sécurité », pas la dernière. Ce
qui est acquis : le *modèle d'accès* (qui possède, qui partage, qui supervise) est
un bloc nommé, comme l'émission SQL l'est déjà. Ce qui reste dans
`_validate_structures` : `public`, `restrictedTo`, et les refus de sécurité
adossés à d'autres briques (`requiresOwn`, l'exigence de propriétaire de
`payable`) — chacun petit et collé à sa brique, moins urgent à isoler. Et
`_validate_structures` reste un fourre-tout de 1250 lignes : le décomposer par
préoccupation est un chantier distinct, à mener quand il coûtera vraiment.
Ensemble, 108 et 109 délimitent le noyau sécurité (émission + décision d'accès) —
c'est ce périmètre-là qu'un éventuel portage Rust aurait à reproduire.

---

## 110. Rust évalué par un spike mesuré, et écarté

Question posée : introduire un langage (Rust ?) pour de meilleures performances,
sécurité et stabilité, sur le cœur compilateur. Décision de méthode : ne pas
trancher sur une intuition, mais **mesurer**. Un spike a été écrit — un parser
Monl en Rust, isolé, hors dépendances, testé en différentiel contre le parser
Lark existant. Puis retiré du dépôt : sa valeur était la mesure, pas le code.

### Ce que le spike a montré

- **Faisabilité : oui.** Le parser Rust reproduisait l'AST de Lark **à
  l'identique** sur 6/6 specs (les cinq exemples réduits au sous-ensemble
  couvert + un corpus exerçant toutes les formes de règles). Un portage est
  possible, et le test différentiel est le bon garde-fou.
- **Sécurité : hors sujet pour Rust.** La sécurité de monl est celle de l'app
  GÉNÉRÉE (contrôle d'accès, pas d'injection), pas la sécurité mémoire du
  compilateur — Python est déjà memory-safe, et le défaut du point 107 était une
  faute de logique, pas de mémoire. Le vrai gain (un modèle typé) est déjà pris
  côté Python aux points 108 et 109.
- **Performance : un piège.** Au premier jet, Rust semblait 56× plus rapide
  (0,9 ms contre 50 ms/parse). En creusant : `parse_monl_string` **reconstruisait
  le parseur Lark à chaque appel** — la compilation de grammaire (~50 ms)
  dominait tout. Parseur mis en cache (correctif d'une ligne), Python parse en
  **0,4 ms** — plus vite que le binaire Rust (0,9 ms, spawn de process inclus).
  Le « gain Rust » était une inefficacité Python corrigeable gratuitement.
- **Erreurs : gain marginal.** Rust disait « ligne 3 : type attendu après
  'title:' » là où Lark dit « élément inattendu » — un peu mieux, pas de quoi
  justifier un second langage.

### Le verdict, et ce qu'il a rapporté

Aucun endroit ne passe le critère « utile », coût compris (second toolchain,
build, CI, frontière sous-process, deux parsers à maintenir en phase). **Rust
n'est pas adopté.** Le spike a exactement rempli son office : éviter d'engager un
langage sur une hypothèse, en la réfutant par la mesure.

Le vrai gain a été trouvé en chemin, en Python : **mettre le parseur Lark en
cache** (`_get_parser`, parser.py) — de ~50 ms à 0,4 ms par parse. Sur une
compilation isolée c'est invisible ; sur la suite de tests, qui compile des
centaines de specs, elle est passée de ~344 s à ~200 s. Un one-liner valait, ici
et maintenant, plus qu'une réécriture.

**Règle à retenir** : « quel langage pour aller plus vite / plus sûr » se répond
en mesurant sur le code réel, pas sur les propriétés d'un langage. La bonne
première question n'était pas « Rust ou Go ? » mais « où le temps part-il
vraiment ? » — et la réponse était une ligne de Python.

---

## 111. `public`, `requiresOwn` et `payable` sortent du fourre-tout

Suite directe des points 108-109 : ce qu'ils laissaient explicitement ouvert
comme « reste dans `_validate_structures` ». Deux blocs de sécurité,
commentés mais encore anonymes dans la méthode fourre-tout, en sortent :

- **`_valider_regle_public()`** — la règle `public` (une action qui n'exige
  plus d'authentification).
- **`_valider_requires_own_et_payable()`** — `requiresOwn` (brique 17) et
  `payable` (brique paiement), extraits ENSEMBLE parce que contigus dans le
  fichier d'origine. `payable` lit `self.masked_fields`, peuplé par la
  validation `hidden` qui reste dans `_validate_structures` et s'exécute
  avant cet appel : contrairement au point 109 (un seul bloc contigu), ici il
  fallait vérifier qu'aucun ordre d'exécution ne bougeait, pas seulement que
  le bloc ne dépendait que de `self.*`. Les appels remplacent les blocs
  exactement à leur position d'origine — aucune réorganisation.

**Preuve** : déplacement d'octets exact (vérifié par relecture du diff : les
lignes supprimées d'un endroit sont les lignes ajoutées ailleurs, à
l'indentation près, aucun texte réécrit), 728 tests contre 724 avant ce point
— les 4 nouveaux sont ceux du point 112, aucune régression sur les 724
existants.

**Méthode de travail, une première** : ce chantier est le premier mené avec
la nouvelle répartition orchestrateur/exécuteur — Claude conçoit le
découpage exact (quels blocs, quelles méthodes, quelle contrainte d'ordre à
préserver, quels messages d'erreur ne pas toucher) et vérifie après coup ;
Codex CLI exécute le déplacement mécanique. La vérification est restée
intégralement indépendante de ce que Codex a rapporté : relecture du diff
complet, `ruff check` et suite de tests relancés dans mon propre
environnement, pas seulement lus dans son rapport.

---

## 112. `restrictedTo`, jamais validé structurellement

Trouvé en auditant ce qui restait de logique de sécurité anonyme dans
`_validate_structures` pour le point 111 : `restrictedTo` (point 2 — marque
un champ sensible pour l'audit `[SECURITY_AUDIT]` des blocs `custom`) n'avait
AUCUNE validation structurelle. Il est seulement lu par
`_audit_security_rules` pour construire un dictionnaire utilisé dans un
rapport — rien ne vérifiait que l'entité existe, que le champ est déclaré
dessus, ni que l'acteur nommé est un acteur déclaré.

Le point 2 est explicite : `restrictedTo` est volontairement un
avertissement, pas un refus de compilation — inchangé ici. Mais une faute de
frappe sur le champ ou l'acteur ne déclenche alors ni l'avertissement ni
aucun signal : `_audit_security_rules` ne trouve simplement jamais de
correspondance. Une protection qu'on croit posée et qui ne l'est pas, en
silence — exactement le défaut que `ownedBy`/`requiresOwn`/`public` refusent
déjà à la compilation, plus jamais accepté ailleurs dans le validateur depuis
le point 90.

`_valider_regle_restrictedTo()` referme cet écart : entité, champ et acteur
doivent exister, sinon `ASTValidationError`. Quatre tests l'éprouvent dans
`tests/test_validateur_refus.py` — entité absente et champ absent via le
tableau `CIBLES_INEXISTANTES` existant, acteur non déclaré et le témoin bien
formé en tests dédiés (l'acteur fautif ne peut pas passer par le socle
commun, qui n'a qu'un seul acteur).

### La portée, honnête

Ce n'est pas un chantier de sécurité découvert par accident : c'est le genre
de trou qu'un audit systématique de « qu'est-ce qui manque encore dans le
fourre-tout ? » trouve, précisément parce que 108-111 ont réduit ce
fourre-tout à presque rien. Avec 111 et 112, `_validate_structures` ne porte
plus aucune règle de contrôle d'accès ou de visibilité anonyme — tout ce qui
décide qui peut voir, toucher ou payer quoi vit dans une méthode nommée.

---

## 113. Le verrou de paiement bloquait aussi le superviseur, et personne ne le savait

Parti de « numéro de suivi transporteur » (noté ouvert depuis les points 91
et 96 : « un champ à ajouter, une décision à prendre sur qui l'écrit »). La
décision à prendre s'est avérée plus large que le champ : **vérifié contre un
vrai serveur**, un acteur superviseur (`sharedBy` sur `Update`, distinct du
propriétaire) reçoit le même 409 que le propriétaire une fois l'entité
réglée. `_payment_lock_lines` (point 91) n'a jamais été conditionné par
l'acteur — ce n'est pas un oubli du point 91, c'est ce qu'il a délibérément
choisi (« le verrou ne change ni chemin, ni acteur, ni champ »), mais
personne n'avait mesuré la conséquence : **une fois une commande payée,
personne — client ou administrateur — ne peut plus jamais faire avancer son
statut vers "expédiée" ou "livrée".** La brique `oneOf` (point 96) déclare
ces valeurs ; rien ne pouvait jamais les atteindre après paiement.

### La décision, et celle qui a été écartée

Deux voies possibles. **Assouplir le verrou générique** par un marqueur
conditionnel à l'acteur — rejetée : le verrou de paiement reste la seule
protection ABSOLUE et INCONDITIONNELLE du compilateur ; y coudre une
exception, même étroite, en aurait fait une protection qui dépend d'une
lecture attentive de toutes ses exceptions pour être comprise. **Une route
dédiée**, sur le modèle exact de `payable` (qui a déjà ce précédent : deux
routes séparées plutôt qu'un trou dans le CRUD générique) — retenue.

### `rule Entite.champ writableAfterPayment Acteur`

Un champ ainsi marqué reste modifiable après paiement, mais SEULEMENT par
l'acteur nommé, via une route dédiée `PUT /entite/{id}/apres-paiement` —
jamais par la route `Update` générique, qui reste verrouillée sans exception,
strictement inchangée. Neuf refus à la compilation : référence mal formée,
entité ou champ inexistant, entité non `payable` (la règle n'aurait rien à
débloquer), acteur non déclaré, cumul avec `generated`/`derivedFrom`/
`timestamp`/`numbered` (ces règles interdisent déjà toute écriture cliente,
pour toujours), **l'acteur ne peut pas être le propriétaire** (sinon le
verrou se contournerait par la bande — c'est le refus qui compte), un seul
acteur par entité, pas de doublon de champ.

La route ne lit JAMAIS `payment_status` : c'est un canal réservé au
superviseur, pas un canal « seulement après paiement » — il fonctionne aussi
avant, redondant avec `Update` mais sans y nuire. Le corps est un schéma
Pydantic dédié où chaque champ marqué est optionnel (seuls les champs fournis
s'écrivent, les autres restent inchangés), et respecte les contraintes déjà
posées sur le champ — un `oneOf` reste un `Literal`, un refus 422 sur une
valeur hors liste, exactement comme ailleurs. L'écriture SQL passe par
`sql.*` (point 108), comme tout le reste du contrôle d'accès.

### Ce que Codex a trouvé que la spec n'avait pas anticipé

`self.transitive_ownership` (point 107/109) ne couvre QUE la propriété
transitive : `_valider_controle_dacces` fait `continue` sans y écrire une
entrée quand le propriétaire déclaré est déjà un acteur (propriété directe).
La détection « l'acteur ne peut pas être le propriétaire » a donc un repli
sur `self.ownership_rules` pour ce cas — trouvé et corrigé par Codex en
écrivant le validateur, pas par moi en le concevant. Repéré en relisant le
diff, confirmé correct : le repli ne s'applique que si un seul propriétaire
direct est déclaré, ce qui couvre le cas réel (Order/Commande, propriétaire
unique) sans fragiliser rien d'existant.

### Éprouvé par

Neuf tests structurels dans `tests/test_validateur_refus.py` (les neuf
refus). Et surtout, contre un **vrai serveur, un vrai paiement (webhook
Stripe signé), une vraie base SQLite** — écrit avant la conception, pas
après, pour ÉTABLIR le problème plutôt que le confirmer, puis réutilisé pour
prouver le correctif :

- `PUT /commande/{id}` générique par l'Admin sur une commande réglée → 409,
  **inchangé** — le verrou générique ne bouge pas d'un bit.
- `PUT /commande/{id}/apres-paiement` par Alice (propriétaire) → **403** :
  la garantie qui compte le plus, le propriétaire ne contourne jamais son
  propre verrou.
- `PUT /commande/{id}/apres-paiement` par l'Admin → **200**, `status` et
  `trackingNumber` réellement écrits en base, vérifié par lecture SQL directe
  (pas par la réponse HTTP seule).
- Un statut hors de la liste `oneOf` sur cette route → **422**, le `Literal`
  fonctionne identiquement à la route standard.

### La portée, honnête

Deux chantiers volontairement PAS ouverts ici. `frontend_contract.py` ne
décrit pas encore cette route — un frontend généré par IA ne saurait pas
qu'elle existe. `projets/SneakerLab/spec.ml` n'adopte pas encore la règle :
son propre `CLAUDE.md` de projet est explicite — la spec s'y fait évoluer
par décision du propriétaire du projet, pas en silence depuis une session
qui travaille sur le compilateur. Les deux sont des suites naturelles, pas
des oublis.

### Méthode

Deuxième chantier mené en orchestrateur/exécuteur. Le découpage était plus
fin que pour 111-112 : conception complète (grammaire, refus, forme de la
route, ce qui ne doit PAS bouger) écrite avant délégation, parce que du code
NEUF n'a pas l'ancre d'un diff byte-exact à vérifier après coup. Codex a
exécuté, corrigé un écart réel dans ma spec (`transitive_ownership`) en le
documentant plutôt qu'en le camouflant, et a rapporté honnêtement que son
bac à sable interdit les sockets — 193 tests réseau en erreur dans SON
rapport, comptés ni passés ni skippés. La suite complète, rejouée dans mon
propre environnement (qui, lui, autorise les sockets) : 740 tests, 0 échec.
Le serveur réel, le paiement réel et la preuve par lecture SQL directe sont
restés de mon ressort — c'est la partie qu'un bac à sable sans réseau ne peut
tout simplement pas exécuter.

---

## 114. Le point 113 fermé sur les deux sites, et un trou qu'il avait laissé

En vérifiant ce qui restait à « terminer » sur les sites e-commerce du
dépôt : `exemples/02_boutique.ml` portait `payable` sans jamais avoir eu
`oneOf` sur `status` ni `releases` sur l'annulation — le MÊME défaut que
SneakerLab avant les points 96 et 98, jamais corrigé sur l'exemple parce que
personne ne l'avait rejoué contre un vrai marchand. Un audit systématique
(comparer chaque site aux briques qui existent) l'a trouvé, pas une
relecture ciblée.

### Le trou que 113 avait lui-même laissé

En adoptant la règle sur un cas réel (`trackingNumber` sur SneakerLab), un
défaut du point 113 est apparu : un champ `writableAfterPayment` restait
présent dans le schéma `Create`/`Update` standard — donc un CLIENT pouvait
encore l'écrire par les routes génériques. Inoffensif pour `status` (déjà
écrivable par ailleurs avant paiement), mais absurde pour `trackingNumber` :
le schéma de création l'aurait rendu **obligatoire**, forçant le client à
inventer un numéro de suivi pour sa propre commande avant même de payer.

Corrigé dans `_generate_schema_lines` (schemas.py) : les champs
`writableAfterPayment` rejoignent `generated`/`derivedFrom`/`sumOf`/
`timestamp`/`numbered` dans l'exclusion du schéma standard — même famille de
raison, même ligne de code. Seule la route dédiée du point 113 peut désormais
les écrire, à aucun moment ailleurs.

### Adopté

- `exemples/02_boutique.ml` : `oneOf` sur `status`, `releases` sur
  l'annulation, `writableAfterPayment ShopManager` sur `status`.
- `projets/SneakerLab/spec.ml` : `trackingNumber: String` (nouveau champ),
  `writableAfterPayment Admin` sur `status` ET `trackingNumber`.

### Éprouvé par

`tests/test_invariants_securite.py` compile déjà TOUS les `exemples/*.ml` —
`02_boutique.ml` y passe avec les nouvelles règles, aucun test à ajouter.
Suite complète : 740 tests, 0 échec, inchangée (fermer un trou de sécurité
ne devait rien casser, et rien n'a bougé). `monl update projets/SneakerLab`
: migration additive propre, colonne `trackingNumber` ajoutée sans toucher
aux données existantes (voir `docs/MIGRATIONS.md`). `monl run
projets/SneakerLab --check` : **smoke test réel** (serveur éphémère, base
neuve, frontend existant exécuté en jsdom) réussi — la preuve que le champ
ajouté ne casse pas un frontend qui ne le connaît pas encore.

### La portée, honnête

Le frontend de SneakerLab ne sait pas encore que `writableAfterPayment`
existe : `monl update` a généré `FRONTEND_UPDATE_PROMPT.md` avec le delta
(`+ champ ajouté : Order.trackingNumber`), mais l'écrire est le travail de
l'agent FRONTEND du projet (voir son propre `CLAUDE.md` : « ton rôle ici, le
frontend, rien d'autre »), pas de cette session compilateur. Délibérément
laissé pour une session dédiée au frontend de SneakerLab.

### Méthode

Troisième délégation Codex de la session, la plus large : trois fichiers
indépendants (un correctif compilateur, deux specs) en un seul brief. Codex
a tout livré sans écart. Vérification indépendante inchangée : diff relu
intégralement, `ruff check`, suite complète rejouée hors du bac à sable de
Codex, ET les deux commandes `monl` officielles du projet (`update`, `run
--check`) — jamais une édition manuelle de `projets/SneakerLab/spec.ml`
sans repasser par l'outillage qui régénère tout ce qui en dépend.

---

## 115. Brique 26 : `monl content export`/`import`, le contenu en masse

**Le trou.** `monl assets add` (points 83-84) n'attache une photo qu'à une
fiche de seed qui existe DÉJÀ — il n'a jamais eu vocation à en créer. Et le
dialogue guidé (`monl init`) ne demande aucun vrai contenu : il propose de
« pré-remplir avec des données de démonstration », donc des fiches
PLACEHOLDER (noms inventés, photos `picsum.photos`). Le vrai besoin — un
commerçant qui veut remplacer douze fiches inventées par ses douze vrais
produits et leurs vraies photos — n'avait aucun outil : soit éditer le DSL à
la main, soit poser les photos une par une sur des fiches déjà là.

### Deux commandes, sur le modèle exact du point 84

`monl content export [dossier]` écrit `content/<Entite>.csv` — une entité
par fichier, une colonne par champ déclaré (dans l'ordre de l'entité), moins
les champs que le client ne peut jamais fournir : même famille d'exclusion
que le schéma Create/Update (`generated`, `derivedFrom`, `sumOf`,
`timestamp`, `numbered`, et depuis le point 113 `writableAfterPayment`) —
réutilisée telle quelle, pas redéfinie. Un champ `Boolean` est exclu aussi :
la grammaire des seeds n'a AUCUN littéral vrai/faux
(`?seed_value: STRING_LITERAL | SIGNED_NUMBER`), donc rien à proposer.
`content/LISEZMOI.txt` accompagne chaque export : les valeurs `oneOf`
permises, les colonnes obligatoires, où déposer les photos.

`monl content import [dossier]` relit les CSV et **remplace en entier** le
bloc `seed` de chaque entité — pas de fusion ligne à ligne, décision prise
au moment de la conception pour éviter la classe de bug déjà rencontrée au
point 84 (une fiche qui n'est pas une ligne). Passe par EXACTEMENT la même
discipline que `assets add`, sans la redupliquer : `_valider`/`_revalider`/
`_charger`, `_blocs_seed`, `_litteral`, `resoudre_asset` sont importés
depuis `assets_tool.py`, pas réécrits. Une valeur manquante dans une cellule
est OMISE de la fiche plutôt que d'inventer une valeur par défaut — c'est
au vrai validateur de refuser un champ `required` absent, pas à cet outil
de deviner.

### Ce qui a exigé une décision, pas une simple transposition

**Les entités enfants de catalogue** (brique 21, point 100 —
`seed Variant for Product.name "Chaise Ligne"`) ont besoin de savoir à quel
parent chaque ligne CSV se rattache : une colonne `_parent` en tête,
détectée depuis la forme des blocs `seed` déjà présents. Si l'entité n'a
encore AUCUN seed, l'export refuse plutôt que deviner si elle a besoin d'un
parent — un exemple écrit à la main d'abord fixe la forme.

**Blocs non contigus refusés.** Si les blocs `seed` d'une entité sont
dispersés dans le fichier (un autre bloc d'une autre entité entre les deux),
l'import refuse plutôt que de choisir où écrire — même discipline que
partout ailleurs dans ce module : deviner serait pire qu'un refus nommé.

### Éprouvé

Huit tests unitaires (aller-retour stable à l'octet sans modification, une
valeur changée ne touche rien d'autre, image absente nommée avec la ligne
CSV, nombre invalide refusé avant compilation, blocs non contigus refusés,
regroupement `_parent` correct, entité sans seed signalée sans bloquer les
autres, `LISEZMOI.txt` énumère les valeurs `oneOf`). Suite complète : 748
tests, 0 échec (740 + les 8 nouveaux).

Et surtout, sur un **vrai petit projet compilé** (pas seulement en mémoire) :
`monl compile` → `monl content export` → édition RÉELLE du CSV (nouvelle
fiche, nouvelle photo posée dans `assets/`) → `monl content import` →
`monl update` → un vrai serveur démarré, `GET /product` renvoie les trois
fiches avec le bon texte (accents compris) et les bons chemins de photo. Le
service HTTP des assets (`/site/assets/…`) n'a pas pu être re-testé ici sans
détour : il dépend de l'existence d'un dossier `frontend/`
(`cli.py:cmd_run`), ce qui est un comportement PRÉEXISTANT du point 83, déjà
couvert par sa propre suite de tests — pas une propriété de cette brique.

### Méthode, et une leçon de process

Quatrième délégation Codex de la session, conception la plus détaillée des
quatre (fichier neuf, pas d'ancre de diff byte-exact possible). Aucun écart
non justifié.

**Un vrai faux-positif rencontré pendant la vérification, entièrement de
mon fait.** En testant l'outil sur un vrai projet, j'ai lancé une suite
complète en tâche de fond PUIS, en parallèle, manipulé mes propres serveurs
de test avec `pkill -9 -f uvicorn` — qui a tué les serveurs que la suite
elle-même lançait pour ses propres tests E2E, produisant deux `ERROR`
qui n'avaient rien à voir avec le code. Relancé proprement, sans rien en
parallèle : 748 passés, 0 échec. La leçon, générale : **ne jamais tuer des
processus par un motif large (`-f uvicorn`) pendant qu'une suite de tests
tourne** — un serveur qui semble « orphelin » peut appartenir à un test en
cours.

---

## 116. Briques 27 et 28 : `publicWhen` et `oncePer`, livrées sans leurs garde-fous

Deux briques étaient arrivées dans l'arbre de travail — `rule X.Read publicWhen
champ "valeur"` (publication conditionnelle) et `rule X.Create oncePer A, B`
(unicité composite) — avec leur grammaire, leur validation, leur émission SQL et
leur place dans le contrat. Elles compilaient. Ce point ne raconte pas leur
conception : il raconte ce que **sauter trois garde-fous du dépôt** avait laissé
passer, et ce qu'a coûté chaque vérification omise.

### Ce que la couverture de compilation ne pouvait pas voir

Les deux briques n'avaient que des assertions de compilation : un dictionnaire
d'IR relu, un nom d'index cherché dans le TEXTE de `app.py`. C'est exactement ce
que le point 95 déclarait clos (« aucune brique n'a plus la seule couverture de
compilation »), et la sanction est tombée au premier serveur réel.

**`publicWhen` cachait le contenu filtré À TOUT LE MONDE.** Le modérateur qui
venait de masquer un post ne pouvait plus ni le lister (`total: 0`) ni le rouvrir
(404) ; l'auteur d'un brouillon ne retrouvait jamais son brouillon. Une
modération à SENS UNIQUE : on masque, on ne révise pas, on ne revient pas en
arrière. Le modèle « Communauté » du catalogue livrait précisément cette
configuration, commentaire à l'appui (« le modérateur change le statut du
post ») et workflow `Read Post` compris.

Le correctif suit le mécanisme déjà acquis plutôt que d'en inventer un : un
`sharedBy` sur la MÊME référence nomme les rôles qui transpercent la condition —
pendant exact du superviseur d'`accessibleBy` (brique 23, point 106) et
d'`ownedBy` (point 88). `_superviseurs_declares()` devient la source UNIQUE des
deux, sans quoi la validation des rôles (celle qui empêche une faute de frappe
de désactiver la supervision, point 112) existerait en deux exemplaires.

**Deux exemptions, toutes deux déclaratives**, et rien d'implicite : le
superviseur nommé, et le PROPRIÉTAIRE par sa colonne d'identité (point 99), qui
voit ses propres enregistrements quel que soit leur état. Un rôle qui lit
l'entité sans être déclaré superviseur reste soumis à la condition — sinon
« masqué » ne voudrait plus rien dire dès qu'on est connecté.

**L'identité devient FACULTATIVE, et c'est la décision à ne pas rouvrir.** Une
route publique ne doit JAMAIS répondre 401 : `get_optional_identity` rend `{}`
sur un jeton absent, invalide ou révoqué. Elle ne peut donc que DONNER des
droits, jamais faire échouer une requête — c'est ce qui la rend sûre sur une
route ouverte à tous, et un test le vérifie avec un jeton bidon. Elle n'est
émise que si une exemption existe (`_condition_exemptions`, source unique
partagée par la route et le runtime) : une spec sans superviseur ni
propriétaire produit l'app.py d'avant ce point, à l'octet.

### `oncePer` avait volé la phrase de `unique`

Troisième cause pour le même 409, et sa phrase prenait le pas sur les autres :
un simple doublon de champ `unique`, sur une AUTRE cible et par un AUTRE compte,
s'entendait répondre « vous l'avez déjà fait pour cette cible ». C'est le défaut
que le point 85 avait nommé et fermé, rouvert par la brique suivante. Les deux
causes se distinguent désormais sur les COLONNES que SQLite nomme dans son
erreur, au lieu de deviner laquelle des deux règles a parlé.

### Le pire : un index composite qui ne refusait rien

Posé sur `exemples/03_reseau_social.ml`, `oncePer Member, Post` laissait liker
dix fois le même post. **La colonne visée par un `increments` sort de l'INSERT
quand elle est la PREMIÈRE relation entrante** (`_client_fk_columns` tranche sur
`_get_incoming_relation`, pas sur `_decrement_fk_column`) : `post_id` restait
NULL, et SQLite tient deux NULL pour distincts. L'index existait, la règle était
déclarée, et rien n'était protégé.

Bug d'ORDRE, donc invisible sur la spec qui l'a fait naître : mon banc d'essai
déclarait la relation vers l'acteur en premier et fonctionnait parfaitement.
Même famille que le point 92, à un autre endroit du même calcul.

La génération REFUSE désormais un `oncePer` dont une colonne n'est jamais écrite
à la création, et le message dit quoi réordonner. Refuser plutôt que produire une
règle sans effet : c'est mot pour mot ce que le point 85 a établi pour `unique`.
La cause profonde — deux sources pour « quelle colonne porte le compteur » —
reste ouverte et n'est pas traitée ici ; le refus empêche seulement qu'elle
produise une garantie fausse.

### L'angle mort du delta, neuvième et dixième fois

`_contract_signature` ne lisait pas `business_rules`. Poser
`rule Article.Read publicWhen status "published"` ne crée aucune route, ne
renomme aucun champ, ne change aucun acteur : `monl update` répondait « aucun
changement d'interface — le frontend existant reste valide » pendant qu'il
fallait dessiner un état brouillon, un filtre de liste et un écran de
modération. `oncePer` est le même angle mort côté écriture : le bouton « voter »
gagne un 409 que personne n'avait annoncé.

Vérifié par exécution, pas par lecture : `monl diff` sur une spec passée de
`public` à `publicWhen` imprimait bien « aucun changement ». La VALEUR entre dans
le digest, pas seulement la présence de la règle — passer de `"published"` à
`"validated"` ne renomme rien non plus (leçon des points 89 et 96).

**Ce n'est plus une série de coïncidences, c'est la question à poser AVANT
d'écrire une brique** — et elle a encore été sautée deux fois.

### Une suite qui ne pouvait pas passer sur un clone neuf

`tests/test_projets_metier.py` lisait `projets/CommunauteHub` et
`projets/GestionPro`. Or `/projets/` est ignoré par git : la suite passait sur le
poste de son auteur et échouait en CI par six `FileNotFoundError`. Un test ne
peut pas dépendre de ce que le dépôt ne transporte pas — les specs vivent
désormais dans le fichier de test, comme le fait déjà
`tests/test_access_parties.py`.

### Ce que ce point coûte, et ce qu'il rappelle

Trois questions du dépôt, sautées, trois défauts :

| Question omise | Ce qu'elle aurait attrapé |
|---|---|
| Un test contre SERVEUR ? | La modération à sens unique, l'index qui ne refuse rien |
| `_contract_signature` la voit-elle ? | Deux briques muettes pour `monl update` |
| Un EXEMPLE la compile-t-il ? | La colonne NULL — le trou de corpus des points 99 et 100 |

Aucune n'est nouvelle. Toutes trois sont écrites dans `CLAUDE.md`, chacune
payée par un point antérieur. Les briques 27 et 28 sont désormais éprouvées par
`tests/test_publication_conditionnelle.py` (10 tests, trois comptes distincts)
et `tests/test_unicite_composite.py` (8 tests, deux comptes et deux cibles —
avec un seul de chaque, une règle qui figerait tout passerait pour bonne), et
compilées par `exemples/03_reseau_social.ml`.

---

## 117. La colonne du compteur avait deux sources, et l'ordre des relations tranchait

Le point 92 avait posé `_decrement_fk_column` comme source UNIQUE de la colonne
visée par un `increments`/`decrements`, après un bug où le stock d'un produit
était décompté en portant l'identifiant de la commande. La leçon écrite alors —
« ne jamais recalculer ce que cette fonction sait » — n'avait pas été appliquée
partout : trois autres endroits déduisaient la même colonne de
`_get_incoming_relation`, c'est-à-dire de la PREMIÈRE relation entrante déclarée.

### Le défaut, mesuré avant d'être corrigé

Sur une entité à DEUX relations entrantes dont celle du compteur est déclarée en
premier (`relation Post hasMany Like` avant `relation Member hasMany Like`), la
route `Create` produisait :

```
INSERT INTO "like" ("note", "member_id") VALUES (?, ?)
```

`post_id` n'y figurait pas. Après un like : le compteur du post valait bien 1,
et la ligne en base était `(1, 'bravo', None, 1)`. **Le like ne savait pas quel
post il likait.** Aucune erreur, aucun avertissement — la colonne existe au
schéma, elle est déclarée au contrat, et elle reste vide.

Inverser les deux relations suffisait à tout faire fonctionner. C'est donc un
bug d'ORDRE, de la même famille que celui du point 92 : **il ne se voit pas sur
la spec qui l'a fait naître**, et le banc d'essai qui a servi à valider `oncePer`
au point 116 déclarait justement l'acteur en premier.

### Ce qu'il emportait avec lui

Le point 116 avait ajouté un refus à la compilation pour `oncePer` posé sur une
colonne jamais écrite — SQLite tenant deux NULL pour distincts, l'index existait
et ne refusait rien. Ce refus traitait le SYMPTÔME. La cause était ici, et elle
touchait toute entité portant un compteur, `oncePer` ou pas.

### Le correctif

`_counter_fk_columns` (generator/core.py) dérive la colonne de
`_decrement_fk_column` pour CHAQUE règle de l'entité, dédoublonnée. Les trois
lecteurs la partagent : `_client_fk_columns` l'exclut des clés étrangères
client, `schemas.py` l'expose au corps de requête, `routes.py` l'écrit à
l'insertion. **La colonne est écrite exactement une fois, jamais zéro, jamais
deux.**

Un `elif` devenu `if` porte l'essentiel : la branche du compteur était
mutuellement exclusive avec le peuplement depuis l'identité, alors que les deux
colonnes coexistent — `member_id` vient du jeton, `post_id` du client. Et le
repli silencieux `or owner_info["fk_column"]` de `routes.py` devient une erreur
de génération : mieux vaut un compilateur qui s'arrête qu'une route qui
décrémente la mauvaise ligne — même arbitrage qu'au point 99.

Le refus d'`oncePer` du point 116 n'est PAS supprimé : il devient inatteignable
pour une colonne correctement écrite, et reste actif pour une colonne qui ne
l'est réellement jamais. Le supprimer parce qu'un cas connu ne le déclenche plus
supposerait qu'aucun autre ne le déclenchera.

### Méthode

Délégué à Codex avec la reproduction minimale, l'interdiction de commiter, et
les vérifications exigées. **Son rapport n'a pas été pris pour argent
comptant** : les épreuves ont été REJOUÉES ici — suite complète (836 tests,
91,87 %), `ruff`, les trois formes de spec (compteur d'abord, acteur d'abord,
relation unique) compilées et servies, et le parcours modérateur rejoué de bout
en bout sur une application produite par le VRAI dialogue guidé, pas par un
assemblage direct du modèle. C'est la règle du dépôt, et elle vaut pour tout
exécutant.

Éprouvé par `tests/test_colonne_compteur_independante_de_l_ordre.py` (les deux
ordres donnent la même ligne en base) et deux assertions de catalogue dans
`tests/test_app_templates.py`.

---

## 118. Le backend savait tout faire sauf se déployer

Vingt-huit briques, un contrôle d'accès éprouvé contre un vrai serveur, une
frontière d'émission SQL typée — et un `app.py` qu'on ne pouvait pas mettre en
ligne. Il manquait quatre choses, aucune d'elles n'étant une brique du DSL :
un frontend hébergé ailleurs ne pouvait pas appeler l'API (pas de CORS), un
orchestrateur ne pouvait pas savoir si le service répondait (pas de
healthcheck), un exploitant ne pouvait rien tirer des journaux (texte libre
d'uvicorn), et rien n'empêchait de démarrer en production avec un secret JWT
généré sur place — donc invalidé au prochain redémarrage, donc tous les jetons
révoqués sans que personne l'ait demandé.

Ces quatre manques ont un point commun : ils ne se voient pas en compilant, ni
en lançant le serveur sur son poste. Ils ne se voient qu'en DÉPLOYANT.

### CORS est opt-in, et `*` est refusé au démarrage

`MONL_CORS_ORIGINS` liste des origines explicites, séparées par des virgules.
Absente, **aucun en-tête CORS n'est émis** : le comportement d'avant ce point
est strictement inchangé, et un backend monl reste par défaut inappelable
depuis une autre origine.

L'étoile est refusée, et le refus est un **arrêt au démarrage**, pas un
avertissement. La raison n'est pas le purisme : le middleware émet
`allow_credentials=True`, et « toutes les origines » plus « avec les
identifiants » est la combinaison exacte qui laisse n'importe quel site lire
les réponses authentifiées d'un utilisateur connecté. Un avertissement dans un
journal que personne ne lit aurait laissé cette porte ouverte en production —
même arbitrage qu'au point 92 sur les avertissements qui se trompent : un
message qu'on apprend à ignorer ne protège de rien.

Les méthodes annoncées sont **calculées depuis les routes réellement émises**
(`_cors_methods`, generator/runtime.py) et non listées en dur. Une application
qui n'a aucune route `Delete` n'annonce pas `DELETE` : le contrat CORS dit ce
que le backend fait, comme le contrat frontend (points 76 et 79).

### Deux healthchecks, et ils ne sont pas dans le contrat

`/health` répond sans toucher à la base — c'est la VIVACITÉ, la question
« le processus est-il vivant ? ». La faire dépendre de SQLite ferait
redémarrer en boucle un service dont seule la base est momentanément
indisponible. `/health/ready` exécute un `SELECT 1` — c'est la
DISPONIBILITÉ, et elle rend 503 quand la base ne répond pas.

Les deux sont `include_in_schema=False` et **absents du contrat frontend** :
une IA d'interface n'a rien à dessiner avec elles. Elles rejoignent donc la
liste `infra` de `tests/test_orchestrator.py` — délibérément, en la nommant,
plutôt qu'en affaiblissant l'égalité stricte entre le contrat et les
décorateurs réellement écrits dans `app.py`.

### Les journaux structurés ne recopient rien

`MONL_LOG_FORMAT=json` fait émettre une ligne JSON par requête : horodatage,
méthode, chemin, code, durée, identifiant de requête. **Aucun corps, aucun
en-tête entrant, aucune query string** n'y entre. Ce n'est pas une économie de
place : le corps de `/register` et de `/login` contient le mot de passe en
clair, et un journal est ce qui se recopie, s'archive et se donne à lire. Le
test l'exige explicitement — il inscrit un compte avec un mot de passe témoin
et vérifie qu'il n'apparaît nulle part.

L'`X-Request-ID` fourni par l'appelant est REPRIS, mais seulement s'il passe
un motif étroit (alphanumérique, points, tirets, 64 caractères au plus) ;
sinon il est remplacé par une valeur tirée au hasard. Un identifiant de
requête va dans une ligne de journal : accepter n'importe quoi laisserait
écrire des sauts de ligne dans le journal, c'est-à-dire y fabriquer de fausses
entrées.

### Le refus de démarrer sans secret en production

`MONL_ENV=production` sans `MONL_JWT_SECRET` **arrête le processus**, même
quand un fichier `.jwt_secret` est présent dans le dossier — vérifié en réel,
c'est le cas qui compte. Le repli sur `.jwt_secret` est correct en
développement et faux en production : il fait dépendre la validité de tous les
jetons émis d'un fichier qui ne suit pas l'image, donc perdu au premier
redéploiement.

### `Dockerfile` et `.dockerignore` : produits, jamais scellés

La compilation les écrit s'ils n'existent pas, et **ne les touche plus
ensuite**. Ils rejoignent `.jwt_secret` et `CLAUDE.md` dans les fichiers
préservés du staging (point sur la publication transactionnelle), et
n'entrent PAS dans les empreintes d'artefacts protégés : un déploiement réel
demande presque toujours d'adapter l'image (dépendance système, port,
utilisateur non-root), et un fichier scellé rendrait cette adaptation
impossible sans contourner le garde-fou — ce que ce dépôt refuse partout
ailleurs.

Le `.dockerignore` exclut `.jwt_secret` : le secret n'entre pas dans l'image,
il vient de l'environnement. Vérifié en réel — `ls /app` dans le conteneur ne
le montre pas.

### Ce qui a été prouvé

Un projet compilé, construit avec `podman build`, lancé en conteneur :
démarrage refusé sans `MONL_JWT_SECRET` (l'image portant `MONL_ENV=production`),
puis avec le secret — inscription, connexion, création et lecture d'un
enregistrement réel, en-tête CORS correct pour l'origine déclarée et absent
pour une autre, journaux JSON parsables, secret absent de l'image.

`_contract_signature` a été interrogée, comme l'exige la liste de questions à
poser avant toute brique : la réponse est NON, aucun de ces changements ne
modifie ce que le frontend doit dessiner. C'est la première fois que la
réponse est négative après vérification plutôt que par omission.

Éprouvé par `tests/test_deploiement.py` (9 tests contre de vrais serveurs).

---

## 119. La couche données choisit son dialecte au démarrage

Le backend généré devait pouvoir sortir du mono-fichier SQLite sans faire
diverger l'artefact scellé entre développement et production. Le choix est
donc **au démarrage**, par `MONL_DATABASE_URL`, et non à la compilation :
variable absente = SQLite strictement comme avant; `postgresql://` ou
`postgres://` = psycopg v3. `psycopg` est une dépendance optionnelle (`.[postgres]`)
et une absence avec un DSN est nommée explicitement au démarrage.

### Une seule source de SQL, deux paramétrages

Le générateur continue d'émettre `?` et les paramètres dans un tuple. La
connexion PostgreSQL traduit uniquement le marqueur en `%s`. Cette réécriture
est sûre pour la raison du point 108 : aucune valeur client n'entre dans le
texte d'une requête, `sql.py` n'offre pas d'API pour le faire, et les tests
`test_sql_emission.py` et `test_invariants_securite.py` l'interdisent. Le texte
reste donc du SQL fixe; la traduction ne peut déplacer aucune valeur.

Le `schema.sql` conservé pour SQLite est adapté au moment où PostgreSQL est
connu : `INTEGER PRIMARY KEY AUTOINCREMENT` devient une identité PostgreSQL.
`DOUBLE PRECISION` est utilisé pour les nombres flottants. `Money` reste
`NUMERIC(10, 2)` : les montants partent chez Stripe et un flottant binaire
n'est pas un type d'argent.

### Les erreurs d'intégrité sont des données structurées

Les routes ne déduisent plus la cause d'un 409 PostgreSQL depuis un message
humain. Elles lisent SQLSTATE `23505`/`23503` et, pour `23505`, le nom de
contrainte psycopg (`idx_once_per_…` ou index de champ unique). SQLite conserve
son repli historique. Les trois réponses restent distinctes : `oncePer`,
`unique`, et clé étrangère invalide.

Le compteur `_monl_sequences` reste dans la transaction de création; le
verrou de ligne PostgreSQL et l'index unique du champ numéroté sont éprouvés
par deux créations simultanées. Le stock conserve une seule instruction
conditionnelle `UPDATE`, qui départage deux commandes concurrentes sans lecture
préalable.

### Ce que le frontend ne voit pas

`_contract_signature` ne tient toujours pas compte du choix de moteur, des
placeholders, des types SQL internes, des migrations ou des erreurs internes :
ils ne modifient ni routes, ni accès, ni forme de réponse. En revanche, le
type d'un champ exposé appartient au contrat frontend : A2 le compare et
signale par exemple `Note.priority : String → Integer`. Les empreintes de
`app.py`, `schema.sql`, `manage.py` et `monl.json` changent parce que le
backend généré change; le contrat reste identique pour un changement interne.

Éprouvé contre un vrai serveur par `tests/test_postgresql.py` (6 cas, sautés
proprement sans `MONL_TEST_DATABASE_URL`), et par la suite SQLite complète.

### Deux défauts trouvés en revue, et ce qu'ils apprennent

Le classement structuré des erreurs d'intégrité a été écrit en trois branches
nommées — `oncePer`, `unique`, clé étrangère — et le `raise` inconditionnel qui
terminait le bloc a disparu avec elles. **Un `except` qui n'aboutit pas à un
`raise` est un `except` qui ment** : une intégrité violée d'une quatrième
espèce (NOT NULL, CHECK, ou un index unique que la spec ne DÉCLARE pas)
sortait du bloc sans rien lever, et la route continuait jusqu'à son
`return {'status': 'success'}` — après un `rollback`.

Le cas est atteignable sans rien forcer : la brique 22 pose un index unique
sans qu'on écrive `unique`, donc `uniques_ici` est vide et la branche `unique`
n'était même pas émise. Mesuré sur un vrai serveur, compteur remis à zéro comme
le ferait la restauration d'une sauvegarde partielle : **500
`UnboundLocalError` sur `row_id`** au lieu d'un 409. Et là où `row_id` est déjà
lié — une intégrité levée par une instruction plus tardive du même `try`,
recalcul d'agrégat ou décompte — la route aurait annoncé écrit ce qui venait
d'être défait. C'est la faute la plus grave possible pour une couche données :
mentir sur ce qui est en base.

Le second défaut est d'une autre famille. `manage.py` réutilise désormais
`_connect()` du `app.py` généré — décision juste, c'est lui qui porte le choix
de dialecte, et deux connexions divergentes créeraient des comptes dans une
autre base que `/register`. Mais l'import était en TÊTE de fichier, or `app.py`
lit `.jwt_secret` et `schema.sql` relativement au dossier courant : `manage.py`
cessait de fonctionner depuis n'importe quel autre dossier. **C'est le SEUL
chemin pour créer un compte à rôle privilégié** (un rôle sans `selfRegister`
n'est inscriptible par aucune route), donc casser son usage depuis ailleurs
casse le provisionnement. L'import vit maintenant dans `_connect()`, après le
`chdir`. La leçon rejoint le point 105 : le dossier courant est un état, pas
une constante.

Aucun des deux ne se voyait en relisant le diff — le premier demandait de
regarder le code GÉNÉRÉ, le second de lancer la commande depuis ailleurs.

---

## 120. Les migrations non additives sont nommées et refusent le démarrage

Le point 32 ne rattrapait volontairement que les colonnes ajoutées. Une
comparaison de schéma ne peut pas prouver qu'une colonne `heading` est
l'ancien `title`, ni qu'un texte se convertira sans perte en entier. Le
compilateur accepte donc un seul moyen explicite de franchir cette frontière :

```
migration note_fields
    rename Note.title to heading
    alter Note.priority from String to Integer
    drop Note.legacy
```

Le nom de la migration est l'identifiant de l'opération demandée ; il ne sert
pas de commentaire. Au démarrage, une différence non additive sans migration
correspondante est rapportée et le serveur refuse de servir l'application.
L'auteur doit exécuter `monl migrate PROJET --name note_fields`. La montée et
la descente des renommages et changements de type sont transactionnelles et
inscrites dans `_monl_migrations`; un `drop` reste irréversible sans
sauvegarde et sa descente est refusée.

L'historique porte l'opération, la table, le sens, la date, les détails et
l'empreinte SHA-256 du schéma résultant. Les ajouts automatiques sont eux
aussi enregistrés. Il rend une base lisible sans faire croire qu'il constitue
une sauvegarde.

La syntaxe est un bloc de premier niveau. `assets_tool.py` le reconnaît pour
positionner textuellement un éventuel bloc `assets`; `content_tool.py` ne lit
que les blocs `seed` et laisse les migrations intactes. Le changement ne
contredit donc pas les outils qui lisent la spec sans construire un AST.

### Un défaut trouvé en revue : la trace qui noie le diagnostic

`manage.py` refuse d'écrire dans une base qui attend une migration non
additive, et c'est juste : provisionner un compte dans un schéma en attente
l'expose au même risque que le servir. Mais il sortait sur un `RuntimeError`
NON RATTRAPÉ — le diagnostic d'`app.py`, correct et précis, se retrouvait noyé
sous quinze lignes de trace.

**Une trace n'apprend rien à qui doit décider quoi faire.** C'est le reproche
des points 97 et 105, sur un troisième point d'entrée. La sortie NOMME
désormais le remède et le dossier concerné, et `manage.py` est justement le
message que lit un exploitant bloqué : c'est le seul chemin pour créer un
compte à rôle privilégié.

Le correctif a lui-même buté sur un piège du dépôt, qui mérite d'être écrit :
`admin_cli.py` est un GABARIT formaté, pas du code Python ordinaire. Une
accolade y est un champ de format (`{{}}` pour en produire une) et un
antislash y est consommé une fois (`\\n` pour produire `\n`). Les deux erreurs
ont été faites, et **aucune des deux n'était visible dans le diff** : la
première faisait échouer la génération, la seconde produisait un `manage.py`
au `SyntaxError`. Seule la recompilation réelle les a montrées.

---

## 121. Le fichier déposé par le client est un `Upload`, pas une `Image`

`Image` et `Upload` ne fusionnent pas. `Image` est un chemin relatif vers un
asset fourni par l'auteur avant la compilation : le compilateur en vérifie la
présence, `assets_tool.py` le liste, et `monl frontend` le laisse hors de
`frontend/`. `Upload` est au contraire une déclaration d'octets qui
n'existent qu'à l'exécution ; lui appliquer le validateur d'assets refuserait
un fichier avant même que le client ne l'ait envoyé. `content_tool.py` et
`assets_tool.py` ignorent donc explicitement `Upload` au lieu d'en faire un
seed ou un média éditorial.

La plus petite forme retenue est celle qui produit effectivement les trois
contraintes indispensables et les routes :

```
avatar: Upload
rule Profile.avatar upload max 5242880 types "image/png", "image/jpeg"
```

Il n'y a ni option de confort ni plafond implicite : la limite est en octets
et les MIME sont obligatoires. Le compilateur ne fait aucun appel réseau. Au
runtime, le type est établi par signature d'octets (magic number), jamais par
le nom ou le `Content-Type` du client. La liste actuellement sûre est PNG,
JPEG, GIF, WebP et PDF ; HTML et SVG sont refusés. La lecture renvoie toujours
`application/octet-stream`, `Content-Disposition: attachment` et `nosniff`,
afin qu'un fichier déposé ne puisse pas devenir un HTML ou un SVG exécutable
depuis la même origine.

La colonne SQL contient uniquement une référence hexadécimale aléatoire. Les
octets sont écrits sous `.monl_uploads/<entite>/<id>/<champ>/<reference>`, ou
dans `MONL_UPLOADS_DIR`, qui doit être un volume dédié. Ce dossier est hors de
`frontend/`, hors des artefacts scellés, ajouté au `.dockerignore` et ignoré
par git. C'est nécessaire parce que `monl frontend` renomme `frontend/` en
`frontend.precedent/` : y placer le dépôt ferait disparaître les fichiers sans
message. Le nom fourni par le client n'est jamais un chemin.

La protection porte sur le fichier autant que sur la ligne : une déclaration
Upload exige Read et Update non publics et une règle `ownedBy` ou
`accessibleBy` sur chacun. Les routes multipart et de lecture réutilisent
l'ACL de la ligne et renvoient `404` à un tiers ; connaître la référence ne
suffit pas. Le dépôt remplace l'ancien fichier après commit. La suppression
de la ligne supprime le fichier après commit ; il n'y a pas de ramasse-miettes
inventé. Une erreur de suppression physique est seulement signalée, et le
fichier reste inaccessible faute de ligne et d'URL statique.

Le contrat frontend donne le nom du champ multipart, la limite, les types, la
route POST et la route GET. `_contract_signature` inclut le digest de ces
contraintes : changer la limite ou les types déclenche le delta, y compris
pour un champ déjà présent. Le smoke test garde ces valeurs en dur comme un
client quelconque. La génération est conditionnelle : une spec sans Upload
ne change pas `app.py`, et les deux moteurs SQLite/PostgreSQL n'écrivent que
la même colonne de référence.

### Ce que la revue a mesuré, et qui n'était pas dans les tests

Trois angles éprouvés en plus contre un vrai serveur, parce qu'ils décident de
la solidité de la brique plutôt que de sa fonction :

**Un type hors liste blanche mais parfaitement bénin** — un GIF sur une
déclaration `"image/png", "application/pdf"` — est refusé en 415. Sans ce
contrôle, la brique n'aurait interdit que HTML et SVG, c'est-à-dire seulement
ce à quoi on avait pensé.

**Trente mébioctets envoyés contre une limite de 2048 octets** rendent 413 en
0,07 seconde, avec 11 Mo de mémoire crête, et le serveur reste vivant. C'est la
question qui compte vraiment sur un téléversement : un plafond qui n'est
appliqué qu'APRÈS avoir lu le corps entier n'est pas un plafond, c'est un
déni de service en une ligne de `curl`.

**Un nom de fichier hostile** (`../../../../tmp/EVASION.png`) est accepté sans
broncher — et n'écrit rien hors de la zone de dépôt, parce que le nom du client
n'est jamais un chemin. Refuser le nom aurait été un contrôle de plus à tenir
juste ; ne jamais s'en servir est un contrôle de moins à tenir.

## 122. Monl sait envoyer un message sans promettre sa remise

La brique B2 choisit le plus petit déclencheur utile :

    capability auth
        identifier: email

    rule Order.Create sends "Commande reçue" "Votre commande¶est prise en compte"

Un envoi part après chaque création métier réussie, vers le compte authentifié
qui vient de créer la ligne. Le déclencheur oneOf/transition n'est pas retenu
ici : il appartient à une notification d'état, avec la question des transitions
réelles et des rejouements ; la brique reste creation-only. Il n'y a donc ni
confirmation d'adresse, ni mot de passe oublié, ni autre preuve qu'une boîte
reçoit un message. Monl ne vérifie que la forme déclarée de l'identité.

Le refus de compilation le plus important est volontaire : une règle sends
exige capability auth avec identifier: email. Sans ce lien d'identité, monl
n'a aucune adresse de compte où écrire. Un champ métier libre nommé email ne
vaut pas une adresse de compte vérifiée. Une création publique est également
refusée, puisqu'elle ne fournit aucun compte destinataire. Le corps reste un
littéral monoligne et ¶ devient une séparation de paragraphes dans le
message.

Le sujet ne peut contenir ni retour chariot ni saut de ligne : le compilateur
refuse l'injection d'en-têtes SMTP à cet endroit. Le destinataire et
l'expéditeur sont contrôlés à nouveau au runtime, avant de construire
EmailMessage, pour neutraliser une adresse de compte historique ou une
configuration empoisonnée contenant CR/LF. Une identité email reste une
forme ; monl ne contacte jamais la boîte pour la vérifier.

Les variables de transport sont uniquement l'environnement :
MONL_SMTP_HOST et MONL_SMTP_FROM sont obligatoires, MONL_SMTP_PORT vaut
587 par défaut, et MONL_SMTP_USERNAME/MONL_SMTP_PASSWORD sont optionnelles
mais doivent venir ensemble. Une variable requise absente est nommée dans la
trace. La création est commitée avant le lancement d'un thread daemon
éphémère : un SMTP lent ou injoignable ne retarde pas la route et ne défait
jamais l'écriture métier. Il n'y a ni file persistante, ni retry, ni garantie
de remise ; l'échec est une trace [MONL_MESSAGE] explicite côté serveur,
visible par l'exploitant.

Le contrat frontend porte le déclencheur, le destinataire, le sujet, le corps
structuré et la limite de garantie. _contract_signature inclut le digest de
ces éléments : monl update doit donc signaler une notification ajoutée,
retirée ou réécrite, même si aucune route ni aucun champ ne change. Le delta
est l'endroit où l'interface apprend d'afficher qu'une tentative de message a
été lancée — et de ne pas promettre une remise que cette brique ne garantit
pas.

La forme rule ne change rien à la lecture textuelle de assets_tool.py et
content_tool.py : ils ne reconnaissent que leurs blocs seed/assets, qu'une
règle sends ne modifie pas. L'envoi ouvre une connexion indépendante à
_monl_users et fonctionne de la même façon quand le dialecte de démarrage
est SQLite ou PostgreSQL. Le compilateur lui-même ne fait aucun appel réseau.

### Ce que la revue a mesuré contre un vrai faux SMTP

Un serveur SMTP minimal écrit pour l'occasion enregistre TOUT ce qui passe sur
le fil — c'est la seule façon de vérifier qu'un message est parti, plutôt que
de croire un code 200. Ce qu'il a reçu :

```
MAIL FROM:<boutique@exemple.test>
RCPT TO:<cliente@exemple.test>
From / To / Subject: Votre commande
Merci pour votre commande.
Elle est prise en compte.
```

Le `¶` du point 64 est bien devenu un saut de paragraphe, sans nouvelle
syntaxe multiligne. Deux créations donnent deux messages, jamais trois.

**L'injection d'en-têtes est fermée en amont, pas dans le formateur.** Une
inscription sous `pirate@exemple.test\nBcc: victime@ailleurs.test` est refusée
en 422 par le contrôle de forme du point 95 : l'adresse d'envoi étant
l'identifiant de COMPTE, et un identifiant ne pouvant pas contenir
d'espacement, il n'existe aucun chemin par lequel un client fabrique un
destinataire caché. C'est la conséquence utile du refus de compilation qui
porte la brique — sans `identifier: email`, il aurait fallu défendre un champ
texte libre, ce qui est un contrôle de plus à tenir juste.

**La résilience, mesurée plutôt que déduite.** SMTP injoignable : la route
métier rend 200 en 3,7 ms, l'écriture est conservée, et la trace nomme
l'entité, l'identifiant et la cause (`[Errno 111] Connection refused`). Aucune
variable configurée : 200 en 3,8 ms, et la trace NOMME `MONL_SMTP_HOST`. Les
deux chiffres comptent autant que les codes : une route qui attendrait
l'expiration d'un SMTP mort mettrait plusieurs secondes, et une brique
d'envoi rendrait alors l'application inutilisable le jour où le fournisseur
tombe. Le smoke test reste vert hors ligne, sans erreur ni alerte.

## 123. Filtrer et trier sans inventer un langage de requête

La brique B3 retient deux déclarations séparées et aucune recherche textuelle :

    rule Order.Read filter status
    rule Order.Read filter shipped
    rule Order.Read sort placedAt

Un filtre est une égalité exacte sur un champ déclaré. Les champs texte libres
restent possibles si l'auteur les déclare, mais monl ne fournit ni LIKE, ni
recherche insensible à la casse, ni tokenisation : ce serait à la fois plus
cher et divergent entre SQLite et PostgreSQL. Une valeur de oneOf apparaît
dans le contrat comme liste de choix ; un booléen y apparaît comme true/false.
Les autres champs scalaires acceptent leur valeur typée exacte. Plusieurs
filtres se combinent par AND, sans opérateur que le client choisit.

Un tri accepte sort parmi les colonnes déclarées et direction=asc|desc. La
colonne vient d'une whitelist calculée à la compilation et est rendue par
sql.ident(). Les deux directions sont des mots SQL fixes produits par
sql.kw(). Les valeurs de filtre passent par sql.bind(). Une valeur client ne
peut donc entrer dans le texte SQL, et le tri ne peut pas devenir une
expression.

Le filtre est ajouté au WHERE d'accès déjà présent : propriété directe ou
transitive, accessibleBy, superviseur et publicWhen gardent leur sémantique.
Une liste filtrée est donc toujours un sous-ensemble de la liste non filtrée
pour le même compte. Un champ hidden, categorized ou Upload est refusé à la
compilation : compter les réponses permettrait de retrouver respectivement
une valeur masquée, le nombre remplacé par une catégorie, ou l'existence d'un
fichier. Les noms explicitement évocateurs d'un secret (password, secret,
token, api_key) sont refusés par la même garde. Le DSL n'a pas de type Secret ;
si ce type apparaît un jour, il devra rejoindre cette liste avant d'être
filtrable ou triable.

Le contrat frontend indique les champs concernés, le paramètre exact, les
valeurs permises et la whitelist de tri. _contract_signature inclut ce bloc :
ajouter ou modifier une capacité réécrit donc le frontend, même si aucune
route ni aucun champ ne change. Le smoke test lit ce contrat et appelle les
routes de liste avec une requête conforme, comme tout autre client.

La forme n'ajoute pas de syntaxe aux blocs seed ou assets : leurs lecteurs
textuels restent inchangés. Elle ne change pas la signature des listes
historiques, où limit et offset gardent leurs bornes. Pour une spec qui ne
déclare ni filter ni sort, app.py reste inchangé à l'octet.

Le compilateur ne crée pas d'index automatiquement. Un filtre sans index peut
faire un balayage complet ; la cardinalité et la charge réelle appartiennent
au projet, et monl ne promet aucune performance qu'il n'a pas mesurée.
L'auteur peut choisir une stratégie d'indexation adaptée à sa base. Les tris
textuels suivent la collation du moteur ; les dates ISO UTC produites par
timestamp restent ordonnables comme du texte. La brique ne fait pas de
recherche textuelle, donc elle ne promet pas un comportement de casse entre
SQLite et PostgreSQL.

La sortie générée est conditionnelle, et les invariants de l'émission SQL
restent ceux des points 108 et 109. Le vérificateur est concerné dès que les
paramètres apparaissent dans une route ; les tests contre serveur couvrent
SQLite et PostgreSQL, sans exécuter deux suites en parallèle.

### Ce que la revue a mesuré, et pourquoi le filtre est borné DEUX fois

Quatorze contrôles contre un vrai serveur. Les deux qui décident de la brique :

**Une valeur de filtre n'atteint jamais le SQL si elle n'est pas déjà légale.**
Le paramètre est typé `Optional[Literal['nouvelle', 'expediee', 'annulee']]`,
c'est-à-dire borné par le `oneOf` de la brique 19 : `' OR 1=1 --`, `%`, et une
valeur de 6000 caractères rendent 422 AVANT toute requête. Le `sql.bind()`
derrière est la seconde barrière, pas la première. Deux bornes valent mieux
qu'une parce qu'elles ne tombent pas ensemble : la première dit ce qui est
légal, la seconde dit que rien n'est interprété.

**Le tri ne concatène rien.** La chaîne du client sert de CLÉ dans un
dictionnaire construit à la compilation (`{'placeeLe': '"placeeLe"'}`), et
une clé absente rend 422. Un nom de colonne ne peut pas être lié par `?` :
la seule façon sûre de le choisir est donc de ne jamais le lire, mais de
l'élire dans une liste close. `id"; DROP TABLE commande;--` et
`ASC; DROP TABLE commande` rendent 422 ; la table a toujours ses cinq lignes.

**Le filtre s'AJOUTE à la propriété.** Avec deux comptes, la liste filtrée du
second ne montre que sa propre ligne. Le `WHERE` d'accès reste la base, le
filtre est joint par `AND` — l'inverse aurait fait d'un paramètre d'URL une
façon de lire les lignes d'autrui.

**Les cinq refus de compilation sont ceux qui manquaient.** Filtrer ou trier
sur un champ `hidden` ou `categorized` est refusé, et le message porte le
raisonnement : *« un filtre ou un tri est un oracle »*. Compter les lignes qui
reviennent pour chaque valeur essayée lit un champ que la brique 2 retire de
toutes les réponses, et retrouve le nombre exact que la brique 5 remplace
volontairement par un libellé. C'est une fuite qui ne passe par aucune
réponse : elle passe par le TOTAL.

Ce que la brique ne fait PAS, et l'assume : aucune recherche textuelle
(`LIKE`, casse, opérateurs), aucun index créé automatiquement, aucune promesse
de performance sur une colonne non indexée. La ligne rouge de CLAUDE.md tient :
rien de ce qui est filtrable n'est choisi par le client, tout est déclaré.
