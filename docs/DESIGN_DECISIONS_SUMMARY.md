# Design decisions — English summary

`docs/design_decisions.md` is the project's design journal. It stays in
French: every strict compiler rule, every fixed bug and every architecture
decision is written there with its "why", and that text is the reference.
This page is its English map — the same thematic contents, one line per
point, each linking to the full French entry.

Two numbering quirks are intentional: points 45 and 46 each name two
distinct entries (a merge left-over), and point 6 is a reserved, empty
duplicate of point 1, kept so that references do not shift. Cite a point by
its title as well as by its number.

## Contents by theme

**Security and access control**:[206](design_decisions.md#206-un-modèle-de-menaces-défensif-avec-des-preuves-vérifiables) Defensive threat model with verified test evidence ·
[1](design_decisions.md#1-collision-de-privilèges-critical_collision) Privilege collision ·
[2](design_decisions.md#2-restriction-de-champ-restrictedto) Field restriction ·
[3](design_decisions.md#3-avertissement-sur-les-suppressions-non-admin-critical_warning) Warning on non-Admin deletions ·
[5](design_decisions.md#5-contrôle-daccès-par-propriété-ownedby) Ownership control (`ownedBy`) ·
[9](design_decisions.md#9-limitation-de-débit-sur-login) Rate limiting on `/login` ·
[11](design_decisions.md#11-secret-jwt-unique-par-projet-faille-corrigée) Per-project unique JWT secret ·
[12](design_decisions.md#12-révocation-de-token-logout) Token revocation ·
[13](design_decisions.md#13-limitation-de-débit-sur-register) Rate limiting on `/register` ·
[16](design_decisions.md#16-actions-publiques-public--cas-dusage-portfolio) Public actions (`public`) ·
[106](design_decisions.md#106-rôle-superviseur-au-dessus-daccessibleby-brique-23) Supervisor role (`accessibleBy`) ·
[107](design_decisions.md#107-la-chaîne-de-propriété-qui-remonte-toute-la-profondeur-brique-24) Transitive ownership at full depth (brick 24) ·
[108](design_decisions.md#108-lémission-sql-typée-la-frontière-de-sécurité) Typed SQL emission (security boundary) ·
[109](design_decisions.md#109-le-contrôle-daccès-sorti-de-lombre-du-validateur) Access control, moved out of the validator's catch-all ·
[110](design_decisions.md#110-rust-évalué-par-un-spike-mesuré-et-écarté) Rust evaluated by a measured spike, and rejected ·
[111](design_decisions.md#111-public-requiresown-et-payable-sortent-du-fourre-tout) `public`, `requiresOwn` and `payable` leave the catch-all ·
[112](design_decisions.md#112-restrictedto-jamais-validé-structurellement) `restrictedTo` never validated structurally ·
[113](design_decisions.md#113-le-verrou-de-paiement-bloquait-aussi-le-superviseur-et-personne-ne-le-savait) The payment lock also blocked the supervisor ·
[114](design_decisions.md#114-le-point-113-fermé-sur-les-deux-sites-et-un-trou-quil-avait-laissé) Point 113 adopted on both sites, and its own hole closed ·
[115](design_decisions.md#115-brique-26--monl-content-exportimport-le-contenu-en-masse) Brick 26: `monl content export`/`import`, bulk content ·
[116](design_decisions.md#116-briques-27-et-28--publicwhen-et-onceper-livrées-sans-leurs-garde-fous) Bricks 27 and 28: `publicWhen` and `oncePer`, shipped without their safeguards ·
[117](design_decisions.md#117-la-colonne-du-compteur-avait-deux-sources-et-lordre-des-relations-tranchait) The counter column had two sources, and relation order decided ·
[118](design_decisions.md#118-le-backend-savait-tout-faire-sauf-se-déployer) The backend could do everything except deploy itself ·
[119](design_decisions.md#119-la-couche-données-choisit-son-dialecte-au-démarrage) The data layer picks its dialect at startup ·
[120](design_decisions.md#120-les-migrations-non-additives-sont-nommées-et-refusent-le-démarrage) Named non-additive migrations ·
[121](design_decisions.md#121-le-fichier-déposé-par-le-client-est-un-upload-pas-une-image) A file uploaded by the client is an `Upload`, not an `Image`
[122](design_decisions.md#122-monl-sait-envoyer-un-message-sans-promettre-sa-remise) Sending a message without promising delivery ·
[123](design_decisions.md#123-filtrer-et-trier-sans-inventer-un-langage-de-requête) Filtering and sorting without inventing a query language ·
[124](design_decisions.md#124-authentification-complète--verrouillage-réinitialisation-rafraîchissement-et-totp) Complete authentication: lockout, reset, refresh and TOTP ·
[125](design_decisions.md#125-le-contrat-nommait-le-jeton-sans-dire-sous-quel-nom-le-lire) The contract named the token without saying under which name to read it ·
[126](design_decisions.md#126-la-devise-dencaissement-et-son-exposant) The payment currency and its exponent ·
[127](design_decisions.md#127-la-démonstration-nallait-plus-chercher-ses-images-chez-un-tiers) The demo no longer fetched its images from a third party ·
[128](design_decisions.md#128-encaisser-par-mobile-money--le-prestataire-devient-enfichable) Paying by mobile money: the provider becomes pluggable ·
[129](design_decisions.md#129-loracle-temporel-se-mesure-par-paires-jamais-par-séries) The timing oracle is measured in PAIRS, never in series ·
[130](design_decisions.md#130-une-sonde-qui-prouve-quun-worker-répond-ne-prouve-rien-des-autres) A probe that proves ONE worker answers proves nothing about the others ·
[131](design_decisions.md#131-fedapay--la-devise-quil-encaisse-vraiment-et-lappariement-prouvé-du-webhook) FedaPay: the currency it actually collects, and the proven webhook matching ·
[132](design_decisions.md#132-le-serveur-mourait-au-démarrage-à-plusieurs-workers) The server died at startup with several workers ·
[133](design_decisions.md#133-limage-servait-lapi-et-répondait-404-sur-le-site) The image served the API and answered 404 on the site ·
[134](design_decisions.md#134-la-frontière-de-lagent-était-une-énumération-incomplète) The agent's boundary was an incomplete enumeration ·
[135](design_decisions.md#135-mesurer-le-coût-avant-de-vendre-la-génération--yandex-ai-studio) Measuring the cost before selling generation: Yandex AI Studio ·
[136](design_decisions.md#136-un-système-de-design-avant-le-code--et-un-manifeste-qui-devient-une-preuve) A design system before the code — and a manifest that becomes a proof ·
[137](design_decisions.md#137-brique-29--le-site-réclamait-six-fichiers-que-personne-navait-livrés) Brick 29: the site requested six files nobody had delivered ·
[138](design_decisions.md#138-le-dialogue-ne-demandait-jamais-comment-on-se-connecte-et-lindicatif-ne-servait-quen-europe) The dialogue never asked how people sign in, and the dialling code only worked in Europe ·
[139](design_decisions.md#139-le-compilateur-avait-repris-la-main-sur-la-palette-par-lautre-tuyau) The compiler had taken back control of the palette, through the other pipe ·
[140](design_decisions.md#140-le-harnais-de-test-sautait-au-lieu-déchouer-et-vingt-et-un-fichiers-avec-lui) The test harness skipped instead of failing, and twenty-one files with it ·
[141](design_decisions.md#141-ouvrir-la-plateforme-au-public--cinq-manques-et-une-base-qui-ne-se-fermait-jamais) Opening the platform to the public: five gaps, and a database that never closed ·
[142](design_decisions.md#142-les-deux-falaises-produit--un-mot-de-passe-perdu-et-aucun-administrateur) The two product cliffs: a lost password, and no administrator ·
[143](design_decisions.md#143-un-marqueur-nommait-la-section-sans-jamais-prouver-quil-y-avait-quelque-chose-dedans) A marker named the section without proving there was anything in it ·
[144](design_decisions.md#144-le-pied-de-page-nétait-exigé-nulle-part-et-monl-ne-pouvait-pas-le-deviner) The footer was required nowhere ·
[145](design_decisions.md#145-ouvrir-un-compte-ne-coûtait-rien-sur-une-plateforme-qui-dépense) Opening an account cost nothing, on a platform that spends ·
[146](design_decisions.md#146-la-brique-du-pied-de-page-existait-et-rien-ne-la-produisait) The footer brick existed, and nothing produced it ·
[147](design_decisions.md#147-la-correction-automatique-pouvait-tout-casser-et-monl-gardait-le-pire) Automatic correction could break everything, and monl kept the worst ·
[148](design_decisions.md#148-le-fichier-était-emballé-dans-du-json-et-cest-lemballage-qui-cassait) The file was wrapped in JSON, and the wrapping was what broke ·
[149](design_decisions.md#149-on-demandait-un-appjs-de-1-500-jetons-puis-on-le-refusait-parce-quil-était-incomplet) We asked for a 1,500-token app.js, then refused it ·
[150](design_decisions.md#150-le-brief-demandait-de-factoriser-et-cest-la-factorisation-qui-faisait-refuser-le-site) The brief asked to factor the code, and factoring got it refused ·
[151](design_decisions.md#151-toute-boutique-vendait-des-théières) Every shop sold teapots ·
[152](design_decisions.md#152-le-validateur-est-devenu-un-paquet-et-un-contrat-darchitecture-sest-tu) The validator became a package, and an architecture contract went silent ·
[153](design_decisions.md#153-le-garde-fou-dempreinte-nétait-plus-exercé-par-le-test-qui-le-nomme) The fingerprint safeguard was no longer exercised by the test that names it ·
[154](design_decisions.md#154-un-décorateur-qui-saute-les-mixins-et-deux-exceptions-qui-nexcusaient-plus-rien) A decorator that skips mixins, and two exceptions that no longer excused anything ·
[155](design_decisions.md#155-cinq-angles-morts-dans-lanalyse-qui-découpe-et-un-plafond-qui-nexistait-pas) Five blind spots in the splitting analysis, and a ceiling that did not exist ·
[156](design_decisions.md#156-un-repère-qui-glisse-une-bascule-qui-révèle-et-un-volet-qui-ment) A marker that slides, a toggle that reveals, and a pane that lies ·
[157](design_decisions.md#157-le-logo-au--o--orange-et-trois-mesures-qui-mentaient) The logo with the orange "o", and three measurements that lied ·
[158](design_decisions.md#158-sept-couleurs-dérivées-de-la-grammaire-et-un-surtitre-de-moins-par-section) Seven colours derived from the grammar, and one eyebrow fewer per section ·
[159](design_decisions.md#159-une-assertion-de-rejeu-qui-rejouait-un-code-neuf-et-sa-voisine-qui-ne-mesurait-plus-rien) A replay assertion that replayed a fresh code ·
[160](design_decisions.md#160-un-seuil-de-temps-en-secondes-ne-veut-pas-dire-la-même-chose-sur-deux-machines) A time threshold in seconds does not mean the same thing on two machines ·
[161](design_decisions.md#161-la-ci-avait-deux--q-et-ses-sauts-ne-se-voyaient-pas) CI had two `-q`, and its skips could not be seen ·
[162](design_decisions.md#162-le-cap--une-base-de-données-déterministe-et-sûre-le-reste-chez-le-fournisseur-de-lusager) The course: a deterministic and safe database, the rest at the user's provider ·
[163](design_decisions.md#163-le-dialogue-guidé-sur-le-web-et-deux-pages-mortes-que-rien-ne-voyait) The guided dialogue on the web, and two dead pages ·
[164](design_decisions.md#164-quatre-bloquants-quaucun-test-ne-voyait-trouvés-en-étant-le-premier-usager) Four blockers found by being the first user ·
[165](design_decisions.md#165-le-site-à-375-pixels--quatre-défauts-et-une-mesure-qui-portait-à-côté) The site at 375 pixels, and a measurement that was aimed elsewhere ·
[166](design_decisions.md#166-le-chemin-conteneur-enfin-exécuté--et-le-déploiement-recommandé-était-aveugle) The container path executed, and blind supervision ·
[167](design_decisions.md#167-rendre-le-compilateur-publiable--sans-le-publier) Making the compiler publishable, without publishing it ·
[168](design_decisions.md#168-loracle-temporel-tombe-une-troisième-fois--le-bruit-se-mesure) The timing oracle falls a third time: noise gets measured ·
[169](design_decisions.md#169-publier-sans-secret--et-les-trois-listes-écrites-à-la-main) Publishing without secrets, and the hand-written lists ·
[170](design_decisions.md#170-la-complexité-mesurée-devient-un-cliquet--et-un-témoin-qui-ne-rougit-jamais-seul) Complexity becomes a ratchet, and the witness that never fails on its own ·
[171](design_decisions.md#171-la-console-jetait-la-liste-des-choix--et-une-barre-translucide-coupe-le-texte) The console threw away the list of choices, and the translucent bar ·
[172](design_decisions.md#172-le-serveur-sait-et-ne-dit-pas--deux-fois-avant-la-mise-en-ligne) The server knows and does not say: cleartext cookie, silent hosted sites ·
[172bis](design_decisions.md#172bis-une-borne-de-disque-se-tient-à-chaque-instant-pas-seulement-à-la-fin) A disk bound holds at every moment ·
[173](design_decisions.md#173-trois-briques-que-le-dialogue-nécrivait-pas--et-une-photo-que-personne-ne-voyait) Three bricks without a producer, and the photo nobody could see ·
[174](design_decisions.md#174-la-mémoire-du-projet-ignorait-des-briques-et-un-garde-fou-la-rend-vivante) The project memory ignored bricks, and a safeguard keeps it alive ·
[175](design_decisions.md#175-un-fichier-vide-quon-ne-peut-pas-enlever-et-une-adresse-quun-inconnu-vous-prend) An empty file that cannot be removed, and a stolen address ·
[176](design_decisions.md#176-une-archive-se-lit--docs-pour-ce-qui-se-lit-la-racine-pour-ce-qui-sexécute) An archive is read: docs/ for what is read, the root for what runs ·
[177](design_decisions.md#177-le-logo-monochrome-remplace-lorange--et-un-témoin-nommait-le-mauvais-signe) The monochrome logo replaces the orange one, and a witness named the wrong sign ·
[178](design_decisions.md#178-la-page-daccueil-affirmait-une-vérification-qui-nexistait-pas) The home page claimed a verification that did not exist ·
[179](design_decisions.md#179-required-disait--présent--jamais--rempli---et-le-dialogue-sen-contentait) `required` said "present", never "filled" ·
[180](design_decisions.md#180-une-limite-annoncée-se-périme-comme-une-brique--la-table-du-guide-disait-faux) An announced limit goes stale like a brick ·
[181](design_decisions.md#181-ce-quune-route-interroge-nétait-pas-indexé-et-le-jeton-se-décodait-deux-fois) What a route queries was not indexed ·
[182](design_decisions.md#182-une-connexion-neuve-par-requête--11-ms-payés-54-fois-le-prix-de-la-requête) A new connection per request ·
[183](design_decisions.md#183-un-correctif-ferme-les-cas-connus--un-invariant-ferme-la-classe) An invariant closes the class ·
[184](design_decisions.md#184-une-barrière-de-couverture-mesurée-sur-une-liste-de-tests-ment-sur-ce-quelle-mesure) A barrier measured on a list lies ·
[185](design_decisions.md#185-le-déploiement-de-production-éprouvé-pour-de-vrai--quatre-défauts-quaucune-lecture-naurait-montrés) The production deployment, tested for real ·
[186](design_decisions.md#186-un-audit-statique-trouve-cinq-défauts-réels--le-corps-http-et-la-recompilation-fermés) A static audit finds five real defects — the HTTP body and recompilation closed ·
[187](design_decisions.md#187-le-state-oauth-ne-prouvait-rien-du-navigateur--et-la-page-de-confidentialité-affirmait-un-seul-cookie) The OAuth `state` proved nothing about the browser ·
[188](design_decisions.md#188-les-deux-derniers-défauts-de-laudit--et-la-borne-quon-mesurait-sur-ce-quelle-contraint-jamais-sur-ce-quelle-sert) A bound measured on what it constrains, never on what it serves ·
[189](design_decisions.md#189-la-production-était-à-terre-depuis-cinquante-minutes-et-rien-ne-lavait-dit) Production was down, and nothing had said so ·
[190](design_decisions.md#190-la-documentation-ne-peut-plus-se-périmer-en-silence--et-le-témoin-a-fabriqué-un-mensonge-avant-quon-le-corrige) Documentation can no longer go stale silently ·
[191](design_decisions.md#191-le-statut-post-paiement-naissait-hors-de-son-propre-cycle-de-vie) The post-payment status was born outside its own lifecycle ·
[192](design_decisions.md#192-les-tests-dhébergement-laissaient-leurs-serveurs-orphelins) Hosting tests left their servers orphaned ·
[193](design_decisions.md#193-la-page-de-connexion-avait-quatre-comportements-quaucun-test-ne-voyait) The sign-in page had four behaviours no test could see ·
[194](design_decisions.md#194-lattente-sarrêtait-aux-en-têtes-et-linclinaison-passait-sur-une-carte-de-taille-nulle) The wait stopped at the headers, and the tilt ran on a zero-size card ·
[195](design_decisions.md#195-le-contrat-omettait-la-clé-visée-par-le-compteur) The contract omitted the key targeted by the counter ·
[196](design_decisions.md#196-deux-aides-qui-mentaient-par-omission-ou-par-promesse) Two help texts that lied, by omission or by promise ·
[197](design_decisions.md#197-deux-garanties-dauthentification-sans-témoin-et-deux-fichiers-de-tests-creux) Two authentication guarantees without a witness ·
[198](design_decisions.md#198-monl-comme-plugin-claude-code-la-cli-plutôt-que-le-mcp-local) monl as a Claude Code plugin ·
[199](design_decisions.md#199-un-compteur-sur-une-fiche-dacteur-frappait-au-hasard) A counter on an actor's profile hit at random ·
[200](design_decisions.md#200-la-grammaire-devient-une-promesse-vérifiable) Grammar compatibility becomes an executable promise ·
[201](design_decisions.md#201-un-texte-required-doit-contenir-autre-chose-que-des-espaces) Required text rejects whitespace without changing stored data ·
[202](design_decisions.md#202-un-compteur-dévénements-appartient-au-serveur) An event counter belongs to the server ·
[203](design_decisions.md#203-les-en-têtes-de-sécurité-enveloppent-aussi-le-site) Security headers wrap the API and static site ·
[204](design_decisions.md#204-une-spec-abîmée-reçoit-une-erreur-monl-jamais-une-trace-python) A damaged spec gets a monl error, never a Python traceback ·
[205](design_decisions.md#205-les-petites-specs-ne-prouvent-pas-la-croissance-du-compilateur) Deterministic generated specs measure compilation growth and exercise every contract route on a real server ·
**AI escape hatch**:[4](design_decisions.md#4-garde-fou-statique-sur-le-code-généré-par-lia) Static safeguard (`custom`) ·
[21](design_decisions.md#21-bloc-landing--front-marketing-sur--deuxième-échappatoire-ia) `landing` block (text safeguard)

**API and data**:[7](design_decisions.md#7-registre-dutilisateurs-réel-register-login) Real user registry ·
[8](design_decisions.md#8-relations-belongsto-et-hasone) `belongsTo`/`hasOne` relations ·
[10](design_decisions.md#10-route-de-liste-get-entite) List route ·
[14](design_decisions.md#14-pagination-sur-la-route-de-liste) Pagination

**Frontend and visual identity**:[15](design_decisions.md#15-identité-visuelle-du-front-minimal) Automatic theme ·
[17](design_decisions.md#17-surcharge-explicite-du-rendu-visuel-bloc-ui) `ui` override ·
[18](design_decisions.md#18-agencement-de-liste-adapté-au-rôle-de-chaque-entité) Layout by entity role ·
[19](design_decisions.md#19-front-minimal-en-react-au-lieu-de-js-impératif) React frontend (since removed, see 22) ·
[20](design_decisions.md#20-unicité-visuelle-par-projet-graine-monl_theme_seed) Per-project visual uniqueness ·
[22](design_decisions.md#22-suppression-du-back-office-ui--monl-ne-génère-plus-de-front-crud) Removal of the `/ui` back office ·
[23](design_decisions.md#23-tableau-de-bord-post-connexion-app-et-corrections-diverses) Post-login dashboard (`/app`) ·
[24](design_decisions.md#24-écosystème-de-capacités--brique-1--capability-auth) Capability ecosystem (brick 1) ·
[25](design_decisions.md#25-écosystème-de-capacités--brique-2--masquage-de-champ-hidden) Field masking (brick 2) ·
[26](design_decisions.md#26-écosystème-de-capacités--brique-3--réputation-dynamique-decrements) Dynamic reputation (brick 3) ·
[27](design_decisions.md#27-écosystème-de-capacités--brique-4--appréciations-increments) Appreciations (brick 4) ·
[28](design_decisions.md#28-écosystème-de-capacités--brique-5--likes-en-catégories-categorized) Likes in categories (brick 5) ·
[29](design_decisions.md#29-écosystème-de-capacités--assemblage-final-réseau-social-anonyme) Final assembly (anonymous social network) ·
[30](design_decisions.md#30-écosystème-de-capacités--pseudonyme-anonyme-généré-generated) Generated anonymous pseudonym (`generated`) ·
[31](design_decisions.md#31-écosystème-de-capacités--accès-à-deux-parties-accessibleby) Two-party access (`accessibleBy`) ·
[32](design_decisions.md#32-migrations-de-schéma-sans-perte-de-données) Schema migrations without data loss ·
[33](design_decisions.md#33-rate-limiting-persistant-multi-workers) Persistent multi-worker rate limiting ·
[34](design_decisions.md#34-enrichissement-du-mode-template-état-de-connexion) Enriching the template mode ·
[35](design_decisions.md#35-frontend--archétypes-dinterface-dérivés-de-la-spec) Frontend: interface archetypes derived from the spec ·
[36](design_decisions.md#36-données-de-démonstration-seed--des-sites-complets) Demo data (`seed`) ·
[37](design_decisions.md#37-frontend--images-robustes-librairies-cdn-et-ton-vitrine) Frontend: robust images, CDN libraries and showcase tone ·
[38](design_decisions.md#38-espace-connecté-interactif--fil-social-façon-twitter) Interactive signed-in area (Twitter-like social feed) ·
[39](design_decisions.md#39-frontend--sections-éditoriales-et-dashboards-lisibles) Editorial sections and readable dashboards ·
[40](design_decisions.md#40-pivot--monl-orchestrateur-dialogue-guidé-contrat-frontend-runupdate) Pivot: monl as an orchestrator ·
[41](design_decisions.md#41-le-pivot-mené-à-terme--boucle-fermée-et-suppression-du-frontend-généré) Pivot carried through (closed loop, generated frontend removed) ·
[42](design_decisions.md#42-monl-import--la-voie-sans-clé-api-abonnement-claudeai) `monl import`: the path without an API key ·
[43](design_decisions.md#43-claude-code--le-travail-directement-dans-le-dossier-cible) Claude Code: working directly in the target folder ·
[44](design_decisions.md#44-modèle-local-pour-comprendre-lutilisateur--linterprète-pas-le-rédacteur) Local model: the interpreter, not the writer ·
[45](design_decisions.md#45-le-dialogue-ouvre-sur-un-catalogue-de-10-modèles-dapplications) The dialogue opens on a catalogue of 10 templates ·
[46](design_decisions.md#46-la-démonstration-complète-ateliervélo-et-ce-quelle-prouve) The complete demo (AtelierVélo)

**Beta 3 and after** — note that numbering restarts at 45: numbers 45
and 46 each name TWO distinct points (a merge left-over, kept as is
because many internal references rely on it) ·
[45](design_decisions.md#45-le-rôle-ne-peut-pas-être-choisi-par-celui-qui-sinscrit-bêta-3) The role is not chosen by the person signing up ·
[46](design_decisions.md#46-le-déterminisme-doit-être-testé-entre-processus-bêta-3) Determinism is tested across processes ·
[47](design_decisions.md#47-découper-le-générateur-avant-de-le-réécrire-bêta-3) Split the generator before rewriting it ·
[48](design_decisions.md#48-une-clause-de-contrat-que-rien-ne-vérifie-nest-pas-une-clause-bêta-3) A clause nothing verifies is not a clause ·
[49](design_decisions.md#49-le-dialogue-montre-son-parcours-avant-de-le-faire-subir-bêta-3) The dialogue shows its route ·
[50](design_decisions.md#50-une-règle-de-propriété-qui-ne-couvre-pas-la-lecture-nen-est-pas-une-bêta-3) An ownership rule must cover reading ·
[51](design_decisions.md#51-un-contrat-qui-dicte-un-port-en-dur-punit-lia-qui-lui-obéit) A contract that hard-codes a port punishes the AI that obeys it ·
[52](design_decisions.md#52-proposer-une-police-que-le-même-contrat-interdit-de-charger) Suggesting a font the same contract forbids loading ·
[53](design_decisions.md#53-le-dialogue-interrogeait-la-structure-jamais-lintention) The dialogue asked about structure, never about intent ·
[54](design_decisions.md#54-le-pivot-a-supprimé-une-intelligence-au-lieu-de-la-déplacer) The pivot removed an intelligence instead of moving it ·
[55](design_decisions.md#55-monl-modélisait-des-données-un-site-est-surtout-du-contenu) monl modelled data; a site is mostly content ·
[56](design_decisions.md#56-cinq-couleurs-plates-ne-font-pas-une-palette) Five flat colours do not make a palette ·
[57](design_decisions.md#57-un-contrat-qui-décrit-mal-le-corps-est-pire-quun-contrat-muet) A contract that misdescribes the body is worse than a silent one ·
[58](design_decisions.md#58-rendre-la-main--sans-épinglage-le-visuel-appartient-à-lia) Handing back control: without pinning, the visuals belong to the AI ·
[59](design_decisions.md#59-où-vit-un-contenu-et-à-quoi-ressemblent-les-images-de-démonstration) Where content lives, and what demo images look like ·
[60](design_decisions.md#60-ce-qui-est-standard-nest-pas-une-question) What is standard is not a question ·
[61](design_decisions.md#61-demander-le-texte-dune-rubrique-plutôt-que-son-existence) Ask for a section's text rather than whether it exists ·
[62](design_decisions.md#62-un-budget-épuisé-nest-pas-une-panne) An exhausted budget is not an outage ·
[63](design_decisions.md#63-mesurer-le-dépôt-pas-seulement-le-faire-passer-au-vert) Measure the repository, do not just turn it green ·
[64](design_decisions.md#64-ce-qui-traverse-mal-la-frontière-et-ce-que-personne-ne-mesurait) What crosses the boundary badly, and what nobody measured ·
[65](design_decisions.md#65-un-paquet-quon-ne-peut-pas-installer-nest-pas-un-paquet) A package that cannot be installed is not a package ·
[66](design_decisions.md#66-rendre-public-ne-pardonne-pas-les-exceptions-à-ses-propres-règles) Going public does not forgive exceptions to its own rules ·
[67](design_decisions.md#67-un-test-qui-échoue-une-fois-sur-deux-est-pire-quun-test-absent) A test that fails one time in two is worse than no test ·
[68](design_decisions.md#68-une-démo-qui-versionne-sa-propre-sortie-se-contredit) A demo that versions its own output contradicts itself ·
[69](design_decisions.md#69-le-garde-fou-ne-doit-pas-dépendre-de-qui-écrit) The safeguard must not depend on who writes ·
[70](design_decisions.md#70-compiler-nest-pas-se-comporter-et-le-câblage-ne-se-relit-pas) Compiling is not behaving, and wiring cannot be proofread ·
[71](design_decisions.md#71-ce-que-le-compilateur-refuse-nétait-presque-pas-mesuré) What the compiler refuses was barely measured ·
[72](design_decisions.md#72-le-compilateur-na-pas-davis-sur-le-visuel) The compiler has no opinion on visuals ·
[73](design_decisions.md#73-un-agent-qui-ne-touche-à-rien-a-quand-même--construit-) An agent that touches nothing has still "built" ·
[74](design_decisions.md#74-encaisser-et-le-montant-qui-ne-vient-jamais-du-client) Collecting payment, and the amount that never comes from the client ·
[75](design_decisions.md#75-payable-accessible-depuis-le-dialogue-et-deux-trous-que-lassemblage-a-montrés) `payable` reachable from the dialogue, and two holes the assembly revealed ·
[76](design_decisions.md#76-un-champ-que-lapi-renvoie-et-que-le-contrat-taisait) A field the API returns and the contract kept quiet about ·
[77](design_decisions.md#77-le-montant-venait-bien-de-la-base--et-cest-le-client-qui-lavait-écrit) The amount did come from the database — and the client had written it ·
[78](design_decisions.md#78-derivedfrom-et-le-champ-serveur-que-la-route-update-réécrivait) `derivedFrom`, and the server field the Update route rewrote ·
[79](design_decisions.md#79-le-refus-cassant--une-boutique-quon-peut-voler-ne-doit-pas-compiler) The breaking refusal: a shop that can be robbed must not compile ·
[80](design_decisions.md#80-le-propriétaire-est-un-compte-et-le-panier-qui-la-révélé) The owner is an account, and the cart that revealed it ·
[81](design_decisions.md#81-la-propriété-transitive--quand-le-contrôle-daccès-devient-une-jointure) Transitive ownership: when access control becomes a join ·
[82](design_decisions.md#82-le-panier-qui-sait-ce-quil-coûte-et-la-faille-du-point-77-arrêtée-à-lentrée) The cart that knows what it costs, and point 77's hole stopped at the door ·
[83](design_decisions.md#83-monl-ne-savait-pas-quun-fichier-existe--le-type-image-et-le-bloc-assets) monl did not know a file exists: the `Image` type and the `assets` block ·
[84](design_decisions.md#84-loutil-qui-écrit-dans-la-spec-et-la-garantie-quil-fallait-énoncer-juste) The tool that writes into the spec, and the guarantee that had to be stated exactly ·
[85](design_decisions.md#85-les-quatre-règles-qui-ne-faisaient-rien) The four rules that did nothing ·
[86](design_decisions.md#86-décompter-ce-que-le-client-a-demandé-et-le-plancher-qui-larme) Counting down what the client asked for, and the floor that arms it ·
[87](design_decisions.md#87-encaisser-une-ligne-et-le-refus-qui-protégeait-dautre-chose-que-ce-quil-disait) Paying for a line, and the refusal that protected something other than what it said ·
[88](design_decisions.md#88-le-back-office-et-les-deux-mensonges-quil-a-fait-tomber) The back office, and the two lies it brought down ·
[89](design_decisions.md#89-la-date-que-personne-ne-peut-se-donner-et-la-colonne-quon-ne-rattrape-pas) The date nobody can give themselves, and the column that cannot be backfilled ·
[90](design_decisions.md#90-on-ne-commande-pas-sans-être-identifié) No ordering without being identified ·
[91](design_decisions.md#91-ce-quon-a-encaissé-ne-se-remodifie-plus) What has been paid can no longer be modified ·
[92](design_decisions.md#92-le-stock-qui-ne-revenait-jamais-et-la-variable-qui-fuyait) The stock that never came back, and the leaking variable ·
[93](design_decisions.md#93-retoucher-sans-reconstruire) Touching up without rebuilding ·
[94](design_decisions.md#94-une-faq-est-une-liste-et-le-contenu-que-le-delta-ne-regardait-pas) A FAQ is a list, and the content the delta did not look at ·
[95](design_decisions.md#95-sinscrire-avec-son-adresse-et-la-forme-canonique-qui-porte-la-brique) Signing up with one's address, and the canonical form that carries the brick ·
[96](design_decisions.md#96-un-statut-nest-pas-du-texte-et-la-fiche-quon-pouvait-effacer) A status is not free text, and the profile that could be deleted ·
[97](design_decisions.md#97-le-message-qui-devinait-à-la-place-de-lagent) The message that guessed in the agent's place ·
[98](design_decisions.md#98-annuler-rend-les-paires-et-la-transition-quon-ne-joue-quune-fois) Cancelling returns the pairs, and the transition played only once ·
[99](design_decisions.md#99-le-rattachement-fantôme-et-la-sécurité-qui-nétait-quun-accident) The phantom attachment, and the security that was only an accident ·
[100](design_decisions.md#100-une-vitrine-qui-montre-des-enfants-et-la-désignation-qui-se-lit) A storefront that shows children, and the designation that can be read ·
[101](design_decisions.md#101-le-type-frère-resté-debout-dix-points-de-plus) The sibling type, left standing for ten more points ·
[102](design_decisions.md#102-le-numéro-que-lhumain-lit-et-dicte) The number a human reads and dictates ·
[103](design_decisions.md#103-voir-le-delta-avant-décrire) Seeing the delta before writing ·
[104](design_decisions.md#104-les-icônes-quon-croyait-interdites) The icons we thought were forbidden ·
[105](design_decisions.md#105-deux-messages-qui-envoyaient-corriger-ce-qui-nétait-pas-cassé) Two messages that sent people to fix what was not broken
