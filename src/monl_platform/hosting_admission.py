"""Bounded admission of hosted site processes.

Without a ceiling, a request on a project host started one more
`serve.py`, with no limit at all: as many Python processes as projects
visited, on a machine that already carries two per site. This module
decides WHO is allowed to run, and who gives up their place."""

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
    """Reads both ceilings together and falls back on any improper value.

    **Read ONCE, when the `SiteManager` is built**: changing the environment
    variable of a running server moves no ceiling, it must be restarted. It is
    the same rule as the other settings of `docs/EXPLOITATION.md`, and it is
    better than a per-request read, which would make an admission decision
    depend on the state of the environment at the exact moment of the call.
    Corollary for tests: set the environment BEFORE building the application,
    never after.

    An improper value (text, zero, negative) falls back on the default rather
    than making startup fail: a mistyped ceiling must not make the platform
    unable to start, whereas a default ceiling keeps it serving."""
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
    """Chooses the oldest site whose eviction resolves the reached ceiling.

    Returns `(candidate, ceiling_reached)`. A true `ceiling_reached` without a
    candidate means "every site in place is still serving": the caller then
    refuses, it does not evict at random.

    **The ACCOUNT's ceiling comes before the platform's**, and that is what
    makes the rest acceptable: an account never occupies more than
    `account_limit` places, so it cannot fill the platform on its own and
    cause the others to be evicted in a loop.

    **When the GLOBAL ceiling is reached, the candidate can belong to ANOTHER
    account.** A deliberate decision: a site inactive for five minutes is not
    deleted, it is stopped — the next request starts it again, at the cost of
    a startup. It is a replacement cache, not an eviction, and the per-account
    ceiling above bounds its abuse. The alternative — never touching a third
    party's site — would refuse an account because others left sleeping
    sites, which punishes the wrong one.

    Inactivity is a NECESSARY condition: a site that has served within the
    last five minutes is never stopped, even to make room."""
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
