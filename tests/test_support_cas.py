"""`verifier_chaque_cas` porte la garantie qu'apportait `parametrize` : un cas
en échec ne cache jamais les suivants, et chaque cas fautif est nommé.

Quarante fonctions de la suite en dépendent ; s'il s'arrêtait au premier échec
ou passait sur une table vide, elles vérifieraient moins sans rougir.
"""
import pytest

from tests.support.cas import verifier_chaque_cas


def test_tous_les_cas_s_executent_et_chaque_echec_est_nomme():
    vus = []

    def cas(n):
        vus.append(n)
        assert n % 2 == 0, f"{n} est impair"
        if n == 4:
            pytest.fail("échec explicite sur 4")

    with pytest.raises(pytest.fail.Exception) as echec:
        verifier_chaque_cas([(1,), (2,), (3,), (4,), (6,)], cas,
                            ids=["un", "deux", "trois", "quatre", "six"])
    assert vus == [1, 2, 3, 4, 6], "un échec a interrompu les cas suivants"
    message = str(echec.value)
    assert "3/5 cas en échec" in message
    for nom in ("un", "trois", "quatre"):
        assert f"- {nom} :" in message
    for nom in ("deux", "six"):
        assert f"- {nom} :" not in message


def test_une_table_vide_ne_passe_pas():
    with pytest.raises(AssertionError, match="vide"):
        verifier_chaque_cas([], lambda: None)


def test_une_table_saine_passe_et_deballe_chaque_tuple():
    recus = []
    verifier_chaque_cas([(1, "a"), (2, "b")], lambda n, s: recus.append((n, s)))
    assert recus == [(1, "a"), (2, "b")]
