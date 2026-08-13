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
from pathlib import Path

from .ui_patterns import render_pattern_block, select_ui_patterns

DESIGN_SYSTEM_FILENAME = "DESIGN_SYSTEM.md"
DESIGN_SPEC_FILENAME = "DESIGN_SPEC.md"
ASSET_MANIFEST_FILENAME = "ASSET_MANIFEST.json"
GENERATED_MARKER = "<!-- généré par monl — design system -->"


_PALETTES = {
    "commerce": {
        "name": "Matière et conversion",
        "primary": "#1F2A24",
        "secondary": "#C47A52",
        "accent": "#DDB892",
        "surface": "#F5F0E8",
        "text": "#18201C",
        "mood": "matière, confiance, désir d'achat sans surcharge décorative",
    },
    "operations": {
        "name": "Signal opérationnel",
        "primary": "#16324F",
        "secondary": "#2F6690",
        "accent": "#F0A202",
        "surface": "#F4F7FA",
        "text": "#17202A",
        "mood": "calme, lisibilité, signaux d'état et décisions rapides",
    },
    "editorial": {
        "name": "Éditorial chaleureux",
        "primary": "#2B2522",
        "secondary": "#9A6B51",
        "accent": "#C9A66B",
        "surface": "#FAF7F2",
        "text": "#27211E",
        "mood": "profondeur, respiration, matière et lecture longue",
    },
    "service": {
        "name": "Confiance accessible",
        "primary": "#24443B",
        "secondary": "#5B8E7D",
        "accent": "#D07A4B",
        "surface": "#F7F8F4",
        "text": "#1D2925",
        "mood": "accueil, réassurance, progression simple vers l'action",
    },
    "generic": {
        "name": "Clarté distinctive",
        "primary": "#243447",
        "secondary": "#52708A",
        "accent": "#C96B4B",
        "surface": "#F6F7F5",
        "text": "#1B232B",
        "mood": "identité nette, contraste mesuré, information hiérarchisée",
    },
}


def _slug(value: str) -> str:
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
        style = "Trust & Authority / Social Proof-Focused"
        typography = "Sans-serif accueillante, titres courts et labels d'action sans ambiguïté."
        effects = "feedback immédiat sur les formulaires, états de disponibilité visibles"
    elif "monl-commerce" in skills or "shop" in archetypes or "Pay" in actions:
        kind = "commerce"
        pattern = "Hero produit + catalogue guidé + réassurance + conversion"
        style = "Editorial Grid / Conversion-Optimized"
        typography = "Une sans-serif lisible pour l'interface, avec une serif ou une graisse distinctive pour les titres si le brief l'autorise."
        effects = "survols courts, changement d'état explicite, mouvement réduit respecté"
    elif "monl-operations" in skills:
        kind = "operations"
        pattern = "Vue d'ensemble + files de travail + détail contextuel"
        style = "Data-Dense Dashboard / Accessible & Ethical"
        typography = "Sans-serif fonctionnelle, chiffres tabulaires et échelle compacte mais respirable."
        effects = "transitions discrètes, filtres instantanément compréhensibles, aucun mouvement décoratif"
    elif contract.get("sections") or contract.get("faq") or "gallery" in archetypes:
        kind = "editorial"
        pattern = "Hero narratif + preuves de confiance + récit structuré + appel final"
        style = "Editorial Grid / Storytelling-Driven"
        typography = "Contraste net entre titres et texte courant, priorité à la lecture et à la longueur de ligne."
        effects = "apparitions légères, transitions de navigation sobres, pas de parallaxe obligatoire"
    elif any(word in text for word in ("rendez-vous", "appointment", "réserver", "service")):
        kind = "service"
        pattern = "Promesse claire + offres + disponibilité + prise de contact"
        style = "Trust & Authority / Social Proof-Focused"
        typography = "Sans-serif accueillante, titres courts et labels d'action sans ambiguïté."
        effects = "feedback immédiat sur les formulaires, états de disponibilité visibles"
    else:
        kind = "generic"
        pattern = "Entrée claire + contenu principal + preuve + action suivante"
        style = "Minimalism & Swiss Style / Feature-Rich Showcase"
        typography = "Hiérarchie typographique forte, familles locales ou embarquées uniquement."
        effects = "états de focus visibles, transitions de 150–300 ms quand elles servent la compréhension"

    palette = _PALETTES[kind]
    media_entities = [
        {"entity": name, "fields": [field for field, _type in _entity_media(spec)]}
        for name, spec in entities.items()
        if _entity_media(spec)
    ]
    pages = ["Accueil / entrée principale"]
    if any(item.get("archetype") == "shop" for item in entities.values()):
        pages.extend(["Catalogue", "Fiche détaillée", "Panier ou récapitulatif"])
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
        "style": style,
        "palette": palette,
        "typography": typography,
        "effects": effects,
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
    for section in contract.get("sections") or []:
        markers.append(f'data-monl-section="{_slug(section.get("title", "section"))}"')
    if contract.get("faq"):
        markers.append('data-monl-section="faq"')
    return list(dict.fromkeys(markers))


def build_asset_manifest(contract: dict, profile: dict) -> dict:
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
    return {
        "schema_version": 1,
        "status": "planned",
        "generated_by": "monl",
        "design_system": DESIGN_SYSTEM_FILENAME,
        "products": {},
        "editorial": {},
        "planned_assets": planned,
        "required_markers": {"index.html": _required_markers(contract, profile)},
        "notes": [
            "Les chemins de planned_assets sont des attentes de première construction.",
            "Après génération du frontend, Monl passe ce manifeste à active et vérifie les fichiers livrés.",
            "Un manifeste rédigé par l'auteur remplace ce plan et n'est jamais écrasé.",
        ],
    }


def render_design_system(contract: dict) -> str:
    profile = infer_design_profile(contract)
    palette = profile["palette"]
    pages = "\n".join(f"- {page}" for page in profile["pages"])
    patterns = render_pattern_block(profile["ui_patterns"])
    media = "\n".join(
        f"- `{item['entity']}` : {', '.join(item['fields'])}"
        for item in profile["media_entities"]
    ) or "- Aucun média structuré détecté ; ne pas inventer de photos distantes."
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
- **Style de référence :** {profile['style']}
- **Matière visuelle :** {palette['mood']}

## Tokens de départ

Ces tokens sont une base de travail, pas une contrainte de marque :

| Token | Valeur |
|---|---|
| Primary | `{palette['primary']}` |
| Secondary | `{palette['secondary']}` |
| Accent / CTA | `{palette['accent']}` |
| Surface | `{palette['surface']}` |
| Text | `{palette['text']}` |

- **Typographie :** {profile['typography']}
- **Effets :** {profile['effects']}
- **Contraste :** 4,5:1 minimum pour le texte courant, 3:1 pour les grands titres.

## Pages et blocs à rendre

{pages}

Les sections éditoriales et la FAQ déclarées dans le contrat doivent être
visibles sur l'accueil, pas seulement cachées derrière la navigation.

{patterns}

## Assets

{media}

Tous les assets doivent être locaux et servir dans `frontend/`. Aucun CDN,
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


def ensure_design_artifacts(project_dir: str, staging_dir: str, contract: dict) -> dict:
    """Émet les artefacts visuels générés, sans écraser le travail humain."""
    project = Path(project_dir)
    staging = Path(staging_dir)
    design_system = _write_generated(
        staging / DESIGN_SYSTEM_FILENAME, render_design_system(contract))

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

    manifest = build_asset_manifest(contract, infer_design_profile(contract))
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
