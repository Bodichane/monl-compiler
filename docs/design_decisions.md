# MonLang — Choix de conception assumés

Ce document répertorie les règles strictes et opinionées du compilateur — ce
qu'elles interdisent, pourquoi ce choix a été fait, et comment le contourner
quand le besoin est légitime. Objectif : servir à la fois de documentation
pour qui écrit une spec MonLang, et de mémoire pour le mainteneur du projet.

---

## 1. Collision de privilèges (`CRITICAL_COLLISION`)

**Ce qu'elle interdit :** par défaut, deux acteurs différents ne peuvent pas
avoir le droit d'effectuer la même action d'écriture (`Create`, `Update`,
`Delete`) sur la même entité. La compilation échoue si c'est le cas.

**Pourquoi :** dans un système où chaque route n'a historiquement qu'un seul
acteur autorisé, permettre silencieusement à plusieurs acteurs d'accéder à la
même action rendrait difficile de savoir, en lisant la spec, qui a réellement
le droit de faire quoi. La règle stricte force à rendre ce partage explicite
plutôt qu'accidentel.

**Comment le contourner légitimement :** déclarer une règle `sharedBy` :
```
rule Post.Delete sharedBy Admin, Moderator
```
Le compilateur fusionne alors les deux workflows en une seule route, avec un
contrôle d'accès qui accepte n'importe lequel des acteurs listés. Voir
`exemples/06_moderation_shared.yaml` pour un exemple complet.

---

## 2. Restriction de champ (`restrictedTo`)

**Ce qu'elle interdit :** une règle `rule Entite.champ restrictedTo Acteur`
marque un champ comme sensible. Si un bloc `custom` (logique IA) appelé par
un acteur différent de celui déclaré utilise ce champ en entrée, l'audit de
sécurité statique émet un avertissement `[SECURITY_AUDIT]`.

**Pourquoi :** empêcher qu'une donnée sensible (email, information privée...)
soit exposée à la logique métier générée par IA pour un acteur qui ne devrait
pas y avoir accès, même indirectement via un bloc `custom`.

**Comment le contourner légitimement :** ce n'est pas un blocage strict de la
compilation — c'est un avertissement. Si l'usage est volontaire, il suffit de
documenter pourquoi dans la spec (aucune syntaxe d'acquittement n'existe
encore pour faire taire l'avertissement).

---

## 3. Avertissement sur les suppressions non-`Admin` (`CRITICAL_WARNING`)

**Ce qu'elle signale :** tout workflow permettant à un acteur autre que
`Admin` d'exécuter une action `Delete` déclenche un avertissement (pas un
blocage).

**Pourquoi :** la suppression est l'action la plus risquée du CRUD de base
(irréversible sans sauvegarde) — le compilateur attire l'attention dessus
plutôt que de la laisser passer silencieusement, sans pour autant l'interdire
puisque c'est un besoin métier légitime dans de nombreux cas (un `User` qui
supprime ses propres données, par exemple).

**Comment réagir :** ce n'est qu'un signal — à charge du développeur de la
spec de vérifier que la suppression est bien protégée au niveau infra
(sauvegarde, log d'audit, etc.), ce que le compilateur ne peut pas garantir
depuis la spec seule.

---

## 4. Garde-fou statique sur le code généré par l'IA

**Ce qu'il interdit :** le code Python produit par le LLM pour remplir un
bloc `custom` est rejeté s'il contient :
- un import parmi une liste bannie (`os`, `subprocess`, `socket`, `requests`,
  `pickle`, etc. — modules réseau, système, ou de désérialisation dangereuse)
- un appel à une fonction bannie (`eval`, `exec`, `open`, `__import__`,
  `getattr`/`setattr`, etc.)
- une requête SQL construite par f-string, concaténation `+` ou `%` à
  l'intérieur d'un appel `.execute()`
- une boucle `while True`/`while 1` sans `break` détectable

**Pourquoi :** le bloc `custom` est pensé comme une zone de logique métier
pure (transformer des données, appliquer une règle de calcul) — il ne doit
jamais avoir besoin d'accéder au système de fichiers, au réseau, ou à la base
de données directement. Tout ce qui ressemble à une tentative de sortir de ce
périmètre est bloqué par défaut, sans exception.

**Comment le contourner légitimement :** ce n'est volontairement pas prévu.
Si un besoin métier réel nécessite un accès réseau ou fichier depuis la
logique custom, ce n'est plus un cas d'usage pour le bloc `custom` — il faut
l'implémenter comme une route à part entière dans le socle déterministe, où
le code n'est pas généré par un LLM et peut donc être audité normalement par
un humain avant déploiement.

---

## 5. Contrôle d'accès JWT, sans granularité au-delà de l'acteur

**Ce qu'il permet/interdit :** le contrôle d'accès généré est basé
uniquement sur l'acteur (le rôle) porté par le token JWT — il n'y a pas de
notion de propriétaire d'une ressource (« seul l'auteur de ce Post peut le
modifier », par exemple).

**Pourquoi :** c'est une limite du modèle actuel, pas un choix de sécurité
délibéré — le DSL ne permet pas encore d'exprimer une règle de propriété
individuelle, seulement des règles par rôle.

**Statut :** limite connue, pas encore de syntaxe prévue pour l'exprimer.
À considérer pour une future évolution du DSL si le besoin se présente
(ex. une syntaxe `rule Post.Update ownedBy author` référençant une relation).
