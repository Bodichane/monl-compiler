# La licence de monl-compiler, en clair

> Ce document **explique** la licence, il ne la modifie pas et n'y ajoute
> aucune condition. En cas de divergence, seul le texte de
> [LICENSE](LICENSE) fait foi.

monl-compiler est publié sous **FSL-1.1-ALv2** — la *Functional Source
License*, avec bascule automatique vers Apache-2.0. Le texte est celui,
inchangé, publié sur [fsl.software](https://fsl.software).

## Ce qui change par rapport à l'ancienne licence

L'ancienne licence propriétaire réservait « l'utilisation du logiciel, y
compris à des fins internes ou personnelles ». Autrement dit : le dépôt était
lisible, et rien de plus. Ce n'est plus le cas.

**Vous pouvez désormais**, sans rien demander :

- utiliser monl-compiler, y compris dans un cadre professionnel et commercial ;
- l'installer en interne, dans votre CI, chez vos clients ;
- le modifier, le forker, en dériver des travaux ;
- le redistribuer, sous ces mêmes conditions ;
- vous en servir dans le cadre de prestations que vous facturez.

Ce dernier point est explicite dans la licence (*Permitted Purposes*, point 4) :
une agence ou un indépendant peut employer monl-compiler pour livrer des
applications à ses clients, et facturer cette prestation.

## La seule chose interdite : l'usage concurrent

La licence interdit un **Competing Use** : rendre le logiciel disponible à des
tiers dans un produit ou un service commercial qui s'y substitue, ou qui offre
une fonctionnalité identique ou substantiellement similaire.

Concrètement, pour monl-compiler :

| Vous voulez… | Permis ? |
|---|---|
| Compiler vos propres applications, pour vous ou pour un client | Oui |
| Vendre le développement d'applications réalisées avec monl-compiler | Oui |
| Enseigner ou étudier monl-compiler hors cadre commercial | Oui |
| Forker et publier vos correctifs sous la même licence | Oui |
| Lancer un service en ligne qui compile des specs monl pour des tiers | Non |
| Reprendre le compilateur dans votre propre produit low-code commercial | Non |

Ces deux derniers cas ne sont pas fermés définitivement : ils demandent une
licence commerciale — ouvrez une *issue* sur
<https://github.com/Bodichane/monl-compiler>.

## Les applications produites vous appartiennent

La licence porte sur **le compilateur et son outillage**, pas sur ce qu'ils
génèrent. Les `app.py`, `schema.sql`, `manage.py` et frontends produits à
partir de **vos** spécifications sont à vous : vous les hébergez, les modifiez
et les maintenez librement, y compris après la fin de toute relation
commerciale. Aucun composant de monl-compiler n'est embarqué dans
l'application générée, et celle-ci ne rappelle jamais monl à l'exécution.

Les **dépendances tierces** de l'application produite (FastAPI, Lark, PyJWT,
uvicorn, psycopg…) restent régies par leurs licences respectives.

## La bascule vers Apache-2.0

Chaque version publiée devient utilisable sous **Apache-2.0 deux ans après sa
mise à disposition**. Le compte à rebours est **par version**, pas global :

- `v0.9.0-beta.7`, publiée le **12 août 2026**, sera sous Apache-2.0 le
  **12 août 2028** ;
- une version publiée en 2027 basculera en 2029.

Cette bascule est **irrévocable** : elle est accordée dans le texte même de la
licence, au moment de la publication. Elle ne dépend d'aucune décision
ultérieure du titulaire des droits.

## Ce qui n'est plus réservé

Par honnêteté, deux réserves de l'ancienne licence ont disparu, parce que la
FSL est reprise sans modification et ne les contient pas :

- **l'entraînement de modèles sur ce code** n'est plus explicitement interdit ;
- l'intégration dans un autre logiciel est désormais permise, tant qu'elle ne
  constitue pas un usage concurrent.

C'est le prix assumé d'une licence standard, identifiable et lisible par les
outils de conformité — plutôt qu'un texte maison que chaque service juridique
devrait faire analyser.

## Contributions

Les contributions extérieures ne sont pas ouvertes pour l'instant (voir
[CONTRIBUTING.md](CONTRIBUTING.md)). Les rapports de bug et remarques restent
bienvenus dans les *issues*.
