"""Direction visuelle stable transmise à l'IA frontend.

Extrait de l'ancien module monolithique src/generator.py (1307 lignes)
lors du découpage en package — voir docs/design_decisions.md.
"""
import colorsys
import hashlib
import os
import secrets

# AUCUNE POLICE DISTANTE (point 52). Les six systèmes nommaient des Google
# Fonts que la règle « frontend AUTONOME, aucun CDN » du même contrat interdit
# de charger : l'IA UI, prise entre les deux, retombait sur les piles de
# secours et la moitié la plus visible de l'identité — sa typographie —
# s'évaporait à chaque projet. La personnalité vient donc désormais du choix
# de familles réellement présentes sur les machines, distinctes d'un système à
# l'autre, comme le faisait déjà « atelier ». Ne pas y réintroduire de fonte
# à télécharger sans lever d'abord la règle d'autonomie (et le smoke test hors
# ligne qu'elle rend possible).
SYSTEM_SANS = ("system-ui, -apple-system, 'Segoe UI', Roboto, "
               "'Helvetica Neue', Arial, sans-serif")
SYSTEM_MONO = ("ui-monospace, SFMono-Regular, Menlo, Consolas, "
               "'DejaVu Sans Mono', monospace")


class ThemeMixin:
    def _select_theme(self, seed=None):
        """AJOUT (roadmap, identité visuelle) : choisit un système visuel
        complet (palette, typographies, rayon de bordure, traitement des
        cartes) parmi 5 propositions distinctes et volontairement écartées
        des trois looks par défaut que produit une IA sans direction (fond
        crème + accent terracotta, fond quasi-noir + accent acide unique,
        colonnes façon journal à filets fins). Le choix est motivé par le
        vocabulaire du domaine (noms d'entités/attributs/app) quand un signal
        existe ; sinon il est réparti de façon stable (par hachage du nom de
        l'app) entre les 5 systèmes, pour que deux apps génériques différentes
        ne se ressemblent pas non plus."""
        themes = {
            # AJOUT (bêta 3) : sixième système, né du frontend de la démo —
            # papier technique quadrillé, trait fin, données en chasse fixe et
            # un seul accent haute visibilité (celui des gilets et des bandes
            # réfléchissantes). Il couvre le vocabulaire de l'atelier et de la
            # pièce détachée, mal servi par « market » (pensé pour la vitrine
            # marchande). C'est lui qui, le premier, s'est passé de police
            # distante — les cinq autres l'ont rejoint au point 52.
            "atelier": {
                "keywords": {"part", "piece", "repair", "atelier", "workshop", "tool",
                             "velo", "bike", "maintenance", "revision", "stock"},
                "bg": "#F1F3EE", "surface": "#FBFCFA", "ink": "#101C24",
                "accent": "#D9F227", "accent2": "#A8412A",
                "font_display": "'Helvetica Neue', Helvetica, Arial, sans-serif",
                "font_body": "'Helvetica Neue', Helvetica, Arial, sans-serif",
                "font_mono": SYSTEM_MONO,
                "radius": "0px", "card_style": "atelier",
            },
            "editorial": {
                "keywords": {"post", "article", "blog", "comment", "story", "author", "publish"},
                "bg": "#F3EFE1", "surface": "#FFFFFF", "ink": "#241F16",
                "accent": "#2F5D50", "accent2": "#B23A48",
                "font_display": "'Palatino Linotype', 'Book Antiqua', Palatino, "
                                "'URW Palladio L', Georgia, serif",
                "font_body": SYSTEM_SANS,
                "font_mono": SYSTEM_MONO,
                "radius": "4px", "card_style": "editorial",
            },
            "market": {
                "keywords": {"product", "order", "price", "cart", "shop", "invoice", "money",
                              "stock", "customer", "payment", "checkout"},
                "bg": "#EFEDE4", "surface": "#FFFFFF", "ink": "#1B2420",
                "accent": "#0B6E4F", "accent2": "#C98A00",
                "font_display": "'Arial Narrow', 'Liberation Sans Narrow', "
                                "'Helvetica Neue', Arial, sans-serif",
                "font_body": "'Helvetica Neue', Helvetica, Arial, "
                             "'Liberation Sans', sans-serif",
                "font_mono": SYSTEM_MONO,
                "radius": "2px", "card_style": "market",
            },
            "console": {
                "keywords": {"todo", "task", "ticket", "issue", "workflow", "project", "bug", "status"},
                "bg": "#161A1E", "surface": "#20262C", "ink": "#E7E4DC",
                "accent": "#5B8DEF", "accent2": "#3FB68B",
                "font_display": SYSTEM_MONO,
                "font_body": SYSTEM_SANS,
                "font_mono": SYSTEM_MONO,
                "radius": "10px", "card_style": "console",
            },
            "civic": {
                "keywords": {"reservation", "booking", "event", "member", "social", "friend",
                              "profile", "community", "guest", "appointment", "slot",
                              "professional", "schedule"},
                "bg": "#F1ECE4", "surface": "#FFFFFF", "ink": "#2B2118",
                "accent": "#3D5A80", "accent2": "#C9A227",
                "font_display": "Georgia, 'Times New Roman', Times, serif",
                "font_body": "'Trebuchet MS', 'Lucida Grande', "
                             "'Lucida Sans Unicode', 'DejaVu Sans', sans-serif",
                "font_mono": SYSTEM_MONO,
                "radius": "18px", "card_style": "civic",
            },
            "ledger": {
                "keywords": set(),
                "bg": "#EAE6DC", "surface": "#FFFFFF", "ink": "#1E1B16",
                "accent": "#1D3557", "accent2": "#588157",
                "font_display": "'Times New Roman', Times, 'Liberation Serif', serif",
                "font_body": "Verdana, 'DejaVu Sans', Geneva, sans-serif",
                "font_mono": SYSTEM_MONO,
                "radius": "6px", "card_style": "ledger",
            },
        }

        # AJOUT (roadmap, contrôle du rendu visuel) : un bloc 'ui' peut forcer
        # explicitement le thème de toute l'application (le thème reste une
        # identité unique par app, partagée par toutes les entités, pas un
        # réglage par entité) — la première surcharge valide trouvée l'emporte
        # sur la sélection automatique par mots-clés.
        theme_name, theme = None, None
        for override in self.ui_overrides.values():
            requested_theme = override.get("theme")
            if requested_theme and requested_theme in themes:
                theme_name, theme = requested_theme, dict(themes[requested_theme])
                break
        # AJOUT (bêta 3) : un thème épinglé dans la spec est CONTRAIGNANT —
        # le contrat le publie comme tel et le smoke test vérifie que la
        # palette apparaît réellement dans le frontend. Il échappe donc à la
        # variation de teinte appliquée plus bas : une valeur vérifiable doit
        # être exacte et reproductible, pas décalée par une graine.
        pinned = theme is not None

        if theme_name is None:
            vocabulary = (self.app_name + " " + " ".join(self.entities.keys())).lower()
            for entity_attrs in self.entities.values():
                vocabulary += " " + " ".join(entity_attrs.keys()).lower()

            scores = {name: sum(1 for kw in t["keywords"] if kw in vocabulary) for name, t in themes.items()}
            best_score = max(scores.values())

            if best_score > 0:
                candidates = sorted([n for n, s in scores.items() if s == best_score])
            else:
                candidates = sorted(themes.keys())

            hash_source = self.app_name + (":" + seed if seed else "")
            pick_index = int(hashlib.sha256(hash_source.encode()).hexdigest(), 16) % len(candidates)
            theme_name = candidates[pick_index]
            theme = dict(themes[theme_name])

        # AJOUT (roadmap, unicité visuelle par projet) : le choix ci-dessus
        # ne dépend QUE du domaine (vocabulaire de l'app) — deux projets de
        # même domaine (deux todo-lists, par exemple) obtiennent donc le
        # même thème de base à chaque fois, par construction. La graine
        # aléatoire propre au projet (voir _load_or_create_theme_seed) sert
        # ici à appliquer une variation fine SUR ce thème (teinte des
        # couleurs d'accent, rayon des bordures) sans jamais changer le
        # thème lui-même : deux todo-lists restent bien reconnaissables
        # comme telles (même palette de base, mêmes polices), mais cessent
        # d'être des pixels identiques.
        if seed and not pinned:
            variation_hash = hashlib.sha256(f"{self.app_name}:{seed}".encode()).hexdigest()
            hue_shift_accent = (int(variation_hash[0:4], 16) % 41) - 20     # -20..+20 degrés
            hue_shift_accent2 = (int(variation_hash[4:8], 16) % 41) - 20
            radius_factor = 0.8 + (int(variation_hash[8:10], 16) % 41) / 100.0  # ~0.8x..1.2x
            theme["accent"] = self._shift_hue(theme["accent"], hue_shift_accent)
            theme["accent2"] = self._shift_hue(theme["accent2"], hue_shift_accent2)
            base_radius_px = float(theme["radius"].replace("px", ""))
            theme["radius"] = f"{round(base_radius_px * radius_factor, 1)}px"

        theme["pinned"] = pinned
        return theme_name, theme

    @staticmethod
    def _shift_hue(hex_color, degrees):
        """AJOUT (roadmap, unicité visuelle par projet) : fait pivoter la
        teinte (HSL) d'une couleur hexadécimale d'un nombre de degrés donné,
        en conservant sa luminosité et sa saturation d'origine -- donc son
        niveau de contraste avec le fond/le texte, ce qui est important pour
        la lisibilité. N'agit que sur les couleurs d'accent, jamais sur
        bg/surface/ink, pour ne pas risquer de dégrader le contraste texte."""
        hex_color = hex_color.lstrip("#")
        r, g, b = (int(hex_color[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
        h, l, s = colorsys.rgb_to_hls(r, g, b)
        h = (h + degrees / 360.0) % 1.0
        r, g, b = colorsys.hls_to_rgb(h, l, s)
        return "#{:02X}{:02X}{:02X}".format(round(r * 255), round(g * 255), round(b * 255))

    def _load_or_create_theme_seed(self):
        """AJOUT (roadmap, unicité visuelle par projet) : génère, à la toute
        première compilation d'un projet, une graine aléatoire de 16 octets
        conservée dans '.monl_theme_seed' (ignorée via .gitignore,
        jamais commitée -- même logique que '.jwt_secret'). Recompiler la
        spec NE régénère PAS la graine : le style visuel du projet reste
        stable dans le temps ; il faut supprimer le fichier à la main pour
        en tirer un nouveau look."""
        # La graine appartient au projet compilé : elle suit --output.
        seed_path = os.path.join(self.output_dir, ".monl_theme_seed")
        if not os.path.exists(seed_path):
            new_seed = secrets.token_hex(16)
            with open(seed_path, "w", encoding="utf-8") as f:
                f.write(new_seed)
            print("🎨 Nouvelle graine de variation visuelle générée et stockée dans '.monl_theme_seed'.")
            return new_seed
        with open(seed_path, "r", encoding="utf-8") as f:
            return f.read().strip()

