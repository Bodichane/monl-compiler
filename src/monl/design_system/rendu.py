"""Le document rendu à l'IA d'interface, et le plan des images.

`plan_generated_images` vit ICI et non avec le manifeste : il appelle le
rendu, qui appelle le manifeste. Le placer là-bas ferait un cycle."""

import json
import shutil
from pathlib import Path

from ..ui_patterns import render_pattern_block
from .manifeste import _generated_image_plan, build_asset_manifest
from .marqueurs import _generated_image_block_markers, _required_markers, _section_substance
from .noms import (
    ASSET_MANIFEST_FILENAME,
    DESIGN_SPEC_FILENAME,
    DESIGN_SYSTEM_FILENAME,
    GENERATED_MARKER,
)
from .profil import _guarantees, infer_design_profile


def render_design_system(contract: dict, generate_images=False) -> str:
    profile = infer_design_profile(contract)
    pages = "\n".join(f"- {page}" for page in profile["pages"])
    patterns = render_pattern_block(profile["ui_patterns"])
    media = "\n".join(
        f"- `{item['entity']}` : {', '.join(item['fields'])}"
        for item in profile["media_entities"]
    ) or "- Aucun média structuré détecté ; ne pas inventer de photos distantes."
    generated = build_asset_manifest(
        contract, profile, generate_images=generate_images).get("generated_assets") or []
    block_markers = _generated_image_block_markers(contract, profile, generated)
    generated_block = "\n".join(
        f"- `{item['path']}` — rôle : {item['role']} — emploi unique "
        "obligatoire : rendre ce fichier une seule fois"
        + (f" — précision : bloc HTML exact : `{marker}`" if marker else "")
        for item, marker in zip(generated, block_markers, strict=True)
    ) or "- Aucun fichier graphique supplémentaire planifié ; ne pas inventer de chemin d'image."
    anti_patterns = {
        "commerce": "catalogue réduit à trois cartes, prix relégué, faux stock, faux paiement réussi, hero sans produit",
        "operations": "dashboard décoratif sans décision, cartes répétées, tableau illisible sur mobile, action privilégiée cachée",
        "editorial": "sections réduites à des paragraphes sans rythme, hero générique, images distantes, FAQ aplatie en texte",
        "service": "formulaire sans réassurance, promesse non prouvée, calendrier fictif, états d'erreur silencieux",
        "generic": "écran vide après le hero, grille uniforme, faux contenu, navigation sans issue claire",
    }[profile["kind"]]
    markers = "\n".join(f"- `{marker}`" for marker in _required_markers(contract, profile))
    liens = "\n".join(
        f"- **{lien['label']}** → `{lien['url']}`"
        for lien in (contract.get("links") or [])
    ) or ("- Aucun lien déclaré. Ne pas en inventer : une adresse de réseau "
          "social devinée mène chez quelqu'un d'autre.")
    garanties = "\n".join(f"- {phrase}" for phrase in _guarantees(contract)) or (
        "- Aucune garantie dérivable du contrat : ne rien affirmer plutôt "
        "qu'inventer une preuve.")
    substance = "\n".join(
        "- `{}` : {}".format(
            marker.partition("=")[2].strip('"'),
            ", ".join(
                part for part in (
                    "un titre" if regle.get("heading") else "",
                    "un formulaire" if regle.get("form") else "",
                    "un bouton ou un lien d'action" if regle.get("action") else "",
                    (f"au moins {regle['text']} caractères de texte lisible"
                     if regle.get("text") else ""),
                ) if part
            ),
        )
        for marker, regle in _section_substance(contract, profile).items()
    ) or "- Aucune section obligatoire pour ce projet."
    return f"""{GENERATED_MARKER}
# {contract.get('app', 'Monl')} — système de design initial

Ce document est produit par Monl avant la génération du frontend. Il donne à
l'IA une décision de composition cohérente et révisable. Il ne remplace ni la
spec métier, ni un `DESIGN_SPEC.md` écrit par l'auteur : si ce dernier existe,
il est prioritaire.

## Décision principale

- **Type détecté :** {profile['kind']}
- **Pattern :** {profile['pattern']}

## Méthode attendue — les valeurs sont à TOI

Ce document ne contient aucune couleur, aucune fonte et aucun rayon, et c'est
délibéré : l'identité vient du brief et du dialogue, jamais du compilateur. Ce
qui est exigé ici, c'est la RIGUEUR, pas le goût.

- **Tokens** : définis tes couleurs, tes espacements et tes rayons comme
  variables CSS nommées, en tête de feuille, et n'écris aucune valeur en dur
  ailleurs. Une retouche doit pouvoir changer l'identité en un endroit.
- **Échelle typographique** : choisis une progression et tiens-t'y. Chaque
  taille doit avoir un RÔLE nommé ; une taille qui n'appartient à aucun rôle
  est une taille de trop. La hiérarchie doit rester lisible sur petit écran —
  un titre principal qui rejoint la taille des sous-titres l'efface.
- **Longueur de ligne** : borne-la pour les blocs de texte suivi.
- **Rythme d'espacement** : une échelle, pas des nombres au cas par cas. Le
  rythme vertical d'une section doit refléter son importance, et se comprimer
  sur petit écran plutôt que rester identique.
- **États** : chaque contrôle interactif doit couvrir repos, survol quand il a
  du sens, focus visible au clavier, actif, désactivé, attente et erreur. Une
  erreur se place À CÔTÉ du champ concerné, pas seulement dans un message
  global. Une action en cours empêche le double envoi.
- **Mouvement** : borne les durées et donne-leur une raison. `prefers-reduced-motion`
  est respecté.
- **Contraste** : 4,5:1 minimum pour le texte courant, 3:1 pour les grands
  titres — vérifie-le sur le texte des BOUTONS, c'est là qu'il manque le plus
  souvent.
- **Profondeur** : si tu emploies des ombres, qu'elles forment un modèle à
  plusieurs niveaux ; une ombre unique répartie partout n'établit aucune
  hiérarchie.

## Pages et blocs à rendre

{pages}

Les sections éditoriales et la FAQ déclarées dans le contrat doivent être
visibles sur l'accueil, pas seulement cachées derrière la navigation.

{patterns}

## Propriété du contenu — éviter les répétitions

Chaque section déclarée doit apparaître **une seule fois** sur la page
d'accueil, sur son propre élément HTML portant
`data-monl-section="<slug>"`. Lorsqu'un pattern `editorial` est présent, le
bloc éditorial porte ces éléments à l'intérieur de lui : fusionner « À propos »,
« Horaires », etc. dans ce récit au lieu d'ajouter ensuite un second bloc. Un
seul élément, un seul marqueur, un seul rendu. De même, chaque image générée
a un rôle unique : le bloc exact auquel elle est appariée est indiqué dans
« Assets graphiques produits par la construction » ci-dessous. Rends chaque
fichier une seule fois dans ce bloc et ne réutilise jamais son chemin dans un
autre bloc ; n'échange pas les deux appariements.

## Assets

{media}

### Assets graphiques produits par la construction

{generated_block}

Tous les assets doivent être locaux et servir dans le dossier déclaré par la
specification, monté sous `/site/<assets_dir>/`. Aucun CDN,
aucune URL distante et aucun placeholder silencieux sur un chemin déclaré.
Le manifeste associé est `ASSET_MANIFEST.json`. Pour chaque entité média,
marquer la zone qui rend ses images avec `data-monl-media="nom-entite"` : ce
marqueur permet à Monl de vérifier qu'une image n'a pas disparu derrière une
carte vide ou un faux placeholder.

## Anti-patterns à éviter

- {anti_patterns}
- Dégradés violets/roses génériques, emojis utilisés comme icônes et texte gris insuffisamment contrasté.
- États de chargement globaux qui masquent toute la page ; préférer un état local à la zone concernée.
- Interface desktop simplement réduite sur mobile, débordement horizontal ou boutons sans état focus.

## Checklist de livraison

- [ ] Chaque parcours principal du contrat possède une entrée visible.
- [ ] Chargement, vide, succès, erreur, refus et indisponibilité sont traités quand ils existent.
- [ ] Les images ont un `alt` utile et un fallback local contrôlé.
- [ ] Les boutons et liens sont distinguables, atteignables au clavier et visibles au focus.
- [ ] `prefers-reduced-motion` est respecté.
- [ ] Les largeurs 375 px, 768 px, 1024 px et 1440 px restent utilisables.
- [ ] `monl run . --check` passe après activation du manifeste.

## Marqueurs structurels attendus

{markers}

## Substance minimale de chaque section — refus à la vérification

Un marqueur nomme une section, il ne la remplit pas. Une section marquée mais
vide fait **échouer la construction** : ce n'est pas un avertissement. Ce qui
est exigé, section par section :

{substance}

Le texte compté est celui qu'un humain lit : le contenu d'un `<script>` ne
compte pas, et une section ne peut pas emprunter le texte de sa voisine. Ces
seuils sont des PLANCHERS, pas des cibles — les atteindre avec du remplissage
serait manquer le but. Ce qui manque doit être pris dans le contrat et dans le
contenu déclaré, jamais inventé.

Une section de collection (`catalogue`, `workspace`) n'a PAS à contenir de
données en dur : ses lignes viennent de l'API à l'exécution. Ce qu'elle doit
porter, c'est son titre, sa zone de rendu et son état vide.

## Pied de page — obligatoire, et vérifié

Le pied de page porte `data-monl-section="footer"`. C'est le dernier endroit
où un site se dénonce comme une maquette : deux mots gris, aucun lien, aucune
mention. Il doit porter, au minimum :

- **les liens déclarés ci-dessous, tous, avec leur adresse exacte** — leur
  absence fait échouer la construction ;
- une **navigation** vers les sections de la page (les mêmes ancres que le
  menu principal) ;
- l'**identité** de qui édite le site et l'année en cours ;
- le **contact** s'il existe une adresse ou un téléphone déclarés.

Ne JAMAIS inventer : pas de réseau social non déclaré, pas de mentions
légales fictives, pas de « © 2026 Tous droits réservés » sur un nom
d'entreprise qu'on aurait imaginé. Ce qui n'est pas déclaré n'existe pas.

### Liens déclarés — à rendre tels quels

{liens}

## Garanties réellement vérifiables — matière de la section de réassurance

Ces phrases décrivent ce que le backend fait vraiment. La section `trust` doit
se construire à partir d'elles, reformulées dans le registre du site. Toute
autre affirmation — avis client, logo partenaire, nombre d'utilisateurs,
récompense, délai non déclaré — est **interdite** : monl ne peut pas la
vérifier, donc le site ne peut pas la promettre.

{garanties}
"""

