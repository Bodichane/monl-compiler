"""Admission bornée des processus de sites hébergés.

Sans plafond, une requête sur un hôte de projet démarrait un `serve.py` de
plus, sans aucune limite : autant de processus Python que de projets visités,
sur une machine qui en porte déjà deux par site. Ce module décide QUI a le
droit de tourner, et qui cède sa place.
"""

import os

DEFAULT_MAX_RUNNING_SITES = 20
DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT = 3
SITE_INACTIVITY_SECONDS = 300
MAX_RUNNING_SITES_ENV = "MONL_MAX_RUNNING_SITES"
MAX_RUNNING_SITES_PER_ACCOUNT_ENV = "MONL_MAX_RUNNING_SITES_PER_ACCOUNT"


def _positive_integer(value, default):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def hosting_limits():
    """Lit les deux plafonds ensemble et replie toute valeur impropre.

    **Lu UNE fois, à la construction du `SiteManager`** : changer la variable
    d'environnement d'un serveur en marche ne déplace aucun plafond, il faut le
    redémarrer. C'est la même règle que les autres réglages de
    `docs/EXPLOITATION.md`, et elle vaut mieux qu'une lecture par requête, qui
    ferait dépendre une décision d'admission de l'état de l'environnement au
    moment exact de l'appel. Corollaire pour les tests : poser l'environnement
    AVANT de construire l'application, jamais après.

    Une valeur impropre (texte, zéro, négatif) replie sur le défaut plutôt que
    de faire échouer le démarrage : un plafond mal tapé ne doit pas rendre la
    plateforme indémarrable, alors qu'un plafond par défaut la garde servante.
    """
    return (
        _positive_integer(
            os.environ.get(MAX_RUNNING_SITES_ENV, str(DEFAULT_MAX_RUNNING_SITES)),
            DEFAULT_MAX_RUNNING_SITES,
        ),
        _positive_integer(
            os.environ.get(
                MAX_RUNNING_SITES_PER_ACCOUNT_ENV,
                str(DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT),
            ),
            DEFAULT_MAX_RUNNING_SITES_PER_ACCOUNT,
        ),
    )


def eviction_candidate(running, user_id, now, global_limit, account_limit):
    """Choisit le plus ancien site dont l'éviction résout le plafond atteint.

    Rend `(candidat, plafond_atteint)`. Un `plafond_atteint` vrai sans candidat
    signifie « tous les sites en place servent encore » : l'appelant refuse
    alors, il n'évince pas au hasard.

    **Le plafond du COMPTE passe avant celui de la plateforme**, et c'est ce
    qui rend le reste acceptable : un compte n'occupe jamais plus de
    `account_limit` places, donc il ne peut pas remplir la plateforme à lui
    seul et provoquer l'éviction des autres en boucle.

    **Quand le plafond GLOBAL est atteint, le candidat peut appartenir à un
    AUTRE compte.** Décision assumée : un site inactif depuis cinq minutes
    n'est pas supprimé, il est arrêté — la requête suivante le relance, au prix
    d'un démarrage. C'est un cache à remplacement, pas une expulsion, et le
    plafond par compte ci-dessus en borne l'abus. L'alternative — ne jamais
    toucher au site d'un tiers — ferait refuser un compte parce que d'autres
    ont laissé des sites endormis, ce qui punit le mauvais.

    L'inactivité est une condition NÉCESSAIRE : on n'arrête jamais un site qui
    a servi dans les cinq dernières minutes, même pour faire de la place.
    """
    live = list(running.values())
    same_account = [site for site in live if site.user_id == user_id]
    if len(same_account) >= account_limit:
        pool = same_account
    elif len(live) >= global_limit:
        pool = live
    else:
        return None, False
    inactive = [
        site for site in pool
        if now - site.last_activity >= SITE_INACTIVITY_SECONDS
    ]
    if not inactive:
        return None, True
    return min(inactive, key=lambda site: site.last_activity), True
