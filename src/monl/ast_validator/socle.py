"""Ce que tout le validateur lit, et qui ne lit rien en retour.

Ce module est la FEUILLE du paquet : il n'importe aucun autre module
d'`ast_validator`, et c'est ce qui rend un cycle d'import impossible.
Un test le vérifie plutôt que de le laisser à la discipline."""


from ..errors import ValidationError

# Dossier par défaut des assets fournis par l'humain (brique 13, point 83).
# HORS de frontend/ : ce dossier-là est renommé par 'monl frontend' à chaque
# construction, et sa liste blanche n'accepte pas les .jpg -- les photos qu'on y
# déposait finissaient donc dans frontend.precedent/ sans un mot.
DEFAULT_ASSETS_DIR = "assets"

# ---------------------------------------------------------------------------
# DEVISES D'ENCAISSEMENT (brique 2a). L'exposant est le nombre de décimales de
# la devise : le prestataire attend un ENTIER dans l'unité mineure, donc
# `montant × 10**exposant`.
#
# La raison d'être de cette table tient en un exemple. Le code figeait
# `int(round(montant * 100))` pour toute devise. Le franc CFA (XOF) n'a AUCUNE
# sous-unité : une commande de 5 000 FCFA serait partie chez le prestataire
# pour 500 000 FCFA — cent fois le prix, sans qu'aucun test ne s'en aperçoive,
# puisque le calcul est juste pour l'euro. C'est la famille du point 77 (le
# montant que le client contrôle), par une porte que personne n'avait ouverte :
# celle des UNITÉS.
#
# Une devise ABSENTE de cette table est REFUSÉE, jamais devinée à 2 décimales.
# Deviner, c'est reprendre exactement le bug qu'on ferme : un défaut d'unité ne
# se voit pas à la lecture, il se voit sur le relevé bancaire.
#
# Les devises à TROIS décimales (BHD, JOD, KWD, OMR, TND…) sont volontairement
# absentes : les prestataires y imposent un arrondi particulier (montants
# multiples de 10 chez Stripe), et une brique qui l'ignorerait serait fausse
# d'une façon plus discrète encore. Les refuser en le DISANT vaut mieux que les
# accepter à moitié.
DEVISES = {
    # Sans sous-unité — c'est le cas qui a motivé la brique.
    "XOF": 0,  # franc CFA (UEMOA : Bénin, Côte d'Ivoire, Sénégal, Togo…)
    "XAF": 0,  # franc CFA (CEMAC)
    "XPF": 0,  # franc Pacifique
    "BIF": 0, "CLP": 0, "DJF": 0, "GNF": 0, "JPY": 0, "KMF": 0,
    "KRW": 0, "PYG": 0, "RWF": 0, "UGX": 0, "VND": 0, "VUV": 0,
    # Deux décimales.
    "EUR": 2, "USD": 2, "GBP": 2, "CHF": 2, "CAD": 2,
    "MAD": 2, "NGN": 2, "GHS": 2, "KES": 2, "ZAR": 2,
}

DEVISE_PAR_DEFAUT = "EUR"

# ---------------------------------------------------------------------------
# PRESTATAIRES D'ENCAISSEMENT (brique 2b). Stripe n'opère pas en Afrique de
# l'Ouest ; l'argent y passe par le mobile money (MTN MoMo, Moov, Wave)
# derrière un agrégateur. FedaPay est le premier ajouté : son flux serveur et
# sa vérification de webhook sont documentés, et la recette cryptographique a
# été relue dans son SDK officiel plutôt que déduite d'une prose.
#
# Ce qui est délibérément ABSENT : KKiaPay. Sa documentation publique expose un
# widget navigateur, sans endpoint serveur de création de session, et ne publie
# ni l'algorithme ni les données signées de son en-tête de webhook. Construire
# cette vérification par analogie avec Stripe ou FedaPay ne serait pas une
# approximation : ce serait un trou de sécurité à l'unique endroit du backend
# généré où un tiers non authentifié écrit en base. Il est donc refusé EN LE
# DISANT, plutôt qu'implémenté à peu près.
PRESTATAIRES = {"stripe", "fedapay"}
PRESTATAIRE_PAR_DEFAUT = "stripe"

# Prestataires connus mais volontairement non implémentés, avec la raison —
# le message vaut mieux que « prestataire inconnu », qui enverrait chercher
# une faute de frappe dans un nom parfaitement correct.
PRESTATAIRES_ECARTES = {
    "kkiapay": ("sa documentation publique ne donne ni l'algorithme ni les "
                "données signées de son webhook ; monl ne devinera pas une "
                "vérification de signature"),
    "cinetpay": ("son webhook exige une revalidation par un second appel, non "
                 "encore écrite, et ses bacs à sable sont annoncés "
                 "indisponibles"),
}

# DEVISES RÉELLEMENT ENCAISSABLES PAR PRESTATAIRE. `None` = pas de restriction
# connue, donc aucune garde : mieux vaut ne rien affirmer que d'affirmer faux.
#
# FedaPay ne règle QU'EN FRANC CFA (UEMOA) — sa propre documentation le dit
# sans ambiguïté (« For now, Fedapay allows you to only use the XOF currency
# (CFA) for your various transactions »), et son module Odoo officiel ne
# déclare que `SUPPORTED_CURRENCIES = ['XOF']`. Sans cette table,
# `provider: fedapay` + `currency: EUR` COMPILE et ne peut pas fonctionner :
# l'auteur ne l'apprend qu'au premier vrai encaissement, en 502, devant un
# client qui voulait payer. C'est le point 85 appliqué au monde extérieur —
# refuser une configuration sans effet plutôt que la laisser passer.
DEVISES_PAR_PRESTATAIRE = {
    "fedapay": {"XOF"},
    "stripe": None,
}


class ASTValidationError(ValidationError):
    pass
