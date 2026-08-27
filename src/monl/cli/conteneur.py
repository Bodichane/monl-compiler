"""Ce qu'un projet emporte pour tourner ailleurs."""

import os

from ..serving import rendre_wrapper
from . import nomenclature


def _ensure_container_artifacts(staging_dir, uploads=False):
    """Émet les gabarits de conteneur sans écraser ceux de l'auteur."""
    dockerfile = nomenclature.DEFAULT_DOCKERFILE
    dockerignore = nomenclature.DEFAULT_DOCKERIGNORE
    if uploads:
        dockerfile = dockerfile.replace(
            "    'PyJWT>=2.8,<3.0'\n",
            "    'PyJWT>=2.8,<3.0' " + "\\\n"
            "    'python-multipart>=0.0.9,<1.0'\n",
        )
        dockerignore += ".monl_uploads/\n"
    defaults = {
        "Dockerfile": dockerfile,
        ".dockerignore": dockerignore,
    }
    for name, content in defaults.items():
        path = os.path.join(staging_dir, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
            continue
        # Un gabarit émis lors d'une compilation antérieure se rafraîchit ;
        # un fichier Docker réellement personnalisé reste, lui, sous la
        # responsabilité de l'auteur.
        with open(path, encoding="utf-8") as fh:
            actuel = fh.read()
        if name == "Dockerfile":
            # `content` est le gabarit courant, Upload appliqué ou non : les
            # DEUX formes courantes doivent être reconnues comme « jamais
            # touchées », sinon une spec qui perd son Upload garderait la
            # dépendance devenue inutile.
            connus = (nomenclature.DEFAULT_DOCKERFILE, content, *nomenclature.DOCKERFILES_HERITES)
        else:
            connus = (nomenclature.DEFAULT_DOCKERIGNORE,)
        if actuel in connus and actuel != content:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)

def _emettre_wrapper(staging_dir, contract):
    """Écrit serve.py DÈS LA COMPILATION, et non plus au seul 'monl run'.

    POINT 133. Le Dockerfile produit par 'monl compile' lançait `app:app` :
    l'image servait l'API et répondait 404 sur /site et sur les photos, parce
    que le wrapper qui les monte n'était écrit que par 'monl run'. Un produit
    dont l'argument est « un site livré » livrait donc une API sans site.
    Vérifié en construisant réellement l'image, pas en relisant le code.

    Le dossier d'assets vient du CONTRAT, déjà dérivé de la spec et vérifié
    cohérent avec elle — relire la spec ici ferait un second parseur à faire
    dériver (même raison qu'`_assets_dir_du_projet`, dont ceci est le pendant
    à la compilation).

    Écrit sans condition : c'est du code généré, pas un gabarit que l'auteur
    adapte. Le Dockerfile, lui, reste éditable — d'où deux traitements.
    """
    assets_dir = (contract.get("assets") or {}).get("dir") or None
    with open(os.path.join(staging_dir, "serve.py"), "w", encoding="utf-8") as fh:
        fh.write(rendre_wrapper(assets_dir))