def _write_generated(path: Path, content: str, marker: str = GENERATED_MARKER) -> bool:
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8")
        except OSError:
            current = ""
        if marker not in current:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True

def ensure_design_artifacts(project_dir: str, staging_dir: str, contract: dict,
                            generate_images=False) -> dict:
    """Émet les artefacts visuels générés, sans écraser le travail humain."""
    project = Path(project_dir)
    staging = Path(staging_dir)
    design_system = _write_generated(
        staging / DESIGN_SYSTEM_FILENAME,
        render_design_system(contract, generate_images=generate_images))

    design_spec = f"""{GENERATED_MARKER}
# {contract.get('app', 'Monl')} — cahier visuel initial

Le système de design complet est dans `DESIGN_SYSTEM.md`. Cette synthèse est
produite depuis le contrat frontend et peut être remplacée par un cahier
spécifique écrit par l'auteur.

## Intention

{contract.get('brief') or 'Construire une interface claire, complète et adaptée aux parcours du contrat.'}

## Contenu obligatoire

{chr(10).join(f"- {section.get('title', 'Section')} : {section.get('body', '')}" for section in contract.get('sections') or []) or '- Rendre les parcours et entités du contrat avec une hiérarchie explicite.'}

## Règles de qualité

- Les parcours principaux, états d'erreur et états vides sont visibles et compréhensibles.
- Les sections éditoriales déclarées restent présentes sur l'accueil.
- Les visuels sont locaux, cohérents avec le système de design et réellement référencés.
- Les détails d'accessibilité et de responsive de `DESIGN_SYSTEM.md` sont obligatoires.
"""
    design_spec_written = _write_generated(staging / DESIGN_SPEC_FILENAME, design_spec)

    manifest = build_asset_manifest(
        contract, infer_design_profile(contract), generate_images=generate_images)
    manifest_text = GENERATED_MARKER + "\n" + json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    manifest_written = _write_generated(staging / ASSET_MANIFEST_FILENAME, manifest_text)

    # ``copy_preserved_files`` s'occupe déjà des cahiers humains. Ce fallback
    # rend la fonction sûre lorsqu'elle est appelée indépendamment du pipeline.
    for name, written in ((DESIGN_SPEC_FILENAME, design_spec_written),
                          (ASSET_MANIFEST_FILENAME, manifest_written)):
        if not written and not (staging / name).exists() and (project / name).exists():
            (staging / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(project / name, staging / name)
    return {
        DESIGN_SYSTEM_FILENAME: design_system,
        DESIGN_SPEC_FILENAME: design_spec_written,
        ASSET_MANIFEST_FILENAME: manifest_written,
    }

def plan_generated_images(project_dir: str) -> list[dict]:
    """Active le plan d'images après le choix explicite de l'IA image.

    ``monl compile`` reste sans image par défaut. Cette étape est appelée par
    ``monl frontend --generate-images`` juste avant la construction, afin que
    le manifeste et le brief texte contiennent les noms avant l'écriture du
    premier fichier HTML.
    """
    project = Path(project_dir)
    contract_path = project / "frontend_contract.json"
    manifest_path = project / ASSET_MANIFEST_FILENAME
    if not contract_path.exists() or not manifest_path.exists():
        return []
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        content = manifest_path.read_text(encoding="utf-8")
        if not content.startswith(GENERATED_MARKER):
            return []
        manifest = json.loads("\n".join(content.splitlines()[1:]))
    except (OSError, json.JSONDecodeError):
        return []
    if manifest.get("generated_by") != "monl":
        return []
    generated = _generated_image_plan(contract, infer_design_profile(contract))
    manifest["generated_assets"] = generated
    manifest["status"] = "planned"
    manifest_path.write_text(
        GENERATED_MARKER + "\n" + json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    design_path = project / DESIGN_SYSTEM_FILENAME
    if design_path.exists():
        try:
            design = design_path.read_text(encoding="utf-8")
        except OSError:
            design = ""
        if GENERATED_MARKER in design:
            design_path.write_text(
                render_design_system(contract, generate_images=True), encoding="utf-8")
    return generated
