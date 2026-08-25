# Identité Monl

Monl compile des règles métier en un backend exact. L'identité est
**typographique** : charbon, crème, et un seul cuivre réservé à ce qui est
actionnable. Le monde de référence est l'imprimerie, pas le terminal — une
spécification se lit avant de s'exécuter.

## Signe

Deux fûts et une barre de compilation. Bouts **carrés**, joints **vifs** : le
trait vient du plomb, il ne cherche ni la rondeur ni l'écran.

Fichier source : [`brand/monl-mark.svg`](brand/monl-mark.svg).

**Le signe est tracé en `currentColor`, sans fond.** C'est la règle qui compte,
et elle vient d'un défaut mesuré : le signe d'origine était le texte `m/` dans
un carré `#17141a`, lequel tombait à **1,09:1** contre le fond sombre. La marque
avait donc deux formes — un carré le jour, un glyphe flottant la nuit — et
dépendait d'une police installée. Un tracé en `currentColor` prend la couleur du
texte : il tient sur n'importe quel fond, dans les deux thèmes, et jusqu'à 16 px.

**Une seule exception, le favicon.** Il vit dans un onglet, hors de toute page,
sans couleur à hériter : il porte donc sa pastille et ses tracés en dur. C'est
la seule place où un fond est justifié — un onglet en attend un.

- Ne pas modifier les proportions ni l'épaisseur des tracés.
- Ne pas arrondir les extrémités : le bout carré EST le signe.
- Ne pas remplacer les tracés par des caractères typographiques.
- Conserver autour du signe un espace libre au moins égal au quart de sa largeur.
- Taille minimale : 16 px pour le signe, 96 px pour le lockup complet.

## Palette

| Rôle | Clair | Sombre |
|---|---|---|
| Encre | `#2E2B25` | `#F9F4ED` |
| Papier | `#F9F4ED` | `#171512` |
| Surface | `#FFFDF9` | `#211E1A` |
| Texte secondaire | `#665F55` | `#B9B0A5` |
| Séparateur | `#DDD4C8` | `#403B34` |
| Bordure de contrôle | `#8B8175` | `#786F64` |
| Action principale | `#2E2B25` | `#F9F4ED` |
| Accent cuivre | `#924821` | `#E5A45F` |
| Fond de code | `#2E2B25` | `#0F0E0C` |
| Alerte | `#B3123C` | `#FF90A6` |

**L’action principale reste monochrome.** Boutons, liens et états actifs
reprennent l’encre ou le crème du logo. Le cuivre est réservé aux repères fins :
surtitres, progression et syntaxe. Il ne remplit ni carte ni grande section.

**Deux valeurs pour un seul cuivre.** `#924821` sur papier (6,62:1), `#E5A45F`
sur fond sombre (6,59:1). Le cuivre de jour serait trop sombre la nuit, et
l'inverse illisible le jour : c'est la même couleur à deux valeurs, pas deux
accents à entretenir.

**Deux bordures, pas une.** `Séparateur` délimite une carte ou une ligne de
tableau ; `Bordure de contrôle` entoure ce qui se clique ou se remplit, et tient
**3:1** parce que WCAG 1.4.11 l'exige d'un composant d'interface. Confondre les
deux donne des boutons secondaires et des champs qu'on ne distingue pas du fond.

**L'alerte est un rouge d'encre, pas un orangé.** Il doit se lire comme une
autre encre, pas comme une variation du cuivre d'action.

Aucun état ne se lit par la couleur seule : un libellé ou une icône le porte
toujours aussi.

## Où vivent ces valeurs

Dans `src/monl_platform/theme.py`, et **nulle part ailleurs**. Les pages
n'écrivent que des variables (`var(--brand)`, `var(--code-muted)`) : c'est ainsi
qu'un changement d'identité se fait en un endroit. Une refonte antérieure avait
laissé cinq verts en dur dans la console — ils ont survécu à un changement
complet de palette sans que rien ne le signale. `tests/test_platform_marque.py`
l'interdit désormais, et ne cite lui-même aucune couleur : il mesure des
contrastes depuis les variables réellement déclarées, ce qui le laisse valable
d'une direction à l'autre.

## Typographie et ton

Les textes emploient la police sans serif du système, les données techniques sa
monospace. Aucune police distante : la plateforme doit s'ouvrir derrière un
pare-feu, et c'est déjà l'autonomie qu'elle exige des frontends qu'elle fait
produire.

Le ton est direct et factuel : verbe d'action, résultat observable, aucune
promesse vague. On écrit « Compiler le backend » plutôt que « Commencer la
magie ».
