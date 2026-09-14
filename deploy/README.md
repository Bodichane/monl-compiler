# Déploiement de la plateforme

Ces fichiers préparent un déploiement Docker/Podman derrière un reverse proxy
TLS. Ils ne contiennent aucun secret et ne remplacent pas la configuration du
DNS ou du fournisseur d'hébergement.

Les commandes utilisent Docker Compose v2 (`docker compose`). Avec Podman,
installer au préalable un fournisseur Compose compatible (`podman-compose`,
par exemple), puis lancer les scripts avec `CONTAINER_RUNTIME=podman` ; le
script ajoute alors le format d'image Docker nécessaire au transport du
`HEALTHCHECK`. Une machine Docker reste la voie la plus simple.

La CI construit aussi `Dockerfile.platform`, démarre l’image et vérifie son
healthcheck sur chaque push : une régression de packaging ou de readiness est
détectée avant le déploiement manuel.

Sur un tag `v*`, le workflow d’image publie en plus
`ghcr.io/bodichane/monl-platform` après ce contrôle. Pour l’utiliser, rendre
le paquet GHCR accessible au serveur puis renseigner `MONL_PLATFORM_IMAGE` avec
un tag précis dans `.env`, puis lancer :

```bash
USE_PREBUILT_IMAGE=1 scripts/deploy_platform.sh
```

L’image locale reste le repli par défaut.
En mode `USE_PREBUILT_IMAGE=1`, le script refuse `latest` et les références
sans tag ; utiliser un tag immuable de release ou un digest `sha256`.

## Préparer la machine

```bash
git clone https://github.com/Bodichane/monl-compiler.git
cd monl-compiler
cp .env.platform.example .env
$EDITOR .env
chmod 600 .env
python3 scripts/check_platform_env.py .env
```

Renseigner au minimum `MONL_PLATFORM_DOMAIN` et
`MONL_PLATFORM_PUBLIC_URL`. Si aucun fournisseur OAuth n'est activé,
`MONL_PLATFORM_OAUTH_STATE_SECRET` peut rester vide. Ne jamais mettre de
valeur réelle dans le dépôt.

Le DNS doit pointer la valeur de `MONL_PLATFORM_DOMAIN` et son wildcard
(`*.MONL_PLATFORM_DOMAIN`, en remplaçant ce texte par le domaine réel) vers la
machine. Le wildcard est nécessaire pour les hôtes attribués aux projets
compilés.

Le pare-feu de la machine ne doit exposer que TCP 80 et 443. Le port 8022 est
lié à `127.0.0.1` et ne doit jamais être ouvert directement sur Internet.

## Démarrer

Le chemin recommandé enchaîne la validation, le contrôle Compose, le build,
le démarrage, la readiness locale et l'état `healthy` de la sauvegarde :

```bash
scripts/deploy_platform.sh
```

Les commandes équivalentes restent disponibles si un opérateur doit
intervenir entre deux étapes.

Le port 8022 reste privé. Installer le reverse proxy et copier
`deploy/nginx/monl-platform.conf.example` dans la configuration Nginx après
avoir remplacé le domaine et installé le certificat TLS.

Après activation du proxy :

```bash
curl -fsS https://monl.example.com/health
curl -fsS https://monl.example.com/ready
./scripts/smoke_platform.sh https://monl.example.com
```

## Vérification avant ouverture

- inscription, connexion et récupération par code de secours ;
- compilation d'une spec et téléchargement de l'archive ;
- création puis révocation d'une clé MCP ;
- isolation des projets entre deux comptes ;
- réponse `503` explicite si un OAuth déclaré manque de secret ;
- sauvegarde créée dans `/backups`, puis restauration testée sur une copie ;
- état `healthy` du service `sauvegarde` après sa première copie ;
- alerte externe branchée sur `/ready` ;
- certificat renouvelable et logs de proxy configurés.

La sauvegarde compose reste sur la même machine : exporter les fichiers du
volume `monl-platform-backups` vers un stockage séparé avant l'ouverture.

Pour copier les sauvegardes vers un dossier de l'hôte sans connaître le nom
préfixé du volume Compose :

```bash
sudo install -d -m 700 /var/backups/monl
sudo scripts/export_platform_backups.sh /var/backups/monl
```

Synchroniser ensuite `/var/backups/monl` vers un stockage hors machine
(restic, S3, rsync vers un autre hôte, etc.). Le script ne modifie jamais le
volume source et refuse un chemin d'export relatif ou la racine `/`.
