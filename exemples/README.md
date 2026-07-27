# Exemples de spécifications

**Cinq fichiers `.ml`, une page chacun : la description complète de cinq
applications.** C'est la seule chose écrite à la main. Le schéma de base, l'API
REST, l'authentification, le contrôle d'accès et le contrat frontend en sont
dérivés à la compilation.

| Spécification | Ce qu'elle décrit | Ce qu'elle démontre du langage |
|---|---|---|
| `01_portfolio.ml` | Galerie publique + zone d'administration | `public` en lecture, formulaire de contact ouvert en écriture seule, bloc `seed` |
| `02_boutique.ml` | Catalogue et commandes | Deux acteurs, `ownedBy` sur les commandes, thème épinglé |
| `03_reseau_social.ml` | Réseau social anonyme | Le plus dense : `generated` (pseudonyme), `hidden`, `categorized`, `increments` / `decrements`, `accessibleBy` (messagerie privée) |
| `04_kanban.ml` | Tâches d'équipe | Propriété par enregistrement, lecture comprise |
| `05_classement.ml` | Classement communautaire | Compteurs transactionnels : un vote fait monter un score |

## Les lire, les compiler

```bash
monl compile exemples/01_portfolio.ml --output /tmp/portfolio
```

```bash
monl run /tmp/portfolio
```

Chaque fichier est commenté : ce qui est déclaré, et **pourquoi** cette règle
plutôt qu'une autre. Les lire dans l'ordre donne une progression du plus simple
au plus complet.

## Ce que la suite de tests en fait

`tests/test_compile_all.py` compile les cinq à chaque exécution, et
`tests/test_exploit_all.py` rejoue sur chacun l'audit offensif — usurpation de
rôle, JWT forgé, élévation de privilège. Un exemple ne peut donc pas cesser de
compiler, ni devenir vulnérable, sans que la CI le dise.

C'est aussi ce qui les rend fiables comme documentation : une syntaxe montrée
ici est nécessairement une syntaxe que le compilateur accepte encore.
