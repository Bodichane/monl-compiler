"""Exécuter une table de cas dans UN test, sans qu'un cas cache les autres.

`@pytest.mark.parametrize` compte chaque ligne comme un test : 89 fonctions
de la suite en produisaient 370. Pour une vérification pure (aucun serveur,
aucun fichier ni réglage partagé entre les cas), c'est le même travail,
réparti sur autant d'items.

`verifier_chaque_cas` garde ce qui rend un paramétrage utile : TOUS les cas
s'exécutent, même après un échec, et le message nomme chaque cas fautif avec
sa cause. Il ne garde pas le compteur : un cas n'est pas un test.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence

import pytest


def verifier_chaque_cas(table: Iterable[tuple], verifier: Callable, *,
                        ids: Sequence[str] | None = None) -> None:
    """Appelle `verifier(*cas)` pour chaque tuple de `table`.

    Échoue UNE fois, à la fin, en listant chaque cas fautif. Une table vide
    échoue aussi : un test qui ne vérifie rien ne doit pas passer (point 161).
    Un `pytest.skip` dans un cas n'est PAS rattrapé : il sauterait tout le
    test, d'où le refus de convertir un corps qui en contient.
    """
    table = [tuple(cas) for cas in table]
    assert table, "table de cas vide : ce test ne vérifierait rien"
    if ids is not None:
        assert len(ids) == len(table), "un nom par cas"
    echecs = []
    for rang, cas in enumerate(table):
        try:
            verifier(*cas)
        except (Exception, pytest.fail.Exception) as exc:  # on agrège, on ne masque pas
            nom = ids[rang] if ids is not None else repr(cas)[:160]
            echecs.append(f"- {nom} : {type(exc).__name__}: {exc}")
    if echecs:
        pytest.fail(f"{len(echecs)}/{len(table)} cas en échec :\n" + "\n".join(echecs),
                    pytrace=False)
