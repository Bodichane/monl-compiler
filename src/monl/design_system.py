"""Design system déterministe produit avant le frontend.

Cette couche reprend une idée importante des skills UI/UX spécialisés : le
modèle ne devrait pas inventer la direction visuelle pendant qu'il écrit le
HTML. Monl produit donc d'abord un plan lisible par un humain et par l'IA,
depuis le contrat déjà validé.

Le résultat reste une recommandation de composition, pas une nouvelle source
de vérité métier. Une ``DESIGN_SPEC.md`` ou un ``ASSET_MANIFEST.json`` écrit
par l'auteur est toujours prioritaire et n'est jamais écrasé.
"""

from __future__ import annotations

import json
import re
import shutil
import unicodedata
from pathlib import Path

from .ui_patterns import render_pattern_block, select_ui_patterns

DESIGN_SYSTEM_FILENAME = "DESIGN_SYSTEM.md"
DESIGN_SPEC_FILENAME = "DESIGN_SPEC.md"
ASSET_MANIFEST_FILENAME = "ASSET_MANIFEST.json"
GENERATED_MARKER = "<!-- généré par monl — design system -->"


# POINT 139 : il n'y a PLUS de palette ici, et il ne doit pas y en avoir.
# Cinq palettes indexées sur le type d'activité vivaient à cet endroit. Le
# point 72 l'interdit — « le compilateur ne décide RIEN du visuel : ni palette,
# ni typographie, ni rayon » — et trois faits l'ont tranché plutôt qu'un
# argument : les cinq couleurs `:root` de projets/AtelierNaya sont identiques à
# l'octet à la palette « service », écrite quarante minutes plus tôt ; le
# garde-fou ne regardait que le contrat, pendant que la palette voyageait par
# DESIGN_SYSTEM.md ; et cette palette échouait au contraste qu'elle promettait
# elle-même dans le même document (blanc sur #D07A4B : 3,20:1 pour un seuil
# annoncé de 4,5:1, mesuré sur le bouton « Réserver »).
#
# La ligne retenue est plus fine que « méthode contre goût » : une échelle, un
# rythme, une durée ou une rupture deviennent du GOÛT dès que le compilateur en
# choisit les VALEURS. Ce fichier peut donc exiger qu'une échelle existe et
# qu'elle soit suivie ; il ne peut pas dire laquelle.

