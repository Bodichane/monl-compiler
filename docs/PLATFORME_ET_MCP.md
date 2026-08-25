# Plateforme web et serveur MCP

Monl conserve une seule autorité de compilation. La ligne de commande, la
plateforme web et le serveur MCP appellent le même pipeline Python :
`monl.cli.compile_project`.

La plateforme ne génère pas de design et n'exécute aucun agent IA. Elle sert à :

1. expliquer la frontière entre interface libre et métier compilé ;
2. saisir ou importer une spécification `.ml` ;
3. valider puis compiler le backend ;
4. inspecter les entités, acteurs et routes du contrat ;
5. télécharger le backend, son schéma SQL et son contrat ;
6. exposer les mêmes opérations aux agents par MCP.

## Lancer la plateforme

Après installation du paquet :

```bash
monl-platform --host 127.0.0.1 --port 8022
```

Ou depuis le dépôt :

```bash
python3 -m monl_platform --port 8022
```

L'espace de compilation vaut `platform-projects/` par défaut. Pour choisir un
autre emplacement :

```bash
MONL_PLATFORM_WORKSPACE=/var/lib/monl monl-platform --host 0.0.0.0
```

Pour une installation conteneurisée, le dépôt fournit une image non-root et
un volume persistant :

```bash
docker compose -f compose.platform.yaml up --build -d
```

Le port n'est exposé que sur `127.0.0.1` : placez un reverse proxy HTTPS
devant le service. `MONL_COOKIE_SECURE=1` exige ce HTTPS. Ne définissez
`MONL_TRUST_PROXY=1` que si ce proxy remplace l'en-tête `X-Forwarded-For` reçu
du public.

Les téléchargements n'incluent jamais `.jwt_secret`. Le backend en génère un
au premier démarrage, ce qui évite de transporter un secret de la plateforme.

## API web

| Méthode | Route | Effet |
|---|---|---|
| `GET` | `/health` | État du service |
| `GET` | `/ready` | Disponibilité de SQLite et du stockage |
| `POST` | `/api/auth/register` | Crée un compte et une session |
| `POST` | `/api/auth/login` | Ouvre une session |
| `POST` | `/api/auth/logout` | Révoque la session active |
| `GET` | `/api/templates` | Catalogue des dix modèles métier |
| `POST` | `/api/validate` | Validation sans écriture persistante |
| `POST` | `/api/compile` | Backend et contrat dans un projet opaque |
| `GET` | `/api/projects` | Projets du compte actif |
| `GET` | `/api/projects/{id}` | Manifeste et résumé |
| `GET` | `/api/projects/{id}/contract` | Contrat frontend complet |
| `GET` | `/api/projects/{id}/download` | Archive ZIP sans secret |
| `POST` | `/api/keys` | Crée une clé MCP affichée une fois |
| `DELETE` | `/api/keys/{id}` | Révoque une clé MCP |
| `POST` | `/mcp` | Transport MCP HTTP avec clé Bearer |

La plateforme n'accepte jamais de chemin de sortie fourni par le client. Une
spec est limitée à 256 ko et chaque projet reçoit un identifiant UUID opaque.

## MCP local, par stdio

```json
{
  "mcpServers": {
    "monl": {
      "command": "monl-mcp"
    }
  }
}
```

Depuis le dépôt, la commande équivalente est :

```bash
python3 -m monl_platform.mcp_server
```

## Outils MCP

- `monl_list_templates` : découvrir les modèles métier ;
- `monl_validate_spec` : obtenir les erreurs du vrai parseur et de l'audit ;
- `monl_compile_backend` : compiler et recevoir l'identifiant du projet ainsi
  que le chemin HTTP de téléchargement ;
- `monl_inspect_contract` : lire le manifeste et le contrat complet.

## Garde-fous d'exploitation

- mots de passe `scrypt`, sessions et clés stockées uniquement sous forme
  d'empreintes ;
- projets isolés par compte, expirant après 30 jours par défaut ;
- cinq tentatives de connexion ou inscription par minute et par IP ;
- dix compilations par heure et par compte, 120 appels MCP par minute ;
- compteurs persistés dans SQLite et partagés entre workers web ;
- au plus deux compilations simultanées par processus web ;
- chaque compilation s'exécute dans un sous-processus borné en temps CPU,
  mémoire, taille de fichiers et nombre de descripteurs ;
- le conteneur est non-root, sans capabilities, en lecture seule hors `/data`.

Les valeurs d'exploitation se règlent avec
`MONL_PROJECT_RETENTION_DAYS`, `MONL_MAX_CONCURRENT_COMPILES`,
`MONL_COMPILE_TIMEOUT_SECONDS`, `MONL_COMPILE_CPU_SECONDS`,
`MONL_COMPILE_MEMORY_MB` et `MONL_COMPILE_OUTPUT_MB`.
