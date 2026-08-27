"""Ce que le frontend RÉCLAME : les fichiers cités par le HTML et le CSS.

La limite est ÉNONCÉE (point 137) : seules les références portant une
extension connue sont retenues, pour ne jamais confondre un fichier avec une
route (`/item`) ou une navigation (`#/panier`). Une référence enracinée
(`/photo.svg`) n'est PAS réécrite vers `/site/` : c'est un vrai défaut, et le
réécrire le masquerait."""

import os
import posixpath
import re

# ---- références locales du frontend (brique 29, point 137) ----------------
# Un fichier que la page RÉCLAME mais que personne n'a livré ne casse aucun
# script : le navigateur affiche un trou, jsdom ne bronche pas, et le smoke
# test déclarait vert. C'est ce qui est arrivé à AtelierNaya — six SVG
# référencés, aucun livré, `monl run --check` au vert.
#
# On ne retient que les références portant une EXTENSION de fichier connue.
# La limite est ÉNONCÉE plutôt que devinée : `<img src="/photos/hero">` (sans
# extension) n'est pas contrôlé. C'est le prix à payer pour ne JAMAIS dénoncer
# une route du contrat ni un lien de navigation `#/x` — un avertissement qui se
# trompe sur un site correct apprend à ne plus lire les avertissements
# (points 57 et 92).
EXTENSIONS_REFERENCEES = (
    ".html", ".css", ".js", ".json", ".svg", ".png", ".jpg", ".jpeg",
    ".webp", ".gif", ".avif", ".ico", ".bmp", ".woff", ".woff2", ".ttf",
    ".otf", ".eot", ".mp4", ".webm", ".ogg", ".mp3", ".wav", ".pdf",
)

_REF_ATTRIBUT = re.compile(r'(?:src|href|poster)\s*=\s*["\']([^"\']+)["\']', re.I)

_REF_SRCSET = re.compile(r'srcset\s*=\s*["\']([^"\']+)["\']', re.I)

_REF_CSS_URL = re.compile(r'url\(\s*["\']?([^)"\']+?)["\']?\s*\)', re.I)

_SCHEMA_URL = re.compile(r'^[a-zA-Z][a-zA-Z0-9+.\-]*:')

def _est_reference_locale(ref):
    """Vrai si la référence désigne un fichier de CE site.

    Écartés : les ancres et la navigation par fragment (`#`, `#/panier`), les
    URL absolues et protocol-relative (`//cdn…`), et tout ce qui porte un
    schéma (`data:`, `mailto:`, `tel:`, `javascript:`, `http:`…).
    """
    ref = ref.strip()
    if not ref or ref.startswith(("#", "//")):
        return False
    return not _SCHEMA_URL.match(ref)

def _references_locales(frontend_dir):
    """Les fichiers locaux réclamés par le frontend, en couples (page, chemin).

    Ne lit que le HTML et le CSS : une URL construite en JavaScript ne se
    connaît qu'à l'exécution, et la deviner produirait des faux positifs — la
    couche jsdom, elle, éprouve déjà les `fetch()`.
    """
    trouvees, vues = [], set()
    for racine, _dirs, fichiers in os.walk(frontend_dir):
        for nom in sorted(fichiers):
            if not nom.lower().endswith((".html", ".htm", ".css")):
                continue
            plein = os.path.join(racine, nom)
            page = os.path.relpath(plein, frontend_dir).replace(os.sep, "/")
            with open(plein, encoding="utf-8", errors="ignore") as fh:
                contenu = fh.read()
            brutes = _REF_ATTRIBUT.findall(contenu) + _REF_CSS_URL.findall(contenu)
            for jeu in _REF_SRCSET.findall(contenu):
                brutes += [part.strip().split()[0]
                           for part in jeu.split(",") if part.strip()]
            for ref in brutes:
                if not _est_reference_locale(ref):
                    continue
                chemin = ref.strip().split("#", 1)[0].split("?", 1)[0]
                if not chemin.lower().endswith(EXTENSIONS_REFERENCEES):
                    continue
                if (page, chemin) not in vues:
                    vues.add((page, chemin))
                    trouvees.append((page, chemin))
    return trouvees

def _url_de_reference(page, chemin):
    """L'URL que le NAVIGATEUR demanderait, la page étant servie sous /site/.

    Une référence enracinée (`/photo.svg`) part à la racine du serveur, pas
    dans /site/ : c'est un vrai défaut, et le 404 le dira. On ne la réécrit
    pas — réécrire, c'est masquer.
    """
    if chemin.startswith("/"):
        return chemin
    resolu = posixpath.normpath(posixpath.join(posixpath.dirname(page), chemin))
    if resolu.startswith(".."):
        return None
    return "/site/" + resolu
