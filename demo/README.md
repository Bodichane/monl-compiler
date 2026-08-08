# StudioNova — la démonstration versionnée

Le portfolio d'un photographe : galerie publique de projets, formulaire de
contact, zone d'administration. Produit par le parcours complet de monl-compiler, du
dialogue guidé jusqu'à l'interface.

**Deux fichiers, les deux seuls écrits :**

| Fichier | Écrit par |
|---|---|
| `spec.ml` | le dialogue guidé, à partir des réponses de l'auteur |
| `frontend/` | une IA d'interface, contre le contrat produit par monl-compiler |

Tout le reste — backend, contrat, brief, état du projet — se recalcule depuis
`spec.ml` en une seconde, et se trouve donc dans le dossier de compilation, pas
ici. Ces neuf fichiers ont été versionnés jusqu'au point 68 du journal ; ils
avaient silencieusement vieilli, le contrat livré datant d'avant trois
évolutions du compilateur.

## Le refaire tourner

```bash
monl compile demo/spec.ml --output /tmp/studionova
```

```bash
cp -r demo/frontend /tmp/studionova/
```

```bash
monl run /tmp/studionova
```

## Ce que la suite de tests en fait

- `tests/test_demo.py` recompile cette spec, y dépose ce frontend, et exige que
  l'ensemble passe la vérification de cohérence **et** le smoke test
  comportemental — l'interface est réellement exécutée dans jsdom contre un
  serveur éphémère. La démo ne peut donc pas pourrir en silence.
- `tests/test_design_contract.py` s'en sert pour prouver la moitié la moins
  intuitive du point 58 : cette spec n'épingle aucun thème, l'IA s'est autorisé
  une palette entièrement différente de celle qui lui était proposée, et monl-compiler
  doit l'accepter sans un mot.

## Ce qu'elle montre du langage

`rule Project.Read public` ouvre la galerie aux visiteurs sans compte ;
`rule Message.Create public` ouvre le formulaire de contact tout en gardant les
messages reçus privés ; le bloc `landing` porte le brief et les rubriques
éditoriales — « À propos », « Services » — qu'aucune entité ne pourrait
fournir, puisque ce sont des textes et non des données.
