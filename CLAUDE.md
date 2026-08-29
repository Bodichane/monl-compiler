# monl — mémoire de projet pour Claude Code

## Ce qu'est monl

PIVOT (point 40 de docs/design_decisions.md) : monl est désormais une
plateforme d'ORCHESTRATION. `./monl` (src/cli.py) mène un dialogue guidé
sans IA (src/dialogue_engine.py) qui produit la spec, compile le backend,
et génère un contrat frontend (src/frontend_contract.py :
frontend_contract.json + FRONTEND_PROMPT.md) destiné à une IA UI externe.
`monl run` vérifie la cohérence (empreintes dans monl.json) et monte
frontend/ sur /site via un wrapper serve.py — app.py reste scellé.
`monl update` recompile et rapporte le delta du contrat. Le dialogue
ouvre sur un catalogue de 10 modèles d'applications (src/app_templates.py,
point 45 — chaque modèle est testé compilable en tout-non/tout-oui) et
fonctionne en saisie stricte, entièrement déterministe : aucune IA, aucun
appel réseau. La spec produite est revalidée par le vrai parseur avant
d'être écrite.
`monl frontend` appelle l'IA soit par clé API — Anthropic, ou n'importe
quel fournisseur au dialecte OpenAI via la table `OPENAI_COMPATIBLE` et
l'échappatoire `--provider openai-compatible` (point 69) — soit par un
agent en ligne de commande (`--provider claude-code|codex|gemini`, ou
`--agent-command` pour tout autre, point 69 ; authentification par
abonnement — point 43) ; `monl import` couvre le copier/coller claude.ai
(point 42). Dans tous les cas : mêmes garde-fous, même re-vérification
(cohérence + smoke test). Le garde-fou d'empreinte des artefacts protégés
ne dépend PAS de l'agent utilisé — ne jamais le contourner en ajoutant une
voie. ATTENTION : chaque projet compilé reçoit son PROPRE CLAUDE.md
(généré par write_project_claude_md) — ne pas confondre avec ce fichier-ci,
qui est la mémoire du dépôt monl lui-même. Le cœur
ci-dessous est inchangé et reste la source de vérité :

Compilateur DSL (fichiers `.ml` — l'ancienne extension `.yaml` reste acceptée) qui génère des applications
complètes (FastAPI + SQLite + JWT) à partir de specs déclaratives. Pipeline :
grammaire Lark (`src/parser.py`) → validateur + audit de sécurité
(`src/ast_validator.py`) → AST normalisé → générateur (package
`src/generator/`)
→ `app.py` / `schema.sql` / `sandbox_ai.py` + `frontend_contract.json` /
`FRONTEND_PROMPT.md` (couche orchestrateur, voir src/cli.py).

## Documentation à lire avant toute nouvelle brique

**`docs/design_decisions.md`** est le journal détaillé du projet — numéroté
jusqu'à 90, avec sommaire complet en tête de fichier. Deux pièges de
numérotation, tous deux assumés : les numéros **45 et 46 désignent chacun
deux points distincts** (séquelle d'une fusion), et le **point 6 est un
doublon réservé** du point 1, vide, gardé pour ne pas décaler les renvois.
Citer un point par son titre autant que par son numéro. Chaque règle stricte du
compilateur, chaque bug corrigé, chaque décision d'architecture y est
expliquée avec le "pourquoi", pas seulement le "quoi". **Le consulter avant
d'ajouter quoi que ce soit** — plusieurs pièges déjà rencontrés (voir points
23, 26) ne sont pas évidents à deviner depuis le code seul.

## Méthode de travail — non négociable

**Chaque changement est prouvé par exécution réelle, jamais par relecture
de code seule.** Concrètement :
- Compiler réellement (`python3 -m monl.main exemples/03_reseau_social.ml`,
  depuis la racine avec `src/` sur le PYTHONPATH — ou `./monl compile`)
- Relancer un vrai serveur (`python3 -m uvicorn app:app --host 127.0.0.1 --port PORT`)
- Faire de vrais appels (`curl`, ou un script Node+jsdom pour le JS front —
  voir `/tmp/jsdom_test/` dans les sessions précédentes, à recréer si besoin :
  `npm install jsdom` puis charger le HTML généré avec `runScripts: "dangerously"`)
- Lancer la suite de tests : `python3 -m pytest tests/ -q` (1379 tests
  actuellement ; `tests/test_demo.py` s'appuie sur le dossier `demo/`
  versionné — ne pas le supprimer. La démo est **CodexShop**, une papeterie
  qui exerce la chaîne marchande entière ; ses ENTRÉES seules sont suivies
  (`spec.ml`, `frontend/`, `assets/`), jamais sa sortie compilée ni son
  `.jwt_secret`. `test_design_contract.py` ne s'en sert plus : il construit
  sa propre spec)

Plusieurs bugs réels (ordre des contraintes `FOREIGN KEY`, collision avec un
mot-clé SQL réservé, `scrollIntoView` absent masquant un vrai succès,
sur-échappement de backslash entre couches de templating Python, un mécanisme
de clé étrangère qui décrémentait le mauvais enregistrement) ne se seraient
JAMAIS révélés par simple lecture — ne pas sauter cette étape pour aller
plus vite.

**Outillage de vérification** (point 63) — trois questions, trois commandes :
```bash
ruff check src tests                                  # zéro attendu : tout
                                                      # signalement est un vrai
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing   # 89 %
python3 -m pytest tests/test_architecture.py -q       # les frontières de ce
                                                      # fichier, vérifiées
```
Les exceptions de `ruff` vivent dans `pyproject.toml` et portent chacune sa
raison — en ajouter une sans raison écrite, c'est rouvrir la porte que le
point 63 ferme. La CI (`.github/workflows/ci.yml`) rejoue lint + suite.

**Toujours nettoyer avant/après compilation** (depuis le point 64, la suite
de tests ne salit plus la racine : ce nettoyage ne concerne que VOS
compilations manuelles) :
```bash
rm -f app.py schema.sql sandbox_ai.py .jwt_secret *.db \
      frontend_contract.json FRONTEND_PROMPT.md FRONTEND_UPDATE_PROMPT.md monl.json serve.py
find . -name "__pycache__" -exec rm -rf {} +
```

**Piège d'environnement récurrent** : les processus lancés en arrière-plan
(`&`) dans un appel d'outil ne survivent PAS à l'appel suivant — démarrer un
serveur ET faire les requêtes de test doivent être dans le MÊME appel bash.

## Vision produit : écosystème de capacités, construit brique par brique

Décision explicite et actée : PAS de multi-DSL ni d'IR multi-cible pour
l'instant (projet d'une tout autre ampleur, à reconsidérer seulement une
fois plusieurs capacités réelles éprouvées). Chaque brique est petite,
testée avant la suivante. Progression du simple au complexe, avec un
réseau social anonyme comme banc d'essai final.

### Briques terminées et testées (points 24-31, puis 74)

> **Où sont passés les fichiers de preuve.** Chaque brique avait à l'origine
> son `exemples/NN_xxx_demo.yaml` dédié. La bêta 3 (commit `2105a1f`) les a
> tous supprimés au profit de 5 exemples thématiques : `01_portfolio.ml`,
> `02_boutique.ml`, `03_reseau_social.ml`, `04_kanban.ml`,
> `05_classement.ml`. **`exemples/03_reseau_social.ml` consolide à lui seul
> les briques 3 à 8** ; `tests/test_compile_all.py` compile chaque exemple à
> chaque exécution de la suite. Les références ci-dessous ont été
> resynchronisées le 26/07/2026 — ne pas les faire pointer vers les anciens
> fichiers, ils n'existent plus.
>
> Attention à la nuance : compiler n'est pas se comporter correctement.
> **Les vingt-trois briques sont désormais éprouvées contre un vrai serveur
> éphémère** : `accessibleBy` (`tests/test_access_parties.py`), le filtrage de
> lecture d'`ownedBy` (`tests/test_lecture_privee.py`), le masquage `hidden`
> (`tests/test_masquage_hidden.py`, point 64), puis `generated`, `increments`,
> `decrements` et `categorized` (`tests/test_briques_comportement.py`,
> point 70), `payable` (`tests/test_paiement.py`, point 74 — avec son
> faux Stripe embarqué), `derivedFrom` (`tests/test_derivation.py`, point 77),
> la propriété transitive (`tests/test_propriete_transitive.py`, point 81),
> l'agrégation (`tests/test_agregation.py`, point 82 — même faux Stripe, pour
> vérifier le montant sur ce que le PRESTATAIRE reçoit), les assets
> (`tests/test_assets.py`, point 83), les contraintes de champ
> (`tests/test_contraintes_de_champ.py`, point 85), le décompte de stock
> (`tests/test_stock.py`, point 86) et l'horodatage
> (`tests/test_horodatage.py`, point 89 — dont un redémarrage sur base déjà
> peuplée, seul moyen d'éprouver la colonne qu'on ne rattrape pas) et la fiche
> obligatoire (`tests/test_fiche_obligatoire.py`, point 90 — avec DEUX comptes,
> sans quoi « existe-t-il au moins une fiche ? » passerait) et le verrou de
> paiement (`tests/test_verrou_paiement.py`, point 91 — les cinq portes fermées,
> ET la contre-épreuve des cinq écritures AVANT règlement, sans quoi un verrou
> qui figerait tout passerait pour bon), et le rattachement d'un jeu de
> démonstration (`tests/test_seed_parent.py`, point 100 — dont la base
> pré-peuplée d'identifiants divergents, seule façon de départager la résolution
> au démarrage d'un rang calculé à la compilation).
> Puis le rôle superviseur au-dessus d'`accessibleBy` (`tests/test_access_parties.py`,
> volet superviseur, point 106 — le modérateur voit/supprime tout, les parties
> restent dans leurs colonnes).
> Depuis le point 95, **aucune brique n'a plus la seule couverture de
> compilation** : `capability auth` était la dernière, ce qui était cohérent
> tant qu'elle ne produisait rien — elle
> compilation, ce qui était cohérent tant qu'elle ne produisait rien — elle
> contraint désormais la forme de l'identifiant de compte
> (`tests/test_identifiant_de_compte.py`). Toute NOUVELLE brique doit arriver
> avec son test contre serveur : la couverture de compilation, à elle seule, a
> laissé passer cinq briques pendant toute la vie du projet.

1. **`capability auth`** — la brique dormante s'est RÉVEILLÉE au point 95.
   Elle contraint la FORME de l'identifiant de compte :
   `capability auth` + `identifier: email, phone` (bloc indenté OPTIONNEL — une
   spec d'avant ce point compile à l'identique, et `None` ≠ `[]` : deviner
   « email par défaut » verrouillerait tous les projets existants).
   **La substance n'est pas la validation, c'est la NORMALISATION** : sans forme
   canonique, l'unicité se contourne en changeant une majuscule (deux comptes
   pour une personne) et la connexion échoue selon la façon dont on tape. Elle
   s'applique aux TROIS endroits — `/register`, `/login` et **`manage.py`**, le
   troisième étant celui qu'on oublie ; le contrôle de forme, lui, est
   volontairement absent de `manage.py` (rôles de service sans adresse). Le
   champ reste nommé `username` SUR LE FIL (le renommer casserait le formulaire
   de tout projet existant) : c'est le CONTRAT qui dit ce qu'il doit contenir.
   401 et jamais 422 à la connexion — un identifiant mal formé n'existe pas, et
   le dire apprendrait la règle à un attaquant. Ne convertit AUCUN compte
   existant : ils continuent de fonctionner et sont comptés au démarrage
   (comme au point 89). monl vérifie la forme, jamais qu'une boîte reçoit —
   donc pas de code de confirmation ni de mot de passe oublié par courriel,
   ce sont des briques qui commencent par « monl sait envoyer un message ».
   **Le vérificateur doit obéir à la règle qu'il fait appliquer** : le smoke
   test s'inscrivait sous 'smoke' en dur et récoltait 422 sur sa PROPRE
   inscription (`_identifiant_smoke`, smoke_test.py, dérive l'identifiant du
   contrat). **`phone_prefix: "+33"`** rend « 06… » et « +336… » canoniques : sans lui
   les deux notations sont deux comptes (limite ÉNONCÉE, avec son témoin —
   monl fait DÉCLARER ce qu'il ne peut pas savoir, comme `min` arme le stock au
   point 86). Éprouvée par `tests/test_identifiant_de_compte.py` (47 tests).
   Voir point 95.
   **POINT 138, deux corrections.** (a) Le **dialogue guidé ne posait jamais la
   question** : aucun des dix modèles ne déclarait d'identifiant, et tout projet
   né du dialogue acceptait `'!!!'` ou deux espaces comme identifiant de compte
   (constaté sur `projets/AtelierNaya`, atelier à Cotonou — des réservations
   qu'on ne peut honorer faute de pouvoir joindre personne, le point 90 par une
   autre porte). `_ask_account_identifier` la pose juste après
   `_ask_self_register`, et SEULEMENT si quelqu'un s'inscrit en ligne. C'est le
   symétrique du point 85 : là-bas une règle écrite ne produisait rien, ici une
   brique qui produit beaucoup n'était offerte à personne — **toute brique qui
   contraint une ENTRÉE doit être branchée au dialogue**, sinon elle ne protège
   que les specs écrites à la main. (b) **`phone_prefix` ne canonicalisait qu'un
   numéro commençant par `0`** — un préfixe interurbain européen, déduit du seul
   exemple `"+33"` qui avait servi à écrire la règle. Au Bénin le numéro s'écrit
   sans zéro de tête, donc `"+229"` ne produisait RIEN : inscrit en `97123456`,
   on récoltait 401 en se connectant en `+22997123456` (mesuré). L'indicatif
   s'applique désormais dès qu'il est déclaré ; le zéro de tête est retiré s'il
   existe, et un numéro déjà international tapé sans `+` n'est jamais préfixé
   deux fois (sinon le correctif fabriquait lui-même un troisième compte). Les
   DEUX fonctions — `runtime.py` et `admin_cli.py` — doivent rester identiques.
2. **`rule Entite.champ hidden`** — masque un champ de toutes les réponses
   de lecture (liste + détail), pour tout le monde. Reste en base, reste
   modifiable en écriture. Implémenté dans `src/parser.py` (`masking_rule`)
   et `src/generator/routes.py`. Couvert depuis le point 64 par
   `tests/test_masquage_hidden.py`, contre un vrai serveur : masquage en
   liste ET en détail, connecté comme anonyme, champ toujours écrivable et
   toujours en base (vérifié par lecture SQLite directe). Reste absent de
   tous les exemples — la couverture vient du test, pas d'une compilation.
3. **`rule Entite.Create decrements Entite.champ [by N]`** — décrémente un
   champ numérique sur une entité liée à la création d'un enregistrement
   (typiquement un signalement). Compilé par `exemples/03_reseau_social.ml`
   (`Report.Create decrements Member.reputation`).
4. **`rule Entite.Create increments Entite.champ [by N]`** — symétrique de
   `decrements`, pour les likes/appréciations. Grammaire : deux productions
   Lark nommées distinctes (`decrement_rule`/`increment_rule`), pas une seule
   règle partagée par mot-clé (évite le piège de filtrage Lark qui avait fait
   annuler le premier essai). `ast_validator.py` valide les deux dans la même
   boucle, chaque règle portant un champ `"direction"`. `generator.py` choisit
   `+`/`-` selon ce champ. Compilé par `exemples/03_reseau_social.ml` et
   `exemples/05_classement.ml`.
