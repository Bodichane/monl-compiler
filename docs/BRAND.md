# Identité Monl

Monl compile des règles métier en un backend exact. L'identité est
**typographique** : charbon, crème, et un seul cuivre réservé à ce qui est
actionnable. Le monde de référence est l'imprimerie, pas le terminal — une
spécification se lit avant de s'exécuter.

## Signe

Le mot **monl**, dont le « o » est cerclé d'un anneau orange tracé à main
levée. Le signe est ce « o » seul : un anneau dans un anneau, et le fond au
centre.

Fichiers sources : [`brand/monl-mark.svg`](brand/monl-mark.svg) (le signe),
[`brand/monl-wordmark.svg`](brand/monl-wordmark.svg) (le mot). Tous deux sont
**vectorisés depuis l'artwork** par `outils/vectoriser_logo.py`, qui refuse
d'écrire si le tracé re-rasterisé s'écarte de plus de 6 % du dessin d'origine —
mesuré 0,34 % sur les lettres et 0,15 % sur l'anneau. Ne pas les retoucher à la
main : `src/monl_platform/brand.py` est la source, tout le reste en découle.
L'artwork d'origine est conservé à côté d'eux
([`brand/monl-logo-source.png`](brand/monl-logo-source.png)) : sans lui, on ne
pourrait ni re-vectoriser ni vérifier. Le logo PRÉCÉDENT — une bannière en
pointe — vit à côté sous
[`brand/monl-logo-precedent.png`](brand/monl-logo-precedent.png), rangé là et
non à la racine : deux logos côte à côte à la racine ont déjà fait vectoriser
le mauvais.

**Les lettres sont tracées en `currentColor`, sans fond.** C'est la règle qui
compte, et elle vient d'un défaut mesuré : servi en `<img>`, le logo garde le
fond sombre de son artwork quel que soit le thème — l'ancienne bannière tombait
à **1,29:1** contre la page sombre, un logo littéralement invisible dans
l'en-tête. En SVG dans la page, les lettres prennent la couleur du texte et le
fond de la page se voit à travers le trou des deux anneaux.

**L'anneau, lui, ne suit AUCUN thème.** Un logo qui change de teinte avec le
fond n'est plus le logo. Il garde `#D67730` partout — voir la palette
ci-après pour ce que cela implique.

**Une seule exception, le favicon.** Il vit dans un onglet, hors de toute page,
sans couleur à hériter : il porte donc sa pastille et ses tracés en dur. C'est
la seule place où un fond est justifié — un onglet en attend un. Et
`/favicon.ico` existe à côté du SVG : les navigateurs le demandent d'office, et
un 404 les laisse afficher l'ancienne icône gardée en cache.

- Ne pas modifier les proportions ni l'épaisseur des tracés.
- Ne pas fermer l'anneau ni le régulariser en cercle parfait : l'irrégularité
  du tracé à main levée EST le signe.
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
| Orange du logo | `#D67730` | `#D67730` |
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

**L'orange du logo n'est PAS l'accent cuivre, et c'est une tension assumée.**
Le cuivre est une couleur d'interface : il a deux valeurs parce qu'il doit
rester lisible sur les deux fonds. L'orange du logo est une couleur de marque :
il n'en a qu'une, parce qu'un logo se reconnaît à sa teinte. Ne pas s'en servir
pour un bouton, un surtitre ou un état — il n'appartient qu'au signe. Mesuré :
5,67:1 sur le fond sombre, 2,94:1 sur le clair. Ce second chiffre passe sous le
3:1 de WCAG 1.4.11, et c'est ACCEPTÉ ici parce que la norme exempte
explicitement les logotypes — ce qui porte la lecture du mot, ce sont les
lettres, à 12,89:1. La même valeur employée pour un composant d'interface
serait, elle, un vrai défaut.

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
