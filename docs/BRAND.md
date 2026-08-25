# Identité Monl

Monl est un compilateur de règles métier. Son monde d'origine est la ligne de
commande, et l'identité l'assume : charbon, lin et **ambre**. Pas de vert — la
couleur par défaut de tout outil d'infrastructure, au point qu'elle ne dit plus
rien. Pas de bleu SaaS non plus.

## Signe

Un `m` construit sort d'un chevron de prompt, suivi d'un curseur. Trois formes,
une seule idée : quelque chose entre, quelque chose sort, et la machine attend.

Fichier source : [`brand/monl-mark.svg`](brand/monl-mark.svg).

**Le signe est tracé en `currentColor`, sans fond.** C'est la règle qui compte,
et elle vient d'un défaut mesuré : le signe précédent était le texte `m/` dans
un carré `#17141a`, lequel tombait à **1,09:1** contre le fond sombre. La marque
avait donc deux formes — un carré le jour, un glyphe flottant la nuit — et
dépendait d'une police installée. Un tracé en `currentColor` prend la couleur du
texte : il tient sur n'importe quel fond, dans les deux thèmes, et jusqu'à 16 px.

**Une seule exception, le favicon.** Il vit dans un onglet, hors de toute page,
sans couleur à hériter : il porte donc sa pastille charbon et son ambre en dur.
C'est la seule place où un fond est justifié — un onglet en attend un.

- Ne pas modifier les proportions ni l'épaisseur des tracés.
- Ne pas remplacer les tracés par des caractères typographiques.
- Conserver autour du signe un espace libre au moins égal au quart de sa largeur.
- Taille minimale : 16 px pour le signe, 96 px pour le lockup complet.

## Palette

| Rôle | Clair | Sombre |
|---|---|---|
| Encre | `#171512` | `#F3ECE0` |
| Fond | `#F6F4F0` | `#0B0A09` |
| Surface | `#FFFDFA` | `#141210` |
| Texte secondaire | `#615B51` | `#A79E90` |
| Séparateur | `#D3CABB` | `#3D372E` |
| Bordure de contrôle | `#8F8060` | `#6F6555` |
| Ambre (accent) | `#96520A` | `#FFB020` |
| Fond de code | `#0F0E0C` | `#060505` |
| Alerte | `#A32448` | `#FF8FA8` |

**L'ambre change de valeur selon le fond, mais reste une seule couleur.** Vif la
nuit (`#FFB020`), brûlé le jour (`#96520A`) : l'ambre pur ne tient que 1,8:1 sur
un fond clair, il y serait illisible. Ce n'est pas deux accents à entretenir,
c'est le même accent à deux valeurs — et c'est le prix de l'ambre, énoncé
plutôt que découvert.

**Deux bordures, pas une.** `Séparateur` délimite une carte ou une ligne de
tableau ; `Bordure de contrôle` entoure ce qui se clique ou se remplit, et tient
**3:1** parce que WCAG 1.4.11 l'exige d'un composant d'interface. Confondre les
deux donne des boutons secondaires et des champs qu'on ne distingue pas du fond.

**L'alerte est rose-framboise, pas rouge.** Un rouge orangé se confondrait avec
l'ambre à côté duquel il vit ; la teinte s'en écarte franchement.

Aucun état ne se lit par la couleur seule : un libellé ou une icône le porte
toujours aussi.

## Où vivent ces valeurs

Dans `src/monl_platform/theme.py`, et **nulle part ailleurs**. Les pages
n'écrivent que des variables (`var(--brand)`, `var(--code-muted)`) : c'est ainsi
qu'un changement d'identité se fait en un endroit. La refonte précédente avait
laissé cinq verts en dur dans la console — ils ont survécu à un changement
complet de palette sans que rien ne le signale. `tests/test_platform_marque.py`
l'interdit désormais.

## Typographie et ton

Les textes emploient la police sans serif du système, les données techniques sa
monospace. Aucune police distante : la plateforme doit s'ouvrir derrière un
pare-feu, et c'est déjà l'autonomie qu'elle exige des frontends qu'elle fait
produire.

Le ton est direct et factuel : verbe d'action, résultat observable, aucune
promesse vague. On écrit « Compiler le backend » plutôt que « Commencer la
magie ».