5. **`rule Entite.champ categorized: "label" below N, ..., "label" otherwise`**
   — remplace un champ `Integer`/`Float` par un libellé de catégorie dans
   toutes les réponses de lecture (liste + détail), sur le même principe que
   `hidden` mais avec substitution plutôt que suppression. Portée générale
   (n'importe quel champ numérique, pas seulement ceux ciblés par
   `increments`/`decrements`). Incompatible avec `hidden` sur le même champ
   (erreur de compilation explicite). Dernier palier obligatoirement
   `otherwise` (couverture totale garantie). Libellés injectés via `repr()`
   dans le code généré (jamais d'interpolation manuelle entre guillemets).
   Compilé par `exemples/03_reseau_social.ml` (`Post.likes` en peu /
   populaire / viral).

6. **Assemblage final : réseau social anonyme** — toutes les briques
   ci-dessus combinées dans une seule spec (aujourd'hui
   `exemples/03_reseau_social.ml`, héritier de `17_anon_social_network.yaml`),
   chacune dans son rôle le plus naturel plutôt qu'empilées sur la même
   entité (`Post` anonyme/public/catégorisé — auteur en pseudonyme
   `generated`, brique 7 ci-dessous — `Comment` identifié avec `ownedBy`).
   Deux bugs réels découverts en l'assemblant (pas en le
   relisant), tous deux résolus : un commentaire seul sur sa propre ligne
   entre deux blocs de premier niveau faisait planter la compilation
   (`Tree` non transformé) ; un commentaire seul À L'INTÉRIEUR d'un bloc
   indenté (`entity`/`workflow`...) faisait carrément échouer le parsing
   (`UnexpectedToken`). Corrigé à la racine dans `src/parser.py` :
   `parse_monl_string()` retire du texte source toute ligne qui n'est
   QUE du commentaire, avant même que Lark ne la voie — un seul correctif
   couvrant les deux cas, plutôt que 5 règles de grammaire à corriger
   séparément (entity/workflow/custom_block/ui_block/landing_block).
