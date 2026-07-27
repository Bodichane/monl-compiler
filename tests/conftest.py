"""Rend le paquet monl importable depuis les tests (point 65).

Avant : chaque fichier de tests commençait par un sys.path.insert vers
src/, suivi d'imports à plat marqués « noqa: E402 » — vingt fois la même
incantation, et un ordre d'instructions qui devait être respecté sous peine
d'ImportError. Le paquet a rendu l'incantation inutile ; ce fichier la
concentre au seul endroit où elle reste nécessaire, tant que le dépôt n'est
pas installé (`pip install -e .`) dans l'environnement qui lance pytest.
"""
import os
import sys

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)
