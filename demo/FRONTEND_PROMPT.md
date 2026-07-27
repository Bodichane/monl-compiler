# Brief frontend — AtelierVelo (généré par monl)

**Brief produit :** Une boutique d'accessoires vélo, réparation et pièces détachées.

Vous êtes une IA spécialisée en interfaces. Générez le frontend de
l'application **AtelierVelo** en respectant STRICTEMENT le contrat
ci-dessous. Le backend existe déjà et ne doit pas être modifié.

## Direction de design (IMPOSÉE par la spec — vérifiée au smoke test)
Système « atelier » — fond `#F1F3EE`, surfaces `#FBFCFA`, texte `#101C24`, accents `#D9F227` / `#A8412A`, rayon `0px`.
Typographies : titres 'Helvetica Neue', Helvetica, Arial, sans-serif, corps 'Helvetica Neue', Helvetica, Arial, sans-serif — piles système, aucune police à télécharger : c'est le choix des familles et leur traitement (graisses, interlettrage, échelle) qui portent l'identité, pas un fichier distant. Vous écrivez le HTML/CSS ; la spec ÉPINGLE ce thème : ces cinq couleurs doivent apparaître telles quelles dans votre CSS, le smoke test le vérifie. Le reste — mise en page, rythme, échelles — demeure votre décision.

**Tons dérivés — la palette n'est pas plate.** Déduits des cinq couleurs
ci-dessus, à employer plutôt que d'improviser des gris :
- `#5D6569` texte secondaire (légendes, méta, libellés)
- `#D2D5D2` filets, séparateurs, contours de champs
- `#EFF1EF` second niveau de surface (en-têtes, zones inertes)
- `#EEF3D2` fond teinté (étiquettes, état sélectionné)
- `#B5CB26` survol et état actif de l'accent

Une interface sans texte atténué, sans filet et sans état de survol paraît
plate quelle que soit la qualité de sa palette. Ces cinq tons existent pour
qu'aucune de ces trois choses ne manque.

## Règles non négociables
- Écrire tous les fichiers dans `frontend/`, avec `frontend/index.html`
  comme point d'entrée (HTML/CSS/JS statiques, aucun build requis).
- Frontend AUTONOME : aucune librairie CDN, aucun script externe — tout le
  JS/CSS vit dans `frontend/` (c'est ce qui rend le smoke test possible).
- N'appeler QUE les routes listées plus bas, en chemins RELATIFS —
  `fetch('/entite')`, JAMAIS `fetch('http://127.0.0.1:8000/entite')`. Le
  frontend est servi sur `/site` par le serveur qui porte l'API : l'origine
  est déjà la bonne. Une URL absolue avec un port codé en dur casse au
  premier `monl run --port` et fait échouer le smoke test.
- Authentification : `POST /register` (username, password 8+, actor parmi
  ['Customer']), `POST /login` → token JWT, à
  envoyer ensuite en en-tête `Authorization: Bearer <token>` sur toute route
  non publique. Les rôles déclarés mais absents de cette liste
  (['Admin'])
  sont provisionnés hors ligne : ils se connectent par `/login`, jamais par
  `/register`.
- Les routes de liste sont paginées : `?limit=&offset=`, réponse
  `{status, total, limit, offset, data}`.
- Ne jamais envoyer un champ marqué « généré serveur » à la création.
- Ne pas modifier `app.py`, `schema.sql`, la spec `.ml` ni les autres
  artefacts monl.


## Entités
### Product
_Forme conseillée : boutique — le prix est l'information décisive : il doit rester lisible sans effort à côté de chaque article, avec un appel à l'action clair._
_Proche de : une vitrine de commerce en ligne standard : liste filtrable, fiche produit dense, panier explicite._
Ce qu'un visiteur s'attend à y trouver :
  - prix et disponibilité visibles sans défiler
  - un appel à l'action évident sur chaque article
  - plusieurs vues du produit si les données le permettent
  - la description structurée (usage, matière, dimensions)
  - `name: String` (TITRE — l'identifie d'un coup d'œil; requis)
  - `price: Money` (PRIX)
  - `description: Text` (DESCRIPTION — le texte long)
  - `imageUrl: String` (MÉDIA — l'image de l'enregistrement)
  - `category: String` (CATÉGORIE — bon pour un filtre)
  - `stock: Integer` (DISPONIBILITÉ — à montrer près du prix, pas en note de bas de page)
### Order
_Forme conseillée : liste — rien à mettre en vitrine ici, ou collection réservée aux comptes autorisés : lecture dense et rapide, en rangées plutôt qu'en cartes._
_Proche de : un tableau de bord d'administration, une grille de gestion interne, un tableau de suivi._
Ce qu'un visiteur s'attend à y trouver :
  - des rangées scannables, alignées en colonnes
  - un tri et une recherche dès que la liste s'allonge
  - les actions d'édition à portée, sans changer de page
  - un état vide qui explique quoi faire
  - `total: Money` (PRIX; requis)
  - `status: String` (TITRE — l'identifie d'un coup d'œil)
  - `note: Text` (DESCRIPTION — le texte long)
### Customer
_Forme conseillée : liste — rien à mettre en vitrine ici, ou collection réservée aux comptes autorisés : lecture dense et rapide, en rangées plutôt qu'en cartes._
_Proche de : un tableau de bord d'administration, une grille de gestion interne, un tableau de suivi._
Ce qu'un visiteur s'attend à y trouver :
  - des rangées scannables, alignées en colonnes
  - un tri et une recherche dès que la liste s'allonge
  - les actions d'édition à portée, sans changer de page
  - un état vide qui explique quoi faire
  - `displayName: String` (TITRE — l'identifie d'un coup d'œil; requis)

## Routes disponibles
- `GET /customer` — List Customer — JWT (Customer)
- `POST /customer` — Create Customer — JWT (Customer) — corps : `{displayName}`
- `DELETE /customer/{id}` — Delete Customer — JWT (Customer)
- `GET /customer/{id}` — Read Customer — JWT (Customer)
- `PUT /customer/{id}` — Update Customer — JWT (Customer) — corps : `{displayName}`
- `GET /order` — List Order — JWT (Admin, Customer)
- `POST /order` — Create Order — JWT (Customer) — corps : `{total, status, note}`
- `DELETE /order/{id}` — Delete Order — JWT (Customer)
- `GET /order/{id}` — Read Order — JWT (Admin, Customer)
- `PUT /order/{id}` — Update Order — JWT (Customer) — corps : `{total, status, note}`
- `GET /product` — List Product — public
- `POST /product` — Create Product — JWT (Admin) — corps : `{name, price, description, imageUrl, category, stock}`
- `DELETE /product/{id}` — Delete Product — JWT (Admin)
- `GET /product/{id}` — Read Product — public
- `PUT /product/{id}` — Update Product — JWT (Admin) — corps : `{name, price, description, imageUrl, category, stock}`

## Contrat machine-lisible complet
Le fichier `frontend_contract.json` (même dossier) contient la version
exhaustive de ce contrat — s'y référer en cas de doute.

---

## Vous lisez ceci dans une conversation (claude.ai, sans clé API) ?
Générez le frontend demandé, puis rendez-le sous une forme téléchargeable :
soit un fichier ZIP contenant les fichiers (index.html à la racine ou dans
un unique sous-dossier), soit un `index.html` AUTONOME (CSS et JS inclus
dans le fichier). L'utilisateur l'installera ensuite avec :
`monl import <fichier téléchargé> <dossier du projet>` — monl
re-vérifiera automatiquement l'ensemble (cohérence + smoke test) et, en cas
d'erreurs, elles vous seront recollées ici pour correction.
