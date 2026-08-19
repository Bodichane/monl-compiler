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
- Lancer la suite de tests : `python3 -m pytest tests/ -q` (1171 tests
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
   point 86). Éprouvée par `tests/test_identifiant_de_compte.py` (37 tests).
   Voir point 95.
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
  lignes a été découpé) : `core.py` (état issu de l'AST, orchestration,
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
- **POINT 141 : le pied de page est exigé, et ses liens sont DÉCLARÉS.**
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
- **POINT 140 : un marqueur nomme une section, il ne prouve pas qu'elle
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
- **POINT 146 : le budget demandé à un étage vient du CONTRAT, jamais d'une
  constante.** monl réclamait « environ 1 500 tokens » pour `app.js` quel que
  soit le contrat, avec une limite dure de 12 000 caractères — pour un fichier
  dont les exemples complets du dépôt pèsent 26 à 43 Ko. Le modèle obéissait au
  jeton près (1 698 mesurés, ZÉRO reprise : rien n'était tronqué), puis monl le
  refusait pour incomplétude. **Changer de modèle n'y peut rien** : le modèle
  solide obéit mieux, donc produit moins. Plafond-sans-plancher pour la
  troisième fois — et c'est l'instruction CHIFFRÉE, la dernière lue, que le
  modèle écoute. Le plancher est désormais énoncé à l'étage, et la limite dure
  suit le budget au lieu de le contredire.
- **POINT 145 : où part l'argent d'une construction, mesuré.** `styles.css`
  consomme 50 % des jetons de SORTIE (la partie sans fonction), `app.js` 34 %
  alors qu'il porte toute la complétude. Les « reprises » d'une étape viennent
  d'une réponse ILLISIBLE : emballer un fichier JS dans une chaîne JSON casse
  chez les modèles bon marché, et la relance les pousse vers ce qui PARSE,
  donc vers le fichier minimal. D'où le filet du bloc clôturé
  (`_fichier_depuis_un_bloc`) — repli seulement, passant par `_validate_files`
  comme tout le reste. **Le vrai levier de coût est `--model-for` :** modèle
  solide sur `app.js`, modèle bon marché sur `styles.css`.
- **POINT 144 : la correction automatique garde la MEILLEURE tentative, pas
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
- **POINT 143 : une brique sans PRODUCTEUR n'existe pas.** La brique 29
  (liens du pied de page) était déclarable depuis le point 141 et rien ne
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
- **POINT 142 : la connexion par Google/GitHub vit dans
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
- **Un test qui passe ne prouve pas qu'il mord** (point 142). Le refus du
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
