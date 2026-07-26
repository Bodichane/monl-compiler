# Brief frontend — AtelierVelo (généré par monl)

**Brief produit :** Une boutique d'accessoires vélo, réparation et pièces détachées.

Vous êtes une IA spécialisée en interfaces. Générez le frontend de
l'application **AtelierVelo** en respectant STRICTEMENT le contrat
ci-dessous. Le backend existe déjà et ne doit pas être modifié.

## Direction de design (IMPOSÉE par la spec — vérifiée au smoke test)
Système « atelier » — fond `#F1F3EE`, surfaces `#FBFCFA`, texte `#101C24`, accents `#D9F227` / `#A8412A`, rayon `0px`.
Typographies : titres 'Helvetica Neue', Helvetica, Arial, sans-serif, corps 'Helvetica Neue', Helvetica, Arial, sans-serif (piles système : aucune police à télécharger). Vous écrivez le HTML/CSS ; la spec ÉPINGLE ce thème : ces cinq couleurs doivent apparaître telles quelles dans votre CSS, le smoke test le vérifie.

## Règles non négociables
- Écrire tous les fichiers dans `frontend/`, avec `frontend/index.html`
  comme point d'entrée (HTML/CSS/JS statiques, aucun build requis).
- Frontend AUTONOME : aucune librairie CDN, aucun script externe — tout le
  JS/CSS vit dans `frontend/` (c'est ce qui rend le smoke test possible).
- N'appeler QUE les routes listées plus bas, sur `http://127.0.0.1:8000`.
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
  - `name: String` (requis)
  - `price: Money`
  - `description: Text`
  - `imageUrl: String`
  - `category: String`
  - `stock: Integer`
### Order
  - `total: Money` (requis)
  - `status: String`
  - `note: Text`
### Customer
  - `displayName: String` (requis)

## Routes disponibles
- `GET /customer` — List Customer — JWT (Customer)
- `POST /customer` — Create Customer — JWT (Customer)
- `DELETE /customer/{id}` — Delete Customer — JWT (Customer)
- `GET /customer/{id}` — Read Customer — JWT (Customer)
- `PUT /customer/{id}` — Update Customer — JWT (Customer)
- `GET /order` — List Order — JWT (Admin, Customer)
- `POST /order` — Create Order — JWT (Customer)
- `DELETE /order/{id}` — Delete Order — JWT (Customer)
- `GET /order/{id}` — Read Order — JWT (Admin, Customer)
- `PUT /order/{id}` — Update Order — JWT (Customer)
- `GET /product` — List Product — public
- `POST /product` — Create Product — JWT (Admin)
- `DELETE /product/{id}` — Delete Product — JWT (Admin)
- `GET /product/{id}` — Read Product — public
- `PUT /product/{id}` — Update Product — JWT (Admin)

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
