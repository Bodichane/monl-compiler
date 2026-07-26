#!/usr/bin/env python3
"""Point d'entrée console pour l'installation en mode editable (`pip install -e .`).

Conserve la structure « src plat » actuelle : on ajoute simplement 'src/' au
chemin d'import avant de déléguer au CLI orchestrateur. En mode editable, le code
reste dans l'arbre source, donc ce fichier voisin de 'src/' résout correctement.

Passage à un vrai paquet Python installable (imports en package) : chantier GA,
voir docs/BETA.md.
"""
import os
import sys


def main():
    src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from cli import main as _cli_main
    _cli_main()


if __name__ == "__main__":
    main()
