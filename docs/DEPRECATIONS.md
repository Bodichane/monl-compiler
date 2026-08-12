# Compatibilités historiques et dépréciations

Ce fichier fixe les compatibilités conservées pendant la bêta. Une
compatibilité n'est supprimée qu'après une période d'avertissement et un test
de migration.

| Élément | État actuel | Remplacement recommandé |
|---|---|---|
| `*.yaml` | Accepté pour les anciennes specs | Utiliser `*.ml` |
| `landing.mode` / `landing.template` | Acceptés, avertissement à la validation, sans effet sur le backend | Conserver uniquement `landing.brief`, `section` et `question` |
| `run_claude_code()` | Alias conservé pour compatibilité | Utiliser `run_cli_agent(..., agent="claude-code")` ou `generate_with_cli_agent()` |
| `generate_with_claude_code()` | Façade conservée | Utiliser `generate_with_cli_agent()` |

## Règles de retrait

- Aucun élément ne sera supprimé sans recherche d'usage interne et test de
  compatibilité.
- Les avertissements de `landing.mode` et `landing.template` sont déjà émis
  par le validateur.
- Les extensions `.yaml` restent compilables tant que des exemples ou projets
  externes en dépendent.
- Les alias Claude Code seront retirés seulement après une version bêta
  annonçant explicitement la rupture.

Les documents `docs/phase_*.md` décrivent l'historique de conception ; ils ne
constituent pas une description normative de l'architecture courante. Pour
celle-ci, consulter le rapport [CODEBASE_AUDIT.md](../CODEBASE_AUDIT.md) et le
README.
