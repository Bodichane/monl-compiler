"""What the whole validator reads, and which reads nothing back.

This module is the package's LEAF: it imports no other `ast_validator`
module, and that is what makes an import cycle impossible. A test checks
it rather than leaving it to discipline."""


from ..errors import ValidationError

# Default folder for the assets supplied by the human (brick 13, point 83).
# OUTSIDE frontend/: that folder is renamed by 'monl frontend' on every build,
# and its allowlist does not accept .jpg -- so the photos dropped there ended
# up in frontend.precedent/ without a word.
DEFAULT_ASSETS_DIR = "assets"

# ---------------------------------------------------------------------------
# CHARGING CURRENCIES (brick 2a). The exponent is the currency's number of
# decimals: the provider expects an INTEGER in the minor unit, hence `amount ×
# 10**exponent`.
#
# The reason for this table fits in one example. The code hard-coded
# `int(round(amount * 100))` for every currency. The CFA franc (XOF) has NO
# subunit: an order of 5,000 FCFA would have gone to the provider as 500,000
# FCFA — a hundred times the price, without any test noticing, since the
# calculation is right for the euro. It is the point 77 family (the amount the
# client controls), through a door nobody had opened: UNITS.
#
# A currency ABSENT from this table is REFUSED, never guessed at 2 decimals.
# Guessing would bring back exactly the bug being closed: a unit defect does
# not show when reading, it shows on the bank statement.
#
# Three-decimal currencies (BHD, JOD, KWD, OMR, TND…) are deliberately absent:
# providers impose a special rounding on them (amounts in multiples of 10 at
# Stripe), and a brick that ignored it would be wrong in an even more discreet
# way. Refusing them and SAYING so is better than half accepting them.
DEVISES = {
    # No subunit — the case that motivated the brick.
    "XOF": 0,  # CFA franc (WAEMU: Benin, Côte d'Ivoire, Senegal, Togo…)
    "XAF": 0,  # franc CFA (CEMAC)
    "XPF": 0,  # franc Pacifique
    "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "JPY": 0, "KMF": 0,
    "KRW": 0, "PYG": 0, "RWF": 0, "UGX": 0, "VND": 0, "VUV": 0,
    # Two decimals.
    "EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "CAD": 2,
    "MAD": 2, "NGN": 2, "GHS": 2, "KES": 2, "ZAR": 2,
}

CURRENCY_DEFAULT = "EUR"

# ---------------------------------------------------------------------------
# PAYMENT PROVIDERS (brick 2b). Stripe does not operate in West Africa; money
# there goes through mobile money (MTN MoMo, Moov, Wave) behind an aggregator.
# FedaPay is the first one added: its server flow and its webhook verification
# are documented, and the cryptographic recipe was reread in its official SDK
# rather than inferred from prose.
#
# What is deliberately ABSENT: KKiaPay. Its public documentation exposes a
# browser widget, with no server endpoint to create a session, and publishes
# neither the algorithm nor the signed data of its webhook header. Building
# that check by analogy with Stripe or FedaPay would not be an approximation:
# it would be a security hole in the only place in the generated backend where
# an unauthenticated third party writes to the database. It is therefore
# refused and the refusal SAYS so, rather than implemented roughly.
PROVIDERS = {"stripe", "fedapay"}
PROVIDER_DEFAULT = "stripe"

# Providers known but deliberately not implemented, with the reason — the
# message is better than "unknown provider", which would send people looking
# for a typo in a perfectly correct name.
PROVIDERS_DISCARDED = {
    "kkiapay": ("its public documentation gives neither the algorithm nor the "
                "signed data of its webhook; monl will not guess a signature "
                "check"),
    "cinetpay": ("its webhook requires revalidation through a second call, not "
                 "written yet, and its sandboxes are announced as "
                 "unavailable"),
}

# CURRENCIES EACH PROVIDER CAN REALLY CHARGE. `None` = no known restriction,
# hence no guard: better to assert nothing than to assert something false.
#
# FedaPay settles ONLY IN CFA FRANCS (WAEMU) — its own documentation says so
# unambiguously ("For now, Fedapay allows you to only use the XOF currency
# (CFA) for your various transactions"), and its official Odoo module only
# declares `SUPPORTED_CURRENCIES = ['XOF']`. Without this table, `provider:
# fedapay` + `currency: EUR` COMPILES and cannot work: the author only learns
# it at the first real charge, as a 502, in front of a customer who wanted to
# pay. It is point 85 applied to the outside world — refuse a configuration
# with no effect rather than let it through.
CURRENCIES_BY_PROVIDER = {
    "fedapay": {"XOF"},
    "stripe": None,
}


class ASTValidationError(ValidationError):
    pass
