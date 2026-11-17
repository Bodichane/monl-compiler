"""Arrêter un serveur de test lancé par `subprocess.Popen` : arrêter ET fermer.

`terminate()` puis `wait()` arrêtent le processus, mais un `stdout=PIPE` ou
`stderr=PIPE` laisse un descripteur ouvert que rien ne referme : il part au
ramasse-miettes (`ResourceWarning: unclosed file <_io.BufferedReader ...>`).
Le smoke test du code livré le ferme déjà (`smoke_test/__init__.py`) ; onze
fixtures de la suite ne le faisaient pas.
"""

from __future__ import annotations

import subprocess


def fermer_tubes(processus: subprocess.Popen) -> None:
    """Ferme les tubes encore ouverts, sans toucher au processus."""
    for tube in (processus.stdin, processus.stdout, processus.stderr):
        if tube is not None and not tube.closed:
            tube.close()


def arreter_processus(processus: subprocess.Popen, delai: float = 10) -> None:
    """`terminate`, attente bornée, `kill` en dernier recours, puis fermeture.

    Après un `kill`, on ATTEND encore : sans `wait`, le processus reste zombie
    et `Popen.__del__` le signale lui aussi.
    """
    if processus.poll() is None:
        processus.terminate()
        try:
            processus.wait(timeout=delai)
        except subprocess.TimeoutExpired:
            processus.kill()
            processus.wait()
    fermer_tubes(processus)