def _slug(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value or "section"


def _all_text(contract: dict) -> str:
    values = [contract.get("app") or "", contract.get("brief") or ""]
    for section in contract.get("sections") or []:
        values.extend((section.get("title") or "", section.get("body") or ""))
    for question in contract.get("faq") or []:
        values.extend((question.get("question") or "", question.get("answer") or ""))
    return " ".join(values).lower()


def _entity_media(entity: dict) -> list[tuple[str, str]]:
    return [
        (field.get("name", "media"), field.get("type", "String"))
        for field in entity.get("fields") or []
        if field.get("role") == "media"
    ]


def infer_design_profile(contract: dict) -> dict:
    """Déduit une direction initiale à partir de signaux du contrat.

    Les signaux sont structurels (routes, archétypes, contenu), pas des noms
    magiques d'entités. La direction peut ensuite être remplacée par le
    cahier visuel écrit par l'auteur.
    """
    skills = set(contract.get("design_skills") or [])
    entities = contract.get("entities") or {}
    routes = contract.get("routes") or []
    text = _all_text(contract)
    archetypes = {item.get("archetype") for item in entities.values()}
    actions = {route.get("action") for route in routes}
    # Un service réservable peut porter un prix et donc ressembler à une
    # boutique au niveau de l'archétype. Le signal métier explicite de
    # réservation doit toutefois primer : l'interface attendue est un
    # parcours de disponibilité et de prise de rendez-vous, pas un panier.
    scheduling_signal = any(word in text for word in (
        "rendez-vous", "réserver", "réservation", "appointment", "booking",
        "créneau", "disponibilité",
    ))

    if scheduling_signal:
        kind = "service"
        pattern = "Promesse claire + offres + disponibilité + prise de contact"
    elif "monl-commerce" in skills or "shop" in archetypes or "Pay" in actions:
        kind = "commerce"
        pattern = "Hero produit + catalogue guidé + réassurance + conversion"
    elif "monl-operations" in skills:
        kind = "operations"
        pattern = "Vue d'ensemble + files de travail + détail contextuel"
    elif contract.get("sections") or contract.get("faq") or "gallery" in archetypes:
        kind = "editorial"
        pattern = "Hero narratif + preuves de confiance + récit structuré + appel final"
    elif any(word in text for word in ("rendez-vous", "appointment", "réserver", "service")):
        kind = "service"
        pattern = "Promesse claire + offres + disponibilité + prise de contact"
    else:
        kind = "generic"
        pattern = "Entrée claire + contenu principal + preuve + action suivante"

    media_entities = [
        {"entity": name, "fields": [field for field, _type in _entity_media(spec)]}
        for name, spec in entities.items()
        if _entity_media(spec)
    ]
    pages = ["Accueil / entrée principale"]
    if kind == "commerce":
        pages.extend(["Catalogue", "Fiche détaillée", "Panier ou récapitulatif"])
    elif kind == "service":
        pages.append("Prestations, disponibilité et réservation")
    if "monl-operations" in skills:
        pages.append("Espace de travail par rôle")
    if contract.get("sections"):
        pages.append("Sections éditoriales sur l'accueil, avec prolongement si nécessaire")
    if contract.get("faq"):
        pages.append("FAQ structurée")
    pages.append("Compte, authentification et états d'erreur utiles")

    profile = {
        "kind": kind,
        "pattern": pattern,
        "pages": pages,
        "media_entities": media_entities,
    }
    profile["ui_patterns"] = select_ui_patterns(contract, kind)
    return profile


def _required_markers(contract: dict, profile: dict) -> list[str]:
    # Une spec purement API n'a pas demandé de site éditorial. Elle reçoit
    # bien un design system pour le jour où un frontend sera ajouté, mais
    # Monl ne doit pas lui imposer des sections de landing qu'elle n'a jamais
    # déclarées (compatibilité avec les projets historiques et les backends
    # sans interface).
    if not (contract.get("brief") or contract.get("sections") or contract.get("faq")):
        return []
    markers = [pattern["marker"] for pattern in profile.get("ui_patterns", [])]
    markers.extend(
        f'data-monl-media="{_slug(name)}"'
        for name, spec in (contract.get("entities") or {}).items()
        if _entity_media(spec)
    )
    if profile["kind"] == "commerce":
        markers.extend(['data-monl-section="catalogue"', 'data-monl-section="panier"'])
    if profile["kind"] == "operations":
        markers.append('data-monl-section="workspace"')
    # Un marqueur identifie l'élément qui porte la section, il n'exige jamais
    # un bloc séparé. Quand le pattern `editorial` est présent, cet élément vit
    # à l'intérieur du bloc éditorial : un seul élément, un seul marqueur, un
    # seul rendu. La garantie « chaque section déclarée est rendue » reste donc
    # active sans pousser l'IA à dupliquer « À propos ».
    markers.extend(_declared_section_markers(contract))
    if contract.get("faq"):
        markers.append('data-monl-section="faq"')
    return list(dict.fromkeys(markers))


def _declared_section_markers(contract: dict) -> list[str]:
    """Retourne un marqueur distinct pour chaque section, dans l'ordre déclaré."""
    used_slugs = set()
    next_rank_by_slug = {}
    markers = []
    for section in contract.get("sections") or []:
        base_slug = _slug(section.get("title", "section"))
        rank = next_rank_by_slug.get(base_slug, 1)
        section_slug = base_slug if rank == 1 else f"{base_slug}-{rank}"
        while section_slug in used_slugs:
            rank += 1
            section_slug = f"{base_slug}-{rank}"
        next_rank_by_slug[base_slug] = rank + 1
        used_slugs.add(section_slug)
        markers.append(f'data-monl-section="{section_slug}"')
    return markers


def _generated_image_block_markers(contract: dict, profile: dict,
                                   generated: list[dict]) -> list[str | None]:
    """Associe chaque image planifiée à un bloc déjà déclaré.

    Le manifeste porte séparément les rôles des images et les marqueurs de
    sections qui doivent être uniques. Le brief doit faire le rapprochement
    explicitement : le premier visuel est le hero ; le visuel secondaire va
    dans la première section déclarée, sinon dans le pattern éditorial, la
    preuve ou l'appel final déjà requis. Aucun nouveau marqueur n'est inventé.
    """
    required = _required_markers(contract, profile)
    hero_marker = 'data-monl-section="hero"'
    unique_sections = [
        marker for marker in _declared_section_markers(contract)
        if marker != hero_marker
    ]
    fallback_sections = [
        f'data-monl-section="{name}"'
        for name in ("editorial", "trust", "closing-cta")
    ]
    candidates = unique_sections + [
        marker for marker in fallback_sections
        if marker in required and marker not in unique_sections
    ] + [
        marker for marker in required
        if marker.startswith('data-monl-section="')
        and marker not in {hero_marker, *unique_sections}
        and marker not in fallback_sections
    ]

    placements = []
    used = set()
    for index, _item in enumerate(generated):
        if index == 0 and hero_marker in required:
            marker = hero_marker
        else:
            marker = next((candidate for candidate in candidates
                           if candidate not in used), None)
        placements.append(marker)
        if marker:
            used.add(marker)
    return placements


def _generated_image_plan(contract: dict, profile: dict) -> list[dict]:
    """Retourne le plan explicite d'images matricielles.

    L'absence de plan est le défaut. Cette fonction ne lit donc jamais le
    brief pour chercher un mot-clé : le booléen ``generate_images`` est la
    décision humaine qui l'appelle.
    """
    assets_dir = ((contract.get("assets") or {}).get("dir") or "assets").strip("/")
    prefix = f"{assets_dir}/generated"
    planned = [{
        "kind": "generated-image",
        "path": f"{prefix}/hero.jpg",
        "role": "bandeau principal du premier écran",
        "aspect_ratio": {"width": 16, "height": 9},
        "frontend_reference": f"{prefix}/hero.jpg",
        "required": True,
    }]
    if contract.get("sections") or profile["kind"] in {"service", "editorial", "commerce"}:
        planned.append({
            "kind": "generated-image",
            "path": f"{prefix}/editorial.jpg",
            "role": "vignette secondaire pour le récit ou la preuve",
            "frontend_reference": f"{prefix}/editorial.jpg",
            "required": True,
        })
    return planned


def build_asset_manifest(contract: dict, profile: dict, generate_images=False) -> dict:
    """Construit un plan d'assets sans prétendre que les fichiers existent déjà."""
    planned = []
    for media in profile["media_entities"]:
        for field in media["fields"]:
            planned.append({
                "kind": "entity-media",
                "entity": media["entity"],
                "field": field,
                "path_pattern": f"assets/{_slug(media['entity'])}/{{slug}}.svg",
                "required": True,
            })
    if contract.get("sections"):
        planned.append({
            "kind": "editorial-hero",
            "path_pattern": "assets/editorial/hero.svg",
            "required": True,
        })
    generated_assets = (_generated_image_plan(contract, profile)
                        if generate_images else [])
    return {
        "schema_version": 1,
        "status": "planned",
        "generated_by": "monl",
        "design_system": DESIGN_SYSTEM_FILENAME,
        "products": {},
        "editorial": {},
        "planned_assets": planned,
        "generated_assets": generated_assets,
        "required_markers": {"index.html": _required_markers(contract, profile)},
        "unique_section_markers": {
            "index.html": _declared_section_markers(contract),
        },
        "notes": [
            "Les chemins de planned_assets sont des attentes de première construction.",
            "Après génération du frontend, Monl passe ce manifeste à active et vérifie les fichiers livrés.",
            "Un manifeste rédigé par l'auteur remplace ce plan et n'est jamais écrasé.",
        ],
    }


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
        f"- `{item['path']}` — {item['role']} — bloc HTML exact : "
        f"`{marker}` (à rendre une seule fois)"
        if marker else
        f"- `{item['path']}` — {item['role']} — bloc HTML distinct à choisir "
        "parmi les marqueurs de section obligatoires du manifeste (à rendre "
        "une seule fois)"
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


def activate_asset_manifest(project_dir: str) -> bool:
    """Passe le manifeste généré en mode vérifiable après écriture du frontend."""
    path = Path(project_dir) / ASSET_MANIFEST_FILENAME
    if not path.exists():
        return False
    try:
        content = path.read_text(encoding="utf-8")
        if GENERATED_MARKER not in content:
            return False
        manifest = json.loads("\n".join(content.splitlines()[1:]))
    except (OSError, json.JSONDecodeError):
        return False
    if manifest.get("generated_by") != "monl" or manifest.get("status") != "planned":
        return False
    manifest["status"] = "active"
    path.write_text(
        GENERATED_MARKER + "\n" + json.dumps(
            manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    return True