7. **`rule Entite.champ generated`** — retire un champ `String` du schéma
   Pydantic de la route `Create` de son entité ; le serveur le peuple seul
   avec un pseudonyme anonyme stable par compte (`Anon#3821`, généré une
   seule fois à `/register`, porté par le JWT comme `actor`/`user_id`).
   Ferme le trou du point 29 (`Post.author` en `String` libre, sans
   garantie d'intégrité). Incompatible avec `hidden` sur le même champ, et
   avec une action `Create` `public` sur la même entité (pas d'identité
   fiable dont dériver un pseudonyme). Compilé par
   `exemples/03_reseau_social.ml` (`Post.author`).

8. **`rule Entite.Action accessibleBy col1, col2`** — contrôle d'accès à
   deux parties (ou plus) : l'action n'est permise que si l'identifiant JWT
   de l'appelant apparaît dans l'une des colonnes listées (expéditeur via
   la FK de relation auto-peuplée, destinataire via un champ Integer
   déclaré). Liste filtrée par WHERE ... OR ..., détail/Update/Delete en
   403 pour les tiers. Au moins deux colonnes distinctes (sinon `ownedBy`),
   conflit bloquant avec `ownedBy`, `public` l'emporte. Ferme la brique
   « messagerie privée » évoquée dès la brique 1. Éprouvé contre un serveur
   réel éphémère par `tests/test_access_parties.py` (qui embarque sa propre
   spec), et compilé par `exemples/03_reseau_social.ml` (`PrivateMessage`).
   Voir point 31 de `docs/design_decisions.md`.

9. **`rule Entite.champ payable`** — la règle nomme le champ qui porte le
   MONTANT, donc l'entité qu'on encaisse. Ajoute deux colonnes de suivi
   (`payment_status`, `payment_ref`, jamais fournies par le client) et deux
   routes : `POST /entite/{id}/paiement` et `POST /paiement/webhook`.
   **Le montant vient de la BASE, jamais du corps de requête** — la route de
   règlement n'accepte aucun corps, et relit le champ à chaque appel. Sept
   refus à la compilation (entité ou champ inexistant, champ non numérique,
   cumul avec `hidden`, deux champs `payable` sur une entité, création
   `public`, et depuis le point 75 l'absence de relation entrante désignant un
   propriétaire — sans elle la route de règlement ne peut opposer de 403 à
   personne). Premier appel SORTANT d'un backend monl : secrets par
   l'environnement (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`), 503 en
   nommant la variable absente, et le reste du serveur intact — `monl run` et
   le smoke test restent verts hors ligne. Le webhook vérifie la signature du
   prestataire : c'est le SEUL endroit du backend généré où un tiers non
   authentifié écrit en base, ne jamais l'affaiblir ; la référence qu'il lit
   est qualifiée par le nom de l'entité (`'Order:42'`, point 75) pour qu'une
   app à plusieurs entités `payable` ne confonde jamais les id de deux tables.
   Éprouvé contre un serveur réel et un faux Stripe embarqué par
   `tests/test_paiement.py`, et compilé par `exemples/02_boutique.ml`
   (`Order.totalAmount`). Accessible depuis le dialogue guidé (`_ask_payable`,
   dès qu'un champ `Money` existe sur une entité possédée) depuis le point 75,
   pas seulement en écrivant la spec à la main. Voir points 74 et 75.

10. **`rule Entite.champ derivedFrom Entite.champ by champ`** — le champ nommé
    à gauche est CALCULÉ PAR LE SERVEUR depuis une ligne liée
    (`rule Order.total derivedFrom Product.price by quantity`), et disparaît des
    corps de requête — création ET modification, le schéma Pydantic étant unique
    par entité. Existe parce que `payable` relisait en base un montant que le
    client y avait écrit : **deux exploits prouvés** (POST avec `total: 0.01`,
    puis PUT sur une commande honnête), voir point 77. Treize refus à la
    compilation ; deux méritent d'être connus : le multiplicateur doit porter
    `required` (sinon calcul sur du vide), et la source ne peut pas être le
    propriétaire (sa FK vient du jeton, donc le client ne pourrait désigner
    aucune ligne). Le montant est **recalculé au PUT** — sans quoi la faille se
    déplace sur la quantité — depuis la FK **stockée**, jamais celle du corps de
    requête : la route Update de monl n'écrit pas les FK, donc calculer sur
    `data.<fk>` laissait facturer 89 € un article à 189 € (vérifié, les deux
    sens essayés). Éprouvée contre un serveur réel par
    `tests/test_derivation.py`. Voir points 77 et 78.
    **`payable` l'EXIGE désormais** (point 79, premier refus cassant du
    projet) : un montant que le client peut écrire fait échouer la compilation.
    Le raisonnement, à ne pas réouvrir — le créateur d'un enregistrement en est
    toujours le propriétaire (`populate_owner` écrit `current_user_id`), le
    propriétaire est le seul à pouvoir payer (403 sinon), donc un montant
    écrivable est un montant que le payeur fixe lui-même. Aucun cas légitime
    n'existe, pas même la facture émise par un admin : il en deviendrait
    propriétaire, et le client ne pourrait pas la régler.
    Le refus vit dans un recoupement APRÈS les deux boucles de validation (il
    lui faut les deux listes) ; les refus antérieurs de `payable` se
    déclenchent toujours avant lui.

11. **`rule Entite.Action ownedBy Entite`** — propriété **TRANSITIVE** : « cette
    ligne appartient à qui possède sa commande ». Aucune syntaxe nouvelle — c'est
    le refus du point 80 qui devient une brique, sous condition que la chaîne
    remonte à un acteur. Le renversement à comprendre : la colonne de propriété
    n'est plus déduite du jeton mais **fournie par le client**, donc elle doit
    être VÉRIFIÉE à la création (403, même réponse pour « n'existe pas » et « pas
    à vous » — les distinguer laisserait énumérer les commandes des autres). Le
    contrôle d'accès devient une jointure sur les quatre chemins : sous-requête
    `IN` en liste, remontée d'un cran en détail (404), jointure rendant l'id de
    COMPTE en Update/Delete — ce qui laisse la comparaison inchangée par rapport
    au cas direct. Quatre refus : intermédiaire sans propriétaire, chaîne à deux
    niveaux, intermédiaire ambigu, mélange direct+transitif. Un cinquième
    existait — `payable` sur une entité transitive — **levé au point 87** : il
    protégeait d'une comparaison fausse dans la route de règlement, pas d'une
    impossibilité de la brique, et cette route emploie désormais la même
    jointure qu'Update et Delete. Éprouvée contre un serveur réel par
    `tests/test_propriete_transitive.py`, avec des identifiants volontairement
    DIVERGENTS : le premier essai de la sonde du point 80 n'avait rien montré
    parce que « utilisateur 1 » et « commande 1 » coïncidaient. Voir point 81.

12. **`rule Entite.champ sumOf Entite.champ`** — le champ nommé est la SOMME d'un
    champ de toutes les lignes ENFANTS, recalculée par le serveur à chaque
    écriture de ligne. C'est ce que `derivedFrom` ne savait pas faire (il ne lit
    qu'UNE ligne liée), donc ce qui rend une commande à plusieurs articles
    chiffrable — et encaissable : `payable` accepte désormais un champ `sumOf`.
    **Recalculer, jamais ajuster** : un `total = total + x` se désynchronise dès
    qu'une écriture échoue et rien ne le rattrape ; la somme est relue depuis la
    table, avec `COALESCE` (panier vidé → 0, jamais NULL) et `ROUND` (une somme de
    flottants dérive, et c'est un montant). Trois branchements, et le troisième
    est celui qu'on oublie : création (dans LA MÊME transaction que l'insertion),
    modification (parent relu EN BASE, jamais `data.<fk>` — leçon du point 78),
    suppression (parent lu AVANT le DELETE, après quoi la clé étrangère a
    disparu). **Le refus qui porte la brique** : sommer un montant que le client
    écrit donne un total qu'il contrôle encore, en une addition de plus — la
    faille du point 77 par la porte du panier. Ce refus vit dans le recoupement
    avec `payable`, PAS dans la boucle `sumOf`, parce que sommer un champ client
    reste légitime hors paiement (`Commande.nbArticles sumOf Ligne.quantite`
    compte des articles, il n'encaisse rien) : c'est le cumul qui est fautif.
    Éprouvée contre un serveur réel ET un faux Stripe par
    `tests/test_agregation.py` — le montant est vérifié sur ce que le
    PRESTATAIRE reçoit. Compilée par `exemples/02_boutique.ml`, désormais un
    vrai panier. Voir point 82.

13. **`assets` + type `Image`** — les fichiers fournis par l'HUMAIN (photos,
    logo, favicon) déclarés dans la spec, et **vérifiés présents à la
    compilation**. Née d'une question d'ergonomie, arrivée ailleurs : trois
    chemins fautifs (fichier absent, dossier/extension mal tapés, `/etc/passwd`)
    compilaient tous en silence, et une image cassée ne se voit qu'à l'œil, en
    ligne. Deux familles de contrôles, séparées à dessein — de **forme** (chemin
    absolu, remontée `..`, URL distante sous `Image`) toujours actifs car purs ;
    d'**existence** seulement quand `base_dir` est connu, sinon le validateur se
    TAIT plutôt que de deviner. `Image` désigne un fichier LOCAL : une URL y est
    refusée parce que monl ne fait aucun appel réseau et ne pourrait rien en
    affirmer — `String` reste là pour l'adresse distante, non vérifiée.
    **Le dossier vit HORS de `frontend/`** : ce dossier-là est renommé par
    `monl frontend` et sa liste blanche exclut `.jpg`, donc les photos qu'on y
    déposait finissaient dans `frontend.precedent/` sans un mot — c'était le
    défaut le plus grave de la série. Le rôle `media` du contrat vient désormais
    du TYPE et non plus du nom (`MEDIA_HINTS` n'est qu'un repli).
    « Existe » n'est pas « servi » : le smoke test monte le projet avec le MÊME
    wrapper que `monl run` (via `serving.py`, feuille volontaire pour éviter le
    cycle cli↔smoke_test) et fait un vrai GET sur chaque asset. **Le montage des
    assets doit précéder celui de `/site`** — inversé, trois 404. Éprouvée par
    `tests/test_assets.py`, adoptée par `projets/SneakerLab`. Voir point 83.
    **Couche 2 (point 84) : `monl assets add <fichier> --for "Halo RS"`**, plus
    `--logo` / `--favicon` et `monl assets list`. Elle copie, renomme en slug,
    écrit la déclaration dans la spec — et fait REVALIDER le résultat par le vrai
    parseur et le vrai validateur avant de l'enregistrer : *l'outil écrit, le
    compilateur prouve*. Trois choses à ne pas défaire. **L'édition est
    TEXTUELLE** (`src/monl/assets_tool.py`), jamais un aller-retour parse →
    regénère : la spec d'un projet réel est plus qu'à moitié faite de
    commentaires, et ce sont eux qui expliquent les briques employées. **La
    revalidation se fait SANS `base_dir`**, l'existence de ce que l'outil écrit
    étant vérifiée à part via `resoudre_asset` — la première version validait
    tout avec `base_dir` et c'était un défaut à deux faces : `list` ne pouvait
    pas rapporter un asset manquant, et `add` était inutilisable sur une spec
    déclarant deux photos absentes. Leçon à retenir : **une garantie trop large
    n'est pas plus sûre, elle est fausse ailleurs.** Et **l'outil ne supprime
    rien, n'écrit aucun crédit, ne recompile pas** — l'orphelin est signalé,
    `monl update` reste le geste explicite. `resoudre_asset` /
    `candidats_asset` (ast_validator.py) sont la source UNIQUE de la résolution,
    partagée entre le refus du compilateur et le rapport de l'outil. Éprouvée par
    `tests/test_assets_tool.py` (33 tests) ; c'est elle qui a posé le logo et le
    favicon de `projets/SneakerLab`.

13bis. **Brique 26 (point 115) : `monl content export`/`import`** — remplacer
    en masse le contenu placeholder du dialogue guidé par du vrai texte et de
    vraies photos, sans toucher au DSL à la main. `export` écrit
    `content/<Entite>.csv` (une colonne par champ, moins ceux que le client ne
    peut jamais fournir — même exclusion que le schéma Create/Update) et
    `content/LISEZMOI.txt` ; `import` REMPLACE en entier le bloc `seed` de
    chaque entité depuis le CSV (pas de fusion ligne à ligne). Réutilise SANS
    LES RÉÉCRIRE la discipline du point 84 (`_valider`/`_revalider`,
    `_blocs_seed`, `_litteral`, `resoudre_asset`, importés depuis
    `assets_tool.py`). Une entité enfant de catalogue (brique 21) gagne une
    colonne `_parent` ; des blocs `seed` non contigus pour une même entité
    font refuser l'import plutôt que deviner où écrire. `src/monl/content_tool.py`,
    `tests/test_content_tool.py` (8 tests) — éprouvée aussi sur un vrai projet
    compilé (export → édition réelle du CSV et d'une photo → import → `monl
    update` → serveur réel).

14. **`required` / `unique` / `min` / `max` enfin appliqués** (point 85) — les
    quatre plus ANCIENNES règles du compilateur ne faisaient **rien** : sortie
    identique à l'octet avec ou sans elles, et référence fantôme acceptée en
    silence (`rule Colis.champFantome required` compilait). `exemples/02_boutique.ml`
    déclarait `rule Product.price min 0` et le serveur écrivait `price: -99` en
    base — dans une boutique où le prix se multiplie, se somme et part chez
    Stripe. Désormais : référence validée, `min`/`max` en contraintes Pydantic
    (422 avant tout INSERT ; longueur sur les types texte, valeur sur les types
    nombre — la portée est ÉCRITE, pas devinée), `unique` en **index unique**.
    Un INDEX et pas une contrainte de colonne : SQLite ne sait pas ajouter
    `UNIQUE` à une colonne existante, `CREATE UNIQUE INDEX IF NOT EXISTS` si —
    la migration additive du point 32 reste tenue, et une base déjà en doublon
    est NOMMÉE au démarrage sans empêcher le serveur de tourner. `required`
    reste une assertion (les schémas rendent déjà tout champ obligatoire), mais
    vérifiée. Deux pièges : le 409 avait déjà une cause (clé étrangère) et en a
    maintenant deux — le message distingue ; et **SQLite lève à l'`execute`, pas
    au `commit`**, une garde autour du seul commit donnait 500 au PUT en
    doublon. Éprouvée par `tests/test_contraintes_de_champ.py` (22 tests), dont
    celui qui exige que compiler AVEC et SANS ces règles donne des sorties
    différentes. Corrigé au passage : `payload.dict()` dans les blocs `custom`,
    déprécié en Pydantic v2 et **retiré en v3**. Voir point 85.

15. **`rule Entite.Create decrements Entite.champ by champ`** — décompter CE QUE
    LE CLIENT A DEMANDÉ, pas une constante. La boutique encaissait depuis le
    point 74 sans jamais toucher à son stock : cinquante paires sur douze, et on
    payait. **Le plancher n'est pas câblé** : la vérification de disponibilité
    s'arme depuis la déclaration `rule Product.stock min 0` (point 85), donc une
    réputation sans `min` continue de passer sous zéro, ce qui est son droit.
    UNE seule instruction SQL porte la condition et l'écriture (`... AND "stock"
    - ? >= ?` puis `rowcount == 0` → 409), dans la transaction de création : deux
    commandes simultanées ne peuvent pas lire le même stock. **Le bug à
    connaître** : la colonne visée est celle qui pointe vers l'entité
    DÉCRÉMENTÉE, pas la relation « propriétaire » — tant qu'une entité
    déclenchante n'avait qu'UNE relation entrante les deux coïncidaient, et
    `OrderLine` en a deux : le stock du produit portant l'id de la COMMANDE était
    décompté. Éprouvée par `tests/test_stock.py` (11 tests) et sur
    `projets/SneakerLab` en réel. **Le dialogue guidé produit désormais la
    chaîne entière** (panier, propriété transitive, `derivedFrom`, `sumOf`,
    `min`, décompte, `payable`) : il en restait à la forme mono-article du
    point 77. Voir point 86.
    **TROIS branchements, pas un** (point 92) : création, modification
    (point 91), et **suppression** — le troisième est celui qu'on oublie. Il a
    manqué six points durant : vider son panier laissait le stock à 9 sur 12 sur
    `projets/SneakerLab`, pendant que le total du parent, lui, redescendait bien
    à zéro (le point 82 avait NOMMÉ ce piège pour l'agrégation, et la leçon n'a
    pas traversé jusqu'à la brique suivante). La restitution **ne porte aucun
    plancher** — elle rétablit un état qui a existé et qui était valide, et un
    garde-fou y interdirait d'annuler une commande. Quantité et clé étrangère
    sont relues EN BASE **avant** le `DELETE` : après, plus rien ne dit quoi
    rendre ni à qui. Ne répare pas les unités déjà perdues.

16. **`rule Entite.champ timestamp`** — l'instant de CRÉATION, écrit par le
    serveur en ISO 8601 UTC et jamais ensuite. Le champ doit être `DateTime` et
    disparaît des corps de requête, création ET modification : une date qu'on se
    donne à soi-même n'atteste de rien. Née du back-office du point 88 — un
    carnet de commandes sans date ne dit ni ce qui est récent, ni dans quel ordre
    honorer. **Trois décisions à ne pas rouvrir.** `Date` est REFUSÉ, en
    l'expliquant : tronquer au jour perdrait une information que le serveur
    possède et rendrait deux enregistrements du même jour inordonnables. La
    **milliseconde** n'est pas du zèle : à la seconde, deux commandes passées
    coup sur coup portaient la même date, et le tri annoncé par le contrat
    devenait faux exactement quand un carnet en a besoin. Et **les
    enregistrements antérieurs restent à `NULL`** : la migration additive
    (point 32) rattrape une colonne, jamais son contenu ; un `DEFAULT
    CURRENT_TIMESTAMP` daterait d'aujourd'hui les commandes d'avant-hier — une
    base qui MENT, pire qu'une case vide. Le serveur les COMPTE et les nomme au
    démarrage, et le contrat dit à l'IA d'afficher un tiret. Aucun refus de cumul
    n'a été écrit : `generated` veut du `String`, `derivedFrom`/`sumOf`/`payable`
    du numérique — le refus de type tombe avant, et un refus inatteignable ferait
    croire à une protection. `required`/`min`/`max` sont hérités du recoupement
    du point 85 sans une ligne de plus. Éprouvée par `tests/test_horodatage.py`
    (20 tests), compilée par `exemples/02_boutique.ml`, adoptée par
    `projets/SneakerLab`, et **émise par le dialogue guidé sans aucune question**
    (la seule réponse utile serait « oui »). Voir point 89.

17. **`rule Entite.Create requiresOwn Entite`** — l'appelant doit DÉJÀ posséder
    un enregistrement de l'entité nommée pour créer celui-ci. Née d'un constat
    en base sur `projets/SneakerLab` : deux commandes réelles portaient un compte
    SANS aucune fiche client, et `_monl_users` n'est exposé par aucune route —
    donc des commandes que le back-office ne pouvait attribuer à personne,
    c'est-à-dire **inexpédiables**. La voie écartée mérite d'être connue :
    exposer le login du compte aurait donné un nom sans adresse, et entamé la
    promesse du pseudonyme `generated` (brique 7). **Trois décisions.** La
    vérification est la TOUTE PREMIÈRE requête de la route — un appelant sans
    fiche n'apprend rien du catalogue et ne consomme aucun stock (placée après un
    `decrements`, elle laisserait décompter avant de refuser). **409 et non
    403** : un état à corriger, pas un droit qui manque, et le message dit quoi
    créer. La fiche se cherche par identifiant de COMPTE via
    `_identity_fk_columns` (point 88) — un `WHERE id = ?` trouverait celle d'un
    autre dès que les deux id divergent. Seule `Create` peut l'exiger : ailleurs
    l'enregistrement existe déjà. **Le piège du test** : « existe-t-il au moins
    une fiche ? » passe tant qu'on n'emploie qu'UN compte. Éprouvée par
    `tests/test_fiche_obligatoire.py` (17 tests), adoptée par
    `projets/SneakerLab`. Ne répare pas l'existant. Voir point 90.

18. **Le verrou de l'enregistrement payé** — aucune syntaxe nouvelle : c'est
    `payable` (brique 9) qui FIGE désormais les écritures, dès que
    `payment_status` vaut `payee`. Mesuré sur `projets/SneakerLab` avant d'écrire
    une ligne : une commande réglée 89 € acceptait une paire à 149 €, le total
    remontait à 238 € et le back-office affichait « Payée » en face d'un montant
    que personne n'avait réglé. La faille du point 77 par la porte que les
    points 77 à 82 n'avaient pas regardée — non plus « quel montant le client
    peut-il écrire », mais **« pendant combien de temps »**.
    **Cinq portes, pas deux** : verrouiller la seule commande n'aurait rien servi,
    le total ne se modifie pas par elle mais par la LIGNE. Le verrou vit donc là
    où le total se recalcule — `_payment_locked_parents` (generator/core.py) est
    le pendant exact de `_aggregation_recomputes`, ne pas réécrire la chaîne
    ailleurs. **409 et non 403** (un état définitif, pas un droit qui manque ; le
    message renvoie au remboursement), et le parent est relu EN BASE en
    `Update`/`Delete` depuis la clé étrangère STOCKÉE — leçon du point 78, pour la
    troisième fois. La garde vient AVANT tout calcul et tout décompte : placée
    après, un refus aurait déjà consommé du stock.
    **Le contrat le porte** (`payment_locked` + note) et le delta de
    `monl update` le rapporte — quatrième forme de l'angle mort des points 88 à
    90. Deux pièges y vivent : la note n'avait été posée que sur `Update` et
    `Delete`, laissant une IA dessiner « + Ajouter un article » sur une commande
    payée ; et la CRÉATION se verrouille par un PARENT réglé, jamais par l'entité
    payable elle-même (`inclure_soi=False` dans `_verrou_paiement`) — sinon le
    bouton « Commander » disparaît. La route de règlement lit aussi
    `payment_status` pour refuser un second paiement : ce n'est PAS ce verrou, sa
    propre note le dit déjà, et le test de non-divergence les distingue par le
    message de `_payment_lock_lines`. Éprouvée par
    `tests/test_verrou_paiement.py` (15 tests, vrai serveur + faux Stripe) et
    quatre tests de contrat dans `tests/test_orchestrator.py`. Compilée par
    `exemples/02_boutique.ml`. Voir point 91.

19. **`rule Entite.champ oneOf "a", "b", …`** — une valeur PARMI UNE LISTE.
    Nommée « la prochaine brique évidente » aux points 91 et 92 : sur une
    commande NON réglée, le client posait `status: "livrée"` et le serveur
    l'acceptait — il se déclarait livré tout seul. **`Literal` plutôt qu'un
    motif** : 422 AVANT tout INSERT (même place que les bornes du point 85), la
    liste sort dans le schéma OpenAPI donc dans `/docs`, et le message d'erreur
    ÉNUMÈRE les valeurs permises. **Types TEXTE seulement** — pour un nombre,
    `min`/`max` et `categorized` disent déjà cela, et une troisième façon
    d'exprimer la même contrainte finirait par en contredire une autre. Cinq
    refus : champ inexistant, champ numérique, une seule valeur, valeur vide,
    doublon, cumul avec `generated`. L'ORDRE déclaré est conservé (sur un statut
    c'est le cycle de vie). Le contrat porte `allowed_values` et le brief dit
    **MENU DÉROULANT** : sans ça l'IA dessine un champ texte. Éprouvée par
    `tests/test_valeur_parmi_une_liste.py` (24 tests), compilée par
    `projets/SneakerLab`. Voir point 96.

20. **`rule Entite.champ "valeur" releases Entite`** — atteindre une VALEUR
    défait un effet. Annuler une commande la passait en « annulée » en gardant
    ses lignes : le stock restait consommé. Supprimer les lignes le rendait
    (point 92) mais effaçait la trace — un marchand veut les deux. **Ne rendre
    QU'UNE FOIS** : l'état est lu avant l'écriture, la libération n'a lieu qu'à
    la TRANSITION (deux PUT rendraient sinon deux fois). **L'état libéré est
    TERMINAL** : réactiver laisserait une commande vivante sans rien avoir
    consommé — du stock gratuit, famille du point 77 ; et le reprendre
    supposerait qu'il soit encore disponible. Exige `oneOf` sur le champ, sans
    quoi une faute de frappe donnerait une règle qui ne se déclenche jamais.
    Aucun refus de cumul avec le verrou du point 91 : une commande réglée
    refuse déjà tout Update, un refus inatteignable ferait croire à une
    protection. Éprouvée par `tests/test_liberation.py` (16 tests), adoptée par
    `projets/SneakerLab`. Voir point 98.

21. **`seed Enfant for Parent.champ "valeur"`** — un jeu de démonstration peut
    RATTACHER un enfant. Née du point 99 : la clé étrangère d'une entité fille
    d'une table métier était devenue honnête, mais un `seed` n'accepte que des
    champs DÉCLARÉS et une colonne de rattachement n'en est pas un — une boutique
    à variantes s'ouvrait donc sur un catalogue dont rien n'était commandable.
    **Désigner par une VALEUR, jamais par un rang** : un numéro ne se lit pas et
    se décale à la première insertion ; c'est déjà le choix de
    `monl assets add --for "Halo RS"` (point 84), même phrase dans le code.
    **La résolution se fait au DÉMARRAGE**, par un `SELECT` sur le parent : un
    `id` figé à la compilation supposerait que le parent vient d'être semé, or le
    socle ne sème que dans une table VIDE — sur une base déjà peuplée, le rang
    désignerait la mauvaise ligne (`test_le_rattachement_suit_lid_reel_pas_le_rang`
    le départage). Sept refus, dont l'AMBIGUÏTÉ (deux lignes portant la valeur →
    vitrine non déterministe), la valeur que personne ne porte, un parent ACTEUR
    (sa colonne porte un id de COMPTE, point 99 — et aucun compte n'existe au
    démarrage), et l'ORDRE (un parent semé après son enfant est refusé, jamais
    réordonné en silence). Éprouvée par `tests/test_seed_parent.py` (15 tests),
    compilée par `exemples/02_boutique.ml` — qui gagne au passage son entité
    `Variant` (le produit est ce qu'on MONTRE, la variante ce qu'on VEND) et
    ferme le trou de corpus qui avait laissé passer les points 99 et 100.
    **Contrainte inattendue** : `assets_tool.py` lit les blocs `seed`
    TEXTUELLEMENT — sa regex a dû apprendre la nouvelle forme, sinon il sautait
    le bloc en silence. Voir point 100.

22. **`rule Entite.champ numbered "CMD-{YYYY}-{NNNN}"`** — le numéro que
    l'humain lit et dicte, attribué par le serveur à la création et jamais
    ensuite. Même famille que `timestamp` : absent des corps de requête,
    création ET modification. Née du point 101 : `Order.reference` était un
    `UUID`, donc une chaîne que le CLIENT écrivait — personne ne dicte un UUID au
    téléphone. **Le compteur vit dans une table SYSTÈME** (`_monl_sequences`,
    clé primaire `(entite, champ, periode)`) et jamais dans un `MAX(...) + 1` sur
    la table métier, qui redonnerait le numéro d'un enregistrement SUPPRIMÉ —
    deux factures, une référence. C'est la PÉRIODE qui fait repartir la séquence
    (année, mois ou jour selon les jalons du gabarit ; `''` = séquence globale).
    **L'attribution vit DANS la transaction de création** : hors d'elle, une
    insertion refusée laisserait le compteur avancé. **L'index unique est créé
    sans qu'on déclare `unique`** — faire dépendre cette garantie d'une ligne
    qu'on peut oublier rouvrirait la porte du point 85. Six refus, dont le
    gabarit sans séquence (tous les enregistrements porteraient le même numéro)
    et le mois sans année (`CMD-03-0001` revient chaque mars — l'index unique
    l'attraperait un an plus tard). Le mot-clé n'est PAS `reference` : il se
    confondrait avec le nom du champ. Les enregistrements antérieurs restent
    sans numéro et sont comptés au démarrage (point 89, mot pour mot). Éprouvée
    par `tests/test_numerotation.py` (24 tests), compilée par
    `exemples/02_boutique.ml`. Voir point 102.

23. **Rôle superviseur au-dessus d'`accessibleBy`** — un `sharedBy` porté sur la
    MÊME référence qu'une action régie par `accessibleBy` nomme les rôles qui
    transpercent le contrôle par colonnes : ils listent, lisent, modifient et
    suppriment TOUS les enregistrements, quand les parties restent confinées
    aux leurs. C'est le pendant exact du superviseur déjà acquis pour `ownedBy`
    au point 88 (`rule X.Update sharedBy Proprietaire, Patron`). L'action
    `accessibleBy` devient **exempte de CRITICAL_COLLISION** (miroir d'`ownedBy`) :
    plusieurs rôles peuvent légitimement viser la même route, chacun restant
    cantonné soit à ses messages, soit à tout — s'il est déclaré superviseur.
    Éprouvé contre un vrai serveur éphémère par `tests/test_access_parties.py`
    (volet superviseur, serveur + Sessions) et compilé par
    `exemples/03_reseau_social.ml` (`Moderator`). Voir point 106.

27. **`rule Entite.Read publicWhen champ "valeur"`** — une lecture publique
    SOUS CONDITION : la liste est filtrée et le détail répond 404 tant que le
    champ ne porte pas la valeur. Appliqué côté API, jamais côté frontend — un
    contenu modéré ne doit pas rester lisible par son URL. **Deux exemptions,
    toutes deux DÉCLARATIVES** (point 116) : le SUPERVISEUR nommé par un
    `sharedBy` sur la même référence — même mot-clé et même sens qu'aux
    points 88 et 106 — et le PROPRIÉTAIRE par sa colonne d'identité
    (point 99), qui retrouve toujours les siens. Sans elles, la brique cachait
    le contenu À TOUT LE MONDE : le modérateur qui venait de masquer un post ne
    pouvait plus ni le lister ni le rouvrir, et l'auteur perdait son brouillon
    — une modération à sens unique, trouvée contre un vrai serveur et pas en
    relisant. Un rôle simplement connecté reste soumis à la condition : sinon
    « masqué » ne voudrait plus rien dire dès qu'on a un compte.
    **`get_optional_identity` ne peut que DONNER des droits** — un jeton absent,
    invalide ou révoqué laisse anonyme, et une route publique ne répond jamais
    401 ; elle n'est émise que si une exemption existe
    (`_condition_exemptions`, generator/core.py, source unique partagée par la
    route et le runtime). Éprouvée par
    `tests/test_publication_conditionnelle.py` (10 tests, TROIS comptes — avec
    un seul, « le contenu masqué est-il caché ? » passerait même caché à tous),
    compilée par `exemples/03_reseau_social.ml`. Voir point 116.

28. **`rule Entite.Create oncePer Parent, Parent`** — un compte n'agit qu'UNE
    fois par cible (un like par post, un vote par entrée). L'unicité tient à un
    **index composite SQLite**, jamais à une vérification applicative : c'est
    lui qui protège aussi deux requêtes concurrentes, et les colonnes viennent
    des relations, jamais d'une empreinte fournie par le client.
    **Le piège qui a coûté le plus** (point 116) : un index sur une colonne que
    la route Create n'écrit JAMAIS ne refuse rien — SQLite tient deux NULL pour
    distincts. La colonne visée par un `increments` sort de l'INSERT quand elle
    est la PREMIÈRE relation entrante (`_client_fk_columns` tranche sur
    `_get_incoming_relation`, pas sur `_decrement_fk_column`) : `oncePer Member,
    Post` laissait liker dix fois. Bug d'ORDRE, donc invisible sur la spec qui
    l'a fait naître. La génération REFUSE désormais ce cas en nommant la
    relation à déplacer — refuser plutôt que produire une règle sans effet, mot
    pour mot le point 85. **La cause profonde est FERMÉE au point 117** :
    `_counter_fk_columns` (generator/core.py) dérive la colonne de
    `_decrement_fk_column` pour CHAQUE règle, et `_client_fk_columns`,
    `schemas.py` et `routes.py` la lisent tous les trois — la colonne est
    écrite exactement une fois, jamais zéro. Le refus reste actif, mais
    seulement pour une colonne réellement jamais écrite. Le 409 d'`oncePer` et celui
    d'`unique` se distinguent sur les COLONNES nommées par SQLite, sinon le
    premier volait la phrase du second (défaut du point 85, rouvert).
    Éprouvée par `tests/test_unicite_composite.py` (8 tests, DEUX comptes et
    DEUX cibles), compilée par `exemples/03_reseau_social.ml`. Voir point 116.

29. **Tout fichier local RÉCLAMÉ par le frontend doit être servi** — aucune
    syntaxe nouvelle : le smoke test demande en HTTP réel chaque référence
    locale du HTML et du CSS, et un 404 fait échouer en nommant la page, la
    référence et l'URL. Née de `projets/AtelierNaya`, construit par DeepSeek
    pour 48 roubles : six SVG référencés, aucun livré, et `monl run --check`
    au VERT des deux côtés. **Rien ne l'avait vu parce qu'un fichier absent ne
    lève aucune exception** — jsdom reçoit le 404 et continue, comme un vrai
    navigateur. C'est la forme de preuve du point 83 (*« existe » n'est pas
    « servi »*) appliquée non plus aux assets DÉCLARÉS mais à ce que l'IA a
    écrit ; le manifeste du point 136 ne la rend pas inutile (vérifié en
    exécutant : ses sections sont vides sur AtelierNaya, il décrit ce que le
    contrat prévoit, pas ce que l'IA invente). **La limite est ÉNONCÉE** : seules
    les références portant une extension connue sont retenues, pour ne jamais
    confondre un fichier avec une route (`/item`) ou une navigation (`#/panier`)
    — le point 92 avait déjà vu cet avertissement dénoncer quatre routes
    correctes. Une référence enracinée (`/photo.svg`) n'est PAS réécrite vers
    `/site/` : c'est un vrai défaut, et le réécrire le masquerait. **Deux
    hypothèses fausses corrigées par le test** : `StaticFiles` sert TOUT le
    dossier `frontend/` (une image posée à la main marche), et la liste blanche
    gouverne ce que l'IA a le droit de LIVRER, pas ce que le serveur rend ; la
    vraie voie silencieuse est `monl import`, qui RETIRE de l'archive ce qui
    n'est pas en liste blanche. Éprouvée par `tests/test_fichiers_reclames.py`
    (12 tests) et sur AtelierNaya, copie intacte VERTE contre copie amputée
    ROUGE. Voir point 137.
30. **`landing … link "Libellé": "adresse"`** — le pied de page est EXIGÉ, et
    ses destinations sont DÉCLARÉES. Le plancher de substance (point 143)
    comptait quatre sections et s'arrêtait au-dessus du pied de page : tous les
    sites produits sortaient avec deux mots gris, aucun réseau, aucun contact —
    le dernier endroit où un site se dénonce comme une maquette, et le seul que
    la vérification ne regardait pas. **monl ne peut pas DEVINER une adresse**
    (une adresse inventée mène chez quelqu'un d'autre, pire que rien) : même
    impasse qu'au point 83 pour les images et qu'au point 86 pour le stock,
    donc même issue — il fait DÉCLARER ce qu'il ne peut pas savoir, puis il
    l'exige. Forme PLATE et ordre conservé, mot pour mot `section` (point 55)
    et `question` (point 94). **L'adresse doit porter un schéma** — `https://`,
    `http://`, `mailto:` ou `tel:` — sans quoi « instagram.com/atelier » est lu
    comme un chemin RELATIF et mène à une page inexistante du site lui-même :
    un lien qui ne marche pas est pire qu'un lien absent, parce qu'il se voit.
    Sont refusés aussi le libellé vide, l'adresse vide, deux libellés
    identiques et deux fois la même adresse. **Ce que monl ne vérifie PAS, et
    le dit** : qu'une adresse RÉPONDE — aucun appel réseau, même frontière
    qu'au point 83. Ce qu'il vérifie, c'est que l'adresse déclarée figure
    réellement dans le site LIVRÉ, et la comparaison porte sur l'ADRESSE et
    jamais sur le libellé (un libellé se reformule, une adresse non). Le pied
    de page n'exige PAS de titre : lui en imposer un ferait écrire « Pied de
    page » en gros, ce qu'aucun site réel ne fait — l'invariant du manifeste
    est donc « aucune règle vide », pas « un titre partout ».
    **TROIS producteurs, sans quoi la brique n'existe pas** (point 146, qui est
    le point 85 sous un autre jour) : le dialogue guidé (`_ask_footer_links`,
    cinq entrées proposées), les dix modèles, et la console web de la
    plateforme. Le mode express ne pose rien — c'est sa raison d'être, ses
    liens viennent de l'appelant (`express_links`). **Compléter n'est pas
    deviner** : la complétion n'a lieu que là où il n'existe qu'UNE lecture, et
    ce qui reste incompris est écarté EN LE DISANT (frontière du point 105). Le
    téléphone est traité AVANT le refus des espaces, « +33 6 12 34 56 78 » étant
    la façon dont un numéro s'écrit. `adresse_de_lien` (`dialogue_engine.py`)
    est la source unique côté Python ; la console en a une copie JavaScript
    puisqu'elle valide dans le navigateur, et **l'accord des deux est
    VÉRIFIÉ** — deux mises en œuvre d'une même règle divergent toujours.
    Éprouvée par `tests/test_liens_de_pied.py` (10 tests) et
    `tests/test_liens_pied_de_page.py` (5 tests). Voir points 144 et 146.

### Briques suivantes déjà évoquées, non cadrées
- Le **panier multi-articles est terminé** : ses trois briques cadrées au
  point 80 sont faites (11 = propriété transitive et clé étrangère cliente sur le
  parent propriétaire, 12 = agrégation). (FERMÉ au point 107 : la chaîne de
  propriété remonte désormais toute la profondeur jusqu'à un acteur — brique 24 ;
  cycle, cul-de-sac et maillon ambigu restent refusés.) `payable` sur une entité
  possédée transitivement, lui, est ACQUIS depuis le point 87.
- (FERMÉ au point 96 : le statut en texte libre, par la brique 19 `oneOf`.)
- **Le stock PAR VARIANTE est acquis** (points 99 et 100) — le modèle `Product
  hasMany Variant` (stock, prix et décompte portés par la variante) ne demande
  AUCUNE syntaxe nouvelle, et `exemples/02_boutique.ml` le compile désormais avec
  une vitrine réellement remplie. Il était hors de portée pour deux raisons
  distinctes, toutes deux corrigées : le rattachement fantôme (99) et
  l'impossibilité de semer un enfant (100). **Reste ouvert et purement produit** :
  l'appliquer à `projets/SneakerLab`, qui est une décision de MIGRATION plus que
  de spec — les `OrderLine` existantes visent des produits, `Product.stock` perdrait
  son sens, et la migration additive ne rattrape jamais un contenu (points 89 et
  99). (FERMÉ au point 113 sur `exemples/02_boutique.ml` ET `projets/
  SneakerLab` : `writableAfterPayment` adopté — statut d'expédition sur les
  deux, `trackingNumber` en plus sur SneakerLab, éprouvé par un vrai smoke
  test `monl run --check`.)
  (FERMÉ au point 102 : la référence de commande lisible, par la brique 22
  `numbered` — `exemples/02_boutique.ml` délivre `CMD-2026-0001`,
  `projets/SneakerLab` délivre `SL-2026-0001`. Les deux l'ont déjà adopté.)
- **(historique) Un statut restait un texte libre** (point 91) — sur une commande NON réglée, le
  client pose `status: "livrée"` et le serveur l'accepte : il n'existe aucune
  brique « valeur parmi une liste ». Le verrou de la brique 18 ne couvre l'entité
  qu'une fois l'encaissement fait. C'est la prochaine brique évidente de la série
  du panier, et elle n'est pas écrite. Hors de portée et assumés dans la même
  série : les frais de port et la TVA (le total est la somme des lignes, rien
  d'autre — décision produit, pas défaut du compilateur) et tout envoi de
  courriel.
- **Attribution VISIBLE exigée par une licence** — reste à trancher (point 83).
  C'est un comportement (un texte doit être sur la page), donc vérifiable par le
  smoke test, contrairement à la véracité d'un nom d'auteur. Règle retenue :
  **monl vérifie la complétude, jamais la véracité** ; `CREDITS.json` reste une
  convention de projet, et `monl assets add` se borne à signaler qu'un fichier
  n'y figure pas (point 84).
- (FERMÉ au point 103 : le dry-run du delta, par `monl diff`.)
- (FERMÉ : `monl run --check` signale les artefacts produits par un compilateur
  antérieur. La détection compare à une RÉGÉNÉRATION et non à un numéro de
  version — `__version__` n'avait pas bougé pendant les points 74 à 81, un
  tampon n'aurait rien vu. Avertissement et non erreur : bloquer immobiliserait
  tout projet après n'importe quelle évolution du compilateur. `cli.py:263`,
  test dans `tests/test_orchestrator.py`.)
- **Le filtrage et le tri sur les routes de liste** — `limit`/`offset`
  seulement. « Les commandes à expédier » se fait donc côté navigateur, ce qui
  passe à l'échelle d'un SneakerLab et pas au-delà. Volontairement gardé pour
  APRÈS la page d'administration : on décidera sur ce qui coince vraiment. Le
  risque à surveiller est de dériver vers un langage de requête, ce que ce
  fichier refuse. Le tri, lui, est déjà possible sans rien ajouter depuis le
  point 89 — un horodatage se trie comme du texte.
- (FERMÉ au point 86 : le décompte du stock par un champ, et la vérification
  de disponibilité qu'il exige.)
- (FERMÉ au point 89 : la date de création, née du back-office du point 88.)

### Hors de portée, assumé et documenté
- Algorithme de recommandation basé sur les likes — moteur de scoring/ML,
  pas un compilateur déclaratif.
- (Le mode `template` de l'ancienne landing n'existe plus : tout le
  frontend généré par monl a été retiré au point 41.)

## Quatre gestes sur un site en marche, et lequel choisir

- **`monl diff`** (point 103) — la question de `monl update`, posée SANS rien
  écrire. Compile dans un dossier temporaire, imprime le MÊME rapport
  (`_rapporter_delta` est partagé — deux calculs de delta divergeraient, et
  c'est le calcul que six points ont eu du mal à tenir juste), et s'en va.
  Aucun fichier du projet n'est touché, contrat de référence compris.
- **`monl update`** — la SPEC a changé. Recompile et rapporte le delta du
  contrat (routes, champs, accès, lecture seule, préalables, verrous, contenu,
  rattachements).
- **`monl retouche "<ce qui cloche>"`** (point 93) — la spec n'a PAS changé, le
  site est juste au regard du contrat, mais quelque chose cloche à l'œil.
  Corrige sans reconstruire, sauvegarde dans `frontend.precedent/`, et **échoue
  si l'IA ne change rien** (sur une retouche, ne rien faire est la demande non
  traitée — pas un état neutre comme au point 73).
- **`monl frontend`** — reconstruire depuis le contrat. Le geste le plus lourd :
  un tirage non déterministe dont on peut perdre ce qu'on aimait.

Le piège à connaître : **un défaut d'affichage n'est pas toujours un défaut de
frontend.** La FAQ de SneakerLab sortait collée parce que la SPEC tenait quatre
questions dans une chaîne (point 94) — une retouche l'aurait fait deviner à
l'IA, et la structure se serait reperdue à la reconstruction suivante. La
consigne de retouche dit désormais de SIGNALER ce cas plutôt que de le
contourner. Avant de retoucher : le contenu dit-il vraiment ce qu'on veut voir ?

## Repères utiles dans le code

- Depuis le point 65, tout le code vit dans le paquet `src/monl/` :
  les imports internes sont RELATIFS (`from .parser import …`) et les tests
  importent `monl.xxx` sans manipuler `sys.path` (voir `tests/conftest.py`).
  `src/monl/generator/` est un sous-package depuis la bêta 3 (l'ancien module de 1 307
  lignes a été découpé ; depuis le point 155, `routes.py` et `runtime.py` sont
  eux aussi des familles de mixins — `routes_*.py` et `runtime_*.py` — et
  `frontend_contract`, `smoke_test`, `cli`, `dialogue_engine`, `assets_tool`,
  `design_system`, `validation_pipeline` sont des paquets) : `core.py` (état issu de l'AST, orchestration,
  `_compute_route_map`), `runtime.py` (socle du app.py généré : secret,
  `_connect`, init/migrations/seed, register/login/logout, quota),
  `routes.py` (une route par couple action/entité + contrôle d'accès),
  `schemas.py`, `sql_schema.py`, `sandbox.py`, `admin_cli.py`
  (manage.py). La classe est recomposée par mixins dans `core.py` : une
  nouvelle brique de génération s'ajoute dans le module de sa couche, pas
  dans `core.py`. `from generator import MonlSecureGenerator` reste l'import
  public.
- Un champ peuplé par le SERVEUR (`generated`, `derivedFrom`, `sumOf`,
  `timestamp`) doit être exclu de la route `Update` autant que du schéma
  d'entrée (point 78). `update_<entite>`
  lisait `data.<champ>` pour TOUS les attributs : toute entité combinant
  `generated` et `Update` répondait **500** (`AttributeError`), défaut latent
  depuis le point 30 parce qu'aucun exemple ne combinait les deux. Leçon
  générale : **neuf briques testées une par une ne testent pas leurs paires.**
- `ownedBy` désigne un **acteur** (propriété directe) ou une **entité qui remonte
  à un acteur** (propriété transitive, brique 11 / point 81). Ce qui reste
  interdit : une chaîne qui n'aboutit à aucun compte. Nommer une entité
  compilait en silence jusqu'au point 80 et produisait un rattachement faux —
  défaut le plus grave de la série 77-80, parce qu'il touchait une brique
  présente depuis les premières versions et contredisait la promesse affichée
  par le README.
  **La règle de conception à retenir** : une clé étrangère que le CLIENT fournit
  doit être validée à l'écriture ; une clé étrangère déduite du jeton n'a rien à
  valider. La propriété transitive fait passer la colonne de propriété du second
  cas au premier — c'est tout l'enjeu de la brique, et la raison du contrôle à la
  création (sans lui elle ouvrirait un trou plus large que celui qu'elle ferme).
  Source unique : `_transitive_chain()` et `_owner_lookup_sql()` dans
  generator/core.py — ne pas réécrire la jointure ailleurs. `_owner_lookup_sql()`
  a au passage fusionné les blocs Update et Delete de routes.py, qui étaient
  identiques et qu'il fallait donc corriger deux fois.
- **POINT 108 : tout le SQL de contrôle d'accès passe par `generator/sql.py`,
  la frontière d'émission typée.** Une valeur n'entre dans une requête que par
  `sql.bind()` (→ `?` + paramètre lié) ; `sql.ident()` pour un identifiant,
  `sql.kw()` pour du SQL fixe (qui refuse un `?`). Il n'existe AUCUNE API pour
  coller une valeur dans le texte — c'est la classe de défaut du point 107
  rendue impossible. Ne jamais reconstruire une requête de contrôle d'accès par
  f-string : passer par cette couche. Éprouvée par `tests/test_sql_emission.py`,
  dont un garde-fou qui interdit le motif du point 107 sur le code généré, ET par
  `tests/test_invariants_securite.py` qui étend ce garde-fou à TOUTES les specs du
  dépôt (AST sur l'app.py généré : aucune valeur client dans un littéral SQL).
- **POINT 109 : le modèle de contrôle d'accès (côté validateur) vit dans
  `_valider_controle_dacces()` (ast_validator.py), pas éparpillé dans
  `_validate_structures`.** Y vivent : `ownedBy` (propriété directe), la
  résolution de la chaîne transitive (briques 11 et 24), `accessibleBy` et le
  superviseur (brique 23). C'est là qu'on ajoute ou relit un refus d'accès —
  jamais en le glissant ailleurs dans le fourre-tout. Le bloc n'utilise que
  `self.*` (la matrice de collision et `shared_permissions` restent dans
  `_validate_structures`). Avec le point 108 (émission SQL typée), les deux
  versants de la sécurité — décision et émission — sont désormais des frontières
  nommées.
- **POINT 140 : `uvicorn_server` (tests/support/server.py) ÉCHOUE, il ne saute
  plus.** Il convertissait la mort d'un serveur en `pytest.skip`, donc les
  vingt et un fichiers d'intégration qui passent par lui pouvaient ne rien
  vérifier en rendant du vert — mesuré : `992 passed, 17 skipped`, code de
  sortie 0, dont un `serveur uvicorn arrêté (code 1)` que personne ne lisait.
  La socket est désormais liée par le parent et PASSÉE à l'enfant
  (`uvicorn --fd` + `pass_fds`) : le port ne redevient jamais libre entre le
  choix et l'écoute, donc la collision est impossible plutôt que retentée
  (retenter aurait masqué une panne déterministe). La sortie d'uvicorn ne part
  plus dans `DEVNULL`, elle est dans le message d'échec. **`free_port` reste
  racé et sa docstring le dit** — une vingtaine de fichiers l'appellent encore,
  mais eux échouent franchement. Le piège à connaître, mesuré en écrivant le
  témoin : un `Skipped` levé dans un `pytest.raises` fait SAUTER le test qui
  l'entoure — d'où `echec_attendu()` dans `tests/test_support_serveur.py`, qui
  attrape les deux issues séparément. **Ce que le correctif a trouvé dès sa
  première exécution** : `test_uploads.py` ne s'exécutait plus sur la machine
  du mainteneur (`python-multipart` absent — pourtant DÉCLARÉ dans
  `pyproject.toml`), et rendait du vert. Un saut ne dit pas « rien à vérifier
  ici », il dit « je n'ai pas vérifié ».
- **POINT 141 : la plateforme est exploitable — pages légales, suppression de
  compte, journal, sauvegarde, purge périodique.** Cinq manques qui n'étaient
  pas des défauts de code, mais des choses inexistantes. Trois règles à ne pas
  défaire. **`legal.py` n'invente RIEN** : `EDITEUR` et `CONTACT` portent un
  marqueur `[À COMPLÉTER]` visible dans la page servie, gardé par un test —
  fabriquer une mention légale plausible produirait un faux document. **La
  liste des données conservées est confrontée au schéma SQLite réel** : une
  table qui garde de la donnée et que la page ne nomme pas fait échouer la
  suite (une politique désynchronisée est pire qu'absente, elle AFFIRME).
  **`journal.py` ne PEUT PAS écrire un secret** — masquage par le NOM du champ
  ET par la FORME de la valeur, même logique que la frontière SQL du point 108 ;
  le nom d'événement y est positionnel uniquement (`/`), sans quoi un champ
  `nom=` levait un `TypeError` pile quand on veut journaliser. `_purger` est la
  source UNIQUE appelée au démarrage et dans la boucle, et le fil vit dans le
  `lifespan`, jamais dans `create_app`.
  **CE QUE LA DOCUMENTATION A TROUVÉ.** Écrire la procédure de restauration a
  révélé que **`with sqlite3.connect(...)` ne FERME pas** : l'objet `Connection`
  prend part à des cycles de références, donc il n'est rendu qu'au ramasse-miettes
  cyclique. Mesuré : 500 lectures → **197 descripteurs ouverts**, base à 4 096
  octets avec 111 Ko de WAL à côté, et la restauration qui échouait sur un
  `disk I/O error`. `IdentityStore._connect` est désormais un gestionnaire de
  contexte qui ferme (197 → 0). Ne pas le refaire rendre une connexion nue.
  **Un document se garde comme du code** : deux tests confrontent
  `docs/EXPLOITATION.md` au code (variables d'environnement, événements
  journalisés) dans les DEUX sens — une variable tue ne se réglera pas, une
  variable documentée mais ignorée se réglera pour rien. Voir point 141.
  **LE JOURNAL MASQUAIT LE COMPTE**, trouvé en lançant le serveur une fois les
  vingt-cinq tests au vert : un `uuid4().hex` fait 32 caractères, donc
  `FORMES_SENSIBLES` l'avalait et toutes les lignes disaient
  `compte=[masqué]` — étanche et inutile. Le remède ne touche PAS au masquage
  (exempter des noms de champs rouvrirait le trou) : `journal.court()` tronque
  à huit caractères ce qu'on lui PASSE, et un test relit `app.py` pour
  qu'aucun identifiant n'y soit journalisé nu. Voir point 141.
- **POINT 142 : les deux falaises produit sont fermées — codes de secours, et
  `monl-platform admin`.** Ni des défauts de code ni des manques
  d'exploitation : des situations où le service, en marchant exactement comme
  prévu, faisait perdre tout son travail à quelqu'un.
  **Un mot de passe perdu emportait le compte et ses projets.** Huit codes de
  secours remis UNE fois à l'inscription — le contrat déjà passé pour les clés
  d'API, pas une promesse de plus. « On vous envoie un lien » est la voie
  ÉCARTÉE : elle commencerait par « monl sait envoyer un message », et la
  politique de confidentialité promet le contraire. Trois choses à ne pas
  défaire : le code est consommé DANS la transaction du changement de mot de
  passe (sinon une écriture ratée brûle une chance sur huit pour rien) ;
  toutes les sessions tombent (sinon la reprise ne sert à rien dans le seul cas
  qui compte) ; régénérer REMPLACE (on régénère parce qu'on craint une fuite).
  Reprise bornée à 5 essais/heure/IP, refus unique — 401 — pour code faux,
  adresse inconnue et mot de passe invalide. Comptes antérieurs COMPTÉS, pas
  convertis (point 89). Quatre documents devenaient faux d'un coup ; deux
  l'ont dit eux-mêmes par leurs tests.
  **Aucun rôle administrateur** : tout passait par `sqlite3`, serveur arrêté.
  `monl-platform admin` (src/monl_platform/administration.py) donne huit
  verbes. **Le panneau web est la voie écartée et c'est le cœur de la
  décision** : il demanderait sa propre authentification et une colonne de
  privilège, et deviendrait la cible dont une faille donne tous les comptes —
  or qui possède le shell possède déjà la base. Un test lit `/openapi.json` et
  échoue si une route d'administration apparaît. `expirer` marque échu sans
  effacer (la purge nettoie : deux chemins de suppression finiraient par
  diverger) ; `prolonger` compte depuis MAINTENANT, jamais depuis l'ancienne
  date. Tout geste qui écrit est journalisé.
  **Les tests vérifient l'EFFET, jamais l'affichage** — clé révoquée rejouée
  contre le serveur MCP, codes régénérés réellement présentés à
  `/api/auth/recover`. Une commande qui imprime « clé révoquée » sans que la
  clé cesse de fonctionner serait pire qu'absente : on la croirait faite.
  **Au passage** : `--garder N` range les sauvegardes (le tri est sur la DATE,
  jamais sur le nom), le compose embarque un service compagnon de sauvegarde
  sur volume séparé, et la barrière de couverture a retrouvé sa portée
  déclarée — `--cov=src/monl` et non `--cov=src`, la plateforme étant rapportée
  sans être barrée. Voir point 142.
- **POINT 157 : le logo est celui au « o » orange, et une mesure peut mentir
  de trois façons.** `outils/vectoriser_logo.py` sépare DEUX couches (anneau
  orange, lettres crème), toutes deux en `evenodd` ; `brand.py` reste sans une
  seule couleur et `theme.ORANGE` est la source unique, lue par l'outil qui
  fabrique les images ET par le test qui vérifie qu'elles n'ont pas dérivé.
  **Les trois pièges de mesure, tous éprouvés** : une vérification qui empile
  les sous-chemins au lieu de les combiner en OU EXCLUSIF mesure sa propre
  erreur (8,08 % annoncés pour 0,49 % réels) ; une classification « couleur la
  plus proche » range le bord antialiasé d'une lettre claire du côté de
  l'orange, d'où un liseré sur chaque lettre (séparer sur la SATURATION, avec
  des seuils DÉRIVÉS des couleurs relevées) ; et **Lanczos invente des pixels
  saturés** par dépassement aux bords francs — 52 morceaux au lieu de 4, contre
  4 en bilinéaire. L'ICÔNE est le « o » entier et jamais l'anneau seul (les
  lettres recouvrent l'anneau dans l'artwork, donc la couche isolée porte leurs
  encoches) ; les deux tracés partagent UNE transformation, séparée par une
  barre verticale et surtout pas par une espace. L'orange ne suit AUCUN thème
  (5,67:1 en sombre, 2,94:1 en clair — WCAG exempte les logotypes, et ce sont
  les lettres qui portent la lecture à 12,89:1). Les TROIS artefacts raster
  sortent du même outil : `outils/fabriquer_images.py`. Voir point 157.
- **POINT 156 : le volet Navigateur masqué ne recalcule PAS le style — il
  mesure la géométrie, jamais la cascade.** Un style posé EN LIGNE n'y change
  pas `getComputedStyle` ; un clone lit la même couleur avec et sans la classe
  qu'on lui ajoute. Trois sondages y ont « prouvé » des choses fausses, dont
  l'absence d'anneau de focus sur les onze types interactifs (un `.focus()`
  scripté ne déclenche pas `:focus-visible` — mesurés ensuite à 6,52:1 au pire
  en clair, 7,5:1 en sombre, soit très au-dessus des 3:1 de WCAG 2.2). **Toute
  question de cascade se tranche donc hors du navigateur** : `_specificite()`
  (tests/test_platform_landing.py) calcule le poids des deux sélecteurs et
  exige que celui qui cède le fond soit plus fort ET écrit après. Le repère des
  onglets (`case-repere`) est POSÉ par le script, jamais servi dans le balisage
  — sinon il s'affiche dans l'angle chez qui n'exécute pas le script. Et la
  bascule de thème tient le refus du mouvement en JAVASCRIPT : le bloc
  `@media (prefers-reduced-motion)` porte sur `*`, qui n'atteint aucun
  `::view-transition-*` ; la même garde couvre l'absence de l'API.
  **Un commentaire CSS est du CONTENU de page** — écrire « ci-dessus » dans la
  feuille inlinée a fait tomber un test de la page de confidentialité.
  Voir point 156.
- **POINT 158 : la coloration des specs DÉRIVE de la grammaire, et l'or n'a
  plus qu'un emploi.** `src/monl_platform/coloration.py` rend la coloration au
  SERVEUR (aucun JavaScript, aucune dépendance) et **n'écrit aucun mot-clé** :
  les tables viennent des terminaux de `monl.parser.grammaire.grammar`, donc
  une brique neuve est colorée le jour où elle entre dans la grammaire.
  `_terminal()` ÉCHOUE plutôt que de rendre un ensemble vide — une coloration
  qui manque ne ressemble pas à une panne. L'échappement se fait par FRAGMENT :
  échapper d'abord ferait voir `&quot;` au motif de chaîne, qui ne
  reconnaîtrait plus rien. Avant ce point il n'existait que `.kw` et `.cm`,
  écrites à la main dans les gabarits : c'est pour ça que l'or marquait tout
  mot-clé de toute spec, sur onze blocs.
  **La règle de palette a TROIS axes, et le contraste entre deux jetons n'en
  est pas un** : WCAG parle du FOND (4,5:1, seuil du TEXTE — du code se lit).
  Deux jetons sont distincts s'ils diffèrent en teinte (≥ 35°, les deux ayant
  une chroma utilisable), OU en clarté (≥ 1,35:1), OU en franchise (≥ 40 de
  chroma). Ne pas employer la saturation HSV : un pastel est peu saturé par
  construction, et le vert des types comme le violet des noms se voyaient
  traités comme des gris. Gardé par `tests/test_platform_coloration.py`, dont
  les contre-épreuves rejouent les deux défauts mesurés (noms en crème à
  1,06:1 de l'encre ; rose et olive à 32° de l'or).
  **Les surtitres de section sont retirés** — le seul `.eyebrow` qui survit est
  « Erreur 404 », où le surtitre EST le titre.
  **Le volet Navigateur masqué ment aussi sur le DÉFILEMENT** (point 156
  élargi) : `scrollTop` reste à 0 quoi qu'on fasse, parce qu'une page qui ne
  composite pas ne défile pas. `html { overflow-x: clip }` ne bloque RIEN — un
  A/B en iframes le prouve (500 avec, sans, et avec `hidden`). Isoler la
  variable, jamais lire la valeur.
  **L'ANCIENNE ICÔNE REVENAIT DU CACHE, pas du serveur** : l'octet servi était
  le bon, mais `/favicon.ico` est une adresse qui ne change jamais et les deux
  routes répondaient `max-age=86400`. Les `<link rel="icon">` portent
  maintenant une empreinte du CONTENU (`?v=3cf62446`) — pas un numéro à la
  main, qui aurait le même défaut le jour où on oublie de l'incrémenter
  (point 85 transposé au cache). `cache_icone` (theme.py) est la source unique
  des deux politiques : versionnée un an et `immutable`, NUE cinq minutes —
  l'adresse nue est celle que le navigateur demande d'office sans lire la page,
  donc la seule qu'on ne peut pas versionner. Voir point 158.
- **POINT 158bis : Pillow n'était que dans l'extra `ai`, et la CI installe
  `.[dev,postgres]`.** Trois exécutions rouges pendant que la suite était verte
  en local. Le correctif a découvert pire : un
  `pytest.importorskip("PIL.Image")` faisait SAUTER le test de réencodage JPEG
  à chaque exécution de la CI depuis qu'il existe — on ne l'a su que parce
  qu'un test voisin échouait franchement. Pillow entre dans `dev`,
  l'`importorskip` disparaît, et deux témoins de `tests/test_architecture.py`
  gardent la paire : **aucun `importorskip` dans `tests/`** (détecté par AST) et
  **les bibliothèques dont les tests dépendent sont déclarées là où la CI les
  installe**. Les `pytest.skip` conditionnels restent permis — ils gardent une
  intégration qu'on peut légitimement ne pas demander (un vrai PostgreSQL) et
  ils la NOMMENT ; une bibliothèque Python installable, non. **Toute
  bibliothèque qu'un test importe se déclare dans `dev`, jamais dans un extra
  que la CI n'installe pas.** Voir point 158.
- **POINT 158ter : un test d'image compare les PIXELS, jamais les octets.**
  `test_les_images_raster_ne_derivent_pas_de_la_marque` comparait les fichiers
  octet pour octet : vert en local, rouge sur les trois versions de Python de
  la CI. Un `.ico` et un `.png` portent des pixels COMPRESSÉS, et le même
  Pillow 12.3 lié à des zlib différents n'écrit pas la même suite d'octets pour
  la même image — le test mesurait l'ENCODEUR et pas le DESSIN. Le décodage,
  lui, est sans perte : la comparaison porte sur les pixels de toutes les
  tailles de l'ICO. Contre-épreuve franche — décaler l'orange d'UN point fait
  tomber le test. **Même leçon que la palette et que la ligne de commande :
  une mesure peut porter sur autre chose que ce qu'on croit mesurer.**
  Voir point 158.
- **POINT 161 : la CI avait DEUX `-q`, donc ses sauts ne se voyaient pas.**
  `pyproject.toml` pose `addopts = "-q"` et chaque commande de `ci.yml` en
  posait un second : `-qq` supprime la ligne de décompte ET la section de
  résumé. Un saut n'apparaissait plus que comme un `s` au milieu de 1 377
  points — c'est ainsi que le saut de Pillow a vécu dans cette CI depuis
  toujours. Le `-q` redondant est retiré, `-rs` NOMME chaque saut avec son
  motif (compter ne suffit pas : « 2 skipped » ne dit pas lesquels).
  **La garantie est gardée par un test** — `tests/test_ci_les_sauts_se_voient.py`
  refuse toute commande qui repose `-q` ou qui n'emporte pas `-rs`, avec un
  témoin sur la prémisse (`addopts` porte-t-il encore `-q` ?) et un témoin sur
  l'EXTRACTEUR, sans quoi une fonction qui ne trouve rien rendrait les deux
  règles vertes en ne regardant rien. Piège de lecture YAML : `--cov=…`
  commence par un tiret comme un élément de liste — c'est le tiret SUIVI D'UNE
  ESPACE qui ouvre une liste, et sans cette distinction la commande repliée
  `>-` est coupée en son milieu. Faire ÉCHOUER sur un saut est une décision
  SÉPARÉE, volontairement non prise. Voir point 161.
- **POINT 159 : un test qui dépend d'une horloge FIXE son instant de référence,
  puis ne la relit plus.** L'assertion de rejeu TOTP de
  `tests/test_authentification_b4.py` RECALCULAIT le code au lieu de rejouer
  celui déjà employé : à chaque bascule de la fenêtre de 30 s elle envoyait un
  code NEUF, jamais consommé, que le serveur acceptait à juste titre (`assert
  200 == 401` en CI). Le pas est arrêté une fois (`_pas_totp_stable`), et
  `_totp_code(secret, step)` n'a plus de défaut — déduire le pas dans le helper
  est exactement ce qui laissait passer le défaut. **Le moteur affiché n'était
  pas la cause** : la bascule forcée rougit sur les DEUX moteurs, `[postgres]`
  n'était qu'un tirage d'ordonnancement. **Et sa voisine ne mordait plus** : la
  fenêtre précédente était éprouvée APRÈS la connexion valide, donc refusée par
  l'anti-rejeu de celle-ci — une tolérance de ±1 fenêtre donnée au serveur
  laissait le test VERT. Déplacée avant, elle rougit. Point 145 mot pour mot.
  Voir point 159.
- **POINT 163 : « servi » n'est pas « exécutable » — deux pages étaient mortes
  et 1373 tests verts ne le disaient pas.** Dans une chaîne Python NON BRUTE,
  `\\'` vaut `'` : écrire `'…Démarrer l\\'API…'` dans un gabarit émet une
  apostrophe NUE au milieu d'un littéral JavaScript, le navigateur lève
  `SyntaxError` et **tout le script de la page cesse de s'exécuter**. Deux
  occurrences — `/console`, et **`/account` cassée sur `main` depuis `bc01b40`
  (26/08/2026)**, le commit même qui donne les codes de secours du point 142 :
  la page où l'on récupère un compte perdu n'avait jamais exécuté une ligne de
  JavaScript.
  **Pourquoi rien ne l'a vu** : les tests de page CHERCHENT DES CHAÎNES dans le
  HTML servi, ce qu'une page morte contient tout aussi bien — et l'assertion
  `"Démarrer l'API" in response.text` visait la forme NUE, donc elle passait
  *exactement parce que* la page était cassée. `tests/test_console_javascript.py`
  extrait le script de ce que la ROUTE rend — jamais de la constante du module,
  c'est ENTRE LES DEUX que l'échappement se perd — et le passe à `node --check`
  sur les six pages qui en portent. Node est déclaré dans `ci.yml` et son
  absence fait ÉCHOUER, jamais sauter (point 140).
  **Le dialogue guidé de la console** repose sur le REJEU : le moteur étant
  entièrement déterministe, on le relance depuis le début avec un `ask` qui
  dépile les réponses connues — donc **serveur sans état**, et **aucune règle
  du dialogue en JavaScript** (point 146). Le piège : le moteur retente TROIS
  fois avant de lever, et une réponse refusée qui reste dans la liste brûle une
  tentative pour toujours — trois fautes de frappe et le dialogue mourait, 48
  réponses perdues. `soumettre` rejoue avant/après et ne retient la réponse que
  si la question a AVANCÉ (quand le moteur refuse, il redemande le MÊME texte) ;
  la réponse HTTP porte la liste FAISANT AUTORITÉ. Voir point 163.
- **POINT 162 : la plateforme ne construit plus d'interface — et retirer une
  fonctionnalité se prouve comme on prouve une brique.** Partis :
  `builder.py`, `worker.py`, `seed_ai.py`, `progress.py`, `revisions.py`,
  `quota.py`, `store_builds.py`, la file de constructions, `/api/usage` et les
  huit paramètres d'IA de `create_app`. Restent la compilation
  (`compilation.py` : `compiler_le_projet`, déterministe, isolée) et
  l'hébergement.
  **CE QUE LE RETRAIT A TROUVÉ, et qu'aucune relecture n'aurait donné.**
  (a) **L'hébergement ne pouvait plus jamais démarrer** : `start_project`
  exigeait un build `reussie` et servait son SNAPSHOT — sans constructeur, la
  porte restait close à jamais. Il sert désormais le dossier COMPILÉ, et le
  frontend devient FACULTATIF (le wrapper `serve.py` le disait déjà :
  « l'API répond, /site renverra 404 »). `SiteNotBuiltError` →
  `SiteNotCompiledError`, qui NOMME le fichier absent : sinon uvicorn meurt sur
  un dossier vide et l'erreur parle de démarrage, jamais de compilation.
  (b) **Aucun test n'exerçait `start_project`** — la seule couverture portait
  sur l'ADRESSAGE. Le couplage pouvait être cassé sans qu'une ligne rougisse ;
  d'où `tests/test_platform_hebergement.py` (vrai processus, vrai HTTP) et sa
  contre-épreuve qui remet la porte du build.
  (c) **`seed_ai.py` n'avait AUCUN appelant dans `src/`** (vérifié par
  `git grep` au commit précédent) : le point 151 décrit une brique que rien ne
  branchait, et deux fichiers de tests suffisaient à la faire paraître vivante.
  Point 146 pour la deuxième fois.
  **`compiler_dans` (service.py) est la source UNIQUE de la décision
  d'isolation** — deux lectures de `MONL_ISOLATE_COMPILES` divergeraient sur la
  seule barrière qui empêche une spec fournie de s'exécuter dans
  l'interpréteur de la plateforme. La table `builds` et son garde-fou
  survivent pour les bases ANTÉRIEURES, et c'est écrit à côté d'eux : sur une
  base neuve ils ne refusent plus rien. La console : « Créer et lancer la
  construction » → « Démarrer l'API » (`/compiler` puis `/start`).
  Voir point 162.
- **POINT 162bis : la boucle MCP est fermée, et une borne exprimée par une
  liste de noms cesse de borner en silence.** Sept outils désormais —
  `monl_list_projects`, `monl_diff_spec` et `monl_update_backend` s'ajoutent
  aux quatre existants — et **l'archive s'ouvre à la clé MCP**
  (`_require_user_ou_cle`, app_http.py : session PUIS clé, pour qu'un en-tête
  `Authorization` traînant ne l'emporte jamais sur qui est connecté ; même
  `api_key_user` que `/mcp`, même `_require_project` derrière ; 404 et jamais
  403 pour la clé valide d'un autre compte). Le delta n'est PAS recalculé :
  `_contract_signature` reste la source unique, `evolution.py` la lit pour DEUX
  contrats. `recompiler` produit le nouveau dossier EN ENTIER avant de toucher
  à l'ancien — une spec refusée laisse le projet intact — et l'identifiant
  comme l'adresse de téléchargement SURVIVENT.
  **LE PIÈGE** : `MONL_MAX_CONCURRENT_COMPILES` était armé par une égalité sur
  le seul `monl_compile_backend`. Les deux outils neufs compilent aussi ; les
  oublier laissait la borne intacte à la lecture et contournée à l'exécution
  (`OUTILS_QUI_COMPILENT`). **Toute borne exprimée par une liste de noms doit
  être relue quand un nom s'ajoute.**
  **La contre-épreuve a reproduit l'angle mort des points 88 à 119 en direct** :
  aveuglé sur tout sauf les ROUTES, le delta déclarait « interface inchangée »
  pour un champ ajouté avec son `oneOf`. Éprouvé par
  `tests/test_platform_mcp_boucle.py` — un agent compile, liste, télécharge le
  ZIP, mesure et recompile sans jamais ouvrir de session. Voir point 162.
- **POINT 160 : un seuil de temps en SECONDES ne veut pas dire la même chose
  sur deux machines.** Le test d'oracle temporel de `test_authentification_b4`
  comparait l'écart entre le chemin « compte verrouillé » et le chemin
  « compte inexistant » à 0,10 s fixe : la CI de `main` est tombée à 0,1016 s.
  Deux défauts, à séparer avant de toucher au seuil. **L'ESTIMATEUR** — la
  médiane de CINQ écarts appariés monte à 9,70 ms sur un blocage isolé, celle
  de QUINZE reste sous 1,54 ms (`TOURS_MESURE`). **L'ÉCHELLE** — la tolérance
  est désormais une PART du temps de réponse observé (20 %, plancher 5 ms),
  parce que ce qui compte pour un attaquant est le SIGNAL sur le BRUIT, pas un
  nombre de millisecondes. **Une différence RÉELLE subsiste** : le chemin
  verrouillé coûte 1,7 ms de plus, dans 19 mesures sur 24 ; ce n'est PAS un
  biais d'ordre (vérifié en inversant l'ordre dans chaque paire : +1,81 contre
  +1,63 ms). Le test la BORNE, il n'exige pas zéro. **Contre-épreuve
  obligatoire, et c'est elle qui distingue un seuil corrigé d'un seuil
  désarmé** : une vraie fuite injectée dans le serveur généré est refusée à
  20 ms (19,83 mesurées pour 16,45 de tolérance), pas à 10 — soit cinq fois
  plus fin que les 100 ms d'avant. Voir point 160.
- **POINT 155 : aucun fichier de `src/` ne dépasse 400 lignes, aucune fonction
  non plus — et c'est VÉRIFIÉ.** `tests/test_architecture.py` porte trois
  contrats : `PLAFOND_FICHIER`, `PLAFOND_FONCTION`, et **une exception doit
  encore servir** (un fichier redevenu court, ou disparu, fait échouer). Les
  deux seules exceptions sont des LITTÉRAUX de données et portent chacune leur
  raison : `app_templates.py` (les dix modèles) et `parser/grammaire.py` (la
  grammaire Lark, qui est UNE chaîne). Ne pas en ajouter sans raison écrite —
  c'est la même discipline que les exceptions de `ruff` dans `pyproject.toml`.
  Le plafond ne porte pas sur `tests/`, et c'est délibéré (un fichier de test
  est une suite de cas, pas une pièce dont la complexité croît).
  **Deux disciplines à ne pas réapprendre en cassant** : une découpe se donne
  en INDEX D'INSTRUCTION et jamais en numéros de ligne (un numéro tombe au
  milieu d'un `if`), et les coupes s'appliquent du BAS vers le HAUT (couper en
  haut décale tout ce qui suit, en silence).
  **Et deux pièges de Python** : `import a.b as a` lie le SOUS-MODULE — trois
  tests de migration sont tombés sur « module 'importlib.util' has no attribute
  'util' » ; et un `monkeypatch` vise le module où la fonction lit son global
  (`monl.cli.construction.publish_files`), jamais le paquet — ré-exporter le
  nom ferait passer le `setattr` sans atteindre l'appel, soit un test vert qui
  ne vérifie plus rien (point 153). Voir point 155.
- **POINT 110 : le parseur Lark est mis en cache** (`_get_parser`, parser.py) —
  construit une fois, pas à chaque `parse_monl_string`. La construction (~50 ms)
  dominait le parsing ; en cache, 0,4 ms/parse, et la suite est passée de ~344 s
  à ~200 s. Né d'un spike Rust (écarté) : la question « quel langage pour aller
  plus vite » s'est résolue en une ligne de Python. Ne pas reconstruire le
  parseur ailleurs. Voir point 110.
- **POINT 111 : `public` et `requiresOwn`+`payable` vivent aussi dans des
  méthodes nommées** — `_valider_regle_public()` et
  `_valider_requires_own_et_payable()` (ast_validator.py). Suite de 108-109 :
  `_validate_structures` ne porte plus AUCUNE règle de contrôle d'accès ou de
  visibilité anonyme.
- **POINT 112 : `restrictedTo` (point 2) exige désormais une entité, un champ
  et un acteur déclarés** — `_valider_regle_restrictedTo()`. Avant, une faute
  de frappe désactivait la restriction sans le moindre avertissement ;
  l'audit `[SECURITY_AUDIT]` reste un AVERTISSEMENT (inchangé depuis le point
  2), seule l'existence des références citées est désormais vérifiée à la
  compilation.
- **POINT 113 : le verrou de paiement (point 91) bloque TOUS les acteurs,
  superviseur compris — vérifié contre un vrai serveur.** Pour faire avancer
  un champ après paiement (ex. le statut d'expédition), utiliser
  `rule Entite.champ writableAfterPayment Acteur` : route dédiée
  `PUT /entite/{id}/apres-paiement`, réservée à l'acteur nommé (jamais le
  propriétaire), sans toucher au verrou générique d'`Update` qui reste
  absolu. Ne PAS ajouter d'exception d'acteur dans `_payment_lock_lines` —
  c'est la voie explicitement écartée.
- Un rôle n'est inscriptible que s'il porte `selfRegister` dans la spec
  (bêta 3). Toute évolution touchant `/register`, le contrat frontend ou le
  smoke test doit conserver cette frontière : c'est elle qui empêche un
  client anonyme de s'attribuer un rôle privilégié. Chemin légitime pour les
  autres rôles : le `manage.py` généré.
- `_compute_route_map` (generator/core.py) : source unique de vérité pour le
  regroupement des routes, partagée entre la génération FastAPI et le
  contrat frontend (src/frontend_contract.py) — ne pas dupliquer cette
  logique ailleurs. Un test (tests/test_orchestrator.py) confronte le
  contrat aux décorateurs réellement écrits dans app.py.
- Le contrat doit décrire ce que le backend fait VRAIMENT, pas seulement ce que
  la spec déclare — y compris quand une brique RETIRE la possibilité d'écrire
  un champ, pas seulement quand elle ajoute une colonne (point 79 : le défaut
  du point 76 s'est reproduit sur `derivedFrom`, la brique née pour le
  corriger). Tout champ peuplé par le serveur doit sortir des
  `request_fields`, via `server_generated`.
- **POINT 99 : « peuplée depuis l'identité » exige que le parent soit un ACTEUR.**
  `_identity_fk_columns` écartait la création publique, la cible d'un compteur et
  la propriété transitive — mais retenait n'importe quelle relation entrante pour
  le reste. Une entité fille d'une table MÉTIER (`relation Produit hasMany
  Variante`) recevait donc `current_user_id` dans `produit_id`, déclarée
  `REFERENCES _monl_users` : **la variante était rattachée au vendeur, jamais à
  son produit**, et le client ne pouvait en désigner aucun. Défaut du point 80 par
  l'autre bout, invisible en vingt briques parce qu'**aucun exemple du dépôt
  n'écrit un enfant de table métier** (les cinq compilent des enfants d'acteurs).
  Le choix ne dépend plus de l'ordre des relations : seuls les parents acteurs
  sont candidats, `ownedBy` tranche entre eux. `populate_owner` (routes.py) LIT
  désormais ce helper au lieu de recalculer les mêmes conditions à côté.
  **Le corollaire à ne pas oublier** : `payable` perdait ici une sécurité
  ACCIDENTELLE — la route de règlement comparait la colonne de propriété à
  l'appelant, et ça ne marchait que parce que la colonne recevait
  `current_user_id` faute de mieux. D'où un refus (parent acteur ou chaîne
  transitive obligatoires) et une ERREUR DE GÉNÉRATION si la colonne de compte
  manque : mieux vaut un compilateur qui s'arrête qu'une route de paiement sans
  contrôle d'accès. Éprouvé par `tests/test_rattachement.py` (18 tests, dont 11
  échouent sans la correction). Voir point 99.
- **POINT 144 : le pied de page est exigé, et ses liens sont DÉCLARÉS.**
  `landing` accepte `link "Libellé": "adresse"` (répétable, ordre conservé) ;
  l'adresse doit porter un schéma — `https://`, `http://`, `mailto:`, `tel:` —
  sans quoi le navigateur la lit comme un chemin RELATIF du site lui-même.
  monl ne vérifie PAS qu'une adresse répond (aucun appel réseau, même frontière
  qu'au point 83) mais il vérifie qu'elle FIGURE dans le site livré
  (`_declared_link_errors`, frontend_ai.py), en comparant l'ADRESSE et jamais le
  libellé. Le pied de page est la seule section obligatoire SANS titre exigé :
  lui en imposer un ferait écrire « Pied de page » en gros. Ne JAMAIS inventer
  un réseau social absent de la spec — c'est écrit dans le brief, et c'est la
  raison d'être de la brique.
- **POINT 143 : un marqueur nomme une section, il ne prouve pas qu'elle
  contient quelque chose.** `src/monl/section_substance.py` mesure la MATIÈRE
  (titre, texte lisible, action, formulaire) ; les seuils sont PAR SECTION et
  voyagent dans `ASSET_MANIFEST.json` sous `section_substance`, donc un projet
  compilé par une version antérieure reste accepté. Deux pièges de mesure, tous
  deux éprouvés : le corps d'un `<script>` ne compte pas, et la pile du parseur
  porte le NOM de la balise — un `<p>` jamais refermé est du HTML5 légal, et
  sans ça une section avale le texte de sa voisine et la barrière ne refuse
  plus rien. Ne JAMAIS exiger de données en dur dans un `catalogue` : ses
  lignes viennent de l'API, et les réclamer ferait inventer des produits.
  Le plancher de sections vit dans `select_ui_patterns` (`ui_patterns.py`) —
  `hero`, la matière (catalogue/workspace/booking), `trust`, `closing-cta` —
  et la matière de `trust` vient de `_guarantees()` (design_system.py), donc du
  CONTRAT et jamais de l'imagination. Mesuré sur les 10 modèles du catalogue
  par le vrai chemin de dialogue : minimum 4, médiane 7, maximum 10.
- POINT 88 : une clé étrangère référence l'une de DEUX choses — le registre des
  COMPTES (`_monl_users`) quand la route Create la peuple depuis le jeton, l'`id`
  d'une table métier sinon. `_identity_fk_columns` (core.py) tranche ; le contrat
  le PORTE désormais (`references_account` + la note qui dit de joindre par la
  colonne HOMONYME, jamais par l'`id`). Sans ça, une page d'administration
  affiche le bon nom sur le premier enregistrement et rien sur les suivants —
  une jointure qui marche à moitié. Un test confronte le contrat aux
  `REFERENCES` réellement écrits dans schema.sql.
- **L'ANGLE MORT DU DELTA, HUIT fois** (points 88, 89, 90, 91, 94, 99, puis DEUX
  fois au point 116) : `publicWhen` et `oncePer` vivaient dans `business_rules`,
  que la signature ne lisait pas — une lecture devenait filtrée par un état, une
  création gagnait un 409, et `monl update` répondait « aucun changement
  d'interface ». Les deux briques ont sauté la question, écrite ici depuis le
  point 99. Détail ci-dessous, l'énoncé d'origine reste valable mot pour mot :
  un changement
  qui ne renomme rien oblige quand même à réécrire le frontend — un ACTEUR de plus
  sur une route (88), un champ qui devient calculé par le serveur (89), une route
  qui gagne un PRÉALABLE (90), une route qui gagne un VERROU de paiement (91), et
  du CONTENU éditorial ajouté ou RÉÉCRIT (94 — le premier qui ne touche pas aux
  données ; `section` y échappait depuis le point 55), et une clé étrangère qui
  change de NATURE sans changer de nom (99 — ce qu'elle CONTIENT, un id de compte
  ou l'id d'une ligne métier, et QUI la renseigne, le serveur depuis le jeton ou
  le client : le second cas ajoute un champ obligatoire au formulaire de création,
  donc un 422). La signature de contrat compte donc HUIT ensembles, dont le
  septième est un DICTIONNAIRE : sur du contenu, le texte compte autant que le
  titre, et ne comparer que les titres serait l'erreur du point 89. **Toute brique
  qui ajoute une promesse au contrat doit se demander si `_contract_signature`
  (cli.py) la voit** — six fois la
  réponse a été non, et six fois `monl update` aurait répondu « aucun changement
  d'interface » en laissant un écran ou un parcours entier à écrire. Ce n'est plus
  une série de coïncidences : c'est la question à poser à chaque brique, AVANT
  d'écrire le code. Un préalable/accès/verrou porté par une route qui vient
  d'apparaître est EXCLU du rapport : déjà dit par « route ajoutée » — et depuis le
  point 99, les rattachements d'une entité qui vient d'apparaître le sont aussi,
  même arbitrage porté cette fois sur les entités.
- POINT 89 : le delta de `monl update` compare aussi la LECTURE SEULE des
  champs. Il ne comparait que des noms : poser `derivedFrom` (ou `timestamp`)
  sur un champ existant ne renomme rien, donc « aucun changement d'interface »
  pendant qu'un formulaire devenait un champ que le serveur ignore. Pire qu'un
  403 : envoyer la valeur n'échoue pas, elle est écartée en silence. Même angle
  mort que le point 88, sur l'autre moitié du contrat. Un champ NEUF en lecture
  seule est annoté dans « champs ajoutés », pas remis dans une rubrique à part —
  même arbitrage anti-doublon que pour les accès.
- POINT 88 : le delta de `monl update` compare aussi les ACTEURS autorisés.
  Ouvrir une route existante à un rôle de plus ne crée aucune route : le delta
  répondait « aucun changement d'interface » alors qu'il manquait tout un
  back-office. Les accès d'une route qui vient d'apparaître sont exclus — déjà
  dits par « route ajoutée ».
- **Le rôle superviseur EXISTE** (attendu comme brique non cadrée depuis le
  point 31) : le contrôle de propriété généré est gardé par l'acteur, donc
  `rule X.Update sharedBy Proprietaire, Patron` suffit — le propriétaire ne
  touche que les siens, l'autre rôle voit et modifie tout. Vérifié en réel au
  point 88 ; ne pas reconstruire ce qui est déjà là.
- Le contrat doit décrire ce que le backend renvoie VRAIMENT, pas seulement
  ce que la spec déclare (point 76). Les routes de lecture générées font un
  `SELECT *` : toute colonne ajoutée par une brique (ex. `payment_status`,
  `payment_ref` de `payable`) sort dans les réponses et doit donc être
  déclarée dans `entities.<Entite>.fields`, sinon une IA d'interface fidèle
  au contrat ne peut pas l'afficher. Deux réflexes pour toute nouvelle brique
  qui ajoute une colonne : la déclarer avec `server_generated: true` (le
  `forbidden` existant couvre alors l'entrée), et l'ajouter APRÈS
  `_assign_field_roles` — passée à l'attribution des rôles, elle volerait
  des emplacements « méta » (3 au plus, point 35) à de vrais champs de la
  spec. Les noms de ces colonnes ont une source unique
  (`PAYMENT_*_COLUMN` dans generator/core.py) : ne pas les réécrire en dur.
- `src/tui.py` : présentation du dialogue. Le moteur ne l'importe QUE via
  l'interface `PlainDialogueUI` (rendu nu = chaînes historiques) ; le rendu
  stylé n'est injecté que par `run_interactive_dialogue`. Ne jamais mettre de
  logique de dialogue dans tui.py, ni de mise en forme dans dialogue_engine.py.
- POINT 104 : le brief dit désormais **par quel MOYEN une icône est possible**
  (SVG en ligne, fichiers `.svg` en liste blanche). Constat du mainteneur :
  aucun site produit n'employait d'icône — pas un défaut de l'IA, mais une
  lecture correcte d'un brief qui interdisait les CDN sans jamais dire ce qui
  restait faisable. Énoncer un MOYEN n'est pas prescrire un goût : même
  frontière que le contraste WCAG et l'autonomie, gardés par le point 72
  lui-même. Frontière mince, donc gardée par un test — le brief ne doit
  recommander aucune icône ni aucun style d'icône.
- Direction de design (point 72) : le compilateur ne décide RIEN du visuel —
  ni palette, ni typographie, ni rayon. Le bloc `ui … theme:` reste accepté
  par la grammaire mais n'a plus aucun effet, `.monl_theme_seed` a disparu, et
  `_verifier_palette` avec elle. La direction vient du DIALOGUE (registre
  visuel, place des images) et voyage par le brief. Ne pas réintroduire de
  suggestion « facultative » dans le contrat : elle oriente quand même.
- POINT 87 : `payable` fonctionne sur une entité possédée TRANSITIVEMENT. La
  route de règlement passe par la jointure de `_transitive_chain`, qui rend un
  id de COMPTE — donc la comparaison à `current_user_id` est la même qu'en
  propriété directe. **La jointure entre DANS le SELECT existant** : la sortir
  rouvrirait la fenêtre entre contrôle d'accès et calcul du montant (invariant
  du point 74), et un test compte les `cursor.execute` de la route pour
  l'interdire. Le refus du point 81 protégeait d'une comparaison fausse, pas
  d'une impossibilité — contre-épreuve : sans la jointure, un tiers règle la
  ligne d'autrui avec succès.
- POINT 91 : le verrou du payé a UNE source, `_payment_locked_parents`
  (generator/core.py), partagée par les cinq routes qu'il ferme et par le contrat
  (`_verrou_paiement` dans frontend_contract.py l'appelle, il ne recalcule pas la
  chaîne — deux vérités finiraient par diverger). Il se lit comme le pendant
  d'`_aggregation_recomputes` : partout où une écriture recalcule la somme d'un
  parent, ce parent peut déjà avoir été encaissé. La signature du webhook est
  aussi DATÉE depuis ce point (tolérance de cinq minutes, comme Stripe) — sans
  quoi un appel légitime capté une fois restait rejouable indéfiniment ; les
  tests qui signaient avec une date de 2023 passaient précisément parce que rien
  n'était daté.
- Paiement (points 74-75) : `_generate_payment_routes` (generator/routes.py)
  est la seule couche qui parle à l'extérieur. Trois invariants à ne jamais
  assouplir — le montant est lu en base et la route n'accepte AUCUN corps ;
  la signature du webhook est vérifiée avant toute écriture (seul endroit du
  backend généré où un tiers non authentifié écrit) ; une clé absente donne
  503 en la nommant, sans empêcher le reste du serveur de fonctionner.
  `MONL_STRIPE_BASE_URL` existe pour que la brique soit éprouvable sans
  appeler le vrai Stripe (`tests/test_paiement.py` embarque son prestataire).
  Un quatrième invariant depuis le point 75 : `payable` exige une relation
  entrante (owner) validée à la compilation (`ast_validator.py`), et la
  référence envoyée à/relue depuis Stripe est qualifiée par le nom de
  l'entité (`'Order:42'`) pour qu'une app à plusieurs entités `payable` ne
  confonde jamais l'id de deux tables au webhook. `_ask_payable`
  (`dialogue_engine.py`) rend la brique accessible depuis le dialogue guidé,
  à partir d'un champ `Money` sur une entité possédée — toute modification du
  dialogue qui touche à l'ordre des questions après `_ask_self_register` doit
  vérifier `tests/test_app_templates.py` (les modèles Boutique, Petites
  annonces et Suivi de dépenses posent la question `payable`, décalant les
  réponses scriptées si elle n'est pas prise en compte).
- Deux garde-fous d'empreinte dans src/frontend_ai.py, complémentaires
  (point 73) : `_fingerprint_protected` vérifie ce qui NE DOIT PAS bouger
  (app.py & consorts, point 69), `_fingerprint_frontend` vérifie ce qui DOIT
  bouger. Sans le second, un frontend valide préexistant franchissait tous les
  contrôles et monl annonçait une construction qui n'avait pas eu lieu.
- Une contrainte de champ (`required`/`unique`/`min`/`max`) vit dans
  `_valider_contraintes_de_champ` (ast_validator.py) et sort par
  `security.field_constraints`, indexé par `(entite, champ)`. Le générateur en
  fait deux choses : les bornes partent dans `schemas.py` (Pydantic), `unique`
  dans `_compute_unique_indexes` (core.py) puis `runtime.py` (index créé au
  démarrage). **Ne jamais réintroduire une règle qui ne produit rien** : c'est
  tout le point 85, et le test qui l'interdit compare la sortie avec et sans.
- POINT 92 : `_decrement_fk_column` (generator/core.py) est la source UNIQUE de
  la colonne visée par un `decrements`/`increments`, pour les TROIS branchements.
  C'est là qu'a vécu le bug du point 86 (la relation « propriétaire » confondue
  avec la cible du décompte) ; le calcul était recopié à chaque branche, et une
  troisième copie en préparait la troisième occurrence. **Ne jamais lire, dans
  une branche de la boucle de génération, une variable assignée dans une
  autre** : `reputation_rules_here` (branche `Create`) était relue dans la
  branche `Update` — d'où un compilateur qui PLANTAIT sur toute spec ayant un
  `Update` sans aucun `Create`, et un `Update` qui héritait des règles d'une
  autre entité (modifier un avis décomptait le stock d'un produit). Ça marche
  tant que l'ordre des routes met les deux branches côte à côte : **un bug
  d'ordre d'itération ne se voit pas sur la spec qui l'a fait naître.**
- POINT 96 : `requiresOwn` a un PENDANT à la suppression
  (`_profile_dependents`, generator/core.py). La règle gardait la création
  depuis le point 90 ; supprimer sa fiche laissait la commande sans
  destinataire — 1 commande, 0 fiche, vérifié sur `projets/SneakerLab`. Seule
  la DERNIÈRE fiche est protégée (« au moins une »), et le décompte porte sur
  le compte de l'appelant : avec un seul compte au banc, « existe-t-il une
  fiche quelque part ? » passerait.
- **LE VÉRIFICATEUR EST UN CLIENT COMME UN AUTRE** (points 95, 96, puis 100) :
  toute brique qui contraint une ENTRÉE contraint aussi le smoke test, qui code
  ses valeurs en dur et n'a aucun moyen de le savoir. Deux fois de suite il a
  déclaré cassée une application saine — `'smoke'` refusé par `identifier:
  email`, puis `'smoke-status'` refusé par `oneOf` ; au point 101 la question a
  été posée AVANT d'écrire le motif (`'smoke-reference'` n'est pas un `UUID`),
  et c'est la seule différence qui compte. **Le point 100 l'élargit** :
  toute brique qui change la FORME d'une ligne de spec contraint aussi les outils
  qui la lisent TEXTUELLEMENT. `assets_tool.py` détecte les blocs `seed` par une
  regex ancrée en fin de ligne ; la désignation de parent la faisait échouer en
  silence, alors que l'AST contenait bien le bloc. La question rejoint celle
  de `_contract_signature` dans la liste à poser AVANT d'écrire une brique.
- POINT 105 : **le dossier existe-t-il, PUIS porte-t-il un projet.** `_load_state`
  rend `None` dans les deux cas, et les quatre points d'entrée concluaient à la
  seconde — `monl frontend` conseillait même « lancer 'monl compile' » pour un
  dossier jamais trouvé. `_erreur_de_chemin` (cli.py) pose la première question,
  partagée, et explique la barre oblique de tête (`/projets/X` est cherché à la
  RACINE DU SYSTÈME). Même reproche qu'au point 97 : une hypothèse affichée
  comme un diagnostic envoie corriger ce qui n'est pas cassé.
  **`retouche` est le SEUL geste dont le premier argument n'est pas le dossier**
  (`run`, `update`, `diff`, `compile`, `frontend` le prennent tous en tête) :
  l'inversion est donc l'erreur attendue, elle est DÉTECTÉE et NOMMÉE — jamais
  corrigée d'office, ce serait deviner. Le témoin à ne pas perdre : un faux
  positif refuserait une retouche bien écrite.
- POINT 97 : la sortie de l'agent est CONSERVÉE et affichée quand rien n'a
  bougé. `run_cli_agent` la rendait déjà, personne ne la lisait — monl affichait
  « reformuler en nommant l'écran » sur une demande qui les nommait, pendant que
  l'agent expliquait que la rubrique venait de la SPEC. **Une hypothèse affichée
  comme un diagnostic est pire qu'un message vague** : elle envoie corriger ce
  qui n'est pas cassé. Le conseil de reformulation ne s'affiche plus que si
  l'agent s'est tu.
- Le séparateur de paragraphes **`¶`** (point 64) structure le corps d'une
  `section` sans nouvelle brique — la grammaire interdit le saut de ligne dans un
  STRING_LITERAL, `paragraphes()` (frontend_contract.py) le retraduit. Y penser
  AVANT d'envisager une brique : « je veux pas un paragraphe » se réglait comme
  ça (point 97).
- POINT 93 : il n'y a qu'UNE voie vers l'IA — `_lancer_ia` (cli.py) et
  `brief_evolution` (frontend_ai.py), partagés par `frontend` et `retouche`.
  Le dispatch appelait le modèle en ligne ; recopier ces lignes pour la retouche
  aurait fait deux endroits où les garde-fous peuvent diverger. `brief_evolution`
  ne décide QUE du nom du brief, tout le reste est commun, et un test lance un
  agent malveillant PAR la voie retouche pour le vérifier.
- POINT 94 : `landing` accepte `question "…": "…"`, répétable comme `section`.
  Forme PLATE volontairement — un sous-bloc indenté aurait ajouté un niveau à la
  seule grammaire où l'indentation a déjà coûté deux bugs (point 6). L'ORDRE de
  déclaration est conservé : dans une FAQ il porte du sens, et rien ne permet de
  le retrouver après coup. Le brief doit dire que c'est une LISTE — déposer les
  couples sans le dire laissait refaire le pavé de prose qu'on répare.
- POINT 92 : l'avertissement « chemins absents du contrat » (cli.py) exclut les
  routes de NAVIGATION, reconnues par le `#/x` présent dans le même fichier. Il
  dénonçait quatre routes correctes sur SneakerLab. Un avertissement qui se
  trompe sur un site correct apprend à ne plus lire les avertissements — même
  arbitrage qu'au point 57, sur le même avertissement. Garder son témoin : un
  chemin réellement fautif doit rester signalé.
- `min` sur un champ décrémenté ARME la vérification de disponibilité
  (`routes.py`, point 86). Ce n'est pas une coïncidence à préserver par
  discipline : c'est la seule façon déclarative de distinguer un stock (qui ne
  doit pas passer sous zéro) d'une réputation (qui le peut). Câbler une
  exception « stock » à la place rouvrirait la question à chaque nouveau cas.
- `src/monl/assets_tool.py` est le SEUL endroit du dépôt, hors dialogue guidé,
  qui écrive dans la spec de l'humain (point 84). Trois règles y tiennent tout :
  édition TEXTUELLE (les commentaires sont la documentation du projet, un
  aller-retour parse → regénère les effacerait), revalidation par le vrai
  parseur + validateur AVANT écriture, et retour en arrière complet en cas
  d'échec (fichier copié retiré, écrasement `--force` restauré). Ne pas
  réintroduire `base_dir` dans `_valider` : le contrôle d'existence est ciblé
  sur ce que l'outil ÉCRIT, sinon `list` redevient incapable de rapporter un
  manquant et `add` redevient inutilisable sur une spec incomplète.
- **POINT 154 : `generator/core.py` est réduit à `__init__` + sept mixins, et
  `parser` est un PAQUET.** Les mixins de `generator/` :
  `pipeline` (dont `_compute_route_map`), `modele`, `proprietaire` (dont
  `_transitive_chain`, `_owner_lookup_sql`, `_identity_fk_columns`), `calculs`
  (dont `_decrement_fk_column`), `paiement` (dont `_payment_locked_parents`),
  `sql_colonnes`, `prealables`. Les sources UNIQUES citées plus bas dans ce
  fichier ont donc changé de module, pas de rôle.
  **LE PIÈGE À CONNAÎTRE POUR TOUT DÉCOUPAGE DE TRANSFORMATEUR LARK** :
  `@v_args(inline=True)` porté par une CLASSE saute toute méthode héritée
  (`name in libmembers and name not in cls.__dict__` → `continue`). Déplacer
  les productions dans des mixins nus les aurait laissées non enveloppées :
  elles auraient reçu une LISTE d'enfants au lieu d'arguments inlinés, sans
  qu'une ligne ne lève. Chaque mixin hérite donc de `Transformer` et porte son
  PROPRE `@v_args` — vérifié par exécution (73 productions, 73 enveloppées).
  **Un décorateur de classe ne suit pas le code qu'on déplace.**
  `parser/grammaire.py` dépasse 400 lignes À DESSEIN : la grammaire est UN
  artefact déclaratif, Lark ignore l'ordre des règles, donc toute coupure
  serait arbitraire. L'exception est écrite dans la docstring du fichier.
  **Et la troisième forme du même défaut** (après 152 et 153) : deux
  `per-file-ignores` de `pyproject.toml` visaient des fichiers devenus des
  paquets — elles n'excusaient plus rien, et `ruff` ne se plaint pas d'un
  chemin orphelin. Un témoin de `tests/test_architecture.py` le refuse
  désormais. **Une garantie qui cesse de porter sur quoi que ce soit ne fait
  aucun bruit : la suite reste verte les trois fois.**
- **POINT 153 : `frontend_ai` est un PAQUET, et un remplacement d'attribut vise
  le module où le nom est CHERCHÉ.** Onze modules (`fondations`, `fournisseurs`,
  `reponse`, `squelette`, `controles_design`, `controles_fichiers`, `redaction`,
  `etages`, `images`, `agents`, `orchestration`). **Règle interne : un appel
  entre modules du paquet passe par l'objet MODULE** (`reponse._write_files(…)`),
  jamais par un nom lié — ça donne UN seul point de remplacement par fonction au
  lieu d'un par appelant. Donc un test écrit
  `monkeypatch.setattr(frontend_ai.agents, "_fingerprint_protected", …)` et non
  `setattr(frontend_ai, …)` ; le second ne mord plus, EN SILENCE.
  **Ce que ça a révélé** : le test de la voie agent passait sans exercer le
  garde-fou d'empreinte du point 73 — la vraie fonction tournait et rendait un
  dictionnaire vide. Contre-épreuve faite avec un stub levant : atteint quand il
  vise `.agents`, jamais atteint quand il vise le paquet. Les imports de `cli.py`
  vers `frontend_ai` sont DANS les fonctions, donc résolus après le
  remplacement : ceux-là continuent de mordre.
  Deux corollaires pour le prochain découpage : **un nom de module ne doit
  ressembler à aucune variable locale du code qu'il accueille** (`brief` et
  `socle` visaient la variable, pas le module — `ruff` F823), et **une surface
  publique se mesure par AST**, jamais par `grep` (les imports multi-lignes et
  les accès par attribut échappent au texte).
- **POINT 152 : le validateur est un PAQUET (`src/monl/ast_validator/`).**
  Même forme que `generator/` : un module par préoccupation, la classe
  recomposée par mixins dans `core.py`. Une nouvelle règle s'ajoute dans le
  module de sa couche — `acces.py`, `champs.py`, `commerce.py`… — jamais dans
  `core.py`. L'ordre d'exécution vient du pipeline
  (`validation_pipeline.py`), PAS de l'ordre des bases. `socle.py` est la
  FEUILLE (constantes + `ASTValidationError`) et ne lit rien de son paquet :
  c'est ce qui rend un cycle impossible, et un test le vérifie plutôt que de
  le laisser à la discipline. La surface publique n'a pas bougé —
  `from monl.ast_validator import MonlAST, ASTValidationError,
  DEFAULT_ASSETS_DIR, resoudre_asset`.
  **Ce que le découpage a trouvé** : `tests/test_architecture.py` nommait
  `generator` EN DUR dans `MODULES`, donc `ast_validator` en est sorti en
  devenant un paquet — son contrat restait écrit dans `INTERDITS` en ne
  regardant plus rien, sans qu'aucun test devienne rouge. La liste est lue sur
  le disque, et un témoin exige que chaque contrat porte sur un module connu.
  **Un test d'architecture cesse de regarder de deux façons : il ne voit plus
  les imports, ou il ne voit plus les modules — la seconde ne laisse aucune
  trace.** Toute restructuration pure se prouve par
  `tests/test_golden_artifacts.py` : les onze empreintes doivent être
  INCHANGÉES. Et **ne jamais faire une contre-épreuve pendant qu'une suite
  tourne** : un sous-processus relit le disque, là où le pytest principal a
  déjà son import en mémoire.
- **POINT 151 : le jeu de démonstration d'un MODÈLE est adapté par l'IA, dans
  `src/monl_platform/seed_ai.py` et nulle part ailleurs.** Toute boutique
  vendait « Théière Kyoto » : la description n'atteignait que le `brief`, donc
  les TEXTES, jamais les données. Le dialogue guidé reste déterministe — c'est
  la plateforme qui personnalise, puisqu'elle appelle déjà une IA. **L'IA écrit
  des LIGNES de CSV, jamais la structure** : l'en-tête vient de `monl content
  export`, un en-tête différent fait refuser la réponse. L'écriture passe par
  `importer_contenu` (point 115), donc par le vrai parseur — aucune machinerie
  nouvelle. Un échec restaure le CSV d'origine : un catalogue générique est un
  défaut, une construction perdue est une facture. Une spec FOURNIE par
  l'usager n'est jamais touchée. L'appel porte le garde-fou de quota du
  produit.
- **POINT 150 : une mesure INDÉTERMINÉE n'est pas une mesure NULLE.**
  `_frontend_fetch_calls` (cli.py) ne comptait une fonction d'accès que
  écrite `fetch(endpoint, …)` ; le modèle écrivait `const url =
  \`${API_BASE}${endpoint}\`; fetch(url, config)`. Résultat : « 0 route sur
  15 » sur un frontend qui en appelait cinq et dont le smoke test passait —
  refusé pour de bon. Et l'instruction d'étage dit « factorise le code » :
  monl demandait la factorisation puis refusait le site factorisé. Le
  contrôle suit désormais le FLUX du paramètre (direct, gabarit, variable
  locale) en restant conservateur — il exige un flux démontrable, sinon
  n'importe quelle fonction contenant un `fetch` ferait compter ses arguments
  comme des routes. **Le sens de l'erreur compte** : pour une route fantôme,
  ne pas compter l'irréductible est juste ; pour une couverture, c'est
  accuser un site correct.
- **POINT 149 : le budget demandé à un étage vient du CONTRAT, jamais d'une
  constante.** monl réclamait « environ 1 500 tokens » pour `app.js` quel que
  soit le contrat, avec une limite dure de 12 000 caractères — pour un fichier
  dont les exemples complets du dépôt pèsent 26 à 43 Ko. Le modèle obéissait au
  jeton près (1 698 mesurés, ZÉRO reprise : rien n'était tronqué), puis monl le
  refusait pour incomplétude. **Changer de modèle n'y peut rien** : le modèle
  solide obéit mieux, donc produit moins. Plafond-sans-plancher pour la
  troisième fois — et c'est l'instruction CHIFFRÉE, la dernière lue, que le
  modèle écoute. Le plancher est désormais énoncé à l'étage, et la limite dure
  suit le budget au lieu de le contredire.
- **POINT 148 : où part l'argent d'une construction, mesuré.** `styles.css`
  consomme 50 % des jetons de SORTIE (la partie sans fonction), `app.js` 34 %
  alors qu'il porte toute la complétude. Les « reprises » d'une étape viennent
  d'une réponse ILLISIBLE : emballer un fichier JS dans une chaîne JSON casse
  chez les modèles bon marché, et la relance les pousse vers ce qui PARSE,
  donc vers le fichier minimal. D'où le filet du bloc clôturé
  (`_fichier_depuis_un_bloc`) — repli seulement, passant par `_validate_files`
  comme tout le reste. **Le vrai levier de coût est `--model-for` :** modèle
  solide sur `app.js`, modèle bon marché sur `styles.css`.
- **POINT 147 : la correction automatique garde la MEILLEURE tentative, pas
  la dernière.** Mesuré en payant : à qui on demandait de réparer deux lignes,
  le modèle a réécrit le site et perdu 14 routes sur 15 — et monl conservait
  cette version-là, parce que la boucle rendait l'état final. Le classement est
  `(erreurs, avertissements)` sans pondération (une gravité inventée serait une
  opinion déguisée en mesure) ; les erreurs rapportées sont celles des fichiers
  CONSERVÉS ; la restauration ne touche que la liste blanche, jamais les images
  générées, et retire les fichiers de la tentative écartée — un mélange des
  deux serait pire que l'une ou l'autre. Contre-épreuve obligatoire : une
  seconde tentative MEILLEURE doit rester en place, sinon le garde-fou annule
  la correction automatique et passe pour bon.
- **POINT 146 : une brique sans PRODUCTEUR n'existe pas.** La brique 30
  (liens du pied de page) était déclarable depuis le point 144 et rien ne
  l'écrivait — ni le dialogue guidé, ni les dix modèles, ni la console web :
  tout site sortait avec un pied de page sans une destination. C'est le
  point 85 sous un autre jour, et le test de compilation ne peut pas le voir.
  **Question à poser pour toute nouvelle brique, à côté de celle de
  `_contract_signature` : qui l'écrira ?** La complétion d'adresse a UNE source
  (`adresse_de_lien`, dialogue_engine.py) ; la console en a nécessairement une
  copie JavaScript, et `tests/test_liens_pied_de_page.py` exécute les DEUX sur
  les mêmes entrées — deux mises en œuvre de la même règle divergent toujours.
  Le mode express ne pose aucune question : ses liens arrivent par
  `express_links`.
- **Ne jamais découper un scénario de test par une tranche négative.**
  `SCENARIO_PORTFOLIO[:-4]` a cassé huit tests d'un coup à la première question
  ajoutée, sans jamais dire ce qu'il retirait ; les scénarios sont désormais
  composés de morceaux nommés, et le nombre d'entrées proposées est LU sur
  `GuidedDialogue.LIENS_PROPOSES`.
- **POINT 145 : la connexion par Google/GitHub vit dans
  `src/monl_platform/oauth.py`, et nulle part ailleurs.** Quatre décisions y
  sont écrites et ne se rouvrent pas : l'identité du fournisseur a son PROPRE
  espace de noms (`github:<id>`) — aucun rattachement automatique à un compte
  par mot de passe de même adresse, sans quoi l'un prendrait le contrôle de
  l'autre ; seule une adresse VÉRIFIÉE par le fournisseur est acceptée (sinon
  la brique déplace la chaîne quelconque au lieu de la fermer) ; le `state` est
  signé ET daté (le rejeu, comme la signature du webhook au point 91) ; et
  l'adresse de retour vient de `MONL_PLATFORM_PUBLIC_URL`, **jamais** de
  l'en-tête `Host` — son absence empêche le DÉMARRAGE dès qu'un fournisseur est
  configuré, plutôt que de laisser un bouton répondre 503 au clic. Le jeton
  voyage dans le FRAGMENT (jamais envoyé au serveur, jamais journalisé) et la
  console efface la barre d'adresse après l'avoir récolté. Éprouvé par un FAUX
  fournisseur embarqué (`MONL_OAUTH_*_BASE_URL`, précédent du faux Stripe du
  point 74) et par un pilote jsdom contre le serveur réel. **Le piège du banc**
  : jsdom n'a pas `matchMedia`, sans quoi le script de la console meurt à sa
  première ligne et on mesure le banc au lieu du produit.
- **Un test qui passe ne prouve pas qu'il mord** (point 145). Le refus du
  `password_hash` nul dans `authenticate_account` pouvait être retiré en
  laissant la suite entièrement verte : `_password_matches` l'écartait déjà une
  couche plus bas. Retirer un garde-fou pour voir tomber un test est le seul
  moyen de savoir où la garantie vit vraiment.
- Le smoke test (src/smoke_test.py) démarre un serveur ÉPHÉMÈRE dans un
  dossier temporaire : il ne touche jamais app.db du projet. Le fetch de
  jsdom DOIT être injecté via beforeParse (bug réel : assigné après
  construction, il n'est jamais vu par les scripts de la page).
- Le contrat annonce `api.base_url = ""` — MÊME ORIGINE, jamais d'URL absolue
  ni de port codé en dur : `monl run` monte frontend/ sur /site du serveur qui
  porte déjà l'API. Y remettre une base absolue casserait `monl run --port` et
  ferait recaler par le smoke test (port éphémère) tout frontend obéissant.
  Le shim jsdom refuse explicitement les URL absolues plutôt que de les
  réécrire : les réécrire serait un faux positif. Point 51.

## Commandes de référence

```bash
pip install -e . --break-system-packages   # point 65 : vrai paquet, commande 'monl'
./monl compile exemples/01_portfolio.ml --output build/portfolio
python3 -m uvicorn app:app --reload        # jamais `python3 app.py` directement
python3 -m pytest tests/ -v
```
