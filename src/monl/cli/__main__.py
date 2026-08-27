"""`python -m monl.cli`.

Remplace le `if __name__ == "__main__"` que portait le module d'origine :
un paquet ne peut pas s'exécuter par son `__init__`. Le point d'entrée
installé reste `monl = monl.cli:main` (pyproject.toml)."""

from . import main

if __name__ == "__main__":
    raise SystemExit(main())
