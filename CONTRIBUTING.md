# Travailler sur monl

> **Statut.** Dépôt public, logiciel **propriétaire** (voir [LICENSE](LICENSE)).
> Les contributions extérieures ne sont pas ouvertes pour l'instant. Ce document
> décrit comment travailler sur le dépôt — il s'adresse au mainteneur, à un
> futur collaborateur autorisé, et à toute IA de développement travaillant ici.
> Les rapports de bug et remarques restent bienvenus dans les *issues*.

## Mise en place

```bash
pipx install -e .        # ou : pip install -e . --break-system-packages
python3 -m pytest tests/ -q
```

La suite dure environ deux minutes : elle démarre de vrais serveurs. C'est
délibéré, voir ci-dessous.

## La règle non négociable

**Chaque changement est prouvé par exécution réelle, jamais par relecture de code
seule.** Compiler pour de vrai, relancer un vrai serveur, faire de vrais appels,
lancer la suite.

Ce n'est pas un principe décoratif. Plusieurs bugs réels du projet — ordre des
contraintes `FOREIGN KEY`, collision avec un mot-clé SQL réservé, sur-échappement
de backslash entre couches de templating, un mécanisme de clé étrangère qui
décrémentait le mauvais enregistrement — ne se seraient **jamais** révélés par
lecture. Les tests démarrent donc des serveurs éphémères et exécutent le vrai
dialogue plutôt que de le simuler ; c'est pourquoi ils sont lents.

Corollaire : un test qui ne peut pas échouer ne vaut rien. Si vous écrivez un
garde-fou, vérifiez qu'il **voit** encore quelque chose — un contrôle devenu muet
est pire qu'un contrôle absent, parce qu'il rassure.

## Avant d'ouvrir une pull request

```bash
ruff check src tests                                   # zéro signalement attendu
python3 -m pytest tests/ -q --cov=src --cov-report=term-missing
python3 -m pytest tests/test_architecture.py -q        # frontières d'architecture
```

La CI rejoue tout cela sur Python 3.10 et 3.12, et `main` est protégée : rien ne
fusionne sans que les deux vérifications passent.

## Les règles du dépôt

**Le journal d'abord.** [`docs/design_decisions.md`](docs/design_decisions.md)
contient 66 points, chacun expliquant le *pourquoi* d'une règle, pas seulement le
*quoi*. **Le consulter avant d'ajouter quoi que ce soit** : plusieurs pièges ne
sont pas devinables depuis le code. Toute décision structurante y gagne un point
numéroté, avec ce qui a été écarté et pourquoi.

**Les exceptions portent leur raison.** Une exception `ruff` sans justification
écrite dans `pyproject.toml`, un `# noqa` orphelin, une clause de contrat que
rien ne vérifie : trois façons de rouvrir une porte que le projet a fermée
exprès. Une clause que rien ne vérifie n'est pas une clause.

**Les frontières sont exécutables.** Le compilateur (`parser`, `ast_validator`,
`generator`) ignore l'orchestrateur ; `tui.py` ne porte aucune logique de
dialogue ; `app_templates.py` est de la donnée, pas du code.
`tests/test_architecture.py` le vérifie — ne le contournez pas, corrigez la
dépendance.

**Le déterminisme est un acquis.** Aucune IA, aucun appel réseau dans le
compilateur : même spec, même sortie, à l'octet près. La seule IA du cycle de vie
construit le frontend, à partir du contrat.

**Nettoyer après une compilation manuelle** (la suite de tests, elle, ne salit
plus la racine) :

```bash
rm -f app.py schema.sql sandbox_ai.py manage.py .jwt_secret .monl_theme_seed *.db \
      frontend_contract.json FRONTEND_PROMPT.md FRONTEND_UPDATE_PROMPT.md monl.json serve.py
```

## Messages de commit

Format `type(portée): résumé à l'impératif`, puis un corps qui explique le
**pourquoi** — pas la liste des fichiers touchés, que `git diff` donne déjà. Si
le changement correspond à un point du journal, le citer par son numéro.

```
fix(cohérence): le scellé du backend n'était mesuré par rien

Point 64 du journal. check_coherence vérifiait l'empreinte de la spec et
celle du contrat, mais seulement l'EXISTENCE de app.py — une retouche
manuelle passait sans un mot, pendant que 'monl run' affichait
« Cohérence statique vérifiée ».
```

## Où intervenir

| Ce que vous voulez faire | Où |
|---|---|
| Ajouter une question au dialogue | `src/monl/dialogue_engine.py` |
| Ajouter ou modifier un modèle d'application | `src/monl/app_templates.py` |
| Nouveau mot-clé du langage `.ml` | `src/monl/parser.py`, puis `ast_validator.py` |
| Changer ce que le backend génère | le module concerné dans `src/monl/generator/` |
| Changer ce que l'IA frontend reçoit | `src/monl/frontend_contract.py` |
| Ajouter une vérification au lancement | `src/monl/cli.py` (statique) ou `smoke_test.py` (réelle) |
| Comprendre *pourquoi* une règle existe | `docs/design_decisions.md` |
